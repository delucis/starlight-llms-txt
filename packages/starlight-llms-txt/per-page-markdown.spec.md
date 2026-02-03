# Per-Page Markdown Endpoints

## Overview

Extend starlight-llms-txt to generate per-page `.md` endpoints for each documentation page, enabling LLM/agent optimization at the individual page level.

## Goals

1. **Per-page markdown** - Each HTML docs page available as `.md`
2. **SSR content negotiation** - Optional middleware for `Accept: text/markdown`
3. **Discovery via llms.txt** - List page URLs in optional `## Pages` section
4. **Backwards compatibility** - Keep existing `/llms.txt`, `/llms-small.txt`, `/llms-full.txt`

## Target Use Case

IDE agents (Claude Code, Cursor) fetching documentation during coding sessions.

## URL Mapping

### Algorithm: Doc Entry to Markdown URL

Given a Starlight docs collection entry, derive the markdown URL as follows:

```ts
function docEntryToMarkdownSlug(entry: CollectionEntry<'docs'>): string {
  // 1. Start with collection entry ID (e.g., "guides/intro.mdx")
  let slug = entry.id;

  // 2. Strip file extension (.md, .mdx)
  slug = slug.replace(/\.mdx?$/, '');

  // 3. Handle frontmatter slug override (if present)
  if (entry.data.slug) {
    slug = entry.data.slug;
  }

  // 4. Handle index files: "guides/index" -> "guides", "index" -> ""
  slug = slug.replace(/\/index$/, '');
  if (slug === 'index') slug = '';

  // 5. Apply base path from Astro config
  // Final URL: `${base}${slug}.md` (or `${base}index.md` if slug is empty)

  return slug || 'index';
}
```

### Examples

| Source File | Frontmatter `slug` | Base | Markdown URL |
|-------------|-------------------|------|--------------|
| `getting-started/intro.mdx` | (none) | `/` | `/getting-started/intro.md` |
| `guides/index.mdx` | (none) | `/` | `/guides.md` |
| `index.mdx` | (none) | `/` | `/index.md` |
| `api/auth.mdx` | `authentication` | `/` | `/authentication.md` |
| `getting-started/intro.mdx` | (none) | `/docs/` | `/docs/getting-started/intro.md` |

### Rules

- `.md` URLs never have trailing slashes (file semantics)
- Frontmatter `slug` overrides the file-path-derived slug
- Base path from `astro.config.mjs` is prepended
- HTML URLs follow site's `trailingSlash` config; markdown URLs do not

## Output Format

```yaml
---
title: "Page Title"
description: "Page description or tagline"
url: "https://example.com/getting-started/intro/"
---

# Content heading

Markdown content here...
```

### Frontmatter Fields

| Field | Source | Required |
|-------|--------|----------|
| `title` | `hero.title` or `data.title` | Yes |
| `description` | `hero.tagline` or `data.description` | No (omit if empty) |
| `url` | Canonical HTML page URL | Yes (if `site` configured) |

### YAML Serialization

Use `JSON.stringify()` for all string values to ensure valid YAML:

```ts
function serializeFrontmatter(fields: Record<string, string>): string {
  const lines = ['---'];
  for (const [key, value] of Object.entries(fields)) {
    if (value) {
      // JSON.stringify handles quotes, colons, newlines, special chars
      lines.push(`${key}: ${JSON.stringify(value)}`);
    }
  }
  lines.push('---');
  return lines.join('\n');
}
```

**Examples of edge cases handled:**

| Input | Serialized |
|-------|-----------|
| `Hello World` | `title: "Hello World"` |
| `Config: Advanced` | `title: "Config: Advanced"` |
| `Say "Hello"` | `title: "Say \"Hello\""` |
| `Line1\nLine2` | `title: "Line1\nLine2"` |

### Response Headers

```
Content-Type: text/markdown; charset=utf-8
```

## Feature Behavior

### Enabled by Default

Per-page markdown is enabled automatically when the plugin is installed. No additional config required.

### Locale Handling

Only default locale pages get `.md` endpoints. Matches existing `llms*.txt` behavior.

### Exclusions

Pages are excluded from `.md` generation if:
- `draft: true` in frontmatter
- Match any pattern in plugin's `exclude` config

### Collision Handling

If a source file would create a conflicting `.md` URL (e.g., `foo.md.mdx` → `/foo.md/` HTML and `/foo.md.md` markdown):
- Skip generating the `.md` file for that page
- Log a warning during build

## llms.txt Integration

