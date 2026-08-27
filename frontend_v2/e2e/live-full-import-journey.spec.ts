import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });
test.skip(process.env.KTRA_LIVE_E2E !== "1", "Live journey is opt-in because it creates real business records.");
test.setTimeout(12 * 60 * 1000);

const email = process.env.KTRA_LIVE_EMAIL || "";
const password = process.env.KTRA_LIVE_PASSWORD || "";
const runId = process.env.KTRA_LIVE_RUN_ID || String(Date.now());

type DealResult = { id: number; ref: string; description: string; amount: number };
type ShipmentResult = { id: number; number: string };

async function login(page: Page) {
  await page.goto("/");
  const emailInput = page.getByPlaceholder("example@email.com");
  if (!(await emailInput.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: "تسجيل الدخول" }).first().click();
  }
  await emailInput.fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "تسجيل الدخول" }).last().click();
  await expect(page).not.toHaveURL(/login/i, { timeout: 20_000 });
  await expect(page.getByRole("heading", { name: /مرحباً/ })).toBeVisible({ timeout: 20_000 });
}

async function createSupplier(page: Page, name: string) {
  await page.goto("/suppliers");
  const search = page.getByPlaceholder("بحث بالاسم / الهاتف…");
  await expect(search).toBeVisible({ timeout: 20_000 });
  await search.fill(name);
  const existing = page.getByText(name, { exact: true }).first();
  if (await existing.waitFor({ state: "visible", timeout: 5_000 }).then(() => true).catch(() => false)) return;
  await page.getByTitle("إضافة مورد").click();
  await expect(page.getByRole("heading", { name: "إضافة مورد جديد" })).toBeVisible();
  await page.getByPlaceholder("اسم الشركة أو المورد").fill(name);
  await page.getByRole("button", { name: "حفظ البيانات" }).click();
  await expect(page.getByRole("heading", { name: "إضافة مورد جديد" })).toBeHidden({ timeout: 20_000 });
  await search.fill(name);
  await expect(page.getByText(name).first()).toBeVisible({ timeout: 20_000 });
}

async function createDeal(page: Page, supplier: string, description: string, product: string, amount: number): Promise<DealResult> {
  await page.goto("/deals");
  const dealSearch = page.getByPlaceholder("بحث برقم الصفقة، المورد، المنتج… (F6)");
  await expect(dealSearch).toBeVisible({ timeout: 20_000 });
  await dealSearch.fill(description);
  const existingRow = page.getByRole("row").filter({ hasText: description }).first();
  if (await existingRow.waitFor({ state: "visible", timeout: 5_000 }).then(() => true).catch(() => false)) {
    const popupPromise = page.waitForEvent("popup");
    await existingRow.dblclick({ force: true });
    const popup = await popupPromise;
    await popup.waitForLoadState("domcontentloaded");
    const existingUrl = popup.url();
    await popup.close();
    await page.goto(existingUrl);
    await expect(page).toHaveURL(/\/deals\/\d+$/, { timeout: 30_000 });
    const id = Number(page.url().match(/\/deals\/(\d+)$/)?.[1]);
    const ref = (await page.locator(".ktra-status-item").filter({ hasText: "رقم الصفقة" }).locator("b").innerText()).trim();
    return { id, ref, description, amount };
  }
  await dealSearch.fill("");
  await page.getByRole("button", { name: "معالِج الصفقة" }).click();
  await page.getByPlaceholder("ابحث عن مورد بالاسم…").fill(supplier);
  await page.getByRole("button", { name: new RegExp(supplier) }).first().click();
  await page.getByPlaceholder("مثال: طلبية ألواح شمسية").fill(description);
  await page.getByRole("button", { name: "التالي" }).click();

  const productInput = page.getByPlaceholder("اكتب أو اختر منتجاً").first();
  const itemRow = productInput.locator("xpath=..");
  await productInput.fill(product);
  const numberInputs = itemRow.locator('input[type="number"]');
  await numberInputs.nth(0).fill("1");
  await numberInputs.nth(1).fill(String(amount));
  await page.getByRole("button", { name: "التالي" }).click();
  await expect(page.getByText(product, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "إنشاء الصفقة" }).click();
  await expect(page).toHaveURL(/\/deals\/\d+$/, { timeout: 30_000 });
  const id = Number(page.url().match(/\/deals\/(\d+)$/)?.[1]);
  await expect(page.getByText(/رقم الصفقة/).first()).toBeVisible({ timeout: 20_000 });
  const ref = (await page.locator(".ktra-status-item").filter({ hasText: "رقم الصفقة" }).locator("b").innerText()).trim();
  return { id, ref, description, amount };
}

