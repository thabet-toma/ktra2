import type { Deal, DealInstallment, DealPayment } from "@/types";

function paymentProgressScore(p: DealPayment): number {
  let s = 0;
  const jid = Number((p as { journalId?: unknown }).journalId);
  if (Number.isFinite(jid) && jid > 0) s += 32;
  if (p.bankSwiftImage && String(p.bankSwiftImage).trim()) s += 8;
  if (p.confirmedBySupplier) s += 4;
  if (p.isPosted) s += 4;
  if (p.alibabaClaimImage && String(p.alibabaClaimImage).trim()) s += 1;
  return s;
}

/** أفضل دفعة لنفس القسط إن وُجد أكثر من سجل (دفع مكرر): نفضّل من عليه سليب/تأكيد/ترحيل. */
export function pickBestDealPayment(
  candidates: DealPayment[]
): DealPayment | undefined {
  if (candidates.length === 0) return undefined;
  if (candidates.length === 1) return candidates[0];
  return [...candidates].sort(
    (a, b) => paymentProgressScore(b) - paymentProgressScore(a)
  )[0];
}

function typeMatchesInstallmentNumber(type: string | undefined, n: number): boolean {
  const t = String(type || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "");
  if (!t) return false;
  return (
    t === `دفعة_${n}` ||
    t === `دفعة${n}` ||
    t === `دفعه_${n}` ||
    t === `payment_${n}` ||
    t === `payment${n}` ||
    t === `الدفعة${n}` ||
    t === `الدفعة_${n}`
  );
}

/** ربط دفعة SQL بالقسط: installmentId من الواجهة لا يُخزَّن في MySQL، لذا نطابق برقم الدفعة أو عنوان النوع. */
export function findPaymentForInstallment(
  deal: Partial<Deal> | undefined,
  inst: Pick<DealInstallment, "id" | "installmentNumber">
): DealPayment | undefined {
  const list = deal?.payments || [];
  const byLink = list.filter((p) => p.installmentId === inst.id);
  if (byLink.length) return pickBestDealPayment(byLink);
  const n = inst.installmentNumber;
  const matched = list.filter(
    (p) =>
      p.installmentNumber === n || typeMatchesInstallmentNumber(p.type, n)
  );
  if (matched.length) return pickBestDealPayment(matched);
  /* صفقة بقسط واحد في الجدول — اربط بأي دفعة مسجّلة */
  if (
    list.length > 0 &&
    (deal?.installments?.length ?? 0) === 1 &&
    n === 1
  ) {
    return pickBestDealPayment(list);
  }
  /* عدة صفوف دفع كلها = إجمالي الصفقة (تكرار خطأ) — اربطها بالقسط 1 */
  const total = Number(deal?.totalAmount || 0);
  const eps = Math.max(0.01, total * 0.005);
  if (
    n === 1 &&
    list.length > 1 &&
    total > 0 &&
    list.every((p) => Math.abs(Number(p.amount || 0) - total) < eps)
  ) {
    return pickBestDealPayment(list);
  }
  if (list.length === 1 && n === 1) return list[0];
  return undefined;
}

export function findPaymentForInstallmentId(
  deal: Partial<Deal> | undefined,
  installmentId: string
): DealPayment | undefined {
  const inst = deal?.installments?.find((i) => i.id === installmentId);
  if (inst) return findPaymentForInstallment(deal, inst);
  const byPid = (deal?.payments || []).filter(
    (p) => p.installmentId === installmentId
  );
  if (byPid.length) return pickBestDealPayment(byPid);
  const m = /^sql-inst-(\d+)$/.exec(installmentId);
  if (m) {
    const n = Number(m[1]);
    if (Number.isFinite(n))
      return findPaymentForInstallment(deal, {
        id: installmentId,
        installmentNumber: n,
      });
  }
  return undefined;
}

/**
 * اختيار صف الدفع لتسجيل السليب بحيث لا يُحدَّث سجل قسط آخر (مثلاً دفع «الدفعة 2» فيُحدَّث سطر «الدفعة 1»).
 */
export function resolvePaymentForSwiftInstallment(
  payments: DealPayment[] | undefined,
  paymentType: string,
  installmentNumber: number | undefined | null,
  preferredId?: string | null
): { payment?: DealPayment; rejectReason?: string } {
  const list = payments || [];
  const typeEq = (p: DealPayment) =>
    String(p.type || "").trim() === String(paymentType || "").trim();

  const instDefined =
    installmentNumber != null && Number.isFinite(Number(installmentNumber));
  const inst = instDefined ? Number(installmentNumber) : undefined;

  if (preferredId != null && String(preferredId).trim() !== "") {
    const hit = list.find((p) => String(p.id) === String(preferredId));
    if (!hit) {
      return {
        rejectReason:
          "لم يُعثر على الدفعة المحددة. حدّث الصفحة (F5) ثم أعد المحاولة.",
      };
    }
    if (
      inst != null &&
      hit.installmentNumber != null &&
      Number(hit.installmentNumber) !== inst
    ) {
      return {
        rejectReason:
          "تعارض بين القسط المفتوح وسجل الدفعة — لا يُحدَّث سطر قسط آخر بالخطأ. حدّث الصفحة (F5) ثم نفّذ الدفع من سطر «الدفعة 2» فقط.",
      };
    }
    return { payment: hit };
  }

  const sameType = list.filter(typeEq);
  if (!sameType.length) {
    return {};
  }

  if (inst == null) {
    return {
      payment:
        sameType.length === 1
          ? sameType[0]
          : pickBestDealPayment(sameType),
    };
  }

  const matched = sameType.filter(
    (p) =>
      p.installmentNumber == null || Number(p.installmentNumber) === inst
  );
  if (matched.length) {
    return {
      payment:
        matched.length === 1
          ? matched[0]
          : pickBestDealPayment(matched),
    };
  }

  return {
    rejectReason:
      `يوجد سجل بنوع «${paymentType}» لكنه غير مربوط برقم القسط ${inst} في البيانات المحمّلة. حدّث الصفحة (F5) أو راجع الدفعات في الخادم لتجنّب دمج مبلغين على القسط الأول.`,
  };
}
