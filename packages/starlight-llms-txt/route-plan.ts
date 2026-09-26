export interface LlmsRouteDefinition {
  entrypoint: string;
  pattern: string;
}

export function getLlmsRoutePlan(progressiveCorpus: boolean, tieredHierarchy: boolean): LlmsRouteDefinition[] {
  const routes: LlmsRouteDefinition[] = [
    {
      entrypoint: progressiveCorpus ? './progressive-llms.txt.ts' : './llms.txt.ts',
      pattern: '/llms.txt',
    },
    {
      entrypoint: progressiveCorpus ? './progressive-llms-full.txt.ts' : './llms-full.txt.ts',
      pattern: '/llms-full.txt',
    },
  ];
  if (!progressiveCorpus) {
    routes.push(
      { entrypoint: './llms-small.txt.ts', pattern: '/llms-small.txt' },
      { entrypoint: './llms-locale.txt.ts', pattern: '/[locale]/llms.txt' },
      { entrypoint: './llms-locale-full.txt.ts', pattern: '/[locale]/llms-full.txt' },
      { entrypoint: './llms-locale-small.txt.ts', pattern: '/[locale]/llms-small.txt' },
    );
  }
  if (tieredHierarchy || progressiveCorpus) {
    routes.push({
      entrypoint: progressiveCorpus ? './progressive-tiered.txt.ts' : './llms-tiered.txt.ts',
      pattern: '/_llms-txt/[...path].txt',
    });
  }
  return routes;
}
