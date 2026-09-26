import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Pencil } from 'lucide-react';
import { apiGetObject } from '../../services/restApi';
import { formatMoney, formatNumber, formatQuantity } from '../../utils/formatNumber';
import { formatDateLocalized, todayIso } from '../../utils/formatDate';
import { isReservationActive } from '../../utils/documentBadges';
import { relatedInvoiceTypeLabel, stockMovementReferenceLabel } from '../../utils/documentTypeLabels';
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
  withStatementLinkSublines, foldStatementReversals,
  type FoldedStatementRow, type StatementLinkTarget, type StatementReversalPair,
} from '../../utils/entityLinks';
import { clientLogger } from '../../services/logger';
import {
  defaultStatementCurrency, partnerKindFromType, partnerTypeLabel, partnerVoucherDirections,
} from '../../utils/partnerActions';
import { NewPaymentModal } from '../sales/SalesCustomerPaymentsPage';
import { NewSupplierPaymentModal } from '../sales/NewSupplierPaymentModal';
import { VoucherAllocationModal, type AllocatableDoc } from '../shared/VoucherAllocationModal';
import { NoteAllocationModal } from '../shared/NoteAllocationModal';
import {
  listCustomerPayments,
  listCreditDebitNotes,
  getAgingReport,
  listQuotations,
  listSalesOrders,
  type SalesQuotationRow,
  type SalesOrderRow,
} from '../../services/salesApi';
import { purchaseInvoiceApi } from '../../services/purchaseInvoiceApi';
import { useAppBack } from '../../hooks/useAppBack';
import { usePermissions } from '../../contexts/PermissionsContext';

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
  /** الدائن: غير الموزَّع من سنداته + ما زاد على مستحقٍّ لحظة دفعه (بالعملة الأساسية). */
  on_account_payments?: string;
  /** الدائن: ما صار زائداً لأن مستحقّه خُفِّض بعد دفعه («تعديل الاستحقاق»). */
  accrual_surplus?: string;
}

interface StatementRow {
  /** نصّيٌّ للسطر المعلوماتي (`withStatementLinkSublines`) وحده. */
  id: number | string;
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
  /**
   * ‏#214-ب: نوعُ المستند الحقيقيّ (`sale` · `sale_return`).
   *
   * قيدُ المرتجع يحمل `reference_type="SALES_INVOICE"` **كالبيعة حرفاً** لأنّه
   * فعلاً صفُّ `SalesInvoice` بنوعٍ آخر — فبلا هذا الحقل لا تملك الشاشةُ ما
   * تفرّق به، وتكتب اسمَ فاتورة المبيعات على المرتجع.
   */
  reference_kind?: string | null;
  /** مفتاح الربط: الفاتورة وسندها يتشاركانه ⇒ يُعرَضان متجاورين بإطار واحد. */
  link_key?: string | null;
  link_label?: string | null;
  link_count?: number;
  /** سندٌ موزَّع على أكثر من مستند: كل مستندٍ وما وُزِّع عليه — سطرٌ فرعيٌّ في مجموعته. */
  link_targets?: StatementLinkTarget[];
  /** السطر المعلوماتي داخل مجموعة المستند: ما وُزِّع عليه من السند، بلا أثر على الرصيد. */
  info_amount?: string;
  /**
   * «SH-0017 — شحنة رقع» — وسم الشحنة الحيّ من مستند الحركة المرجعي (تخليص، إرسالية،
   * استحقاق شحن، دفعاتها، سند صرفٍ موزَّع عليها). القيد القديم يحمل الرقم وحده.
   */
  shipment_label?: string | null;
  /** الرصيد بلا أزواج «القيد + عكسه» — لقطتا حلقة الخادم نفسها. */
  running_balance_folded?: string;
  balance_before_folded?: string;
  /** رقم قيد الأصل حين يكون السطر طرفاً في «قيد + عكسه» صافيهما صفر. */
  reversal_pair_id?: number | null;
  reversal_pair?: StatementReversalPair | null;
  /** كشف الدولار: سطرٌ بلا مبلغ بالدولار — يُعرض بشيكله ولا يدخل الرصيد. */
  currency_missing?: boolean;
  base_debit?: string;
  base_credit?: string;
}