Add optional `## Pages` section to `/llms.txt` listing all per-page markdown URLs:

```markdown
# Project Name

> Description

## Docs

- [Full documentation](/llms-full.txt)
- [Abridged documentation](/llms-small.txt)

## Pages

- [Getting Started](/getting-started.md): Introduction to the project
- [Configuration](/configuration.md): How to configure settings
```

Each entry includes:
- Page title as link text
- `.md` URL as link target
- Description (if available) after colon

## Content Negotiation

### How It Works by Deployment Mode

| Mode | Runtime Negotiation | Notes |
|------|---------------------|-------|
| **Static** | Not available | Astro middleware does not execute for prerendered pages at request time. Agents must request `.md` URLs directly, or use external infrastructure (reverse proxy, edge worker). |
| **SSR/Hybrid** | Supported | Middleware checks `Accept` header at request time and rewrites to `.md` endpoint. |

### Accept Header Parsing (RFC 7231)

Parse the `Accept` header respecting quality values (`q`) and specificity. Per RFC 7231:
- More specific media types take precedence over wildcards
- When specificity is equal, higher `q` wins
- `q=0` means "not acceptable" and explicitly rejects that type

**Design decision:** When markdown and HTML have equal `q` values, we default to HTML. This is a deliberate choice for backwards compatibility with browsers (which send `text/html` by default), not strict RFC ordering.

```ts
type MediaType = { type: string; q: number; specificity: number };

function parseAcceptHeader(accept: string): MediaType[] {
  if (!accept) return [];

  return accept
    .split(',')
    .map((part) => {
      const [type, ...params] = part.trim().split(';');
      let q = 1.0;
      for (const param of params) {
        const [key, value] = param.trim().split('=');
        if (key === 'q' && value) {
          q = parseFloat(value);
          if (isNaN(q)) q = 1.0;
        }
      }
      // Specificity: 3 = exact type, 2 = subtype wildcard, 1 = full wildcard
      const mediaType = type.trim();
      let specificity = 3;
      if (mediaType === '*/*') specificity = 1;
      else if (mediaType.endsWith('/*')) specificity = 2;

      return { type: mediaType, q, specificity };
    })
    .sort((a, b) => {
      // Sort by: specificity desc, then q desc
      if (a.specificity !== b.specificity) return b.specificity - a.specificity;
      return b.q - a.q;
    });
}

function prefersMarkdown(accept: string): boolean {
  const types = parseAcceptHeader(accept);

  // Track explicit rejections (q=0) separately from "not mentioned"
  let markdownQ: number | null = null;  // null = not mentioned
  let htmlQ: number | null = null;
  let markdownRejected = false;  // explicitly q=0
  let htmlRejected = false;

  for (const { type, q, specificity } of types) {
    // Exact matches - these override wildcards due to specificity sort
    if (type === 'text/markdown' || type === 'text/plain') {
      if (markdownQ === null) {
        if (q === 0) markdownRejected = true;
        else markdownQ = q;
      }
    }
    if (type === 'text/html' || type === 'application/xhtml+xml') {
      if (htmlQ === null) {
        if (q === 0) htmlRejected = true;
        else htmlQ = q;
      }
    }

    // Wildcard matches (only apply if no explicit match yet AND not rejected)
    if (type === 'text/*' || type === '*/*') {
      if (markdownQ === null && !markdownRejected) {
        if (q === 0) markdownRejected = true;
        else markdownQ = q;
      }
      if (htmlQ === null && !htmlRejected) {
        if (q === 0) htmlRejected = true;
        else htmlQ = q;
      }
    }
  }

  // If markdown explicitly rejected, return false
  if (markdownRejected) return false;

  // If HTML explicitly rejected and markdown is acceptable, return true
  if (htmlRejected && markdownQ !== null && markdownQ > 0) return true;

  // Compare q values (null treated as 0)
  const mdQ = markdownQ ?? 0;
  const htQ = htmlQ ?? 0;

  // Prefer markdown only if strictly higher quality than HTML
  // Default to HTML when equal or when neither specified
  return mdQ > htQ;
}
```

**Examples:**

