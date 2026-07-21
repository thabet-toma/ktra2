/**
 * تجميع البراندات — الكرت المجمّع: بطاقة المقاس/الأساس (مثل عجل 185/65/14) تجمع
 * مؤشّرات وحركات وفواتير كل البراندات تحته. النقر على عقدة «المقاس» في شجرة الأصناف
 * (أو الجرد) يفتح هذه البطاقة. يعيد استخدام AseelDocumentShell + LedgerTable (DRY).
 * المسار: /product-group?ids=1,2,3&name=185/65/14
 */
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { inventoryApi } from '../../services/inventoryApi';
import { AseelDocumentShell, AseelTab } from '../aseel';
import { LedgerTable, DocRefCell, type LedgerColumn } from '../shared/LedgerTable';
import { openInNewTab } from '../../utils/openInNewTab';
import { productProfilePath } from '../../utils/entityLinks';
import { formatQuantity, formatMoney } from '../../utils/formatNumber';

interface GroupMember {
  id: number;
  sku: string;
  brand: string;
  name: string;
  quantity_on_hand: string;
  avg_cost: string;
  inventory_valuation: string;
  sold_qty: string;
}

interface GroupProfile {
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

interface LedgerRow {
  id: number;
  date: string | null;
  movement_type_label: string;
  reference_type: string | null;
  reference_id: number | null;
  party: string | null;
  warehouse: string | null;
  product_name?: string;
  qty_in: string;
  qty_out: string;
  running_balance: string;
}

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

export const GroupProfilePage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const ids = useMemo(() => {
    const raw = new URLSearchParams(location.search).get('ids') || '';
    return raw.split(',').map((s) => s.trim()).filter((s) => /^\d+$/.test(s)).map(Number);
  }, [location.search]);
  const nameParam = useMemo(
    () => new URLSearchParams(location.search).get('name') || '',
    [location.search],
  );

