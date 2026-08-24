import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

test.use({
  serviceWorkers: "block",
  viewport: { width: 1440, height: 900 },
});

type AppView =
  | "dashboard"
  | "tasks"
  | "task-management"
  | "users"
  | "reports"
  | "sourcing"
  | "settings"
  | "employee-notes"
  | "points-history"
  | "points-management"
  | "attendance"
  | "purchase-invoices"
  | "international-invoices"
  | "sales-invoices"
  | "sales-customers"
  | "old-invoices"
  | "items-management"
  | "items-categories"
  | "supplier-management"
  | "price-offers"
  | "deals-management"
  | "shipments-management"
  | "customs-clearance"
  | "cash-boxes"
  | "cash-box-details"
  | "gallery"
  | "store"
  | "accounting-coa"
  | "accounting-journals"
  | "accounting-journal-entry"
  | "accounting-cheques"
  | "accounting-general-ledger"
  | "accounting-trial-balance"
  | "accounting-vat-report"
  | "accounting-landed-cost"
  | "sales-customer-payments"
  | "sales-settings"
  | "purchase-settings"
  | "product-profile"
  | "product-group"
  | "local-shipping"
  | "sql-products"
  | "sql-partners"
  | "sql-deals"
  | "sql-shipments"
  | "group-constants"
  | "smart-assistant"
  | "accounting-fiscal-periods"
  | "accounting-exchange-rates"
  | "stock-levels"
  | "stock-movements"
  | "warehouses"
  | "warehouse-transfer"
  | "stocktake"
  | "product-cost"
  | "property-rental"
  | "aseel-kit"
  | "aseel-sales"
  | "sales-quotations"
  | "credit-debit-notes"
  | "sql-clearances"
  | "sql-purchase-invoices"
  | "shipments"
  | "shipment-management"
  | "clearance"
  | "accounting-balance-sheet"
  | "accounting-income-statement"
  | "accounting-vat-statements"
  | "accounting-year-end-close"
  | "sales-return"
  | "purchase-return"
  | "supplier-payments"
  | "invoice-profits"
  | "partner-profile"
  | "import-flow"
  | "activity-log"
  | "about-us"
  | "contact";

type ViewTarget = {
  view: AppView;
  path?: string;
  skipReason?: string;
};

/**
 * Fixed census inventory copied from the AppView union in types/common.ts.
 * Paths mirror App.tsx VIEW_PATHS; query routes use App.tsx's supported ?view= fallback.
 */
