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
    const isApi = url.hostname === "api.smart.ktragroup.com" || url.port === "8000" || url.pathname.startsWith("/api/");
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
    if (await responder(route, url)) return;
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
