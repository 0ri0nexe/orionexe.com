#!/usr/bin/env bash
#
# Refresh is the cron used to refresh the shedule for all the year.

set -euo pipefail

EDT_DIR="${EDT_DIR:-/srv/orionexe/edt}"
OUT="${OUT:-/srv/orionexe/shared/edt/schedule.json}"
LOG="${LOG:-${EDT_DIR}/refresh.log}"

cd "$EDT_DIR"

# One scrape at a time: the cron and the "Refresh" button can land together,
# and two concurrent runs would double the load on the portal while each merged
# a stale version of the file.
exec 9>"${EDT_DIR}/.refresh.lock"
if ! flock -n 9; then
	echo "$(date -Is) already running, giving up" >>"${LOG:-${EDT_DIR}/refresh.log}"
	exit 0
fi

# Bounded log: we keep the last 2000 lines.
if [[ -f "$LOG" && $(wc -l <"$LOG") -gt 2000 ]]; then
	tail -n 1000 "$LOG" >"${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi
exec >>"$LOG" 2>&1
echo "--- $(date -Is) ---"

# shellcheck disable=SC1091
set -a
. ./.env
set +a

if [[ -s "$OUT" ]]; then
	FROM="$(date +%Y-%m)"
	TO="$(date -d '+1 month' +%Y-%m)"
else
	# Current academic year: it starts in August.
	YEAR="$(date +%Y)"
	[[ "$(date +%m)" -lt 8 ]] && YEAR=$((YEAR - 1))
	FROM="${YEAR}-08"
	TO="$((YEAR + 1))-07"
	echo "No existing file: seeding from ${FROM} -> ${TO}"
fi

timeout 1200 ./venv/bin/python scrape.py --merge --from "$FROM" --to "$TO" --out "$OUT"
chmod 644 "$OUT"
