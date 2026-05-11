---
'starlight-llms-txt': minor
---

Preserve the contents of fenced code blocks when collapsing whitespace in `llms-small.txt`.

Previously, the `minify.whitespace` option collapsed every whitespace run — including newlines inside fenced code blocks — into a single space, so multi-line code samples ended up on one line. Now, fenced code blocks (` ``` ` and `~~~`, of any fence length ≥ 3) keep their original newlines and indentation while whitespace in prose still collapses for token efficiency.

A new `minify.collapseCodeBlocks` option (default `false`) controls the new behavior. Set it to `true` to restore the previous flatten-everything output.
