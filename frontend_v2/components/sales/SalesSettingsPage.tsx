/**
 * N4-T3 — SalesSettingsPage (L9): Aseel shell wrap + إشارة لـ GroupConstantsPage
 * Ref: task5.md:681-683
 *
 * تَبقى الحسابات الافتراضية المتعلّقة بالمبيعات. الحقول العامة (طوابع رسوم...)
 * انتقلت إلى GroupConstantsPage (N0-T4).
 */
import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Save, Info } from "lucide-react";
import {
  getSalesSettings,
  updateSalesSettings,
  restoreSalesSettingsDefaults,
  type SalesSettings,
} from "../../services/salesApi";
import { apiGetList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { AseelDocumentShell, type AseelToolbarAction } from "../aseel";

type AccountOpt = {
  id: number;
  code?: string | null;
  name?: string | null;
  account_type?: string | null;
  is_active?: boolean;
};
type CurrOpt = { CurrencyID: number; Code: string; Name?: string };
type PartnerRow = { id: number; name: string; partner_type?: string };
type TaxRateRow = {
  id: number;
  code: string;
  name: string;
  rate: string | number;
  direction?: string;
};

const Section: React.FC<{
  title: string;
  description?: string;
  children: React.ReactNode;
}> = ({ title, description, children }) => (
  <div className="rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel p-5 space-y-3">
    <div>
      <h3 className="text-base font-semibold aseel-text-ink dark:aseel-text-soft">
        {title}
      </h3>
      {description && (
        <p className="text-xs aseel-text-soft dark:aseel-text-soft mt-1">
          {description}
        </p>
      )}
    </div>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{children}</div>
  </div>
);

const FieldLabel: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <label className="block">
    <span className="text-xs font-medium aseel-text-soft dark:aseel-text-soft">
      {label}
    </span>
    <div className="mt-1">{children}</div>
  </label>
);

const input =
  "w-full rounded-md border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel px-2.5 py-1.5 text-sm aseel-text-ink dark:aseel-text-soft focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/50";

