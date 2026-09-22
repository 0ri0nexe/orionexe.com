import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	server: {
		proxy: {
			// En production c'est Caddy qui renvoie /edt/refresh au declencheur.
			// En dev, lancer le service a la main pour que le bouton reponde :
			//   EDT_DIR=edt python3 edt/trigger.py
			'/edt/refresh': 'http://127.0.0.1:8899'
		}
	},

	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// Fully prerendered static site, served by Caddy straight off disk.
			adapter: adapter({
				pages: 'build',
				assets: 'build',
				// Caddy serves this for any unknown path (see deploy/Caddyfile).
				fallback: '404.html',
				precompress: true,
				strict: true
			})
		})
	]
});
