/**
 * فهرسُ صفحات الإعدادات (#75/#69): «أوّل ما أفوت يكون بس عناوين الإعدادات، ولمّا
 * أكبس على واحد يبيّن اللي تحته». هنا بحثُ الفهرس وحده — دالّةٌ خالصة تُختبر بلا
 * واجهة؛ والشاشةُ في `components/settings/SettingsIndex.tsx`.
 */
export interface SettingsIndexEntry {
  id: string;
  title: string;
  description: string;
  /** أسماءُ الحقول داخل القسم: من يبحث عن «خصم المصدر» يجد قسمَ الضرائب لا عنوانَه فقط. */
  keywords?: readonly string[];
}

/** الهمزاتُ والتاءُ المربوطةُ والألفُ المقصورةُ والتشكيلُ والتطويلُ لا تُسقط مطابقة. */
export const normalizeSettingsSearch = (text: string): string =>
  text
    .replace(/[ً-ْـ]/g, '')
    .replace(/[أإآ]/g, 'ا')
    .replace(/ة/g, 'ه')
    .replace(/ى/g, 'ي')
    .replace(/\s+/g, ' ')
    .toLowerCase()
    .trim();

/** كلُّ كلمةٍ في البحث يجب أن تظهر في العنوان أو الوصف أو أسماء الحقول؛ الترتيبُ يبقى كما هو. */
export function filterSettingsSections<T extends SettingsIndexEntry>(sections: readonly T[], query: string): T[] {
  const words = normalizeSettingsSearch(query).split(' ').filter(Boolean);
  if (!words.length) return [...sections];
  return sections.filter((section) => {
    const haystack = normalizeSettingsSearch([section.title, section.description, ...(section.keywords ?? [])].join(' '));
    return words.every((word) => haystack.includes(word));
  });
}
