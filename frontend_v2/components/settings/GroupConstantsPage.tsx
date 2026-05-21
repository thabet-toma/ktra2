/**
 * N0-T4 — GroupConstantsPage (ثوابت المجموعة F11)
 *
 * صفحة Aseel-style بـ AseelDocumentShell. 4 tabs:
 *   1. بيانات عامة     — TenantSettings (company info, fiscal period)
 *   2. أرقام الدفاتر   — TenantBook (15 doc types × 10 books)
 *   3. حسابات افتراضية — SalesSettings.default_*_account
 *   4. ضرائب           — TenantSettings + SalesSettings rates/flags
 *
 * Reference: docs/aseel_reference/full/الأدوات.txt 10-200.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  AseelDocumentShell,
  AseelFormSection,
  AseelGrid,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../aseel";
import {
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { getSalesSettings, updateSalesSettings, type SalesSettings } from "../../services/salesApi";
import { Save, RefreshCw, Database } from "lucide-react";

/** ── Types ───────────────────────────────────────────────────────────── */

type TenantSettingsData = {
  id?: number;
  company_name_primary?: string | null;
  company_name_sub?: string | null;
  address?: string | null;
  po_box?: string | null;
  phone?: string | null;
  fax?: string | null;
  email?: string | null;
  licensed_dealer_no?: string | null;
  income_tax_file_no?: string | null;
  default_vat_rate?: string | null;
  default_source_discount_rate?: string | null;
  currency?: number | null;
  fiscal_period_label?: string | null;
  fiscal_period_start?: string | null;
  fiscal_period_end?: string | null;
  default_freight_credit_account?: number | null;
  mixture_auto_fill_enabled?: boolean;
  barcode_action?: string | null;
};

type TenantBookRow = {
  id: number;
  document_type: string;
  document_type_label?: string;
  book_number: number;
  name: string;
  last_used_number: number;
  is_active: boolean;
};

type CurrencyRow = { CurrencyID: number; Code: string; Name?: string | null };
type AccountRow = { id: number; code?: string | null; name?: string | null; account_type?: string | null };

const DOC_TYPE_LABELS: Record<string, string> = {
  sales_invoice: "فاتورة مبيعات",
  purchase_invoice: "فاتورة شراء",
  sales_return: "مرجع بيع",
  purchase_return: "مرجع شراء",
  receipt_voucher: "سند قبض",
  payment_voucher: "سند صرف",
  multi_receipt: "إيصال قبض متعدد",
  multi_payment: "سند صرف متعدد",
  credit_note: "إشعار دائن",
  debit_note: "إشعار مدين",
  quotation: "عرض سعر",
  journal_entry: "قيد محاسبة",
  deal: "صفقة",
  shipment: "شحنة",
  clearance: "تخليص جمركي",
};

/** ── Helper: labelled field ──────────────────────────────────────────── */

const fld = (label: string, node: React.ReactNode) => (
  <label className="aseel-field">
    <span className="aseel-field-label">{label}</span>
    {node}
  </label>
);

/** ── Component ───────────────────────────────────────────────────────── */

