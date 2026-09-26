import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import type { APIRoute, GetStaticPaths, InferGetStaticParamsType } from 'astro';
import { getProgressivePaths, loadProgressiveCorpus, renderProgressiveNode } from './progressive-corpus';
import { ensureTrailingSlash } from './utils';

export const prerender = true;

const options = starlightLllmsTxtContext.progressiveCorpus;
if (!options) throw new Error('progressive corpus configuration is required');
const corpus = loadProgressiveCorpus(options);

export const getStaticPaths = (() =>
  getProgressivePaths(corpus.root).map((entry) => ({ params: { path: entry.path } }))) satisfies GetStaticPaths;

type Params = InferGetStaticParamsType<typeof getStaticPaths>;

export const GET: APIRoute<never, Params> = (context) => {
  const routePath = context.params.path;
  const site = new URL(ensureTrailingSlash(starlightLllmsTxtContext.base), context.site);
  const assetBaseUrl = new URL(options.assetBaseUrl || 'snapshot/', site);
  try {
    return new Response(renderProgressiveNode(corpus, routePath, site, assetBaseUrl), {
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    });
  } catch {
    return new Response('Not found', { status: 404 });
  }
};