export const SalesSettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<SalesSettings | null>(null);
  const [accounts, setAccounts] = useState<AccountOpt[]>([]);
  const [currencies, setCurrencies] = useState<CurrOpt[]>([]);
  const [customers, setCustomers] = useState<PartnerRow[]>([]);
  const [taxRates, setTaxRates] = useState<TaxRateRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const tenantId = resolveTenantId();
      const results = await Promise.allSettled([
        getSalesSettings(),
        apiGetList<AccountOpt>("accounting/accounts/", { tenantId }),
        apiGetList<CurrOpt>("accounting/currencies/", { tenantId }),
        apiGetList<PartnerRow>("partners/lookup/?limit=500", { tenantId }),
        apiGetList<TaxRateRow>("accounting/tax-rates/", { tenantId }),
      ]);

      const [ssRes, accsRes, currsRes, partsRes, taxesRes] = results;

      if (ssRes.status === "fulfilled" && ssRes.value) {
        setSettings(ssRes.value);
      } else {
        // Core settings object failed to load; the form gates on `settings`
        // being non-null and shows this error instead of white-screening.
        setErr((prev) => (prev ? prev + " | " : "") + "تعذر تحميل إعدادات المبيعات الأساسية");
      }

      setAccounts(accsRes.status === "fulfilled" ? (accsRes.value || []) : []);
      if (accsRes.status === "rejected") setErr((prev) => (prev ? prev + " | " : "") + "بعض الحسابات لم تُحمل");

      setCurrencies(currsRes.status === "fulfilled" ? (currsRes.value || []) : []);
      if (currsRes.status === "rejected") setErr((prev) => (prev ? prev + " | " : "") + "العملات لم تُحمل");

      const parts = partsRes.status === "fulfilled" ? (partsRes.value || []) : [];
      setCustomers(parts.filter((p) => !p.partner_type || p.partner_type === "Customer"));
      if (partsRes.status === "rejected") setErr((prev) => (prev ? prev + " | " : "") + "العملاء لم يتم تحميلهم");

      setTaxRates(taxesRes.status === "fulfilled" ? (taxesRes.value || []) : []);
      if (taxesRes.status === "rejected") setErr((prev) => (prev ? prev + " | " : "") + "الضرائب لم تُحمل");

    } catch (e: unknown) {
      setErr((prev) => (prev ? prev + " | " : "") + (e instanceof Error ? e.message : String(e)));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setField = <K extends keyof SalesSettings>(
    key: K,
    value: SalesSettings[K]
  ) => {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      const { id: _id, updated_at: _ua, ...rest } = settings;
      // نرسل الحقول القابلة للكتابة فقط (نتجاهل الحقول الـ read-only مثل *_name)
      const writable: Partial<SalesSettings> = {
        default_customer: rest.default_customer,
        default_currency: rest.default_currency,
        default_revenue_account_product: rest.default_revenue_account_product,
        default_revenue_account_service: rest.default_revenue_account_service,
        default_cash_account: rest.default_cash_account,
        default_inventory_account: rest.default_inventory_account,
        default_cogs_account: rest.default_cogs_account,
        default_ar_account: rest.default_ar_account,
        default_payment_type: rest.default_payment_type,
        stock_on_post_default: rest.stock_on_post_default,
        allow_negative_stock_default: rest.allow_negative_stock_default,
        default_vat_rate: rest.default_vat_rate,
        prices_include_tax: rest.prices_include_tax,
        auto_post_invoices: rest.auto_post_invoices,
        show_journal_preview: rest.show_journal_preview,
        warn_on_duplicate_item: rest.warn_on_duplicate_item,
        block_loss_invoices: rest.block_loss_invoices,
        default_shipping_origin: rest.default_shipping_origin,
        default_shipping_destination: rest.default_shipping_destination,
      };
      const updated = await updateSalesSettings(writable);
      setSettings(updated);
      setMsg("تم حفظ الإعدادات بنجاح");
      window.setTimeout(() => setMsg(null), 2500);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  // T-S3: استعادة خريطة القيد الافتراضية (الحسابات الافتراضية لكل نوع فاتورة).
  const handleRestoreDefaults = async () => {
    if (!window.confirm(
      "استعادة خريطة القيد الافتراضية؟ سيُعاد ضبط الحسابات الافتراضية (صندوق/ذمم/إيراد/مخزون/تكلفة) من شجرة الحسابات."
    )) return;
    setSaving(true); setMsg(null); setErr(null);
    try {
      const updated = await restoreSalesSettingsDefaults();
      setSettings(updated);
      setMsg("تمت استعادة خريطة القيد الافتراضية");
      window.setTimeout(() => setMsg(null), 2500);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  // اسم الحساب من القائمة المحمَّلة (لعرض خريطة القيد).
  const acctName = (id: number | null): string => {
    if (id == null) return "— غير محدد —";
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} ${a.name}` : `#${id}`;
  };

  if (loading && !settings) {
    return (
      <div className="flex items-center justify-center p-10 aseel-text-soft">
        <Loader2 className="w-6 h-6 animate-spin me-2" /> تحميل الإعدادات...
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="p-6 aseel-text-state dark:aseel-text-soft">
        تعذّر تحميل الإعدادات. {err}
      </div>
    );
  }

  const accountsActive = accounts.filter((a) => a.is_active !== false);
  const revenueAccounts = accountsActive.filter(
    (a) => (a.account_type || "").toLowerCase() === "revenue"
  );
  const cashAccounts = accountsActive.filter((a) => {
    const t = (a.account_type || "").toLowerCase();
    return t === "asset" || t === "cash" || t === "bank";
  });
  const liabilityAccounts = accountsActive.filter(
    (a) => (a.account_type || "").toLowerCase() === "liability"
  );
  const inventoryAccounts = accountsActive;
  const cogsAccounts = accountsActive.filter(
    (a) => (a.account_type || "").toLowerCase() === "expense"
  );

  const accountLabel = (a: AccountOpt) =>
    `${a.code ? a.code + " — " : ""}${a.name || ""}`;

  const toolbarActions: AseelToolbarAction[] = [
    {
      key: "save",
      label: saving ? "..." : "حفظ الإعدادات",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: handleSave,
      disabled: saving,
    },
  ];

  const innerContent = (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5" dir="rtl">
      <div className="aseel-banner" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px 12px", background: "var(--aseel-surface-2, #f4ede0)" }}>
        <Info className="w-4 h-4" style={{ color: "var(--aseel-ink-soft)" }} />
        <span style={{ fontSize: "12px" }}>
          الحقول العامة (طوابع رسوم، عملة أساسية، إلخ.) انتقلت إلى صفحة «ثوابت المجموعة».
          تَبقى هنا الحسابات الافتراضية الخاصة بفواتير المبيعات فقط.
        </span>
      </div>

      {msg && (
        // task16 D12: تأكيد «حُفظ بنجاح» واضح (بنر نجاح أخضر + علامة)
        <div className="aseel-banner aseel-banner--ok" role="status" aria-live="polite">
          <Info className="h-4 w-4 shrink-0" />
          <span>{msg}</span>
        </div>
      )}
      {err && (
        <div className="rounded aseel-bg-panel aseel-text-state dark:aseel-bg-panel/30 dark:aseel-text-soft text-sm px-3 py-2">
          {err}
        </div>
      )}

      <Section
        title="العميل الافتراضي"
        description="الزبون العام / الكاش المستخدم تلقائيًا عند إنشاء فاتورة جديدة"
      >
        <FieldLabel label="العميل الافتراضي">
          <select
            className={input}
            value={settings.default_customer ?? ""}
            onChange={(e) =>
              setField(
                "default_customer",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {settings.default_customer_name && (
            <div className="text-[11px] aseel-text-soft mt-1">
              الحالي: {settings.default_customer_name}
            </div>
          )}
        </FieldLabel>
      </Section>

      <Section title="العملات والدفع">
        <FieldLabel label="العملة الافتراضية">
          <select
            className={input}
            value={settings.default_currency ?? ""}
            onChange={(e) =>
              setField(
                "default_currency",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {currencies.map((c) => (
              <option key={c.CurrencyID} value={c.CurrencyID}>
                {c.Code} {c.Name ? `— ${c.Name}` : ""}
              </option>
            ))}
          </select>
          {settings.default_currency_code && (
            <div className="text-[11px] aseel-text-soft mt-1">
              الحالي: {settings.default_currency_code}
            </div>
          )}
        </FieldLabel>

        <FieldLabel label="نوع الدفع الافتراضي">
          <select
            className={input}
            value={settings.default_payment_type}
            onChange={(e) =>
              setField(
                "default_payment_type",
                e.target.value as "cash" | "credit"
              )
            }
          >
            <option value="credit">آجل</option>
            <option value="cash">نقدي</option>
          </select>
        </FieldLabel>

        <FieldLabel label="حساب الصندوق الافتراضي (للنقدي)">
          <select
            className={input}
            value={settings.default_cash_account ?? ""}
            onChange={(e) =>
              setField(
                "default_cash_account",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {cashAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a)}
              </option>
            ))}
          </select>
        </FieldLabel>

        <FieldLabel label="حساب ذمم (AR) افتراضي">
          <select
            className={input}
            value={settings.default_ar_account ?? ""}
            onChange={(e) =>
              setField(
                "default_ar_account",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {accountsActive.map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a)}
              </option>
            ))}
          </select>
        </FieldLabel>
      </Section>

      <Section
        title="حسابات الإيرادات"
        description="تُستخدم عند ترحيل الفاتورة حسب نوع الصنف (منتج/خدمة)"
      >
        <FieldLabel label="حساب إيراد بيع البضائع (منتج)">
          <select
            className={input}
            value={settings.default_revenue_account_product ?? ""}
            onChange={(e) =>
              setField(
                "default_revenue_account_product",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {revenueAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a)}
              </option>
            ))}
          </select>
          {settings.default_revenue_account_product_name && (
            <div className="text-[11px] aseel-text-soft mt-1">
              الحالي: {settings.default_revenue_account_product_name}
            </div>
          )}
        </FieldLabel>

        <FieldLabel label="حساب إيراد الخدمات">
          <select
            className={input}
            value={settings.default_revenue_account_service ?? ""}
            onChange={(e) =>
              setField(
                "default_revenue_account_service",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {revenueAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a)}
              </option>
            ))}
          </select>
          {settings.default_revenue_account_service_name && (
            <div className="text-[11px] aseel-text-soft mt-1">
              الحالي: {settings.default_revenue_account_service_name}
            </div>
          )}
        </FieldLabel>
      </Section>

      <Section
        title="المخزون وتكلفة المبيعات"
        description="حسابات افتراضية تُستخدم عند عدم تحديدها على فئة المنتج"
      >
        <FieldLabel label="حساب مخزون افتراضي">
          <select
            className={input}
            value={settings.default_inventory_account ?? ""}
            onChange={(e) =>
              setField(
                "default_inventory_account",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {inventoryAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a)}
              </option>
            ))}
          </select>
        </FieldLabel>

        <FieldLabel label="حساب تكلفة مبيعات (COGS) افتراضي">
          <select
            className={input}
            value={settings.default_cogs_account ?? ""}
            onChange={(e) =>
              setField(
                "default_cogs_account",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— اختر —</option>
            {cogsAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a)}
              </option>
            ))}
          </select>
        </FieldLabel>

        <FieldLabel label="خصم المخزون عند الترحيل (افتراضيًا)">
          <select
            className={input}
            value={settings.stock_on_post_default ? "yes" : "no"}
            onChange={(e) =>
              setField("stock_on_post_default", e.target.value === "yes")
            }
          >
            <option value="yes">خصم المخزون عند الترحيل</option>
            <option value="no">عدم خصم المخزون عند الترحيل</option>
          </select>
        </FieldLabel>

        <FieldLabel label="سياسة الرصيد السالب (افتراضيًا)">
          <select
            className={input}
            value={settings.allow_negative_stock_default ? "yes" : "no"}
            onChange={(e) =>
              setField("allow_negative_stock_default", e.target.value === "yes")
            }
          >
            <option value="yes">السماح ببيع المخزون بالسالب (تحذير فقط)</option>
            <option value="no">منع البيع إذا تجاوز الكمية المتوفرة</option>
          </select>
        </FieldLabel>
      </Section>

      <Section title="الضرائب">
        <FieldLabel label="نسبة ضريبة القيمة المضافة الافتراضية">
          <select
            className={input}
            value={settings.default_vat_rate ?? ""}
            onChange={(e) =>
              setField(
                "default_vat_rate",
                e.target.value ? Number(e.target.value) : null
              )
            }
          >
            <option value="">— بدون —</option>
            {taxRates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.code} — {t.name} ({t.rate}%)
              </option>
            ))}
          </select>
        </FieldLabel>

        <FieldLabel label="الأسعار شاملة الضريبة؟">
          <select
            className={input}
            value={settings.prices_include_tax ? "yes" : "no"}
            onChange={(e) =>
              setField("prices_include_tax", e.target.value === "yes")
            }
          >
            <option value="no">لا — تُضاف الضريبة فوق السعر</option>
            <option value="yes">نعم — السعر يشمل الضريبة</option>
          </select>
        </FieldLabel>
      </Section>

      <Section title="سلوك الترحيل والمعاينة">
        <FieldLabel label="ترحيل تلقائي بعد الحفظ">
          <select
            className={input}
            value={settings.auto_post_invoices ? "yes" : "no"}
            onChange={(e) =>
              setField("auto_post_invoices", e.target.value === "yes")
            }
          >
            <option value="no">حفظ فقط بدون ترحيل</option>
            <option value="yes">ترحيل تلقائي بعد الحفظ</option>
          </select>
        </FieldLabel>

        <FieldLabel label="إظهار معاينة القيد قبل الترحيل">
          <select
            className={input}
            value={settings.show_journal_preview ? "yes" : "no"}
            onChange={(e) =>
              setField("show_journal_preview", e.target.value === "yes")
            }
          >
            <option value="yes">إظهار معاينة القيد</option>
            <option value="no">إخفاء معاينة القيد</option>
          </select>
        </FieldLabel>
      </Section>

      {/* T-S2: إعدادات عامة (سلوك) — مودلة على إعدادات التطبيق المكتبي (صورة 7). */}
      <Section
        title="إعدادات عامة (السلوك)"
        description="سلوكيات عامة لمحرّر الفاتورة. تُربط بسلوك حقيقي في الشاشة."
      >
        <FieldLabel label="عند تكرار المادة في الفاتورة">
          <select
            className={input}
            value={settings.warn_on_duplicate_item ? "yes" : "no"}
            onChange={(e) => setField("warn_on_duplicate_item", e.target.value === "yes")}
          >
            <option value="yes">إظهار رسالة تنبيه وتأكيد (مُوصى)</option>
            <option value="no">إضافة سطر جديد مباشرة بلا تنبيه</option>
          </select>
        </FieldLabel>
        <FieldLabel label="فاتورة البيع بخسارة (سعر أقل من التكلفة)">
          <select
            className={input}
            value={settings.block_loss_invoices ? "yes" : "no"}
            onChange={(e) => setField("block_loss_invoices", e.target.value === "yes")}
          >
            <option value="no">السماح بالحفظ (افتراضي)</option>
            <option value="yes">منع الحفظ والترحيل</option>
          </select>
        </FieldLabel>
      </Section>

      {/* T-S3: خريطة القيد المحاسبي لكل نوع فاتورة (صورة 6) + استعادة الافتراضي. */}
      <Section
        title="خريطة القيد المحاسبي (الحسابات الافتراضية لكل نوع)"
        description="الحسابات التي يُرحَّل إليها كل نوع فاتورة. تُعدَّل من حقول الحسابات أعلاه."
      >
        <div className="md:col-span-2 overflow-x-auto">
          <table className="w-full text-sm aseel-grid" data-variant="list">
            <thead>
              <tr>
                <th className="text-right p-2">نوع الفاتورة / الحركة</th>
                <th className="text-right p-2">مدين</th>
                <th className="text-right p-2">دائن</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="p-2">بيع نقدي</td>
                <td className="p-2">{acctName(settings.default_cash_account)}</td>
                <td className="p-2">{acctName(settings.default_revenue_account_product)} <span className="aseel-text-soft">+ ض.ق.م مخرجات</span></td>
              </tr>
              <tr>
                <td className="p-2">بيع آجل (ذمم)</td>
                <td className="p-2">ذمم العميل <span className="aseel-text-soft">(حساب العميل المرتبط، أو الافتراضي: {acctName(settings.default_ar_account)})</span></td>
                <td className="p-2">{acctName(settings.default_revenue_account_product)} <span className="aseel-text-soft">+ ض.ق.م مخرجات</span></td>
              </tr>
              <tr>
                <td className="p-2">بيع خدمات</td>
                <td className="p-2">الصندوق / ذمم العميل</td>
                <td className="p-2">{acctName(settings.default_revenue_account_service)}</td>
              </tr>
              <tr>
                <td className="p-2">تكلفة المبيعات (عند خصم المخزون)</td>
                <td className="p-2">{acctName(settings.default_cogs_account)}</td>
                <td className="p-2">{acctName(settings.default_inventory_account)}</td>
              </tr>
            </tbody>
          </table>
          <button
            type="button"
            onClick={handleRestoreDefaults}
            disabled={saving}
            className="mt-3 text-sm px-3 py-1.5 rounded-lg border aseel-border-soft hover:aseel-bg-panel disabled:opacity-40"
          >
            استعادة خريطة القيد الافتراضية
          </button>
        </div>
      </Section>

      <Section
        title="الشحن المحلي"
        description="القيم الافتراضية لواجهة الشحن (From / To)"
      >
        <FieldLabel label="الجهة (From)">
          <input
            className={input}
            value={settings.default_shipping_origin || ""}
            onChange={(e) => setField("default_shipping_origin", e.target.value)}
          />
        </FieldLabel>

        <FieldLabel label="إلى (To)">
          <input
            className={input}
            value={settings.default_shipping_destination || ""}
            onChange={(e) =>
              setField("default_shipping_destination", e.target.value)
            }
          />
        </FieldLabel>
      </Section>
    </div>
  );

  // task11 M6: المحتوى في منطقة gridwrap الرئيسية المرنة — كان محشوراً في
  // tab سفلي بارتفاع أقصى 220px تاركاً فراغاً أبيض ضخماً وسط الشاشة.
  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="إعدادات فواتير المبيعات"
        state="حسابات افتراضية + ضرائب + شحن"
        actions={toolbarActions}
        header={<></>}
      >
        {innerContent}
      </AseelDocumentShell>
    </div>
  );
};

export default SalesSettingsPage;
