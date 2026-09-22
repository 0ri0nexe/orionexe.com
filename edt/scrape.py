#!/usr/bin/env python3
"""
Fetches the timetable from IMT's Alcuin OpenPortal (si-etudiants.imtbs-tsp.eu)
and writes it to schedule.json, consumed by the static frontend (index.html).

Credentials: EDT_USER / EDT_PASS environment variables, otherwise prompted for.

    EDT_USER='<your-login>' EDT_PASS='...' python3 scrape.py --from 2026-09 --to 2027-07
"""
import argparse
import getpass
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://si-etudiants.imtbs-tsp.eu"
LOGIN = f"{BASE}/OpDotNet/Noyau/Login.aspx?auth=SAMLv2ProviderConfiguration"
# The agenda module is a classic ASP app: it is reached through a bridge from ASP.NET
AGENDA_BRIDGE = (
    f"{BASE}/OpDotnet/commun/Login/aspxtoasp.aspx"
    "?url=/Eplug/Agenda/Agenda.asp?IdApplication=190&TypeAcces=Utilisateur&IdLien=304&groupe=843"
)
AGENDA = f"{BASE}/Eplug/Agenda/Agenda.asp"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
REQUEST_TIMEOUT = (10, 30)  # (connect, read), in seconds


# --------------------------------------------------------------------------- HTTP

class TimeoutSession(requests.Session):
    """Session with a default timeout.

    requests sets none: without this, a portal that accepts the connection but
    never answers freezes the hourly run forever.
    """

    def __init__(self, timeout=REQUEST_TIMEOUT):
        super().__init__()
        self.timeout = timeout

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        return super().request(method, url, **kwargs)


def new_session():
    s = TimeoutSession()
    s.headers.update({"User-Agent": UA})
    return s


def submit_form(session, response, extra=None, form_id=None):
    """Replays an HTML form (SAML auto-submit, CAS form, ASP bridge...)."""
    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form", id=form_id) if form_id else soup.find("form")
    if form is None:
        raise RuntimeError(f"no form found on {response.url}")

    action = form.get("action")
    url = urljoin(response.url, action) if action else response.url
    # a relative action ("login") loses the query string CAS needs
    if action and not urlparse(action).query and urlparse(response.url).query \
            and urlparse(url).path == urlparse(response.url).path:
        url = response.url

    data = {}
    for field in form.find_all("input"):
        name = field.get("name")
        if name and (field.get("type") or "text").lower() != "submit":
            data[name] = field.get("value", "")
    if extra:
        data.update(extra)
    return session.post(url, data=data)


def login(session, user, password):
    """SAML SP -> Shibboleth IdP -> CAS -> consent -> back to the portal."""
    r = session.get(LOGIN)
    r = submit_form(session, r, form_id="samlform")                       # -> IdP
    r = submit_form(session, r, {"shib_idp_ls_supported": "",             # localStorage probe
                                 "_eventId_proceed": ""})                 # -> CAS
    r = submit_form(session, r, {"username": user, "password": password,
                                 "_eventId": "submit",
                                 "geolocation": "", "deviceFingerprint": ""})

    for _ in range(5):
        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form")
        if form is None:
            break
        names = {i.get("name") for i in form.find_all("input")}
        if "SAMLResponse" in names:
            r = submit_form(session, r)                                   # -> portal ACS
            break
        if "username" in names and "password" in names:
            raise SystemExit("Login failed: credentials rejected by CAS.")
        r = submit_form(session, r, {"_eventId_proceed": ""})             # consent

    if "si-etudiants" not in r.url:
        raise SystemExit(f"Incomplete login, landed on {r.url}")
    return r


def fetch_identity(session):
    """Display name and current space, read from the portal banner."""
    r = session.get(f"{BASE}/OpDotNet/Noyau/Bandeau.aspx")
    soup = BeautifulSoup(r.text, "html.parser")

    def text(el_id):
        el = soup.find(id=el_id)
        return el.get_text(" ", strip=True) if el else ""

    name = " ".join(filter(None, [text("lblCurrentUserSurname"), text("lblCurrentUserName")]))
    space = re.sub(r"^Mon espace\s*:\s*", "", text("lblEspaces")).strip()
    return {"name": name, "space": space}


