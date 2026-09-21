#!/usr/bin/env bash
#
# Build locally, ship to the VPS, flip a symlink. No downtime, instant rollback.
#
#   npm run deploy            # build + deploy
#   npm run deploy -- --skip-build
#
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_HOST="${REMOTE_HOST:-51.91.253.130}"
APP_DIR="${APP_DIR:-/srv/orionexe}"
SITE_URL="${SITE_URL:-https://orionexe.com}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"

cd "$(dirname "$0")/.."

SKIP_BUILD=0
[[ "${1:-}" == "--skip-build" ]] && SKIP_BUILD=1

ssh_do() { ssh -o ConnectTimeout=10 "${REMOTE_USER}@${REMOTE_HOST}" "$@"; }

step() { printf '\n\033[1;36m==>\033[0m \033[1m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m==> %s\033[0m\n' "$1" >&2; exit 1; }

if [[ $SKIP_BUILD -eq 0 ]]; then
	step "Building"
	npm run build
fi

[[ -f build/index.html ]] || fail "build/index.html missing — did the build succeed?"

RELEASE="$(date -u +%Y%m%d%H%M%S)"
RELEASE_DIR="${APP_DIR}/releases/${RELEASE}"

step "Uploading release ${RELEASE}"
ssh_do "mkdir -p '${RELEASE_DIR}'"
rsync -az --delete --info=stats1 \
	-e "ssh -o ConnectTimeout=10" \
	build/ "${REMOTE_USER}@${REMOTE_HOST}:${RELEASE_DIR}/"

step "Activating"
# Symlink swap via `mv -T` is atomic: a request is served either the old
# release or the new one, never a half-written directory.
ssh_do "
	set -euo pipefail
	chmod -R a+rX '${RELEASE_DIR}'
	ln -sfn '${RELEASE_DIR}' '${APP_DIR}/.current.tmp'
	mv -Tf '${APP_DIR}/.current.tmp' '${APP_DIR}/current'
	ls -1dt '${APP_DIR}'/releases/*/ 2>/dev/null | tail -n +$((KEEP_RELEASES + 1)) | xargs -r rm -rf
"

step "Verifying"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "${SITE_URL}" 2>/dev/null)"
CODE="${CODE:-000}"
if [[ "$CODE" == "200" ]]; then
	printf '\033[1;32m==> Live at %s (HTTP %s, release %s)\033[0m\n' "$SITE_URL" "$CODE" "$RELEASE"
else
	printf '\033[1;33m==> Deployed, but %s returned HTTP %s\033[0m\n' "$SITE_URL" "$CODE" >&2
	printf '    Check DNS/TLS, then: ssh %s@%s "sudo journalctl -u caddy -n 50"\n' \
		"$REMOTE_USER" "$REMOTE_HOST" >&2
fi
