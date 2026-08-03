import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const membership = {
  id: 42,
  tenant: {
    TenantID: 42,
    CompanyName: "شركة الاختبار",
    SubscriptionPlan: "Enterprise",
    Status: "Active",
    CreatedAt: "2026-07-22T00:00:00Z",
    import_enabled: true,
    is_example: false,
  },
  role: "manager",
  is_default: true,
  created_at: "2026-07-22T00:00:00Z",
  can_access_import: true,
};

const companyDashboard = {
  period: { from: "2026-07-20", to: "2026-07-26" },
  is_new_company: false,
  financials: { revenue: 0, expenses: 0, net_profit: 0 },
  sales_invoices: { total: 0, posted: 0, draft: 0, recent: [] },
  purchase_invoices: { total: 0, posted: 0, draft: 0, recent: [] },
  inventory: {
    total_products: 0, in_stock: 0, low_stock: 0, out_of_stock: 0,
    inventory_value: 0, movements_this_month: 0, low_stock_items: [],
  },
  accounting: { journals_this_month: 0 },
  alerts: [],
};

const companyMembers = [
  {
    membership_id: 7, user_id: 70, username: "mgr", email: "mgr@example.test",
    full_name: "مدير الشركة", role: "manager", is_default: true,
    can_access_import: true, is_active: true, created_at: "2026-07-22T00:00:00Z",
  },
  {
    membership_id: 8, user_id: 80, username: "sami", email: "sami@example.test",
    full_name: "سامي", role: "staff", is_default: false,
    can_access_import: false, is_active: true, created_at: "2026-07-22T00:00:00Z",
  },
];

async function installMocks(page: Page, isSuperAdmin: boolean) {
  /** آخر أجسام الطلبات — تثبت أن أزرار اللوحة تصل الخادم فعلاً */
  const calls: Record<string, any> = {};
  const company = {
    id: 42, name: "شركة الاختبار", plan: "Enterprise", status: "Active",
    import_enabled: true, is_example: false, member_count: 2, created_at: "2026-07-22T00:00:00Z",
    members: companyMembers.map((member) => ({ ...member })),
  };

  await page.addInitScript(() => {
    localStorage.setItem("token", "platform-e2e-token");
    localStorage.setItem("userId", "platform-e2e-user");
    localStorage.setItem("tenantId", "42");
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.hostname === "api.smart.ktragroup.com" || url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/platform-e2e-user/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        id: "platform-e2e-user",
        name: isSuperAdmin ? "سوبر أدمن" : "مدير الشركة",
        role: "manager",
        email: isSuperAdmin ? "platform@example.test" : "manager@example.test",
        employmentStatus: "active",
        isApproved: true,
        isEmailVerified: true,
        isSuperAdmin,
      }) });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([membership]) });
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        role: "manager", is_manager: true, permissions: [],
      }) });
    }
    if (url.pathname.endsWith("/platform/dashboard/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        companies: { total: 3, active: 2, trial: 1, suspended: 0 },
        users: { total: 8, active: 7 },
        memberships: 10,
        status_distribution: { Active: 2, Trial: 1 },
        plan_distribution: { Enterprise: 3 },
        company_rows: [{
          id: 42, name: "شركة الاختبار", plan: "Enterprise", status: "Active",
          import_enabled: true, is_example: company.is_example,
          member_count: 4, created_at: "2026-07-22T00:00:00Z",
        }],
      }) });
    }
    if (/\/platform\/companies\/\d+\/members\/\d+\/$/.test(url.pathname)) {
      calls.memberPatch = request.postDataJSON?.() ?? JSON.parse(request.postData() || "{}");
      const member = company.members.find((row) => url.pathname.includes(`/${row.membership_id}/`));
      Object.assign(member!, calls.memberPatch);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(member) });
    }
    if (/\/platform\/companies\/\d+\/$/.test(url.pathname)) {
      if (request.method() === "PATCH") {
        calls.companyPatch = JSON.parse(request.postData() || "{}");
        Object.assign(company, calls.companyPatch);
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(company) });
    }
    if (/\/platform\/users\/\d+\/set-active\/$/.test(url.pathname)) {
      calls.setActive = { path: url.pathname, ...JSON.parse(request.postData() || "{}") };
      const member = company.members.find((row) => url.pathname.includes(`/${row.user_id}/`));
      member!.is_active = calls.setActive.is_active;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        id: member!.user_id, username: member!.username, is_active: member!.is_active,
      }) });
    }
    if (url.pathname.endsWith("/platform/development-notes/") && request.method() === "GET") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([{
        id: 1, title: "تحسين شاشة الجرد", description: "إضافة فلتر للمستودع",
        status: "in_progress", priority: "high", assignee: "فريق الواجهة",
        due_date: "2026-08-10", position: 0, created_by: 1,
        created_by_name: "سوبر أدمن", updated_by: 1, updated_by_name: "سوبر أدمن",
        created_at: "2026-08-01T10:00:00Z", updated_at: "2026-08-01T10:00:00Z",
      }]) });
    }
    if (url.pathname.endsWith("/platform/development-notes/") && request.method() === "POST") {
      const payload = request.postDataJSON();
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        id: 2, ...payload, created_by: 1, created_by_name: "سوبر أدمن",
        updated_by: 1, updated_by_name: "سوبر أدمن",
        created_at: "2026-08-01T11:00:00Z", updated_at: "2026-08-01T11:00:00Z",
      }) });
    }
    if (url.pathname.endsWith("/dashboard/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(companyDashboard) });
    }
    return route.fulfill({ contentType: "application/json", body: "[]" });
  });

  return calls;
}

