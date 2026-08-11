import { expect, test, type Page } from "@playwright/test";

/**
 * THA-24 م2 — بوابة وحدة «خدمة ما بعد البيع» وشاشة بطاقات الكفالة.
 *
 * الشاشة داخلية، فتلزمها نقاط الدخول الوهمية الثلاث (المستخدم/الشركات/الصلاحيات).
 * ما يُثبَت هنا شيئان لا يُثبتهما `tsc` ولا اختبار الوحدة:
 *
 * 1. **الفشل مغلقاً حتى الشبكة**: شركةٌ بلا ترخيص لا ترى البند ولا تطلب chunk
 *    الشاشة أصلاً — لا يكفي أن تُحجَب بعد التنزيل.
 * 2. **الشاشة حيّة**: `tsc` لا يفحص خصائص JSX في هذا المستودع، فشاشة ميتة تبقى
 *    خضراء. البطاقة تُنشأ فعلاً وتُقرأ حالتها المشتقّة من الجدول.
 *
 * المخزن الوهمي **قابل للكتابة**: الإنشاء يكتب فيه والقائمة تقرأ منه، ويُحسب
 * `end_date`/`status` كما يحسبهما الخادم — كي تكون «أنشئ ← أعد التحميل ← ما زالت
 * هناك» دورةً حقيقية لا تأكيداً على نفسها.
 */

test.use({ serviceWorkers: "block" });

const PROFILE = {
  id: "aftersales-user",
  name: "مدير الشركة",
  role: "manager",
  email: "aftersales@example.test",
  employmentStatus: "active",
  isApproved: true,
  isEmailVerified: true,
};

const MEMBERSHIP = {
  id: 42,
  tenant: {
    TenantID: 42,
    CompanyName: "شركة الاختبار",
    SubscriptionPlan: "Enterprise",
    Status: "Active",
    CreatedAt: "2026-07-22T00:00:00Z",
    import_enabled: false,
  },
  role: "manager",
  is_default: true,
  created_at: "2026-07-22T00:00:00Z",
  can_access_import: false,
};

const PERMISSION_KEYS = [
  "aftersales.warranty.view",
  "aftersales.warranty.manage",
  // بند الأجهزة الحساسة يلزمه الترخيص **والصلاحية** معاً في الموضعين — داخل
  // القسم وخارجه — فبدونها لا يظهر ولو رُخِّصت وحدته.
  "devices.registry.view",
  "inventory.item.view",
];

const PRODUCTS = [
  {
    id: 7,
    sku: "P-0007",
    display_name: "جهاز لوحي (سامسونج)",
    name_ar: "جهاز لوحي",
    warranty_months: 12,
    supplier_warranty_months: 24,
    is_serialized: true,
    is_service: false,
  },
];

const PARTNERS = [{ id: 3, name: "زبون تجريبي", partner_type: "customer", phone: "0599123456" }];

/** بطاقة تلقائية قائمة — نهايتها بعيدة فحالتها «سارية». */
const AUTO_CARD = {
  id: 1,
  product: 7,
  product_name: "جهاز لوحي (سامسونج)",
  device_name: "",
  serial: "SN-AUTO-1",
  product_serial: 11,
  sales_invoice_line: 5,
  sales_invoice: 9,
  sales_invoice_number: "SI-9",
  partner: 3,
  partner_name: "زبون تجريبي",
  customer_name: "زبون تجريبي",
  customer_phone: "0599123456",
  start_date: "2026-08-01",
  duration_months: 12,
  end_date: "2027-08-01",
  source: "auto_sale",
  source_label: "تلقائية من فاتورة بيع",
  supplier: null,
  supplier_name: "",
  supplier_warranty_end_date: null,
  supplier_warranty_active: false,
  notes: "",
  status: "active",
  days_remaining: 300,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

type CardRow = Record<string, unknown>;

/** الشهور تقويمية — نفس قاعدة `after_sales.models.add_months`. */
function addMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const total = y * 12 + (m - 1) + months;
  const year = Math.floor(total / 12);
  const month = (total % 12) + 1;
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const day = Math.min(d, lastDay);
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** أُنشئت الملفات المطلوبة: أعلام الوحدات + المخزن + عدّاد طلبات chunk الشاشة. */
async function mockTenant(
  page: Page,
  opts: { afterSales: boolean; devices?: boolean },
): Promise<{ cards: CardRow[]; chunkRequests: string[] }> {
  const cards: CardRow[] = [{ ...AUTO_CARD }];
  const chunkRequests: string[] = [];

  await page.addInitScript(() => {
    localStorage.setItem("token", "aftersales-token");
    localStorage.setItem("userId", "aftersales-user");
    localStorage.setItem("tenantId", "42");
  });

  page.on("request", (req) => {
    const url = req.url();
    // في التطوير تُطلب الوحدة بمسار مصدرها؛ في البناء باسم الـchunk. النمط
    // مقيّد بالمجلد واسم الملف كي لا يلتقط مسارات الـAPI الحاملة اسم المستخدم.
    if (/\/components\/aftersales\/|WarrantyCardsScreen/.test(new URL(url).pathname)) {
      chunkRequests.push(url);
    }
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const path = url.pathname;
    const json = (body: unknown) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });

    if (path.endsWith("/hr/users/aftersales-user/")) return json(PROFILE);
    if (path.endsWith("/tenants/companies/my-companies/")) return json([MEMBERSHIP]);
    if (path.endsWith("/permissions/me/")) {
      return json({
        role: "manager",
        is_manager: true,
        permissions: PERMISSION_KEYS,
        modules: {
          after_sales: opts.afterSales,
          sensitive_devices: opts.devices === true,
        },
      });
    }
    if (path.includes("/inventory/products/")) return json(PRODUCTS);
    if (path.includes("/partners/lookup/")) return json(PARTNERS);

    if (path.includes("/after-sales/warranties/")) {
      // الترخيص أولاً: الخادم يردّ 404 لا 403 على شركةٍ غير مرخّصة.
      if (!opts.afterSales) return route.fulfill({ status: 404, body: "{}" });
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        const start = String(body.start_date || "2026-08-10");
        const months = Number(body.duration_months || 0);
        const end = String(body.end_date || "") || addMonths(start, months);
        const created = {
          ...AUTO_CARD,
          id: cards.length + 1,
          product: body.product ?? null,
          product_name: body.product
            ? PRODUCTS[0].display_name
            : String(body.device_name || ""),
          device_name: String(body.device_name || ""),
          serial: String(body.serial || ""),
          product_serial: null,
          sales_invoice_line: null,
          sales_invoice: null,
          sales_invoice_number: null,
          partner: body.partner ?? null,
          partner_name: String(body.customer_name || ""),
          customer_name: String(body.customer_name || ""),
          customer_phone: String(body.customer_phone || ""),
          start_date: start,
          duration_months: months,
          end_date: end,
          source: "manual",
          source_label: "يدوية",
          notes: String(body.notes || ""),
          // الحالة **مشتقّة** كما في الخادم — لا تصل من جسم الطلب.
          status: end >= "2026-08-10" ? "active" : "expired",
          days_remaining: end >= "2026-08-10" ? 365 : -10,
        };
        cards.unshift(created);
        return json(created);
      }
      return json({ count: cards.length, next: null, previous: null, results: cards });
    }

    return json([]);
  });

  return { cards, chunkRequests };
}

