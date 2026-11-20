import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const INITIAL_SETTINGS = {
  id: 1,
  default_customer: 10,
  default_customer_name: "زبون نقدي",
  default_currency: 1,
  default_currency_code: "ILS",
  default_revenue_account_product: 401,
  default_revenue_account_product_name: "إيراد المبيعات",
  default_revenue_account_service: 402,
  default_revenue_account_service_name: "إيراد الخدمات",
  default_cash_account: 101,
  default_cash_account_name: "الصندوق الرئيسي",
  default_inventory_account: 104,
  default_cogs_account: 501,
  cost_variance_account: null as number | null,
  cost_variance_account_name: null as string | null,
  cogs_cost_method: "fifo",
  product_price_column: "last_purchase",
  default_ar_account: 102,
  default_payment_type: "credit",
  stock_on_post_default: true,
  negative_stock_policy: "allow",
  default_vat_rate: 1,
  default_vat_rate_code: "VAT16",
  default_vat_rate_value: "16.000",
  vat_input_account: 105,
  vat_input_account_name: "ضريبة مدخلات",
  prices_include_tax: false,
  auto_post_invoices: false,
  auto_post_payments: true,
  auto_refund_on_sales_return: false,
  show_journal_preview: true,
  warn_on_duplicate_item: true,
  loss_invoice_policy: "allow",
  customer_approval_post_policy: "allow",
  serial_entry_mode: "off",
  dormant_customer_days: 30,
  quotation_valid_days: 14,
  order_reserve_days: 7,
  allow_document_delete: true,
  block_reserved_stock_sale: true,
  default_shipping_origin: "",
  default_shipping_destination: "",
  delivery_doc_label: "إرسالية",
  standalone_delivery_label: "سند تسليم",
  allow_standalone_delivery: true,
  allow_edit_delivery: true,
  updated_at: "2026-11-20T10:00:00Z",
};

const STUB_ACCOUNTS = [
  { id: 100, code: "1", name: "الأصول", parent: null, account_type: "Asset", is_active: true, nature: null as string | null },
  { id: 101, code: "1101", name: "الصندوق الرئيسي", parent: 100, account_type: "Asset", is_active: true, nature: null as string | null },
  { id: 102, code: "1201", name: "ذمم العملاء", parent: 100, account_type: "Asset", is_active: true, nature: null as string | null },
  { id: 104, code: "1301", name: "المخزون", parent: 100, account_type: "Asset", is_active: true, nature: null as string | null },
  { id: 105, code: "1401", name: "ضريبة مدخلات", parent: 100, account_type: "Asset", is_active: true, nature: null as string | null },
  { id: 400, code: "4", name: "الإيرادات", parent: null, account_type: "Revenue", is_active: true, nature: null as string | null },
  { id: 401, code: "4101", name: "إيراد المبيعات", parent: 400, account_type: "Revenue", is_active: true, nature: null as string | null },
  { id: 402, code: "4102", name: "إيراد الخدمات", parent: 400, account_type: "Revenue", is_active: true, nature: null as string | null },
  { id: 500, code: "5", name: "تكلفة المبيعات", parent: null, account_type: "Expense", is_active: true, nature: null as string | null },
  { id: 501, code: "5101", name: "تكلفة البضاعة المباعة", parent: 500, account_type: "Expense", is_active: true, nature: null as string | null },
];
const STUB_CURRENCIES = [{ CurrencyID: 1, Code: "ILS", Name: "شيكل" }];
const STUB_PARTNERS = [{ id: 10, name: "زبون نقدي", partner_type: "Customer" }];
const STUB_TAX_RATES = [{ id: 1, code: "VAT16", name: "ض.ق.م", rate: "16" }];

type StubAccount = {
  id: number;
  code: string;
  name: string;
  parent: number | null;
  account_type: string;
  is_active: boolean;
  nature: string | null;
};

// مرآة `inventory/models.py` (`COGS_METHOD_CHOICES`).
const COGS_METHOD_CHOICES = ["fifo", "avco", "standard", "last_purchase"];
// معرّف الحساب الذي يُنشئه المحلِّل في الـstub؛ يبقي تأكيد غياب «#5190» ذا معنى.
const CREATED_VARIANCE_ACCOUNT_ID = 5190;
const MISSING_COGS_VARIANCE_ACCOUNT_ERROR =
  "تعذّر إنشاء حساب فروقات التكلفة تلقائياً لعدم وجود حساب تكلفة مبيعات صالح؛ " +
  "يرجى اختيار حساب الفروقات يدوياً.";

