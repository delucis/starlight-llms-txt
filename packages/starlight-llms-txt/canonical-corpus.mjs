import { createHash } from 'node:crypto';
import { closeSync, lstatSync, mkdirSync, openSync, readFileSync, writeFileSync, writeSync } from 'node:fs';
import { dirname, join, resolve, sep } from 'node:path';

const digest = (bytes) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`;
const bytes = (text) => Buffer.byteLength(text, 'utf8');
const segment = (value) => {
  const result = String(value)
    .normalize('NFKD')
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-|-$/g, '');
  if (!result || result === '.' || result === '..') throw new Error(`Invalid hierarchy segment: ${value}`);
  return result;
};
const hint = (value) =>
  String(value || '')
    .replace(/[\r\n[\]<>]/g, ' ')
    .replace(/\s+/g, ' ')
    .slice(0, 160);
function safeFile(root, name) {
  if (
    !name ||
    name.includes('\\') ||
    name.startsWith('/') ||
    name.split('/').some((x) => !x || x === '.' || x === '..')
  )
    throw new Error(`Unsafe canonical path: ${name}`);
  const target = resolve(root, name);
  if (!target.startsWith(resolve(root) + sep)) throw new Error(`Unsafe canonical path: ${name}`);
  let current = resolve(root);
  for (const part of name.split('/')) {
    current = join(current, part);
    if (lstatSync(current).isSymbolicLink()) throw new Error(`Canonical symlink: ${name}`);
  }
  return target;
}

// Blank lines are boundaries only outside fenced code and HTML comments. Tables,
// lists and adjacent anchor/heading blocks remain intact. Nothing is truncated.
export function splitMarkdown(text, limit = 128 * 1024) {
  const blocks = [];
  let block = '';
  let fence = null;
  let comment = false;
  for (const line of text.match(/[^\n]*\n|[^\n]+$/g) || []) {
    block += line;
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (!comment && marker) {
      if (!fence) fence = marker[1];
      else if (
        marker[1][0] === fence[0] &&
        marker[1].length >= fence.length &&
        /^ {0,3}(?:`+|~+)\s*$/.test(line.trimEnd())
      )
        fence = null;
    }
    if (!fence) {
      if (line.includes('<!--')) comment = true;
      if (line.includes('-->')) comment = false;
    }
    if (!fence && !comment && /^\s*$/.test(line)) {
      blocks.push(block);
      block = '';
    }
  }
  if (fence || comment) throw new Error('Unterminated Markdown fence or comment');
  if (block) blocks.push(block);
  const parts = [];
  let part = '';
  for (const item of blocks) {
    if (bytes(item) > limit) throw new Error(`indivisible Markdown block exceeds ${limit} bytes (${bytes(item)})`);
    if (bytes(part) + bytes(item) > limit) {
      parts.push(part);
      part = '';
    }
    part += item;
  }
  if (part || !parts.length) parts.push(part);
  return parts;
}

