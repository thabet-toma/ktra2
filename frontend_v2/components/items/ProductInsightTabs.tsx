/**
 * كرت المنتج الموحّد — الجزء القرائي (نظرة عامة + الفواتير المرتبطة + حركة المخزون).
 *
 * كان هذا المحتوى حبيس `ProductProfilePage` بينما التحرير حبيس `ItemForm`،
 * فصار للمنتج كرتان: واحد يُرى وآخر يُعدَّل. استُخرج هنا ليركّبه نموذج الكرت نفسه
 * (`ItemForm`) كتبويبات، وتستهلك بطاقةُ المودال المختصرة نفسَ النظرة العامة —
 * مصدر واحد لكل عرض للمنتج. يقرأ `inventory/products/{id}/profile|stock-ledger|invoices`.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiGetObject } from "../../services/restApi";
import { inventoryApi, type ProductGroupSelector, type ProductSerialRow } from "../../services/inventoryApi";
import { resolveTenantId } from "../../utils/tenantContext";
import type { KitTab } from "../kit";
import { LedgerTable, DocRefCell, type LedgerColumn } from "../shared/LedgerTable";
import SerialEntryModal from "../shared/SerialEntryModal";
import { formatQuantity, formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { openInNewTab } from "../../utils/openInNewTab";
import { productProfilePath } from "../../utils/entityLinks";

export interface ProductProfileData {
  id: number;
  sku: string;
  name: string;
  /** #21: معرّف «المنتج» (الأب) — وجوده شرط عرض «أضف براند» من كرت المنتج. */
  family_id?: number | null;
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
  /** كرت المنتج: التسعير والربحية — كلها مشتقّة خادمياً (لا حساب في الواجهة). */
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
    tone === "danger" ? "var(--ktra-danger,#c00)"
    : tone === "warn" ? "var(--ktra-warn,#b8800a)"
    : tone === "ok" ? "var(--ktra-ok,#267346)"
    : "var(--ktra-ink)";
  return (
    <div className="p-2 border border-[var(--ktra-border)] rounded" title={hint}>
      <div className="text-xs text-[var(--ktra-ink-soft)]">{label}</div>
      <div className="text-base font-bold" style={{ color }}>{value}</div>
    </div>
  );
};

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="mb-3">
    <div className="text-xs font-bold text-[var(--ktra-ink-soft)] mb-1.5 pr-0.5">{title}</div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">{children}</div>
  </section>
);

/**
 * ترتيب المصادر في مستند البيع: آخر سعر باعه هذا الزبون ← عرض سعره ← السعر العام
 * في كرت المنتج. فالسعر العام لا يظهر للزبون إلا حين لا عرض له ولا شراء سابق.
 */
const SALE_SOURCE_LABEL: Record<"product" | "last_invoice", string> = {
  product: "سعر عام يدوي — يُقترح للزبون الذي لا عرض له ولا شراء سابق",
  last_invoice: "لا سعر عام محفوظ — هذا آخر سعر بيع فعلي",
};

/**
 * النظرة العامة: التسعير والربحية أولاً (سعر البيع مقابل التكلفة كما في كرت الأصيل)،
 * ثم المخزون، ثم حركة الشراء/البيع، ثم بيانات التعريف.
 */
export const ProductOverview: React.FC<{
  profile: ProductProfileData | null;
  loading?: boolean;
  addBrandSlot?: React.ReactNode;
}> = ({ profile, loading, addBrandSlot }) => {
  if (!profile) {
    return (
      <div className="p-4 text-center text-[var(--ktra-ink-soft)]">
        {loading ? "جاري التحميل…" : "لا توجد بيانات لهذا المنتج بعد."}
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
          hint="المتوسط المرجّح لمشتريات المنتج المرحّلة" />
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
            : "لا فاتورة بيع مرحّلة لهذا المنتج"} />
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
        <Kpi label="رقم المنتج (SKU)" value={profile.sku || "—"} />
        <Kpi label="الباركود" value={profile.barcode || "—"} />
        <Kpi label="البراند" value={profile.brand || "—"} />
        <Kpi label="التصنيف" value={profile.category || "—"} />
        <Kpi label="الوحدة" value={profile.uom || "—"} />
        <Kpi label="طبيعة المنتج" value={profile.is_service ? "خدمة" : "بضاعة"} />
      </Section>

      {/* #23: «كرت المنتج يعرض المجمَّع والتفصيل معاً» — حين يتبع هذا البراند
          منتجاً له إخوة، يظهر مجمّعهم وتفصيلهم هنا بلا مغادرة الكرت. */}
      {profile.family_id != null &&
        <FamilyBrandsSection familyId={profile.family_id} addBrandSlot={addBrandSlot} />}
    </div>
  );
};