async function installMocks(page: Page) {
  let saved = { ...INITIAL_SETTINGS };
  const patchPayloads: Array<Record<string, unknown>> = [];
  const accounts: StubAccount[] = STUB_ACCOUNTS.map((a) => ({ ...a }));

  // مرآة `sales/services/foundation.py` (`cost_variance_account_error`) بترتيب فحوصه.
  // فحصا «يتبع الشركة نفسها» (للحساب ولحساب التكلفة) لا ينطبقان على stub بشركة واحدة:
  // الحقل `TenantScopedPrimaryKeyRelatedField` يرفض الـpk الأجنبي قبلهما بـ«غير موجود».
  const costVarianceAccountError = (
    acc: StubAccount,
    cogsAcc: StubAccount | null,
  ): string | null => {
    if (acc.account_type !== "Expense") {
      return "حساب فروقات التكلفة يجب أن يكون من نوع مصروفات (Expense).";
    }
    if (!acc.is_active) {
      return "حساب فروقات التكلفة يجب أن يكون نشطاً.";
    }
    if (accounts.some((a) => a.parent === acc.id)) {
      return "حساب فروقات التكلفة يجب أن يكون حساباً فرعياً (ورقة) بلا حسابات تابعة.";
    }
    if (acc.nature != null && acc.nature !== "" && acc.nature !== "both") {
      return "طبيعة حساب فروقات التكلفة يجب أن تقبل المدين والدائن.";
    }
    if (cogsAcc == null) {
      return "عيّن حساب تكلفة المبيعات الافتراضي أولاً قبل تحديد حساب الفروقات.";
    }
    if (acc.id === cogsAcc.id) {
      return "حساب فروقات التكلفة لا يمكن أن يكون نفس حساب تكلفة المبيعات الافتراضي.";
    }
    const cogsCode = (cogsAcc.code ?? "").trim();
    if (cogsCode.length < 2) {
      return "عيّن حساب تكلفة مبيعات بكود صالح (حرفان على الأقل) أولاً.";
    }
    if (!(acc.code ?? "").trim().startsWith(cogsCode.slice(0, 2))) {
      return `حساب فروقات التكلفة يجب أن يكون ضمن مجموعة تكلفة المبيعات (يبدأ كوده بـ ${cogsCode.slice(0, 2)}).`;
    }
    return null;
  };

  // مرآة `_inspect_default_cost_variance_account` (ومنها `default_cost_variance_account_code`
  // و`default_cost_variance_account_error`): الكود `G+90`، والحساب القائم الصالح، أو رسالة الخطأ.
  const inspectDefaultCostVarianceAccount = (
    cogsAcc: StubAccount | null,
  ): { code: string | null; existing: StubAccount | null; error: string | null } => {
    if (cogsAcc == null) {
      return { code: null, existing: null, error: MISSING_COGS_VARIANCE_ACCOUNT_ERROR };
    }
    const cogsCode = (cogsAcc.code ?? "").trim();
    if (cogsCode.length < 2) {
      return { code: null, existing: null, error: MISSING_COGS_VARIANCE_ACCOUNT_ERROR };
    }
    const code = `${cogsCode.slice(0, 2)}90`;
    const existing = accounts.find((a) => a.code === code) ?? null;
    if (existing != null) {
      if (costVarianceAccountError(existing, cogsAcc) != null) {
        return {
          code,
          existing: null,
          error:
            `الحساب الافتراضي (${code}) موجود لكنه لا يصلح كحساب فروقات تكلفة؛ ` +
            "يرجى اختيار حساب الفروقات يدوياً.",
        };
      }
      return { code, existing, error: null };
    }
    return { code, existing: null, error: null };
  };

  await page.addInitScript(() => {
    localStorage.setItem("token", "cogs-settings-e2e-token");
    localStorage.setItem("userId", "cogs-settings-e2e-user");
    localStorage.setItem("tenantId", "1");
    localStorage.setItem("ktra_ui_mode::1", "advanced");
  });

  await page.route("**/*", async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    const p = url.pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (p.endsWith("/hr/users/cogs-settings-e2e-user/")) {
      return json({
        id: "cogs-settings-e2e-user",
        name: "مدير المبيعات",
        role: "manager",
        email: "sales-settings@example.test",
        employmentStatus: "active",
        isApproved: true,
        isEmailVerified: true,
      });
    }
    if (p.endsWith("/tenants/companies/my-companies/")) {
      return json([{
        id: 1,
        role: "manager",
        is_default: true,
        can_access_import: false,
        created_at: "2026-01-01T00:00:00Z",
        tenant: {
          TenantID: 1,
          CompanyName: "شركة المبيعات",
          SubscriptionPlan: "Enterprise",
          Status: "Active",
          CreatedAt: "2026-01-01T00:00:00Z",
          import_enabled: false,
        },
      }]);
    }
    if (p.endsWith("/permissions/me/")) {
      return json({
        role: "manager",
        is_manager: true,
        ui_mode: "advanced",
        permissions: ["sales.settings.manage", "sales.invoice.view"],
      });
    }
    if (p.endsWith("/sales/settings/current/")) {
      if (req.method() === "PATCH") {
        const body = req.postDataJSON() as Record<string, unknown>;
        const has = (key: string) => Object.prototype.hasOwnProperty.call(body, key);
        // مرآة `int()` الذي يطبّقه الـlookup على الـpk: الرقم يُبتر، والنص يُقبل إن كان عدداً صحيحاً.
        const pythonInt = (value: unknown): number | null => {
          if (typeof value === "number") return Number.isFinite(value) ? Math.trunc(value) : null;
          if (typeof value === "string" && /^\s*[+-]?\d+\s*$/.test(value)) return Number(value);
          return null;
        };
        const pkOrNull = (value: unknown) => (value != null ? pythonInt(value) : null);
        // مرآة `PrimaryKeyRelatedField.to_internal_value`: null مقبول (`allow_null=True` لكل FK)،
        // وما لا يصير int (bool، كائن، نص غير رقمي) ← `incorrect_type` باسم نوعه في بايثون،
        // والـpk المجهول ← `does_not_exist`.
        const pkError = (value: unknown, knownIds: () => number[]): string | null => {
          if (value == null) return null;
          const pk = typeof value === "boolean" ? null : pythonInt(value);
          if (pk == null) {
            const dataType =
              typeof value === "boolean" ? "bool"
              : typeof value === "string" ? "str"
              : Array.isArray(value) ? "list"
              : "dict";
            return `نوع غير صحيح. يتوقع قيمة معرف العنصر، بينما حصل على ${dataType}.`;
          }
          if (!knownIds().includes(pk)) {
            return `معرف العنصر "${String(value)}" غير صالح -  العنصر غير موجود.`;
          }
          return null;
        };
        const accountIds = () => accounts.map((a) => a.id);
        const accountPkError = (value: unknown) => pkError(value, accountIds);
        // مرآة `ChoiceField` لحقلٍ بلا `allow_null` (`Field` `null`، ثم `invalid_choice`)،
        // ثم `validate_cogs_cost_method` لـavco.
        const cogsMethodError = (value: unknown): string | null => {
          if (value === null) return "لا يمكن لهذا الحقل ان يكون فارغاً null.";
          if (!COGS_METHOD_CHOICES.includes(String(value))) return `"${String(value)}" ليس خياراً صالحاً.`;
          if (value === "avco") return "طريقة المتوسط المرجّح غير متاحة بعد.";
          return null;
        };
        // مرحلة الحقول (`to_internal_value`) بترتيب `Meta.fields`: تُجمع أخطاء الحقول كلها ثم 400.
        const fieldChecks: Array<[string, (value: unknown) => string | null]> = [
          ["default_customer", (v) => pkError(v, () => STUB_PARTNERS.map((x) => x.id))],
          ["default_currency", (v) => pkError(v, () => STUB_CURRENCIES.map((x) => x.CurrencyID))],
          ["default_revenue_account_product", accountPkError],
          ["default_revenue_account_service", accountPkError],
          ["default_cash_account", accountPkError],
          ["default_inventory_account", accountPkError],
          ["default_cogs_account", accountPkError],
          ["cost_variance_account", accountPkError],
          ["cogs_cost_method", cogsMethodError],
          ["default_ar_account", accountPkError],
          ["default_vat_rate", (v) => pkError(v, () => STUB_TAX_RATES.map((x) => x.id))],
          ["vat_input_account", accountPkError],
        ];
        const fieldErrors: Record<string, string[]> = {};
        for (const [field, check] of fieldChecks) {
          if (!has(field)) continue;
          const err = check(body[field]);
          if (err) fieldErrors[field] = [err];
        }
        if (Object.keys(fieldErrors).length > 0) {
          return json(fieldErrors, 400);
        }
        // مرآة `SalesSettingsSerializer` (`_final_cogs_settings_values`, `_cogs_settings_changed`).
        const finalMethod = has("cogs_cost_method")
          ? String(body.cogs_cost_method)
          : saved.cogs_cost_method;
        const finalCogsId = has("default_cogs_account")
          ? pkOrNull(body.default_cogs_account)
          : saved.default_cogs_account;
        const finalVarianceId = has("cost_variance_account")
          ? pkOrNull(body.cost_variance_account)
          : saved.cost_variance_account;
        const cogsSettingsChanged =
          (has("cogs_cost_method") && body.cogs_cost_method !== saved.cogs_cost_method) ||
          (has("default_cogs_account") && finalCogsId !== saved.default_cogs_account) ||
          (has("cost_variance_account") && finalVarianceId !== saved.cost_variance_account);
        const cogsAcc =
          finalCogsId == null ? null : accounts.find((a) => a.id === finalCogsId) ?? null;
        const fixedMethod = finalMethod === "standard" || finalMethod === "last_purchase";
        let resolvedVarianceId = finalVarianceId;
        if (cogsSettingsChanged) {
          // مرآة `SalesSettingsSerializer.validate`.
          if (finalVarianceId != null) {
            const acc = accounts.find((a) => a.id === finalVarianceId);
            const err = acc ? costVarianceAccountError(acc, cogsAcc) : null;
            if (err) {
              return json({ cost_variance_account: [err] }, 400);
            }
          } else if (fixedMethod) {
            const { error } = inspectDefaultCostVarianceAccount(cogsAcc);
            if (error) {
              return json({ cost_variance_account: [error] }, 400);
            }
          }
          // مرآة `SalesSettingsSerializer.update` → `resolve_default_cost_variance_account`.
          if (fixedMethod && finalVarianceId == null && cogsAcc != null) {
            const { code, existing } = inspectDefaultCostVarianceAccount(cogsAcc);
            let resolved = existing;
            if (resolved == null && code != null) {
              resolved = {
                id: CREATED_VARIANCE_ACCOUNT_ID,
                code,
                name: "فروقات أسعار البضاعة المباعة",
                parent: cogsAcc.parent,
                account_type: "Expense",
                is_active: true,
                nature: null,
              };
              accounts.push(resolved);
            }
            resolvedVarianceId = resolved?.id ?? null;
          }
        }
        patchPayloads.push(body);
        const nextVarianceName =
          resolvedVarianceId == null
            ? null
            : accounts.find((a) => a.id === resolvedVarianceId)?.name ?? null;
        saved = {
          ...saved,
          ...body,
          cogs_cost_method: finalMethod,
          cost_variance_account: resolvedVarianceId,
          cost_variance_account_name: nextVarianceName,
          updated_at: "2026-11-20T10:05:00Z",
        };
        return json(saved);
      }
      return json(saved);
    }
    if (p.endsWith("/accounting/accounts/")) {
      return json(accounts);
    }
    if (p.endsWith("/accounting/currencies/")) {
      return json(STUB_CURRENCIES);
    }
    if (p.endsWith("/partners/lookup/")) {
      return json(STUB_PARTNERS);
    }
    if (p.endsWith("/accounting/tax-rates/")) {
      return json(STUB_TAX_RATES);
    }
    return json([]);
  });

  return { patchPayloads };
}

