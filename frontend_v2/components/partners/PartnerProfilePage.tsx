import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiGetObject } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { AseelDocumentShell, AseelTab } from '../aseel';
import { LedgerTable, DocRefCell, type LedgerColumn } from '../shared/LedgerTable';
import { CustomerPriceListTab } from './CustomerPriceListTab';
import { CustomerNotesTab } from './CustomerNotesTab';
import { StatementDetailsModal } from './StatementDetailsModal';
import { referenceTypeLabel, clarifyStatementDescription } from '../../utils/entityLinks';

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
  // فتح تبويب محدد عبر ?tab= (مثلاً من شارة «عرض السعر» في فاتورة المبيعات).
  const initialTab = useMemo(() => {
    const m = location.search.match(/[?&]tab=([^&]+)/);
    return m ? decodeURIComponent(m[1]) : undefined;
  }, [location.search]);
  const navigate = useNavigate();
  // تبويب مُتحكَّم به: يبدأ من ?tab=، ويُتجاوَز بجسر إشعار التذكير (sessionStorage).
  const [activeTabKey, setActiveTabKey] = useState<string | undefined>(initialTab);
  const [focusNoteId, setFocusNoteId] = useState<string | null>(null);
  const [partner, setPartner] = useState<PartnerApi | null>(null);
  const [profile, setProfile] = useState<PartnerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // statement (party ledger) — paginated
  const [stmt, setStmt] = useState<{ rows: StatementRow[]; count: number }>({ rows: [], count: 0 });
  const [stmtOffset, setStmtOffset] = useState(0);
  const [stmtLoading, setStmtLoading] = useState(false);

  // تفاصيل حركة كشف الحساب (نافذة)
  const [detailRow, setDetailRow] = useState<StatementRow | null>(null);

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

  // مزامنة التبويب مع ?tab= في المسار (روابط خارجية مثل شارة «عرض السعر»).
  useEffect(() => { if (initialTab) setActiveTabKey(initialTab); }, [initialTab]);

  // جسر إشعار الموقع: عند الوصول من نقرة إشعار تذكير، افتح تبويب «ملاحظات الزبون»
  // وحدّد الملاحظة المستهدفة (يُضبط في NotificationCenter قبل التنقل).
  useEffect(() => {
    try {
      const tab = sessionStorage.getItem('ktra_focus_partner_tab');
      if (tab) {
        setActiveTabKey(tab);
        setFocusNoteId(sessionStorage.getItem('ktra_focus_partner_note'));
        sessionStorage.removeItem('ktra_focus_partner_tab');
        sessionStorage.removeItem('ktra_focus_partner_note');
      }
    } catch { /* خاصية خاصة */ }
  }, [location.key]);

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
      header: 'الحركة',
      render: (r) => (
        <DocRefCell
          referenceType={r.reference_type}
          referenceId={r.reference_id}
          label={`${referenceTypeLabel(r.reference_type)}${r.reference_id != null ? ` #${r.reference_id}` : ''}`}
        />
      ),
    },
    { key: 'description', header: 'البيان', render: (r) => clarifyStatementDescription(r.reference_type, r.description) || '—' },
    { key: 'debit', header: 'مدين (Dr)', align: 'right', render: (r) => <span className="aseel-num">{r?.debit ?? ''}</span> },
    { key: 'credit', header: 'دائن (Cr)', align: 'right', render: (r) => <span className="aseel-num">{r?.credit ?? ''}</span> },
    { key: 'running_balance', header: 'الرصيد', align: 'right', render: (r) => <b className="aseel-num">{r?.running_balance ?? ''}</b> },
    {
      key: 'details',
      header: 'تفاصيل',
      align: 'center',
      render: (r) => (
        <button
          type="button"
          onClick={() => setDetailRow(r)}
          className="text-[var(--aseel-accent,#2563eb)] underline hover:opacity-80"
        >
          تفاصيل
        </button>
      ),
    },
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
            summaryRow={
              (stmt?.rows && stmt.rows.length > 0) ? (
                <tr className="bg-[#e6e4d5] font-bold border-t-2 border-[var(--aseel-border)]">
                  <td colSpan={3} className="px-2 py-2 text-right">الإجمالي (هذه الصفحة):</td>
                  <td className="px-2 py-2 text-right aseel-num">
                    {stmt.rows.reduce((sum, r) => {
                      const val = parseFloat(String(r?.debit || "0").replace(/,/g, ''));
                      return sum + (isNaN(val) ? 0 : val);
                    }, 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-2 py-2 text-right aseel-num">
                    {stmt.rows.reduce((sum, r) => {
                      const val = parseFloat(String(r?.credit || "0").replace(/,/g, ''));
                      return sum + (isNaN(val) ? 0 : val);
                    }, 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-2 py-2"></td>
                  <td className="px-2 py-2"></td>
                </tr>
              ) : undefined
            }
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
    // ملاحظات الزبون (CRM) — للعملاء: ملاحظات + تذكيرات تظهر في إشعارات الموقع.
    ...(!isSupplier && id
      ? [{
          key: 'customer_notes',
          label: 'ملاحظات الزبون',
          content: <CustomerNotesTab customerId={id} focusNoteId={focusNoteId} />,
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
            ? [
                {
                  key: 'new-receipt',
                  label: 'سند قبض جديد',
                  onClick: () => navigate(`/sales/customer-payments?pay_partner=${id}`),
                  separatorBefore: true,
                },
                {
                  key: 'new-invoice',
                  label: 'فاتورة مبيعات جديدة',
                  onClick: () => navigate(`/sales/invoices/new?customer_id=${id}`),
                },
                {
                  key: 'new-quotation',
                  label: 'عرض سعر جديد',
                  onClick: () => navigate(`/sales/quotations?action=new&customer_id=${id}`),
                },
              ]
            : []),
        ]}
        tabs={tabs}
        activeTab={activeTabKey}
        onTabChange={setActiveTabKey}
        status={
          error ? <span className="text-[var(--aseel-danger)]">{error}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="aseel-status-item">{isSupplier ? 'مورد' : 'عميل'}{profile ? ` · الرصيد ${profile.balance} ${profile.balance_side}` : ''}</span>
        }
      >
        <></>
      </AseelDocumentShell>
      <StatementDetailsModal movement={detailRow} onClose={() => setDetailRow(null)} />
    </div>
  );
};
