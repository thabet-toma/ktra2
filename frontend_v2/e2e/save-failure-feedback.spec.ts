/**
 * SAVE-4 — إثبات معيار نجاح THA-123: «لا حفظ صامت ولا فقدان بيانات».
 *
 * الخادم لا يُشغَّل في بيئة الوكيل (MySQL80 متوقّفة بلا صلاحية تشغيل)، فالـAPI
 * مموَّه هنا على منوال `sales-invoice-collect-panel.spec.ts` القائم.
 *
 * ثلاثة مشاهد:
 *  1. رفض 400 بأخطاء حقول → سبب عربي **ظاهر**، والمحرّر مفتوح، وكل ما أُدخل باقٍ.
 *  2. فشل شبكة كامل (`route.abort`) → رسالة «لم يصل الطلب … بياناتك ما زالت أمامك».
 *  3. رفض 400 عام (`detail`) → السبب في اللافتة، والمحرّر مفتوح.
 *
 * لماذا اللافتة لا الـtoast: الـtoast يختفي بعد ثوانٍ، فلا يمكن لاختبار — ولا
 * لمستخدم — أن يؤكّد رسالةً غير موجودة. لذلك نُقل سبب الفشل إلى لافتة ثابتة.
 */
import { expect, test, type Page } from "@playwright/test";

test.use({ serviceWorkers: "block" });

/** كيف يفشل نداء الحفظ في هذا المشهد. */
type SaveFailure =
  | { kind: "fieldErrors" }
  | { kind: "detail" }
  | { kind: "networkDown" };