test("إعداد طريقة تكلفة المبيعات: جدول المثال، إخفاء avco، وتأكيد التغيير قبل الإرسال", async ({ page }) => {
  const { patchPayloads } = await installMocks(page);
  await page.goto("/sales/settings");

  const card = page.getByTestId("settings-card-cogs-cost-method");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await card.click();

  const section = page.locator('[data-settings-section="cogs-cost-method"]');
  await expect(section).toBeVisible();

  const select = section.locator("select").first();
  const optionValues = await select.locator("option").evaluateAll((opts) =>
    opts.map((o) => (o as HTMLOptionElement).value),
  );
  expect(optionValues).toEqual(["fifo", "standard", "last_purchase"]);

  const standardRow = section.getByTestId("cogs-example-table").locator('tr[data-method="standard"]');
  await expect(standardRow).toContainText("110");
  await expect(standardRow).toContainText("مدين 2");

  // تغيير الطريقة والضغط على حفظ يفتح حوار التأكيد؛ الإلغاء لا يرسل PATCH.
  await select.selectOption("standard");
  await expect(standardRow).toHaveAttribute("data-selected", "true");

  const saveBtn = page.getByRole("button", { name: "حفظ الإعدادات" });
  await saveBtn.click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("تغيير طريقة التكلفة");
  await dialog.getByRole("button", { name: "إلغاء" }).click();
  await expect(dialog).toBeHidden();
  await expect(saveBtn).toBeEnabled();
  await expect(select).toHaveValue("standard");
  expect(patchPayloads).toHaveLength(0);

  // التأكيد يرسل PATCH يحمل `cogs_cost_method`.
  await saveBtn.click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "تأكيد" }).click();
  await expect(page.getByText("تم حفظ الإعدادات بنجاح")).toBeVisible();

  expect(patchPayloads).toHaveLength(1);
  expect(patchPayloads[0].cogs_cost_method).toBe("standard");

  await page.getByRole("button", { name: "كل الإعدادات" }).click();
  await page.getByTestId("settings-card-journal-map").click();
  const varianceCell = page.getByTestId("journal-map-variance-account");
  await expect(varianceCell).toBeVisible();
  await expect(varianceCell).toContainText("فروقات أسعار البضاعة المباعة");
  await expect(varianceCell).not.toContainText("#5190");
});
