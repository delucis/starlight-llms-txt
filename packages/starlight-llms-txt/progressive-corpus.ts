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

export interface ProgressiveCorpusOptions {
  manifest: string;
  contentRoot: string;
  assetBaseUrl?: string;
  title?: string;
  description?: string;
  sources?: Record<string, ProgressiveSourceMetadata>;
}

interface ProgressiveEntry {
  id: string;
  data: { title: string; description?: string };
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

function parseDocument(markdown: string, routeId: string): { title: string; description?: string; body: string } {
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
  const description =
    typeof frontmatter.description === 'string' && frontmatter.description.trim()
      ? frontmatter.description.trim()
      : undefined;
  return { title, ...(description ? { description } : {}), body: (match[2] ?? '').trim() };
}

export function buildProgressiveCorpus(
  manifest: ProgressiveCorpusManifest,
  readDocument: (path: string) => string,
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
    const parsed = parseDocument(markdown, routeId);
    entries.push({
      id: routeId,
      data: { title: parsed.title, ...(parsed.description ? { description: parsed.description } : {}) },
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

  const root = buildTierTree(entries);
  const leaves = getAllTierPaths(root).filter((entry) => entry.type === 'leaf');
  if (leaves.length !== entries.length) throw new Error('progressive corpus route collision');
  const sources = [...new Set(entries.map((entry) => entry.corpus.sourceId))].sort(compareText);
  return { root, sources, sourceRoots: { ...manifest.source_roots }, assets };
}

export function loadProgressiveCorpus(options: ProgressiveCorpusOptions): ProgressiveCorpus {
  const manifestPath = path.resolve(options.manifest);
  const contentRoot = path.resolve(options.contentRoot);
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as ProgressiveCorpusManifest;
  return buildProgressiveCorpus(manifest, (relativePath) => {
    const absolutePath = path.resolve(contentRoot, relativePath);
    const relative = path.relative(contentRoot, absolutePath);
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
      throw new Error(`document path escapes content root: ${relativePath}`);
    }
    return readFileSync(absolutePath, 'utf8');
  });
}

export function getProgressivePaths(root: DirectoryNode): TierPath[] {
  return getAllTierPaths(root);
}

export function findProgressiveNode(root: DirectoryNode, routePath: string): DirectoryNode | LeafNode | undefined {
  let current: DirectoryNode = root;
  const segments = routePath.split('/').filter(Boolean);
  for (let index = 0; index < segments.length; index += 1) {
    const child = current.children.get(segments[index] ?? '');
    if (!child) return undefined;
    if (index === segments.length - 1) return child;
    if (child.type !== 'directory') return undefined;
    current = child;
  }
  return current;
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
