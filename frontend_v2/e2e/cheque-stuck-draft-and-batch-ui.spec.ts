/**
 * CHQ-4 — الطريق المسدود يُفتح، والإيداع يصير حزمةً.
 *
 * ثلاثة أشياء لا يراها `tsc` (لا يفحص خصائص JSX هنا) ولا اختبارُ خادم:
 *   1. ورقةٌ سندُها مسودة: هل تظهر لها شارة «بانتظار ترحيل السند» وزرٌّ يرحّله
 *      فعلاً — أم تبقى الشاشة طريقاً مسدوداً كما كانت؟
 *   2. حالةٌ نهائية: هل اختفى زرّ «تحويل» الذي كان يفتح نافذةً فارغة؟
 *   3. التحديد المتعدد والإيداع الجماعي: الشريط والنافذة والجسم المُرسَل،
 *      ورفضُ الخادم الذرّي معروضاً بأسماء الأوراق لا برسالة عامة.
 */
import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const SHOTS = "e2e/cheque-batch-shots";

const MOVES_RECEIVED = [
  { value: "deposit", label: "إيداع للتحصيل (بنك)", requires_bank_account: true, requires_endorsee: false },
  { value: "collect", label: "تحصيل — دخل الصندوق/البنك", requires_bank_account: true, requires_endorsee: false },
];

/** ثلاث أوراق: مؤهَّلتان للإيداع، وواحدة عالقة بسندٍ مسودة، ورابعةٌ نهائية. */
const CHEQUES = [
  {
    id: 31, cheque_number: "BAT-1", amount: "1000.00", currency: 1,
    due_date: "2026-09-10", issue_date: "2026-08-01",
    bank_name: "بنك فلسطين", bank_display: "بنك فلسطين", account_number: "9001",
    payee_name: "شركتنا", partner: 8, direction: "Incoming",
    status: "Received", status_label: "مستلَم — في المحفظة",
    allowed_movements: MOVES_RECEIVED,
    needs_document_post: false,
    source_document: { type: "customer_payment", label: "سند قبض", id: 71, number: "#71", is_posted: true },
    deposit_bank_account: null, deposit_bank_account_name: null,
  },
  {
    id: 32, cheque_number: "BAT-2", amount: "500.00", currency: 1,
    due_date: "2026-09-12", issue_date: "2026-08-02",
    bank_name: "بنك القدس", bank_display: "بنك القدس", account_number: "9002",
    payee_name: "شركتنا", partner: 8, direction: "Incoming",
    status: "Received", status_label: "مستلَم — في المحفظة",
    allowed_movements: MOVES_RECEIVED,
    needs_document_post: false,
    source_document: { type: "customer_payment", label: "سند قبض", id: 72, number: "#72", is_posted: true },
    deposit_bank_account: null, deposit_bank_account_name: null,
  },
  {
    // العالقة: الخادم يُفرغ حركاتها لأن سندها لم يُرحَّل — لا قائمة كاذبة.
    id: 33, cheque_number: "STUCK-9", amount: "750.00", currency: 1,
    due_date: "2026-09-20", issue_date: "2026-08-03",
    bank_name: "البنك العربي", bank_display: "البنك العربي", account_number: "9003",
    payee_name: "شركتنا", partner: 8, direction: "Incoming",
    status: "Draft", status_label: "مسودة",
    allowed_movements: [],
    needs_document_post: true,
    source_document: { type: "customer_payment", label: "سند قبض", id: 73, number: "#73", is_posted: false },
    deposit_bank_account: null, deposit_bank_account_name: null,
  },
  {
    id: 34, cheque_number: "DONE-4", amount: "200.00", currency: 1,
    due_date: "2026-07-01", issue_date: "2026-06-01",
    bank_name: "بنك القاهرة", bank_display: "بنك القاهرة", account_number: "9004",
    payee_name: "شركتنا", partner: 8, direction: "Incoming",
    status: "Collected", status_label: "محصَّل",
    allowed_movements: [],
    needs_document_post: false,
    source_document: { type: "customer_payment", label: "سند قبض", id: 74, number: "#74", is_posted: true },
    deposit_bank_account: 3, deposit_bank_account_name: "بنك فلسطين — جاري شيكل (ILS)",
  },
];

const PARTNERS = [
  { id: 8, name: "عميل الشيكات", partner_type: "Customer" },
  { id: 9, name: "مورد الأدوات", partner_type: "Supplier" },
];

