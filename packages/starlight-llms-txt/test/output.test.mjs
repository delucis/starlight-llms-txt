import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';

const fixtureRoot = fileURLToPath(new URL('./fixtures/basic/', import.meta.url));
/** Path to Astro’s CLI entrypoint, so the build does not depend on `node_modules/.bin` being on `PATH`. */
const astroCli = fileURLToPath(new URL('./bin/astro.mjs', import.meta.resolve('astro/package.json')));
const read = (file) => readFileSync(new URL(`./fixtures/basic/dist/${file}`, import.meta.url), 'utf8');

/** Extract the body of the fenced code block that follows the given heading. */
function codeBlockAfter(markdown, heading) {
	const section = markdown.split(`## ${heading}\n`)[1];
	assert.ok(section, `Heading "${heading}" not found`);
	const match = section.match(/```diff\n([\s\S]*?)\n```/);
	assert.ok(match, `No diff code block found after "${heading}"`);
	return match[1];
}

describe('generated Markdown', () => {
	/** @type {string} */
	let full;
	/** @type {string} */
	let small;

	before(() => {
		execFileSync(process.execPath, [astroCli, 'build', '--root', fixtureRoot], { stdio: 'inherit' });
		full = read('llms-full.txt');
		small = read('llms-small.txt');
	});

	test('does not include Starlight heading anchor links', () => {
		for (const output of [full, small]) {
			assert.ok(output.includes('Getting started'));
			assert.doesNotMatch(output, /Section titled/);
			assert.doesNotMatch(output, /\]\(#getting-started\)/);
		}
	});

	test('places markers before indentation in `diff lang="…"` blocks', () => {
		assert.equal(
			codeBlockAfter(full, 'Diff with a language'),
			[
				'export default defineConfig({',
				'+  site: "https://example.com/",',
				'  integrations: [',
				'+    starlight({ title: "Docs" }),',
				'  ],',
				'});',
			].join('\n'),
		);
	});

	test('places markers before indentation for `ins`/`del` meta', () => {
		assert.equal(
			codeBlockAfter(full, 'Inserted and deleted lines'),
			['function f() {', '-  return 1;', '+  return 2;', '}'].join('\n'),
		);
	});

	test('keeps markers in plain `diff` blocks', () => {
		const block = codeBlockAfter(full, 'Plain diff');
		assert.match(block, /^\+added$/m);
		assert.match(block, /^-removed$/m);
	});

	test('leaves unified diffs with headers unchanged', () => {
		assert.equal(
			codeBlockAfter(full, 'Unified diff with headers'),
			['--- a/file.txt', '+++ b/file.txt', '@@ -1,2 +1,2 @@', ' context', '-old', '+new'].join('\n'),
		);
	});
});
