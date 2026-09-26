# starlight-llms-txt

## 2.1.0

### Minor Changes

- [#651](https://github.com/f5-sales-demo/starlight-llms-txt/pull/651) [`cee3ef6`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/cee3ef6613f459a4bd42ccdd070606019ce74c14) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - # Progressive external corpora
  
  Add progressive, English-only machine-readable routes for verified external Markdown corpora.

## 2.0.0

### Major Changes

- [#614](https://github.com/f5-sales-demo/starlight-llms-txt/pull/614) [`8f34c7d`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/8f34c7d1bde8f5ed59a22cd8ef982bd9337aead6) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - <!-- markdownlint-disable MD041 -->
  Require Node.js 24.19 or newer and modernize the Changesets release toolchain.
  <!-- markdownlint-enable MD041 -->

### Patch Changes

- [#601](https://github.com/f5-sales-demo/starlight-llms-txt/pull/601) [`d46422d`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/d46422d1c3b44dea38c6c8e4b15243e86620e7cf) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - <!-- markdownlint-disable MD041 -->
  Apply promote and demote patterns relative to configured locale prefixes, and
  preserve directory children when an ancestor index sorts after its descendants.
  <!-- markdownlint-enable MD041 -->

## 1.4.1

### Patch Changes

- [#363](https://github.com/f5-sales-demo/starlight-llms-txt/pull/363) [`e64f25f`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/e64f25fe44cce873f0c47319b8577b2e4352dd6a) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Align the runtime MDX integration and development toolchain with Astro 7 so consumers no longer need a dependency override.

## 1.4.0

### Minor Changes

- [#338](https://github.com/f5-sales-demo/starlight-llms-txt/pull/338) [`65e1570`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/65e1570875591bdce11f6856dd869ca926a3f002) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Generate the llms.txt surface for every locale, not just the default one.

  A multilingual site previously produced `/<locale>/llms-full.txt` and
  `/<locale>/llms-small.txt` that nothing linked to, and no per-locale index or
  tiered hierarchy at all — so a non-default-locale consumer had no entry point and
  no progressive path, only a single multi-hundred-kilobyte document.

  - New `/[locale]/llms.txt` index for every locale that occupies a URL path
    segment, including the default locale. The default locale's index links the
    existing root documents rather than duplicating them.
  - The `/_llms-txt/` tiered hierarchy now covers every locale. Document ids carry
    the locale in their first path segment, so its top tier becomes a language
    selector with the full depth of tiers beneath each language.
  - The root `llms.txt` gains a `## Translations` block listing each other
    language's index.

  Sites with a single locale, and sites whose default locale is `root`, are
  unaffected: no `/root/…` route is emitted and their `llms.txt` is unchanged.

## 1.3.1

### Patch Changes

- [#195](https://github.com/f5-sales-demo/starlight-llms-txt/pull/195) [`5b734d4`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/5b734d4affd4e288238703f774f1215c7197847d) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Widen `peerDependencies.astro` from `^6.0.0` to `>=6.0.0` so consumers can use astro 7+.

## 1.3.0

### Minor Changes

- [#41](https://github.com/f5-sales-demo/starlight-llms-txt/pull/41) [`193dd0d`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/193dd0d1bc4b8870a40f7fdf4fbf5435b04fba96) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Add auto-tiered `.txt` hierarchy for progressive AI discovery.
  Every hint link in `llms.txt` now points to a `.txt` file. Content lives only at leaf nodes; intermediate tiers contain metadata hints. Replaces `customSets` and `perPageMarkdown` with a single `tieredHierarchy` option (enabled by default).

## 1.2.2

### Patch Changes

- [#30](https://github.com/f5-sales-demo/starlight-llms-txt/pull/30) [`a4e3c1c`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/a4e3c1c5b9135f7b311733e6982a5e7ae0ff49e0) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Deduplicate Sections entries when a node matches a custom set.
  This prevents duplicate Guides/Functions lines in the llms.txt output for subcategory-aware sites.

## 1.2.1

### Patch Changes

- [#25](https://github.com/f5-sales-demo/starlight-llms-txt/pull/25) [`068535a`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/068535ab4d725cc0c9095f0162031c306a0675a3) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Make ## Sections link to custom set \_llms-txt/\*.txt files instead of individual page URLs when a section node matches a custom set label.
  When sidebarNav is enabled, custom sets are moved from Documentation Sets into Sections to avoid duplication.

## 1.2.0

### Minor Changes

- [#18](https://github.com/f5-sales-demo/starlight-llms-txt/pull/18) [`f850ddd`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/f850dddf7f7791c11ac15c0d1dfc379bb4262351) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Add subcategory-aware grouping to section tree and auto-generate custom sets from frontmatter

## 1.1.0

### Minor Changes

- [#3](https://github.com/f5-sales-demo/starlight-llms-txt/pull/3) [`c59c96d`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/c59c96d3a3569552c3b70dec2cbf253d2bc9ccaa) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Add categorized federation support.
  Federated sites can now be grouped by category with optional section headings and descriptions. Fully backwards-compatible — when no categories are defined, rendering is unchanged.

## 1.0.0

### Major Changes

- [#1](https://github.com/f5-sales-demo/starlight-llms-txt/pull/1) [`9ef7e93`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/9ef7e93d1685e1d5ccc0dd43f0b4de6dded1522f) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Initial release of the F5 XC Sales Demos fork, derived from `starlight-llms-txt@0.8.1`. Adds:

  - `perPageMarkdown` — per-page `.md` endpoints (Tier 4 routing in the xcsh#223 cascading knowledge hierarchy). Rebased from [delucis#32](https://github.com/delucis/starlight-llms-txt/pull/32) by Matthias Vallentin, with `excludePages` extended to accept glob patterns.
  - `sidebarNav` — sidebar hierarchy in `llms.txt` (Tier 2 routing), with frontmatter descriptions inlined automatically.
  - `federatedSites` — cross-repo links block in `llms.txt` (Tier 1 routing).

  The `starlight-llms-txt` package is authored by Chris Swithinbank (delucis). This fork exists to ship features needed by the f5-sales-demo documentation federation; we intend to upstream compatible features once they have been validated in production.

### Minor Changes

- [#1](https://github.com/f5-sales-demo/starlight-llms-txt/pull/1) [`940de8c`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/940de8ce11bd6d7124b6e41708c991adc576dc59) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Add `federatedSites` option.
  When set to a non-empty array, the plugin includes a `## Federated Sites` block in `llms.txt` listing links to other sites' `llms.txt` entry points. Intended for docs portals that federate out to product-specific documentation.

- [#1](https://github.com/f5-sales-demo/starlight-llms-txt/pull/1) [`a8e692c`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/a8e692c82c96bbfe36d3fc993d2fca4d0d5dc74e) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Add individual Markdown file generation for each documentation page

  Implements the second part of the llmstxt.org standard proposal by generating clean Markdown versions of each documentation page. These individual `.md` files are accessible at the same URL path with `.md` appended, allowing LLMs to fetch specific documentation pages on-demand.

  New configuration option:

  - `perPageMarkdown`: Enable individual page generation. Set to `true` for defaults, or an object for advanced configuration:
    - `extensionStrategy`: Control URL pattern - `'append'` or `'replace'` (default: `'append'`)
    - `excludePages`: Exclude specific pages from .md generation (default: `['404']`)

- [#1](https://github.com/f5-sales-demo/starlight-llms-txt/pull/1) [`46d0562`](https://github.com/f5-sales-demo/starlight-llms-txt/commit/46d0562410dd4ddea05fd6f3b9b4bfb732253891) Thanks [@robinmordasiewicz](https://github.com/robinmordasiewicz)! - Add `sidebarNav` option.
  When enabled, the plugin includes a `## Sections` block in `llms.txt` with the site's pages grouped hierarchically. Entries include frontmatter descriptions inline when present.

## 0.8.1

### Patch Changes

- [`29e5efb`](https://github.com/delucis/starlight-llms-txt/commit/29e5efb3a7d4d8b2167696e87b7f4d60db1ac93a) Thanks [@mvanhorn](https://github.com/mvanhorn)! - Strips HTML comments from llms.txt files. `<!-- ...  -->` style comments in `.md` files are no longer emitted in the generated files.

## 0.8.0

### Minor Changes

- [#80](https://github.com/delucis/starlight-llms-txt/pull/80) [`dea7b22`](https://github.com/delucis/starlight-llms-txt/commit/dea7b22b6821168b9982fa9d8840163c6f55b70e) Thanks [@nonoakij](https://github.com/nonoakij)! - Adds support for Astro v6 and Starlight v0.38, drops support for lower versions.

## 0.7.0

### Minor Changes

- [#43](https://github.com/delucis/starlight-llms-txt/pull/43) [`1db4591`](https://github.com/delucis/starlight-llms-txt/commit/1db45917d329e7e2ec00630a0c517b973c08fe5f) Thanks [@sanscontext](https://github.com/sanscontext)! - Enforces llms.txt files to be prerendered at build time.
  Previously, sites using Astro’s `output: server` configuration would generate llms.txt files on-demand, which can be slow, and additionally was incompatible with the [custom sets](https://delucis.github.io/starlight-llms-txt/configuration/#customsets) feature.
  This change means that llms.txt files are statically generated even for sites using `output: server`.

  ⚠️ **Potentially breaking change:** If you were relying on on-demand rendered llms.txt files, for example by using middleware to gate access, this may be a breaking change. Please [share your use case](https://github.com/delucis/starlight-llms-txt/issues) to let us know if you need this.

## 0.6.1

### Patch Changes

- [#49](https://github.com/delucis/starlight-llms-txt/pull/49) [`56b8233`](https://github.com/delucis/starlight-llms-txt/commit/56b823325bd42374300597a82b0f04e289be4b25) Thanks [@delucis](https://github.com/delucis)! - No code changes. This release is the first published using OIDC trusted publisher configuration for improved security.

## 0.6.0

### Minor Changes

- [#30](https://github.com/delucis/starlight-llms-txt/pull/30) [`a1650c9`](https://github.com/delucis/starlight-llms-txt/commit/a1650c92b16377d9abdcccc8b2a68b34bc695796) Thanks [@alvinometric](https://github.com/alvinometric)! - Adds a new `rawContent` option to skip the Markdown processing pipeline

## 0.5.1

### Patch Changes

- [#22](https://github.com/delucis/starlight-llms-txt/pull/22) [`2a8102a`](https://github.com/delucis/starlight-llms-txt/commit/2a8102a2554ac80495568b89acba2bb5a437d206) Thanks [@florian-lefebvre](https://github.com/florian-lefebvre)! - Fixes output of Expressive Code `diff` codeblocks with a `lang` attribute

## 0.5.0

### Minor Changes

- [#18](https://github.com/delucis/starlight-llms-txt/pull/18) [`52838f6`](https://github.com/delucis/starlight-llms-txt/commit/52838f63fc5280436982880744921dac923d4be2) Thanks [@pelikhan](https://github.com/pelikhan)! - Add page separator configuration object

## 0.4.1

### Patch Changes

- [#13](https://github.com/delucis/starlight-llms-txt/pull/13) [`629fa9b`](https://github.com/delucis/starlight-llms-txt/commit/629fa9b00444a70ebf9aac3e15375f400f8a10cc) Thanks [@jumski](https://github.com/jumski)! - Filters out draft pages from output

## 0.4.0

### Minor Changes

- [#10](https://github.com/delucis/starlight-llms-txt/pull/10) [`7f914f5`](https://github.com/delucis/starlight-llms-txt/commit/7f914f526dbe504ed3e3763864fd9ec1d5150d0d) Thanks [@delucis](https://github.com/delucis)! - Adds a new `customSets` option to support breaking up large docs into multiple custom document sets

### Patch Changes

- [`0c0678d`](https://github.com/delucis/starlight-llms-txt/commit/0c0678da19f1f9981f808a1fa0e1a01c77a26b4d) Thanks [@delucis](https://github.com/delucis)! - Improves rendering of Starlight’s `<FileTree>` component by removing “Directory” labels

## 0.3.0

### Minor Changes

- [#7](https://github.com/delucis/starlight-llms-txt/pull/7) [`cba125e`](https://github.com/delucis/starlight-llms-txt/commit/cba125ed259601895ba78f6da95a55564b914470) Thanks [@hippotastic](https://github.com/hippotastic)! - Adds options to promote or demote pages in the order of the `llms-full.txt` and `llms-small.txt` output files

## 0.2.1

### Patch Changes

- [`39760e7`](https://github.com/delucis/starlight-llms-txt/commit/39760e70e921b685bc6dc6a5338f8f80bf79e57e) Thanks [@delucis](https://github.com/delucis)! - Removes Expressive Code’s “Terminal Window” labels from output

- [`26fa616`](https://github.com/delucis/starlight-llms-txt/commit/26fa616793798bda41911bfe7dc229475f89db26) Thanks [@delucis](https://github.com/delucis)! - Fixes a bug where pages excluded using the `exclude` configuration option were excluded in `llms-full.txt` instead of only in `llms-small.txt`

## 0.2.0

### Minor Changes

- [#4](https://github.com/delucis/starlight-llms-txt/pull/4) [`a4a77ca`](https://github.com/delucis/starlight-llms-txt/commit/a4a77ca433b7cee7cbeb3c603498e760cd037867) Thanks [@delucis](https://github.com/delucis)! - Adds support for generating a smaller `llms-small.txt` file for smaller context windows

- [`618fa88`](https://github.com/delucis/starlight-llms-txt/commit/618fa882d29bc4b7ce054392c9b65d97ce1ceb82) Thanks [@delucis](https://github.com/delucis)! - Adds support for including additional optional links in the main `llms.txt` entrypoint

### Patch Changes

- [#4](https://github.com/delucis/starlight-llms-txt/pull/4) [`a4a77ca`](https://github.com/delucis/starlight-llms-txt/commit/a4a77ca433b7cee7cbeb3c603498e760cd037867) Thanks [@delucis](https://github.com/delucis)! - Sort pages in llms.txt output

## 0.1.2

### Patch Changes

- [`d5ca030`](https://github.com/delucis/starlight-llms-txt/commit/d5ca0307192585f141164dd8328f244f32db5a90) Thanks [@delucis](https://github.com/delucis)! - Improves rendering of Starlight Tabs component in output

## 0.1.1

### Patch Changes

- [`04f641c`](https://github.com/delucis/starlight-llms-txt/commit/04f641c48dd70acf480c80df26d9e2f774510428) Thanks [@delucis](https://github.com/delucis)! - Preserves language metadata on code blocks

## 0.1.0

### Minor Changes

- [`249438b`](https://github.com/delucis/starlight-llms-txt/commit/249438b23d2998ef79a1bbb19ac7a532938f7ade) Thanks [@delucis](https://github.com/delucis)! - Initial release
