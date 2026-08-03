import assert from "node:assert/strict";
import test from "node:test";
import { buildPartnerChequeDefaults, selectPartnerBankAccount } from "./partnerChequeDefaults.ts";

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
