import { expect, test, type Page } from "@playwright/test";

/**
 * #73/#69 — «لما يفتح ملف عميل ويحط خلف برجعو لراس القائمة هاد غلط».
 *
 * كان ملفُّ العميل يستبدل القائمةَ كلَّها (`if (selected) return …`): يضيع البحثُ
 * وموضعُ التمرير، ويعاد تحميلُ لوح المدير، وزرُّ «رجوع» المتصفح يُخرج من مركز
 * العمليات. الآن الملفُّ في الرابط (`?tab=crm&lead=`) والقائمةُ مركَّبةٌ تحته.
 */

test.use({ serviceWorkers: "block" });

const LEADS = Array.from({ length: 60 }, (_, index) => ({
  id: index + 1,
  store_name: `محل رقم ${index + 1}`,
  owner_name: "",
  city: "نابلس",
  address: "",
  activity: "",
  status: "new",
  assigned_to: null,
  assigned_at: null,
  next_follow_up_at: null,
  source: "admin_upload",
  approval_status: "approved",
  suggested_by: null,
  rejection_reason: "",
  converted_tenant: null,
  phones: [{ id: index + 1, e164: `+97259900${String(index).padStart(4, "0")}`, raw: "", kind: "primary" }],
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
}));

const SAMI = { id: 7, name: "سامي" };
const TEAM = {
  employees: [{
    employee_id: 7, employee_name: "سامي", employee_status: "active", total: 2, overdue: 1, by_status: { new: 2 },
    attempts: 4, reached: 3, converted: 1, last_activity_at: "2026-09-29T10:00:00Z",
  }],
  pool_size: 58,
  period: { date_from: "2026-09-01", date_to: "2026-09-30" },
};

async function installMocks(page: Page, seenQueries: string[], posted: unknown[] = []) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "e2e-crm-token");
    localStorage.setItem("userId", "e2e-crm-admin");
    localStorage.setItem("tenantId", "1");
  });
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const p = url.pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (p.endsWith("/hr/users/e2e-crm-admin/")) {
      return json({
        id: "e2e-crm-admin", name: "مدير العمليات", role: "manager", email: "ops@example.test",
        employmentStatus: "active", isApproved: true, isEmailVerified: true, isSuperAdmin: true,
      });
    }
    if (p.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1, role: "manager", is_default: true, can_access_import: false, created_at: "2026-01-01T00:00:00Z",
        tenant: { TenantID: 1, CompanyName: "شركة الإدارة", SubscriptionPlan: "Enterprise", Status: "Active", CreatedAt: "2026-01-01T00:00:00Z", import_enabled: false },
      }]);
    }
    if (p.endsWith("/permissions/me/")) return json({ role: "manager", is_manager: true, permissions: [] });
    if (p.endsWith("/platform/ops/notifications/unread-count/")) return json({ unread_count: 0 });

    if (p.endsWith("/platform/crm/leads/")) {
      seenQueries.push(url.search);
      const q = url.searchParams.get("q") || "";
      const assigned = url.searchParams.get("assigned_to");
      let rows = q ? LEADS.filter((lead) => lead.store_name.includes(q)) : LEADS;
      if (assigned === "7") rows = rows.slice(0, 2).map((lead) => ({ ...lead, assigned_to: SAMI }));
      if (assigned === "none") {
        // المخزن مُصفَّحٌ كالخادم (50 في الصفحة) — ما تُرسله بقية الاختبارات يبقى صفحةً واحدة.
        const pageNo = Number(url.searchParams.get("page") || 1);
        const slice = rows.slice((pageNo - 1) * 50, pageNo * 50);
        return json({ count: rows.length, next: pageNo * 50 < rows.length ? `?page=${pageNo + 1}` : null, previous: null, results: slice });
      }
      return json({ count: rows.length, next: null, previous: null, results: rows });
    }
    const leadMatch = p.match(/\/platform\/crm\/leads\/(\d+)\/$/);
    if (leadMatch) return json(LEADS[Number(leadMatch[1]) - 1]);
    if (/\/platform\/crm\/leads\/\d+\/activities\/$/.test(p)) {
      if (request.method() === "POST") { posted.push(request.postDataJSON()); return json({ id: 1 }, 201); }
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    if (/\/platform\/crm\/leads\/\d+\/stats\/$/.test(p)) return json(null, 404);
    if (p.endsWith("/platform/crm/stats/overview/")) { seenQueries.push(`overview${url.search}`); return json(TEAM); }
    if (p.endsWith("/platform/crm/transfer-requests/")) return json({ count: 0, next: null, previous: null, results: [] });
    if (p.endsWith("/platform/crm/colleagues/")) return json([{ ...SAMI, job_title: "تسويق", is_me: false }]);
    return json([]);
  });
}

