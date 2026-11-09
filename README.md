# orionexe

Personal site. SvelteKit 2 + Svelte 5 (runes) + TailwindCSS 4, fully prerendered to
static HTML and served by Caddy on a VPS.

## Local development

```sh
npm install
npm run dev        # http://localhost:5173
```

| Script            | What it does                                |
| ----------------- | ------------------------------------------- |
| `npm run dev`     | Dev server with HMR                         |
| `npm run build`   | Prerender the whole site into `build/`      |
| `npm run preview` | Serve `build/` locally, as production would |
| `npm run check`   | `svelte-check` type checking                |
| `npm run lint`    | Prettier check + ESLint                     |
| `npm run format`  | Rewrite files with Prettier                 |
| `npm run deploy`  | Build and ship to the VPS                   |

## Deployment

The site is static: Caddy serves files off disk, there is no Node process in
production. A deploy uploads a new timestamped release and flips a symlink.

```
/srv/orionexe/
├── current -> releases/20260921134500     # atomic symlink, Caddy's root
└── releases/
    ├── 20260921134500/
    └── ...                                 # last 5 kept
```

### First time only

Copy `.env.example` to `.env` and fill in `REMOTE_USER` / `REMOTE_HOST` — the
scripts read them from there, so the repo names no host. Then install your SSH
key on the server and provision it:

```sh
ssh-copy-id "$REMOTE_USER@$REMOTE_HOST"
./scripts/provision.sh
```

`provision.sh` creates `/srv/orionexe`, installs [`deploy/Caddyfile`](deploy/Caddyfile)
to `/etc/caddy/sites/orionexe.com.caddy`, makes the main Caddyfile import that
directory, validates the config and reloads Caddy. It is idempotent — re-run it
after any change to `deploy/Caddyfile`.

### Every time after that

```sh
npm run deploy
```

Build → rsync → symlink swap → HTTP check. No downtime; requests are served
either the old release or the new one, never a partial upload.

### Rollback

```sh
./scripts/rollback.sh --list    # what is on the server
./scripts/rollback.sh           # back to the previous release
./scripts/rollback.sh 20260921134500
```

### Overrides

All scripts source `.env`, then read these environment variables:

| Variable      | Default                 |
| ------------- | ----------------------- |
| `REMOTE_USER` | _required, from `.env`_ |
| `REMOTE_HOST` | _required, from `.env`_ |
| `APP_DIR`     | `/srv/orionexe`         |
| `SITE_URL`    | `https://orionexe.com`  |

## Timetable (`/edt/`)

`/edt/` shows my IMT timetable. The page is prerendered like everything else and
fetches its data client-side from `/edt/schedule.json`.

That JSON is **not** part of a release. It is written hourly on the VPS by
`edt/scrape.py`, which logs into the school portal (SAML → Shibboleth → CAS) and
scrapes the agenda module. It lives in `/srv/orionexe/shared/edt/`, outside
`releases/`, so a deploy never overwrites it and the cron never fights a deploy.

```
/srv/orionexe/
├── current -> releases/...        # Caddy's root
├── shared/edt/schedule.json       # rewritten hourly, served at /edt/schedule.json
└── edt/                           # scraper, venv, .env (mode 600), refresh.log
```

The page and the JSON are both behind HTTP basic auth — the timetable carries my
name, my groups and my teachers. The bcrypt hash lives in `/etc/caddy/edt.env`
(root:caddy, 640), injected into Caddy through a systemd `EnvironmentFile`, so no
secret is ever committed.

### Setup

Fill in `.env` (see [`.env.example`](.env.example)), then:

```sh
npm run deploy               # ship the page
./scripts/provision-edt.sh   # scraper, venv, secrets, cron, Caddy — idempotent
```

`provision-edt.sh` seeds the whole academic year on its first run (a few
minutes), then a cron at `:17` keeps it fresh.

### Manual refresh

The page has a refresh button. Since the site is static, Caddy cannot run a
script, so a tiny service (`edt/trigger.py`, `edt-refresh.service`) listens on
`127.0.0.1:8899` and Caddy reverse-proxies `/edt/refresh` to it — already covered
by the same basic auth. It has no auth of its own and is not reachable from
outside the box.

`POST` starts a run and returns immediately; the page polls `GET` until it is
done, then reloads the JSON. A run already in progress returns `409`, and a
second run within a minute returns `429`, so the button cannot be used to hammer
the school portal. `refresh.sh` also takes an `flock`, so the cron and the button
can never scrape at the same time.

### Why the hourly run is cheap

A full-year scrape is ~300 requests to the portal. Hourly, that would be rude.
`refresh.sh` instead re-scrapes only the current and next month with
`scrape.py --merge`, which keeps the rest of the year and reuses room/teacher
details already known for unchanged event ids. Steady state is about a dozen
requests per hour.

```sh
ssh "$REMOTE_USER@$REMOTE_HOST" tail -n 30 /srv/orionexe/edt/refresh.log
```

### When the portal misbehaves

It throttles: log in a few times in a row and it starts returning pages with no
form, or stops answering. Every request therefore carries a timeout — `requests`
sets none by default, and a silent portal once froze a run indefinitely — and
`connect()` retries four times with growing pauses. A run that still fails leaves
the previous `schedule.json` untouched, so the page shows slightly stale data
rather than nothing.

## Course notes (`/cours/`)

My course notes, written as standalone HTML pages outside this repo, then copied
into `src/lib/server/cours/content/`:

```
content/
├── index.html              # /cours/
├── reseaux/index.html      # /cours/reseaux/
└── reseaux/05-vlans.html   # /cours/reseaux/05-vlans/
```

`src/lib/server/cours/index.ts` keeps each page's `<main>`, rewrites its relative
links (`05-vlans.html`, `index.html`, `assets/x`) to site routes and builds the
sidebar from its `h2`/`h3` ids. A single route, `src/routes/cours/[...path]`,
prerenders them all. The load runs server-side so the raw HTML is never bundled
into the client; styling lives in `src/lib/cours.css`, scoped under `.cours`.

To add a subject: drop its pages in `content/<slug>/`, add `<slug>` to `SUBJECTS`
in `index.ts`, add a card to `content/index.html`, then `npm run deploy`. Files a
page links to (`assets/...`) go in `static/cours/<slug>/`.

## Adding pages

Routes live in `src/routes/`. Everything is prerendered (`src/routes/+layout.ts`),
so pages must not depend on request-time data. If you later need SSR, swap
`@sveltejs/adapter-static` for `@sveltejs/adapter-node` in `vite.config.ts` and
point the Caddyfile at `reverse_proxy localhost:3000` instead of `root`.
