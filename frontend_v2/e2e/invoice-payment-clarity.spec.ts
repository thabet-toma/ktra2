import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

async function installMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "invoice-clarity-token");
    localStorage.setItem("userId", "invoice-clarity-user");
    localStorage.setItem("tenantId", "1");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/invoice-clarity-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "invoice-clarity-user",
          name: "مدير الفواتير",
          role: "manager",
          email: "invoice@example.test",
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
            CreatedAt: "2026-07-23T00:00:00Z",
            import_enabled: true,
          },
          role: "manager",
          is_default: true,
          created_at: "2026-07-23T00:00:00Z",
          can_access_import: true,
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
          permissions: [
            "sales.invoice.view",
            "sales.payment.create",
            "purchase.invoice.view",
            "import.deal.manage",
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/lookup/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ id: 8, name: "عميل واضح", partner_type: "Customer" }]),
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
        body: JSON.stringify([{ id: 10, code: "1101", name: "الصندوق الرئيسي", account_type: "Asset" }]),
      });
      return;
    }
    /* T-CASHBOX M1: الصندوق الافتراضي يُحلّ من **الصناديق المسجَّلة** لا من أوّل
       حساب نقدي في الشجرة — فبلا هذين المُوجِّهَين تبقى اللوحة بلا صندوق ويرفض
       زرُّ التحصيل الإرسال. */
    if (url.pathname.endsWith("/accounting/cash-box-accounts/my-default/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ cash_box: 1, cash_box_name: "الصندوق الرئيسي" }),
      });
      return;
    }
    if (url.pathname.endsWith("/accounting/cash-box-accounts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 1, name: "الصندوق الرئيسي", account_id: 10, account_code: "1101",
          currency_code: "ILS", is_default: true, is_active: true,
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/settings/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ default_cash_account: 10 }),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/payments/91/allocate/")) {
      await route.fulfill({ contentType: "application/json", body: "{}" });
      return;
    }
    // T4: تحصيل الفاتورة من لوحتها — الردّ هو الفاتورة بعد التحصيل + رقم السند.
    if (url.pathname.endsWith("/sales/invoices/145/collect/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: 145,
          invoice_number: "SI-6-145",
          invoice_date: "2026-07-22",
          customer: 8,
          invoice_type: "credit",
          status: "posted",
          currency: 1,
          exchange_rate: "1",
          grand_total: "1000.00",
          amount_paid: "700.00",
          remaining_balance: "300.00",
          payment_status: "partially_paid",
          payment_status_display: "مدفوعة جزئياً",
          journal: 41,
          lines: [],
          payment_details: [],
          payment_id: 93,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/payments/")) {
      if (route.request().method() === "POST") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ id: 92, is_posted: true, auto_post_error: "" }),
        });
        return;
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 91,
          payment_date: "2026-07-24",
          amount: "300.00",
          unallocated_amount: "300.00",
          is_posted: true,
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/credit-debit-notes/")) {
      await route.fulfill({ contentType: "application/json", body: "[]" });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/145/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: 145,
          invoice_number: "SI-6-145",
          invoice_date: "2026-07-22",
          due_date: "2026-08-22",
          customer: 8,
          customer_name: "عميل واضح",
          invoice_type: "credit",
          status: "posted",
          currency: 1,
          exchange_rate: "1",
          subtotal_excl_tax: "1000.00",
          invoice_discount: "0.00",
          tax_amount: "0.00",
          grand_total: "1000.00",
          amount_paid: "400.00",
          remaining_balance: "600.00",
          payment_status: "partially_paid",
          payment_status_display: "مدفوعة جزئياً",
          customer_balance_before_invoice: "200.00",
          customer_balance_after_invoice: "800.00",
          journal: 41,
          stock_on_post: true,
          lines: [],
          payment_details: [{
            id: 77,
            payment_date: "2026-07-23",
            allocated_amount: "400.00",
            total_payment_amount: "400.00",
            currency_code: "ILS",
            exchange_rate: "1",
            is_posted: true,
            journal: 72,
            notes: "",
          }],
        }),
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
            id: 145,
            invoice_number: "SI-6-145",
            invoice_date: "2026-07-22",
            customer: 8,
            customer_name: "عميل واضح",
            invoice_type: "credit",
            status: "posted",
            grand_total: "1000.00",
            amount_paid: "400.00",
            remaining_balance: "600.00",
            payment_status: "partially_paid",
            payment_status_display: "مدفوعة جزئياً",
            customer_balance: "1600.00",
          }],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/logistics/purchase-invoices/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          next: null,
          previous: null,
          results: [{
            id: 15,
            invoice_number: "INV-0015",
            invoice_name: "",
            invoice_date: "2026-07-09",
            invoice_type: "local",
            partner: 22,
            partner_name: "المورد الظاهر",
            currency_code: "ILS",
            exchange_rate: 1,
            subtotal: 900,
            discount_amount: 0,
            tax_rate: 0,
            tax_amount: 0,
            grand_total: 900,
            payable_total: "900.00",
            amount_paid: "300.00",
            remaining_balance: "600.00",
            payment_status: "partially_paid",
            payment_status_display: "مدفوعة جزئياً",
            supplier_balance: "1200.00",
            status: "completed",
            status_display: "مكتملة",
            is_posted: true,
            is_return: false,
            items_count: 1,
            created_at: "2026-07-09T00:00:00Z",
            updated_at: "2026-07-09T00:00:00Z",
          }],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/logistics/purchase-invoices/15/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: 15,
          invoice_number: "INV-0015",
          invoice_date: "2026-07-09",
          invoice_type: "local",
          partner: 22,
          partner_name: "المورد الظاهر",
          currency: "ILS",
          currency_code: "ILS",
          exchange_rate: 1,
          subtotal: 900,
          discount_amount: 0,
          tax_rate: 0,
          tax_amount: 0,
          grand_total: 900,
          payable_total: "900.00",
          amount_paid: "300.00",
          remaining_balance: "600.00",
          payment_status: "partially_paid",
          payment_status_display: "مدفوعة جزئياً",
          supplier_balance_current: "1200.00",
          supplier_balance_before_invoice: "600.00",
          supplier_balance_after_invoice: "1200.00",
          status: "completed",
          is_posted: true,
          items: [],
          fees: [],
          payment_details: [{
            source: "supplier_payment",
            id: 12,
            payment_date: "2026-07-23",
            amount: "300.00",
            currency_code: "ILS",
            exchange_rate: "1",
            cash_or_bank_account_name: "الصندوق",
            is_posted: true,
            journal: 88,
          }],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/logistics/deals/9/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: 9,
          ref_number: "D-0009",
          partner: 22,
          partner_name: "المورد الظاهر",
          status: "Open",
          total_amount: "1000.00",
          posted_paid_amount: "400.00",
          unposted_registered_amount: "200.00",
          amount_outstanding: "600.00",
          supplier_advance: "0.00",
          payment_status_summary: "partially_paid",
          supplier_balance_current: "-400.00",
          supplier_balance_before_deal_payments: "0.00",
          supplier_balance_after_deal_payments: "-400.00",
          items: [],
          payments: [{
            id: 5,
            amount: "400.00",
            payment_number: 1,
            title: "دفعة",
            transfer_date: "2026-07-23",
            is_posted: true,
            journal: 99,
          }, {
            id: 6,
            amount: "200.00",
            payment_number: 2,
            title: "دفعة",
            transfer_date: "2026-07-23",
            is_posted: false,
            journal: null,
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

test("credit and debit note choices explain their customer impact", async ({ page }) => {
  await installMocks(page);
  await page.goto("/sales/credit-debit-notes");
  await page.getByRole("button", { name: "إشعار جديد", exact: true }).last().click();

  await expect(page.getByText("ينقص المبلغ المطلوب من العميل", { exact: false })).toBeVisible();
  await expect(page.getByText("العميل", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("الحساب (العميل/المورد)", { exact: true })).toHaveCount(0);

  await page.getByLabel("النوع").selectOption("debit");
  await expect(page.getByText("يزيد المبلغ المطلوب من العميل", { exact: false })).toBeVisible();
});

test("sales and purchase lists show payment state remaining and partner balance", async ({ page }) => {
  await installMocks(page);
  await page.goto("/sales/invoices");
  await expect(page.locator(".ktra-grid")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("حالة الدفع", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".ktra-grid").getByText("مدفوعة جزئياً", { exact: true })).toBeVisible();
  await expect(page.getByText("رصيد العميل", { exact: true })).toBeVisible();
  await expect(page.locator(".ktra-grid").getByText("600", { exact: true })).toBeVisible();
  const salesFilterRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/sales/invoices/")
      && url.searchParams.get("payment_status") === "partially_paid";
  });
  await page.getByRole("combobox", { name: "حالة الدفع" }).selectOption("partially_paid");
  await salesFilterRequest;

  await page.goto("/purchase-invoices");
  await expect(page.locator(".ktra-grid")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("المورد الظاهر", { exact: true })).toBeVisible();
  await expect(page.getByText("حالة الدفع", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".ktra-grid").getByText("مدفوعة جزئياً", { exact: true })).toBeVisible();
  await expect(page.getByText("رصيد المورد", { exact: true })).toBeVisible();
  const purchaseFilterRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/logistics/purchase-invoices/")
      && url.searchParams.get("payment_status") === "partially_paid";
  });
  await page.getByRole("combobox", { name: "حالة الدفع" }).selectOption("partially_paid");
  await purchaseFilterRequest;
});