export function readCanonicalCorpus(contentRoot) {
  const root = resolve(contentRoot);
  const manifestBytes = readFileSync(join(root, 'generated-manifest.json'));
  const manifest = JSON.parse(manifestBytes);
  if (manifest.schema_version !== 1 || !manifest.files || Array.isArray(manifest.files))
    throw new Error('Invalid canonical manifest');
  const pages = [];
  const ids = new Set();
  const routes = new Set();
  // Validate every canonical receipt before output or staging, including machine assets.
  for (const [file, receipt] of Object.entries(manifest.files).sort(([a], [b]) => a.localeCompare(b, 'en'))) {
    if (!file.startsWith('documentation/')) continue;
    const name = file.slice('documentation/'.length);
    const data = readFileSync(safeFile(root, name));
    if (data.length !== receipt.bytes || digest(data) !== receipt.sha256)
      throw new Error(`Canonical source receipt mismatch: ${name}`);
    if (!name.endsWith('.md') || name.startsWith('_data/')) continue;
    const text = data.toString('utf8');
    if (!Buffer.from(text).equals(data)) throw new Error(`Invalid canonical UTF-8: ${name}`);
    const frontmatter = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n(?:\r?\n)?/);
    const line = frontmatter?.[1].split('\n').find((x) => x.startsWith('xcsh_docs: '));
    if (!line) throw new Error(`Missing canonical metadata: ${name}`);
    const meta = JSON.parse(line.slice(11));
    const body = text.slice(frontmatter[0].length);
    if (meta.body_bytes !== bytes(body) || meta.body_sha256 !== digest(body))
      throw new Error(`Canonical body receipt mismatch: ${name}`);
    if (!meta.id || ids.has(meta.id)) throw new Error(`Canonical ID collision: ${meta.id}`);
    const slug = name
      .replace(/(^|\/)index\.md$/, '')
      .replace(/\.md$/, '')
      .replace(/\/$/, '');
    if (routes.has(slug)) throw new Error(`Canonical route collision: ${slug}`);
    ids.add(meta.id);
    routes.add(slug);
    const titleLine = frontmatter[1].split('\n').find((x) => x.startsWith('page_title: ') || x.startsWith('title: '));
    pages.push({
      name,
      slug,
      title: titleLine ? JSON.parse(titleLine.slice(titleLine.indexOf(':') + 1)) : meta.id,
      meta,
    });
  }
  for (const page of pages) {
    for (const id of [...(page.meta.child_ids || []), ...(page.meta.relationships || []).map((x) => x.target_id)]) {
      if (!ids.has(id)) throw new Error(`Unresolved canonical relationship: ${page.meta.id} -> ${id}`);
    }
  }
  const config = JSON.parse(readFileSync(join(root, 'llms-config.json'), 'utf8'));
  if (!config.canonicalCorpus?.taxonomy) throw new Error('Canonical publication requires llms-config.json taxonomy');
  return { root, pages, manifest, manifestSha256: digest(manifestBytes), config: config.canonicalCorpus };
}

