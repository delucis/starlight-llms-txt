import type { APIContext } from 'astro';
import { getCollection } from 'astro:content';
import { entryToSimpleMarkdown } from './entryToSimpleMarkdown';
import { getSiteTitle, isDefaultLocale } from './utils';

/**
 * Generates a single plaintext Markdown document from the full website content.
 */
export async function generateLlmsTxt(
	context: APIContext,
	options: {
		/** Generate a smaller file to fit within smaller context windows. */
		minify: boolean;
	}
): Promise<string> {
	const docs = await getCollection('docs', isDefaultLocale);
	const segments: string[] = [];
	for (const doc of docs) {
		const docSegments = [`# ${doc.data.hero?.title || doc.data.title}`];
		const description = doc.data.hero?.tagline || doc.data.description;
		if (description) docSegments.push(`> ${description}`);
		docSegments.push(await entryToSimpleMarkdown(doc, context, options.minify));
		segments.push(docSegments.join('\n\n'));
	}
	const preamble = `<SYSTEM>This is the ${
		options.minify ? 'abridged' : 'full'
	} developer documentation for ${getSiteTitle()}</SYSTEM>`;
	return preamble + '\n\n' + segments.join('\n\n');
}
