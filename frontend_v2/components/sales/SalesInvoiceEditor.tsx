import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  attachSalesInvoiceIntent,
  createSalesInvoice,
  collectSalesInvoice,
  duplicateSalesInvoice,
  getCreditPreview,
  getCustomerPriceList,
  getReservedStock,
  listCustomerPayments,
  resolveSalePrice,
  getNextInvoiceNumber,
  getSalesInvoice,
  patchSalesInvoice,
  postSalesInvoice,
  unpostSalesInvoice,
  type AttachedCheque,
  type CreditPreviewResponse,
  type InvoiceIntentPayload,
  type ReservedStockRow,
  type SalesInvoiceDetail,
  type SalesInvoiceRow,
  salesInvoiceContextApi,
} from "../../services/salesApi";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { useConfirm } from "../../contexts/ConfirmContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import { usePriceVisibility } from "../../contexts/PriceVisibilityContext";
import { useStaleConfirm } from "../offline/StaleDataConfirm";
import {
  DocumentPaymentPanel,
  deriveDocumentPayment,
  deriveInvoiceSettlement,
} from "../shared/DocumentPaymentPanel";
import { InvoicePaymentsSection } from "../shared/InvoicePaymentsSection";
import { DocumentPaymentsTab } from "../shared/DocumentPaymentsTab";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import { EntityActivityLog } from "../activity/EntityActivityLog";
import {
  InvoiceStockTab,
  InvoicePartnerLedgerTab,
  InvoiceAttachmentsTab,
} from "../shared/DocumentContextTabs";
import { PartnerNoteAlert } from "../partners/PartnerNoteAlert";
import { AseelDatePicker } from "../ui/AseelDatePicker";
import { FieldHint } from "../ui/FieldHint";

