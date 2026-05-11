---
'starlight-llms-txt': minor
---

Add a top-level `removeSelectors` option that strips elements matching the provided CSS selectors from every generated text output (`llms.txt`, `llms-full.txt`, `llms-small.txt`, and any `customSets`).

Selectors are matched with [`hast-util-select`](https://github.com/syntax-tree/hast-util-select), the same engine that powers `minify.customSelectors`. Unlike `minify.customSelectors`, which is only applied when generating `llms-small.txt`, `removeSelectors` is applied unconditionally to every bundle, so it can be used to remove transient HTML injected by docs-site rendering plugins (for example, code-block hover popovers from `expressive-code-twoslash`) that would otherwise leak into the Markdown shipped to LLM tooling.

```ts
starlightLlmsTxt({
  removeSelectors: ['.twoslash-popup-container', '.twoslash-error-box'],
}),
```
