---
title: Advanced Usage
description: Advanced usage patterns for starlight-llms-txt
---

This is a test page for nested documentation paths.

## Advanced Configuration

You can configure the plugin with various advanced options.

### Custom Sets

Create specialized subsets of your documentation:

```js
customSets: [
  {
    label: 'API Reference',
    paths: ['api/**'],
    description: 'Complete API documentation'
  }
]
```

### Individual Page Markdown

Generate individual markdown files for each page:

```js
generatePageMarkdown: true,
markdownFilePattern: 'append'
```