import type { StarlightUserConfig } from '@astrojs/starlight/types';
import type { AstroConfig } from 'astro';
import type { ProgressiveCorpusOptions } from './progressive-corpus';

export type { ProgressiveCorpusOptions } from './progressive-corpus';

interface FederatedSiteCategoryUserConfig {
  id: string;
  label: string;
  description?: string;
}

export interface ProjectContext {
  base: AstroConfig['base'];
  defaultLocale: StarlightUserConfig['defaultLocale'];
  locales: StarlightUserConfig['locales'];
  title: StarlightUserConfig['title'];
  description: StarlightUserConfig['description'];
  details: StarlightLllmsTextOptions['details'];
  optionalLinks: NonNullable<StarlightLllmsTextOptions['optionalLinks']>;
  minify: NonNullable<StarlightLllmsTextOptions['minify']>;
  promote: NonNullable<StarlightLllmsTextOptions['promote']>;
  demote: NonNullable<StarlightLllmsTextOptions['demote']>;
  exclude: NonNullable<StarlightLllmsTextOptions['exclude']>;
  pageSeparator: NonNullable<StarlightLllmsTextOptions['pageSeparator']>;
  rawContent: NonNullable<StarlightLllmsTextOptions['rawContent']>;
  sidebarNav: NonNullable<StarlightLllmsTextOptions['sidebarNav']>;
  tieredHierarchy: NonNullable<StarlightLllmsTextOptions['tieredHierarchy']>;
  federatedSites: NonNullable<StarlightLllmsTextOptions['federatedSites']>;
  federatedSiteCategories: NonNullable<StarlightLllmsTextOptions['federatedSiteCategories']>;
  progressiveCorpus?: ProgressiveCorpusOptions | undefined;
}

export interface StarlightLllmsTextOptions {
  projectName?: string;
  description?: string;
  details?: string;
  optionalLinks?: Array<{ label: string; url: string; description?: string }>;
  minify?: {
    note?: boolean;
    tip?: boolean;
    caution?: boolean;
    danger?: boolean;
    details?: boolean;
    whitespace?: boolean;
    customSelectors?: string[];
  };
  promote?: string[];
  demote?: string[];
  exclude?: string[];
  pageSeparator?: string;
  rawContent?: boolean;
  sidebarNav?: boolean;
  /**
   * When enabled, auto-generates a tiered `.txt` hierarchy under `/_llms-txt/`.
   * @default true
   */
  tieredHierarchy?: boolean;
  federatedSites?: Array<{
    label: string;
    url: string;
    description?: string;
    category?: string;
  }>;
  federatedSiteCategories?: Array<FederatedSiteCategoryUserConfig>;
  /**
   * Generate an English-only progressive hierarchy from a verified Markdown
   * corpus outside Starlight's docs collection.
   */
  progressiveCorpus?: ProgressiveCorpusOptions;
}
