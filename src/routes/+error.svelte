<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>{page.status} — orionexe</title>
</svelte:head>

<main class="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-6 py-16">
	<h1 class="text-4xl font-semibold tracking-tight">{page.status}</h1>
	<p class="mt-4 text-lg text-zinc-400">{page.error?.message ?? 'Something went wrong.'}</p>
	<a
		href={resolve('/')}
		class="mt-8 text-sm text-zinc-500 underline underline-offset-4 hover:text-zinc-300"
	>
		Back home
	</a>
</main>
