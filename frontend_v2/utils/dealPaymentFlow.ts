import type { DealPayment } from "@/types";

/**
 * الدفعة «مسجّلة» بأي شكل (مبلغ، سليب، صندوق، ترحيل، مطالبة) ولم يُؤكَّد استلامها من المورد بعد.
 * يحدد زر «تأكيد المورد» ونافذة التأكيد الخفيفة — بدون إعادة فتح شاشة «إجراء الدفع» الكاملة.
 */
export function isAwaitingSupplierConfirmation(
  p: DealPayment | undefined | null
): boolean {
  if (!p || p.confirmedBySupplier) return false;
  if (Number(p.amount || 0) > 0) return true;
  if (p.alibabaClaimImage && String(p.alibabaClaimImage).trim()) return true;
  return Boolean(
    (p.bankSwiftImage && String(p.bankSwiftImage).trim()) ||
      (p.cashBoxWithdrawalAt && String(p.cashBoxWithdrawalAt).trim()) ||
      p.isPosted
  );
}
