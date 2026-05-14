---
'starlight-llms-txt': minor
---

Extend the `customSelectors` option to support per-output control.

The option is now exposed at the top level of the plugin configuration and accepts either of two shapes:

- **Array** (legacy) — selectors apply to `llms-small.txt` only, matching the existing scope of `minify.customSelectors`.
- **Object** with optional `small`, `full`, and `all` arrays — `small` applies to `llms-small.txt`, `full` applies to `llms-full.txt` and any `customSets` outputs, and `all` applies to both (merged with `small` and `full`).

The deprecated `minify.customSelectors` option keeps working: selectors listed there are merged additively into the `small` bucket so existing configurations are unaffected.

Use the new object shape to strip transient HTML injected by docs-site rendering plugins (for example, hover popovers from [`expressive-code-twoslash`](https://www.npmjs.com/package/expressive-code-twoslash)) from every generated output:

```ts
starlightLlmsTxt({
  customSelectors: {
    all: ['.twoslash-popup-container', '.twoslash-error-box'],
  },
}),
```
