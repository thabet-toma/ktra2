import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const applicant = {
  id: 10,
  job: 7,
  job_title: "محاسب",
  name: "أحمد المتقدم",
  phone: "0599000000",
  email: "ahmad@example.test",
  about: "خبرة مناسبة",
  has_cv: true,
  cv_name: "ahmad-cv.pdf",
  status: "new",
  rating: 0,
  notes: "",
  hired_employee: null,
  reference_code: "REF-CV-10",
  created_at: "2026-09-10T08:00:00Z",
  updated_at: "2026-09-10T08:00:00Z",
};

async function installManagerMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "hiring-e2e-token");
    localStorage.setItem("userId", "hiring-e2e-user");
    localStorage.setItem("tenantId", "42");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/hiring-e2e-user/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "hiring-e2e-user",
          name: "مدير التوظيف",
          role: "manager",
          email: "manager@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 42,
          tenant: {
            TenantID: 42,
            CompanyName: "شركة الاختبار",
            SubscriptionPlan: "Enterprise",
            Status: "Active",
            CreatedAt: "2026-09-01T00:00:00Z",
          },
          role: "manager",
          is_default: true,
          created_at: "2026-09-01T00:00:00Z",
        }]),
      });
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager",
          is_manager: true,
          ui_mode: "advanced",
          modules: { employee_ops: true },
          permissions: ["employee_ops.manage", "employee_ops.self"],
        }),
      });
    }
    if (url.pathname.endsWith("/employee-ops/jobs/")) {
      return route.fulfill({ contentType: "application/json", body: "[]" });
    }
    if (url.pathname.endsWith("/employee-ops/applicants/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([applicant]),
      });
    }
    if (url.pathname.endsWith("/employee-ops/applicants/10/cv/")) {
      return route.fulfill({
        contentType: "application/pdf",
        body: Buffer.from("%PDF-1.7 hiring e2e"),
      });
    }
    return route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

test("فتح CV يمر عبر طلب مصادَق عليه ثم يعرض نسخة المتصفح المحلية", async ({ page }) => {
  await installManagerMocks(page);
  await page.goto("/employee-ops/hiring");

  await page.getByRole("button", { name: /المتقدمون/ }).click();
  await page.getByRole("button", { name: "فتح", exact: true }).click();

  const cvTrigger = page
    .getByRole("button", { name: /فتح السيرة الذاتية/ })
    .or(page.getByRole("link", { name: /فتح السيرة الذاتية/ }));
  await expect(cvTrigger).toBeVisible();
  const [request, popup] = await Promise.all([
    page.waitForRequest((req) => req.url().endsWith("/employee-ops/applicants/10/cv/")),
    page.waitForEvent("popup"),
    cvTrigger.click(),
  ]);

  expect(request.headers().authorization).toBe("Token hiring-e2e-token");
  expect(request.headers()["x-tenant-id"]).toBe("42");
  const viewer = popup.locator('iframe[title="ahmad-cv.pdf"]');
  await expect(viewer).toBeVisible();
  await expect(viewer).toHaveAttribute("src", /^blob:/);
});

test("الطلب بلا CV يحتاج تأكيداً والإلغاء يبقي البيانات ولا يرسل", async ({ page }) => {
  let applyCalls = 0;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/employee-ops/public/jobs/public-job-token/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          title: "محاسب",
          description: "وصف الوظيفة",
          requirements: "",
          location: "رام الله",
          employment_type: "full_time",
          salary_range: "",
        }),
      });
    }
    if (url.pathname.endsWith("/employee-ops/public/jobs/public-job-token/apply/")) {
      applyCalls += 1;
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ reference_code: "REF-NO-CV" }),
      });
    }
    return route.fulfill({ contentType: "application/json", body: "{}" });
  });

  await page.goto("/jobs/public-job-token");
  await expect(page.getByText("التقديم على الوظيفة", { exact: true })).toBeVisible();
  await page.locator('input[type="text"]').first().fill("سارة");
  await page.locator('input[type="tel"]').fill("0599111111");
  await page.getByRole("button", { name: "إرسال الطلب" }).click();

  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("إرسال الطلب دون سيرة ذاتية؟");
  expect(applyCalls).toBe(0);

  await dialog.getByRole("button", { name: "إضافة السيرة" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('input[type="text"]').first()).toHaveValue("سارة");
  await expect(page.locator('input[type="tel"]')).toHaveValue("0599111111");
  expect(applyCalls).toBe(0);

  await page.getByRole("button", { name: "إرسال الطلب" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "إرسال دون سيرة" }).click();

  await expect(page.getByText("تم استلام طلبك")).toBeVisible();
  expect(applyCalls).toBe(1);
});
