import { expect, test } from "@playwright/test";
import { getPurchaseInvoiceFeeEditorState } from "../components/procurement/invoices/purchaseInvoiceFeeEditorState";
import {
  allocateInvoiceFinalCosts,
  invoiceGrandTotalIls,
  invoiceVatBaseIls,
  purchaseInvoiceFeeAmount,
} from "../utils/invoiceTaxesAndFees";
import {
  getPurchaseInvoiceCostLabels,
  mergeClearanceImportDeals,
} from "../utils/invoiceConversionUtils";

test.describe("Purchase invoice tax and fee editor", () => {
  test("allows a saved draft to enter edit mode and add a line directly", () => {
    expect(getPurchaseInvoiceFeeEditorState({
      readOnly: false,
      viewMode: true,
      isPosted: false,
      isHistorical: false,
    })).toEqual({
      canAdd: true,
      requiresEdit: true,
      message: null,
    });
  });

  test("allows direct addition while already editing", () => {
    expect(getPurchaseInvoiceFeeEditorState({
      readOnly: false,
      viewMode: false,
      isPosted: false,
      isHistorical: false,
    }).requiresEdit).toBe(false);
  });

  test("explains why a posted invoice cannot accept another line", () => {
    const state = getPurchaseInvoiceFeeEditorState({
      readOnly: false,
      viewMode: true,
      isPosted: true,
      isHistorical: false,
    });

    expect(state.canAdd).toBe(false);
    expect(state.message).toContain("تراجع عن الترحيل");
  });
});

test.describe("Imported invoice VAT totals", () => {
  test("does not add landed allocations twice when item totals already include them", () => {
    const metadata = {
      allocation_method: "server_pro_rata",
      line_meta: {
        deal_ship_allocated_ils: 20,
        deal_transfer_commissions_ils: 5,
        deal_local_shipping_from_clearance_ils: 10,
      },
    };
    const localPayments = {
      includedInPrice: false,
      calculationMethod: "detailed" as const,
      customsClearanceFees: 15,
      customsDuties: 10,
      portFees: 5,
      palestinianTaxCustoms: 0,
      internalShippingFees: 10,
    };

    expect(invoiceVatBaseIls(100, metadata, localPayments)).toBe(105);
    expect(invoiceGrandTotalIls(100, 16.8, metadata, localPayments)).toBeCloseTo(121.8);
  });

  test("keeps the legacy calculation when item totals do not embed landed allocations", () => {
    const metadata = {
      line_meta: {
        deal_ship_allocated_ils: 20,
        deal_transfer_commissions_ils: 5,
        deal_local_shipping_from_clearance_ils: 10,
      },
    };
    const localPayments = {
      includedInPrice: false,
      calculationMethod: "detailed" as const,
      customsClearanceFees: 15,
      customsDuties: 10,
      portFees: 5,
      palestinianTaxCustoms: 0,
      internalShippingFees: 10,
    };

    expect(invoiceVatBaseIls(100, metadata, localPayments)).toBe(165);
  });
});

test("uses authoritative clearance options when shipment detail has no deals", () => {
  expect(mergeClearanceImportDeals([], [{
    deal_id: 42,
    deal_ref: "D-0042",
    is_converted: false,
    invoice_id: null,
    invoice_number: null,
  }])).toEqual([expect.objectContaining({
    dealId: "42",
    dealNumber: "D-0042",
  })]);
});

test("calculates a percentage fee on goods or after main VAT", () => {
  const fee = {
    description: "رسم كترا",
    amount: 0,
    calculationType: "percentage" as const,
    calculationValue: 10,
    percentageBasis: "goods" as const,
    expenseAccountId: 1,
    capitalizeToInventory: false,
    isTaxable: false,
  };

  expect(purchaseInvoiceFeeAmount(fee, 1000, 1200, 192)).toBe(100);
  expect(purchaseInvoiceFeeAmount(
    { ...fee, percentageBasis: "after_main_vat" },
    1000,
    1200,
    192,
  )).toBe(139.2);
});

test("labels shipment-linked item prices as import-inclusive costs", () => {
  expect(getPurchaseInvoiceCostLabels(true)).toEqual({
    unitPrice: "تكلفة الوحدة الشاملة للاستيراد",
    lineTotal: "إجمالي السطر الشامل للاستيراد",
    merchandiseBase: "قيمة البضاعة قبل تكاليف الاستيراد",
  });
});

test("keeps ordinary purchase invoice price labels unchanged", () => {
  expect(getPurchaseInvoiceCostLabels(false)).toEqual({
    unitPrice: "سعر الوحدة",
    lineTotal: "الإجمالي",
    merchandiseBase: "سعر الأساس (المنتجات)",
  });
});

test("distributes VAT and added fees into the final unit cost without changing the base", () => {
  const items = [
    { quantity: 10, totalPrice: 100, landedLineTotalIls: 100 },
    { quantity: 20, totalPrice: 300, landedLineTotalIls: 300 },
  ];

  const allocated = allocateInvoiceFinalCosts(items, {
    transferTotalIls: 0,
    taxAndFeesTotalIls: 104,
  });

  expect(allocated.map((row) => row.finalUnit)).toEqual([12.6, 18.9]);
  expect(allocated.reduce((sum, row) => sum + row.finalLine, 0)).toBe(504);
  expect(items.map((row) => row.totalPrice)).toEqual([100, 300]);
});