| Accept Header | Markdown Q | HTML Q | Result |
|---------------|------------|--------|--------|
| `text/markdown` | 1.0 | null | Markdown |
| `text/html` | null | 1.0 | HTML |
| `text/markdown, text/html` | 1.0 | 1.0 | HTML (equal q, HTML default) |
| `text/markdown;q=0.9, text/html` | 0.9 | 1.0 | HTML (higher q) |
| `text/markdown, text/html;q=0.9` | 1.0 | 0.9 | Markdown (higher q) |
| `text/*;q=0.8, text/markdown;q=0.7` | 0.7 | 0.8 | HTML (specific md=0.7, wildcard html=0.8) |
| `*/*` | 1.0 | 1.0 | HTML (equal q, HTML default) |
| `text/html;q=0, text/markdown` | 1.0 | rejected | Markdown (HTML rejected) |
| `text/markdown;q=0, text/*;q=0.8` | rejected | 0.8 | HTML (markdown rejected) |
| `text/markdown;q=0.8, text/html;q=0.5` | 0.8 | 0.5 | Markdown (higher q) |

### SSR Middleware (Optional)

For sites running in SSR/hybrid mode, optional middleware handles content negotiation:

**Behavior:**
- Request: `GET /foo/` with `Accept: text/markdown`
- Middleware uses `context.rewrite("/foo.md")` to serve markdown inline
- Response: 200 with markdown body, `Content-Type: text/markdown; charset=utf-8`

**Configuration:**
```ts
starlightLlmsTxt({
  // Enable content negotiation middleware for SSR
  contentNegotiation: true,
})
```

Default: `false` (disabled)

**Middleware implementation:**
```ts
// src/middleware.ts (generated by plugin)
import { defineMiddleware } from 'astro:middleware';

// Base path from Astro config (injected at build time via virtual module)
const BASE_PATH = '/docs/'; // example: '/docs/' or '/'

// Set of known docs slugs WITHOUT base path (populated from getStaticPaths)
// These match the slugs returned by docEntryToMarkdownSlug()
const docsRoutes: Set<string> = new Set([
  // e.g., 'getting-started/intro', 'guides', 'index'
  // NOT '/docs/getting-started/intro' - base is stripped
]);

export const onRequest = defineMiddleware(async (context, next) => {
  const url = new URL(context.request.url);
  const pathname = url.pathname;

  // Guard: Skip if path has a file extension (assets, existing .md, .txt, etc.)
  if (/\.\w+$/.test(pathname)) {
    return next();
  }

  // Guard: Skip llms*.txt routes (with or without base)
  if (pathname.match(/\/llms(-\w+)?\.txt$/)) {
    return next();
  }

  // Guard: Pathname must start with base path
  if (!pathname.startsWith(BASE_PATH.replace(/\/$/, ''))) {
    return next();
  }

  // Strip base path to get the slug for lookup
  // e.g., '/docs/getting-started/intro/' -> 'getting-started/intro'
  let slug = pathname;
  if (BASE_PATH !== '/') {
    slug = pathname.slice(BASE_PATH.replace(/\/$/, '').length);
  }
  slug = slug.replace(/^\//, '').replace(/\/$/, ''); // trim slashes
  if (!slug) slug = 'index'; // root path -> index

  // Guard: Only rewrite known docs routes
  if (!docsRoutes.has(slug)) {
    return next();
  }

  // Check Accept header
  const accept = context.request.headers.get('Accept') || '';
  if (prefersMarkdown(accept)) {
    // Build rewrite path from slug (not pathname) to handle root correctly
    // slug='index' -> /docs/index.md, slug='intro' -> /docs/intro.md
    const basePath = BASE_PATH.replace(/\/$/, ''); // '/docs' or ''
    const mdPath = slug === 'index'
      ? `${basePath}/index.md`
      : `${basePath}/${slug}.md`;
    return context.rewrite(mdPath);
  }

  return next();
});
```

**Base path handling:**
- `BASE_PATH` is injected from `astro.config.mjs` via virtual module at build time
- `docsRoutes` contains slugs WITHOUT base path (matches `docEntryToMarkdownSlug()` output)
- Middleware strips base path from request pathname before lookup
- Rewrite path is built from `slug`, not `pathname`, to correctly handle root:
  - `/docs/` (slug='index') → `/docs/index.md`
  - `/docs/intro/` (slug='intro') → `/docs/intro.md`

### Static Site Infrastructure (Optional)

For static sites wanting Accept header support, deploy behind a reverse proxy or edge worker.

