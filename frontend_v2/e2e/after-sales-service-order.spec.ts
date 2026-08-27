import { expect, test, type Page } from "@playwright/test";

/**
 * THA-24 م4 — رحلة أمر الصيانة: استقبال ← إصلاح ← قطع ← فوترة ← تسليم.
 *
 * ما يُثبَت هنا لا يُثبته `tsc` (لا يفحص خصائص JSX في هذا المستودع) ولا اختبار
 * الوحدة: أن الشاشة **حيّة** وأنها تحترم عقود الخادم بدل أن تجتهد فوقها.
 *
 * المخزن الوهمي يُحاكي حرّاس الخادم نفسها — الموانع محسوبة فيه لا مكتوبة
 * ثابتةً: لو كانت الشاشة تستنتج الموانع بنفسها بدل عرض ما يرسله الخادم، لمرّ
 * هذا الاختبار وهو لا يقيس شيئاً.
 */

test.use({ serviceWorkers: "block" });

const PROFILE = {
  id: "svc-user",
  name: "فنيّ الكاونتر",
  role: "manager",
  email: "svc@example.test",
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
  "aftersales.order.view",
  "aftersales.order.create",
  "aftersales.order.edit",
  "aftersales.order.post",
  "aftersales.order.unpost",
  "aftersales.warranty.view",
  "inventory.item.view",
];

const PRODUCTS = [
  { id: 7, sku: "P-0007", display_name: "شاشة بديلة", name_ar: "شاشة بديلة", sale_price: "80" },
];

const PARTNERS = [{ id: 3, name: "زبون تجريبي", partner_type: "customer", phone: "0599123456" }];

/** تغطية وحدةٍ بعناها — بطاقة سارية + نسب الوحدة، كما يردّها `lookup/`. */
const COVERAGE = {
  serial: "SN-9",
  covered: true,
  supplier_covered: false,
  cards: [{
    id: 1, serial: "SN-9", product: 7, device_name: "جهاز لوحي",
    start_date: "2026-08-01", end_date: "2027-08-01", duration_months: 12,
    source: "auto_sale", status: "active", days_remaining: 300,
    customer_name: "زبون تجريبي", partner: 3, supplier: null,
    supplier_warranty_end_date: null, supplier_warranty_active: false,
  }],
  unit: {
    id: 11, serial: "SN-9", status: "sold", status_display: "مُباع", product: 7,
    product_name: "جهاز لوحي", warranty_months: 12, supplier_warranty_months: 24,
    sales_invoice: 9, sales_invoice_number: "SI-9", sale_date: "2026-08-01",
    customer_name: "زبون تجريبي",
  },
};

interface MockPart {
  id: number;
  product: number;
  product_name: string;
  quantity: string;
  billing: "billable" | "covered";
  unit_price: string;
  sales_invoice_line: number | null;
  materialized_at: string | null;
}

interface MockOrder {
  id: number;
  order_number: string;
  order_date: string;
  partner: number | null;
  customer_name: string;
  customer_phone: string;
  product: number | null;
  serial: string;
  device_description: string;
  complaint: string;
  diagnosis: string;
  resolution: string;
  status: string;
  outcome: string;
  warranty_covered: boolean;
  warranty_card: number | null;
  covered_posted_at: string | null;
  sales_invoice: number | null;
  sales_invoice_number: string | null;
  billing_waived_reason: string;
  estimated_amount: string | null;
  parts: MockPart[];
  events: { id: number; text: string; event_type: string; created_at: string }[];
}

const STATUS_LABELS: Record<string, string> = {
  received: "مُستلَم", in_diagnosis: "قيد التشخيص", awaiting_approval: "بانتظار الموافقة",
  in_repair: "قيد الإصلاح", ready: "جاهز للتسليم", delivered: "تم التسليم", cancelled: "ملغى",
};

const OUTCOME_LABELS: Record<string, string> = {
  repaired: "تم الإصلاح", unrepaired: "تعذّر الإصلاح",
  rejected_estimate: "رفض الزبون التقدير", no_fault: "لا عطل", "": "",
};

/** الحرّاس نفسها التي في `after_sales/service_orders.py` — محسوبة لا ثابتة. */
function deliveryBlockers(order: MockOrder): string[] {
  const blockers: string[] = [];
  const pending = order.parts.filter((p) => p.billing === "covered" && !p.materialized_at).length;
  if (pending) blockers.push(`${pending} قطعة مغطاة بالكفالة لم تُرحَّل بعد — رحّل صرفها أولاً.`);
  if (!order.sales_invoice && !order.billing_waived_reason.trim()) {
    blockers.push("لم يُحسم أمر الفوترة — ولّد فاتورة الصيانة أو اكتب سبب الإعفاء من الفوترة.");
  }
  return blockers;
}

