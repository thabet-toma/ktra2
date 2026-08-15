import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const membership = {
  id: 42,
  tenant: {
    TenantID: 42,
    CompanyName: "شركة الاختبار",
    SubscriptionPlan: "Enterprise",
    Status: "Active",
    CreatedAt: "2026-07-22T00:00:00Z",
    import_enabled: true,
    is_example: false,
  },
  role: "manager",
  is_default: true,
  created_at: "2026-07-22T00:00:00Z",
  can_access_import: true,
};

const companyDashboard = {
  period: { from: "2026-07-20", to: "2026-07-26" },
  is_new_company: false,
  financials: { revenue: 0, expenses: 0, net_profit: 0 },
  sales_invoices: { total: 0, posted: 0, draft: 0, recent: [] },
  purchase_invoices: { total: 0, posted: 0, draft: 0, recent: [] },
  inventory: {
    total_products: 0, in_stock: 0, low_stock: 0, out_of_stock: 0,
    inventory_value: 0, movements_this_month: 0, low_stock_items: [],
  },
  accounting: { journals_this_month: 0 },
  alerts: [],
};

const companyMembers = [
  {
    membership_id: 7, user_id: 70, username: "mgr", email: "mgr@example.test",
    full_name: "مدير الشركة", role: "manager", is_default: true,
    can_access_import: true, is_active: true, created_at: "2026-07-22T00:00:00Z",
  },
  {
    membership_id: 8, user_id: 80, username: "sami", email: "sami@example.test",
    full_name: "سامي", role: "staff", is_default: false,
    can_access_import: false, is_active: true, created_at: "2026-07-22T00:00:00Z",
  },
];

