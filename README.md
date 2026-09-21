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

Install your SSH key on the server, then provision it:

```sh
ssh-copy-id ubuntu@51.91.253.130
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

All scripts read these environment variables:

| Variable      | Default                |
| ------------- | ---------------------- |
| `REMOTE_USER` | `ubuntu`               |
| `REMOTE_HOST` | `51.91.253.130`        |
| `APP_DIR`     | `/srv/orionexe`        |
| `SITE_URL`    | `https://orionexe.com` |

## Adding pages

Routes live in `src/routes/`. Everything is prerendered (`src/routes/+layout.ts`),
so pages must not depend on request-time data. If you later need SSR, swap
`@sveltejs/adapter-static` for `@sveltejs/adapter-node` in `vite.config.ts` and
point the Caddyfile at `reverse_proxy localhost:3000` instead of `root`.