export const GroupConstantsPage: React.FC = () => {
  const tenantId = resolveTenantId();
  const [settings, setSettings] = useState<TenantSettingsData | null>(null);
  const [books, setBooks] = useState<TenantBookRow[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyRow[]>([]);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [salesSettings, setSalesSettings] = useState<SalesSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [localErr, setLocalErr] = useState<string | null>(null);

  /** Account helpers */
  const revenueAccounts = accounts.filter((a) => a.account_type === "Revenue");
  const assetAccounts = accounts.filter((a) => a.account_type === "Asset");
  const liabilityAccounts = accounts.filter((a) => a.account_type === "Liability");

  /** Load everything in parallel. Each call is fault-tolerant. */
  const loadData = useCallback(async () => {
    setLocalErr(null);
    setMsg(null);
    const [s, b, c, a, ss] = await Promise.allSettled([
      apiGetObject<TenantSettingsData>("tenants/settings/current/", { tenantId }),
      apiGetList<TenantBookRow>("tenants/books/", { tenantId }),
      apiGetList<CurrencyRow>("tenants/currencies/", { tenantId }),
      apiGetList<AccountRow>("accounting/accounts/", { tenantId }),
      getSalesSettings(),
    ]);

    if (s.status === "fulfilled") setSettings(s.value);
    else setSettings({} as TenantSettingsData);

    if (b.status === "fulfilled") setBooks(b.value);
    if (c.status === "fulfilled") setCurrencies(c.value);
    if (a.status === "fulfilled") setAccounts(a.value.filter((x) => x.id));
    if (ss.status === "fulfilled") setSalesSettings(ss.value);

    const errs = [s, b, c, a, ss].filter((r) => r.status === "rejected");
    if (errs.length === 5) setLocalErr("فشل تحميل بيانات الإعدادات.");
  }, [tenantId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  /** Seed the default 10 books per doc type if missing. */
  const seedBooks = async () => {
    if (seeding) return;
    setSeeding(true);
    setMsg(null);
    setLocalErr(null);
    try {
      const res = await apiPostObject<{ created: number; books: TenantBookRow[] }>(
        "tenants/books/seed/",
        {},
        { tenantId }
      );
      setBooks(res.books);
      setMsg(`تم إنشاء ${res.created} دفتر جديد.`);
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "فشل تهيئة الدفاتر.");
    } finally {
      setSeeding(false);
    }
  };

  /** Save Tab 1 + Tab 2 (TenantSettings + TenantBook changes). */
  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setLocalErr(null);
    setMsg(null);
    try {
      await apiPatchObject("tenants/settings/current/", settings, { tenantId });

      // Save each modified book (PATCH per row)
      await Promise.all(
        books.map((b) =>
          apiPatchObject(
            `tenants/books/${b.id}/`,
            {
              name: b.name,
              last_used_number: b.last_used_number,
              is_active: b.is_active,
            },
            { tenantId }
          )
        )
      );

      // Save SalesSettings changes (Tab 3 + Tab 4)
      if (salesSettings) {
        await updateSalesSettings({
          default_revenue_account_product: salesSettings.default_revenue_account_product,
          default_revenue_account_service: salesSettings.default_revenue_account_service,
          default_cash_account: salesSettings.default_cash_account,
          default_inventory_account: salesSettings.default_inventory_account,
          default_cogs_account: salesSettings.default_cogs_account,
          default_ar_account: salesSettings.default_ar_account,
          default_vat_rate: salesSettings.default_vat_rate,
          prices_include_tax: salesSettings.prices_include_tax,
        });
      }

      setMsg("تم حفظ ثوابت المجموعة بنجاح.");
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "فشل الحفظ.");
    } finally {
      setSaving(false);
    }
  };

  const upd = (key: keyof TenantSettingsData, value: any) => {
    setSettings((p) => (p ? { ...p, [key]: value } : p));
  };
  const updSales = (key: keyof SalesSettings, value: any) => {
    setSalesSettings((p) => (p ? ({ ...p, [key]: value } as SalesSettings) : p));
  };
  const updBook = (id: number, key: keyof TenantBookRow, value: any) => {
    setBooks((arr) => arr.map((b) => (b.id === id ? { ...b, [key]: value } : b)));
  };

  /** ── Tab 1: بيانات عامة ───────────────────────────────────────────── */
  const generalTab = (
    <AseelFormSection title="بيانات الشركة" cols={3}>
      {fld("الاسم الرئيسي", (
        <input className="aseel-input" value={settings?.company_name_primary || ""}
          onChange={(e) => upd("company_name_primary", e.target.value)} />
      ))}
      {fld("الاسم الفرعي", (
        <input className="aseel-input" value={settings?.company_name_sub || ""}
          onChange={(e) => upd("company_name_sub", e.target.value)} />
      ))}
      {fld("العنوان", (
        <input className="aseel-input" value={settings?.address || ""}
          onChange={(e) => upd("address", e.target.value)} />
      ))}
      {fld("ص.ب", (
        <input className="aseel-input" value={settings?.po_box || ""}
          onChange={(e) => upd("po_box", e.target.value)} />
      ))}
      {fld("الهاتف", (
        <input className="aseel-input" value={settings?.phone || ""}
          onChange={(e) => upd("phone", e.target.value)} />
      ))}
      {fld("الفاكس", (
        <input className="aseel-input" value={settings?.fax || ""}
          onChange={(e) => upd("fax", e.target.value)} />
      ))}
      {fld("البريد الإلكتروني", (
        <input className="aseel-input" type="email" value={settings?.email || ""}
          onChange={(e) => upd("email", e.target.value)} />
      ))}
      {fld("رقم المشتغل المرخص", (
        <input className="aseel-input" value={settings?.licensed_dealer_no || ""}
          onChange={(e) => upd("licensed_dealer_no", e.target.value)} />
      ))}
      {fld("رقم ملف ضريبة الدخل", (
        <input className="aseel-input" value={settings?.income_tax_file_no || ""}
          onChange={(e) => upd("income_tax_file_no", e.target.value)} />
      ))}
      {fld("العملة", (
        <select className="aseel-input" value={settings?.currency || ""}
          onChange={(e) => upd("currency", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {currencies.map((c) => (
            <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code} — {c.Name || ""}</option>
          ))}
        </select>
      ))}
      {fld("تسمية الفترة المالية", (
        <input className="aseel-input" value={settings?.fiscal_period_label || ""}
          onChange={(e) => upd("fiscal_period_label", e.target.value)} />
      ))}
      {fld("بداية الفترة", (
        <input className="aseel-input" type="date" value={settings?.fiscal_period_start || ""}
          onChange={(e) => upd("fiscal_period_start", e.target.value)} />
      ))}
      {fld("نهاية الفترة", (
        <input className="aseel-input" type="date" value={settings?.fiscal_period_end || ""}
          onChange={(e) => upd("fiscal_period_end", e.target.value)} />
      ))}
      {fld("إجراء الباركود", (
        <select className="aseel-input" value={settings?.barcode_action || "index"}
          onChange={(e) => upd("barcode_action", e.target.value)}>
          <option value="index">فتح فهرس الأصناف</option>
          <option value="cashier">فتح فاتورة كاشير</option>
        </select>
      ))}
      <label className="aseel-field aseel-field--inline" style={{ gridColumn: "1 / -1" }}>
        <input type="checkbox" checked={settings?.mixture_auto_fill_enabled || false}
          onChange={(e) => upd("mixture_auto_fill_enabled", e.target.checked)} />
        <span className="aseel-field-label" style={{ flex: "unset" }}>تعبئة تلقائية لرقم الخلطة/تاريخ الانتهاء</span>
      </label>
    </AseelFormSection>
  );

  /** ── Tab 2: أرقام الدفاتر ─────────────────────────────────────────── */
  const bookColumns: AseelGridColumn<TenantBookRow>[] = [
    {
      key: "document_type",
      header: "نوع المستند",
      width: "25%",
      readOnly: true,
      render: (r) => <span>{DOC_TYPE_LABELS[r.document_type] || r.document_type}</span>,
    },
    { key: "book_number", header: "رقم الدفتر", width: "80px", align: "center", readOnly: true },
    {
      key: "name",
      header: "اسم الدفتر",
      render: (r) => (
        <input
          className="aseel-input"
          value={r.name || ""}
          onChange={(e) => updBook(r.id, "name", e.target.value)}
        />
      ),
    },
    {
      key: "last_used_number",
      header: "آخر رقم مستخدم",
      width: "140px",
      align: "center",
      render: (r) => (
        <input
          className="aseel-input"
          type="number"
          value={r.last_used_number || 0}
          onChange={(e) => updBook(r.id, "last_used_number", Number(e.target.value) || 0)}
        />
      ),
    },
    {
      key: "is_active",
      header: "نشط",
      width: "70px",
      align: "center",
      render: (r) => (
        <input
          type="checkbox"
          checked={r.is_active}
          onChange={(e) => updBook(r.id, "is_active", e.target.checked)}
        />
      ),
    },
  ];

  const booksTab = (
    <div>
      {books.length === 0 && (
        <div className="aseel-banner aseel-banner--warn" style={{ marginBottom: 8 }}>
          <span>لا توجد دفاتر مهيَّأة بعد. اضغط «تهيئة الدفاتر» لإنشاء 10 دفاتر لكل نوع مستند.</span>
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={seedBooks}
            disabled={seeding}
            style={{ marginInlineStart: 12 }}
          >
            <Database className="h-4 w-4" />
            {seeding ? "...تهيئة" : "تهيئة الدفاتر"}
          </button>
        </div>
      )}
      {books.length > 0 && (
        <AseelGrid<TenantBookRow>
          columns={bookColumns}
          rows={books}
          getRowKey={(r) => r.id}
          getCell={(r, k) => (r as any)[k] ?? ""}
        />
      )}
    </div>
  );

  /** ── Tab 3: حسابات افتراضية ───────────────────────────────────────── */
  const accountsTab = (
    <AseelFormSection title="الحسابات المحاسبية الافتراضية" cols={2}>
      {fld("حساب الإيراد (منتج)", (
        <select className="aseel-input" value={salesSettings?.default_revenue_account_product || ""}
          onChange={(e) => updSales("default_revenue_account_product", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {revenueAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
        </select>
      ))}
      {fld("حساب الإيراد (خدمة)", (
        <select className="aseel-input" value={salesSettings?.default_revenue_account_service || ""}
          onChange={(e) => updSales("default_revenue_account_service", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {revenueAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
        </select>
      ))}
      {fld("حساب الصندوق الافتراضي", (
        <select className="aseel-input" value={salesSettings?.default_cash_account || ""}
          onChange={(e) => updSales("default_cash_account", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {assetAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
        </select>
      ))}
      {fld("حساب ذمم العملاء الافتراضي", (
        <select className="aseel-input" value={salesSettings?.default_ar_account || ""}
          onChange={(e) => updSales("default_ar_account", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {assetAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
        </select>
      ))}
      {fld("حساب المخزون", (
        <select className="aseel-input" value={salesSettings?.default_inventory_account || ""}
          onChange={(e) => updSales("default_inventory_account", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {assetAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
        </select>
      ))}
      {fld("حساب تكلفة المبيعات (COGS)", (
        <select className="aseel-input" value={salesSettings?.default_cogs_account || ""}
          onChange={(e) => updSales("default_cogs_account", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {accounts.filter((a) => a.account_type === "Expense").map((a) =>
            <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
        </select>
      ))}
      {fld("حساب أجرة الشحن (دائن)", (
        <select className="aseel-input" value={settings?.default_freight_credit_account || ""}
          onChange={(e) => upd("default_freight_credit_account", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {liabilityAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
        </select>
      ))}
    </AseelFormSection>
  );

  /** ── Tab 4: ضرائب ─────────────────────────────────────────────────── */
  const taxesTab = (
    <AseelFormSection title="إعدادات الضرائب" cols={2}>
      {fld("نسبة ض.ق.م الافتراضية (%)", (
        <input className="aseel-input" type="number" step="0.01"
          value={settings?.default_vat_rate ?? "16"}
          onChange={(e) => upd("default_vat_rate", e.target.value)} />
      ))}
      {fld("نسبة خصم المصدر الافتراضية (%)", (
        <input className="aseel-input" type="number" step="0.01"
          value={settings?.default_source_discount_rate ?? "0"}
          onChange={(e) => upd("default_source_discount_rate", e.target.value)} />
      ))}
      <label className="aseel-field aseel-field--inline" style={{ gridColumn: "1 / -1" }}>
        <input type="checkbox" checked={salesSettings?.prices_include_tax || false}
          onChange={(e) => updSales("prices_include_tax", e.target.checked)} />
        <span className="aseel-field-label" style={{ flex: "unset" }}>
          الأسعار المُدخَلة تَشمل قيمة الضريبة المضافة (افتراضياً)
        </span>
      </label>
      <p className="aseel-hint" style={{ gridColumn: "1 / -1" }}>
        تُستخدَم نسبة ض.ق.م الافتراضية عند إضافة فاتورة جديدة. يَجوز
        تجاوزها لكل فاتورة عبر حقل «الأسعار تشمل ض.ق.م» داخل الفاتورة.
      </p>
    </AseelFormSection>
  );

  /** ── Toolbar + banner ─────────────────────────────────────────────── */

  const toolbarActions: AseelToolbarAction[] = [
    {
      key: "save",
      label: saving ? "...حفظ" : "حفظ",
      icon: <Save />,
      onClick: !saving ? handleSave : undefined,
      disabled: saving,
    },
    {
      key: "reload",
      label: "تحديث",
      icon: <RefreshCw />,
      onClick: loadData,
      separatorBefore: true,
    },
  ];

  const banner = (localErr || msg) ? (
    <div className={`aseel-banner ${localErr ? "aseel-banner--err" : "aseel-banner--ok"}`}>
      <span>{localErr || msg}</span>
    </div>
  ) : null;

  return (
    <div
      dir="rtl"
      data-skin="aseel"
      style={{ height: "calc(100vh - 6rem)", display: "flex", flexDirection: "column" }}
    >
      <AseelDocumentShell
        title="ثوابت المجموعة"
        state="F11"
        actions={toolbarActions}
        header={<></>}
        tabs={[
          { key: "general", label: "بيانات عامة", content: generalTab },
          { key: "books", label: "أرقام الدفاتر", content: booksTab },
          { key: "accounts", label: "حسابات افتراضية", content: accountsTab },
          { key: "taxes", label: "ضرائب", content: taxesTab },
        ]}
        status={
          <>
            <span className="aseel-status-item">
              المستخدم <b>admin</b>
            </span>
            <span className="aseel-status-item">
              {books.length} دفتر · {accounts.length} حساب · {currencies.length} عملة
            </span>
          </>
        }
      >
        {banner}
      </AseelDocumentShell>
    </div>
  );
};
