import type { APIRoute } from 'astro';
import { generateLlmsTxt } from './generator';
import { getSiteTitle } from './utils';

/**
 * Route that generates a single plaintext Markdown document from the full website content.
 */
export const GET: APIRoute = async (context) => {
	const body = await generateLlmsTxt(context, {
		minify: false,
		description: `This is the full developer documentation for ${getSiteTitle()}`,
	});
	return new Response(body);
};
