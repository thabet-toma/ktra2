/**
 * T5 — منطق «نشط / غير نشط» الخالص للأطراف: فلتر الحالة، نصّ تأكيد الإيقاف، ووسم الاسم في
 * شاشات الدفع، وتقليم نسخة الأطراف المخزَّنة للعمل دون اتصال.
 *
 * الموقوف لا يظهر في الفواتير والطلبيات الجديدة، لكن الدفع له يبقى مسموحاً كي يُسدَّد رصيده —
 * لذا شاشات السندات والشيكات والإشعارات تطلب `status=all` وتَسِم الموقوف باسمه.
 */

import { IMPACT_NUMBERS_SHOWN, type ActiveStatus, type DraftDocumentRow } from "./activeStatus.ts";

/** استجابة `partners/{id}/deactivation-impact/`. */
export interface PartnerDeactivationImpact {
  open_balance: string;
  balance_side_label: string;
  draft_documents_count: number;
  draft_documents: DraftDocumentRow[];
}

/**
 * نصّ نافذة تأكيد الإيقاف: الرصيد المفتوح (إن وُجد) والمستندات غير المكتملة (إن وُجدت)
 * ثم القاعدة. `formatAmount` يُمرَّر من الشاشة (`formatMoney`) فيبقى هذا الملف خالصاً.
 */
export function deactivationConfirmMessage(
  name: string,
  impact: PartnerDeactivationImpact,
  formatAmount: (value: string) => string,
): string {
  const lines: string[] = [`سيصبح «${name}» غير نشط.`];
  const balance = Number(impact.open_balance);
  if (Number.isFinite(balance) && balance !== 0) {
    const side = impact.balance_side_label ? ` (${impact.balance_side_label})` : "";
    lines.push(`رصيده المفتوح: ${formatAmount(String(Math.abs(balance)))}${side}`);
  }
  if (impact.draft_documents_count > 0) {
    const shown = impact.draft_documents.slice(0, IMPACT_NUMBERS_SHOWN).map((d) => d.number);
    const rest = impact.draft_documents_count - shown.length;
    const numbers = shown.join("، ") + (rest > 0 ? ` و${rest} أخرى` : "");
    lines.push(`مستندات غير مكتملة: ${impact.draft_documents_count} (${numbers})`);
  }
  lines.push("", "لن يظهر في المستندات الجديدة، والدفعات له تبقى مسموحة.");
  return lines.join("\n");
}

/**
 * نصّ تأكيد الإيقاف الجماعي: كم طرفاً، وكم منها عليه رصيد مفتوح، وكم مستنداً غير مكتمل
 * في مجموعهم. الأرصدة لا تُجمع (جهاتها مختلفة) — يُعدّ من عليه رصيدٌ فقط.
 */
export function bulkDeactivationConfirmMessage(count: number, impacts: PartnerDeactivationImpact[]): string {
  const withBalance = impacts.filter((i) => Number(i.open_balance) !== 0).length;
  const drafts = impacts.reduce((sum, i) => sum + i.draft_documents_count, 0);
  const lines: string[] = [`سيصبح ${count} من الأطراف المحدَّدة غير نشطين.`];
  if (withBalance > 0) lines.push(`عليهم رصيدٌ مفتوح: ${withBalance} منهم`);
  if (drafts > 0) lines.push(`مستندات غير مكتملة: ${drafts}`);
  lines.push("", "لن يظهروا في المستندات الجديدة، والدفعات لهم تبقى مسموحة.");
  return lines.join("\n");
}

/** ما يلزم من صفّ نسخة الأطراف المخزَّنة (Dexie) لقرار التقليم. */
export interface CachedPartnerRow {
  id: number;
  partner_type: string;
  data: string;
}

function cachedIsInactive(row: CachedPartnerRow): boolean {
  try {
    return (JSON.parse(row.data) as { is_active?: unknown }).is_active === false;
  } catch {
    return false;
  }
}

/** النوع قد يكون قائمة مفصولة بفاصلة (الأطراف الدائنة) كما يقبلها الخادم؛ فارغ = كل الأنواع. */
function inTypeScope(row: CachedPartnerRow, partnerType?: string): boolean {
  return !partnerType || partnerType.split(",").includes(row.partner_type);
}

/**
 * بعد جلبٍ ناجح: الصفوف المخزَّنة التي يجب حذفها لأن الخادم لم يعد يعيدها — طرفٌ أُوقف أو حُذف
 * يختفي دون اتصال أيضاً. الحدود: نوع الجلب فقط، وبحالة `all` يُقلَّم كل غائب، أما بحالة
 * `active` فلا يُمسّ المخزَّن الموقوف (خرج من جلبٍ سابق بـ`all` وهو مطلوب لشاشات الدفع).
 */
export function staleCachedPartnerIds(
  cached: CachedPartnerRow[],
  fetchedIds: Iterable<number>,
  partnerType: string | undefined,
  status: ActiveStatus,
): number[] {
  const fetched = new Set(fetchedIds);
  return cached
    .filter((row) => inTypeScope(row, partnerType) && !fetched.has(row.id))
    .filter((row) => status === "all" || !cachedIsInactive(row))
    .map((row) => row.id);
}

/** الأطراف المخزَّنة المعروضة دون اتصال: نوعها ضمن النطاق، والموقوف إلا إن طُلب `all`. */
export function visibleCachedPartners<T extends CachedPartnerRow>(
  cached: T[],
  partnerType: string | undefined,
  status: ActiveStatus,
): T[] {
  return cached
    .filter((row) => inTypeScope(row, partnerType))
    .filter((row) => {
      if (status === "all") return true;
      return status === "inactive" ? cachedIsInactive(row) : !cachedIsInactive(row);
    });
}
