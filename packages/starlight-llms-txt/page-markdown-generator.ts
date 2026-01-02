import type { APIContext } from 'astro';
import type { CollectionEntry } from 'astro:content';
import { getCollection } from 'astro:content';
import micromatch from 'micromatch';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { entryToSimpleMarkdown } from './entryToSimpleMarkdown';
import { isDefaultLocale } from './utils';

/**
 * Generates Markdown content for a single documentation page.
 */
export async function generatePageMarkdown(
	doc: CollectionEntry<'docs'>,
	context: APIContext
): Promise<string> {
	return generateMarkdownForEntry(doc, context);
}

/**
 * Generates Markdown content for a single collection entry.
 */
async function generateMarkdownForEntry(
	doc: CollectionEntry<'docs'>,
	context: APIContext
): Promise<string> {
	const segments: string[] = [];

	// Add the page title
	segments.push(`# ${doc.data.hero?.title || doc.data.title}`);

	// Add the description if available
	const description = doc.data.hero?.tagline || doc.data.description;
	if (description) {
		segments.push(`> ${description}`);
	}

	// Convert the content to Markdown
	const markdown = await entryToSimpleMarkdown(doc, context, false);
	segments.push(markdown);

	return segments.join('\n\n');
}

/**
 * Get all documentation pages for static path generation.
 */
export async function getAllPages(): Promise<CollectionEntry<'docs'>[]> {
	return getCollection(
		'docs',
		(doc) =>
			isDefaultLocale(doc) &&
			!doc.data.draft &&
			!micromatch.isMatch(doc.id, starlightLllmsTxtContext.perPageMarkdown.excludePages)
	);
}