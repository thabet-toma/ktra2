/**
 * كرت الصنف الموحّد — الجزء القرائي (نظرة عامة + الفواتير المرتبطة + حركة المخزون).
 *
 * كان هذا المحتوى حبيس `ProductProfilePage` بينما التحرير حبيس `ItemFormAseel`،
 * فصار للصنف كرتان: واحد يُرى وآخر يُعدَّل. استُخرج هنا ليركّبه نموذج الكرت نفسه
 * (`ItemFormAseel`) كتبويبات، وتستهلك بطاقةُ المودال المختصرة نفسَ النظرة العامة —
 * مصدر واحد لكل عرض للصنف. يقرأ `inventory/products/{id}/profile|stock-ledger|invoices`.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiGetObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import type { AseelTab } from "../aseel";
import { LedgerTable, DocRefCell, type LedgerColumn } from "../shared/LedgerTable";
import { formatQuantity, formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";

export interface ProductProfileData {
  id: number;
  sku: string;
  name: string;
  brand?: string | null;
  uom?: string | null;
  barcode?: string | null;
  is_service?: boolean;
  min_stock_level?: number | null;
  category: string | null;
  quantity_on_hand: string;
  reserved_quantity?: string;
  available_quantity?: string;
  avg_cost: string;
  inventory_valuation: string;
  purchased_qty: string;
  purchased_value: string;
  sold_qty: string;
  sold_value: string;
  avg_weekly_sales?: string;
  avg_monthly_sales?: string;
  /** كرت الصنف: التسعير والربحية — كلها مشتقّة خادمياً (لا حساب في الواجهة). */
  sale_price?: string | null;
  last_sale_price?: string | null;
  last_sale_invoice?: string | null;
  last_sale_date?: string | null;
  last_purchase_price?: string | null;
  effective_sale_price?: string | null;
  sale_price_source?: "product" | "last_invoice" | null;
  profit_per_unit?: string | null;
  profit_margin_pct?: string | null;
  sale_valuation?: string | null;
}

export interface LedgerRow {
  id: number;
  date: string | null;
  movement_type_label: string;
  reference_type: string | null;
  reference_id: number | null;
  party: string | null;
  warehouse: string | null;
  qty_in: string;
  qty_out: string;
  running_balance: string;
}

export interface InvoiceRow {
  document_type: string;
  document_id: number;
  document_number: string;
  date: string | null;
  party: string | null;
  is_posted: boolean;
}

/** نوع الحركة المعروض: مشتريات/مبيعات مشتقّة من نوع المستند المرجعي. */
export const ledgerTypeLabel = (r: LedgerRow): string => {
  if (r.reference_type === "PURCHASE_INVOICE") return "مشتريات";
  if (r.reference_type === "SALE") return "مبيعات";
  return r.movement_type_label;
};

const PAGE = 50;

/** بطاقة مؤشّر واحدة — نفس الشكل في كل أقسام النظرة العامة والمودال. */
export const Kpi: React.FC<{
  label: string; value: React.ReactNode; hint?: string; tone?: "ok" | "warn" | "danger";
}> = ({ label, value, hint, tone }) => {
  const color =
    tone === "danger" ? "var(--aseel-danger,#c00)"
    : tone === "warn" ? "var(--aseel-warn,#b8800a)"
    : tone === "ok" ? "var(--aseel-ok,#267346)"
    : "var(--aseel-ink)";
  return (
    <div className="p-2 border border-[var(--aseel-border)] rounded" title={hint}>
      <div className="text-xs text-[var(--aseel-ink-soft)]">{label}</div>
      <div className="text-base font-bold" style={{ color }}>{value}</div>
    </div>
  );
};

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="mb-3">
    <div className="text-xs font-bold text-[var(--aseel-ink-soft)] mb-1.5 pr-0.5">{title}</div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">{children}</div>
  </section>
);

