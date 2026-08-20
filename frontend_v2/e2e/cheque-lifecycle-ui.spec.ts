/**
 * CHQ-4 — دورة حياة الشيك على الشاشة.
 *
 * الخادم لا يُشغَّل في بيئة الوكيل (MySQL متوقّف)، فالـAPI مموَّه هنا بشكل عقد
 * CHQ-3 حرفياً: `status_label` و`allowed_movements` مع كل شيك، و`journal_number`
 * مع كل حركة، وتقرير `cheques-maturity` بصفوفه الخاصة.
 *
 * الفخّ المقصود: `tsc` لا يفحص خصائص JSX هنا، فالمكوّن قد يكون سليماً والشاشة
 * ميّتة. هذه الاختبارات تفتح الشاشة الحيّة وتضغط أزرارها.
 */
import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const SHOTS = "e2e/cheque-lifecycle-shots";

/** الحركات كما يبنيها `allowed_movement_options` في الخادم — لا جدول في الواجهة. */
const CHEQUES = [
  {
    id: 7, cheque_number: "CH-700", amount: "1000.00", currency: 1,
    due_date: "2026-09-01", issue_date: "2026-08-01",
    bank_name: "بنك فلسطين", bank_display: "بنك فلسطين", account_number: "9001",
    payee_name: "شركتنا", partner: 8, direction: "Incoming",
    status: "Received", status_label: "مستلَم — في المحفظة",
    allowed_movements: [
      { value: "deposit", label: "إيداع للتحصيل (بنك)", requires_bank_account: false, requires_endorsee: false },
      { value: "collect", label: "تحصيل — دخل الصندوق/البنك", requires_bank_account: true, requires_endorsee: false },
      { value: "endorse", label: "تظهير لطرف ثالث", requires_bank_account: false, requires_endorsee: true },
      { value: "return_to_customer", label: "إعادة الورقة للعميل", requires_bank_account: false, requires_endorsee: false },
    ],
  },
  {
    id: 8, cheque_number: "CH-800", amount: "400.00", currency: 1,
    due_date: "2026-08-25", issue_date: "2026-08-02",
    bank_name: "البنك العربي", bank_display: "البنك العربي", account_number: "4402",
    payee_name: "مورد الأدوات", partner: 9, direction: "Outgoing",
    // نفس الرمز `Under_Collection` — وتسميته على الصادر ليست «برسم التحصيل».
    status: "Under_Collection", status_label: "مسلَّم — بانتظار الصرف",
    allowed_movements: [
      { value: "collect", label: "صُرف من حسابنا — إغلاق الالتزام", requires_bank_account: true, requires_endorsee: false },
      { value: "withdraw", label: "صرف مباشر من حسابنا", requires_bank_account: true, requires_endorsee: false },
      { value: "bounce", label: "ارتداد — عاد الدين على المورد", requires_bank_account: false, requires_endorsee: false },
      { value: "cancel", label: "إلغاء الشيك — إيقافه قبل صرفه", requires_bank_account: false, requires_endorsee: false },
    ],
  },
  {
    id: 9, cheque_number: "CH-900", amount: "250.00", currency: 1,
    due_date: "2026-08-10", issue_date: "2026-07-20",
    bank_name: "بنك القدس", bank_display: "بنك القدس", account_number: "7712",
    payee_name: "شركتنا", partner: 8, direction: "Incoming",
    status: "Bounced", status_label: "مرتدّ",
    allowed_movements: [
      { value: "redeposit", label: "إعادة إيداع بعد الارتداد", requires_bank_account: false, requires_endorsee: false },
      { value: "return_to_customer", label: "إعادة الورقة للعميل", requires_bank_account: false, requires_endorsee: false },
      { value: "settle", label: "تسوية نقدية من العميل", requires_bank_account: true, requires_endorsee: false },
    ],
  },
];

/** حركتان: واحدة أنتجت قيداً، وواحدة لم تمسّ الدفاتر — ولا مبلغ مع أيّهما. */
const MOVEMENTS_7 = [
  {
    id: 21, cheque: 7, movement_type: "receive",
    movement_type_display: "استلام", movement_type_label: "استلام ضمن سند القبض",
    journal: 55, journal_number: "#55", journal_reference: "customer_payment",
    journal_date: "2026-08-01",
    notes: "سند قبض 12", created_at: "2026-08-01T09:15:00Z", created_by_name: "أمين الصندوق",
  },
  {
    id: 22, cheque: 7, movement_type: "deposit",
    movement_type_display: "إيداع", movement_type_label: "إيداع للتحصيل (بنك)",
    journal: null, journal_number: null, journal_reference: null, journal_date: null,
    notes: "", created_at: "2026-08-05T11:00:00Z", created_by_name: "أمين الصندوق",
  },
];

