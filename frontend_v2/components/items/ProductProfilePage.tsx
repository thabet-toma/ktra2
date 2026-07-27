/**
 * FEAT-3 — ProductProfilePage: بطاقة الصنف الاحترافية.
 * رأس بمؤشرات (المخزون/المشتريات/المبيعات/التقييم) + تبويبان: الفواتير المرتبطة
 * ودفتر حركة المخزون (رصيد جارٍ). يعيد استخدام LedgerTable المشترك.
 */
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiGetObject } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { AseelDocumentShell, AseelTab } from '../aseel';
import { LedgerTable, DocRefCell, type LedgerColumn } from '../shared/LedgerTable';
import { openInNewTab } from '../../utils/openInNewTab';
import { formatQuantity, formatMoney } from '../../utils/formatNumber';
import { formatDateLocalized } from "../../utils/formatDate";

interface ProductProfile {
  id: number;
  sku: string;
  name: string;
  category: string | null;
  quantity_on_hand: string;
  avg_cost: string;
  inventory_valuation: string;
  purchased_qty: string;
  purchased_value: string;
  sold_qty: string;
  sold_value: string;
  // W8: معدّلات البيع (من StockMovement) — أسبوعي 28ي÷4 · شهري 90ي÷3.
  avg_weekly_sales?: string;
  avg_monthly_sales?: string;
}

interface LedgerRow {
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

/**
 * نوع الحركة المعروض في «حركة المخزون» — مثل تبويب الفواتير المرتبطة: مشتريات/مبيعات
 * مشتقّة من نوع المستند المرجعي، وما عداها يبقى على وصف نوع الحركة كما هو.
 */
const ledgerTypeLabel = (r: LedgerRow): string => {
  if (r.reference_type === 'PURCHASE_INVOICE') return 'مشتريات';
  if (r.reference_type === 'SALE') return 'مبيعات';
  return r.movement_type_label;
};

interface InvoiceRow {
  document_type: string;
  document_id: number;
  document_number: string;
  date: string | null;
  party: string | null;
  is_posted: boolean;
}

const PAGE = 50;

export const ProductProfilePage: React.FC = () => {
  // App مركّب على مسار splat (/*) بلا Route فيه :id، لذا useParams().id يرجع
  // undefined. نستخرج المعرّف من المسار مباشرة (/products/:id).
  const location = useLocation();
  const id = useMemo(() => {
    const m = location.pathname.match(/\/products\/([^/]+)/);
    return m ? m[1] : undefined;
  }, [location.pathname]);
  // التبويب الابتدائي عبر ?tab= — أي رابط «ذكر لمنتج» يفتح «حركة المخزون» مباشرة.
  const initialTab = useMemo(() => {
    const t = new URLSearchParams(location.search).get("tab");
    return t === "ledger" || t === "invoices" || t === "kpis" ? t : undefined;
  }, [location.search]);
  const navigate = useNavigate();
  const tenantId = useMemo(() => resolveTenantId(), []);

  const [profile, setProfile] = useState<ProductProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [ledger, setLedger] = useState<{ rows: LedgerRow[]; count: number }>({ rows: [], count: 0 });
  const [ledOffset, setLedOffset] = useState(0);
  const [ledLoading, setLedLoading] = useState(false);

  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    apiGetObject<ProductProfile>(`inventory/products/${id}/profile/`, { tenantId })
      .then((p) => { setProfile(p); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [id, tenantId]);

  const loadLedger = useCallback(
    (offset: number) => {
      if (!id) return;
      setLedLoading(true);
      apiGetObject<{ results: LedgerRow[]; count: number }>(
        `inventory/products/${id}/stock-ledger/?limit=${PAGE}&offset=${offset}`,
        { tenantId },
      )
        .then((d) => setLedger({ rows: d.results, count: d.count }))
        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setLedLoading(false));
    },
    [id, tenantId],
  );

  useEffect(() => { loadLedger(ledOffset); }, [loadLedger, ledOffset]);

  useEffect(() => {
    if (!id) return;
    setInvLoading(true);
    setInvError(null);
    apiGetObject<InvoiceRow[]>(`inventory/products/${id}/invoices/`, { tenantId })
      .then((d) => setInvoices(Array.isArray(d) ? d : []))
      .catch((err) => {
        // ميّز فشل التحميل عن «لا توجد فواتير» — لا تُظهر الفراغ كأنه نتيجة سليمة.
        setInvError(err instanceof Error ? err.message : String(err));
        setInvoices([]);
      })
      .finally(() => setInvLoading(false));
  }, [id, tenantId]);

  const ledColumns: LedgerColumn<LedgerRow>[] = [
    { key: 'date', header: 'التاريخ', render: (r) => formatDateLocalized(r.date) || '—' },
    { key: 'movement_type_label', header: 'النوع', render: (r) => ledgerTypeLabel(r) },
    { key: 'party', header: 'الطرف', render: (r) => r.party || '—' },
    {
      key: 'reference',
      header: 'المستند',
      render: (r) => (
        <DocRefCell
          referenceType={r.reference_type}
          referenceId={r.reference_id}
          label={r.reference_id != null ? `${r.reference_type || ''} #${r.reference_id}` : '—'}
        />
      ),
    },
    { key: 'warehouse', header: 'المستودع', render: (r) => r.warehouse || '—' },
    { key: 'qty_in', header: 'وارد', align: 'center', render: (r) => (Number(r.qty_in) ? r.qty_in : '—') },
    { key: 'qty_out', header: 'صادر', align: 'center', render: (r) => (Number(r.qty_out) ? r.qty_out : '—') },
    { key: 'running_balance', header: 'الرصيد', align: 'center', render: (r) => <b>{r.running_balance}</b> },
  ];

  const invColumns: LedgerColumn<InvoiceRow>[] = [
    {
      key: 'document_number',
      header: 'رقم الفاتورة',
      render: (r) => (
        <DocRefCell referenceType={r.document_type} referenceId={r.document_id} label={r.document_number} />
      ),
    },
    { key: 'document_type', header: 'النوع', render: (r) => (r.document_type === 'SALES_INVOICE' ? 'بيع' : 'شراء') },
    { key: 'party', header: 'الطرف', render: (r) => r.party || '—' },
    { key: 'date', header: 'التاريخ', render: (r) => formatDateLocalized(r.date) || '—' },
    { key: 'is_posted', header: 'الحالة', align: 'center', render: (r) => (r.is_posted ? 'مرحّلة' : 'مسودة') },
  ];

  const Kpi: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
    <div className="p-3 border border-[var(--aseel-border)] rounded">
      <div className="text-xs text-[var(--aseel-ink-soft)]">{label}</div>
      <div className="text-lg font-bold text-[var(--aseel-ink)]">{value}</div>
    </div>
  );