/**
 * #23: مجمَّع براندات المنتج (الأب) + تفصيلها — يقرأ نفس نقطة الكرت المجمّع
 * القائمة (`useGroupInsights`/`product_group_profile`) بمحدِّد `family` بدل
 * تعداد المعرّفات؛ لا منطق تجميعٍ ثانٍ. صامتةٌ (`null`) حين لا إخوة بعد —
 * منتجٌ ببراندٍ واحد يبقى كرته كما هو اليوم بلا قسمٍ زائد.
 */
const FamilyBrandsSection: React.FC<{
  familyId: number;
  /** حقل «أضف براند» جاهزاً من المستدعي. يُمرَّر عنصراً لا دالّة كي لا تستورد
   *  هذه الوحدة من `ItemForm` (تلك تستورد منها أصلاً — استيرادٌ دائري). */
  addBrandSlot?: React.ReactNode;
}> = ({ familyId, addBrandSlot }) => {
  const { profile: group, loading } = useGroupInsights({ family: familyId });
  // القسم كان يصمت لمنتجٍ ببراندٍ واحد. ومع مقبس الإضافة يجب أن يظهر: هذا
  // بالضبط المنتج الذي يريد صاحبه أن يضيف له ثانياً، وإخفاء القسم يُخفي
  // الطريق الوحيد إليه.
  if (!loading && (!group || group.member_count <= 1) && !addBrandSlot) return null;
  return (
    <section className="mb-3">
      <div className="text-xs font-bold text-[var(--ktra-ink-soft)] mb-1.5 pr-0.5">
        براندات هذا المنتج
      </div>
      {addBrandSlot && <div className="mb-2">{addBrandSlot}</div>}
      {group && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
          <Kpi label="إجمالي الرصيد (كل البراندات)" value={formatQuantity(group.quantity_on_hand, "—")} />
          <Kpi label="تقييم المخزون المجمّع" value={formatMoney(group.inventory_valuation, "—")} />
          <Kpi label="عدد البراندات" value={formatQuantity(group.member_count, "—")} />
        </div>
      )}
      <LedgerTable<GroupMember>
        columns={groupMemberColumns}
        rows={group?.members || []}
        loading={loading}
        emptyText="لا توجد براندات أخرى بعد."
      />
    </section>
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
 * T-SERIAL: وحدات المنتج المُرقَّمة — «أي وحدة جاءت من أي مورّد وذهبت لأي زبون».
 * الحالة والمستندان يأتيان من الخادم كما هي (`inventory/serials.py::_serial_row`).
 */
const serialColumns: LedgerColumn<ProductSerialRow>[] = [
  {
    key: "serial",
    header: "الرقم التسلسلي",
    render: (r) => <b style={{ direction: "ltr", display: "inline-block" }}>{r.serial}</b>,
  },
  {
    key: "status",
    header: "الحالة",
    align: "center",
    render: (r) => (
      <span style={{ color: r.status === "sold" ? "var(--ktra-ink-soft)" : "var(--ktra-ok,#267346)" }}>
        {r.status_display}
      </span>
    ),
  },
  {
    key: "purchase",
    header: "فاتورة الشراء",
    render: (r) => (
      <DocRefCell
        referenceType="PURCHASE_INVOICE"
        referenceId={r.purchase_invoice}
        label={r.purchase_invoice_number || "—"}
      />
    ),
  },
  { key: "supplier_name", header: "المورد", render: (r) => r.supplier_name || "—" },
  {
    key: "sales",
    header: "فاتورة البيع",
    render: (r) => (
      <DocRefCell
        referenceType="SALES_INVOICE"
        referenceId={r.sales_invoice}
        label={r.sales_invoice_number || "—"}
      />
    ),
  },
  { key: "customer_name", header: "الزبون", render: (r) => r.customer_name || "—" },
  { key: "created_at", header: "تاريخ الإدخال", render: (r) => formatDateLocalized(r.created_at) || "—" },
];

/**
 * يجلب بيانات الكرت القرائية لمنتج محفوظ (`productId=null` عند منتج جديد → بلا نداءات)
 * ويبني تبويباته جاهزة للتركيب في `KitDocumentShell`.
 *
 * `isSerialized` يأتي من الكرت لا من نقطة `profile` (لا تحمله): تبويب الأرقام
 * التسلسلية لا يُبنى أصلاً لمنتج غير متتبَّع، فلا نداء ولا تبويب فارغ.
 */
export const useProductInsights = (
  productId: number | null,
  options: { isSerialized?: boolean; addBrandSlot?: React.ReactNode } = {},
) => {
  const { isSerialized = false, addBrandSlot } = options;
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

  const [serials, setSerials] = useState<ProductSerialRow[]>([]);
  const [serLoading, setSerLoading] = useState(false);
  const [serError, setSerError] = useState<string | null>(null);
  const [serQuery, setSerQuery] = useState("");

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

  useEffect(() => {
    if (productId == null || !isSerialized) { setSerials([]); return; }
    setSerLoading(true);
    setSerError(null);
    inventoryApi.getProductSerials(productId)
      .then((rows) => setSerials(rows))
      .catch((err) => {
        setSerError(err instanceof Error ? err.message : String(err));
        setSerials([]);
      })
      .finally(() => setSerLoading(false));
  }, [productId, isSerialized]);

  /**
   * ترقيم مخزون قائم: الوحدة لا تُنشأ إلا من فاتورة شراء، فمخزون ما قبل الميزة
   * كان يبقى بلا أرقام — و«إجباري» في البيع يرفض بيعه بلا مخرج. الزر يفتح نافذة
   * الإدخال نفسها (`capture`)، والسقف خادمي: لا ترقيم فوق رصيد المنتج.
   */
  const [registerOpen, setRegisterOpen] = useState(false);
  const inStockUnits = useMemo(
    () => serials.filter((r) => r.status === "in_stock").length,
    [serials],
  );
  const untrackedQty = useMemo(() => {
    const onHand = Math.trunc(Number(profile?.quantity_on_hand ?? 0)) || 0;
    return Math.max(0, onHand - inStockUnits);
  }, [profile, inStockUnits]);

  const registerSerials = useCallback((list: string[]) => {
    if (productId == null || list.length === 0) { setRegisterOpen(false); return; }
    setSerLoading(true);
    inventoryApi.registerProductSerials(productId, list)
      .then((rows) => { setSerials(rows); setSerError(null); setRegisterOpen(false); })
      .catch((err) => {
        // الرسالة تُعرض في التبويب لا داخل النافذة: النافذة تُغلق فيبقى السبب
        // ظاهراً مع القائمة التي يخصّه (السقف، أو رقم مستخدم مسبقاً).
        setSerError(err instanceof Error ? err.message : String(err));
        setRegisterOpen(false);
      })
      .finally(() => setSerLoading(false));
  }, [productId]);

  // البحث على الرقم وعلى رقمَي المستند والطرفين معاً — الجرد يبحث بالرقم،
  // وخدمة ما بعد البيع تبحث باسم الزبون أو رقم فاتورته.
  const filteredSerials = useMemo(() => {
    const term = serQuery.trim().toLowerCase();
    if (!term) return serials;
    return serials.filter((r) =>
      [r.serial, r.purchase_invoice_number, r.supplier_name, r.sales_invoice_number, r.customer_name]
        .some((v) => (v || "").toLowerCase().includes(term)),
    );
  }, [serials, serQuery]);

  const emptyHint = "احفظ المنتج أولاً لتظهر بياناته هنا.";

  const tabs: KitTab[] = [
    {
      key: "overview",
      label: "نظرة عامة",
      content: productId == null
        ? <div className="p-4 text-[var(--ktra-ink-soft)]">{emptyHint}</div>
        : error
          ? <div role="alert" className="p-3 text-sm text-[var(--ktra-danger,#c00)]">تعذّر تحميل النظرة العامة: {error}</div>
          : <ProductOverview profile={profile} loading={loading} addBrandSlot={addBrandSlot} />,
    },
    {
      key: "invoices",
      label: "الفواتير المرتبطة",
      content: productId == null
        ? <div className="p-4 text-[var(--ktra-ink-soft)]">{emptyHint}</div>
        : (
          <div className="p-2">
            <LedgerTable<InvoiceRow>
              columns={invoiceColumns}
              rows={invoices}
              loading={invLoading}
              error={invError}
              emptyText="لا توجد فواتير تحتوي هذا المنتج."
            />
          </div>
        ),
    },
    {
      key: "ledger",
      label: "حركة المخزون",
      content: productId == null
        ? <div className="p-4 text-[var(--ktra-ink-soft)]">{emptyHint}</div>
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
              emptyText="لا توجد حركات مخزون لهذا المنتج."
            />
          </div>
        ),
    },
  ];

  /**
   * T-SERIAL: تبويب الوحدات — منفصل عن `tabs` عمداً كي يركّبه الكرت **آخر** القائمة.
   * `KitDocumentShell` يتتبّع التبويب النشط بالفهرس لا بالمفتاح، فإدراج تبويب في
   * وسط القائمة وقت التفعيل كان يقفز بالمستخدم من «بيانات عامة» إلى التبويب الجديد.
   * تبويبٌ يُلحق في النهاية لا يزحزح فهرس أحد. (بلا تتبّع: لا تبويب أصلاً.)
   */
  const serialsTab: KitTab | null = !isSerialized ? null : {
      key: "serials",
      label: "الأرقام التسلسلية",
      content: productId == null
        ? <div className="p-4 text-[var(--ktra-ink-soft)]">{emptyHint}</div>
        : (
          <div className="p-2">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <input
                className="ktra-input"
                style={{ maxWidth: 280 }}
                value={serQuery}
                onChange={(e) => setSerQuery(e.target.value)}
                placeholder="بحث برقم الوحدة أو الفاتورة أو الطرف…"
              />
              <span className="text-xs text-[var(--ktra-ink-soft)]">
                {formatQuantity(inStockUnits)} في المخزن
                {" · "}
                {formatQuantity(serials.filter((r) => r.status === "sold").length)} مُباعة
                {untrackedQty > 0 ? ` · ${formatQuantity(untrackedQty)} بلا ترقيم` : ""}
                {serQuery.trim() ? ` · ${formatQuantity(filteredSerials.length)} مطابقة` : ""}
              </span>
              {untrackedQty > 0 && (
                <button
                  type="button"
                  className="ktra-addrow"
                  style={{ margin: 0 }}
                  title="أعطِ أرقاماً لوحدات موجودة في المخزن قبل تفعيل التتبّع"
                  onClick={() => setRegisterOpen(true)}
                >
                  تسجيل أرقام لمخزون قائم
                </button>
              )}
            </div>
            {registerOpen && (
              <SerialEntryModal
                mode="capture"
                productId={productId}
                productName={profile?.name || ""}
                quantity={untrackedQty}
                value={[]}
                onClose={() => setRegisterOpen(false)}
                onSave={registerSerials}
              />
            )}
            <LedgerTable<ProductSerialRow>
              columns={serialColumns}
              rows={filteredSerials}
              loading={serLoading}
              error={serError}
              emptyText={
                serQuery.trim()
                  ? "لا وحدة تطابق البحث."
                  : "لا وحدات مُرقَّمة بعد — تُنشأ عند استلام بضاعة فاتورة شراء تحمل أرقاماً، أو سجّل أرقام المخزون القائم."
              }
            />
          </div>
        ),
    };

  return { profile, loading, error, reload: loadProfile, tabs, serialsTab };
};

