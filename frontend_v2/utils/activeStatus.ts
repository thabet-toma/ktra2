/**
 * T4 — منطق «نشط / غير نشط» العامّ المشترك بين الأطراف والأصناف: الحالة الثلاثية،
 * وتحليلها، وتحديد ما يغيب عن قائمة المنتقي من سجلاّت يحملها مستندٌ قديم.
 *
 * المنتقي (`lookup/products/`، `partners/lookup/`) يُخفي الموقوف كي لا يدخل مستنداً جديداً؛
 * أما مستندٌ قائمٌ يحمل منتجاً أو طرفاً أُوقف لاحقاً فلا بدّ أن يبقى يعرضه باسمه.
 */

export type ActiveStatus = "active" | "inactive" | "all";

export const ACTIVE_STATUS_VALUES: readonly ActiveStatus[] = ["active", "inactive", "all"];

/** قيمة من الرابط أو التخزين → حالة صالحة؛ أيّ شيء آخر = «نشط» (الافتراضي). */
export function parseActiveStatus(raw: unknown): ActiveStatus {
  return ACTIVE_STATUS_VALUES.includes(raw as ActiveStatus) ? (raw as ActiveStatus) : "active";
}

/** السجلّ موقوفٌ صراحةً؟ الغائب/null = نشط (الخادم قد لا يرسل الحقل بعد). */
export function isInactiveRecord(rec: { is_active?: boolean | null } | null | undefined): boolean {
  return rec?.is_active === false;
}

/**
 * معرّفات يحملها المستند وليست في قائمة المنتقي ولم تُجلَب بعد — هي ما يُجلب فرادى
 * من نقطة الاسترجاع (غير المفلترة بالحالة). الفارغ والصفر وغير الرقمي يُتجاهل.
 */
export function missingRecordIds(
  used: Iterable<unknown>,
  known: Iterable<{ id: number | string }>,
  settled: ReadonlySet<number>,
): number[] {
  const have = new Set<number>();
  for (const r of known) have.add(Number(r.id));
  const out = new Set<number>();
  for (const raw of used) {
    if (raw === "" || raw == null) continue;
    const id = Number(raw);
    if (!Number.isInteger(id) || id <= 0) continue;
    if (!have.has(id) && !settled.has(id)) out.add(id);
  }
  return [...out];
}

/** عدد أرقام المستندات المعروضة في نافذة تأكيد الإيقاف؛ الباقي يُختصر بـ«و N أخرى». */
export const IMPACT_NUMBERS_SHOWN = 5;

/** صفّ مستندٍ غير مرحَّل في استجابة `deactivation-impact/` — للمنتج والطرف معاً
 *  (`inventory/services.py` — `draft_documents_holding`). */
export interface DraftDocumentRow {
  kind: string;
  kind_label: string;
  id: number;
  number: string;
  date: string | null;
}

/** اسم السجلّ في المنتقيات التي تعرض الموقوف: يحمل «(غير نشط)» بعد اسمه. */
export function labelWithStatus(name: string, isActive: boolean | null | undefined): string {
  return isActive === false ? `${name} (غير نشط)` : name;
}
