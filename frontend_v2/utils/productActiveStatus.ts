/**
 * T4 — منطق إيقاف المنتج الخالص: نصّ تأكيد الإيقاف (بالكمية والمسوّدات) ووسم الاسم.
 *
 * الإيقاف جائز برصيدٍ موجود (قرار المالك) — الواجهة تحذّر ولا تمنع: الصنف الموقوف
 * لا يظهر في المستندات الجديدة، وتبقى له شاشات الجرد وحركات المخزون والتحويل والتقارير
 * كي يُصفَّى ما تبقّى منه.
 */
import { IMPACT_NUMBERS_SHOWN, type DraftDocumentRow } from "./activeStatus.ts";

/** استجابة `inventory/products/{id}/deactivation-impact/`. */
export interface ProductDeactivationImpact {
  quantity_on_hand: string;
  draft_documents_count: number;
  draft_documents: DraftDocumentRow[];
}

/** «فاتورة بيع 123» لكل مستند — حتى `IMPACT_NUMBERS_SHOWN` منها والباقي «و N أخرى». */
function draftSummary(impact: ProductDeactivationImpact): string {
  const shown = impact.draft_documents
    .slice(0, IMPACT_NUMBERS_SHOWN)
    .map((d) => `${d.kind_label} ${d.number}`.trim());
  const rest = impact.draft_documents_count - shown.length;
  return shown.join("، ") + (rest > 0 ? ` و${rest} أخرى` : "");
}

/**
 * نصّ نافذة تأكيد إيقاف منتج واحد: الكمية الموجودة (إن وُجدت) والمسوّدات (إن وُجدت)
 * ثم القاعدة. `formatQty` يُمرَّر من الشاشة (`formatQuantity`) فيبقى الملف خالصاً.
 */
export function productDeactivationConfirmMessage(
  name: string,
  impact: ProductDeactivationImpact,
  formatQty: (value: string) => string,
): string {
  const lines: string[] = [`سيصبح «${name}» غير نشط.`];
  const qty = Number(impact.quantity_on_hand);
  if (Number.isFinite(qty) && qty !== 0) {
    lines.push(`الكمية الموجودة في المخزون: ${formatQty(impact.quantity_on_hand)}`);
  }
  if (impact.draft_documents_count > 0) {
    lines.push(`مسوّدات تحمله: ${impact.draft_documents_count} (${draftSummary(impact)})`);
  }
  lines.push("", "لن يظهر في المستندات الجديدة، وستُرفض مسوّداته عند الترحيل حتى تنشّطه.");
  return lines.join("\n");
}

/**
 * إيقاف منتجٍ ذي براندات (صفّ العائلة في القائمة) دفعةً واحدة: الكمية مجموعُ براندَاته،
 * والمسوّدات اتحادُ مسوّداتها بلا تكرار (مستندٌ واحد قد يحمل براندين).
 */
export function familyDeactivationConfirmMessage(
  name: string,
  impacts: ProductDeactivationImpact[],
  formatQty: (value: string) => string,
): string {
  const lines: string[] = [`سيصبح «${name}» غير نشط بكل براندَاته (${impacts.length}).`];
  const qty = impacts.reduce((sum, i) => sum + (Number(i.quantity_on_hand) || 0), 0);
  if (qty !== 0) lines.push(`الكمية الموجودة في المخزون: ${formatQty(String(qty))}`);
  const drafts = new Map<string, ProductDeactivationImpact["draft_documents"][number]>();
  for (const i of impacts) {
    for (const d of i.draft_documents) drafts.set(`${d.kind}:${d.id}`, d);
  }
  // العدّاد الخادمي يسبق القائمة المقصوصة (≤20)؛ المجموع هنا الأكبر بينهما.
  const count = Math.max(drafts.size, ...impacts.map((i) => i.draft_documents_count));
  if (count > 0) {
    lines.push(`مسوّدات تحمله: ${count} (${draftSummary({
      quantity_on_hand: "0", draft_documents_count: count, draft_documents: [...drafts.values()],
    })})`);
  }
  lines.push("", "لن يظهر في المستندات الجديدة، وستُرفض مسوّداته عند الترحيل حتى تنشّطه.");
  return lines.join("\n");
}

