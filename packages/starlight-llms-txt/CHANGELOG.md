# starlight-llms-txt

## 0.6.0

### Minor Changes

- [#30](https://github.com/delucis/starlight-llms-txt/pull/30) [`a1650c9`](https://github.com/delucis/starlight-llms-txt/commit/a1650c92b16377d9abdcccc8b2a68b34bc695796) Thanks [@alvinometric](https://github.com/alvinometric)! - Adds a new `rawContent` option to skip the Markdown processing pipeline

## 0.5.1

### Patch Changes

- [#22](https://github.com/delucis/starlight-llms-txt/pull/22) [`2a8102a`](https://github.com/delucis/starlight-llms-txt/commit/2a8102a2554ac80495568b89acba2bb5a437d206) Thanks [@florian-lefebvre](https://github.com/florian-lefebvre)! - Fixes output of Expressive Code `diff` codeblocks with a `lang` attribute

## 0.5.0

### Minor Changes

- [#18](https://github.com/delucis/starlight-llms-txt/pull/18) [`52838f6`](https://github.com/delucis/starlight-llms-txt/commit/52838f63fc5280436982880744921dac923d4be2) Thanks [@pelikhan](https://github.com/pelikhan)! - Add page separator configuration object

## 0.4.1

### Patch Changes

- [#13](https://github.com/delucis/starlight-llms-txt/pull/13) [`629fa9b`](https://github.com/delucis/starlight-llms-txt/commit/629fa9b00444a70ebf9aac3e15375f400f8a10cc) Thanks [@jumski](https://github.com/jumski)! - Filters out draft pages from output

## 0.4.0

### Minor Changes

- [#10](https://github.com/delucis/starlight-llms-txt/pull/10) [`7f914f5`](https://github.com/delucis/starlight-llms-txt/commit/7f914f526dbe504ed3e3763864fd9ec1d5150d0d) Thanks [@delucis](https://github.com/delucis)! - Adds a new `customSets` option to support breaking up large docs into multiple custom document sets

### Patch Changes

- [`0c0678d`](https://github.com/delucis/starlight-llms-txt/commit/0c0678da19f1f9981f808a1fa0e1a01c77a26b4d) Thanks [@delucis](https://github.com/delucis)! - Improves rendering of Starlight’s `<FileTree>` component by removing “Directory” labels

## 0.3.0

### Minor Changes

- [#7](https://github.com/delucis/starlight-llms-txt/pull/7) [`cba125e`](https://github.com/delucis/starlight-llms-txt/commit/cba125ed259601895ba78f6da95a55564b914470) Thanks [@hippotastic](https://github.com/hippotastic)! - Adds options to promote or demote pages in the order of the `llms-full.txt` and `llms-small.txt` output files

## 0.2.1

### Patch Changes

- [`39760e7`](https://github.com/delucis/starlight-llms-txt/commit/39760e70e921b685bc6dc6a5338f8f80bf79e57e) Thanks [@delucis](https://github.com/delucis)! - Removes Expressive Code’s “Terminal Window” labels from output

- [`26fa616`](https://github.com/delucis/starlight-llms-txt/commit/26fa616793798bda41911bfe7dc229475f89db26) Thanks [@delucis](https://github.com/delucis)! - Fixes a bug where pages excluded using the `exclude` configuration option were excluded in `llms-full.txt` instead of only in `llms-small.txt`

## 0.2.0

### Minor Changes

- [#4](https://github.com/delucis/starlight-llms-txt/pull/4) [`a4a77ca`](https://github.com/delucis/starlight-llms-txt/commit/a4a77ca433b7cee7cbeb3c603498e760cd037867) Thanks [@delucis](https://github.com/delucis)! - Adds support for generating a smaller `llms-small.txt` file for smaller context windows

- [`618fa88`](https://github.com/delucis/starlight-llms-txt/commit/618fa882d29bc4b7ce054392c9b65d97ce1ceb82) Thanks [@delucis](https://github.com/delucis)! - Adds support for including additional optional links in the main `llms.txt` entrypoint

### Patch Changes

- [#4](https://github.com/delucis/starlight-llms-txt/pull/4) [`a4a77ca`](https://github.com/delucis/starlight-llms-txt/commit/a4a77ca433b7cee7cbeb3c603498e760cd037867) Thanks [@delucis](https://github.com/delucis)! - Sort pages in llms.txt output

## 0.1.2

### Patch Changes

- [`d5ca030`](https://github.com/delucis/starlight-llms-txt/commit/d5ca0307192585f141164dd8328f244f32db5a90) Thanks [@delucis](https://github.com/delucis)! - Improves rendering of Starlight Tabs component in output

## 0.1.1

### Patch Changes

- [`04f641c`](https://github.com/delucis/starlight-llms-txt/commit/04f641c48dd70acf480c80df26d9e2f774510428) Thanks [@delucis](https://github.com/delucis)! - Preserves language metadata on code blocks

## 0.1.0

### Minor Changes

- [`249438b`](https://github.com/delucis/starlight-llms-txt/commit/249438b23d2998ef79a1bbb19ac7a532938f7ade) Thanks [@delucis](https://github.com/delucis)! - Initial release
