---
'starlight-llms-txt': minor
---

Enforces llms.txt files to be prerendered at build time.
Previously, sites using Astro’s `output: server` configuration would generate llms.txt files on-demand, which can be slow, and additionally was incompatible with the [custom sets](https://delucis.github.io/starlight-llms-txt/configuration/#customsets) feature.
This change means that llms.txt files are statically generated even for sites using `output: server`.

⚠️ **Potentially breaking change:** If you were relying on on-demand rendered llms.txt files, for example by using middleware to gate access, this may be a breaking change. Please [share your use case](https://github.com/delucis/starlight-llms-txt/issues) to let us know if you need this.
