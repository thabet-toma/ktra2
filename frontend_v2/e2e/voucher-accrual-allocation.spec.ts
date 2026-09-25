import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * سند صرف المخلّص يُوزَّع على تخليصاته: المنتقي يعرض مستحقّاته اللوجستية مع
 * فواتير الشراء، و«توزيع تلقائي» يملأ من الأقدم، والحفظ يذهب إلى
 * `allocate-accruals/` لا إلى توزيع الفواتير.
 */
test.use({ serviceWorkers: "block" });

type ApiResponder = (route: Route, url: URL) => Promise<boolean>;

async function installAuthenticatedApiMocks(page: Page, responder: ApiResponder) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "alloc-e2e-token");
    localStorage.setItem("userId", "alloc-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/alloc-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "alloc-e2e-user", name: "مدير", role: "manager", email: "m@example.test",
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
          permissions: ["purchase.supplier.view", "sales.customer.view", "purchase.payment.post"],
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
    if (url.pathname.includes("/mapper/activityStatus/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ isCurrentlyActive: true }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

const voucher = {
  id: 501, partner: 83, partner_name: "حاييم", payment_date: "2026-08-01",
  amount: "2527.00", unallocated_amount: "2527.00", allocated_amount: "0.00",
  is_posted: true, currency_code: "ILS", allocations: [], logistics_allocations: [],
};

test("broker voucher allocates FIFO onto his clearances", async ({ page }) => {
  const posted: Array<{ path: string; body: unknown }> = [];
  await installAuthenticatedApiMocks(page, async (route, url) => {
    const method = route.request().method();
    if (url.pathname.endsWith("/logistics/supplier-payments/logistics-accruals/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ accruals: [
          { kind: "clearance", id: 5, label: "تخليص #5", date: "2026-07-10", due: "4000", paid: "0", allocated: "0", remaining: "4000.00", overpaid: "0" },
          { kind: "clearance", id: 3, label: "تخليص #3 — SH-0013", date: "2026-06-10", due: "7073", paid: "5000", allocated: "0", remaining: "2073.00", overpaid: "0" },
        ] }),
      });
      return true;
    }
    if (url.pathname.endsWith("/logistics/supplier-payments/501/allocate-accruals/") && method === "POST") {
      posted.push({ path: url.pathname, body: route.request().postDataJSON() });
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...voucher, unallocated_amount: "0.00" }) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/supplier-payments/501/allocate/")) {
      posted.push({ path: url.pathname, body: route.request().postDataJSON() });
      await route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: "wrong endpoint" }) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/supplier-payments/") && method === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ count: 1, results: [voucher] }) });
      return true;
    }
    return false;
  });

  await page.goto("/supplier-payments");
  await page.getByTitle("توزيع على المستندات (فواتير ومستحقّات)").first().click({ timeout: 15000 });
  await expect(page.getByText("توزيع سند #501 — حاييم")).toBeVisible();
  const picker = page.locator("select").filter({ hasText: "اختر مستنداً" });
  const options = await picker.locator("option").allTextContents();
  expect(options.some((o) => o.includes("تخليص #3 — SH-0013"))).toBe(true);

  await page.getByRole("button", { name: /توزيع تلقائي/ }).click();
  const rows = page.locator("table tbody tr").filter({ hasText: "تخليص #" });
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("تخليص #3 — SH-0013");
  await expect(rows.nth(0).locator("input")).toHaveValue("2073.00");
  await expect(rows.nth(1).locator("input")).toHaveValue("454.00");

  await page.getByRole("button", { name: "توزيع", exact: true }).click();
  await expect.poll(() => posted.length).toBe(1);
  expect(posted[0]).toEqual({
    path: expect.stringContaining("/allocate-accruals/"),
    body: { allocations: [
      { kind: "clearance", id: 3, amount: "2073.00" },
      { kind: "clearance", id: 5, amount: "454.00" },
    ] },
  });
});
