---
'starlight-llms-txt': minor
---

Resolve in-page fragment links per page so they stay unambiguous in concatenated output

In-page links such as `[Renderers](#renderers)` were copied verbatim into the generated Markdown. Once every page is concatenated into `llms-full.txt` (and `llms-small.txt` / custom sets), a bare `#renderers` no longer identifies which page it belongs to. Such links are now resolved against the page being processed and kept **root-relative** — e.g. `#renderers` becomes `/docs/guide/#renderers` — so they stay unambiguous after concatenation while remaining host- and version-neutral (important for sites served from multiple hosts/versions).