function cancellationBlockers(order: MockOrder): string[] {
  const blockers: string[] = [];
  if (order.covered_posted_at) blockers.push("صرف قطع الكفالة مرحَّل — تراجع عن ترحيله قبل الإلغاء.");
  if (order.sales_invoice) blockers.push("للأمر فاتورة صيانة مرتبطة — افصلها أو ألغِها قبل إلغاء الأمر.");
  return blockers;
}

const orderJson = (order: MockOrder) => ({
  ...order,
  status_label: STATUS_LABELS[order.status],
  outcome_label: OUTCOME_LABELS[order.outcome] ?? "",
  partner_name: order.partner ? PARTNERS[0].name : order.customer_name,
  product_name: order.product ? PRODUCTS[0].display_name : order.device_description,
  received_condition: "",
  accessories: "",
  technician: null,
  technician_name: "",
  warranty_status: order.warranty_card
    ? {
        id: 1, end_date: "2027-08-01", status: "active", days_remaining: 300,
        supplier_warranty_end_date: null, supplier_warranty_active: false,
      }
    : null,
  supplier_claim: false,
  supplier_claim_note: "",
  approved_at: null,
  approved_by: null,
  photos: [],
  notes: "",
  delivered_at: null,
  created_at: "2026-08-12T08:00:00Z",
  updated_at: "2026-08-12T08:00:00Z",
  parts: order.parts.map((p) => ({
    ...p,
    billing_label: p.billing === "covered" ? "مغطاة بالكفالة" : "مفوترة على الزبون",
    is_materialized: p.materialized_at !== null,
    notes: "",
    created_at: "2026-08-12T08:00:00Z",
  })),
  events: order.events.map((e) => ({
    ...e, event_type_label: "حدث", from_status: "", to_status: "", actor: 1, actor_name: "فنيّ الكاونتر",
  })),
  delivery_blockers: deliveryBlockers(order),
  cancellation_blockers: cancellationBlockers(order),
});

