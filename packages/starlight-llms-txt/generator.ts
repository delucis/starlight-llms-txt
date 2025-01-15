import type { APIContext } from 'astro';
import { getCollection } from 'astro:content';
import micromatch from 'micromatch';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { entryToSimpleMarkdown } from './entryToSimpleMarkdown';
import { defaultLang, getSiteTitle, isDefaultLocale } from './utils';

/** Collator to compare two strings in the default language. */
const collator = new Intl.Collator(defaultLang);

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
	let docs = await getCollection('docs', isDefaultLocale);
	if (options.minify) {
		docs = docs.filter((doc) => !micromatch.isMatch(doc.id, starlightLllmsTxtContext.exclude));
	}
	docs.sort((a, b) => {
		const aIsIndex = a.id === 'index';
		const bIsIndex = b.id === 'index';
		return aIsIndex && !bIsIndex ? -1 : bIsIndex && !aIsIndex ? 1 : collator.compare(a.id, b.id);
	});
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
