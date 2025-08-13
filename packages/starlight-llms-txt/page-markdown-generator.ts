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
	context: APIContext,
	slug: string
): Promise<string | null> {
	const { excludePages } = starlightLllmsTxtContext;

	// Check if this page should be excluded
	if (excludePages && micromatch.isMatch(slug, excludePages)) {
		return null;
	}

	// Get all docs from the collection
	const docs = await getCollection('docs', (doc) => isDefaultLocale(doc) && !doc.data.draft);

	// Find the matching doc by slug
	const doc = docs.find((d) => d.id === slug || d.slug === slug);

	if (!doc) {
		return null;
	}

	// Generate Markdown content for the page
	const content = await generateMarkdownForEntry(doc, context);
	return content;
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
 * Get all documentation page slugs for static path generation.
 */
export async function getAllPageSlugs(): Promise<string[]> {
	const { excludePages } = starlightLllmsTxtContext;

	// Get all docs from the collection
	const docs = await getCollection('docs', (doc) => isDefaultLocale(doc) && !doc.data.draft);

	// Filter out excluded pages
	let slugs = docs.map((doc) => doc.id);
	if (excludePages) {
		slugs = slugs.filter((slug) => !micromatch.isMatch(slug, excludePages));
	}

	return slugs;
}