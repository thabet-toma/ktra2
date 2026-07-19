import { expect, test } from "@playwright/test";
import {
  getImportJourneyGuidance,
  getMissingDealMeasureRefs,
} from "../components/import-flow/importJourneyGuidance";

const ready = {
  shipmentSaved: true,
  invoiceEligible: true,
  dealsCount: 1,
  freightTotalUsd: 100,
  freightCostEstablished: true,
  clearanceExists: true,
  clearanceCostTotal: 50,
  convertedInvoiceId: null,
  remainingDealsCount: 1,
};

test.describe("Import journey guidance", () => {
  test("returns one clear next action for every required stage", () => {
    expect(getImportJourneyGuidance({ ...ready, shipmentSaved: false }).action).toBe("save_shipment");
    expect(getImportJourneyGuidance({ ...ready, dealsCount: 0 }).action).toBe("link_deals");
    expect(getImportJourneyGuidance({ ...ready, freightCostEstablished: false }).action).toBe("pay_freight");
    expect(getImportJourneyGuidance({ ...ready, clearanceExists: false }).action).toBe("create_clearance");
    expect(getImportJourneyGuidance({ ...ready, clearanceCostTotal: 0 }).action).toBe("enter_clearance_costs");
    expect(getImportJourneyGuidance(ready).action).toBe("create_invoice");
  });

  test("does not make local transport or clearance payment invoice prerequisites", () => {
    const guidance = getImportJourneyGuidance(ready);

    expect(guidance.action).toBe("create_invoice");
    expect(guidance.description).toContain("لا يشترط");
  });

  test("opens the existing invoice when the journey is complete", () => {
    expect(getImportJourneyGuidance({ ...ready, convertedInvoiceId: 42, remainingDealsCount: 0 }).action).toBe("view_invoice");
  });

  test("keeps the import action when another deal is not converted", () => {
    const guidance = getImportJourneyGuidance({ ...ready, convertedInvoiceId: 42, remainingDealsCount: 1 });
    expect(guidance.action).toBe("create_invoice");
    expect(guidance.actionLabel).toContain("المتبقية (1)");
  });

  test("routes transport-only shipments to local transport instead of an invoice", () => {
    expect(getImportJourneyGuidance({ ...ready, invoiceEligible: false }).action).toBe("manage_local_transport");
  });

  test("a zero-cost freight shipment is import-ready without any payment", () => {
    // كان الشحن الصفري يوقف الرحلة فيُضطر المستخدم لدفعة وهمية 0.01.
    const guidance = getImportJourneyGuidance({
      ...ready, freightTotalUsd: 0, freightCostEstablished: true,
    });
    expect(guidance.action).toBe("create_invoice");
  });

  test("identifies deals that need the selected freight measure before allocation", () => {
    const allocations = [
      { deal_ref: "D-0108", deal_total_cbm: 2, deal_total_weight_kg: 0 },
      { deal_ref: "D-0109", deal_total_cbm: 0, deal_total_weight_kg: 40 },
    ];

    expect(getMissingDealMeasureRefs(allocations, "cbm")).toEqual(["D-0109"]);
    expect(getMissingDealMeasureRefs(allocations, "kg")).toEqual(["D-0108"]);
  });
});
