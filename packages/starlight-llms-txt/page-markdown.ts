import type {
	APIRoute,
	GetStaticPaths,
	InferGetStaticParamsType,
	InferGetStaticPropsType,
} from 'astro';
import type { CollectionEntry } from 'astro:content';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { generatePageMarkdown, getAllPages } from './page-markdown-generator';

export const getStaticPaths = (async () => {
	const { perPageMarkdown } = starlightLllmsTxtContext;

	// Only generate paths if the feature is enabled
	if (!perPageMarkdown.enabled) {
		return [];
	}

	// Get all pages
	const pages = await getAllPages();

	// Generate paths based on the file pattern
	const paths = pages.flatMap((doc) => {
		const slug = doc.id;

		// Handle different URL patterns
		if (perPageMarkdown.extensionStrategy === 'replace') {
			// Simple .md replacement pattern
			return [
				{
					params: { slug },
					props: { doc },
				},
			];
		} else {
			// 'append' pattern - add .html.md
			if (slug === 'index') {
				return [
					{
						params: { slug: 'index.html' },
						props: { doc },
					},
				];
			} else {
				return [
					{
						params: { slug: `${slug}.html` },
						props: { doc },
					},
				];
			}
		}
	});

	return paths;
}) satisfies GetStaticPaths;

type Props = InferGetStaticPropsType<typeof getStaticPaths>;
type Params = InferGetStaticParamsType<typeof getStaticPaths>;

/**
 * Route that generates individual Markdown files for each documentation page.
 */
export const GET: APIRoute<Props, Params> = async (context) => {
	// Generate the Markdown content using the doc from props
	const content = await generatePageMarkdown(context.props.doc, context);

	// Return the Markdown content with appropriate headers
	return new Response(content, {
		headers: {
			'Content-Type': 'text/plain; charset=utf-8',
		},
	});
};