import { expect, test, type BrowserContext, type Route } from "@playwright/test";

/**
 * #73/#69 — «لما تفتح عميل وتكبس «خلف» ترجع لمكانك مو لبداية القائمة».
 *
 * عملاءُ المبيعات يفتحون كرتَ العميل بتبويبٍ جديد، فلا سابقةَ فيه يرجع إليها
 * المتصفح؛ وكان «رجوع» يقود إلى «دليل الأطراف». الآن التبويبُ يحمل مسارَ الفاتح
 * (`TabHandoff.openerPath`) والقائمةُ تحفظ بحثَها وصفحتَها وصفَّها في الرابط —
 * فـ«رجوع» يعيد القائمةَ نفسَها بفلترها، والصفُّ المفتوح مختارٌ.
 */

test.use({ serviceWorkers: "block" });

const customers = Array.from({ length: 60 }, (_, i) => ({
  id: i + 1,
  name: i + 1 === 57 ? "أحمد السابع والخمسون" : `عميل ${i + 1}`,
  partner_type: "Customer",
  is_active: true,
}));

async function install(context: BrowserContext, listRequests: string[]) {
  await context.addInitScript(() => {
    localStorage.setItem("token", "customers-back-token");
    localStorage.setItem("userId", "customers-back-user");
    localStorage.setItem("tenantId", "1");
  });
  await context.route("**/*", async (route: Route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const p = url.pathname;
    const json = (body: unknown) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });

    if (p.endsWith("/hr/users/customers-back-user/")) {
      return json({
        id: "customers-back-user", name: "مدير المبيعات", role: "manager", email: "sales@example.test",
        employmentStatus: "active", isApproved: true, isEmailVerified: true,
      });
    }
    if (p.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1, role: "manager", is_default: true, created_at: "2026-08-01T00:00:00Z",
        tenant: { TenantID: 1, CompanyName: "KTRA", SubscriptionPlan: "Enterprise", Status: "Active", CreatedAt: "2026-08-01T00:00:00Z" },
      }]);
    }
    if (p.endsWith("/permissions/me/")) {
      return json({ role: "manager", is_manager: true, permissions: ["sales.customer.view", "purchase.supplier.view"] });
    }
    if (/\/partners\/?$/.test(p) && url.searchParams.get("partner_type") === "Customer") {
      listRequests.push(url.search);
      const q = url.searchParams.get("search") ?? "";
      const pageNo = Number(url.searchParams.get("page") || 1);
      const size = Number(url.searchParams.get("page_size") || 50);
      const matched = customers.filter((c) => !q || c.name.includes(q) || String(c.id).includes(q));
      return json({ count: matched.length, next: null, previous: null, results: matched.slice((pageNo - 1) * size, pageNo * size) });
    }
    const one = p.match(/\/partners\/(\d+)\/$/);
    if (one) return json(customers.find((c) => c.id === Number(one[1])) ?? {});
    if (/\/partners\/\d+\/profile\/$/.test(p)) {
      return json({ balance: "0", balance_side: "Cr", outstanding_balance: "0", total_sales: "0", total_purchases: "0", last_transaction_date: null });
    }
    if (/\/partners\/\d+\/statement\/$/.test(p)) return json({ results: [], count: 0 });
    return json([]);
  });
}

test("«رجوع» من كرت عميلٍ فُتح بتبويب جديد يعيد القائمةَ بصفحتها وصفّها لا رأسَها", async ({ context }) => {
  const listRequests: string[] = [];
  await install(context, listRequests);
  const list = await context.newPage();
  await list.goto("/sales/customers");
  await expect(list.getByRole("button", { name: "عميل 1", exact: true })).toBeVisible({ timeout: 30_000 });

  // الصفحةُ الثانية في الرابط، ثم فتحُ عميلٍ منها.
  await list.getByRole("button", { name: "التالي", exact: true }).click();
  await expect(list).toHaveURL(/[?&]page=2/);
  const [child] = await Promise.all([
    context.waitForEvent("page"),
    list.getByRole("button", { name: "أحمد السابع والخمسون" }).click(),
  ]);
  await expect(list).toHaveURL(/[?&]sel=57/);

  await child.waitForLoadState("domcontentloaded");
  await expect(child).toHaveURL(/\/partners\/57$/);
  const back = child.getByRole("button", { name: /^رجوع — إلى «/ }).first();
  await expect(back).toBeVisible({ timeout: 30_000 });
  await back.click();

  await expect(child).toHaveURL(/\/sales\/customers\?.*page=2/);
  await expect(child).toHaveURL(/[?&]sel=57/);
  const row = child.locator('tr[data-row-key="57"]');
  await expect(row).toHaveClass(/ktra-row--selected/, { timeout: 30_000 });
  await expect(row).toBeInViewport();
  await expect(child.getByRole("button", { name: "عميل 1", exact: true })).toHaveCount(0);
});

test("البحث في الرابط: يبقى بعد التحديث، ويعود مع «رجوع» من كرت العميل", async ({ context }) => {
  const listRequests: string[] = [];
  await install(context, listRequests);
  const list = await context.newPage();
  await list.goto("/sales/customers");
  const search = list.locator('[data-ktra-field="search"]');
  await expect(search).toBeVisible({ timeout: 30_000 });

  await search.fill("أحمد");
  await expect(list).toHaveURL(/[?&]q=/);
  await expect(list.getByRole("button", { name: "أحمد السابع والخمسون" })).toBeVisible();
  await expect(list.getByRole("button", { name: "عميل 1", exact: true })).toHaveCount(0);

  await list.reload();
  await expect(list.locator('[data-ktra-field="search"]')).toHaveValue("أحمد", { timeout: 30_000 });
  await expect(list.getByRole("button", { name: "عميل 1", exact: true })).toHaveCount(0);

  const [child] = await Promise.all([
    context.waitForEvent("page"),
    list.getByRole("button", { name: "أحمد السابع والخمسون" }).click(),
  ]);
  const back = child.getByRole("button", { name: /^رجوع — إلى «/ }).first();
  await expect(back).toBeVisible({ timeout: 30_000 });
  await back.click();
  await expect(child.locator('[data-ktra-field="search"]')).toHaveValue("أحمد", { timeout: 30_000 });
  await expect(child.getByRole("button", { name: "عميل 1", exact: true })).toHaveCount(0);
});