async function enablePlanSetCbmAndPay(page: Page, deal: DealResult, cbm: number) {
  console.log(`LIVE_STEP deal ${deal.ref}: open`);
  await page.goto(`/deals/${deal.id}`);
  console.log(`LIVE_STEP deal ${deal.ref}: terms`);
  await page.getByRole("tab", { name: "الشروط والشحن" }).click({ force: true });
  const cbmLabel = page.locator("label").filter({ hasText: "حجم (CBM)" });
  await cbmLabel.locator("xpath=..").locator("input").fill(String(cbm));

  console.log(`LIVE_STEP deal ${deal.ref}: enable payment plan`);
  await page.getByRole("tab", { name: "الدفعات" }).click({ force: true });
  const enablePlan = page.getByTitle("تفعيل جدول الدفعات");
  if (await enablePlan.isVisible().catch(() => false)) await enablePlan.click();
  await page.getByRole("button", { name: /تخزين/ }).click();
  await expect(page.getByText(/تم حفظ|تم تحديث|بنجاح/).first()).toBeVisible({ timeout: 20_000 });

  console.log(`LIVE_STEP deal ${deal.ref}: execute payment`);
  await page.goto(`/deals/${deal.id}`);
  await page.getByRole("tab", { name: "الدفعات" }).click({ force: true });
  const payButton = page.getByRole("button", { name: "إجراء الدفع" }).first();
  if (await payButton.isVisible().catch(() => false)) {
    await payButton.click();
    const cashBox = page.getByRole("combobox").last();
    await cashBox.selectOption({ index: 1 }, { force: true });
    await page.getByRole("button", { name: /تنفيذ التحويل وخصم/ }).click();
    await page.getByRole("button", { name: "تنفيذ الدفع", exact: true }).click();
    await expect(page.getByText(/تم تنفيذ الدفع/).first()).toBeVisible({ timeout: 30_000 });
  }

  await page.goto(`/deals/${deal.id}`);
  console.log(`LIVE_STEP deal ${deal.ref}: shipping stage`);
  await page.getByRole("tab", { name: "المراحل والشحن" }).click({ force: true });
  const readyButton = page.getByRole("button", { name: "تم الشحن للوكيل", exact: true });
  if (await readyButton.isEnabled().catch(() => false)) {
    await readyButton.click();
    await expect(page.getByText(/بانتظار الشحن الدولي|تم الشحن للوكيل/).first()).toBeVisible({ timeout: 20_000 });
  }
}

async function createShipmentForDeal(page: Page, deal: DealResult, freightRate: number): Promise<ShipmentResult> {
  await page.goto(`/import-flow/new?join_deal=${deal.id}`);
  await page.locator("label").filter({ hasText: "نوع الشحن" }).locator("select").selectOption("sea");
  await page.locator("label").filter({ hasText: "رقم البوليصة" }).locator("input").fill(`BL-${runId}-${deal.id}`);
  await page.locator("label").filter({ hasText: "رقم الحاوية" }).locator("input").fill(`CONT-${runId}-${deal.id}`);
  await page.getByRole("button", { name: /حفظ|تخزين/ }).first().click();
  await expect(page).toHaveURL(/\/import-flow\/\d+/, { timeout: 30_000 });
  const id = Number(page.url().match(/\/import-flow\/(\d+)/)?.[1]);
  await expect(page.getByRole("heading", { name: "اختر صفقة للربط" })).toBeVisible({ timeout: 20_000 });
  await page.getByText(deal.description, { exact: false }).last().click();
  await expect(page.getByTestId(`shipment-deal-cbm-${deal.id}`)).toBeVisible({ timeout: 20_000 });

  const freightInput = page.locator("label").filter({ hasText: "سعر/CBM" }).locator("input");
  await freightInput.fill(String(freightRate));
  await freightInput.blur();
  await expect(page.getByText(new RegExp(`\\$?${freightRate}`)).first()).toBeVisible({ timeout: 20_000 });

  await page.getByRole("tab", { name: "الدفعات" }).click({ force: true });
  await page.getByRole("button", { name: /دفعة شحن دولي/ }).click();
  await page.getByRole("button", { name: "تسجيل دفعة الشحن" }).click();
  await expect(page.getByText(/مكتمل — الاستيراد متاح/)).toBeVisible({ timeout: 20_000 });

  await page.getByRole("tab", { name: "التخليص" }).click({ force: true });
  await page.getByRole("button", { name: "إنشاء سجل تخليص" }).click();
  await expect(page.getByPlaceholder("تكلفة التخليص الإجمالية ₪")).toBeVisible({ timeout: 20_000 });
  await page.getByPlaceholder("تكلفة التخليص الإجمالية ₪").fill(String(500 + freightRate));
  await page.getByRole("button", { name: "اعتماد وحفظ" }).click();
  await expect(page.getByText(/سُجّلت تكلفة التخليص الإجمالية/)).toBeVisible({ timeout: 20_000 });

  const bodyText = await page.locator("body").innerText();
  const number = bodyText.match(/SH-\d{4}/)?.[0] || `#${id}`;
  return { id, number };
}

