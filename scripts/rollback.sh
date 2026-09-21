#!/usr/bin/env bash
#
# Point `current` back at the previous release. Takes about a second.
#
#   ./scripts/rollback.sh          # previous release
#   ./scripts/rollback.sh --list   # show what is on the server
#   ./scripts/rollback.sh 20260921134500
#
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_HOST="${REMOTE_HOST:-51.91.253.130}"
APP_DIR="${APP_DIR:-/srv/orionexe}"

TARGET="${1:-}"

if [[ "$TARGET" == "--list" ]]; then
	ssh "${REMOTE_USER}@${REMOTE_HOST}" "
		echo 'current -> '\$(readlink -f '${APP_DIR}/current')
		echo '--- releases (newest first) ---'
		ls -1dt '${APP_DIR}'/releases/*/ | sed 's#.*/releases/##'
	"
	exit 0
fi

ssh "${REMOTE_USER}@${REMOTE_HOST}" "
	set -euo pipefail
	cd '${APP_DIR}/releases'
	if [[ -n '${TARGET}' ]]; then
		DEST='${TARGET}'
	else
		CURRENT=\$(basename \$(readlink -f '${APP_DIR}/current'))
		DEST=\$(ls -1dt */ | sed 's#/\$##' | grep -v \"^\${CURRENT}\$\" | head -1)
	fi
	[[ -d \"\$DEST\" ]] || { echo \"No such release: \$DEST\" >&2; exit 1; }
	ln -sfn '${APP_DIR}/releases/'\"\$DEST\" '${APP_DIR}/.current.tmp'
	mv -Tf '${APP_DIR}/.current.tmp' '${APP_DIR}/current'
	echo \"Rolled back to \$DEST\"
"