const WALLET = {
  as_of: "2026-08-20",
  incoming: {
    open_total: "1250.00", open_count: 2,
    buckets: [
      { status: "Bounced", count: 1, amount: "250.00" },
      { status: "Received", count: 1, amount: "1000.00" },
    ],
    due_buckets: [
      { key: "overdue", label: "متأخر", count: 1, amount: "250.00" },
      { key: "d30", label: "خلال 30 يوماً", count: 1, amount: "1000.00" },
    ],
  },
  outgoing: {
    open_total: "400.00", open_count: 1,
    buckets: [{ status: "Under_Collection", count: 1, amount: "400.00" }],
    due_buckets: [{ key: "d30", label: "خلال 30 يوماً", count: 1, amount: "400.00" }],
  },
  net_open: "850.00",
};

/** التقرير كما يبنيه `_cheques_maturity`: المتأخر أولاً، وسطر بلا استحقاق آخراً. */
const MATURITY = {
  key: "cheques-maturity",
  title: "استحقاق الشيكات وأثر السيولة",
  category: "finance",
  description: "الشيكات المفتوحة أسبوعاً بأسبوع على أفق 90 يوماً.",
  columns: [
    { key: "period", header: "الفترة", kind: "text", width: "150px" },
    { key: "due_from", header: "من", kind: "date", width: "110px" },
    { key: "due_to", header: "إلى", kind: "date", width: "110px" },
    { key: "incoming_count", header: "عدد الوارد", kind: "int", total: true },
    { key: "incoming", header: "وارد مستحق", kind: "money", total: true },
    { key: "outgoing_count", header: "عدد الصادر", kind: "int", total: true },
    { key: "outgoing", header: "صادر مستحق", kind: "money", total: true },
    { key: "net", header: "الصافي", kind: "money", total: true },
    { key: "cumulative_net", header: "الصافي التراكمي", kind: "money" },
  ],
  rows: [
    {
      period_key: "overdue", period: "متأخر", due_from: null, due_to: "2026-08-19",
      incoming_count: 1, incoming: "250.00", outgoing_count: 0, outgoing: "0.00",
      net: "250.00", cumulative_net: "250.00",
    },
    {
      period_key: "w1", period: "الأسبوع 1", due_from: "2026-08-20", due_to: "2026-08-26",
      incoming_count: 0, incoming: "0.00", outgoing_count: 1, outgoing: "400.00",
      net: "-400.00", cumulative_net: "-150.00",
    },
    {
      period_key: "w2", period: "الأسبوع 2", due_from: "2026-08-27", due_to: "2026-09-02",
      incoming_count: 1, incoming: "1000.00", outgoing_count: 0, outgoing: "0.00",
      net: "1000.00", cumulative_net: "850.00",
    },
    {
      period_key: "undated", period: "بلا تاريخ استحقاق", due_from: null, due_to: null,
      incoming_count: 1, incoming: "75.00", outgoing_count: 0, outgoing: "0.00",
      net: "75.00", cumulative_net: "",
    },
  ],
  totals: {
    incoming_count: "3", incoming: "1325.00", outgoing_count: "1",
    outgoing: "400.00", net: "925.00",
  },
  generated_at: "2026-08-20T08:00:00Z",
};

const PARTNERS = [
  { id: 8, name: "عميل الشيكات", partner_type: "Customer" },
  { id: 9, name: "مورد الأدوات", partner_type: "Supplier" },
  { id: 10, name: "مورد التغليف", partner_type: "Supplier" },
];

/** رفض الخادم على التحويل — الشكل الحقيقي: `ValidationError` تُغلَّف `{"detail": [...]}`. */
type Mocks = { transferError?: string };