async function installMocks(page: Page, failure: SaveFailure) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "save-failure-token");
    localStorage.setItem("userId", "save-failure-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    const method = route.request().method();

    // ── نداء الحفظ: هو وحده ما نُسقطه ──────────────────────────────
    if (url.pathname.endsWith("/sales/invoices/") && method === "POST") {
      if (failure.kind === "networkDown") {
        // الطلب لا يصل الخادم إطلاقاً — يقابل انقطاع الشبكة.
        await route.abort("connectionrefused");
        return;
      }
      if (failure.kind === "fieldErrors") {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            customer: ["This field is required."],
            invoice_date: ["هذا الحقل مطلوب."],
          }),
        });
        return;
      }
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "الفترة المالية مقفلة — لا يمكن الحفظ في تاريخ مقفل." }),
      });
      return;
    }

    // ── ما تحتاجه الشاشة كي تفتح ──────────────────────────────────
    if (url.pathname.endsWith("/hr/users/save-failure-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "save-failure-user",
          name: "محاسب",
          role: "manager",
          email: "save@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 1,
          tenant: {
            TenantID: 1,
            CompanyName: "KTRA",
            SubscriptionPlan: "Enterprise",
            Status: "Active",
            CreatedAt: "2026-08-01T00:00:00Z",
          },
          role: "manager",
          is_default: true,
          created_at: "2026-08-01T00:00:00Z",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager",
          is_manager: true,
          ui_mode: "advanced",
          permissions: [
            "sales.invoice.view",
            "sales.invoice.edit",
            "sales.invoice.create",
            "sales.invoice.post",
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/partners/lookup/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ id: 8, name: "عميل الاختبار", partner_type: "Customer" }]),
      });
      return;
    }
    if (url.pathname.endsWith("/accounting/currencies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ CurrencyID: 1, Code: "ILS" }]),
      });
      return;
    }
    if (url.pathname.endsWith("/accounting/accounts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          { id: 10, code: "1101", name: "الصندوق الرئيسي", account_type: "Asset" },
          { id: 40, code: "4101", name: "المبيعات", account_type: "Revenue" },
        ]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/settings/current/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          default_cash_account: 10,
          default_currency: 1,
          default_customer: 8,
          default_revenue_account_product: 40,
        }),
      });
      return;
    }
    if (
      url.pathname.endsWith("/inventory/products/")
      || url.pathname.endsWith("/lookup/products/")
    ) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 42,
          sku: "P-42",
          name_ar: "لابتوب",
          quantity_on_hand: "9",
          sale_price: "100",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/sales/invoices/resolve-price/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ unit_price: "100", source: {} }),
      });
      return;
    }
    if (url.pathname.endsWith("/dashboard/")) {
      await route.fulfill({ contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

/**
 * يفتح محرّر فاتورة بيع جديدة ويملأ بنداً حقيقياً حتى يتجاوز تحقّق العميل
 * (`validateClient`) ويصل النداء إلى الخادم — وإلا لاختبرنا رسالة تحقّق محلّية
 * بدل رسالة رفض الخادم، وهي ليست موضوع هذه المهمة.
 */
async function openNewInvoiceAndFill(page: Page) {
  await page.goto("/sales/invoices/new");

  const product = page.getByPlaceholder("اكتب اسم المنتج…").first();
  await expect(product).toBeVisible({ timeout: 20_000 });
  await product.fill("لابتوب");
  await page.getByText("لابتوب").last().click();

  const qty = page.locator("#ktra-grid-input-0-quantity");
  await expect(qty).toBeVisible({ timeout: 10_000 });
  await qty.fill("2");

  // نصّ مميّز نتحقّق لاحقاً أنه لم يُمسح بفشل الحفظ.
  const notes = page.getByPlaceholder("ملاحظات").first();
  await notes.fill("علامة الاختبار — يجب ألا تُمسح");
}

test("رفض 400 بأخطاء حقول: السبب ظاهر، المحرّر مفتوح، والمدخلات باقية", async ({ page }) => {
  await installMocks(page, { kind: "fieldErrors" });
  await openNewInvoiceAndFill(page);

  await page.getByRole("button", { name: /حفظ/ }).first().click();

  // 1) السبب معروض ومعرَّب: التسمية العربية للحقل (`customer` → «العميل») مع
  //    ترجمة رسالة DRF الإنجليزية. لو عُرض الردّ خاماً لظهر
  //    «customer: This field is required.» ولسقط هذا التوكيد.
  const banner = page.locator(".ktra-banner--err");
  await expect(banner.first()).toBeVisible({ timeout: 15_000 });
  await expect(banner.first()).toContainText("العميل: هذا الحقل مطلوب");
  await expect(banner.first()).not.toContainText("This field is required");
  await expect(banner.first()).toContainText("تاريخ الفاتورة: هذا الحقل مطلوب");

  // 2) المحرّر لم يُغلق.
  await expect(page.getByPlaceholder("اكتب اسم المنتج…").first()).toBeVisible();

  // 3) ما أُدخل ما زال في مكانه.
  await expect(page.getByPlaceholder("ملاحظات").first())
    .toHaveValue("علامة الاختبار — يجب ألا تُمسح");
});

test("فشل شبكة كامل: «لم يصل الطلب … بياناتك ما زالت أمامك»", async ({ page }) => {
  await installMocks(page, { kind: "networkDown" });
  await openNewInvoiceAndFill(page);

  await page.getByRole("button", { name: /حفظ/ }).first().click();

  const banner = page.locator(".ktra-banner--err");
  await expect(banner.first()).toBeVisible({ timeout: 20_000 });
  await expect(banner.first()).toContainText("لم يصل الطلب إلى الخادم");
  await expect(banner.first()).toContainText("بياناتك ما زالت أمامك");

  await expect(page.getByPlaceholder("ملاحظات").first())
    .toHaveValue("علامة الاختبار — يجب ألا تُمسح");
});

test("رفض 400 عام: نصّ detail يظهر كما أرسله الخادم", async ({ page }) => {
  await installMocks(page, { kind: "detail" });
  await openNewInvoiceAndFill(page);

  await page.getByRole("button", { name: /حفظ/ }).first().click();

  const banner = page.locator(".ktra-banner--err");
  await expect(banner.first()).toBeVisible({ timeout: 15_000 });
  await expect(banner.first()).toContainText("الفترة المالية مقفلة");

  await expect(page.getByPlaceholder("ملاحظات").first())
    .toHaveValue("علامة الاختبار — يجب ألا تُمسح");
});


/* ─────────────────────────────────────────────────────────────────────────
   المشهد الرابع — فاتورة **الشراء** بمرفق مرفوع.
   هي الشاشة الوحيدة التي تحمل مرفقات، فبند معيار النجاح «الصورة المرفوعة ما
   زالت مرفقة» لا يُثبَت إلا عليها. ويثبت المشهدُ معه شيئين لم يكن عليهما دليل
   تشغيلي: مسار `purchaseInvoiceApi.handle` بعد إعادة كتابته، وعرضُ خطأ الحقل
   بجانب حقله في `InvoiceForm` (‏`tsc` لا يفحص خصائص JSX، فالبناء الأخضر لا
   يثبت أن المكوّن يُعرض).
   ──────────────────────────────────────────────────────────────────────── */

async function installPurchaseMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "save-failure-token");
    localStorage.setItem("userId", "save-failure-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const method = route.request().method();

    // رفع المرفق ينجح ويعيد رابطاً — المرجع يسكن حالة النموذج.
    if (url.pathname.endsWith("/media/upload/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ url: "https://cdn.example.test/attachment-proof.png" }),
      });
      return;
    }

    // حفظ فاتورة الشراء يُرفض بأخطاء حقول.
    if (url.pathname.endsWith("/logistics/purchase-invoices/") && method === "POST") {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({
          supplier: ["This field is required."],
          supplier_invoice_number: ["هذا الحقل مطلوب."],
        }),
      });
      return;
    }

    if (url.pathname.endsWith("/hr/users/save-failure-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "save-failure-user",
          name: "محاسب",
          role: "manager",
          email: "save@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 1,
          tenant: {
            TenantID: 1,
            CompanyName: "KTRA",
            SubscriptionPlan: "Enterprise",
            Status: "Active",
            CreatedAt: "2026-08-01T00:00:00Z",
          },
          role: "manager",
          is_default: true,
          created_at: "2026-08-01T00:00:00Z",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/permissions/me/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "manager",
          is_manager: true,
          ui_mode: "advanced",
          permissions: [
            "purchase.invoice.view",
            "purchase.invoice.edit",
            "purchase.invoice.create",
            "purchase.invoice.post",
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/accounting/accounts/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([
          { id: 10, code: "1101", name: "الصندوق الرئيسي", account_type: "Asset" },
          { id: 51, code: "5101", name: "مصاريف شحن", account_type: "Expense" },
        ]),
      });
      return;
    }
    // مورد ومنتج حقيقيان — بدونهما يوقف تحقّق العميل النداءَ قبل خروجه فلا
    // نختبر رفض الخادم أصلاً.
    if (url.pathname.includes("/partners/lookup/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 8,
          name: "مورد الاختبار",
          partner_type: "Supplier",
          trade_name: "مورد الاختبار",
        }]),
      });
      return;
    }
    if (
      url.pathname.endsWith("/inventory/products/")
      || url.pathname.endsWith("/lookup/products/")
    ) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{
          id: 42,
          sku: "P-42",
          name_ar: "لابتوب",
          quantity_on_hand: "9",
          purchase_price: "100",
          sale_price: "150",
        }]),
      });
      return;
    }
    if (url.pathname.endsWith("/dashboard/")) {
      await route.fulfill({ contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });
}

