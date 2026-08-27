import { expect, test } from "@playwright/test";

test.use({ serviceWorkers: "block" });

/** سجل النشاط يعرض تفصيل الحركة: البند المضاف/المحذوف والقيمة من ← إلى. */
test("activity feed renders the change detail of an invoice edit", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("token", "activity-token");
    localStorage.setItem("userId", "activity-user");
    localStorage.setItem("tenantId", "1");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/activity-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "activity-user",
          name: "مدير الاختبار",
          role: "manager",
          email: "manager@example.test",
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
            CreatedAt: "2026-08-01T00:00:00Z",
          },
          role: "manager",
          is_default: true,
          created_at: "2026-08-01T00:00:00Z",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ role: "manager", is_manager: true, permissions: [] }),
      });
      return;
    }
    if (url.pathname.endsWith("/activity/users/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ id: 5, name: "ثابت طعمه" }]),
      });
      return;
    }
    if (url.pathname.endsWith("/activity/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
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
        }]),
      });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/?view=activity-log");

  const row = page.locator("tbody tr").first();
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
});
