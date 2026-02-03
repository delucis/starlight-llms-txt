import { defineMiddleware } from 'astro:middleware';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { getDocsEntries } from './docsEntries';
import { docEntryToMarkdownSlug, ensureTrailingSlash } from './utils';

type MediaType = { type: string; q: number; specificity: number };

function parseAcceptHeader(accept: string): MediaType[] {
	if (!accept) return [];
	return accept
		.split(',')
		.map((part) => {
			const [type, ...params] = part.trim().split(';');
			let q = 1.0;
			for (const param of params) {
				const [key, value] = param.trim().split('=');
				if (key === 'q' && value) {
					const parsed = Number.parseFloat(value);
					q = Number.isNaN(parsed) ? 1.0 : parsed;
				}
			}
			const mediaType = type.trim();
			let specificity = 3;
			if (mediaType === '*/*') specificity = 1;
			else if (mediaType.endsWith('/*')) specificity = 2;
			return { type: mediaType, q, specificity };
		})
		.sort((a, b) => {
			if (a.specificity !== b.specificity) return b.specificity - a.specificity;
			return b.q - a.q;
		});
}

function prefersMarkdown(accept: string): boolean {
	const types = parseAcceptHeader(accept);
	let markdownQ: number | null = null;
	let htmlQ: number | null = null;
	let markdownRejected = false;
	let htmlRejected = false;

	for (const { type, q } of types) {
		if (type === 'text/markdown' || type === 'text/plain') {
			if (markdownQ === null) {
				if (q === 0) markdownRejected = true;
				else markdownQ = q;
			}
		}
		if (type === 'text/html' || type === 'application/xhtml+xml') {
			if (htmlQ === null) {
				if (q === 0) htmlRejected = true;
				else htmlQ = q;
			}
		}

		if (type === 'text/*' || type === '*/*') {
			if (markdownQ === null && !markdownRejected) {
				if (q === 0) markdownRejected = true;
				else markdownQ = q;
			}
			if (htmlQ === null && !htmlRejected) {
				if (q === 0) htmlRejected = true;
				else htmlQ = q;
			}
		}
	}

	if (markdownRejected) return false;
	if (htmlRejected && markdownQ !== null && markdownQ > 0) return true;

	const mdQ = markdownQ ?? 0;
	const htQ = htmlQ ?? 0;
	return mdQ > htQ;
}

const docsRoutes = new Set<string>();
const docs = await getDocsEntries();
for (const entry of docs) {
	const slug = docEntryToMarkdownSlug(entry);
	if (slug.endsWith('.md')) {
		console.warn(
			`starlight-llms-txt: Skipping per-page markdown for "${entry.id}" because its slug "${slug}" would conflict with .md output.`
		);
		continue;
	}
	docsRoutes.add(slug);
}

const BASE_PATH = ensureTrailingSlash(starlightLllmsTxtContext.base);

export const onRequest = defineMiddleware(async (context, next) => {
	const url = new URL(context.request.url);
	const pathname = url.pathname;

	if (/\.\w+$/.test(pathname)) return next();
	if (pathname.match(/\/llms(-\w+)?\.txt$/)) return next();

	const basePrefix = BASE_PATH.replace(/\/$/, '');
	if (!pathname.startsWith(basePrefix)) return next();

	let slug = pathname;
	if (BASE_PATH !== '/') {
		slug = pathname.slice(basePrefix.length);
	}
	slug = slug.replace(/^\//, '').replace(/\/$/, '');
	if (!slug) slug = 'index';

	if (!docsRoutes.has(slug)) return next();

	const accept = context.request.headers.get('Accept') || '';
	if (prefersMarkdown(accept)) {
		const basePath = BASE_PATH.replace(/\/$/, '');
		const mdPath = slug === 'index' ? `${basePath}/index.md` : `${basePath}/${slug}.md`;
		return context.rewrite(mdPath);
	}

	return next();
});
