/**
 * THA-132 — تبويبات سياق الفاتورة: برهان الكسل **بالقياس** لا بالثقة.
 *
 * معيار المهمة: «فتح فاتورة لا يُصدر أي نداء إضافي حتى يُفتح تبويب». هنا يُعدّ
 * كل نداء لنقاط التبويبات الثلاث: صفرٌ بعد فتح الفاتورة، وواحدٌ لكل تبويب عند
 * فتحه، ولا يتكرّر بالعودة إليه (`KitDocumentShell` يبقي التبويب النشط وحده
 * مركَّباً، والمكوّن لا يُعيد الجلب لنفس الفاتورة).
 *
 * ويثبت الاختبار أيضاً أن «الرصيد قبل/بعد» المعروض يأتي من **مرساة كشف
 * الحساب** لا من حسابٍ في الواجهة: الفاتورة هنا مدفوعة بالكامل، والحساب القديم
 * كان يُظهر أثراً صفرياً بينما الصحيح كامل الإجمالي.
 */
import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const INVOICE_ID = 501;

const invoice = {
  id: INVOICE_ID,
  invoice_number: "SI-501",
  invoice_date: "2026-08-10",
  due_date: "2026-09-10",
  customer: 8,
  customer_name: "عميل السياق",
  invoice_type: "credit",
  invoice_kind: "sale",
  status: "posted",
  currency: 1,
  exchange_rate: "1",
  subtotal_excl_tax: "1000.00",
  invoice_discount: "0.00",
  tax_amount: "0.00",
  grand_total: "1000.00",
  amount_paid: "1000.00",
  remaining_balance: "0.00",
  payment_status: "paid",
  payment_status_display: "مدفوعة بالكامل",
  journal: 77,
  stock_movement_no: 9101,
  stock_on_post: true,
  lines: [],
  payment_details: [],
};

interface Counters {
  stock: number;
  ledger: number;
  attachments: number;
}

async function installMocks(page: Page, counters: Counters) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "ctx-tabs-token");
    localStorage.setItem("userId", "ctx-tabs-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    // ── النقاط الثلاث المقيسة ────────────────────────────────────────────
    if (url.pathname.endsWith(`/sales/invoices/${INVOICE_ID}/stock-movements/`)) {
      counters.stock += 1;
      return json({
        results: [{
          id: 9101,
          date: "2026-08-10",
          movement_type: "OUT",
          movement_type_label: "صرف / بيع",
          reference_type: "SALE",
          product_id: 42,
          product_name: "لابتوب",
          warehouse: "المستودع الرئيسي",
          qty_in: "0",
          qty_out: "10.0000",
          quantity_before: "100.0000",
          running_balance: "90.0000",
          unit_cost: "60.0000",
          total_cost: "600.00",
        }],
        count: 1,
        total_cost: "600.00",
        is_posted: true,
        stock_on_post: true,
        delivery_status: "delivered",
        delivery_status_display: "مسلَّمة",
      });
    }
    if (url.pathname.endsWith(`/sales/invoices/${INVOICE_ID}/customer-ledger/`)) {
      counters.ledger += 1;
      return json({
        results: [
          {
            id: 1, journal_id: 77, date: "2026-08-10",
            reference_type: "SALES_INVOICE", reference_id: INVOICE_ID,
            description: "فاتورة مبيعات SI-501",
            debit: "1000.00", credit: "0.00",
            balance_before: "250.00", running_balance: "1250.00",
            is_anchor: true,
          },
          {
            id: 2, journal_id: 78, date: "2026-08-11",
            reference_type: "CUSTOMER_PAYMENT", reference_id: 900,
            description: "سند قبض",
            debit: "0.00", credit: "1000.00",
            balance_before: "1250.00", running_balance: "250.00",
            is_anchor: false,
          },
        ],
        count: 2,
        closing_balance: "250.00",
        customer_name: "عميل السياق",
        anchor: {
          line_ids: [1],
          balance_before: "250.00",
          balance_after: "1250.00",
          effect: "1000.00",
        },
      });
    }
    if (url.pathname.endsWith(`/sales/invoices/${INVOICE_ID}/attachments/`)) {
      counters.attachments += 1;
      return json([]);
    }

    // ── حمولة الإقلاع ────────────────────────────────────────────────────
    if (url.pathname.endsWith("/hr/users/ctx-tabs-user/")) {
      return json({
        id: "ctx-tabs-user", name: "مستخدم السياق", role: "manager",
        email: "ctx@example.test", employmentStatus: "active",
        isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: "KTRA", SubscriptionPlan: "Enterprise",
          Status: "Active", CreatedAt: "2026-08-01T00:00:00Z",
        },
        role: "manager", is_default: true, created_at: "2026-08-01T00:00:00Z",
      }]);
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return json({
        role: "manager", is_manager: true, ui_mode: "advanced",
        permissions: [
          "sales.invoice.view", "sales.invoice.edit",
          "sales.invoice.create", "sales.invoice.post",
        ],
      });
    }
    if (url.pathname.endsWith(`/sales/invoices/${INVOICE_ID}/`)) return json(invoice);
    if (url.pathname.endsWith("/accounting/currencies/")) {
      return json([{ CurrencyID: 1, Code: "ILS" }]);
    }
    if (url.pathname.endsWith("/sales/settings/current/")) {
      return json({ default_currency: 1, default_customer: 8 });
    }
    return json([]);
  });
}

