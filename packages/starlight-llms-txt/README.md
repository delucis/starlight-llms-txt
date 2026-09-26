# @f5-sales-demo/starlight-llms-txt

Fork of [`starlight-llms-txt`](https://github.com/delucis/starlight-llms-txt) by Chris Swithinbank, extended for the [f5-sales-demo](https://github.com/f5-sales-demo) documentation federation.

## Additions over upstream

- `perPageMarkdown` — per-page `.md` endpoints
- `sidebarNav` — sidebar hierarchy in `llms.txt`, with frontmatter descriptions inlined automatically
- `federatedSites` — cross-repo links for federated doc portals
- `progressiveCorpus` — English-only progressive indices and full-document
  leaves sourced from a verified external Markdown corpus

A progressive corpus stays outside the Starlight `docs` collection, so its
documents do not create HTML pages. Configure the immutable mounted snapshot:

```js
starlightLlmsTxt({
  progressiveCorpus: {
    manifest: '/corpus/manifest.json',
    contentRoot: '/corpus',
    assetBaseUrl: '/my-site/snapshot/',
    title: 'F5 Docs Corpus',
  },
})
```

This mode emits `/llms.txt`, a link-only `/llms-full.txt`, and progressively
narrower `/_llms-txt/<source>/<path>.txt` routes. It deliberately omits
`llms-small.txt` and locale routes.

See the [configuration docs](https://f5-sales-demo.github.io/starlight-llms-txt/configuration/) for the full option reference.

## Relationship to upstream

Compatible features are intended to land upstream at `delucis/starlight-llms-txt` after production validation. Until then, this package tracks the f5-sales-demo integration needs.

## License

MIT — copyright Chris Swithinbank, fork modifications by f5-sales-demo contributors.
