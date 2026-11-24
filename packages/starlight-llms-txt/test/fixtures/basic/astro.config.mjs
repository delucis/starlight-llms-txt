import starlight from '@astrojs/starlight';
import { defineConfig } from 'astro/config';
import starlightLlmsTxt from '../../../index.ts';

export default defineConfig({
	site: 'https://example.com',
	integrations: [
		starlight({
			title: 'Fixture',
			plugins: [starlightLlmsTxt()],
		}),
	],
});
