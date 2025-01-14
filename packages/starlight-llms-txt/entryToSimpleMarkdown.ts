import mdxServer from '@astrojs/mdx/server.js';
import type { APIContext } from 'astro';
import { experimental_AstroContainer } from 'astro/container';
import { render, type CollectionEntry } from 'astro:content';
import rehypeParse from 'rehype-parse';
import rehypeRemark from 'rehype-remark';
import remarkGfm from 'remark-gfm';
import remarkStringify from 'remark-stringify';
import { unified } from 'unified';

const astroContainer = await experimental_AstroContainer.create({
	renderers: [{ name: 'astro:jsx', ssr: mdxServer }],
});

const htmlToMarkdownPipeline = unified()
	.use(rehypeParse)
	.use(rehypeRemark)
	.use(remarkGfm)
	.use(remarkStringify);

/** Render a content collection entry to HTML and back to Markdown to support rendering and simplifying MDX components */
export async function entryToSimpleMarkdown(entry: CollectionEntry<'docs'>, context: APIContext) {
	const { Content } = await render(entry);
	const html = await astroContainer.renderToString(Content, context);
	const file = await htmlToMarkdownPipeline.process(html);
	return String(file);
}