import { ProductCardModal } from "../shared/ProductCardModal";
import { SerialEntryModal } from "../shared/SerialEntryModal";
import { Item } from "../../types";
import type { SerialEntryMode } from "../../types/inventory";
import db from "../../services/offline/db";
import { computeInvoiceTotals, type LineInput } from "../../utils/salesInvoiceMath";
import {
  availableForSale,
  buildReservationIndex,
  reservedSaleWarnings,
  totalReserved,
} from "../../utils/reservedStock";
import { formatMoney, formatQuantity, formatNumber } from "../../utils/formatNumber";
import { openInNewTab } from "../../utils/openInNewTab";
import { productProfilePath } from "../../utils/entityLinks";
import { availableOf, needsAlternative, stockAlternatives, stockBadgeFor } from "../../utils/stockBadge";
import { accountMatchesPurpose } from "../../utils/accountTree";
import { entityPathForReference } from "../../utils/entityLinks";
import { DeliverGoodsModal } from "./DeliverGoodsModal";
import { clientLogger } from "../../services/logger";
import { apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { invoiceActionPermissions } from "../../utils/viewPermissions";
import {
  isOfflineRecordForTenant,
  tenantScopedOfflineKey,
} from "../../utils/offlineTenantScope";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Pencil,
  Plus,
  Printer,
  Receipt,
  Save,
  Search,
  Send,
  Trash2,
  X,
  CreditCard,
  ArrowRight,
  Undo2,
  Info,
  Truck,
  ClipboardList,
  ExternalLink,
  Wrench,
  StickyNote,
} from "lucide-react";
import { eventBus } from "../../utils/eventBus";
import { ItemQuickCreateModal } from "../items/ItemQuickCreateModal";
import { ItemQuickEditModal } from "../items/ItemQuickEditModal";
import { SalesProductPickerModal, formatProductPrimaryName } from "./SalesProductPickerModal";
import { CustomerQuickAddModal } from "./CustomerQuickAddModal";
import { SalesInvoicePrintView } from "./SalesInvoicePrintView";
import { formatDateTimeValue } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { FieldError } from "../ui/FieldError";
import {
  AseelDocumentShell,
  AseelDocumentView,
  AseelGrid,
  AseelIndexPicker,
  AseelAutocomplete,
  useAseelKeymap,
  useRecordNavigation,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../aseel";

export type ProductRow = {
  id: number;
  sku: string;
  barcode?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  quantity_on_hand: string;
  online_price?: string | null;
  /** «سعر البيع» العام في كرت الصنف — يُقترح حين لا سعر خاص بهذا الزبون. */
  sale_price?: string | null;
  avg_cost?: string | null;
  /** T-SERVICELINE: خدمة لا بضاعة — بلا مخزون، وإيرادها على حساب الخدمات. */
  is_service?: boolean;
  /** T-SERIAL: الصنف يتتبّع وحداته برقم تسلسلي — يُظهر عمود الأرقام على سطره. */
  is_serialized?: boolean;
  /** T-REORDER: حالة المخزون كما يحسمها الخادم (`inventory/stock_status.py`). */
  stock_status?: string | null;
  /** T-REORDER: مفتاح «النوع» — موديلات النوع الواحد بدائلُ بعضها. */
  group_key?: string | null;
  /** المتاح بعد الحجز — يرسله عقد المنتقي بجانب الرصيد. */
  available_quantity?: string | number | null;
};

export type PartnerRow = {
  id: number;
  name: string;
  partner_type: string;
  /** يصل من `partners/lookup/` — يُبحَث فيه ولا يُعرض في السطر. */
  phone?: string | null;
  credit_limit?: string | null;
  /** M5: customer's linked GL account — enables ledger drill-down. */
  linked_account?: number | null;
};

/** T4: صفّ شيك في لوحة التحصيل — الاستحقاق إلزامي (الخادم يفرضه أيضاً). */
type CollectChequeRow = {
  key: string;
  cheque_number: string;
  bank_name: string;
  due_date: string;
  amount: string;
};

/** T4: سند قبض مرحّل بقي منه رصيد «على الحساب» يصلح لتسديد هذه الفاتورة. */
type OnAccountVoucher = { id: number; unallocated: number };

export type CurrRow = { CurrencyID: number; Code: string; Name?: string | null };
export type AccountRow = {
  id: number;
  code?: string | null;
  name?: string | null;
  account_type?: string | null;
};
export type TaxRow = {
  id: number;
  name: string;
  code: string;
  rate: string;
  tax_account?: number;
  direction?: string;
  tax_account_type?: string;
};

export type DraftLine = {
  key: string;
  id?: number;
  product: number | "";
  quantity: string;
  unit_price: string;
  line_discount: string;
  tax_rate: number | "" | null;
  /** FEAT-2 edit-protection: مضبوط عندما يحرّر المستخدم سعر السطر يدوياً.
   *  السعر المقترح لا يُدَس على سطر مَلموس عند تغيير العميل. */
  priceTouched?: boolean;
  /** DEF-005: مصدر السعر المقترح للشارة — آخر فاتورة / عرض كرت الزبون / عرض واجهة
   *  العروض / «default» = السعر العام في كرت الصنف. */
  priceSource?: "last_invoice" | "quote" | "sales_quote" | "default" | null;
  /** رابط فتح مصدر السعر عند النقر (عرض العروض أو تبويب عرض السعر بكرت الزبون). */
  priceSourceLink?: string | null;
  /** T-SERIAL: الوحدات المختارة صراحةً لهذا البند — الفارغ يعني «أي وحدة» (FIFO خادمي). */
  serials?: string[];
  /** ملاحظة الموظف على البند — لا تُطبع للعميل أبداً. */
  internal_note?: string;
  /** ملاحظة تُطبع للعميل تحت اسم الصنف في الفاتورة. */
  customer_note?: string;
};

const newLineKey = () => `ln-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

const initialBlankLine = (): DraftLine => ({
  key: newLineKey(),
  product: "",
  quantity: "1",
  unit_price: "0",
  line_discount: "0",
  tax_rate: "",
});

/**
 * T-NOTES: ملاحظتا البند في نافذة واحدة، مفصولتين بصرياً بقدر فصلهما في المخطط.
 *
 * الفصل هو الميزة نفسها: «العميل ساوم على السعر» و«الجهاز مفتوح العلبة» ملاحظتان
 * لصاحب المحل، و«الكفالة سنة من تاريخ الفاتورة» ملاحظةٌ تُطبع للزبون. حقلٌ واحد
 * يعني أن إحداهما ستُطبع خطأً — والخطأ في هذا الاتجاه لا يُستدرَك بعد التسليم.
 */
const LineNotesModal: React.FC<{
  productName: string;
  internalNote: string;
  customerNote: string;
  readOnly?: boolean;
  onClose: () => void;
  onSave: (next: { internalNote: string; customerNote: string }) => void;
}> = ({ productName, internalNote, customerNote, readOnly = false, onClose, onSave }) => {
  const [internal, setInternal] = useState(internalNote);
  const [forCustomer, setForCustomer] = useState(customerNote);

  return (
    <div
      dir="rtl"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-lg rounded-2xl aseel-bg-field dark:aseel-bg-panel shadow-xl border aseel-border-soft">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b aseel-border-soft">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-[var(--color-primary)] text-white rounded-xl">
              <StickyNote className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold aseel-text-ink dark:text-white">ملاحظات البند</h3>
              <p className="text-xs aseel-text-soft">{productName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 aseel-text-soft hover:aseel-bg-panel rounded-lg"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 sm:p-6 space-y-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-bold aseel-text-ink dark:aseel-text-soft">
              ملاحظة داخلية — للموظف
            </span>
            <textarea
              rows={3}
              maxLength={500}
              disabled={readOnly}
              value={internal}
              onChange={(e) => setInternal(e.target.value)}
              className="px-2 py-1.5 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-sm resize-y"
              placeholder="لا تُطبع للعميل — سبب الخصم، حالة العلبة، من وافق على السعر…"
            />
            <span className="text-[11px] aseel-text-soft">
              لا تظهر في نسخة العميل المطبوعة إطلاقاً.
            </span>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-bold aseel-text-ink dark:aseel-text-soft">
              ملاحظة للزبون — تُطبع في الفاتورة
            </span>
            <textarea
              rows={3}
              maxLength={500}
              disabled={readOnly}
              value={forCustomer}
              onChange={(e) => setForCustomer(e.target.value)}
              className="px-2 py-1.5 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-sm resize-y"
              placeholder="تُطبع تحت اسم الصنف — مدّة الكفالة، شروط التركيب، ملحقات مرفقة…"
            />
            <span className="text-[11px] aseel-text-soft">
              تظهر تحت اسم الصنف في الفاتورة المطبوعة.
            </span>
          </label>

          <div className="flex items-center justify-end gap-3 pt-2 border-t aseel-border-soft">
            <button
              onClick={onClose}
              className="px-4 py-2 aseel-text-ink dark:aseel-text-soft aseel-bg-panel rounded-lg"
            >
              إلغاء
            </button>
            <button
              onClick={() => onSave({
                internalNote: internal.trim(),
                customerNote: forCustomer.trim(),
              })}
              disabled={readOnly}
              className="px-5 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 text-white rounded-lg font-medium"
            >
              حفظ الملاحظات
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

type Props = {
  products: ProductRow[];
  partners: PartnerRow[];
  currencies: CurrRow[];
  accounts: AccountRow[];
  taxRates: TaxRow[];
  draftToEditId: number | null;
  onDraftEditConsumed: () => void;
  onInvoiceSaved: () => void;
  /** task16: العودة لقائمة الفواتير (زر صريح في الشريط + إغلاق المحرر). */
  onClose?: () => void;
  /** قائمة الفواتير الحالية (لتنقّل السجلات الأول/السابق/التالي/الأخير). */
  invoiceList?: SalesInvoiceRow[];
  /** اسم/رقم المستخدم الحالي لشريط الحالة (اختياري). */
  currentUserName?: string;
  /** M5: فتح الأستاذ العام لحساب العميل المرتبط (drill-down من رصيد العميل). */
  onOpenGeneralLedger?: (accountId: number) => void;
  initialCustomerId?: number;
  salesSettings?: {
    default_customer: number | null;
    default_currency: number | null;
    default_payment_type: "cash" | "credit";
    default_cash_account: number | null;
    default_revenue_account_product: number | null;
    stock_on_post_default: boolean;
    default_vat_rate: number | null;
    prices_include_tax: boolean;
    auto_post_invoices: boolean;
    show_journal_preview: boolean;
    /** T-R3: تنبيه عند تكرار الصنف على سطر جديد (الافتراضي مُفعّل). */
    warn_on_duplicate_item?: boolean;
    /** منع حفظ/ترحيل فاتورة بيع بخسارة (الافتراضي مُعطّل). */
    block_loss_invoices?: boolean;
    /** T-SERIAL: نمط اختيار الوحدة المباعة — `off` يخفي العمود بالكامل. */
    serial_entry_mode?: SerialEntryMode;
  } | null;
};

/** هل الحساب صندوق/بنك مناسب لاستلام نقد؟
 *  THA-111: الغرض هو الحكم الآن — يقرأ التصنيف الوظيفي المخزَّن في الخادم.
 *  استثناء `till/petty` الذي كان هنا انتقل إلى اشتقاق التصنيف نفسه، فلم يعد
 *  لهذه الشاشة إجابة خاصة بها عن سؤال «ما الصندوق؟».
 */
const isCashboxAccount = (a: AccountRow): boolean =>
  accountMatchesPurpose(a, "cash");

/** هل الحساب حساب إيراد مناسب لفاتورة مبيعات؟ */
const isRevenueAccount = (a: AccountRow): boolean => {
  if (a.account_type === "Revenue") return true;
  // أحياناً account_type لم يُعبَّأ — نستخدم الكود كـ fallback (4xxx = Revenue في COA)
  if (!a.account_type) {
    const code = (a.code || "").trim();
    return /^4/.test(code);
  }
  return false;
};

export const SalesInvoiceEditor: React.FC<Props> = ({
  products: productsProp,
  partners,
  currencies,
  accounts,
  taxRates,
  draftToEditId,
  onDraftEditConsumed,
  onInvoiceSaved,
  onClose,
  invoiceList = [],
  currentUserName,
  onOpenGeneralLedger,
  salesSettings,
  initialCustomerId,
}) => {
  const confirm = useConfirm();
  const { can: canPerm, uiMode } = usePermissions();
  // الربح الإجمالي يتبع زر العين (الخصوصية): يختفي حين تُخفى الأسعار/الأرباح.
  const { visible: profitVisible } = usePriceVisibility();
  const [draftId, setDraftId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<boolean>(!!draftToEditId);
  const [invoiceNumber, setInvoiceNumber] = useState<string>("");
  const [customerId, setCustomerId] = useState<number | "">(initialCustomerId || "");
  const [invDate, setInvDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [dueDate, setDueDate] = useState("");
  const [invType, setInvType] = useState<"cash" | "credit">("credit");
  const [currencyId, setCurrencyId] = useState<number | "">("");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [invoiceDiscount, setInvoiceDiscount] = useState("0");
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [revenueAccountId, setRevenueAccountId] = useState<number | "">("");
  const [stockOnPost, setStockOnPost] = useState(true);
  const [notes, setNotes] = useState("");
  // ── M2-T1: Aseel header fields ─────────────────────────────────────────
  const [bookNumber, setBookNumber] = useState<string>("0");
  const [secondDate, setSecondDate] = useState<string>("");
  const [licensedDealerNo, setLicensedDealerNo] = useState<string>("");
  const [settlementInvoiceNo, setSettlementInvoiceNo] = useState<string>("");
  const [pricesIncludeTax, setPricesIncludeTax] = useState(false);
  const [discountPercent, setDiscountPercent] = useState<string>("0");
  const [activeTabKey, setActiveTabKey] = useState("notes");
  // ── M2-T4: Source discount overrides (null = use customer default) ─────
  const [sourceDiscountPctOverride, setSourceDiscountPctOverride] = useState<string>("");
  const [sourceDiscountAmtOverride, setSourceDiscountAmtOverride] = useState<string>("");
  const [lines, setLines] = useState<DraftLine[]>(() => [initialBlankLine()]);
  const [productFilter, setProductFilter] = useState("");
  const [taxEditKey, setTaxEditKey] = useState<string | null>(null);
  const [taxPercentDraft, setTaxPercentDraft] = useState<Record<string, string>>({});
  const [taxSavingKey, setTaxSavingKey] = useState<string | null>(null);
  const [productPickerLineKey, setProductPickerLineKey] = useState<string | null>(null);
  // DEF-007/008: بطاقة الصنف (مودال مشترك) — تُفتح من الشجرة/القائمة/سطر الفاتورة.
  const [cardProductId, setCardProductId] = useState<number | null>(null);
  // T-ITEMS M3: الصنف الجاري تحريره سريعاً من داخل الفاتورة (بلا مغادرتها).
  const [quickEditProductId, setQuickEditProductId] = useState<number | null>(null);
  // «موافق» (إضافة للفاتورة) يظهر فقط عند فتح البطاقة من الشجرة، لا من أيقونة (i).
  const [cardCanAdd, setCardCanAdd] = useState(false);
  // T-R2: السعر المقترح ومصدره — يُحسبان عند فتح البطاقة من الشجرة لعرضهما داخلها.
  const [cardSuggestedPrice, setCardSuggestedPrice] = useState<number | null>(null);
  const [cardPriceSource, setCardPriceSource] = useState<DraftLine["priceSource"]>(null);
  const [invoiceStatus, setInvoiceStatus] = useState<string>("draft");
  const [postedJournalId, setPostedJournalId] = useState<number | null>(null);
  // task18: المدفوع/الإجمالي المحفوظان — لحساب المتبقي عند تسجيل سند قبض على فاتورة مرحّلة.
  const [paidAmount, setPaidAmount] = useState(0);
  // T-INTENT: الدفعة المرفقة بالمسودة — مسجَّلة ولم تدخل الدفاتر بعد.
  const [pendingIntent, setPendingIntent] = useState(0);
  const [intentCash, setIntentCash] = useState(0);
  const [intentCashAccountId, setIntentCashAccountId] = useState<number | null>(null);
  const [attachedCheques, setAttachedCheques] = useState<AttachedCheque[]>([]);
  const [savedGrandTotal, setSavedGrandTotal] = useState(0);
  const [paymentStatusDisplay, setPaymentStatusDisplay] = useState("غير مدفوعة");
  // حالة تسليم البضاعة (تظهر للفاتورة التي لا تخصم المخزون عند الترحيل).
  const [deliveryStatusDisplay, setDeliveryStatusDisplay] = useState("غير مسلَّمة");
  const [deliveryStatus, setDeliveryStatus] = useState<string>("not_delivered");
  const [customerBalanceBeforeInvoice, setCustomerBalanceBeforeInvoice] = useState(0);
  const [customerBalanceAfterInvoice, setCustomerBalanceAfterInvoice] = useState(0);
  /** THA-132: رقم الحركة المخزنية — يُعرض في شريط الحالة كما في الأصيل. */
  const [stockMovementNo, setStockMovementNo] = useState<number | null>(null);
  const [paymentDetails, setPaymentDetails] = useState<SalesInvoiceDetail["payment_details"]>([]);
  // T-SLINEAGE: المستند الأب (طلبية/عرض) — يُعرض في بيانات المستند برابط يفتحه.
  const [sourceDocument, setSourceDocument] =
    useState<SalesInvoiceDetail["source_document"]>(null);
  // T-RETURNUI: مرجع البيع يُفتح من نفس المحرر لكنه مستند مختلف — عنوان وشارة
  // ورابط للفاتورة الأصلية، وأقسام الدفع/التسليم لا تنطبق عليه.
  const [invoiceKind, setInvoiceKind] = useState<string>("sale");
  const [originalInvoiceId, setOriginalInvoiceId] = useState<number | null>(null);
  const [originalInvoiceNumber, setOriginalInvoiceNumber] = useState<string | null>(null);
  const isReturn = invoiceKind === "sale_return";
  /* ── T4: لوحة التحصيل داخل المحرّر ────────────────────────────────────────
     أوجه الدفع الثلاثة (نقد · شيكات · رصيد العميل) في مكان واحد، و«المتبقي»
     مشتقٌّ منها حيّاً. حلّت محلّ نافذة «تسديد» في جانب المبيعات: سطحان
     يفعلان الشيء نفسه كانا يفترقان في ما يقبلانه (لا شيكات، ولا فائض). */
  const [collectCash, setCollectCash] = useState("");
  const [collectCashAccountId, setCollectCashAccountId] = useState<number | "">("");
  const [collectCheques, setCollectCheques] = useState<CollectChequeRow[]>([]);
  const [chequesOpen, setChequesOpen] = useState(false);
  const [collectFromBalance, setCollectFromBalance] = useState("");
  const [onAccountVouchers, setOnAccountVouchers] = useState<OnAccountVoucher[]>([]);
  /** يُزاد بعد كل تحصيل ناجح لإعادة جلب رصيد العميل على الحساب. */
  const [onAccountKey, setOnAccountKey] = useState(0);
  const [collecting, setCollecting] = useState(false);
  const collectPanelRef = useRef<HTMLDivElement | null>(null);
  const collectCashInputRef = useRef<HTMLInputElement | null>(null);
  // P3-2-b wiring: offline status + stale-data confirm for line additions.
  const { online: networkOnline } = useOnlineStatus();
  const { confirm: confirmStale, modal: staleModal } = useStaleConfirm();

  const [saving, setSaving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [localErr, setLocalErr] = useState<string | null>(null);
  // SAVE-3 (إضافة لا إعادة هيكلة): المحرّر كان يعرض سبب الفشل في لافتة ويبقى
  // مفتوحاً — وهذا صحيح أصلاً. الناقص كان أخطاء الحقول التي يرسلها الخادم مع
  // كل رفض (`err.fieldErrors`) وتُسحق في نصّ واحد. نعرضها مفصّلة تحت اللافتة.
  const [saveFieldErrors, setSaveFieldErrors] = useState<Record<string, string>>({});
  const [creditHint, setCreditHint] = useState<CreditPreviewResponse | null>(null);
  const [showPreview, setShowPreview] = useState(true);
  /** آخر مفتاح اختصار ضُغط (يُعرض في شريط الحالة — سلوك الأصيل). */
  const [lastKey, setLastKey] = useState<string>("—");
  /** فهرس الحسابات (العميل) منبثق بمفتاح + أو زر «…». */
  const [customerPickerOpen, setCustomerPickerOpen] = useState(false);
  const [showAddCustomerModal, setShowAddCustomerModal] = useState(false);
  const [showPrintView, setShowPrintView] = useState(false);
  // نافذة تسليم البضاعة (تُنشئ إرسالية بالبنود المؤشَّرة).
  const [showDeliver, setShowDeliver] = useState(false);
  // T-SERVICELINE: نافذة «إضافة خدمة» — تُنشئ الخدمة وتضعها في سطر الفاتورة.
  const [showServiceModal, setShowServiceModal] = useState(false);
  const navLoadingRef = useRef(false);

  const dirtyRef = useRef(false);

  /* T-QUICKPARTY: العميل المُنشأ من داخل الفاتورة يُستعمل فوراً — نفس علاج
     `extraProducts`: القائمة تصل من الشاشة الأم بعد بثّ حدث `partners`، وحتى
     يصل نعرضه محلياً. بلا هذا يبقى حقل العميل فارغاً بعد الإنشاء (والمعرَّف
     مسنداً!) — وعلى شركةٍ بأكثر من 500 عميل يبقى فارغاً للأبد لأن
     `partners/lookup/` مسقوفة عند 500. */
  const [extraCustomers, setExtraCustomers] = useState<PartnerRow[]>([]);
  const customers = useMemo(() => {
    const own = partners.filter((p) => p.partner_type === "Customer");
    if (extraCustomers.length === 0) return own;
    const known = new Set(own.map((p) => p.id));
    return [...own, ...extraCustomers.filter((p) => !known.has(p.id))];
  }, [partners, extraCustomers]);

  /** خيارات الإكمال التلقائي لحقل العميل — الرقم سطرٌ ثانوي كي يبقى قابلاً للبحث. */
  const customerOptions = useMemo(
    // T-SEARCH: الهاتف والرقم يُبحَث فيهما — كان الاسم وحده، والبائع يعرف
    // زبونه برقمه غالباً. الهاتف يصل من `partners/lookup/` أصلاً.
    () => customers.map((c) => ({
      id: c.id,
      label: c.name,
      sub: `#${c.id}`,
      keywords: [String(c.id), c.phone || ""].filter(Boolean).join(" ").toLowerCase(),
    })),
    [customers],
  );

  /** T-QUICKPARTY: الاسم المكتوب في حقل العميل يُحمل إلى نافذة الإضافة. */
  const [quickAddName, setQuickAddName] = useState("");

  /** T-SEARCH: نصُّ البحث المنقول إلى الفهرس الكامل (من «+N أخرى» أو الباركود). */
  const [pickerQuery, setPickerQuery] = useState("");

  /** حقل «بحث سريع/باركود»: محطة الإدخال التالية بعد حسم العميل، وهدف F6.
   *  مؤجَّل دورةً كي لا تسحب إعادةُ الرسم بعد إغلاق القائمة التركيزَ منه. */
  const focusBarcodeField = () => {
    window.setTimeout(() => {
      document
        .querySelector<HTMLInputElement>('[data-aseel-field="barcode"]')
        ?.focus();
    }, 0);
  };

  /** مصدر واحد لأثر اختيار العميل — من الإكمال التلقائي أو الفهرس أو الإنشاء
   *  السريع: يُثبَّت، تُعلَّم الفاتورة مُتّسخة، ويمضي التركيز إلى البند الأول. */
  const pickCustomer = (id: number) => {
    setCustomerId(id);
    markDirty();
    setCustomerPickerOpen(false);
    focusBarcodeField();
  };

  // T-SERVICELINE: الخدمة المُنشأة من داخل الفاتورة تُستعمل فوراً — قائمة الأصناف
  // تصل عبر الخصائص من الشاشة الأم، فننتظر تحديثها ونعرض المُضاف محلياً حتى يصل.
  const [extraProducts, setExtraProducts] = useState<ProductRow[]>([]);
  const products = useMemo(() => {
    if (extraProducts.length === 0) return productsProp;
    const known = new Set(productsProp.map((p) => p.id));
    return [...productsProp, ...extraProducts.filter((p) => !known.has(p.id))];
  }, [productsProp, extraProducts]);

  const productsById = useMemo(() => {
    const m = new Map<number, ProductRow>();
    products.forEach((p) => m.set(p.id, p));
    return m;
  }, [products]);

  /* T-RESERVEVIS: الحجوزات السارية — نفس صفوف «تقرير المحجوزات» التي يحرسها
     الخادم، فما يُعرض على السطر هو بعينه ما سيُقاس عليه الترحيل. تُجلب مرة عند
     الفتح: الحجز لا يتغيّر أثناء تحرير الفاتورة. */
  const [reservationRows, setReservationRows] = useState<ReservedStockRow[]>([]);
  useEffect(() => {
    if (!networkOnline) { setReservationRows([]); return; }
    let cancelled = false;
    getReservedStock()
      .then((rows) => { if (!cancelled) setReservationRows(rows); })
      .catch(() => { if (!cancelled) setReservationRows([]); });
    return () => { cancelled = true; };
  }, [networkOnline]);

  // حجز زبون الفاتورة نفسه لا يُطرح من متاحه — نفس استثناء الحارس.
  const reservationIndex = useMemo(
    () => buildReservationIndex(reservationRows, customerId === "" ? null : Number(customerId)),
    [reservationRows, customerId],
  );
  /** هل لأيّ صنف على الفاتورة حجزٌ سارٍ؟ بلا حجز يبقى «الرصيد» وحده. */
  const anyLineReserved = useMemo(
    () => lines.some((l) => l.product !== ""
      && totalReserved(reservationIndex.get(Number(l.product))) > 0),
    [lines, reservationIndex],
  );

  /* T-SERIAL: نمط اختيار الوحدة المباعة. `off` (الافتراضي) ⇒ لا عمود ولا زر
     ولا حقل في الحمولة — الشاشة كما كانت تماماً. */
  const serialMode: SerialEntryMode = salesSettings?.serial_entry_mode ?? "off";
  /** بند مفتوح في نافذة اختيار الوحدات (بمفتاح السطر). */
  const [serialLineKey, setSerialLineKey] = useState<string | null>(null);
  /** T-NOTES: البند المفتوحة ملاحظتاه. */
  const [notesLineKey, setNotesLineKey] = useState<string | null>(null);
  /** الصنف يتتبّع وحداته؟ الخدمة مستثناة — بلا مخزون فبلا وحدات. */
  const lineTracksSerials = useCallback(
    (row: DraftLine) => {
      if (serialMode === "off" || row.product === "") return false;
      const pr = productsById.get(Number(row.product));
      return Boolean(pr?.is_serialized && !pr?.is_service);
    },
    [serialMode, productsById],
  );
  /** عمود الأرقام يظهر فقط حين تحمل الفاتورة صنفاً تسلسلياً — لا عمود فارغ. */
  const anyLineSerialized = useMemo(
    () => lines.some(lineTracksSerials),
    [lines, lineTracksSerials],
  );

  /** تنبيه بيع المحجوز — يسمّي الطلبية وصاحبها قبل أن يرفض الخادم الترحيل. */
  const reservedWarnings = useMemo(() => {
    if (invoiceStatus === "posted" || !stockOnPost) return [];
    return reservedSaleWarnings(
      lines
        .filter((l) => l.product !== "")
        .map((l) => {
          const pr = productsById.get(Number(l.product));
          return {
            productId: Number(l.product),
            quantity: l.quantity,
            onHand: pr?.quantity_on_hand ?? 0,
            name: pr ? (pr.name_ar || pr.name_en || pr.sku) : `#${l.product}`,
            exempt: !pr || !!pr.is_service,
          };
        }),
      reservationIndex,
    );
  }, [lines, productsById, reservationIndex, stockOnPost, invoiceStatus]);

  // M3: selling below available stock is ALLOWED — but we surface a
  // non-blocking warning so the user is aware the stock will go negative.
  const overSellWarnings = useMemo(() => {
    if (invoiceStatus === "posted" || !stockOnPost) return [] as { name: string; qty: number; available: number }[];
    const out: { name: string; qty: number; available: number }[] = [];
    for (const l of lines) {
      if (l.product === "") continue;
      const pr = productsById.get(Number(l.product));
      if (!pr) continue;
      const q = Number(l.quantity) || 0;
      const avail = Number(pr.quantity_on_hand) || 0;
      if (q > avail + 1e-6) out.push({ name: pr.name_ar || pr.name_en || pr.sku, qty: q, available: avail });
    }
    return out;
    // lines/quantities are strings in state; recompute whenever they change
  }, [lines, productsById, stockOnPost, invoiceStatus]);

  /** نسب الضرائب المسموحة للمبيعات: direction ∈ {sales, both} أو بدون direction (قديم). */
  const salesTaxRates = useMemo(
    () =>
      taxRates.filter((t) => {
        const d = (t.direction || "both").toLowerCase();
        return d === "sales" || d === "both";
      }),
    [taxRates]
  );

  const taxRateMap = useMemo(() => {
    const m = new Map<number, number>();
    taxRates.forEach((t) => m.set(t.id, Number(t.rate)));
    return m;
  }, [taxRates]);

  const taxRateById = useMemo(() => {
    const m = new Map<number, TaxRow>();
    taxRates.forEach((t) => m.set(t.id, t));
    return m;
  }, [taxRates]);

  const accountsById = useMemo(() => {
    const m = new Map<number, AccountRow>();
    accounts.forEach((a) => m.set(a.id, a));
    return m;
  }, [accounts]);

  const cashboxAccounts = useMemo(
    () => accounts.filter(isCashboxAccount).sort((a, b) => (a.code || "").localeCompare(b.code || "")),
    [accounts]
  );
  const revenueAccounts = useMemo(
    () => accounts.filter(isRevenueAccount).sort((a, b) => (a.code || "").localeCompare(b.code || "")),
    [accounts]
  );

  /** نسبة ض.ق.م الافتراضية من الإعدادات أو الافتراضي 16% */
  const defaultVatRateId = useMemo(() => {
    if (salesSettings?.default_vat_rate) {
      const settingRate = Number(salesSettings.default_vat_rate);
      const bySettings = salesTaxRates.find((t) => Math.abs(Number(t.rate) - settingRate) < 0.02);
      if (bySettings) return bySettings.id;
    }
    const byCode = salesTaxRates.find((t) => t.code === "VAT16");
    if (byCode) return byCode.id;
    const byRate = salesTaxRates.find((t) => Math.abs(Number(t.rate) - 16) < 0.02);
    return byRate?.id;
  }, [salesTaxRates, salesSettings?.default_vat_rate]);

  const makeEmptyLine = useCallback((): DraftLine => {
    return {
      key: newLineKey(),
      product: "",
      quantity: "1",
      unit_price: "0",
      line_discount: "0",
      tax_rate: defaultVatRateId ?? "",
    };
  }, [defaultVatRateId]);

  const lineInputsForMath: LineInput[] = useMemo(
    () =>
      lines.map((l) => ({
        quantity: l.quantity,
        unit_price: l.unit_price,
        line_discount: l.line_discount,
        tax_rate_id: l.tax_rate === "" || l.tax_rate === null ? null : Number(l.tax_rate),
      })),
    [lines]
  );

  const totals = useMemo(
    () => computeInvoiceTotals(lineInputsForMath, taxRateMap, invoiceDiscount),
    [lineInputsForMath, taxRateMap, invoiceDiscount]
  );

  /** حساب افتراضي لحساب الإيراد عند وصول قائمة الحسابات (أول Revenue). */
  useEffect(() => {
    if (revenueAccountId !== "") return;
    if (salesSettings?.default_revenue_account_product) {
      setRevenueAccountId(salesSettings.default_revenue_account_product);
      return;
    }
    if (!revenueAccounts.length) return;
    setRevenueAccountId(revenueAccounts[0].id);
  }, [revenueAccounts, revenueAccountId, salesSettings?.default_revenue_account_product]);

  /** تطبيق القيم الافتراضية من الإعدادات عند أول تحميل. */
  useEffect(() => {
    if (!salesSettings) return;
    if (draftId) return; // لا تُغير فاتورة موجودة قيد التحرير
    if (customerId === "" && salesSettings.default_customer) {
      setCustomerId(salesSettings.default_customer);
    }
    if (currencyId === "" && salesSettings.default_currency) {
      setCurrencyId(salesSettings.default_currency);
    }
    // نوع الدفع — نُطبّقه مرة واحدة فقط إذا كان افتراضنا credit
    if (salesSettings.default_payment_type && invType !== salesSettings.default_payment_type) {
      setInvType(salesSettings.default_payment_type);
    }
    // إخفاء/إظهار معاينة القيد
    setShowPreview(salesSettings.show_journal_preview);
    // افتراضي تخفيض المخزون عند الترحيل
    setStockOnPost(salesSettings.stock_on_post_default);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [salesSettings?.default_customer, salesSettings?.default_currency, salesSettings?.show_journal_preview]);

  useEffect(() => {
    if (!salesSettings) return;
    if (draftId || draftToEditId) return;
    setPricesIncludeTax(Boolean(salesSettings.prices_include_tax));
  }, [salesSettings?.prices_include_tax, draftId, draftToEditId]);

  /** حساب افتراضي للصندوق عند التحويل إلى نقدي. */
  useEffect(() => {
    if (invType !== "cash") return;
    if (cashAccountId !== "") return;
    if (salesSettings?.default_cash_account) {
      setCashAccountId(salesSettings.default_cash_account);
      return;
    }
    if (!cashboxAccounts.length) return;
    setCashAccountId(cashboxAccounts[0].id);
  }, [invType, cashboxAccounts, cashAccountId, salesSettings?.default_cash_account]);

  /** T4: صندوق التحصيل الافتراضي — إعدادات المبيعات ثم أول صندوق في الشجرة. */
  useEffect(() => {
    if (collectCashAccountId !== "") return;
    const fallback = salesSettings?.default_cash_account ?? cashboxAccounts[0]?.id ?? null;
    if (fallback != null) setCollectCashAccountId(fallback);
  }, [collectCashAccountId, cashboxAccounts, salesSettings?.default_cash_account]);

  /* T4: رصيد العميل «على الحساب» = سنداته المرحّلة التي بقي منها غير موزَّع.
     نفس مصدر `SettleFromOnAccountModal` الذي حلّت هذه اللوحة محلّه هنا — مصدر
     واحد للرصيد لا اثنان. */
  useEffect(() => {
    if (customerId === "" || !networkOnline || !canPerm("sales.payment.create")) {
      setOnAccountVouchers([]);
      return;
    }
    let alive = true;
    listCustomerPayments({ partner: Number(customerId), page: 1, page_size: 200 })
      .then((rows) => {
        if (!alive) return;
        setOnAccountVouchers(
          (rows || [])
            .filter((p) => p.is_posted && Number(p.unallocated_amount ?? 0) > 0.009)
            .map((p) => ({ id: p.id, unallocated: Number(p.unallocated_amount ?? 0) })),
        );
      })
      .catch(() => { if (alive) setOnAccountVouchers([]); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId, networkOnline, onAccountKey]);

  /** معاينة القيد المحاسبي المباشرة — تطابق منطق post_sales_invoice في الخادم. */
  type PreviewLine = {
    accountId: number | null;
    accountLabel: string;
    debit: number;
    credit: number;
    description?: string;
  };

  const journalPreview = useMemo((): {
    lines: PreviewLine[];
    totalDebit: number;
    totalCredit: number;
    balanced: boolean;
    errors: string[];
    revenue: number;
    cogs: number;
    grossProfit: number;
    marginPct: number;
  } => {
    const errors: string[] = [];
    const out: PreviewLine[] = [];
    const grand = totals.grandTotal;
    const net = totals.subtotalExclTax;
    const tax = totals.taxAmount;

    if (grand <= 0) {
      return {
        lines: [],
        totalDebit: 0,
        totalCredit: 0,
        balanced: true,
        errors: [],
        revenue: 0,
        cogs: 0,
        grossProfit: 0,
        marginPct: 0,
      };
    }

    // 1) المدين — دائماً يُقيّد على ذمم العميل أولاً
    const custName =
      customerId !== "" ? customers.find((c) => c.id === Number(customerId))?.name : "";
    const arLabel = custName
      ? `ذمم مدينة — ${custName}`
      : "ذمم مدينة (سيُحدَّد تلقائياً من linked_account للعميل)";
    
    out.push({
      accountId: null,
      accountLabel: arLabel,
      debit: grand,
      credit: 0,
      description: "إثبات ذمم",
    });

    // 2) تسوية الدفعة النقدية إن وجدت
    if (invType === "cash") {
      if (cashAccountId === "") {
        errors.push("لم يُحدَّد حساب الصندوق/البنك الافتراضي — عيّنه في إعدادات المبيعات.");
      } else {
        const a = accountsById.get(Number(cashAccountId));
        out.push({
          accountId: Number(cashAccountId),
          accountLabel: a ? `${a.code || ""} — ${a.name || ""}` : `#${cashAccountId}`,
          debit: grand,
          credit: 0,
          description: "تحصيل نقدي",
        });
        out.push({
          accountId: null,
          accountLabel: arLabel,
          debit: 0,
          credit: grand,
          description: "تسوية ذمم (تحصيل نقدي)",
        });
      }
    }

    // 2) الدائن — الإيراد
    if (revenueAccountId === "") {
      errors.push("لم يُحدَّد حساب الإيراد الافتراضي — عيّنه في إعدادات المبيعات.");
    } else if (net > 0) {
      const a = accountsById.get(Number(revenueAccountId));
      out.push({
        accountId: Number(revenueAccountId),
        accountLabel: a ? `${a.code || ""} — ${a.name || ""}` : `#${revenueAccountId}`,
        debit: 0,
        credit: net,
        description: "إيراد مبيعات",
      });
    }

    // 3) الدائن — ضرائب مخرجات (تجميع حسب الحساب)
    const taxBuckets = new Map<number, number>();
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (l.tax_rate === "" || l.tax_rate === null) continue;
      const tr = taxRateById.get(Number(l.tax_rate));
      if (!tr || !tr.tax_account) continue;
      const d = (tr.direction || "both").toLowerCase();
      if (d !== "sales" && d !== "both") {
        errors.push(`الضريبة "${tr.code}" اتجاهها ${d} — غير صالحة للمبيعات.`);
        continue;
      }
      const amt = totals.perLine[i]?.lineTax || 0;
      if (amt > 0) {
        taxBuckets.set(tr.tax_account, (taxBuckets.get(tr.tax_account) || 0) + amt);
      }
    }
    taxBuckets.forEach((amt, accId) => {
      const a = accountsById.get(accId);
      out.push({
        accountId: accId,
        accountLabel: a ? `${a.code || ""} — ${a.name || ""}` : `#${accId}`,
        debit: 0,
        credit: amt,
        description: "ضريبة مخرجات",
      });
    });
    // تحقق تقريبي: مجموع الضريبة المحلوظة مقابل total tax
    const taxSum = Array.from(taxBuckets.values()).reduce((s, v) => s + v, 0);
    if (Math.abs(taxSum - tax) > 0.02 && tax > 0) {
      errors.push(
        `ضريبة غير مُسجَّلة: إجمالي الضريبة ${tax.toFixed(2)} لا يطابق ما سيُقيَّد ${taxSum.toFixed(
          2
        )}. تأكد من وجود tax_account لكل نسبة.`
      );
    }

    // 4) COGS / Inventory (إن كان خصم المخزون عند الترحيل)
    // M5: cost is computed unconditionally so gross profit can be shown even
    // when stock is not deducted at post-time; the journal lines below are
    // still only emitted when stock_on_post is enabled.
    let cogsTotal = 0;
    for (const l of lines) {
      if (l.product === "") continue;
      const p = productsById.get(Number(l.product));
      if (!p) continue;
      const avg = Number(p.avg_cost || 0);
      const qty = Number(l.quantity || 0);
      if (avg > 0 && qty > 0) {
        cogsTotal += avg * qty;
      }
    }
    if (stockOnPost) {
      if (cogsTotal > 0) {
        out.push({
          accountId: null,
          accountLabel: "تكلفة مبيعات (COGS) — يُحدَّد من فئة المنتج",
          debit: cogsTotal,
          credit: 0,
          description: "COGS",
        });
        out.push({
          accountId: null,
          accountLabel: "المخزون — يُحدَّد من فئة المنتج (أو 1104)",
          debit: 0,
          credit: cogsTotal,
          description: "صرف مخزون",
        });
      }
    }

    const totalDebit = out.reduce((s, r) => s + r.debit, 0);
    const totalCredit = out.reduce((s, r) => s + r.credit, 0);
    const balanced = Math.abs(totalDebit - totalCredit) < 0.02;
    if (!balanced && out.length > 0) {
      errors.push(
        `القيد غير متوازن: مدين ${totalDebit.toFixed(2)} ≠ دائن ${totalCredit.toFixed(2)}`
      );
    }
    // M5: gross profit = net revenue − cost of goods (estimate from WAC).
    const revenue = net;
    const grossProfit = revenue - cogsTotal;
    const marginPct = revenue > 0 ? (grossProfit / revenue) * 100 : 0;
    return {
      lines: out,
      totalDebit,
      totalCredit,
      balanced,
      errors,
      revenue,
      cogs: cogsTotal,
      grossProfit,
      marginPct,
    };
  }, [
    invType,
    cashAccountId,
    customerId,
    customers,
    revenueAccountId,
    lines,
    totals,
    taxRateById,
    accountsById,
    stockOnPost,
    productsById,
  ]);

  const applyDetail = useCallback((d: SalesInvoiceDetail) => {
    setInvoiceNumber(d.invoice_number || "");
    setCustomerId(d.customer);
    setInvDate(d.invoice_date);
    setDueDate(d.due_date || "");
    setInvType(d.invoice_type);
    setCurrencyId(d.currency);
    setExchangeRate(formatNumber(d.exchange_rate ?? 1, { maxDecimals: 6, fallback: "1" }));
    setInvoiceDiscount(formatQuantity(d.invoice_discount ?? 0, "0"));
    setStockOnPost(d.stock_on_post !== false);
    setNotes(d.notes || "");
    setCashAccountId(d.cash_or_bank_account ?? "");
    setRevenueAccountId(d.revenue_account ?? "");
    setDraftId(d.id);
    setInvoiceStatus(d.status || "draft");
    setPostedJournalId(d.journal ?? null);
    setPaidAmount(Number((d as { amount_paid?: number | string }).amount_paid ?? 0));
    setPendingIntent(
      Number((d as { pending_payment_total?: number | string }).pending_payment_total ?? 0),
    );
    setIntentCash(Number(d.attached_cash_amount ?? 0));
    setIntentCashAccountId(d.attached_cash_account ?? null);
    setAttachedCheques(d.cheques || []);
    setSavedGrandTotal(Number((d as { grand_total?: number | string }).grand_total ?? 0));
    setPaymentStatusDisplay(d.payment_status_display || "غير مدفوعة");
    setDeliveryStatusDisplay(d.delivery_status_display || "غير مسلَّمة");
    setDeliveryStatus(d.delivery_status || "not_delivered");
    setCustomerBalanceBeforeInvoice(Number(d.customer_balance_before_invoice || 0));
    setCustomerBalanceAfterInvoice(Number(d.customer_balance_after_invoice || 0));
    setStockMovementNo(d.stock_movement_no ?? null);
    setPaymentDetails(d.payment_details || []);
    setSourceDocument(d.source_document ?? null);
    setInvoiceKind(d.invoice_kind || "sale");
    setOriginalInvoiceId(d.original_invoice ?? null);
    setOriginalInvoiceNumber(d.original_invoice_number ?? null);
    setProductPickerLineKey(null);
    setTaxEditKey(null);
    setTaxPercentDraft({});
    // M2-T1
    setBookNumber(String(d.book_number ?? 0));
    setSecondDate(d.second_date || "");
    setLicensedDealerNo(d.licensed_dealer_no || "");
    setSettlementInvoiceNo(d.settlement_invoice_no || "");
    setPricesIncludeTax(Boolean(d.prices_include_tax));
    setDiscountPercent(formatQuantity(d.discount_percent ?? 0, "0"));
    // M2-T4
    setSourceDiscountPctOverride(
      d.source_discount_percent_override == null
        ? ""
        : formatQuantity(d.source_discount_percent_override, "")
    );
    setSourceDiscountAmtOverride(
      d.source_discount_amount_override == null
        ? ""
        : formatQuantity(d.source_discount_amount_override, "")
    );
    setLines(
      d.lines.map((ln) => ({
        key: newLineKey(),
        id: ln.id,
        product: ln.product,
        quantity: formatQuantity(ln.quantity, "0"),
        unit_price: formatQuantity(ln.unit_price, "0"),
        line_discount: formatQuantity(ln.line_discount ?? 0, "0"),
        tax_rate: ln.tax_rate != null ? ln.tax_rate : null,
        // FEAT-2: أسعار فاتورة محمَّلة مُثبّتة — لا يُعاد تسعيرها عند تغيير العميل.
        priceTouched: true,
        // T-SERIAL: الاختيار نيّةٌ على البند تبقى بعد إلغاء الترحيل، فإعادة
        // الترحيل تستهلك الوحدات ذاتها لا غيرها.
        serials: Array.isArray(ln.serials) ? ln.serials.map(String) : [],
        internal_note: ln.internal_note ?? "",
        customer_note: ln.customer_note ?? "",
      }))
    );
    dirtyRef.current = false;
  }, []);

  const fetchNextInvoiceNumber = useCallback(async (bookNumStr: string) => {
    try {
      const next = await getNextInvoiceNumber(Number(bookNumStr) || 0);
      if (next) setInvoiceNumber(next);
    } catch (e) {
      console.warn("Failed to fetch next invoice number preview:", e);
    }
  }, []);

  useEffect(() => {
    if (draftId || draftToEditId) return;
    fetchNextInvoiceNumber(bookNumber);
  }, [bookNumber, draftId, draftToEditId, fetchNextInvoiceNumber]);

  useEffect(() => {
    if (draftToEditId == null) return;
    setViewMode(true);
    let cancelled = false;
    (async () => {
      try {
        const d = await getSalesInvoice(draftToEditId);
        if (!cancelled) applyDetail(d);
        setMsg(null);
        setLocalErr(null);
      } catch (e) {
        if (!cancelled) {
          const raw = humanizeThrown(e, "فشل تحميل الفاتورة");
          const friendly =
            /not found|404|غير موجود/i.test(raw) || /^\.?\s*not\s*found/i.test(raw)
              ? "الفاتورة غير موجودة أو حُذفت."
              : raw;
          setLocalErr(friendly);
        }
      } finally {
        if (!cancelled) onDraftEditConsumed();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [draftToEditId, applyDetail, onDraftEditConsumed]);

  useEffect(() => {
    if (!currencies.length) return;
    if (draftToEditId != null) return;
    setCurrencyId((prev) => {
      if (prev === "") return currencies[0].CurrencyID;
      const ok = currencies.some((c) => c.CurrencyID === prev);
      return ok ? prev : currencies[0].CurrencyID;
    });
  }, [currencies, draftToEditId]);

  useEffect(() => {
    if (defaultVatRateId == null) return;
    if (draftToEditId != null) return;
    if (draftId != null) return;
    setLines((prev) =>
      prev.map((l) => (l.tax_rate === "" ? { ...l, tax_rate: defaultVatRateId } : l))
    );
  }, [defaultVatRateId, draftToEditId, draftId]);

  // M5: fetch the customer's balance as soon as a customer is selected (for
  // both cash and credit invoices) so the current balance + debtor/creditor
  // status can be shown immediately. The credit-limit warning still only
  // applies to credit invoices (handled at the display layer).
  useEffect(() => {
    if (customerId === "") {
      setCreditHint(null);
      return;
    }
    const t = window.setTimeout(() => {
      getCreditPreview({
        customer: Number(customerId),
        proposed_total: totals.grandTotal.toFixed(2),
        excludeInvoice: draftId ?? undefined,
      })
        .then(setCreditHint)
        .catch(() => setCreditHint(null));
    }, 400);
    return () => clearTimeout(t);
  }, [customerId, totals.grandTotal, draftId]);

  // ── M4: beforeunload guard ─────────────────────────────────────────────
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current && invoiceStatus === "draft") {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [invoiceStatus]);

  const markDirty = () => {
    dirtyRef.current = true;
  };

  const isPosted = invoiceStatus === "posted";
  const readOnly = isPosted || viewMode;
  const invoicePermissions = invoiceActionPermissions("sales", draftId == null, canPerm);

  /* ───────────── THA-110: قناع «الوضع السهل» ─────────────
     إخفاءٌ عرضيٌّ بحت: العنصر المخفيّ يحتفظ بقيمته وحالته كما هما، فتبقى حمولة
     `buildPayload` من الوضع السهل مطابقةً لحمولة الوضع المتقدّم حين يترك مستخدمه
     الافتراضيات — لا يتغيّر قيدٌ ولا سطرٌ واحد، ولا سطر خادميّ واحد تغيَّر.
     يسمّر هذا التطابقَ `sales/tests/test_simple_mode_journal_parity.py`.

     وقاعدة السقوط للأمان فوق قائمة الإخفاء كلها: **حقلٌ مطلوبٌ لم يُحَلّ افتراضيُه
     يظهر رغم الوضع** — لا فشل صامت، ولا حالة بلا مخرج. */
  const simpleMode = uiMode === "simple";
  /** افتراضٌ مطلوبٌ لم يُحَلّ ⇒ `validateClient` سيرفض الحفظ، فلا يُخفى تفسيرُه. */
  const unresolvedRequiredDefault =
    (invType === "cash" && cashAccountId === "") || revenueAccountId === "";
  /** العملة تُخفى فقط حين حسمها افتراضُ الإعدادات فعلاً. */
  const showCurrencyField =
    !simpleMode || !salesSettings?.default_currency || currencyId === "";
  /** «شامل الضريبة» يبقى على افتراضي الإعدادات — والقيمة تُرسَل كما هي. */
  const showTaxInclusiveToggle = !simpleMode;
  /* THA-131: حقلا الحالة يتبعان الحالة نفسها لا وضعَ الواجهة — الاستحقاق مفهومٌ
     آجلٌ بحت، والصندوق مفهومٌ نقديٌّ بحت. فتبديل «نقدي» يبدّل الحقلين فوراً في
     الوضعين. القيمة المخفيّة تبقى كما هي (قانون قناع THA-110 أعلاه)، فلا حمولة
     تتغيّر بمجرّد الإخفاء. */
  /** الفاتورة النقدية مدفوعةٌ عند الترحيل فلا استحقاق لها — الحقل للآجلة. */
  const showDueDateField = invType !== "cash";
  /** الصندوق وجهةُ نقد الفاتورة النقدية — والوضع السهل يُخفيه: افتراضُه محلولٌ
   *  دائماً (الإعدادات ثم أول صندوق في الشجرة)، وحين لا يُحلّ فلأنه لا صندوق في
   *  الشجرة أصلاً — وحقلُ اختيارٍ بلا خيارات لا يُخرج من ذلك، بل تحذيرُ
   *  «بيانات أخرى» الذي يفرضه `unresolvedRequiredDefault`. */
  const showCashAccountField = invType === "cash" && !simpleMode;
  /** التبويبات المتقدّمة (القيد/الحركات/السجل) — تُطوى في الوضع السهل. */
  const showAdvancedTabs = !simpleMode;
  /** «بيانات أخرى» يحمل تحذيرات الإعداد: يبقى ظاهراً ما دام تحذيرٌ حيّاً. */
  const showOtherTab = !simpleMode || unresolvedRequiredDefault;

  const buildPayload = useCallback(() => {
    const body: Record<string, unknown> = {
      customer: customerId,
      invoice_date: invDate,
      due_date: dueDate || null,
      invoice_type: invType,
      currency: currencyId,
      exchange_rate: Number(exchangeRate) || 1,
      invoice_discount: Number(invoiceDiscount) || 0,
      stock_on_post: stockOnPost,
      notes: notes || "",
      lines: lines
        .filter((l) => l.product !== "")
        .map((l) => ({
          ...(l.id ? { id: l.id } : {}),
          product: l.product,
          quantity: l.quantity,
          unit_price: l.unit_price,
          line_discount: Number(l.line_discount) || 0,
          tax_rate: l.tax_rate === "" || l.tax_rate === null ? null : l.tax_rate,
          // T-SERIAL: يُرسَل دائماً — القائمة الفارغة تمسح اختياراً سابقاً بدل
          // أن يبقى معلّقاً على البند بلا ظهور في الشاشة.
          serials: l.serials ?? [],
          // الملاحظتان حقلان مستقلّان حتى في الحمولة: الداخلية لا تمرّ بأي
          // مسارٍ يُطبع، والمطبوعة لا تحمل ما كُتب للموظف.
          internal_note: l.internal_note ?? "",
          customer_note: l.customer_note ?? "",
        })),
      // ── M2-T1: Aseel header fields ───────────────────────────────
      book_number: Number(bookNumber) || 0,
      second_date: secondDate || null,
      licensed_dealer_no: licensedDealerNo || "",
      settlement_invoice_no: settlementInvoiceNo || "",
      prices_include_tax: pricesIncludeTax,
      discount_percent: Number(discountPercent) || 0,
      // ── M2-T4: Source discount overrides (null = use customer default) ─
      source_discount_percent_override:
        sourceDiscountPctOverride === "" ? null : Number(sourceDiscountPctOverride),
      source_discount_amount_override:
        sourceDiscountAmtOverride === "" ? null : Number(sourceDiscountAmtOverride),
    };
    if (invType === "cash" && cashAccountId !== "") body.cash_or_bank_account = cashAccountId;
    if (revenueAccountId !== "") body.revenue_account = revenueAccountId;
    return body;
  }, [
    customerId,
    invDate,
    dueDate,
    invType,
    currencyId,
    exchangeRate,
    invoiceDiscount,
    stockOnPost,
    notes,
    lines,
    cashAccountId,
    revenueAccountId,
    bookNumber,
    secondDate,
    licensedDealerNo,
    settlementInvoiceNo,
    pricesIncludeTax,
    discountPercent,
    sourceDiscountPctOverride,
    sourceDiscountAmtOverride,
  ]);

  // ── M4: local-draft persistence (Dexie) ────────────────────────────────
  const activeTenantId = resolveTenantId();
  const localDraftKey = tenantScopedOfflineKey(
    activeTenantId,
    draftId ? String(draftId) : "new",
  );

  const clearLocalDraft = useCallback(async () => {
    try {
      await db.invoice_drafts.delete(localDraftKey);
    } catch {
      /* best-effort cleanup */
    }
  }, [localDraftKey]);

  // Debounced autosave: mirrors the in-progress draft to IndexedDB so an
  // accidental reload/close does not lose unsaved work. Declared AFTER
  // buildPayload so the dependency reference is past its TDZ.
  useEffect(() => {
    if (!dirtyRef.current || invoiceStatus !== "draft") return;
    const t = window.setTimeout(() => {
      void db.invoice_drafts
        .put({
          draft_id: localDraftKey,
          tenant_id: activeTenantId,
          data: JSON.stringify(buildPayload()),
          updated_at: new Date().toISOString(),
        })
        .catch((err) => console.error("Autosave to Dexie failed:", err));
    }, 2000);
    return () => clearTimeout(t);
  }, [buildPayload, localDraftKey, invoiceStatus]);

  // Restore-on-return: for a brand-new (unsaved) invoice, offer to recover the
  // last autosaved draft instead of silently discarding it.
  const [recoverableDraft, setRecoverableDraft] = useState<{
    data: Record<string, unknown>;
    updated_at: string;
  } | null>(null);

  useEffect(() => {
    if (draftToEditId != null || draftId != null) return;
    let cancelled = false;
    (async () => {
      try {
        const row = await db.invoice_drafts.get(localDraftKey);
        if (
          cancelled ||
          !row?.data ||
          !isOfflineRecordForTenant(row, activeTenantId)
        ) return;
        const parsed = JSON.parse(row.data) as Record<string, unknown>;
        const hasContent =
          Array.isArray(parsed.lines) && (parsed.lines as unknown[]).length > 0;
        if (hasContent) setRecoverableDraft({ data: parsed, updated_at: row.updated_at });
      } catch {
        /* corrupt/absent draft — ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
    // run once on mount for a fresh invoice
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hydrateFromLocalDraft = useCallback(
    (p: Record<string, unknown>) => {
      const s = (v: unknown, fb = "") => (v == null ? fb : String(v));
      setCustomerId((p.customer as number) ?? "");
      if (p.invoice_date) setInvDate(s(p.invoice_date));
      setDueDate(s(p.due_date));
      if (p.invoice_type === "cash" || p.invoice_type === "credit")
        setInvType(p.invoice_type);
      setCurrencyId((p.currency as number) ?? "");
      setExchangeRate(formatNumber(p.exchange_rate ?? 1, { maxDecimals: 6, fallback: "1" }));
      setInvoiceDiscount(formatQuantity(p.invoice_discount, "0"));
      setStockOnPost(p.stock_on_post !== false);
      setNotes(s(p.notes));
      setBookNumber(s(p.book_number, "0"));
      setSecondDate(s(p.second_date));
      setLicensedDealerNo(s(p.licensed_dealer_no));
      setSettlementInvoiceNo(s(p.settlement_invoice_no));
      setPricesIncludeTax(Boolean(p.prices_include_tax));
      setDiscountPercent(formatQuantity(p.discount_percent, "0"));
      setSourceDiscountPctOverride(
        p.source_discount_percent_override == null
          ? ""
          : formatQuantity(p.source_discount_percent_override, "")
      );
      setSourceDiscountAmtOverride(
        p.source_discount_amount_override == null
          ? ""
          : formatQuantity(p.source_discount_amount_override, "")
      );
      if (p.cash_or_bank_account != null)
        setCashAccountId(p.cash_or_bank_account as number);
      if (p.revenue_account != null) setRevenueAccountId(p.revenue_account as number);
      const rawLines = Array.isArray(p.lines) ? (p.lines as Record<string, unknown>[]) : [];
      if (rawLines.length) {
        setLines(
          rawLines.map((ln) => ({
            key: newLineKey(),
            id: typeof ln.id === "number" ? ln.id : undefined,
            product: (ln.product as number) ?? "",
            quantity: formatQuantity(ln.quantity, "0"),
            unit_price: formatQuantity(ln.unit_price, "0"),
            line_discount: formatQuantity(ln.line_discount, "0"),
            tax_rate:
              ln.tax_rate === "" || ln.tax_rate == null ? null : (ln.tax_rate as number),
            // FEAT-2: أسعار مستعادة من المسودة مُثبّتة — لا يُعاد تسعيرها تلقائياً.
            priceTouched: true,
          }))
        );
      }
      dirtyRef.current = true;
    },
    []
  );

  const validateClient = (): string | null => {
    if (customerId === "") return "اختر العميل.";
    if (currencyId === "") return "اختر العملة.";
    if (invType === "cash" && cashAccountId === "")
      return "حساب الصندوق/البنك غير مُعيَّن في إعدادات المبيعات.";
    if (revenueAccountId === "") return "حساب الإيراد غير مُعيَّن في إعدادات المبيعات.";
    const filled = lines.filter((l) => l.product !== "");
    if (!filled.length) return "أضف بنداً واحداً على الأقل.";
    for (const l of filled) {
      const q = Number(l.quantity);
      const p = Number(l.unit_price);
      if (!(q > 0)) return "الكمية يجب أن تكون أكبر من صفر في كل السطور المكتملة.";
      if (p < 0 || Number.isNaN(p)) return "سعر الوحدة غير صالح.";
      // M3: selling below available stock is permitted (business rule).
      // The backend enforces/logs the negative-stock policy; the client no
      // longer hard-blocks over-sell here.
    }
    return null;
  };

  // منع فاتورة الخسارة (إعداد اختياري) — يُطابق الحارس الخادمي guard_loss_invoice:
  // على مستوى **السطر** (صافي إيراد السطر بعد الخصومات < كمية×متوسط التكلفة)، حتى لو
  // كان إجمالي الفاتورة رابحاً. يسمّي الأسطر المخالفة. المفتاح OFF = السماح بالحفظ.
  const lossBlockMessage = (): string | null => {
    if (!salesSettings?.block_loss_invoices) return null;
    const offenders: string[] = [];
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (l.product === "") continue;
      const p = productsById.get(Number(l.product));
      if (!p) continue;
      const cost = Number(p.avg_cost || 0) * Number(l.quantity || 0);
      const revenue = totals.perLine[i]?.lineNetAdjusted ?? 0;
      if (revenue - cost < 0) {
        const name = p.name_ar || p.name_en || p.sku || `#${l.product}`;
        offenders.push(`«${name}» (التكلفة ${fmt(cost)} أعلى من صافي البيع ${fmt(revenue)})`);
      }
    }
    if (offenders.length === 0) return null;
    return (
      `لا يُسمح بحفظ فاتورة تحتوي بنداً يُباع بخسارة: ${offenders.join("؛ ")}. ` +
      "عدّل الأسعار أو فعّل «السماح بحفظ فاتورة بخسارة» من إعدادات المبيعات."
    );
  };

  const handleSaveDraft = async (): Promise<{ id: number; posted: boolean } | undefined> => {
    setLocalErr(null);
    setMsg(null);
    setSaveFieldErrors({});
    if (!invoicePermissions.canSave) {
      setLocalErr("لا تملك صلاحية حفظ هذه الفاتورة.");
      return;
    }
    const v = validateClient();
    if (v) {
      setLocalErr(v);
      return;
    }
    const lossErr = lossBlockMessage();
    if (lossErr) {
      setLocalErr(lossErr);
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload();
      let activeDraftId = draftId;
      let savedInvoice: SalesInvoiceDetail;
      if (draftId) {
        const updated = await patchSalesInvoice(draftId, payload);
        savedInvoice = updated;
        applyDetail(updated);
        setMsg("تم حفظ المسودة.");
      } else {
        const created = await createSalesInvoice({ ...payload, auto_post: false });
        savedInvoice = created;
        activeDraftId = created.id;
        setDraftId(created.id);
        applyDetail(created);
        if (created.status === "posted") {
          setMsg(
            `تم إنشاء وترحيل الفاتورة ${created.invoice_number} (ترحيل تلقائي)`,
          );
        } else {
          setMsg(`تم إنشاء المسودة ${created.invoice_number}`);
        }
      }

      dirtyRef.current = false;
      // M4: the draft is now persisted server-side — drop the local recovery copy.
      void clearLocalDraft();
      setRecoverableDraft(null);
      onInvoiceSaved();
      return { id: activeDraftId as number, posted: savedInvoice.status === "posted" };
    } catch (e) {
      setLocalErr(humanizeThrown(e, "فشل الحفظ"));
      setSaveFieldErrors(
        (e as { fieldErrors?: Record<string, string> })?.fieldErrors ?? {},
      );
    } finally {
      setSaving(false);
    }
  };

  /** يرحّل الفاتورة. `idOverride` لمن يحفظ ويرحّل في نفس النقرة (حالة الـid لم
   *  تُحدَّث بعد). يُعيد true عند النجاح كي يتابع المتصل خطوته التالية. */
  const handlePost = async (idOverride?: number) => {
    if (!invoicePermissions.canPost) {
      setLocalErr("لا تملك صلاحية ترحيل فاتورة البيع.");
      return false;
    }
    const targetId = idOverride ?? draftId;
    if (!targetId) {
      setLocalErr("احفظ المسودة أولاً ثم رحّل.");
      return false;
    }
    setLocalErr(null);
    setMsg(null);
    const v = validateClient();
    if (v) {
      setLocalErr(v);
      return false;
    }
    const lossErr = lossBlockMessage();
    if (lossErr) {
      setLocalErr(lossErr);
      return false;
    }
    if (!journalPreview.balanced || journalPreview.errors.length) {
      setLocalErr(
        "القيد غير صالح أو غير متوازن في المعاينة. صحّح الأخطاء المعروضة ثم أعد المحاولة."
      );
      return false;
    }
    setPosting(true);
    try {
      if (dirtyRef.current) await patchSalesInvoice(targetId, buildPayload());
      const posted = await postSalesInvoice(targetId);
      // T-CASH2: تسوية البيع النقدي تتمّ خادمياً ذرّياً مع الترحيل (سند قبض مستقل)،
      // فالردّ يحمل المحصَّل وحالة الدفع الجديدين — نطبّقه كاملاً لا حالةً وقيداً فقط،
      // وإلا بقيت الشاشة تقول «غير مدفوعة» حتى إعادة التحميل.
      applyDetail(posted);
      setMsg(
        posted.journal
          ? `تم الترحيل — القيد #${posted.journal}`
          : "تم الترحيل بنجاح."
      );
      void clearLocalDraft();
      setRecoverableDraft(null);
      onInvoiceSaved();
      return true;
    } catch (e) {
      setLocalErr(humanizeThrown(e, "فشل الترحيل"));
      return false;
    } finally {
      setPosting(false);
    }
  };

  // Feature 1: التراجع عن الترحيل — حذف قيود الفاتورة وإرجاعها مسودة قابلة للتعديل/الحذف.
  const handleUnpost = async () => {
    if (!draftId) return;
    if (!(await confirm({
      message:
        "هذا المستند مرحَّل. سيؤدي التراجع عن الترحيل إلى حذف كل قيود اليومية " +
        "وحركات المخزون الخاصة بهذه الفاتورة وإرجاعها مسودة. متابعة؟",
      confirmText: "متابعة",
    }))) return;
    setLocalErr(null);
    setMsg(null);
    setPosting(true);
    try {
      const inv = await unpostSalesInvoice(draftId);
      // الخادم يصفّر المحصَّل عند إلغاء الترحيل — نطبّق الردّ كاملاً كي لا يبقى
      // «المحصَّل» القديم معروضاً على فاتورةٍ عادت مسودة.
      applyDetail(inv);
      setMsg("تم التراجع عن الترحيل وحذف القيود. الفاتورة الآن مسودة.");
      onInvoiceSaved();
    } catch (e) {
      setLocalErr(humanizeThrown(e, "تعذر التراجع عن الترحيل"));
    } finally {
      setPosting(false);
    }
  };

  const resetForm = () => {
    setDraftId(null);
    setInvoiceNumber("");
    setInvoiceStatus("draft");
    setPostedJournalId(null);
    setPaidAmount(0);
    setPendingIntent(0);
    setIntentCash(0);
    setIntentCashAccountId(null);
    setAttachedCheques([]);
    setSavedGrandTotal(0);
    setPaymentStatusDisplay("غير مدفوعة");
    setDeliveryStatusDisplay("غير مسلَّمة");
    setDeliveryStatus("not_delivered");
    setCustomerBalanceBeforeInvoice(0);
    setCustomerBalanceAfterInvoice(0);
    setStockMovementNo(null);
    setPaymentDetails([]);
    setSourceDocument(null);
    setInvoiceKind("sale");
    setOriginalInvoiceId(null);
    setOriginalInvoiceNumber(null);
    // تطبيق العميل الافتراضي من الإعدادات
    setCustomerId(salesSettings?.default_customer ?? "");
    setInvDate(new Date().toISOString().slice(0, 10));
    setDueDate("");
    setInvType("credit");
    if (salesSettings?.default_currency) setCurrencyId(salesSettings.default_currency);
    else if (currencies.length) setCurrencyId(currencies[0].CurrencyID);
    setExchangeRate("1");
    setInvoiceDiscount("0");
    setCashAccountId(salesSettings?.default_cash_account ?? "");
    if (salesSettings?.default_revenue_account_product)
      setRevenueAccountId(salesSettings.default_revenue_account_product);
    else if (revenueAccounts.length) setRevenueAccountId(revenueAccounts[0].id);
    else setRevenueAccountId("");
    setStockOnPost(salesSettings?.stock_on_post_default ?? true);
    setNotes("");
    setProductPickerLineKey(null);
    setTaxEditKey(null);
    setTaxPercentDraft({});
    setLines([makeEmptyLine()]);
    // M2 resets
    setBookNumber("0");
    setSecondDate("");
    setLicensedDealerNo("");
    setSettlementInvoiceNo("");
    setPricesIncludeTax(Boolean(salesSettings?.prices_include_tax));
    setDiscountPercent("0");
    setSourceDiscountPctOverride("");
    setSourceDiscountAmtOverride("");
    setMsg(null);
    setLocalErr(null);
    fetchNextInvoiceNumber("0");
    dirtyRef.current = false;
  };

  // T-R4: حارس التغييرات غير المحفوظة — يُستدعى من «إضافة/جديدة» و«إلغاء». بدل
  // التجاهل الصامت للعمل، يسأل المستخدم ويُتيح الحفظ قبل المغادرة (سلوك احترافي).
  const guardedReset = async () => {
    const hasContent = lines.some((l) => l.product !== "" && l.product !== -1);
    if (!isPosted && dirtyRef.current && hasContent) {
      const proceed = await confirm({
        message: "لديك تغييرات غير محفوظة في هذه الفاتورة. المتابعة بفاتورة جديدة؟",
        confirmText: "متابعة",
        cancelText: "عودة",
        danger: false,
      });
      if (!proceed) return;
      const save = await confirm({
        message: "هل تريد حفظ هذه الفاتورة قبل البدء بفاتورة جديدة؟",
        confirmText: "حفظ ثم جديدة",
        cancelText: "تجاهل التغييرات",
        danger: false,
      });
      if (save) {
        await handleSaveDraft();
        resetForm();
        return;
      }
    }
    resetForm();
  };

  const addRow = () => {
    if (readOnly) return;
    setLines((prev) => [...prev, makeEmptyLine()]);
    markDirty();
  };

  /** يُدرج صنفاً في أول سطر فارغ (أو سطر جديد) ثم يجلب سعره — مدخل موحّد
   *  للشجرة وزر «موافق» في بطاقة الصنف. */
  const insertProductIntoInvoice = (
    productId: number,
    opts?: { quantity?: number; unitPrice?: number; source?: DraftLine["priceSource"] }
  ) => {
    if (!productId || readOnly || isPosted) return;
    // T-R3/M5: Duplicate checking logic has been moved to onSelectProduct 
    // to unify behavior across both tree picker and inline combobox.
    let targetKey = "";
    setLines((prev) => {
      const emptyIdx = prev.findIndex((l) => l.product === "" && !l.description);
      if (emptyIdx >= 0) {
        targetKey = prev[emptyIdx].key;
        const next = [...prev];
        next[emptyIdx] = { ...next[emptyIdx], product: -1 };
        return next;
      }
      const newLine = makeEmptyLine();
      newLine.product = -1;
      targetKey = newLine.key;
      return [...prev, newLine];
    });
    setTimeout(() => onSelectProduct(targetKey, productId, opts), 0);
  };

  const removeRow = (key: string) => {
    if (readOnly) return;
    setLines((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.key !== key)));
    markDirty();
  };

  const updateLine = (key: string, patch: Partial<DraftLine>) => {
    if (readOnly) return;
    setLines((prev) => {
      const next = prev.map((r) => (r.key === key ? { ...r, ...patch } : r));
      const lastLine = next[next.length - 1];
      // T-R1: أبقِ سطراً فارغاً واحداً فقط في الذيل. أضِف سطراً جديداً عندما يكتسب
      // آخر سطر صنفاً حقيقياً فقط — لا بناءً على الكمية. (الخلل السابق: makeEmptyLine
      // يبدأ بالكمية "1" فكان كل سطر فارغ يُحسب «ممتلئاً» وتتكاثر السطور الوهمية.)
      const lastHasProduct = lastLine && lastLine.product !== "" && lastLine.product !== -1;
      if (lastHasProduct) {
        return [...next, makeEmptyLine()];
      }
      return next;
    });
    markDirty();
  };

  const commitTaxPercent = async (lineKey: string) => {
    const raw = taxPercentDraft[lineKey];
    setTaxEditKey(null);
    const pct = raw === undefined || raw === "" ? NaN : Number(raw);
    if (!Number.isFinite(pct) || pct < 0) return;
    if (pct === 0) {
      updateLine(lineKey, { tax_rate: null });
      return;
    }
    const match = salesTaxRates.find((t) => Math.abs(Number(t.rate) - pct) < 0.02);
    if (match) {
      updateLine(lineKey, { tax_rate: match.id });
      return;
    }
    const base = salesTaxRates.find((t) => t.code === "VAT16") || salesTaxRates[0];
    const accId = base?.tax_account;
    if (accId == null) {
      setLocalErr(
        "لا يوجد حساب ضريبة مرجعي للمبيعات. حدّث الصفحة بعد تشغيل الترحيلات أو أضف نسبة من الإدارة."
      );
      return;
    }
    setTaxSavingKey(lineKey);
    setLocalErr(null);
    try {
      const code = `VAT_${pct}_${Date.now().toString(36)}`.slice(0, 20);
      const created = (await apiPostObject(
        "accounting/tax-rates/",
        {
          name: `ضريبة ${pct}%`,
          code,
          rate: String(pct),
          tax_account: accId,
          direction: "sales",
          is_active: true,
        },
        { tenantId: resolveTenantId() }
      )) as { id: number };
      onInvoiceSaved();
      updateLine(lineKey, { tax_rate: created.id });
    } catch (e) {
      setLocalErr(humanizeThrown(e, "فشل حفظ نسبة الضريبة"));
    } finally {
      setTaxSavingKey(null);
    }
  };

  // DEF-005: ترجمة نوع مصدر السعر من الـ resolver إلى شارة السطر.
  const priceSourceFromResolve = (docType?: string): DraftLine["priceSource"] => {
    if (docType === "SALES_INVOICE") return "last_invoice";
    if (docType === "SALES_QUOTATION") return "sales_quote";
    if (docType === "CUSTOMER_QUOTE") return "quote";
    // سعر عام من كرت الصنف — أضعف المصادر (لا عرض لهذا الزبون ولا شراء سابق).
    if (docType === "PRODUCT_SALE_PRICE") return "default";
    return null;
  };
  // رابط فتح مصدر السعر: عرض «واجهة العروض» أو تبويب «عرض السعر» بكرت الزبون.
  const priceSourceLinkFromResolve = (
    source?: { document_type?: string; document_id?: number | null },
  ): string | null => {
    if (source?.document_type === "SALES_QUOTATION" && source.document_id != null)
      return `/sales/quotations?open=${source.document_id}`;
    if (source?.document_type === "CUSTOMER_QUOTE" && customerId !== "")
      return `/partners/${customerId}?tab=price_list`;
    return null;
  };

  const onSelectProduct = async (
    key: string,
    productId: number,
    opts?: { quantity?: number; unitPrice?: number; source?: DraftLine["priceSource"] }
  ) => {
    const pr = productsById.get(productId);

    // T-R3 / M5: تنبيه عند تكرار الصنف (نفس سلوك فاتورة الشراء)
    const isDuplicate = lines.some(
      (l) => l.key !== key && l.product !== "" && l.product !== -1 && Number(l.product) === Number(productId)
    );
    if (isDuplicate && (salesSettings?.warn_on_duplicate_item ?? true)) {
      const merge = await confirm({
        message: `الصنف «${pr?.name_ar || productId}» مضاف مسبقاً في الفاتورة. اختر الإجراء:`,
        confirmText: "دمج الكمية",
        cancelText: "سطر جديد مستقل",
        danger: false,
      });
      if (merge) {
        // ابحث عن السطر الأصلي الذي يحوي هذا الصنف واجمع الكميات
        setLines((prev) => {
          const next = [...prev];
          const dupIndex = next.findIndex(
            (l) => l.key !== key && l.product !== "" && l.product !== -1 && Number(l.product) === Number(productId)
          );
          if (dupIndex >= 0) {
            const addedQty = opts?.quantity ?? 1;
            next[dupIndex] = {
              ...next[dupIndex],
              quantity: String((Number(next[dupIndex].quantity) || 0) + addedQty),
            };
          }
          // أفرغ السطر الحالي (الذي اختار فيه المستخدم الصنف المكرر)
          const currentIdx = next.findIndex((l) => l.key === key);
          if (currentIdx >= 0) {
            next[currentIdx] = { ...next[currentIdx], product: "", quantity: "0", unit_price: "0", priceTouched: false };
          }
          return next;
        });
        markDirty();
        return;
      }
    }

    // T-R2: عند تمرير سعر من بطاقة الصنف نستخدمه ونثبّته (priceTouched) فلا يدهسه
    // الـ resolver؛ وإلا نبدأ بسعر البيع الافتراضي ثم نقترح عبر الـ resolver.
    const price =
      opts?.unitPrice != null
        ? String(opts.unitPrice)
        : pr?.sale_price != null && pr.sale_price !== ""
        ? String(pr.sale_price)
        : pr?.online_price != null && pr.online_price !== ""
        ? String(pr.online_price)
        : "0";
    // P3-2-b: when offline, warn the user if the product row is from the
    // local cache and older than 1 hour. The cached row may show a stale
    // quantity which the user is about to commit to a sale.
    if (!networkOnline) {
      try {
        const cached = await db.products.get(productId);
        if (cached && isOfflineRecordForTenant(cached, activeTenantId)) {
          const ageMs = Date.now() - new Date(cached.updated_at).getTime();
          if (ageMs > 3600_000) {
            const verdict = await confirmStale(
              pr?.name_ar || cached.sku || String(productId),
              "—",
              cached.updated_at,
            );
            if (verdict === "cancel") return;
          }
        }
      } catch { /* IndexedDB unavailable — fall through without blocking */ }
    }
    updateLine(key, {
      product: productId,
      unit_price: price,
      priceSource: opts?.source ?? null,
      // T-SERIAL: وحدات الصنف السابق لا معنى لها على صنف جديد.
      serials: [],
      // سعر مُدخَل من البطاقة = مُثبّت (لا يُعاد تسعيره تلقائياً).
      ...(opts?.unitPrice != null ? { quantity: String(opts.quantity ?? 1), priceTouched: true } : {}),
    });
    // FEAT-2 / DEF-005: اقترح سعر الوحدة عبر PriceResolver المشترك — آخر سعر
    // دفعه هذا العميل لهذا الصنف (يفوز دائماً)، ثم عرض السعر اليدوي، ثم سعر البيع
    // الافتراضي، ثم فارغ. القيمة تبقى قابلة للتعديل، ولا تُدَس على سطر حرّره
    // المستخدم يدوياً (edit-protection). الشارة تعكس مصدر السعر.
    if (networkOnline && opts?.unitPrice == null) {
      resolveSalePrice({
        product: productId,
        customer: customerId,
        currency: currencyId,
        exchange_rate: exchangeRate,
        tax_inclusive: pricesIncludeTax,
      })
        .then((res) => {
          if (res?.unit_price == null) return;
          const src = priceSourceFromResolve(res.source?.document_type);
          const link = priceSourceLinkFromResolve(res.source);
          // DEF-003: عرض السعر المقترح دون أصفار عشرية زائدة (يبقى قابلاً للتحرير).
          const shown = Number(res.unit_price);
          const priceStr = Number.isNaN(shown) ? String(res.unit_price) : formatNumber(shown, { maxDecimals: 2 });
          setLines((prev) =>
            prev.map((r) =>
              r.key === key && !r.priceTouched
                ? { ...r, unit_price: priceStr, priceSource: src, priceSourceLink: link }
                : r,
            ),
          );
        })
        .catch(() => { /* لا سجل سابق — نُبقي السعر الافتراضي */ });
    }
  };

  // FEAT-2: عند تغيير العميل بعد وجود بنود، أعِد تسعير الأسطر غير المَلموسة فقط
  // (أسعار محمَّلة/مُحرَّرة يدوياً = priceTouched، فلا تُمَسّ). أول تحميل/عميل
  // افتراضي بلا بنود = لا عملية.
  const prevCustomerRef = React.useRef<number | "" | null>(null);
  useEffect(() => {
    if (prevCustomerRef.current === null) {
      prevCustomerRef.current = customerId;
      return;
    }
    if (prevCustomerRef.current === customerId) return;
    prevCustomerRef.current = customerId;
    if (customerId === "" || !networkOnline) return;
    let cancelled = false;
    // اقرأ اللقطة الحالية للأسطر دون إعادة رندر (إرجاع نفس المرجع).
    setLines((snapshot) => {
      snapshot
        .filter((l) => l.product !== "" && !l.priceTouched)
        .forEach((l) => {
          resolveSalePrice({
            product: Number(l.product),
            customer: customerId,
            currency: currencyId,
            exchange_rate: exchangeRate,
            tax_inclusive: pricesIncludeTax,
          })
            .then((res) => {
              if (cancelled || res?.unit_price == null) return;
              const src = priceSourceFromResolve(res.source?.document_type);
              const link = priceSourceLinkFromResolve(res.source);
              const shown = Number(res.unit_price);
              const priceStr = Number.isNaN(shown) ? String(res.unit_price) : formatNumber(shown, { maxDecimals: 2 });
              setLines((cur) =>
                cur.map((r) =>
                  r.key === l.key && !r.priceTouched
                    ? { ...r, unit_price: priceStr, priceSource: src, priceSourceLink: link }
                    : r,
                ),
              );
            })
            .catch(() => { /* لا سجل سابق للعميل الجديد — نُبقي السعر */ });
        });
      return snapshot;
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId]);

  /**
   * T-SEARCH: المسح يُدخل السطر، والفشل **يقول لماذا**.
   *
   * كان الفشل صمتاً تاماً: المطابقة تامّةٌ على الباركود/الـSKU/المعرّف وحدها،
   * فباركودٌ فيه فراغٌ زائد أو اسمٌ مكتوب باليد لا يفعل شيئاً ولا يعتذر —
   * والمستخدم يظنّ الشاشة معطّلة. الآن: تطابقٌ تامّ ⇒ سطر، وإلا فبحثٌ في
   * الفهرس الكامل بالنصّ نفسه مع رسالة تسمّي ما جرى.
   */
  const handleBarcodeEnter = (raw: string) => {
    const t = raw.trim();
    if (!t) return;
    const norm = t.toLowerCase();
    const byBar = products.find(
      (p) => (p.barcode || "").trim().toLowerCase() === norm
        || (p.sku || "").trim().toLowerCase() === norm
        || String(p.id) === t,
    );
    if (byBar) {
      const emptyIdx = lines.findIndex((l) => l.product === "");
      let key = "";
      if (emptyIdx >= 0) {
        key = lines[emptyIdx].key;
      } else {
        const newLine = makeEmptyLine();
        setLines((prev) => [...prev, newLine]);
        key = newLine.key;
      }
      onSelectProduct(key, byBar.id);
      setProductFilter("");
      return;
    }
    // لا تطابق تامّ: افتح الفهرس مُصفّىً بالنصّ بدل أن يبتلعه الصمت.
    const emptyIdx = lines.findIndex((l) => l.product === "");
    const targetKey = emptyIdx >= 0 ? lines[emptyIdx].key : (() => {
      const newLine = makeEmptyLine();
      setLines((prev) => [...prev, newLine]);
      return newLine.key;
    })();
    setPickerQuery(t);
    setProductPickerLineKey(targetKey);
    setMsg(`لا صنف بالباركود/الرقم «${t}» — ابحث في الفهرس الكامل.`);
  };

  // G1: عرض موحّد بلا أصفار عشرية زائدة (مع فاصل آلاف للمبالغ).
  const fmt = (n: number) => formatMoney(n);

  /* ───────────── تنقّل السجلات (M1-T2) — نفس API: getSalesInvoice ───────────── */
  /** تحميل فاتورة بالمعرّف عبر نفس مسار getSalesInvoice الموجود (بلا API جديد). */
  const loadInvoice = useCallback(
    async (id: number) => {
      if (navLoadingRef.current) return;
      navLoadingRef.current = true;
      setLocalErr(null);
      setMsg(null);
      try {
        const d = await getSalesInvoice(id);
        applyDetail(d);
      } catch (e) {
        setLocalErr(humanizeThrown(e, "فشل تحميل الفاتورة"));
      } finally {
        navLoadingRef.current = false;
      }
    },
    [applyDetail]
  );

  const nav = useRecordNavigation<SalesInvoiceRow>({
    items: invoiceList,
    getId: (r) => r.id,
    currentId: draftId,
    onSelect: (id) => {
      if (id == null) resetForm();
      else void loadInvoice(Number(id));
    },
  });

  /* ───────────── اختصارات الأصيل (M1-T3) ───────────── */
  const noteKey = (k: string) => setLastKey(k);

  useAseelKeymap(
    {
      F2: () => {
        noteKey("F2 طباعة");
        setShowPrintView(true);
      },
      F3: () => {
        noteKey("F3 سند مالي");
        if (isPosted) {
          setMsg("الفاتورة مرحَّلة — السند مغلق.");
          return;
        }
        setActiveTabKey("financial_movements");
      },
      F6: () => {
        noteKey("F6 بحث");
        focusBarcodeField();
      },
      F12: () => {
        noteKey("F12 تخزين");
        if (!readOnly && !saving) void handleSaveDraft();
      },
      Escape: () => {
        noteKey("Esc إلغاء");
        if (customerPickerOpen) {
          setCustomerPickerOpen(false);
          return;
        }
        if (productPickerLineKey) {
          setProductPickerLineKey(null);
          return;
        }
        if (!isPosted) resetForm();
      },
      plus: () => {
        // فهرس الحساب/الصنف حسب الحقل المركَّز عليه
        const active = document.activeElement as HTMLElement | null;
        const field = active?.getAttribute?.("data-aseel-field");
        if (field === "customer") {
          noteKey("+ فهرس الحسابات");
          setCustomerPickerOpen(true);
        } else {
          noteKey("+ فهرس الأصناف");
          const emptyIdx = lines.findIndex((l) => l.product === "");
          const key =
            emptyIdx >= 0 ? lines[emptyIdx].key : lines[lines.length - 1]?.key;
          if (key) setProductPickerLineKey(key);
        }
      },
      star: () => {
        // الحساب التالي داخل حقل العميل
        const active = document.activeElement as HTMLElement | null;
        if (active?.getAttribute?.("data-aseel-field") === "customer") {
          noteKey("* الحساب التالي");
          const idx = customers.findIndex((c) => c.id === Number(customerId));
          const nextC = customers[idx + 1] ?? customers[0];
          if (nextC) {
            setCustomerId(nextC.id);
            markDirty();
          }
        }
      },
      minus: () => {
        const active = document.activeElement as HTMLElement | null;
        if (active?.getAttribute?.("data-aseel-field") === "customer") {
          noteKey("- الحساب السابق");
          const idx = customers.findIndex((c) => c.id === Number(customerId));
          const prevC = customers[idx - 1] ?? customers[customers.length - 1];
          if (prevC) {
            setCustomerId(prevC.id);
            markDirty();
          }
        }
      },
      // N0-T11: Ctrl+nav handlers
      CtrlHome: () => { noteKey("Ctrl+Home الأول"); nav.first(); },
      CtrlEnd: () => { noteKey("Ctrl+End الأخير"); nav.last(); },
      CtrlPageUp: () => { noteKey("Ctrl+PgUp السابق"); nav.prev(); },
      CtrlPageDown: () => { noteKey("Ctrl+PgDn التالي"); nav.next(); },
      CtrlIns: () => { noteKey("Ctrl+Ins جديد"); resetForm(); },
    },
    // T-QUICKPARTY: نافذة إضافة العميل صارت تُفتح من الحقل مباشرةً (بلا فهرس
    // مفتوح تحتها) — فبلا استثنائها كان Esc داخلها يُصفّر الفاتورة كلّها.
    { enabled: !customerPickerOpen && !showAddCustomerModal && productPickerLineKey === null }
  );

  /* ───────────── شريحة الحالة + بيانات الرأس ───────────── */
  const docState = isPosted
    ? `فاتورة مرحّلة #${draftId ?? ""}`
    : draftId
      ? `مسودة #${draftId}`
      : "فاتورة جديدة";

  const selectedCustomer =
    customerId !== "" ? customers.find((c) => c.id === Number(customerId)) : undefined;

  const grandSubtotalBeforeDiscount = lines.reduce(
    (s, l) =>
      s +
      Math.max(
        (Number(l.quantity) || 0) * (Number(l.unit_price) || 0) -
          (Number(l.line_discount) || 0),
        0
      ),
    0
  );
  // W4: إجمالي الكميات (مجموع كميات البنود) بجانب الإجماليات المالية.
  const totalQty = lines.reduce((s, l) => s + (Number(l.quantity) || 0), 0);

  /* ───────────── أعمدة جدول البنود (AseelGrid) ─────────────
     T-RESERVEVIS: «المتاح» وحده كان يعرض الرصيد الكامل فيبدو الصنف المحجوز حراً.
     صار الرصيد صريحاً، ويظهر معه عمودا «محجوز/المتاح للبيع» فقط حين يوجد حجز
     يزاحم هذه الفاتورة — لا أعمدة فارغة على فاتورة بلا حجز. */
  const gridColumns: AseelGridColumn<DraftLine>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "product", header: "بيان الصنف", width: "30%" },
    { key: "avail", header: "الرصيد", width: "70px", align: "center", readOnly: true },
    ...(anyLineReserved ? [
      {
        key: "reserved", header: "محجوز", width: "70px", align: "center" as const, readOnly: true,
        render: (row: DraftLine) => {
          const entry = row.product ? reservationIndex.get(Number(row.product)) : undefined;
          const reserved = totalReserved(entry);
          if (!entry || reserved <= 0) return <span>—</span>;
          const holders = [...entry.holders, ...entry.ownHolders];
          return (
            <span
              style={{ color: "var(--aseel-warn, #b06800)", fontWeight: 600 }}
              title={`محجوز بطلبيات: ${holders.map((h) => `${h.orderNumber} (${h.customerName})`).join("، ")}`}
            >{fmt(reserved)}</span>
          );
        },
      },
      {
        key: "available_for_sale", header: "المتاح للبيع", width: "86px",
        align: "center" as const, readOnly: true,
        render: (row: DraftLine) => {
          const pr = row.product ? productsById.get(Number(row.product)) : undefined;
          if (!pr) return <span>—</span>;
          const entry = reservationIndex.get(Number(row.product));
          const available = availableForSale(pr.quantity_on_hand, entry);
          return (
            <span
              style={available < 0
                ? { color: "var(--aseel-danger, #c00)", fontWeight: 700 }
                : undefined}
              title="الرصيد بعد حجوزات الزبائن الآخرين"
            >{fmt(available)}</span>
          );
        },
      },
    ] : []),
    { key: "quantity", header: "الكمية", width: "84px", align: "center", type: "number" },
    // T-SERIAL: زر الوحدات على الأصناف التسلسلية وحدها، ويختفي كلياً بنمط «معطّل».
    ...(anyLineSerialized ? [{
      key: "serials", header: "الوحدات", width: "92px", align: "center" as const, readOnly: true,
    }] : []),
    { key: "unit_price", header: "سعر الوحدة", width: "100px", align: "center", type: "number" },
    { key: "line_discount", header: "خصم سطر", width: "84px", align: "center", type: "number" },
    { key: "tax", header: "الضريبة", width: "150px" },
    // T-NOTES: ملاحظتا البند — أيقونة واحدة تفتح الاثنتين، فلا يتضخّم عرض الشبكة
    // بعمودَي نصٍّ حرّ نادرَي الاستعمال.
    { key: "notes", header: "ملاحظات", width: "76px", align: "center" as const, readOnly: true },
    { key: "line_total", header: "السعر الإجمالي", width: "110px", align: "center", readOnly: true },
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const gridGetCell = (row: DraftLine, key: string): string | number => {
    const idx = lines.findIndex((l) => l.key === row.key);
    const comp = idx >= 0 ? totals.perLine[idx] : undefined;
    switch (key) {
      case "seq":
        return idx + 1;
      case "quantity":
        return row.quantity;
      case "unit_price":
        return row.unit_price;
      case "line_discount":
        return row.line_discount;
      case "avail": {
        if (invoiceStatus === "posted") return "—";
        const pr = row.product ? productsById.get(Number(row.product)) : undefined;
        return pr ? fmt(Number(pr.quantity_on_hand)) : "—";
      }
      case "line_total":
        return comp ? fmt(comp.lineTotal) : "—";
      default:
        return "";
    }
  };

  const gridOnChange = (rowIndex: number, key: string, value: string) => {
    const row = lines[rowIndex];
    if (!row) return;
    if (key === "quantity") updateLine(row.key, { quantity: value });
    // FEAT-2: تحرير السعر يدوياً يضع علامة «مَلموس» فلا يُعاد تسعيره تلقائياً.
    else if (key === "unit_price") updateLine(row.key, { unit_price: value, priceTouched: true, priceSource: null });
    else if (key === "line_discount") updateLine(row.key, { line_discount: value });
  };

  /* task24: خريطة سعر العميل (آخر بيع/عرض سعر) لكامل الكتالوج — تُجلب دفعة واحدة
     عند تغيّر العميل لعرض السعر داخل خيارات المنتقي بلا نقر. */
  const [customerPriceMap, setCustomerPriceMap] = useState<
    Map<number, { price: string; source: "last_invoice" | "quote" | "default"; prices?: any[] }>
  >(new Map());
  useEffect(() => {
    if (customerId === "" || !networkOnline) { setCustomerPriceMap(new Map()); return; }
    let cancelled = false;
    getCustomerPriceList(customerId)
      .then((rows) => {
        if (cancelled) return;
        const m = new Map<number, { price: string; source: "last_invoice" | "quote" | "default"; prices?: any[] }>();
        for (const r of rows) {
          if (r.price != null && Number(r.price) > 0) {
            m.set(r.product_id, { price: r.price, source: r.source, prices: r.prices });
          }
        }
        setCustomerPriceMap(m);
      })
      .catch(() => { if (!cancelled) setCustomerPriceMap(new Map()); });
    return () => { cancelled = true; };
  }, [customerId, networkOnline]);

  /* task13 M5: منتقي مدمج — الكتابة في الخلية تفلتر الأصناف فورياً وتعبئ
     السطر (المودال الكامل يبقى متاحاً من زر «…» واختصار +). لا خيار «صنف حر»
     هنا لأن سطر فاتورة المبيعات يتطلب صنفاً معرّفاً في المخزون. */
  const productOptions = useMemo(
    () => products.map((p) => {
      // task24: السعر المقترح يظهر داخل الخيار مباشرة (بلا نقر): آخر بيع/عرض سعر
      // لهذا العميل من خريطة العميل، وإلا سعر البيع الافتراضي للصنف.
      const cp = customerPriceMap.get(p.id);
      let price: string | undefined;
      let priceLabel: string | undefined;
      let prices: any[] | undefined;
      if (cp) {
        price = formatMoney(Number(cp.price));
        priceLabel = cp.source === "quote" ? "عرض سعر" : cp.source === "default" ? "سعر عام" : "آخر بيع";
        prices = cp.prices?.map((pr: any) => ({
          label: pr.label,
          value: formatMoney(Number(pr.unit_price)),
          link: pr.document_id ? `/sales/invoices/${pr.document_id}` : undefined,
        }));
      } else if (p.sale_price != null && p.sale_price !== "" && Number(p.sale_price) > 0) {
        // بلا عميل مختار (أو بلا أي سعر خاص به): السعر العام من كرت الصنف.
        price = formatMoney(Number(p.sale_price));
        priceLabel = "سعر عام";
      } else if (p.online_price != null && p.online_price !== "" && Number(p.online_price) > 0) {
        price = formatMoney(Number(p.online_price));
        priceLabel = "افتراضي";
      } else {
        // لا آخر بيع لهذا العميل ولا عرض سعر ولا سعر عام.
        priceLabel = "بدون سعر";
      }
      return {
        id: p.id,
        label: formatProductPrimaryName(p),
        // T-REORDER: «نفذ»/«منخفض» بجانب الاسم — القاعدة من الخادم لا من الشاشة.
        badge: stockBadgeFor(p),
        // T-SERVICELINE: «المتاح: 0» على خدمة معلومة كاذبة — الخدمة بلا مخزون.
        // T-RESERVEVIS: والمحجوز يُذكر في الخيار نفسه — «المتاح» كان يعرض الرصيد.
        sub: p.is_service
          ? "خدمة — بلا مخزون"
          : (() => {
            const entry = reservationIndex.get(p.id);
            const reserved = totalReserved(entry);
            const onHand = Number(p.quantity_on_hand || 0);
            return reserved > 0
              ? `الرصيد: ${fmt(onHand)} · محجوز: ${fmt(reserved)} · المتاح للبيع: ${fmt(availableForSale(onHand, entry))}`
              : `الرصيد: ${fmt(onHand)}`;
          })(),
        price,
        priceLabel,
        prices,
        // T-SEARCH: رقم الصنف وباركوده يُبحَث فيهما ولا يُعرضان — كانا يصلان
        // الشاشة في البيانات ولا يجدهما البحث المدمج أبداً، فيضطرّ البائع لفتح
        // الفهرس الكامل لكل مسحة باركود.
        keywords: [p.sku, p.barcode].filter(Boolean).join(" ").toLowerCase(),
      };
    }),
    [products, customerPriceMap, reservationIndex],
  );

  const renderProductCell = (row: DraftLine, ri: number) => {
    const selectedId = row.product && Number(row.product) > 0 ? Number(row.product) : null;
    // T-REORDER: صنفٌ نفد أو بلغ حدّه لا يُنهي البيع ما دام في نوعه موديلٌ آخر
    // على الرفّ. الشريط يظهر تحت السطر عند الحاجة وحدها، والنقر يستبدل الصنف
    // في السطر نفسه (فيعاد تسعيره من مصدره كأي اختيار).
    const selectedProduct = selectedId != null ? productsById.get(selectedId) : undefined;
    const alternatives = selectedProduct && needsAlternative(selectedProduct)
      ? stockAlternatives(products, selectedProduct)
      : [];
    return (
    <div className="flex flex-col gap-0.5">
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <AseelAutocomplete
        value={(() => {
          const pr = row.product ? productsById.get(Number(row.product)) : undefined;
          return pr ? formatProductPrimaryName(pr) : "";
        })()}
        options={productOptions}
        disabled={readOnly}
        placeholder="اكتب اسم الصنف…"
        onPick={(id) => {
          void onSelectProduct(row.key, Number(id));
          setTimeout(() => {
            document.getElementById(`aseel-grid-input-${ri}-quantity`)?.focus();
          }, 50);
        }}
        onInfo={(id) => { setCardCanAdd(false); setCardProductId(Number(id)); }}
        onEdit={readOnly ? undefined : (id) => setQuickEditProductId(Number(id))}
        onShowMore={(q) => { setPickerQuery(q); setProductPickerLineKey(row.key); }}
      />
      {/* DEF-008: أيقونة (i) بجانب المنتج المختار على السطر → بطاقة الصنف */}
      {selectedId != null && (
        <button
          type="button"
          className="aseel-ellipsis"
          onClick={() => { setCardCanAdd(false); setCardProductId(selectedId); }}
          title="بطاقة الصنف"
        ><Info className="w-3.5 h-3.5" /></button>
      )}
      {/* T-ITEMS M3: قلمٌ بجانب (i) — تعديل الصنف دون مغادرة الفاتورة. */}
      {selectedId != null && !readOnly && (
        <button
          type="button"
          className="aseel-ellipsis"
          onClick={() => setQuickEditProductId(selectedId)}
          title="تعديل سريع للصنف"
        ><Pencil className="w-3.5 h-3.5" /></button>
      )}
      {/* DEF-005: شارة مصدر السعر المقترح */}
      {row.priceSource === "last_invoice" && (
        <span className="aseel-price-badge aseel-price-badge--last" title="السعر من آخر فاتورة لهذا العميل">من آخر فاتورة</span>
      )}
      {row.priceSource === "default" && (
        <span className="aseel-price-badge aseel-price-badge--general"
          title="سعر عام من كرت الصنف — لا عرض لهذا الزبون ولا شراء سابق">سعر عام</span>
      )}
      {(row.priceSource === "quote" || row.priceSource === "sales_quote") && (() => {
        // sales_quote ⇒ عرض «واجهة العروض»؛ quote ⇒ عرض كرت الزبون (رابط احتياطي).
        const link = row.priceSourceLink
          ?? (row.priceSource === "quote" && customerId !== "" ? `/partners/${customerId}?tab=price_list` : null);
        const title = row.priceSource === "sales_quote" ? "فتح عرض السعر في واجهة العروض" : "فتح عرض السعر في كرت الزبون";
        return link ? (
          <button
            type="button"
            className="aseel-price-badge aseel-price-badge--quote"
            style={{ cursor: "pointer", textDecoration: "underline" }}
            title={title}
            onClick={() => {
              clientLogger.info("invoice.open_quote", { source: row.priceSource, link });
              openInNewTab(link);
            }}
          >من عرض السعر</button>
        ) : (
          <span className="aseel-price-badge aseel-price-badge--quote" title="السعر من عرض السعر">من عرض السعر</span>
        );
      })()}
      <button
        type="button"
        className="aseel-ellipsis"
        disabled={readOnly}
        onClick={() => setProductPickerLineKey(row.key)}
        title="فهرس الأصناف الكامل (+)"
      >…</button>
    </div>
    {selectedProduct && needsAlternative(selectedProduct) && !readOnly && (
      <div className="flex flex-wrap items-center gap-1 text-[10px] leading-tight">
        {alternatives.length === 0 ? (
          <span className="text-[var(--aseel-ink-soft)]">لا بديل متوفّر من هذا النوع</span>
        ) : (
          <>
            <span className="text-[var(--aseel-ink-soft)]">بدائل من نفس النوع:</span>
            {alternatives.map((alt) => (
              <button
                key={alt.id}
                type="button"
                className="rounded border border-[var(--aseel-warn-bd)] bg-[var(--aseel-warn-bg)] px-1 py-px text-[var(--aseel-warn-fg)] hover:opacity-80"
                title={`استبدال الصنف بـ«${formatProductPrimaryName(alt)}» — المتاح ${formatQuantity(availableOf(alt))}`}
                onClick={() => { void onSelectProduct(row.key, alt.id); }}
              >
                {formatProductPrimaryName(alt)} · {formatQuantity(availableOf(alt))}
              </button>
            ))}
          </>
        )}
      </div>
    )}
    </div>
    );
  };

  const renderUnitPriceCell = (row: DraftLine) => {
    const p = row.product ? productsById.get(Number(row.product)) : undefined;
    const cost = p ? Number(p.avg_cost || 0) : 0;
    const price = Number(row.unit_price || 0);
    const belowCost = cost > 0 && price > 0 && price < cost;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "2px", alignItems: "center" }}>
        <input
          className={`aseel-input ${belowCost ? "border-red-500 focus:ring-red-500" : ""}`}
          type="text"
          inputMode="decimal"
          value={row.unit_price}
          disabled={readOnly || isPosted}
          style={{ textAlign: "center", ...(belowCost ? { color: "#ef4444", borderColor: "#ef4444" } : {}) }}
          onChange={(e) => {
            updateLine(row.key, { unit_price: e.target.value, priceTouched: true, priceSource: null });
          }}
        />
        {belowCost && (
          <span style={{ color: "#ef4444", fontSize: "0.65rem", whiteSpace: "nowrap", fontWeight: "bold" }}>
            أقل من التكلفة ({fmt(cost)})
          </span>
        )}
      </div>
    );
  };


  const renderTaxCell = (row: DraftLine) => {
    const isEdit = taxEditKey === row.key;
    return (
      <div className="aseel-cell-tax">
        {isEdit ? (
          <input
            className="aseel-input"
            type="number"
            min={0}
            max={100}
            step={0.01}
            disabled={taxSavingKey === row.key || readOnly}
            value={taxPercentDraft[row.key] ?? ""}
            onChange={(e) =>
              setTaxPercentDraft((d) => ({ ...d, [row.key]: e.target.value }))
            }
            onBlur={() => void commitTaxPercent(row.key)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void commitTaxPercent(row.key);
              }
            }}
            placeholder="%"
          />
        ) : (
          <select
            className="aseel-input"
            disabled={readOnly}
            value={row.tax_rate === null || row.tax_rate === "" ? "" : row.tax_rate}
            onChange={(e) =>
              updateLine(row.key, {
                tax_rate: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          >
            <option value="">بدون</option>
            {salesTaxRates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.rate}%)
              </option>
            ))}
          </select>
        )}
        {!readOnly && (
          <button
            type="button"
            className="aseel-iconbtn"
            title="تعديل النسبة يدوياً %"
            onClick={() => {
              if (taxEditKey === row.key) {
                setTaxEditKey(null);
                return;
              }
              setTaxEditKey(row.key);
              const pctStr =
                row.tax_rate != null && row.tax_rate !== ""
                  ? String(salesTaxRates.find((t) => t.id === row.tax_rate)?.rate ?? "16")
                  : "16";
              setTaxPercentDraft((d) => ({ ...d, [row.key]: pctStr }));
            }}
          >
            <Pencil className="h-3 w-3" />
          </button>
        )}
      </div>
    );
  };

  /* T-SERIAL: شارة الوحدات على السطر — «تلقائي» حين لا اختيار، والعدد حين يوجد.
     النقص في النمط الإجباري يظهر أحمرَ هنا، والمنع نفسه يقع على الخادم. */
  const renderSerialCell = (row: DraftLine) => {
    if (!lineTracksSerials(row)) return <span className="aseel-text-soft">—</span>;
    const chosen = row.serials?.length ?? 0;
    const qty = Math.max(0, Math.trunc(Number(row.quantity) || 0));
    const incomplete = serialMode === "required" && chosen !== qty;
    return (
      <button
        type="button"
        className="aseel-toolbtn"
        style={{
          width: "100%", fontWeight: 600,
          ...(incomplete ? { color: "var(--aseel-danger, #c00)" } : {}),
        }}
        onClick={() => setSerialLineKey(row.key)}
        title={chosen > 0
          ? `الوحدات المختارة: ${row.serials!.join("، ")}`
          : "لم تُختر وحدة — الخادم يخصّص الأقدم (FIFO)"}
      >
        {chosen > 0 ? `${chosen}/${qty}` : (incomplete ? `0/${qty}` : "تلقائي")}
      </button>
    );
  };

  /* T-NOTES: شارة الملاحظتين — الحرف يقول أيّهما مكتوبة قبل الفتح: «د» داخلية،
     «ز» للزبون. الملاحظة الداخلية لا تظهر في الـtitle عند الطباعة لأنها لا تُطبع
     أصلاً؛ لكنها تظهر هنا للبائع الذي كتبها. */
  const renderNotesCell = (row: DraftLine) => {
    const internal = (row.internal_note ?? "").trim();
    const forCustomer = (row.customer_note ?? "").trim();
    const marks = [internal ? "د" : "", forCustomer ? "ز" : ""].filter(Boolean);
    return (
      <button
        type="button"
        className="aseel-toolbtn"
        style={{ width: "100%", fontWeight: 600 }}
        onClick={() => setNotesLineKey(row.key)}
        title={
          marks.length
            ? [
                internal ? `داخلية: ${internal}` : "",
                forCustomer ? `للزبون: ${forCustomer}` : "",
              ].filter(Boolean).join("\n")
            : "أضف ملاحظة داخلية أو ملاحظة تُطبع للزبون"
        }
      >
        {marks.length ? marks.join("·") : <StickyNote className="h-3.5 w-3.5 mx-auto" />}
      </button>
    );
  };

  const renderDeleteCell = (row: DraftLine) =>
    readOnly ? null : (
      <button
        type="button"
        className="aseel-iconbtn aseel-iconbtn--danger"
        onClick={() => removeRow(row.key)}
        title="حذف السطر"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    );

  // حقن الأعمدة المخصّصة (تستخدم render) — بالمفتاح لا بالترتيب: أعمدة الحجز
  // تظهر وتختفي بحسب وجود حجز، فالفهرس الثابت كان سيحقن العمود الخطأ.
  const injectRender = (key: string, render: AseelGridColumn<DraftLine>["render"]) => {
    const column = gridColumns.find((c) => c.key === key);
    if (column) column.render = render;
  };
  injectRender("product", renderProductCell);
  injectRender("serials", renderSerialCell);
  injectRender("notes", renderNotesCell);
  injectRender("unit_price", renderUnitPriceCell);
  injectRender("tax", renderTaxCell);
  injectRender("del", renderDeleteCell);

  /* ───────────── T4/T-APPAY: حساب لوحة الدفع ─────────────
     الاشتقاق كلّه في `deriveDocumentPayment` المشتركة مع محرّر الشراء — نسخةٌ
     ثانية من هذه الحسبة تعني «متبقّياً» يختلف بين شاشتين. */
  /** أساس الاحتساب: المرحّلة من إجماليها المحفوظ، والمسودة من إجمالي الشاشة. */
  const collectBase = isPosted ? savedGrandTotal : totals.grandTotal;
  /* T-INTENT: تسوية المستند نفسه من مشتقّةٍ واحدة يقرأها الشريط وعرضُ المستند
     والطباعة — بدل أربع حسبات كانت تفترق بصمت. */
  const settlement = useMemo(() => deriveInvoiceSettlement({
    grandTotal: collectBase,
    paid: paidAmount,
    pendingIntent,
    isPosted,
  }), [collectBase, paidAmount, pendingIntent, isPosted]);
  const remainingDue = settlement.remaining;
  const paymentInput = useMemo(() => ({
    base: collectBase,
    paid: paidAmount,
    isCashDocument: invType === "cash",
    cash: collectCash,
    cheques: collectCheques,
    fromBalance: collectFromBalance,
    onAccountVouchers: onAccountVouchers.map((v) => ({ id: v.id, unallocated: v.unallocated })),
  }), [collectBase, paidAmount, invType, collectCash, collectCheques,
       collectFromBalance, onAccountVouchers]);
  const payment = useMemo(() => deriveDocumentPayment(paymentInput), [paymentInput]);
  const collectRemainingBefore = payment.remainingBefore;
  const collectChequesTotal = payment.chequesTotal;
  const collectCashNum = Number(collectCash) || 0;
  const collectPaidNow = payment.paidNow;
  const onAccountPlan = payment.onAccountPlan;
  const collectChequeError = payment.chequeError;
  const cashInvoiceShortfall = payment.cashShortfall;

  /** اللوحة تظهر لمن يملك التحصيل، على فاتورة بيع لها عميل وما زال عليها متبقٍّ. */
  const showCollectPanel =
    !isReturn
    && canPerm("sales.payment.create")
    && (isPosted || invoicePermissions.canSaveAndPost)
    && customerId !== ""
    && !(isPosted && remainingDue <= 0.009);

  const focusCollectPanel = () => {
    if (customerId === "") {
      setLocalErr("اختر العميل أولاً.");
      return;
    }
    if (isPosted && remainingDue <= 0.009) {
      setMsg("الفاتورة مسدَّدة بالكامل — لا متبقٍّ.");
      return;
    }
    collectPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    collectCashInputRef.current?.focus();
  };

  const patchCheque = (key: string, patch: Partial<CollectChequeRow>) =>
    setCollectCheques((rows) => rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const addChequeRow = () => {
    setChequesOpen(true);
    setCollectCheques((rows) => [
      ...rows,
      { key: newLineKey(), cheque_number: "", bank_name: "", due_date: "", amount: "" },
    ]);
  };

  const resetCollectInputs = () => {
    setCollectCash("");
    setCollectCheques([]);
    setChequesOpen(false);
    setCollectFromBalance("");
  };

  /**
   * T-INTENT: يكتب نيّة الدفع على المسودة — بدلالة الاستبدال، فالنداء يحمل
   * **الصورة الكاملة** للنيّة لا الفرق. مصدرٌ واحد يخدم الحفظ والتعديل والحذف.
   */
  const writeIntent = async (
    intent: {
      cash: number;
      cashAccountId: number | null;
      cheques: InvoiceIntentPayload["cheques"];
    },
    successMsg: string,
  ): Promise<boolean> => {
    let targetId = draftId;
    if (!targetId) {
      const saved = await handleSaveDraft();
      if (!saved) return false;
      targetId = saved.id;
    }
    setCollecting(true);
    try {
      const detail = await attachSalesInvoiceIntent(targetId, {
        cash_amount: intent.cash.toFixed(2),
        ...(intent.cash > 0 && intent.cashAccountId
          ? { cash_account_id: intent.cashAccountId }
          : {}),
        cheques: intent.cheques,
      });
      applyDetail(detail);
      resetCollectInputs();
      setMsg(successMsg);
      onInvoiceSaved();
      return true;
    } catch (e) {
      setLocalErr(humanizeThrown(e, "تعذّر حفظ الدفعة على المسودة"));
      return false;
    } finally {
      setCollecting(false);
    }
  };

  /** الشيكات المرفقة بالمسودة كما يعيدها الخادم — صفوف النيّة في الجدول. */
  const intentCheques = useMemo(
    () => (attachedCheques || []).filter((c) => c.status === "Draft"),
    [attachedCheques],
  );

  /** صورة النيّة الحالية بصيغة الإرسال — أساسُ كل تعديل عليها. */
  const currentIntentCheques = (): InvoiceIntentPayload["cheques"] => intentCheques.map((c) => ({
    cheque_number: c.cheque_number,
    amount: Number(c.amount).toFixed(2),
    due_date: c.due_date || null,
    bank_name: c.bank_name || "",
  }));

  const saveIntentFromPanel = () => {
    if (customerId === "") { setLocalErr("اختر العميل أولاً."); return; }
    if (collectCashNum > 0 && collectCashAccountId === "") {
      setLocalErr("اختر حساب الصندوق أو البنك للمبلغ النقدي.");
      return;
    }
    if (collectChequeError) { setLocalErr(collectChequeError); return; }
    setLocalErr(null);
    setMsg(null);
    // اللوحة تضيف إلى النيّة القائمة لا تستبدلها — وإلا محا إدخالُ شيكٍ ثانٍ الأول.
    void writeIntent(
      {
        cash: intentCash + collectCashNum,
        cashAccountId:
          collectCashAccountId !== "" ? Number(collectCashAccountId) : intentCashAccountId,
        cheques: [
          ...currentIntentCheques(),
          ...collectCheques.map((row) => ({
            cheque_number: row.cheque_number.trim(),
            amount: (Number(row.amount) || 0).toFixed(2),
            due_date: row.due_date || null,
            bank_name: row.bank_name.trim(),
          })),
        ],
      },
      "حُفِظت الدفعة على المسودة — تتحوّل إلى سند قبض عند الترحيل.",
    );
  };

  /** التعديل = سحب النيّة إلى اللوحة ومسحها من المستند، فيعيد المستخدم بناءها. */
  const editIntent = () => {
    setCollectCash(intentCash > 0 ? intentCash.toFixed(2) : "");
    if (intentCashAccountId) setCollectCashAccountId(intentCashAccountId);
    setCollectCheques(intentCheques.map((c) => ({
      key: newLineKey(),
      cheque_number: c.cheque_number,
      bank_name: c.bank_name || "",
      due_date: c.due_date || "",
      amount: String(c.amount),
    })));
    setChequesOpen(intentCheques.length > 0);
    void writeIntent({ cash: 0, cashAccountId: null, cheques: [] }, "عدّل الدفعة ثم احفظها.");
    focusCollectPanel();
  };

  const removeIntentCash = () => {
    void writeIntent(
      { cash: 0, cashAccountId: null, cheques: currentIntentCheques() },
      "حُذِفت الدفعة النقدية من المسودة.",
    );
  };

  const removeIntentCheque = (chequeId: number) => {
    void writeIntent(
      {
        cash: intentCash,
        cashAccountId: intentCashAccountId,
        cheques: intentCheques
          .filter((c) => c.id !== chequeId)
          .map((c) => ({
            cheque_number: c.cheque_number,
            amount: Number(c.amount).toFixed(2),
            due_date: c.due_date || null,
            bank_name: c.bank_name || "",
          })),
      },
      "حُذِف الشيك من المسودة.",
    );
  };

  /**
   * نداء واحد إلى `/collect/`: على المسودة يُحفظ المستند أولاً ثم يُرحَّل
   * ويُحصَّل داخل معاملة الخادم نفسها (`post_invoice`)، وعلى المرحّلة يُحصَّل
   * المتبقّي فوراً. الردّ هو الفاتورة بعد التحصيل — تُطبَّق كما هي بلا جلب ثانٍ.
   */
  const submitCollect = async () => {
    if (customerId === "") {
      setLocalErr("اختر العميل أولاً.");
      return;
    }
    if (collectPaidNow <= 0.009) {
      setLocalErr("أدخل مبلغاً للتحصيل (نقداً أو شيكات أو من رصيد العميل).");
      return;
    }
    if (collectChequeError) {
      setLocalErr(collectChequeError);
      return;
    }
    if (collectCashNum > 0 && collectCashAccountId === "") {
      setLocalErr("اختر حساب الصندوق أو البنك للمبلغ النقدي.");
      return;
    }
    if ((Number(collectFromBalance) || 0) > payment.onAccountAvailable + 0.01) {
      setLocalErr("المطلوب من رصيد العميل يتجاوز رصيده المتاح على الحساب.");
      return;
    }
    if (cashInvoiceShortfall > 0) {
      setLocalErr(
        "الفاتورة نقدية — المدفوع لا يغطي الإجمالي؛ أكمل المبلغ أو ارفع علامة «نقدي» لتصير آجلةً على ذمم العميل.",
      );
      return;
    }
    setLocalErr(null);
    setMsg(null);
    setCollecting(true);
    try {
      let targetId = draftId;
      let alreadyPosted = isPosted;
      if (!isPosted) {
        if (!invoicePermissions.canSaveAndPost) {
          setLocalErr("التحصيل من مسودة يتطلّب صلاحية الحفظ والترحيل.");
          return;
        }
        if (!journalPreview.balanced || journalPreview.errors.length) {
          setLocalErr(
            "القيد غير صالح أو غير متوازن في المعاينة. صحّح الأخطاء المعروضة ثم أعد المحاولة.",
          );
          return;
        }
        const saved = await handleSaveDraft();
        if (!saved) return; // `handleSaveDraft` عرض سبب الفشل
        targetId = saved.id;
        alreadyPosted = saved.posted;
      }
      if (!targetId) {
        setLocalErr("احفظ الفاتورة أولاً ثم حصّلها.");
        return;
      }
      const detail = await collectSalesInvoice(targetId, {
        // مفتاح النقد يُحذف حين لا نقد أصلاً — «غير مذكور» ≠ «صفر» عند الخادم.
        ...(collectCash.trim() !== "" ? { cash: collectCashNum.toFixed(2) } : {}),
        ...(collectCashNum > 0 && collectCashAccountId !== ""
          ? { cash_account_id: Number(collectCashAccountId) }
          : {}),
        cheques: collectCheques.map((row) => ({
          cheque_number: row.cheque_number.trim(),
          amount: (Number(row.amount) || 0).toFixed(2),
          due_date: row.due_date,
          bank_name: row.bank_name.trim(),
        })),
        from_on_account: onAccountPlan.map((row) => ({
          payment_id: row.payment_id,
          amount: row.amount.toFixed(2),
        })),
        post_invoice: !alreadyPosted,
      });
      applyDetail(detail);
      resetCollectInputs();
      setOnAccountKey((k) => k + 1);
      dirtyRef.current = false;
      setMsg(
        detail.payment_id
          ? `تم التحصيل — سند قبض #${detail.payment_id} مرحَّل ومربوط بالفاتورة.`
          : "تم ترحيل الفاتورة.",
      );
      onInvoiceSaved();
    } catch (e) {
      setLocalErr(humanizeThrown(e, "فشل التحصيل"));
    } finally {
      setCollecting(false);
    }
  };

  const handleSaveAndPost = async () => {
    clientLogger.info("invoice.save_and_post_requested", {
      invoiceType: "sales",
      existingInvoice: draftId != null,
    });
    const saved = await handleSaveDraft();
    if (!saved) return;
    if (!saved.posted && !(await handlePost(saved.id))) return;
    clientLogger.info("invoice.save_and_post_completed", {
      invoiceType: "sales",
      invoiceId: saved.id,
    });
  };

  // فاتورة مرحّلة لا تخصم المخزون عند الترحيل ولم تُسلَّم كلها ⇒ مسارا التسليم.
  const canDeliverGoods =
    Boolean(draftId)
    && isPosted
    && !stockOnPost
    && deliveryStatus !== "delivered";

  const toolbarActions: AseelToolbarAction[] = [
    // task16: زر صريح للعودة لقائمة الفواتير (إلى جانب ✕ إغلاق في الإطار)
    ...(onClose
      ? [{ key: "back", label: "الفواتير", icon: <ArrowRight />, onClick: onClose } as AseelToolbarAction]
      : []),
    ...(canPerm("sales.invoice.create")
      ? [{ key: "new", label: "إضافة", icon: <Plus />, onClick: guardedReset } as AseelToolbarAction]
      : []),
    ...(viewMode && !isPosted && invoicePermissions.canSave ? [{
      key: "edit",
      label: "تحرير",
      icon: <Pencil />,
      onClick: () => setViewMode(false),
      separatorBefore: true,
    } as AseelToolbarAction] : []),
    ...(invoicePermissions.canSave ? [{
      key: "save",
      label: saving ? "...تخزين" : "تخزين",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: !readOnly && !saving ? () => void handleSaveDraft() : undefined,
      disabled: readOnly || saving,
    } as AseelToolbarAction] : []),
    ...(invoicePermissions.canSaveAndPost ? [{
      key: "save-and-post",
      label: saving || posting ? "...حفظ وترحيل" : "حفظ وترحيل",
      icon: saving || posting ? <Loader2 className="animate-spin" /> : <CheckCircle2 />,
      onClick:
        networkOnline &&
        !readOnly &&
        journalPreview.balanced &&
        journalPreview.errors.length === 0 &&
        !saving &&
        !posting
          ? () => void handleSaveAndPost()
          : undefined,
      disabled:
        !networkOnline ||
        readOnly ||
        !journalPreview.balanced ||
        journalPreview.errors.length > 0 ||
        saving ||
        posting,
      separatorBefore: true,
    } as AseelToolbarAction] : []),
    ...(invoicePermissions.canPost ? [{
      key: "post",
      // P3-1-b: posting requires a server-side document number + journal
      // post — block visually when offline so the user is not misled.
      label: posting ? "...ترحيل" : !networkOnline ? "ترحيل (يتطلب اتصال)" : "ترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Send />,
      onClick:
        networkOnline &&
        !isPosted &&
        draftId != null &&
        journalPreview.balanced &&
        journalPreview.errors.length === 0 &&
        !posting
          ? () => void handlePost()
          : undefined,
      disabled:
        !networkOnline ||
        isPosted ||
        draftId == null ||
        !journalPreview.balanced ||
        journalPreview.errors.length > 0 ||
      posting,
      separatorBefore: true,
    } as AseelToolbarAction] : []),
    // T-PERM: «تراجع عن الترحيل» يظهر فقط لمن يملك الصلاحية (الخادم يفرضها أيضاً).
    ...(canPerm("sales.invoice.unpost") ? [{
      key: "unpost",
      label: posting ? "...تراجع" : "تراجع عن الترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Undo2 />,
      onClick: isPosted && !posting ? () => void handleUnpost() : undefined,
      disabled: !isPosted || posting,
    } as AseelToolbarAction] : []),
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: !isPosted ? guardedReset : undefined,
      disabled: isPosted,
      danger: true,
    },
    // T-RETURNUI: التحصيل والتسليم مفاهيم فاتورة البيع — لا تُعرض على مرجع.
    ...(!isReturn && canPerm("sales.payment.create") && (isPosted || invoicePermissions.canSaveAndPost) ? [{
      // T4: الزرّ لم يعد يفتح نافذة — التحصيل صار داخل الشاشة، فيُنزِل الزرُّ
      // المستخدمَ إلى لوحته ويضع المؤشّر في خانة النقد.
      key: "receipt",
      label: isPosted && remainingDue <= 0.009 ? "مسدَّدة" : "سند قبض",
      icon: <Receipt />,
      onClick: !(isPosted && remainingDue <= 0.009) ? focusCollectPanel : undefined,
      disabled: isPosted && remainingDue <= 0.009,
      separatorBefore: true,
    } as AseelToolbarAction] : []),
    // التسليم: نافذة سريعة تُنشئ إرسالية بالبنود المؤشَّرة، أو المحرّر الكامل
    // في شاشة الإرساليات بالفاتورة نفسها مربوطةً مسبقاً (مرآة فاتورة الشراء).
    ...(!isReturn && canDeliverGoods ? [{
      key: "deliver",
      label: "تسليم",
      icon: <Truck />,
      onClick: () => setShowDeliver(true),
      separatorBefore: true,
    } as AseelToolbarAction] : []),
    ...(!isReturn && canDeliverGoods ? [{
      key: "new-delivery-note",
      label: "إرسالية جديدة",
      icon: <ClipboardList />,
      onClick: () => openInNewTab(`/sales/delivery-notes/new?invoice=${draftId}`),
    } as AseelToolbarAction] : []),
    // T-SERVICELINE: «بدي أضيف خدمة» — إنشاؤها من داخل الفاتورة ثم وضعها في
    // السطر مباشرةً، بدل الخروج إلى شاشة الأصناف والعودة.
    ...(readOnly ? [] : [{
      key: "add-service",
      label: "إضافة خدمة",
      icon: <Wrench />,
      onClick: () => setShowServiceModal(true),
      separatorBefore: true,
    } as AseelToolbarAction]),
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => setShowPrintView(true) },
  ];

  const banner =
    localErr || msg ? (
      <div className={`aseel-banner ${localErr ? "aseel-banner--err" : "aseel-banner--ok"}`}>
        {localErr ? (
          <AlertCircle className="h-4 w-4 shrink-0" />
        ) : (
          <CheckCircle2 className="h-4 w-4 shrink-0" />
        )}
        <span className="flex flex-col gap-0.5">
          <span>{localErr || msg}</span>
          {localErr &&
            Object.entries(saveFieldErrors).map(([field, text]) => (
              <FieldError key={field} message={text} />
            ))}
        </span>
      </div>
    ) : null;

  // M3: non-blocking warning when one or more lines exceed available stock.
  const stockWarningBanner =
    overSellWarnings.length > 0 ? (
      <div
        className="aseel-banner"
        role="status"
        style={{
          backgroundColor: "#fef9c3",
          color: "#854d0e",
          border: "1px solid #fde047",
        }}
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        <span>
          تنبيه: الكمية تتجاوز المتوفر وسيصبح المخزون بالسالب —{" "}
          {overSellWarnings
            .map((w) => `«${w.name}» (المطلوب ${w.qty} / المتوفر ${w.available})`)
            .join("، ")}
          . البيع مسموح ويمكنك المتابعة.
        </span>
      </div>
    ) : null;

  /* T-RESERVEVIS: تنبيه بيع المحجوز — الخادم يرفض ترحيل هذه الفاتورة (إن كان
     «منع بيع الكمية المحجوزة» مُفعَّلاً)، فيُقال ذلك هنا قبل الضغط على ترحيل
     مع تسمية الطلبية الحاجزة وصاحبها. */
  const reservedWarningBanner =
    reservedWarnings.length > 0 ? (
      <div
        className="aseel-banner"
        role="alert"
        data-testid="reserved-stock-warning"
        style={{ backgroundColor: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        <span>
          تنبيه: تبيع كمية محجوزة لطلبية زبون آخر —{" "}
          {reservedWarnings
            .map((w) => `«${w.name}» (المطلوب ${fmt(w.quantity)} / المتاح للبيع ${fmt(w.available)}`
              + ` / محجوز ${fmt(w.reserved)} بـ${w.holders.join("، ")})`)
            .join("، ")}
          {salesSettings?.block_reserved_stock_sale === false
            ? ". هذا تحذير فقط حسب إعدادات المبيعات الحالية، ويمكنك المتابعة."
            : ". ألغِ الحجز من «تقرير المحجوزات» أو عدّل الكمية — وإلا رُفض الترحيل."}
        </span>
      </div>
    ) : null;

  // M4: recover an autosaved-but-unsaved draft (only offered for a fresh invoice).
  const restoreBanner = recoverableDraft ? (
    <div className="aseel-banner aseel-banner--ok" role="status">
      <AlertCircle className="h-4 w-4 shrink-0" />
      <span>
        توجد مسودة غير محفوظة محليّاً (
        {formatDateTimeValue(recoverableDraft.updated_at)}). هل تريد
        استعادتها؟
      </span>
      <button
        type="button"
        className="mr-3 underline font-semibold hover:no-underline"
        onClick={async () => {
          if (dirtyRef.current) {
            const confirmed = await confirm({
              message: "لديك تعديلات غير محفوظة حالياً. هل أنت متأكد من استعادة المسودة وفقدان هذه التعديلات؟",
              confirmText: "استعادة",
              cancelText: "إلغاء",
              danger: false,
            });
            if (!confirmed) return;
          }
          hydrateFromLocalDraft(recoverableDraft.data);
          setRecoverableDraft(null);
        }}
      >
        استعادة
      </button>
      <button
        type="button"
        className="mr-3 underline font-semibold hover:no-underline"
        onClick={() => {
          void db.invoice_drafts.delete(localDraftKey);
          setRecoverableDraft(null);
        }}
      >
        تجاهل
      </button>
    </div>
  ) : null;

  const fld = (label: string, node: React.ReactNode) => (
    <label className="aseel-field">
      <span className="aseel-field-label">{label}</span>
      {node}
    </label>
  );

  /* ───────────── تبويب: معاينة القيد (M1-T4) ───────────── */
  const journalTab = (
    <div className="aseel-journal">
      {journalPreview.errors.length > 0 && (
        <div className="aseel-journal-errs">
          {journalPreview.errors.map((e, i) => (
            <div key={i} className="aseel-journal-err">
              <AlertCircle className="h-3 w-3 shrink-0" />
              <span>{e}</span>
            </div>
          ))}
        </div>
      )}
      {journalPreview.lines.length === 0 ? (
        <p className="aseel-journal-empty">أدخل الأسطر والحسابات لعرض القيد المحاسبي.</p>
      ) : (
        <table className="aseel-grid" data-variant="journal">
          <thead>
            <tr>
              <th>الحساب</th>
              <th style={{ width: "90px" }}>مدين</th>
              <th style={{ width: "90px" }}>دائن</th>
              <th style={{ width: "120px" }}>البيان</th>
            </tr>
          </thead>
          <tbody>
            {journalPreview.lines.map((l, i) => (
              <tr key={i}>
                <td>{l.accountLabel}</td>
                <td className="aseel-num">{l.debit > 0 ? fmt(l.debit) : "—"}</td>
                <td className="aseel-num">{l.credit > 0 ? fmt(l.credit) : "—"}</td>
                <td>{l.description || "—"}</td>
              </tr>
            ))}
            <tr className="aseel-row--total">
              <td>الإجمالي</td>
              <td className="aseel-num">{fmt(journalPreview.totalDebit)}</td>
              <td className="aseel-num">{fmt(journalPreview.totalCredit)}</td>
              <td>
                {journalPreview.balanced ? (
                  <span className="aseel-ok-text">متوازن ✓</span>
                ) : (
                  <span className="aseel-err-text">غير متوازن</span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );

  /* ───────────── تبويب: بيانات أخرى (تنبيهات الإعداد) ───────────── */
  const otherTab = (
    <div className="aseel-other">
      {revenueAccounts.length === 0 && (
        <div className="aseel-note aseel-note--err">
          لا توجد حسابات إيراد (Revenue) في شجرة الحسابات. شغّل
          <code> python manage.py seed_professional_coa </code>
          لإنشاء شجرة الحسابات الاحترافية (يشمل حساب مبيعات 4101).
        </div>
      )}
      {invType === "cash" && cashboxAccounts.length === 0 && (
        <div className="aseel-note aseel-note--warn">
          لا توجد حسابات صناديق/بنوك (Asset بكود 1101/1102/1103 أو باسم يحتوي صندوق/بنك).
        </div>
      )}
      {salesTaxRates.length === 0 && (
        <div className="aseel-note aseel-note--warn">
          لا توجد نسب ضريبة مبيعات (direction=sales/both). يُنشأ تلقائياً سجل 16% بعد
          الترحيلات أو أضف من الإدارة.
        </div>
      )}
      <label className="aseel-field aseel-field--inline">
        <input
          type="checkbox"
          disabled={readOnly}
          checked={stockOnPost}
          onChange={(e) => {
            setStockOnPost(e.target.checked);
            markDirty();
          }}
        />
        <span className="aseel-field-label" style={{ flex: "unset" }}>
          خصم المخزون عند الترحيل (إن أُلغيَ يُخصم لاحقاً عند تسليم البنود)
        </span>
      </label>
      <p className="aseel-hint">
        تُسجَّل القيود المحاسبية (عملاء/صندوق، مبيعات، ضريبة، تكلفة) عند «ترحيل» فقط، وليس
        عند «تخزين» المسودة.{stockOnPost ? "" : " (الخصم مؤجّل للتسليم.)"}
      </p>
    </div>
  );

  /* ───────────── واجهة العرض المستندية (وضع القراءة) ─────────────
     كان «وضع العرض» هو نموذج التحرير نفسه بحقول معطّلة، فيبدو صفوفاً من
     المربّعات الرمادية لا مستنداً. الآن عرض مستندي مخصّص، والتحرير يُفتح من
     زر «تحرير» في شريط الأدوات. */
  const currencyCode =
    currencyId !== "" ? currencies.find((c) => c.CurrencyID === currencyId)?.Code : undefined;
  const money = (n: number) => `${fmt(n)}${currencyCode ? ` ${currencyCode}` : ""}`;
  const filledLines = lines.filter((l) => l.product !== "");

  /**
   * مسار المستند الأب. لا مسار بمعرّف للطلبية/العرض (شاشة تبويبات واحدة)، فيُمرَّر
   * `?open=` لتفتح الشاشة المستند نفسه لا القائمة — نفس عقد شاشة عروض البيع.
   */
  const sourceDocumentPath = (
    source: NonNullable<SalesInvoiceDetail["source_document"]>,
  ) => (source.kind === "order"
    ? `/sales/orders?open=${source.id}`
    : `/sales/quotations?open=${source.id}`);

  const documentView = (
    <AseelDocumentView<DraftLine>
      title={isReturn ? "مرجع بيع" : "فاتورة مبيعات"}
      subtitle={isReturn ? "SALES RETURN / CREDIT NOTE" : "SALES INVOICE"}
      documentNumber={invoiceNumber || (draftId ? `#${draftId}` : "مسودة")}
      status={
        isPosted
          ? { label: isReturn ? "مرحَّل" : "مرحّلة", tone: "ok" }
          : { label: "مسودة", tone: "warn" }
      }
      metrics={[
        {
          label: isReturn ? "إجمالي المرجوع" : "الإجمالي",
          value: money(totals.grandTotal),
          tone: isReturn ? "warn" : "info",
        },
        // T-RETURNUI: المرجع يعكس الاتجاه — الدفع/المتبقي/التسليم مفاهيم
        // الفاتورة لا المرجع (قيمته تخفّض ذمم العميل وتعيد الكمية للمخزون).
        ...(!isReturn
          ? [
            { label: "المدفوع المرحّل", value: money(paidAmount), tone: "ok" as const },
            ...(settlement.pendingIntent > 0.009
              ? [{
                label: "دفعة غير مرحّلة",
                value: money(settlement.pendingIntent),
                tone: "warn" as const,
              }]
              : []),
            { label: "المتبقي", value: money(settlement.remainingAfterIntent), tone: "warn" as const },
            {
              label: "حالة الدفع",
              value: settlement.intentCoversAll
                ? "مدفوعة — غير مرحّلة"
                : paymentStatusDisplay,
            },
            // التسليم بُعد مستقل — يُعرض فقط حين لا يُخصم المخزون مع الترحيل.
            ...(isPosted && !stockOnPost
              ? [{ label: "حالة التسليم", value: deliveryStatusDisplay }]
              : []),
          ]
          : [{
            label: "أثر الترحيل",
            value: "يعيد الكمية للمخزون ويخفّض ذمم العميل",
          }]),
      ]}
      parties={[
        {
          title: "العميل",
          fields: [
            { label: "الاسم", value: selectedCustomer?.name || "عميل نقدي" },
            ...(selectedCustomer?.phone
              ? [{ label: "الهاتف", value: selectedCustomer.phone }]
              : []),
          ],
        },
      ]}
      meta={[
        { label: isReturn ? "تاريخ المرجع" : "تاريخ الفاتورة", value: invDate || "—" },
        // THA-131: نوع الدفع مرئيٌّ في العرض كما في التحرير — والاستحقاق يتبعه،
        // فلا يقرأ أحدٌ «الاستحقاق —» على فاتورة نقدية ويظنّه بياناً ناقصاً.
        ...(!isReturn ? [{ label: "نوع الدفع", value: invType === "cash" ? "نقدي" : "آجل" }] : []),
        ...(!isReturn && invType !== "cash"
          ? [{ label: "تاريخ الاستحقاق", value: dueDate || "—" }]
          : []),
        { label: "العملة", value: currencyCode || "—" },
        // T-RETURNUI: المرجع يقول أي فاتورة يعود إليها — والرقم يفتحها.
        ...(isReturn && originalInvoiceId != null
          ? [{
            label: "مرجع للفاتورة",
            value: (
              <button
                type="button"
                className="aseel-text-accent inline-flex items-center gap-1 hover:underline"
                title={`فتح الفاتورة الأصلية ${originalInvoiceNumber || `#${originalInvoiceId}`}`}
                onClick={() => openInNewTab(`/sales/invoices/${originalInvoiceId}`)}
              >
                <ExternalLink className="h-3 w-3" />
                <b dir="ltr">{originalInvoiceNumber || `#${originalInvoiceId}`}</b>
              </button>
            ),
          }]
          : []),
        ...(postedJournalId != null
          ? [{ label: "قيد اليومية", value: `#${postedJournalId}` }]
          : []),
        // T-SLINEAGE: الفاتورة تقول من أين جاءت، والرقم يفتح مستنده الأب.
        ...(sourceDocument
          ? [{
            label: sourceDocument.kind === "order" ? "أُنشئت من طلبية" : "أُنشئت من عرض سعر",
            value: (
              <button
                type="button"
                data-testid="open-invoice-source"
                className="aseel-text-accent inline-flex items-center gap-1 hover:underline"
                title={`فتح المستند المصدر ${sourceDocument.number}`}
                onClick={() => openInNewTab(sourceDocumentPath(sourceDocument))}
              >
                <ExternalLink className="h-3 w-3" />
                <b dir="ltr">{sourceDocument.number}</b>
              </button>
            ),
          }]
          : []),
      ]}
      columns={[
        {
          key: "name",
          header: "الصنف",
          render: (row) => {
            const pr = productsById.get(Number(row.product));
            return (
              <span className="font-semibold">
                {pr ? pr.name_ar || pr.name_en || pr.sku : "—"}
              </span>
            );
          },
        },
        {
          key: "qty",
          header: "الكمية",
          width: "80px",
          align: "center",
          numeric: true,
          render: (row) => formatQuantity(row.quantity),
        },
        {
          key: "price",
          header: "سعر الوحدة",
          width: "110px",
          align: "left",
          numeric: true,
          render: (row) => fmt(Number(row.unit_price)),
        },
        {
          key: "discount",
          header: "الخصم",
          width: "90px",
          align: "left",
          numeric: true,
          render: (row) => fmt(Number(row.line_discount)),
        },
        {
          key: "total",
          header: "الإجمالي",
          width: "120px",
          align: "left",
          numeric: true,
          render: (row) => {
            const idx = lines.findIndex((l) => l.key === row.key);
            return (
              <b>{fmt(idx >= 0 ? totals.perLine[idx]?.lineTotal || 0 : 0)}</b>
            );
          },
        },
      ]}
      rows={filledLines}
      rowKey={(row) => row.key}
      totals={[
        { label: "المجموع قبل الضريبة", value: money(totals.subtotalExclTax) },
        ...(Number(invoiceDiscount) > 0
          ? [{ label: isReturn ? "خصم المرجع" : "خصم الفاتورة", value: money(Number(invoiceDiscount)) }]
          : []),
        { label: "الضريبة", value: money(totals.taxAmount) },
        {
          label: isReturn ? "إجمالي المرجوع" : "الإجمالي",
          value: money(totals.grandTotal),
          emphasis: true,
        },
        // T-RETURNUI: المدفوع/المتبقي مفاهيم فاتورة — لا معنى لهما على مرجع.
        ...(!isReturn
          ? [
            { label: "المدفوع المرحّل", value: money(paidAmount) },
            ...(settlement.pendingIntent > 0.009
              ? [{ label: "دفعة غير مرحّلة", value: money(settlement.pendingIntent) }]
              : []),
            { label: "المتبقي", value: money(settlement.remainingAfterIntent), tone: "warn" as const },
          ]
          : []),
        /* THA-132: أُزيل هنا سطرا «رصيد العميل قبل/بعد». كانا يُشتقّان من
           «المتبقّي» مطروحاً من رصيد **اليوم**، فلا يطابقان كشف الحساب: قيد
           الفاتورة يدين الذمم بكامل الإجمالي (التحصيل قيد منفصل)، فالفاتورة
           المدفوعة بالكامل كانت تُظهر أثراً صفرياً وهي ليست كذلك. الجواب
           الصحيح — من كشف الحساب نفسه — في تبويب «حساب العميل». */
      ]}
      sections={[
        /* T-INTENT: جدول السندات انتقل إلى `InvoicePaymentsSection` المشترك
           ويُعرض في وضعَي التحرير والعرض معاً — كان هنا وحده، أي أنّ من يحرّر
           فاتورته لا يرى دفعاتها إطلاقاً. وزرُّ «طباعة السند» كان يفتح قائمة
           السندات لا السند. */
        ...(notes ? [{ key: "notes", title: isReturn ? "سبب المرجوع / ملاحظات" : "ملاحظات", content: notes }] : []),
      ]}
    />
  );

  /* ───────────── T4: لوحة تحصيل الفاتورة (نمط «الأصيل») ─────────────
     صفٌّ واحد: «المدفوع نقداً» · «المدفوع شيكات» · «من رصيد العميل» ·
     «المتبقي» مشتقّاً للقراءة فقط. تُعرض خارج منطقة الإدخال المخفيّة في وضع
     العرض، فالتحصيل على فاتورة مرحّلة يجري من نفس المكان تماماً. */
  /* T-INTENT: جدول دفعات الفاتورة — يظهر في وضعَي التحرير والعرض على كل فاتورة
     (لا على المرحّلة وحدها)، فمن سجّل دفعةً على مسودته يراها فوراً. */
  const paymentsSection = isReturn ? null : (
    <InvoicePaymentsSection
      side="customer"
      posted={paymentDetails || []}
      intentCash={intentCash}
      intentCashAccountLabel={
        intentCashAccountId
          ? accountsById.get(intentCashAccountId)?.name || undefined
          : undefined
      }
      intentCheques={intentCheques}
      settlement={settlement}
      paid={paidAmount}
      editable={!isPosted && canPerm("sales.payment.create")}
      busy={collecting}
      onAddPayment={focusCollectPanel}
      onEditIntent={editIntent}
      onRemoveIntentCash={removeIntentCash}
      onRemoveIntentCheque={removeIntentCheque}
      onOpenVoucher={(paymentId) => {
        const path = entityPathForReference("CUSTOMER_PAYMENT", paymentId);
        if (path) openInNewTab(path);
      }}
    />
  );

  const collectPanel = !showCollectPanel ? null : (
    <DocumentPaymentPanel
      side="customer"
      onSaveIntent={saveIntentFromPanel}
      derived={payment}
      input={paymentInput}
      isPosted={isPosted}
      busy={collecting}
      panelRef={collectPanelRef}
      cashInputRef={collectCashInputRef}
      chequesOpen={chequesOpen}
      onToggleCheques={() => setChequesOpen((v) => !v)}
      onCashChange={setCollectCash}
      onFromBalanceChange={setCollectFromBalance}
      onAddCheque={addChequeRow}
      onPatchCheque={patchCheque}
      onRemoveCheque={(key) =>
        setCollectCheques((rows) => rows.filter((r) => r.key !== key))
      }
      onFillCashShortfall={() =>
        setCollectCash((collectCashNum + cashInvoiceShortfall).toFixed(2))
      }
      onMakeCredit={() => setInvType("credit")}
      onSubmit={() => void submitCollect()}
      cashAccountField={(
        <AccountTreeField
          className="aseel-input"
          accounts={accounts}
          value={collectCashAccountId}
          disabled={collecting}
          allowClear={false}
          isSelectable={(account) => cashboxAccounts.some((row) => row.id === account.id)}
          onChange={(id) => setCollectCashAccountId(id ?? "")}
          placeholder="الصندوق / البنك"
          title="حساب الصندوق أو البنك للتحصيل"
        />
      )}
    />
  );

  return (
    <div
      id="sales-invoice-print"
      dir="rtl"
      style={{ height: "100%", minHeight: 0, display: "flex", flexDirection: "column" }}
    >
      <AseelDocumentShell
        gridFitContent={viewMode}
        title={isReturn ? "مرجع بيع" : "فاتورة مبيعات"}
        state={docState}
        company={
          postedJournalId != null ? `قيد محاسبي #${postedJournalId}` : undefined
        }
        nav={nav}
        actions={toolbarActions}

        header={viewMode ? undefined : (
          <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] p-1.5 flex flex-col gap-1 w-full shadow-sm">
            {/* ملاحظة عاجلة مستحقة على هذا العميل — تظهر لكل مستخدم قبل إتمام الفاتورة. */}
            <PartnerNoteAlert partnerId={customerId === "" ? null : customerId} />
            <div className="flex flex-col xl:flex-row gap-2 items-start">

              {/* Customer Section */}
              <div className="flex-1 flex flex-col gap-1 xl:border-l border-[var(--color-border)] pl-2 w-full">
                <div className="flex items-center gap-1">
                  <span className="font-bold text-[var(--color-text)] min-w-[35px] text-xs">العميل</span>
                  <FieldHint hint="invoice.customer" />
                  {/* T-QUICKPARTY: الحقل صار يُكتب فيه لا يُنقر وحسب — الكتابة
                      تُرشِّح العملاء، وآخر سطرٍ في القائمة «إضافة «ما كتبته»»
                      يفتح نافذة الإنشاء بالاسم معبّأً. زرّ «…» يُبقي فهرس
                      الحسابات الكامل (أعمدة + لوحة مفاتيح الأصيل) في متناول اليد. */}
                  <div className="flex-1 relative min-w-[120px]">
                    <AseelAutocomplete
                      value={selectedCustomer ? `#${selectedCustomer.id} - ${selectedCustomer.name}` : ""}
                      options={customerOptions}
                      onPick={(id) => pickCustomer(Number(id))}
                      onFreeText={(text) => { setQuickAddName(text); setShowAddCustomerModal(true); }}
                      createLabel={(text) => `إضافة «${text}» كعميل جديد`}
                      placeholder="اكتب اسم العميل…"
                      disabled={readOnly}
                    />
                  </div>
                  <button
                    type="button"
                    className="shrink-0 px-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] text-xs font-bold"
                    title="فهرس الحسابات — العملاء"
                    aria-label="فهرس الحسابات — العملاء"
                    disabled={readOnly}
                    onClick={() => !readOnly && setCustomerPickerOpen(true)}
                  >
                    …
                  </button>
                  {selectedCustomer && (
                    <button
                      type="button"
                      className="shrink-0 text-emerald-600 hover:text-emerald-700 text-[10px] underline px-1"
                      title="فتح بطاقة العميل في تبويب جديد"
                      onClick={() => openInNewTab(`/partners/${selectedCustomer.id}`)}
                    >
                      بطاقة
                    </button>
                  )}
                  {/* مربع اختيار واحد بدل قائمة نقدي/أجل: مؤشَّر = بيع نقدي
                      (مدفوع، يُسوّى تلقائياً عند الترحيل بسند قبض مستقل)،
                      فارغ = آجل على ذمم العميل. */}
                  <label
                    className="flex items-center gap-1 text-xs text-[var(--color-text)] cursor-pointer select-none shrink-0"
                    title="مؤشَّر = فاتورة نقدية مدفوعة (تُسوّى تلقائياً عند الترحيل) · فارغ = آجلة على ذمم العميل"
                  >
                    <input
                      type="checkbox"
                      className="w-3.5 h-3.5 accent-emerald-600"
                      disabled={readOnly}
                      checked={invType === "cash"}
                      onChange={(e) => { setInvType(e.target.checked ? "cash" : "credit"); markDirty(); }}
                    />
                    نقدي
                  </label>
                  {/* THA-131: الحالة مشتقّة ومرئية — مربّعٌ صامت لا يقول للمستخدم
                      ماذا صارت الفاتورة. الشارة تُسمّي الحالة الناتجة فور النقر،
                      قبل أي حفظ، وهي وحقلا الرأس (الصندوق/الاستحقاق) وجهٌ واحد. */}
                  <span
                    data-testid="invoice-payment-type-badge"
                    className={`shrink-0 rounded border px-1.5 py-px text-[10px] font-bold ${
                      invType === "cash"
                        ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300"
                        : "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300"
                    }`}
                  >
                    {invType === "cash" ? "نقدي" : "آجل"}
                  </span>
                  {/* خارج الـ`label` قصداً: زرٌّ داخلها كان سيُبدّل خانة الاختيار. */}
                  <FieldHint hint="invoice.paid" />
                </div>

                {selectedCustomer && creditHint && (() => {
                  const bal = Number(creditHint.open_balance);
                  const isDebtor = bal > 0.005;
                  const isCreditor = bal < -0.005;
                  const statusLabel = isDebtor ? "عليه" : isCreditor ? "له" : "متوازن";
                  const color = isDebtor ? "text-red-600 dark:text-red-400" : isCreditor ? "text-emerald-600 dark:text-emerald-400" : "text-[var(--color-text-muted)]";
                  const ledgerAcct = selectedCustomer?.linked_account ?? null;
                  const canDrill = Boolean(onOpenGeneralLedger && ledgerAcct);

                  // الرصيد المتوقّع = الرصيد الحالي + الفاتورة − ما حُصِّل فعلاً
                  // بسندات مرحّلة (لا وعود إدخال غير مُرحَّلة).
                  const balAfterRaw = bal + totals.grandTotal - paidAmount;
                  const isDebtorAfter = balAfterRaw > 0.005;
                  const isCreditorAfter = balAfterRaw < -0.005;
                  const statusLabelAfter = isDebtorAfter ? "عليه" : isCreditorAfter ? "له" : "متوازن";
                  const colorAfter = isDebtorAfter ? "text-red-600 dark:text-red-400" : isCreditorAfter ? "text-emerald-600 dark:text-emerald-400" : "text-[var(--color-text-muted)]";

                  return (
                    <div className="flex items-center flex-wrap gap-x-2 gap-y-0.5 text-[11px]">
                      <div className="flex items-center gap-1">
                        <span className="text-[var(--color-text-muted)]">سابق:</span>
                        {canDrill ? (
                          <button type="button" className={`font-bold hover:underline ${color}`} onClick={() => onOpenGeneralLedger!(ledgerAcct as number)}>
                            {fmt(Math.abs(bal))} <span className="font-normal opacity-80">{statusLabel}</span>
                          </button>
                        ) : (
                          <span className={`font-bold ${color}`}>
                            {fmt(Math.abs(bal))} <span className="font-normal opacity-80">{statusLabel}</span>
                          </span>
                        )}
                      </div>
                      <span className="text-gray-300 dark:text-gray-600 hidden sm:inline">|</span>
                      <div className="flex items-center gap-1">
                        <span className="text-[var(--color-text-muted)]">متوقع:</span>
                        <span className={`font-bold ${colorAfter}`}>
                          {fmt(Math.abs(balAfterRaw))} <span className="font-normal opacity-80">{statusLabelAfter}</span>
                        </span>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* Barcode Search */}
              <div className="w-full xl:w-[250px] shrink-0 flex flex-col gap-0.5 xl:border-l border-[var(--color-border)] pl-2 justify-center">
                 <div className="flex justify-between items-end">
                   <label className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400">بحث سريع / باركود (F6)</label>
                   <FieldHint hint="invoice.barcode" />
                 </div>
                 <div className="relative">
                   <div className="absolute inset-y-0 right-0 flex items-center pr-1.5 pointer-events-none">
                     <Search className="w-3 h-3 text-emerald-500" />
                   </div>
                   <input
                    className="w-full bg-emerald-50/50 dark:bg-emerald-900/10 border border-emerald-300 dark:border-emerald-800/60 rounded px-2 py-0.5 pr-6 text-xs font-bold focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none placeholder:text-gray-400 placeholder:font-normal"
                    data-aseel-field="barcode"
                    disabled={readOnly}
                    value={productFilter}
                    onChange={(e) => setProductFilter(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleBarcodeEnter(productFilter);
                      }
                    }}
                    placeholder="الاسم/SKU/الباركود ⏎"
                  />
                 </div>
              </div>

              {/* Invoice Metadata */}
              <div className="w-full xl:w-[280px] shrink-0 flex flex-col gap-1">
                <div className="flex justify-between items-center text-xs pb-0.5 border-b border-[var(--color-border)]">
                  <span className="font-bold text-[var(--color-text)]">الفاتورة</span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-extrabold">{invoiceNumber || "جديدة"}</span>
                </div>
                <div className="flex gap-1">
                  <div className="flex items-center gap-1 flex-1">
                    <span className="text-[var(--color-text-muted)] text-[10px] min-w-[30px]">تاريخ</span>
                    <FieldHint hint="invoice.date" />
                    <input type="date" className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-emerald-500 text-[11px]" disabled={readOnly} value={invDate} onChange={(e) => { setInvDate(e.target.value); markDirty(); }} />
                  </div>
                  {showDueDateField && (
                    <div className="flex items-center gap-1 flex-1">
                      <span className="text-[var(--color-text-muted)] text-[10px] min-w-[35px]">استحقاق</span>
                      <FieldHint hint="invoice.due-date" />
                      <input type="date" className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-emerald-500 text-[11px]" disabled={readOnly} value={dueDate} onChange={(e) => { setDueDate(e.target.value); markDirty(); }} />
                    </div>
                  )}
                </div>
                {/* THA-131: وجهة النقد كانت تُحسم بصمت من الإعدادات ولا تُعرض —
                    فيقبض المستخدم على صندوقٍ لم يره ولا يملك تبديله من الفاتورة.
                    نفس حقل الشجرة المستعمل في لوحة التحصيل، بنفس قصّ الصناديق. */}
                {showCashAccountField && (
                  <div className="flex items-center gap-1">
                    <span className="text-[var(--color-text-muted)] text-[10px] min-w-[30px]">الصندوق</span>
                    <div className="flex-1 min-w-0">
                      <AccountTreeField
                        className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-emerald-500 text-[11px]"
                        accounts={accounts}
                        value={cashAccountId}
                        disabled={readOnly}
                        allowClear={false}
                        isSelectable={(account) => cashboxAccounts.some((row) => row.id === account.id)}
                        onChange={(id) => { setCashAccountId(id ?? ""); markDirty(); }}
                        placeholder="الصندوق / البنك"
                        title="حساب الصندوق أو البنك الذي يدخله نقد هذه الفاتورة"
                      />
                    </div>
                  </div>
                )}
                {(showCurrencyField || showTaxInclusiveToggle) && (
                  <div className="flex justify-between items-center">
                    {showCurrencyField && (
                      <div className="flex items-center gap-1">
                        <span className="text-[var(--color-text-muted)] text-[10px] min-w-[30px]">عملة</span>
                        <FieldHint hint="invoice.currency" />
                        <select className="bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded px-1 py-0.5 text-[11px] outline-none focus:ring-1 focus:ring-emerald-500" disabled={readOnly} value={currencyId} onChange={(e) => { setCurrencyId(e.target.value ? Number(e.target.value) : ""); markDirty(); }}>
                          <option value="">—</option>
                          {currencies.map((c) => (<option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>))}
                        </select>
                      </div>
                    )}
                    {showTaxInclusiveToggle && (
                      <label className="flex items-center gap-1 text-[11px] font-bold cursor-pointer text-[var(--color-text)]">
                        <input type="checkbox" className="rounded text-emerald-600 focus:ring-emerald-500 w-3 h-3" disabled={readOnly} checked={pricesIncludeTax} onChange={(e) => { setPricesIncludeTax(e.target.checked); markDirty(); }} />
                        شامل الضريبة
                      </label>
                    )}
                  </div>
                )}
              </div>

            </div>
          </div>
        )}
        activeTab={activeTabKey}
        onTabChange={setActiveTabKey}
        tabs={[
          {
            // task18: إعادة تبويب «ملاحظات» (نُقل سابقاً للأسفل) — المفتاح يطابق activeTabKey الافتراضي.
            key: "notes",
            label: "ملاحظات",
            content: (
              <textarea
                className="aseel-input"
                style={{ width: "100%", minHeight: "90px" }}
                placeholder="ملاحظات الفاتورة…"
                disabled={readOnly}
                value={notes}
                onChange={(e) => { setNotes(e.target.value); markDirty(); }}
              />
            ),
          },
          ...(showAdvancedTabs ? [{
            key: "accounts",
            label: "الحسابات / مركز التكلفة",
            content: journalTab,
          }] : []),
          ...(showOtherTab ? [{ key: "other", label: "بيانات أخرى", content: otherTab }] : []),
          ...(showAdvancedTabs && draftId && Number(draftId) > 0 ? [{
            key: "financial_movements",
            label: "الحركات المالية المرتبطة",
            content: (
              <DocumentPaymentsTab
                referenceType="SALES_INVOICE"
                referenceId={draftId}
                searchQuery={invoiceNumber}
              />
            ),
          }] : []),
          ...(showAdvancedTabs && draftId && Number(draftId) > 0 ? [{
            key: "activity_log",
            label: "سجل النشاط",
            content: <EntityActivityLog entityType="sales_invoice" entityId={draftId} defaultOpen refreshKey={isPosted ? "posted" : "draft"} />,
          }] : []),
          /* THA-132 — تبويبات السياق. تُلحق **آخر** القائمة: الغلاف يتتبّع
             التبويب بالفهرس، فإدراج تبويب في الوسط يقفز بالمستخدم. ولا شيء
             منها يُجلَب حتى يُفتح تبويبه (الغلاف يركّب المحتوى النشط وحده). */
          ...(showAdvancedTabs && draftId && Number(draftId) > 0 ? [{
            key: "stock_impact",
            label: "حركة المخزون",
            content: <InvoiceStockTab invoiceId={Number(draftId)} api={salesInvoiceContextApi} side="customer" />,
          }] : []),
          ...(showAdvancedTabs && draftId && Number(draftId) > 0 ? [{
            key: "customer_ledger",
            label: "حساب العميل",
            content: <InvoicePartnerLedgerTab invoiceId={Number(draftId)} api={salesInvoiceContextApi} side="customer" />,
          }] : []),
          /* المرفقات خارج `showAdvancedTabs` وحدها: إرفاق صورة إيصال فعلٌ
             أساسي لا متقدّم، ويحتاجه الوضع السهل قبل غيره. */
          ...(draftId && Number(draftId) > 0 ? [{
            key: "attachments",
            label: "المرفقات",
            content: (
              <InvoiceAttachmentsTab
                invoiceId={Number(draftId)}
                api={salesInvoiceContextApi}
                readOnly={!invoicePermissions.canSave}
              />
            ),
          }] : []),
        ]}
        totals={viewMode ? undefined : (
          <>
            <div className="aseel-total-row">
              <span>مجموع البنود (قبل الخصم)</span>
              <span className="aseel-total-value">{fmt(grandSubtotalBeforeDiscount)}</span>
            </div>
            <div className="aseel-total-row">
              <span>خصم الفاتورة</span>
              <input
                className="aseel-input aseel-total-input"
                type="number"
                step="0.01"
                min="0"
                disabled={isPosted}
                value={invoiceDiscount}
                onChange={(e) => {
                  setInvoiceDiscount(e.target.value);
                  markDirty();
                }}
              />
            </div>
            <div className="aseel-total-row">
              <span>المجموع قبل الضريبة</span>
              <span className="aseel-total-value">{fmt(totals.subtotalExclTax)}</span>
            </div>
            {Number(discountPercent) > 0 && (
              <div className="aseel-total-row">
                <span>خصم مكتسب %</span>
                <span className="aseel-total-value">{discountPercent}%</span>
              </div>
            )}
            <div className="aseel-total-row">
              <span>الضريبة المضافة</span>
              <span className="aseel-total-value">{fmt(totals.taxAmount)}</span>
            </div>
            {profitVisible && journalPreview.revenue > 0 && journalPreview.cogs > 0 && (
              <div className="aseel-total-row">
                <span>الربح الإجمالي</span>
                <span
                  className="aseel-total-value"
                  style={{
                    color:
                      journalPreview.grossProfit >= 0 ? "var(--aseel-status-credit)" : "var(--aseel-status-debit)",
                  }}
                >
                  {fmt(journalPreview.grossProfit)} (
                  {formatNumber(journalPreview.marginPct, { maxDecimals: 1 })}%)
                </span>
              </div>
            )}
            {creditHint &&
              (() => {
                const bal = Number(creditHint.open_balance);
                const isDebtor = bal > 0.005;
                const isCreditor = bal < -0.005;
                const statusLabel = isDebtor ? "مدين" : isCreditor ? "دائن" : "متوازن";
                const color = isDebtor
                  ? "var(--aseel-status-debit)"
                  : isCreditor
                  ? "var(--aseel-status-credit)"
                  : "var(--aseel-ink-soft)";
                const ledgerAcct = selectedCustomer?.linked_account ?? null;
                const canDrill = Boolean(onOpenGeneralLedger && ledgerAcct);
                return (
                  <div className="aseel-total-row">
                    <span>رصيد العميل</span>
                    <span className="aseel-total-value" style={{ color }}>
                      {canDrill ? (
                        <button
                          type="button"
                          className="underline hover:no-underline cursor-pointer"
                          style={{ color, background: "none", border: "none", padding: 0, font: "inherit" }}
                          title="فتح الأستاذ العام لحساب العميل"
                          onClick={() => onOpenGeneralLedger!(ledgerAcct as number)}
                        >
                          {fmt(Math.abs(bal))} ({statusLabel})
                        </button>
                      ) : (
                        <>
                          {fmt(Math.abs(bal))} ({statusLabel})
                        </>
                      )}
                    </span>
                  </div>
                );
              })()}
            {invType === "credit" && creditHint && (
              <div
                className={`aseel-total-row ${
                  creditHint.would_exceed ? "aseel-total-row--warn" : ""
                }`}
              >
                <span>
                  الرصيد بعد الفاتورة
                  {creditHint.would_exceed && (
                    <span className="aseel-err-text ms-1">⚠ يتجاوز حد الائتمان</span>
                  )}
                </span>
                <span className="aseel-total-value">
                  {fmt(Number(creditHint.projected_balance))}
                </span>
              </div>
            )}
            <div className="aseel-total-row aseel-total-row--grand">
              <span>مبلغ الفاتورة الإجمالي <FieldHint hint="invoice.total" /></span>
              <span className="aseel-total-value">{fmt(totals.grandTotal)}</span>
            </div>
            <div className="aseel-total-row">
              <span>إجمالي الكمية</span>
              <span className="aseel-total-value">{formatQuantity(totalQty)}</span>
            </div>

            {/* T-ONEPAY: المحصَّل = سندات قبض مرحّلة فقط (لا خانات إدخال هنا). */}
            <div className="aseel-total-row">
              <span>المحصَّل</span>
              <span className="aseel-total-value">{fmt(paidAmount)}</span>
            </div>

            {/* T-INTENT: الدفعة المسجَّلة على المسودة تُعرَض موسومةً بأنها لم
                تدخل الدفاتر — لا تُخلط بالمحصَّل ولا تُخفى عن صاحبها. */}
            {settlement.pendingIntent > 0.009 && (
              <div className="aseel-total-row">
                <span>دفعة غير مرحّلة</span>
                <span className="aseel-total-value text-amber-600">
                  {fmt(settlement.pendingIntent)}
                </span>
              </div>
            )}

            <div className="aseel-total-row">
              <span>المتبقي على الحساب</span>
              <span className="aseel-total-value">
                {fmt(settlement.remainingAfterIntent)}
              </span>
            </div>
          </>
        )}
        status={
          <>
            <span className="aseel-status-item">
              المستخدم <b>{currentUserName || "—"}</b>
            </span>
            <span className="aseel-status-item">
              رقم القيد <b>{postedJournalId ?? "—"}</b>
            </span>
            {/* THA-132: «رقم الحركة» المخزنية بجانب رقم القيد — سلوك الأصيل
                نفسه (`invoices.txt`: «رقم الحركة المخزنية المسلسل… يمكن
                استخدام هذا الحقل للاستعلام عن الحركات»). يُملأ من تبويب حركة
                المخزون حين يُفتح، فلا يكلّف فتحَ الفاتورة نداءً. */}
            <span className="aseel-status-item">
              رقم الحركة <b>{stockMovementNo ?? "—"}</b>
            </span>
            <span className="aseel-status-item">
              الحالة <b>{isPosted ? "مرحّلة" : draftId ? "مسودة" : "جديدة"}</b>
            </span>
            <span className="aseel-status-item">
              السجل <b>{nav.position}/{nav.total}</b>
            </span>
            <span className="aseel-status-item">
              آخر مفتاح <b>{lastKey}</b>
            </span>
            <span className="aseel-status-item">
              {readOnly ? "للقراءة فقط" : "قابل للتعديل ✓"}
            </span>
          </>
        }
      >
        {banner}
        {reservedWarningBanner}
        {stockWarningBanner}
        {restoreBanner}
        {/* وضع القراءة: مستند مُنسَّق بدل شبكة الإدخال المعطّلة. */}
        {viewMode && documentView}
        {/* الشجرة انتقلت إلى الشريط الجانبي (aside) ليرتفع لأعلى المستند. */}
        <div style={{ flex: 1, minWidth: 0, display: viewMode ? "none" : "flex", flexDirection: "column", gap: "8px" }}>
            <AseelGrid<DraftLine>
              columns={gridColumns}
              rows={lines}
              getCell={gridGetCell}
              getRowKey={(r) => r.key}
              onChange={readOnly ? undefined : gridOnChange}
              onAddRow={readOnly ? undefined : addRow}
              emptyHint="لا توجد بنود — أضف صنفاً (+ فهرس الأصناف)"
            />
            {/* DEF-006: السطر الجديد يُضاف فقط عبر هذا الزر الصريح (لا من نقر خارجي/شجرة). */}
            {!readOnly && (
              // الزرّ يبقى ممتداً كما كان (`flex-1`)، و«؟» بجانبه تشرح الجدول
              // كلّه — فهذا مدخل البنود لا زرٌّ ثانوي.
              <div className="flex items-center gap-1">
                <button type="button" className="aseel-addrow flex-1" onClick={addRow}>
                  <Plus className="h-3 w-3" /> إضافة سطر
                </button>
                <FieldHint hint="invoice.lines" />
              </div>
            )}

            {/* INLINE FOOTER: الملاحظات. خلاصة التحصيل وخاناته انتقلت إلى لوحة
                التحصيل أسفلَه — لتظهر في وضع العرض أيضاً (فاتورة مرحّلة). */}
            <div style={{ display: "flex", gap: "16px", background: "var(--aseel-panel)", padding: "8px", border: "1px solid var(--aseel-border)" }}>
              <div style={{ flex: 1 }}>
                <label className="aseel-field">
                  <span className="aseel-field-label">الملاحظات <FieldHint hint="invoice.notes" /></span>
                  <textarea
                    className="aseel-input"
                    rows={2}
                    disabled={readOnly}
                    value={notes}
                    onChange={(e) => {
                      setNotes(e.target.value);
                      markDirty();
                    }}
                  />
                </label>
              </div>
            </div>
            {/* Warnings */}
            {revenueAccounts.length === 0 && (
              <div className="aseel-note aseel-note--err">لا توجد حسابات إيراد. شغّل seed_professional_coa.</div>
            )}
            {salesTaxRates.length === 0 && (
              <div className="aseel-note aseel-note--warn">لا توجد نسبة ضريبة مبيعات مسجلة في الإعدادات.</div>
            )}
          </div>
        {/* T4: لوحة التحصيل خارج حاوية الإدخال قصداً — الفاتورة المرحّلة تُفتح في
            وضع العرض حيث تلك الحاوية مخفيّة، وتحصيلها من هنا نفسه. */}
        {paymentsSection}
        {collectPanel}
      </AseelDocumentShell>

      {/* فهرس الحسابات (العميل) */}
      <AseelIndexPicker<PartnerRow>
        open={customerPickerOpen}
        title="فهرس الحسابات — العملاء"
        rows={customers}
        columns={[
          { key: "id", header: "الرقم", width: "70px", value: (r) => r.id },
          { key: "name", header: "الاسم", value: (r) => r.name },
          {
            key: "limit",
            header: "حد الائتمان",
            width: "120px",
            value: (r) => r.credit_limit ?? "—",
          },
        ]}
        getRowKey={(r) => r.id}
        searchValue={(r) => `${r.id} ${r.name}`}
        onCreate={(typed) => { setQuickAddName(typed); setShowAddCustomerModal(true); }}
        createLabel={(typed) => `إضافة «${typed}» كعميل جديد`}
        actionButton={
          <button
            type="button"
            onClick={() => { setQuickAddName(""); setShowAddCustomerModal(true); }}
            className="flex items-center gap-1 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
          >
            <Plus className="w-4 h-4" /> إضافة عميل
          </button>
        }
        onSelect={(r) => pickCustomer(r.id)}
        onClose={() => setCustomerPickerOpen(false)}
      />

      {showAddCustomerModal && (
        // task16: إصلاح — كان يفتح SupplierModal (يُنشئ مورداً!)؛ الآن يُنشئ عميلاً
        <CustomerQuickAddModal
          isOpen={showAddCustomerModal}
          initialName={quickAddName}
          onClose={() => setShowAddCustomerModal(false)}
          onSaveSuccess={(newCustomer) => {
            setShowAddCustomerModal(false);
            // T-QUICKPARTY: أدخِله القائمة المحلية قبل إسناده — وإلا بقي الحقل
            // فارغاً حتى تصل قائمة الشاشة الأم (وهي قد لا تصل أصلاً).
            setExtraCustomers((prev) =>
              prev.some((p) => p.id === newCustomer.id)
                ? prev
                : [...prev, {
                    id: newCustomer.id,
                    name: newCustomer.name,
                    partner_type: newCustomer.partner_type || "Customer",
                    credit_limit: newCustomer.credit_limit ?? null,
                    linked_account: newCustomer.linked_account ?? null,
                  }],
            );
            pickCustomer(newCustomer.id);
          }}
        />
      )}

      {/* T-ITEMS M3: تعديل سريع للصنف من السطر — الفاتورة تبقى خلف النافذة
          بحالتها كاملةً. الصفّ المحدَّث يحلّ محلّ نسخته في `extraProducts`،
          والحدث يوقظ الشاشة الأم التي تحمل القائمة الرئيسية. */}
      {quickEditProductId != null && (
        <ItemQuickEditModal
          productId={quickEditProductId}
          onClose={() => setQuickEditProductId(null)}
          onSaved={(updated) => {
            const row = updated as unknown as ProductRow;
            if (!row?.id) return;
            setExtraProducts((prev) => {
              const hit = prev.some((p) => Number(p.id) === Number(row.id));
              return hit ? prev.map((p) => (Number(p.id) === Number(row.id) ? row : p)) : [...prev, row];
            });
          }}
          onOpenFullCard={() => openInNewTab(productProfilePath(quickEditProductId))}
        />
      )}

      {/* T-SERVICELINE: إنشاء خدمة من داخل الفاتورة ثم وضعها في السطر مباشرةً.
          إيرادها يُقيَّد على حساب «إيرادات الخدمات» (يحلّه الخادم عند الترحيل). */}
      {showServiceModal && (
        <ItemQuickCreateModal
          isOpen={showServiceModal}
          initialIsService
          onClose={() => setShowServiceModal(false)}
          onSaved={(created: ProductRow) => {
            setShowServiceModal(false);
            if (!created?.id) return;
            setExtraProducts((prev) => [...prev, created]);
            // الشاشة الأم تحمل قائمة الأصناف — نُعلمها كي تُحدّثها من الخادم.
            try { eventBus.publish("products", resolveTenantId()); } catch { /* غير حرج */ }
            // نفس المدخل الموحّد الذي تستعمله الشجرة وبطاقة الصنف.
            insertProductIntoInvoice(created.id);
          }}
        />
      )}

      {/* فهرس الأصناف */}
      <SalesProductPickerModal
        isOpen={productPickerLineKey !== null}
        products={products}
        // T-SEARCH: يفتح على نفس ما كتبه المستخدم — «+N أخرى» أو فشل الباركود
        // ينقلان الاستعلام بدل أن يبدأ من صفحة بيضاء.
        initialSearch={pickerQuery}
        onSelect={(productId) => {
          if (productPickerLineKey) onSelectProduct(productPickerLineKey, productId);
          setProductPickerLineKey(null);
        }}
        onClose={() => setProductPickerLineKey(null)}
      />

      {/* DEF-007/008: بطاقة الصنف المشتركة */}
      {cardProductId != null && (
        <ProductCardModal
          productId={cardProductId}
          productName={(() => { const p = products.find((x) => x.id === cardProductId); return p ? (p.name_ar || p.name_en || p.sku) : undefined; })()}
          addMode={cardCanAdd && !readOnly && !isPosted}
          suggestedPrice={cardSuggestedPrice}
          priceSource={cardPriceSource}
          onConfirm={cardCanAdd && !readOnly && !isPosted ? (opts) => insertProductIntoInvoice(cardProductId, opts) : undefined}
          onClose={() => setCardProductId(null)} />
      )}

      {/* T-SERIAL: اختيار الوحدات المباعة لهذا البند (أو تركها للخادم FIFO). */}
      {serialLineKey != null && (() => {
        const row = lines.find((l) => l.key === serialLineKey);
        if (!row || row.product === "") return null;
        const pr = productsById.get(Number(row.product));
        return (
          <SerialEntryModal
            mode="pick"
            productId={Number(row.product)}
            productName={pr ? (pr.name_ar || pr.name_en || pr.sku) : `#${row.product}`}
            quantity={Number(row.quantity) || 0}
            value={row.serials ?? []}
            required={serialMode === "required"}
            readOnly={readOnly}
            onClose={() => setSerialLineKey(null)}
            onSave={(picked) => {
              updateLine(row.key, { serials: picked });
              setSerialLineKey(null);
            }}
          />
        );
      })()}

      {/* T-NOTES: ملاحظتا البند — حقلان مفصولان بصرياً كما هما مفصولان في المخطط. */}
      {notesLineKey != null && (() => {
        const row = lines.find((l) => l.key === notesLineKey);
        if (!row) return null;
        const pr = row.product !== "" ? productsById.get(Number(row.product)) : undefined;
        return (
          <LineNotesModal
            productName={pr ? (pr.name_ar || pr.name_en || pr.sku) : "بند بلا صنف"}
            internalNote={row.internal_note ?? ""}
            customerNote={row.customer_note ?? ""}
            readOnly={readOnly}
            onClose={() => setNotesLineKey(null)}
            onSave={(next) => {
              updateLine(row.key, {
                internal_note: next.internalNote,
                customer_note: next.customerNote,
              });
              setNotesLineKey(null);
            }}
          />
        );
      })()}

      {/* Attached payment voucher modal removed - now a bottom tab */}
      {/* P3-2-b: stale-data confirmation portal for offline product picks */}
      {staleModal}
      {/* T4: نافذة «تسديد» انسحبت من جانب المبيعات — التحصيل كلّه في لوحة
          المحرّر (نقد + شيكات + رصيد العميل في نداء واحد). النافذة نفسها ما
          زالت تخدم جانب المشتريات كما هي. */}
      {showPrintView && (
        <SalesInvoicePrintView
          data={{
            invoiceNumber,
            invoiceDate: invDate,
            dueDate,
            invoiceType: invType,
            isReturn,
            originalInvoiceNumber,
            customer: customerId !== "" ? customers.find((c) => c.id === Number(customerId)) : undefined,
            lines,
            productsById,
            totals,
            currentUserName,
            notes,
            currencyCode: currencyId !== "" ? currencies.find((c) => c.CurrencyID === currencyId)?.Code : undefined,
            amountPaid: paidAmount,
            // الطباعة مستندٌ يُسلَّم للعميل: المتبقّي فيه حقيقةُ الدفاتر
            // (المرحّل وحده) لا ما ينتظر الترحيل.
            remainingBalance: settlement.remaining,
            paymentStatusDisplay,
            customerBalanceBeforeInvoice,
            customerBalanceAfterInvoice,
            paymentDetails: paymentDetails || [],
          }}
          onClose={() => setShowPrintView(false)}
        />
      )}
      {/* تسليم سريع: يُنشئ إرسالية بالبنود المؤشَّرة (كلها افتراضياً). */}
      {showDeliver && draftId != null && (
        <DeliverGoodsModal
          invoiceId={draftId}
          invoiceNumber={invoiceNumber}
          onClose={() => setShowDeliver(false)}
          onDelivered={(message) => {
            setShowDeliver(false);
            setMsg(message);
            void loadInvoice(draftId);
          }}
        />
      )}
    </div>
  );
};

// وظائف duplicate غير مستخدمة هنا ولكن تبقى معروفة (duplicateSalesInvoice)
export { duplicateSalesInvoice };
