import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import type { APIRoute } from 'astro';
import { loadProgressiveCorpus, renderProgressiveIndex } from './progressive-corpus';
import { ensureTrailingSlash } from './utils';

export const prerender = true;

export const GET: APIRoute = (context) => {
  const options = starlightLllmsTxtContext.progressiveCorpus;
  if (!options) return new Response('Not found', { status: 404 });
  const corpus = loadProgressiveCorpus(options);
  const site = new URL(ensureTrailingSlash(starlightLllmsTxtContext.base), context.site);
  return new Response(renderProgressiveIndex(corpus, site, options), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
