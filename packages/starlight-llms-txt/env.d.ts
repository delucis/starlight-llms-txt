/// <reference types="../../docs/.astro/types.d.ts" />

declare module 'virtual:starlight-llms-txt/context' {
	export const starlightLllmsTxtContext: import('./types').ProjectContext;
}

declare module 'vfile' {
	interface DataMap {
		starlightLlmsTxt: {
			minify: boolean;
			/** Root-relative path of the page being processed. Used to qualify
			 * in-page fragment links (`#foo`) so they stay unambiguous once pages
			 * are concatenated into `llms-full.txt`. */
			pagePath?: string;
		};
	}
}
