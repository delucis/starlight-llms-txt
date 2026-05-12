---
'starlight-llms-txt': minor
---

Preserves the contents of code blocks when collapsing whitespace in `llms-small.txt`.

Previously, the `minify.whitespace` option collapsed every whitespace run — including newlines inside fenced code blocks — into a single space, so multi-line code samples ended up on one line. Now, fenced code blocks keep their original newlines and indentation while whitespace in prose still collapses for token efficiency.

A new `minify.collapseCodeBlocks` option controls this behavior. Set it to `true` to restore the previous flatten-everything output.
