/**
 * #27 (تحت مواصفة #17) — رحلة Playwright الجامعة لنموذج «منتج ← براندات».
 *
 * رحلةٌ واحدة فقط بقرار المالك — شاشة الضمّ الجماعي (#24) مغطّاة خادمياً ولا
 * تدخل هنا. الخطوات الخمس كما وردت في التذكرة حرفياً:
 *   1) سجّل منتجاً بالاسم فقط (الأب يُنشأ ضمنياً — المستخدم لا يختاره أبداً).
 *   2) ابدأ تسجيل نفس الاسم ثانيةً ← الشاشة تعرض «أضف براند» بدل صنفٍ ثانٍ.
 *   3) أضف ذلك البراند.
 *   4) اخترْه في بند فاتورة.
 *   5) اطبعها فيظهر السطر «الاسم (البراند)».
 *
 * الخادم مقنَّعٌ بالكامل (`page.route`) على نمط specs الجيران — لا خادم جانغو
 * حيّ ولا قاعدة بيانات. الحالة هنا **مخزنٌ قابل للكتابة**: منتج «195/85/15»
 * يُكتب في الخطوة 1، ويُسمَّى براندُه الضمنيّ في الخطوة 3، وقراءتا الخطوتين 2
 * و4 تُجريان على نفس الصفّ المتغيّر — لا حمولةً ثابتة تُصادف الاختبار نفسه.
 * حتى اسم العرض المطبوع في الخطوة 5 (`name_snapshot`) يُحسب من حالة المتجر
 * وقت الترحيل (`productDisplayName`) لا نصّاً جاهزاً — يطابق
 * `inventory.services.product_display_name` الفعلية بلا استيرادها.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const PRODUCT_NAME = "مقاس إطار 195/85/15";
const BRAND_NAME = "دانتير";

/** اسم المنتج يحمل «/» و«()» — حروفاً خاصّة في Regex، فيجب تحييدها قبل مطابقة نصٍّ حرفي. */
const escapeRegExp = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

type ServerProduct = {
  id: number;
  sku: string;
  name_ar: string;
  name_en: string;
  brand: string;
  family_id: number;
};

type ServerFamily = { id: number; name_ar: string; name_en: string };

type ServerState = {
  family: ServerFamily | null;
  product: ServerProduct | null;
  nextFamilyId: number;
  nextProductId: number;
  createProductCalls: Array<Record<string, unknown>>;
  addBrandCalls: Array<Record<string, unknown>>;
  invoiceCreateCalls: Array<Record<string, unknown>>;
  invoiceLines: Record<number, Array<Record<string, unknown>>>;
  postedIds: number[];
};

const freshState = (): ServerState => ({
  family: null,
  product: null,
  nextFamilyId: 701,
  nextProductId: 4201,
  createProductCalls: [],
  addBrandCalls: [],
  invoiceCreateCalls: [],
  invoiceLines: {},
  postedIds: [],
});

/** نفس صيغة `inventory.services.product_display_name` — لا تُستورد، تُطابَق. */
const productDisplayName = (state: ServerState): string => {
  if (!state.product) return "";
  const name = (state.product.name_ar || state.product.name_en || state.product.sku || "").trim();
  const brand = (state.product.brand || "").trim();
  return brand && !name.includes(brand) ? `${name} (${brand})` : name;
};

const productPickerRow = (state: ServerState) => {
  const p = state.product!;
  return {
    id: p.id,
    sku: p.sku,
    barcode: "",
    name_ar: p.name_ar,
    name_en: p.name_en,
    display_name: productDisplayName(state),
    brand: p.brand,
    category: null,
    category_name: "",
    quantity_on_hand: "50",
    avg_cost: "0",
    sale_price: "100",
    online_price: null,
    is_service: false,
    is_serialized: false,
    stock_status: "in_stock",
    group_key: null,
    has_group: false,
    family_id: p.family_id,
    family_name: state.family?.name_ar ?? null,
  };
};

