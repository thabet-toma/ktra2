import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ serviceWorkers: "block" });

type ApiResponder = (route: Route, url: URL) => Promise<boolean>;

async function installAuthenticatedApiMocks(page: Page, responder: ApiResponder) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "import-e2e-token");
    localStorage.setItem("userId", "import-e2e-user");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/import-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "import-e2e-user",
          name: "Import Journey Tester",
          role: "manager",
          email: "import@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }
    // القناع العام `[]` في ذيل هذا الموجّه كان يردّ على `/permissions/me/` أيضاً،
    // فتصير `res.permissions` غير معرّفة والمجموعة فارغة بينما `loaded` صحيح ⇒
    // `can()` كاذبة لكل مفتاح، فيردّ `canView` شاشةَ الصفقات إلى لوحة التحكم قبل
    // ظهور أي حقل. المفاتيح بعينها في `utils/viewPermissions.ts`.
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager",
          is_manager: true,
          modules: {},
          ui_mode: "advanced",
          permissions: ["import.deal.manage", "import.shipment.manage"],
        }),
      });
      return;
    }
    // وبلا عضوية شركةٍ مفعَّلٍ فيها الاستيراد يبقى `canAccessImport` كاذباً،
    // فيوجّه `App.tsx` كل مسار استيراد (`/deals/*`, `/import-flow/*`) إلى
    // `/dashboard` — حارسٌ ثانٍ مستقل عن الصلاحيات، وسقوطه وحده يكفي لإفشال الأربعة.
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 1,
            tenant: {
              TenantID: 1,
              CompanyName: "شركة الاختبار",
              SubscriptionPlan: "basic",
              Status: "active",
              CreatedAt: "2026-01-01T00:00:00Z",
              import_enabled: true,
            },
            role: "manager",
            is_default: true,
            created_at: "2026-01-01T00:00:00Z",
            can_access_import: true,
          },
        ]),
      });
      return;
    }
    if (await responder(route, url)) return;
    // القناع العام `[]` هنا يُسقط الشاشة: `costDrift.stale_posted_invoices.length`
    // على مصفوفة ⇒ TypeError وصفحةٌ بيضاء، فتفشل كل اختبارات `/import-flow/<id>`.
    if (url.pathname.endsWith("/shipment-cost-drift/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ posted_count: 0, stale_posted_invoices: [] }),
      });
      return;
    }
    if (url.pathname.includes("/mapper/activityStatus/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ isCurrentlyActive: true }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

const shipment = (overrides: Record<string, unknown> = {}) => ({
  id: 91,
  shipment_number: "SH-0007",
  shipment_name: "شحنة اختبار",
  shipment_date: "2026-07-18",
  shipping_type: "sea",
  editable: true,
  total_shipping_cost_usd: 0,
  total_volume: 0,
  total_weight_kg: 0,
  shipment_deal_allocations: [],
  payments: [],
  ...overrides,
});

test("new shipment form posts a blank number and receives the server-generated SH number", async ({ page }) => {
  let submitted: Record<string, unknown> | null = null;
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/shipments/") && route.request().method() === "POST") {
      submitted = route.request().postDataJSON();
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(shipment()) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/shipments/91/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(shipment()) });
      return true;
    }
    return false;
  });

  await page.goto("/import-flow/new");
  await page.getByRole("button", { name: "حفظ" }).click();

  await expect.poll(() => submitted?.shipment_number).toBe("");
  await expect(page.getByText(/SH-0007/).first()).toBeVisible();
});

test("failed shipment save retains the entered shipping fields", async ({ page }) => {
  let saveAttempts = 0;
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/shipments/") && route.request().method() === "POST") {
      saveAttempts += 1;
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ shipping_agent: ["هذا الحقل مطلوب."] }),
      });
      return true;
    }
    return false;
  });

  await page.goto("/import-flow/new");
  const shippingType = page.locator("label").filter({ hasText: "نوع الشحن" }).locator("select");
  const billOfLading = page.locator("label").filter({ hasText: "رقم البوليصة" }).locator("input");
  const containerNumber = page.locator("label").filter({ hasText: "رقم الحاوية" }).locator("input");
  await shippingType.selectOption("sea");
  await billOfLading.fill("BL-KEEP-1");
  await containerNumber.fill("CONT-KEEP-1");

  await page.getByRole("button", { name: "حفظ" }).click();
  await expect.poll(() => saveAttempts).toBe(1);

  await expect(shippingType).toHaveValue("sea");
  await expect(billOfLading).toHaveValue("BL-KEEP-1");
  await expect(containerNumber).toHaveValue("CONT-KEEP-1");
});