type Calls = { posted: string[]; deposits: unknown[]; listUrls: string[] };
type Mocks = { depositRejected?: boolean };

async function installMocks(page: Page, calls: Calls, opts: Mocks = {}) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "cheque-batch-token");
    localStorage.setItem("userId", "cheque-batch-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
    // القسيمة تُطبع بنافذةٍ منبثقة — تُستبدل بمزدوجٍ صامت كي لا يُحجب الاختبار.
    (window as unknown as { open: () => unknown }).open = () => ({
      document: { write() {}, close() {} },
      focus() {}, print() {}, close() {},
    });
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const path = url.pathname;

    let body: unknown = [];
    if (path.endsWith("/hr/users/cheque-batch-user/")) {
      body = {
        id: "cheque-batch-user", name: "محاسب الشيكات", role: "manager",
        email: "batch@example.test", employmentStatus: "active",
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
    } else if (/\/sales\/payments\/\d+\/post\/$/.test(path)) {
      calls.posted.push(path);
      body = { id: 73, is_posted: true };
    } else if (path.endsWith("/accounting/cheques/deposit-batch/")) {
      calls.deposits.push(JSON.parse(request.postData() || "{}"));
      if (opts.depositRejected) {
        return route.fulfill({
          status: 400, contentType: "application/json",
          body: JSON.stringify({
            detail: "تعذّر إيداع الدفعة — لم تُودَع أي ورقة.",
            rejected: [{ cheque_id: 32, cheque_number: "BAT-2", reason: "لا يمكن الإيداع من حالة «محصَّل»." }],
          }),
        });
      }
      return route.fulfill({
        status: 201, contentType: "application/json",
        body: JSON.stringify({
          deposited_count: 2, batch_ref: "ab12cd34",
          slip: {
            slip_date: "2026-08-25", batch_ref: "ab12cd34", notes: "إيداع الصباح",
            bank_account: { id: 3, bank_name: "بنك فلسطين", name: "جاري شيكل", account_number: "12345" },
            currency_code: "ILS", total: "1500.00",
            cheques: [
              { id: 31, cheque_number: "BAT-1", drawer_bank: "بنك فلسطين", payee_name: "شركتنا", partner_name: "عميل الشيكات", due_date: "2026-09-10", amount: "1000.00" },
              { id: 32, cheque_number: "BAT-2", drawer_bank: "بنك القدس", payee_name: "شركتنا", partner_name: "عميل الشيكات", due_date: "2026-09-12", amount: "500.00" },
            ],
          },
        }),
      });
    } else if (path.endsWith("/accounting/cheques/wallet/")) {
      body = { as_of: "2026-08-25", incoming: { open_total: "0", open_count: 0, buckets: [], due_buckets: [] }, outgoing: { open_total: "0", open_count: 0, buckets: [], due_buckets: [] }, net_open: "0" };
    } else if (path.endsWith("/movements/")) {
      body = [];
    } else if (path.endsWith("/accounting/cheques/")) {
      calls.listUrls.push(url.search);
      body = { count: CHEQUES.length, results: CHEQUES };
    } else if (path.endsWith("/accounting/bank-accounts/")) {
      body = [{
        id: 3, bank: 1, bank_name: "بنك فلسطين", branch: 5, branch_name: "فرع رام الله",
        name: "جاري شيكل", account_number: "12345", iban: null, currency: 1,
        currency_code: "ILS", account: 900, account_code: "1102K0001",
        is_default: true, is_active: true, notes: null, balance: "1500.00",
      }];
    } else if (path.endsWith("/dashboard/")) {
      body = {};
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function openCheques(page: Page, opts: Mocks = {}) {
  const calls: Calls = { posted: [], deposits: [], listUrls: [] };
  await installMocks(page, calls, opts);
  await page.goto("/accounting/cheques");
  await expect(page.getByText("BAT-1")).toBeVisible({ timeout: 15_000 });
  return calls;
}

test("الورقة العالقة تسمّي سندها ويُرحَّل من مكانه", async ({ page }) => {
  const calls = await openCheques(page);
  const stuck = page.locator("tbody tr", { hasText: "STUCK-9" });

  // شارةٌ تشرح لماذا لا حركة لها، ورابطٌ إلى سندها في عمود المستند.
  await expect(stuck.getByTestId("cheque-awaiting-post")).toBeVisible();
  await expect(stuck.getByTestId("cheque-source-link")).toContainText("سند قبض #73");
  // وزرّ «تحويل» لا يُعرض عليها — كان يفتح نافذةً بقائمة حركاتٍ مرفوضة حتماً.
  await expect(stuck.getByTitle("تحويل الشيك")).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/01-stuck-draft-names-its-voucher.png`, fullPage: true });

  await stuck.getByTestId("cheque-post-document").click();
  // التأكيد نافذةٌ داخل التطبيق لا حوار متصفح (`useConfirm`)، وزرّه «ترحيل»
  // لا «حذف»: `ConfirmDialog` افتراضه `danger` فيلزم تمرير النصّ صراحةً.
  await page.getByRole("button", { name: "ترحيل", exact: true }).click();
  await expect.poll(() => calls.posted).toContain("/api/sales/payments/73/post/");
});

test("الحالة النهائية لا زرّ لها — «نهائي» بدل وعدٍ كاذب", async ({ page }) => {
  await openCheques(page);
  const done = page.locator("tbody tr", { hasText: "DONE-4" });
  await expect(done.getByTitle("تحويل الشيك")).toHaveCount(0);
  await expect(done).toContainText("نهائي");
  // وبنك إيداعها ظاهرٌ في عموده — الدفاتر لا تحمل هذه الحقيقة.
  await expect(done).toContainText("بنك فلسطين — جاري شيكل");
});

test("حزمة الصباح: تحديدٌ متعدد، إجماليٌ قبل الفعل، وإيداعٌ ببنك", async ({ page }) => {
  const calls = await openCheques(page);

  // الورقة العالقة والنهائية بلا مربع اختيار — لا يُبطل تحديدُها الدفعة كلها.
  await expect(page.locator("tbody tr", { hasText: "STUCK-9" }).getByTestId("cheque-select")).toHaveCount(0);
  await expect(page.locator("tbody tr", { hasText: "DONE-4" }).getByTestId("cheque-select")).toHaveCount(0);

  await page.getByTestId("cheque-select-all").check();
  await expect(page.getByTestId("cheque-batch-summary")).toContainText("2");
  await expect(page.getByTestId("cheque-batch-summary")).toContainText("1,500");
  await page.screenshot({ path: `${SHOTS}/02-batch-bar-with-total.png`, fullPage: true });

  await page.getByTestId("cheque-deposit-open").click();
  const submit = page.getByTestId("cheque-deposit-submit");
  // بنكٌ إلزامي ما دامت للشركة بنوك — لا سقوطَ صامتٍ على الصندوق الافتراضي.
  await expect(submit).toBeDisabled();
  await page.getByTestId("cheque-deposit-bank").selectOption("3");
  await expect(submit).toBeEnabled();
  await page.screenshot({ path: `${SHOTS}/03-deposit-dialog.png`, fullPage: true });

  await submit.click();
  await expect.poll(() => calls.deposits.length).toBe(1);
  expect(calls.deposits[0]).toMatchObject({ cheque_ids: [31, 32], bank_account: 3 });
  await expect(page.getByTestId("cheque-deposit-dialog")).toHaveCount(0);
});

test("رفض الدفعة ذرّي — والشاشة تسمّي الورقة التي أبطلتها", async ({ page }) => {
  await openCheques(page, { depositRejected: true });

  await page.getByTestId("cheque-select-all").check();
  await page.getByTestId("cheque-deposit-open").click();
  await page.getByTestId("cheque-deposit-bank").selectOption("3");
  await page.getByTestId("cheque-deposit-submit").click();

  const rejected = page.getByTestId("cheque-deposit-rejected");
  await expect(rejected).toContainText("لم تُودَع أي ورقة");
  await expect(rejected).toContainText("BAT-2");
  await page.screenshot({ path: `${SHOTS}/04-atomic-rejection.png`, fullPage: true });
});

test("البحث يسافر إلى الخادم — لا تصفيةٌ في المتصفح", async ({ page }) => {
  const calls = await openCheques(page);
  calls.listUrls.length = 0;

  await page.getByTestId("cheque-search").fill("BAT-2");

  await expect.poll(() => calls.listUrls.some((s) => s.includes("search=BAT-2")))
    .toBe(true);
});
