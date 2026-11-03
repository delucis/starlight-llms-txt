import type { CollectionEntry } from 'astro:content';
import { starlightLllmsTxtContext } from 'virtual:starlight-llms-txt/context';

const { defaultLocale, locales, title } = starlightLllmsTxtContext;
export const defaultLang = (defaultLocale === 'root' ? locales?.root?.lang : defaultLocale) || 'en';

/** Get the site title from the Starlight config, in the passed locale’s language if available. */
export function getSiteTitle(locale?: string): string {
	if (typeof title === 'string') return title;
	const lang = locale && (locales?.[locale]?.lang || locale);
	return (lang && title[lang]) || (title[defaultLang] as string);
}

/** Keys of all locales other than the default locale, e.g. `['fr', 'pt-br']`. */
export const localeKeys = Object.keys(locales || {}).filter(
	(key) => key !== 'root' && key !== defaultLang
);
const startsWithLocaleRE = new RegExp(`^(${localeKeys.join('|')})\/`);

/** Check if a content collection entry is part of the default locale or not. */
export function isDefaultLocale(doc: CollectionEntry<'docs'>): boolean {
	return !(localeKeys.includes(doc.id) || startsWithLocaleRE.test(doc.id));
}

/** Check if a content collection entry is part of the passed non-default locale. */
export function isInLocale(doc: CollectionEntry<'docs'>, locale: string): boolean {
	return doc.id === locale || doc.id.startsWith(locale + '/');
}

/** Directory of the default locale’s content, or `undefined` for the root locale. */
const defaultLocaleDir = defaultLocale === 'root' ? undefined : defaultLocale;

/**
 * Get the ID the equivalent page has in the default locale, e.g. `fr/guides/example` becomes
 * `guides/example`. This lets localized pages match the page patterns set in the plugin options.
 */
export function toDefaultLocaleId(id: string, locale: string): string {
	const path = id.slice(locale.length + 1);
	if (defaultLocaleDir) return path ? `${defaultLocaleDir}/${path}` : defaultLocaleDir;
	return path || 'index';
}

/** Append a `/` to the passed string if it doesn’t already end with one. */
export function ensureTrailingSlash(path: string) {
	return path.at(-1) === '/' ? path : path + '/';
}
