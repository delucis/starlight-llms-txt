import type { StarlightUserConfig } from '@astrojs/starlight/types';
import type { AstroConfig } from 'astro';

interface CustomSetUserConfig {
	/** Label for this subset of documentation, e.g. `"Tutorial"` */
	label: string;
	/** An array of page slugs or glob patterns that match page slugs for docs to include in this set., e.g. `["tutorial/**"]` */
	paths: string[];
	/** An optional description for this subset of the documentation, e.g. `"a step-by-step tutorial to build a new project"` */
	description?: string;
}

interface CustomSet extends CustomSetUserConfig {
	slug: string;
}

/** Project configuration metadata passed from the integration to the routes in a virtual module. */
export interface ProjectContext {
	base: AstroConfig['base'];
	defaultLocale: StarlightUserConfig['defaultLocale'];
	locales: StarlightUserConfig['locales'];
	title: StarlightUserConfig['title'];
	description: StarlightUserConfig['description'];
	details: StarlightLllmsTextOptions['details'];
	optionalLinks: NonNullable<StarlightLllmsTextOptions['optionalLinks']>;
	customSets: Array<CustomSet>;
	minify: NonNullable<StarlightLllmsTextOptions['minify']>;
	promote: NonNullable<StarlightLllmsTextOptions['promote']>;
	demote: NonNullable<StarlightLllmsTextOptions['demote']>;
	exclude: NonNullable<StarlightLllmsTextOptions['exclude']>;
	pageSeparator: NonNullable<StarlightLllmsTextOptions['pageSeparator']>;
	rawContent: NonNullable<StarlightLllmsTextOptions['rawContent']>;
	customSelectors: NonNullable<StarlightLllmsTextOptions['customSelectors']>;
	trailingSlash: AstroConfig['trailingSlash'];
}

/** Plugin user options. */
export interface StarlightLllmsTextOptions {
	/**
	 * Provide a custom name for this project or software. This will be used in `llms.txt` to identify
	 * what the documentation is for.
	 *
	 * Default: the value of Starlight’s `title` option.
	 *
	 * @example "FastHTML"
	 */
	projectName?: string;

	/**
	 * Set a custom description for your documentation site to share with large language models.
	 * Can include Markdown syntax. Will be displayed in `llms.txt` immediately after the file’s title.
	 *
	 * According to <https://llmstxt.org/> this should be:
	 *
	 * > a short summary of the project, containing key information necessary for understanding the
	 * > rest of the file
	 *
	 * Default: The value of Starlight’s `description` option.
	 *
	 * @example
	 * ```md
	 * FastHTML is a python library which brings together Starlette, Uvicorn, HTMX, and fastcore's `FT` "FastTags" into a library for creating server-rendered hypermedia applications.
	 * ```
	 */
	description?: string;

	/**
	 * Provide addition details to add after the description in `llms.txt`.
	 *
	 * According to <https://llmstxt.org/> this should be:
	 *
	 * > Zero or more markdown sections (e.g. paragraphs, lists, etc) of any type except headings,
	 * > containing more detailed information about the project and how to interpret the provided files
	 *
	 * @example
	 * ```md
	 * Important notes:
	 *
	 * - Although parts of its API are inspired by FastAPI, it is *not* compatible with FastAPI syntax and is not targeted at creating API services
	 * - FastHTML is compatible with JS-native web components and any vanilla JS library, but not with React, Vue, or Svelte.
	 * ```
	 */
	details?: string;

	/**
	 * An array of optional links to add to the `llms.txt` entrypoint.
	 *
	 * URLs provided here can be skipped by the LLM if a shorter context is needed.
	 * Use it for secondary information which is not already in your docs content.
	 */
	optionalLinks?: Array<{
		label: string;
		url: string;
		description?: string;
	}>;

	/**
	 * An array of custom subsets of your docs to process and add to the `llms.txt` entrypoint.
	 */
	customSets?: Array<CustomSetUserConfig>;

