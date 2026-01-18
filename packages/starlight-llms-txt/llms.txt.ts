import type { APIRoute } from 'astro';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { getDocsEntries } from './docsEntries';
import { defaultLang, docEntryToMarkdownSlug, ensureTrailingSlash, getSiteTitle } from './utils';

// Explicitly set this to prerender so it works the same way for sites in `server` mode.
export const prerender = true;
/**
 * Route that generates an introductory summary of this site for LLMs.
 */
export const GET: APIRoute = async (context) => {
	const title = getSiteTitle();
	const description = starlightLllmsTxtContext.description
		? `> ${starlightLllmsTxtContext.description}`
		: '';
	const site = new URL(ensureTrailingSlash(starlightLllmsTxtContext.base), context.site);
	const llmsFullLink = new URL('./llms-full.txt', site);
	const llmsSmallLink = new URL('./llms-small.txt', site);

	const segments = [`# ${title}`];
	if (description) segments.push(description);
	if (starlightLllmsTxtContext.details) segments.push(starlightLllmsTxtContext.details);

	// Further documentation links.
	segments.push(`## Documentation Sets`);
	segments.push(
		[
			`- [Abridged documentation](${llmsSmallLink}): a compact version of the documentation for ${getSiteTitle()}, with non-essential content removed`,
			`- [Complete documentation](${llmsFullLink}): the full documentation for ${getSiteTitle()}`,
			...starlightLllmsTxtContext.customSets.map(
				({ label, description, slug }) =>
					`- [${label}](${new URL(`./_llms-txt/${slug}.txt`, site)})` +
					(description ? `: ${description}` : '')
			),
		].join('\n')
	);

	const docs = await getDocsEntries();
	const collator = new Intl.Collator(defaultLang);
	docs.sort((a, b) => collator.compare(a.id, b.id));
	const pages = docs
		.map((doc) => {
			const slug = docEntryToMarkdownSlug(doc);
			if (slug.endsWith('.md')) {
				console.warn(
					`starlight-llms-txt: Skipping per-page markdown for "${doc.id}" because its slug "${slug}" would conflict with .md output.`
				);
				return null;
			}
			const markdownPath = `${ensureTrailingSlash(starlightLllmsTxtContext.base)}${slug}.md`;
			const title = doc.data.hero?.title || doc.data.title;
			const description = doc.data.hero?.tagline || doc.data.description;
			return `- [${title}](${markdownPath})${description ? `: ${description}` : ''}`;
		})
		.filter((line): line is string => Boolean(line));
	if (pages.length > 0) {
		segments.push('## Pages');
		segments.push(pages.join('\n'));
	}

	// Additional notes.
	segments.push(`## Notes`);
	segments.push(`- The complete documentation includes all content from the official documentation
- The content is automatically generated from the same source as the official documentation`);

	// Optional links.
	if (starlightLllmsTxtContext.optionalLinks.length > 0) {
		segments.push('## Optional');
		segments.push(
			starlightLllmsTxtContext.optionalLinks
				.map(
					(link) =>
						`- [${link.label}](${link.url})${link.description ? `: ${link.description}` : ''}`
				)
				.join('\n')
		);
	}

	return new Response(segments.join('\n\n') + '\n');
};
