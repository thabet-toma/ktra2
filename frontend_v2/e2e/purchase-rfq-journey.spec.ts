import { expect, test, type Page, type BrowserContext } from "@playwright/test";

/**
 * ISSUE #116 (مواصفة #108) — الوصلة الرابعة الناقصة: رحلةٌ واحدةٌ تُثبت أنّ
 * القطع تتكلّم فعلياً عبر الحدود الثلاث (React ← DRF ← صفحة `docshare` العامّة
 * المُصيَّرة من Django مباشرةً لا من الـSPA):
 *
 *   طلبية (بلا سعر إلزامي) ← إرسالٌ لموردين ← رابطُ كلّ موردٍ الخاصّ ← موردٌ
 *   يفتح رابطه في سياقٍ بلا توثيق ويكتب أسعاره ← عرضٌ يتولّد باسمه ← شاشةُ
 *   المقارنة تُظهر الموردين ← الترسية.
 *
 * **لماذا "حيّ" (`KTRA_LIVE_E2E`) لا مُقنَّع بـ`page.route` مثل
 * `document-draft-recovery.spec.ts`:** صفحة المورّد العامّة (`/s/<token>`)
 * قالبُ Django (`docshare/templates/docshare/share.html`) يُصيَّره الخادم
 * نفسه — لا مسار React ولا نداء REST يمكن تمويهه بـ`page.route`. تزييفُ HTML
 * كامل لصفحة زائرٍ لإثبات "القطع تتكلّم" ينقض غرض الاختبار نفسه. النمط هنا
 * إذاً نمط `live-full-import-journey.spec.ts` حرفياً: مستخدمٌ حقيقي، بيانات
 * عمل حقيقية، اختياريٌّ بعَلَم بيئة لأنه يكتب في قاعدة بيانات حقيقية.
 *
 * ملاحظاتُ تنفيذٍ حرجة (خُذها كما هي، لا افتراضات بديلة):
 * - رابطُ المورّد العامّ (`DOCSHARE_PUBLIC_BASE_URL`) قد يكون نطاقاً مختلفاً
 *   تماماً عن `baseURL` الخاص بـPlaywright (افتراضه في `core/settings.py`
 *   نطاقُ إنتاجٍ: `https://ktra-pro.tech`) — الاختبار **لا** يُفترض مسبقاً
 *   شكل هذا الرابط؛ يقرأه حرفياً من الشاشة (حقل القراءة تحت تبويب «الموردون»
 *   في `PurchaseRFQForm.tsx`) ويفتحه كما هو. مسؤوليةُ من يُشغّل الاختبار أن
 *   تكون `DOCSHARE_PUBLIC_BASE_URL` مضبوطةً على عنوانٍ يصل إليه المتصفّح
 *   فعلياً (مثلاً نفس مضيف الخادم الخلفي) — بلا ذلك الخطوة تفشل بوضوح على
 *   فشل تنقّل، لا بنجاحٍ مزيَّف.
 * - قاعدة بيانات التطوير المحلية هنا (MySQL) كانت **متأخّرة عن الهجرات** وقت
 *   كتابة هذا الملف (`django.db.utils.OperationalError: Unknown column
 *   'tenants.Template'`) — فحصٌ مباشر عبر `python manage.py shell`، لا
 *   افتراضاً. هذا الملف لا يُصلح ذلك (خارج الحدود المسموحة: لا تعديل على
 *   أي شيء غير هذا الملف)، ولا عزائم `KTRA_LIVE_E2E=1` بلا خادمٍ مهاجَرٍ
 *   فعلياً وبيانات اعتماد صالحة (`KTRA_LIVE_EMAIL`/`KTRA_LIVE_PASSWORD`).
 */

test.use({ serviceWorkers: "block" });
test.skip(process.env.KTRA_LIVE_E2E !== "1", "Live journey is opt-in because it creates real business records.");
test.setTimeout(10 * 60 * 1000);

const email = process.env.KTRA_LIVE_EMAIL || "";
const password = process.env.KTRA_LIVE_PASSWORD || "";
const runId = process.env.KTRA_LIVE_RUN_ID || String(Date.now());

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

/** حقل القراءة تحت صفّ مستقبِل بعينه في تبويب «الموردون» — قيمته `share_url`
 *  كما تولّده `docshare/services.public_url` حرفياً، لا رابطٌ مُخمَّن. */
