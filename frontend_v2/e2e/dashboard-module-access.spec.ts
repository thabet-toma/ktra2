import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const profile = {
  id: "dashboard-user",
  name: "مدير الشركة",
  role: "manager",
  email: "dashboard@example.test",
  employmentStatus: "active",
  isApproved: true,
  isEmailVerified: true,
};

const dashboard = {
  period: { from: "2026-07-20", to: "2026-07-26" },
  is_new_company: false,
  financials: { revenue: 12000, expenses: 4500, net_profit: 7500 },
  sales_invoices: { total: 3, posted: 2, draft: 1, recent: [] },
  purchase_invoices: { total: 2, posted: 2, draft: 0, recent: [] },
  inventory: {
    total_products: 4,
    in_stock: 3,
    low_stock: 0,
    out_of_stock: 0,
    inventory_value: 8100,
    movements_this_month: 2,
    low_stock_items: [],
  },
  accounting: { journals_this_month: 5 },
  alerts: [],
};

async function mockCompany(page: Page, importEnabled: boolean) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "dashboard-token");
    localStorage.setItem("userId", "dashboard-user");
    localStorage.setItem("tenantId", "42");
  });
  const membership = {
    id: 42,
    tenant: {
      TenantID: 42,
      CompanyName: "شركة الاختبار",
      SubscriptionPlan: "Enterprise",
      Status: "Active",
      CreatedAt: "2026-07-22T00:00:00Z",
      import_enabled: importEnabled,
    },
    role: "manager",
    is_default: true,
    created_at: "2026-07-22T00:00:00Z",
    can_access_import: importEnabled,
  };

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    if (url.pathname.endsWith("/hr/users/dashboard-user/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(profile) });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([membership]) });
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager",
          is_manager: true,
          permissions: [],
        }),
      });
    }
    if (url.pathname.endsWith("/dashboard/")) {
      const payload = importEnabled
        ? {
            ...dashboard,
            import_operations: {
              deals: { open: 2, active_value: 1000, status_distribution: [] },
              shipments: { in_transit: 1, clearing: 1 },
              payments: { paid_this_month: 100 },
            },
          }
        : dashboard;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) });
    }
    return route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

test("company without import sees the business dashboard and import deep links are blocked", async ({ page }) => {
  await mockCompany(page, false);
  await page.goto("/deals/123");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByTestId("business-dashboard")).toBeVisible();
  await expect(page.getByText("إيرادات الفترة")).toBeVisible();
  await expect(page.getByText("مصروفات الفترة")).toBeVisible();
  const periodSummary = page.getByText(/المؤشرات المالية والمبيعات والمشتريات من/);
  await expect(periodSummary).toContainText("إلى");
  await expect(periodSummary).toContainText("20/07/2026");
  await expect(page.getByText("صافي الربح")).toBeVisible();
  await expect(page.getByTestId("import-overview")).toHaveCount(0);

  await page.getByRole("button", { name: "بحث سريع" }).click();
  await expect(page.getByRole("button", { name: "فواتير المبيعات" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "الصفقات" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "الشحنات" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "التخليص" })).toHaveCount(0);
});

test("company with import permission sees the compact import overview", async ({ page }) => {
  await mockCompany(page, true);
  await page.goto("/dashboard");
  await expect(page.getByTestId("import-overview")).toBeVisible();
  await expect(page.getByText("صفقات مفتوحة")).toBeVisible();
  await expect(page.getByText("شحنات في الطريق")).toBeVisible();
  await expect(page.getByText("شحنات قيد التخليص")).toBeVisible();
});