async function mockServer(page: Page): Promise<{ orders: MockOrder[] }> {
  const orders: MockOrder[] = [];
  let nextId = 1;
  let nextPartId = 1;
  let nextEventId = 1;

  const logEvent = (order: MockOrder, text: string) => {
    order.events.push({
      id: nextEventId++, text, event_type: "status", created_at: "2026-08-12T08:00:00Z",
    });
  };

  await page.addInitScript(() => {
    localStorage.setItem("token", "svc-token");
    localStorage.setItem("userId", "svc-user");
    localStorage.setItem("tenantId", "42");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const path = url.pathname;
    const method = route.request().method();
    const json = (body: unknown) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });

    if (path.endsWith("/hr/users/svc-user/")) return json(PROFILE);
    if (path.endsWith("/tenants/companies/my-companies/")) return json([MEMBERSHIP]);
    if (path.endsWith("/permissions/me/")) {
      return json({
        role: "manager", is_manager: true, permissions: PERMISSION_KEYS,
        modules: { after_sales: true, sensitive_devices: false },
      });
    }
    if (path.includes("/inventory/products/")) return json(PRODUCTS);
    if (path.includes("/partners/lookup/")) return json(PARTNERS);

    if (path.includes("/after-sales/service-orders/")) {
      const tail = path.split("/service-orders/")[1] || "";
      const byId = (id: string) => orders.find((o) => String(o.id) === id);

      if (tail.startsWith("lookup/")) {
        const term = url.searchParams.get("serial") || "";
        return json({
          term,
          warranty: term === "SN-9"
            ? COVERAGE
            : { serial: term, covered: false, cards: [], unit: null },
          sensitive_devices: [],
          open_orders: [],
        });
      }

      if (!tail && method === "POST") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        const order: MockOrder = {
          id: nextId, order_number: `SO-42-${nextId}`, order_date: String(body.order_date || "2026-08-12"),
          partner: (body.partner as number) ?? null,
          customer_name: String(body.customer_name || ""),
          customer_phone: String(body.customer_phone || ""),
          product: (body.product as number) ?? null,
          serial: String(body.serial || ""),
          device_description: String(body.device_description || ""),
          complaint: String(body.complaint || ""),
          diagnosis: "", resolution: "", status: "received", outcome: "",
          warranty_covered: Boolean(body.warranty_covered),
          warranty_card: (body.warranty_card as number) ?? null,
          covered_posted_at: null, sales_invoice: null, sales_invoice_number: null,
          billing_waived_reason: "", estimated_amount: null, parts: [], events: [],
        };
        nextId += 1;
        logEvent(order, "استُلم الجهاز");
        orders.unshift(order);
        return json(orderJson(order));
      }

      if (!tail && method === "GET") {
        return json({ count: orders.length, next: null, previous: null, results: orders.map(orderJson) });
      }

      const [id, action, partId] = tail.replace(/\/$/, "").split("/");
      const order = byId(id);
      if (!order) return route.fulfill({ status: 404, body: "{}" });

      if (!action && method === "GET") return json(orderJson(order));
      if (!action && method === "PATCH") {
        Object.assign(order, route.request().postDataJSON());
        return json(orderJson(order));
      }

      if (action === "transition") {
        const body = route.request().postDataJSON() as { to_status: string; outcome?: string };
        if (body.to_status === "delivered") {
          const blockers = deliveryBlockers(order);
          if (blockers.length) {
            return route.fulfill({
              status: 400, contentType: "application/json",
              body: JSON.stringify({ detail: `تعذّر التسليم: ${blockers.join(" • ")}` }),
            });
          }
          order.outcome = body.outcome || "";
        }
        logEvent(order, `الحالة: ${STATUS_LABELS[order.status]} ← ${STATUS_LABELS[body.to_status]}`);
        order.status = body.to_status;
        return json(orderJson(order));
      }

      if (action === "parts" && method === "POST") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        order.parts.push({
          id: nextPartId++, product: Number(body.product), product_name: PRODUCTS[0].display_name,
          quantity: String(body.quantity), billing: body.billing as "billable" | "covered",
          unit_price: String(body.unit_price ?? "0"), sales_invoice_line: null, materialized_at: null,
        });
        return json({ id: nextPartId - 1 });
      }

      if (action === "parts" && method === "DELETE") {
        order.parts = order.parts.filter((p) => String(p.id) !== partId);
        return route.fulfill({ status: 204, body: "" });
      }

      if (action === "post-covered") {
        // الالتقاط بالنوع **وغياب القفل** معاً — حارس التجسّد المزدوج نفسه.
        const pending = order.parts.filter((p) => p.billing === "covered" && !p.materialized_at);
        if (!pending.length) {
          return route.fulfill({
            status: 400, contentType: "application/json",
            body: JSON.stringify({ detail: "لا توجد قطع مغطاة بالكفالة بانتظار الترحيل." }),
          });
        }
        pending.forEach((p) => { p.materialized_at = "2026-08-12T09:00:00Z"; });
        order.covered_posted_at = "2026-08-12T09:00:00Z";
        return json({ posted: { parts: pending.length }, order: orderJson(order) });
      }

      if (action === "unpost-covered") {
        order.parts.filter((p) => p.billing === "covered").forEach((p) => { p.materialized_at = null; });
        order.covered_posted_at = null;
        return json({ unposted: {}, order: orderJson(order) });
      }

      if (action === "generate-invoice") {
        const pending = order.parts.filter((p) => p.billing === "billable" && !p.materialized_at);
        pending.forEach((p, index) => {
          p.materialized_at = "2026-08-12T09:30:00Z";
          p.sales_invoice_line = 100 + index;
        });
        order.sales_invoice = 55;
        order.sales_invoice_number = "SI-42-55";
        return json({
          invoice: { id: 55, invoice_number: "SI-42-55", status: "draft", grand_total: "160.00" },
          order: orderJson(order),
        });
      }

      if (action === "note") {
        logEvent(order, String((route.request().postDataJSON() as { text: string }).text));
        return json({ id: nextEventId, text: "", event_type: "note", created_at: "2026-08-12T09:00:00Z" });
      }
    }

    return json([]);
  });

  return { orders };
}

