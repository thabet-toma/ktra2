/**
 * اختيار التبويب النشط **بالمعرّف لا بالفهرس**.
 *
 * كان `KitDocumentShell` و`KitTabs` يحفظان التبويب النشط رقماً (`localTab`)،
 * فأيّ شاشة تغيّر طول مصفوفة `tabs` وقت التشغيل تقفز بالمستخدم إلى تبويب آخر:
 * إدراج تبويب قبل الفهرس الحالي يزيح كل ما بعده. (وقع فعلاً عند تفعيل «تتبّع
 * بالرقم التسلسلي» في كرت الصنف، فعُولج حينها بإلحاق التبويب آخر القائمة.)
 *
 * القاعدة كلّها هنا، دالّةً صرفة تُختبر بلا متصفح — والغلافان يستهلكانها.
 */

export interface KeyedTab {
  key: string;
}

/**
 * @param tabs      التبويبات المعروضة الآن (قد تتغيّر وقت التشغيل).
 * @param picked    ما اختاره المستخدم بيده (أقوى مصدر ما دام موجوداً).
 * @param requested تبويبٌ مطلوب من الخارج (`initialTab` أو `?tab=` في الرابط).
 * @returns مفتاح التبويب النشط، أو `null` حين لا تبويب أصلاً.
 */
export function resolveActiveTabKey(
  tabs: readonly KeyedTab[],
  picked?: string | null,
  requested?: string | null,
): string | null {
  if (!tabs || tabs.length === 0) return null;
  const exists = (key?: string | null): boolean =>
    !!key && tabs.some((t) => t.key === key);
  if (exists(picked)) return picked as string;
  if (exists(requested)) return requested as string;
  return tabs[0].key;
}
