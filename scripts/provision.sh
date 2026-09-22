#!/usr/bin/env bash
#
# One-time VPS setup. Idempotent — safe to re-run after editing deploy/Caddyfile.
#
#   ./scripts/provision.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

# Host and account live in .env (gitignored) so the repo names no infrastructure.
if [[ -f .env ]]; then
	# shellcheck disable=SC1091
	set -a
	. ./.env
	set +a
fi

REMOTE_USER="${REMOTE_USER:?set REMOTE_USER in .env (see .env.example)}"
REMOTE_HOST="${REMOTE_HOST:?set REMOTE_HOST in .env (see .env.example)}"
APP_DIR="${APP_DIR:-/srv/orionexe}"
SITE_NAME="${SITE_NAME:-orionexe.com}"

step() { printf '\n\033[1;36m==>\033[0m \033[1m%s\033[0m\n' "$1"; }

step "Creating ${APP_DIR}"
ssh "${REMOTE_USER}@${REMOTE_HOST}" "
	set -euo pipefail
	sudo mkdir -p '${APP_DIR}/releases'
	sudo chown -R ${REMOTE_USER}:${REMOTE_USER} '${APP_DIR}'
	chmod 755 '${APP_DIR}'
	sudo mkdir -p /etc/caddy/sites /var/log/caddy
	sudo chown caddy:caddy /var/log/caddy
"

step "Installing Caddy site config"
scp -q deploy/Caddyfile "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${SITE_NAME}.caddy"
ssh "${REMOTE_USER}@${REMOTE_HOST}" "
	set -euo pipefail
	sudo mv /tmp/${SITE_NAME}.caddy /etc/caddy/sites/${SITE_NAME}.caddy
	sudo chown root:root /etc/caddy/sites/${SITE_NAME}.caddy

	# Make the main Caddyfile pull in everything under sites/, once.
	if ! sudo grep -q '^import /etc/caddy/sites/' /etc/caddy/Caddyfile; then
		sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak.\$(date +%s)
		echo '' | sudo tee -a /etc/caddy/Caddyfile >/dev/null
		echo 'import /etc/caddy/sites/*.caddy' | sudo tee -a /etc/caddy/Caddyfile >/dev/null
	fi

	sudo caddy fmt --overwrite /etc/caddy/Caddyfile
	sudo caddy validate --config /etc/caddy/Caddyfile
	sudo systemctl reload caddy
"

step "Done — run 'npm run deploy' to ship the site"