/**
 * ترتيب المصادر في مستند البيع: آخر سعر باعه هذا الزبون ← عرض سعره ← السعر العام
 * في كرت الصنف. فالسعر العام لا يظهر للزبون إلا حين لا عرض له ولا شراء سابق.
 */
const SALE_SOURCE_LABEL: Record<"product" | "last_invoice", string> = {
  product: "سعر عام يدوي — يُقترح للزبون الذي لا عرض له ولا شراء سابق",
  last_invoice: "لا سعر عام محفوظ — هذا آخر سعر بيع فعلي",
};

/**
 * النظرة العامة: التسعير والربحية أولاً (سعر البيع مقابل التكلفة كما في كرت الأصيل)،
 * ثم المخزون، ثم حركة الشراء/البيع، ثم بيانات التعريف.
 */
export const ProductOverview: React.FC<{ profile: ProductProfileData | null; loading?: boolean }> = ({ profile, loading }) => {
  if (!profile) {
    return (
      <div className="p-4 text-center text-[var(--aseel-ink-soft)]">
        {loading ? "جاري التحميل…" : "لا توجد بيانات لهذا الصنف بعد."}
      </div>
    );
  }
  const qty = Number(profile.quantity_on_hand);
  const minLevel = profile.min_stock_level;
  const profit = profile.profit_per_unit != null ? Number(profile.profit_per_unit) : null;
  const source = profile.sale_price_source;
  return (
    <div className="p-3">
      <Section title="التسعير والربحية">
        <Kpi
          label="سعر البيع العام"
          value={formatMoney(profile.effective_sale_price ?? "", "—")}
          hint={source ? SALE_SOURCE_LABEL[source] : "لا سعر بيع محفوظ ولا فاتورة بيع سابقة"}
          tone={source === "product" ? "ok" : undefined}
        />
        <Kpi label="سعر التكلفة (متوسط)" value={formatMoney(profile.avg_cost, "—")}
          hint="المتوسط المرجّح لمشتريات الصنف المرحّلة" />
        <Kpi
          label="الربح للوحدة"
          value={formatMoney(profile.profit_per_unit ?? "", "—")}
          hint="سعر البيع − سعر التكلفة"
          tone={profit == null ? undefined : profit < 0 ? "danger" : "ok"}
        />
        <Kpi
          label="هامش الربح"
          value={profile.profit_margin_pct != null ? `${formatMoney(profile.profit_margin_pct)}%` : "—"}
          hint="الربح ÷ سعر البيع"
          tone={profit == null ? undefined : profit < 0 ? "danger" : undefined}
        />
        <Kpi label="آخر سعر بيع" value={formatMoney(profile.last_sale_price ?? "", "—")}
          hint={profile.last_sale_invoice
            ? `فاتورة ${profile.last_sale_invoice} · ${formatDateLocalized(profile.last_sale_date) || ""}`
            : "لا فاتورة بيع مرحّلة لهذا الصنف"} />
        <Kpi label="آخر سعر شراء" value={formatMoney(profile.last_purchase_price ?? "", "—")}
          hint="من آخر فاتورة شراء مرحّلة (لا من متوسط التكلفة)" />
        <Kpi label="القيمة البيعية للمخزون" value={formatMoney(profile.sale_valuation ?? "", "—")}
          hint="الرصيد × سعر البيع" />
        <Kpi label="تقييم المخزون (بالتكلفة)" value={formatMoney(profile.inventory_valuation, "—")} />
      </Section>

      <Section title="المخزون">
        <Kpi label="الرصيد الحالي" value={formatQuantity(profile.quantity_on_hand, "—")}
          tone={qty <= 0 ? "danger" : minLevel != null && qty <= minLevel ? "warn" : undefined} />
        <Kpi label="محجوز لطلبيات" value={formatQuantity(profile.reserved_quantity ?? 0, "—")}
          hint="طلبيات زبائن مؤكَّدة سارية" />
        <Kpi label="المتاح للبيع" value={formatQuantity(profile.available_quantity ?? profile.quantity_on_hand, "—")}
          hint="الرصيد − المحجوز" />
        <Kpi label="الحد الأدنى" value={minLevel != null ? formatQuantity(minLevel) : "—"} />
      </Section>

      <Section title="حركة الشراء والبيع">
        <Kpi label="إجمالي المشتراة (كمية)" value={formatQuantity(profile.purchased_qty, "—")} />
        <Kpi label="إجمالي المشتراة (قيمة)" value={formatMoney(profile.purchased_value, "—")} />
        <Kpi label="إجمالي المباعة (كمية)" value={formatQuantity(profile.sold_qty, "—")} />
        <Kpi label="إجمالي المباعة (قيمة)" value={formatMoney(profile.sold_value, "—")} />
        <Kpi label="متوسط البيع الأسبوعي" value={formatQuantity(profile.avg_weekly_sales ?? "", "—")}
          hint="صافي البيع خلال 28 يوماً ÷ 4" />
        <Kpi label="متوسط البيع الشهري" value={formatQuantity(profile.avg_monthly_sales ?? "", "—")}
          hint="صافي البيع خلال 90 يوماً ÷ 3" />
      </Section>

      <Section title="التعريف">
        <Kpi label="رقم الصنف (SKU)" value={profile.sku || "—"} />
        <Kpi label="الباركود" value={profile.barcode || "—"} />
        <Kpi label="البراند" value={profile.brand || "—"} />
        <Kpi label="التصنيف" value={profile.category || "—"} />
        <Kpi label="الوحدة" value={profile.uom || "—"} />
        <Kpi label="نوع الصنف" value={profile.is_service ? "خدمة" : "بضاعة"} />
      </Section>
    </div>
  );
};