/* ─────────────────────────────────────────────────────────────────────────
 * الكرت المجمّع: عقدة المقاس/التصنيف تجمع كل البراندات تحتها.
 * كان كلّه محبوساً في صفحة `GroupProfilePage`، فلمّا احتاجته شجرة المنتجات
 * لتعرضه في بطاقتها الجانبية كان الطريق إمّا نسخةً ثانية منه أو استخراجه —
 * فاستُخرج هنا كما استُخرجت تبويبات المنتج المفرد، والصفحة صارت غلافاً فوقه.
 * ───────────────────────────────────────────────────────────────────────── */

export interface GroupMember {
  id: number;
  sku: string;
  brand: string;
  name: string;
  quantity_on_hand: string;
  avg_cost: string;
  inventory_valuation: string;
  sold_qty: string;
}

export interface GroupProfileData {
  name: string;
  category: string | null;
  member_count: number;
  members: GroupMember[];
  quantity_on_hand: string;
  inventory_valuation: string;
  purchased_qty: string;
  purchased_value: string;
  sold_qty: string;
  sold_value: string;
}

/** حركة المخزون المجمّعة = صفّ حركة المنتج + البراند الذي جاءت منه. */
export interface GroupLedgerRow extends LedgerRow {
  product_name?: string;
}