async function installMocks(page: Page, isSuperAdmin: boolean) {
  /** آخر أجسام الطلبات — تثبت أن أزرار اللوحة تصل الخادم فعلاً */
  const calls: Record<string, any> = {};
  const company = {
    id: 42, name: "شركة الاختبار", plan: "Enterprise", status: "Active",
    import_enabled: true, is_example: false, member_count: 2, created_at: "2026-07-22T00:00:00Z",
    members: companyMembers.map((member) => ({ ...member })),
    branches: [
      { id: 1, name: "الفرع الرئيسي", code: "MAIN" },
      // بلا رمز عمداً — الرمز اختياري في تعريف الفرع فلا يُطبع فاصلٌ يتيم بعده.
      { id: 2, name: "فرع دمشق", code: "" },
    ],
    storage_bytes: 5242880,
    last_activity_at: "2026-08-09T07:30:00Z",
  };
  const companyActivity = [
    {
      timestamp: "2026-08-09T07:30:00Z", user_name: "سوبر أدمن", action: "update",
      action_label: "تعديل", entity_type: "tenant_limit", entity_label: "الفروع",
      description: "الحدّ: 3 ← 5",
    },
    {
      timestamp: "2026-08-08T10:00:00Z", user_name: "ندى", action: "post",
      action_label: "ترحيل", entity_type: "sales_invoice", entity_label: "INV-1001",
      description: "",
    },
  ];
  // مبعثرة عمداً (المكتملة أولاً والأقدم في الوسط) — الشاشة تُرتّبها بنفسها:
  // الأهمّ أولاً، والأقدم أولاً داخل الأولوية الواحدة، والمكتملة في قسمها.
  const developmentNotes = [
    {
      id: 3, title: "ترحيل الشاشة القديمة", description: "أُنجزت",
      status: "done", priority: "low", images: [],
      due_date: null, completed_at: "2026-08-05T09:00:00Z", created_by: 1,
      created_by_name: "سوبر أدمن", updated_by: 1, updated_by_name: "سوبر أدمن",
      created_at: "2026-08-01T09:00:00Z", updated_at: "2026-08-01T09:00:00Z",
      comments: [],
    },
    {
      id: 1, title: "تحسين شاشة الجرد",
      // وصف طويل عمداً — أطول من سطرين في الجدول، فيُختبر القصّ وكشفُه الكامل
      // داخل نافذة التعديل.
      description: [
        "إضافة فلتر للمستودع مع إظهار كامل تفاصيل الملاحظة الطويلة للمحاسب والمخلّص.",
        "ويشمل ذلك ترتيب الأعمدة وحفظ تفضيلات كل مستخدم على حدة دون خلط بين الشاشات.",
        "كما يلزم بيان أثر الفلتر على تقارير الجرد والمخزون المتاح والمحجوز معاً.",
        "وأخيراً تُراجع الحالات الحدّية: مستودع بلا حركة، وصنف محجوز بالكامل.",
      ].join("\n"),
      status: "in_progress", priority: "high", images: [],
      due_date: "2026-08-10", completed_at: null, created_by: 1,
      created_by_name: "سوبر أدمن", updated_by: 1, updated_by_name: "سوبر أدمن",
      created_at: "2026-08-01T10:00:00Z", updated_at: "2026-08-01T10:00:00Z",
      comments: [{
        id: 11, body: "بدأت بالفلتر، والباقي غداً.", created_by: 1,
        created_by_name: "سوبر أدمن", created_at: "2026-08-02T08:00:00Z",
      }],
    },
    {
      id: 2, title: "تقرير الأرباح", description: "مطلوب من المالك",
      status: "todo", priority: "medium", images: [],
      due_date: null, completed_at: null, created_by: 1,
      created_by_name: "سوبر أدمن", updated_by: 1, updated_by_name: "سوبر أدمن",
      created_at: "2026-08-01T11:00:00Z", updated_at: "2026-08-01T11:00:00Z",
      comments: [],
    },
    {
      // الأقدم على الإطلاق ومنخفضة الأولوية — تُثبت أن الأولوية تسبق التاريخ.
      id: 4, title: "توثيق شاشة الإعدادات", description: "متى ما توفّر وقت",
      status: "todo", priority: "low", images: [],
      due_date: null, completed_at: null, created_by: 1,
      created_by_name: "سوبر أدمن", updated_by: 1, updated_by_name: "سوبر أدمن",
      created_at: "2026-08-01T08:00:00Z", updated_at: "2026-08-01T08:00:00Z",
      comments: [],
    },
  ];

  await page.addInitScript(() => {
    localStorage.setItem("token", "platform-e2e-token");
    localStorage.setItem("userId", "platform-e2e-user");
    localStorage.setItem("tenantId", "42");
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/platform-e2e-user/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        id: "platform-e2e-user",
        name: isSuperAdmin ? "سوبر أدمن" : "مدير الشركة",
        role: "manager",
        email: isSuperAdmin ? "platform@example.test" : "manager@example.test",
        employmentStatus: "active",
        isApproved: true,
        isEmailVerified: true,
        isSuperAdmin,
      }) });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([membership]) });
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        role: "manager", is_manager: true, permissions: [],
      }) });
    }
    // بلا هذا المحاكي يبتلع الردّ الافتراضي (`[]`) النداءَ فتصل `results`
    // معدومة، وتموت اللوحة كلها على `pendingAccountants.length` قبل أن تُرسم.
    if (url.pathname.endsWith("/platform/accountants/pending/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        results: [], count: 0,
      }) });
    }
    if (url.pathname.endsWith("/platform/dashboard/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        companies: { total: 3, active: 2, trial: 1, suspended: 0 },
        users: { total: 8, active: 7 },
        memberships: 10,
        status_distribution: { Active: 2, Trial: 1 },
        plan_distribution: { Enterprise: 3 },
        company_rows: [{
          id: 42, name: "شركة الاختبار", plan: "Enterprise", status: "Active",
          import_enabled: true, is_example: company.is_example,
          member_count: 4, created_at: "2026-07-22T00:00:00Z",
          branch_count: 3, storage_bytes: 5242880, storage_asset_count: 12,
          document_count: 180, last_login_at: "2026-08-13T08:00:00Z",
          last_activity_at: "2026-08-14T09:30:00Z",
          near_limit: [{ key: "company.branches", label: "الفروع", usage: 3, limit: 3 }],
        }, {
          // شركة ساكنة بلا بايتات — الحالة الفارغة تُختبر كما يُختبر الرقم.
          id: 43, name: "شركة الظلّ", plan: "Basic", status: "Trial",
          import_enabled: false, is_example: false, member_count: 1,
          created_at: "2026-05-02T00:00:00Z", branch_count: 1,
          storage_bytes: 0, storage_asset_count: 0, document_count: 0,
          last_login_at: null, last_activity_at: null, near_limit: [],
        }],
        kpis: {
          active_companies: 2,
          idle_companies: {
            days: 30, count: 1,
            companies: [{ id: 43, name: "شركة الظلّ", last_activity_at: null }],
          },
          top_storage: [{
            id: 42, name: "شركة الاختبار", storage_bytes: 5242880, storage_asset_count: 12,
          }],
          near_limit_companies: {
            count: 1,
            companies: [{
              id: 42, name: "شركة الاختبار", key: "company.branches",
              label: "الفروع", usage: 3, limit: 3,
            }],
          },
        },
        storage: { ledger_total_bytes: 6291456, unattributed_bytes: 1048576 },
      }) });
    }
    if (/\/platform\/companies\/\d+\/members\/\d+\/$/.test(url.pathname)) {
      calls.memberPatch = request.postDataJSON?.() ?? JSON.parse(request.postData() || "{}");
      const member = company.members.find((row) => url.pathname.includes(`/${row.membership_id}/`));
      Object.assign(member!, calls.memberPatch);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(member) });
    }
    if (/\/platform\/companies\/\d+\/activity\/$/.test(url.pathname)) {
      // عدّاد لا قيمة: يثبت أن القائمة لا تُجلب إلا عند فتح القسم.
      calls.activityHits = (calls.activityHits ?? 0) + 1;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        results: companyActivity,
      }) });
    }
    if (/\/platform\/companies\/\d+\/$/.test(url.pathname)) {
      if (request.method() === "PATCH") {
        calls.companyPatch = JSON.parse(request.postData() || "{}");
        Object.assign(company, calls.companyPatch);
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(company) });
    }
    if (/\/platform\/users\/\d+\/set-active\/$/.test(url.pathname)) {
      calls.setActive = { path: url.pathname, ...JSON.parse(request.postData() || "{}") };
      const member = company.members.find((row) => url.pathname.includes(`/${row.user_id}/`));
      member!.is_active = calls.setActive.is_active;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        id: member!.user_id, username: member!.username, is_active: member!.is_active,
      }) });
    }
    if (url.pathname.endsWith("/platform/development-notes/") && request.method() === "GET") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(developmentNotes) });
    }
    if (/\/platform\/development-notes\/\d+\/comments\/\d+\/$/.test(url.pathname)
      && request.method() === "DELETE") {
      const [, noteId, commentId] = url.pathname.match(/\/(\d+)\/comments\/(\d+)\/$/)!;
      calls.commentDeleted = Number(commentId);
      const note = developmentNotes.find((row) => row.id === Number(noteId));
      note!.comments = note!.comments.filter((row) => row.id !== Number(commentId));
      return route.fulfill({ status: 204, body: "" });
    }
    if (/\/platform\/development-notes\/\d+\/comments\/$/.test(url.pathname)
      && request.method() === "POST") {
      calls.commentPost = request.postDataJSON();
      const note = developmentNotes.find((row) => url.pathname.includes(`/${row.id}/comments/`));
      // الخادم يختم كاتب الردّ — هنا مستخدم آخر غير صاحب الملاحظة (created_by 1).
      const comment = {
        id: 99, body: calls.commentPost.body, created_by: 2,
        created_by_name: "المالك", created_at: "2026-08-06T07:00:00Z",
      };
      note!.comments = [...note!.comments, comment];
      return route.fulfill({
        status: 201, contentType: "application/json", body: JSON.stringify(comment),
      });
    }
    if (/\/platform\/development-notes\/\d+\/$/.test(url.pathname) && request.method() === "PATCH") {
      calls.notePatch = request.postDataJSON();
      const note = developmentNotes.find((row) => url.pathname.includes(`/${row.id}/`));
      const wasStatus = note!.status;
      Object.assign(note!, calls.notePatch);
      // مرآة ختم الخادم: يُختم عند الانتقال إلى done ويُمحى عند الخروج منها.
      if (note!.status !== wasStatus) {
        note!.completed_at = note!.status === "done" ? "2026-08-09T06:00:00Z" : null;
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(note) });
    }
    if (url.pathname.endsWith("/media/upload/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        url: "https://res.cloudinary.com/demo/image/upload/v1/note-shot.png",
      }) });
    }
    if (url.pathname.endsWith("/platform/development-notes/") && request.method() === "POST") {
      const payload = request.postDataJSON();
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({
        id: 9, ...payload, completed_at: null, created_by: 1, created_by_name: "سوبر أدمن",
        updated_by: 1, updated_by_name: "سوبر أدمن",
        created_at: "2026-08-01T12:00:00Z", updated_at: "2026-08-01T12:00:00Z",
        comments: [],
      }) });
    }
    if (url.pathname.endsWith("/dashboard/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(companyDashboard) });
    }
    return route.fulfill({ contentType: "application/json", body: "[]" });
  });

  return calls;
}

