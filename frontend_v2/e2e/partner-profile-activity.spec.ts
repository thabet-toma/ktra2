import { expect, test } from "@playwright/test";

test.use({ serviceWorkers: "block" });

test("partner statement sorting and related activity use the partner scope", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("token", "partner-profile-token");
    localStorage.setItem("userId", "partner-profile-user");
    localStorage.setItem("tenantId", "1");
  });

  const statementOrderRequests: string[] = [];
  const activityPartnerRequests: string[] = [];
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/partner-profile-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "partner-profile-user",
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
            CreatedAt: "2026-07-23T00:00:00Z",
          },
          role: "manager",
          is_default: true,
          created_at: "2026-07-23T00:00:00Z",
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
          permissions: ["sales.customer.view", "purchase.supplier.view"],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/7/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: 7,
          name: "مورد الاختبار",
          partner_type: "Supplier",
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/7/profile/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          balance: "0",
          balance_side: "Cr",
          outstanding_balance: "0",
          total_sales: "0",
          total_purchases: "0",
          last_transaction_date: null,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/7/statement/")) {
      const ordering = url.searchParams.get("ordering") || "";
      statementOrderRequests.push(ordering);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ results: [], count: 0, ordering }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/7/invoices/")) {
      await route.fulfill({ contentType: "application/json", body: "[]" });
      return;
    }
    if (url.pathname.endsWith("/activity/")) {
      activityPartnerRequests.push(url.searchParams.get("partner_id") || "");
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 91,
            action: "update",
            action_label: "تعديل",
            is_view: false,
            entity_type: "purchase_invoice",
            entity_id: 8,
            entity_label: "INV-0008",
            description: "تعديل فاتورة شراء",
            metadata: {},
            user: 5,
            user_name: "ثابت طعمه",
            ip_address: "127.0.0.1",
            timestamp: "2026-07-23T08:12:00Z",
          },
          {
            id: 92,
            action: "post",
            action_label: "ترحيل",
            is_view: false,
            entity_type: "supplier_payment",
            entity_id: 55,
            entity_label: "#55",
            description: "ترحيل سند صرف مورد",
            metadata: {},
            user: 5,
            user_name: "ثابت طعمه",
            ip_address: "127.0.0.1",
            timestamp: "2026-07-23T08:13:00Z",
          },
        ]),
      });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/partners/7?tab=statement");
  const statementTab = page.getByRole("tab", { name: "كشف الحساب" });
  await expect(statementTab).toBeVisible({ timeout: 15000 });
  await statementTab.click();
  const ordering = page.getByLabel("ترتيب الحركات:");
  await expect(ordering).toHaveValue("newest", { timeout: 15000 });
  await expect.poll(() => statementOrderRequests).toContain("newest");

  await ordering.selectOption("oldest");
  await expect.poll(() => statementOrderRequests.at(-1)).toBe("oldest");

  await page.getByRole("tab", { name: "سجل النشاطات" }).click();
  await expect.poll(() => activityPartnerRequests).toContain("7");
  await expect(page.getByText("INV-0008")).toBeVisible();
  await expect(page.getByRole("button", { name: "سند صرف #55" })).toBeVisible();
  await expect(page.getByText("ثابت طعمه").first()).toBeVisible();

  await page.getByRole("button", { name: /فاتورة شراء INV-0008/ }).click();
  await expect(page).toHaveURL(/\/purchase-invoices\/8$/);
});

test("new customer receipt stays inside the profile and uses saved cheque defaults", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("token", "partner-profile-token");
    localStorage.setItem("userId", "partner-profile-user");
    localStorage.setItem("tenantId", "1");
  });

  let createdPayment: Record<string, unknown> | null = null;
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/partner-profile-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "partner-profile-user",
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
            CreatedAt: "2026-07-23T00:00:00Z",
          },
          role: "manager",
          is_default: true,
          created_at: "2026-07-23T00:00:00Z",
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
          permissions: ["sales.customer.view", "sales.payment.create"],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/8/payment-defaults/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          partner_id: 8,
          partner_name: "عميل الاختبار",
          direction: "Incoming",
          selected_bank_account: {
            id: 19,
            bank_name: "بنك القدس",
            account_number: "123-456",
            branch_name: "رام الله",
            beneficiary_name: "عميل الاختبار",
            currency: 1,
            is_active: true,
            is_default: true,
          },
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/8/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: 8,
          name: "عميل الاختبار",
          partner_type: "Customer",
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/8/profile/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          balance: "0",
          balance_side: "Dr",
          outstanding_balance: "0",
          total_sales: "0",
          total_purchases: "0",
          last_transaction_date: null,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/8/statement/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ results: [], count: 0, ordering: "newest" }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/8/invoices/") || url.pathname.endsWith("/activity/")) {
      await route.fulfill({ contentType: "application/json", body: "[]" });
      return;
    }
    if (url.pathname.endsWith("/accounting/accounts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 11,
          code: "1101",
          name: "الصندوق",
          account_type: "Asset",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/accounting/currencies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ CurrencyID: 1, Code: "ILS", Name: "شيكل" }]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/reports/aging/")) {
      await route.fulfill({ contentType: "application/json", body: "[]" });
      return;
    }
    if (url.pathname.endsWith("/settings/current/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ default_cash_account: 11 }),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/payments/") && request.method() === "POST") {
      createdPayment = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: 41,
          ...createdPayment,
          journal: null,
          is_posted: false,
          allocations: [],
        }),
      });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/partners/8");
  await page.getByRole("button", { name: "سند قبض جديد" }).click();

  await expect(page).toHaveURL(/\/partners\/8$/);
  await expect(page.getByRole("heading", { name: "سند قبض جديد" })).toBeVisible();
  await expect(page.getByText("العميل *").locator("..").getByRole("textbox")).toHaveValue("عميل الاختبار");

  await page.getByRole("button", { name: "شيك", exact: true }).click();
  const chequeRow = page.locator("table tbody tr").last();
  const chequeInputs = chequeRow.locator("input");
  await expect(chequeInputs.nth(1)).toHaveValue("123-456");
  await expect(chequeInputs.nth(2)).toHaveValue("عميل الاختبار");
  await expect(chequeInputs.nth(5)).toHaveValue("بنك القدس");
  await expect(chequeInputs.nth(6)).toHaveValue("رام الله");
  await chequeInputs.nth(0).fill("CHK-125");
  await chequeInputs.nth(3).fill("2026-08-20");
  await chequeInputs.nth(4).fill("125");
  await page.getByRole("button", { name: "حفظ", exact: true }).click();

  await expect.poll(() => createdPayment).not.toBeNull();
  expect(createdPayment).toMatchObject({
    partner: 8,
    amount: "125.00",
    cash_or_bank_account: 11,
    cheques: [{
      cheque_number: "CHK-125",
      amount: "125",
      bank_name: "بنك القدس",
      account_number: "123-456",
      bank_branch: "رام الله",
      payee_name: "عميل الاختبار",
      due_date: "2026-08-20",
    }],
  });
  expect(createdPayment).not.toHaveProperty("allocations");
  await expect(page.getByRole("heading", { name: "سند قبض جديد" })).toHaveCount(0);
  await expect(page).toHaveURL(/\/partners\/8$/);
});
