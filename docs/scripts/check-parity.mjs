// Compares each built docs page with its section of llms-full.txt using markdown-parity-check.
// Run after `astro build`: `node scripts/check-parity.mjs [dist]`.
// Exit 0: every page matches. Exit 1: content differs. Exit 2: the build output could not be read or mapped.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { renderText, run } from 'markdown-parity-check';

// Must match `pageSeparator` in astro.config.ts.
const PAGE_SEPARATOR = '\n\n\n';

class InputError extends Error {}

function decodeEntities(text) {
	return text
		.replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
		.replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(Number(dec)))
		.replace(/&quot;/g, '"')
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&amp;/g, '&');
}

/** The site URL with base path, read from the generated llms.txt so it follows the Astro config. */
function siteBase(dist) {
	const llms = readFileSync(join(dist, 'llms.txt'), 'utf8');
	const match = /\]\((https?:\/\/[^)\s]+\/)llms-full\.txt\)/.exec(llms);
	if (!match) throw new InputError('llms.txt does not link to llms-full.txt');
	return match[1];
}

/** Every page built to `<slug>/index.html`, with the title and description llms-full.txt uses. */
function htmlPages(dist, base) {
	const files = [];
	const walk = (dir) => {
		for (const name of readdirSync(dir)) {
			const path = join(dir, name);
			if (statSync(path).isDirectory()) walk(path);
			else if (name === 'index.html') files.push(path);
		}
	};
	walk(dist);
	return files.map((file) => {
		const slug = relative(dist, file).split(sep).slice(0, -1).join('/');
		const html = readFileSync(file, 'utf8');
		const titles = [...html.matchAll(/<h1 id="_top"[^>]*>([\s\S]*?)<\/h1>/g)];
		const descriptions = [...html.matchAll(/<meta name="description" content="([^"]*)"/g)];
		if (titles.length !== 1 || descriptions.length !== 1) {
			throw new InputError(`${slug || '/'}: expected one page title and one meta description`);
		}
		return {
			slug: slug || '/',
			file,
			html,
			title: decodeEntities(titles[0][1].replace(/<[^>]+>/g, '').trim()),
			description: decodeEntities(descriptions[0][1]),
			url: base + (slug ? `${slug}/` : ''),
		};
	});
}

/**
 * Splits llms-full.txt into pages. Each page starts with the separator, its `# title` line and its
 * `> description` line. Every header must occur exactly once, and the pages must cover the file from
 * the first header to the end, so an ambiguous or missing page stops the check instead of guessing.
 */
function splitExport(full, pages) {
	const system = /^<SYSTEM>[^\n]*<\/SYSTEM>/.exec(full);
	if (!system) throw new InputError('llms-full.txt does not start with a <SYSTEM> line');
	const located = pages
		.map((page) => {
			const header = `${PAGE_SEPARATOR}# ${page.title}\n\n> ${page.description}\n\n`;
			const starts = [];
			for (let i = full.indexOf(header); i !== -1; i = full.indexOf(header, i + 1)) starts.push(i);
			if (starts.length !== 1) {
				throw new InputError(`${page.slug}: page header occurs ${starts.length} times in llms-full.txt`);
			}
			return { ...page, start: starts[0], header };
		})
		.sort((a, b) => a.start - b.start);
	if (located[0].start !== system[0].length) {
		throw new InputError('llms-full.txt has text between the <SYSTEM> line and the first page');
	}
	return located.map((page, i) => {
		const end = i + 1 < located.length ? located[i + 1].start : full.length;
		return { ...page, markdown: full.slice(page.start + page.header.length, end) };
	});
}

try {
	const dist = process.argv[2] ?? 'dist';
	for (const name of ['llms.txt', 'llms-full.txt']) {
		if (!existsSync(join(dist, name))) throw new InputError(`missing ${join(dist, name)}; build the docs first`);
	}
	const full = readFileSync(join(dist, 'llms-full.txt'), 'utf8');
	const pages = splitExport(full, htmlPages(dist, siteBase(dist)));
	let failed = 0;
	for (const page of pages) {
		const source = (file, body) => ({ body, base: page.url, meta: { kind: 'file', file, bytes: Buffer.byteLength(body) } });
		const report = run(
			source(relative(dist, page.file), page.html),
			source(`llms-full.txt (${page.slug})`, page.markdown),
			// Compare the article body. The title and description were matched exactly above.
			{ mode: 'offline', strict: true, htmlProfile: 'starlight', selector: '.sl-markdown-content' }
		);
		if (report.summary.exitCode === 0) {
			console.log(`ok ${page.slug}`);
		} else {
			failed++;
			console.log(renderText(report));
		}
	}
	console.log(`${pages.length - failed}/${pages.length} pages match llms-full.txt`);
	process.exit(failed ? 1 : 0);
} catch (error) {
	console.error(error instanceof InputError ? `check-parity: ${error.message}` : error);
	process.exit(2);
}
