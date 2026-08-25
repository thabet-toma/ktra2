import { expect, test, type Page } from "@playwright/test";

/**
 * الورقتان اللتان تُسلَّمان بيد الموظف: قسيمة راتبه، وكشف دوامه اليومي.
 *
 * التقريران الجماعيان (`payslips` و`timesheet-daily`) موجودان على شاشة
 * التقارير منذ THA-126، لكنهما لكل الموظفين — لا يُسلَّمان لأحد. وهذا الملف
 * يحرس ما ينقص: أن **شاشة الرواتب نفسها** تُخرج ورقةً لموظفٍ واحد.
 *
 * ولا يُثبت ذلك إلا اختبار متصفّح: `tsc` في هذا المستودع لا يفحص خصائص JSX
 * (لا `@types/react`)، فزرٌّ غير مركَّب يمرّ خضراء عنده. النافذة المنبثقة
 * ومحتواها هما الدليل.
 *
 * الشبكة موقوفة بالكامل — لا خادم ولا قاعدة بيانات.
 */

const EMPLOYEES = [
  {
    id: 1, code: "EMP-1", name: "عمر", pay_type: "hourly", pay_type_label: "بالساعة",
    monthly_salary: "0.00", hourly_rate: "20.00", standard_hours_per_day: "8.00",
    working_days_per_month: "26.00", job_title: "فنّي", phone: "", national_id: "",
    hire_date: null, is_active: true, notes: "", user: null, account: 5,
    account_code: "21120001", account_name: "عمر", balance: "250.00",
    created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: 2, code: "EMP-2", name: "سامي", pay_type: "monthly", pay_type_label: "شهري",
    monthly_salary: "2600.00", hourly_rate: "0.00", standard_hours_per_day: "8.00",
    working_days_per_month: "26.00", job_title: "محاسب", phone: "", national_id: "",
    hire_date: null, is_active: true, notes: "", user: null, account: 6,
    account_code: "21120002", account_name: "سامي", balance: "1600.00",
    created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
  },
];

const MONTH = (() => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
})();

const day = (n: number) => `${MONTH}-${String(n).padStart(2, "0")}`;

const WORK_LOGS = [
  { id: 11, employee: 1, employee_name: "عمر", date: day(3), hours: "8.00", notes: "", created_at: "" },
  { id: 12, employee: 1, employee_name: "عمر", date: day(4), hours: "7.50", notes: "جرد", created_at: "" },
];

const PAYSLIPS = [{
  id: 71, employee: 2, employee_name: "سامي",
  period_start: `${MONTH}-01`, period_end: `${MONTH}-28`,
  pay_type: "monthly", rate: "2600.00", worked_hours: "0.00",
  absence_days: "1.00", late_minutes: 90, gross: "2600.00", allowances: "100.00",
  absence_deduction: "100.00", late_deduction: "0.00", other_deductions: "0.00",
  net: "2600.00", status: "posted", status_label: "مرحّل", notes: "",
  posted_at: "2026-08-20T00:00:00Z", paid_total: "1000.00",
  created_at: "", updated_at: "",
}];

async function installPayrollMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "payroll-print-token");
    localStorage.setItem("userId", "payroll-print-user");
    localStorage.setItem("tenantId", "1");
    // حوار الطباعة لا يُفتح في اختبار — النافذة ومحتواها هما المقصودان.
    window.print = () => {};
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: "application/json", body: JSON.stringify(body),
    });

    if (url.pathname.endsWith("/hr/users/payroll-print-user/")) {
      return json({
        id: "payroll-print-user", name: "المدير", role: "manager",
        email: "payroll@example.test", employmentStatus: "active",
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: "شركة الكشوف", SubscriptionPlan: "basic",
          Status: "active", CreatedAt: "2026-01-01T00:00:00Z", import_enabled: false,
        },
        role: "manager", is_default: true,
        created_at: "2026-01-01T00:00:00Z", can_access_import: false,
      }]);
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return json({
        role: "manager", is_manager: true, ui_mode: "advanced", modules: {},
        permissions: ["hr.payroll.view", "hr.payroll.manage", "hr.payroll.post"],
      });
    }
    if (url.pathname.endsWith("/hr/employees/")) return json(EMPLOYEES);
    if (url.pathname.endsWith("/hr/work-logs/")) return json(WORK_LOGS);
    if (url.pathname.endsWith("/hr/attendance-adjustments/")) {
      return json([{
        id: 21, employee: 1, employee_name: "عمر", date: day(10),
        kind: "absence", kind_label: "غياب", days: "1.00", minutes: 0,
        is_deductible: true, notes: "سفر", created_at: "",
      }]);
    }
    if (url.pathname.includes("/hr/payslips/preview")) {
      return json({
        pay_type: "monthly", rate: "2600.00", worked_hours: "0.00",
        absence_days: "1.00", late_minutes: "90", gross: "2600.00",
        allowances: "0.00", absence_deduction: "100.00", late_deduction: "0.00",
        other_deductions: "0.00", net: "2500.00",
      });
    }
    if (url.pathname.endsWith("/hr/payslips/")) return json(PAYSLIPS);
    if (url.pathname.endsWith("/hr/payroll-payments/")) return json([]);
    return json([]);
  });
}

