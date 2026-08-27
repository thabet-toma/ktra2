/**
 * T4 — لوحة التحصيل داخل محرّر فاتورة المبيعات.
 *
 * الخادم لا يُشغَّل في بيئة الوكيل (MySQL متوقّف)، فالـAPI مموَّه هنا بشكل الردّ
 * الحقيقي لـ`invoices/{id}/collect/`: الفاتورة كاملةً + `payment_id`.
 *
 * يثبت ثلاثة أشياء: «المتبقي» يتحرّك حيّاً مع تقسيم ٦٠/٤٠، والنداء يخرج بحمولة
 * واحدة مطابقة، وتنبيه الفائض يظهر حين يتجاوز المدفوعُ المتبقّي.
 */
import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const SHOTS = "e2e/collect-panel-shots";

/** الفاتورة المرحّلة قيد الاختبار: إجمالي 100، لم يُحصَّل منها شيء بعد. */
const invoice = (overrides: Record<string, unknown> = {}) => ({
  id: 301,
  invoice_number: "SI-6-301",
  invoice_date: "2026-08-10",
  due_date: "2026-09-10",
  customer: 8,
  customer_name: "عميل التحصيل",
  invoice_type: "credit",
  invoice_kind: "sale",
  status: "posted",
  currency: 1,
  exchange_rate: "1",
  subtotal_excl_tax: "100.00",
  invoice_discount: "0.00",
  tax_amount: "0.00",
  grand_total: "100.00",
  amount_paid: "0.00",
  remaining_balance: "100.00",
  payment_status: "unpaid",
  payment_status_display: "غير مدفوعة",
  customer_balance_before_invoice: "0.00",
  customer_balance_after_invoice: "100.00",
  journal: 55,
  stock_on_post: true,
  lines: [],
  payment_details: [],
  ...overrides,
});

async function installMocks(page: Page, opts: { simpleMode?: boolean } = {}) {
  const simple = Boolean(opts.simpleMode);
  await page.addInitScript((isSimple) => {
    localStorage.setItem("token", "collect-panel-token");
    localStorage.setItem("userId", "collect-panel-user");
    localStorage.setItem("tenantId", "1");
    // THA-110: الوضع يُقرأ من الخادم، والـcache يطبّقه قبل ردّه.
    localStorage.setItem("ktra_ui_mode::1", isSimple ? "simple" : "advanced");
  }, simple);

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/collect-panel-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "collect-panel-user",
          name: "أمين الصندوق",
          role: "manager",
          email: "collect@example.test",
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
        body: JSON.stringify({
          role: "manager",
          is_manager: true,
          ui_mode: simple ? "simple" : "advanced",
          permissions: [
            "sales.invoice.view",
            "sales.invoice.edit",
            "sales.invoice.create",
            "sales.invoice.post",
            "sales.payment.create",
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/lookup/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ id: 8, name: "عميل التحصيل", partner_type: "Customer" }]),
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
          default_cash_account: 10,
          default_currency: 1,
          default_customer: 8,
          default_revenue_account_product: 40,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/inventory/products/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 42,
          sku: "P-42",
          name_ar: "لابتوب",
          quantity_on_hand: "9",
          sale_price: "100",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/resolve-price/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ unit_price: "100", source: {} }),
      });
      return;
    }
    // مسودة جديدة: الحفظ يُنشئ الفاتورة، ثم يُطلب التحصيل معها الترحيلَ.
    if (url.pathname.endsWith("/sales/invoices/302/collect/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          ...invoice({
            id: 302,
            invoice_number: "SI-6-302",
            amount_paid: "100.00",
            remaining_balance: "0.00",
            payment_status: "paid",
            payment_status_display: "مدفوعة بالكامل",
          }),
          payment_id: 778,
        }),
      });
      return;
    }
    // رصيد العميل «على الحساب»: سند مرحّل بقي منه 25.
    if (url.pathname.endsWith("/sales/payments/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 91,
          partner: 8,
          payment_date: "2026-08-01",
          amount: "25.00",
          unallocated_amount: "25.00",
          is_posted: true,
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/301/collect/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          ...invoice({
            amount_paid: "100.00",
            remaining_balance: "0.00",
            payment_status: "paid",
            payment_status_display: "مدفوعة بالكامل",
          }),
          payment_id: 777,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/301/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(invoice()) });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/") && route.request().method() === "POST") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(invoice({
          id: 302,
          invoice_number: "SI-6-302",
          status: "draft",
          journal: null,
        })),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          next: null,
          previous: null,
          results: [{
            id: 301,
            invoice_number: "SI-6-301",
            invoice_date: "2026-08-10",
            customer: 8,
            customer_name: "عميل التحصيل",
            invoice_type: "credit",
            status: "posted",
            grand_total: "100.00",
            amount_paid: "0.00",
            remaining_balance: "100.00",
            payment_status: "unpaid",
            payment_status_display: "غير مدفوعة",
          }],
        }),
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

async function openPanel(page: Page) {
  await installMocks(page);
  await page.goto("/sales/invoices/301");
  const panel = page.getByTestId("document-payment-panel");
  await expect(panel).toBeVisible({ timeout: 15_000 });
  return panel;
}

