import mdxServer from '@astrojs/mdx/server.js';
import type { APIContext } from 'astro';
import { experimental_AstroContainer } from 'astro/container';
import { render, type CollectionEntry } from 'astro:content';
import type { RootContent } from 'hast';
import { isElement } from 'hast-util-is-element';
import { matches, select, selectAll } from 'hast-util-select';
import rehypeParse from 'rehype-parse';
import rehypeRemark from 'rehype-remark';
import remarkGfm from 'remark-gfm';
import remarkStringify from 'remark-stringify';
import { unified } from 'unified';
import { remove } from 'unist-util-remove';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';

/** Minification defaults */
const minifyDefaults = {
	note: true,
	tip: true,
	caution: false,
	danger: false,
	details: true,
	whitespace: true,
	customSelectors: [],
};
/** Resolved minification options */
const minify = { ...minifyDefaults, ...starlightLllmsTxtContext.minify };

const astroContainer = await experimental_AstroContainer.create({
	renderers: [{ name: 'astro:jsx', ssr: mdxServer }],
});

const htmlToMarkdownPipeline = unified()
	.use(rehypeParse, { fragment: true })
	.use(function minifyLlmsTxt() {
		return (tree, file) => {
			if (!file.data.starlightLlmsTxt.minify) {
				return;
			}
			remove(tree, (node) => {
				// Remove <details> elements:
				if (minify.details && isElement(node, 'details')) {
					return true;
				}

				for (const selector of minify.customSelectors) {
					if (matches(selector, node as RootContent)) {
						return true;
					}
				}

				// Remove aside components:
				return Boolean(
					isElement(node, 'aside') &&
						Array.isArray(node.properties.className) &&
						node.properties.className.includes('starlight-aside') &&
						((minify.note && node.properties.className.includes('starlight-aside--note')) ||
							(minify.tip && node.properties.className.includes('starlight-aside--tip')) ||
							(minify.caution && node.properties.className.includes('starlight-aside--caution')) ||
							(minify.danger && node.properties.className.includes('starlight-aside--danger')))
				);
			});
			return tree;
		};
	})
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
	.use(function improveTabsHandling() {
		return (tree) => {
			const tabInstances = selectAll('starlight-tabs', tree as Parameters<typeof selectAll>[1]);
			for (const instance of tabInstances) {
				const tabs = selectAll('[role="tab"]', instance);
				const panels = selectAll('[role="tabpanel"]', instance);
				// Convert parent `<starlight-tabs>` element to empty unordered list.
				instance.tagName = 'ul';
				instance.properties = {};
				instance.children = [];
				// Iterate over tabs and panels to build a list with tab label as initial list text.
				for (let i = 0; i < Math.min(tabs.length, panels.length); i++) {
					const tab = tabs[i];
					const panel = panels[i];
					if (!tab || !panel) continue;
					// Filter out extra whitespace and icons from tab contents.
					const tabLabel = tab.children
						.filter((child) => child.type === 'text' && child.value.trim())
						.map((child) => child.type === 'text' && child.value.trim())
						.join('');
					// Add list entry for this tab and panel.
					instance.children.push({
						type: 'element',
						tagName: 'li',
						properties: {},
						children: [
							{
								type: 'element',
								tagName: 'p',
								children: [{ type: 'text', value: tabLabel }],
								properties: {},
							},
							panel,
						],
					});
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
	shouldMinify: boolean = false
) {
	const { Content } = await render(entry);
	const html = await astroContainer.renderToString(Content, context);
	const file = await htmlToMarkdownPipeline.process({
		value: html,
		data: { starlightLlmsTxt: { minify: shouldMinify } },
	});
	let markdown = String(file).trim();
	if (shouldMinify && minify.whitespace) {
		markdown = markdown.replace(/\s+/g, ' ');
	}
	return markdown;
}