test("invoice and deal documents show posted pending remaining balances and payment rows", async ({ page }) => {
  await installMocks(page);

  await page.goto("/sales/invoices/145");
  await expect(page.getByText("المدفوع المرحّل", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  const notesRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/customer-notes/")
      && url.searchParams.get("target_type") === "page"
      && url.searchParams.get("target_id") === "/sales/invoices/145";
  });
  await page.getByRole("button", { name: "ملاحظة أو تذكير على الصفحة الحالية" }).click();
  await expect(page.getByRole("dialog", { name: "ملاحظات وتذكيرات الصفحة" })).toBeVisible();
  await notesRequest;
  await page.getByRole("button", { name: "إغلاق ملاحظات الصفحة" }).click();

  /* T-INTENT: الجدول انتقل إلى `InvoicePaymentsSection` المشترك ويُعرض في
     وضعَي التحرير والعرض معاً — كان في وضع العرض وحده، أي أنّ من يحرّر فاتورته
     لا يرى دفعاتها إطلاقاً. */
  const paymentsSection = page.getByTestId("invoice-payments-section");
  await expect(paymentsSection).toBeVisible();
  await expect(paymentsSection.getByText("سندات القبض والدفعات")).toBeVisible();
  await expect(paymentsSection.getByText("#77")).toBeVisible();
  /* THA-132 قلَب هذا التوقّع: سطرا «رصيد العميل قبل/بعد» أُزيلا من لوحة
     المجاميع لأن رقمهما كان كاذباً (المتبقّي مطروحاً من رصيد **اليوم**، بينما
     قيد الفاتورة يدين الذمم بكامل الإجمالي والتحصيل قيد منفصل). فالتوقّع صار
     سالباً — لا يعودان — والوعدُ الصحيح (قبل/الأثر/بعد من مرساة كشف الحساب)
     يحرسه `e2e/sales-invoice-context-tabs.spec.ts` على تبويب «حساب العميل». */
  await expect(page.getByText(/رصيد العميل .* احتساب/)).toHaveCount(0);
  /* والزرّ صار يقول ما يفعله: كان مكتوباً عليه «طباعة السند» وهو يفتح قائمة
     السندات مصفّاةً — تسميةٌ تَعِد بما لا تفعل. */
  const printButton = page.getByRole("button", { name: "فتح سند قبض #77" });
  await expect(printButton).toBeVisible();
  const [receiptPage] = await Promise.all([
    page.waitForEvent("popup"),
    printButton.click(),
  ]);
  await expect(receiptPage).toHaveURL(/\/sales\/customer-payments\?payment_id=77$/);
  await receiptPage.close();

  /* T4: التحصيل صار داخل الشاشة لا في نافذة — الزر يُنزل إلى اللوحة، والنقد
     والرصيد على الحساب يخرجان في نداء `collect/` واحد بدل نداءين. */
  await page.getByRole("button", { name: "سند قبض", exact: true }).first().click();
  const collectPanel = page.getByTestId("document-payment-panel");
  await expect(collectPanel).toBeVisible();
  await expect(page.getByTestId("payment-remaining")).toHaveText("600");

  await collectPanel.getByLabel("المدفوع نقداً").fill("175");
  await expect(page.getByTestId("payment-remaining")).toHaveText("425");
  await collectPanel.getByLabel("من رصيد العميل").fill("125");
  await expect(page.getByTestId("payment-remaining")).toHaveText("300");

  const collectRequest = page.waitForRequest((request) =>
    request.method() === "POST"
    && new URL(request.url()).pathname.endsWith("/sales/invoices/145/collect/"),
  );
  await page.getByTestId("payment-submit").click();
  expect((await collectRequest).postDataJSON()).toEqual({
    cash: "175.00",
    cash_account_id: 10,
    cheques: [],
    from_on_account: [{ payment_id: 91, amount: "125.00" }],
    post_invoice: false,
  });

  await page.goto("/purchase-invoices/15");
  await expect(page.getByText("تفاصيل دفعات المورد (1)", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("سند صرف #12", { exact: true })).toBeVisible();
  await expect(page.getByText("رصيد المورد الحالي بعد احتسابه (بالعملة الأساسية)", { exact: true })).toBeVisible();

  await page.goto("/deals/9");
  await expect(page.getByText("المدفوع والمرحّل", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("مسجّل بانتظار الترحيل", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("رصيد المورد الحالي بعد الدفعات المرحّلة (بالعملة الأساسية)", { exact: true })).toBeVisible();
});