type StatementDisplayRow = FoldedStatementRow<StatementRow>;

/** سطر فرق الصرف الختامي في كشف الدولار (`_statement_fx` في الخادم). */
interface StatementFx {
  currency: string;
  book_balance: string;
  currency_balance: string;
  rate: string | null;
  rate_source: 'exchange_rate' | 'last_entry' | null;
  revalued_balance: string | null;
  difference: string | null;
}

interface StatementResponse {
  results: StatementRow[];
  count: number;
  currency?: string | null;
  currencies?: string[];
  missing_count?: number;
  missing_base_balance?: string;
  fx?: StatementFx;
}

/** وسم الشحنة تحت البيان — حين لا يحمله نصّ القيد أصلاً (القيود القديمة). */
function StatementShipmentLabel({ row }: { row: StatementRow }) {
  if (!row.shipment_label || (row.description || '').includes(row.shipment_label)) return null;
  return <span className="text-[10px] text-[var(--ktra-ink-soft)]">الشحنة: {row.shipment_label}</span>;
}

/** حركات مخزون مستندٍ واحد، كما يجمعها الخادم تحت المستند المسبِّب. */
interface StockMovementGroup {
  reference_type: string | null;
  reference_id: number | null;
  movements: Array<{
    id: number;
    date: string | null;
    movement_type: string | null;
    movement_type_label: string;
    product_name: string;
    warehouse: string | null;
    qty_in: string;
    qty_out: string;
    running_balance: string;
  }>;
}

/** رصيد «على الحساب» موحَّد الشكل: سند (قبض للعميل، صرف للمورد) أو إشعارٌ مسوٍّ لم يُوزَّع. */
type OnAccountVoucherRow = {
  id: number;
  payment_date: string;
  amount: string;
  is_posted: boolean;
  unallocated_amount?: string;
  source: 'voucher' | 'note';
  /** رقم الإشعار — صفّ المصدر «إشعار». */
  number?: string;
  currency_code?: string | null;
};

interface InvoiceRow {
  document_type: string;
  invoice_kind?: string | null;
  document_id: number;
  document_number: string;
  /** مستحقّات المخلّص/الوكيل/الناقل: الرابط إلى شحنتها (لا شاشة للمستحق وحده). */
  shipment_id?: number | null;
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
  // ISSUE #82: اسم فاتورة المبيعات من المعجم — يتبدّل باسمه البديل في مكتب المحاسبة.
  const { term } = usePermissions();
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
  // «₪ / $»: الكشف بالشيكل (null) أو بالدولار من `amount_currency`.
  const [stmtCurrency, setStmtCurrency] = useState<'USD' | null>(null);
  const [stmtMeta, setStmtMeta] = useState<Omit<StatementResponse, 'results' | 'count'>>({});
  const stmtCurrencyPicked = useRef(false);
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
  // «القيد + عكسه» مطويّان افتراضياً في سطرٍ رماديّ؛ الخيار يعيدهما كاملين بالرصيد الخام.
  const [stmtShowReversals, setStmtShowReversals] = useState(false);
  const [expandedPairs, setExpandedPairs] = useState<ReadonlySet<number>>(() => new Set());
  const toggleReversalPair = useCallback((pairId: number) => {
    setExpandedPairs((prev) => {
      const next = new Set(prev);
      if (next.has(pairId)) next.delete(pairId);
      else next.add(pairId);
      return next;
    });
  }, []);
  // الربط وحده يُظهر أسطر السند الموزَّع الفرعية — بلا ربط لا مجموعة تحويها.
  const stmtDisplayRows = useMemo(() => {
    const rows: StatementDisplayRow[] = stmtShowReversals
      ? stmt.rows
      : foldStatementReversals(stmt.rows, expandedPairs);
    return stmtGrouped ? withStatementLinkSublines(rows) : rows;
  }, [stmt.rows, stmtGrouped, stmtShowReversals, expandedPairs]);
  // مجموع الصفحة: الزوج المطويّ صافيه صفر، فلا يُجمع مدينه ودائنه مرّتين في الذيل.
  const stmtTotalRows = useMemo(
    () => (stmtShowReversals ? stmt.rows : stmt.rows.filter((r) => r.reversal_pair_id == null)),
    [stmt.rows, stmtShowReversals],
  );