  const tabs: AseelTab[] = [
    {
      key: 'kpis',
      label: 'نظرة عامة',
      content: (
        <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-3">
          {profile ? (
            <>
              <Kpi label="المخزون الحالي" value={formatQuantity(profile.quantity_on_hand, '—')} />
              <Kpi label="متوسط التكلفة" value={formatMoney(profile.avg_cost, '—')} />
              <Kpi label="تقييم المخزون" value={formatMoney(profile.inventory_valuation, '—')} />
              <Kpi label="إجمالي المشتراة (كمية)" value={formatQuantity(profile.purchased_qty, '—')} />
              <Kpi label="إجمالي المشتراة (قيمة)" value={formatMoney(profile.purchased_value, '—')} />
              <Kpi label="إجمالي المباعة (كمية)" value={formatQuantity(profile.sold_qty, '—')} />
              <Kpi label="إجمالي المباعة (قيمة)" value={formatMoney(profile.sold_value, '—')} />
              {/* W8: معدّلات البيع من StockMovement (بعد خصم المرتجعات). */}
              <Kpi label="متوسط البيع الأسبوعي (28ي÷4)" value={formatQuantity(profile.avg_weekly_sales ?? '', '—')} />
              <Kpi label="متوسط البيع الشهري (90ي÷3)" value={formatQuantity(profile.avg_monthly_sales ?? '', '—')} />
              <Kpi label="التصنيف" value={profile.category || '—'} />
              <Kpi label="SKU" value={profile.sku} />
            </>
          ) : (
            <span className="text-[var(--aseel-ink-soft)]">جاري التحميل…</span>
          )}
        </div>
      ),
    },
    {
      key: 'invoices',
      label: 'الفواتير المرتبطة',
      content: (
        <div className="p-2">
          <LedgerTable<InvoiceRow>
            columns={invColumns}
            rows={invoices}
            loading={invLoading}
            error={invError}
            emptyText="لا توجد فواتير تحتوي هذا الصنف."
          />
        </div>
      ),
    },
    {
      key: 'ledger',
      label: 'حركة المخزون',
      content: (
        <div className="p-2">
          <LedgerTable<LedgerRow>
            columns={ledColumns}
            rows={ledger.rows}
            loading={ledLoading}
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

  const title = profile
    ? `بطاقة الصنف: ${profile.name}`
    : error
      ? `بطاقة الصنف #${id}`
      : 'جاري التحميل...';

  return (
    <div className="min-h-[calc(100vh-5rem)]">
      <AseelDocumentShell
        title={title}
        initialTab={initialTab}
        actions={[
          { key: 'cost', label: 'تكلفة المنتجات', onClick: () => openInNewTab(`/product-cost?product=${id}`) },
          { key: 'back', label: 'عودة', onClick: () => navigate(-1) },
        ]}
        tabs={tabs}
        status={
          error ? <span className="text-[var(--aseel-danger)]">تعذّر تحميل البطاقة: {error}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="aseel-status-item">{profile ? `المخزون ${formatQuantity(profile.quantity_on_hand, '—')} · تقييم ${formatMoney(profile.inventory_valuation, '—')}` : ''}</span>
        }
      >
        {error && (
          <div role="alert" className="m-2 p-3 rounded border border-[var(--aseel-danger,#c00)] text-[var(--aseel-danger,#c00)] text-sm">
            تعذّر تحميل بيانات الصنف: {error}
            <div className="text-xs mt-1 text-[var(--aseel-ink-soft)]">
              إن كان الخطأ 404 فأعد تشغيل خادم Django لالتقاط نقاط البطاقة الجديدة.
            </div>
          </div>
        )}
      </AseelDocumentShell>
    </div>
  );
};

export default ProductProfilePage;
