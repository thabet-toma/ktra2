import { expect, test, type Page } from "@playwright/test";

/**
 * التذكرة 210-F: إثباتُ الرحلة الأعلى من تفعيل خدمة الإدخال حتى الوحدة والتقييم
 * والمحفظة وChampions والربحيّة — بلا shell، عبر شبكةٍ مموَّهةٍ بالكامل
 * (لا خادمَ حقيقياً) على مكوّنات #210 الفعليّة.
 *
 * الأنماط متّبعةٌ من `auth-startup-performance.spec.ts` (حجب service workers،
 * توجيه `**\/*`) و`users-screen-company-scope.spec.ts` (عدّادات `seen` لإثبات
 * أن الشاشة تصل الخادم فعلاً لا مجرّد عرض حالة محلية).
 */

test.use({ serviceWorkers: "block" });

const COMPANY_ID = 501;
const COMPANY_NAME = "شركة النور للتجارة";
const EMPLOYEE_ID = 88;
const EMPLOYEE_NAME = "سامر الموظف";
const WORK_ORDER_TITLE = "فحص فاتورة استيراد";

interface WorkOrderState {
  id: number;
  tenant: number;
  company_name: string;
  assignee: number | null;
  assignee_name: string | null;
  title: string;
  kind: string;
  kind_display: string;
  status: string;
  status_display: string;
  deadline_at: string | null;
  received_at: string;
  created_at: string;
  updated_at: string;
  description: string;
  source: string;
  source_display: string;
  priority: string;
  priority_display: string;
  return_status: string;
  waiting_seconds_total: number;
  waiting_entered_at: string | null;
  approved_at: string | null;
  closed_at: string | null;
  effective_duration_seconds: number;
}

interface DocumentLinkState {
  id: number;
  work_order: number;
  deliverable: number | null;
  document_type: string;
  document_type_display: string;
  document_id: number;
  line_count: number;
  line_count_source: "observed" | "declared";
  line_count_source_display: string;
  recount_reason: string;
  complexity: string;
  complexity_display: string;
  linked_by: number | null;
  created_at: string;
  updated_at: string;
}

interface DeliverableState {
  id: number;
  work_order: number;
  kind: string;
  kind_display: string;
  review_status: "pending" | "approved" | "rejected";
  review_status_display: string;
  content: string;
  payload: Record<string, unknown>;
  file_url: string;
  content_snapshot: Record<string, unknown>;
  rejection_reason: string;
  rejection_category: string;
  rejection_category_display: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
  submitted_by: number | null;
  document_links: DocumentLinkState[];
  created_at: string;
  updated_at: string;
}

/** حالةٌ مشتركةٌ متغيّرة عبر النداءات — تحاكي خادماً حقيقياً بلا خادم حقيقي. */
function buildServerState() {
  return {
    subscription: null as null | Record<string, unknown>,
    nextSubscriptionId: 9001,
    workOrders: [] as WorkOrderState[],
    nextWorkOrderId: 7001,
    documentLinks: [] as DocumentLinkState[],
    nextLinkId: 3001,
    deliverables: [] as DeliverableState[],
    nextDeliverableId: 9101,
    usageEvents: [] as Record<string, unknown>[],
    nextUsageEventId: 5001,
  };
}