test("super admin gets a separate platform dashboard and development notes sheet", async ({ page }) => {
  await installMocks(page, true);
  await page.goto("/super-admin");

  await expect(page.getByRole("heading", { name: "لوحة تحكم السوبر أدمن" })).toBeVisible();
  await expect(page.getByText("إجمالي الشركات")).toBeVisible();
  await expect(page.getByText("شركة الاختبار").last()).toBeVisible();
  await expect(page.getByRole("button", { name: "إدارة المنصة" })).toBeVisible();

  // سكرولر الصفحة لا يتجاوز الشاشة — كان min-height بـ 100vh يقصّ أسفل اللوحة
  // فلا تُرى آخر الشركات مهما سكرلت.
  const overflowBelowViewport = await page.evaluate(() => {
    const main = document.querySelector("main.app-content");
    return main ? main.getBoundingClientRect().bottom - window.innerHeight : null;
  });
  expect(overflowBelowViewport).not.toBeNull();
  expect(overflowBelowViewport as number).toBeLessThanOrEqual(1);

  await page.getByRole("button", { name: /ملاحظات التطوير/ }).first().click();
  await expect(page).toHaveURL(/\/super-admin\/development-notes$/);
  await expect(page.getByRole("heading", { name: "ملاحظات التطوير" })).toBeVisible();
  await expect(page.locator('input[value="تحسين شاشة الجرد"]')).toBeVisible();
  await page.getByLabel("عنوان ملاحظة جديدة").fill("إضافة تقرير هامش الربح");
  await page.getByRole("button", { name: "إضافة", exact: true }).click();
  await expect(page.locator('input[value="إضافة تقرير هامش الربح"]')).toBeVisible();
});

test("super admin controls a company and its members from the platform panel", async ({ page }) => {
  const calls = await installMocks(page, true);
  await page.goto("/super-admin");

  await page.getByRole("button", { name: "تحكم بـشركة الاختبار" }).click();
  await expect(page.getByRole("heading", { name: /تحكم المنصة بالشركة/ })).toBeVisible();

  // إعدادات الشركة: الحالة/الخطة/الاستيراد تُحفظ من هنا لا من نافذة المدير
  await page.getByLabel("حالة الشركة").selectOption("Suspended");
  await page.getByRole("button", { name: "حفظ" }).click();
  await expect.poll(() => calls.companyPatch?.status).toBe("Suspended");
  await expect(page.getByLabel("حالة الشركة")).toHaveValue("Suspended");

  // دور عضو
  await page.getByLabel("دور sami").selectOption("accountant");
  await expect.poll(() => calls.memberPatch?.role).toBe("accountant");

  // إيقاف حساب العضو — بتأكيد صريح
  await page.getByRole("button", { name: "إيقاف حساب sami" }).click();
  await page.getByRole("button", { name: "إيقاف الحساب" }).click();
  await expect.poll(() => calls.setActive?.is_active).toBe(false);
  await expect(page.getByRole("button", { name: "تفعيل حساب sami" })).toBeVisible();
});

test("super admin assigns the example company and sees its label", async ({ page }) => {
  const calls = await installMocks(page, true);
  await page.goto("/super-admin");

  await page.getByLabel("تعيين الشركة المثال").selectOption("42");

  await expect.poll(() => calls.companyPatch?.is_example).toBe(true);
  await expect(page.getByLabel("تعيين الشركة المثال")).toHaveValue("42");
  await expect(page.getByText("شركة الاختبار (مثال)", { exact: true })).toBeVisible();
});

test("company manager cannot see or open platform administration", async ({ page }) => {
  await installMocks(page, false);
  await page.goto("/super-admin");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText("إدارة المنصة")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "لوحة تحكم السوبر أدمن" })).toHaveCount(0);
  await expect(page.getByTestId("business-dashboard")).toBeVisible();
});