def connect(user, password, attempts=4, backoff=20):
    """Opens a session ready to query the agenda.

    The portal sometimes returns a page with no form, or drops the connection —
    it visibly throttles when logins come back to back. An unattended hourly run
    must not die on a hiccup, hence the generous waits (20s, 40s, 60s). Rejected
    credentials, on the other hand, are not worth retrying.
    """
    last = None
    for attempt in range(1, attempts + 1):
        session = new_session()
        try:
            login(session, user, password)
            identity = fetch_identity(session)
            return session, identity, open_agenda(session)
        except SystemExit:
            raise
        except (requests.RequestException, RuntimeError) as exc:
            last = exc
            if attempt < attempts:
                wait = backoff * attempt
                print(f"Login failed ({exc}) — retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise SystemExit(f"Could not log in after {attempts} attempts: {last}")


def open_agenda(session):
    """Crosses the ASP.NET -> ASP bridge and returns the agenda HTML."""
    r = session.get(AGENDA_BRIDGE)
    r = submit_form(session, r)
    if "Agenda.asp" not in r.url:
        raise SystemExit(f"Could not open the agenda (landed on {r.url})")
    return r.text


def serialize_form(page_html):
    """Serializes the agenda form the way a browser would.

    The EtaFil/TypFil filters are checkbox groups: sending a single value per
    name empties the calendar server-side.
    """
    form = BeautifulSoup(page_html, "html.parser").find("form", {"name": "formul"})
    if form is None:
        raise RuntimeError("form 'formul' not found: agenda session lost?")
    fields = []
    for el in form.find_all(["input", "select"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "select":
            opt = el.find("option", attrs={"Selected": "true"}) or el.find("option", selected=True)
            fields.append((name, opt.get("value") if opt else ""))
            continue
        kind = (el.get("type") or "text").lower()
        if kind in ("checkbox", "radio"):
            if el.has_attr("checked"):
                fields.append((name, el.get("value", "on")))
        elif kind != "submit":
            fields.append((name, el.get("value", "")))
    return fields


def fetch_view(session, page_html, yyyymmdd, typvis):
    fields = [(k, yyyymmdd if k == "NumDat" else (typvis if k == "TypVis" else v))
              for k, v in serialize_form(page_html)]
    r = session.post(AGENDA, data=fields, headers={"Referer": AGENDA})
    return r.text


def fetch_month(session, page_html, yyyymmdd):
    """'Table' view (Vis-Tab.xsl): a whole month of events in one request."""
    return fetch_view(session, page_html, yyyymmdd, "Vis-Tab.xsl")


def fetch_week_ids(session, page_html, yyyymmdd):
    """Event ids for the week, by day and in chronological order.

    The monthly view sometimes confuses two twin slots (same course, same time,
    different groups) and returns the one belonging to another group. The weekly
    view is the personal agenda: it is authoritative on *which* slot is ours.
    Since it renders by hour then by day, document order directly gives the
    chronological order within a day.
    """
    html_text = fetch_view(session, page_html, yyyymmdd, "Vis-Sem.xsl")
    by_day = {}
    for event_id, raw_day in re.findall(r"DetEve\('(\d+)'[^)]*'(\d{8})'\)", html_text):
        day = f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:]}"
        by_day.setdefault(day, []).append(event_id)
    return by_day


# --------------------------------------------------------------------------- parsing

def parse_month(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    view = soup.find(id="DivVis")
    if view is None:
        return []

    table = None
    for candidate in view.find_all("table"):
        rows = candidate.find_all("tr")
        if rows and "Titre" in [c.get_text(strip=True) for c in rows[0].find_all(["td", "th"])]:
            table = candidate
            break
    if table is None:
        return []

    events = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        ids = re.findall(r"DetEve\('(\d+)'", str(row))
        text = [c.get_text(" ", strip=True) for c in cells]
        day = parse_date(text[4])
        if not day:
            continue
        events.append({
            "id": ids[0] if ids else None,
            "title": text[1],
            "type": text[2],
            "status": text[3],
            "date": day,
            "start": parse_time(text[5]),
            "end": parse_time(text[6]),
            "description": text[7] if len(text) > 7 else "",
        })
    return events


def parse_date(raw):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def last_of_month(ym):
    year, month = ym
    return date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)


def parse_iso(iso):
    return date(*(int(p) for p in iso.split("-")))


def parse_time(raw):
    m = re.search(r"(\d{1,2})\s*[h:]\s*(\d{2})", raw or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


# The detail comes wrapped in parent.MajDet('<table>...</table>')
DETAIL_RE = re.compile(r"parent\.MajDet\('(.*)'\);", re.S)


def fetch_detail(session, event_id, day):
    """Fetches room / teachers / group, which the table view omits."""
    src = day.replace("-", "") if day else ""
    r = session.get(f"{BASE}/Eplug/Agenda/Eve-Det.asp",
                    params={"NumEve": event_id, "DatSrc": src, "NomCal": ""})
    m = DETAIL_RE.search(r.text)
    if not m:
        return {}

    fragment = m.group(1).replace("\\/", "/").replace("\\'", "'").replace("\\\\", "\\")
    soup = BeautifulSoup(fragment, "html.parser")

    detail = {}
    # rooms are the only VisRes(...) links
    rooms = [a.get_text(" ", strip=True) for a in soup.find_all("a")
             if "VisRes(" in (a.get("onclick") or "")]
    if rooms:
        detail["room"] = ", ".join(dict.fromkeys(rooms))

    # the other fields are <td><b>Label</b> :</td><td>value</td> pairs
    for label in soup.find_all("b"):
        key = label.get_text(strip=True).rstrip(" :")
        cell = label.find_parent("td")
        value_cell = cell.find_next_sibling("td") if cell else None
        if value_cell is None:
            continue
        value = value_cell.get_text(", ", strip=True)
        if not value:
            continue
        if re.search(r"Formateur", key):
            detail["teachers"] = value
        elif re.search(r"Organisme", key):
            detail["group"] = value
        elif key == "Projets":
            detail["course"] = value
    return detail


# --------------------------------------------------------------------------- driver

def reconcile_ids(events, week_ids):
    """Aligns slot ids with those of the personal agenda.

    Both views list a day in the same chronological order; we only rewrite when
    the counts match, so as to invent nothing.
    """
    by_day = {}
    for ev in events:
        by_day.setdefault(ev["date"], []).append(ev)

    fixed, skipped = 0, 0
    for day, day_events in by_day.items():
        expected = week_ids.get(day)
        if not expected:
            continue
        day_events.sort(key=lambda e: e["start"] or "")
        if len(expected) != len(day_events):
            skipped += 1
            continue
        for ev, event_id in zip(day_events, expected):
            if ev["id"] != event_id:
                ev["id"] = event_id
                fixed += 1
    return fixed, skipped


def mondays_between(first_day, last_day):
    cur = first_day - timedelta(days=first_day.weekday())
    while cur <= last_day:
        yield cur.strftime("%Y%m%d")
        cur += timedelta(days=7)


DETAIL_FIELDS = ("room", "teachers", "course", "group")


def load_previous(path):
    """Previous contents of --out, or None. Used as the base for --merge mode."""
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload.get("events"), list) else None


def detail_cache(previous):
    """Details already known, indexed by event id.

    Room and teacher do not change as long as the id does not: reusing them
    avoids one request per slot on every cron run.
    """
    cache = {}
    for ev in previous["events"]:
        if not ev.get("id"):
            continue
        known = {k: ev[k] for k in DETAIL_FIELDS if ev.get(k)}
        if known:
            cache[ev["id"]] = known
    return cache


def merge_events(previous, fresh, first_day, last_day):
    """Replaces the [first_day, last_day] window with `fresh`, keeps the rest."""
    kept = [ev for ev in previous["events"]
            if not (first_day <= parse_iso(ev["date"]) <= last_day)]
    return kept + fresh


def months_between(start, end):
    y, m = start
    while (y, m) <= end:
        yield f"{y:04d}{m:02d}01"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def parse_month_arg(value, fallback):
    if not value:
        return fallback
    try:
        d = datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise SystemExit(f"Invalid month format: {value!r} (expected YYYY-MM)")
    return (d.year, d.month)


def main():
    today = date.today()
    ap = argparse.ArgumentParser(description="Fetches the IMT timetable into schedule.json")
    ap.add_argument("--from", dest="start", help="first month (YYYY-MM)")
    ap.add_argument("--to", dest="end", help="last month (YYYY-MM)")
    ap.add_argument("--out", default="schedule.json", help="output file")
    ap.add_argument("--no-details", action="store_true",
                    help="skip rooms/teachers (much faster)")
    ap.add_argument("--delay", type=float, default=0.15,
                    help="pause between two detail requests (seconds)")
    ap.add_argument("--merge", action="store_true",
                    help="merge into the existing --out: only re-downloads the requested "
                         "period and reuses details already known (cron mode)")
    args = ap.parse_args()

    start = parse_month_arg(args.start, (today.year, today.month))
    end = parse_month_arg(args.end, (start[0] + (1 if start[1] > 7 else 0), 7))
    if end < start:
        raise SystemExit("--to is earlier than --from")

    previous = load_previous(args.out) if args.merge else None
    known_details = detail_cache(previous) if previous else {}

    user = os.environ.get("EDT_USER") or input("Username: ").strip()
    password = os.environ.get("EDT_PASS") or getpass.getpass("Password: ")

    print("Connecting to the portal...", file=sys.stderr)
    session, identity, page = connect(user, password)
    print(f"Connected: {identity['name'] or user} ({identity['space']})", file=sys.stderr)

    events, seen = [], set()
    for numdat in months_between(start, end):
        label = f"{numdat[:4]}-{numdat[4:6]}"
        month_events = parse_month(fetch_month(session, page, numdat))
        fresh = 0
        for ev in month_events:
            key = (ev["id"], ev["date"], ev["start"])
            if key in seen:
                continue
            seen.add(key)
            events.append(ev)
            fresh += 1
        print(f"  {label}: {fresh} event(s)", file=sys.stderr)

    # cross-check against the personal agenda before fetching the details
    if events:
        first = min(parse_iso(e["date"]) for e in events)
        last = max(parse_iso(e["date"]) for e in events)
        week_ids = {}
        for monday in mondays_between(first, last):
            week_ids.update(fetch_week_ids(session, page, monday))
        fixed, skipped = reconcile_ids(events, week_ids)
        if fixed:
            print(f"{fixed} slot(s) reassigned to the right group", file=sys.stderr)
        if skipped:
            print(f"{skipped} day(s) not reconciled (counts differ)", file=sys.stderr)

    if not args.no_details:
        todo = [ev for ev in events if ev["id"] and ev["id"] not in known_details]
        for ev in events:
            if ev["id"] in known_details:
                ev.update(known_details[ev["id"]])
        print(f"Details: {len(todo)} to fetch, "
              f"{len(events) - len(todo)} already known", file=sys.stderr)
        for i, ev in enumerate(todo, 1):
            try:
                ev.update(fetch_detail(session, ev["id"], ev["date"]))
            except requests.RequestException as exc:
                print(f"  detail {ev['id']} skipped: {exc}", file=sys.stderr)
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}", file=sys.stderr)
            time.sleep(args.delay)

    scraped_range = {"from": f"{start[0]:04d}-{start[1]:02d}", "to": f"{end[0]:04d}-{end[1]:02d}"}

    if previous:
        window_start = date(start[0], start[1], 1)
        window_end = last_of_month(end)
        before = len(events)
        events = merge_events(previous, events, window_start, window_end)
        print(f"Merge: {before} refreshed, "
              f"{len(events) - before} kept outside the window", file=sys.stderr)
        scraped_range = {
            "from": min(previous.get("range", {}).get("from", scraped_range["from"]),
                        scraped_range["from"]),
            "to": max(previous.get("range", {}).get("to", scraped_range["to"]),
                      scraped_range["to"]),
        }

    events.sort(key=lambda e: (e["date"], e["start"] or ""))
    payload = {
        "student": identity,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "range": scraped_range,
        "events": events,
    }
    # atomic write: the web server must never read a truncated JSON
    tmp = f"{args.out}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, args.out)
    print(f"{len(events)} events written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