async function installMocks(page: Page, opts: Mocks = {}) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "cheque-lifecycle-token");
    localStorage.setItem("userId", "cheque-lifecycle-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const path = url.pathname;

    let body: unknown = [];
    if (path.endsWith("/hr/users/cheque-lifecycle-user/")) {
      body = {
        id: "cheque-lifecycle-user", name: "محاسب الشيكات", role: "manager",
        email: "cheques@example.test", employmentStatus: "active",
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith("/tenants/companies/my-companies/")) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: "شركة الشيكات", SubscriptionPlan: "Enterprise",
          Status: "Active", CreatedAt: "2026-07-01T00:00:00Z", import_enabled: false,
        },
        role: "manager", is_default: true, created_at: "2026-07-01T00:00:00Z",
      }];
    } else if (path.endsWith("/permissions/me/")) {
      body = { role: "manager", is_manager: true, ui_mode: "advanced", permissions: [] };
    } else if (path.endsWith("/partners/lookup/")) {
      const type = url.searchParams.get("partner_type");
      body = type ? PARTNERS.filter((p) => p.partner_type === type) : PARTNERS;
    } else if (path.endsWith("/accounting/cheques/wallet/")) {
      body = WALLET;
    } else if (path.endsWith("/movements/")) {
      body = MOVEMENTS_7;
    } else if (/\/accounting\/cheques\/\d+\/transfer\/$/.test(path)) {
      if (opts.transferError) {
        return route.fulfill({
          status: 400, contentType: "application/json",
          body: JSON.stringify({ detail: [opts.transferError] }),
        });
      }
      body = CHEQUES[0];
    } else if (path.endsWith("/accounting/cheques/")) {
      body = CHEQUES;
    } else if (path.endsWith("/accounting/bank-accounts/")) {
      body = [{
        id: 3, bank: 1, bank_name: "بنك فلسطين", branch: 5, branch_name: "فرع رام الله",
        name: "جاري شيكل", account_number: "12345", iban: null, currency: 1,
        currency_code: "ILS", account: 900, account_code: "1102K0001",
        is_default: true, is_active: true, notes: null, balance: "1500.00",
      }];
    } else if (path.endsWith("/accounting/currencies/")) {
      body = [{ CurrencyID: 1, Code: "ILS", Name: "شيكل", Symbol: "₪", IsBaseCurrency: true }];
    } else if (path.endsWith("/reports/cheques-maturity/")) {
      body = MATURITY;
    } else if (path.endsWith("/dashboard/")) {
      body = {};
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function openCheques(page: Page, opts: Mocks = {}) {
  await installMocks(page, opts);
  await page.goto("/accounting/cheques");
  await expect(page.getByText("CH-700")).toBeVisible({ timeout: 15_000 });
}

test("الحالة تُقرأ بتسمية اتجاهها — الرمز واحد والدلالة مختلفة", async ({ page }) => {
  await openCheques(page);
  // نفس `Under_Collection` لا يُقرأ «برسم التحصيل» على ورقة تخرج من حسابنا.
  await expect(page.locator("tbody tr", { hasText: "CH-700" }))
    .toContainText("مستلَم — في المحفظة");
  await expect(page.locator("tbody tr", { hasText: "CH-800" }))
    .toContainText("مسلَّم — بانتظار الصرف");
  await expect(page.getByText("برسم التحصيل")).toHaveCount(0);
  // وفلتر الحالة يعرض التسميات نفسها، لا جدولاً ثانياً.
  const statusFilter = page.locator(".aseel-field", { hasText: "الحالة" }).first().locator("select");
  await expect(statusFilter.locator("option")).toContainText([
    "الكل", "مستلَم — في المحفظة", "مسلَّم — بانتظار الصرف", "مرتدّ",
  ]);
  await page.screenshot({ path: `${SHOTS}/01-status-labels-per-direction.png`, fullPage: true });
});

test("أزرار الحركة تأتي من الخادم: إلغاء للصادر، وإعادة إيداع للمرتدّ", async ({ page }) => {
  await openCheques(page);

  await page.locator("tbody tr", { hasText: "CH-800" }).getByTitle("تحويل الشيك").click();
  const moves = page.getByTestId("cheque-move-select").locator("option");
  await expect(moves).toContainText(["— اختر الحركة —", "صُرف من حسابنا — إغلاق الالتزام",
    "صرف مباشر من حسابنا", "ارتداد — عاد الدين على المورد", "إلغاء الشيك — إيقافه قبل صرفه"]);
  await page.screenshot({ path: `${SHOTS}/02-outgoing-actions-with-cancel.png`, fullPage: true });
  await page.getByRole("button", { name: "إلغاء", exact: true }).click();

  await page.locator("tbody tr", { hasText: "CH-900" }).getByTitle("تحويل الشيك").click();
  await expect(page.getByTestId("cheque-move-select").locator("option"))
    .toContainText(["إعادة إيداع بعد الارتداد", "إعادة الورقة للعميل", "تسوية نقدية من العميل"]);
  await page.screenshot({ path: `${SHOTS}/03-bounced-actions-with-redeposit.png`, fullPage: true });
});

test("التظهير يطلب المورد المستفيد ويرسله، والحساب البنكي يظهر للتحصيل وحده", async ({ page }) => {
  await openCheques(page);
  await page.locator("tbody tr", { hasText: "CH-700" }).getByTitle("تحويل الشيك").click();

  // `requires_bank_account` وحده يفتح حقل الحساب — لا قائمة حركات في الواجهة.
  await page.getByTestId("cheque-move-select").selectOption("collect");
  await expect(page.getByTestId("cheque-bank-select")).toBeVisible();
  await expect(page.getByTestId("cheque-endorsee-select")).toHaveCount(0);

  await page.getByTestId("cheque-move-select").selectOption("endorse");
  await expect(page.getByTestId("cheque-bank-select")).toHaveCount(0);
  const endorsee = page.getByTestId("cheque-endorsee-select");
  await expect(endorsee).toBeVisible();
  // بلا مستفيد لا يمرّ الإرسال — القيد بلا طرفٍ مدين لا معنى له.
  await expect(page.getByTestId("cheque-transfer-submit")).toBeDisabled();
  // والقائمة موردون فقط: العميل ليس فيها.
  await expect(endorsee.locator("option")).toContainText(["— اختر المورد —", "مورد الأدوات", "مورد التغليف"]);
  await expect(endorsee.locator("option", { hasText: "عميل الشيكات" })).toHaveCount(0);

  await endorsee.selectOption("10");
  await page.screenshot({ path: `${SHOTS}/04-endorse-picks-supplier.png`, fullPage: true });

  const request = page.waitForRequest((r) =>
    r.method() === "POST" && new URL(r.url()).pathname.endsWith("/accounting/cheques/7/transfer/"));
  await page.getByTestId("cheque-transfer-submit").click();
  expect((await request).postDataJSON()).toMatchObject({
    movement_type: "endorse",
    endorsed_to: 10,
  });
});

test("مسار الشيك يعرض قيد كل خطوة رابطاً — بلا مبلغ", async ({ page }) => {
  await openCheques(page);
  await page.locator("tbody tr", { hasText: "CH-700" }).getByTitle("تحويل الشيك").click();

  const rows = page.getByTestId("cheque-movement-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText("استلام ضمن سند القبض");
  // الخطوة التي لم تمسّ الدفاتر تقولها صراحةً بدل رابط ميّت.
  await expect(rows.nth(1)).toContainText("بلا قيد");
  // لا مبلغ في السطر — لا مبلغ الشيك ولا مبلغ القيد (THA-489).
  await expect(rows.first()).not.toContainText("1,000");
  await expect(rows.first()).not.toContainText("1000");
  await page.screenshot({ path: `${SHOTS}/05-movement-log-journal-links.png`, fullPage: true });

  await page.getByTestId("cheque-journal-link").first().click();
  await expect(page).toHaveURL(/\/accounting\/journals\/55$/);
});

test("رفض الخادم يظهر في النافذة — لا ضغطة تذهب بلا ردّ (THA-492)", async ({ page }) => {
  // CHQ-1 استحدث حارس «السند غير مرحّل»؛ كل رفضٍ منه يصل إلى هذه النافذة،
  // وكانت `err` تُكتب ولا تُعرض: المستخدم يضغط «تحويل» فلا يحدث شيء إطلاقاً.
  const detail = "لا يمكن تحريك الشيك CH-700 قبل ترحيل السند/الفاتورة المرتبطة به — رحّل المستند أولاً ثم أعد المحاولة.";
  await openCheques(page, { transferError: detail });
  await page.locator("tbody tr", { hasText: "CH-700" }).getByTitle("تحويل الشيك").click();
  await page.getByTestId("cheque-move-select").selectOption("deposit");
  await page.getByTestId("cheque-transfer-submit").click();

  // الرسالة نفسها التي أرسلها الخادم، مرئيةً على الشاشة — لا نصّ عام.
  const banner = page.getByTestId("cheque-transfer-error");
  await expect(banner).toBeVisible({ timeout: 15_000 });
  await expect(banner).toContainText("قبل ترحيل السند");
  // والنافذة تبقى مفتوحة بمدخلاتها كي يُعاد المحاولة بعد ترحيل السند.
  await expect(page.getByTestId("cheque-transfer-dialog")).toBeVisible();
  await expect(page.getByTestId("cheque-transfer-submit")).toBeEnabled();
  await page.screenshot({ path: `${SHOTS}/07-transfer-rejection-visible.png`, fullPage: true });
});

test("تبويب الاستحقاق: المتأخر أولاً، والسطر بلا تاريخ تراكميّه «—» لا صفر", async ({ page }) => {
  await openCheques(page);
  await page.getByRole("tab", { name: "الاستحقاق والسيولة" }).click();

  const overdue = page.locator("tbody tr", { hasText: "متأخر" }).first();
  await expect(overdue).toBeVisible({ timeout: 15_000 });
  await expect(overdue).toContainText("250");

  const undated = page.locator("tbody tr", { hasText: "بلا تاريخ استحقاق" }).first();
  const cells = undated.locator("td");
  // آخر عمود = الصافي التراكمي: فارغٌ من الخادم عمداً، يُعرض «—» لا «0».
  await expect(cells.last()).toHaveText("—");
  await page.screenshot({ path: `${SHOTS}/06-maturity-tab.png`, fullPage: true });
});
