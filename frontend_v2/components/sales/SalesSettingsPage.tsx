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
  type SalesSettings,
} from "../../services/salesApi";
import { apiGetList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { AseelDocumentShell, type AseelToolbarAction, type AseelTab } from "../aseel";

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
  <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 space-y-3">
    <div>
      <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
        {title}
      </h3>
      {description && (
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
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
    <span className="text-xs font-medium text-slate-600 dark:text-slate-300">
      {label}
    </span>
    <div className="mt-1">{children}</div>
  </label>
);

const input =
  "w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-2.5 py-1.5 text-sm text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/50";

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
      const [ss, accs, currs, parts, taxes] = await Promise.all([
        getSalesSettings(),
        apiGetList<AccountOpt>("accounting/accounts/", { tenantId }),
        apiGetList<CurrOpt>("accounting/currencies/", { tenantId }),
        apiGetList<PartnerRow>("partners/", { tenantId }),
        apiGetList<TaxRateRow>("accounting/tax-rates/", { tenantId }),
      ]);
      setSettings(ss);
      setAccounts(accs || []);
      setCurrencies(currs || []);
      setCustomers(
        (parts || []).filter(
          (p) => !p.partner_type || p.partner_type === "Customer"
        )
      );
      setTaxRates(taxes || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
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
        default_vat_rate: rest.default_vat_rate,
        prices_include_tax: rest.prices_include_tax,
        auto_post_invoices: rest.auto_post_invoices,
        show_journal_preview: rest.show_journal_preview,
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

  if (loading && !settings) {
    return (
      <div className="flex items-center justify-center p-10 text-slate-500">
        <Loader2 className="w-6 h-6 animate-spin me-2" /> تحميل الإعدادات...
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="p-6 text-red-600 dark:text-red-400">
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
        <div className="rounded bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 text-sm px-3 py-2">
          {msg}
        </div>
      )}
      {err && (
        <div className="rounded bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm px-3 py-2">
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
            <div className="text-[11px] text-slate-500 mt-1">
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
            <div className="text-[11px] text-slate-500 mt-1">
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
            <div className="text-[11px] text-slate-500 mt-1">
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
            <div className="text-[11px] text-slate-500 mt-1">
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

  const tabs: AseelTab[] = [
    { key: "settings", label: "الإعدادات", content: innerContent },
  ];

  return (
    <div data-skin="aseel" style={{ height: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="إعدادات فواتير المبيعات"
        state="حسابات افتراضية + ضرائب + شحن"
        actions={toolbarActions}
        header={<></>}
        tabs={tabs}
      />
    </div>
  );
};

export default SalesSettingsPage;