	/** Control what elements are removed in `llms-small.txt`. */
	minify?: {
		/**
		 * Remove Starlight note asides in `llms-small.txt`.
		 * @default true
		 */
		note?: boolean;
		/**
		 * Remove Starlight tip asides in `llms-small.txt`.
		 * @default true
		 */
		tip?: boolean;
		/**
		 * Remove Starlight caution asides in `llms-small.txt`.
		 * @default false
		 */
		caution?: boolean;
		/**
		 * Remove Starlight danger asides in `llms-small.txt`.
		 * @default false
		 */
		danger?: boolean;
		/**
		 * Remove HTML `<details>` elements in `llms-small.txt`.
		 * @default true
		 */
		details?: boolean;
		/**
		 * Collapse whitespace in `llms-small.txt`.
		 * @default true
		 */
		whitespace?: boolean;

		/**
		 * When `whitespace` is enabled, also collapse whitespace inside fenced
		 * code blocks (``` and ~~~). By default, the bodies of fenced code
		 * blocks keep their original newlines (and indentation) so multi-line
		 * code samples stay multi-line in `llms-small.txt`.
		 *
		 * Whitespace in prose (paragraphs, lists, etc.) is always collapsed
		 * when `whitespace` is enabled; this option only controls whether
		 * code-block bodies are exempt. Both variable-length fences (e.g.
		 * four or more backticks) and tilde fences are recognized.
		 *
		 * Set this to `true` to restore the previous behavior of collapsing
		 * every whitespace run, including newlines inside code fences, into a
		 * single space.
		 *
		 * Has no effect when `whitespace` is `false`.
		 *
		 * @default false
		 */
		collapseCodeBlocks?: boolean;

		/**
		 * Custom selectors to exclude when generating `llms-small.txt`.
		 *
		 * @deprecated Use the top-level
		 * {@link StarlightLllmsTextOptions.customSelectors | `customSelectors`} option instead.
		 * Selectors listed here continue to apply to `llms-small.txt` only, additively with any
		 * selectors listed in `customSelectors.small` and `customSelectors.all`.
		 *
		 * @default []
		 *
		 * @example
		 * // Filter out elements with the class name `sponsors` when creating llms-small.txt
		 * customSelectors: [".sponsors"],
		 */
		customSelectors?: string[];
	};

	/**
	 * Micromatch expressions to match page IDs that should be sorted to the top of the output.
	 *
	 * @default
	 * ['index*']
	 */
	promote?: string[];

	/**
	 * Micromatch expressions to match page IDs that should be sorted to the end of the output.
	 *
	 * If a page matches both `promote` and `demote`, it will be demoted.
	 *
	 * @default []
	 */
	demote?: string[];

	/**
	 * Slugs of pages to exclude from `llms-small.txt`. Supports glob patterns.
	 *
	 * @default []
	 *
	 * @example
	 * // Ignore an old page and all tutorial pages when creating llms-small.txt
	 * exclude: ["old-page", "tutorial/**"],
	 */
	exclude?: string[];

	/**
	 * String used to separate pages in the generated text.
	 * @default "\n\n"
	 */
	pageSeparator?: string;

	/**
	 * When enabled, returns raw content without processing MDX components.
	 * This skips the HTML rendering and Markdown conversion pipeline for faster processing.
	 * Useful when you want to preserve the original Markdown content without component processing.
	 *
	 * @default false
	 */
	rawContent?: boolean;

	/**
	 * CSS-style selectors matching elements that should be removed from the rendered HTML
	 * before it is converted to Markdown.
	 *
	 * Selectors are tested with
	 * [`hast-util-select`’s matching features](https://github.com/syntax-tree/hast-util-select#support)
	 * and should match your site’s rendered HTML output.
	 *
	 * Two shapes are supported:
	 *
	 * - **Array** — selectors apply to `llms-small.txt` only (same scope as the
	 *   deprecated {@link StarlightLllmsTextOptions.minify | `minify.customSelectors`} option).
	 * - **Object** with optional `small`, `full`, and `all` arrays:
	 *   - `small` applies to `llms-small.txt`.
	 *   - `full` applies to `llms-full.txt` and any `customSets` outputs.
	 *   - `all` applies to both (merged with `small` and `full`).
	 *
	 * Selectors listed via the legacy `minify.customSelectors` option are merged additively
	 * into the `small` bucket so existing configurations keep working.
	 *
	 * @default []
	 *
	 * @example
	 * // Array form (legacy): strip a sponsors banner from llms-small.txt only.
	 * customSelectors: ['.sponsors-banner'],
	 *
	 * @example
	 * // Object form: strip code-block hover popovers from every output, while keeping a
	 * // small-only filter for an interactive demo and a full-only filter for verbose notes.
	 * customSelectors: {
	 *   all: ['.twoslash-popup-container', '.twoslash-error-box'],
	 *   small: ['interactive-demo'],
	 *   full: ['.verbose-only'],
	 * },
	 */
	customSelectors?:
		| string[]
		| {
				/** Selectors applied when generating `llms-small.txt`. */
				small?: string[];
				/** Selectors applied when generating `llms-full.txt` and any `customSets` outputs. */
				full?: string[];
				/** Selectors applied to every generated output (merged with `small` and `full`). */
				all?: string[];
		  };

	/**
	 * Set to `false` to disable generation of individual `.md` files for each documentation page.
	 * @default true
	 */
	mdRoutes?: false;
}