const VIEW_TARGETS: readonly ViewTarget[] = [
  { view: "dashboard", path: "/dashboard" },
  { view: "tasks", path: "/tasks" },
  { view: "task-management", path: "/task-management" },
  { view: "users", path: "/users" },
  { view: "reports", path: "/reports" },
  { view: "sourcing", path: "/sourcing" },
  { view: "settings", path: "/settings" },
  { view: "employee-notes", path: "/employee-notes" },
  { view: "points-history", path: "/points-history" },
  { view: "points-management", path: "/points-management" },
  { view: "attendance", path: "/attendance" },
  { view: "purchase-invoices", path: "/purchase-invoices" },
  { view: "international-invoices", path: "/international-invoices" },
  { view: "sales-invoices", path: "/sales/invoices" },
  { view: "sales-customers", path: "/sales/customers" },
  { view: "old-invoices", path: "/old-invoices" },
  { view: "items-management", path: "/items" },
  { view: "items-categories", path: "/items/categories" },
  { view: "supplier-management", path: "/suppliers" },
  { view: "price-offers", path: "/price-offers" },
  { view: "deals-management", path: "/deals" },
  { view: "shipments-management", path: "/shipments" },
  { view: "customs-clearance", path: "/clearance" },
  { view: "cash-boxes", path: "/cash-boxes" },
  { view: "cash-box-details", skipReason: "requires a selected cash-box record" },
  { view: "gallery", path: "/gallery" },
  { view: "store", path: "/store" },
  { view: "accounting-coa", path: "/accounting/coa" },
  { view: "accounting-journals", path: "/accounting/journals" },
  { view: "accounting-journal-entry", path: "/accounting/journals/new" },
  { view: "accounting-cheques", path: "/accounting/cheques" },
  { view: "accounting-general-ledger", path: "/accounting/general-ledger" },
  { view: "accounting-trial-balance", path: "/accounting/trial-balance" },
  { view: "accounting-vat-report", path: "/accounting/vat-report" },
  { view: "accounting-landed-cost", path: "/accounting/landed-cost" },
  { view: "sales-customer-payments", path: "/sales/customer-payments" },
  { view: "sales-settings", path: "/sales/settings" },
  { view: "purchase-settings", path: "/purchase-settings" },
  { view: "product-profile", skipReason: "requires a product record identifier" },
  { view: "product-group", path: "/product-group" },
  { view: "local-shipping", path: "/local-shipping" },
  { view: "sql-products", path: "/?view=sql-products" },
  { view: "sql-partners", path: "/?view=sql-partners" },
  { view: "sql-deals", path: "/?view=sql-deals" },
  { view: "sql-shipments", path: "/?view=sql-shipments" },
  {
    view: "group-constants",
    skipReason: "opens as an F11 modal and has no standalone render case",
  },
  { view: "smart-assistant", path: "/assistant" },
  { view: "accounting-fiscal-periods", path: "/accounting/fiscal-periods" },
  { view: "accounting-exchange-rates", path: "/accounting/exchange-rates" },
  { view: "stock-levels", path: "/stock-levels" },
  { view: "stock-movements", path: "/stock-movements" },
  { view: "warehouses", path: "/warehouses" },
  { view: "warehouse-transfer", path: "/warehouse-transfer" },
  { view: "stocktake", path: "/stocktake" },
  { view: "product-cost", path: "/product-cost" },
  { view: "property-rental", path: "/property-rental" },
  { view: "aseel-kit", path: "/aseel-kit" },
  { view: "aseel-sales", path: "/aseel-sales" },
  { view: "sales-quotations", path: "/sales/quotations" },
  { view: "credit-debit-notes", path: "/sales/credit-debit-notes" },
  {
    view: "sql-clearances",
    skipReason: "declared in AppView but has no route or render case",
  },
  {
    view: "sql-purchase-invoices",
    skipReason: "declared in AppView but has no route or render case",
  },
  { view: "shipments", skipReason: "legacy alias has no render case" },
  { view: "shipment-management", skipReason: "legacy alias has no render case" },
  { view: "clearance", skipReason: "legacy alias has no render case" },
  { view: "accounting-balance-sheet", path: "/accounting/balance-sheet" },
  { view: "accounting-income-statement", path: "/accounting/income-statement" },
  { view: "accounting-vat-statements", path: "/accounting/vat-statements" },
  { view: "accounting-year-end-close", path: "/accounting/year-end-close" },
  { view: "sales-return", path: "/sales/returns" },
  { view: "purchase-return", path: "/purchase-returns" },
  { view: "supplier-payments", path: "/supplier-payments" },
  { view: "invoice-profits", path: "/sales/profits" },
  { view: "partner-profile", skipReason: "requires a partner record identifier" },
  { view: "import-flow", path: "/import-flow" },
  { view: "activity-log", path: "/?view=activity-log" },
  { view: "about-us", path: "/about-us" },
  { view: "contact", path: "/contact" },
] as const;

type CensusCategory = {
  count: number;
  values: string[];
};

type ViewCensus = {
  path: string;
  buttons: CensusCategory;
  fields: CensusCategory;
  tabs: CensusCategory;
  tableHeaders: CensusCategory;
  toolbarItems: CensusCategory;
};

type ParityBaseline = {
  schemaVersion: 1;
  viewport: { width: 1440; height: 900 };
  views: Record<string, ViewCensus>;
  skipped: Record<string, string>;
};

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const BASELINE_PATH = join(E2E_DIR, "parity-baseline.json");
const SHOTS_DIR = join(E2E_DIR, "parity-shots", "baseline");
const COMPARE_MODE = process.env.PARITY_MODE === "compare";
const CAPTURE_SHOTS = process.env.PARITY_SHOTS === "1";

const normalise = (value: string | null | undefined): string =>
  (value ?? "").replace(/\s+/g, " ").trim();

async function installAuthenticatedApiMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("token", "parity-e2e-token");
    localStorage.setItem("userId", "parity-e2e-user");
    localStorage.setItem("tenantId", "1");
  });

  await page.route("**/*", async (route: Route) => {
    const url = new URL(route.request().url());
    const isApi =
      url.port === "8000" ||
      url.pathname.startsWith("/api/");

    if (!isApi) {
      await route.continue();
      return;
    }

    if (url.pathname.endsWith("/hr/users/parity-e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "parity-e2e-user",
          name: "Parity Census Tester",
          role: "manager",
          email: "parity@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }

    /* بلا عضوية شركة يقف التطبيق على شاشة «لنُنشئ شركتك الأولى» فلا يُرسم
       AppLayout أبداً: ينتظر كل هدفٍ 15ث على `main.app-content` ثم يُسجَّل
       skipped، وتنتهي مهلة الاختبار (78 × 15ث) قبل بلوغ المقارنة. الشاشة دخلت
       في 7923721 (2026-07-22) بعد تسجيل خط الأساس في 70f10c7 (2026-07-21)
       بيوم واحد، فتعطّل الحارس بصمت شهراً كاملاً. */
    if (url.pathname.includes("tenants/companies/my-companies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 1,
          role: "manager",
          is_default: true,
          created_at: "2026-07-22T00:00:00Z",
          can_access_import: true,
          tenant: {
            TenantID: 1,
            CompanyName: "Parity Census Co",
            SubscriptionPlan: "Enterprise",
            Status: "Active",
            CreatedAt: "2026-07-22T00:00:00Z",
            import_enabled: true,
          },
        }]),
      });
      return;
    }

    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ role: "manager", is_manager: true, permissions: [] }),
      });
      return;
    }

    if (url.pathname.includes("/mapper/activityStatus/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ isCurrentlyActive: true }),
      });
      return;
    }

    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