/**
 * أعمدة الحركة المجمّعة = أعمدة المنتج نفسها + «البراند» بعد التاريخ، والرصيد
 * يُسمّى رصيد البراند لأنه جارٍ لكل براند على حدة لا للمجموعة.
 * الحقن **بالمفتاح لا بالفهرس**: تغيّر ترتيب الأعمدة المشتركة لا يزحزح شيئاً.
 */
const groupLedgerColumns = (): LedgerColumn<GroupLedgerRow>[] => {
  const out: LedgerColumn<GroupLedgerRow>[] = [];
  for (const col of ledgerColumns({ withParty: true }) as LedgerColumn<GroupLedgerRow>[]) {
    out.push(col.key === "running_balance" ? { ...col, header: "رصيد البراند" } : col);
    if (col.key === "date") {
      out.push({ key: "product_name", header: "البراند", render: (r) => r.product_name || "—" });
    }
  }
  return out;
};

const groupMemberColumns: LedgerColumn<GroupMember>[] = [
  {
    key: "name",
    header: "البراند",
    render: (m) => (
      <button
        type="button"
        className="text-[var(--ktra-accent,#2563eb)] underline hover:opacity-80"
        onClick={() => openInNewTab(productProfilePath(m.id))}
        title="فتح بطاقة هذا البراند"
      >{m.name}</button>
    ),
  },
  { key: "sku", header: "الكود", render: (m) => m.sku },
  { key: "quantity_on_hand", header: "الكمية", align: "center", render: (m) => formatQuantity(m.quantity_on_hand, "—") },
  { key: "avg_cost", header: "متوسط التكلفة", align: "center", render: (m) => formatMoney(m.avg_cost, "—") },
  { key: "inventory_valuation", header: "التقييم", align: "center", render: (m) => formatMoney(m.inventory_valuation, "—") },
  { key: "sold_qty", header: "المباع", align: "center", render: (m) => formatQuantity(m.sold_qty, "—") },
];