  const [profile, setProfile] = useState<GroupProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [ledger, setLedger] = useState<{ rows: LedgerRow[]; count: number }>({ rows: [], count: 0 });
  const [ledOffset, setLedOffset] = useState(0);
  const [ledLoading, setLedLoading] = useState(false);

  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);

  useEffect(() => {
    if (!ids.length) { setError('لا توجد أصناف في المجموعة'); setLoading(false); return; }
    setLoading(true);
    inventoryApi.getProductGroupProfile(ids)
      .then((p) => { setProfile(p as GroupProfile); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [ids]);

  const loadLedger = useCallback((offset: number) => {
    if (!ids.length) return;
    setLedLoading(true);
    inventoryApi.getProductGroupLedger(ids, PAGE, offset)
      .then((d) => setLedger({ rows: d.results, count: d.count }))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLedLoading(false));
  }, [ids]);

  useEffect(() => { loadLedger(ledOffset); }, [loadLedger, ledOffset]);

  useEffect(() => {
    if (!ids.length) return;
    setInvLoading(true);
    setInvError(null);
    inventoryApi.getProductGroupInvoices(ids)
      .then((d) => setInvoices(Array.isArray(d) ? d : []))
      .catch((err) => { setInvError(err instanceof Error ? err.message : String(err)); setInvoices([]); })
      .finally(() => setInvLoading(false));
  }, [ids]);

  const ledColumns: LedgerColumn<LedgerRow>[] = [
    { key: 'date', header: 'التاريخ', render: (r) => r.date || '—' },
    { key: 'product_name', header: 'البراند', render: (r) => r.product_name || '—' },
    { key: 'movement_type_label', header: 'النوع', render: (r) => ledgerTypeLabel(r) },
    { key: 'party', header: 'الطرف', render: (r) => r.party || '—' },
    {
      key: 'reference', header: 'المستند',
      render: (r) => (
        <DocRefCell
          referenceType={r.reference_type}
          referenceId={r.reference_id}
          label={r.reference_id != null ? `${r.reference_type || ''} #${r.reference_id}` : '—'}
        />
      ),
    },
    { key: 'qty_in', header: 'وارد', align: 'center', render: (r) => (Number(r.qty_in) ? r.qty_in : '—') },
    { key: 'qty_out', header: 'صادر', align: 'center', render: (r) => (Number(r.qty_out) ? r.qty_out : '—') },
    { key: 'running_balance', header: 'رصيد البراند', align: 'center', render: (r) => <b>{r.running_balance}</b> },
  ];

  const invColumns: LedgerColumn<InvoiceRow>[] = [
    {
      key: 'document_number', header: 'رقم الفاتورة',
      render: (r) => <DocRefCell referenceType={r.document_type} referenceId={r.document_id} label={r.document_number} />,
    },
    { key: 'document_type', header: 'النوع', render: (r) => (r.document_type === 'SALES_INVOICE' ? 'بيع' : 'شراء') },
    { key: 'party', header: 'الطرف', render: (r) => r.party || '—' },
    { key: 'date', header: 'التاريخ', render: (r) => r.date || '—' },
    { key: 'is_posted', header: 'الحالة', align: 'center', render: (r) => (r.is_posted ? 'مرحّلة' : 'مسودة') },
  ];

  const memColumns: LedgerColumn<GroupMember>[] = [
    {
      key: 'name', header: 'البراند',
      render: (m) => (
        <button
          type="button"
          className="text-[var(--aseel-accent,#2563eb)] underline hover:opacity-80"
          onClick={() => openInNewTab(productProfilePath(m.id))}
          title="فتح بطاقة هذا البراند"
        >{m.name}</button>
      ),
    },
    { key: 'sku', header: 'الكود', render: (m) => m.sku },
    { key: 'quantity_on_hand', header: 'الكمية', align: 'center', render: (m) => formatQuantity(m.quantity_on_hand, '—') },
    { key: 'avg_cost', header: 'متوسط التكلفة', align: 'center', render: (m) => formatMoney(m.avg_cost, '—') },
    { key: 'inventory_valuation', header: 'التقييم', align: 'center', render: (m) => formatMoney(m.inventory_valuation, '—') },
    { key: 'sold_qty', header: 'المباع', align: 'center', render: (m) => formatQuantity(m.sold_qty, '—') },
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
      label: 'نظرة عامة (مجمّع)',
      content: (
        <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-3">
          {profile ? (
            <>
              <Kpi label="إجمالي المخزون (كل البراندات)" value={formatQuantity(profile.quantity_on_hand, '—')} />
              <Kpi label="تقييم المخزون المجمّع" value={formatMoney(profile.inventory_valuation, '—')} />
              <Kpi label="عدد البراندات" value={profile.member_count} />
              <Kpi label="إجمالي المشتراة (كمية)" value={formatQuantity(profile.purchased_qty, '—')} />
              <Kpi label="إجمالي المشتراة (قيمة)" value={formatMoney(profile.purchased_value, '—')} />
              <Kpi label="إجمالي المباعة (كمية)" value={formatQuantity(profile.sold_qty, '—')} />
              <Kpi label="إجمالي المباعة (قيمة)" value={formatMoney(profile.sold_value, '—')} />
              <Kpi label="التصنيف" value={profile.category || '—'} />
            </>
          ) : (
            <span className="text-[var(--aseel-ink-soft)]">جاري التحميل…</span>
          )}
        </div>
      ),
    },
    {
      key: 'members',
      label: 'البراندات',
      content: (
        <div className="p-2">
          <LedgerTable<GroupMember>
            columns={memColumns}
            rows={profile?.members || []}
            loading={loading}
            emptyText="لا توجد براندات في هذه المجموعة."
          />
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
            emptyText="لا توجد فواتير لهذه المجموعة."
          />
        </div>
      ),
    },
    {
      key: 'ledger',
      label: 'حركة المخزون (مجمّعة)',
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
            emptyText="لا توجد حركات مخزون لهذه المجموعة."
          />
        </div>
      ),
    },
  ];

  const title = profile ? `كرت مجمّع: ${nameParam || profile.name}` : `كرت مجمّع: ${nameParam}`;

  return (
    <div className="min-h-[calc(100vh-5rem)]">
      <AseelDocumentShell
        title={title}
        actions={[{ key: 'back', label: 'عودة', onClick: () => navigate(-1) }]}
        tabs={tabs}
        status={
          error ? <span className="text-[var(--aseel-danger)]">تعذّر التحميل: {error}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="aseel-status-item">{profile ? `إجمالي المخزون ${formatQuantity(profile.quantity_on_hand, '—')} · تقييم ${formatMoney(profile.inventory_valuation, '—')}` : ''}</span>
        }
      >
        {error && (
          <div role="alert" className="m-2 p-3 rounded border border-[var(--aseel-danger,#c00)] text-[var(--aseel-danger,#c00)] text-sm">
            تعذّر تحميل الكرت المجمّع: {error}
          </div>
        )}
      </AseelDocumentShell>
    </div>
  );
};

export default GroupProfilePage;
