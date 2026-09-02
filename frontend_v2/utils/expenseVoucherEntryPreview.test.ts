/**
 * issue #56 — سند مصروف: صاحب المحلّ لا يعرف المدين من الدائن، فالنموذج يُقرّر
 * عنه (أيّ حقول يطلبها كل مصدر دفع) ويُعاين له القيد قبل الحفظ.
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  buildExpenseVoucherEntryPreview,
  EXPENSE_PAYMENT_METHODS,
  expenseVoucherRequiresCashAccount,
  TRADE_PAYABLES_LABEL,
  VAT_INPUT_LABEL,
} from "./expenseVoucherEntryPreview.ts";
import { CHEQUES_PAYABLE_LABEL } from "./voucherEntryPreview.ts";

test("صندوق/بنك وحدها تطلب حساب صندوق — الشيك و«على الحساب» يحلّهما الخادم", () => {
  assert.equal(expenseVoucherRequiresCashAccount("cash"), true);
  assert.equal(expenseVoucherRequiresCashAccount("cheque"), false);
  assert.equal(expenseVoucherRequiresCashAccount("on_account"), false);
});

test("قائمة مصادر الدفع الثلاثة كما في التذكرة، بلا أكثر ولا أقل", () => {
  assert.deepEqual(EXPENSE_PAYMENT_METHODS.map((m) => m.value), ["cash", "cheque", "on_account"]);
});

test("مصروف كهرباء نقداً بلا ضريبة: مدين المصروف، دائن الصندوق", () => {
  const lines = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: "5203 كهرباء ومياه",
    amount: 500,
    paymentMethod: "cash",
    cashAccountLabel: "1101 النقدية",
  });
  assert.deepEqual(lines, [
    { side: "Dr", label: "5203 كهرباء ومياه", amount: 500 },
    { side: "Cr", label: "1101 النقدية", amount: 500 },
  ]);
});

test("مصروف بضريبة: شطر الضريبة على 1105 منفصلاً عن صافي المصروف", () => {
  const lines = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: "5203 كهرباء ومياه",
    amount: 580,
    taxAmount: 80,
    paymentMethod: "cash",
    cashAccountLabel: "1101 النقدية",
  });
  assert.deepEqual(lines, [
    { side: "Dr", label: "5203 كهرباء ومياه", amount: 500 },
    { side: "Dr", label: VAT_INPUT_LABEL, amount: 80 },
    { side: "Cr", label: "1101 النقدية", amount: 580 },
  ]);
});

test("الشيك يُدائن «شيكات برسم الدفع» لا الصندوق", () => {
  const lines = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: "5203 كهرباء ومياه",
    amount: 300,
    paymentMethod: "cheque",
  });
  assert.deepEqual(lines, [
    { side: "Dr", label: "5203 كهرباء ومياه", amount: 300 },
    { side: "Cr", label: CHEQUES_PAYABLE_LABEL, amount: 300 },
  ]);
});

test("على الحساب بلا مستفيد يُدائن «الدائنون» العام", () => {
  const lines = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: "5203 كهرباء ومياه",
    amount: 300,
    paymentMethod: "on_account",
  });
  assert.deepEqual(lines, [
    { side: "Dr", label: "5203 كهرباء ومياه", amount: 300 },
    { side: "Cr", label: TRADE_PAYABLES_LABEL, amount: 300 },
  ]);
});

test("على الحساب بمستفيد يُدائن اسم المستفيد لا الحساب العام", () => {
  const lines = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: "5203 كهرباء ومياه",
    amount: 300,
    paymentMethod: "on_account",
    beneficiaryLabel: "شركة الكهرباء",
  });
  assert.deepEqual(lines, [
    { side: "Dr", label: "5203 كهرباء ومياه", amount: 300 },
    { side: "Cr", label: "شركة الكهرباء", amount: 300 },
  ]);
});

test("الضريبة السالبة أو الأكبر من الإجمالي تُقصّ إلى [0, المبلغ]", () => {
  const negative = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: "مصروف", amount: 100, taxAmount: -10, paymentMethod: "cash",
  });
  assert.deepEqual(negative, [
    { side: "Dr", label: "مصروف", amount: 100 },
    { side: "Cr", label: "الصندوق / البنك", amount: 100 },
  ]);

  const overTax = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: "مصروف", amount: 100, taxAmount: 500, paymentMethod: "cash",
  });
  assert.deepEqual(overTax, [
    { side: "Dr", label: VAT_INPUT_LABEL, amount: 100 },
    { side: "Cr", label: "الصندوق / البنك", amount: 100 },
  ]);
});

test("بلا مبلغ موجب لا معاينة — فشلٌ نحو الفراغ لا نحو رقمٍ ملفَّق", () => {
  assert.deepEqual(
    buildExpenseVoucherEntryPreview({ expenseAccountLabel: "مصروف", amount: 0, paymentMethod: "cash" }),
    [],
  );
  assert.deepEqual(
    buildExpenseVoucherEntryPreview({ expenseAccountLabel: "مصروف", amount: -5, paymentMethod: "cash" }),
    [],
  );
});
