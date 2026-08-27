import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

/** ردود قشرة التطبيق — مشتركة بين اختبارات هذا الملف كي لا تتكرر ثلاث مرات. */
const SHELL_RESPONSES: Record<string, unknown> = {
  "/hr/users/activity-user/": {
    id: "activity-user",
    name: "مدير الاختبار",
    role: "manager",
    email: "manager@example.test",
    employmentStatus: "active",
    isApproved: true,
    isEmailVerified: true,
  },
  "/tenants/companies/my-companies/": [{
    id: 1,
    tenant: {
      TenantID: 1,
      CompanyName: "KTRA",
      SubscriptionPlan: "Enterprise",
      Status: "Active",
      CreatedAt: "2026-08-01T00:00:00Z",
    },
    role: "manager",
    is_default: true,
    created_at: "2026-08-01T00:00:00Z",
  }],
  "/permissions/me/": { role: "manager", is_manager: true, permissions: [] },
  "/activity/users/": [{ id: 5, name: "ثابت طعمه" }],
};

/**
 * يسجّل الجلسة ويعترض كل نداءات الـAPI.
 *
 * `onActivity` يقرّر ردّ `/api/activity/` وحده ويستقبل الاستعلام كما وصل، فيصلح
 * لفحص الحمولة (أي مدىً أُرسل) ولفحص العرض (بأي صفوف يُرسم الجدول) معاً.
 */
async function stubApi(page: Page, onActivity: (search: string) => unknown) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "activity-token");
    localStorage.setItem("userId", "activity-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    for (const [suffix, body] of Object.entries(SHELL_RESPONSES)) {
      if (url.pathname.endsWith(suffix)) {
        await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
        return;
      }
    }
    if (url.pathname.endsWith("/activity/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(onActivity(url.search) ?? []),
      });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

const EDIT_ROW = {
  id: 101,
  action: "update",
  action_label: "تعديل",
  is_view: false,
  entity_type: "sales_invoice",
  entity_id: 293,
  entity_label: "SI-6-293",
  description:
    "تعديل فاتورة مبيعات — «إطار 205»: السعر من 100 إلى 120؛ "
    + "حذف منتج «زيت محرك»؛ أضاف منتج «فلتر هواء» (الكمية 3 · السعر 70)",
  metadata: {
    changes: [
      {
        kind: "line_changed",
        label: "إطار 205",
        changes: [{ field: "unit_price", label: "السعر", old: "100", new: "120" }],
      },
      { kind: "line_removed", label: "زيت محرك", values: [] },
      {
        kind: "line_added",
        label: "فلتر هواء",
        values: [{ label: "الكمية", value: "3" }, { label: "السعر", value: "70" }],
      },
      { field: "invoice_discount", label: "خصم الفاتورة", old: "0", new: "10" },
    ],
  },
  user: 5,
  user_name: "ثابت طعمه",
  ip_address: "82.205.43.240",
  timestamp: "2026-08-07T16:42:00Z",
};

/** سجل النشاط يعرض تفصيل الحركة: البند المضاف/المحذوف والقيمة من ← إلى. */
test("activity feed renders the change detail of an invoice edit", async ({ page }) => {
  await stubApi(page, () => [EDIT_ROW]);
  await page.goto("/?view=activity-log");

  // بعد التجميع باليوم صار أوّل صفٍّ في tbody ترويسةَ اليوم، فالمرساة هي المستند نفسه.
  const row = page.locator("tbody tr", { hasText: "SI-6-293" }).first();
  await expect(row.getByText("SI-6-293")).toBeVisible({ timeout: 15000 });
  // البند المعدَّل: الاسم + القيمة القديمة والجديدة
  await expect(row.getByText("إطار 205")).toBeVisible();
  await expect(row.getByText("100", { exact: true })).toBeVisible();
  await expect(row.getByText("120", { exact: true })).toBeVisible();
  // المحذوف والمضاف باسميهما + قيم المضاف
  await expect(row.getByText("حذف")).toBeVisible();
  await expect(row.getByText("زيت محرك")).toBeVisible();
  await expect(row.getByText("أضاف")).toBeVisible();
  await expect(row.getByText("فلتر هواء")).toBeVisible();
  await expect(row.getByText("(الكمية 3 · السعر 70)")).toBeVisible();
  // حقل الترويسة
  await expect(row.getByText("خصم الفاتورة:")).toBeVisible();

  // ترويسة اليوم فوق الصف — التجميع الزمني حيّ لا زينة في الكود.
  await expect(page.locator("tbody tr").first()).toContainText("حدثاً");
});

/** المدى الزمني: الشريحة تُرسل `range`، و«مخصص» تستبدله بحدّين صريحين. */
test("range chips drive the activity query", async ({ page }) => {
  const calls: string[] = [];
  await stubApi(page, (search) => { calls.push(search); return []; });
  await page.goto("/?view=activity-log");

  // الافتراضي «اليوم» — ولم يكن للمستخدم قبل اليوم مخرجٌ منه.
  await expect.poll(() => calls.some((q) => q.includes("range=today"))).toBe(true);

  await page.getByRole("button", { name: "هذا الشهر", exact: true }).click();
  await expect.poll(() => calls.some((q) => q.includes("range=month"))).toBe(true);

  await page.getByRole("button", { name: "الكل", exact: true }).click();
  await expect.poll(() => calls.some((q) => q.includes("range=all"))).toBe(true);

  await page.getByRole("button", { name: "مخصص", exact: true }).click();
  await expect.poll(
    () => calls.some((q) => q.includes("date_from=") && !q.includes("range=")),
  ).toBe(true);
});

/** الإنشاء يُعرض بمحتواه: كل بندٍ أُضيف، والترويسة قيمةً واحدة لا «من ← إلى». */
test("creation detail renders added lines and field_set values", async ({ page }) => {
  await stubApi(page, () => [{
    id: 202,
    action: "create",
    action_label: "إنشاء",
    is_view: false,
    entity_type: "sales_invoice",
    entity_id: 300,
    entity_label: "SI-6-300",
    description: "إنشاء فاتورة مبيعات — العميل: أحمد؛ أضاف منتج «إطار 205» (الكمية 4 · السعر 110)",
    metadata: {
      changes: [
        { kind: "field_set", field: "customer", label: "العميل", new: "أحمد" },
        {
          kind: "line_added",
          label: "إطار 205",
          values: [{ label: "الكمية", value: "4" }, { label: "السعر", value: "110" }],
        },
      ],
    },
    user: 5,
    user_name: "ثابت طعمه",
    ip_address: "82.205.43.240",
    timestamp: "2026-08-07T16:42:00Z",
  }]);
  await page.goto("/?view=activity-log");

  const row = page.locator("tbody tr", { hasText: "SI-6-300" }).first();
  await expect(row.getByText("العميل:")).toBeVisible({ timeout: 15000 });
  await expect(row.getByText("أحمد", { exact: true })).toBeVisible();
  // `field_set` قيمةٌ واحدة — بلا شطبِ قيمةٍ قديمة، وإلا قُرئ الإنشاء تعديلاً.
  await expect(row.locator(".line-through")).toHaveCount(0);
  await expect(row.getByText("أضاف")).toBeVisible();
  await expect(row.getByText("(الكمية 4 · السعر 110)")).toBeVisible();
});
