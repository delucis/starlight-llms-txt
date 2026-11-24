---
'starlight-llms-txt': patch
---

Fixes two Markdown output issues: removes Starlight’s “Section titled …” heading anchor links, and places `+`/`-` diff markers at the start of the line (including for plain `diff` code blocks, where they were previously dropped).