/** أعمدة دفتر حركة المخزون — مشتركة بين تبويب الكرت وبطاقة المودال. */
export const ledgerColumns = (opts: { withParty?: boolean; withWarehouse?: boolean } = {}): LedgerColumn<LedgerRow>[] => [
  { key: "date", header: "التاريخ", render: (r) => formatDateLocalized(r.date) || "—" },
  { key: "movement_type_label", header: "النوع", render: (r) => ledgerTypeLabel(r) },
  ...(opts.withParty ? [{ key: "party", header: "الطرف", render: (r: LedgerRow) => r.party || "—" }] : []),
  {
    key: "reference",
    header: "المستند",
    render: (r) => (
      <DocRefCell
        referenceType={r.reference_type}
        referenceId={r.reference_id}
        label={r.reference_id != null ? `${r.reference_type || ""} #${r.reference_id}` : "—"}
      />
    ),
  },
  ...(opts.withWarehouse ? [{ key: "warehouse", header: "المستودع", render: (r: LedgerRow) => r.warehouse || "—" }] : []),
  { key: "qty_in", header: "وارد", align: "center" as const, render: (r) => (Number(r.qty_in) ? formatQuantity(r.qty_in) : "—") },
  { key: "qty_out", header: "صادر", align: "center" as const, render: (r) => (Number(r.qty_out) ? formatQuantity(r.qty_out) : "—") },
  { key: "running_balance", header: "الرصيد", align: "center" as const, render: (r) => <b>{formatQuantity(r.running_balance)}</b> },
];

const invoiceColumns: LedgerColumn<InvoiceRow>[] = [
  {
    key: "document_number",
    header: "رقم الفاتورة",
    render: (r) => (
      <DocRefCell referenceType={r.document_type} referenceId={r.document_id} label={r.document_number} />
    ),
  },
  { key: "document_type", header: "النوع", render: (r) => (r.document_type === "SALES_INVOICE" ? "بيع" : "شراء") },
  { key: "party", header: "الطرف", render: (r) => r.party || "—" },
  { key: "date", header: "التاريخ", render: (r) => formatDateLocalized(r.date) || "—" },
  { key: "is_posted", header: "الحالة", align: "center", render: (r) => (r.is_posted ? "مرحّلة" : "مسودة") },
];

