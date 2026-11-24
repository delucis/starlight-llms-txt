---
title: Fixture
---

## Getting started

Some text.

### Nested heading

More text.

## Diff with a language

```diff lang="js"
export default defineConfig({
+  site: "https://example.com/",
  integrations: [
+    starlight({ title: "Docs" }),
  ],
});
```

## Inserted and deleted lines

```js ins={3} del={2}
function f() {
  return 1;
  return 2;
}
```

## Plain diff

```diff
 context
+added
-removed
```

## Unified diff with headers

```diff
--- a/file.txt
+++ b/file.txt
@@ -1,2 +1,2 @@
 context
-old
+new
```
