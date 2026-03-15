---
"starlight-llms-txt": minor
---

Add individual Markdown file generation for each documentation page

Implements the second part of the llmstxt.org standard proposal by generating clean Markdown versions of each documentation page. These individual `.md` files are accessible at the same URL path with `.md` appended, allowing LLMs to fetch specific documentation pages on-demand.

New configuration option:

- `perPageMarkdown`: Enable individual page generation. Set to `true` for defaults, or an object for advanced configuration:
  - `extensionStrategy`: Control URL pattern - `'append'` or `'replace'` (default: `'append'`)
  - `excludePages`: Exclude specific pages from .md generation (default: `['404']`)