const baseInvoiceDetail = (
  id: number,
  status: "draft" | "posted",
  lines: Array<Record<string, unknown>>,
): Record<string, unknown> => ({
  id,
  invoice_number: `SI-${id}`,
  customer: 8,
  invoice_date: "2026-09-01",
  due_date: null,
  invoice_type: "credit",
  status,
  grand_total: "100.00",
  amount_paid: "0.00",
  remaining_balance: "100.00",
  pending_payment_total: "0.00",
  payment_status: "unpaid",
  payment_status_display: "غير مدفوعة",
  currency: 1,
  stock_on_post: true,
  delivery_status: "not_delivered",
  delivery_status_display: "غير مسلَّمة",
  book_number: 0,
  original_invoice: null,
  original_invoice_number: null,
  source_document: null,
  exchange_rate: "1",
  subtotal_excl_tax: "100.00",
  invoice_discount: "0.00",
  tax_amount: "0.00",
  revenue_account: 40,
  cash_or_bank_account: null,
  accounts_receivable_account: null,
  journal: status === "posted" ? 9501 : null,
  notes: "",
  attached_cash_amount: 0,
  attached_cash_account: null,
  cheques: [],
  customer_balance_before_invoice: 0,
  customer_balance_after_invoice: 0,
  stock_movement_no: null,
  payment_details: [],
  invoice_kind: "sale",
  second_date: "",
  licensed_dealer_no: "",
  settlement_invoice_no: "",
  prices_include_tax: false,
  discount_percent: "0",
  source_discount_percent_override: null,
  source_discount_amount_override: null,
  lines,
});