const scrollTop = (page: Page) =>
  page.evaluate(() => document.querySelector<HTMLElement>("main.app-content")?.scrollTop ?? window.scrollY);

test("فتح عميل ثم «العودة» يعيد البحث نفسه وموضع التمرير نفسه", async ({ page }) => {
  const seen: string[] = [];
  await installMocks(page, seen);
  await page.goto("/super-admin/platform-ops?tab=crm");

  await expect(page.getByRole("button", { name: /محل رقم 60/ })).toBeVisible({ timeout: 30_000 });
  await page.locator("#crm-lead-search").fill("محل رقم 5");
  await page.getByRole("button", { name: "بحث", exact: true }).click();
  await expect(page.getByRole("button", { name: /محل رقم 1\b/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /محل رقم 59/ })).toBeVisible();

  // ابحث من جديد بلا ترشيح كي تطول القائمة، ثم انزل إلى أسفلها.
  await page.locator("#crm-lead-search").fill("");
  await page.getByRole("button", { name: "بحث", exact: true }).click();
  const target = page.getByRole("button", { name: /محل رقم 48/ });
  await target.scrollIntoViewIfNeeded();
  const before = await scrollTop(page);
  expect(before).toBeGreaterThan(200);

  await target.click();
  await expect(page).toHaveURL(/tab=crm/);
  await expect(page).toHaveURL(/lead=48/);
  await expect(page.getByRole("button", { name: /العودة إلى العملاء/ })).toBeVisible();

  await page.getByRole("button", { name: /العودة إلى العملاء/ }).click();
  await expect(page).not.toHaveURL(/lead=/);
  await expect(page).toHaveURL(/tab=crm/);
  await expect(target).toBeVisible();
  await expect.poll(() => scrollTop(page)).toBeGreaterThan(before - 5);
  expect(await scrollTop(page)).toBeLessThan(before + 5);
});

test("الترشيح يبقى بعد فتح الملف وزرّ «رجوع» المتصفح، ويُرسَل مع كل إعادة تحميل", async ({ page }) => {
  const seen: string[] = [];
  await installMocks(page, seen);
  await page.goto("/super-admin/platform-ops?tab=crm");
  await expect(page.getByRole("button", { name: /محل رقم 60/ })).toBeVisible({ timeout: 30_000 });

  await page.locator("#crm-lead-search").fill("محل رقم 5");
  await page.getByRole("button", { name: "بحث", exact: true }).click();
  await page.getByRole("button", { name: /محل رقم 52/ }).click();
  await expect(page).toHaveURL(/lead=52/);

  await page.goBack();
  await expect(page).not.toHaveURL(/lead=/);
  await expect(page.locator("#crm-lead-search")).toHaveValue("محل رقم 5");
  await expect(page.getByRole("button", { name: /محل رقم 1\b/ })).toHaveCount(0);

  // تبديلُ النطاق لا يُسقط البحث — كان يُعيد التحميل بلا `q`.
  seen.length = 0;
  await page.getByRole("tab", { name: "المخزن المتاح" }).click();
  await expect.poll(() => seen.some((query) => query.includes("scope=pool"))).toBe(true);
  expect(seen.filter((query) => query.includes("scope=pool")).every((query) => query.includes("q="))).toBe(true);
});

