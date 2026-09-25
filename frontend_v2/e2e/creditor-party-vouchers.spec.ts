import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * الأطراف الدائنة غير «مورد» (مخلّص، وكيل شحن، ناقل): سند الصرف لهم افتراضياً،
 * وسند القبض خيارٌ ثانٍ صريح (استرداد). كرت المخلّص كان يعرض «سند قبض» كأنه عميل،
 * ونافذة سند الصرف كانت تفلتر على «مورد» وحده.
 */
test.use({ serviceWorkers: "block" });

type ApiResponder = (route: Route, url: URL) => Promise<boolean>;

async function installAuthenticatedApiMocks(page: Page, responder: ApiResponder) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "creditor-e2e-token");
    localStorage.setItem("userId", "creditor-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/creditor-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "creditor-e2e-user", name: "مدير", role: "manager", email: "m@example.test",
          employmentStatus: "active", isApproved: true, isEmailVerified: true,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager", is_manager: true, modules: {}, ui_mode: "advanced",
          permissions: ["purchase.supplier.view", "sales.customer.view", "purchase.payment.post"],
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
            TenantID: 1, CompanyName: "شركة الاختبار", SubscriptionPlan: "basic",
            Status: "active", CreatedAt: "2026-01-01T00:00:00Z", import_enabled: true,
          },
          role: "manager", is_default: true, created_at: "2026-01-01T00:00:00Z",
          can_access_import: true,
        }]),
      });
      return;
    }
    if (await responder(route, url)) return;
    if (url.pathname.includes("/mapper/activityStatus/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ isCurrentlyActive: true }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

const broker = { id: 83, name: "حاييم", partner_type: "CustomsBroker", supplier_scope: "" };

const profileResponder: ApiResponder = async (route, url) => {
  if (url.pathname.endsWith("/partners/83/")) {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(broker) });
    return true;
  }
  if (url.pathname.endsWith("/partners/83/profile/")) {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        balance: "24751.50", balance_side: "Cr", outstanding_balance: "24751.50",
        total_sales: "0", total_purchases: "0", last_transaction_date: null,
      }),
    });
    return true;
  }
  if (url.pathname.endsWith("/partners/83/statement/")) {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ results: [], count: 0 }) });
    return true;
  }
  return false;
};

test("customs broker card defaults to a payment voucher; receipt is the explicit refund option", async ({ page }) => {
  await installAuthenticatedApiMocks(page, profileResponder);
  await page.goto("/partners/83");

  await expect(page.getByText("مخلّص جمركي").first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("button", { name: "سند صرف جديد" })).toBeVisible();
  await expect(page.getByRole("button", { name: "سند قبض جديد" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "سند قبض (استرداد)" })).toBeVisible();

  await page.getByRole("button", { name: "سند صرف جديد" }).click();
  await expect(page.getByRole("heading", { name: "سند صرف جديد" })).toBeVisible();
  await expect(page.getByText("المورد / المستفيد *").locator("..").getByRole("textbox")).toHaveValue("حاييم");
});

test("payment voucher picker lists the broker, forwarder and carrier — not customers", async ({ page }) => {
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/partners/lookup/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          { id: 7, name: "مورد عادي", partner_type: "Supplier" },
          broker,
          { id: 35, name: "yoyo", partner_type: "FreightForwarder" },
          { id: 84, name: "اسامه", partner_type: "LocalTransporter" },
          { id: 90, name: "زبون", partner_type: "Customer" },
        ]),
      });
      return true;
    }
    return false;
  });
  await page.goto("/supplier-payments");
  await page.getByRole("button", { name: /^سند صرف جديد/ }).click();
  const picker = page.getByText("المورد / المستفيد *").locator("..").locator("select");
  await expect(picker).toBeVisible({ timeout: 15000 });
  const options = await picker.locator("option").allTextContents();
  expect(options).toContain("مورد عادي");
  expect(options).toContain("حاييم — مخلّص جمركي");
  expect(options).toContain("yoyo — وكيل شحن");
  expect(options).toContain("اسامه — ناقل محلي");
  expect(options.some((o) => o.includes("زبون"))).toBe(false);
});

