import type {
	APIRoute,
	GetStaticPaths,
	InferGetStaticParamsType,
	InferGetStaticPropsType,
} from 'astro';
import type { CollectionEntry } from 'astro:content';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { getDocsEntries } from './docsEntries';
import { entryToSimpleMarkdown } from './entryToSimpleMarkdown';
import { docEntryToMarkdownSlug, ensureTrailingSlash } from './utils';

export const getStaticPaths = (async () => {
	const docs = await getDocsEntries();
	return docs.flatMap((entry) => {
		const slug = docEntryToMarkdownSlug(entry);
		if (slug.endsWith('.md')) {
			console.warn(
				`starlight-llms-txt: Skipping per-page markdown for "${entry.id}" because its slug "${slug}" would conflict with .md output.`
			);
			return [];
		}
		return {
			params: { slug },
			props: { entry, slug },
		};
	});
}) satisfies GetStaticPaths;

export const prerender = true;

type Props = InferGetStaticPropsType<typeof getStaticPaths>;
type Params = InferGetStaticParamsType<typeof getStaticPaths>;

function serializeFrontmatter(fields: Record<string, string>) {
	const lines = ['---'];
	for (const [key, value] of Object.entries(fields)) {
		if (value) lines.push(`${key}: ${JSON.stringify(value)}`);
	}
	lines.push('---');
	return lines.join('\n');
}

function getDocHtmlPath(slug: string): string {
	const basePath = starlightLllmsTxtContext.base.replace(/\/$/, '');
	const normalizedSlug = slug === 'index' ? '' : slug;
	let path = normalizedSlug ? `${basePath}/${normalizedSlug}` : basePath || '/';
	if (!path.startsWith('/')) path = `/${path}`;

	const trailingSlash = starlightLllmsTxtContext.trailingSlash;
	if (trailingSlash === 'always') return ensureTrailingSlash(path);
	if (trailingSlash === 'never') return path === '/' ? '/' : path.replace(/\/$/, '');
	return path;
}

function getDocTitle(entry: CollectionEntry<'docs'>): string {
	return entry.data.hero?.title || entry.data.title;
}

function getDocDescription(entry: CollectionEntry<'docs'>): string | undefined {
	return entry.data.hero?.tagline || entry.data.description;
}

export const GET: APIRoute<Props, Params> = async (context) => {
	const { entry, slug } = context.props;
	const title = getDocTitle(entry);
	const description = getDocDescription(entry);
	const url = new URL(getDocHtmlPath(slug), context.site).toString();
	const frontmatter = serializeFrontmatter({
		title,
		description: description ?? '',
		url,
	});
	const markdown = await entryToSimpleMarkdown(entry, context);
	const body = `${frontmatter}\n\n${markdown}\n`;
	return new Response(body, {
		headers: {
			'Content-Type': 'text/markdown; charset=utf-8',
		},
	});
};
