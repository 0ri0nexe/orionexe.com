// Pure types and helpers for the timetable. The data comes from
// /edt/schedule.json, produced on the VPS by edt/scrape.py (hourly cron).

export type Slot = {
	id: string | null;
	title: string;
	type: string;
	status: string;
	date: string; // YYYY-MM-DD
	start: string; // HH:MM
	end: string;
	description?: string;
	room?: string;
	teachers?: string;
	course?: string;
	group?: string;
};

export type Schedule = {
	student?: { name?: string; space?: string };
	generated_at?: string;
	range?: { from: string; to: string };
	events: Slot[];
};

export const DAY_START = 7;
export const DAY_END = 20;

// Displayed as-is in the header: the UI stays in French, like the portal data.
export const DOW = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];

// Tailwind scans the source: class names must be written out in full, never
// composed at runtime.
export type Palette = { bar: string; border: string; text: string; bg: string; dot: string };

const PALETTES: Record<string, Palette> = {
	td: {
		bar: 'bg-sky-400',
		border: 'border-sky-400',
		text: 'text-sky-300',
		bg: 'bg-sky-500/10',
		dot: 'bg-sky-400'
	},
	tp: {
		bar: 'bg-violet-400',
		border: 'border-violet-400',
		text: 'text-violet-300',
		bg: 'bg-violet-500/10',
		dot: 'bg-violet-400'
	},
	cours: {
		bar: 'bg-emerald-400',
		border: 'border-emerald-400',
		text: 'text-emerald-300',
		bg: 'bg-emerald-500/10',
		dot: 'bg-emerald-400'
	},
	exam: {
		bar: 'bg-rose-400',
		border: 'border-rose-400',
		text: 'text-rose-300',
		bg: 'bg-rose-500/10',
		dot: 'bg-rose-400'
	},
	langue: {
		bar: 'bg-amber-400',
		border: 'border-amber-400',
		text: 'text-amber-300',
		bg: 'bg-amber-500/10',
		dot: 'bg-amber-400'
	},
	presta: {
		bar: 'bg-fuchsia-400',
		border: 'border-fuchsia-400',
		text: 'text-fuchsia-300',
		bg: 'bg-fuchsia-500/10',
		dot: 'bg-fuchsia-400'
	},
	perso: {
		bar: 'bg-zinc-500',
		border: 'border-zinc-500',
		text: 'text-zinc-300',
		bg: 'bg-zinc-500/10',
		dot: 'bg-zinc-500'
	}
};

// Keys are the portal's own labels — they must match the scraped data verbatim.
const TYPE_KEYS: Record<string, keyof typeof PALETTES> = {
	TD: 'td',
	TP: 'tp',
	Examen: 'exam',
	Langues: 'langue',
	'Travail Personnel': 'perso',
	Présentation: 'presta',
	'Cours Magistral': 'cours',
	'Cours Professeur': 'cours',
	'Cours Intégré': 'cours'
};

export function palette(type: string): Palette {
	return PALETTES[TYPE_KEYS[type] ?? 'perso'];
}

/* ------------------------------------------------------------------ dates */

export function startOfWeek(date: Date): Date {
	const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
	d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); // Monday = 0
	return d;
}

export function addDays(date: Date, n: number): Date {
	const d = new Date(date);
	d.setDate(d.getDate() + n);
	return d;
}

/** "YYYY-MM-DD" key in local time — toISOString would shift to UTC. */
export function isoDay(date: Date): string {
	const p = (n: number) => String(n).padStart(2, '0');
	return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}

export function parseDay(iso: string): Date {
	const [y, m, d] = iso.split('-').map(Number);
	return new Date(y, m - 1, d);
}

export function minutes(hhmm: string | undefined): number | null {
	if (!hhmm) return null;
	const [h, m] = hhmm.split(':').map(Number);
	return h * 60 + m;
}

export function formatMonthYear(date: Date): string {
	return date.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
}

export function formatLongDay(date: Date): string {
	return date.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
}

export function formatShortDay(date: Date): string {
	return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

export function humanDuration(mins: number): string {
	const h = Math.floor(mins / 60);
	const m = mins % 60;
	if (h && m) return `${h} h ${String(m).padStart(2, '0')}`;
	return h ? `${h} h` : `${m} min`;
}

export function capitalize(s: string): string {
	return s.charAt(0).toUpperCase() + s.slice(1);
}

/* ------------------------------------------------------------------- text */

/** "B107 Labo RST 24pl" -> "B107 Labo RST": the capacity clutters the display. */
export function shortRoom(room: string | undefined): string {
	if (!room) return '';
	return room
		.split(',')
		.map((r) =>
			r
				.trim()
				.replace(/\s*\d+\s*pl\b.*$/i, '')
				.trim()
		)
		.filter(Boolean)
		.join(', ');
}

/** Portal titles repeat the course and the format; we keep what matters. */
export function displayTitle(slot: Slot): string {
	if (slot.course && slot.course !== 'Travail académique autonome') return slot.course;
	return slot.title.split(' - ')[0].trim() || slot.title;
}

/** Session suffix ("S3") found at the end of a title. */
export function sessionTag(slot: Slot): string {
	const m = /-\s*S(\d+)\s*$/.exec(slot.title);
	return m ? `S${m[1]}` : '';
}

/* ------------------------------------------------------------------- data */

export function matches(slot: Slot, query: string): boolean {
	const q = query.trim().toLowerCase();
	if (!q) return true;
	return [
		slot.title,
		slot.type,
		slot.room,
		slot.teachers,
		slot.group,
		slot.course,
		slot.description
	].some((v) => v?.toLowerCase().includes(q));
}

export function groupByDay(slots: Slot[]): Map<string, Slot[]> {
	const map = new Map<string, Slot[]>();
	for (const slot of slots) {
		const list = map.get(slot.date);
		if (list) list.push(slot);
		else map.set(slot.date, [slot]);
	}
	for (const list of map.values()) {
		list.sort((a, b) => (minutes(a.start) ?? 0) - (minutes(b.start) ?? 0));
	}
	return new Map([...map].sort(([a], [b]) => a.localeCompare(b)));
}

export type Placed = { slot: Slot; from: number; to: number; col: number; cols: number };

/**
 * Lays overlapping slots out in side-by-side columns: each one gets its column
 * and the column count of its overlap group.
 */
export function layoutDay(dayslots: Slot[]): Placed[] {
	const placed: Placed[] = [];
	let cluster: Placed[] = [];
	let clusterEnd = -1;

	const flush = () => {
		const width = cluster.reduce((max, p) => Math.max(max, p.col + 1), 0);
		for (const p of cluster) p.cols = width;
		cluster = [];
		clusterEnd = -1;
	};

	for (const slot of dayslots) {
		const from = minutes(slot.start) ?? DAY_START * 60;
		const to = Math.max(minutes(slot.end) ?? from + 60, from + 30);

		if (cluster.length && from >= clusterEnd) flush();

		let col = 0;
		while (cluster.some((p) => p.col === col && p.to > from)) col++;

		const entry: Placed = { slot, from, to, col, cols: 1 };
		cluster.push(entry);
		placed.push(entry);
		clusterEnd = Math.max(clusterEnd, to);
	}
	flush();
	return placed;
}