test("super admin gets a separate platform dashboard and development notes sheet", async ({ page }) => {
  await installMocks(page, true);
  await page.goto("/super-admin");

  await expect(page.getByRole("heading", { name: "لوحة تحكم السوبر أدمن" })).toBeVisible();
  await expect(page.getByText("إجمالي الشركات")).toBeVisible();
  await expect(page.getByText("شركة الاختبار").last()).toBeVisible();
  await expect(page.getByRole("button", { name: "إدارة المنصة" })).toBeVisible();

  // سكرولر الصفحة لا يتجاوز الشاشة — كان min-height بـ 100vh يقصّ أسفل اللوحة
  // فلا تُرى آخر الشركات مهما سكرلت.
  const overflowBelowViewport = await page.evaluate(() => {
    const main = document.querySelector("main.app-content");
    return main ? main.getBoundingClientRect().bottom - window.innerHeight : null;
  });
  expect(overflowBelowViewport).not.toBeNull();
  expect(overflowBelowViewport as number).toBeLessThanOrEqual(1);

  await page.getByRole("button", { name: /ملاحظات التطوير/ }).first().click();
  await expect(page).toHaveURL(/\/super-admin\/development-notes$/);
  await expect(page.getByRole("heading", { name: "ملاحظات التطوير" })).toBeVisible();
  await expect(page.locator('input[type="date"]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: "تعديل تحسين شاشة الجرد" })).toBeInViewport();
  await expect(page.getByRole("button", { name: "إضافة ملاحظة" })).toBeInViewport();
  await expect(page.getByText("تحسين شاشة الجرد", { exact: true })).toBeVisible();

  // الإضافة من نافذة واحدة صريحة — لا صفّ شبح في ذيل الجدول.
  await page.getByRole("button", { name: "إضافة ملاحظة" }).click();
  await page.getByLabel("العنوان *").fill("إضافة تقرير هامش الربح");
  await page.getByRole("button", { name: "إضافة الملاحظة" }).click();
  await expect(page.getByText("إضافة تقرير هامش الربح", { exact: true })).toBeVisible();
});

test("لوحة المنصة: مؤشرات التشغيل، وأعمدة القياس في جدول الشركات", async ({ page }) => {
  await installMocks(page, true);
  await page.goto("/super-admin");
  await expect(page.getByRole("heading", { name: "لوحة تحكم السوبر أدمن" })).toBeVisible();

  // كروت المؤشرات تسمّي الشركات المعنيّة، لا عددها وحده
  const insights = page.locator('section[aria-label="مؤشرات التشغيل"]');
  await expect(insights.getByText("بلا نشاط 30 يوماً")).toBeVisible();
  await expect(insights.getByText("شركة الظلّ")).toBeVisible();
  await expect(insights.getByText("لا نشاط مسجَّل")).toBeVisible();
  // إجمالي السجلّ (٦ م.ب) غير أعلى شركة فيه (٥ م.ب) — الكرت يعرض الاثنين
  await expect(insights.getByText("6 م.ب", { exact: true })).toBeVisible();
  await expect(insights.getByText("5 م.ب", { exact: true })).toBeVisible();
  await expect(insights.getByText("الفروع 3/3")).toBeVisible();

  const table = page.locator("table").first();
  await expect(table.locator("thead th")).toHaveText([
    "الشركة", "الخطة", "الحالة", "الأعضاء", "الفروع", "المستندات هذا الشهر",
    "التخزين", "آخر نشاط", "الاستيراد", "تاريخ الإنشاء", "تحكم",
  ]);

  const row = (index: number) => table.locator("tbody tr").nth(index);
  await expect(row(0).locator("td").nth(4)).toHaveText("3");
  await expect(row(0).locator("td").nth(5)).toHaveText("180");
  await expect(row(0).locator("td").nth(6)).toHaveText("5 م.ب");
  await expect(row(0).locator("td").nth(7)).toHaveText("14/08/2026");
  await expect(row(0)).toContainText("قرب الحدّ: الفروع");
  // الشركة بلا بايتات مقيسة: «—» لا صفر مُختلَق، وسكونها يُقال صراحةً
  await expect(row(1).locator("td").nth(6)).toHaveText("—");
  await expect(row(1).locator("td").nth(7)).toHaveText("لا نشاط مسجَّل");
  await expect(row(1)).not.toContainText("قرب الحدّ");

  // سطر تخزين المنصة أسفل الجدول — باسمه هو، و«غير منسوب» تبقى محجوزة لتقرير
  // الاسترجاع الأثري (كمّية أخرى: إجمالي Cloudinary ناقص السجلّ كلّه)
  await expect(page.getByText("تخزين مرفوع لا يخصّ شركة بعينها:")).toBeVisible();
  await expect(page.getByText("1 م.ب", { exact: true })).toBeVisible();
  await expect(page.getByText("غير منسوب")).toHaveCount(0);
});

/** القسم من عنوانه — للصفحة قسمان لكلٍّ جدوله، فلا تُخلط صفوفهما. */
const notesSection = (page: Page, heading: RegExp) =>
  page.locator("section").filter({ has: page.getByRole("heading", { name: heading }) });
const notesTable = (page: Page, heading: RegExp = /قيد العمل/) =>
  notesSection(page, heading).locator('table:has(th:text-is("صور توضيحية"))');
const noteRows = (page: Page, heading: RegExp = /قيد العمل/) =>
  notesTable(page, heading).locator("tbody tr");
/** عمود «الملاحظة» = الثاني: عنوانٌ عريض (بجانبه عدّاد الردود) فوق مقتطف الوصف. */
const noteTitles = (page: Page, heading: RegExp = /قيد العمل/) =>
  noteRows(page, heading).locator("td:nth-child(2) > div > div:first-child > span:first-child");

test("قسما الملاحظات: الأهمّ أولاً، ختم الإنجاز بتاريخه، والوصف والصور من نافذة واحدة", async ({ page }) => {
  const calls = await installMocks(page, true);
  await page.goto("/super-admin/development-notes");
  await expect(page.getByRole("heading", { name: "ملاحظات التطوير" })).toBeVisible();

  // كل الأعمدة ظاهرة داخل عرض الإطار — لا عمود يُقصّ خارج الشاشة
  const headers = notesTable(page).locator("thead th");
  await expect(headers).toHaveText(
    ["#", "الملاحظة", "الحالة", "الأولوية", "الموعد", "صور توضيحية", "أُضيفت", "إجراءات"],
  );
  await expect(headers.last()).toBeInViewport();

  // قسمان بعدّاديهما — المفتوحة ثلاث والمكتملة واحدة
  await expect(page.getByRole("heading", { name: "قيد العمل (3)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "تم تنفيذها (1)" })).toBeVisible();

  // وصلت مبعثرة من الخادم: الأولوية تسبق التاريخ — «تحسين شاشة الجرد» (عالية،
  // أُنشئت 10:00) تتقدّم «توثيق شاشة الإعدادات» (منخفضة، أقدم الجميع 08:00)
  await expect(noteTitles(page).nth(0)).toHaveText("تحسين شاشة الجرد");
  await expect(noteTitles(page).nth(1)).toHaveText("تقرير الأرباح");
  await expect(noteTitles(page).nth(2)).toHaveText("توثيق شاشة الإعدادات");
  await expect(noteRows(page)).toHaveCount(3);

  // المكتملة في قسمها: شطبٌ + شارة «تم تنفيذها ✓» + تاريخ الإنجاز لا تاريخ التعديل
  const doneTitle = noteTitles(page, /تم تنفيذها/).nth(0);
  await expect(doneTitle).toHaveText("ترحيل الشاشة القديمة");
  await expect(doneTitle).toHaveCSS("text-decoration-line", "line-through");
  const doneStatusCell = noteRows(page, /تم تنفيذها/).nth(0).locator("td").nth(2);
  await expect(doneStatusCell).toContainText("تم تنفيذها ✓");
  await expect(doneStatusCell).toContainText("05/08/2026");
  // ويبقى التراجع ممكناً من نفس الخلية.
  await expect(doneStatusCell.locator("select")).toHaveValue("done");

  // شريط الأولوية على حافة الصف: أحمر للعالية، ولونٌ آخر للمنخفضة
  const strip = (row: number, heading?: RegExp) =>
    noteRows(page, heading).nth(row).locator("td:first-child span[aria-hidden]");
  await expect(strip(0)).toHaveCSS("background-color", "rgb(220, 38, 38)");
  expect(await strip(2).evaluate((el) => getComputedStyle(el).backgroundColor))
    .not.toBe("rgb(220, 38, 38)");

  // عدّاد الردود بجانب العنوان — ملاحظةٌ واحدة لها ردّ
  await expect(noteRows(page).nth(0).locator("td:nth-child(2)")).toContainText("1");

  // القسم المكتمل يُطوى ويُفتح
  await page.getByRole("button", { name: /تم تنفيذها/ }).click();
  await expect(notesTable(page, /تم تنفيذها/)).toHaveCount(0);
  await page.getByRole("button", { name: /تم تنفيذها/ }).click();
  await expect(notesTable(page, /تم تنفيذها/)).toBeVisible();

  // الصفحة RTL: النص العربي يبدأ من اليمين — `AseelDenseTable` كان يفرض `left`
  await expect(noteRows(page).nth(0).locator("td").nth(1)).toHaveCSS("text-align", "right");

  // الوصف الطويل مقصوص في الجدول، وكاملاً في نافذة التعديل
  const excerpt = noteRows(page).nth(0).locator("td:nth-child(2) p");
  expect(await excerpt.evaluate(
    (element) => element.scrollHeight > element.clientHeight + 1,
  )).toBe(true);
  await page.getByRole("button", { name: "تعديل تحسين شاشة الجرد" }).click();
  const description = page.getByLabel("الوصف", { exact: true });
  await expect(description).toContainText("وأخيراً تُراجع الحالات الحدّية");

  // الصور تُرفع داخل النافذة وتُحفظ مع الملاحظة عند الضغط على «حفظ التعديلات»
  await page.getByLabel("إدراج صورة توضيحية").setInputFiles({
    name: "shot.png", mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
      "base64",
    ),
  });
  await expect(page.getByRole("button", { name: "معاينة صورة 1" })).toBeVisible();
  await page.getByRole("button", { name: "حفظ التعديلات" }).click();
  await expect.poll(() => calls.notePatch?.images?.length).toBe(1);

  // ملاحظة جديدة: التاريخ مملوء بتاريخ اليوم تلقائياً — لا يكتبه المستخدم
  await page.getByRole("button", { name: "إضافة ملاحظة" }).click();
  const today = new Date();
  await expect(page.getByLabel("موعد الملاحظة")).toHaveValue([
    String(today.getDate()).padStart(2, "0"),
    String(today.getMonth() + 1).padStart(2, "0"),
    String(today.getFullYear()),
  ].join("/"));
  await page.getByRole("button", { name: "إلغاء" }).click();

  // تغيير الحالة من الجدول يُحفظ فوراً وينقل الصف إلى قسم المكتملة بختمه
  await page.getByLabel("حالة الملاحظة تحسين شاشة الجرد").selectOption("done");
  await expect.poll(() => calls.notePatch?.status).toBe("done");
  await expect(noteTitles(page).nth(0)).toHaveText("تقرير الأرباح");
  await expect(noteRows(page)).toHaveCount(2);
  // داخل المكتملة أيضاً الأولوية أولاً — العالية المُنجَزة توّاً تتصدّر المنخفضة.
  await expect(noteTitles(page, /تم تنفيذها/).nth(0)).toHaveText("تحسين شاشة الجرد");
  await expect(noteTitles(page, /تم تنفيذها/).nth(1)).toHaveText("ترحيل الشاشة القديمة");
  // الختم جاء من ردّ الخادم لا من ساعة المتصفح.
  await expect(noteRows(page, /تم تنفيذها/).nth(0).locator("td").nth(2))
    .toContainText("09/08/2026");
});

test("ردود الملاحظة: إرسالٌ فوري، تمييز ردّ غير صاحبها بالأحمر، ثم حذفه", async ({ page }) => {
  const calls = await installMocks(page, true);
  await page.goto("/super-admin/development-notes");
  await expect(page.getByRole("heading", { name: "ملاحظات التطوير" })).toBeVisible();

  await page.getByRole("button", { name: "تعديل تحسين شاشة الجرد" }).click();
  const thread = page.locator("div", { hasText: /^الردود \(/ }).last();
  await expect(page.getByText("بدأت بالفلتر، والباقي غداً.")).toBeVisible();

  // ردّ صاحب الملاحظة نفسه محايد — لا حدّ أحمر. (`color-mix` يُحسب
  // `color(srgb …)` لا `rgb(…)`، فالمطابقة على الصيغتين معاً.)
  const bubble = (body: string) => thread.locator("div.rounded-lg").filter({ hasText: body });
  const DANGER = /220, 38, 38|0\.862745/;
  const borderOf = (body: string) =>
    bubble(body).evaluate((el) => getComputedStyle(el).borderTopColor);
  expect(await borderOf("بدأت بالفلتر")).not.toMatch(DANGER);

  // الإرسال مستقلّ عن حفظ الملاحظة — يصل الخادم فوراً ويظهر في الحال
  await page.getByLabel("نص الردّ").fill("المطلوب أيضاً فلتر المورّد.");
  await page.getByRole("button", { name: "إرسال" }).click();
  await expect.poll(() => calls.commentPost?.body).toBe("المطلوب أيضاً فلتر المورّد.");
  await expect(page.getByText("المطلوب أيضاً فلتر المورّد.")).toBeVisible();
  await expect(page.getByLabel("نص الردّ")).toHaveValue("");
  await expect(bubble("فلتر المورّد")).toContainText("المالك");

  // كاتبه غير صاحب الملاحظة ⇒ فقاعة حمراء
  expect(await borderOf("فلتر المورّد")).toMatch(DANGER);

  // العدّاد على العنوان صار ردّين — النافذة والجدول يتحدّثان معاً
  await page.getByRole("button", { name: "إغلاق النافذة" }).click();
  await expect(noteRows(page).nth(0).locator("td:nth-child(2)")).toContainText("2");

  // الحذف بتأكيد صريح (لا confirm المتصفح)
  await page.getByRole("button", { name: "تعديل تحسين شاشة الجرد" }).click();
  await page.getByRole("button", { name: "حذف ردّ المالك" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "حذف" }).click();
  await expect.poll(() => calls.commentDeleted).toBe(99);
  await expect(page.getByText("المطلوب أيضاً فلتر المورّد.")).toHaveCount(0);
  await expect(page.getByText("بدأت بالفلتر، والباقي غداً.")).toBeVisible();
});

test("super admin controls a company and its members from the platform panel", async ({ page }) => {
  const calls = await installMocks(page, true);
  await page.goto("/super-admin");

  await page.getByRole("button", { name: "تحكم بـشركة الاختبار" }).click();
  await expect(page.getByRole("heading", { name: /تحكم المنصة بالشركة/ })).toBeVisible();

  // إعدادات الشركة: الحالة/الخطة/الاستيراد تُحفظ من هنا لا من نافذة المدير
  await page.getByLabel("حالة الشركة").selectOption("Suspended");
  await page.getByRole("button", { name: "حفظ" }).click();
  await expect.poll(() => calls.companyPatch?.status).toBe("Suspended");
  await expect(page.getByLabel("حالة الشركة")).toHaveValue("Suspended");

  // دور عضو
  await page.getByLabel("دور sami").selectOption("accountant");
  await expect.poll(() => calls.memberPatch?.role).toBe("accountant");

  // إيقاف حساب العضو — بتأكيد صريح
  await page.getByRole("button", { name: "إيقاف حساب sami" }).click();
  await page.getByRole("button", { name: "إيقاف الحساب" }).click();
  await expect.poll(() => calls.setActive?.is_active).toBe(false);
  await expect(page.getByRole("button", { name: "تفعيل حساب sami" })).toBeVisible();
});

test("company panel reads branches, and fetches the activity feed only when it is opened", async ({ page }) => {
  const calls = await installMocks(page, true);
  await page.goto("/super-admin");

  await page.getByRole("button", { name: "تحكم بـشركة الاختبار" }).click();
  await expect(page.getByRole("heading", { name: /تحكم المنصة بالشركة/ })).toBeVisible();

  // التخزين المستهلَك في ترويسة اللوحة — الرقم نفسه يظهر خلفها في جدول الشركات،
  // فالتأكيد على فقرة الترويسة لا على النص وحده.
  await expect(page.getByText(/التخزين المستهلَك/)).toContainText("5 م.ب");

  const branches = page.locator('section[aria-label="فروع الشركة"]');
  await expect(branches.getByRole("heading", { name: "الفروع (2)" })).toBeVisible();
  await expect(branches.getByText("الفرع الرئيسي")).toBeVisible();
  await expect(branches.getByText("MAIN")).toBeVisible();

  // القسم موجود ولم تُطلب مئة الحركة مع فتح اللوحة
  const feed = page.locator('section[aria-label="آخر حركات الشركة"]');
  await expect(feed.getByRole("heading", { name: "آخر الحركات" })).toBeVisible();
  expect(calls.activityHits ?? 0).toBe(0);

  await feed.getByRole("button", { name: /عرض آخر 100 حركة/ }).click();
  await expect(feed.getByText("INV-1001")).toBeVisible();
  await expect(feed.getByText("الحدّ: 3 ← 5")).toBeVisible();
  await expect(feed.getByText("فاتورة مبيعات INV-1001")).toBeVisible();
  // نوع المستند يُعرَّب — لا يُطبع مفتاحه الإنجليزي في شاشة عربية
  await expect(feed.getByText("حدّ خطة الفروع")).toBeVisible();
  await expect.poll(() => calls.activityHits).toBe(1);

  // الطيّ ثم البسط يعرضان المجلوب نفسه بلا نداء ثانٍ
  await feed.getByRole("button", { name: /إخفاء/ }).click();
  await expect(feed.getByText("INV-1001")).toHaveCount(0);
  await feed.getByRole("button", { name: /عرض آخر 100 حركة/ }).click();
  await expect(feed.getByText("INV-1001")).toBeVisible();
  expect(calls.activityHits).toBe(1);
});

test("super admin assigns the example company and sees its label", async ({ page }) => {
  const calls = await installMocks(page, true);
  await page.goto("/super-admin");

  await page.getByLabel("تعيين الشركة المثال").selectOption("42");

  await expect.poll(() => calls.companyPatch?.is_example).toBe(true);
  await expect(page.getByLabel("تعيين الشركة المثال")).toHaveValue("42");
  await expect(page.getByText("شركة الاختبار (مثال)", { exact: true })).toBeVisible();
});

test("company manager cannot see or open platform administration", async ({ page }) => {
  await installMocks(page, false);
  await page.goto("/super-admin");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText("إدارة المنصة")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "لوحة تحكم السوبر أدمن" })).toHaveCount(0);
  await expect(page.getByTestId("business-dashboard")).toBeVisible();
});
