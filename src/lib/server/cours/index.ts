// Course notes served under /cours/. Each page is a standalone HTML file in
// content/ (written outside this repo); at build time we keep only its <main>,
// rewrite its relative links to site routes and derive the sidebar from it.
// Server-only on purpose: the raw HTML must not end up in the client bundle.
// Math written as \( ... \) or \[ ... \] is rendered to HTML with KaTeX here,
// so pages ship no math JavaScript.

import katex from 'katex';

const files = import.meta.glob<string>('./content/**/*.html', {
	query: '?raw',
	import: 'default',
	eager: true
});

export type TocEntry = { id: string; text: string; level: 2 | 3 };

export type CoursPage = {
	path: string; // '' for the hub, 'reseaux' for a subject, 'reseaux/05-vlans' for a chapter
	title: string;
	description: string;
	code: string;
	back: { href: string; label: string };
	toc: TocEntry[];
	html: string;
};

const SUBJECTS: Record<string, string> = {
	reseaux: 'Introduction aux réseaux',
	cellulaire: 'Réseaux cellulaires',
	maths: 'Fondements mathématiques',
	algo: 'Algorithmique',
	'droit-social': 'Droit social',
	anglais: 'Anglais'
};

const ENTITIES: Record<string, string> = {
	'&amp;': '&',
	'&lt;': '<',
	'&gt;': '>',
	'&quot;': '"',
	'&#39;': "'",
	'&nbsp;': ' '
};

const text = (html: string) =>
	html
		.replace(/<[^>]+>/g, '')
		.replace(/&[a-z#0-9]+;/g, (e) => ENTITIES[e] ?? e)
		.replace(/\s+/g, ' ')
		.trim();

const first = (html: string, re: RegExp) => html.match(re)?.[1] ?? '';

/** content/reseaux/05-vlans.html -> reseaux/05-vlans, content/reseaux/index.html -> reseaux */
function toPath(file: string) {
	return file
		.replace(/^\.\/content\//, '')
		.replace(/\.html$/, '')
		.replace(/(^|\/)index$/, '');
}

function url(path: string) {
	return path ? `/cours/${path}/` : '/cours/';
}

/** Relative links between the HTML files become absolute site routes. */
function rewriteLinks(html: string, subject: string) {
	return html.replace(/href="([^"#:]+?)(#[^"]*)?"/g, (whole, target: string, hash = '') => {
		if (target === '../../index.html') return `href="${url('')}${hash}"`;
		if (target.startsWith('assets/')) return `href="${url(subject)}${target.slice(7)}"`;
		if (!target.endsWith('.html')) return whole;
		const path = toPath(`./content/${subject ? subject + '/' : ''}${target}`);
		return `href="${url(path)}${hash}"`;
	});
}

const unescape = (tex: string) => tex.replace(/&(amp|lt|gt);/g, (e) => ENTITIES[e]);

/** \( inline \) and \[ display \] math become KaTeX HTML. */
function renderMath(html: string) {
	return html.replace(/\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)/g, (_, display, inline) =>
		katex.renderToString(unescape(display ?? inline), {
			displayMode: display !== undefined,
			throwOnError: true,
			strict: 'ignore'
		})
	);
}

function parse(file: string, raw: string): CoursPage {
	const path = toPath(file);
	const [subject, chapter] = path.split('/');
	const main = first(raw, /<main>([\s\S]*?)<\/main>/);
	const toc = [...main.matchAll(/<h([23])\s+id="([^"]+)"([^>]*)>([\s\S]*?)<\/h\1>/g)].map(
		([, level, id, attrs, inner]) => ({
			id,
			level: Number(level) as 2 | 3,
			text: text(first(attrs, /data-toc="([^"]*)"/) || inner)
		})
	);

	const back = chapter
		? { href: url(subject), label: SUBJECTS[subject] ?? subject }
		: subject
			? { href: url(''), label: 'Tous les cours' }
			: { href: '/', label: 'orionexe' };

	return {
		path,
		title: text(first(raw, /<title>([\s\S]*?)<\/title>/)),
		description: text(first(main, /<p class="lead">([\s\S]*?)<\/p>/)),
		code: text(first(raw, /<div class="course-code">([\s\S]*?)<\/div>/)),
		back,
		toc,
		html: renderMath(rewriteLinks(main, subject ?? ''))
	};
}

const pages = new Map(
	Object.entries(files).map(([file, raw]) => {
		const page = parse(file, raw);
		return [page.path, page];
	})
);

export const coursPaths = () => [...pages.keys()];
export const coursPage = (path: string) => pages.get(path.replace(/\/+$/, ''));
