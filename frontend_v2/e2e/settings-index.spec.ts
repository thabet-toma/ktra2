import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * #75/#69 — «صفحة كبيرة غير منظّمة… أوّل ما أفوت يكون بس عناوين الإعدادات، ولمّا
 * أكبس على واحد يبيّن اللي تحته».
 *
 * الإعداداتُ فهرسُ بطاقاتٍ ببحث؛ الكبسةُ تفتح القسمَ وحده مع رجوعٍ للفهرس، والقسمُ
 * في الرابط (`?section=`) فزرُّ «رجوع» المتصفح يعيد الفهرس. وبطاقاتُ الشاشات
 * المستقلّة تتبع الصلاحيات: من لا يملك إدارةَ الصلاحيات لا يرى بطاقتها.
 */

test.use({ serviceWorkers: "block" });

async function install(page: Page, permissions: string[]) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "settings-e2e-token");
    localStorage.setItem("userId", "settings-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route: Route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const p = url.pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (p.endsWith("/hr/users/settings-e2e-user/")) {
      return json({
        id: "settings-e2e-user", name: "مدير الإعدادات", role: "manager", email: "settings@example.test",
        employmentStatus: "active", isApproved: true, isEmailVerified: true,
      });
    }
    if (p.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1, role: "manager", is_default: true, can_access_import: false, created_at: "2026-01-01T00:00:00Z",
        tenant: { TenantID: 1, CompanyName: "شركة الإعدادات", SubscriptionPlan: "Enterprise", Status: "Active", CreatedAt: "2026-01-01T00:00:00Z", import_enabled: false },
      }]);
    }
    if (p.endsWith("/permissions/me/")) return json({ role: "manager", is_manager: true, permissions });
    if (p.endsWith("/my-plan/usage/")) return json({ plan: "Enterprise", plan_label: "المؤسّسات", limits: [] });
    if (p.endsWith("/pricing/plans/")) {
      return json({ currency: "ILS", plans: [], data_entry_addon: { key: "data_entry", label: "", price: 0, included_operations: 0, extra_operation_price: null } });
    }
    if (p.endsWith("/hr/auth/devices/")) return json({ devices: [], has_primary: true, primary_invitation: null });
    return json([]);
  });
}

const card = (page: Page, id: string) => page.getByTestId(`settings-card-${id}`);

test("الدخول يعرض العناوين وحدَها، والكبسةُ تفتح قسماً واحداً، و«رجوع» يعيد الفهرس", async ({ page }) => {
  await install(page, ["sales.settings.manage", "purchase.settings.manage"]);
  await page.goto("/settings");

  await expect(card(page, "security")).toBeVisible({ timeout: 30_000 });
  await expect(card(page, "profile")).toBeVisible();
  await expect(card(page, "appearance")).toBeVisible();
  // لا حقلَ ظاهرٌ قبل أن يُفتح قسمُه.
  await expect(page.getByRole("button", { name: "تحديث كلمة المرور" })).toBeHidden();
  await expect(page.getByText("مظهر الواجهة", { exact: true })).toBeHidden();

  await card(page, "security").click();
  await expect(page).toHaveURL(/section=security/);
  await expect(page.getByRole("button", { name: "تحديث كلمة المرور" })).toBeVisible();
  await expect(page.getByText("أجهزة الدخول", { exact: true })).toBeVisible();
  await expect(page.getByText("مظهر الواجهة", { exact: true })).toBeHidden();
  await expect(card(page, "profile")).toBeHidden();

  await page.getByRole("button", { name: "كل الإعدادات" }).click();
  await expect(page).not.toHaveURL(/section=/);
  await expect(card(page, "profile")).toBeVisible();

  // رجوعُ المتصفح من قسمٍ يعيد الفهرس لا الصفحةَ السابقة.
  await card(page, "appearance").click();
  await expect(page.getByText("مظهر الواجهة", { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(card(page, "appearance")).toBeVisible();
});

test("البحث يطابق أسماءَ الحقول داخل الأقسام، وEnter يفتح النتيجةَ الوحيدة", async ({ page }) => {
  await install(page, []);
  await page.goto("/settings");
  const search = page.getByRole("searchbox", { name: "ابحث عن إعداد" });
  await expect(search).toBeVisible({ timeout: 30_000 });

  await search.fill("حجم الخط");
  await expect(card(page, "appearance")).toBeVisible();
  await expect(card(page, "security")).toHaveCount(0);

  await search.fill("شيء غير موجود");
  await expect(page.getByText(/لا إعداد يطابق/)).toBeVisible();
  await page.getByRole("button", { name: "مسح البحث" }).click();
  await expect(card(page, "security")).toBeVisible();

  await search.fill("كلمة المرور");
  await search.press("Enter");
  await expect(page).toHaveURL(/section=security/);
});

test("بطاقاتُ الشاشات المستقلّة تتبع الصلاحيات وتنقل إليها", async ({ page }) => {
  await install(page, ["sales.settings.manage"]);
  await page.goto("/settings");
  await expect(card(page, "sales")).toBeVisible({ timeout: 30_000 });
  await expect(card(page, "purchase")).toHaveCount(0);
  await expect(card(page, "permissions")).toHaveCount(0);
  await expect(card(page, "company")).toHaveCount(0);

  await card(page, "sales").click();
  await expect(page).toHaveURL(/\/sales\/settings/);
});

test("‎/settings#my-plan (حارسُ حدّ الخطّة) يفتح قسمَ الخطّة", async ({ page }) => {
  await install(page, []);
  await page.goto("/settings#my-plan");
  await expect(page).toHaveURL(/section=plan/, { timeout: 30_000 });
  await expect(page.locator("#my-plan")).toBeVisible();
});
