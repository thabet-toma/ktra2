import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Pencil } from 'lucide-react';
import { apiGetObject } from '../../services/restApi';
import { formatMoney, formatQuantity } from '../../utils/formatNumber';
import { formatDateLocalized, todayIso } from '../../utils/formatDate';
import { isReservationActive } from '../../utils/documentBadges';
import { resolveTenantId } from '../../utils/tenantContext';
import { KitDocumentShell, KitTab } from '../kit';
import { LedgerTable, DocRefCell, type LedgerColumn } from '../shared/LedgerTable';
import { PaymentStatusBadge, type InvoicePaymentStatus } from '../shared/PaymentStatusBadge';
import { CustomerPriceListTab } from './CustomerPriceListTab';
import { CustomerNotesTab } from './CustomerNotesTab';
import { StatementDetailsModal } from './StatementDetailsModal';
import { PartnerNoteAlert } from './PartnerNoteAlert';
import { PartnerEditorModal } from './PartnerEditorModal';
import { EntityActivityLog } from '../activity/EntityActivityLog';
import {
  referenceTypeLabel, clarifyStatementDescription, statementToneRowClass,
} from '../../utils/entityLinks';
import { clientLogger } from '../../services/logger';
import { NewPaymentModal } from '../sales/SalesCustomerPaymentsPage';
import { NewSupplierPaymentModal } from '../sales/NewSupplierPaymentModal';
import { VoucherAllocationModal } from '../shared/VoucherAllocationModal';
import {
  listCustomerPayments,
  getAgingReport,
  listQuotations,
  listSalesOrders,
  type SalesQuotationRow,
  type SalesOrderRow,
} from '../../services/salesApi';
import { purchaseInvoiceApi } from '../../services/purchaseInvoiceApi';
import { useAppBack } from '../../hooks/useAppBack';

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
  bank_accounts?: Array<{
    id: number;
    bank_name: string;
    account_number: string;
    branch_name?: string | null;
    iban?: string | null;
    currency?: number | null;
    is_active: boolean;
    is_default: boolean;
  }>;
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
  /** THA-128: الرصيد قبل أثر هذه الحركة — لقطةٌ من حلقة الكشف نفسها. */
  balance_before?: string;
  /** رقم المستند حين تكون الحركة فاتورة. */
  document_number?: string | null;
  /** مفتاح الربط: الفاتورة وسندها يتشاركانه ⇒ يُعرَضان متجاورين بإطار واحد. */
  link_key?: string | null;
  link_label?: string | null;
  link_count?: number;
}

/** حركات مخزون مستندٍ واحد، كما يجمعها الخادم تحت المستند المسبِّب. */
interface StockMovementGroup {
  reference_type: string | null;
  reference_id: number | null;
  movements: Array<{
    id: number;
    date: string | null;
    movement_type_label: string;
    product_name: string;
    warehouse: string | null;
    qty_in: string;
    qty_out: string;
    running_balance: string;
  }>;
}

/** سند «على الحساب» موحَّد الشكل بين العميل (قبض) والمورد (صرف). */
type OnAccountVoucherRow = {
  id: number;
  payment_date: string;
  amount: string;
  is_posted: boolean;
  unallocated_amount?: string;
};

interface InvoiceRow {
  document_type: string;
  document_id: number;
  document_number: string;
  date: string | null;
  grand_total: string;
  is_posted: boolean;
  amount_paid: string;
  remaining_balance: string;
  payment_status: InvoicePaymentStatus;
  payment_status_display: string;
}

