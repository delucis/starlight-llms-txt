import starlight from '@astrojs/starlight';
import { defineConfig } from 'astro/config';
import starlightLlmsTxt from 'starlight-llms-txt';

export default defineConfig({
	site: 'https://delucis.github.io',
	base: '/starlight-llms-txt',
	integrations: [
		starlight({
			title: 'starlight-llms-txt',
			description: 'Generate llms.txt context files for your Starlight documentation site',
			social: [
				{
					icon: 'github',
					label: 'GitHub repository',
					href: 'https://github.com/delucis/starlight-llms-txt',
				},
			],
			editLink: {
				baseUrl: 'https://github.com/delucis/starlight-llms-txt/edit/main/docs/',
			},
			lastUpdated: true,
			plugins: [
				starlightLlmsTxt({
					description:
						'starlight-llms-txt is a plugin for the Starlight documentation website framework that auto-generates llms.txt context files for large language models based on a documentation site’s content.',
					optionalLinks: [
						{
							label: 'The /llms.txt file',
							url: 'https://llmstxt.org/',
							description: 'full context about how to use llms.txt files',
						},
						{
							label: 'Starlight documentation',
							url: 'https://starlight.astro.build/',
							description: 'documentation for the Starlight documentation framework',
						},
					],
					// Exclude landing page from llms-small.txt
					exclude: ['index'],
					pageSeparator: `\n\n\n`,
				}),
			],
			sidebar: ['getting-started', 'configuration'],
			customCss: ['./src/styles.css'],
			logo: {
				src: './public/favicon.svg',
			},
		}),
	],
});
