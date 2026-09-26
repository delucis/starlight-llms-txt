import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import {
  buildProgressiveCorpus,
  getProgressivePaths,
  type ProgressiveCorpusManifest,
  renderProgressiveFullIndex,
  renderProgressiveIndex,
  renderProgressiveNode,
  rewriteCorpusAssetReferences,
} from '../progressive-corpus';
import { getLlmsRoutePlan } from '../route-plan';

const document = (sourceId: string, path: string, markdown: string) => ({
  sourceId,
  url: `https://source.example/${path}`,
  path,
  body_sha256: '0'.repeat(64),
  file_sha256: createHash('sha256').update(markdown).digest('hex'),
  size_bytes: Buffer.byteLength(markdown),
});

const fixture = () => {
  const files = new Map([
    ['content/docs-cloud-f5-com/guides/index.md', '---\ntitle: Guides\ndescription: Product guides\n---\n\nWelcome.\n'],
    ['content/docs-cloud-f5-com/guides/setup/index.md', '---\ntitle: Setup\n---\n\n![Diagram](assets/a.png)\n'],
    ['content/my-f5-com/support/index.md', '---\ntitle: Support\n---\n\nSupport body.\n'],
  ]);
  const manifest: ProgressiveCorpusManifest = {
    schema_version: 2,
    source_roots: {
      'docs-cloud-f5-com': 'https://docs.cloud.f5.com/docs-v2',
      'my-f5-com': 'https://my.f5.com/manage/s',
    },
    documents: [...files].map(([path, markdown]) => document(path.split('/')[1] ?? '', path, markdown)),
    assets: [
      {
        path: 'content/docs-cloud-f5-com/guides/setup/assets/a.png',
        sha256: 'a'.repeat(64),
        media_type: 'image/png',
        size_bytes: 8,
      },
    ],
  };
  return { corpus: buildProgressiveCorpus(manifest, (path) => files.get(path) ?? ''), manifest };
};

describe('buildProgressiveCorpus', () => {
  it('constructs a deterministic English-only hierarchy with index collisions', () => {
    const { corpus } = fixture();
    expect(getProgressivePaths(corpus.root)).toEqual([
      { path: 'docs-cloud-f5-com', type: 'directory' },
      { path: 'docs-cloud-f5-com/guides', type: 'directory' },
      { path: 'docs-cloud-f5-com/guides/index', type: 'leaf' },
      { path: 'docs-cloud-f5-com/guides/setup', type: 'leaf' },
      { path: 'my-f5-com', type: 'directory' },
      { path: 'my-f5-com/support', type: 'leaf' },
    ]);
    expect(getProgressivePaths(corpus.root).filter((entry) => entry.type === 'leaf')).toHaveLength(3);
  });

  it('uses source metadata and deterministic descriptions instead of summaries', () => {
    const { corpus } = fixture();
    const index = renderProgressiveIndex(corpus, new URL('https://example.com/html-to-markdown/'), {
      title: 'F5 Docs Corpus',
      description: 'Verified F5 documentation snapshots.',
      sources: { 'docs-cloud-f5-com': { title: 'F5 Distributed Cloud Docs' } },
    });
    expect(index).toContain('# F5 Docs Corpus');
    expect(index).toContain('[F5 Distributed Cloud Docs]');
    expect(index).toContain('Documentation from F5 Distributed Cloud Docs.');
    expect(index).toContain('Source: https://docs.cloud.f5.com/docs-v2');
    expect(index).not.toContain('llms-small.txt');
    expect(index).not.toContain('Translations');
  });

  it('rejects duplicate leaf routes caused by index collisions', () => {
    const markdown = '---\ntitle: Duplicate\n---\n\nBody.\n';
    const manifest: ProgressiveCorpusManifest = {
      schema_version: 2,
      source_roots: { source: 'https://source.example' },
      documents: [
        document('source', 'content/source/guides/index.md', markdown),
        document('source', 'content/source/guides/index/index.md', markdown),
      ],
      assets: [],
    };
    expect(() => buildProgressiveCorpus(manifest, () => markdown)).toThrow(/route collision/);
  });

  it('falls back to structural titles when frontmatter metadata is absent', () => {
    const markdown = '---\nurl: https://source.example/getting-started\n---\n\nBody.\n';
    const manifest: ProgressiveCorpusManifest = {
      schema_version: 2,
      source_roots: { source: 'https://source.example' },
      documents: [document('source', 'content/source/getting-started/index.md', markdown)],
      assets: [],
    };
    const corpus = buildProgressiveCorpus(manifest, () => markdown);
    const full = renderProgressiveFullIndex(corpus, new URL('https://example.com/corpus/'));
    expect(full).toContain('[Getting Started]');
    expect(full).toContain('Documentation for Getting Started.');
  });

  it('rejects undeclared sources, unsafe paths, size mismatches, and digest mismatches', () => {
    const markdown = '---\ntitle: Page\n---\n\nBody.\n';
    const base: ProgressiveCorpusManifest = {
      schema_version: 2,
      source_roots: { source: 'https://source.example' },
      documents: [document('source', 'content/source/page/index.md', markdown)],
      assets: [],
    };
    expect(() =>
      buildProgressiveCorpus({ ...base, documents: [{ ...base.documents[0], sourceId: 'other' }] }, () => markdown),
    ).toThrow(/not declared/);
    expect(() =>
      buildProgressiveCorpus(
        { ...base, documents: [{ ...base.documents[0], path: '../page/index.md' }] },
        () => markdown,
      ),
    ).toThrow(/safe canonical path/);
    expect(() =>
      buildProgressiveCorpus({ ...base, documents: [{ ...base.documents[0], size_bytes: 1 }] }, () => markdown),
    ).toThrow(/size mismatch/);
    expect(() =>
      buildProgressiveCorpus(
        { ...base, documents: [{ ...base.documents[0], file_sha256: '0'.repeat(64) }] },
        () => markdown,
      ),
    ).toThrow(/digest mismatch/);
  });
});

