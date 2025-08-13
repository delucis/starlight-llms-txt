import type {
	APIRoute,
	GetStaticPaths,
	InferGetStaticParamsType,
	InferGetStaticPropsType,
} from 'astro';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { generatePageMarkdown, getAllPageSlugs } from './page-markdown-generator';

export const getStaticPaths = (async () => {
	const { generatePageMarkdown: generatePageMarkdownEnabled, markdownFilePattern } = starlightLllmsTxtContext;

	// Only generate paths if the feature is enabled
	if (!generatePageMarkdownEnabled) {
		return [];
	}

	// Get all page slugs
	const slugs = await getAllPageSlugs();

	// Generate paths based on the file pattern
	const paths = slugs.flatMap((slug) => {
		const urlPaths = [];

		// Handle different URL patterns
		if (markdownFilePattern === 'replace') {
			// Simple .md replacement pattern
			urlPaths.push({
				params: { slug: slug === 'index' ? undefined : slug },
				props: { originalSlug: slug },
			});
		} else {
			// 'append' pattern - add .html.md
			// For index pages
			if (slug === 'index') {
				urlPaths.push({
					params: { slug: 'index.html' },
					props: { originalSlug: slug },
				});
			} else {
				// For regular pages, support both clean URL and .html.md patterns
				urlPaths.push({
					params: { slug },
					props: { originalSlug: slug },
				});
				urlPaths.push({
					params: { slug: `${slug}.html` },
					props: { originalSlug: slug },
				});
			}
		}

		return urlPaths;
	});

	return paths;
}) satisfies GetStaticPaths;

type Props = InferGetStaticPropsType<typeof getStaticPaths>;
type Params = InferGetStaticParamsType<typeof getStaticPaths>;

/**
 * Route that generates individual markdown files for each documentation page.
 */
export const GET: APIRoute<Props, Params> = async (context) => {
	const { generatePageMarkdown: generatePageMarkdownEnabled } = starlightLllmsTxtContext;

	// Return 404 if the feature is disabled
	if (!generatePageMarkdownEnabled) {
		return new Response('Not Found', { status: 404 });
	}

	// Get the original slug from props
	const originalSlug = context.props.originalSlug;

	// Generate the markdown content
	const content = await generatePageMarkdown(context, originalSlug);

	if (!content) {
		return new Response('Not Found', { status: 404 });
	}

	// Return the markdown content with appropriate headers
	return new Response(content, {
		headers: {
			'Content-Type': 'text/plain; charset=utf-8',
		},
	});
};