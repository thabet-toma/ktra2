import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * دفعة وكيل الشحن بكبسة واحدة كالمخلّص والناقل: «دفع للوكيل» يرسل إلى
 * `pay_agent_from_cashbox/` (إنشاء + ترحيل معاً) من صندوقٍ بالدولار افتراضياً، ولا
 * PATCH لقائمة الدفعات بعد الآن، ورقم القيد يظهر في جدول الدفعات.
 */
test.use({ serviceWorkers: "block" });

type ApiResponder = (route: Route, url: URL) => Promise<boolean>;

async function installAuthenticatedApiMocks(page: Page, responder: ApiResponder) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "agent-e2e-token");
    localStorage.setItem("userId", "agent-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/agent-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "agent-e2e-user", name: "مدير", role: "manager", email: "m@example.test",
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

const shipment = (payments: unknown[]) => ({
  id: 91, shipment_number: "S-0011", shipment_name: "شحنة yoyo", shipment_date: "2026-06-01",
  shipping_type: "sea", editable: true, total_shipping_cost_usd: 1000, total_volume: 0,
  total_weight_kg: 0, shipping_agent: 35, agent_name: "yoyo", shipment_deal_allocations: [], payments,
});

test("paying the agent posts in one click from the USD box and shows the journal number", async ({ page }) => {
  const posts: Array<Record<string, unknown>> = [];
  let patches = 0;
  let paid = false;
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/shipments/91/")) {
      if (route.request().method() === "PATCH") patches += 1;
      const payments = paid ? [{
        id: 190, payment_number: 1, title: "دفعة شحن 1", amount: "500.00", usd_to_ils: "3.240000",
        transfer_date: "2026-07-05", status: "Confirmed", confirmed_by_supplier: true,
        cash_box_external_id: "usd-box", is_posted: true, journal: 9200,
      }] : [];
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(shipment(payments)) });
      return true;
    }
    if (url.pathname.endsWith("/accounting/cash-box-accounts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          { id: 1, external_id: "1B0001", name: "صندوق شيكل", currency_code: "ILS", account: 10, is_active: true, is_default: true },
          { id: 2, external_id: "usd-box", name: "صندوق دولار", currency_code: "USD", account: 11, is_active: true, is_default: false },
        ]),
      });
      return true;
    }
    if (url.pathname.endsWith("/logistics/shipments/91/pay_agent_from_cashbox/")) {
      posts.push(route.request().postDataJSON());
      paid = true;
      await route.fulfill({
        status: 201, contentType: "application/json",
        body: JSON.stringify({ status: "تم", journal_id: 9200, payment: { id: 190, journal: 9200 } }),
      });
      return true;
    }
    if (url.pathname.endsWith("/recalculate-landed-cost/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ updated: 0 }) });
      return true;
    }
    return false;
  });

  await page.goto("/import-flow/91");
  await page.getByText("الدفعات", { exact: true }).first().click();
  await page.getByRole("button", { name: "دفعة شحن دولي" }).click();
  const box = page.locator("label").filter({ hasText: "الصندوق" }).locator("select").first();
  await expect(box).toHaveValue("usd-box");
  await expect(page.getByText("مؤكّدة (دُفعت فعلاً)")).toHaveCount(0);
  await page.locator("label").filter({ hasText: "المبلغ (USD)" }).locator("input").fill("500");
  await page.locator("label").filter({ hasText: "سعر الصرف (₪/$)" }).locator("input").last().fill("3.24");
  await page.getByRole("button", { name: "دفع للوكيل" }).click();

  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0]).toMatchObject({ amount: 500, usd_to_ils: 3.24, cash_box_external_id: "usd-box" });
  await expect(page.getByRole("cell", { name: "#9200" })).toBeVisible();
  expect(patches).toBe(0);
});
