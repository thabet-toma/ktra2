import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * دفعة المخلّص أكبر من متبقّي التخليص المرحَّل: قبل الحفظ تنبيه «سيُفصل X كدفعة
 * تحت الحساب» بالمتبقّي من `accrual-status/` (المصدر الذي يفصل به الخادم)، والإلغاء
 * لا يرسل شيئاً، والتأكيد يرسل المبلغ كما كُتب ويذكر السند المفصول.
 */
test.use({ serviceWorkers: "block" });

type ApiResponder = (route: Route, url: URL) => Promise<boolean>;

async function installAuthenticatedApiMocks(page: Page, responder: ApiResponder) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "split-e2e-token");
    localStorage.setItem("userId", "split-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/split-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "split-e2e-user", name: "مدير", role: "manager", email: "m@example.test",
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
  id: 91, shipment_number: "SH-0013", shipment_name: "شحنة حاييم", shipment_date: "2026-06-01",
  shipping_type: "sea", editable: true, total_shipping_cost_usd: 0, total_volume: 0,
  total_weight_kg: 0, shipment_deal_allocations: [], payments: [],
};
const clearance = {
  id: 3, shipment: 91, shipment_number: "SH-0013", customs_broker: 83, broker_name: "حاييم",
  status: "Cleared", clearance_date: "2026-06-10", journal: 9001, is_posted: true,
  lines: [{ seq: 1, line_type: "broker_commission", description: "رسوم تخليص", debit: "7073.00", credit: "0" }],
};

async function openClearancePaymentForm(page: Page, posts: Array<Record<string, unknown>>) {
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/shipments/91/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(shipment) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/clearances/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([clearance]) });
      return true;
    }
    if (url.pathname.endsWith("/accounting/cash-box-accounts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 1, external_id: "box-ils", name: "صندوق شيكل", currency_code: "ILS",
          account: 10, is_active: true, is_default: true,
        }]),
      });
      return true;
    }
    if (url.pathname.endsWith("/logistics/supplier-payments/accrual-status/")) {
      expect(url.searchParams.get("kind")).toBe("clearance");
      expect(url.searchParams.get("id")).toBe("3");
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          kind: "clearance", id: 3, label: "تخليص #3 — SH-0013", accrual_posted: true,
          due: "7073.00", paid: "0.00", allocated: "0.00", remaining: "7073.00", overpaid: "0.00",
        }),
      });
      return true;
    }
    if (url.pathname.endsWith("/logistics/clearances/3/pay_from_cashbox/")) {
      posts.push(route.request().postDataJSON());
      await route.fulfill({
        status: 201, contentType: "application/json",
        body: JSON.stringify({
          status: "تم ترحيل الدفع بنجاح.", journal_id: 9100,
          payment: { id: 12, amount: "7073.00", payment_purpose: "clearance_fee", is_posted: true },
          on_account_voucher: { id: 50, amount: "2527.00" },
        }),
      });
      return true;
    }
    return false;
  });

  await page.goto("/import-flow/91");
  await page.getByText("الدفعات", { exact: true }).first().click();
  await page.getByRole("button", { name: "تسجيل دفعة للمخلّص" }).first().click();
  const amount = page.locator("label").filter({ hasText: "المبلغ (المتبقي" }).locator("input");
  await amount.fill("9600");
}

test("overpaying the broker warns how much becomes on-account, and cancel sends nothing", async ({ page }) => {
  const posts: Array<Record<string, unknown>> = [];
  await openClearancePaymentForm(page, posts);

  await page.getByRole("button", { name: "تأكيد دفعة المخلّص" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("سيُفصل 2,527");
  await expect(dialog).toContainText("كدفعة تحت الحساب");
  await dialog.getByRole("button", { name: "إلغاء" }).click();
  await expect(dialog).toHaveCount(0);
  expect(posts).toHaveLength(0);
});

test("confirming sends the full amount and reports the separated voucher", async ({ page }) => {
  const posts: Array<Record<string, unknown>> = [];
  await openClearancePaymentForm(page, posts);

  await page.getByRole("button", { name: "تأكيد دفعة المخلّص" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "سجّل وافصل الزائد" }).click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0]).toMatchObject({ amount: 9600, cash_box_external_id: "box-ils", payment_kind: "clearance" });
  await expect(page.getByText(/سند صرف #50 تحت الحساب/)).toBeVisible();
});