test("فاتورة شراء بمرفق: الرفض يُبقي النموذج والمرفق، ويعرض الخطأ بجانب حقله", async ({ page }) => {
  await installPurchaseMocks(page);
  // زرّ «فاتورة جديدة» في القائمة يفتح **تبويباً جديداً**، فنقصد المسار مباشرة.
  await page.goto("/purchase-invoices/new");

  // مورد حقيقي — بدونه يوقف تحقّق العميل النداءَ قبل خروجه فلا نختبر رفض
  // الخادم أصلاً. الاختيار من الفهرس يكون بنقرة مزدوجة على السطر.
  await expect(page.locator('[data-ktra-field="supplier"]')).toBeVisible({ timeout: 20_000 });
  await page.locator('[data-ktra-field="supplier"]').click();
  await page.getByRole("row").filter({ hasText: "مورد الاختبار" }).first().dblclick();
  await expect(page.locator('[data-ktra-field="supplier"]')).toHaveValue("#8");

  // المرفقات في تبويبها الخاص — حقل الملف لا يُرندَر قبل فتحه. وفي القسم
  // منطقتا رفع: الأولى لملفات PDF والثانية للصور، فنقصد الثانية.
  await page.getByText("المرفقات", { exact: true }).first().click();
  const fileInput = page.locator('input[type="file"]').nth(1);
  await expect(fileInput).toBeAttached({ timeout: 20_000 });

  // مرفق مرفوع فعلاً قبل الحفظ (`FileDropZone` يخفي حقل الملف، فنملؤه مباشرة).
  await fileInput.setInputFiles({
    name: "attachment-proof.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
      "base64",
    ),
  });

  const attachment = page.locator('img[src*="attachment-proof"]');
  await expect(attachment.first()).toBeVisible({ timeout: 20_000 });

  // زرّ الحفظ في هذا المحرّر اسمه «تخزين (F12)» لا «حفظ».
  await page.getByRole("button", { name: /تخزين/ }).first().click();

  // 1) سبب عربي ظاهر في لافتة ثابتة.
  const banner = page.getByTestId("save-error");
  await expect(banner).toBeVisible({ timeout: 15_000 });
  await expect(banner).toContainText("المورد: هذا الحقل مطلوب");
  await expect(banner).not.toContainText("This field is required");
  await expect(banner).not.toContainText("supplier");

  // 2) خطأ الحقل معروض **بجانب حقله** لا في اللافتة وحدها — وهذا ما يثبت أن
  //    `FieldError` داخل `fld()` حيّ فعلاً (`tsc` لا يفحص خصائص JSX).
  //    حقل المورد في تبويب «بيانات الفاتورة».
  await page.getByText("بيانات الفاتورة", { exact: true }).first().click();
  const supplierField = page
    .locator("label.ktra-field")
    .filter({ hasText: "المورد" })
    .first();
  await expect(supplierField.getByRole("alert")).toHaveText("هذا الحقل مطلوب.");

  // 3) النموذج لم يُغلق — ما زلنا في المحرّر لا في القائمة.
  await expect(page.locator('[data-ktra-field="supplier"]')).toBeVisible();

  // 4) المرفق ما زال مرفقاً — بند معيار النجاح. (نعود إلى تبويبه: التبويبات
  //    تُرندَر عند فتحها، فالصورة لا توجد في DOM تبويب «بيانات الفاتورة».)
  await page.getByText("المرفقات", { exact: true }).first().click();
  await expect(attachment.first()).toBeVisible();
});
