import { expect, test } from "@playwright/test";
import { getPurchaseInvoiceFeeEditorState } from "../components/procurement/invoices/purchaseInvoiceFeeEditorState";

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
