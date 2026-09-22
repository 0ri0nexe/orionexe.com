#!/usr/bin/env python3
"""Triggers refresh.sh on demand, for the "Refresh" button on /edt.

The site is static: Caddy cannot run a script. This service listens locally and
Caddy proxies /edt/refresh to it. It has no authentication of its own: it listens
on 127.0.0.1 only, and Caddy protects /edt/* with basic auth.

    GET  -> current state, as JSON
    POST -> starts a scrape if one is not already running

The scrape runs in a thread: the request answers immediately and the page polls
the state until it is done, rather than holding a connection open for the whole
duration of the scrape.
"""

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EDT_DIR = os.environ.get("EDT_DIR", "/srv/orionexe/edt")
REFRESH = os.path.join(EDT_DIR, "refresh.sh")
LOG = os.path.join(EDT_DIR, "refresh.log")
HOST = os.environ.get("EDT_TRIGGER_HOST", "127.0.0.1")
PORT = int(os.environ.get("EDT_TRIGGER_PORT", "8899"))

# A manual scrape right after another one learns nothing and hits the portal for
# nothing: we enforce a minimum delay between two triggers.
COOLDOWN = int(os.environ.get("EDT_TRIGGER_COOLDOWN", "60"))
TIMEOUT = int(os.environ.get("EDT_TRIGGER_TIMEOUT", "900"))

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | running
    "started_at": None,
    "finished_at": None,
    "ok": None,
    "message": "",
}


def _last_log_line():
    """Last useful log line, to say *why* a run failed."""
    try:
        with open(LOG, encoding="utf-8", errors="replace") as fh:
            lines = [line.strip() for line in fh.readlines()[-40:] if line.strip()]
    except OSError:
        return ""
    return lines[-1] if lines else ""


def _run():
    """Runs refresh.sh and records the result."""
    try:
        proc = subprocess.run(
            [REFRESH],
            cwd=EDT_DIR,
            timeout=TIMEOUT,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        # refresh.sh redirects its output to its log: on failure, what is left on
        # the pipes is precisely what broke beforehand.
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        if tail:
            message = tail[-1]
        elif ok:
            message = _last_log_line() or "done"
        else:
            message = _last_log_line() or f"code {proc.returncode}"
    except subprocess.TimeoutExpired:
        ok, message = False, f"gave up after {TIMEOUT}s"
    except OSError as exc:
        ok, message = False, str(exc)

    with _lock:
        _state.update(
            status="idle",
            finished_at=time.time(),
            ok=ok,
            message=message,
        )


def _start():
    """Starts a scrape. Returns (HTTP code, response body)."""
    with _lock:
        if _state["status"] == "running":
            return 409, {**_state, "reason": "already running"}

        waited = time.time() - (_state["finished_at"] or 0)
        if waited < COOLDOWN:
            return 429, {
                **_state,
                "reason": "too soon",
                "retry_after": int(COOLDOWN - waited) + 1,
            }

        _state.update(status="running", started_at=time.time(), ok=None, message="")

    threading.Thread(target=_run, daemon=True).start()
    with _lock:
        return 202, dict(_state)


class Handler(BaseHTTPRequestHandler):
    server_version = "edt-trigger"

    def _reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        with _lock:
            self._reply(200, dict(_state))

    def do_POST(self):
        code, payload = _start()
        self._reply(code, payload)

    def log_message(self, fmt, *args):
        pass  # logged by Caddy, no point duplicating it in systemd


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
