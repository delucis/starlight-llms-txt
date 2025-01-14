import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { entryToSimpleMarkdown } from './entryToSimpleMarkdown';
import { getSiteTitle, isDefaultLocale } from './utils';

/**
 * Route that generates a single plaintext Markdown document from the full website content.
 */
export const GET: APIRoute = async (context) => {
	const docs = await getCollection('docs', isDefaultLocale);
	const segments: string[] = [];
	for (const doc of docs) {
		const docSegments = [`# ${doc.data.hero?.title || doc.data.title}`];
		const description = doc.data.hero?.tagline || doc.data.description;
		if (description) docSegments.push(`> ${description}`);
		docSegments.push(await entryToSimpleMarkdown(doc, context));
		segments.push(docSegments.join('\n\n'));
	}
	const preamble = `<SYSTEM>This is the full developer documentation for ${getSiteTitle()}</SYSTEM>`;
	const body = preamble + '\n\n' + segments.join('\n\n');
	return new Response(body);
};