test.setTimeout(120000);

test("قسيمة راتب موظفٍ واحد تُطبع من شاشة الرواتب", async ({ page }) => {
  await installPayrollMocks(page);
  await page.goto("/payroll");

  await expect(page.getByRole("button", { name: "كشوف الرواتب" })).toBeVisible({ timeout: 20000 });
  await page.selectOption("select", "2");
  await page.getByRole("button", { name: "كشوف الرواتب" }).click();
  await expect(page.getByText("مرحّل").first()).toBeVisible({ timeout: 20000 });

  const [slipWindow] = await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("button", { name: "طباعة القسيمة" }).first().click(),
  ]);
  await slipWindow.waitForLoadState("domcontentloaded");
  const body = slipWindow.locator("body");

  await expect(body).toContainText("كشف راتب — سامي");
  await expect(body).toContainText("شركة الكشوف");
  // هويّة الموظف على الورقة، لا الأرقام وحدها.
  await expect(body).toContainText("EMP-2");
  await expect(body).toContainText("محاسب");
  // خمسة سطور ثابتة — والصفر منها يُطبع.
  await expect(body).toContainText("الراتب الأساسي");
  await expect(body).toContainText("خصم الغياب");
  await expect(body).toContainText("خصم التأخير");
  await expect(body).toContainText("الصافي المستحق");
  await expect(body).toContainText("2,600");
  // «المتبقّي» لا يُشتقّ على ورقةٍ تُوقَّع — المصروف والرصيد من الخادم.
  await expect(body).toContainText("المصروف من هذا الكشف");
  await expect(body).not.toContainText("المتبقّي");
  await expect(body).toContainText("توقيع المستلم");
  await slipWindow.close();
});

test("كشف الساعات: جدولٌ فيه كل يوم من الشهر ومجموع الساعات", async ({ page }) => {
  await installPayrollMocks(page);
  await page.goto("/payroll");

  await expect(page.getByRole("button", { name: "السجل اليومي" })).toBeVisible({ timeout: 20000 });
  await page.selectOption("select", "1");
  await page.getByRole("button", { name: "السجل اليومي" }).click();
  await expect(page.getByRole("button", { name: "تسجيل الساعات" })).toBeVisible({ timeout: 20000 });

  const [sheetWindow] = await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("button", { name: "طباعة كشف الساعات" }).click(),
  ]);
  await sheetWindow.waitForLoadState("domcontentloaded");
  const body = sheetWindow.locator("body");

  await expect(body).toContainText("كشف ساعات الدوام — عمر");
  await expect(body).toContainText("EMP-1");
  // صفٌّ لكل يوم من أيام الشهر — لا لكل سجلّ (سجلّان فقط في المُعِدّ).
  const rows = sheetWindow.locator("tbody tr");
  await expect(rows).toHaveCount(new Date(
    Number(MONTH.slice(0, 4)), Number(MONTH.slice(5, 7)), 0,
  ).getDate());
  await expect(body).toContainText("15.5");
  await expect(body).toContainText("جرد");
  await expect(body).toContainText("توقيع الموظف");
  await sheetWindow.close();
});