test("#69 — لوح الفريق: كبسةُ موظّفٍ تفتح أرقامَه في القائمة، والمدّةُ تُرسَل للخادم", async ({ page }) => {
  const seen: string[] = [];
  await installMocks(page, seen);
  await page.goto("/super-admin/platform-ops?tab=crm");

  const row = page.getByTestId("crm-team-row-7");
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText("1 متأخرة");
  await expect(row).toContainText("(75%)");
  expect(seen).toContain("overview?period=month");

  await page.getByRole("button", { name: "هذا الأسبوع" }).click();
  await expect.poll(() => seen.includes("overview?period=week")).toBe(true);

  seen.length = 0;
  await row.getByRole("button", { name: /سامي/ }).click();
  await expect.poll(() => seen.some((query) => query.includes("scope=all") && query.includes("assigned_to=7"))).toBe(true);
  await expect(page.getByTestId("crm-employee-filter-chip")).toContainText("سامي");
  await expect(page.getByRole("combobox", { name: "ترشيح بالموظف" })).toHaveValue("7");
  await expect(page.getByRole("button", { name: /محل رقم 1\b/ })).toContainText("عند سامي");
  await expect(page.getByRole("button", { name: /محل رقم 3\b/ })).toHaveCount(0);

  // البحثُ لا يُسقط الموظّف، و✕ يُسقطه وحده.
  seen.length = 0;
  await page.locator("#crm-lead-search").fill("محل");
  await page.getByRole("button", { name: "بحث", exact: true }).click();
  await expect.poll(() => seen.some((query) => query.includes("q=") && query.includes("assigned_to=7"))).toBe(true);
  seen.length = 0;
  await page.getByRole("button", { name: "إلغاء ترشيح الموظف" }).click();
  await expect(page.getByTestId("crm-employee-filter-chip")).toHaveCount(0);
  await expect.poll(() => seen.some((query) => query.includes("scope=all") && !query.includes("assigned_to"))).toBe(true);

  // المخزن من اللوح = `assigned_to=none`.
  seen.length = 0;
  await page.getByRole("button", { name: /في المخزن بلا موظف/ }).click();
  await expect.poll(() => seen.some((query) => query.includes("assigned_to=none"))).toBe(true);
});

test("#69 — تسجيلُ اتصالٍ لا يُحفظ بلا نتيجة، ويُرسل النتيجة المختارة", async ({ page }) => {
  const seen: string[] = [];
  const posted: unknown[] = [];
  await installMocks(page, seen, posted);
  await page.goto("/super-admin/platform-ops?tab=crm&lead=5");

  await page.getByRole("button", { name: "تسجيل اتصال" }).click({ timeout: 30_000 });
  const outcome = page.getByLabel("النتيجة");
  await expect(outcome).toHaveValue("");
  await page.getByRole("button", { name: "حفظ السجل" }).click();
  expect(posted).toHaveLength(0);

  await outcome.selectOption("no_answer");
  await page.getByRole("button", { name: "حفظ السجل" }).click();
  await expect.poll(() => posted.length).toBe(1);
  expect(posted[0]).toMatchObject({ kind: "call", outcome: "no_answer" });
});

test("الترشيح في الرابط: تحديثُ الصفحة على ملفّ عميل ثم «العودة» يعيد القائمة مرشَّحة", async ({ page }) => {
  const seen: string[] = [];
  await installMocks(page, seen);
  await page.goto("/super-admin/platform-ops?tab=crm");
  await expect(page.getByRole("button", { name: /محل رقم 60/ })).toBeVisible({ timeout: 30_000 });

  await page.locator("#crm-lead-search").fill("محل رقم 5");
  await page.getByRole("button", { name: "بحث", exact: true }).click();
  await expect(page).toHaveURL(/[?&]q=/);
  await page.getByRole("button", { name: /محل رقم 52/ }).click();
  await expect(page).toHaveURL(/lead=52/);

  await page.reload();
  const back = page.getByRole("button", { name: /العودة إلى العملاء/ });
  await expect(back).toBeVisible({ timeout: 30_000 });
  await back.click();
  await expect(page).not.toHaveURL(/lead=/);
  await expect(page.locator("#crm-lead-search")).toHaveValue("محل رقم 5");
  await expect(page.getByRole("button", { name: /محل رقم 59/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /محل رقم 1/ })).toHaveCount(0);
  expect(seen.filter((q) => !q.startsWith("overview")).at(-1)).toContain("q=");
});

test("أرقامُ المخزن أكثر من صفحة: «عرض المزيد» يقول كم بقي ويُلحق الباقي", async ({ page }) => {
  const seen: string[] = [];
  await installMocks(page, seen);
  await page.goto("/super-admin/platform-ops?tab=crm");
  await page.getByRole("button", { name: /في المخزن بلا موظف/ }).click({ timeout: 30_000 });
  await expect(page).toHaveURL(/employee=none/);

  const more = page.getByTestId("crm-load-more");
  await expect(more).toContainText(/50.*من.*60/);
  await expect(page.getByRole("button", { name: /محل رقم 60/ })).toHaveCount(0);
  await more.click();
  await expect(page.getByRole("button", { name: /محل رقم 60/ })).toBeVisible();
  await expect(more).toHaveCount(0);
  expect(seen.some((q) => q.includes("assigned_to=none") && q.includes("page=2"))).toBe(true);
});
