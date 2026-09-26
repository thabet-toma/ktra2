/**
 * بلاغ المالك: «أنا عبّيت شيك قيد التحصيل — لازم يطلع ع حساب تحصيل شيكات مش
 * نقدي». سطر القيد تحت النموذج كان يعرض الصندوق دائماً ولو كان السند كلّه
 * شيكات، فيقرأ المستخدم قيداً غير الذي سيُرحَّل فعلاً.
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  buildVoucherEntryPreview,
  CHEQUES_PAYABLE_LABEL,
  CHEQUES_UNDER_COLLECTION_LABEL,
} from "./voucherEntryPreview.ts";

const base = {
  cashAccountLabel: "1101 النقدية",
  partnerLabel: "أشرف",
  direction: "Incoming" as const,
};

test("a cheque-only receipt debits cheques under collection, never cash", () => {
  const lines = buildVoucherEntryPreview({ ...base, cashAmount: 0, chequesAmount: 50 });
  assert.deepEqual(lines, [
    { side: "Dr", label: CHEQUES_UNDER_COLLECTION_LABEL, amount: 50 },
    { side: "Cr", label: "ذمم العميل أشرف", amount: 50 },
  ]);
});

test("a cash-only receipt debits the chosen cash account", () => {
  const lines = buildVoucherEntryPreview({ ...base, cashAmount: 50, chequesAmount: 0 });
  assert.deepEqual(lines, [
    { side: "Dr", label: "1101 النقدية", amount: 50 },
    { side: "Cr", label: "ذمم العميل أشرف", amount: 50 },
  ]);
});

test("a mixed receipt splits the debit between cash and cheques", () => {
  const lines = buildVoucherEntryPreview({ ...base, cashAmount: 20, chequesAmount: 30 });
  assert.deepEqual(lines, [
    { side: "Dr", label: "1101 النقدية", amount: 20 },
    { side: "Dr", label: CHEQUES_UNDER_COLLECTION_LABEL, amount: 30 },
    { side: "Cr", label: "ذمم العميل أشرف", amount: 50 },
  ]);
});

test("an outgoing voucher mirrors it: supplier debited, cheques payable credited", () => {
  const lines = buildVoucherEntryPreview({
    ...base, direction: "Outgoing", partnerLabel: "المورد", cashAmount: 0, chequesAmount: 70,
  });
  assert.deepEqual(lines, [
    { side: "Dr", label: "ذمم المورد المورد", amount: 70 },
    { side: "Cr", label: CHEQUES_PAYABLE_LABEL, amount: 70 },
  ]);
});

test("nothing to preview before any amount is entered", () => {
  assert.deepEqual(
    buildVoucherEntryPreview({ ...base, cashAmount: 0, chequesAmount: 0 }), [],
  );
});

test("refund vouchers name the party by its role, not by the direction", () => {
  const refund = buildVoucherEntryPreview({ ...base, cashAmount: 80, chequesAmount: 0, direction: "Outgoing", partnerRole: "العميل" });
  assert.equal(refund[0].side, "Dr");
  assert.match(refund[0].label, /^ذمم العميل /);
  const receipt = buildVoucherEntryPreview({ ...base, cashAmount: 80, chequesAmount: 0, partnerRole: "المورد" });
  assert.match(receipt.find((l) => l.side === "Cr")?.label ?? "", /^ذمم المورد /);
});
