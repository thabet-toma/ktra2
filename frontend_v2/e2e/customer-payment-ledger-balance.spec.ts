import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const json = (route: Route, body: unknown, status = 200) => route.fulfill({
  status,
  contentType: "application/json",
  body: JSON.stringify(body),
});

async function installMocks(page: Page, options: {
  failFirstBalance?: boolean;
  delayFirstBalance?: boolean;
} = {}) {
  let balance8Attempts = 0;

  await page.addInitScript(() => {
    localStorage.setItem("token", "customer-payment-balance-token");
    localStorage.setItem("userId", "customer-payment-balance-user");
    localStorage.setItem("tenantId", "1");
  });

  await page.route(/(?:\/api\/|:8000\/)/, async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname.endsWith("/hr/users/customer-payment-balance-user/")) {
      return json(route, {
        id: "customer-payment-balance-user",
        name: "مدير التحصيل",
        role: "manager",
        email: "payments@example.test",
        employmentStatus: "active",
        isApproved: true,
        isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return json(route, [{
        id: 1,
        tenant: {
          TenantID: 1,
          CompanyName: "شركة التحصيل",
          SubscriptionPlan: "Enterprise",
          Status: "Active",
          CreatedAt: "2026-09-01T00:00:00Z",
          import_enabled: true,
        },
        role: "manager",
        is_default: true,
        created_at: "2026-09-01T00:00:00Z",
        can_access_import: true,
      }]);
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return json(route, {
        role: "manager",
        is_manager: true,
        modules: {},
        ui_mode: "advanced",
        permissions: [
          "sales.payment.view",
          "sales.payment.create",
          "sales.payment.post",
        ],
      });
    }
    if (url.pathname.endsWith("/partners/lookup/")) {
      return json(route, [
        { id: 8, name: "عميل مدين", partner_type: "Customer" },
        { id: 9, name: "عميل دائن", partner_type: "Customer" },
        { id: 10, name: "عميل متوازن", partner_type: "Customer" },
      ]);
    }
    if (url.pathname.endsWith("/accounting/accounts/")) {
      return json(route, [{ id: 10, code: "1101", name: "الصندوق", account_type: "Asset" }]);
    }
    if (url.pathname.endsWith("/accounting/currencies/")) {
      return json(route, [{ CurrencyID: 1, Code: "ILS" }]);
    }
    if (
      url.pathname.endsWith("/accounting/cash-box-accounts/my-default/")
      || url.pathname.endsWith("/accounting/cash-box-accounts/")
    ) {
      return json(route, []);
    }
    if (url.pathname.endsWith("/logistics/purchase-invoices/settings/")) {
      return json(route, {});
    }
    if (url.pathname.endsWith("/sales/settings/")) {
      return json(route, { default_cash_account: 10, auto_post_payments: true });
    }
    if (url.pathname.endsWith("/sales/reports/aging/")) {
      return json(route, [
        {
          invoice_id: 81,
          invoice_number: "SI-81",
          customer_id: 8,
          customer_name: "عميل مدين",
          invoice_date: "2026-09-01",
          grand_total: "400.00",
          amount_paid: "100.00",
          remaining: "300.00",
          invoice_kind: "sale",
        },
        {
          invoice_id: 82,
          invoice_number: "SR-82",
          customer_id: 8,
          customer_name: "عميل مدين",
          invoice_date: "2026-09-02",
          grand_total: "50.00",
          amount_paid: "0.00",
          remaining: "50.00",
          invoice_kind: "sale_return",
        },
      ]);
    }
    if (url.pathname.endsWith("/sales/payments/")) {
      return json(route, [{
        id: 91,
        partner: 8,
        partner_name: "عميل مدين",
        payment_date: "2026-09-20",
        amount: "300.00",
        unallocated_amount: "300.00",
        cash_or_bank_account: 10,
        is_posted: true,
        allocations: [],
      }]);
    }
    const balanceMatch = url.pathname.match(/\/partners\/(8|9|10)\/balance\/$/);
    if (balanceMatch) {
      const partnerId = Number(balanceMatch[1]);
      if (partnerId === 8) {
        balance8Attempts += 1;
        if (options.failFirstBalance && balance8Attempts === 1) {
          await new Promise((resolve) => setTimeout(resolve, 150));
          return json(route, { detail: "temporary failure" }, 503);
        }
        if (options.delayFirstBalance && balance8Attempts === 1) {
          await new Promise((resolve) => setTimeout(resolve, 150));
        }
      }
      const openBalance = partnerId === 8 ? "275.00" : partnerId === 9 ? "-125.00" : "0.00";
      return json(route, {
        partner: partnerId,
        partner_type: "Customer",
        debit: "0.00",
        credit: "0.00",
        open_balance: openBalance,
        proposed_total: "0.00",
        projected_balance: openBalance,
      });
    }
    if (url.pathname.includes("/payment-defaults/")) {
      return json(route, { selected_bank_account: null });
    }
    if (url.pathname.endsWith("/dashboard/")) return json(route, {});
    return json(route, []);
  });
}

test("سند القبض يشرح رصيد العميل ويتيح إعادة الجلب ويستبعد المرتجع من التوزيع", async ({ page }) => {
  await installMocks(page, { failFirstBalance: true });
  await page.goto("/sales/customer-payments");
  await page.getByRole("button", { name: /سند قبض جديد/ }).click();

  const customer = page.getByLabel("العميل *");
  await customer.selectOption("8");
  const balance = page.getByTestId("customer-ledger-balance");
  await expect(balance).toContainText("جارٍ تحميل رصيد العميل");
  await expect(balance).toContainText("تعذّر تحميل رصيد العميل");
  await balance.getByRole("button", { name: "إعادة المحاولة" }).click();
  await expect(balance).toContainText("على العميل 275");

  await customer.selectOption("9");
  await expect(balance).toContainText("للعميل 125");

  await customer.selectOption("10");
  await expect(balance).toContainText("الرصيد متوازن");

  await customer.selectOption("8");
  await expect(balance).toContainText("على العميل 275");
  await expect(page.getByRole("option", { name: /SI-81/ })).toHaveCount(1);
  await expect(page.getByRole("option", { name: /SR-82/ })).toHaveCount(0);
});

test("تبديل العميل لا يسمح لاستجابة الرصيد المتأخرة أن تستبدل الرصيد الحالي", async ({ page }) => {
  await installMocks(page, { delayFirstBalance: true });
  await page.goto("/sales/customer-payments");
  await page.getByRole("button", { name: /سند قبض جديد/ }).click();

  const customer = page.getByLabel("العميل *");
  const balance = page.getByTestId("customer-ledger-balance");
  await customer.selectOption("8");
  await expect(balance).toContainText("جارٍ تحميل رصيد العميل");
  await customer.selectOption("9");
  await expect(balance).toContainText("للعميل 125");
  await page.waitForTimeout(200);
  await expect(balance).not.toContainText("على العميل 275");
});

test("نافذة توزيع سند قائم تعرض رصيد العميل", async ({ page }) => {
  await installMocks(page);
  await page.goto("/sales/customer-payments");
  await expect(page.locator(".ktra-grid")).toBeVisible({ timeout: 15_000 });

  await page.getByTitle("توزيع على الفواتير").click();
  const balance = page.getByTestId("customer-ledger-balance");
  await expect(balance).toContainText("على العميل 275");
  await expect(page.getByRole("option", { name: /SI-81/ })).toHaveCount(1);
  await expect(page.getByRole("option", { name: /SR-82/ })).toHaveCount(0);
});
