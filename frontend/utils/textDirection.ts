export function normalizeLanguageTag(languageCode?: string): string {
  return (languageCode || 'en').trim().toLowerCase().replace(/_/g, '-');
}

export function getTextDirection(languageCode?: string): 'ltr' | 'rtl' {
  const baseLanguage = normalizeLanguageTag(languageCode).split('-')[0];
  return ['ar', 'he', 'ur'].includes(baseLanguage) ? 'rtl' : 'ltr';
}