test("شركة بلا ترخيص لا ترى القسم ولا تُنزّل chunk الشاشة", async ({ page }) => {
  const state = await mockTenant(page, { afterSales: false });

  await page.goto("/dashboard");
  await expect(page.getByRole("button", { name: "خدمة ما بعد البيع" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "بطاقات الكفالة" })).toHaveCount(0);

  // الدخول المباشر بالرابط يُردّ برسالة الترخيص لا بالشاشة.
  await page.goto("/after-sales");
  await expect(page.getByText("وحدة خدمة ما بعد البيع غير مفعّلة لهذه الشركة.")).toBeVisible();
  await expect(page.getByTestId("warranty-cards-screen")).toHaveCount(0);
  expect(state.chunkRequests).toEqual([]);
});

test("سجل الأجهزة وحده يبقى بنداً مستقلاً — عقد THA-45: تُطفأ وتُشغَّل باستقلال", async ({ page }) => {
  await mockTenant(page, { afterSales: false, devices: true });
  await page.goto("/dashboard");
  await expect(page.getByRole("button", { name: "الأجهزة الحساسة" })).toBeVisible();
  await expect(page.getByRole("button", { name: "خدمة ما بعد البيع" })).toHaveCount(0);
});

test("مع ترخيص الوحدتين ينتقل بند الأجهزة تحت «خدمة ما بعد البيع» — بند واحد لا اثنان", async ({ page }) => {
  await mockTenant(page, { afterSales: true, devices: true });

  // القسم مطويّ على الرئيسية: لا بند أجهزة مستقلّ بجانبه.
  await page.goto("/dashboard");
  await expect(page.getByRole("button", { name: "خدمة ما بعد البيع" })).toBeVisible();
  await expect(page.getByRole("button", { name: "الأجهزة الحساسة" })).toHaveCount(0);

  // القسم يُفتح تلقائياً على شاشته: البندان داخله، والأجهزة مرة واحدة لا مرتين.
  await page.goto("/after-sales");
  await expect(page.getByRole("button", { name: "بطاقات الكفالة" })).toBeVisible();
  await expect(page.getByRole("button", { name: "الأجهزة الحساسة" })).toHaveCount(1);
});

test("شركة مرخّصة تفتح الشاشة، تُنشئ بطاقة يدوية، وترى حالتها المشتقّة", async ({ page }) => {
  const state = await mockTenant(page, { afterSales: true });

  await page.goto("/after-sales");

  await expect(page.getByTestId("warranty-cards-screen")).toBeVisible();
  expect(state.chunkRequests.length).toBeGreaterThan(0);

  // البطاقة التلقائية القائمة تُعرض بحالتها المحسوبة من تاريخ الانتهاء.
  const autoRow = page.getByRole("row").filter({ hasText: "SN-AUTO-1" });
  await expect(autoRow).toContainText("سارية");
  await expect(autoRow).toContainText("01/08/2027");

  // بطاقة يدوية جديدة
  await page.getByRole("button", { name: "بطاقة يدوية" }).click();
  const dialog = page.getByRole("dialog", { name: "بطاقة كفالة يدوية جديدة" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("الرقم التسلسلي").fill("SN-MANUAL-9");
  await dialog.getByLabel("اسم الجهاز (لجهازٍ لم نبعه)").fill("جهاز زبون خارجي");
  await dialog.getByLabel("بداية الكفالة").fill("2026-08-10");
  await dialog.getByLabel("المدة (أشهر)").fill("6");
  // النهاية مشتقّة من المدة قبل الحفظ — شهور تقويمية لا 30 يوماً.
  await expect(dialog.getByLabel("نهاية الكفالة")).toHaveValue("2027-02-10");
  await dialog.getByRole("button", { name: "حفظ" }).click();

  await expect(dialog).toHaveCount(0);
  const manualRow = page.getByRole("row").filter({ hasText: "SN-MANUAL-9" });
  await expect(manualRow).toContainText("سارية");
  await expect(manualRow).toContainText("10/02/2027");
  expect(state.cards.some((c) => c.serial === "SN-MANUAL-9")).toBe(true);
});