export function writeCanonicalHierarchy({ contentRoot, outputRoot, base = '/', title = 'Canonical documentation' }) {
  const started = performance.now();
  const corpus = readCanonicalCorpus(contentRoot);
  // Preflight every block before writing anything. A failure leaves the
  // existing publication untouched and names the canonical page to repair.
  const blockFailures = [];
  for (const page of corpus.pages) {
    const body = readFileSync(join(corpus.root, page.name), 'utf8').replace(
      /^---\r?\n[\s\S]*?\r?\n---\r?\n(?:\r?\n)?/,
      '',
    );
    try {
      splitMarkdown(body, 128 * 1024 - 4096);
    } catch (error) {
      blockFailures.push({ page: page.name, reason: error.message });
    }
  }
  if (blockFailures.length) throw new Error(`Canonical content preflight failed: ${JSON.stringify(blockFailures)}`);
  const taxonomy = corpus.config.taxonomy;
  const prefix = '/' + base.split('/').filter(Boolean).join('/');
  const url = (route) => `${prefix === '/' ? '' : prefix}/${route}`;
  const scopes = new Map();
  const unclassified = [];
  const pageIndexes = {};
  const generated = new Set();
  const scope = (route, label) => {
    if (scopes.has(route) && scopes.get(route).title !== hint(label))
      throw new Error(`Hierarchy route collision: ${route}`);
    if (!scopes.has(route)) scopes.set(route, { route, title: hint(label), entries: new Map() });
    return scopes.get(route);
  };
  const link = (parent, child, description = '') =>
    parent.entries.set(`scope:${child.route}`, {
      title: child.title,
      route: `${child.route ? child.route + '/' : ''}llms.txt`,
      description: hint(description),
    });
  const root = scope('', title);
  const topics = scope('_llms-txt/topics', 'Topics');
  const families = scope('_llms-txt/families', 'Provider families');
  const tasks = scope('_llms-txt/tasks', 'Tasks');
  link(root, topics);
  link(root, families);
  link(root, tasks);
  const collections = Map.groupBy(corpus.pages, (p) => p.meta.collection_id);
  for (const [collectionId, pages] of collections) {
    const representative =
      pages.find((p) => p.meta.role === 'fundamentals') || pages.find((p) => p.meta.role === 'overview') || pages[0];
    const m = representative.meta;
    const reviewed = taxonomy.topics?.[m.category];
    const reasons = [];
    if (m.classification?.status !== 'resolved') reasons.push('unresolved-classification');
    if (m.classification?.rules_sha256 !== taxonomy.rulesDigest) reasons.push('rules-digest');
    if (!reviewed) reasons.push('unmapped-category');
    if (pages.some((p) => p.meta.category !== m.category || p.meta.classification?.status !== m.classification?.status))
      reasons.push('collection-taxonomy-conflict');
    if (reasons.length)
      unclassified.push({
        collectionId,
        reasons,
        category: m.category,
        classification: m.classification,
        upstream: m.upstream_identity,
        summary: m.summary,
      });
    const topicName = reasons.length ? 'Unclassified' : reviewed.title;
    const topic = scope(`_llms-txt/topics/${segment(topicName)}`, topicName);
    link(topics, topic);
    const subcategoryName = reasons.length ? 'Needs review' : reviewed.subcategory;
    const sub = scope(`${topic.route}/${segment(subcategoryName)}`, subcategoryName);
    link(topic, sub);
    const family = segment(m.provider_type);
    const topicFamily = scope(`${sub.route}/${family}`, m.provider_type);
    link(sub, topicFamily);
    const collectionRoute = representative.slug || '_llms-txt/provider';
    const collection = scope(collectionRoute, representative.title);
    link(topicFamily, collection, m.summary);
    const familyScope = scope(`${families.route}/${family}`, m.provider_type);
    link(families, familyScope);
    link(familyScope, collection, m.summary);
    for (const task of new Set(pages.flatMap((p) => p.meta.tasks || []))) {
      const taskScope = scope(`${tasks.route}/${segment(task)}`, task);
      link(tasks, taskScope);
      link(taskScope, collection, m.summary);
    }
    for (const page of pages) {
      const roleName = segment(page.meta.role);
      let parent = scope(`${collectionRoute}/_llms/roles/${roleName}`, page.meta.role);
      link(collection, parent);
      for (const branch of page.meta.schema_path || []) {
        const child = scope(`${parent.route}/${segment(branch)}`, branch);
        link(parent, child);
        parent = child;
      }
      const content = scope(`${page.slug || '_llms-txt/root'}/_llms/content`, page.title);
      link(parent, content, page.meta.summary);
      pageIndexes[page.meta.id] = {
        html: url(page.slug ? `${page.slug}/` : ''),
        index: url(`${content.route}/llms.txt`),
        scope: content.route,
      };
    }
  }
  // All canonical pages are read one at a time. Bodies never enter a Vite module.
  const write = (route, text, limit = Infinity) => {
    if (bytes(text) > limit) throw new Error(`Output byte budget exceeded: ${route} (${bytes(text)} > ${limit})`);
    const file = join(outputRoot, route);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, text);
    generated.add(route);
  };
  mkdirSync(outputRoot, { recursive: true });
  const bulkFd = openSync(join(outputRoot, 'llms-full.txt'), 'w');
  const bulkHash = createHash('sha256');
  let bulkBytes = 0;
  try {
    for (const page of corpus.pages) {
      const text = readFileSync(join(corpus.root, page.name), 'utf8');
      const body = text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n(?:\r?\n)?/, '');
      const bulk = `\n\n<!-- canonical-id: ${page.meta.id} -->\n\n${body}`;
      writeSync(bulkFd, bulk);
      bulkHash.update(bulk);
      bulkBytes += bytes(bulk);
      const parts = splitMarkdown(body, 128 * 1024 - 4096);
      const content = scopes.get(pageIndexes[page.meta.id].scope);
      for (let i = 0; i < parts.length; i++) {
        const route = `${content.route}/part-${String(i + 1).padStart(4, '0')}.txt`;
        const next =
          i + 1 < parts.length
            ? `\n\n[Continue](${url(`${content.route}/part-${String(i + 2).padStart(4, '0')}.txt`)})\n`
            : '';
        write(route, parts[i] + next, 128 * 1024);
        content.entries.set(`part:${i}`, { title: `${page.title} — part ${i + 1}`, route, description: page.meta.id });
      }
    }
  } finally {
    closeSync(bulkFd);
  }
  generated.add('llms-full.txt');
  const corpusSha256 = `sha256:${bulkHash.digest('hex')}`;
  const render = (node, entries, optional = '') =>
    `# ${node.title}\n\n${entries.map((e) => `- [${hint(e.title)}](${url(e.route)}): ${hint(e.description)}\n`).join('')}${optional}`;
  // Recursively group using the smallest entry budget so every entry file has
  // complete immediate navigation, without descendant bodies or omitted links.
  const materialize = (node) => {
    let entries = [...node.entries.values()].sort((a, b) => a.route.localeCompare(b.route, 'en'));
    let depth = 0;
    const fits = (list) => list.length <= 32 && bytes(render(node, list)) <= 3500;
    while (!fits(entries)) {
      const chunks = [];
      let chunk = [];
      for (const entry of entries) {
        if (!fits([entry])) throw new Error(`indivisible index entry exceeds budget: ${entry.route}`);
        if (!fits([...chunk, entry])) {
          chunks.push(chunk);
          chunk = [];
        }
        chunk.push(entry);
      }
      if (chunk.length) chunks.push(chunk);
      if (chunks.length >= entries.length) throw new Error(`Hierarchy cannot converge: ${node.route}`);
      entries = chunks.map((group, i) => {
        const child = scope(
          `${node.route ? node.route + '/' : ''}_groups/${depth}-${i + 1}`,
          `${node.title} group ${i + 1}`,
        );
        for (const entry of group) child.entries.set(entry.route, entry);
        materialize(child);
        return {
          title: child.title,
          route: `${child.route}/llms.txt`,
          description: `${group.length} immediate entries`,
        };
      });
      depth++;
    }
    const optional =
      node.route === ''
        ? `\n## Optional\n\n- [Complete corpus download](${url('llms-full.txt')}): ${bulkBytes} bytes; ${corpus.pages.length} canonical pages, each once.\n`
        : '';
    const text = render(node, entries, optional);
    write(`${node.route ? node.route + '/' : ''}llms-small.txt`, text, 4096);
    write(`${node.route ? node.route + '/' : ''}llms.txt`, text, 16384);
    if (node.route) write(`${node.route}/llms-full.txt`, text, 16384);
  };
  for (const node of [...scopes.values()]) materialize(node);
  // Verify only discovery links, including continuation links. Existing content
  // links and property fragments remain governed by the canonical verifier.
  for (const route of generated) {
    if (route === 'llms-full.txt') continue;
    const text = readFileSync(join(outputRoot, route), 'utf8');
    const links =
      route.endsWith('llms.txt') || route.endsWith('llms-small.txt') || route.endsWith('llms-full.txt')
        ? [...text.matchAll(/\]\(([^)]+)\)/g)].map((x) => x[1])
        : [...text.matchAll(/\[Continue\]\(([^)]+)\)/g)].map((x) => x[1]);
    for (const target of links) {
      const relative = target.slice((prefix === '/' ? '' : prefix).length + 1);
      if (!generated.has(relative)) throw new Error(`Unresolved discovery link: ${route} -> ${target}`);
    }
  }
  writeFileSync(
    join(outputRoot, 'taxonomy-review.json'),
    JSON.stringify({ taxonomyDigest: digest(JSON.stringify(taxonomy)), unclassified }, null, 2) + '\n',
  );
  const result = {
    schemaVersion: 1,
    pages: corpus.pages.length,
    scopes: [...scopes.keys()],
    pageIndexes,
    unclassified,
    linksVerified: true,
    sourceManifestSha256: corpus.manifestSha256,
    taxonomyDigest: digest(JSON.stringify(taxonomy)),
    corpusSha256,
    bulkBytes,
    generatedFiles: generated.size,
    durationMs: Math.round(performance.now() - started),
    peakRssBytes: process.resourceUsage().maxRSS * 1024,
  };
  writeFileSync(join(outputRoot, 'llms-hierarchy-receipt.json'), JSON.stringify(result, null, 2) + '\n');
  return result;
}