test("broker statement: a voucher over three clearances stays one row with a subline in each group", async ({ page }) => {
  const row = (id: number, extra: Record<string, unknown>) => ({
    id, journal_id: id, date: "2026-08-0" + (id % 9), description: "", balance_before: "0",
    document_number: null, reference_kind: null, link_count: 1, link_targets: [], shipment_label: null, ...extra,
  });
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/partners/83/statement/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 3,
          closing_balance: "-4000.00",
          results: [
            row(3, {
              reference_type: "SUPPLIER_PAYMENT", reference_id: 2460, debit: "19000.00", credit: "0.00",
              running_balance: "-4000.00", link_key: null, link_count: 3,
              link_label: "3 مستحقات: SH-0019، SH-0014، SH-0015",
              link_targets: [
                { key: "LOGISTICS_CLEARANCE:14", label: "SH-0019 — داتا لوجر", amount: "9000.00" },
                { key: "LOGISTICS_CLEARANCE:12", label: "SH-0014 — ثلاجات", amount: "6000.00" },
                { key: "LOGISTICS_CLEARANCE:11", label: "SH-0015 — تلفزيونات", amount: "4000.00" },
              ],
            }),
            row(2, {
              reference_type: "LOGISTICS_CLEARANCE", reference_id: 14, debit: "0.00", credit: "9000.00",
              running_balance: "15000.00", link_key: "LOGISTICS_CLEARANCE:14", link_label: "SH-0019 — داتا لوجر",
            }),
            row(1, {
              reference_type: "LOGISTICS_CLEARANCE", reference_id: 12, debit: "0.00", credit: "6000.00",
              running_balance: "6000.00", link_key: "LOGISTICS_CLEARANCE:12", link_label: "SH-0014 — ثلاجات",
            }),
          ],
        }),
      });
      return true;
    }
    return profileResponder(route, url);
  });
  await page.goto("/partners/83?tab=statement");

  await expect(page.getByText("↔ مقابل 3 مستحقات: SH-0019، SH-0014، SH-0015")).toBeVisible({ timeout: 15000 });
  // التخليص مرساةُ نفسه — لا «مقابل» تحته.
  await expect(page.getByText(/↔ مقابل SH-00/)).toHaveCount(0);
  const sublines = page.getByText(/↳ من سند صرف #2460/);
  await expect(sublines).toHaveCount(2);
  await expect(sublines.nth(0)).toContainText("9,000");
  await expect(sublines.nth(1)).toContainText("6,000");
  // السطر الفرعي داخل إطار مجموعة تخليصه، لا صفٌّ مستقلّ.
  const group14 = page.locator("tbody", { hasText: "مستحق تخليص #14" });
  await expect(group14.getByText(/↳ من سند صرف #2460/)).toBeVisible();
  // صفّ السند نفسه مرّة واحدة: رصيده الجاري لا يتكرّر.
  await expect(page.getByText("-4000.00")).toHaveCount(1);

  // بلا ربط: لا أسطر فرعية.
  await page.getByLabel("ربط الفاتورة بسندها").uncheck();
  await expect(page.getByText(/↳ من سند صرف/)).toHaveCount(0);
});

test("statement folds a payment and its reversal into one grey row; the option shows them in full", async ({ page }) => {
  const pair = { original_journal_id: 283, reversal_journal_id: 10979 };
  const row = (id: number, extra: Record<string, unknown>) => ({
    id, journal_id: id, date: "2026-05-10", description: "", reference_id: 175,
    document_number: null, reference_kind: null, link_key: null, link_label: null,
    link_count: 0, link_targets: [], shipment_label: null, reversal_pair_id: null, reversal_pair: null, ...extra,
  });
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/partners/83/statement/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 4,
          closing_balance: "7049.26",
          results: [
            row(10980, {
              reference_type: "LOGISTICS_PAYMENT", debit: "4298.96", credit: "0.00",
              balance_before: "8630.30", running_balance: "7049.26",
              balance_before_folded: "11348.22", running_balance_folded: "7049.26",
            }),
            row(10979, {
              reference_type: "LOGISTICS_PAYMENT_UNPOST", debit: "0.00", credit: "13928.63",
              balance_before: "-2580.41", running_balance: "11348.22",
              balance_before_folded: "11348.22", running_balance_folded: "11348.22",
              reversal_pair_id: 283, reversal_pair: { ...pair, role: "reversal" },
            }),
            row(283, {
              reference_type: "LOGISTICS_PAYMENT", debit: "13928.63", credit: "0.00",
              balance_before: "11348.22", running_balance: "-2580.41",
              balance_before_folded: "11348.22", running_balance_folded: "11348.22",
              reversal_pair_id: 283, reversal_pair: { ...pair, role: "original" },
            }),
            row(12, {
              reference_type: "SHIPMENT_FREIGHT_ACCRUAL", reference_id: 12, debit: "0.00", credit: "11348.22",
              balance_before: "0", running_balance: "11348.22",
              balance_before_folded: "0", running_balance_folded: "11348.22",
            }),
          ],
        }),
      });
      return true;
    }
    return profileResponder(route, url);
  });
  await page.goto("/partners/83?tab=statement");

  const summary = page.getByRole("button", { name: /قيد صُحّح: #283 ⇄ #10979 \(صافي 0\)/ });
  await expect(summary).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("-2580.41")).toHaveCount(0);
  await expect(page.getByText("13928.63")).toHaveCount(0);

  // بكبسة يُفتح الزوج تحت سطره — بلا رصيدٍ جارٍ مضلّل.
  await summary.click();
  await expect(summary).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("13928.63")).toHaveCount(2);
  await expect(page.getByText("-2580.41")).toHaveCount(0);

  // الخيار يعيدهما كاملين بالرصيد الخام، والختامي نفسه.
  await page.getByLabel("إظهار القيود المعكوسة").check();
  await expect(summary).toHaveCount(0);
  await expect(page.getByText("-2580.41")).toBeVisible();
  await expect(page.getByText("7049.26")).toBeVisible();
});