async function importShipmentInvoice(page: Page, shipment: ShipmentResult) {
  await page.goto(`/import-flow/${shipment.id}`);
  const alreadyConverted = page.getByRole("button", { name: /فتح الفاتورة/ }).first();
  if (await alreadyConverted.waitFor({ state: "visible", timeout: 10_000 }).then(() => true).catch(() => false)) return;
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: /إنشاء الفاتورة الدولية|إنشاء الفواتير المتبقية/ }).first().click();
  const invoicePage = await popupPromise;
  await invoicePage.waitForLoadState("domcontentloaded");
  await expect(invoicePage.getByRole("heading", { name: "استيراد فواتير من تخليص جمركي" })).toBeVisible({ timeout: 30_000 });
  const selectAll = invoicePage.getByRole("button", { name: "اختيار كل المتبقي" });
  await expect(selectAll).toBeVisible({ timeout: 30_000 });
  await selectAll.click();
  const importButton = invoicePage.getByRole("button", { name: "استيراد الفواتير (شيكل)" });
  await expect(importButton).toBeEnabled({ timeout: 30_000 });
  await importButton.click();
  await expect(invoicePage.getByRole("heading", { name: "استيراد فواتير من تخليص جمركي" })).toBeHidden({ timeout: 30_000 });
  await invoicePage.close();
}

async function completeExistingD0109(page: Page) {
  const deal = { id: 87, ref: "D-0109", description: "Chengdu Sunrise Electric", amount: 3000 };
  await enablePlanSetCbmAndPay(page, deal, 0.3);
  await page.goto("/import-flow/16");
  const alreadyConverted = page.getByRole("button", { name: /فتح الفاتورة/ }).first();
  if (await alreadyConverted.waitFor({ state: "visible", timeout: 10_000 }).then(() => true).catch(() => false)) return;
  await page.getByRole("tab", { name: "التخليص" }).click({ force: true });
  const quickTotal = page.getByPlaceholder("تكلفة التخليص الإجمالية ₪");
  await expect(quickTotal).toBeVisible({ timeout: 20_000 });
  await quickTotal.fill("1250");
  await page.getByRole("button", { name: "اعتماد وحفظ" }).click();
  const replaceButton = page.getByRole("button", { name: "استبدال", exact: true });
  if (await replaceButton.isVisible().catch(() => false)) await replaceButton.click();
  await expect(page.getByText(/سُجّلت تكلفة التخليص الإجمالية/)).toBeVisible({ timeout: 20_000 });
  await importShipmentInvoice(page, { id: 16, number: "SH-0002" });
}

test("fresh user completes D-0109 and creates two new deal-to-invoice journeys through the UI", async ({ page }) => {
  test.skip(process.env.KTRA_LIVE_VERIFY_ONLY === "1", "Verification-only run reuses the completed live records.");
  expect(email).not.toBe("");
  expect(password).not.toBe("");
  page.setDefaultTimeout(15_000);
  page.setDefaultNavigationTimeout(30_000);
  page.on("response", async (response) => {
    if (response.status() >= 400 && response.url().includes("/api/")) {
      console.log(`LIVE_API_ERROR ${response.status()} ${response.request().method()} ${response.url()} ${await response.text().catch(() => "")}`);
    }
  });

  console.log("LIVE_STEP login");
  await login(page);
  console.log("LIVE_STEP complete D-0109");
  await completeExistingD0109(page);

  const supplier1 = `Solar Harbor ${runId}`;
  const supplier2 = `Grid Motion ${runId}`;
  await createSupplier(page, supplier1);
  await createSupplier(page, supplier2);

  const deal1 = await createDeal(page, supplier1, `Live solar shipment ${runId}`, `Solar Controller ${runId}`, 2100);
  const deal2 = await createDeal(page, supplier2, `Live battery shipment ${runId}`, `Battery Module ${runId}`, 2400);
  await enablePlanSetCbmAndPay(page, deal1, 1);
  await enablePlanSetCbmAndPay(page, deal2, 1);

  const shipment1 = await createShipmentForDeal(page, deal1, 120);
  await importShipmentInvoice(page, shipment1);
  const shipment2 = await createShipmentForDeal(page, deal2, 140);
  await importShipmentInvoice(page, shipment2);

  console.log(`LIVE_RESULT ${JSON.stringify({ runId, deals: [deal1, deal2], shipments: [shipment1, shipment2], completedExisting: "D-0109" })}`);
});

test("fresh user can verify the three completed international invoices from their shipment screens", async ({ page }) => {
  test.skip(process.env.KTRA_LIVE_VERIFY_ONLY !== "1", "Runs only after the live journey has completed.");
  page.setDefaultTimeout(15_000);
  page.setDefaultNavigationTimeout(30_000);
  await login(page);

  const verified: Array<Record<string, unknown>> = [];
  for (const shipmentId of [16, 18, 19]) {
    const invoiceResponse = page.waitForResponse((response) =>
      response.status() === 200 && response.url().includes(`/api/logistics/purchase-invoices/?shipment=${shipmentId}`)
    );
    await page.goto(`/import-flow/${shipmentId}`);
    const invoices = await (await invoiceResponse).json();
    const openInvoice = page.getByRole("button", { name: /فتح الفاتورة/ }).first();
    await expect(openInvoice).toBeVisible({ timeout: 20_000 });
    verified.push({ shipmentId, button: (await openInvoice.innerText()).trim(), invoices });
  }
  console.log(`LIVE_VERIFIED ${JSON.stringify(verified)}`);
});
