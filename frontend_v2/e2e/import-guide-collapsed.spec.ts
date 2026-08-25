import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * THA-115 — المرشد مرافق لا مقيم.
 *
 * `tsc` هنا لا يفحص خصائص JSX (لا `@types/react`)، فشاشة كاملة قد تموت والبناء
 * أخضر. هذه الجولة تفتح الشاشة فعلاً في متصفح وتسأل الأسئلة الثلاثة التي طلبها
 * المالك: هل اختفى اللوح؟ هل بقي طريقٌ إليه؟ وهل يقطع الاسمُ الطويل جاره؟
 */

const LONG_TITLE = "صفقة استيراد أدوات كهربائية ومواسير نحاسية وقطع غيار مكيّفات من مصنع تشنغدو الصيني للموسم القادم";

const MEMBERSHIP = {
  id: 42,
  tenant: {
    TenantID: 42,
    CompanyName: "شركة الاختبار",
    SubscriptionPlan: "Enterprise",
    Status: "Active",
    CreatedAt: "2026-07-22T00:00:00Z",
    import_enabled: true,
  },
  role: "manager",
  is_default: true,
  created_at: "2026-07-22T00:00:00Z",
  can_access_import: true,
};

async function installMocks(page: Page, extra?: (route: Route, url: URL) => Promise<boolean>) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "guide-e2e-token");
    localStorage.setItem("userId", "guide-e2e-user");
    localStorage.setItem("tenantId", "42");
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) {
      await route.continue();
      return;
    }
    if (extra && (await extra(route, url))) return;
    if (url.pathname.endsWith("/hr/users/guide-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "guide-e2e-user",
          name: "Guide Tester",
          role: "manager",
          email: "guide@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([MEMBERSHIP]) });
      return;
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager",
          is_manager: true,
          permissions: ["import.deal.manage"],
          modules: {},
          ui_mode: "advanced",
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/logistics/import-journey/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          offers: { awaiting_decision: 0, accepted_not_converted: 0 },
          deals: {
            without_shipment: 1,
            rows: [{
              id: 501,
              ref: "D-0501",
              title: LONG_TITLE,
              partner_name: "مصنع تشنغدو",
              currency_code: "USD",
              total: "10000",
              paid: "0",
              remaining: "10000",
              payments_count: 0,
              pending_payments_count: 0,
              shipment_id: null,
            }],
          },
          shipments: [],
        }),
      });
      return;
    }
    if (url.pathname.includes("/mapper/activityStatus/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ isCurrentlyActive: true }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

const guidePanel = (page: Page) => page.locator('aside[aria-label="مرشد رحلة الاستيراد"]');
const guideButton = (page: Page) => page.getByRole("button", { name: /مرشد الرحلة/ });

test("الصفقات تُفتح بلا لوح فوقها — زرّ في رأس الشاشة لا لوحٌ مقيم", async ({ page }) => {
  await installMocks(page);
  await page.goto("/deals");

  await expect(guideButton(page)).toBeVisible({ timeout: 15_000 });
  await expect(guidePanel(page)).toHaveCount(0);
  // الزرّ ساكنٌ في شريط الرأس، لا عائمٌ فوق المحتوى.
  await expect(page.locator("#import-guide-slot button")).toHaveCount(1);
});

test("الزرّ يفتح اللوح، والاختيار يُحفظ لهذا المستخدم وحده", async ({ page }) => {
  await installMocks(page);
  await page.goto("/deals");

  await guideButton(page).click();
  await expect(guidePanel(page)).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("ktra.importGuide.open:guide-e2e-user"))).toBe("1");

  await page.getByRole("button", { name: "طيّ المرشد" }).click();
  await expect(guidePanel(page)).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("ktra.importGuide.open:guide-e2e-user"))).toBe("0");
  // المفتاح العام لا يُكتب: طيّ هذا المستخدم لا يسري على زميله على الجهاز نفسه.
  expect(await page.evaluate(() => localStorage.getItem("ktra.importGuide.open"))).toBeNull();
});

test("اسم الصفقة الطويل يُقصّ ولا يزيح «الخطوة س من ص»", async ({ page }) => {
  await installMocks(page);
  await page.goto("/deals");
  await guideButton(page).click();

  const label = guidePanel(page).locator(`[title="صفقة D-0501 — ${LONG_TITLE}"]`);
  await expect(label).toBeVisible();

  const clipped = await label.evaluate((el) => ({
    overflowing: el.scrollWidth > el.clientWidth,
    lines: Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)),
  }));
  expect(clipped.overflowing, "النصّ أطول من الحيّز فعلاً — القصّ مُختبَر لا مفترَض").toBe(true);
  expect(clipped.lines).toBe(1);

  // الجار على السطر نفسه، لا مدفوعاً إلى سطر ثانٍ.
  const step = guidePanel(page).getByText(/الخطوة \d+ من \d+/);
  const [labelBox, stepBox] = [await label.boundingBox(), await step.boundingBox()];
  expect(Math.abs((labelBox!.y) - (stepBox!.y))).toBeLessThan(labelBox!.height);
});

test("وصف الصفقة الطويل في القائمة سطر واحد لا يبتلع أعمدة جاره", async ({ page }) => {
  await installMocks(page, async (route, url) => {
    if (url.pathname.includes("/logistics/deals/") && route.request().method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          count: 1,
          next: null,
          results: [{
            id: 501,
            ref_number: "D-0501",
            description: LONG_TITLE,
            status: "initial",
            total_amount: "10000.00",
            remaining_amount: "10000.00",
            deal_date: "2026-08-01",
          }],
        }),
      });
      return true;
    }
    return false;
  });
  await page.goto("/deals");

  const cell = page.locator(`td .ktra-cell-clip[title="${LONG_TITLE}"]`);
  await expect(cell).toBeVisible({ timeout: 15_000 });
  const clipped = await cell.evaluate((el) => ({
    overflowing: el.scrollWidth > el.clientWidth,
    lines: Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)),
  }));
  expect(clipped.overflowing).toBe(true);
  expect(clipped.lines).toBe(1);

  // العمود المجاور ما زال ظاهراً بعرضه، لا مسحوقاً خلف الوصف.
  await expect(page.getByRole("columnheader", { name: "المرحلة" })).toBeVisible();
});

// معيار المالك يذكر الجوال صراحةً: الشاشة الضيّقة هي التي يكسرها النصّ الطويل
// أولاً، والاختبارات أعلاه تجري على عرض 1280 الافتراضي لـ Desktop Chrome.
test.describe("على الجوال", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("اللوح لا يفتح نفسه على شاشة ضيّقة، والاسم الطويل يبقى سطراً واحداً", async ({ page }) => {
    await installMocks(page);
    await page.goto("/deals");

    await expect(guideButton(page)).toBeVisible({ timeout: 15_000 });
    await expect(guidePanel(page)).toHaveCount(0);

    await guideButton(page).click();
    const label = guidePanel(page).locator(`[title="صفقة D-0501 — ${LONG_TITLE}"]`);
    await expect(label).toBeVisible();
    expect(await label.evaluate((el) =>
      Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)),
    )).toBe(1);
    // اللوح نفسه لا يتجاوز عرض الشاشة الضيّقة.
    const box = (await guidePanel(page).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
  });
});
