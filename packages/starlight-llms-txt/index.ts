import type { StarlightPlugin } from '@astrojs/starlight/types';
import { AstroError } from 'astro/errors';
import { getLlmsRoutePlan } from './route-plan';
import type { ProjectContext, StarlightLllmsTextOptions } from './types';

export type { ProgressiveCorpusOptions } from './types';

export default function starlightLlmsTxt(opts: StarlightLllmsTextOptions = {}): StarlightPlugin {
  return {
    name: 'starlight-llms-txt',
    hooks: {
      setup({ astroConfig, addIntegration, config }) {
        if (!astroConfig.site) {
          throw new AstroError(
            '`site` not set in Astro configuration',
            'The `starlight-llms-txt` plugin requires setting `site` in your Astro configuration file.',
          );
        }
        addIntegration({
          name: 'starlight-llms-txt',
          hooks: {
            'astro:config:setup'({ injectRoute, updateConfig }) {
              const progressiveCorpus = opts.progressiveCorpus;
              const tieredHierarchy = progressiveCorpus ? true : (opts.tieredHierarchy ?? true);
              for (const route of getLlmsRoutePlan(Boolean(progressiveCorpus), tieredHierarchy)) {
                injectRoute({
                  entrypoint: new URL(route.entrypoint, import.meta.url),
                  pattern: route.pattern,
                  prerender: true,
                });
              }

              const projectContext: ProjectContext = {
                base: astroConfig.base,
                title: opts.projectName ?? config.title,
                description: opts.description ?? config.description,
                details: opts.details,
                optionalLinks: opts.optionalLinks ?? [],
                minify: opts.minify ?? {},
                promote: opts.promote ?? ['index', 'overview'],
                demote: opts.demote ?? [],
                exclude: opts.exclude ?? [],
                defaultLocale: config.defaultLocale,
                locales: config.locales,
                pageSeparator: opts.pageSeparator ?? '\n\n',
                rawContent: opts.rawContent ?? false,
                sidebarNav: opts.sidebarNav ?? false,
                tieredHierarchy,
                federatedSites: opts.federatedSites ?? [],
                federatedSiteCategories: opts.federatedSiteCategories ?? [],
                ...(progressiveCorpus ? { progressiveCorpus } : {}),
              };

              const modules = {
                'virtual:starlight-llms-txt/context': `export const starlightLllmsTxtContext = ${JSON.stringify(
                  projectContext,
                )}`,
              };
              const resolutionMap = Object.fromEntries(
                (Object.keys(modules) as (keyof typeof modules)[]).map((key) => [resolveVirtualModuleId(key), key]),
              );

              updateConfig({
                vite: {
                  plugins: [
                    {
                      name: 'vite-plugin-starlight-llms-text',
                      resolveId(id): string | undefined {
                        if (id in modules) return resolveVirtualModuleId(id);
                        return undefined;
                      },
                      load(id): string | undefined {
                        const resolution = resolutionMap[id];
                        if (resolution) return modules[resolution];
                        return undefined;
                      },
                    },
                  ],
                },
              });
            },
          },
        });
      },
    },
  };
}

function resolveVirtualModuleId<T extends string>(id: T): `\0${T}` {
  return `\0${id}`;
}
