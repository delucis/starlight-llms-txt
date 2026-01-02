import type {
	APIRoute,
	GetStaticPaths,
	InferGetStaticParamsType,
	InferGetStaticPropsType,
} from 'astro';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { generatePageMarkdown, getAllPageSlugs } from './page-markdown-generator';

export const getStaticPaths = (async () => {
	const { perPageMarkdown } = starlightLllmsTxtContext;

	// Only generate paths if the feature is enabled
	if (!perPageMarkdown.enabled) {
		return [];
	}

	// Get all page slugs
	const slugs = await getAllPageSlugs();

	// Generate paths based on the file pattern
	const paths = slugs.flatMap((slug) => {
		const urlPaths = [];

		// Handle different URL patterns
		if (perPageMarkdown.extensionStrategy === 'replace') {
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
				// For regular pages
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
 * Route that generates individual Markdown files for each documentation page.
 */
export const GET: APIRoute<Props, Params> = async (context) => {
	// Get the original slug from props
	const originalSlug = context.props.originalSlug;

	// Generate the Markdown content
	const content = await generatePageMarkdown(context, originalSlug);

	if (!content) {
		return new Response('Not Found', { status: 404 });
	}

	// Return the Markdown content with appropriate headers
	return new Response(content, {
		headers: {
			'Content-Type': 'text/plain; charset=utf-8',
		},
	});
};