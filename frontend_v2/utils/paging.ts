/**
 * أرقام الصفحات المتبقية بعد الأولى — الحسابُ الصرف لـ`getAllProducts`.
 *
 * كانت الحلقةُ المتتالية تكرّر حتى `allRows.length >= count` أو صفحةٍ فارغة،
 * والموازية تحتاج أن تعرف أرقام الصفحات **قبل** أن تبدأ — فالقاعدة هنا هي
 * القاعدة نفسها لا نسخةٌ ثانية منها، وإلا صار في المستودع طريقان لطلب الشيء
 * نفسه يتباعدان بلا أن يلاحظ أحد:
 *
 *   - `count` هو المرجع، لا طولُ الصفحة الأولى. لكنّ **حجمَ الصفحة الفعلي**
 *     هو ما وصل فعلاً: خادمٌ يحدّ `page_size` بأقلّ ممّا طُلب يعيد صفحةً أولى
 *     أقصر من `pageSize` وله صفحاتٌ بعدها بحجمها هي — فحسابُ العدد بحجم الطلب
 *     يعطي صفحاتٍ أقل ويُفقد صفوفاً بصمت (`count=450، طُلب 200، ووصل 120`
 *     ⇒ ‏[2, 3] وحدها، والصفوف 361–450 لا تُطلب أبداً).
 *   - صفحةٌ أولى **فارغة** مع `count` موجب: الحلقة القديمة كانت تتوقّف هناك،
 *     فلا تُطلب صفحةٌ لم تُثبت الحلقةُ وجودها.
 */

/** أرقام الصفحات 2، 3، … التي تكمل صفحةً أولى فيها `firstPageRows` صفّاً. */
export function remainingPageNumbers(
  count: number,
  pageSize: number,
  firstPageRows: number,
): number[] {
  const size = Math.floor(pageSize);
  if (!Number.isFinite(size) || size <= 0) return [];
  const total = Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0;
  const seen = Number.isFinite(firstPageRows) ? Math.max(0, Math.floor(firstPageRows)) : 0;
  // لا صفحةَ بعد صفحةٍ فارغة، ولا بعد `count` وصلت صفوفه كلَّها.
  if (seen <= 0 || total <= seen) return [];
  // حجمُ الصفحة الفعلي: ما أعاده الخادم حين قصر عن المطلوب، وإلا المطلوب.
  const effective = seen < size ? seen : size;
  const pages: number[] = [];
  for (let pg = 2; pg <= Math.ceil(total / effective); pg++) pages.push(pg);
  return pages;
}