const install = async (page: Page, state: ServerState) => {
  await page.addInitScript(() => {
    localStorage.setItem("token", "family-journey-token");
    localStorage.setItem("userId", "family-journey-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
  });

  await page.route("**/*", async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    const path = url.pathname;
    const method = req.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    // ── نقاط الدخول الثلاث ──
    if (path.endsWith("/hr/users/family-journey-user/")) {
      return json({
        id: "family-journey-user", name: "مختبِر رحلة المنتج", role: "manager",
        email: "family-journey@example.test", employmentStatus: "active",
        isApproved: true, isEmailVerified: true,
      });
    }
    if (path.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: "شركة الرحلة", SubscriptionPlan: "Enterprise",
          Status: "Active", CreatedAt: "2026-07-01T00:00:00Z", import_enabled: false,
        },
        role: "manager", is_default: true, created_at: "2026-07-01T00:00:00Z",
        can_access_import: false,
      }]);
    }
    if (path.endsWith("/permissions/me/")) {
      return json({
        role: "manager", is_manager: true, ui_mode: "advanced",
        permissions: [
          "inventory.item.view", "inventory.item.manage",
          "sales.invoice.view", "sales.invoice.create", "sales.invoice.edit",
          "sales.invoice.post", "sales.customer.view",
        ],
      });
    }

    // ── حسابات/عملات/إعدادات المبيعات (فاتورة البيع) ──
    if (path.endsWith("/accounting/currencies/")) {
      return json([{ CurrencyID: 1, Code: "ILS", Name: "شيكل" }]);
    }
    if (path.endsWith("/accounting/accounts/")) {
      return json([{ id: 40, code: "4101", name: "إيراد المبيعات", account_type: "Revenue" }]);
    }
    if (path.endsWith("/sales/settings/current/")) {
      return json({
        default_customer: null, default_currency: 1, default_payment_type: "credit",
        default_cash_account: null, default_revenue_account_product: 40,
        stock_on_post_default: true, default_vat_rate: null,
        prices_include_tax: false, auto_post_invoices: false, show_journal_preview: true,
      });
    }
    if (path.endsWith("/partners/lookup/")) {
      return json([{ id: 8, name: "زبون الرحلة", partner_type: "Customer" }]);
    }

    // ── تسجيل المنتج (خطوة 1) والأصناف/الوحدات لكرت المنتج ──
    if (path.endsWith("/inventory/uoms/")) return json([]);
    if (path.endsWith("/inventory/categories/")) return json([]);

    // #21: اقتراح «هذا موجود — أضف براند؟» (خطوة 2) — قراءةٌ من نفس ما كُتب في 1.
    if (path.endsWith("/product-families/check-name/") && method === "GET") {
      const name = (url.searchParams.get("name") || "").trim();
      if (state.family && name && name === state.family.name_ar) {
        return json({ match: { id: state.family.id, name_ar: state.family.name_ar, name_en: state.family.name_en } });
      }
      return json({ match: null });
    }

    // #21: إضافة/تسمية البراند (خطوة 3) — يكتب في نفس صفّ المنتج الذي أُنشئ في 1.
    if (path.endsWith("/products/add-brand/") && method === "POST") {
      const body = req.postDataJSON() as Record<string, unknown>;
      state.addBrandCalls.push(body);
      if (!state.product || Number(body.family_id) !== state.product.family_id) {
        return json({ detail: "المنتج غير موجود." }, 404);
      }
      // برانداً ضمنياً وحيداً فارغاً — أوّل براندٍ صريح يُسمّيه (created: false).
      state.product.brand = String(body.brand || "");
      return json({
        id: state.product.id, sku: state.product.sku, brand: state.product.brand,
        family_id: state.product.family_id,
        name_ar: state.product.name_ar, name_en: state.product.name_en,
        created: false,
      });
    }

    // إنشاء منتجٍ جديد — نقطة الإنشاء الموحّدة (المنتج ضمناً معه).
    if (path.endsWith("/inventory/products/") && method === "POST") {
      const body = req.postDataJSON() as Record<string, unknown>;
      state.createProductCalls.push(body);
      const familyId = state.nextFamilyId++;
      const productId = state.nextProductId++;
      state.family = {
        id: familyId,
        name_ar: String(body.name_ar || ""),
        name_en: String(body.name_en || ""),
      };
      state.product = {
        id: productId, sku: `P-${productId}`,
        name_ar: String(body.name_ar || ""), name_en: String(body.name_en || ""),
        brand: "", family_id: familyId,
      };
      return json({
        id: productId, sku: state.product.sku,
        name_ar: state.product.name_ar, name_en: state.product.name_en,
        family_id: familyId,
      }, 201);
    }

    // قائمة المنتجات: عقد الشاشة الكاملة (مرقَّم) وعقد المنتقي (`?view=lookup`) —
    // كلاهما يقرآن من نفس الصفّ الذي كتبته 1 و3.
    if (path.endsWith("/inventory/products/") && method === "GET") {
      const rows = state.product ? [productPickerRow(state)] : [];
      if (url.searchParams.get("view") === "lookup") return json(rows);
      return json({ count: rows.length, next: null, previous: null, results: rows });
    }

    if (/\/inventory\/products\/\d+\/profile\/$/.test(path)) {
      const p = state.product;
      return json({
        id: p?.id ?? 0, sku: p?.sku ?? "", name: p ? productDisplayName(state) : "",
        quantity_on_hand: "50", avg_cost: "0", sale_price: "100",
      });
    }
    if (/\/inventory\/products\/\d+\/(stock-ledger|invoices|serials)\/$/.test(path)) {
      return json({ results: [], count: 0 });
    }
    if (/\/inventory\/products\/\d+\/$/.test(path)) {
      return state.product ? json(productPickerRow(state)) : json({ detail: "غير موجود" }, 404);
    }

    // ── فاتورة البيع (خطوة 4 و5) ──
    if (path.endsWith("/sales/invoices/") && method === "GET") {
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    if (path.endsWith("/sales/invoices/") && method === "POST") {
      const body = req.postDataJSON() as Record<string, unknown>;
      state.invoiceCreateCalls.push(body);
      const id = 9601;
      const rawLines = Array.isArray(body.lines) ? body.lines as Array<Record<string, unknown>> : [];
      const lines = rawLines.map((ln, i) => ({
        id: i + 1, product: ln.product, name_snapshot: "",
        quantity: String(ln.quantity ?? "1"), unit_price: String(ln.unit_price ?? "0"),
        line_discount: String(ln.line_discount ?? "0"), tax_rate: ln.tax_rate ?? null,
        serials: [], internal_note: "", customer_note: "",
      }));
      state.invoiceLines[id] = lines;
      return json(baseInvoiceDetail(id, "draft", lines), 201);
    }
    const postMatch = path.match(/\/sales\/invoices\/(\d+)\/post\/$/);
    if (postMatch && method === "POST") {
      const id = Number(postMatch[1]);
      state.postedIds.push(id);
      // اللقطة تُكتب عند الترحيل لا عند الإنشاء (#18) — محسوبةٌ الآن من صفّ
      // المنتج كما هو **هذه اللحظة**، تماماً كما يفعل `product_display_name`
      // الحقيقي على الخادم.
      const lines = (state.invoiceLines[id] || []).map((ln) => ({
        ...ln,
        name_snapshot: state.product && Number(ln.product) === state.product.id
          ? productDisplayName(state)
          : "",
      }));
      return json(baseInvoiceDetail(id, "posted", lines));
    }

    return json([]);
  });
};