**Cloudflare Worker example:**
```ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // Skip paths with extensions (assets, existing .md files)
    if (/\.\w+$/.test(pathname)) {
      return env.ASSETS.fetch(request);
    }

    const accept = request.headers.get('Accept') || '';
    if (prefersMarkdown(accept)) {
      // Handle root path: / -> /index.md
      // Handle other paths: /foo/ -> /foo.md
      const normalizedPath = pathname.replace(/\/$/, '') || '/index';
      const mdPath = normalizedPath === '' ? '/index.md' : `${normalizedPath}.md`;
      const mdUrl = new URL(mdPath, url.origin);
      const mdResponse = await env.ASSETS.fetch(mdUrl);
      if (mdResponse.ok) {
        return new Response(mdResponse.body, {
          headers: { 'Content-Type': 'text/markdown; charset=utf-8' }
        });
      }
      // Fall through to HTML if .md doesn't exist
    }

    return env.ASSETS.fetch(request);
  }
};

// Include prefersMarkdown and parseAcceptHeader functions from above
```

**Root path handling:**
- `/` → strip trailing slash → empty string → `/index.md`
- `/foo/` → strip trailing slash → `/foo` → `/foo.md`

**Caddy example:**

```caddyfile
:8080 {
    # Skip static assets
    @static path *.md *.txt *.js *.css *.png *.svg *.ico

    handle @static {
        file_server
    }

    # Content negotiation for doc pages (exclude root - see note below)
    @wants_markdown {
        header Accept *text/markdown*
        not path /
    }

    handle @wants_markdown {
        rewrite * {path}.md
        file_server
    }

    # Default: serve HTML
    handle {
        try_files {path} {path}/index.html
        file_server
    }
}
```

**Note on root path:** The Caddy example excludes root (`not path /`) because rewriting `/` to `/.md` fails. To serve `/index.md` for root, add a separate handler:

```caddyfile
@root_markdown {
    header Accept *text/markdown*
    path /
}
handle @root_markdown {
    rewrite * /index.md
    file_server
}
```

**nginx example:**

Note: nginx `map` directive cannot properly parse `q` values. For full RFC 7231 compliance, use a Lua module or edge worker.

```nginx
map $http_accept $prefer_markdown {
    default 0;
    "~text/markdown" 1;
}

# Root path special case
location = / {
    if ($prefer_markdown) {
        rewrite ^ /index.md break;
    }
    try_files /index.html =404;
}

# Other doc paths (no extensions)
location ~ ^/([^.]+)/?$ {
    if ($prefer_markdown) {
        rewrite ^/(.+?)/?$ /$1.md break;
    }
    try_files $uri $uri/ $uri/index.html =404;
}

# Static assets
location ~* \.\w+$ {
    try_files $uri =404;
}
```

## Implementation

### New Files

| File | Purpose |
|------|---------|
| `[...slug].md.ts` | Prerendered route generating per-page markdown |
| `middleware.ts` | Optional SSR content negotiation |

### Route: `[...slug].md.ts`

- Pattern: `[...slug].md` (catch-all for nested paths)
- Prerender: `true` (static generation)
- Uses `getStaticPaths` to enumerate all docs pages
- Reuses `entryToSimpleMarkdown()` for content transformation
- No minification (full content)

### Content Transformation

Reuse existing pipeline:
1. Render MDX → HTML via `experimental_AstroContainer`
2. Transform HTML → Markdown via unified.js pipeline
3. Prepend YAML frontmatter

### llms.txt Changes

Modify `/llms.txt.ts` to:
1. Query all docs pages (same as existing)
2. Append `## Pages` section with markdown URLs

## Testing

### Build Verification

```bash
pnpm build
# Check dist contains .md files
ls dist/getting-started/intro.md
```

### Endpoint Verification

```bash
# Markdown endpoint
curl https://example.com/getting-started/intro.md

# llms.txt includes pages section
curl https://example.com/llms.txt | grep "## Pages"
```

### SSR Middleware (if enabled)

```bash
curl -H "Accept: text/markdown" https://example.com/getting-started/intro/
```

## Non-Goals

- Generating markdown for non-docs pages (blog, custom pages)
- Multiple output formats (e.g., `.txt`, `.rst`)
- Per-page minification options
- Locale-specific markdown endpoints

## References

- [Astro On-Demand Rendering](https://docs.astro.build/en/guides/on-demand-rendering/)
- [Astro Middleware](https://docs.astro.build/en/guides/middleware/)
- [Astro Endpoints](https://docs.astro.build/en/guides/endpoints/)
- [Use Accept Header for Markdown (skeptrune.com)](https://www.skeptrune.com/posts/use-the-accept-header-to-serve-markdown-instead-of-html-to-llms/)
- [Astro Roadmap: Middleware file type handling](https://github.com/withastro/roadmap/discussions/643)