test("forwarder statement opens in dollars with the FX closing row; ₪ switches back", async ({ page }) => {
  const agent = { id: 35, name: "yoyo", partner_type: "FreightForwarder", supplier_scope: "" };
  const row = (id: number, extra: Record<string, unknown>) => ({
    id, journal_id: id, date: "2026-06-01", description: "", reference_id: id, balance_before: "0",
    document_number: null, reference_kind: null, link_key: null, link_label: null, link_count: 0,
    link_targets: [], shipment_label: null, reversal_pair_id: null, reversal_pair: null, ...extra,
  });
  const requested: string[] = [];
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/partners/35/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(agent) });
      return true;
    }
    if (url.pathname.endsWith("/partners/35/profile/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ balance: "1060.00", balance_side: "Cr", outstanding_balance: "1060.00",
          total_sales: "0", total_purchases: "0", last_transaction_date: null }),
      });
      return true;
    }
    if (url.pathname.endsWith("/partners/35/statement/")) {
      const currency = url.searchParams.get("currency");
      requested.push(currency ?? "base");
      const body = currency === "USD" ? {
        count: 3, closing_balance: "0.00", currency: "USD", currencies: ["USD"],
        missing_count: 1, missing_base_balance: "700.00",
        fx: { currency: "USD", book_balance: "1060.00", currency_balance: "0.00", rate: "3.240000",
          rate_source: "last_entry", revalued_balance: "0.00", difference: "1060.00" },
        results: [
          row(3, { reference_type: "SUPPLIER_PAYMENT", debit: "", credit: "", base_debit: "0.00",
            base_credit: "700.00", currency_missing: true, running_balance: "0.00" }),
          row(2, { reference_type: "LOGISTICS_PAYMENT", debit: "1000.00", credit: "0.00",
            base_debit: "3240.00", base_credit: "0.00", currency_missing: false, running_balance: "0.00" }),
          row(1, { reference_type: "SHIPMENT_FREIGHT_ACCRUAL", debit: "0.00", credit: "1000.00",
            base_debit: "0.00", base_credit: "3600.00", currency_missing: false, running_balance: "1000.00" }),
        ],
      } : {
        count: 3, closing_balance: "1060.00", currency: null, currencies: ["USD"],
        results: [
          row(3, { reference_type: "SUPPLIER_PAYMENT", debit: "0.00", credit: "700.00", running_balance: "1060.00" }),
          row(2, { reference_type: "LOGISTICS_PAYMENT", debit: "3240.00", credit: "0.00", running_balance: "360.00" }),
          row(1, { reference_type: "SHIPMENT_FREIGHT_ACCRUAL", debit: "0.00", credit: "3600.00", running_balance: "3600.00" }),
        ],
      };
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
      return true;
    }
    return false;
  });
  await page.goto("/partners/35?tab=statement");

  const dollars = page.getByRole("button", { name: "$", exact: true });
  await expect(dollars).toHaveAttribute("aria-pressed", "true", { timeout: 15000 });
  await expect(page.getByRole("columnheader", { name: "مدين (USD)" })).toBeVisible();
  await expect(page.getByText("1000.00", { exact: true }).first()).toBeVisible();
  const fx = page.getByTestId("statement-fx-row");
  await expect(fx).toContainText("1,060");
  await expect(fx).toContainText("سعر آخر قيد");
  await expect(fx).toContainText("فرق صرف غير مقيَّد");
  await expect(page.getByText(/1 حركة بلا مبلغ بالدولار \(صافيها 700 ₪\)/)).toBeVisible();
  await expect(page.getByText(/بلا مبلغ بالدولار — -700/)).toBeVisible();
  expect(requested).toContain("USD");

  await page.getByRole("button", { name: "₪", exact: true }).click();
  await expect(page.getByRole("columnheader", { name: "مدين (Dr)" })).toBeVisible();
  await expect(page.getByText("3240.00", { exact: true })).toBeVisible();
  await expect(fx).toHaveCount(0);
});