/**
 * يجلب الكرت المجمّع ويبني تبويباته. المحدِّد إمّا تصنيفٌ (`{ category }` —
 * الخادم يشتقّ منتجاته وأحفاده فلا يسافر تعدادٌ في الطلب) وإمّا معرّفاتٌ صريحة.
 * المفتاح نصّي كي لا يُعيد مستدعٍ يبني الكائن/المصفوفة في كل رسم إطلاقَ الطلبات
 * بلا نهاية. مجموعةٌ فارغة (تصنيف بلا منتجات) ليست خطأ شبكة: لا نداء، ورسالةٌ
 * تقول ذلك.
 */
export const useGroupInsights = (selector: ProductGroupSelector | number[]) => {
  const given: ProductGroupSelector = Array.isArray(selector) ? { ids: selector } : selector;
  // #23: `family` — الأب يشتقّ الخادم برانداته كلّها (كرت المنتج المفرد).
  const selKey = `${given.family ?? ""}|${given.category ?? ""}|${(given.ids ?? []).join(",")}`;
  const sel = useMemo<ProductGroupSelector>(() => {
    const [fam, cat, idsRaw] = selKey.split("|");
    if (fam) return { family: Number(fam) };
    return cat
      ? { category: Number(cat) }
      : { ids: idsRaw.split(",").filter(Boolean).map(Number) };
  }, [selKey]);
  // «فارغة» = لا أبٌ ولا تصنيف ولا معرّفات؛ أيٌّ منها وحده كافٍ (الخادم يعدّ أعضاءه).
  const isEmpty = !sel.family && !sel.category && !(sel.ids ?? []).length;

  const [profile, setProfile] = useState<GroupProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [ledger, setLedger] = useState<{ rows: GroupLedgerRow[]; count: number }>({ rows: [], count: 0 });
  const [ledOffset, setLedOffset] = useState(0);
  const [ledLoading, setLedLoading] = useState(false);

  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);

  useEffect(() => {
    setLedOffset(0);
    if (isEmpty) {
      setProfile(null);
      setError("لا توجد منتجات في هذه المجموعة بعد.");
      setLoading(false);
      return;
    }
    setLoading(true);
    inventoryApi.getProductGroupProfile(sel)
      .then((p) => { setProfile(p as GroupProfileData); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [sel, isEmpty]);

  useEffect(() => {
    if (isEmpty) { setLedger({ rows: [], count: 0 }); return; }
    setLedLoading(true);
    inventoryApi.getProductGroupLedger(sel, PAGE, ledOffset)
      .then((d) => setLedger({ rows: d.results, count: d.count }))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLedLoading(false));
  }, [sel, isEmpty, ledOffset]);

  useEffect(() => {
    if (isEmpty) { setInvoices([]); return; }
    setInvLoading(true);
    setInvError(null);
    inventoryApi.getProductGroupInvoices(sel)
      .then((d) => setInvoices(Array.isArray(d) ? d : []))
      .catch((err) => { setInvError(err instanceof Error ? err.message : String(err)); setInvoices([]); })
      .finally(() => setInvLoading(false));
  }, [sel, isEmpty]);

  const tabs: KitTab[] = [
    {
      key: "kpis",
      label: "نظرة عامة (مجمّع)",
      content: (
        <div className="p-3">
          {profile ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Kpi label="إجمالي المخزون (كل البراندات)" value={formatQuantity(profile.quantity_on_hand, "—")} />
              <Kpi label="تقييم المخزون المجمّع" value={formatMoney(profile.inventory_valuation, "—")} />
              <Kpi label="عدد البراندات" value={formatQuantity(profile.member_count, "—")} />
              <Kpi label="التصنيف" value={profile.category || "—"} />
              <Kpi label="إجمالي المشتراة (كمية)" value={formatQuantity(profile.purchased_qty, "—")} />
              <Kpi label="إجمالي المشتراة (قيمة)" value={formatMoney(profile.purchased_value, "—")} />
              <Kpi label="إجمالي المباعة (كمية)" value={formatQuantity(profile.sold_qty, "—")} />
              <Kpi label="إجمالي المباعة (قيمة)" value={formatMoney(profile.sold_value, "—")} />
            </div>
          ) : (
            // خطأٌ أو مجموعةٌ فارغة — لا «جاري التحميل…» أبديّ.
            <div role={error ? "alert" : undefined} className="p-4 text-center text-[var(--ktra-ink-soft)]">
              {loading ? "جاري التحميل…" : error || "لا توجد بيانات لهذه المجموعة."}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "members",
      label: "البراندات",
      content: (
        <div className="p-2">
          <LedgerTable<GroupMember>
            columns={groupMemberColumns}
            rows={profile?.members || []}
            loading={loading}
            emptyText="لا توجد براندات في هذه المجموعة."
          />
        </div>
      ),
    },
    {
      key: "invoices",
      label: "الفواتير المرتبطة",
      content: (
        <div className="p-2">
          <LedgerTable<InvoiceRow>
            columns={invoiceColumns}
            rows={invoices}
            loading={invLoading}
            error={invError}
            emptyText="لا توجد فواتير لهذه المجموعة."
          />
        </div>
      ),
    },
    {
      key: "ledger",
      label: "حركة المخزون (مجمّعة)",
      content: (
        <div className="p-2">
          <LedgerTable<GroupLedgerRow>
            columns={groupLedgerColumns()}
            rows={ledger.rows}
            loading={ledLoading}
            count={ledger.count}
            limit={PAGE}
            offset={ledOffset}
            onPage={setLedOffset}
            emptyText="لا توجد حركات مخزون لهذه المجموعة."
          />
        </div>
      ),
    },
  ];

  return { profile, loading, error, tabs };
};