describe('getLlmsRoutePlan', () => {
  it('emits only English progressive routes in corpus mode', () => {
    const routes = getLlmsRoutePlan(true, true);
    expect(routes.map((route) => route.pattern)).toEqual(['/llms.txt', '/llms-full.txt', '/_llms-txt/[...path].txt']);
    expect(routes.map((route) => route.entrypoint)).toEqual([
      './progressive-llms.txt.ts',
      './progressive-llms-full.txt.ts',
      './progressive-tiered.txt.ts',
    ]);
  });
});

describe('progressive corpus rendering', () => {
  it('renders llms-full.txt as a grouped link inventory without document content', () => {
    const { corpus } = fixture();
    const output = renderProgressiveFullIndex(corpus, new URL('https://example.com/html-to-markdown/'));
    expect(output).toContain('## Docs Cloud F5 Com');
    expect(output).toContain('/_llms-txt/docs-cloud-f5-com/guides/setup.txt');
    expect(output).toContain('Documentation for Setup.');
    expect(output).not.toContain('Support body.');
    expect(output).not.toContain('![Diagram]');
  });

  it('renders metadata-only directories and complete-content leaves', () => {
    const { corpus } = fixture();
    const site = new URL('https://example.com/html-to-markdown/');
    const directory = renderProgressiveNode(corpus, 'docs-cloud-f5-com/guides', site, new URL('snapshot/', site));
    expect(directory).toContain('## Contents');
    expect(directory).not.toContain('Welcome.');
    const leaf = renderProgressiveNode(corpus, 'docs-cloud-f5-com/guides/setup', site, new URL('snapshot/', site));
    expect(leaf).toContain('# Setup');
    expect(leaf).toContain(
      '![Diagram](https://example.com/html-to-markdown/snapshot/content/docs-cloud-f5-com/guides/setup/assets/a.png)',
    );
  });

  it('rewrites only manifest-listed local assets and preserves remote links', () => {
    const assets = new Set(['content/source/topic/assets/a.png']);
    const body = [
      '![A](assets/a.png)',
      '[A file](./assets/a.png#download)',
      '![Remote](https://cdn.example/a.png)',
      '[Page](../other/)',
    ].join('\n');
    expect(
      rewriteCorpusAssetReferences(
        body,
        'content/source/topic/index.md',
        assets,
        new URL('https://e.test/x/snapshot/'),
      ),
    ).toBe(
      [
        '![A](https://e.test/x/snapshot/content/source/topic/assets/a.png)',
        '[A file](https://e.test/x/snapshot/content/source/topic/assets/a.png#download)',
        '![Remote](https://cdn.example/a.png)',
        '[Page](../other/)',
      ].join('\n'),
    );
  });

  it('makes every document reachable exactly once with resolving intermediate links', () => {
    const { corpus, manifest } = fixture();
    const site = new URL('https://example.com/html-to-markdown/');
    const paths = getProgressivePaths(corpus.root);
    const routeSet = new Set(paths.map((entry) => entry.path));
    const leaves = paths.filter((entry) => entry.type === 'leaf');
    expect(leaves).toHaveLength(manifest.documents.length);

    for (const entry of paths.filter((candidate) => candidate.type === 'directory')) {
      const output = renderProgressiveNode(corpus, entry.path, site, new URL('snapshot/', site));
      for (const match of output.matchAll(/_llms-txt\/([^\s)]+)\.txt/g)) {
        expect(routeSet.has(match[1] ?? '')).toBe(true);
      }
    }

    const full = renderProgressiveFullIndex(corpus, site);
    for (const leaf of leaves) {
      expect(full.match(new RegExp(`${leaf.path.replaceAll('/', '\\/')}\\.txt`, 'g'))).toHaveLength(1);
    }
    expect(renderProgressiveFullIndex(corpus, site)).toBe(full);
  });
});