const PAGE = 50;
type StatementOrdering = 'newest' | 'oldest';

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
  // كشف الحساب يُفتح في تبويب جديد من الفواتير والقوائم، فبلا سابقة
  // تُعاد الضغطة إلى «دليل الأطراف» بدل أن تصطدم بجدار.
  const back = useAppBack('/partners-directory', 'دليل الأطراف');
  // تبويب مُتحكَّم به: يبدأ من ?tab=، ويُتجاوَز بجسر إشعار التذكير (sessionStorage).
  const [activeTabKey, setActiveTabKey] = useState<string | undefined>(initialTab);
  const [focusNoteId, setFocusNoteId] = useState<string | null>(null);
  // T-ORDERS: عروض الزبون وطلبياته داخل كرته.
  const [partnerQuotes, setPartnerQuotes] = useState<SalesQuotationRow[]>([]);
  const [partnerOrders, setPartnerOrders] = useState<SalesOrderRow[]>([]);
  const [partner, setPartner] = useState<PartnerApi | null>(null);
  const [profile, setProfile] = useState<PartnerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // statement (party ledger) — paginated
  const [stmt, setStmt] = useState<{ rows: StatementRow[]; count: number }>({ rows: [], count: 0 });
  const [stmtOffset, setStmtOffset] = useState(0);
  /* THA-128 — تبويب «المال»: حركات التسوية وحدها من الكشف نفسه (المصدر ذاته،
     فلا معادلة ثانية للرصيد)، ومعها حركات المخزون تحت مستندها المسبِّب. */
  const [money, setMoney] = useState<{ rows: StatementRow[]; count: number }>({ rows: [], count: 0 });
  const [moneyOffset, setMoneyOffset] = useState(0);
  const [moneyLoading, setMoneyLoading] = useState(false);
  const [stockGroups, setStockGroups] = useState<StockMovementGroup[]>([]);
  const [stockLoading, setStockLoading] = useState(false);
  const [stmtLoading, setStmtLoading] = useState(false);
  const [stmtOrdering, setStmtOrdering] = useState<StatementOrdering>('newest');
  // ربط الفاتورة بسندها: يجمع الحركتين متجاورتين داخل إطار واحد (ضمن الصفحة).
  const [stmtGrouped, setStmtGrouped] = useState(true);

  // تفاصيل حركة كشف الحساب (نافذة)
  const [detailRow, setDetailRow] = useState<StatementRow | null>(null);

  // invoices
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);
  const [showReceiptModal, setShowReceiptModal] = useState(false);
  // سند صرف سريع للمورد (مرآة سند القبض للعميل).
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  // نيّة مؤجّلة من قائمة زر اليمين العامّة (سند قبض/صرف) — تُطبَّق بعد تحميل الشريك.
  const [pendingCtxAction, setPendingCtxAction] = useState<string | null>(null);
  const [activityRefreshKey, setActivityRefreshKey] = useState(0);
  const [profileRefreshKey, setProfileRefreshKey] = useState(0);
  // T-ONACC: سندات قبض هذا العميل التي بقي فيها رصيد «على الحساب» غير موزَّع —
  // تُتيح التوزيع على الفواتير من داخل البطاقة بلا الذهاب لصفحة الدفعات.
  const [onAccountPayments, setOnAccountPayments] = useState<OnAccountVoucherRow[]>([]);
  const [showAllocPicker, setShowAllocPicker] = useState(false);
  const [allocTarget, setAllocTarget] = useState<OnAccountVoucherRow | null>(null);
  const [allocDocs, setAllocDocs] = useState<Array<{ id: number; label: string; remaining: string }>>([]);
  const [allocError, setAllocError] = useState<string | null>(null);
  const [paymentsRefreshKey, setPaymentsRefreshKey] = useState(0);

  const tenantId = useMemo(() => resolveTenantId(), []);
  const isSupplier = (partner?.partner_type || '').toLowerCase() === 'supplier';
  const receiptPartner = useMemo(
    () => partner ? { id: partner.id, name: partner.name } : null,
    [partner],
  );

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
  }, [id, profileRefreshKey, tenantId]);

  // T-ORDERS: عروض هذا الزبون وطلبياته (تاب «العروض والطلبيات» في كرته).
  useEffect(() => {
    if (!id || isSupplier) { setPartnerQuotes([]); setPartnerOrders([]); return; }
    let alive = true;
    Promise.all([
      listQuotations().then((rows) => (rows || []).filter((q) => String(q.customer) === String(id))),
      listSalesOrders({ customer: id }),
    ])
      .then(([quotes, orders]) => {
        if (!alive) return;
        setPartnerQuotes(quotes);
        setPartnerOrders(orders || []);
      })
      .catch(() => { if (alive) { setPartnerQuotes([]); setPartnerOrders([]); } });
    return () => { alive = false; };
  }, [id, isSupplier]);

  // T-ONACC: جلب السندات غير الموزَّعة لهذا الطرف — قبض للعميل وصرف للمورد
  // (لعرض زر «توزيع على الفواتير» بقيمة الرصيد على الحساب).
  useEffect(() => {
    if (!id) { setOnAccountPayments([]); return; }
    let alive = true;
    const load = isSupplier
      ? purchaseInvoiceApi.listSupplierPayments(id).then((rows) =>
          (rows || []).map((p) => ({
            id: p.id,
            payment_date: p.payment_date,
            amount: p.amount,
            is_posted: p.is_posted,
            unallocated_amount: p.unallocated_amount,
          })),
        )
      : listCustomerPayments({ partner: id, page: 1, page_size: 200 }).then((rows) =>
          (rows || []).map((p) => ({
            id: p.id,
            payment_date: p.payment_date,
            amount: p.amount,
            is_posted: p.is_posted,
            unallocated_amount: p.unallocated_amount,
          })),
        );
    load
      .then((rows) => {
        if (!alive) return;
        setOnAccountPayments(
          rows.filter((p) => p.is_posted && Number(p.unallocated_amount ?? 0) > 0.009),
        );
      })
      .catch(() => { if (alive) setOnAccountPayments([]); });
    return () => { alive = false; };
  }, [id, isSupplier, paymentsRefreshKey]);

  const totalOnAccount = useMemo(
    () => onAccountPayments.reduce((s, p) => s + Number(p.unallocated_amount ?? 0), 0),
    [onAccountPayments],
  );

  /** يفتح نافذة التوزيع (مباشرةً إن كان سنداً واحداً، وإلا قائمة اختيار). */
  const openAllocation = useCallback(async () => {
    setAllocError(null);
    try {
      if (isSupplier) {
        // فواتير الشراء المفتوحة لهذا المورد.
        const rows = await purchaseInvoiceApi.list({
          partner: String(id), is_posted: 'true', page: '1', page_size: '200',
        }) as Array<{ id: number; invoice_number?: string; remaining_balance?: string }>;
        setAllocDocs(
          (rows || [])
            .filter((inv) => Number(inv.remaining_balance ?? 0) > 0.009)
            .map((inv) => ({
              id: inv.id,
              label: inv.invoice_number || `#${inv.id}`,
              remaining: String(inv.remaining_balance ?? '0'),
            })),
        );
      } else {
        const rows = await getAgingReport();
        setAllocDocs(
          (rows || [])
            .filter((a) => a.customer_id === Number(id))
            .map((a) => ({
              id: a.invoice_id,
              label: a.invoice_number || `#${a.invoice_id}`,
              remaining: a.remaining,
            })),
        );
      }
      if (onAccountPayments.length === 1) {
        setAllocTarget(onAccountPayments[0]);
      } else {
        setShowAllocPicker(true);
      }
      clientLogger.info("partner.payment_allocation_open");
    } catch (e) {
      setAllocError(e instanceof Error ? e.message : 'تعذّر جلب الفواتير المفتوحة');
    }
  }, [id, isSupplier, onAccountPayments]);

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
      // جسر قائمة زر اليمين: نيّة سند قبض/صرف (تُطبَّق بعد تحميل الشريك ومطابقة نوعه).
      const ctxAction = sessionStorage.getItem('ktra_partner_action');
      if (ctxAction) {
        setPendingCtxAction(ctxAction);
        sessionStorage.removeItem('ktra_partner_action');
      }
    } catch { /* خاصية خاصة */ }
  }, [location.key]);

  // تطبيق نيّة قائمة زر اليمين بعد تحميل الشريك — receipt للعميل، payment للمورد.
  useEffect(() => {
    if (!partner || !pendingCtxAction) return;
    if (pendingCtxAction === 'receipt' && !isSupplier) setShowReceiptModal(true);
    if (pendingCtxAction === 'payment' && isSupplier) setShowPaymentModal(true);
    setPendingCtxAction(null);
  }, [partner, pendingCtxAction, isSupplier]);

  const loadStatement = useCallback(
    (offset: number) => {
      if (!id) return;
      setStmtLoading(true);
      apiGetObject<{ results: StatementRow[]; count: number }>(
        `partners/${id}/statement/?limit=${PAGE}&offset=${offset}&ordering=${stmtOrdering}`,
        { tenantId },
      )
        .then((d) => setStmt({ rows: d.results, count: d.count }))
        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setStmtLoading(false));
    },
    [id, tenantId, stmtOrdering],
  );

  useEffect(() => {
    loadStatement(stmtOffset);
  }, [loadStatement, stmtOffset]);

  // تبويب «المال»: نفس نقطة الكشف بـ only_payments — الرصيد قبل/بعد يصل محسوباً
  // على الحساب كلّه، فما يُعرض هنا يطابق كشف الحساب في اللحظات نفسها.
  useEffect(() => {
    if (!id) return;
    setMoneyLoading(true);
    apiGetObject<{ results: StatementRow[]; count: number }>(
      `partners/${id}/statement/?limit=${PAGE}&offset=${moneyOffset}&ordering=${stmtOrdering}&only_payments=true`,
      { tenantId },
    )
      .then((d) => setMoney({ rows: d.results, count: d.count }))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setMoneyLoading(false));
  }, [id, tenantId, stmtOrdering, moneyOffset, paymentsRefreshKey]);

  useEffect(() => {
    if (!id) return;
    setStockLoading(true);
    apiGetObject<{ results: StockMovementGroup[] }>(
      `partners/${id}/stock-movements/?limit=${PAGE}`,
      { tenantId },
    )
      .then((d) => setStockGroups(Array.isArray(d.results) ? d.results : []))
      .catch(() => setStockGroups([]))
      .finally(() => setStockLoading(false));
  }, [id, tenantId]);

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
    // paymentsRefreshKey: يُعيد الجلب بعد توزيع سند على الفواتير (تغيّر المدفوع/المتبقي).
  }, [id, tenantId, paymentsRefreshKey]);

  const stmtColumns: LedgerColumn<StatementRow>[] = [
    { key: 'date', header: 'التاريخ', render: (r) => formatDateLocalized(r.date) || '—' },
    {
      key: 'reference',
      header: 'الحركة',
      render: (r) => (
        <div className="flex flex-col gap-0.5">
          <DocRefCell
            referenceType={r.reference_type}
            referenceId={r.reference_id}
            label={`${referenceTypeLabel(r.reference_type)}${
              r.document_number
                ? ` ${r.document_number}`
                : r.reference_id != null ? ` #${r.reference_id}` : ''
            }`}
          />
          {/* السند يعلن الفاتورة التي وُزّع عليها — الربط ظاهر ولو تفرّقت الصفحة. */}
          {!r.document_number && r.link_label && (
            <span className="text-[10px] text-[var(--ktra-ink-soft)]">
              ↔ مقابل {r.link_label}
            </span>
          )}
        </div>
      ),
    },
    { key: 'description', header: 'البيان', render: (r) => clarifyStatementDescription(r.reference_type, r.description) || '—' },
    { key: 'debit', header: 'مدين (Dr)', align: 'right', render: (r) => <span className="ktra-num">{r?.debit ?? ''}</span> },
    { key: 'credit', header: 'دائن (Cr)', align: 'right', render: (r) => <span className="ktra-num">{r?.credit ?? ''}</span> },
    { key: 'running_balance', header: 'الرصيد', align: 'right', render: (r) => <b className="ktra-num">{r?.running_balance ?? ''}</b> },
    {
      key: 'details',
      header: 'تفاصيل',
      align: 'center',
      render: (r) => (
        <button
          type="button"
          onClick={() => setDetailRow(r)}
          className="text-[var(--ktra-accent,#2563eb)] underline hover:opacity-80"
        >
          تفاصيل
        </button>
      ),
    },
  ];

  const moneyColumns: LedgerColumn<StatementRow>[] = [
    { key: 'date', header: 'التاريخ', render: (r) => formatDateLocalized(r.date) || '—' },
    {
      key: 'reference',
      header: 'الحركة',
      render: (r) => (
        <DocRefCell
          referenceType={r.reference_type}
          referenceId={r.reference_id}
          label={`${referenceTypeLabel(r.reference_type)}${
            r.reference_id != null ? ` #${r.reference_id}` : ''
          }`}
        />
      ),
    },
    { key: 'debit', header: 'مدين (Dr)', align: 'right', render: (r) => <span className="ktra-num">{r?.debit ?? ''}</span> },
    { key: 'credit', header: 'دائن (Cr)', align: 'right', render: (r) => <span className="ktra-num">{r?.credit ?? ''}</span> },
    {
      key: 'balance_before',
      header: 'الرصيد قبل',
      align: 'right',
      render: (r) => <span className="ktra-num">{formatMoney(r?.balance_before ?? '')}</span>,
    },
    {
      key: 'balance_after',
      header: 'الرصيد بعد',
      align: 'right',
      render: (r) => <b className="ktra-num">{formatMoney(r?.running_balance ?? '')}</b>,
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
    { key: 'date', header: 'التاريخ', render: (r) => formatDateLocalized(r.date) || '—' },
    {
      key: 'grand_total',
      header: 'الإجمالي',
      align: 'center',
      render: (r) => <span className="ktra-num">{formatMoney(r.grand_total)}</span>,
    },
    {
      key: 'amount_paid',
      header: 'المدفوع',
      align: 'center',
      render: (r) => <span className="ktra-num">{formatMoney(r.amount_paid ?? 0)}</span>,
    },
    {
      key: 'remaining_balance',
      header: 'المتبقي',
      align: 'center',
      render: (r) => (
        <b className="ktra-num">{formatMoney(r.remaining_balance ?? 0)}</b>
      ),
    },
    {
      key: 'payment_status',
      header: 'حالة الدفع',
      align: 'center',
      render: (r) => (
        <PaymentStatusBadge status={r.payment_status} label={r.payment_status_display} />
      ),
    },
    {
      key: 'is_posted',
      header: 'الحالة',
      align: 'center',
      render: (r) => (r.is_posted ? 'مرحّلة' : 'مسودة'),
    },
  ];

  const Kpi: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
    <div className="p-3 border border-[var(--ktra-border)] rounded">
      <div className="text-xs text-[var(--ktra-ink-soft)]">{label}</div>
      <div className="text-lg font-bold text-[var(--ktra-ink)]">{value}</div>
    </div>
  );

  const tabs: KitTab[] = [
    {
      key: 'details',
      label: 'التفاصيل',
      content: (
        <div className="p-4 grid grid-cols-2 gap-4 text-sm">
          {partner && (
            <>
              <div className="col-span-2 flex justify-end">
                <button
                  type="button"
                  className="ktra-toolbtn"
                  onClick={() => {
                    setActiveTabKey('edit');
                    clientLogger.info('partner.edit_card_open', { partner_id: id });
                  }}
                >
                  <Pencil className="h-3.5 w-3.5" /> تعديل البطاقة
                </button>
              </div>
              <div><span className="text-[var(--ktra-ink-soft)]">الاسم:</span> <b>{partner.name}</b></div>
              <div><span className="text-[var(--ktra-ink-soft)]">الاسم القانوني:</span> <b>{partner.legal_name || '—'}</b></div>
              <div><span className="text-[var(--ktra-ink-soft)]">النوع:</span> <b>{isSupplier ? 'مورد' : partner.partner_type === 'Customer' ? 'عميل' : partner.partner_type}</b></div>
              <div><span className="text-[var(--ktra-ink-soft)]">الهاتف:</span> <b>{partner.phone || '—'}</b></div>
              <div><span className="text-[var(--ktra-ink-soft)]">البريد الإلكتروني:</span> <b>{partner.email || '—'}</b></div>
              <div><span className="text-[var(--ktra-ink-soft)]">الرقم الضريبي:</span> <b>{partner.tax_number || '—'}</b></div>
              <div><span className="text-[var(--ktra-ink-soft)]">حد الائتمان:</span> <b>{partner.credit_limit || '—'}</b></div>
              <div className="col-span-2"><span className="text-[var(--ktra-ink-soft)]">العنوان:</span> <b>{[partner.street_address, partner.city, partner.state_or_province, partner.country].filter(Boolean).join(', ') || '—'}</b></div>
              <div className="col-span-2 mt-2 border-t border-[var(--ktra-border)] pt-3">
                <div className="mb-2 font-bold">الحسابات البنكية</div>
                {partner.bank_accounts?.length ? (
                  <div className="grid gap-2 md:grid-cols-2">
                    {partner.bank_accounts.map((account) => (
                      <div key={account.id} className="rounded border border-[var(--ktra-border)] bg-[var(--ktra-panel)] p-2">
                        <div className="flex items-center justify-between">
                          <b>{account.bank_name}</b>
                          {account.is_default && <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] text-blue-700">افتراضي</span>}
                        </div>
                        <div className="mt-1 font-mono" dir="ltr">{account.account_number}</div>
                        <div className="text-xs text-[var(--ktra-ink-soft)]">{account.branch_name || '—'}{account.iban ? ` · IBAN ${account.iban}` : ''}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-[var(--ktra-ink-soft)]">لا توجد حسابات بنكية محفوظة.</span>
                )}
              </div>
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
            <span className="text-[var(--ktra-ink-soft)]">جاري التحميل…</span>
          )}
        </div>
      ),
    },
    ...(id && partner
      ? [{
          key: 'edit',
          label: 'تعديل البطاقة',
          content: (
            <div className="p-4">
              <PartnerEditorModal
                open
                embedded
                partnerId={Number(id)}
                onClose={() => setActiveTabKey('details')}
                onSaved={() => {
                  setProfileRefreshKey((current) => current + 1);
                  setActivityRefreshKey((current) => current + 1);
                  setActiveTabKey('details');
                }}
              />
            </div>
          ),
        } as KitTab]
      : []),
    {
      key: 'statement',
      label: 'كشف الحساب',
      content: (
        <div className="p-2">
          <div className="mb-3 flex flex-wrap items-center justify-end gap-3">
            {/* مفتاح الألوان: ما يزيد الذمة أحمر وما يسدّدها أخضر. */}
            <div className="me-auto flex items-center gap-3 text-xs text-[var(--ktra-ink-soft)]">
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded-sm border border-[var(--ktra-border)] bg-red-50 dark:bg-red-900/20" />
                {isSupplier ? 'فاتورة شراء' : 'فاتورة بيع'}
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded-sm border border-[var(--ktra-border)] bg-emerald-50 dark:bg-emerald-900/20" />
                {isSupplier ? 'سند صرف' : 'سند قبض'}
              </span>
            </div>
            <label className="flex items-center gap-1.5 text-sm text-[var(--ktra-ink-soft)]">
              <input
                type="checkbox"
                checked={stmtGrouped}
                onChange={(event) => {
                  setStmtGrouped(event.target.checked);
                  clientLogger.info("partner.statement_grouping_changed", {
                    grouped: event.target.checked,
                  });
                }}
              />
              ربط الفاتورة بسندها
            </label>
            <label htmlFor="partner-statement-ordering" className="text-sm text-[var(--ktra-ink-soft)]">
              ترتيب الحركات:
            </label>
            <select
              id="partner-statement-ordering"
              value={stmtOrdering}
              onChange={(event) => {
                const ordering = event.target.value as StatementOrdering;
                setStmtOrdering(ordering);
                setStmtOffset(0);
                clientLogger.info("partner.statement_order_changed", { ordering });
              }}
              className="rounded-lg border border-[var(--ktra-border)] bg-[var(--ktra-panel)] px-3 py-2 text-sm text-[var(--ktra-ink)]"
            >
              <option value="newest">الأحدث أولاً</option>
              <option value="oldest">الأقدم أولاً</option>
            </select>
          </div>
          {stmtGrouped && (
            <div className="mb-2 text-[11px] text-[var(--ktra-ink-soft)]">
              الحركات المترابطة مجمَّعة داخل إطار واحد؛ عمود «الرصيد» يبقى الرصيد الجاري
              زمنياً لكل حركة. الربط ضمن الصفحة المعروضة.
            </div>
          )}
          <LedgerTable<StatementRow>
            columns={stmtColumns}
            rows={stmt.rows}
            loading={stmtLoading}
            count={stmt.count}
            limit={PAGE}
            offset={stmtOffset}
            onPage={setStmtOffset}
            rowClassName={(r) => statementToneRowClass(r.reference_type)}
            rowGroupKey={stmtGrouped ? (r) => r.link_key : undefined}
            emptyText="لا توجد حركات على حساب هذا الشريك."
            summaryRow={
              (stmt?.rows && stmt.rows.length > 0) ? (
                <tr className="bg-[#e6e4d5] font-bold border-t-2 border-[var(--ktra-border)]">
                  <td colSpan={3} className="px-2 py-2 text-right">الإجمالي (هذه الصفحة):</td>
                  <td className="px-2 py-2 text-right ktra-num">
                    {formatMoney(stmt.rows.reduce((sum, r) => {
                      const val = parseFloat(String(r?.debit || "0").replace(/,/g, ''));
                      return sum + (isNaN(val) ? 0 : val);
                    }, 0))}
                  </td>
                  <td className="px-2 py-2 text-right ktra-num">
                    {formatMoney(stmt.rows.reduce((sum, r) => {
                      const val = parseFloat(String(r?.credit || "0").replace(/,/g, ''));
                      return sum + (isNaN(val) ? 0 : val);
                    }, 0))}
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
      key: 'money',
      label: 'المال',
      content: (
        <div className="p-2">
          <div className="mb-2 text-[11px] text-[var(--ktra-ink-soft)]">
            حركات التسوية وحدها (بلا الفاتورة نفسها)، وكلٌّ منها برصيد الحساب قبلها
            وبعدها. الرصيدان محسوبان على الحساب كلّه لا على المعروض، فيطابقان كشف
            الحساب في اللحظات نفسها.
          </div>
          <LedgerTable<StatementRow>
            columns={moneyColumns}
            rows={money.rows}
            loading={moneyLoading}
            count={money.count}
            limit={PAGE}
            offset={moneyOffset}
            onPage={setMoneyOffset}
            rowClassName={(r) => statementToneRowClass(r.reference_type)}
            emptyText="لا توجد حركات مالية على حساب هذا الشريك بعد."
          />

          <h3 className="mt-5 mb-2 text-sm font-bold text-[var(--ktra-ink)]">
            حركات المخزون المرتبطة
          </h3>
          {stockLoading ? (
            <div className="py-4 text-sm text-[var(--ktra-ink-soft)]">جارٍ التحميل…</div>
          ) : stockGroups.length === 0 ? (
            <div className="py-4 text-sm text-[var(--ktra-ink-soft)]">
              لا توجد حركات مخزون مرتبطة بمستندات هذا الشريك.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {stockGroups.map((g) => (
                <div
                  key={`${g.reference_type}:${g.reference_id}`}
                  className="rounded-lg border border-[var(--ktra-border)] p-2"
                >
                  <div className="mb-1 text-xs font-bold">
                    <DocRefCell
                      referenceType={g.reference_type}
                      referenceId={g.reference_id}
                      label={`${referenceTypeLabel(g.reference_type)}${
                        g.reference_id != null ? ` #${g.reference_id}` : ''
                      }`}
                    />
                  </div>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-[var(--ktra-ink-soft)]">
                        <th className="px-2 py-1 text-right">التاريخ</th>
                        <th className="px-2 py-1 text-right">الصنف</th>
                        <th className="px-2 py-1 text-right">الحركة</th>
                        <th className="px-2 py-1 text-right">المستودع</th>
                        <th className="px-2 py-1 text-right">وارد</th>
                        <th className="px-2 py-1 text-right">صادر</th>
                        <th className="px-2 py-1 text-right">الرصيد بعدها</th>
                      </tr>
                    </thead>
                    <tbody>
                      {g.movements.map((m) => (
                        <tr key={m.id}>
                          <td className="px-2 py-1">{formatDateLocalized(m.date) || '—'}</td>
                          <td className="px-2 py-1">{m.product_name}</td>
                          <td className="px-2 py-1">{m.movement_type_label}</td>
                          <td className="px-2 py-1">{m.warehouse || '—'}</td>
                          <td className="px-2 py-1 ktra-num">{formatQuantity(m.qty_in)}</td>
                          <td className="px-2 py-1 ktra-num">{formatQuantity(m.qty_out)}</td>
                          <td className="px-2 py-1 ktra-num font-bold">{formatQuantity(m.running_balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
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
    // T-ORDERS: عروض الزبون وطلبياته في كرته — مصدرهما نفس عقود الشاشتين.
    ...(!isSupplier && id
      ? [{
          key: 'quotes_orders',
          label: 'العروض والطلبيات',
          content: (
            <div className="p-3 space-y-4">
              <div>
                <div className="mb-1 font-bold text-[var(--ktra-ink)]">عروض الأسعار</div>
                {partnerQuotes.length === 0 ? (
                  <div className="text-xs text-[var(--ktra-ink-soft)]">لا عروض لهذا الزبون.</div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="text-[var(--ktra-ink-soft)]">
                      <tr>
                        <th className="p-1 text-right">الرقم</th>
                        <th className="p-1 text-right">التاريخ</th>
                        <th className="p-1 text-right">صالح حتى</th>
                        <th className="p-1 text-left">الإجمالي</th>
                        <th className="p-1 text-center">الحالة</th>
                      </tr>
                    </thead>
                    <tbody>
                      {partnerQuotes.map((q) => (
                        <tr key={q.id} className="border-t border-[var(--ktra-border)]">
                          <td className="p-1">{q.quotation_number}</td>
                          <td className="p-1">{formatDateLocalized(q.quotation_date)}</td>
                          <td className="p-1">{formatDateLocalized(q.valid_until) || '—'}</td>
                          <td className="p-1 text-left">{formatMoney(q.grand_total)}</td>
                          <td className="p-1 text-center">{q.status_display || q.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div>
                <div className="mb-1 font-bold text-[var(--ktra-ink)]">الطلبيات</div>
                {partnerOrders.length === 0 ? (
                  <div className="text-xs text-[var(--ktra-ink-soft)]">لا طلبيات لهذا الزبون.</div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="text-[var(--ktra-ink-soft)]">
                      <tr>
                        <th className="p-1 text-right">الرقم</th>
                        <th className="p-1 text-right">التاريخ</th>
                        <th className="p-1 text-right">الحجز</th>
                        <th className="p-1 text-left">الإجمالي</th>
                        <th className="p-1 text-left">العربون</th>
                        <th className="p-1 text-center">الحالة</th>
                      </tr>
                    </thead>
                    <tbody>
                      {partnerOrders.map((o) => (
                        <tr key={o.id} className="border-t border-[var(--ktra-border)]">
                          <td className="p-1">{o.order_number}</td>
                          <td className="p-1">{formatDateLocalized(o.order_date)}</td>
                          {/* T-RESERVE: التاريخ وحده كان يُقرأ «محجوز» على طلبية
                              ملغاة/محوَّلة أو انتهت مدّتها — الآن الحالة صريحة. */}
                          <td className="p-1">
                            {isReservationActive(o.status, o.reserved_until, todayIso()) ? (
                              <span className="font-semibold text-[var(--ktra-warn)]">
                                محجوز حتى {formatDateLocalized(o.reserved_until)}
                              </span>
                            ) : (
                              <span className="text-[var(--ktra-ink-soft)]">
                                {o.reserved_until
                                  ? `انتهى الحجز (${formatDateLocalized(o.reserved_until)})`
                                  : 'بلا حجز'}
                              </span>
                            )}
                          </td>
                          <td className="p-1 text-left">{formatMoney(o.grand_total)}</td>
                          <td className="p-1 text-left">{formatMoney(o.deposit_amount)}</td>
                          <td className="p-1 text-center">{o.status_display || o.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          ),
        } as KitTab]
      : []),
    ...(id
      ? [{
          key: 'activity',
          label: 'سجل النشاطات',
          content: (
            <div className="p-2">
              <EntityActivityLog
                partnerId={id}
                title="سجل نشاطات المستخدمين لهذه الجهة"
                defaultOpen
                refreshKey={activityRefreshKey}
              />
            </div>
          ),
        } as KitTab]
      : []),
    // DEF-004: عرض السعر — مبيعات فقط (للعملاء، لا للموردين).
    ...(!isSupplier && id
      ? [{
          key: 'price_list',
          label: 'عرض السعر',
          content: <CustomerPriceListTab customerId={id} />,
        } as KitTab]
      : []),
    // ملاحظات الطرف (CRM) — لكل الأطراف: العاجلة منها تُنبّه عند أي معاملة له.
    ...(id
      ? [{
          key: 'customer_notes',
          label: isSupplier ? 'ملاحظات المورد' : 'ملاحظات الزبون',
          content: <CustomerNotesTab customerId={id} focusNoteId={focusNoteId} />,
        } as KitTab]
      : []),
  ];

  return (
    <div className="min-h-[calc(100vh-5rem)]">
      <PartnerNoteAlert partnerId={id} className="mb-2" />
      <KitDocumentShell
        title={partner ? `كشف حساب: ${partner.name}` : 'جاري التحميل...'}
        actions={[
          { key: 'back', label: back.label === 'رجوع' ? 'عودة' : back.label, onClick: back.go },
          // التعديل كان تبويباً وحيداً بين تسعة تبويبات على صفحة عنوانها «كشف
          // حساب»، فلا يُعثر عليه — والأمر مكانه شريط الأوامر كبقية الإجراءات.
          ...(id && partner
            ? [{
                key: 'edit-card',
                label: 'تعديل البطاقة',
                onClick: () => {
                  setActiveTabKey('edit');
                  clientLogger.info('partner.edit_card_open', { partner_id: id });
                },
              }]
            : []),
          // T-P2: سند قبض سريع من كشف الحساب — العميل مُعبّأ مسبقاً.
          ...(!isSupplier && id
            ? [
                {
                  key: 'new-receipt',
                  label: 'سند قبض جديد',
                  onClick: () => {
                    setShowReceiptModal(true);
                    clientLogger.info("partner.customer_payment_open");
                  },
                  separatorBefore: true,
                },
                // T-ONACC: يظهر فقط حين يوجد رصيد سند غير موزَّع («على الحساب»).
                ...(totalOnAccount > 0.009
                  ? [{
                      key: 'allocate-payment',
                      label: `توزيع على الفواتير (${formatMoney(totalOnAccount)})`,
                      onClick: () => { void openAllocation(); },
                    }]
                  : []),
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
          // سند صرف سريع + فاتورة شراء للمورد — مرآة أزرار العميل (المورد مُعبّأ مسبقاً).
          ...(isSupplier && id
            ? [
                {
                  key: 'new-payment',
                  label: 'سند صرف جديد',
                  onClick: () => {
                    setShowPaymentModal(true);
                    clientLogger.info("partner.supplier_payment_open");
                  },
                  separatorBefore: true,
                },
                // T-ONACC: يظهر فقط حين يوجد رصيد سند صرف غير موزَّع (لنا عند المورد).
                ...(totalOnAccount > 0.009
                  ? [{
                      key: 'allocate-payment',
                      label: `توزيع على الفواتير (${formatMoney(totalOnAccount)})`,
                      onClick: () => { void openAllocation(); },
                    }]
                  : []),
                {
                  key: 'new-purchase',
                  label: 'فاتورة مشتريات جديدة',
                  onClick: () => navigate('/purchase-invoices/new'),
                },
              ]
            : []),
        ]}
        tabs={tabs}
        activeTab={activeTabKey}
        onTabChange={setActiveTabKey}
        status={
          error || allocError ? <span className="text-[var(--ktra-danger)]">{error || allocError}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="ktra-status-item">{isSupplier ? 'مورد' : 'عميل'}{profile ? ` · الرصيد ${profile.balance} ${profile.balance_side}` : ''}</span>
        }
      >
        <></>
      </KitDocumentShell>
      <StatementDetailsModal movement={detailRow} onClose={() => setDetailRow(null)} />
      {showReceiptModal && receiptPartner && (
        <NewPaymentModal
          initialPartner={receiptPartner}
          lockPartner
          onClose={() => setShowReceiptModal(false)}
          onSaved={() => {
            setShowReceiptModal(false);
            setStmtOffset(0);
            loadStatement(0);
            apiGetObject<PartnerProfile>(`partners/${id}/profile/`, { tenantId })
              .then(setProfile)
              .catch((err) => setError(err instanceof Error ? err.message : String(err)));
            setActivityRefreshKey((key) => key + 1);
            setPaymentsRefreshKey((key) => key + 1);
            clientLogger.info("partner.customer_payment_saved");
          }}
        />
      )}
      {/* T-ONACC: اختيار السند حين يوجد أكثر من رصيد «على الحساب» لهذا العميل. */}
      {showAllocPicker && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setShowAllocPicker(false); }}
        >
          {/* بلا `data-skin` محليّ: محدِّد التوكنات الكلاسيكية في `index.css`
              بلا `:root` فوسمُ النافذة كان يُطابقه، فتلبس اللوحة الكلاسيكية
              (حدّ زيتوني وسطح أبيض) داخل الجلد الحديث — وبلا مقابلٍ داكن.
              متغيّرات `--ktra-*` معرَّفة على `<html>` في الجلدين، فالنافذة
              الآن تتبع جلد التطبيق وسمته. */}
          <div
            dir="rtl"
            className="max-h-[80vh] w-full max-w-[520px] overflow-auto rounded-[var(--ktra-radius)] border border-[var(--ktra-border)] bg-[var(--ktra-surface)] p-4"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between border-b border-[var(--ktra-border)] pb-2">
              <h3 className="text-[14px] font-semibold">اختر السند المراد توزيعه</h3>
              <button type="button" className="ktra-toolbtn" onClick={() => setShowAllocPicker(false)}>✕</button>
            </div>
            <table className="ktra-compact-grid w-full text-[12px]">
              <thead className="bg-[var(--ktra-surface-2)]">
                <tr>
                  <th>السند</th>
                  <th>التاريخ</th>
                  <th>المبلغ</th>
                  <th>على الحساب</th>
                  <th className="w-[70px]"></th>
                </tr>
              </thead>
              <tbody>
                {onAccountPayments.map((p) => (
                  <tr key={p.id} className="border-t border-[var(--ktra-border)]">
                    <td>#{p.id}</td>
                    <td>{formatDateLocalized(p.payment_date)}</td>
                    <td className="ktra-num">{formatMoney(p.amount)}</td>
                    <td className="ktra-num text-[var(--ktra-warn)]">
                      {formatMoney(p.unallocated_amount ?? 0)}
                    </td>
                    <td className="text-center">
                      <button
                        type="button"
                        className="ktra-toolbtn text-[11px]"
                        onClick={() => { setAllocTarget(p); setShowAllocPicker(false); }}
                      >
                        توزيع
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {allocTarget && partner && (
        <VoucherAllocationModal
          kind={isSupplier ? 'supplier' : 'customer'}
          voucher={{
            id: allocTarget.id,
            amount: allocTarget.amount,
            unallocated: Number(allocTarget.unallocated_amount ?? 0),
            is_posted: allocTarget.is_posted,
          }}
          partnerLabel={partner.name}
          docs={allocDocs}
          onClose={() => setAllocTarget(null)}
          onSaved={() => {
            setAllocTarget(null);
            setStmtOffset(0);
            loadStatement(0);
            setPaymentsRefreshKey((key) => key + 1);
            setActivityRefreshKey((key) => key + 1);
            clientLogger.info("partner.payment_allocation_saved");
          }}
        />
      )}
      {showPaymentModal && receiptPartner && (
        <NewSupplierPaymentModal
          initialPartner={receiptPartner}
          lockPartner
          onClose={() => setShowPaymentModal(false)}
          onSaved={() => {
            setShowPaymentModal(false);
            setStmtOffset(0);
            loadStatement(0);
            apiGetObject<PartnerProfile>(`partners/${id}/profile/`, { tenantId })
              .then(setProfile)
              .catch((err) => setError(err instanceof Error ? err.message : String(err)));
            setActivityRefreshKey((key) => key + 1);
            clientLogger.info("partner.supplier_payment_saved");
          }}
        />
      )}
    </div>
  );
};
