/**
 * T-INTENT — الدفعة المسجَّلة على المسودة، من الشاشة.
 *
 * ما يحرسه هنا هو بالضبط الشكوى التي وُلد منها التغيير: أن يسجّل المستخدم دفعةً
 * على مسودة فلا يرى لها أثراً — «المتبقي» كما هو والحالة «غير مدفوعة» — لأن
 * الخادم كان يرفض النقد على المسودة أصلاً ولا وعاء لنيّة الدفع.
 *
 * ثلاثة وعود: صفّ الدفعة يظهر موسوماً «غير مرحّل»، و«المتبقي» ينزل إلى صفر مع
 * وسمٍ صريح يقول إنها لم تدخل الدفاتر، والحذف يعيد الحال. الخادم مموَّه بشكل
 * الردّ الحقيقي لـ`payment-voucher/` (الفاتورة كاملةً).
 */
import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const SHOTS = "e2e/payment-intent-shots";

/** مسودة إجماليها 100، بلا دفعات — نقطة البداية. */
const draft = (overrides: Record<string, unknown> = {}) => ({
  id: 401,
  invoice_number: "SI-INT-401",
  invoice_date: "2026-08-10",
  due_date: "2026-09-10",
  customer: 8,
  customer_name: "عميل النيّة",
  invoice_type: "credit",
  invoice_kind: "sale",
  status: "draft",
  currency: 1,
  exchange_rate: "1",
  subtotal_excl_tax: "100.00",
  invoice_discount: "0.00",
  tax_amount: "0.00",
  grand_total: "100.00",
  amount_paid: "0.00",
  remaining_balance: "100.00",
  pending_payment_total: "0.00",
  payment_status: "unpaid",
  payment_status_display: "غير مدفوعة",
  customer_balance_before_invoice: "0.00",
  customer_balance_after_invoice: "100.00",
  journal: null,
  stock_on_post: true,
  attached_cash_amount: "0.00",
  attached_cash_account: null,
  cheques: [],
  lines: [{
    id: 1, product: 42, quantity: "1", unit_price: "100.00",
    line_discount: "0.00", tax_rate: null,
  }],
  payment_details: [],
  ...overrides,
});

/** الحالة بعد تسجيل 100 نقداً نيّةً — الدفاتر ساكنة والنيّة ظاهرة. */
const withIntent = () => draft({
  pending_payment_total: "100.00",
  attached_cash_amount: "100.00",
  attached_cash_account: 10,
});

async function installMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "intent-token");
    localStorage.setItem("userId", "intent-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
  });

  // النيّة تعيش في الوهم: أول نداء إرفاق يقلب الردّ إلى «عليها دفعة».
  let attached = false;

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/intent-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "intent-user", name: "أمين الصندوق", role: "manager",
          email: "intent@example.test", employmentStatus: "active",
          isApproved: true, isEmailVerified: true,
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
            TenantID: 1, CompanyName: "KTRA", SubscriptionPlan: "Enterprise",
            Status: "Active", CreatedAt: "2026-08-01T00:00:00Z",
          },
          role: "manager", is_default: true, created_at: "2026-08-01T00:00:00Z",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager", is_manager: true, ui_mode: "advanced",
          permissions: [
            "sales.invoice.view", "sales.invoice.edit", "sales.invoice.create",
            "sales.invoice.post", "sales.payment.create",
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/lookup/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ id: 8, name: "عميل النيّة", partner_type: "Customer" }]),
      });
      return;
    }
    if (url.pathname.endsWith("/accounting/currencies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ CurrencyID: 1, Code: "ILS" }]),
      });
      return;
    }
    if (url.pathname.endsWith("/accounting/accounts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          { id: 10, code: "1101", name: "الصندوق الرئيسي", account_type: "Asset" },
          { id: 40, code: "4101", name: "المبيعات", account_type: "Revenue" },
        ]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/settings/current/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          default_cash_account: 10, default_currency: 1,
          default_customer: 8, default_revenue_account_product: 40,
        }),
      });
      return;
    }
    if (
      url.pathname.endsWith("/inventory/products/")
      || url.pathname.endsWith("/lookup/products/")
    ) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 42, sku: "P-42", barcode: "6291041500213", name_ar: "لابتوب",
          quantity_on_hand: "9", sale_price: "100",
        }]),
      });
      return;
    }
    // النقطة قيد الاختبار: تسجّل النيّة أو تمسحها بدلالة الاستبدال.
    if (url.pathname.endsWith("/sales/invoices/401/payment-voucher/")) {
      const body = route.request().postDataJSON() as { cash_amount?: string };
      attached = Number(body?.cash_amount || 0) > 0;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(attached ? withIntent() : draft()),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/401/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(attached ? withIntent() : draft()),
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

test("الدفعة تُسجَّل على المسودة: المتبقي صفر موسوماً «غير مرحّلة»", async ({ page }) => {
  await installMocks(page);
  await page.goto("/sales/invoices/401");

  const section = page.getByTestId("invoice-payments-section");
  await expect(section).toBeVisible({ timeout: 15_000 });
  // قبل التسجيل: لا دفعات، والمتبقي كامل.
  await expect(section.getByText("لا دفعات على هذا المستند بعد.")).toBeVisible();
  await expect(page.getByTestId("payments-section-remaining")).toHaveText("100");

  const panel = page.getByTestId("document-payment-panel");
  await expect(panel).toBeVisible();
  await panel.getByTestId("payment-cash").fill("100");

  // الزرّ الذي لم يكن موجوداً: يسجّل بلا ترحيل.
  const saveIntent = page.getByTestId("payment-save-intent");
  await expect(saveIntent).toBeEnabled();
  const [request] = await Promise.all([
    page.waitForRequest((r) =>
      r.url().includes("/sales/invoices/401/payment-voucher/") && r.method() === "POST"),
    saveIntent.click(),
  ]);
  expect(request.postDataJSON()).toMatchObject({ cash_amount: "100.00", cash_account_id: 10 });

  // بعده: صفّ نقدٍ موسومٌ «غير مرحّل»، ومتبقٍّ صفر، والحالة تقول إنها لم تُرحَّل.
  await expect(section.getByTestId("intent-row-cash")).toBeVisible();
  await expect(section.getByTestId("intent-row-cash").getByText("غير مرحّل")).toBeVisible();
  await expect(page.getByTestId("payments-section-remaining")).toHaveText("0");
  await expect(
    section.getByText(/الدفعة مسجَّلة بالكامل ولم تدخل الدفاتر بعد/),
  ).toBeVisible();
  await section.screenshot({ path: `${SHOTS}/draft-intent-section.png` });
});

test("حذف الدفعة من المسودة يعيد المتبقي كاملاً", async ({ page }) => {
  await installMocks(page);
  await page.goto("/sales/invoices/401");

  const panel = page.getByTestId("document-payment-panel");
  await expect(panel).toBeVisible({ timeout: 15_000 });
  await panel.getByTestId("payment-cash").fill("100");
  await page.getByTestId("payment-save-intent").click();

  const section = page.getByTestId("invoice-payments-section");
  await expect(section.getByTestId("intent-row-cash")).toBeVisible();

  const [request] = await Promise.all([
    page.waitForRequest((r) =>
      r.url().includes("/sales/invoices/401/payment-voucher/") && r.method() === "POST"),
    section.getByRole("button", { name: "حذف الدفعة النقدية" }).click(),
  ]);
  expect(request.postDataJSON()).toMatchObject({ cash_amount: "0.00" });

  await expect(section.getByTestId("intent-row-cash")).toHaveCount(0);
  await expect(page.getByTestId("payments-section-remaining")).toHaveText("100");
});
