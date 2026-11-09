<script lang="ts">
	import '$lib/cours.css';

	let { data } = $props();

	let active = $state('');

	// Highlights the section being read in the sidebar.
	$effect(() => {
		const heads = data.toc
			.map((t) => document.getElementById(t.id))
			.filter((h): h is HTMLElement => h !== null);
		const observer = new IntersectionObserver(
			(entries) => {
				for (const e of entries) if (e.isIntersecting) active = e.target.id;
			},
			{ rootMargin: '0px 0px -70% 0px' }
		);
		heads.forEach((h) => observer.observe(h));
		return () => observer.disconnect();
	});
</script>

<svelte:head>
	<title>{data.title}</title>
	{#if data.description}
		<meta name="description" content={data.description} />
	{/if}
</svelte:head>

<div class="cours" lang="fr">
	<div class="layout">
		<aside class="sidebar">
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- href is an absolute route built server-side -->
			<a class="home" href={data.back.href}>← {data.back.label}</a>
			{#if data.code}
				<div class="course-code">{data.code}</div>
			{/if}
			<nav>
				{#each data.toc as entry (entry.id)}
					<a href="#{entry.id}" class:sub={entry.level === 3} class:active={active === entry.id}>
						{entry.text}
					</a>
				{/each}
			</nav>
		</aside>
		<main>
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- our own course notes, prerendered from files in the repo -->
			{@html data.html}
		</main>
	</div>
</div>
