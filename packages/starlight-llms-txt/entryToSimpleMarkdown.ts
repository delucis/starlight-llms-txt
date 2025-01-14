import mdxServer from '@astrojs/mdx/server.js';
import type { APIContext } from 'astro';
import { experimental_AstroContainer } from 'astro/container';
import { render, type CollectionEntry } from 'astro:content';
import { select, selectAll } from 'hast-util-select';
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
	.use(function improveExpressiveCodeHandling() {
		return (tree) => {
			const ecInstances = selectAll('.expressive-code', tree as Parameters<typeof selectAll>[1]);
			for (const instance of ecInstances) {
				const pre = select('pre', instance);
				const code = select('code', instance);
				// Use Expressive Code’s `data-language=*` attribute to set a `language-*` class name.
				// This is what `hast-util-to-mdast` checks for code language metadata.
				if (pre?.properties.dataLanguage && code) {
					if (!Array.isArray(code.properties.className)) code.properties.className = [];
					code.properties.className.push(`language-${pre.properties.dataLanguage}`);
				}
			}
		};
	})
	.use(rehypeRemark)
	.use(remarkGfm)
	.use(remarkStringify);

/** Render a content collection entry to HTML and back to Markdown to support rendering and simplifying MDX components */
export async function entryToSimpleMarkdown(
	entry: CollectionEntry<'docs'>,
	context: APIContext,
	minify: boolean = false
) {
	const { Content } = await render(entry);
	const html = await astroContainer.renderToString(Content, context);
	const file = await htmlToMarkdownPipeline.process({
		value: html,
		data: { starlightLlmsTxt: { minify } },
	});
	return String(file);
}