test("editing one CBM keeps the other row mounted and restores app-content scroll", async ({ page }) => {
  let dealPatchCalls = 0;
  let refreshed = false;
  let releaseDealPatch = () => {};
  const dealPatchGate = new Promise<void>((resolve) => {
    releaseDealPatch = resolve;
  });
  const currentShipment = () => shipment({
    chargeable_unit: "cbm",
    freight_rate: 0,
    shipment_deal_allocations: [
      {
        id: 1,
        deal: 101,
        deal_ref: "D-0108",
        deal_title: "صفقة اختبار أولى",
        deal_total_cbm: refreshed ? 2 : 0,
        deal_total_weight_kg: 0,
        allocated_shipping_cost: 0,
      },
      {
        id: 2,
        deal: 102,
        deal_ref: "D-0109",
        deal_title: "صفقة اختبار ثانية",
        deal_total_cbm: 3,
        deal_total_weight_kg: 0,
        allocated_shipping_cost: 0,
      },
    ],
  });
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/shipments/91/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentShipment()) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/deals/101/") && route.request().method() === "PATCH") {
      dealPatchCalls += 1;
      refreshed = true;
      await page.evaluate(() => {
        document.querySelector<HTMLElement>("main.app-content")!.scrollTop = 0;
      });
      await dealPatchGate;
      await route.fulfill({ contentType: "application/json", body: "{}" });
      return true;
    }
    return false;
  });

  await page.goto("/import-flow/91");
  const cbmInput = page.getByTestId("shipment-deal-cbm-101");
  const untouchedCbmInput = page.getByTestId("shipment-deal-cbm-102");
  await expect(cbmInput).toBeVisible();
  await expect(untouchedCbmInput).toBeVisible();
  await untouchedCbmInput.evaluate((element) => {
    element.setAttribute("data-g17-identity", "stable");
  });
  const expectedTop = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>("main.app-content")!;
    const spacer = document.createElement("div");
    spacer.style.height = "1200px";
    main.appendChild(spacer);
    main.scrollTop = 500;
    return main.scrollTop;
  });
  expect(expectedTop).toBeGreaterThan(0);

  await cbmInput.fill("2");
  await cbmInput.blur();
  try {
    await expect.poll(() => dealPatchCalls).toBe(1);
    await expect(page.getByTestId("shipment-allocation-row-101")).toHaveAttribute("aria-busy", "true");
    await expect(untouchedCbmInput).toBeEnabled();
    await expect.poll(() => page.evaluate(() => document.querySelector<HTMLElement>("main.app-content")!.scrollTop)).toBe(0);
  } finally {
    releaseDealPatch();
  }

  await expect(cbmInput).toHaveValue("2");
  await expect(untouchedCbmInput).toHaveAttribute("data-g17-identity", "stable");
  await expect.poll(() => page.evaluate(() => document.querySelector<HTMLElement>("main.app-content")!.scrollTop)).toBe(expectedTop);
});

test("freight accrual rate starts empty and is shown as posted after reload", async ({ page }) => {
  // لا سعر افتراضي: كانت 3.6 معبّأةً سلفاً فتُرحَّل حين لا يعدّلها أحد.
  let posted = false;
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/shipments/91/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(shipment({
          total_shipping_cost_usd: 500,
          shipping_agent: 7,
          freight_is_posted: posted,
          freight_exchange_rate: posted ? "3.240000" : null,
        })),
      });
      return true;
    }
    return false;
  });

  await page.goto("/import-flow/91");
  await page.getByText("الدفعات", { exact: true }).first().click();
  const rate = page.locator("label").filter({ hasText: "سعر الصرف (₪/$)" }).locator("input");
  const postButton = page.getByRole("button", { name: "ترحيل الاستحقاق" });
  await expect(rate).toHaveValue("");
  await expect(postButton).toBeDisabled();
  await rate.fill("3.4");
  await expect(postButton).toBeEnabled();

  // بعد الترحيل وإعادة التحميل: السعر المرحَّل من الشحنة، لا حقلٌ فارغ ولا 3.6.
  posted = true;
  await page.reload();
  await page.getByText("الدفعات", { exact: true }).first().click();
  await expect(rate).toHaveValue("3.240000");
  await expect(rate).toBeDisabled();
  await expect(page.getByText("1,620 ₪", { exact: true }).first()).toBeVisible();
});