  // تفاصيل حركة كشف الحساب (نافذة)
  const [detailRow, setDetailRow] = useState<StatementRow | null>(null);

  // invoices
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);
  const [showReceiptModal, setShowReceiptModal] = useState(false);
  // ردّ فائض العميل نقداً — سند صرف (ردّ) بالنافذة نفسها (`refundMode="refund"`).
  const [showRefundModal, setShowRefundModal] = useState(false);
  // عدد مصادر فائض العميل (سند قبض زائد/إشعار دائن) — يُظهر «سند صرف (ردّ فائض)».
  const [customerSurplusCount, setCustomerSurplusCount] = useState(0);
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
  const [noteAllocTarget, setNoteAllocTarget] = useState<OnAccountVoucherRow | null>(null);
  const [allocDocs, setAllocDocs] = useState<AllocatableDoc[]>([]);
  const [allocError, setAllocError] = useState<string | null>(null);
  const [paymentsRefreshKey, setPaymentsRefreshKey] = useState(0);

  const tenantId = useMemo(() => resolveTenantId(), []);
  // جانب الشراء كلّه لا «مورد» وحده: المخلّص ووكيل الشحن والناقل كانوا يُعامَلون
  // عملاءً هنا («سند قبض» وفواتير بيع). القاعدة نفسها التي تقرؤها قائمة زر اليمين.
  const isSupplier = partnerKindFromType(partner?.partner_type) === 'supplier';
  const voucherDirs = useMemo(
    () => partnerVoucherDirections(partner?.partner_type),
    [partner?.partner_type],
  );
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

  // T-ONACC: جلب السندات غير الموزَّعة لهذا الطرف — قبض للعميل وصرف للمورد — ومعها
  // الإشعارات المسوّية غير الموزَّعة (مدينٌ على دائن، دائنٌ لعميل): رصيدٌ كالسند
  // (لعرض زر «توزيع على الفواتير» بقيمة الرصيد على الحساب).
  useEffect(() => {
    if (!id) { setOnAccountPayments([]); return; }
    let alive = true;
    const vouchers: Promise<OnAccountVoucherRow[]> = isSupplier
      ? purchaseInvoiceApi.listSupplierPayments(id).then((rows) =>
          (rows || []).map((p) => ({
            id: p.id,
            payment_date: p.payment_date,
            amount: p.amount,
            is_posted: p.is_posted,
            unallocated_amount: p.unallocated_amount,
            source: 'voucher' as const,
          })),
        )
      : listCustomerPayments({ partner: id, page: 1, page_size: 200 }).then((rows) =>
          (rows || []).map((p) => ({
            id: p.id,
            payment_date: p.payment_date,
            amount: p.amount,
            is_posted: p.is_posted,
            unallocated_amount: p.unallocated_amount,
            source: 'voucher' as const,
          })),
        );
    const notes: Promise<OnAccountVoucherRow[]> = listCreditDebitNotes(id).then((rows) =>
      (rows || [])
        .filter((n) => n.settles)
        .map((n) => ({
          id: n.id,
          payment_date: n.note_date,
          amount: n.amount,
          is_posted: n.status === 'posted',
          unallocated_amount: n.unallocated_amount,
          source: 'note' as const,
          number: n.note_number,
          currency_code: n.currency_code,
        })),
    );
    Promise.all([vouchers, notes.catch(() => [] as OnAccountVoucherRow[])])
      .then(([voucherRows, noteRows]) => {
        if (!alive) return;
        setOnAccountPayments(
          [...voucherRows, ...noteRows].filter((p) => p.is_posted && Number(p.unallocated_amount ?? 0) > 0.009),
        );
      })
      .catch(() => { if (alive) setOnAccountPayments([]); });
    return () => { alive = false; };
  }, [id, isSupplier, paymentsRefreshKey]);

  useEffect(() => {
    if (!id || isSupplier) { setCustomerSurplusCount(0); return; }
    let alive = true;
    apiGetObject<{ rows: unknown[] }>(`partners/${id}/surplus/`, { tenantId })
      .then((res) => { if (alive) setCustomerSurplusCount((res.rows || []).length); })
      .catch(() => { if (alive) setCustomerSurplusCount(0); });
    return () => { alive = false; };
  }, [id, isSupplier, paymentsRefreshKey, tenantId]);

  const totalOnAccount = useMemo(
    () => onAccountPayments.reduce((s, p) => s + Number(p.unallocated_amount ?? 0), 0),
    [onAccountPayments],
  );

  /** الإشعار يُوزَّع بنافذته (مستندات طرفه من الخادم)، والسند بنافذة السند. */
  const openOnAccountRow = useCallback((row: OnAccountVoucherRow) => {
    if (row.source === 'note') setNoteAllocTarget(row);
    else setAllocTarget(row);
  }, []);

  /** يفتح نافذة التوزيع (مباشرةً إن كان رصيداً واحداً، وإلا قائمة اختيار). */
  const openAllocation = useCallback(async () => {
    setAllocError(null);
    try {
      if (isSupplier) {
        // فواتير الشراء المفتوحة + مستحقّاته اللوجستية (تخليص/شحن/إرسالية).
        setAllocDocs(await purchaseInvoiceApi.supplierAllocatableDocs(id));
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
        openOnAccountRow(onAccountPayments[0]);
      } else {
        setShowAllocPicker(true);
      }
      clientLogger.info("partner.payment_allocation_open");
    } catch (e) {
      setAllocError(e instanceof Error ? e.message : 'تعذّر جلب الفواتير المفتوحة');
    }
  }, [id, isSupplier, onAccountPayments, openOnAccountRow]);

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

  // تطبيق نيّة قائمة زر اليمين بعد تحميل الشريك — ما يسمح به نوعه فقط: صرفٌ للدائن،
  // وقبضٌ للعميل أو للدائن استرداداً.
  useEffect(() => {
    if (!partner || !pendingCtxAction) return;
    const allowed = voucherDirs ? [voucherDirs.primary, voucherDirs.secondary] : [];
    if (pendingCtxAction === 'receipt' && allowed.includes('receipt')) setShowReceiptModal(true);
    if (pendingCtxAction === 'payment' && allowed.includes('payment')) setShowPaymentModal(true);
    setPendingCtxAction(null);
  }, [partner, pendingCtxAction, voucherDirs]);

  const loadStatement = useCallback(
    (offset: number) => {
      if (!id) return;
      setStmtLoading(true);
      apiGetObject<StatementResponse>(
        `partners/${id}/statement/?limit=${PAGE}&offset=${offset}&ordering=${stmtOrdering}${
          stmtCurrency ? `&currency=${stmtCurrency}` : ''}`,
        { tenantId },
      )
        .then(({ results, count, ...meta }) => {
          setStmt({ rows: results, count });
          setStmtMeta(meta);
        })
        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setStmtLoading(false));
    },
    [id, tenantId, stmtOrdering, stmtCurrency],
  );

  // طرفٌ آخر: العملة تُختار له من جديد — وعملاتُ السابق لا تقرّر افتراضيَّه.
  useEffect(() => {
    stmtCurrencyPicked.current = false;
    setStmtCurrency(null);
    setStmtMeta({});
  }, [id]);

  // الافتراضي مرّةً لكل طرف بعد أول كشف: الدولار للوكيل/المورد ذي القيود الدولارية.
  useEffect(() => {
    if (stmtCurrencyPicked.current || !partner || !stmtMeta.currencies) return;
    stmtCurrencyPicked.current = true;
    const picked = defaultStatementCurrency(partner.partner_type, stmtMeta.currencies);
    if (picked) {
      setStmtCurrency(picked);
      setStmtOffset(0);
    }
  }, [partner, stmtMeta.currencies]);

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

  const stmtColumns: LedgerColumn<StatementDisplayRow>[] = [
    { key: 'date', header: 'التاريخ', render: (r) => formatDateLocalized(r.date) || '—' },
    {
      key: 'reference',
      header: 'الحركة',
      render: (r) => r.reversal_summary ? (
        <span className="text-[var(--ktra-ink-soft)]">قيد مصحَّح</span>
      ) : (
        <div className="flex flex-col gap-0.5">
          <DocRefCell
            referenceType={r.reference_type}
            referenceId={r.reference_id}
            label={`${referenceTypeLabel(r.reference_type, r.reference_kind)}${
              r.document_number
                ? ` ${r.document_number}`
                : r.reference_id != null ? ` #${r.reference_id}` : ''
            }`}
          />
          {/* السند يعلن الفاتورة التي وُزّع عليها — الربط ظاهر ولو تفرّقت الصفحة.
              والمستحق مرساةُ نفسه فلا «مقابل» له. */}
          {!r.info_amount && !r.document_number && r.link_label
            && r.link_key !== `${r.reference_type}:${r.reference_id}` && (
            <span className="text-[10px] text-[var(--ktra-ink-soft)]">
              ↔ مقابل {r.link_label}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'description',
      header: 'البيان',
      render: (r) => r.reversal_summary ? (
        <button
          type="button"
          aria-expanded={expandedPairs.has(r.reversal_summary.original_journal_id)}
          onClick={() => toggleReversalPair(r.reversal_summary!.original_journal_id)}
          className="text-right text-[var(--ktra-ink-soft)] hover:underline"
        >
          {expandedPairs.has(r.reversal_summary.original_journal_id) ? '▾' : '▸'} قيد صُحّح:
          #{r.reversal_summary.original_journal_id} ⇄ #{r.reversal_summary.reversal_journal_id} (صافي 0)
        </button>
      ) : r.info_amount ? (
        <span className="text-[11px] italic text-[var(--ktra-ink-soft)]">
          ↳ من {referenceTypeLabel(r.reference_type)} #{r.reference_id}: {formatMoney(r.info_amount)} — جزءٌ من سندٍ موزَّع، لا أثر له على الرصيد
        </span>
      ) : (
        <div className="flex flex-col gap-0.5">
          <span>{clarifyStatementDescription(r.reference_type, r.description) || '—'}</span>
          <StatementShipmentLabel row={r} />
          {r.currency_missing && (
            <span className="text-[10px] font-bold text-amber-700 dark:text-amber-400">
              ⚠ بلا مبلغ بالدولار — {formatMoney(Number(r.base_debit || 0) - Number(r.base_credit || 0))} ₪ (مدين − دائن)، لا يدخل الرصيد
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'debit',
      header: stmtCurrency ? `مدين (${stmtCurrency})` : 'مدين (Dr)',
      align: 'right',
      render: (r) => r.currency_missing
        ? <span className="text-[var(--ktra-ink-soft)]">—</span>
        : <span className="ktra-num">{r?.debit ?? ''}</span>,
    },
    {
      key: 'credit',
      header: stmtCurrency ? `دائن (${stmtCurrency})` : 'دائن (Cr)',
      align: 'right',
      render: (r) => r.currency_missing
        ? <span className="text-[var(--ktra-ink-soft)]">—</span>
        : <span className="ktra-num">{r?.credit ?? ''}</span>,
    },
    {
      key: 'running_balance',
      header: stmtCurrency ? `الرصيد (${stmtCurrency})` : 'الرصيد',
      align: 'right',
      render: (r) => r.reversal_member
        ? <span className="text-[var(--ktra-ink-soft)]">—</span>
        : <b className="ktra-num">{r?.running_balance ?? ''}</b>,
    },
    {
      key: 'details',
      header: 'تفاصيل',
      align: 'center',
      render: (r) => (r.info_amount || r.reversal_summary) ? null : (
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
        <div className="flex flex-col gap-0.5">
          <DocRefCell
            referenceType={r.reference_type}
            referenceId={r.reference_id}
            label={`${referenceTypeLabel(r.reference_type, r.reference_kind)}${
              r.reference_id != null ? ` #${r.reference_id}` : ''
            }`}
          />
          <StatementShipmentLabel row={r} />
        </div>
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
        r.shipment_id
          ? <DocRefCell referenceType="LOGISTICS_SHIPMENT" referenceId={r.shipment_id} label={r.document_number} />
          : <DocRefCell referenceType={r.document_type} referenceId={r.document_id} label={r.document_number} />
      ),
    },
    {
      key: 'document_type',
      header: 'النوع',
      render: relatedInvoiceTypeLabel,
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
              <div><span className="text-[var(--ktra-ink-soft)]">النوع:</span> <b>{partnerTypeLabel(partner.partner_type)}</b></div>
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
              <Kpi
                label={!isSupplier ? 'إجمالي المبيعات' : partner?.partner_type === 'Supplier' ? 'إجمالي المشتريات' : 'إجمالي المستحقّات'}
                value={isSupplier ? profile.total_purchases : profile.total_sales}
              />
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
          {/* الدائن: رصيدٌ لنا لم يُستهلك، مفصولاً رقمين — الرصيد نفسه لا يتغيّر بهما. */}
          {isSupplier && profile && (
            <div className="mb-3 grid grid-cols-2 gap-3 sm:max-w-md">
              <div className="rounded border border-[var(--ktra-border)] p-2" title="سندات صرف لم تُوزَّع، ودفعاتٌ زادت على المستحق لحظة دفعها">
                <div className="text-xs text-[var(--ktra-ink-soft)]">دفعات تحت الحساب</div>
                <div className="font-bold text-[var(--ktra-ink)]">{formatMoney(profile.on_account_payments ?? 0)} ₪</div>
              </div>
              <div className="rounded border border-[var(--ktra-border)] p-2" title="مدفوعٌ صار زائداً لأن المستحق خُفِّض بعد دفعه">
                <div className="text-xs text-[var(--ktra-ink-soft)]">فائض تحت الحساب</div>
                <div className="font-bold text-[var(--ktra-ink)]">{formatMoney(profile.accrual_surplus ?? 0)} ₪</div>
              </div>
            </div>
          )}
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
            <label className="flex items-center gap-1.5 text-sm text-[var(--ktra-ink-soft)]">
              <input
                type="checkbox"
                checked={stmtShowReversals}
                onChange={(event) => {
                  setStmtShowReversals(event.target.checked);
                  clientLogger.info("partner.statement_reversals_changed", {
                    shown: event.target.checked,
                  });
                }}
              />
              إظهار القيود المعكوسة
            </label>
            {(stmtCurrency || stmtMeta.currencies?.includes('USD')) && (
              <div className="flex overflow-hidden rounded-lg border border-[var(--ktra-border)] text-sm" role="group" aria-label="عملة الكشف">
                {([[null, '₪'], ['USD', '$']] as const).map(([code, label]) => (
                  <button
                    key={label}
                    type="button"
                    aria-pressed={stmtCurrency === code}
                    onClick={() => {
                      stmtCurrencyPicked.current = true;
                      setStmtCurrency(code);
                      setStmtOffset(0);
                      clientLogger.info("partner.statement_currency_changed", { currency: code ?? 'base' });
                    }}
                    className={`px-3 py-1.5 ${stmtCurrency === code
                      ? 'bg-[var(--ktra-accent,#2563eb)] font-bold text-white'
                      : 'bg-[var(--ktra-panel)] text-[var(--ktra-ink)]'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
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
          {stmtCurrency && (stmtMeta.missing_count ?? 0) > 0 && (
            <div className="mb-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300" role="status">
              ⚠ {formatNumber(stmtMeta.missing_count ?? 0, { maxDecimals: 0 })} حركة بلا مبلغ بالدولار (صافيها {formatMoney(stmtMeta.missing_base_balance ?? '0')} ₪)
              — معروضةٌ في الكشف ولا تدخل رصيده بالدولار.
            </div>
          )}
          {stmtGrouped && (
            <div className="mb-2 text-[11px] text-[var(--ktra-ink-soft)]">
              الحركات المترابطة مجمَّعة داخل إطار واحد؛ عمود «الرصيد» يبقى الرصيد الجاري
              زمنياً لكل حركة. الربط ضمن الصفحة المعروضة.
            </div>
          )}
          <LedgerTable<StatementDisplayRow>
            columns={stmtColumns}
            rows={stmtDisplayRows}
            loading={stmtLoading}
            count={stmt.count}
            limit={PAGE}
            offset={stmtOffset}
            onPage={setStmtOffset}
            rowClassName={(r) => (
              r.reversal_summary || r.reversal_member
                ? 'bg-gray-100 text-[var(--ktra-ink-soft)] dark:bg-white/5'
                : r.currency_missing ? 'bg-amber-50 dark:bg-amber-900/20'
                : r.info_amount ? 'bg-[var(--ktra-panel)]' : statementToneRowClass(r.reference_type)
            )}
            rowGroupKey={stmtGrouped ? (r) => r.link_key : undefined}
            emptyText="لا توجد حركات على حساب هذا الشريك."
            summaryRow={
              (stmt?.rows && stmt.rows.length > 0) ? (
                <tr className="bg-[#e6e4d5] font-bold border-t-2 border-[var(--ktra-border)]">
                  <td colSpan={3} className="px-2 py-2 text-right">الإجمالي (هذه الصفحة):</td>
                  <td className="px-2 py-2 text-right ktra-num">
                    {formatMoney(stmtTotalRows.reduce((sum, r) => {
                      const val = parseFloat(String(r?.debit || "0").replace(/,/g, ''));
                      return sum + (isNaN(val) ? 0 : val);
                    }, 0))}
                  </td>
                  <td className="px-2 py-2 text-right ktra-num">
                    {formatMoney(stmtTotalRows.reduce((sum, r) => {
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
          {stmtCurrency && stmtMeta.fx && (
            <div
              data-testid="statement-fx-row"
              className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-[var(--ktra-border)] bg-[var(--ktra-panel)] p-2 text-sm"
            >
              <span>الرصيد بالدفاتر: <b className="ktra-num">{formatMoney(stmtMeta.fx.book_balance)}</b> ₪</span>
              {stmtMeta.fx.rate ? (
                <>
                  <span>
                    الرصيد بالدولار <b className="ktra-num">{formatMoney(stmtMeta.fx.currency_balance)}</b> $
                    × {stmtMeta.fx.rate_source === 'exchange_rate' ? 'سعر اليوم' : 'سعر آخر قيد'}{' '}
                    <span className="ktra-num">{formatNumber(stmtMeta.fx.rate, { maxDecimals: 4 })}</span>
                    {' '}= <b className="ktra-num">{formatMoney(stmtMeta.fx.revalued_balance)}</b> ₪
                  </span>
                  <span className="font-bold">
                    الفرق (فرق صرف غير مقيَّد): <span className="ktra-num">{formatMoney(stmtMeta.fx.difference)}</span> ₪
                  </span>
                </>
              ) : (
                <span className="text-[var(--ktra-ink-soft)]">
                  الرصيد بالدولار <b className="ktra-num">{formatMoney(stmtMeta.fx.currency_balance)}</b> $ — لا سعر صرف مسجَّل لحساب الفرق.
                </span>
              )}
            </div>
          )}
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
                      label={`${stockMovementReferenceLabel({
                        reference_type: g.reference_type,
                        movement_type: g.movements[0]?.movement_type ?? null,
                        reference_type_display: referenceTypeLabel(g.reference_type),
                      })}${g.reference_id != null ? ` #${g.reference_id}` : ''}`}
                    />
                  </div>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-[var(--ktra-ink-soft)]">
                        <th className="px-2 py-1 text-right">التاريخ</th>
                        <th className="px-2 py-1 text-right">المنتج</th>
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
                // ردّ فائض العميل (سند قبض زائد/إشعار دائن) نقداً: Dr ذمّته / Cr صندوق.
                ...(customerSurplusCount > 0
                  ? [{
                      key: 'refund-payment',
                      label: 'سند صرف (ردّ فائض)',
                      onClick: () => {
                        setShowRefundModal(true);
                        clientLogger.info("partner.refund_payment_open");
                      },
                    }]
                  : []),
                {
                  key: 'new-invoice',
                  label: `${term('doc.sales_invoice')} جديدة`,
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
                // المخلّص/الوكيل/الناقل تُستحقّ لهم تخاليص وشحن وإرساليات لا فواتير شراء.
                ...(partner?.partner_type === 'Supplier'
                  ? [{
                      key: 'new-purchase',
                      label: 'فاتورة مشتريات جديدة',
                      onClick: () => navigate('/purchase-invoices/new'),
                    }]
                  : []),
                // الخيار الثاني الصريح للدائن: استرداد زيادةٍ دُفعت له (Dr صندوق / Cr ذمّته).
                ...(voucherDirs?.secondary === 'receipt'
                  ? [{
                      key: 'refund-receipt',
                      label: 'سند قبض (استرداد)',
                      onClick: () => {
                        setShowReceiptModal(true);
                        clientLogger.info("partner.refund_receipt_open");
                      },
                    }]
                  : []),
              ]
            : []),
          // إشعار مدين/دائن لأيّ طرف — شاشة المالية بالطرف مُعبّأً مسبقاً.
          ...(id
            ? [{
                key: 'new-credit-debit-note',
                label: 'إشعار مدين/دائن',
                onClick: () => navigate(`/accounting/credit-debit-notes?action=new&partner_id=${id}`),
              }]
            : []),
        ]}
        tabs={tabs}
        activeTab={activeTabKey}
        onTabChange={setActiveTabKey}
        status={
          error || allocError ? <span className="text-[var(--ktra-danger)]">{error || allocError}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="ktra-status-item">{partnerTypeLabel(partner?.partner_type) || (isSupplier ? 'مورد' : 'عميل')}{profile ? ` · الرصيد ${profile.balance} ${profile.balance_side}` : ''}</span>
        }
      >
        <></>
      </KitDocumentShell>
      <StatementDetailsModal movement={detailRow} onClose={() => setDetailRow(null)} />
      {(showReceiptModal || showRefundModal) && receiptPartner && (
        <NewPaymentModal
          initialPartner={receiptPartner}
          lockPartner
          // قبضُ الدائن استردادٌ دائماً: يعرض فائضه ويختار ما يُطفئه (إشعار/سند صرف زائد).
          refundMode={showRefundModal ? 'refund' : isSupplier ? 'receipt' : undefined}
          onClose={() => { setShowReceiptModal(false); setShowRefundModal(false); }}
          onSaved={() => {
            setShowReceiptModal(false);
            setShowRefundModal(false);
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
                  <th>المصدر</th>
                  <th>التاريخ</th>
                  <th>المبلغ</th>
                  <th>على الحساب</th>
                  <th className="w-[70px]"></th>
                </tr>
              </thead>
              <tbody>
                {onAccountPayments.map((p) => (
                  <tr key={`${p.source}:${p.id}`} className="border-t border-[var(--ktra-border)]">
                    <td>{p.source === 'note' ? `إشعار ${p.number}` : `سند #${p.id}`}</td>
                    <td>{formatDateLocalized(p.payment_date)}</td>
                    <td className="ktra-num">{formatMoney(p.amount)}</td>
                    <td className="ktra-num text-[var(--ktra-warn)]">
                      {formatMoney(p.unallocated_amount ?? 0)}
                    </td>
                    <td className="text-center">
                      <button
                        type="button"
                        className="ktra-toolbtn text-[11px]"
                        onClick={() => { openOnAccountRow(p); setShowAllocPicker(false); }}
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
      {noteAllocTarget && partner && (
        <NoteAllocationModal
          noteId={noteAllocTarget.id}
          partnerLabel={partner.name}
          onClose={() => setNoteAllocTarget(null)}
          onSaved={() => {
            setNoteAllocTarget(null);
            setStmtOffset(0);
            loadStatement(0);
            setPaymentsRefreshKey((key) => key + 1);
            setActivityRefreshKey((key) => key + 1);
            clientLogger.info("partner.note_allocation_saved");
          }}
        />
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
