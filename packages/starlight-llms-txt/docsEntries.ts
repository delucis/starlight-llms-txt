import { getCollection, type CollectionEntry } from 'astro:content';
import micromatch from 'micromatch';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';
import { isDefaultLocale } from './utils';

export async function getDocsEntries(): Promise<Array<CollectionEntry<'docs'>>> {
	let docs = await getCollection('docs', (doc) => isDefaultLocale(doc) && !doc.data.draft);
	if (starlightLllmsTxtContext.exclude.length > 0) {
		docs = docs.filter((doc) => !micromatch.isMatch(doc.id, starlightLllmsTxtContext.exclude));
	}
	return docs;
}
