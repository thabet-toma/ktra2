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