async function readRecipientShareUrl(page: Page, supplierName: string): Promise<string> {
  const row = page.locator("li").filter({ hasText: supplierName });
  await expect(row).toBeVisible({ timeout: 20_000 });
  const link = row.locator("input[readonly]");
  await expect(link).toBeVisible({ timeout: 20_000 });
  const value = await link.inputValue();
  expect(value).toMatch(/^https?:\/\//);
  return value;
}

/** يفتح رابط مورّدٍ في سياقٍ متصفّحٍ جديد **بلا** أي localStorage/كوكيز من
 *  الجلسة الموثَّقة — هذا هو "بلا توثيق" فعلياً، لا مجرّد نافذةٍ ثانية تشارك
 *  نفس الأصل والتخزين. */
async function openSupplierLink(context: BrowserContext, url: string): Promise<Page> {
  const supplierPage = await context.newPage();
  await supplierPage.goto(url);
  return supplierPage;
}

/** مطابقة `formatMoney` (`utils/formatNumber.ts`) حرفياً: قصٌّ لمنزلتين ثم
 *  حذف الأصفار غير الدالّة — كي لا يفترض الاختبار تنسيقاً مغايراً لما تعرضه
 *  الشاشة فعلياً. القيم هنا كلّها دون الألف فلا فاصل آلاف يدخل الحساب. */
function expectedMoneyDisplay(raw: string): string {
  const n = Number(raw);
  const fixed = n.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return fixed;
}

test("طلبية بلا أسعار ← إرسال لموردين ← تسعير من الرابط العام ← مقارنة ← ترسية", async ({ page, context }) => {
  expect(email, "KTRA_LIVE_EMAIL must be set").not.toBe("");
  expect(password, "KTRA_LIVE_PASSWORD must be set").not.toBe("");
  page.setDefaultTimeout(15_000);
  page.setDefaultNavigationTimeout(30_000);
  page.on("response", async (response) => {
    if (response.status() >= 400 && response.url().includes("/api/")) {
      console.log(`RFQ_API_ERROR ${response.status()} ${response.request().method()} ${response.url()} ${await response.text().catch(() => "")}`);
    }
  });

  const supplierAName = `RFQ Supplier A ${runId}`;
  const supplierBName = `RFQ Supplier B ${runId}`;
  const item1Name = `RFQ Item One ${runId}`;
  const item2Name = `RFQ Item Two ${runId}`;

  console.log("RFQ_STEP login");
  await login(page);

  console.log("RFQ_STEP create two local suppliers");
  await createSupplier(page, supplierAName);
  await createSupplier(page, supplierBName);

  // ── الطلبية: بنودٌ بلا أسعار (أصل الميزة، #113) ───────────────────────────
  console.log("RFQ_STEP open a new RFQ");
  await page.goto("/price-offers");
  await page.getByRole("button", { name: /الطلبيات/ }).click();
  await page.getByRole("button", { name: "طلبية جديدة" }).click();

  const numberField = page.locator(".ktra-field").filter({ hasText: "رقم الطلبية" }).locator("input");
  await expect(numberField).toHaveValue("يُخصَّص عند أوّل إرسال");

  const productInput1 = page.getByPlaceholder("اكتب اسم الصنف…").nth(0);
  await productInput1.fill(item1Name);
  await productInput1.press("Enter");
  await page.locator("#ktra-grid-input-0-quantity").fill("10");

  await page.getByRole("button", { name: "إضافة سطر" }).click();
  const productInput2 = page.getByPlaceholder("اكتب اسم الصنف…").nth(1);
  await productInput2.fill(item2Name);
  await productInput2.press("Enter");
  await page.locator("#ktra-grid-input-1-quantity").fill("4");

  // لا سعر تقديري على أيّ بندٍ — القيمة الافتراضية، لم يُلمس حقلها إطلاقاً.
  const estimatedPriceInputs = page.locator('input[placeholder="—"]');
  await expect(estimatedPriceInputs).toHaveCount(2);
  await expect(estimatedPriceInputs.nth(0)).toHaveValue("");
  await expect(estimatedPriceInputs.nth(1)).toHaveValue("");

  console.log("RFQ_STEP save the draft (no number yet)");
  await page.getByRole("button", { name: "تخزين (F12)" }).click();
  await expect(page.getByText("تم الحفظ.")).toBeVisible({ timeout: 20_000 });
  await expect(numberField).toHaveValue("يُخصَّص عند أوّل إرسال");

  // ── إرسالٌ لموردين — الرقم يُخصَّص هنا لا عند الإنشاء (#112) ──────────────
  console.log("RFQ_STEP send to both suppliers");
  await page.getByRole("tab", { name: /الموردون/ }).click();
  await page.locator("label").filter({ hasText: supplierAName }).locator('input[type="checkbox"]').check();
  await page.locator("label").filter({ hasText: supplierBName }).locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "إرسال للموردين" }).click();
  await expect(page.getByText(/تم إرسال الطلبية/)).toBeVisible({ timeout: 20_000 });
  await expect(numberField).toHaveValue(/^RFQ-\d+$/);
  const rfqNumber = (await numberField.inputValue()).trim();
  console.log(`RFQ_STEP assigned number ${rfqNumber}`);

  // ── الروابط الخاصة — واحدٌ لكل مورّد، من الشاشة لا من الخادم ──────────────
  await page.getByRole("tab", { name: /الموردون/ }).click();
  const shareUrlA = await readRecipientShareUrl(page, supplierAName);
  const shareUrlB = await readRecipientShareUrl(page, supplierBName);
  expect(shareUrlA).not.toBe(shareUrlB);
  console.log(`RFQ_STEP share links A=${shareUrlA} B=${shareUrlB}`);

  // ── موردٌ أ يفتح رابطه في سياقٍ بلا توثيق ويكتب أسعاره ─────────────────────
  console.log("RFQ_STEP supplier A opens the public link (unauthenticated context)");
  const supplierPageA = await openSupplierLink(context, shareUrlA);
  // ملاحظة: `build_purchase_rfq` (`docshare/documents/purchase_docs.py`) لا
  // يمرّر `show_lines=False` — فجدول البنود العام (`doc.show_lines`) وجدول
  // التسعير (`doc.quote`) يظهران معاً، واسم كل بندٍ يتكرّر مرّتين على
  // الصفحة. `.first()` هنا مقصودة لا تسامحٌ مع غموض — العدد ليس ما نقيسه.
  await expect(supplierPageA.getByText(rfqNumber).first()).toBeVisible({ timeout: 20_000 });
  await expect(supplierPageA.getByText(item1Name).first()).toBeVisible();
  await expect(supplierPageA.getByText(item2Name).first()).toBeVisible();

  // الرابط لا يُظهر السعر التقديري ولا "أقل سعر" — تحقّقٌ نصّي، لا افتراض.
  await expect(supplierPageA.getByText("السعر التقديري")).toHaveCount(0);
  await expect(supplierPageA.getByText("أقل سعر")).toHaveCount(0);
  // ولا مقارنة موردين أو عروض غيره — لا جدول من هذا النوع على الصفحة أصلاً.
  await expect(supplierPageA.getByText("مقارنة الموردين")).toHaveCount(0);

  await supplierPageA.getByPlaceholder("الاسم الكامل").fill("مندوب المورد أ");
  const priceInputsA = supplierPageA.locator('input[type="number"][form="rfq-quote-form"]');
  await expect(priceInputsA).toHaveCount(2);
  const priceA1 = "123.4500";
  const priceA2 = "77.1000";
  await priceInputsA.nth(0).fill(priceA1);
  await priceInputsA.nth(1).fill(priceA2);
  await supplierPageA.getByRole("button", { name: "إرسال الأسعار" }).click();
  await expect(supplierPageA.getByText(/أُرسلت أسعاركم/)).toBeVisible({ timeout: 20_000 });

  // ── موردٌ ب يفتح رابطه — سياقٌ منفصل تماماً، ولا يرى سعر أ ─────────────────
  console.log("RFQ_STEP supplier B opens the public link (separate unauthenticated context)");
  const supplierPageB = await openSupplierLink(context, shareUrlB);
  await expect(supplierPageB.getByText(rfqNumber).first()).toBeVisible({ timeout: 20_000 });
  await expect(supplierPageB.getByText("السعر التقديري")).toHaveCount(0);
  await expect(supplierPageB.getByText("أقل سعر")).toHaveCount(0);
  // لا أثر لسعر المورّد أ ولا لاسمه على رابط المورّد ب — تحقّقٌ نصّي مباشر.
  await expect(supplierPageB.getByText(priceA1)).toHaveCount(0);
  await expect(supplierPageB.getByText("مندوب المورد أ")).toHaveCount(0);

  await supplierPageB.getByPlaceholder("الاسم الكامل").fill("مندوب المورد ب");
  const priceInputsB = supplierPageB.locator('input[type="number"][form="rfq-quote-form"]');
  await expect(priceInputsB).toHaveCount(2);
  const priceB1 = "99.0000";
  const priceB2 = "88.5000";
  await priceInputsB.nth(0).fill(priceB1);
  await priceInputsB.nth(1).fill(priceB2);
  await supplierPageB.getByRole("button", { name: "إرسال الأسعار" }).click();
  await expect(supplierPageB.getByText(/أُرسلت أسعاركم/)).toBeVisible({ timeout: 20_000 });

  await supplierPageA.close();
  await supplierPageB.close();

  // ── عرضٌ تولّد باسم كل مورّد، مربوطٌ بالطلبية — يُرى من شاشتنا ─────────────
  console.log("RFQ_STEP verify supplier quotations were generated and linked to the RFQ");
  await page.goto("/price-offers");
  await page.getByRole("button", { name: /العروض والأوامر/ }).click();
  const searchBox = page.locator('input[data-ktra-field="search"]');
  await searchBox.fill(supplierAName);
  await expect(page.getByText(supplierAName).first()).toBeVisible({ timeout: 20_000 });
  await searchBox.fill(supplierBName);
  await expect(page.getByText(supplierBName).first()).toBeVisible({ timeout: 20_000 });
  await searchBox.fill("");

  // ── المقارنة: الموردان يظهران، والبند بلا سعرٍ تقديري فارغٌ لا صفر ────────
  console.log("RFQ_STEP open the RFQ again and show the comparison matrix");
  await page.getByRole("button", { name: /الطلبيات/ }).click();
  // القائمة تفتح المستند بنقرةٍ مزدوجة (`onRowDoubleClick`) لا بنقرةٍ واحدة.
  await page.getByText(rfqNumber, { exact: true }).first().dblclick();
  await page.getByRole("button", { name: "مقارنة الموردين وترسية" }).click();

  await expect(page.getByRole("heading", { name: new RegExp(rfqNumber) })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(supplierAName)).toBeVisible();
  await expect(page.getByText(supplierBName)).toBeVisible();
  // عمود "السعر التقديري" (الثالث المثبَّت أفقياً) فارغ (—) على كلا صفّي
  // البند — لا صفر: لم يُلمس حقل السعر التقديري إطلاقاً طوال الرحلة.
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(2);
  for (let i = 0; i < 2; i++) {
    await expect(rows.nth(i).locator("td").nth(2)).toHaveText("—");
  }
  await expect(page.getByText(expectedMoneyDisplay(priceA1), { exact: true }).first()).toBeVisible();
  await expect(page.getByText(expectedMoneyDisplay(priceB1), { exact: true }).first()).toBeVisible();

  // ── الترسية على المورّد أ — تنقل الطلبية إلى awarded وتُنتج المستند ────────
  // اسمُ المورّد يظهر في `<th>` الترويسة لا في `<td>` التذييل (الذي يحمل زرّ
  // "ترسية" وحده بلا اسم) — فمطابقة العمود بالفهرس بين الاثنين، لا بالنصّ.
  console.log("RFQ_STEP award to supplier A");
  const headerCells = page.locator("thead th");
  const headerCount = await headerCells.count();
  let supplierAColumnIndex = -1;
  for (let i = 0; i < headerCount; i++) {
    const text = await headerCells.nth(i).innerText();
    if (text.includes(supplierAName)) { supplierAColumnIndex = i; break; }
  }
  expect(supplierAColumnIndex, `supplier ${supplierAName} column must be present`).toBeGreaterThan(-1);

  const awardResponsePromise = page.waitForResponse((response) =>
    /\/purchase-rfqs\/\d+\/award\/$/.test(response.url()) && response.request().method() === "POST"
  );
  await page.locator("tfoot td").nth(supplierAColumnIndex).getByRole("button", { name: "ترسية" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "ترسية" }).click();
  const awardResponse = await awardResponsePromise;
  const awardBody = await awardResponse.json().catch(() => null);
  console.log(`RFQ_RESULT ${JSON.stringify({ runId, rfqNumber, supplierAName, supplierBName, awardBody })}`);

  await expect(page.getByText(/تمّت ترسية الطلبية على/)).toBeVisible({ timeout: 20_000 });

  // المقارنة تُغلق تلقائياً بعد الترسية والمحرِّر يعرض الحالة الجديدة.
  const statusField = page.locator(".ktra-field").filter({ hasText: "الحالة" }).locator("input");
  await expect(statusField).toHaveValue("مُرساة", { timeout: 20_000 });

  // والمستند الناتج (أمر شراء أو فاتورة شراء بحسب إعدادات الشراء) موجودٌ فعلاً.
  const awardedDocument = awardBody?.awarded_document as
    | { type: "purchase_order" | "purchase_invoice"; id: number; number: string }
    | undefined;
  expect(awardedDocument, "award response must include awarded_document").toBeTruthy();
  if (awardedDocument) {
    console.log(`RFQ_STEP verify produced document ${awardedDocument.type} ${awardedDocument.number}`);
    if (awardedDocument.type === "purchase_order") {
      await page.getByRole("button", { name: "رجوع" }).click();
      await page.getByRole("button", { name: /العروض والأوامر/ }).click();
      await page.locator('input[data-ktra-field="search"]').fill(awardedDocument.number);
      await expect(page.getByText(awardedDocument.number).first()).toBeVisible({ timeout: 20_000 });
    } else {
      await page.goto(`/purchase-invoices/${awardedDocument.id}`);
      await expect(page.getByText(awardedDocument.number).first()).toBeVisible({ timeout: 20_000 });
    }
  }

  console.log(`RFQ_DONE ${JSON.stringify({ runId, rfqNumber })}`);
});
