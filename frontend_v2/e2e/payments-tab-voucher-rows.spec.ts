import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * تبويب «الدفعات» يعرض سندات الصرف الموزَّعة بجانب الدفعات المباشرة، والشحنة
 * تُعرف باسمها لا برقمها وحده. إنتاج: سند #2459 وُزِّع 2,045 على تخليص SH-0017 فكان
 * التبويب فارغاً تحت رأسٍ يقول «مدفوع»، والعنوان «شحنة #SH-0017».
 */
test.use({ serviceWorkers: "block" });

type ApiResponder = (route: Route, url: URL) => Promise<boolean>;

async function installAuthenticatedApiMocks(page: Page, responder: ApiResponder) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "vrows-e2e-token");
    localStorage.setItem("userId", "vrows-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/vrows-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "vrows-e2e-user", name: "مدير", role: "manager", email: "m@example.test",
          employmentStatus: "active", isApproved: true, isEmailVerified: true,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager", is_manager: true, modules: {}, ui_mode: "advanced",
          permissions: ["import.deal.manage", "import.shipment.manage"],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 1,
          tenant: {
            TenantID: 1, CompanyName: "شركة الاختبار", SubscriptionPlan: "basic",
            Status: "active", CreatedAt: "2026-01-01T00:00:00Z", import_enabled: true,
          },
          role: "manager", is_default: true, created_at: "2026-01-01T00:00:00Z",
          can_access_import: true,
        }]),
      });
      return;
    }
    if (await responder(route, url)) return;
    if (url.pathname.endsWith("/shipment-cost-drift/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ posted_count: 0, stale_posted_invoices: [] }),
      });
      return;
    }
    if (url.pathname.includes("/mapper/activityStatus/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ isCurrentlyActive: true }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

const shipment = {
  id: 91, shipment_number: "SH-0017", shipment_name: "", shipment_label: "SH-0017 — شحنة رقع",
  shipment_date: "2026-06-01", shipping_type: "sea", editable: true, total_shipping_cost_usd: 1000,
  total_volume: 0, total_weight_kg: 0, shipping_agent: 35, agent_name: "yoyo", freight_is_posted: true,
  freight_exchange_rate: "3.600000", shipment_deal_allocations: [], payments: [],
  freight_voucher_rows: [{
    id: "alloc-7", row_type: "voucher_allocation", voucher_id: 2460, kind_label: "سند صرف — توزيع",
    payment_date: "2026-08-01", amount: "200.00", journal: 9310, shipment_label: "SH-0017 — شحنة رقع",
  }],
};
const clearance = {
  id: 13, shipment: 91, shipment_number: "SH-0017", shipment_label: "SH-0017 — شحنة رقع",
  customs_broker: 83, broker_name: "حاييم", status: "Cleared", clearance_date: "2026-06-10",
  journal: 9001, is_posted: true, amount_paid: "2045.00", remaining_balance: "0.00", advance_balance: "0.00",
  payment_status: "paid",
  lines: [{ seq: 1, line_type: "broker_commission", description: "رسوم تخليص", debit: "2045.00", credit: "0" }],
};

test("the payments tab lists the allocated vouchers and the shipment reads by its name", async ({ page }) => {
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/shipments/91/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(shipment) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/clearances/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([clearance]) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/clearances/13/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(clearance) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/clearances/13/payments/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: "alloc-5", row_type: "voucher_allocation", voucher_id: 2459, kind_label: "سند صرف — توزيع",
          payment_purpose: "clearance", payment_date: "2026-08-01", amount: "2045.00", is_posted: true,
          journal: 9302, shipment_label: "SH-0017 — شحنة رقع",
        }]),
      });
      return true;
    }
    return false;
  });

  await page.goto("/import-flow/91");
  await expect(page.getByText("رحلة الاستيراد — SH-0017 — شحنة رقع").first()).toBeVisible();
  await page.getByText("الدفعات", { exact: true }).first().click();

  // دفعات المخلّص: السند الموزَّع صفٌّ برقمه ومبلغه، والمجموع = المدفوع في الرأس.
  await expect(page.getByRole("heading", { name: "دفعات المخلّص (1)" })).toBeVisible();
  const clearanceRow = page.getByRole("row").filter({ hasText: "#2459" });
  await expect(clearanceRow).toContainText("سند صرف — توزيع");
  await expect(clearanceRow).toContainText("2,045");
  await expect(page.getByText("المدفوع:").locator("b")).toHaveText("2,045 ₪");

  // دفعات الوكيل: سند صرف الوكيل الموزَّع على استحقاق الشحن بالدولار.
  await expect(page.getByRole("heading", { name: "دفعات وكيل الشحن — الشحن الدولي بالدولار (1)" })).toBeVisible();
  const agentRow = page.getByRole("row").filter({ hasText: "#2460" });
  await expect(agentRow).toContainText("سند صرف — توزيع");
  await expect(agentRow).toContainText("200");
  await expect(agentRow).toContainText("#9310");
});
