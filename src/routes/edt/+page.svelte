<!-- This part of the website is just a tool to be more convenient to me 
 and is not related to the portfolio in any way. 
 Beaware that it's also fully vibe-coded and is intended to be a working tool rather than a cool coding thingy
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import {
		DAY_END,
		DAY_START,
		DOW,
		addDays,
		capitalize,
		displayTitle,
		formatLongDay,
		formatMonthYear,
		formatShortDay,
		groupByDay,
		humanDuration,
		isoDay,
		layoutDay,
		matches,
		minutes,
		palette,
		parseDay,
		sessionTag,
		shortRoom,
		startOfWeek,
		type Schedule,
		type Slot
	} from '$lib/edt';

	const ROW = 56; // height of one hour, in pixels
	const VIEWS = [
		{ id: 'week', label: 'Semaine' },
		{ id: 'list', label: 'Liste' }
	] as const;

	let schedule = $state<Schedule | null>(null);
	let failure = $state<string | null>(null);
	let view = $state<'week' | 'list'>('week');
	let anchor = $state(startOfWeek(new Date()));
	const hiddenTypes = new SvelteSet<string>();
	let query = $state('');
	let selected = $state<Slot | null>(null);
	let now = $state(new Date());
	let refreshing = $state(false);
	let refreshNote = $state('');

	const events = $derived(schedule?.events ?? []);
	const types = $derived([...new Set(events.map((e) => e.type))].sort());
	const visible = $derived(events.filter((e) => !hiddenTypes.has(e.type) && matches(e, query)));
	const byDay = $derived(groupByDay(visible));
	const todayIso = $derived(isoDay(now));

	const weekDays = $derived(Array.from({ length: 7 }, (_, i) => addDays(anchor, i)));

	// the weekend only shows up when it carries slots
	const shownDays = $derived(
		weekDays.slice(5).some((d) => (byDay.get(isoDay(d)) ?? []).length > 0)
			? weekDays
			: weekDays.slice(0, 5)
	);

	const weekDaysGrouped = $derived(
		groupByDay(
			visible.filter((e) => {
				const d = parseDay(e.date);
				return d >= anchor && d < addDays(anchor, 7);
			})
		)
	);

	const periodTitle = $derived.by(() => {
		const end = addDays(anchor, 6);
		return anchor.getMonth() === end.getMonth()
			? formatMonthYear(anchor)
			: `${anchor.toLocaleDateString('fr-FR', { month: 'short' })} – ${formatMonthYear(end)}`;
	});

	const nowOffset = $derived.by(() => {
		const mins = now.getHours() * 60 + now.getMinutes();
		if (mins < DAY_START * 60 || mins > DAY_END * 60) return null;
		return ((mins - DAY_START * 60) / 60) * ROW;
	});

	function toggleType(type: string) {
		if (hiddenTypes.has(type)) hiddenTypes.delete(type);
		else hiddenTypes.add(type);
	}

	function isPast(iso: string) {
		return parseDay(iso) < parseDay(todayIso);
	}

	function onKey(e: KeyboardEvent) {
		if (e.target instanceof HTMLInputElement) return;
		if (e.key === 'Escape') selected = null;
		else if (e.key === 'ArrowLeft') anchor = addDays(anchor, -7);
		else if (e.key === 'ArrowRight') anchor = addDays(anchor, 7);
		else if (e.key === 't') anchor = startOfWeek(new Date());
	}

	/** Reloads the JSON. `initial` also sets the week and the view. */
	async function loadSchedule(initial = false) {
		const res = await fetch('/edt/schedule.json', { cache: 'no-store' });
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
		const data: Schedule = await res.json();
		schedule = data;

		if (!initial) return;
		const week = startOfWeek(new Date());
		const hasCurrent = data.events.some((e) => {
			const d = parseDay(e.date);
			return d >= week && d < addDays(week, 7);
		});
		const first = data.events.map((e) => e.date).sort()[0];
		anchor = hasCurrent || !first ? week : startOfWeek(parseDay(first));
		if (window.matchMedia('(max-width: 700px)').matches) view = 'list';
	}

	const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

	/** Waits for the running scrape to finish, then reloads the data. */
	async function waitForRun() {
		for (let i = 0; i < 300; i++) {
			// ~2 s between polls, 10 min in total: plenty for a seeding run.
			await sleep(2000);
			const res = await fetch('/edt/refresh', { cache: 'no-store' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const run = await res.json();
			if (run.status !== 'idle') continue;
			if (run.ok === false) throw new Error(run.message || 'le scrape a echoue');
			await loadSchedule();
			return;
		}
		throw new Error('délai dépassé');
	}

	async function refresh() {
		if (refreshing) return;
		refreshing = true;
		refreshNote = '';
		try {
			const res = await fetch('/edt/refresh', { method: 'POST' });
			const body = await res.json().catch(() => ({}));
			if (res.status === 429) {
				refreshNote = `à jour — réessayez dans ${body.retry_after ?? 60} s`;
				return;
			}
			// 202: started. 409: the cron is already running, we wait for the same result.
			if (res.status !== 202 && res.status !== 409) throw new Error(`HTTP ${res.status}`);
			await waitForRun();
		} catch (e) {
			refreshNote = (e as Error).message;
		} finally {
			refreshing = false;
		}
	}

	onMount(() => {
		// The page is prerendered: it starts empty, the data arrives client-side.
		loadSchedule(true).catch((e: Error) => (failure = e.message));

		const tick = setInterval(() => (now = new Date()), 60_000);
		return () => clearInterval(tick);
	});
</script>

<svelte:head>
	<title>Emploi du temps — orionexe</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<svelte:window onkeydown={onKey} />

<div class="flex min-h-screen flex-col">
	<header
		class="sticky top-0 z-30 flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-zinc-800 bg-zinc-950/90 px-4 py-3 backdrop-blur"
	>
		<div class="min-w-0">
			<h1 class="text-base font-semibold tracking-tight">Emploi du temps</h1>
			<p class="truncate text-xs text-zinc-500">
				{#if schedule?.student?.name}
					{schedule.student.name}{schedule.student.space ? ` · ${schedule.student.space}` : ''}
					{#if schedule.generated_at}
						· màj {new Date(schedule.generated_at).toLocaleString('fr-FR', {
							day: 'numeric',
							month: 'short',
							hour: '2-digit',
							minute: '2-digit'
						})}
					{/if}
				{:else}
					&nbsp;
				{/if}
			</p>
		</div>

		<div class="flex items-center gap-2">
			<button
				type="button"
				aria-label="Semaine précédente"
				class="grid size-8 place-items-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
				onclick={() => (anchor = addDays(anchor, -7))}>‹</button
			>
			<button
				type="button"
				class="h-8 rounded-lg border border-zinc-800 px-3 text-sm text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
				onclick={() => (anchor = startOfWeek(new Date()))}>Aujourd'hui</button
			>
			<button
				type="button"
				aria-label="Semaine suivante"
				class="grid size-8 place-items-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
				onclick={() => (anchor = addDays(anchor, 7))}>›</button
			>
			<div class="ml-1 hidden leading-tight sm:block">
				<div class="text-sm font-medium first-letter:uppercase">{periodTitle}</div>
				<div class="text-xs text-zinc-500">
					{formatShortDay(anchor)} → {formatShortDay(addDays(anchor, 6))}
				</div>
			</div>
		</div>

		<div class="ml-auto flex flex-1 items-center justify-end gap-2 sm:flex-none">
			<div class="flex overflow-hidden rounded-lg border border-zinc-800">
				{#each VIEWS as v (v.id)}
					<button
						type="button"
						aria-pressed={view === v.id}
						class="h-8 px-3 text-sm {view === v.id
							? 'bg-zinc-800 text-zinc-100'
							: 'text-zinc-400 hover:text-zinc-200'}"
						onclick={() => (view = v.id)}>{v.label}</button
					>
				{/each}
			</div>
			<input
				type="search"
				bind:value={query}
				placeholder="Rechercher…"
				aria-label="Rechercher un cours, une salle, un enseignant"
				class="h-8 w-40 min-w-0 rounded-lg border border-zinc-800 bg-transparent px-3 text-sm placeholder:text-zinc-600 focus:border-zinc-600 focus:outline-none"
			/>
			<button
				type="button"
				onclick={refresh}
				disabled={refreshing}
				title={refreshing ? 'Scrape en cours…' : 'Relancer le scrape maintenant'}
				aria-label="Relancer le scrape"
				class="grid size-8 shrink-0 place-items-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100 disabled:opacity-50"
			>
				<svg
					viewBox="0 0 16 16"
					width="14"
					height="14"
					fill="none"
					stroke="currentColor"
					stroke-width="1.6"
					stroke-linecap="round"
					class={refreshing ? 'animate-spin' : ''}
					aria-hidden="true"
				>
					<path d="M14 8a6 6 0 1 1-1.76-4.24" />
					<path d="M14 2v4h-4" />
				</svg>
			</button>
		</div>
	</header>

	{#if refreshNote}
		<p class="border-b border-zinc-800 bg-zinc-900/60 px-4 py-2 text-xs text-zinc-400">
			{refreshNote}
		</p>
	{/if}

	{#if types.length}
		<nav
			class="flex flex-wrap gap-2 border-b border-zinc-800 bg-zinc-950 px-4 py-2.5"
			aria-label="Filtrer par type de créneau"
		>
			{#each types as type (type)}
				{@const on = !hiddenTypes.has(type)}
				<button
					type="button"
					aria-pressed={on}
					class="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition {on
						? 'border-zinc-700 bg-zinc-900 text-zinc-200'
						: 'border-zinc-800 text-zinc-600'}"
					onclick={() => toggleType(type)}
				>
					<span class="size-2 rounded-full {on ? palette(type).dot : 'bg-zinc-700'}"></span>
					{type}
				</button>
			{/each}
		</nav>
	{/if}

	<main class="flex-1 p-4">
		{#if failure}
			<p
				class="mx-auto max-w-lg rounded-xl border border-l-2 border-zinc-800 border-l-rose-500 bg-zinc-900/50 p-5 text-sm text-zinc-400"
			>
				<strong class="text-zinc-200">Impossible de charger l'emploi du temps.</strong><br />
				<code class="text-zinc-300">/edt/schedule.json</code> n'a pas répondu ({failure}). Le cron
				le régénère toutes les heures sur le VPS.
			</p>
		{:else if !schedule}
			<p class="py-20 text-center text-sm text-zinc-600">Chargement…</p>
		{:else if view === 'week'}
			<div class="overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-900/30">
				<div
					class="grid min-w-[720px]"
					style="grid-template-columns: 58px repeat({shownDays.length}, minmax(140px, 1fr))"
				>
					<div class="sticky left-0 z-20 h-13 border-r border-b border-zinc-800 bg-zinc-950"></div>

					{#each shownDays as day (isoDay(day))}
						{@const isToday = isoDay(day) === todayIso}
						<div
							class="sticky top-0 z-10 flex h-13 flex-col justify-center border-b border-l border-zinc-800 bg-zinc-950 px-3"
						>
							<span
								class="text-[11px] font-semibold tracking-wider uppercase {isToday
									? 'text-sky-400'
									: 'text-zinc-500'}">{DOW[(day.getDay() + 6) % 7]}</span
							>
							<span class="text-lg font-semibold {isToday ? 'text-sky-400' : 'text-zinc-100'}"
								>{day.getDate()}</span
							>
						</div>
					{/each}

					<div class="sticky left-0 z-10 border-r border-zinc-800 bg-zinc-950">
						{#each Array.from({ length: DAY_END - DAY_START }, (_, i) => DAY_START + i) as hour (hour)}
							<div class="pr-2 text-right text-[11px] text-zinc-600" style="height: {ROW}px">
								{#if hour > DAY_START}
									<span class="relative -top-2">{String(hour).padStart(2, '0')}:00</span>
								{/if}
							</div>
						{/each}
					</div>

					{#each shownDays as day (isoDay(day))}
						{@const iso = isoDay(day)}
						{@const weekend = day.getDay() === 0 || day.getDay() === 6}
						<div
							class="relative border-l border-zinc-800 {weekend ? 'bg-zinc-900/40' : ''}"
							style="height: {(DAY_END - DAY_START) *
								ROW}px; background-image: repeating-linear-gradient(to bottom, var(--color-zinc-800) 0 1px, transparent 1px {ROW}px)"
						>
							{#each layoutDay(byDay.get(iso) ?? []) as p (p.slot.id ?? `${p.slot.date}-${p.slot.start}`)}
								{@const c = palette(p.slot.type)}
								{@const tag = sessionTag(p.slot)}
								{@const room = shortRoom(p.slot.room)}
								<button
									type="button"
									title={`${p.slot.title}\n${p.slot.start}–${p.slot.end}${p.slot.room ? `\n${p.slot.room}` : ''}`}
									class="absolute flex flex-col items-start overflow-hidden rounded-md border-l-2 px-2 py-1 text-left hover:z-10 hover:brightness-125 {c.bg} {c.border} {isPast(
										iso
									)
										? 'opacity-45'
										: ''}"
									style="top: {((p.from - DAY_START * 60) / 60) * ROW + 2}px; height: {((p.to -
										p.from) /
										60) *
										ROW -
										4}px; left: calc({(p.col * 100) / p.cols}% + 2px); width: calc({100 /
										p.cols}% - 4px)"
									onclick={() => (selected = p.slot)}
								>
									<span class="line-clamp-3 text-xs font-semibold {c.text}">
										{displayTitle(p.slot)}{tag ? ` · ${tag}` : ''}
									</span>
									<span class="block truncate text-[11px] text-zinc-400">
										{p.slot.start}–{p.slot.end}{room ? ` · ${room}` : ''}
									</span>
								</button>
							{/each}

							{#if iso === todayIso && nowOffset !== null}
								<div
									class="pointer-events-none absolute inset-x-0 z-10 h-0.5 bg-sky-400"
									style="top: {nowOffset}px"
								>
									<span class="absolute -top-1 -left-1 size-2 rounded-full bg-sky-400"></span>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{:else if weekDaysGrouped.size === 0}
			<p class="py-20 text-center text-sm text-zinc-600">Aucun créneau sur cette semaine.</p>
		{:else}
			<div class="flex flex-col gap-5">
				{#each weekDaysGrouped as [iso, slots] (iso)}
					<section class="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/30">
						<h2
							class="border-b border-zinc-800 bg-zinc-900/60 px-4 py-3 text-sm font-semibold first-letter:uppercase {iso ===
							todayIso
								? 'text-sky-400'
								: 'text-zinc-200'}"
						>
							{formatLongDay(parseDay(iso))}{iso === todayIso ? " · aujourd'hui" : ''}
						</h2>
						{#each slots as slot (slot.id ?? slot.start)}
							{@const c = palette(slot.type)}
							{@const bits = [shortRoom(slot.room), slot.teachers, slot.group].filter(Boolean)}
							<button
								type="button"
								class="flex w-full items-start gap-3 border-t border-zinc-800/70 px-4 py-3 text-left first:border-t-0 hover:bg-zinc-800/40 {isPast(
									iso
								)
									? 'opacity-55'
									: ''}"
								onclick={() => (selected = slot)}
							>
								<span class="w-14 shrink-0 text-sm text-zinc-500 tabular-nums">
									{slot.start}<br />{slot.end}
								</span>
								<span class="w-1 self-stretch rounded-full {c.bar}"></span>
								<span class="min-w-0">
									<span class="text-sm font-semibold text-zinc-100">
										{displayTitle(slot)}
										<span class="ml-2 rounded-full px-2 py-0.5 text-[11px] {c.bg} {c.text}"
											>{slot.type}</span
										>
									</span>
									{#if bits.length}
										<span class="mt-0.5 block text-xs text-zinc-500">{bits.join(' · ')}</span>
									{/if}
								</span>
							</button>
						{/each}
					</section>
				{/each}
			</div>
		{/if}
	</main>
</div>

{#if selected}
	{@const c = palette(selected.type)}
	{@const duration = (minutes(selected.end) ?? 0) - (minutes(selected.start) ?? 0)}
	<button
		type="button"
		tabindex="-1"
		aria-label="Fermer le détail"
		class="fixed inset-0 z-40 cursor-default bg-black/50"
		onclick={() => (selected = null)}
	></button>
	<aside
		class="fixed inset-y-0 right-0 z-50 w-full max-w-sm overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-6"
		aria-label="Détail du créneau"
	>
		<button
			type="button"
			aria-label="Fermer"
			class="absolute top-4 right-4 grid size-8 place-items-center rounded-lg border border-zinc-800 text-zinc-400 hover:text-zinc-100"
			onclick={() => (selected = null)}>×</button
		>
		<h2 class="mr-10 text-lg font-semibold">{displayTitle(selected)}</h2>
		<span class="mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-semibold {c.bg} {c.text}">
			{selected.type}
		</span>
		<dl class="mt-5 grid grid-cols-[88px_1fr] gap-x-3 gap-y-2.5 text-sm">
			<dt class="text-zinc-500">Date</dt>
			<dd>{capitalize(formatLongDay(parseDay(selected.date)))}</dd>
			<dt class="text-zinc-500">Horaire</dt>
			<dd>
				{selected.start} – {selected.end}{duration > 0 ? ` (${humanDuration(duration)})` : ''}
			</dd>
			<dt class="text-zinc-500">Salle</dt>
			<dd>{selected.room || '—'}</dd>
			<dt class="text-zinc-500">Enseignant</dt>
			<dd>{selected.teachers || '—'}</dd>
			<dt class="text-zinc-500">Groupe</dt>
			<dd>{selected.group || '—'}</dd>
			<dt class="text-zinc-500">Statut</dt>
			<dd>{selected.status || '—'}</dd>
		</dl>
		{#if selected.description}
			<p class="mt-5 border-t border-zinc-800 pt-4 text-sm text-zinc-400">{selected.description}</p>
		{/if}
		{#if selected.title !== displayTitle(selected)}
			<p class="mt-5 border-t border-zinc-800 pt-4 text-sm text-zinc-500">{selected.title}</p>
		{/if}
	</aside>
{/if}
