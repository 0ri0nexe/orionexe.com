import { error } from '@sveltejs/kit';
import { coursPage, coursPaths } from '$lib/server/cours';
import type { EntryGenerator, PageServerLoad } from './$types';

// Every course page is listed explicitly so the prerender does not depend on
// the crawler finding a link to it.
export const entries: EntryGenerator = () => coursPaths().map((path) => ({ path }));

export const load: PageServerLoad = ({ params }) => {
	const page = coursPage(params.path);
	if (!page) error(404, 'Cours introuvable');
	return page;
};