test("archive deal: posted payment rate is edited without unposting", async ({ page }) => {
  // صفقة أرشيف: قيد الدفعة بالرقم الدولاري بسعر 1، فالسعر يُصحَّح مباشرةً (PATCH
  // بـusd_to_ils وحده) — وصفقةٌ غير أرشيف لا يظهر لها الزر أصلاً.
  let patched: Record<string, unknown> | null = null;
  const deal = (isArchive: boolean) => ({
    id: 501,
    ref_number: "D-0091",
    partner: 7,
    partner_name: "مورد الأرشيف",
    order_date: "2025-08-01",
    status: "Open",
    total_amount: "1535.42",
    is_archive: isArchive,
    items: [],
    payments: [{
      id: 24, payment_number: 1, title: "دفعة أولى", amount: "1115.39", usd_to_ils: "2.000000",
      status: "Confirmed", is_posted: true, journal: 166, transfer_date: "2025-10-15",
    }],
  });
  let archive = true;
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/logistics/deals/501/") && route.request().method() === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(deal(archive)) });
      return true;
    }
    if (url.pathname.endsWith("/logistics/deals/501/payments/24/") && route.request().method() === "PATCH") {
      patched = route.request().postDataJSON();
      await route.fulfill({ contentType: "application/json", body: "{}" });
      return true;
    }
    return false;
  });

  await page.goto("/deals/501");
  await page.getByRole("button", { name: "تحرير" }).click();
  await page.getByText("الدفعات", { exact: true }).first().click();
  await page.getByText("السجل المحاسبي المفصّل", { exact: false }).first().click();
  await page.getByRole("button", { name: "تعديل السعر" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("لا يغيّر القيد");
  await dialog.locator("input").fill("3.62");
  await dialog.getByRole("button", { name: "حفظ السعر" }).click();
  await expect.poll(() => patched).toEqual({ usd_to_ils: 3.62 });

  archive = false;
  await page.reload();
  await page.getByRole("button", { name: "تحرير" }).click();
  await page.getByText("الدفعات", { exact: true }).first().click();
  await page.getByText("السجل المحاسبي المفصّل", { exact: false }).first().click();
  await expect(page.getByRole("button", { name: "إلغاء الترحيل" })).toBeVisible();
  await expect(page.getByRole("button", { name: "تعديل السعر" })).toHaveCount(0);
});

test("a supplier created inside the deal form remains searchable without reloading", async ({ page }) => {
  let supplierCreates = 0;
  await installAuthenticatedApiMocks(page, async (route, url) => {
    if (url.pathname.endsWith("/partners/") && route.request().method() === "POST") {
      supplierCreates += 1;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: 299,
          name: "Chengdu Sunrise Electric",
          partner_type: "Supplier",
          is_active: true,
        }),
      });
      return true;
    }
    return false;
  });

  await page.goto("/deals/new");
  const supplierSearch = page.getByPlaceholder("ابحث عن مورد...");
  await expect(supplierSearch).toBeVisible({ timeout: 15_000 });
  await supplierSearch.fill("Chengdu Sunrise Electric");
  await page.getByRole("button", { name: "إضافة مورد جديد" }).click();
  await page.getByPlaceholder("اسم الشركة أو المورد").fill("Chengdu Sunrise Electric");
  await page.getByRole("button", { name: "حفظ البيانات" }).click();

  await expect.poll(() => supplierCreates).toBe(1);
  await expect(page.getByText("Chengdu Sunrise Electric").first()).toBeVisible();
  await page.getByTitle("إزالة المورد").click();
  await supplierSearch.fill("Chengdu Sunrise Electric");
  await expect(page.getByText("Chengdu Sunrise Electric").first()).toBeVisible();
});
