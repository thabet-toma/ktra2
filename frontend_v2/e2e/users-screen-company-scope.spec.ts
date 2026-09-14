import { expect, test, type Page } from "@playwright/test";

/**
 * «إدارة المستخدمين» تعرض أعضاءَ الشركة النشطة — للجميع بمن فيهم السوبر أدمن.
 *
 * كان الفرعُ في `App.tsx` يقرأ مرآةَ `users` العالمية للسوبر أدمن (كلُّ حسابات
 * المنصة بلا شركة) ويقرأ أعضاءَ الشركة لغيره، فاختلف العرضان جذرياً وكلاهما
 * خاطئ. وكان صفُّ العضوية يُسحق دورُه إلى «مدير/موظف» فلا يطابق فلترُ
 * «مشتريات» شيئاً أبداً.
 */

test.use({ serviceWorkers: "block" });

const members = [
  {
    membership_id: 1, user_id: 11, username: "mgr", email: "mgr@example.test",
    full_name: "مدير الشركة", role: "manager", is_active: true,
  },
  {
    membership_id: 2, user_id: 12, username: "buyer", email: "buyer@example.test",
    full_name: "مسؤول المشتريات", role: "procurement", is_active: true,
  },
  {
    membership_id: 3, user_id: 13, username: "acc", email: "acc@example.test",
    full_name: "محاسب الشركة", role: "accountant", is_active: false,
  },
];

async function openUsersScreen(page: Page, isSuperAdmin: boolean) {
  const seen = { mapperUsers: 0, members: 0 };
  await page.addInitScript(() => {
    localStorage.setItem("token", "users-token");
    localStorage.setItem("userId", "users-viewer");
    localStorage.setItem("tenantId", "77");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.includes("/mapper/users")) {
      seen.mapperUsers += 1;
      return route.fulfill({
        contentType: "application/json",
        // مرآةُ المنصة: حساباتٌ من خارج الشركة. ظهورُ أيٍّ منها = رجوعُ العطب.
        body: JSON.stringify([
          { id: "901", name: "حساب من شركة أخرى", role: "employee", email: "x@y.z", isApproved: true },
          { id: "902", name: "حساب منصّة يتيم", role: "employee", email: "a@b.c", isApproved: true },
        ]),
      });
    }
    if (url.pathname.endsWith("/hr/users/users-viewer/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "users-viewer", name: "مدير الشركة", role: "manager",
          email: "mgr@example.test", isApproved: true, isEmailVerified: true,
          isSuperAdmin,
        }),
      });
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager", is_manager: true,
          permissions: ["hr.employees.manage"],
        }),
      });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 77, role: "manager", is_default: true, can_access_import: false,
          created_at: "2026-07-22T00:00:00Z",
          tenant: {
            TenantID: 77, CompanyName: "شركة النور", SubscriptionPlan: "Enterprise",
            Status: "Active", CreatedAt: "2026-07-22T00:00:00Z", import_enabled: false,
          },
        }]),
      });
    }
    if (url.pathname.endsWith("/tenants/companies/77/members/")) {
      seen.members += 1;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(members) });
    }
    return route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/users");
  await expect(page.getByRole("heading", { name: "إدارة المستخدمين" })).toBeVisible();
  return seen;
}

for (const isSuperAdmin of [false, true]) {
  const who = isSuperAdmin ? "السوبر أدمن" : "مديرٌ ليس سوبر أدمن";

  test(`${who} يرى أعضاءَ الشركة وحدَهم بأدوارهم الحقيقية`, async ({ page }) => {
    const seen = await openUsersScreen(page, isSuperAdmin);

    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(3);
    await expect(page.getByText("مسؤول المشتريات")).toBeVisible();
    await expect(page.getByText("محاسب الشركة")).toBeVisible();
    // حسابات المنصة من خارج الشركة لا تصل الشاشة أصلاً.
    await expect(page.getByText("حساب من شركة أخرى")).toHaveCount(0);
    expect(seen.mapperUsers).toBe(0);
    expect(seen.members).toBeGreaterThan(0);

    // الدورُ الحقيقيّ معروضٌ لا مسحوقاً إلى «موظف».
    await expect(rows.filter({ hasText: "مسؤول المشتريات" })).toContainText("موظف مشتريات");
    await expect(rows.filter({ hasText: "محاسب الشركة" })).toContainText("محاسب");

    // فلترُ «مشتريات» يطابق — وهو ما كان يُفرغ الشاشةَ ويُفتح به البلاغ.
    await page.selectOption("#roleFilter", "procurement");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("مسؤول المشتريات");

    // «غير مفعَّل» من `is_active` لا من قيمةٍ مثبَّتة: للمحاسب وحدَه زرُّ «قبول».
    await page.selectOption("#roleFilter", "all");
    await expect(rows.filter({ hasText: "محاسب الشركة" }).getByRole("button", { name: "قبول" }))
      .toHaveCount(1);
    await expect(rows.filter({ hasText: "مدير الشركة" }).getByRole("button", { name: "قبول" }))
      .toHaveCount(0);

    // عمودُ «الحالة الوظيفية» رُفع: لا مصدرَ له فلا يُعرض «غير محدد» للجميع.
    await expect(page.getByRole("columnheader", { name: "الحالة الوظيفية" })).toHaveCount(0);
  });
}
