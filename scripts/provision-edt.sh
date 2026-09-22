#!/usr/bin/env bash
#
# Installs the timetable on the VPS: scraper, venv, secrets, cron, Caddy.
# Idempotent — re-run after any change to edt/ or to deploy/Caddyfile.
#
#   ./scripts/provision-edt.sh
#
# Reads .env at the project root:
#   EDT_USER      IMT portal username
#   EDT_PASS      IMT portal password
#   EDT_WEB_USER  username to reach /edt (basic auth)
#   EDT_WEB_PASS  password to reach /edt
#
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_HOST="${REMOTE_HOST:-51.91.253.130}"
APP_DIR="${APP_DIR:-/srv/orionexe}"
SITE_NAME="${SITE_NAME:-orionexe.com}"

cd "$(dirname "$0")/.."

step() { printf '\n\033[1;36m==>\033[0m \033[1m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m==> %s\033[0m\n' "$1" >&2; exit 1; }

[[ -f .env ]] || fail ".env not found — copy .env.example and fill it in."
# shellcheck disable=SC1091
set -a; . ./.env; set +a

for var in EDT_USER EDT_PASS EDT_WEB_USER EDT_WEB_PASS; do
	[[ -n "${!var:-}" ]] || fail "$var missing from .env"
done

# The files written here are sourced by bash (refresh.sh) and read by systemd.
# Without quoting, a password containing > ! } $ would be truncated or interpreted.
shquote() {
	local s=${1//\'/\'\\\'\'} # ' -> '\''
	printf "'%s'" "$s"
}

ssh_do() { ssh -o ConnectTimeout=10 "${REMOTE_USER}@${REMOTE_HOST}" "$@"; }

step "Creating ${APP_DIR}/edt and ${APP_DIR}/shared/edt"
ssh_do "
	set -euo pipefail
	sudo mkdir -p '${APP_DIR}/edt' '${APP_DIR}/shared/edt'
	sudo chown -R ${REMOTE_USER}:${REMOTE_USER} '${APP_DIR}/edt' '${APP_DIR}/shared'
	# Caddy must be able to traverse shared/ and read the JSON.
	chmod 755 '${APP_DIR}/shared' '${APP_DIR}/shared/edt'
"

step "Uploading scraper"
rsync -az --info=stats1 -e "ssh -o ConnectTimeout=10" \
	edt/scrape.py edt/refresh.sh edt/trigger.py "${REMOTE_USER}@${REMOTE_HOST}:${APP_DIR}/edt/"

step "Python venv"
ssh_do "
	set -euo pipefail
	# Ubuntu ships python3 without ensurepip: without that package, 'python3 -m venv' fails.
	if ! python3 -c 'import ensurepip' 2>/dev/null; then
		sudo apt-get update -qq
		sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv
	fi

	cd '${APP_DIR}/edt'
	# We test pip, not the directory: a half-created venv leaves a misleading bin/.
	[[ -x venv/bin/pip ]] || { rm -rf venv; python3 -m venv venv; }
	./venv/bin/pip install --quiet --upgrade pip
	./venv/bin/pip install --quiet requests beautifulsoup4
	chmod +x refresh.sh
	./venv/bin/python -c 'import requests, bs4; print(\"deps ok\")'
"

step "Portal credentials (${APP_DIR}/edt/.env, mode 600)"
# Goes through stdin: the password shows up neither in argv nor in the ssh logs.
printf 'EDT_USER=%s\nEDT_PASS=%s\n' "$(shquote "$EDT_USER")" "$(shquote "$EDT_PASS")" |
	ssh_do "
		set -euo pipefail
		umask 077
		cat > '${APP_DIR}/edt/.env'
		chmod 600 '${APP_DIR}/edt/.env'
	"

step "Basic auth for /edt (/etc/caddy/edt.env)"
# caddy reads one line: without the trailing newline it returns "Error: EOF". It
# strips it afterwards, so the hash does match the password alone.
HASH="$(printf '%s\n' "$EDT_WEB_PASS" | ssh_do "caddy hash-password")" ||
	fail "caddy hash-password failed"
[[ -n "$HASH" ]] || fail "empty bcrypt hash"

printf 'EDT_WEB_USER=%s\nEDT_WEB_HASH=%s\n' "$(shquote "$EDT_WEB_USER")" "$(shquote "$HASH")" |
	ssh_do "
		set -euo pipefail
		# tee rather than 'install /dev/stdin': under sudo, /dev/stdin is not
		# always reachable and the install fails intermittently.
		sudo tee /etc/caddy/edt.env >/dev/null
		sudo chown root:caddy /etc/caddy/edt.env
		sudo chmod 640 /etc/caddy/edt.env

		# Caddy reads {\$EDT_WEB_*} from its environment: we inject it via systemd.
		sudo mkdir -p /etc/systemd/system/caddy.service.d
		printf '[Service]\nEnvironmentFile=/etc/caddy/edt.env\n' |
			sudo tee /etc/systemd/system/caddy.service.d/edt.conf >/dev/null
		sudo systemctl daemon-reload
	"

step "Refresh trigger service"
scp -q deploy/edt-refresh.service "${REMOTE_USER}@${REMOTE_HOST}:/tmp/edt-refresh.service"
ssh_do "
	set -euo pipefail
	sudo mv /tmp/edt-refresh.service /etc/systemd/system/edt-refresh.service
	sudo chown root:root /etc/systemd/system/edt-refresh.service
	sudo systemctl daemon-reload
	sudo systemctl enable --quiet --now edt-refresh.service
	sudo systemctl restart edt-refresh.service
	sleep 1
	systemctl is-active edt-refresh.service
	curl -fsS --max-time 5 http://127.0.0.1:8899/ | head -c 200; echo
"

step "Caddy site config"
scp -q deploy/Caddyfile "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${SITE_NAME}.caddy"
ssh_do "
	set -euo pipefail
	sudo mv /tmp/${SITE_NAME}.caddy /etc/caddy/sites/${SITE_NAME}.caddy
	sudo chown root:root /etc/caddy/sites/${SITE_NAME}.caddy
	# caddy 2.6 has no --envfile: we load the variables in the validating shell,
	# otherwise {\$EDT_WEB_*} resolves to empty and basicauth rejects the config.
	sudo bash -c 'set -a; . /etc/caddy/edt.env; set +a; caddy validate --config /etc/caddy/Caddyfile' 
	# restart, not reload: EnvironmentFile is only re-read when the service starts.
	sudo systemctl restart caddy
"

step "Hourly cron"
ssh_do "
	set -euo pipefail
	LINE='17 * * * * ${APP_DIR}/edt/refresh.sh'
	# grep -Fv returns 1 when no line is left (empty crontab): without the
	# || true, set -e would make the cron install fail.
	( crontab -l 2>/dev/null | grep -Fv '${APP_DIR}/edt/refresh.sh' || true ; echo \"\$LINE\" ) | crontab -
	crontab -l | grep refresh.sh
"

step "First run (seeding the whole year: a few minutes)"
ssh_do "${APP_DIR}/edt/refresh.sh; tail -n 20 '${APP_DIR}/edt/refresh.log'"

step "Done — /edt is live behind basic auth"
