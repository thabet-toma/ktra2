/**
 * إشعار مدين/دائن على أيّ طرف — قواعد العرض النقيّة (بلا React) لشاشة المالية.
 *
 * الدلالة واحدة من منظور ذمّة الطرف (`sales/services/orders.py` — `post_credit_debit_note`):
 * المدين Dr ذمّته (يزيد ما عليه أو ينقص ما له)، والدائن Cr ذمّته.
 *
 * رصيد الطرف من `partners/{id}/balance/` (`open_balance`): للعميل مدين − دائن
 * (موجبه «عليه»)، وللدائن دائن − مدين (موجبه «له»). فأثر الإشعار على هذا الرقم
 * يعتمد على الطرف: المدين يزيده للعميل وينقصه للدائن، والدائن عكسه.
 */
import { formatMoney } from "./formatNumber.ts";

export type NoteType = "credit" | "debit";

/** أثر الإشعار على `open_balance` بإشارته — يُرسل `proposed_total` لمعاينة «بعد». */
export function noteBalanceDelta(noteType: NoteType, isCreditor: boolean, amount: number): number {
  const raises = (noteType === "debit") !== isCreditor;
  return raises ? amount : -amount;
}

/** «عليه 250» / «له 1,000» / «مسدَّد» — بلغة الطرف لا بإشارة. */
export function partyBalancePhrase(openBalance: number, isCreditor: boolean): string {
  if (!Number.isFinite(openBalance) || Math.abs(openBalance) < 0.005) return "مسدَّد";
  const owesUs = isCreditor ? openBalance < 0 : openBalance > 0;
  return `${owesUs ? "عليه" : "له"} ${formatMoney(Math.abs(openBalance))}`;
}

/** سطر الشرح: «هذا الإشعار سيجعل حاييم مديناً لنا بمبلغ 250». */
export function noteExplanation(partyName: string, noteType: NoteType, amount: number): string {
  const who = partyName.trim() || "الطرف";
  const side = noteType === "debit" ? "مديناً" : "دائناً";
  return `هذا الإشعار سيجعل ${who} ${side} لنا بمبلغ ${formatMoney(amount)}`;
}

/** ما يعنيه النوع لهذا الطرف — تحت سطر الشرح. */
export function noteMeaning(noteType: NoteType, isCreditor: boolean): string {
  if (noteType === "debit") {
    return isCreditor
      ? "ينقص ما له علينا أو يجعله مديناً — خصمٌ أو مرتجعٌ أو مطالبةٌ منه."
      : "يزيد ما عليه — مبلغٌ أو تكلفةٌ إضافية.";
  }
  return isCreditor
    ? "يزيد ما له علينا — مبلغٌ إضافيٌّ مستحقٌّ له."
    : "ينقص ما عليه — خصمٌ أو تسوية لصالحه.";
}
