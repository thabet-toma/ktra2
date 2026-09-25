import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * صفحة الأطراف الدائنة (`/suppliers`): أصنافٌ متعدّدة الاختيار تُطلب من الخادم
 * بعدّاد لكل صنف ويُحفظ اختيارها، «جديد» يسأل عن الصنف أولاً، «فتح البطاقة»
 * ظاهر لكل صف، وتصنيفٌ جماعي للموردين.
 */
test.use({ serviceWorkers: "block" });

type ApiResponder = (route: Route, url: URL) => Promise<boolean>;

async function installAuthenticatedApiMocks(page: Page, responder: ApiResponder) {
  await page.addInitScript(() => {
    // مرّة واحدة لكل تبويب — إعادة التحميل تُبقي اختيار الأصناف المحفوظ.
    if (sessionStorage.getItem("kinds-e2e-init")) return;
    localStorage.clear();
    sessionStorage.clear();
    sessionStorage.setItem("kinds-e2e-init", "1");
    localStorage.setItem("token", "kinds-e2e-token");
    localStorage.setItem("userId", "kinds-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/kinds-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "kinds-e2e-user", name: "مدير", role: "manager", email: "m@example.test",
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

const ROWS = [
  { id: 1, name: "مورد محلي", partner_type: "Supplier", supplier_scope: "local" },
  { id: 2, name: "مورد بلا تصنيف", partner_type: "Supplier", supplier_scope: "" },
  { id: 83, name: "حاييم", partner_type: "CustomsBroker", supplier_scope: "" },
  { id: 84, name: "اسامه", partner_type: "Carrier", supplier_scope: "" },
];
const KIND_OF: Record<number, string> = {
  1: "supplier_local", 2: "supplier_unscoped", 83: "CustomsBroker", 84: "Carrier",
};

function suppliersResponder(seen: { kinds: string[]; bulk: unknown[] }): ApiResponder {
  return async (route, url) => {
    if (url.pathname.endsWith("/partners/kind-counts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          supplier_local: 1, supplier_international: 0, supplier_unscoped: 1,
          FreightForwarder: 0, CustomsBroker: 1, LocalTransporter: 0, Carrier: 1,
        }),
      });
      return true;
    }
    if (url.pathname.endsWith("/partners/bulk-scope/")) {
      seen.bulk.push(route.request().postDataJSON());
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ updated: 1 }) });
      return true;
    }
    if (url.pathname.endsWith("/partners/")) {
      const kinds = (url.searchParams.get("kinds") || "").split(",");
      seen.kinds.push(url.searchParams.get("kinds") || "");
      const results = ROWS.filter((r) => kinds.includes(KIND_OF[r.id]));
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ count: results.length, results }) });
      return true;
    }
    return false;
  };
}

test("kind chips filter on the server, show counts and survive a reload", async ({ page }) => {
  const seen = { kinds: [] as string[], bulk: [] as unknown[] };
  await installAuthenticatedApiMocks(page, suppliersResponder(seen));
  await page.goto("/suppliers");

  const broker = page.locator('[data-kind="CustomsBroker"]');
  await expect(broker).toHaveText(/مخلّص جمركي \(1\)/, { timeout: 15000 });
  await expect(page.getByRole("button", { name: "حاييم" })).toBeVisible();
  await expect(page.getByRole("button", { name: "مورد محلي", exact: true })).toBeVisible();

  await broker.click();
  await page.locator('[data-kind="Carrier"]').click();
  await expect(page.getByRole("button", { name: "مورد محلي", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "اسامه" })).toBeVisible();
  expect(seen.kinds.at(-1)).toBe("CustomsBroker,Carrier");

  await page.reload();
  await expect(page.locator('[data-kind="CustomsBroker"]')).toHaveAttribute("aria-pressed", "true", { timeout: 15000 });
  await expect(page.locator('[data-kind="Carrier"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "حاييم" })).toBeVisible();
  await expect(page.getByRole("button", { name: "مورد محلي", exact: true })).toHaveCount(0);
});

test("open-card button, bulk classify, and the new-party chooser", async ({ page }) => {
  const seen = { kinds: [] as string[], bulk: [] as unknown[] };
  await installAuthenticatedApiMocks(page, suppliersResponder(seen));
  await page.goto("/suppliers");

  await expect(page.getByRole("button", { name: "مورد بلا تصنيف" })).toBeVisible({ timeout: 15000 });
  // الاختيار الجماعي للموردين وحدهم — لا خانة للمخلّص.
  await expect(page.getByLabel("اختيار حاييم")).toHaveCount(0);
  await page.getByLabel("اختيار مورد بلا تصنيف").check();
  await page.getByRole("button", { name: "اجعلهم محليين" }).click();
  await expect(page.getByText("صُنِّف 1 مورداً محلياً.")).toBeVisible();
  expect(seen.bulk).toEqual([{ ids: [2], supplier_scope: "local" }]);

  const row = page.getByRole("row").filter({ hasText: "حاييم" });
  await row.getByRole("button", { name: "فتح البطاقة" }).click();
  await expect(page).toHaveURL(/\/partners\/83$/);
  await page.goBack();

  await page.getByRole("button", { name: /^جديد$/ }).click();
  await expect(page.getByText("شو بدك تنشئ؟")).toBeVisible();
  await page.getByRole("menuitem", { name: "مخلّص جمركي" }).click();
  await expect(page.getByRole("heading", { name: "إضافة طرف جديد" })).toBeVisible();
  // النوع مثبّت: لا منتقي «نوع الطرف» ولا «نطاق المورد».
  await expect(page.getByText("نوع الطرف *")).toHaveCount(0);
  await expect(page.getByText("نطاق المورد")).toHaveCount(0);
});