/**
 * يجلب بيانات الكرت القرائية لصنف محفوظ (`productId=null` عند صنف جديد → بلا نداءات)
 * ويبني التبويبات الثلاثة جاهزة للتركيب في `AseelDocumentShell`.
 */
export const useProductInsights = (productId: number | null) => {
  const tenantId = useMemo(() => resolveTenantId(), []);
  const [profile, setProfile] = useState<ProductProfileData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [ledger, setLedger] = useState<{ rows: LedgerRow[]; count: number }>({ rows: [], count: 0 });
  const [ledOffset, setLedOffset] = useState(0);
  const [ledLoading, setLedLoading] = useState(false);
  const [ledError, setLedError] = useState<string | null>(null);

  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);

  const loadProfile = useCallback(() => {
    if (productId == null) { setProfile(null); return; }
    setLoading(true);
    apiGetObject<ProductProfileData>(`inventory/products/${productId}/profile/`, { tenantId })
      .then((p) => { setProfile(p); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [productId, tenantId]);

  useEffect(() => { setLedOffset(0); loadProfile(); }, [loadProfile]);

  useEffect(() => {
    if (productId == null) { setLedger({ rows: [], count: 0 }); return; }
    setLedLoading(true);
    setLedError(null);
    apiGetObject<{ results: LedgerRow[]; count: number }>(
      `inventory/products/${productId}/stock-ledger/?limit=${PAGE}&offset=${ledOffset}`,
      { tenantId },
    )
      .then((d) => setLedger({ rows: d.results, count: d.count }))
      .catch((err) => setLedError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLedLoading(false));
  }, [productId, tenantId, ledOffset]);

  useEffect(() => {
    if (productId == null) { setInvoices([]); return; }
    setInvLoading(true);
    setInvError(null);
    apiGetObject<InvoiceRow[]>(`inventory/products/${productId}/invoices/`, { tenantId })
      .then((d) => setInvoices(Array.isArray(d) ? d : []))
      .catch((err) => {
        // ميّز فشل التحميل عن «لا توجد فواتير» — لا تُظهر الفراغ كأنه نتيجة سليمة.
        setInvError(err instanceof Error ? err.message : String(err));
        setInvoices([]);
      })
      .finally(() => setInvLoading(false));
  }, [productId, tenantId]);

  const emptyHint = "احفظ الصنف أولاً لتظهر بياناته هنا.";

  const tabs: AseelTab[] = [
    {
      key: "overview",
      label: "نظرة عامة",
      content: productId == null
        ? <div className="p-4 text-[var(--aseel-ink-soft)]">{emptyHint}</div>
        : error
          ? <div role="alert" className="p-3 text-sm text-[var(--aseel-danger,#c00)]">تعذّر تحميل النظرة العامة: {error}</div>
          : <ProductOverview profile={profile} loading={loading} />,
    },
    {
      key: "invoices",
      label: "الفواتير المرتبطة",
      content: productId == null
        ? <div className="p-4 text-[var(--aseel-ink-soft)]">{emptyHint}</div>
        : (
          <div className="p-2">
            <LedgerTable<InvoiceRow>
              columns={invoiceColumns}
              rows={invoices}
              loading={invLoading}
              error={invError}
              emptyText="لا توجد فواتير تحتوي هذا الصنف."
            />
          </div>
        ),
    },
    {
      key: "ledger",
      label: "حركة المخزون",
      content: productId == null
        ? <div className="p-4 text-[var(--aseel-ink-soft)]">{emptyHint}</div>
        : (
          <div className="p-2">
            <LedgerTable<LedgerRow>
              columns={ledgerColumns({ withParty: true, withWarehouse: true })}
              rows={ledger.rows}
              loading={ledLoading}
              error={ledError}
              count={ledger.count}
              limit={PAGE}
              offset={ledOffset}
              onPage={setLedOffset}
              emptyText="لا توجد حركات مخزون لهذا الصنف."
            />
          </div>
        ),
    },
  ];

  return { profile, loading, error, reload: loadProfile, tabs };
};