test("رحلة كاملة: استقبال بتغطية ← إصلاح ← قطعة مغطاة تُرحَّل ← قطعة مفوترة ← تسليم", async ({ page }) => {
  const state = await mockServer(page);

  await page.goto("/after-sales/service-orders");
  await expect(page.getByTestId("service-orders-screen")).toBeVisible();

  // ── الاستقبال: المعرّف يجلب التغطية ونسب الوحدة ──────────────────────
  await page.getByTestId("open-intake").click();
  const intake = page.getByTestId("service-order-intake");
  await expect(intake).toBeVisible();
  await intake.getByLabel(/الرقم التسلسلي أو IMEI/).fill("SN-9");
  await expect(intake.getByTestId("intake-lookup-results")).toContainText("بطاقة كفالة تنتهي");
  await expect(intake.getByTestId("intake-lookup-results")).toContainText("بيعت بفاتورة SI-9");

  await intake.getByRole("button", { name: "تعبئة من الوحدة" }).click();
  await intake.getByLabel("شكوى الزبون (بكلماته)").fill("لا يشحن");
  await intake.getByRole("button", { name: "فتح أمر الصيانة" }).click();

  // ── المستند: شريط التغطية ثم نقل الحالة ──────────────────────────────
  const doc = page.getByTestId("service-order-document");
  await expect(doc).toBeVisible();
  await expect(doc.getByTestId("warranty-banner")).toContainText("الكفالة تنتهي");
  await expect(doc).toContainText("SO-42-1");

  await doc.getByRole("button", { name: "قيد الإصلاح" }).click();
  await expect(doc.getByRole("button", { name: "قيد الإصلاح" })).toBeDisabled();

  // ── قطعة مغطاة: تُضاف ثم يُرحَّل صرفها، فينقلب الزر إلى تراجع ─────────
  await doc.getByRole("button", { name: "قطع الغيار", exact: false }).click();
  await doc.getByLabel("المنتج").selectOption("7");
  await doc.getByLabel("المسار").selectOption("covered");
  await doc.getByRole("button", { name: "إضافة قطعة" }).click();
  await expect(doc.getByRole("row").filter({ hasText: "مغطاة بالكفالة" })).toBeVisible();

  await doc.getByTestId("post-covered").click();
  await expect(doc.getByTestId("unpost-covered")).toBeVisible();
  await expect(doc.getByTestId("post-covered")).toHaveCount(0);
  await expect(doc.getByRole("row").filter({ hasText: "مرحَّل صرفها" })).toBeVisible();

  // ── التسليم ممنوع ما دام أمر الفوترة غير محسوم — والسبب معروضٌ نصّاً ──
  await expect(doc.getByTestId("delivery-blockers")).toContainText("لم يُحسم أمر الفوترة");
  await expect(doc.getByTestId("deliver-button")).toBeDisabled();

  // ── قطعة مفوترة ← فاتورة مسودة تُربط بالأمر ──────────────────────────
  await doc.getByLabel("المسار").selectOption("billable");
  await doc.getByLabel("المنتج").selectOption("7");
  await doc.getByRole("button", { name: "إضافة قطعة" }).click();
  await doc.getByTestId("generate-invoice").click();
  await expect(doc).toContainText("فاتورة SI-42-55");

  // ── التسليم انفتح بعد حسم الفوترة ────────────────────────────────────
  await expect(doc.getByTestId("delivery-blockers")).toHaveCount(0);
  await doc.getByLabel("نتيجة الصيانة").selectOption("repaired");
  await doc.getByTestId("deliver-button").click();

  await expect(doc).toContainText("تم التسليم");
  expect(state.orders[0].status).toBe("delivered");
  expect(state.orders[0].outcome).toBe("repaired");
  // بندان، كلٌّ تجسّد في مستنده وحده — لا بند في المستندين.
  expect(state.orders[0].parts.filter((p) => p.sales_invoice_line !== null).length).toBe(1);
  expect(state.orders[0].parts.filter((p) => p.billing === "covered" && p.materialized_at).length).toBe(1);
});

test("سبب الإعفاء من الفوترة يفتح التسليم بلا فاتورة", async ({ page }) => {
  await mockServer(page);

  await page.goto("/after-sales/service-orders");
  await page.getByTestId("open-intake").click();
  const intake = page.getByTestId("service-order-intake");
  await intake.getByLabel("اسم الزبون").fill("زبون عابر");
  await intake.getByLabel("وصف الجهاز").fill("هاتف");
  await intake.getByLabel("شكوى الزبون (بكلماته)").fill("شاشة مكسورة");
  await intake.getByRole("button", { name: "فتح أمر الصيانة" }).click();

  const doc = page.getByTestId("service-order-document");
  await expect(doc.getByTestId("delivery-blockers")).toContainText("لم يُحسم أمر الفوترة");

  await doc.getByRole("button", { name: "إعفاء: مغطى بالكفالة" }).click();
  await doc.getByRole("button", { name: "حفظ الملف" }).click();

  await expect(doc.getByTestId("delivery-blockers")).toHaveCount(0);
  await doc.getByTestId("deliver-button").click();
  await expect(doc).toContainText("تم التسليم");
});
