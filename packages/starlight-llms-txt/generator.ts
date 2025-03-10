import type { APIContext } from 'astro';
import { getCollection } from 'astro:content';
import micromatch from 'micromatch';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { entryToSimpleMarkdown } from './entryToSimpleMarkdown';
import { defaultLang, isDefaultLocale } from './utils';

/** Collator to compare two strings in the default language. */
const collator = new Intl.Collator(defaultLang);

/**
 * Generates a single plaintext Markdown document from the full website content.
 */
export async function generateLlmsTxt(
	context: APIContext,
	{
		minify,
		description,
		exclude,
		include,
	}: {
		/** Generate a smaller file to fit within smaller context windows. */
		minify: boolean;
		/** Description of the document being generated. Prepended to output inside `<SYSTEM>` tags. */
		description: string | undefined;
		exclude?: string[] | undefined;
		include?: string[] | undefined;
	}
): Promise<string> {
	let docs = await getCollection('docs', (doc) => isDefaultLocale(doc) && !doc.data.draft);
	if (include) {
		docs = docs.filter((doc) => micromatch.isMatch(doc.id, include));
	}
	if (exclude) {
		docs = docs.filter((doc) => !micromatch.isMatch(doc.id, exclude));
	}
	const { promote, demote, pageSeparator } = starlightLllmsTxtContext;
	/** Processes page IDs by prepending underscores to influence the sorting order. */
	const prioritizePages = (id: string) => {
		// Match the page ID against the patterns listed in the `promote` and `demote`
		// config options and return the index of the first match. If a page matches
		// a `demote` pattern, we don't check `promote` as demotions take precedence.
		const demoted = demote.findIndex((expr) => micromatch.isMatch(id, expr));
		const promoted = demoted > -1 ? -1 : promote.findIndex((expr) => micromatch.isMatch(id, expr));
		// Calculate the number of underscores to prefix the page ID with
		// to influence the sorting order. The more underscores, the earlier
		// the page will appear in the list. The amount of underscores added by
		// a pattern is determined by the respective array length and the match index.
		const prefixLength =
			(promoted > -1 ? promote.length - promoted : 0) + demote.length - demoted - 1;
		return '_'.repeat(prefixLength) + id;
	};
	docs.sort((a, b) => collator.compare(prioritizePages(a.id), prioritizePages(b.id)));
	const segments: string[] = [];
	for (const doc of docs) {
		const docSegments = [`# ${doc.data.hero?.title || doc.data.title}`];
		const description = doc.data.hero?.tagline || doc.data.description;
		if (description) docSegments.push(`> ${description}`);
		docSegments.push(await entryToSimpleMarkdown(doc, context, minify));
		segments.push(docSegments.join('\n\n'));
	}
	if (description) {
		segments.unshift(`<SYSTEM>${description}</SYSTEM>`);
	}
	return segments.join(pageSeparator);
}
