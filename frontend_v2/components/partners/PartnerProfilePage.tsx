import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiGetObject } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { AseelDocumentShell, AseelTab } from '../aseel';
import { LedgerTable, DocRefCell, type LedgerColumn } from '../shared/LedgerTable';
import { CustomerPriceListTab } from './CustomerPriceListTab';

interface PartnerApi {
  id: number;
  name: string;
  legal_name?: string | null;
  partner_type: string;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  country?: string | null;
  street_address?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  tax_number?: string | null;
  credit_limit?: string | null;
}

interface PartnerProfile {
  balance: string;
  balance_side: string;
  outstanding_balance: string;
  total_sales: string;
  total_purchases: string;
  last_transaction_date: string | null;
}

interface StatementRow {
  id: number;
  date: string | null;
  reference_type: string | null;
  reference_id: number | null;
  description: string;
  debit: string;
  credit: string;
  running_balance: string;
}

interface InvoiceRow {
  document_type: string;
  document_id: number;
  document_number: string;
  date: string | null;
  grand_total: string;
  is_posted: boolean;
}

const PAGE = 50;

export const PartnerProfilePage: React.FC = () => {
  // App مركّب على مسار splat (/*) بلا Route فيه :id ⇒ useParams().id = undefined.
  // نستخرج المعرّف من المسار مباشرة (/partners/:id).
  const location = useLocation();
  const id = useMemo(() => {
    const m = location.pathname.match(/\/partners\/([^/]+)/);
    return m ? m[1] : undefined;
  }, [location.pathname]);
  const navigate = useNavigate();
  const [partner, setPartner] = useState<PartnerApi | null>(null);
  const [profile, setProfile] = useState<PartnerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // statement (party ledger) — paginated
  const [stmt, setStmt] = useState<{ rows: StatementRow[]; count: number }>({ rows: [], count: 0 });
  const [stmtOffset, setStmtOffset] = useState(0);
  const [stmtLoading, setStmtLoading] = useState(false);

  // invoices
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);

  const tenantId = useMemo(() => resolveTenantId(), []);
  const isSupplier = (partner?.partner_type || '').toLowerCase() === 'supplier';

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      apiGetObject<PartnerApi>(`partners/${id}/`, { tenantId }),
      apiGetObject<PartnerProfile>(`partners/${id}/profile/`, { tenantId }),
    ])
      .then(([p, prof]) => {
        setPartner(p);
        setProfile(prof);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [id, tenantId]);

  const loadStatement = useCallback(
    (offset: number) => {
      if (!id) return;
      setStmtLoading(true);
      apiGetObject<{ results: StatementRow[]; count: number }>(
        `partners/${id}/statement/?limit=${PAGE}&offset=${offset}`,
        { tenantId },
      )
        .then((d) => setStmt({ rows: d.results, count: d.count }))
        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setStmtLoading(false));
    },
    [id, tenantId],
  );

  useEffect(() => {
    loadStatement(stmtOffset);
  }, [loadStatement, stmtOffset]);

  useEffect(() => {
    if (!id) return;
    setInvLoading(true);
    setInvError(null);
    apiGetObject<InvoiceRow[]>(`partners/${id}/invoices/`, { tenantId })
      .then((d) => setInvoices(Array.isArray(d) ? d : []))
      .catch((err) => {
        setInvError(err instanceof Error ? err.message : String(err));
        setInvoices([]);
      })
      .finally(() => setInvLoading(false));
  }, [id, tenantId]);

  const stmtColumns: LedgerColumn<StatementRow>[] = [
    { key: 'date', header: 'التاريخ', render: (r) => r.date || '—' },
    {
      key: 'reference',
      header: 'المرجع',
      render: (r) => (
        <DocRefCell
          referenceType={r.reference_type}
          referenceId={r.reference_id}
          label={r.reference_id != null ? `${r.reference_type || ''} #${r.reference_id}` : '—'}
        />
      ),
    },
    { key: 'description', header: 'البيان', render: (r) => r.description || '—' },
    { key: 'debit', header: 'مدين (Dr)', align: 'center', render: (r) => r.debit },
    { key: 'credit', header: 'دائن (Cr)', align: 'center', render: (r) => r.credit },
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
    {
      key: 'document_type',
      header: 'النوع',
      render: (r) => (r.document_type === 'SALES_INVOICE' ? 'بيع' : 'شراء'),
    },
    { key: 'date', header: 'التاريخ', render: (r) => r.date || '—' },
    { key: 'grand_total', header: 'الإجمالي', align: 'center', render: (r) => r.grand_total },
    {
      key: 'is_posted',
      header: 'الحالة',
      align: 'center',
      render: (r) => (r.is_posted ? 'مرحّلة' : 'مسودة'),
    },
  ];

  const Kpi: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
    <div className="p-3 border border-[var(--aseel-border)] rounded">
      <div className="text-xs text-[var(--aseel-ink-soft)]">{label}</div>
      <div className="text-lg font-bold text-[var(--aseel-ink)]">{value}</div>
    </div>
  );

  const tabs: AseelTab[] = [
    {
      key: 'details',
      label: 'التفاصيل',
      content: (
        <div className="p-4 grid grid-cols-2 gap-4 text-sm">
          {partner && (
            <>
              <div><span className="text-[var(--aseel-ink-soft)]">الاسم:</span> <b>{partner.name}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">الاسم القانوني:</span> <b>{partner.legal_name || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">النوع:</span> <b>{isSupplier ? 'مورد' : partner.partner_type === 'Customer' ? 'عميل' : partner.partner_type}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">الهاتف:</span> <b>{partner.phone || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">البريد الإلكتروني:</span> <b>{partner.email || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">الرقم الضريبي:</span> <b>{partner.tax_number || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">حد الائتمان:</span> <b>{partner.credit_limit || '—'}</b></div>
              <div className="col-span-2"><span className="text-[var(--aseel-ink-soft)]">العنوان:</span> <b>{[partner.street_address, partner.city, partner.state_or_province, partner.country].filter(Boolean).join(', ') || '—'}</b></div>
            </>
          )}
        </div>
      ),
    },
    {
      key: 'balance_summary',
      label: 'ملخص الرصيد',
      content: (
        <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          {profile ? (
            <>
              <Kpi label="الرصيد الحالي" value={`${profile.balance} ${profile.balance_side}`} />
              <Kpi label="المتبقي المستحق" value={profile.outstanding_balance} />
              <Kpi label={isSupplier ? 'إجمالي المشتريات' : 'إجمالي المبيعات'} value={isSupplier ? profile.total_purchases : profile.total_sales} />
              <Kpi label="آخر معاملة" value={profile.last_transaction_date || '—'} />
            </>
          ) : (
            <span className="text-[var(--aseel-ink-soft)]">جاري التحميل…</span>
          )}
        </div>
      ),
    },
    {
      key: 'statement',
      label: 'كشف الحساب',
      content: (
        <div className="p-2">
          <LedgerTable<StatementRow>
            columns={stmtColumns}
            rows={stmt.rows}
            loading={stmtLoading}
            count={stmt.count}
            limit={PAGE}
            offset={stmtOffset}
            onPage={setStmtOffset}
            emptyText="لا توجد حركات على حساب هذا الشريك."
          />
        </div>
      ),
    },
    {
      key: 'invoices',
      label: 'الفواتير',
      content: (
        <div className="p-2">
          <LedgerTable<InvoiceRow>
            columns={invColumns}
            rows={invoices}
            loading={invLoading}
            error={invError}
            emptyText="لا توجد فواتير لهذا الشريك."
          />
        </div>
      ),
    },
    // DEF-004: عرض السعر — مبيعات فقط (للعملاء، لا للموردين).
    ...(!isSupplier && id
      ? [{
          key: 'price_list',
          label: 'عرض السعر',
          content: <CustomerPriceListTab customerId={id} />,
        } as AseelTab]
      : []),
  ];

  return (
    <div data-skin="aseel" className="min-h-[calc(100vh-5rem)]">
      <AseelDocumentShell
        title={partner ? `كشف حساب: ${partner.name}` : 'جاري التحميل...'}
        actions={[
          { key: 'back', label: 'عودة', onClick: () => navigate(-1) },
          // T-P2: سند قبض سريع من كشف الحساب — العميل مُعبّأ مسبقاً.
          ...(!isSupplier && id
            ? [{
                key: 'new-receipt',
                label: 'سند قبض جديد',
                onClick: () => navigate(`/sales/customer-payments?pay_partner=${id}`),
                separatorBefore: true,
              }]
            : []),
        ]}
        tabs={tabs}
        status={
          error ? <span className="text-[var(--aseel-danger)]">{error}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="aseel-status-item">{isSupplier ? 'مورد' : 'عميل'}{profile ? ` · الرصيد ${profile.balance} ${profile.balance_side}` : ''}</span>
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
