import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { parse as parseYaml } from 'yaml';
import { buildTierTree, type DirectoryNode, getAllTierPaths, type LeafNode, type TierPath } from './tier-tree';

export interface ProgressiveCorpusDocument {
  sourceId: string;
  url: string;
  path: string;
  body_sha256: string;
  file_sha256: string;
  size_bytes: number;
}

export interface ProgressiveCorpusAsset {
  path: string;
  sha256: string;
  media_type: string;
  size_bytes: number;
}

export interface ProgressiveCorpusManifest {
  schema_version: number;
  source_roots: Record<string, string>;
  documents: ProgressiveCorpusDocument[];
  assets: ProgressiveCorpusAsset[];
  [key: string]: unknown;
}

export interface ProgressiveSourceMetadata {
  title?: string;
  description?: string;
}

export interface ProgressiveCorpusTaxonomyOptions {
  levels: ['category', 'subcategory'];
  collapseSingletonSubcategories?: boolean;
}

export interface ProgressiveCorpusHintOptions {
  strategy: 'first-sentence';
  maxCharacters: number;
}

export interface ProgressiveCorpusOptions {
  manifest: string;
  contentRoot: string;
  assetBaseUrl?: string;
  title?: string;
  description?: string;
  sources?: Record<string, ProgressiveSourceMetadata>;
  taxonomy?: ProgressiveCorpusTaxonomyOptions;
  hints?: ProgressiveCorpusHintOptions;
}

interface ProgressiveEntry {
  id: string;
  data: { title: string; description?: string; category?: string; subcategory?: string };
  corpus: { sourceId: string; path: string; body: string };
}

export interface ProgressiveCorpus {
  root: DirectoryNode;
  sources: string[];
  sourceRoots: Record<string, string>;
  assets: Set<string>;
}

