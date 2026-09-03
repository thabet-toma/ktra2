/**
 * ISSUE #82 — المعجم: نقطة القراءة الواحدة على جانب الواجهة.
 *
 * الحقيقة تصل من الخادم على حمولة `/api/permissions/me` نفسها (`terms`،
 * القرار 8 في #46: لا آلية ثالثة) — `DEFAULT_TERMS` هنا احتياطٌ لأول رسمة
 * قبل وصول الردّ فقط، ويجب أن يطابق `core/terminology.py` (`_default_terms`)
 * حرفياً لمفتاحين المكتب: `doc.sales_invoice` و`line.item` — الباقي (١٥ نوع
 * مستند آخر) يصل من الخادم وحده ولا نسخة له هنا.
 */
export const DEFAULT_TERMS: Record<string, string> = {
  "doc.sales_invoice": "فاتورة مبيعات",
  "line.item": "منتج",
};

/** المصطلح الفعلي — مفتاحٌ غائب يسقط للافتراضي المحلي ثم للمفتاح نفسه، بلا رمي. */
export function resolveTerm(terms: Record<string, string> | undefined, key: string): string {
  return terms?.[key] ?? DEFAULT_TERMS[key] ?? key;
}
