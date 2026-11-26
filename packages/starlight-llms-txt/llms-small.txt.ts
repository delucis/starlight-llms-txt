import type { APIRoute, GetStaticPaths } from 'astro';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { generateLlmsTxt } from './generator';
import { getSiteTitle, localeKeys } from './utils';

// Explicitly set this to prerender so it works the same way for sites in `server` mode.

export const prerender = true;

// Used by the localized `/[locale]/llms-small.txt` route added by the `i18n` option.
export const getStaticPaths = (() =>
	localeKeys.map((locale) => ({ params: { locale } }))) satisfies GetStaticPaths;

/**
 * Route that generates a single plaintext Markdown document from the full website content.
 */
export const GET: APIRoute = async (context) => {
	const body = await generateLlmsTxt(context, {
		minify: true,
		description: `This is the abridged developer documentation for ${getSiteTitle(context.params.locale)}`,
		exclude: starlightLllmsTxtContext.exclude,
	});
	return new Response(body);
};