const openTab = async (page: Page, label: string) => {
  await page.getByRole("tab", { name: label }).click();
};

test("فتح الفاتورة لا يُصدر نداء تبويب، وكل تبويب يُجلب مرّة عند فتحه", async ({ page }) => {
  const counters: Counters = { stock: 0, ledger: 0, attachments: 0 };
  await installMocks(page, counters);

  await page.goto(`/sales/invoices/${INVOICE_ID}`);
  await expect(page.getByRole("tab", { name: "حركة المخزون" })).toBeVisible();
  // مهلة تكفي لأي جلب متأخّر لو كان التركيب متعجّلاً.
  await page.waitForTimeout(700);

  // ── معيار النجاح: صفر نداءات قبل فتح أي تبويب.
  expect(counters).toEqual({ stock: 0, ledger: 0, attachments: 0 });

  // كل تبويب يجلب **بياناته وحدها** عند فتحه، ولا يوقظ جيرانه.
  // السقف 2 لا 1: `React.StrictMode` (`index.tsx`) يفكّ الـeffects ويعيد
  // تركيبها مرّةً في التطوير عمداً — أثرٌ معروف في هذا المستودع
  // (`e2e/pw-offline-test-utils.ts`) ولا وجود له في الإنتاج. السقف يبقى
  // حارساً ضدّ حلقة جلبٍ هاربة، والصفرُ أعلاه هو معيار المهمة نفسه.
  await openTab(page, "حركة المخزون");
  await expect.poll(() => counters.stock).toBeGreaterThan(0);
  expect(counters.stock).toBeLessThanOrEqual(2);
  expect(counters.ledger).toBe(0);
  expect(counters.attachments).toBe(0);

  await openTab(page, "حساب العميل");
  await expect.poll(() => counters.ledger).toBeGreaterThan(0);
  expect(counters.ledger).toBeLessThanOrEqual(2);
  expect(counters.attachments).toBe(0);

  await openTab(page, "المرفقات");
  await expect.poll(() => counters.attachments).toBeGreaterThan(0);
  expect(counters.attachments).toBeLessThanOrEqual(2);

  // العودة إلى تبويب لا تُصدر نداءً لغيره.
  const before = { ...counters };
  await openTab(page, "حركة المخزون");
  await page.waitForTimeout(400);
  expect(counters.ledger).toBe(before.ledger);
  expect(counters.attachments).toBe(before.attachments);
});

test("تبويب حساب العميل يعرض قبل/بعد من مرساة كشف الحساب", async ({ page }) => {
  const counters: Counters = { stock: 0, ledger: 0, attachments: 0 };
  await installMocks(page, counters);

  await page.goto(`/sales/invoices/${INVOICE_ID}`);
  await openTab(page, "حساب العميل");

  // الفاتورة مدفوعة بالكامل: الحساب القديم كان يُظهر أثراً صفرياً — هنا 1,000.
  await expect(page.getByText("أثر الفاتورة")).toBeVisible();
  await expect(page.getByText("الرصيد قبل الفاتورة")).toBeVisible();
  await expect(page.getByText("الرصيد بعدها")).toBeVisible();
  await expect(page.locator("text=1,250").first()).toBeVisible();
});

test("حركة المخزون تعرض رقم الحركة ورصيد الصنف قبل وبعد", async ({ page }) => {
  const counters: Counters = { stock: 0, ledger: 0, attachments: 0 };
  await installMocks(page, counters);

  await page.goto(`/sales/invoices/${INVOICE_ID}`);
  await openTab(page, "حركة المخزون");

  await expect(page.getByText("لابتوب")).toBeVisible();
  await expect(page.locator("text=9101").first()).toBeVisible();
});

test("شريط الحالة يحمل رقم الحركة المخزنية (سلوك الأصيل)", async ({ page }) => {
  const counters: Counters = { stock: 0, ledger: 0, attachments: 0 };
  await installMocks(page, counters);

  await page.goto(`/sales/invoices/${INVOICE_ID}`);

  const status = page.locator(".ktra-statusbar");
  await expect(status).toContainText("رقم الحركة");
  await expect(status).toContainText("9101");
  // ولم يكلّف ذلك نداءً: الرقم يصل مع حمولة الفاتورة.
  expect(counters.stock).toBe(0);
});