// الرحلة تعبر أربعة مسارات كسولة (`/items`، `/sales/invoices/new`، الطباعة)،
// وأوّل تحويلٍ لكل حزمةٍ على خادم Vite بارد يتجاوز المهلة الافتراضية (30ث)
// وحده — فتفشل الرحلة في نقطةٍ مختلفة كل تشغيلة. الإعلان صراحةً هو عُرف
// المستودع لرحلات المسارات المتعدّدة (`office-practice-walk` 180ث،
// `live-full-import-journey` 12د).
test.setTimeout(180_000);

test("سجّل منتجاً ← اقترح أضف براند ← أضفه ← اخترْه في فاتورة ← اطبعها فتظهر «الاسم (البراند)»", async ({ page }) => {
  const state = freshState();
  await install(page, state);

  // ── 1) تسجيل المنتج بالاسم فقط — الأب يُنشأ ضمنياً، لا اختيار له هنا. ──
  await page.goto("/items");
  await page.getByTitle("إضافة منتج (Ctrl+Ins)").click();

  const nameField = page.locator('.ktra-field:has(span:text-is("اسم المنتج")) input').first();
  await expect(nameField).toBeVisible();
  await nameField.fill(PRODUCT_NAME);
  await page.getByRole("button", { name: /تخزين/ }).click();

  await expect.poll(() => state.createProductCalls.length).toBe(1);
  expect(state.createProductCalls[0].name_ar).toBe(PRODUCT_NAME);
  expect(state.product).not.toBeNull();
  // المنتج الضمنيّ وُلد بلا براند — لم يُخترع اسمٌ من عندنا.
  expect(state.product!.brand).toBe("");
  // عاد إلى القائمة (لا يزال زرّ «إضافة منتج» ظاهراً) — لم يبقَ الكرت مفتوحاً.
  await expect(page.getByTitle("إضافة منتج (Ctrl+Ins)")).toBeVisible();

  // ── 2) تسجيل نفس الاسم ثانيةً ← اقتراح «هذا موجود — أضف براند». ──
  await page.getByTitle("إضافة منتج (Ctrl+Ins)").click();
  const nameField2 = page.locator('.ktra-field:has(span:text-is("اسم المنتج")) input').first();
  await expect(nameField2).toHaveValue("");
  await nameField2.fill(PRODUCT_NAME);

  const offerBanner = page.getByText(/يوجد منتجٌ مسجَّلٌ بهذا الاسم/);
  await expect(offerBanner).toBeVisible({ timeout: 5000 });
  await expect(offerBanner).toContainText(PRODUCT_NAME);

  // ── 3) أضف ذلك البراند — يُسمّي البراند الضمنيّ لنفس الصفّ، لا صفّاً ثانياً. ──
  await page.getByPlaceholder("اسم البراند").fill(BRAND_NAME);
  await page.getByRole("button", { name: "أضف براند إلى هذا المنتج" }).click();

  await expect.poll(() => state.addBrandCalls.length).toBe(1);
  expect(state.addBrandCalls[0].family_id).toBe(state.family!.id);
  expect(state.addBrandCalls[0].brand).toBe(BRAND_NAME);
  expect(state.product!.brand).toBe(BRAND_NAME);
  // ما زال منتجاً واحداً — لم يُنشأ صفّ ثانٍ (created: false في ردّ الخادم).
  expect(state.createProductCalls.length).toBe(1);
  await expect(page.getByText(/سُمّي البراند الضمنيّ/)).toBeVisible();

  // ── 4) اخترْه في بند فاتورة — المنتقي يقرأ نفس الصفّ الذي كتبته 1 و3. ──
  await page.goto("/sales/invoices/new");
  // بوّابة «المحرِّر ركّب» لا توكيدٌ سلوكي — مهلتها سخيّة لأن أوّل تحويلٍ
  // لحزمة هذا المسار على خادمٍ بارد يطول. التوكيدات التي تفحص السلوك بعدها
  // تبقى ضيّقة (5ث) كي يفشل منتقٍ معطوبٌ سريعاً.
  await expect(page.getByText("بحث سريع / باركود (F6)", { exact: true }))
    .toBeVisible({ timeout: 120_000 });

  const expectedOption = `${PRODUCT_NAME} (${BRAND_NAME})`;

  await page.getByPlaceholder("اكتب اسم العميل…").fill("زبون الرحلة");
  // «^» يستبعد سطر «إضافة «زبون الرحلة» كعميل جديد» الذي يطابق نفس الاسم كنصّ فرعي.
  await page.getByRole("option", { name: /^زبون الرحلة/ }).click();

  const productField = page.getByPlaceholder("اكتب اسم المنتج…").first();
  await productField.fill(PRODUCT_NAME);
  const option = page.getByRole("option", { name: new RegExp(`^${escapeRegExp(expectedOption)}`) });
  await expect(option).toBeVisible({ timeout: 5000 });
  await option.click();

  // الاسم على السطر يحمل صيغة «الاسم (البراند)» فور الاختيار.
  await expect(productField).toHaveValue(expectedOption);

  await page.getByRole("button", { name: "حفظ وترحيل" }).click();

  await expect.poll(() => state.invoiceCreateCalls.length).toBe(1);
  const createdLines = state.invoiceCreateCalls[0].lines as Array<Record<string, unknown>>;
  // البند يحمل معرّف **نفس** المنتج الذي أُنشئ في 1 وسُمّي براندُه في 3 —
  // لا معرّفاً جاهزاً كُتب في الاختبار.
  expect(Number(createdLines[0].product)).toBe(state.product!.id);
  await expect.poll(() => state.postedIds).toEqual([9601]);
  await expect(page.getByText(/تم الترحيل/)).toBeVisible();

  // ── 5) اطبعها — السطر المطبوع «الاسم (البراند)»، من لقطة الترحيل لا بحثٍ حيّ. ──
  // شريط أدوات المستند لا شريط الإجراءات السريعة العام — كلاهما بزرّ «طباعة».
  await page.getByRole("toolbar", { name: "فاتورة مبيعات" }).getByRole("button", { name: "طباعة" }).click();
  const printLine = page.locator("td p.font-bold", { hasText: expectedOption });
  await expect(printLine).toBeVisible();
  await expect(printLine).toHaveText(expectedOption);
});
