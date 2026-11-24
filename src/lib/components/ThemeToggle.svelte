<script lang="ts">
	// Light / dark switch. The initial theme is set on <html> by app.html before
	// first paint; this only flips it and remembers the choice.
	import { onMount } from 'svelte';

	let theme = $state<'light' | 'dark'>('dark');

	onMount(() => {
		theme = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
	});

	function toggle() {
		theme = theme === 'light' ? 'dark' : 'light';
		document.documentElement.dataset.theme = theme;
		try {
			localStorage.setItem('theme', theme);
		} catch {
			// Storage blocked: the switch still works for this page view.
		}
	}
</script>

<button
	type="button"
	onclick={toggle}
	class="fixed right-4 bottom-4 z-50 grid size-10 place-items-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-200 shadow-lg transition-colors hover:bg-zinc-800 hover:text-zinc-50 print:hidden"
	aria-label={theme === 'light' ? 'Passer en mode sombre' : 'Passer en mode clair'}
	title={theme === 'light' ? 'Mode sombre' : 'Mode clair'}
>
	{#if theme === 'light'}
		<!-- moon -->
		<svg
			viewBox="0 0 24 24"
			class="size-5"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
		</svg>
	{:else}
		<!-- sun -->
		<svg
			viewBox="0 0 24 24"
			class="size-5"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<circle cx="12" cy="12" r="4" />
			<path
				d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
			/>
		</svg>
	{/if}
</button>
