import type { APIRoute } from 'astro';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { generateLlmsTxt } from './generator';
import { getSiteTitle } from './utils';

/**
 * Route that generates a single plaintext Markdown document from the full website content.
 */
export const GET: APIRoute = async (context) => {
	const body = await generateLlmsTxt(context, {
		minify: true,
		description: `This is the abridged developer documentation for ${getSiteTitle()}`,
		exclude: starlightLllmsTxtContext.exclude,
	});
	return new Response(body);
};
