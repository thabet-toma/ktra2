import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

async function installAppMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "print-layout-token");
    localStorage.setItem("userId", "print-layout-user");
    localStorage.setItem("tenantId", "1");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/print-layout-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "print-layout-user",
          name: "مدير الطباعة",
          role: "manager",
          email: "print@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
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
            TenantID: 1,
            CompanyName: "KTRA",
            SubscriptionPlan: "Enterprise",
            Status: "Active",
            CreatedAt: "2026-07-23T00:00:00Z",
            import_enabled: true,
          },
          role: "manager",
          is_default: true,
          created_at: "2026-07-23T00:00:00Z",
          can_access_import: true,
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          next: null,
          previous: null,
          results: [{
            id: 145,
            invoice_number: "SI-6-145",
            invoice_date: "2026-07-22",
            customer: 8,
            customer_name: "عميل الاختبار",
            invoice_type: "credit",
            status: "posted",
            grand_total: "880.00",
            amount_paid: "0.00",
          }],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/dashboard/")) {
      await route.fulfill({ contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

test("print media keeps the invoice content and removes the app chrome", async ({ page }) => {
  await installAppMocks(page);
  await page.goto("/sales/invoices");
  await expect(page.getByText("فواتير المبيعات", { exact: true }).last()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("العمل يتم عبر قاعدة SQL", { exact: true })).toHaveCount(0);

  const titlebars = page.locator(".aseel-titlebar");
  await expect(titlebars).toHaveCount(2);
  await expect(titlebars.first()).toBeVisible();
  await expect(titlebars.last()).toBeVisible();
  await expect(page.locator("aside").last()).toBeVisible();
  const screenOnlyCells = page.locator(".aseel-grid .aseel-print-hidden");
  const screenOnlyFilters = page.locator(".aseel-headband .aseel-print-hidden");
  await expect(screenOnlyCells.first()).toBeVisible();
  await expect(screenOnlyFilters).toBeVisible();

  await page.emulateMedia({ media: "print" });

  await expect(titlebars.first()).toBeHidden();
  await expect(titlebars.last()).toBeVisible();
  await expect(page.locator("aside").last()).toBeHidden();
  await expect(screenOnlyCells.first()).toBeHidden();
  await expect(screenOnlyFilters).toBeHidden();
  await expect(page.locator("main.app-content")).toHaveCSS("overflow-y", "visible");
  await expect(page.locator(".aseel-grid")).toBeVisible();
});

test("invoice filters use the localized date control instead of the browser date placeholder", async ({ page }) => {
  await installAppMocks(page);
  await page.goto("/sales/invoices");
  await expect(page.getByText("فواتير المبيعات", { exact: true }).last()).toBeVisible({ timeout: 15_000 });

  for (const label of ["من تاريخ", "إلى تاريخ"]) {
    const input = page.getByText(label, { exact: true }).locator("..").locator("input");
    await expect(input).toHaveAttribute("type", "text");
    await expect(input).toHaveAttribute("placeholder", "يوم/شهر/سنة");
  }

  await page.goto("/purchase-invoices");
  await expect(page.getByText("فواتير الشراء", { exact: true }).last()).toBeVisible({ timeout: 15_000 });

  for (const label of ["من تاريخ", "إلى تاريخ"]) {
    const input = page.getByText(label, { exact: true }).locator("..").locator("input");
    await expect(input).toHaveAttribute("type", "text");
    await expect(input).toHaveAttribute("placeholder", "يوم/شهر/سنة");
  }
});

test("import is a top-level navigation group instead of living under inventory", async ({ page }) => {
  await installAppMocks(page);
  await page.goto("/dashboard");

  await expect(page.getByRole("button", { name: "المخزون", exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "أرصدة المخزون", exact: true })).toHaveCount(0);
  const importButton = page.getByRole("button", { name: "الاستيراد", exact: true });
  await expect(importButton).toBeVisible();
});