function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function structuralTitle(value: string): string {
  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function structuralDescription(title: string): string {
  return `Documentation for ${title}.`;
}

function taxonomySlug(value: string): string {
  const slug = value
    .normalize('NFKD')
    .toLocaleLowerCase('en-US')
    .replace(/[’']/g, '')
    .replace(/[^\p{Letter}\p{Number}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
  if (!slug) throw new Error(`taxonomy value has no usable route segment: ${value}`);
  return slug;
}

function plainText(value: string): string {
  return value
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/<[^>]*>/g, ' ')
    .replace(/[`*_~>#]+/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function truncateAtWord(value: string, maxCharacters: number): string {
  if (value.length <= maxCharacters) return value;
  const prefix = value.slice(0, Math.max(1, maxCharacters - 1));
  const boundary = prefix.lastIndexOf(' ');
  return `${prefix.slice(0, boundary > 0 ? boundary : prefix.length).trimEnd()}…`;
}

function compactHint(
  description: string | undefined,
  title: string,
  options: ProgressiveCorpusHintOptions | undefined,
): string | undefined {
  if (!options) return description?.trim() || undefined;
  if (options.strategy !== 'first-sentence' || !Number.isInteger(options.maxCharacters) || options.maxCharacters < 1) {
    throw new Error('progressive corpus hint configuration is invalid');
  }
  const text = plainText(description ?? '') || structuralDescription(title);
  const sentence = text.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? text;
  return truncateAtWord(sentence, options.maxCharacters);
}

function assertSafePath(value: string, label: string): void {
  if (
    !value ||
    value.startsWith('/') ||
    value.includes('\\') ||
    value.split('/').some((part) => !part || part === '.' || part === '..') ||
    path.posix.normalize(value) !== value
  ) {
    throw new Error(`${label} is not a safe canonical path: ${value}`);
  }
}

function routeIdForDocument(document: ProgressiveCorpusDocument): string {
  assertSafePath(document.sourceId, 'document source');
  if (document.sourceId.includes('/')) throw new Error(`document source is invalid: ${document.sourceId}`);
  assertSafePath(document.path, 'document path');
  const prefix = `content/${document.sourceId}/`;
  if (!document.path.startsWith(prefix) || !document.path.endsWith('index.md')) {
    throw new Error(`document path does not match source: ${document.path}`);
  }
  const relative = document.path.slice(prefix.length);
  if (relative !== 'index.md' && !relative.endsWith('/index.md')) {
    throw new Error(`document path is not an index Markdown file: ${document.path}`);
  }
  const suffixLength = relative === 'index.md' ? 'index.md'.length : '/index.md'.length;
  const slug = relative.slice(0, -suffixLength);
  return slug ? `${document.sourceId}/${slug}` : document.sourceId;
}

function parseDocument(
  markdown: string,
  routeId: string,
  hints?: ProgressiveCorpusHintOptions,
): { title: string; description?: string; category?: string; subcategory?: string; body: string } {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) throw new Error(`document has no YAML frontmatter: ${routeId}`);
  const data = parseYaml(match[1] ?? '') as unknown;
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(`document frontmatter is invalid: ${routeId}`);
  }
  const frontmatter = data as Record<string, unknown>;
  const fallbackSegment = routeId.split('/').filter(Boolean).at(-1) ?? routeId;
  const title =
    typeof frontmatter.title === 'string' && frontmatter.title.trim()
      ? frontmatter.title.trim()
      : structuralTitle(fallbackSegment);
  const rawDescription =
    typeof frontmatter.description === 'string' && frontmatter.description.trim()
      ? frontmatter.description.trim()
      : undefined;
  const description = compactHint(rawDescription, title, hints);
  const category = typeof frontmatter.category === 'string' ? frontmatter.category.trim() : '';
  const subcategory = typeof frontmatter.subcategory === 'string' ? frontmatter.subcategory.trim() : '';
  return {
    title,
    ...(description ? { description } : {}),
    ...(category ? { category } : {}),
    ...(subcategory ? { subcategory } : {}),
    body: (match[2] ?? '').trim(),
  };
}

function directory(slug: string, segment: string, title: string): DirectoryNode {
  return { type: 'directory', slug, segment, meta: { title }, children: new Map() };
}

function leaf(entry: ProgressiveEntry): LeafNode {
  return {
    type: 'leaf',
    slug: entry.id,
    segment: entry.id.split('/').at(-1) ?? entry.id,
    meta: { title: entry.data.title, ...(entry.data.description ? { description: entry.data.description } : {}) },
    entry,
  };
}

function buildTaxonomyTree(entries: ProgressiveEntry[], options: ProgressiveCorpusTaxonomyOptions): DirectoryNode {
  if (options.levels.length !== 2 || options.levels[0] !== 'category' || options.levels[1] !== 'subcategory') {
    throw new Error('progressive corpus taxonomy levels must be category then subcategory');
  }
  const root = directory('', '', '');
  const occupiedRoutes = new Set<string>();
  const reserve = (route: string): void => {
    if (occupiedRoutes.has(route)) throw new Error(`progressive corpus route collision: ${route}`);
    occupiedRoutes.add(route);
  };
  const bySource = Map.groupBy(entries, (entry) => entry.corpus.sourceId);
  for (const sourceId of [...bySource.keys()].sort(compareText)) {
    reserve(sourceId);
    const source = directory(sourceId, sourceId, structuralTitle(sourceId));
    root.children.set(sourceId, source);
    const sourceEntries = bySource.get(sourceId) ?? [];
    const byCategory = Map.groupBy(sourceEntries, (entry) => {
      if (!entry.data.category) throw new Error(`document requires a nonempty category: ${entry.id}`);
      return entry.data.category;
    });
    for (const categoryName of [...byCategory.keys()].sort(compareText)) {
      const categorySegment = taxonomySlug(categoryName);
      const categoryRoute = `${sourceId}/_taxonomy/${categorySegment}`;
      reserve(categoryRoute);
      const category = directory(categoryRoute, categorySegment, categoryName);
      source.children.set(categorySegment, category);
      const categoryEntries = byCategory.get(categoryName) ?? [];
      const subcategoryCounts = new Map<string, number>();
      for (const entry of categoryEntries) {
        if (entry.data.subcategory) {
          subcategoryCounts.set(entry.data.subcategory, (subcategoryCounts.get(entry.data.subcategory) ?? 0) + 1);
        }
      }
      const materialized = new Map<string, DirectoryNode>();
      for (const subcategoryName of [...subcategoryCounts.keys()].sort(compareText)) {
        const count = subcategoryCounts.get(subcategoryName) ?? 0;
        if (options.collapseSingletonSubcategories !== false && count < 2) continue;
        const subcategorySegment = taxonomySlug(subcategoryName);
        const subcategoryRoute = `${categoryRoute}/${subcategorySegment}`;
        reserve(subcategoryRoute);
        const subcategory = directory(subcategoryRoute, subcategorySegment, subcategoryName);
        category.children.set(`directory:${subcategorySegment}`, subcategory);
        materialized.set(subcategoryName, subcategory);
      }
      for (const entry of [...categoryEntries].sort((a, b) => compareText(a.id, b.id))) {
        reserve(entry.id);
        const parent = entry.data.subcategory ? (materialized.get(entry.data.subcategory) ?? category) : category;
        parent.children.set(`leaf:${entry.id}`, leaf(entry));
      }
    }
  }
  return root;
}

export function buildProgressiveCorpus(
  manifest: ProgressiveCorpusManifest,
  readDocument: (path: string) => string,
  options: Pick<ProgressiveCorpusOptions, 'taxonomy' | 'hints'> = {},
): ProgressiveCorpus {
  if (manifest.schema_version !== 2 || !Array.isArray(manifest.documents) || !Array.isArray(manifest.assets)) {
    throw new Error('progressive corpus manifest schema is invalid');
  }
  if (!manifest.source_roots || typeof manifest.source_roots !== 'object' || Array.isArray(manifest.source_roots)) {
    throw new Error('progressive corpus source roots are invalid');
  }

  const documentPaths = new Set<string>();
  const entries: ProgressiveEntry[] = [];
  for (const document of [...manifest.documents].sort((a, b) => compareText(a.path, b.path))) {
    if (documentPaths.has(document.path)) throw new Error(`duplicate document path: ${document.path}`);
    if (typeof manifest.source_roots[document.sourceId] !== 'string') {
      throw new Error(`document source is not declared: ${document.sourceId}`);
    }
    documentPaths.add(document.path);
    const routeId = routeIdForDocument(document);
    const markdown = readDocument(document.path);
    if (Buffer.byteLength(markdown) !== document.size_bytes) {
      throw new Error(`document size mismatch: ${document.path}`);
    }
    if (createHash('sha256').update(markdown).digest('hex') !== document.file_sha256) {
      throw new Error(`document digest mismatch: ${document.path}`);
    }
    const parsed = parseDocument(markdown, routeId, options.hints);
    entries.push({
      id: routeId,
      data: {
        title: parsed.title,
        ...(parsed.description ? { description: parsed.description } : {}),
        ...(parsed.category ? { category: parsed.category } : {}),
        ...(parsed.subcategory ? { subcategory: parsed.subcategory } : {}),
      },
      corpus: { sourceId: document.sourceId, path: document.path, body: parsed.body },
    });
  }

  const assets = new Set<string>();
  for (const asset of manifest.assets) {
    assertSafePath(asset.path, 'asset path');
    const sourceId = asset.path.split('/')[1] ?? '';
    if (
      !asset.path.startsWith('content/') ||
      !asset.path.includes('/assets/') ||
      typeof manifest.source_roots[sourceId] !== 'string'
    ) {
      throw new Error(`asset path is outside the corpus: ${asset.path}`);
    }
    if (assets.has(asset.path)) throw new Error(`duplicate asset path: ${asset.path}`);
    assets.add(asset.path);
  }

  const root = options.taxonomy ? buildTaxonomyTree(entries, options.taxonomy) : buildTierTree(entries);
  const leaves = getAllTierPaths(root).filter((entry) => entry.type === 'leaf');
  const routePaths = getAllTierPaths(root).map((entry) => entry.path);
  if (leaves.length !== entries.length || new Set(routePaths).size !== routePaths.length) {
    throw new Error('progressive corpus route collision');
  }
  const sources = [...new Set(entries.map((entry) => entry.corpus.sourceId))].sort(compareText);
  return { root, sources, sourceRoots: { ...manifest.source_roots }, assets };
}

export function loadProgressiveCorpus(options: ProgressiveCorpusOptions): ProgressiveCorpus {
  const manifestPath = path.resolve(options.manifest);
  const contentRoot = path.resolve(options.contentRoot);
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as ProgressiveCorpusManifest;
  return buildProgressiveCorpus(
    manifest,
    (relativePath) => {
      const absolutePath = path.resolve(contentRoot, relativePath);
      const relative = path.relative(contentRoot, absolutePath);
      if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
        throw new Error(`document path escapes content root: ${relativePath}`);
      }
      return readFileSync(absolutePath, 'utf8');
    },
    options,
  );
}

export function getProgressivePaths(root: DirectoryNode): TierPath[] {
  return getAllTierPaths(root);
}

export function findProgressiveNode(root: DirectoryNode, routePath: string): DirectoryNode | LeafNode | undefined {
  const pending: Array<DirectoryNode | LeafNode> = [...root.children.values()];
  while (pending.length > 0) {
    const node = pending.shift();
    if (!node) continue;
    if (node.slug === routePath) return node;
    if (node.type === 'directory') pending.push(...node.children.values());
  }
  return undefined;
}

function sourceMetadata(
  sourceId: string,
  options: Pick<ProgressiveCorpusOptions, 'sources'> = {},
): Required<ProgressiveSourceMetadata> {
  const configured = options.sources?.[sourceId];
  const title = configured?.title || structuralTitle(sourceId);
  return { title, description: configured?.description || `Documentation from ${title}.` };
}

function absoluteRoute(site: URL, routePath: string): string {
  return new URL(`_llms-txt/${routePath}.txt`, site).href;
}

export function renderProgressiveIndex(
  corpus: ProgressiveCorpus,
  site: URL,
  options: Pick<ProgressiveCorpusOptions, 'title' | 'description' | 'sources'> = {},
): string {
  const title = options.title || 'Documentation Corpus';
  const sections = [`# ${title}`];
  if (options.description) sections.push(`> ${options.description}`);
  sections.push('## Sources');
  sections.push(
    corpus.sources
      .map((sourceId) => {
        const metadata = sourceMetadata(sourceId, options);
        return `- [${metadata.title}](${absoluteRoute(site, sourceId)}): ${metadata.description} Source: ${corpus.sourceRoots[sourceId]}`;
      })
      .join('\n'),
  );
  sections.push('## Complete Inventory');
  sections.push(`- [All document links](${new URL('llms-full.txt', site).href}): every document in this snapshot`);
  return `${sections.join('\n\n')}\n`;
}

function leafEntries(root: DirectoryNode): Array<{ route: string; leaf: LeafNode }> {
  const result: Array<{ route: string; leaf: LeafNode }> = [];
  const visit = (node: DirectoryNode): void => {
    for (const child of node.children.values()) {
      if (child.type === 'directory') visit(child);
      else result.push({ route: child.slug, leaf: child });
    }
  };
  visit(root);
  return result.sort((a, b) => compareText(a.route, b.route));
}

export function renderProgressiveFullIndex(corpus: ProgressiveCorpus, site: URL): string {
  const sections = ['# Complete Documentation Inventory'];
  const entries = leafEntries(corpus.root);
  for (const sourceId of corpus.sources) {
    const metadata = sourceMetadata(sourceId);
    const links = entries
      .filter(({ leaf }) => (leaf.entry as ProgressiveEntry).corpus.sourceId === sourceId)
      .map(({ route, leaf }) => {
        const description = leaf.meta.description || structuralDescription(leaf.meta.title);
        return `- [${leaf.meta.title}](${absoluteRoute(site, route)}): ${description}`;
      });
    sections.push(`## ${metadata.title}`);
    sections.push(links.join('\n'));
  }
  return `${sections.join('\n\n')}\n`;
}

function rewriteTarget(target: string, documentPath: string, assets: Set<string>, assetBaseUrl: URL): string {
  if (/^(?:[a-z][a-z0-9+.-]*:|\/|#)/i.test(target)) return target;
  const suffixAt = target.search(/[?#]/);
  const pathname = suffixAt === -1 ? target : target.slice(0, suffixAt);
  const suffix = suffixAt === -1 ? '' : target.slice(suffixAt);
  const normalized = path.posix.normalize(path.posix.join(path.posix.dirname(documentPath), pathname));
  return assets.has(normalized) ? `${new URL(normalized, assetBaseUrl).href}${suffix}` : target;
}

export function rewriteCorpusAssetReferences(
  markdown: string,
  documentPath: string,
  assets: Set<string>,
  assetBaseUrl: URL,
): string {
  const rewrittenMarkdown = markdown.replace(/(!?\[[^\]]*\]\()([^\s)]+)([^)]*\))/g, (_match, open, target, close) => {
    return `${open}${rewriteTarget(target, documentPath, assets, assetBaseUrl)}${close}`;
  });
  return rewrittenMarkdown.replace(/((?:src|href)=["'])([^"']+)(["'])/gi, (_match, open, target, close) => {
    return `${open}${rewriteTarget(target, documentPath, assets, assetBaseUrl)}${close}`;
  });
}

export function renderProgressiveNode(
  corpus: ProgressiveCorpus,
  routePath: string,
  site: URL,
  assetBaseUrl: URL,
): string {
  const node = findProgressiveNode(corpus.root, routePath);
  if (!node) throw new Error(`progressive corpus route not found: ${routePath}`);
  if (node.type === 'directory') {
    const description = node.meta.description || structuralDescription(node.meta.title);
    const links = [...node.children.values()]
      .map((child) => {
        const childDescription = child.meta.description || structuralDescription(child.meta.title);
        return `- [${child.meta.title}](${absoluteRoute(site, child.slug)}): ${childDescription}`;
      })
      .join('\n');
    return `# ${node.meta.title}\n\n> ${description}\n\n## Contents\n\n${links}\n`;
  }
  const entry = node.entry as ProgressiveEntry;
  const body = rewriteCorpusAssetReferences(entry.corpus.body, entry.corpus.path, corpus.assets, assetBaseUrl);
  const sections: string[] = [];
  if (!/^\s*#\s+/.test(body)) sections.push(`# ${node.meta.title}`);
  if (node.meta.description) sections.push(`> ${node.meta.description}`);
  sections.push(body);
  return `${sections.filter(Boolean).join('\n\n')}\n`;
}