test("broker card: its clearances are its invoices, totalled as «إجمالي المستحقّات» and linked to the shipment", async ({ page }) => {
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/partners/83/profile/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          balance: "955.00", balance_side: "Cr", outstanding_balance: "955.00",
          total_sales: "0", total_purchases: "3400.00", last_transaction_date: "2026-06-10",
        }),
      });
      return true;
    }
    if (url.pathname.endsWith("/partners/83/invoices/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          {
            document_type: "LOGISTICS_CLEARANCE", document_id: 14, shipment_id: 19,
            document_number: "تخليص #14 — SH-0019 — داتا لوجر", date: "2026-06-10",
            grand_total: "2500.00", is_posted: true, amount_paid: "2045.00", remaining_balance: "455.00",
            payment_status: "partially_paid", payment_status_display: "مدفوعة جزئياً",
          },
        ]),
      });
      return true;
    }
    return profileResponder(route, url);
  });
  await page.goto("/partners/83");

  await page.getByRole("tab", { name: "ملخص الرصيد" }).click({ timeout: 15000 });
  await expect(page.getByText("إجمالي المستحقّات")).toBeVisible();
  await expect(page.getByText("3400.00")).toBeVisible();
  await expect(page.getByText("إجمالي المشتريات")).toHaveCount(0);
  await page.getByRole("tab", { name: "الفواتير" }).click();
  await expect(page.getByText("مستحق تخليص", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "تخليص #14 — SH-0019 — داتا لوجر" }).click();
  await expect(page).toHaveURL(/\/import-flow\/19$/);
});

test("broker refund receipt reads the balance as «له» — not «للعميل» with a flipped sign", async ({ page }) => {
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/partners/83/balance/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          partner: 83, partner_type: "CustomsBroker", is_creditor: true,
          debit: "2000.00", credit: "9551.50", open_balance: "7551.50",
          proposed_total: "0", projected_balance: "7551.50",
        }),
      });
      return true;
    }
    return profileResponder(route, url);
  });
  await page.goto("/partners/83");
  await page.getByRole("button", { name: "سند قبض (استرداد)" }).click();
  const balance = page.getByTestId("customer-ledger-balance");
  await expect(balance).toContainText("له", { timeout: 15000 });
  await expect(balance).toContainText("7,551.5");
  await expect(balance).not.toContainText("للعميل");
});