test("تقسيم 60 نقداً و40 شيكاً يُنزل «المتبقي» إلى صفر حيّاً", async ({ page }) => {
  const panel = await openPanel(page);
  await expect(page.getByTestId("payment-remaining")).toHaveText("100");

  await panel.getByLabel("المدفوع نقداً").fill("60");
  await expect(page.getByTestId("payment-remaining")).toHaveText("40");

  await panel.getByRole("button", { name: "شيك", exact: true }).click();
  await panel.getByLabel("رقم الشيك 1").fill("12345");
  await panel.getByLabel("بنك الشيك 1").fill("بنك فلسطين");
  await panel.getByLabel("استحقاق الشيك 1").fill("2026-09-01");
  await panel.getByLabel("مبلغ الشيك 1").fill("40");

  await expect(page.getByTestId("payment-cheques-total")).toHaveText("40");
  await expect(page.getByTestId("payment-remaining")).toHaveText("0");
  await expect(page.getByTestId("payment-overpay-note")).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/01-split-60-40-remaining-zero.png`, fullPage: true });
});

test("زرّ التحصيل يُطلق نداء /collect/ واحداً بالحمولة المتوقّعة", async ({ page }) => {
  const panel = await openPanel(page);

  await panel.getByLabel("المدفوع نقداً").fill("60");
  await panel.getByRole("button", { name: "شيك", exact: true }).click();
  await panel.getByLabel("رقم الشيك 1").fill("12345");
  await panel.getByLabel("بنك الشيك 1").fill("بنك فلسطين");
  await panel.getByLabel("استحقاق الشيك 1").fill("2026-09-01");
  await panel.getByLabel("مبلغ الشيك 1").fill("15");
  await panel.getByLabel("من رصيد العميل").fill("25");
  await expect(page.getByTestId("payment-remaining")).toHaveText("0");

  const collectRequest = page.waitForRequest((request) =>
    request.method() === "POST"
    && new URL(request.url()).pathname.endsWith("/sales/invoices/301/collect/"),
  );
  await page.getByTestId("payment-submit").click();
  const payload = (await collectRequest).postDataJSON();
  expect(payload).toEqual({
    cash: "60.00",
    cash_account_id: 10,
    cheques: [{
      cheque_number: "12345",
      amount: "15.00",
      due_date: "2026-09-01",
      bank_name: "بنك فلسطين",
    }],
    from_on_account: [{ payment_id: 91, amount: "25.00" }],
    post_invoice: false,
  });

  // الردّ يحمل الفاتورة بعد التحصيل — الشاشة تُحدَّث منه بلا جلب ثانٍ.
  await expect(page.getByText("سند قبض #777", { exact: false })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/02-collect-call-and-result.png`, fullPage: true });
});

test("الوضع السهل: اللوحة تظهر على مسودة جديدة وتحصّلها مع الترحيل", async ({ page }) => {
  // الفخّ المعروف: `tsc` لا يفحص خصائص JSX هنا، فالمهمّ أن يُظهرها **المستدعي**
  // فعلاً — في الوضعين، وعلى المسودة كما على المرحّلة.
  await installMocks(page, { simpleMode: true });
  await page.goto("/sales/invoices/new");
  await page.waitForLoadState("networkidle");
  await page.getByPlaceholder("اكتب اسم المنتج…").first().fill("لابتوب");
  await page.getByText("لابتوب", { exact: true }).last().click();

  const panel = page.getByTestId("document-payment-panel");
  await expect(panel).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("payment-remaining")).toHaveText("100");

  await panel.getByLabel("المدفوع نقداً").fill("100");
  await expect(page.getByTestId("payment-remaining")).toHaveText("0");
  await page.screenshot({ path: `${SHOTS}/04-simple-mode-draft-panel.png`, fullPage: true });

  const collectRequest = page.waitForRequest((request) =>
    request.method() === "POST"
    && new URL(request.url()).pathname.endsWith("/sales/invoices/302/collect/"),
  );
  await page.getByTestId("payment-submit").click();
  const payload = (await collectRequest).postDataJSON();
  expect(payload).toMatchObject({
    cash: "100.00",
    cash_account_id: 10,
    cheques: [],
    from_on_account: [],
    // المسودة تُرحَّل داخل نفس معاملة التحصيل — لا نداء ترحيل منفصل.
    post_invoice: true,
  });
  await expect(page.getByText("سند قبض #778", { exact: false })).toBeVisible();
});

test("تجاوز المتبقّي يُظهر تنبيه «الفائض يُسجَّل دفعة على الحساب»", async ({ page }) => {
  const panel = await openPanel(page);

  await panel.getByLabel("المدفوع نقداً").fill("130");
  await expect(page.getByTestId("payment-remaining")).toHaveText("0");
  const note = page.getByTestId("payment-overpay-note");
  await expect(note).toBeVisible();
  await expect(note).toHaveText("الفائض 30 يُسجَّل دفعة على الحساب.");
  await page.screenshot({ path: `${SHOTS}/03-overpayment-notice.png`, fullPage: true });
});
