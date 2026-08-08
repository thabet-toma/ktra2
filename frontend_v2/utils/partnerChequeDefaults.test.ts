import assert from "node:assert/strict";
import test from "node:test";
import {
  applyBlankDefaults,
  buildPartnerChequeDefaults,
  selectPartnerBankAccount,
  validateChequeLines,
} from "./partnerChequeDefaults.ts";

const partner = {
  id: 7,
  name: "الزبون",
  legal_name: "شركة الزبون",
};

const banks = [
  {
    id: 1,
    bank_name: "بنك قديم",
    account_number: "111",
    branch_name: "نابلس",
    beneficiary_name: "",
    currency: 2,
    is_active: true,
    is_default: false,
  },
  {
    id: 2,
    bank_name: "بنك فلسطين",
    account_number: "0012300456",
    branch_name: "رام الله",
    beneficiary_name: "شركة الزبون",
    currency: 1,
    is_active: true,
    is_default: true,
  },
];

test("selects the active default account matching the voucher currency", () => {
  assert.equal(selectPartnerBankAccount(banks, 1)?.id, 2);
});

test("incoming cheque receives customer bank snapshots", () => {
  assert.deepEqual(buildPartnerChequeDefaults(partner, banks[1], "Incoming"), {
    bank_name: "بنك فلسطين",
    account_number: "0012300456",
    branch: "رام الله",
    payee_name: "شركة الزبون",
  });
});

test("outgoing cheque never uses the supplier bank as our cheque account", () => {
  assert.deepEqual(buildPartnerChequeDefaults(partner, banks[1], "Outgoing"), {
    payee_name: "شركة الزبون",
  });
});

test("outgoing cheque is drawn on our own bank account", () => {
  const own = { bank_name: "بنك القدس", account_number: "9988", branch_name: "البيرة" };
  assert.deepEqual(
    buildPartnerChequeDefaults(partner, banks[1], "Outgoing", own),
    {
      bank_name: "بنك القدس",
      account_number: "9988",
      branch: "البيرة",
      payee_name: "شركة الزبون",
    },
  );
});

// T-CHQ3/هـ — التعبئة التلقائية تصل بعد نداء بطاقة الطرف، فالسطر المُضاف قبلها
// يجب أن يُملأ لاحقاً بلا أن يُدهس ما كتبه المستخدم.
const blankLine = {
  cheque_number: "",
  payee_name: "",
  due_date: "",
  amount: "",
  bank_name: "",
  branch: "",
  account_number: "",
};

const lineDefaults = {
  payee_name: "شركة الزبون",
  bank_name: "بنك فلسطين",
  account_number: "0012300456",
  branch: "رام الله",
};

test("fills the empty fields of a line that was added before the defaults arrived", () => {
  assert.deepEqual(applyBlankDefaults(blankLine, lineDefaults), {
    ...blankLine,
    ...lineDefaults,
  });
});

test("never overwrites what the user typed", () => {
  const typed = { ...blankLine, payee_name: "فادي", bank_name: "بنك القدس" };
  assert.deepEqual(applyBlankDefaults(typed, lineDefaults), {
    ...typed,
    account_number: "0012300456",
    branch: "رام الله",
  });
});

test("returns the same line reference when nothing changes", () => {
  const full = { ...blankLine, ...lineDefaults };
  assert.equal(applyBlankDefaults(full, lineDefaults), full);
});

test("ignores empty defaults", () => {
  assert.equal(applyBlankDefaults(blankLine, { payee_name: "" }), blankLine);
});

// T-CHQ3/ط — شرط تاريخ الاستحقاق: الخادم يرفضه، والواجهة تقوله قبل الإرسال
// وتسمّي السطر الناقص.
test("a cheque line without a due date is rejected by name of its row", () => {
  const error = validateChequeLines([
    { cheque_number: "1", amount: "50", due_date: "2026-09-01" },
    { cheque_number: "2", amount: "50", due_date: "" },
  ]);
  assert.match(String(error), /الشيك #2/);
  assert.match(String(error), /تاريخ الاستحقاق/);
});

test("a cheque line without a number or a positive amount is rejected first", () => {
  assert.match(
    String(validateChequeLines([{ cheque_number: " ", amount: "50", due_date: "2026-09-01" }])),
    /رقم الشيك/,
  );
  assert.match(
    String(validateChequeLines([{ cheque_number: "1", amount: "0", due_date: "2026-09-01" }])),
    /المبلغ/,
  );
});

test("complete cheque lines pass, and no lines at all is fine", () => {
  assert.equal(
    validateChequeLines([{ cheque_number: "1", amount: "50", due_date: "2026-09-01" }]),
    null,
  );
  assert.equal(validateChequeLines([]), null);
});