async function waitForStableView(page: Page, target: ViewTarget) {
  await page.goto(target.path!, { waitUntil: "domcontentloaded" });
  await page.locator("#root").waitFor({ state: "visible", timeout: 15_000 });

  // هذه الشاشات تُرسم خارج AppLayout فلا يوجد فيها main.app-content إطلاقاً.
  // كان المحدد سابقاً `main.app-content, [data-skin="aseel"]` فيمرّ عندها
  // بالصدفة لأن <html> كان يحمل data-skin="aseel" (الجلد الافتراضي القديم)؛
  // بعد أن صار الافتراضي modern توقّف عن المطابقة فانتهى الانتظار بمهلة
  // وسقطت الشاشتان في skipped. الاستثناء الصريح أدق ولا يعتمد على الجلد.
  const RENDERS_OUTSIDE_LAYOUT = new Set(["store", "aseel-kit", "aseel-sales"]);
  if (!RENDERS_OUTSIDE_LAYOUT.has(target.view)) {
    await page
      .locator("main.app-content")
      .first()
      .waitFor({ state: "visible", timeout: 15_000 });
  } else {
    // هذه الشاشات بلا `main.app-content` فلم يكن لها شرطُ جهوزية إطلاقاً:
    // حزمتها الكسولة تُترجم باردةً فتُلتقط الصفحةُ فارغةً، و«فارغ» حالةٌ
    // مستقرّة تجتازها حلقةُ الاستقرار — فيُبلَّغ عن سقوط الشاشة كلها زوراً.
    // انتظار أول زرّ يُنهي هذا التذبذب (وقع فعلاً على `aseel-sales`).
    await page
      .locator("#root button")
      .first()
      .waitFor({ state: "attached", timeout: 15_000 })
      .catch(() => { /* شاشةٌ بلا أزرار: يتولّاها الالتقاط كما هي */ });
  }

  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        caret-color: transparent !important;
        font-family: Tahoma, Arial, sans-serif !important;
      }
    `,
  });

  // App.tsx uses this exact wrapper while a lazy page chunk is loading. Do not
  // use networkidle here: several real screens intentionally poll in the background.
  if (target.view !== "store" && target.view !== "aseel-kit" && target.view !== "aseel-sales") {
    await page
      .locator("main.app-content .flex.justify-center.py-16 .animate-spin")
      .waitFor({ state: "hidden", timeout: 10_000 })
      .catch(() => undefined);
  }

  const signature = () =>
    page.evaluate(() => {
      const selectors = [
        "button",
        "input, select, textarea",
        '[role="tab"]',
        'th, .aseel-dense-table [role="columnheader"]',
        ".aseel-toolbtn",
      ];
      return JSON.stringify(
        selectors.map((selector) =>
          Array.from(document.querySelectorAll(selector))
            .map((element) => {
              const field = element as HTMLInputElement;
              return [
                (element.textContent ?? "").replace(/\s+/g, " ").trim(),
                field.getAttribute("name") ?? "",
                field.getAttribute("placeholder") ?? "",
                field.getAttribute("aria-label") ?? "",
              ].join("|");
            })
            .sort(),
        ),
      );
    });

  const deadline = Date.now() + 10_000;
  let previous = "";
  let stableSamples = 0;
  while (Date.now() < deadline && stableSamples < 2) {
    const current = await signature();
    stableSamples = current === previous ? stableSamples + 1 : 0;
    previous = current;
    await page.waitForTimeout(200);
  }
}

async function collectCensus(page: Page, path: string): Promise<ViewCensus> {
  const raw = await page.evaluate(() => {
    const text = (element: Element) =>
      (element.textContent ?? "").replace(/\s+/g, " ").trim();
    const values = (selector: string, map: (element: Element) => string) =>
      Array.from(document.querySelectorAll(selector)).map(map);

    return {
      buttons: values("button", text),
      fields: values("input, select, textarea", (element) => {
        const field = element as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
        return [
          `name=${field.getAttribute("name") ?? ""}`,
          `placeholder=${field.getAttribute("placeholder") ?? ""}`,
          `aria-label=${field.getAttribute("aria-label") ?? ""}`,
        ].join("|");
      }),
      tabs: values('[role="tab"]', text),
      tableHeaders: values('th, .aseel-dense-table [role="columnheader"]', text),
      toolbarItems: values(".aseel-toolbtn", text),
    };
  });

  const category = (values: string[]): CensusCategory => {
    const sorted = values.map(normalise).sort((a, b) => a.localeCompare(b, "ar"));
    return { count: sorted.length, values: sorted };
  };

  return {
    path,
    buttons: category(raw.buttons),
    fields: category(raw.fields),
    tabs: category(raw.tabs),
    tableHeaders: category(raw.tableHeaders),
    toolbarItems: category(raw.toolbarItems),
  };
}

function missingValues(baseline: string[], current: string[]): string[] {
  const available = new Map<string, number>();
  for (const value of current) available.set(value, (available.get(value) ?? 0) + 1);

  const missing: string[] = [];
  for (const value of baseline) {
    const count = available.get(value) ?? 0;
    if (count > 0) available.set(value, count - 1);
    else missing.push(value);
  }
  return missing;
}

function compareBaselines(baseline: ParityBaseline, current: ParityBaseline): string[] {
  const failures: string[] = [];
  const categories = ["buttons", "fields", "tabs", "tableHeaders", "toolbarItems"] as const;

  for (const [view, expectedView] of Object.entries(baseline.views)) {
    const actualView = current.views[view];
    if (!actualView) {
      failures.push(`${view}: entire view census is missing`);
      continue;
    }

    for (const category of categories) {
      const missing = missingValues(expectedView[category].values, actualView[category].values);
      if (missing.length > 0) {
        failures.push(
          `${view}.${category}: missing ${missing.map((value) => JSON.stringify(value)).join(", ")}`,
        );
      }

      const added = missingValues(actualView[category].values, expectedView[category].values);
      if (added.length > 0) {
        console.warn(
          `[parity] ${view}.${category}: new ${added.map((value) => JSON.stringify(value)).join(", ")}`,
        );
      }
    }
  }

  for (const view of Object.keys(current.views)) {
    if (!baseline.views[view]) console.warn(`[parity] ${view}: new view census`);
  }

  return failures;
}

function sortedBaseline(baseline: ParityBaseline): ParityBaseline {
  return {
    ...baseline,
    views: Object.fromEntries(Object.entries(baseline.views).sort(([a], [b]) => a.localeCompare(b))),
    skipped: Object.fromEntries(
      Object.entries(baseline.skipped).sort(([a], [b]) => a.localeCompare(b)),
    ),
  };
}

test("authenticated AppView feature-parity census", async ({ page }) => {
  test.setTimeout(15 * 60_000);
  expect(VIEW_TARGETS).toHaveLength(78);
  expect(new Set(VIEW_TARGETS.map(({ view }) => view)).size).toBe(78);

  await installAuthenticatedApiMocks(page);
  if (CAPTURE_SHOTS) await mkdir(SHOTS_DIR, { recursive: true });

  const current: ParityBaseline = {
    schemaVersion: 1,
    viewport: { width: 1440, height: 900 },
    views: {},
    skipped: {},
  };

  for (const target of VIEW_TARGETS) {
    if (target.skipReason || !target.path) {
      current.skipped[target.view] = target.skipReason ?? "no navigation target";
      continue;
    }

    try {
      await waitForStableView(page, target);
      current.views[target.view] = await collectCensus(page, target.path);

      if (CAPTURE_SHOTS) {
        await page.screenshot({
          path: join(SHOTS_DIR, `${target.view}.png`),
          fullPage: true,
          animations: "disabled",
        });
      }
    } catch (error) {
      current.skipped[target.view] = `navigation failed: ${
        error instanceof Error ? error.message.split("\n")[0] : String(error)
      }`;
    }
  }

  const deterministic = sortedBaseline(current);
  if (!COMPARE_MODE) {
    await writeFile(BASELINE_PATH, `${JSON.stringify(deterministic, null, 2)}\n`, "utf8");
    return;
  }

  const baseline = JSON.parse(await readFile(BASELINE_PATH, "utf8")) as ParityBaseline;
  const failures = compareBaselines(baseline, deterministic);
  expect(failures, failures.join("\n")).toEqual([]);
});