async function installMocks(page: Page) {
  const state = buildServerState();

  await page.addInitScript(() => {
    localStorage.setItem("token", "e2e-journey-token");
    localStorage.setItem("userId", "e2e-journey-admin");
    localStorage.setItem("tenantId", "1");
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const p = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    // ── هويّة الجلسة والشركات ────────────────────────────────────────────
    if (p.endsWith("/hr/users/e2e-journey-admin/")) {
      return json({
        id: "e2e-journey-admin", name: "سوبر أدمن المنصّة", role: "manager",
        email: "admin@example.test", employmentStatus: "active",
        isApproved: true, isEmailVerified: true, isSuperAdmin: true,
      });
    }
    if (p.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1, role: "manager", is_default: true, can_access_import: false,
        created_at: "2026-01-01T00:00:00Z",
        tenant: {
          TenantID: 1, CompanyName: "شركة الإدارة", SubscriptionPlan: "Enterprise",
          Status: "Active", CreatedAt: "2026-01-01T00:00:00Z", import_enabled: false,
        },
      }]);
    }
    if (p.endsWith("/permissions/me/")) {
      return json({ role: "manager", is_manager: true, permissions: [] });
    }
    if (p.endsWith("/platform/accountants/pending/")) {
      return json({ results: [], count: 0 });
    }
    if (p.endsWith("/platform/development-notes/") && method === "GET") {
      return json([]);
    }
    if (p.endsWith("/platform/ops/notifications/unread-count/")) {
      return json({ unread_count: 0 });
    }

    // ── لوحة السوبر أدمن وسطح الشركة (تفعيل الخدمة) ──────────────────────
    const companyRow = {
      id: COMPANY_ID, name: COMPANY_NAME, plan: "Enterprise", status: "Active",
      import_enabled: false, is_example: false, member_count: 2,
      created_at: "2026-08-01T00:00:00Z",
      subscription_ends_at: null, subscription_days_left: null, subscription_expired: false,
    };
    if (p.endsWith("/platform/dashboard/")) {
      return json({
        companies: { total: 1, active: 1, trial: 0, suspended: 0 },
        users: { total: 2, active: 2 },
        memberships: 2,
        status_distribution: { Active: 1 },
        plan_distribution: { Enterprise: 1 },
        company_rows: [{
          ...companyRow, branch_count: 1, storage_bytes: 0, storage_asset_count: 0,
          document_count: 0, last_login_at: null, last_activity_at: null, near_limit: [],
        }],
        kpis: {
          active_companies: 1,
          idle_companies: { days: 30, count: 0, companies: [] },
          top_storage: [],
          near_limit_companies: { count: 0, companies: [] },
        },
        storage: { ledger_total_bytes: 0, unattributed_bytes: 0 },
      });
    }
    if (/\/platform\/companies\/\d+\/modules\/$/.test(p)) return json({ results: [] });
    if (/\/platform\/companies\/\d+\/limits\/$/.test(p)) return json({ plan: "Enterprise", results: [] });
    if (/\/platform\/companies\/\d+\/activity\/$/.test(p)) return json({ results: [] });
    if (/\/platform\/companies\/\d+\/$/.test(p) && method === "GET") {
      return json({
        ...companyRow, members: [], branches: [], storage_bytes: 0, last_activity_at: null,
      });
    }

    // ── اشتراك خدمة الإدخال (§١ من التذكرة: تفعيل الخدمة) ────────────────
    if (/\/platform\/ops\/subscriptions\/$/.test(p) && method === "GET") {
      return json(state.subscription ? [state.subscription] : []);
    }
    if (p.endsWith("/platform/ops/subscriptions/start-trial/") && method === "POST") {
      const now = new Date();
      const trialEnds = new Date(now.getTime() + 14 * 24 * 3600 * 1000);
      state.subscription = {
        id: state.nextSubscriptionId++, tenant: COMPANY_ID, plan: "standard",
        status: "trial", status_display: "تجربة",
        monthly_fee: "500.00", included_quota: 100, consumed_quota: 0,
        overage_unit_price: "5.00", billing_customer: null, billing_customer_name: null,
        trial_started_at: now.toISOString(), trial_ends_at: trialEnds.toISOString(),
        scheduled_cancellation_date: null, cancellation_reason: "",
        active_engagements_count: 0,
      };
      return json(state.subscription);
    }

    // ── أوامر العمل (§٢-٤: إنشاء ← ربط مستند ← تسليم ← اعتماد) ──────────
    if (p.endsWith("/platform/ops/work-orders/create/") && method === "POST") {
      const body = request.postDataJSON() as { tenant: number; title: string };
      const now = new Date().toISOString();
      const row: WorkOrderState = {
        id: state.nextWorkOrderId++, tenant: body.tenant, company_name: COMPANY_NAME,
        assignee: null, assignee_name: null, title: body.title,
        kind: "channel_intake", kind_display: "إدخال",
        status: "received", status_display: "مستلم",
        deadline_at: null, received_at: now, created_at: now, updated_at: now,
        description: "", source: "staff", source_display: "موظف",
        priority: "normal", priority_display: "عادية", return_status: "",
        waiting_seconds_total: 0, waiting_entered_at: null,
        approved_at: null, closed_at: null, effective_duration_seconds: 0,
      };
      state.workOrders.push(row);
      return json(row, 201);
    }
    if (p.endsWith("/platform/ops/work-orders/queue/")) return json([]);
    if (/\/platform\/ops\/work-orders\/$/.test(p) && method === "GET") {
      return json(state.workOrders);
    }
    if (/\/platform\/ops\/work-orders\/\d+\/comments\/$/.test(p)) {
      if (method === "GET") return json([]);
    }
    if (/\/platform\/ops\/engagements\/candidates\/$/.test(p)) return json([]);

    const linkDocMatch = p.match(/\/platform\/ops\/work-orders\/(\d+)\/link-document\/$/);
    if (linkDocMatch && method === "POST") {
      const workOrderId = Number(linkDocMatch[1]);
      const body = request.postDataJSON() as { document_type: string; document_id: number; line_count?: number };
      const now = new Date().toISOString();
      const row: DocumentLinkState = {
        id: state.nextLinkId++, work_order: workOrderId, deliverable: null,
        document_type: body.document_type, document_type_display: "فاتورة بيع",
        document_id: body.document_id, line_count: body.line_count ?? 1,
        line_count_source: "observed", line_count_source_display: "مرصود من المستند",
        recount_reason: "", complexity: "", complexity_display: "",
        linked_by: 1, created_at: now, updated_at: now,
      };
      state.documentLinks.push(row);
      return json(row, 201);
    }
    const linksListMatch = p.match(/\/platform\/ops\/work-orders\/(\d+)\/document-links\/$/);
    if (linksListMatch && method === "GET") {
      const workOrderId = Number(linksListMatch[1]);
      return json(state.documentLinks.filter((l) => l.work_order === workOrderId));
    }

    const deliverablesMatch = p.match(/\/platform\/ops\/work-orders\/(\d+)\/deliverables\/$/);
    if (deliverablesMatch && method === "GET") {
      const workOrderId = Number(deliverablesMatch[1]);
      return json(state.deliverables.filter((d) => d.work_order === workOrderId));
    }
    if (deliverablesMatch && method === "POST") {
      const workOrderId = Number(deliverablesMatch[1]);
      const body = request.postDataJSON() as { kind?: string; content?: string; document_link_ids?: number[] };
      const now = new Date().toISOString();
      const links = state.documentLinks.filter((l) => (body.document_link_ids ?? []).includes(l.id));
      const row: DeliverableState = {
        id: state.nextDeliverableId++, work_order: workOrderId,
        kind: body.kind ?? "note", kind_display: "ملاحظة",
        review_status: "pending", review_status_display: "بانتظار المراجعة",
        content: body.content ?? "", payload: {}, file_url: "", content_snapshot: {},
        rejection_reason: "", rejection_category: "", rejection_category_display: "",
        reviewed_by: null, reviewed_at: null, submitted_by: 1,
        document_links: links, created_at: now, updated_at: now,
      };
      state.deliverables.push(row);
      links.forEach((l) => { l.deliverable = row.id; });
      return json(row, 201);
    }

    const reviewMatch = p.match(/\/platform\/ops\/work-orders\/(\d+)\/deliverables\/(\d+)\/review\/$/);
    if (reviewMatch && method === "POST") {
      const deliverableId = Number(reviewMatch[2]);
      const body = request.postDataJSON() as { review_status: "approved" | "rejected" };
      const deliverable = state.deliverables.find((d) => d.id === deliverableId)!;
      const now = new Date().toISOString();
      deliverable.reviewed_by = 1;
      deliverable.reviewed_at = now;
      if (body.review_status === "approved") {
        deliverable.review_status = "approved";
        deliverable.review_status_display = "مقبول";
        const event = {
          id: state.nextUsageEventId++, tenant: COMPANY_ID, company_name: COMPANY_NAME,
          subscription: (state.subscription as { id: number } | null)?.id ?? 0,
          work_order: deliverable.work_order, deliverable: deliverable.id,
          document_link: deliverable.document_links[0]?.id ?? null,
          event_type: "usage", event_type_display: "استخدام",
          source_type: "sales_invoice", source_type_display: "فاتورة بيع",
          source_id: deliverable.document_links[0]?.document_id ?? 0,
          line_count_snapshot: deliverable.document_links[0]?.line_count ?? 0,
          line_count_source: "observed", line_count_source_display: "مرصود من المستند",
          catalog_version: 3, units: "6.50",
          chargeable_to_customer: true, creditable_to_employee: true,
          employee: EMPLOYEE_ID, employee_name: EMPLOYEE_NAME,
          approved_by: 1, approved_at: now, period_start: "2026-09-01", period_end: "2026-09-30",
          idempotency_key: `platform_ops:usage:doclink:${deliverable.document_links[0]?.id}`,
          reversed_event: null, reason: "", correlation_id: "e2e-corr-1", created_at: now,
        };
        state.usageEvents.push(event);
        return json({ deliverable, usage_events: [event] });
      }
      deliverable.review_status = "rejected";
      deliverable.review_status_display = "مرفوض";
      deliverable.rejection_reason = (body as { rejection_reason?: string }).rejection_reason ?? "";
      deliverable.rejection_category = (body as { rejection_category?: string }).rejection_category ?? "";
      return json(deliverable);
    }

    if (/\/platform\/ops\/usage-events\/$/.test(p) && method === "GET") {
      return json(state.usageEvents);
    }

    // ── لوحة عمليات المنصة (نظرة عامة + محفظة الموظّف) ───────────────────
    if (p.endsWith("/platform/ops/dashboard/")) {
      return json({
        view_unit: "employee",
        employees: [{
          id: EMPLOYEE_ID, user_id: 880, name: EMPLOYEE_NAME, username: "samer",
          email: "samer@example.test", specialty: "إدخال بيانات", capacity_target: 10,
          status: "active", active_work_orders_count: 1, overdue_work_orders_count: 0,
          last_active_at: new Date().toISOString(), is_recently_active: true,
        }],
        companies: [],
        anomalies: [], total_anomalies_count: 0, generated_at: new Date().toISOString(),
      });
    }
    if (new RegExp(`/platform/ops/employees/${EMPLOYEE_ID}/wallet/`).test(p)) {
      return json({
        employee_id: EMPLOYEE_ID, period_year: 2026, period_month: 9,
        totals: { confirmed: "350.00", pending: "120.00", expected: "470.00" },
        salary_lines: [{
          id: 1, employee: EMPLOYEE_ID, employee_name: EMPLOYEE_NAME,
          period_year: 2026, period_month: 9, sequence: 1, amount: "350.00",
          status: "eligible", status_display: "مؤهَّل", pending_reason: "",
          compensation_policy: 1, monthly_close: null, adjustment_of: null,
          reason: "راتب شهر أيلول", approved_by: null, approved_at: null,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }],
        commission_lines: [{
          id: 2, acquisition: 1, company_name: COMPANY_NAME, employee: EMPLOYEE_ID,
          employee_name: EMPLOYEE_NAME, period_year: 2026, period_month: 9, sequence: 1,
          commission_month_index: 1, amount: "120.00", status: "pending",
          status_display: "معلّق", pending_reason: "بانتظار تسجيل الدفع",
          compensation_policy: 1, monthly_close: null, adjustment_of: null, reason: "",
          approved_by: null, approved_at: null,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }],
      });
    }
    if (new RegExp(`/platform/ops/employees/${EMPLOYEE_ID}/pilot-performance/`).test(p)) {
      const axis = (numerator: number, denominator: number, weight: number) => ({
        applicable: true, weight, weight_pct: weight, weight_original: weight,
        weight_original_pct: weight, score: numerator / denominator,
        score_pct: Math.round((numerator / denominator) * 100),
        raw_percent: Math.round((numerator / denominator) * 100),
        uncatalogued_document_links: 0,
        weighted_contribution: Math.round((numerator / denominator) * weight),
        numerator, denominator, exclusions: [],
      });
      return json({
        status: "calculated", status_message: "احتُسب من عيّنة كافية لهذا الشهر.",
        composite_score: 82.5, sample_size: 20, min_sample_size: 10,
        axes: {
          task_completion: axis(41, 50, 40),
          quality_accuracy: axis(27, 30, 30),
          sla_adherence: axis(18, 20, 20),
          customer_satisfaction: axis(9, 10, 10),
        },
        weights_sum: 100, policy_used: {},
      });
    }

    // ── KTRA Champions (§١٠) ──────────────────────────────────────────────
    if (p.endsWith("/platform/ops/champions/")) {
      return json({
        period_year: 2026, period_month: 9,
        categories: [
          {
            category: "paid_acquisition", category_label: "الاكتساب المدفوع",
            unit: "عميل",
            entries: [{
              employee_id: EMPLOYEE_ID, employee_name: EMPLOYEE_NAME, value: 4,
              evidence: "اكتسب 4 عملاء في أيلول 2026 — فوق حدّ العيّنة",
            }],
          },
          {
            category: "documented_improvement", category_label: "التحسّن الموثّق",
            unit: "نقطة", entries: [],
          },
        ],
      });
    }

    // ── ربحيّةُ العميل ومطابقةُ الخطة (§٩) ────────────────────────────────
    if (p.endsWith("/platform/ops/profitability/")) {
      return json({
        period_year: 2026, period_month: 9, allocated_expenses_per_tenant: 0,
        rows: [{
          tenant_id: COMPANY_ID, company_name: COMPANY_NAME,
          period_year: 2026, period_month: 9,
          revenue: 750, monthly_fee: 500, included_quota: 100,
          chargeable_units: 82, overage_units: 0,
          human_cost: 205, allocated_expenses: 0, total_cost: 205,
          margin: 545, margin_pct: 72.67, state: "profitable", state_label: "مربح",
          contributors: [{ employee_id: EMPLOYEE_ID, units: 82, unit_cost: 2.5, cost: 205 }],
          suggestions: [{
            code: "buy_extra_units", label: "شراء وحدات إضافية",
            reason: "استهلاكٌ متكرر فوق الحصة شهرين متتاليين.",
            evidence: { over_quota_months: 2 },
          }],
        }],
      });
    }

    return json([]);
  });

  return state;
}

