import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

async function installAuthenticatedApiMocks(
  page: Page,
  onApi: (url: URL) => Promise<{ status?: number; body: unknown; delayMs?: number } | null>,
) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "e2e-token");
    localStorage.setItem("userId", "e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.hostname === "api.smart.ktragroup.com" || url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "e2e-user",
          name: "Direct Open Test User",
          role: "manager",
          email: "direct-open@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }
    const response = await onApi(url);
    if (response) {
      if (response.delayMs) await new Promise((resolve) => setTimeout(resolve, response.delayMs));
      await route.fulfill({
        status: response.status ?? 200,
        contentType: "application/json",
        body: JSON.stringify(response.body),
      });
      return;
    }
    if (url.pathname.includes("/mapper/activityStatus/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ id: "e2e-user", lastCheckIn: new Date().toISOString(), isCurrentlyActive: true }),
      });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

test("opening a deal directly fetches its detail once and skips the deal list", async ({ page }) => {
  let detailRequests = 0;
  let pagedListRequests = 0;
  await installAuthenticatedApiMocks(page, async (url) => {
    if (url.pathname.endsWith("/logistics/deals/42/")) {
      detailRequests += 1;
      return {
        body: {
          id: 42,
          ref_number: "D-42",
          status: "Open",
          order_date: "2026-07-16",
          total_amount: 100,
          remaining_amount: 100,
          items: [],
          payments: [],
        },
      };
    }
    if (url.pathname.endsWith("/logistics/deals/")) {
      if (url.searchParams.has("page")) pagedListRequests += 1;
      return { body: { count: 0, next: null, results: [] } };
    }
    return null;
  });

  await page.goto("/deals/42");
  await expect.poll(() => detailRequests).toBe(1);
  await page.waitForTimeout(500);
  expect(detailRequests).toBe(1);
  expect(pagedListRequests).toBe(0);
});

test("opening a purchase invoice directly does not wait for its list", async ({ page }) => {
  let detailRequests = 0;
  let listRequests = 0;
  let listResponsesFinished = 0;
  await installAuthenticatedApiMocks(page, async (url) => {
    if (url.pathname.endsWith("/logistics/purchase-invoices/42/")) {
      detailRequests += 1;
      return {
        body: {
          id: 42,
          invoice_number: "PI-42",
          partner: 7,
          partner_name: "Test Supplier",
          status: "draft",
          subtotal: 100,
          tax_rate: 0,
          tax_amount: 0,
          grand_total: 100,
          invoice_type: "local",
          items: [],
          fees: [],
        },
      };
    }
    if (url.pathname.endsWith("/logistics/purchase-invoices/")) {
      listRequests += 1;
      // InvoiceForm may load navigation records in the background; it must not gate detail.
      await new Promise((resolve) => setTimeout(resolve, 5_000));
      listResponsesFinished += 1;
      return { body: { count: 0, next: null, results: [] } };
    }
    return null;
  });

  await page.goto("/purchase-invoices/42");
  await expect.poll(() => detailRequests).toBe(1);
  await page.waitForTimeout(500);
  expect(listResponsesFinished).toBe(0);
  // One non-blocking navigation lookup remains inside InvoiceForm; the parent no longer duplicates it.
  expect(listRequests).toBeLessThanOrEqual(1);
});