test("الرحلة الكاملة: تفعيل الخدمة ← أمر عمل ← ربط مستند ← تسليم ← اعتماد يولّد وحدة ← الدفتر ← التقييم والمحفظة ← Champions ← الربحيّة", async ({ page }) => {
  await installMocks(page);

  await test.step("تفعيل خدمة الإدخال للشركة من لوحة السوبر أدمن", async () => {
    await page.goto("/super-admin");
    await expect(page.getByRole("heading", { name: "لوحة تحكم السوبر أدمن" })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: `تحكم بـ${COMPANY_NAME}` }).click();
    await expect(page.getByRole("heading", { name: /تحكم المنصة بالشركة/ })).toBeVisible();
    await expect(page.getByText("الحالة: غير مفعّلة")).toBeVisible();
    await page.getByRole("button", { name: "ابدأ تجربة" }).click();
    await expect(page.getByText(/الحالة: تجربة/)).toBeVisible();
  });

  await test.step("إنشاء أمر عمل جديد للشركة", async () => {
    // انتقالٌ أوّلٌ إلى مسارٍ محمَّلٍ كسولاً — Vite البارد يحتاج مهلةً صريحة
    // بدل `expect` سريعٍ قد يفشل عشوائياً (فخٌّ موثَّق في البريف).
    await page.goto("/super-admin/platform-ops");
    await expect(page.getByRole("heading", { name: "مركز قيادة عمليات المنصة" }))
      .toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "أوامر العمل", exact: true }).click();
    await page.getByRole("button", { name: "+ جديد" }).click();

    await page.getByPlaceholder("ابحث باسم الشركة...").fill(COMPANY_NAME);
    await page.getByRole("button", { name: new RegExp(COMPANY_NAME) }).click();
    await page.getByPlaceholder("عنوان أمر العمل").fill(WORK_ORDER_TITLE);
    await page.getByRole("button", { name: /^إنشاء/ }).click();

    await expect(page.getByRole("button", { name: new RegExp(WORK_ORDER_TITLE) })).toBeVisible();
  });

  await test.step("ربط مستند وتسليم عمل واعتماده — يولّد وحدة استخدام", async () => {
    await page.getByRole("button", { name: new RegExp(WORK_ORDER_TITLE) }).click();
    await expect(page.getByText("ربط مستند")).toBeVisible();

    await page.getByPlaceholder("رقم المستند").fill("555");
    await page.getByPlaceholder("عدد السطور").fill("12");
    await page.getByRole("button", { name: "ربط", exact: true }).click();
    await expect(page.getByText(/فاتورة بيع #555/)).toBeVisible();
    await expect(page.getByText("(مرصود من المستند)")).toBeVisible();

    await page.getByRole("checkbox").check();
    await page.getByPlaceholder("ملاحظة التسليم...").fill("تم إدخال الفاتورة وربطها بالمستند.");
    await page.getByRole("button", { name: "تسليم" }).click();
    await expect(page.getByText("بانتظار المراجعة")).toBeVisible();

    await page.getByRole("button", { name: "اعتماد" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "اعتماد" }).click();
    await expect(page.getByRole("alert")).toContainText("اعتُمد المُسلَّم");
    await expect(page.getByText("مقبول")).toBeVisible();
  });

  await test.step("الوحدة المُولَّدة تظهر في دفتر الاستخدام", async () => {
    await page.getByRole("button", { name: "دفتر الاستخدام" }).click();
    const row = page.locator("tbody tr").filter({ hasText: COMPANY_NAME });
    await expect(row).toBeVisible();
    await expect(row).toContainText("6.5");
    await expect(row).toContainText(EMPLOYEE_NAME);
    await expect(row).toContainText("v3");
  });

  await test.step("التقييمُ الشهريّ ومحاورُه، ومحفظةُ الموظّف بأرقامها الثلاثة", async () => {
    await page.getByRole("button", { name: "محفظة الموظف" }).click();
    await page.getByLabel("الموظّف").selectOption(String(EMPLOYEE_ID));
    await page.getByRole("button", { name: "عرض" }).click();

    await expect(page.getByText("مؤكَّد")).toBeVisible();
    // أرقامُ المحفظة تُقرأ بجوار تسمياتها لا بصنفِ Tailwind: محدِّدٌ مثل
    // `p.text-emerald-700` يربط الاختبارَ بلونٍ يكسره أوّلُ إعادةِ تنسيق.
    // `.first()` لأنّ الرقمَ يظهر مرّتين عن قصد: في بطاقة المجاميع وفي سطر
    // تفصيله — والمقصودُ هنا وصولُه إلى الشاشة لا موضعُه.
    await expect(page.getByText("350", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("120", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("إنجاز العمل المقبول")).toBeVisible();
    await expect(page.getByText("الدقة والجودة")).toBeVisible();
    await expect(page.getByText("الالتزام بالأجل")).toBeVisible();
    await expect(page.getByText("رضا العملاء")).toBeVisible();
  });

  await test.step("KTRA Champions — إيجابيّةٌ فقط", async () => {
    await page.getByRole("button", { name: "Champions", exact: true }).click();
    await expect(page.getByText("KTRA Champions")).toBeVisible();
    await expect(page.getByText("الاكتساب المدفوع")).toBeVisible();
    await expect(page.getByText(EMPLOYEE_NAME)).toBeVisible();
    await expect(page.getByText("لا مرشّحين بحدّ العينة هذا الشهر.")).toBeVisible();
  });

  await test.step("ربحيّةُ العميل ومطابقةُ الخطة", async () => {
    await page.getByRole("button", { name: "الربحيّة" }).click();
    await expect(page.getByText("مربح")).toBeVisible();
    await page.getByRole("button", { name: new RegExp(COMPANY_NAME) }).click();
    await expect(page.getByText("مصادرُ الأرقام")).toBeVisible();
    await expect(page.getByText("شراء وحدات إضافية")).toBeVisible();
  });
});

test("مساحة موظّف عمليات المنصة: حالة التحميل ثم الرفض الصريح لغير المخوَّل", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("token", "e2e-employee-token");
    localStorage.setItem("userId", "e2e-plain-manager");
    localStorage.setItem("tenantId", "1");
  });

  let resolveCapabilities: (() => void) | null = null;
  const capabilitiesGate = new Promise<void>((resolve) => { resolveCapabilities = resolve; });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const p = url.pathname;

    if (p.endsWith("/hr/users/e2e-plain-manager/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        id: "e2e-plain-manager", name: "مديرة الشركة", role: "manager",
        email: "manager@example.test", employmentStatus: "active",
        isApproved: true, isEmailVerified: true, isSuperAdmin: false,
      }) });
    }
    if (p.endsWith("/tenants/companies/my-companies/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([{
        id: 1, role: "manager", is_default: true, can_access_import: false,
        created_at: "2026-01-01T00:00:00Z",
        tenant: {
          TenantID: 1, CompanyName: "شركة عادية", SubscriptionPlan: "Basic",
          Status: "Active", CreatedAt: "2026-01-01T00:00:00Z", import_enabled: false,
        },
      }]) });
    }
    if (p.endsWith("/permissions/me/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        role: "manager", is_manager: true, permissions: [],
      }) });
    }
    // بوابةُ القدرات — تتأخّر عمداً كي نُثبت أن الشاشة تعرض حالة تحميلٍ صريحة
    // لا رفضاً فورياً، ثم ترفض بوضوحٍ حين يحسم الخادمُ الجواب بالرفض.
    if (p.endsWith("/platform-staff/me/")) {
      await capabilitiesGate;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        is_platform_admin: false, is_platform_recruiter: false, is_platform_employee: false,
      }) });
    }
    return route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/platform/employee-space");
  // **مهلةٌ صريحةٌ على أوّل تأكيد**: المسارُ كسولٌ (`lazyPage` في `App.tsx`) وVite
  // الباردُ يبني الحزمةَ عند أوّل طلب، فمهلةُ 5 ثوانٍ الافتراضيّة تسقط عشوائيّاً
  // قبل أن تُركَّب الشاشةُ أصلاً — وهذا بالضبط ما جعل هذا الاختبار `flaky` أوّلَ
  // تشغيلٍ له (مرّ بإعادة المحاولة، فقُرئ «ناجحاً» وهو غيرُ مستقرّ).
  await expect(page.getByText("جارٍ التحقّق من صلاحيّاتك...")).toBeVisible({ timeout: 30_000 });

  resolveCapabilities!();
  await expect(page.getByText("هذه المساحة مخصّصةٌ لموظّفي عمليات المنصة."))
    .toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("جارٍ التحقّق من صلاحيّاتك...")).toHaveCount(0);
});
