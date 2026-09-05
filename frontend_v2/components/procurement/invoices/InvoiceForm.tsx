import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Invoice,
  InvoiceItem,
  Supplier,
  User,
  Item,
  DealInvoiceInfo,
  InvoiceInstallment,
  DealActivity,
} from "@/types";
import {
  Save,
  ArrowRight,
  Loader2,
  Pencil,
  Plus,
  Printer,
  Share2,
  RefreshCw,
  Trash2,
  X,
  Send,
  Undo2,
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Info,
  Banknote,
  PackageCheck,
  Truck,
  Copy,
  Wallet,
} from "lucide-react";
import { ProductCardModal } from "../../shared/ProductCardModal";
import { SerialEntryModal } from "../../shared/SerialEntryModal";
import type { SerialEntryMode } from "@/types/inventory";
import { KitDatePicker } from "../../ui/KitDatePicker";
import {
  suppliersService,
} from "@/services/firestoreService";
import { purchaseInvoiceApi, purchaseInvoiceContextApi } from "@/services/purchaseInvoiceApi";
import type { PurchaseInvoiceDto } from "@/types/purchaseInvoice";
import { accountingApi } from "@/services/accountingApi";
import { AccountTreeField } from "@/components/accounting/AccountTreePicker";
import type { AccountPurpose } from "@/utils/accountTree";
import { maxPaymentPrincipalForDeal } from "@/utils/dealPaymentLimits";
import { resolvePaymentForSwiftInstallment } from "@/utils/dealPaymentMatch";
import { SupplierModal } from "@/components/common/SupplierModal";
import { mapPurchaseInvoiceDtoToInvoice } from "@/utils/mapPurchaseInvoiceDto";
import { dealsService } from "@/services/dealsService";
import { shipmentsService } from "@/services/shipmentsService";
import {
  allocateInvoiceFinalCosts,
  invoiceGrandTotalIls,
  invoiceVatBaseIls,
  purchaseInvoiceFeeAmount,
  sumTaxesAndFeesExtras,
  transferCommissionsIlsForVat,
} from "@/utils/invoiceTaxesAndFees";
import { roundSqlMoney2, roundSqlMoney4 } from "@/utils/sqlMoneyRound";
import { formatMoney, formatNumber, formatQuantity } from "@/utils/formatNumber";
import { buildPurchasePriceHintChips } from "@/utils/purchasePriceHint";
import { inventoryApi } from "@/services/inventoryApi";
import { getReservedStock, type ReservedStockRow } from "@/services/salesApi";
import { buildReservationIndex, totalReserved, availableForSale } from "@/utils/reservedStock";
import { stockBadgeFor } from "@/utils/stockBadge";
import { getPickerFieldVisibility } from "@/utils/pickerFieldVisibility";
import { openInNewTab } from "@/utils/openInNewTab";
import { ItemSearchModal, productToItem } from "../price-offers/ItemSearchModal";
import { ItemQuickEditModal } from "../../items/ItemQuickEditModal";
import { ItemQuickCreateModal } from "../../items/ItemQuickCreateModal";

import {
  InvoiceBasicInfo,
  DealInfoSection,
  InstallmentsSection,
  DealActivityLog,
  ConversionDetailsSection,
  NISItemsTable,
  NISFinancialSummary,
  NISInvoiceTaxStrip,
} from "./sections";
import { ItemsTableSection } from "@/components/forms/shared/ItemsTableSection";
import { AttachmentsSection } from "@/components/forms/shared/AttachmentsSection";
import { PurchaseInvoiceAccountingPanel } from "./PurchaseInvoiceAccountingPanel";
import { askReceiveOnPost, receiveOnPostApplies } from "./receiveOnPostPrompt";
import { ReceiveGoodsModal } from "./ReceiveGoodsModal";
import {
  DocumentPaymentPanel,
  deriveDocumentPayment,
  deriveInvoiceSettlement,
  type PaymentChequeRow,
} from "@/components/shared/DocumentPaymentPanel";
import { InvoicePrintView } from "./InvoicePrintView";
import { DocumentPaymentsTab } from "@/components/shared/DocumentPaymentsTab";
import { InvoicePaymentsSection } from "@/components/shared/InvoicePaymentsSection";
import { ShareDocumentModal } from "@/components/shared/ShareDocumentModal";
import { entityPathForReference } from "@/utils/entityLinks";
import { EntityActivityLog } from "@/components/activity/EntityActivityLog";
import { PartnerNoteAlert } from "@/components/partners/PartnerNoteAlert";
import {
  KitDocumentShell,
  KitDocumentView,
  KitViewTable,
  KitGrid,
  KitIndexPicker,
  KitAutocomplete,
  useRecordNavigation,
  useKitKeymap,
  type KitGridColumn,
  type KitToolbarAction,
} from "../../kit";
import {
  formatInvoiceImportLogisticsLine,
  getPurchaseInvoiceCostLabels,
} from "@/utils/invoiceConversionUtils";
import { useToast } from "@/contexts/ToastContext";
import { humanizeThrown } from "@/utils/drfError";
import { FieldError } from "@/components/ui/FieldError";
import { useConfirm } from "@/contexts/ConfirmContext";
import { usePermissions } from "@/contexts/PermissionsContext";
import { useSimpleUi } from "@/hooks/useSimpleUi";
import { clientLogger } from "@/services/logger";
import { accountMatchesPurpose } from "@/utils/accountTree";
import { pickDefaultCashAccount } from "@/utils/cashBox";
import type { CashBoxLedgerLink } from "@/services/accountingApi";
import {
  InvoiceStockTab,
  InvoicePartnerLedgerTab,
  InvoiceAttachmentsTab,
} from "@/components/shared/DocumentContextTabs";
import { invoiceActionPermissions } from "@/utils/viewPermissions";
import { getPurchaseInvoiceFeeEditorState } from "./purchaseInvoiceFeeEditorState";
import { formatDateLocalized, formatTimeValue } from "../../../utils/formatDate";
import { useDocumentDraft } from "@/hooks/useDocumentDraft";
import { orphanDraftsBannerText } from "@/utils/documentDraft";

interface InvoiceFormProps {
  invoice: Partial<Invoice> | null;
  currentUser: User;
  onCancel: () => void;
  /** يُستدعى بعد حفظ ناجح — يمرَّر معرف الفاتورة في SQL لتحديث الرابط */
  onSave?: (ctx: { id: string }) => void;
  allDbItems: Item[];
  dealData?: any;
  readOnly?: boolean;
  /** T-PAYFULL: الفتح من زرّ «مدفوعة» في القائمة (`?pay=full`) — تُعبَّأ لوحة
   *  الدفع بكامل المتبقّي مرّةً واحدة عند اكتمال التحميل. */
  autoFillPayFull?: boolean;
}

type FeeAccountRow = {
  id: number; code?: string; name?: string; parent?: number | null;
  account_type?: string; is_active?: boolean;
};

/** حسابات صالحة لرسوم فاتورة الشراء (مصروف أو أصل نشط).
 *  THA-111: المنتقي صار يقرأ الغرض `FEE_PURPOSE`؛ وتبقى هذه للاختيار التلقائي
 *  للرسم — أول حساب مناسب حين يضيف المستخدم رسماً جديداً. */
const isFeeAccount = (account: FeeAccountRow) =>
  account.is_active !== false
  && ["Expense", "Asset"].includes(String(account.account_type || ""));

/** رسوم الشراء: مصروف أو أصل. ثابتٌ خارج المكوّن كي لا يُعاد بناء الشجرة مع كل رسم. */
const FEE_PURPOSE: readonly AccountPurpose[] = ["expense", "asset"];

export const InvoiceForm: React.FC<InvoiceFormProps> = ({
  invoice: initialInvoice,
  currentUser,
  onCancel,
  onSave,
  allDbItems: initialDbItems,
  dealData,
  readOnly = false,
  autoFillPayFull = false,
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can: canPerm } = usePermissions();
  const [formData, setFormData] = useState<Partial<Invoice>>(
    initialInvoice || {}
  );
  const invoicePermissions = invoiceActionPermissions("purchase", !formData.id, canPerm);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [saving, setSaving] = useState(false);
  // M2: ترحيل/تراجع داخل المحرر — توحيداً مع شاشة المبيعات (شريط أدوات واحد).
  const [posting, setPosting] = useState(false);
  const [accMsg, setAccMsg] = useState<string | null>(null);
  // SAVE-3: سبب فشل الحفظ كان يُعرض في toast يختفي بعد ثوانٍ، فيبقى المستخدم
  // أمام نموذج ممتلئ بلا تفسير. الآن يبقى في لافتة ثابتة حتى الحفظ التالي،
  // ومعه أخطاء الحقول التي يرسلها الخادم (`err.fieldErrors`) وكانت تُهمَل.
  const [saveError, setSaveError] = useState<
    { message: string; fieldErrors: Record<string, string> } | null
  >(null);
  const [accErr, setAccErr] = useState<string | null>(null);
  const [activeTabKey, setActiveTabKey] = useState<string>("basic");
  const [recalcBusy, setRecalcBusy] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  
  const [allDbItems, setAllDbItems] = useState<Item[]>(initialDbItems);
  // المنتجات تصل من الأب بشكل غير متزامن (subscribeToItems). useState يلتقط الـ prop
  // عند التركيب فقط، فإن فُتحت الفاتورة قبل اكتمال التحميل بقيت القائمة فارغة («لا
  // يوجد تطابق») حتى إعادة فتحها. هذا التأثير يعتمد آخر قائمة وصلت مع الحفاظ على أي
  // منتج أُنشئ inline، ويتفادى إعادة الرندر إن لم يتغيّر المحتوى فعلاً.
  useEffect(() => {
    setAllDbItems((prev) => {
      const incoming = initialDbItems || [];
      const incomingIds = new Set(incoming.map((i) => String(i.id)));
      const localOnly = prev.filter((p) => !incomingIds.has(String(p.id)));
      const merged = localOnly.length ? [...incoming, ...localOnly] : incoming;
      if (
        merged.length === prev.length &&
        merged.every((m, i) => String(m.id) === String(prev[i]?.id))
      ) {
        return prev; // لا تغيير فعلي — تجنّب إعادة الرندر
      }
      return merged;
    });
  }, [initialDbItems]);
  const [showSupplierPicker, setShowSupplierPicker] = useState(false);
  // DEF-007/008: بطاقة المنتج المشتركة (نقر مفرد على الشجرة / أيقونة (i)).
  const [cardProductId, setCardProductId] = useState<number | null>(null);
  // T-ITEMS M3: المنتج الجاري تحريره سريعاً من داخل الفاتورة (بلا مغادرتها).
  const [quickEditProductId, setQuickEditProductId] = useState<number | null>(null);
  // «موافق» (إضافة للفاتورة) يظهر فقط عند فتح البطاقة من الشجرة، لا من أيقونة (i).
  const [cardCanAdd, setCardCanAdd] = useState(false);
  // T-R2: السعر المقترح (آخر فاتورة شراء) ومصدره — لعرضهما داخل البطاقة.
  const [cardSuggestedPrice, setCardSuggestedPrice] = useState<number | null>(null);
  const [showAddSupplierModal, setShowAddSupplierModal] = useState(false);
  const [showPrintView, setShowPrintView] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  // نافذة استلام البضاعة (تُنشئ إرسالية بالبنود المؤشَّرة).
  const [showReceive, setShowReceive] = useState(false);
  const [showItemSearch, setShowItemSearch] = useState(false);
  /** T-SEARCH: نصُّ البحث المنقول إلى الفهرس الكامل (من «+N أخرى» أو الباركود). */
  const [pickerQuery, setPickerQuery] = useState("");
  /* ── T-APPAY: لوحة الدفع داخل المحرّر ───────────────────────────────────
     كان الدفع نافذةً تُلزم بالترحيل أولاً ثم تفتح سند الصرف — نداءان منفصلان،
     فانقطاعُ الثاني يترك فاتورةً مرحّلة بلا سند. اللوحة تنادي `pay/` مرّةً
     واحدة، وهي نفس مكوّن لوحة التحصيل في فاتورة البيع (`DocumentPaymentPanel`)
     بمفرداتِ جانب المورّد. */
  const [payCash, setPayCash] = useState("");
  const [payCashAccountId, setPayCashAccountId] = useState<number | null>(null);
  /** T-CASHBOX M1: مدخلات سلّم الصندوق — الصناديق المسجَّلة، وإعداد الشركة،
      وتفضيل المستخدم. بديل «أوّل حساب نقدي في الشجرة». */
  const [cashBoxes, setCashBoxes] = useState<CashBoxLedgerLink[]>([]);
  const [purchaseDefaultCashAccountId, setPurchaseDefaultCashAccountId] =
    useState<number | null>(null);
  const [myDefaultBoxId, setMyDefaultBoxId] = useState<number | null>(null);
  const [payCheques, setPayCheques] = useState<PaymentChequeRow[]>([]);
  const [payChequesOpen, setPayChequesOpen] = useState(false);
  const [payFromBalance, setPayFromBalance] = useState("");
  const [payAdvances, setPayAdvances] = useState<Array<{ id: number; unallocated: number }>>([]);
  const [paying, setPaying] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [nextNumberPreview, setNextNumberPreview] = useState<string>("");
  const payPanelRef = useRef<HTMLDivElement | null>(null);
  /** آخر فاتورة أعادها الخادم من الحفظ — مصدر الأرقام التي يعرفها هو. */
  const lastSavedRef = useRef<PurchaseInvoiceDto | null>(null);
  /** T-PAYFULL4: «مدفوعة» تُنزِل المستخدم إلى صفّ الدفعة الذي أنشأته للتوّ. */
  const paymentsSectionRef = useRef<HTMLDivElement | null>(null);
  const payCashInputRef = useRef<HTMLInputElement | null>(null);
  /** يُزاد بعد كل دفعة ناجحة لإعادة جلب سلف المورّد غير الموزّعة. */
  const [payAdvancesNonce, setPayAdvancesNonce] = useState(0);
  const [activeItemSearchIndex, setActiveItemSearchIndex] = useState<number | null>(null);
  // task18 DEF-B1/B3: إنشاء منتج جديد inline من خلية اسم المنتج (النص المكتوب يُمرَّر مسبقاً)
  const [inlineCreate, setInlineCreate] = useState<{ rowIndex: number; name: string } | null>(null);
  // T-DEFACC: الشجرة تحتاج القائمة كاملة (الآباء منها) — و`feeAccounts` تبقى
  // المجموعة القابلة للاختيار التي يستعملها الاختيار التلقائي للرسوم.
  const [allAccounts, setAllAccounts] = useState<FeeAccountRow[]>([]);
  const feeAccounts = useMemo(() => allAccounts.filter(isFeeAccount), [allAccounts]);

  useEffect(() => {
    accountingApi.getAccounts()
      .then((rows) => setAllAccounts(rows as FeeAccountRow[]))
      .catch((error) => {
        console.error("[PurchaseInvoiceFees] Failed to load fee accounts", error);
        setAllAccounts([]);
      });
  }, []);

  /* T-CASHBOX M1: مدخلات سلّم الصندوق. كلٌّ منها اختياري — فشلُ أيٍّ منها
     يترك الحقل فارغاً ليحلّه الخادم، لا يوقع على «أوّل حساب في الشجرة». */
  useEffect(() => {
    accountingApi.getCashBoxLedgers()
      .then(setCashBoxes)
      .catch(() => setCashBoxes([]));
    purchaseInvoiceApi.getSettings()
      .then((s) => setPurchaseDefaultCashAccountId(s?.default_cash_account ?? null))
      .catch(() => setPurchaseDefaultCashAccountId(null));
    accountingApi.getMyDefaultCashBox()
      .then((r) => setMyDefaultBoxId(r?.cash_box ?? null))
      .catch(() => setMyDefaultBoxId(null));
  }, []);

  /* T-SERIAL: نمط إدخال الرقم التسلسلي في الشراء. `off` (الافتراضي، وحال تعذّر
     قراءة الإعدادات) ⇒ لا عمود ولا نافذة ولا حقل في الحمولة. */
  const [serialMode, setSerialMode] = useState<SerialEntryMode>("off");
  /* T-RECVOPT: الإعداد العام هو **افتراضُ** مربّع «استلام مع الترحيل» لا حاكمه.
     يبقى `true` حال تعذّر قراءة الإعدادات — وهو افتراضي الخادم نفسه. */
  const [receiveOnPostDefault, setReceiveOnPostDefault] = useState(true);
  useEffect(() => {
    let cancelled = false;
    purchaseInvoiceApi.getSettings()
      .then((s) => {
        if (cancelled) return;
        setSerialMode(s.serial_entry_mode || "off");
        setReceiveOnPostDefault(s.receive_on_post !== false);
      })
      .catch(() => { /* بلا إعدادات: يبقى «معطّل» — الشاشة كما كانت */ });
    return () => { cancelled = true; };
  }, []);
  /** بند مفتوح في نافذة الأرقام التسلسلية (بفهرس السطر). */
  const [serialRowIndex, setSerialRowIndex] = useState<number | null>(null);

  // حارس التغييرات غير المحفوظة (Dirty state tracking)
  const [viewMode, setViewMode] = useState<boolean>(!!initialInvoice?.id);
  const effectiveReadOnly = readOnly || viewMode;
  const dirtyRef = useRef(false);
  const markDirty = () => {
    dirtyRef.current = true;
  };
  /** بيانات الفاتورة والمورد — تُعرض من رأس الصفحة عند الضغط على «تفاصيل» */
  const [invoiceHeaderDetailsOpen, setInvoiceHeaderDetailsOpen] = useState(false);
  /** وصف الصفقة من SQL عند غيابه في الفاتورة المحمّلة */
  const [fetchedDealDescription, setFetchedDealDescription] = useState("");

  const [dealInfo, setDealInfo] = useState<DealInvoiceInfo>(() => {
    return (
      initialInvoice?.dealInfo ||
      dealData || {
        createdBy: currentUser.id,
        createdAt: new Date().toISOString(),
      }
    );
  });

  const [installments, setInstallments] = useState<InvoiceInstallment[]>(
    initialInvoice?.installments || []
  );

  const [installmentPlanEnabled, setInstallmentPlanEnabled] = useState(
    initialInvoice?.installmentPlanEnabled || false
  );

  const [dealActivities, setDealActivities] = useState<DealActivity[]>(
    initialInvoice?.dealInfo?.activityLog || []
  );

  // M4-T1: Kit Navigation for invoices
  const [invoicesList, setInvoicesList] = useState<any[]>([]);
  const invoicesListRequestedRef = useRef(false);

  const nav = useRecordNavigation<any>({
    items: invoicesList,
    getId: (inv) => inv.id || '',
    currentId: formData.id || null,
    onSelect: async (id) => {
      if (id === null) {
        setFormData({});
        setDealInfo({ createdBy: currentUser.id, createdAt: new Date().toISOString() });
        setInstallments([]);
        setInstallmentPlanEnabled(false);
      } else {
        try {
          const loaded = await purchaseInvoiceApi.get(Number(id));
          const mapped = mapPurchaseInvoiceDtoToInvoice(loaded);
          setFormData(mapped);
          setDealInfo(mapped.dealInfo || { createdBy: currentUser.id, createdAt: new Date().toISOString() });
          setInstallments(mapped.installments || []);
          setInstallmentPlanEnabled(mapped.installmentPlanEnabled || false);
        } catch (err) {
          // console suppressed
        }
      }
    },
  });

  /* ── ISSUE #118: مسودّة محلية (IndexedDB) — فاتورة الشراء لا تحفظ اليوم
     شيئاً إطلاقاً. الحمولة كائنٌ خفيف يكفي وحده لإعادة بناء الشاشة؛ لا صلة
     بحمولة الحفظ الخادمية (`invoiceToSqlPayload`) التي يبنيها `handleSave`
     بنفسه — المسودّة نصٌّ محلي لا مستندٌ خادميّ نصفي. */
  const draftPayload = useMemo(
    () => ({ formData, dealInfo, installments, installmentPlanEnabled }),
    [formData, dealInfo, installments, installmentPlanEnabled],
  );

  const onRestoreDraft = useCallback(
    (restored: {
      formData: Partial<Invoice>;
      dealInfo: DealInvoiceInfo;
      installments: InvoiceInstallment[];
      installmentPlanEnabled: boolean;
    }) => {
      setFormData(restored.formData);
      setDealInfo(restored.dealInfo);
      setInstallments(restored.installments);
      setInstallmentPlanEnabled(restored.installmentPlanEnabled);
      // استعادةٌ من مسودّة تعني اختلافاً عن آخر نسخة محفوظة — تسجَّل «ملموسة»
      // فوراً كي يبقى الحارس وسياسة الحفظ متّسقين مع ما يراه المستخدم فعلاً.
      dirtyRef.current = true;
      setViewMode(false);
    },
    [],
  );

  const {
    draftSavedAt,
    draftSaveFailed,
    restoredBanner: draftBanner,
    discardDraft,
    orphanDrafts,
  } = useDocumentDraft<{
    formData: Partial<Invoice>;
    dealInfo: DealInvoiceInfo;
    installments: InvoiceInstallment[];
    installmentPlanEnabled: boolean;
  }>({
    docType: "purchase_invoice",
    docId: formData.id ?? null,
    payload: draftPayload,
    isTouched: dirtyRef.current,
    onRestore: onRestoreDraft,
    isPosted: Boolean(formData.isPosted),
    docUpdatedAt: formData.id ? formData.updatedAt ?? null : null,
  });

  /* ISSUE #120: الحارسُ مقلوب — يعترض المغادرةَ فقط إن فشل الحفظُ المحلّيّ
     فعلاً (`draftSaveFailed` من الخطّاف المشترك، #118)، لا دائماً. طالما
     IndexedDB متاحة (الحال الغالب) لا يظهر هذا الحارس عملياً أبداً — نصّ
     `beforeunload` لا يُخصَّص أصلاً، فهو سؤالٌ احتياطيّ لا شبكةُ أمان؛
     شبكةُ الأمان الحقيقية هي الكتابة عند `visibilitychange→hidden` وعند
     تفكيك المكوّن داخل الخطّاف نفسه. */
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (draftSaveFailed) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [draftSaveFailed]);

  // شريط اليتامى (issue #119 §٧) — إخفاءٌ محليّ بلا مسّ المسودّات نفسها؛
  // يعود ظاهراً عند فتح شاشة «فاتورة جديدة» التالية.
  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);

  /** «تراجع» على شريط الاستعادة: يعيد المستند إلى نسخته المحفوظة ويمسح المسودّة. */
  const handleUndoDraft = useCallback(() => {
    if (initialInvoice?.id) {
      setFormData(initialInvoice);
      setInstallments(initialInvoice.installments || []);
      setInstallmentPlanEnabled(initialInvoice.installmentPlanEnabled || false);
      setDealInfo(
        initialInvoice.dealInfo ||
          dealData || { createdBy: currentUser.id, createdAt: new Date().toISOString() },
      );
      setViewMode(true);
    } else {
      setFormData({});
      setDealInfo({ createdBy: currentUser.id, createdAt: new Date().toISOString() });
      setInstallments([]);
      setInstallmentPlanEnabled(false);
    }
    dirtyRef.current = false;
    void discardDraft();
  }, [initialInvoice, dealData, currentUser.id, discardDraft]);

  const guardedCancel = async () => {
    if (!formData.id && !(formData.items || []).some(i => i.itemId) && !formData.supplierId) {
      // Empty draft, no need to warn
      void discardDraft();
      onCancel();
      return;
    }
    if (dirtyRef.current) {
      if (!(await confirm({ message: "لديك تغييرات غير محفوظة. هل أنت متأكد من الخروج دون حفظ؟", confirmText: "خروج دون حفظ", cancelText: "بقاء", danger: false }))) {
        return;
      }
    }
    // تجاهلٌ صريح: المستخدم أكّد الخروج دون حفظ (أو لم يكن هناك ما يُحفظ أصلاً).
    void discardDraft();
    if (initialInvoice?.id && !viewMode) {
      // فاتورة محفوظة كانت قيد التحرير: الإلغاء يتراجع عن التعديلات ويعيد وضع
      // العرض داخل نفس الفاتورة، لا يغادرها لقائمة الفواتير.
      setFormData(initialInvoice);
      setInstallments(initialInvoice.installments || []);
      setInstallmentPlanEnabled(initialInvoice.installmentPlanEnabled || false);
      setDealInfo(initialInvoice.dealInfo || dealData || { createdBy: currentUser.id, createdAt: new Date().toISOString() });
      dirtyRef.current = false;
      setViewMode(true);
      return;
    }
    onCancel();
  };

  const guardedNew = async () => {
    if (!formData.id && !(formData.items || []).some(i => i.itemId) && !formData.supplierId) {
      nav?.goNew?.();
      return;
    }
    if (dirtyRef.current) {
      if (!(await confirm({ message: "لديك تغييرات غير محفوظة. هل أنت متأكد من فتح فاتورة جديدة وتجاهل التغييرات؟", confirmText: "متابعة", cancelText: "إلغاء", danger: false }))) {
        return;
      }
    }
    nav?.goNew?.();
  };

  // M4-T1: Kit keyboard shortcuts — real handlers.
  useKitKeymap({
    F2: () => setShowPrintView(true),
    F6: () => {
      // كان المحدِّد يشير إلى حقل غير موجود في هذه الشاشة — صار على صندوق
      // الباركود نفسه المستعمل في المبيعات.
      const el = document.querySelector<HTMLInputElement>('[data-ktra-field="barcode"]');
      el?.focus();
    },
    F12: () => handleSave(),
    Escape: () => {
      if (showSupplierPicker) { setShowSupplierPicker(false); return; }
      guardedCancel();
    },
    plus: () => {
      const ae = document.activeElement;
      if (ae?.getAttribute?.('data-ktra-key') === '1') {
        setShowSupplierPicker(true);
      }
    },
    // N0-T11: Ctrl+nav handlers
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => guardedNew(),
  }, { enabled: !showSupplierPicker });

  // Load invoices list for navigation
  useEffect(() => {
    if (invoicesListRequestedRef.current) return;
    invoicesListRequestedRef.current = true;
    const loadInvoices = async () => {
      try {
        // P0-5: قائمة التنقّل صارت أحدث 200 (القائمة مُرقَّمة إلزامياً).
        const list = await purchaseInvoiceApi.list({ page: "1", page_size: "200" });
        setInvoicesList(list);
      } catch (err) {
        // console suppressed
      }
    };
    loadInvoices();
  }, []);

  const effectiveShippingForTotals = (data: Partial<Invoice>) => {
    if (data.currency === "ILS") return 0;
    return data.shippingIncluded ? 0 : data.shippingCost || 0;
  };

  // Load Suppliers
  useEffect(() => {
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
    return () => unsubSuppliers();
  }, []);

  // Recalculate Totals
  const recalculateTotals = (updatedFields: Partial<Invoice> = {}) => {
    const nextData = { ...formData, ...updatedFields };
    const items = nextData.items || [];

    const itemsSubtotal = items.reduce(
      (sum, item) => sum + (item.totalPrice || 0),
      0
    );
    const validShipping = effectiveShippingForTotals(nextData);
    const afterDiscount = Math.max(
      0,
      itemsSubtotal - (nextData.discountAmount || 0)
    );
    const merchandiseBase = afterDiscount + validShipping;
    const vatBase = invoiceVatBaseIls(
      merchandiseBase,
      nextData.conversionMetadata as Record<string, unknown> | null,
      nextData.localPayments
    );

    let taxAmount = 0;
    if (nextData.taxType === 'amount') {
      taxAmount = nextData.taxAmount || 0;
    } else {
      taxAmount = vatBase * ((nextData.taxRate || 0) / 100);
    }
    const mainVatRounded = roundSqlMoney2(taxAmount);

    const grandTotal = roundSqlMoney2(
      invoiceGrandTotalIls(
        merchandiseBase,
        mainVatRounded,
        nextData.conversionMetadata as Record<string, unknown> | null,
        nextData.localPayments
      )
    );
    const fees = (nextData.fees || []).map((fee) => ({
      ...fee,
      amount: purchaseInvoiceFeeAmount(fee, merchandiseBase, vatBase, mainVatRounded),
    }));

    setFormData((prev) => ({
      ...prev,
      ...updatedFields,
      subtotal: roundSqlMoney2(itemsSubtotal),
      taxAmount: mainVatRounded,
      grandTotal: roundSqlMoney2(grandTotal),
      fees,
    }));
  };

  // فاتورة جديدة (بدون id من SQL)
  useEffect(() => {
    if (initialInvoice?.id) return;
    setFormData((prev) => ({
      ...prev,
      items: prev.items && prev.items.length > 0 ? prev.items : [
        {
          id: crypto.randomUUID(),
          itemId: "",
          name: "",
          categoryId: "",
          categoryName: "",
          specifications: "",
          imageUrls: [],
          quantity: 1,
          unitPrice: 0,
          totalPrice: 0,
        }
      ],
      status: "incomplete",
      discountAmount: 0,
      taxRate: 0,
      subtotal: 0,
      grandTotal: 0,
      createdAt: new Date().toISOString(),
      isHistorical: dealData ? true : false,
      dealId: dealData?.id,
      dealNumber: dealData?.dealNumber,
      invoiceName: dealData?.dealDescription || dealData?.internalNotes || "",
      invoiceDate: dealData?.dealDate || new Date().toISOString().split("T")[0],
      dealInfo: dealInfo,
      currency: "ILS",
    }));
  }, [initialInvoice, dealData]);

  // فاتورة محفوظة: عند جلب التفاصيل الكاملة من الـ API (بنود، وصف…) نحدّث النموذج
  useEffect(() => {
    if (!initialInvoice?.id) return;
    setFormData((prev) => ({
      ...prev,
      ...initialInvoice,
      items: initialInvoice.items ?? prev.items ?? [],
    }));
    if (initialInvoice.dealInfo) {
      setDealInfo(initialInvoice.dealInfo);
      setInstallments(initialInvoice.installments || []);
      setInstallmentPlanEnabled(initialInvoice.installmentPlanEnabled || false);
      setDealActivities(initialInvoice.dealInfo.activityLog || []);
    }
    dirtyRef.current = false;
  }, [initialInvoice]);

  // Sync state to formData
  useEffect(() => {
    setFormData((prev) => ({
      ...prev,
      // 🟢 تعديل هام: دمج dealInfo الحالي بدلاً من استبداله بالكامل لمنع مسح التعديلات القادمة من BasicInfo
      dealInfo: {
        ...prev.dealInfo,
        ...dealInfo
      },
      installments: installments,
      installmentPlanEnabled: installmentPlanEnabled,
    }));
  }, [dealInfo, installments, installmentPlanEnabled]);

  const handleSave = async () => {
    if (!invoicePermissions.canSave) {
      toast("لا تملك صلاحية حفظ هذه الفاتورة.", "error");
      return;
    }
    if (!formData.supplierId) {
      toast("الرجاء اختيار المورد", "error");
      return;
    }
    if (!formData.items || formData.items.length === 0) {
      toast("الرجاء إضافة منتج واحد على الأقل", "error");
      return;
    }
    const invalidFee = (formData.fees || []).find(
      (fee) => !fee.description.trim() || Number(fee.amount) <= 0 || !fee.expenseAccountId,
    );
    if (invalidFee) {
      toast("أكمل بيان ومبلغ وحساب كل بند في الضرائب والرسوم الإضافية", "error");
      setActiveTabKey("fees");
      return;
    }
    /* T-PAYFULL2: نقول الشرط قبل الرحلة — الخادم يرفض الفاتورة النقدية بلا
       صندوق، والرفض كان يصل بعد الحفظ بلا حقلٍ مرئي يُصلحه. مرآة حارس البيع. */
    if (formData.paymentType === "cash" && !formData.cashOrBankAccountId) {
      toast("الفاتورة نقدية — اختر صندوق التسوية بجوار علامة «نقدي».", "error");
      return;
    }

    setSaving(true);
    try {
      const isNew = !formData.id;
      const now = new Date().toISOString();
      const invoiceId = formData.id || crypto.randomUUID();

      // 🟢 نأخذ الملاحظات من المكان الصحيح دون دمج قسري
      const activeAlibabaLink = formData.alibabaOrderLink || formData.dealInfo?.alibabaOrderLink || "";
      // هنا نعتمد على ما هو موجود في formData.dealInfo.internalNotes كأولوية للملاحظات الداخلية
      const internalNotes = formData.dealInfo?.internalNotes || formData.notes || "";

      const payload: any = {
        ...formData,
        id: invoiceId,
        updatedAt: now,
        dealInfo: {
          ...dealInfo,
          ...(formData.dealInfo),

          alibabaOrderLink: activeAlibabaLink,
          internalNotes: internalNotes, // حفظ الملاحظات الداخلية بشكل منفصل

          shippingCost: formData.shippingCost,
          shippingIncluded: formData.shippingIncluded,
          totalWeight: formData.totalWeight,
          totalVolume: formData.totalVolume,

          updatedAt: now,
          updatedBy: currentUser.id,
        },
        // الملاحظات العامة (root notes) يمكن أن تكون هي نفسها الداخلية
        notes: internalNotes,
        alibabaOrderLink: activeAlibabaLink,
        installments: installmentPlanEnabled ? installments : [],
        installmentPlanEnabled: installmentPlanEnabled,
      };

      const partnerId = Number(String(payload.supplierId || '').trim());
      const sqlBody: Record<string, unknown> = {
        invoice_name: payload.invoiceName || null,
        invoice_date: payload.invoiceDate || null,
        // T-DUE: الاستحقاق والمهلة — الخادم يحسم أيّهما يفوز (`resolve_due_date`).
        due_date: payload.dueDate || null,
        payment_terms_days: payload.paymentTermsDays ?? null,
        partner: Number.isFinite(partnerId) && partnerId > 0 ? partnerId : undefined,
        deal: payload.dealId ? Number(payload.dealId) : null,
        subtotal: roundSqlMoney2(payload.subtotal ?? 0),
        discount_amount: roundSqlMoney2(payload.discountAmount ?? 0),
        tax_rate: roundSqlMoney4(payload.taxRate ?? 0),
        tax_amount: roundSqlMoney2(payload.taxAmount ?? 0),
        tax_type: payload.taxType || 'percentage',
        shipping_cost: roundSqlMoney2(payload.shippingCost ?? 0),
        shipping_included: payload.shippingIncluded || false,
        grand_total: roundSqlMoney2(payload.grandTotal ?? 0),
        invoice_type: payload.invoiceType || (payload.clearanceId || payload.shipment ? 'international' : 'local'),
        // نوع الدفع يُحفظ من الرأس — كان يُكتب من تبويب المحاسبة وحده، فلا
        // يعرف المحرّر أنقديّةٌ فاتورته أم آجلة.
        payment_type: payload.paymentType || 'credit',
        cash_or_bank_account: payload.paymentType === 'cash'
          ? (payload.cashOrBankAccountId ?? null) : null,
        fees: (payload.fees || []).map((fee: any) => ({
          description: String(fee.description || '').trim(),
          amount: roundSqlMoney2(fee.amount ?? 0),
          calculation_type: fee.calculationType || 'amount',
          calculation_value: roundSqlMoney4(fee.calculationValue ?? fee.amount ?? 0),
          percentage_basis: fee.percentageBasis || 'goods',
          expense_account: Number(fee.expenseAccountId),
          capitalize_to_inventory: Boolean(fee.capitalizeToInventory),
          is_taxable: Boolean(fee.isTaxable),
        })),
        conversion_metadata_json: payload.conversionMetadata || null,
        currency: payload.currency || 'ILS',
        status: payload.status || 'draft',
        notes: payload.notes || null,
        supplier_invoice_number: payload.supplierInvoiceNumber || null,
        factory_name: payload.factoryName || null,
        // W7c: مرفقات الفاتورة/المرجع — يُخزّنها الخادم في SystemAttachment.
        quote_images: payload.quoteImages || payload.quote_images || [],
        quote_pdfs: payload.quotePdfs || payload.quote_pdfs || [],
        items: (payload.items || [])
          .filter((item: any) => item.itemId && item.itemId !== "")
          .map((item: any) => ({
            // معرّف الخادم يجعل الحفظ تعديلاً في مكانه: الكمية المستلَمة
            // وأسطر الإرسالية معلّقة على البند، وحذفه وإعادة إنشاؤه يُسقطها.
            ...(Number(item.serverId) > 0 ? { id: Number(item.serverId) } : {}),
            product: Number(item.itemId) || null,
            name: item.name,
            quantity: roundSqlMoney4(item.quantity ?? 0),
            unit_price: roundSqlMoney4(item.unitPrice ?? 0),
            total_price: roundSqlMoney2(item.totalPrice ?? 0),
            notes: item.notes || null,
            hs_code: item.hsCodePrimary || null,
            landed_unit_price_ils:
              item.landedUnitPriceIls != null && item.landedUnitPriceIls !== ""
                ? roundSqlMoney4(item.landedUnitPriceIls)
                : null,
            landed_line_total_ils:
              item.landedLineTotalIls != null && item.landedLineTotalIls !== ""
                ? roundSqlMoney2(item.landedLineTotalIls)
                : null,
            // T-SERIAL: تُرسَل دائماً — الفارغة تمسح إدخالاً سابقاً بدل أن يبقى
            // معلّقاً على البند بلا ظهور في الشاشة.
            serials: Array.isArray(item.serials) ? item.serials : [],
          })),
      };

      let savedSqlId: string;
      let savedInvoice;
      if (isNew) {
        if (dealData?.id) {
          sqlBody.deal = Number(dealData.id) || null;
        }
        savedInvoice = await purchaseInvoiceApi.create(sqlBody as any);
        savedSqlId = String(savedInvoice.id);
      } else {
        if (formData.isHistorical) {
          toast("لا يمكن تعديل الفواتير المؤرشفة", "error");
          setSaving(false);
          return;
        }
        savedInvoice = await purchaseInvoiceApi.update(Number(formData.id), sqlBody as any);
        savedSqlId = String(formData.id);
      }

      const expectedFeesCount = Array.isArray(sqlBody.fees) ? sqlBody.fees.length : 0;
      const savedFees = Array.isArray(savedInvoice.fees) ? savedInvoice.fees : [];
      if (savedFees.length !== expectedFeesCount) {
        throw new Error("لم يؤكد الخادم حفظ جميع بنود الضرائب والرسوم. لم يتم إغلاق وضع التحرير.");
      }
      const savedMapped = mapPurchaseInvoiceDtoToInvoice(savedInvoice);
      setFormData((prev) => ({ ...prev, ...savedMapped }));
      /* T-PAYFULL4: المستند كما خزّنه الخادم — من يبني على أرقامه (نيّة الدفع)
         يقرؤها من هنا لا من `formData` (إغلاقٌ بائت لا يرى ما وصل للتوّ). */
      lastSavedRef.current = savedInvoice;
      console.info("[PurchaseInvoiceFees] Saved and verified", {
        invoiceId: savedSqlId,
        feesCount: expectedFeesCount,
      });

      const dealIdForWorkflow = formData.dealId || dealData?.id || payload.dealId;
      if (dealIdForWorkflow) {
        try {
          await dealsService.patchShippingWorkflow(String(dealIdForWorkflow), "sw_released");
        } catch {
          /* لا نمنع نجاح حفظ الفاتورة */
        }
        try {
          await shipmentsService.patchLinkedShipmentsRouteForDeal(
            String(dealIdForWorkflow),
            "released"
          );
        } catch {
          /* نفس الأمر — الشحنة قد لا تكون في SQL */
        }
      }
      setAccMsg(null);
      setSaveError(null);
      setViewMode(true);
      if (onSave) onSave({ id: savedSqlId });
      toast("تم حفظ الفاتورة بنجاح", "success");
      dirtyRef.current = false;
      // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      void discardDraft();
      return savedSqlId;
    } catch (error) {
      // console suppressed
      const msg = humanizeThrown(error, "حدث خطأ أثناء الحفظ");
      // النموذج لا يُغلق ولا تُمسح مدخلاته ولا مرفقاته — السبب يبقى أمام المستخدم.
      setSaveError({
        message: msg,
        fieldErrors:
          (error as { fieldErrors?: Record<string, string> })?.fieldErrors ?? {},
      });
      toast(msg, "error");
    } finally {
      setSaving(false);
    }
  };

  /** M2: إعادة تحميل الفاتورة من الخادم بعد ترحيل/تراجع لتحديث الحالة والقيد. */
  const reloadInvoice = async (idOverride?: string | number) => {
    const targetId = idOverride ?? formData.id;
    if (!targetId) return;
    try {
      const loaded = await purchaseInvoiceApi.get(Number(targetId));
      const mapped = mapPurchaseInvoiceDtoToInvoice(loaded);
      setFormData(mapped);
      setDealInfo(mapped.dealInfo || { createdBy: currentUser.id, createdAt: new Date().toISOString() });
    } catch {
      /* تجاهل — الحالة المعروضة ستُحدَّث عند التنقل */
    }
  };

  // M2: ترحيل الفاتورة من شريط الأدوات (موحَّد مع شاشة المبيعات).
  /**
   * T-RECVOPT: يُسأل حيث للجواب معنى فقط — فاتورة محلية لم تُستلَم كلّها.
   *
   * T-PAYFULL2: مصدرٌ واحد لمسارَي الترحيل. `pay/` يرحّل الفاتورة داخله
   * (`post_invoice`) ولم يكن يسأل، فيختلف أثرُ الترحيل على المخزن باختلاف
   * الزرّ الذي أطلقه — وهذا آخر ما يُحتمل في المخزون.
   *
   * يُعيد `null` إن ألغى المستخدم، و`undefined` إن لم يكن للسؤال معنى.
   */
  const askReceiveChoice = async (): Promise<boolean | undefined | null> => {
    if (!receiveOnPostApplies({
      isLocal: !isInternationalInvoice && !formData.shipment && !formData.dealId
        && !formData.clearanceId,
      isReturn: Boolean(formData.isReturn),
      receiptStatus: formData.receiptStatus,
    })) return undefined;
    return askReceiveOnPost(confirm, receiveOnPostDefault);
  };

  const handlePost = async (idOverride?: string | number) => {
    if (!invoicePermissions.canPost) {
      setAccErr("لا تملك صلاحية ترحيل فاتورة الشراء.");
      return false;
    }
    const targetId = idOverride ?? formData.id;
    if (!targetId || posting) return false;
    const answer = await askReceiveChoice();
    if (answer === null) return false;
    const receiveChoice = answer;
    setAccErr(null);
    setAccMsg(null);
    setPosting(true);
    try {
      const res = await purchaseInvoiceApi.postToAccounting(
        Number(targetId), receiveChoice,
      );
      setAccMsg(res.message || `تم الترحيل — قيد محاسبي #${res.journal_id}`);
      setViewMode(true);
      await reloadInvoice(targetId);
      if (onSave) onSave({ id: String(targetId) });
      return true;
    } catch (e) {
      setAccErr(humanizeThrown(e, "تعذّر ترحيل الفاتورة"));
      return false;
    } finally {
      setPosting(false);
    }
  };

  // M2: التراجع عن الترحيل — حذف القيود وإرجاع الفاتورة مسودة (Feature 1).
  const handleUnpost = async () => {
    if (!formData.id || posting) return;
    if (!(await confirm({
      message:
        "هذا المستند مرحَّل. سيؤدي التراجع عن الترحيل إلى حذف كل قيود اليومية " +
        "وحركات المخزون الخاصة بهذه الفاتورة وإرجاعها مسودة قابلة للتعديل/الحذف. متابعة؟",
      confirmText: "متابعة",
    }))) return;
    setAccErr(null);
    setAccMsg(null);
    setPosting(true);
    try {
      await purchaseInvoiceApi.unpost(Number(formData.id));
      setAccMsg("تم التراجع عن الترحيل وحذف القيود. الفاتورة الآن مسودة.");
      setViewMode(true);
      await reloadInvoice();
      if (onSave) onSave({ id: String(formData.id) });
    } catch (e) {
      setAccErr(humanizeThrown(e, "تعذّر التراجع عن الترحيل"));
    } finally {
      setPosting(false);
    }
  };

  const handleAddItem = () => {
    setShowItemSearch(true);
  };

  /* task13 M5: منطق تعبئة السطر مشترك بين المنتقي المدمج والفهرس الكامل */
  // FEAT-1: السعر المقترح لبند الشراء عبر PriceResolver المشترك في الخادم
  // (آخر/أقل سعر شراء حسب إعدادات الشراء، ثم تكلفة المنتج، ثم فارغ). يحل محل
  // مسار supplier_prices القديم (مصدر حقيقة موازٍ) — الآن من الفواتير المرحَّلة.
  const resolveSuggestedPrice = async (productId: string | number): Promise<number> => {
    const pid = Number(productId);
    if (!pid) return 0;
    try {
      // التعبئة دائماً بآخر سعر شراء **من مورد الفاتورة** (بغضّ النظر عن استراتيجية
      // الإعدادات) — القائمة تعرض «أقل شراء» العام و«آخر شراء من المورد» معاً
      // للاطلاع، لكن الحقل يُعبّأ بالأخير (وبأقل سعر عام إن لم يسبق شراء منه).
      const r = await purchaseInvoiceApi.resolvePrice({
        product: pid,
        strategy: "LAST_PURCHASE",
        supplier: formData.supplierId || null,
      });
      return r.unit_price != null ? Number(r.unit_price) || 0 : 0;
    } catch (err) {
      console.error("resolvePrice failed", err);
      return 0;
    }
  };

  /* بحث سريع/باركود — نفس سلوك `handleBarcodeEnter` في محرر المبيعات: الماسح
     يكتب الرقم ويضغط ⏎ فيهبط المنتج على أول سطر فارغ، وإلا على سطر جديد.
     كانت الشاشتان غير متكافئتين: البيع يمسح والشراء لا. */
  const [barcodeQuery, setBarcodeQuery] = useState("");
  const handleBarcodeEnter = async (raw: string) => {
    const t = raw.trim();
    if (!t) return;
    const norm = t.toLowerCase();
    const hit = allDbItems.find(
      (i) => (i.barcode || "").trim().toLowerCase() === norm
        || (i.modelNumber || "").trim().toLowerCase() === norm
        || String(i.id) === t,
    );
    if (!hit) {
      // T-SEARCH: الرسالة وحدها طريقٌ مسدود — نفتح الفهرس على النصّ نفسه.
      setPickerQuery(t);
      setShowItemSearch(true);
      toast(`لا تطابق تامّ لـ«${t}» — ابحث في الفهرس الكامل.`, "info");
      return;
    }
    const items = formData.items || [];
    const emptyIdx = items.findIndex((i) => !i.itemId);
    const price = await resolveSuggestedPrice(hit.id);
    await applyItemAt(emptyIdx >= 0 ? emptyIdx : null, hit, price);
    setBarcodeQuery("");
  };

  const applyItemAt = async (index: number | null, item: Item, lastPrice?: number, qtyOverride?: number) => {
    // task18 DEF-C3: إن كان المنتج موجوداً في سطر آخر — نبّه المستخدم ودعه يختار:
    // موافق = دمج الكمية في السطر القائم · إلغاء = إضافته كسطر مستقل (سعر مختلف).
    const current = formData.items || [];
    const dupIndex = current.findIndex(
      (r, i) => i !== index && String(r.itemId) === String(item.id) && r.itemId !== ""
    );
    if (dupIndex >= 0) {
      const merge = await confirm({
        message: `المنتج «${item.name}» مضاف مسبقاً في الفاتورة. اختر الإجراء:`,
        confirmText: "دمج الكمية",
        cancelText: "سطر جديد مستقل",
        danger: false,
      });
      if (merge) {
        const updated = [...current];
        const existing = { ...updated[dupIndex] };
        existing.quantity = (Number(existing.quantity) || 0) + 1;
        existing.totalPrice = roundSqlMoney2((Number(existing.quantity) || 0) * (Number(existing.unitPrice) || 0));
        updated[dupIndex] = existing;
        // أفرغ السطر الذي كان قيد التحرير (لتفادي تكراره) ما لم يكن سطر الإدخال الفارغ.
        if (index !== null && index < updated.length && index !== dupIndex) {
          updated[index] = {
            id: updated[index].id,
            itemId: "", name: "", categoryId: "", categoryName: "",
            specifications: "", imageUrls: [], quantity: 1, unitPrice: 0, totalPrice: 0,
          };
        }
        recalculateTotals({ items: updated });
        return;
      }
      // إلغاء الدمج → نتابع بالمسار العادي فيُملأ السطر الجاري كمنتج مستقل
      // (سطر مكرّر بسعره الخاص — وهو المطلوب).
    }
    // FEAT-1 edit-protection: السعر اليدوي يُحفظ فقط عند **إعادة اختيار نفس المنتج**
    // على السطر. اختيار منتج *مختلف* يُعاد تسعيره دائماً بسعر المنتج الجديد — وإلا
    // يرث المنتج الجديد سعر المنتج القديم.
    const currentRow =
      index !== null && index < (formData.items || []).length
        ? (formData.items || [])[index]
        : undefined;
    const existingPrice = Number(currentRow?.unitPrice) || 0;
    const sameProduct = currentRow != null && String(currentRow.itemId) === String(item.id);
    // T-R2: الكمية المُدخلة من بطاقة المنتج (إن وُجدت) وإلا 1.
    const qty = qtyOverride && qtyOverride > 0 ? qtyOverride : 1;
    const resolvedPrice = sameProduct && existingPrice > 0 ? existingPrice : (lastPrice || 0);
    const newItem: InvoiceItem = {
      id: crypto.randomUUID(),
      itemId: item.id,
      name: item.name,
      categoryId: item.categoryId,
      categoryName: item.categoryName,
      specifications: item.specifications || "",
      imageUrls: item.imageUrls,
      hsCodePrimary: item.hsCodePrimary,
      quantity: qty,
      unitPrice: roundSqlMoney4(resolvedPrice),
      totalPrice: roundSqlMoney2(qty * resolvedPrice),
    };

    let updatedItems = [...(formData.items || [])];
    if (index !== null && index < updatedItems.length) {
      newItem.id = updatedItems[index].id;
      // الصفّ نفسه لا صفٌّ بديل: بلا نقل المعرّف يُحذف البند ويُعاد إنشاؤه
      // عند الحفظ فتضيع كميته المستلَمة، ويرفض الخادمُ تبديلَ منتجٍ مستلَم
      // برسالته الدقيقة بدل «لا يُحذف».
      newItem.serverId = updatedItems[index].serverId;
      updatedItems[index] = newItem;
    } else {
      updatedItems.push(newItem);
    }

    // ملاحظة: لا نُضيف سطراً فارغاً تلقائياً عند اختيار منتج (طلب المالك) — يُضاف
    // السطر يدوياً بزر «أضف صف» أو من الشجرة. كان السلوك السابق يفتح سطراً بنفسه.
    recalculateTotals({ items: updatedItems });
    markDirty();
  };

  const handleItemSelect = (item: Item, lastPrice?: number) => {
    applyItemAt(activeItemSearchIndex, item, lastPrice);
    setShowItemSearch(false);
    setActiveItemSearchIndex(null);
  };

  const handleUpdateItem = (index: number, field: string, value: any) => {
    const newItems = [...(formData.items || [])];
    newItems[index] = { ...newItems[index], [field]: value };

    if (field === "quantity" || field === "unitPrice") {
      const qty = newItems[index].quantity || 0;
      const price = newItems[index].unitPrice || 0;
      newItems[index].totalPrice = roundSqlMoney2(qty * price);
    }

    recalculateTotals({ items: newItems });
    markDirty();
  };

  const handleRemoveItem = (index: number) => {
    const updatedItems = (formData.items || []).filter((_, i) => i !== index);
    recalculateTotals({ items: updatedItems });
    markDirty();
  };

  const handleUpdateFinancial = (field: string, value: any) => {
    if (field === 'taxType' || field === 'taxAmount' || field === 'taxRate') {
      setFormData((prev) => {
        const updated = { ...prev, [field]: value };
        const items = updated.items || [];
        const itemsSubtotal = items.reduce((sum, item) => sum + (item.totalPrice || 0), 0);
        const validShipping = effectiveShippingForTotals(updated);
        const afterDiscount = Math.max(0, itemsSubtotal - (updated.discountAmount || 0));
        const merchandiseBase = afterDiscount + validShipping;
        const vatBase = invoiceVatBaseIls(
          merchandiseBase,
          updated.conversionMetadata as Record<string, unknown> | null,
          updated.localPayments
        );

        let taxAmount = 0;
        if (updated.taxType === 'amount') {
          taxAmount = updated.taxAmount || 0;
        } else {
          taxAmount = vatBase * ((updated.taxRate || 0) / 100);
        }
        const mainVatRounded = roundSqlMoney2(taxAmount);

        const grandTotal = roundSqlMoney2(
          invoiceGrandTotalIls(
            merchandiseBase,
            mainVatRounded,
            updated.conversionMetadata as Record<string, unknown> | null,
            updated.localPayments
          )
        );
        const fees = (updated.fees || []).map((fee) => ({
          ...fee,
          amount: purchaseInvoiceFeeAmount(fee, merchandiseBase, vatBase, mainVatRounded),
        }));
        return {
          ...updated,
          subtotal: roundSqlMoney2(itemsSubtotal),
          taxAmount: mainVatRounded,
          grandTotal: roundSqlMoney2(grandTotal),
          fees,
        };
      });
      markDirty();
      return;
    }
    recalculateTotals({ [field]: value });
    markDirty();
  };

  const handleDealInfoUpdate = (field: string, value: any) => {
    setDealInfo((prev) => ({ ...prev, [field]: value }));
    markDirty();
  };

  const handleAddInstallment = () => {
    const newInstallmentNumber = installments.length + 1;
    const newInstallment: InvoiceInstallment = {
      id: crypto.randomUUID(),
      installmentNumber: newInstallmentNumber,
      amount: 0,
      status: "unpaid",
      notes: "",
    };
    setInstallments([...installments, newInstallment]);
    markDirty();
  };

  const handleRemoveInstallment = (index: number) => {
    const updatedInstallments = installments.filter((_, i) => i !== index);
    const renumberedInstallments = updatedInstallments.map(
      (installment, idx) => ({ ...installment, installmentNumber: idx + 1 })
    );
    setInstallments(renumberedInstallments);
    markDirty();
  };

  const handleUpdateInstallment = (index: number, field: string, value: any) => {
    const updatedInstallments = [...installments];
    updatedInstallments[index] = { ...updatedInstallments[index], [field]: value };
    setInstallments(updatedInstallments);
    markDirty();
  };

  const handleToggleInstallmentPlan = (enabled: boolean) => {
    setInstallmentPlanEnabled(enabled);
    if (!enabled) {
      setInstallments([]);
    } else {
      handleAddInstallment();
    }
    markDirty();
  };

  const handleRecalculateLanded = async () => {
    if (!formData.shipment || !formData.id) {
      toast("لا توجد شحنة مرتبطة أو الفاتورة غير محفوظة بعد.", "error");
      return;
    }
    const meta = formData.conversionMetadata as Record<string, unknown> | undefined;
    const dr = Number(
      meta?.["remaining_balance_rate_deal"] ??
        meta?.["remainingBalanceRate"] ??
        3.6
    );
    const sr = Number(
      meta?.["remaining_balance_rate_shipment"] ??
        meta?.["shipmentRemainingRate"] ??
        meta?.["remainingBalanceRate"] ??
        3.6
    );
    const basis = String(
      meta?.["clearance_cost_basis"] ?? meta?.["clearanceCostBasis"] ?? ""
    ).toLowerCase();
    const useCl = basis === "cost_lines";
    setRecalcBusy(true);
    try {
      const res = await purchaseInvoiceApi.recalculateLandedCost({
        shipment_id: Number(formData.shipment),
        deal_remaining_rate: dr,
        shipment_remaining_rate: sr,
        use_cost_lines: useCl,
      });
      const full = await purchaseInvoiceApi.get(Number(formData.id));
      setFormData(mapPurchaseInvoiceDtoToInvoice(full));
      const msg =
        typeof res?.message === "string" && res.message.trim()
          ? res.message
          : res?.updated
            ? "تم إعادة حساب تكلفة الرسوم والبنود من الخادم."
            : "لم تُحدَّث الفاتورة من الخادم.";
      toast(msg, res?.updated ? "success" : "info");
    } catch (e) {
      // console suppressed
      toast(humanizeThrown(e, "تعذّر إعادة الحساب"), "error");
    } finally {
      setRecalcBusy(false);
    }
  };

  /** أساس البضاعة + شحن الفاتورة (لنسب «البضاعة» في بنود الرسوم الإضافية) */
  const ilsMerchandiseBase = useMemo(() => {
    const items = formData.items || [];
    const itemsSubtotal = items.reduce((s, i) => s + (Number(i.totalPrice) || 0), 0);
    const validShipping = effectiveShippingForTotals(formData);
    return Math.max(0, itemsSubtotal - (formData.discountAmount || 0)) + validShipping;
  }, [
    formData.items,
    formData.discountAmount,
    formData.currency,
    formData.shippingIncluded,
    formData.shippingCost,
  ]);

  /** أساس ض.ق.م: بضاعة + شحن دولي + تخليص + نقل محلي (كل ما قبل ض.ق.م الفاتورة) */
  const ilsVatBase = useMemo(
    () =>
      invoiceVatBaseIls(
        ilsMerchandiseBase,
        formData.conversionMetadata as Record<string, unknown> | null,
        formData.localPayments
      ),
    [ilsMerchandiseBase, formData.conversionMetadata, formData.localPayments]
  );

  /** وصف الصفقة (عربي) — من صفقة مفتوحة أو من حقل اسم/وصف الفاتورة أو جلب من الصفقة */
  const headerDealDescription = useMemo(() => {
    const fromDeal = String(dealData?.dealDescription ?? "").trim();
    const fromInvoice = String(formData.invoiceName ?? "").trim();
    const fromFetched = String(fetchedDealDescription ?? "").trim();
    return fromDeal || fromInvoice || fromFetched;
  }, [dealData?.dealDescription, formData.invoiceName, fetchedDealDescription]);

  useEffect(() => {
    const fromDeal = String(dealData?.dealDescription ?? "").trim();
    const fromInv = String(formData.invoiceName ?? "").trim();
    const did = formData.dealId;
    if (!did || fromDeal || fromInv) {
      setFetchedDealDescription("");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const d = await dealsService.getDeal(String(did));
        if (!cancelled) {
          setFetchedDealDescription(String(d?.dealDescription ?? "").trim());
        }
      } catch {
        if (!cancelled) setFetchedDealDescription("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [formData.dealId, formData.invoiceName, dealData?.dealDescription]);

  /** اسم المورد للعرض في الرأس */
  const headerSupplierName = useMemo(() => {
    const sid = formData.supplierId;
    const fromList = sid
      ? suppliers.find((s) => s.id === sid)?.tradeName
      : undefined;
    return (
      String(fromList ?? "").trim() ||
      String(formData.factoryName ?? "").trim() ||
      String(formData.supplierSnapshot?.tradeName ?? "").trim() ||
      String(formData.dealInfo?.supplierSnapshot?.tradeName ?? "").trim()
    );
  }, [
    formData.supplierId,
    formData.factoryName,
    formData.supplierSnapshot,
    formData.dealInfo?.supplierSnapshot,
    suppliers,
  ]);

  /** فواتير شيكل بنسبة: مزامنة taxAmount/grandTotal مع الأساس (غالباً كانت tax_amount=0 في DB) */
  useEffect(() => {
    if (effectiveReadOnly) return;
    if (formData.currency !== "ILS") return;
    if (formData.taxType === "amount") return;
    if (!(formData.items || []).length) return;
    recalculateTotals({});
  }, [
    readOnly,
    formData.isHistorical,
    formData.currency,
    formData.taxType,
    formData.items,
    formData.discountAmount,
    formData.shippingCost,
    formData.shippingIncluded,
    formData.conversionMetadata,
    formData.localPayments,
    formData.taxRate,
    ilsMerchandiseBase,
  ]);

  // G1: عرض موحّد بلا أصفار عشرية زائدة (مع فاصل آلاف للمبالغ).
  const fmt = (v: number) => formatMoney(v);
  // W4: إجمالي الكميات (مجموع كميات البنود) يُعرض بجانب الإجماليات المالية.
  const totalQty = (formData.items || []).reduce(
    (s: number, it: any) => s + (Number(it.quantity) || 0), 0,
  );

  /** خطأ الحقل كما أرسله الخادم، بمفتاح DRF التقني. */
  const fe = (name: string): string | undefined => saveError?.fieldErrors[name];

  const fld = (label: string, node: React.ReactNode, error?: string) => (
    <label className="ktra-field">
      <span className="ktra-field-label">{label}</span>
      {node}
      <FieldError message={error} />
    </label>
  );

  /* T-SIMPL2 — قناع العناصر المتقدّمة، بنفس السِّجل ونفس المفاتيح المستعملة في
     محرّر البيع (`utils/uiMode.ts`): «الضريبة» واحدةٌ على الجانبين، فلا يفترق
     الوضع السهل بين فاتورةٍ وأخرى. ومعه قاعدة السقوط للظهور: ما حمل رقماً
     فعلياً يظهر رغم الوضع. */
  const { show: showAdv } = useSimpleUi();
  const invoiceHasTax = Number(formData.taxRate || 0) > 0 || Number(formData.taxAmount || 0) > 0.0001;

  const selectedSupplier = formData.supplierId
    ? suppliers.find((s) => s.id === formData.supplierId)
    : undefined;
  const shipmentLinkId = formData.importLogistics?.shipmentId || formData.shipment;
  const shipmentDisplayNumber = formData.importLogistics?.shipmentNumber || `#${shipmentLinkId || ""}`;
  const isShipmentLinkedImport = Boolean(shipmentLinkId);
  const costLabels = getPurchaseInvoiceCostLabels(isShipmentLinkedImport);

  /* T-RECVIS: «كم انطلب وكم وصل وكم باقي» داخل الفاتورة نفسها.

     الأرقام كلّها من الخادم (`receipt_progress` للرأس و`remainingQuantity`
     للبند) — الشاشة تعرض ولا تطرح، فلا يفترق «الباقي» هنا عن تقرير البواقي.
     تظهر على الفاتورة المحلية المرحّلة وحدها: قبل الترحيل لا استلامَ أصلاً،
     والمستوردة تدخل مخزنها من تخليص الشحنة لا من هذه الشاشة. */
  const receiptProgress = formData.receiptProgress;
  const showReceiptColumns =
    // «المرحّلة فقط» هي القاعدة (لا أعمدةَ أصفارٍ على مسودّة)، لكنّ فاتورةً
    // غير مرحّلة استُلم منها شيءٌ بالمسار القديم تعرضه أيضاً — إخفاء كميةٍ
    // وصلت المخزنَ فعلاً كذبٌ لا اختصار.
    (Boolean(formData.isPosted) || (receiptProgress?.received ?? 0) > 0)
    && !formData.isReturn
    && !isShipmentLinkedImport
    && formData.invoiceType !== "international"
    && !formData.dealId
    && !formData.clearanceId
    && Boolean(receiptProgress && receiptProgress.linesTotal > 0);
  const receiptSummaryText = receiptProgress
    ? `استُلم ${formatQuantity(receiptProgress.received)} من `
      + `${formatQuantity(receiptProgress.ordered)} — باقي `
      + `${formatQuantity(receiptProgress.remaining)}`
    : "";
  /** خليّة «باقي الاستلام»: الباقي > 0 تنبيهٌ لا رقمٌ صامت. */
  const remainingCell = (row: InvoiceItem) => {
    const remaining = Number(row.remainingQuantity) || 0;
    return (
      <span
        className={remaining > 0
          ? "font-semibold text-[var(--ktra-warn)]"
          : "ktra-text-soft"}
      >
        {formatQuantity(remaining)}
      </span>
    );
  };

  /* ───────────── تنبيه أثر السعر على متوسط تكلفة المنتج ───────────── */
  // عند إدخال سعر سيغيّر متوسط تكلفة المنتج (المرجّح بالكمية)، نعرض تنبيهاً فورياً
  // مع رابط لواجهة «تكلفة المنتجات» والمنتج محدد افتراضياً.
  interface CostWarning { productId: number; name: string; from: number; to: number }
  const [costWarnings, setCostWarnings] = useState<Record<string, CostWarning>>({});
  // تخزين مؤقّت لتكلفة كل منتج (متوسط مرجّح + إجمالي الكمية المشتراة) لتفادي طلب لكل ضغطة.
  const costCacheRef = useRef<Record<number, { avg: number; qty: number }>>({});

  const evaluateCostImpact = async (rowId: string, item: InvoiceItem) => {
    const pid = Number(item.itemId);
    const price = Number(item.unitPrice) || 0;
    const lineQty = Number(item.quantity) || 0;
    if (!pid || price <= 0 || lineQty <= 0) {
      setCostWarnings((w) => { if (!w[rowId]) return w; const n = { ...w }; delete n[rowId]; return n; });
      return;
    }
    let base = costCacheRef.current[pid];
    if (!base) {
      try {
        const b = await inventoryApi.getProductCostBreakdown(pid);
        base = { avg: Number(b.average_cost) || 0, qty: Number(b.total_purchased_qty) || 0 };
        costCacheRef.current[pid] = base;
      } catch {
        return; // تعذّر التحميل — لا تُظهر تنبيهاً مضلّلاً
      }
    }
    // متوسط مرجّح متوقّع لو أُضيف هذا السطر: Σ(تكلفة) + سعر×كمية ÷ Σ(كمية) + كمية.
    const newQty = base.qty + lineQty;
    const newAvg = newQty > 0 ? (base.avg * base.qty + price * lineQty) / newQty : price;
    // لا تكلفة سابقة (منتج جديد) → لا متوسط ليتغيّر؛ تغيّر ضئيل (<0.01) يُتجاهل.
    if (base.avg > 0 && Math.abs(newAvg - base.avg) >= 0.01) {
      setCostWarnings((w) => ({ ...w, [rowId]: { productId: pid, name: item.name, from: base.avg, to: newAvg } }));
    } else {
      setCostWarnings((w) => { if (!w[rowId]) return w; const n = { ...w }; delete n[rowId]; return n; });
    }
  };

  /* ───────────── أعمدة جدول البنود (KitGrid) ───────────── */
  const finalCostFeesTotal = (formData.fees || []).reduce(
    (sum, fee) => sum + (Number(fee.amount) || 0), 0,
  );
  const finalItemCosts = useMemo(() => {
    const localExtras = sumTaxesAndFeesExtras(
      formData.localPayments,
      ilsMerchandiseBase,
      {
        mainVatIls: Math.max(0, Number(formData.taxAmount) || 0),
        invoiceVatBaseIls: ilsVatBase,
      },
    );
    return allocateInvoiceFinalCosts(formData.items || [], {
      transferTotalIls: transferCommissionsIlsForVat(
        formData.conversionMetadata as Record<string, unknown> | null,
      ),
      taxAndFeesTotalIls:
        Math.max(0, Number(formData.taxAmount) || 0) +
        localExtras +
        finalCostFeesTotal,
    });
  }, [
    formData.items,
    formData.taxAmount,
    formData.localPayments,
    formData.conversionMetadata,
    ilsMerchandiseBase,
    ilsVatBase,
    finalCostFeesTotal,
  ]);

  /* T-SERIAL: من يتتبّع وحداته؟ الجواب من كتالوج المنتجات (`view=lookup`)، فالبند
     نفسه لا يحمل العَلَم. الخدمة مستثناة — بلا مخزون فبلا وحدات. */
  const dbItemsById = useMemo(() => {
    const m = new Map<string, Item>();
    allDbItems.forEach((it) => m.set(String(it.id), it));
    return m;
  }, [allDbItems]);
  const itemTracksSerials = useCallback(
    (row: InvoiceItem) => {
      if (serialMode === "off" || !row.itemId) return false;
      return Boolean(dbItemsById.get(String(row.itemId))?.isSerialized);
    },
    [serialMode, dbItemsById],
  );
  const anySerializedItem = useMemo(
    () => (formData.items || []).some(itemTracksSerials),
    [formData.items, itemTracksSerials],
  );

  const itemColumns: KitGridColumn<InvoiceItem>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "itemId", header: "رقم المنتج", width: "100px" },
    { key: "name", header: "اسم المنتج", width: "25%" },
    { 
      key: "specifications", 
      header: "بيان", 
      width: "1%",
      render: (r, ri) => (
        <input
          id={`ktra-grid-input-${ri}-specifications`}
          data-ktra-key="1"
          size={Math.max(4, (r.specifications || "").length)}
          style={{
            minWidth: "45px",
            width: "max-content",
            fieldSizing: "content",
            border: "1px solid transparent",
            background: "transparent",
            padding: "0 3px",
            font: "inherit",
            height: "20px",
            outline: "none"
          }}
          value={r.specifications == null ? "" : String(r.specifications)}
          onChange={(e) => handleUpdateItem(ri, "specifications", e.target.value)}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--ktra-accent)";
            e.currentTarget.style.background = "var(--ktra-field-focus)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "transparent";
            e.currentTarget.style.background = "transparent";
          }}
        />
      )
    },
    { key: "quantity", header: "الكمية", width: "80px", align: "center", type: "number" },
    // T-RECVIS: المستلَم والباقي — على الفاتورة المحلية المرحّلة وحدها.
    ...(showReceiptColumns ? [
      { key: "receivedQty", header: "مستلَم", width: "80px", align: "center" as const, readOnly: true },
      {
        key: "remainingQty", header: "باقي الاستلام", width: "100px",
        align: "center" as const, readOnly: true, render: remainingCell,
      },
    ] : []),
    // T-SERIAL: عمود الأرقام على المنتجات التسلسلية وحدها، ويختفي بنمط «معطّل».
    ...(anySerializedItem ? [{
      key: "serials", header: "الأرقام التسلسلية", width: "120px", align: "center" as const, readOnly: true,
    }] : []),
    { key: "unitPrice", header: isShipmentLinkedImport ? "قبل ض.ق.م والرسوم/وحدة" : costLabels.unitPrice, width: isShipmentLinkedImport ? "160px" : "100px", align: "center", type: "number" },
    { key: "totalPrice", header: isShipmentLinkedImport ? "قبل ض.ق.م والرسوم/سطر" : costLabels.lineTotal, width: isShipmentLinkedImport ? "160px" : "100px", align: "center", readOnly: true },
    ...(isShipmentLinkedImport ? [{ key: "finalUnitCost", header: "التكلفة النهائية/وحدة", width: "160px", align: "center" as const, readOnly: true }] : []),
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const itemGetCell = (row: InvoiceItem, key: string): string | number => {
    const idx = (formData.items || []).indexOf(row);
    switch (key) {
      case "seq": return idx + 1;
      case "itemId": return row.itemId || "";
      case "name": return row.name || "";
      case "specifications": return row.specifications || "";
      case "quantity": return row.quantity || 0;
      case "receivedQty": return formatQuantity(row.receivedQuantity || 0);
      case "remainingQty": return formatQuantity(row.remainingQuantity || 0);
      case "unitPrice": return row.unitPrice || 0;
      case "totalPrice": return row.totalPrice || 0;
      case "finalUnitCost": return finalItemCosts[idx]?.finalUnit || 0;
      default: return "";
    }
  };

  const itemOnChange = (rowIndex: number, key: string, value: string) => {
    const items = [...(formData.items || [])];
    const item = { ...items[rowIndex] };
    if (key === "quantity") {
      item.quantity = Number(value) || 0;
      item.totalPrice = roundSqlMoney2(item.quantity * (item.unitPrice || 0));
    } else if (key === "unitPrice") {
      item.unitPrice = Number(value) || 0;
      item.totalPrice = roundSqlMoney2((item.quantity || 0) * item.unitPrice);
    }
    items[rowIndex] = item;

    // تنبيه أثر السعر على متوسط تكلفة المنتج (فوري أثناء كتابة السعر/الكمية).
    if (key === "unitPrice" || key === "quantity") {
      void evaluateCostImpact(item.id, item);
    }

    // Auto-expanding line item grid logic when last row is edited
    const lastRow = items[items.length - 1];
    if (rowIndex === items.length - 1 && lastRow.itemId) {
      items.push({
        id: crypto.randomUUID(),
        itemId: "",
        name: "",
        categoryId: "",
        categoryName: "",
        specifications: "",
        imageUrls: [],
        quantity: 1,
        unitPrice: 0,
        totalPrice: 0,
      });
    }

    recalculateTotals({ items });
  };

  const addRow = () => {
    const newItem: InvoiceItem = {
      id: crypto.randomUUID(),
      itemId: "",
      name: "",
      categoryId: "",
      categoryName: "",
      specifications: "",
      imageUrls: [],
      quantity: 1,
      unitPrice: 0,
      totalPrice: 0,
    };
    recalculateTotals({ items: [...(formData.items || []), newItem] });
    markDirty();
  };

  const removeRow = (key: string) => {
    const updated = (formData.items || []).filter((i) => i.id !== key);
    recalculateTotals({ items: updated });
    markDirty();
  };

  const renderItemIdCell = (row: InvoiceItem, rowIndex: number) => (
    <button
      type="button"
      className="ktra-cell-picker"
      disabled={effectiveReadOnly}
      data-ktra-key="1"
      onClick={() => {
        setActiveItemSearchIndex(rowIndex);
        setShowItemSearch(true);
      }}
      title="فهرس المنتجات الكامل (+)"
    >
      {row.itemId ? `#${row.itemId}` : "…"}
    </button>
  );

  /* task24: خريطة سعر الشراء المقترح (آخر/أقل شراء أو متوسط التكلفة) لكامل
     الكتالوج — تُجلب دفعة واحدة لعرض السعر داخل خيارات المنتقي بلا نقر.
     تُعاد الجلبة عند تغيّر المورد: «آخر شراء» يُحصر بمورد الفاتورة بينما «أقل
     شراء» يبقى عاماً لكل الموردين. */
  const [purchasePriceMap, setPurchasePriceMap] = useState<
    Map<number, { price: string; label: string; prices?: any[] }>
  >(new Map());
  useEffect(() => {
    let cancelled = false;
    purchaseInvoiceApi
      .priceList(formData.supplierId || null)
      .then((rows) => {
        if (cancelled) return;
        const m = new Map<number, { price: string; label: string; prices?: any[] }>();
        for (const r of rows) {
          if (r.unit_price != null && Number(r.unit_price) > 0) {
            m.set(r.product_id, { price: r.unit_price, label: r.source_label, prices: r.prices });
          }
        }
        setPurchasePriceMap(m);
      })
      .catch(() => { /* بلا تاريخ شراء — تُعرض الخيارات بلا سعر */ });
    return () => { cancelled = true; };
  }, [formData.supplierId]);

  /* ISSUE #133 (منتقي أصنافٍ واحد للبيع والشراء): نفس ما يراه البائع — شارة
     حالة المخزون والمتاح بعد الحجز، لا حسابٌ ثانٍ ولا طلبٌ ثانٍ. `allDbItems`
     يصل أصلاً من نفس عقد `?view=lookup` (عبر `itemsService.subscribeToItems`
     في الأب)، و`stock_status`/`is_service`/`available_quantity`/
     `quantity_on_hand` تصل الآن ضمن `Item` نفسه (THA-19
     `mapPickerProductToItem` صار يحملها) — إعادة طلب `listPickerProducts` هنا
     كانت ستُنزّل نفس العقد الموزون (685 كيلوبايت/1490 منتجاً) مرّتين لكل فتح
     شاشة، وهذا العقد ضُيِّق أصلاً لهذا السبب بعينه (راجع تعليق
     `listPickerProducts` في `services/inventoryApi.ts`). */

  /* نفس تقرير «المحجوزات» الذي يقرأه جانب البيع (`getReservedStock`) — بلا
     استثناء زبون هنا: لا زبون على فاتورة شراء أصلاً، فكل حجزٍ «لغيرها». هذا
     تقريرٌ منفصلٌ فعلاً عن حمولة المنتج، فلا بديل له من `allDbItems`. */
  const [reservationRows, setReservationRows] = useState<ReservedStockRow[]>([]);
  useEffect(() => {
    let cancelled = false;
    getReservedStock()
      .then((rows) => { if (!cancelled) setReservationRows(rows); })
      .catch(() => { if (!cancelled) setReservationRows([]); });
    return () => { cancelled = true; };
  }, []);
  const reservationIndex = useMemo(() => buildReservationIndex(reservationRows), [reservationRows]);

  /* العين (`PriceVisibilityContext`) تحكم `indicativePurchasePrice` وحده في
     هذه الدالّة — لا وجود لتلك العين على جانب الشراء أصلاً (لا زبونَ واقفاً
     أمام شاشة الشراء يُحتمل أن يلمح شيئاً)، و`stockBadge`/
     `availableAfterReservation` غير محكومَين بها بنصّ الدالّة نفسه بصرف
     النظر عن السياق. القيمة `true` هنا بلا معنى عملي فعلاً، لا اختياراً صامتاً. */
  const pickerVisibility = useMemo(() => getPickerFieldVisibility("purchase", true), []);

  /* task13 M5: منتقي مدمج في خلية اسم المنتج (يحل محل المودال كمسار أساسي) */
  const itemOptions = useMemo(
    () => allDbItems.map((it) => {
      const pp = purchasePriceMap.get(Number(it.id));
      const reservation = reservationIndex.get(Number(it.id));
      const reserved = totalReserved(reservation);
      const onHand = Number(it.quantity_on_hand ?? 0);
      return {
        id: it.id,
        label: it.name,
        // ISSUE #133: نفس شارة «نفذ/منخفض» التي يراها البائع — القاعدة عند
        // الخادم وحده (`inventory/stock_status.py`)، هنا قراءةٌ لا حساب.
        badge: pickerVisibility.stockBadge
          ? stockBadgeFor({ id: Number(it.id), stock_status: it.stock_status, is_service: it.is_service })
          : undefined,
        // T-RESERVEVIS: رصيد المنتج بجانب اسمه — كان جانب البيع وحده يعرضه،
        // فيطلب المشتري ما عنده منه رفٌّ ممتلئ.
        // ISSUE #133: والمحجوز يُذكر في الخيار نفسه أيضاً — نفس ما يراه البائع.
        sub: pickerVisibility.availableAfterReservation && reserved > 0
          ? `الرصيد: ${formatQuantity(onHand, "—")} · محجوز: ${formatQuantity(reserved, "—")} · المتاح: ${formatQuantity(availableForSale(onHand, reservation), "—")}`
          : `الرصيد: ${formatQuantity(onHand, "—")}`,
        // T-SEARCH: الباركود ورقم الموديل وأرقام كتالوج الموردين يُبحَث فيها
        // ولا تُعرض — وهي ما يكتبه المشتري فعلاً وقت الطلب.
        keywords: [it.barcode, it.modelNumber, it.supplierCodes]
          .filter(Boolean).join(" ").toLowerCase(),
        price: pp ? formatMoney(Number(pp.price)) : undefined,
        // لا آخر/أقل شراء ولا متوسط تكلفة → نص «بدون سعر» بدل الفراغ.
        priceLabel: pp ? pp.label : "بدون سعر",
        // ISSUE #113: «أقل شراء» بالعملة الأساسية بينما «آخر شراء» بعملة
        // الفاتورة المصدر — بلا تمييز يبدو الأقلّ معطوباً لمن يشتري بعملة
        // غير الأساسية. buildPurchasePriceHintChips وحدها تبني هذه الرقاقات
        // (مصدرٌ واحد يشاركه منتقي بند الطلبية).
        prices: buildPurchasePriceHintChips(pp?.prices, {
          invoiceLink: (id) => `/purchase-invoices/${id}`,
        }).map(({ label, value, link }) => ({ label, value, link: link ?? undefined })),
      };
    }),
    [allDbItems, purchasePriceMap, reservationIndex, pickerVisibility],
  );

  /** T-SEARCH: المورّد يُبحَث باسمه وهاتفه ورقمه — مرآة منتقي العميل. */
  const supplierOptions = useMemo(
    () => suppliers.map((sup) => ({
      id: sup.id,
      label: sup.tradeName || sup.alias || `#${sup.id}`,
      sub: `#${sup.id}${sup.city ? ` · ${sup.city}` : ""}`,
      keywords: [sup.id, sup.phone, sup.mobile, sup.alias]
        .filter(Boolean).join(" ").toLowerCase(),
    })),
    [suppliers],
  );

  /**
   * T-PRODUCT M4 — المعالِج الواحد لكل تعديلٍ على منتج من داخل هذه الفاتورة:
   * القلم (`ItemQuickEditModal`) والبطاقة (`ProductCardModal`) يمرّان به معاً.
   *
   * نصفان لا نصف واحد: الكتالوج المحلي **والسطور**. سطر فاتورة الشراء يلتقط
   * الاسم نسخةً عند الاختيار (`applyItemAt`) ويعرض `row.name` لا الكتالوج —
   * فترقيع الكتالوج وحده (وهو ما كان يحدث) يترك السطر على اسمه القديم **إلى
   * الأبد**: لا مشترِك حدثٍ هنا يُنقذه كما في فاتورة البيع.
   *
   * و`markDirty` فقط إن تغيّر صفٌّ فعلاً — وإلا رفع فتحُ النافذة وإغلاقها على
   * فاتورةٍ نظيفة إنذارَ «تغييرات غير محفوظة» بلا تغييرٍ واحد.
   */
  const applyProductUpdate = (updated: Record<string, unknown>) => {
    const item = productToItem(updated);
    setAllDbItems((prev) =>
      prev.some((x) => String(x.id) === String(item.id))
        ? prev.map((x) => (String(x.id) === String(item.id) ? item : x))
        : [item, ...prev],
    );
    // القرار يُتخذ على الحالة الحاضرة لا داخل مُحدِّث `setFormData`: المُحدِّث
    // يعمل في طور الرسم لا فور استدعائه، فراية تُرفع بداخله تُقرأ هنا وهي بعدُ
    // على قيمتها القديمة.
    const rows = formData.items || [];
    const needsRename = rows.some(
      (r) => String(r.itemId) === String(item.id) && r.name !== item.name,
    );
    if (!needsRename) return;
    setFormData((prev) => ({
      ...prev,
      items: (prev.items || []).map((r) => (
        String(r.itemId) === String(item.id) ? { ...r, name: item.name } : r
      )),
    }));
    markDirty();
  };

  const renderItemNameCell = (row: InvoiceItem, rowIndex: number) => {
    const selectedId = row.itemId ? Number(row.itemId) : null;
    return (
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <KitAutocomplete
        value={row.name || ""}
        options={itemOptions}
        disabled={effectiveReadOnly}
        placeholder="اكتب اسم المنتج…"
        onPick={async (id) => {
          const it = allDbItems.find((x) => String(x.id) === String(id));
          if (it) {
            const lastPrice = await resolveSuggestedPrice(it.id);
            applyItemAt(rowIndex, it, lastPrice);
            setTimeout(() => {
              document.getElementById(`ktra-grid-input-${rowIndex}-quantity`)?.focus();
            }, 50);
          }
        }}
        onInfo={(id) => { const pid = Number(id); if (pid) { setCardCanAdd(false); setCardProductId(pid); } }}
        onEdit={effectiveReadOnly ? undefined : (id) => { const pid = Number(id); if (pid) setQuickEditProductId(pid); }}
        onShowMore={(q) => {
          setPickerQuery(q);
          setActiveItemSearchIndex(rowIndex);
          setShowItemSearch(true);
        }}
        onFreeText={(t) => {
          // task18 DEF-B1/B3: «إضافة كمنتج جديد» يفتح إنشاء منتج سريع مُعبّأً بالنص
          // ويُنشئه فعلياً (Product) بدل ترك سطر حر بلا itemId يُحذف عند الحفظ.
          setInlineCreate({ rowIndex, name: t.trim() });
        }}
      />
      {/* DEF-008: أيقونة (i) بجانب المنتج المختار → بطاقة المنتج */}
      {selectedId != null && (
        <button
          type="button"
          className="ktra-ellipsis"
          onClick={() => { setCardCanAdd(false); setCardProductId(selectedId); }}
          title="بطاقة المنتج"
        ><Info className="w-3.5 h-3.5" /></button>
      )}
      {/* T-ITEMS M3: قلمٌ بجانب (i) — تعديل المنتج دون مغادرة الفاتورة.
          الفاتورة المرحّلة للقراءة فقط، فلا قلم عليها — كما في محرّر فاتورة البيع. */}
      {selectedId != null && !effectiveReadOnly && (
        <button
          type="button"
          className="ktra-ellipsis"
          onClick={() => setQuickEditProductId(selectedId)}
          title="تعديل سريع للمنتج"
        ><Pencil className="w-3.5 h-3.5" /></button>
      )}
    </div>
    );
  };

  /* T-SERIAL: زر أرقام البند — العدد مقابل الكمية، وأحمر حين ينقص في النمط
     الإجباري. المنع نفسه عند الاستلام/الترحيل على الخادم. */
  const renderSerialsCell = (row: InvoiceItem, rowIndex: number) => {
    if (!itemTracksSerials(row)) return <span className="ktra-text-soft">—</span>;
    const entered = row.serials?.length ?? 0;
    const qty = Math.max(0, Math.trunc(Number(row.quantity) || 0));
    const incomplete = serialMode === "required" && entered !== qty;
    return (
      <button
        type="button"
        className="ktra-toolbtn"
        style={{
          width: "100%", fontWeight: 600,
          ...(incomplete ? { color: "var(--ktra-danger, #c00)" } : {}),
        }}
        onClick={() => setSerialRowIndex(rowIndex)}
        title={entered > 0 ? `الأرقام: ${row.serials!.join("، ")}` : "لم تُدخَل أرقام بعد"}
      >
        {entered > 0 ? `${entered}/${qty}` : (serialMode === "required" ? `0/${qty}` : "إدخال")}
      </button>
    );
  };

  const renderDeleteCell = (row: InvoiceItem) =>
    effectiveReadOnly ? null : (
      <button
        type="button"
        className="ktra-iconbtn ktra-iconbtn--danger"
        onClick={() => removeRow(row.id)}
        title="حذف السطر"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    );

  itemColumns[1].render = renderItemIdCell;
  itemColumns[2].render = renderItemNameCell;
  const serialsColumn = itemColumns.find((column) => column.key === "serials");
  if (serialsColumn) serialsColumn.render = renderSerialsCell;
  const finalUnitColumn = itemColumns.find((column) => column.key === "finalUnitCost");
  if (finalUnitColumn) {
    finalUnitColumn.render = (row) => {
      const index = (formData.items || []).indexOf(row);
      return formatNumber(finalItemCosts[index]?.finalUnit || 0, { maxDecimals: 4, group: true });
    };
  }
  const deleteColumn = itemColumns.find((column) => column.key === "del");
  if (deleteColumn) deleteColumn.render = renderDeleteCell;

  /* ───────────── تبويبات ───────────── */
  const notesTab = (
    <textarea
      className="ktra-input"
      rows={3}
      style={{ width: "100%" }}
      disabled={effectiveReadOnly}
      value={formData.notes || formData.dealInfo?.internalNotes || ""}
      onChange={(e) => handleDealInfoUpdate("internalNotes", e.target.value)}
    />
  );

  /* T-PCTX: المرفقات صارت نقاطاً حيّة (`attachments/`) لا حقولاً تُحفظ مع
     الفاتورة — المرحّلة لا تُعدَّل، فكان الإرفاق بعد الترحيل مستحيلاً عملياً وهو
     أكثر وقت يُحتاج فيه إيصال المورّد؛ ولا حذفَ كان أصلاً. نفس مكوّن البيع.
     المسودّة غير المحفوظة بلا معرّف ⇒ يبقى المحرّر القديم مدخلَها. */
  const attachmentsTab = formData.id && Number(formData.id) > 0 ? (
    <InvoiceAttachmentsTab
      invoiceId={Number(formData.id)}
      api={purchaseInvoiceContextApi}
      readOnly={readOnly}
    />
  ) : (
    <div className="ktra-legacy-tab">
      <AttachmentsSection data={formData} setData={(val) => { setFormData(val); markDirty(); }} />
    </div>
  );

  const basicInfoTab = (
    <div className="ktra-legacy-tab">
      {/* W7a: هوية مستند المرجع — شارة + رابط الفاتورة الأصلية + لغة معكوسة. */}
      {formData.isReturn && (
        <div
          className="ktra-banner"
          style={{ marginBottom: "8px", display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap", background: "var(--color-danger-bg, #fef2f2)", color: "var(--color-danger, #b91c1c)", fontWeight: 600 }}
        >
          <span style={{ padding: "2px 10px", borderRadius: "999px", background: "var(--color-danger, #b91c1c)", color: "#fff", fontSize: "12px" }}>
            مرتجع شراء ↩
          </span>
          <span style={{ fontWeight: 400 }}>
            هذا مستند إرجاع بضاعة للمورد — يعكس فاتورة الشراء (يُخرج الكمية ويُخفّض ذمم المورد).
          </span>
          {formData.originalInvoiceId && (
            <a
              href={`#/purchase-invoices/${formData.originalInvoiceId}`}
              onClick={(e) => { e.preventDefault(); if (formData.originalInvoiceId) openInNewTab(`/purchase-invoices/${formData.originalInvoiceId}`); }}
              style={{ textDecoration: "underline", cursor: "pointer" }}
              title="فتح الفاتورة الأصلية"
            >
              الفاتورة الأصلية #{formData.originalInvoiceNumber || formData.originalInvoiceId}
            </a>
          )}
        </div>
      )}
      {/* ملاحظة عاجلة مستحقة على هذا المورد — تظهر لكل مستخدم قبل إتمام الفاتورة. */}
      <PartnerNoteAlert partnerId={formData.supplierId || null} className="mb-2" />
      {formData.supplierId && (
        <div
          className="ktra-banner"
          style={{ marginBottom: "8px", display: "flex", gap: "18px", flexWrap: "wrap", fontSize: "13px" }}
        >
          {/* T-PCTX: الرقمان القديمان («قبل/بعد») تقريبٌ يطرح المتبقّي من رصيد
              **اليوم**، فالفاتورة المسدَّدة كانت تُظهر أثراً صفرياً وهي دائنةُ
              ذمم بكامل إجماليها. يبقى المعروض هنا الرصيد الحالي — وهو رقمٌ
              صحيح بذاته — و«قبل/بعد» الحقيقيان في تبويب «حساب المورّد». */}
          <span>رصيد المورد الحالي (بالعملة الأساسية): <strong>{formatMoney(formData.partnerBalance ?? 0)}</strong></span>
          <span className="text-[var(--color-text-muted)]">
            أثر هذه الفاتورة على حسابه — والرصيد قبلها وبعدها — في تبويب «حساب المورّد».
          </span>
        </div>
      )}
      <InvoiceBasicInfo
        data={formData}
        setData={(val) => { setFormData(val); markDirty(); }}
        suppliers={suppliers}
        readOnly={effectiveReadOnly}
        items={formData.items}
        onOpenAddSupplier={() => setShowAddSupplierModal(true)}
      />
    </div>
  );

  const feesTotal = (formData.fees || []).reduce(
    (sum, fee) => sum + (Number(fee.amount) || 0), 0,
  );
  // عمولات تحويل دفعات الصفقة — داخلة في تكلفة المنتج وأساس ض.ق.م، فتُعرض كسطر في الملخص.
  const transferCommissionsIls = transferCommissionsIlsForVat(
    formData.conversionMetadata as Record<string, unknown> | null,
  );
  const payableTotal = (Number(formData.grandTotal) || 0) + feesTotal;
  const defaultInlineFeeAccount =
    feeAccounts.find((account) => account.code === "5307") ||
    feeAccounts.find((account) => account.account_type === "Expense") ||
    feeAccounts[0] || null;
  // رسوم الفواتير الدولية تُصنَّف تحت شجرة «53 مصاريف الاستيراد المباشرة».
  const isInternationalInvoice =
    formData.invoiceType === "international" || isShipmentLinkedImport;
  const importExpenseAccounts = feeAccounts.filter(
    (account) => String(account.code || "").startsWith("53") && account.code !== "53",
  );
  const resolveImportFeeAccount = async (name: string) => {
    try {
      const account = await accountingApi.resolveImportExpenseAccount(name);
      setAllAccounts((prev) => (
        prev.some((a) => a.id === account.id) ? prev : [...prev, account]
      ));
      return account as { id: number; code?: string; name?: string };
    } catch (error) {
      console.error("[PurchaseInvoiceFees] Failed to resolve import expense account", error);
      toast("تعذّر ربط الرسم بحساب «مصاريف الاستيراد» — سيُستخدم الحساب الافتراضي.", "error");
      return null;
    }
  };

  const itemsTab = (
    <div className="ktra-legacy-tab">
      {formData.currency === "ILS" ? (
        <>
          {(formData.conversionMetadata || formData.importLogistics) && (
            <ConversionDetailsSection
              metadata={formData.conversionMetadata}
              importLogistics={formData.importLogistics}
              shippingIncluded={Boolean(formData.shippingIncluded)}
              invoiceShippingCostIls={formData.shippingCost}
              invoiceClearanceId={formData.clearanceId}
            />
          )}
          <NISItemsTable
            items={formData.items || []}
            conversionRate={formData.conversionMetadata?.dealEffectiveRate || 1}
            invoiceTaxAmount={formData.taxAmount || 0}
            localPayments={formData.localPayments || {}}
            taxableBaseIls={ilsMerchandiseBase}
            invoiceVatBaseIls={ilsVatBase}
            conversionMetadata={formData.conversionMetadata}
            additionalFeesTotal={feesTotal}
            isShipmentLinkedImport={isShipmentLinkedImport}
          />
          <NISInvoiceTaxStrip
            taxType={formData.taxType || "percentage"}
            taxRate={formData.taxRate || 0}
            taxAmount={formData.taxAmount || 0}
            taxableBaseIls={ilsMerchandiseBase}
            vatBaseIls={ilsVatBase}
            fees={formData.fees || []}
            defaultFeeAccount={defaultInlineFeeAccount}
            importExpenseAccounts={isInternationalInvoice ? importExpenseAccounts : []}
            onResolveFeeAccount={isInternationalInvoice ? resolveImportFeeAccount : undefined}
            readOnly={effectiveReadOnly}
            onFinancial={handleUpdateFinancial}
            onFeesChange={(fees) => {
              setFormData((prev) => ({ ...prev, fees }));
              markDirty();
            }}
          />
          <NISFinancialSummary
            subtotal={formData.subtotal || 0}
            discountAmount={formData.discountAmount || 0}
            taxAmount={formData.taxAmount || 0}
            taxRate={formData.taxRate || 0}
            shippingCost={0}
            grandTotal={formData.grandTotal || 0}
            localPayments={formData.localPayments || {}}
            taxableBaseIls={ilsMerchandiseBase}
            invoiceVatBaseIls={ilsVatBase}
            hideShippingRow
            fees={formData.fees || []}
            transferCommissionsIls={transferCommissionsIls}
          />
        </>
      ) : (
        <ItemsTableSection
          items={formData.items || []}
          onAddItem={handleAddItem}
          onUpdateItem={handleUpdateItem}
          onRemoveItem={handleRemoveItem}
          onPreviewImage={setPreviewImage}
          supplierId={formData.supplierId}
          readOnly={effectiveReadOnly}
          allDbItems={allDbItems}
          discountAmount={formData.discountAmount}
          taxRate={formData.taxRate || 0}
          taxAmount={formData.taxAmount || 0}
          taxType={formData.taxType || "percentage"}
          shippingCost={formData.shippingCost || 0}
          shippingIncluded={formData.shippingIncluded || false}
          localPayments={formData.localPayments || {}}
          productionDays={formData.dealInfo?.productionDays}
          deliveryDays={formData.dealInfo?.deliveryDays}
          paymentMethod={formData.dealInfo?.paymentMethod}
          shippingMethod={formData.dealInfo?.shippingMethod}
          warrantyDuration={formData.dealInfo?.warrantyDuration}
          totalWeight={formData.totalWeight}
          totalVolume={formData.totalVolume}
          certificates={formData.dealInfo?.certificates}
          shipmentNotes={formData.dealInfo?.shipmentNotes || ""}
          onUpdateFinancial={(field: string, value: any) => {
            const dealInfoFields = [
              "productionDays", "deliveryDays", "paymentMethod",
              "shippingMethod", "warrantyDuration", "certificates",
              "shipmentNotes",
            ];
            const weightVolumeFields = ["totalWeight", "totalVolume"];
            if (dealInfoFields.includes(field)) {
              handleDealInfoUpdate(field, value);
            } else if (weightVolumeFields.includes(field)) {
              handleDealInfoUpdate(field, value);
              handleUpdateFinancial(field, value);
            } else {
              handleUpdateFinancial(field, value);
            }
          }}
          currency={formData.currency}
        />
      )}
    </div>
  );

  const feeEditorState = getPurchaseInvoiceFeeEditorState({
    readOnly,
    viewMode,
    isPosted: Boolean(formData.isPosted),
    isHistorical: Boolean(formData.isHistorical),
  });
  const enterFeeEditMode = () => {
    if (!feeEditorState.canAdd) {
      toast(feeEditorState.message || "لا يمكن تعديل الفاتورة", "info");
      return false;
    }
    if (feeEditorState.requiresEdit) setViewMode(false);
    return true;
  };
  const focusTaxRate = () => {
    if (!enterFeeEditMode()) return;
    window.setTimeout(() => document.querySelector<HTMLInputElement>("[data-purchase-tax-rate='true']")?.focus(), 0);
  };
  const appendFeeLine = (kind: "tax" | "fee") => {
    if (!enterFeeEditMode()) return;
    if (feeAccounts.length === 0) {
      toast("لا توجد حسابات مصروف أو أصل متاحة. أضف الحساب المحاسبي أولاً ثم أعد المحاولة.", "error");
      return;
    }
    const preferred = kind === "tax"
      ? feeAccounts.find((account) => account.code === "1105")
      : feeAccounts.find((account) => account.code === "5307") || feeAccounts.find((account) => account.account_type === "Expense");
    const id = crypto.randomUUID();
    setFormData((prev) => ({
      ...prev,
      fees: [...(prev.fees || []), {
        id,
        description: kind === "tax" ? "ضريبة إضافية" : "رسوم إضافية",
        amount: 0,
        calculationType: "amount",
        calculationValue: 0,
        percentageBasis: "goods",
        expenseAccountId: preferred?.id || null,
        expenseAccountCode: preferred?.code,
        expenseAccountName: preferred?.name,
        capitalizeToInventory: false,
        isTaxable: false,
      }],
    }));
    markDirty();
    console.info("[PurchaseInvoiceFees] Added fee editor line", { kind, invoiceId: formData.id || null });
    window.setTimeout(() => document.querySelector<HTMLInputElement>(`[data-fee-amount='${id}']`)?.focus(), 0);
  };
  const feesTab = (
    <div className="ktra-legacy-tab">
      <div className="mb-3 grid grid-cols-1 gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 sm:grid-cols-3">
        <div><span className="block text-xs text-[var(--color-text-muted)]">إجمالي الفاتورة الأساسي</span><b>{formatMoney(formData.grandTotal || 0)} ₪</b></div>
        <div><span className="block text-xs text-[var(--color-text-muted)]">ضرائب ورسوم إضافية</span><b className="text-amber-700">{formatMoney(feesTotal)} ₪</b></div>
        <div><span className="block text-xs text-[var(--color-text-muted)]">إجمالي المستحق</span><b className="text-emerald-700">{formatMoney(payableTotal)} ₪</b></div>
      </div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold">بنود الضرائب والرسوم الإضافية</h4>
          <p className="text-xs text-[var(--color-text-muted)]">كل بند له حساب واضح؛ ويمكن رسملته على تكلفة المخزون أو تحميله كمصروف.</p>
        </div>
        {feeEditorState.canAdd && (
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className="ktra-toolbtn" onClick={focusTaxRate}>
              <Pencil size={14} /> {feeEditorState.requiresEdit ? "تحرير وضبط ض.ق.م" : "ضبط ض.ق.م الأساسية"}
            </button>
            <button type="button" className="ktra-toolbtn" onClick={() => appendFeeLine("tax")}>
              <Plus size={14} /> {feeEditorState.requiresEdit ? "تحرير وإضافة ضريبة" : "إضافة ضريبة مستقلة"}
            </button>
            <button type="button" className="ktra-toolbtn" onClick={() => appendFeeLine("fee")}>
              <Plus size={14} /> {feeEditorState.requiresEdit ? "تحرير وإضافة رسم" : "إضافة رسم"}
            </button>
          </div>
        )}
      </div>
      <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
        ضريبة القيمة المضافة الأساسية تُحسب من «نسبة الضريبة %» أعلى الفاتورة. استخدم البنود أدناه للرسوم أو الضرائب المستقلة فقط.
      </div>
      {!feeEditorState.canAdd && feeEditorState.message && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <Info size={15} className="shrink-0" /> {feeEditorState.message}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="ktra-input w-full text-xs">
          <thead><tr>
            <th className="p-1 text-start">البيان</th>
            <th className="p-1 text-start">الحساب</th>
            <th className="w-32 p-1 text-center">المبلغ (₪)</th>
            <th className="w-24 p-1 text-center">رسملة</th>
            <th className="w-14 p-1"></th>
          </tr></thead>
          <tbody>
            {(formData.fees || []).map((fee, index) => (
              <tr key={fee.id || index}>
                <td className="p-1"><input className="ktra-input w-full" disabled={effectiveReadOnly} value={fee.description} placeholder="مثال: رسوم فحص أو ضريبة إضافية" onChange={(e) => { const fees = [...(formData.fees || [])]; fees[index] = { ...fee, description: e.target.value }; setFormData((prev) => ({ ...prev, fees })); markDirty(); }} /></td>
                <td className="p-1"><AccountTreeField accounts={allAccounts} value={fee.expenseAccountId || ""} disabled={effectiveReadOnly} purpose={FEE_PURPOSE} title="اختيار حساب الرسم" onChange={(id, account) => { const fees = [...(formData.fees || [])]; fees[index] = { ...fee, expenseAccountId: id, expenseAccountCode: account?.code, expenseAccountName: account?.name ?? undefined }; setFormData((prev) => ({ ...prev, fees })); markDirty(); }} /></td>
                <td className="p-1"><input className="ktra-input w-full text-center" data-fee-amount={fee.id} type="number" min="0" step="0.01" disabled={effectiveReadOnly || fee.calculationType === "percentage"} value={fee.calculationType === "percentage" ? fee.amount : (fee.calculationValue ?? fee.amount)} onChange={(e) => { const value = Number(e.target.value) || 0; const fees = [...(formData.fees || [])]; fees[index] = { ...fee, amount: value, calculationValue: value }; setFormData((prev) => ({ ...prev, fees })); markDirty(); }} /></td>
                <td className="p-1 text-center"><input type="checkbox" disabled={effectiveReadOnly} checked={fee.capitalizeToInventory} onChange={(e) => { const fees = [...(formData.fees || [])]; fees[index] = { ...fee, capitalizeToInventory: e.target.checked }; setFormData((prev) => ({ ...prev, fees })); markDirty(); }} /></td>
                <td className="p-1 text-center">{!effectiveReadOnly && <button type="button" className="ktra-toolbtn" onClick={() => { setFormData((prev) => ({ ...prev, fees: (prev.fees || []).filter((_, i) => i !== index) })); markDirty(); }}><Trash2 size={14} /></button>}</td>
              </tr>
            ))}
            {(formData.fees || []).length === 0 && <tr><td colSpan={5} className="p-6 text-center text-[var(--color-text-muted)]">لا توجد ضرائب أو رسوم إضافية. استخدم «إضافة ضريبة مستقلة» أو «إضافة رسم» عند الحاجة.</td></tr>}
          </tbody>
        </table>
      </div>
      {!viewMode && !effectiveReadOnly && (
        <div className="mt-3 flex justify-end">
          <button type="button" className="ktra-toolbtn" disabled={saving} onClick={() => void handleSave()}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            حفظ الفاتورة والرسوم
          </button>
        </div>
      )}
    </div>
  );

  const installmentsTab = (
    <div className="ktra-legacy-tab">
      <InstallmentsSection
        installments={installments}
        installmentPlanEnabled={installmentPlanEnabled}
        items={formData.items || []}
        discountAmount={formData.discountAmount}
        taxRate={formData.taxRate}
        shippingCost={formData.shippingCost || 0}
        shippingIncluded={formData.shippingIncluded || false}
        localPayments={formData.localPayments || {}}
        onToggleInstallmentPlan={(e) => { handleToggleInstallmentPlan(e); markDirty(); }}
        onAddInstallment={() => { handleAddInstallment(); markDirty(); }}
        onRemoveInstallment={(i) => { handleRemoveInstallment(i); markDirty(); }}
        onUpdateInstallment={(i, f, v) => { handleUpdateInstallment(i, f, v); markDirty(); }}
        readOnly={formData.isHistorical || false}
        currency={formData.currency}
        grandTotalFromForm={formData.currency === "ILS" ? payableTotal : undefined}
        mainVatForExtras={formData.taxAmount || 0}
        conversionMetadata={formData.conversionMetadata}
      />
    </div>
  );

  const dealInfoTab = (
    <div className="ktra-legacy-tab">
      <DealInfoSection
        dealInfo={dealInfo}
        formData={formData}
        onUpdateDealInfo={(f, v) => { handleDealInfoUpdate(f, v); markDirty(); }}
      />
    </div>
  );

  const activityTab = (
    <div className="ktra-legacy-tab">
      {dealActivities.length > 0 ? (
        <DealActivityLog activities={dealActivities} />
      ) : (
        <p className="ktra-hint">لا يوجد سجل نشاطات للصفقة المرتبطة.</p>
      )}
    </div>
  );

  const otherTab = (
    <div className="ktra-other">
      <label className="ktra-field ktra-field--inline">
        <input
          type="checkbox"
          disabled={effectiveReadOnly}
          checked={formData.shippingIncluded || false}
          onChange={(e) => { handleUpdateFinancial("shippingIncluded", e.target.checked); markDirty(); }}
        />
        <span className="ktra-field-label" style={{ flex: "unset" }}>
          الأسعار تشمل الشحن
        </span>
      </label>
      <p className="ktra-hint">
        عملة الفاتورة: {formData.currency === "ILS" ? "شيكل (₪)" : "دولار ($)"}
        {formData.dealId ? ` — مرتبطة بالصفقة ${formData.dealNumber || formData.dealId}` : ""}
      </p>
    </div>
  );

  const isPosted = Boolean(formData.isPosted);
  const canPostDocument = Boolean(formData.id) && !isPosted && !formData.isHistorical;

  // T-ONEPAY (مرآة فاتورة البيع): مدخل واحد لدفع المورد — نقد و/أو شيكات في سند
  // صرف واحد. التوزيع يلزمه فاتورة مرحّلة، فنحفظ ونرحّل ضمن نفس النقرة بتأكيد.
  /* T-INTENT: تسوية المستند من المشتقّة المشتركة مع محرّر البيع — الرقم نفسه
     في الشريط وعرض المستند والطباعة، ولا حسبةَ ثانية تفترق غداً. */
  /* T-AUTOPAID (مرآة البيع): فاتورة الشراء النقدية تُسوّى **بالكامل** تلقائياً
     عند الترحيل (`_auto_settle_cash_purchase` وكنس المرفق)، فمسودّتها تعرض
     دفعتها القادمة حيّةً من أرقام الشاشة: تظهر مع أول بندٍ وسعر وتتحدّث مع كل
     تعديل، بلا كتابةٍ للخادم قبل الحفظ. الصفُّ مشتقٌّ لا مخزَّن. */
  const draftChequesTotal = useMemo(
    () => (formData.cheques || [])
      .filter((c) => c.status === "Draft")
      .reduce((s, c) => s + Number(c.amount || 0), 0),
    [formData.cheques],
  );
  const intentIsAuto =
    !isPosted && !formData.isReturn && formData.paymentType === "cash";
  const autoCashIntent = intentIsAuto
    ? Math.max(payableTotal - (Number(formData.amountPaid) || 0) - draftChequesTotal, 0)
    : 0;
  const settlement = useMemo(() => deriveInvoiceSettlement({
    grandTotal: payableTotal,
    paid: Number(formData.amountPaid) || 0,
    // النقدية: النيّة الفعلية هي التغطية الكاملة القادمة — لا حالة الخادم وحدها.
    pendingIntent: intentIsAuto
      ? autoCashIntent + draftChequesTotal
      : Number(formData.pendingPaymentTotal) || 0,
    isPosted,
  }), [payableTotal, formData.amountPaid, formData.pendingPaymentTotal, isPosted,
       intentIsAuto, autoCashIntent, draftChequesTotal]);
  const supplierRemaining = Math.max(Number(formData.remainingBalance) || 0, 0);

  /* T-APPAY: سلف المورّد المرحّلة غير الموزَّعة — «رصيدٌ لنا عنده» يصلح لتسديد
     هذه الفاتورة ربطاً بلا قيد جديد (مرآة «من رصيد العميل» في البيع). */
  useEffect(() => {
    const supplierId = formData.supplierId;
    if (!supplierId) { setPayAdvances([]); return; }
    let cancelled = false;
    purchaseInvoiceApi.listSupplierPayments(supplierId)
      .then((rows) => {
        if (cancelled) return;
        setPayAdvances(
          (rows || [])
            .filter((r) => r.is_posted)
            .map((r) => ({ id: r.id, unallocated: Number(r.unallocated_amount ?? 0) }))
            .filter((r) => r.unallocated > 0.009),
        );
      })
      .catch(() => { if (!cancelled) setPayAdvances([]); });
    return () => { cancelled = true; };
  }, [formData.supplierId, payAdvancesNonce]);

  /** T-CASHBOX M1 — الصندوق الافتراضي للوحة بسلّم `utils/cashBox`.
   *
   * كان `allAccounts.find(accountMatchesPurpose(a,"cash"))`: أوّل حساب نقدي
   * بترتيب الكود، أي صندوق الشيقل دائماً — بلا نظرٍ إلى إعداد «الصندوق
   * الافتراضي للمشتريات» (كان إعداداً حيّاً لا يقرؤه أحد) ولا إلى عملة
   * الفاتورة. والقيمة كانت تُرسَل، فتبدو اختياراً من المستخدم.
   *
   * و`null` مقصود حين يعجز السلّم: الخادم يحلّه بالسلّم نفسه أو يشرح النقص.
   */
  useEffect(() => {
    if (payCashAccountId !== null) return;
    const pick = pickDefaultCashAccount({
      boxes: cashBoxes,
      currency: formData.currency,
      settingsAccountId: purchaseDefaultCashAccountId,
      userDefaultBoxId: myDefaultBoxId,
    });
    if (pick.accountId) setPayCashAccountId(pick.accountId);
  }, [payCashAccountId, cashBoxes, formData.currency,
      purchaseDefaultCashAccountId, myDefaultBoxId]);

  /** T-PAYFULL2 — صندوق الفاتورة النقدية نفسها (لا صندوق لوحة الدفع).
   *
   * `cash_or_bank_account` كان حقلاً ميّتاً في هذا المحرّر: النموذج يقرؤه في
   * بناء الحمولة، والمُطابِق يملأه من الخادم، ولا **موضع واحد** يكتبه. فعلامة
   * «نقدي» في الرأس كانت طريقاً مسدوداً: المُسلسِل يرفض
   * (`الدفع النقدي يتطلب اختيار حساب صندوق/بنك`) ولا حقل على الشاشة يُصلح
   * الرفض. مرآة `SalesInvoiceEditor` التي تملأه بالسلّم نفسه منذ T-CASHBOX.
   */
  useEffect(() => {
    if (formData.paymentType !== "cash") return;
    if (formData.cashOrBankAccountId) return;
    const pick = pickDefaultCashAccount({
      boxes: cashBoxes,
      currency: formData.currency,
      settingsAccountId: purchaseDefaultCashAccountId,
      userDefaultBoxId: myDefaultBoxId,
    });
    if (pick.accountId) {
      setFormData((prev) => ({ ...prev, cashOrBankAccountId: pick.accountId }));
    }
  }, [formData.paymentType, formData.cashOrBankAccountId, cashBoxes,
      formData.currency, purchaseDefaultCashAccountId, myDefaultBoxId]);

  const paymentInput = useMemo(() => ({
    base: payableTotal,
    paid: Number(formData.amountPaid) || 0,
    isCashDocument: formData.paymentType === "cash",
    cash: payCash,
    cheques: payCheques,
    fromBalance: payFromBalance,
    onAccountVouchers: payAdvances,
  }), [payableTotal, formData.amountPaid, formData.paymentType, payCash, payCheques,
       payFromBalance, payAdvances]);
  const payment = useMemo(() => deriveDocumentPayment(paymentInput), [paymentInput]);

  /** اللوحة تظهر لمن يملك الدفع، على فاتورة شراء لها مورّد وما زال عليها متبقٍّ. */
  const showPayPanel =
    !formData.isReturn
    && canPerm("purchase.payment.create")
    && (isPosted || invoicePermissions.canSaveAndPost)
    && Boolean(formData.supplierId)
    && !(isPosted && supplierRemaining <= 0.009);

  const resetPayInputs = () => {
    setPayCash("");
    setPayCheques([]);
    setPayChequesOpen(false);
    setPayFromBalance("");
  };

  /* ── T-INTENT: نيّة الدفع على المسودة — مرآة محرّر البيع حرفياً ────────── */

  /** شيكات المسودة كما يعيدها الخادم — صفوف النيّة في جدول الدفعات. */
  const intentCheques = useMemo(
    () => (formData.cheques || []).filter((c) => c.status === "Draft"),
    [formData.cheques],
  );
  const intentCash = Number(formData.attachedCashAmount) || 0;
  const intentCashAccountId = formData.attachedCashAccountId ?? null;

  const currentIntentCheques = () => intentCheques.map((c) => ({
    cheque_number: c.cheque_number,
    amount: Number(c.amount).toFixed(2),
    due_date: c.due_date || null,
    bank_name: c.bank_name || "",
  }));

  /**
   * يكتب صورة النيّة **كاملةً** (بدلالة الاستبدال لا الفرق) — مصدرٌ واحد
   * يخدم الحفظ والتعديل والحذف على السواء.
   */
  const writeIntent = async (
    intent: {
      cash: number;
      cashAccountId: number | null;
      cheques: ReturnType<typeof currentIntentCheques>;
    },
    successMsg: string,
    opts?: { saveFirst?: boolean; targetId?: number | string },
  ): Promise<boolean> => {
    /* `targetId` الصريح: من حفظ للتوّ يمرّر المعرّف **بالقيمة** — قراءة
       `formData.id` هنا إغلاقٌ بائت، فكانت «مدفوعة» على فاتورةٍ جديدة تحفظ
       ثم يحفظ هذا ثانيةً: فاتورتان لضغطةٍ واحدة (مرآة عطل جانب البيع).
       و`saveFirst`: المبلغ من الشاشة والنيّة على صفٍّ في القاعدة. */
    let targetId = opts?.targetId ?? formData.id;
    if (!targetId || (opts?.saveFirst && !opts?.targetId)) {
      const saved = await handleSave();
      if (!saved) return false;
      targetId = saved;
    }
    setPaying(true);
    try {
      const dto = await purchaseInvoiceApi.attachIntent(Number(targetId), {
        cash_amount: intent.cash.toFixed(2),
        ...(intent.cash > 0 && intent.cashAccountId
          ? { cash_account_id: intent.cashAccountId }
          : {}),
        cheques: intent.cheques,
      });
      setFormData(mapPurchaseInvoiceDtoToInvoice(dto));
      resetPayInputs();
      setAccMsg(successMsg);
      if (onSave) onSave({ id: String(targetId) });
      return true;
    } catch (e) {
      toast(humanizeThrown(e, "تعذّر حفظ الدفعة على المسودة"), "error");
      return false;
    } finally {
      setPaying(false);
    }
  };

  const saveIntentFromPanel = () => {
    if (!formData.supplierId) { toast("اختر المورد أولاً.", "error"); return; }
    if ((Number(payCash) || 0) > 0 && !payCashAccountId) {
      toast("اختر حساب الصندوق أو البنك للمبلغ النقدي.", "error");
      return;
    }
    if (payment.chequeError) { toast(payment.chequeError, "error"); return; }
    // اللوحة تُضيف إلى النيّة القائمة لا تستبدلها.
    void writeIntent(
      {
        cash: intentCash + (Number(payCash) || 0),
        cashAccountId: payCashAccountId ?? intentCashAccountId,
        cheques: [
          ...currentIntentCheques(),
          ...payCheques.map((row) => ({
            cheque_number: row.cheque_number.trim(),
            amount: (Number(row.amount) || 0).toFixed(2),
            due_date: row.due_date || null,
            bank_name: row.bank_name.trim(),
          })),
        ],
      },
      "حُفِظت الدفعة على المسودة — تتحوّل إلى سند صرف عند الترحيل.",
    );
  };

  /** التعديل = سحب النيّة إلى اللوحة ومسحها من المستند فيعيد المستخدم بناءها. */
  const editIntent = () => {
    setPayCash(intentCash > 0 ? intentCash.toFixed(2) : "");
    if (intentCashAccountId) setPayCashAccountId(intentCashAccountId);
    setPayCheques(intentCheques.map((c, i) => ({
      key: `intent-${c.id}-${i}`,
      cheque_number: c.cheque_number,
      bank_name: c.bank_name || "",
      due_date: c.due_date || "",
      amount: String(c.amount),
    })));
    setPayChequesOpen(intentCheques.length > 0);
    void writeIntent({ cash: 0, cashAccountId: null, cheques: [] }, "عدّل الدفعة ثم احفظها.");
    focusPayPanel();
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
   * نداء واحد إلى `pay/`: على المسودة تُحفظ الفاتورة أولاً ثم تُرحَّل ويُسجَّل
   * سند الصرف داخل معاملة الخادم نفسها (`post_invoice`)، وعلى المرحّلة يُسجَّل
   * السند فوراً. الكلّ أو لا شيء — لا فاتورةٌ مرحّلة بسندٍ نصفِ مولود.
   */
  const submitPayment = async (opts?: { saveFirst?: boolean }) => {
    if (!formData.supplierId) { toast("اختر المورد أولاً.", "error"); return; }
    if (!payment.canSubmit) return;
    if ((Number(payCash) || 0) > 0 && !payCashAccountId) {
      toast("اختر حساب الصندوق أو البنك للمبلغ النقدي.", "error");
      return;
    }
    setPaying(true);
    try {
      /* `saveFirst`: الدخول من «حفظ وترحيل» — الاسم يَعِد بحفظ ما على الشاشة،
         و`pay/` وحده يدفع ويرحّل ولا يحفظ تعديلات البنود. حفظةٌ واحدة هنا
         تخدم المسارين: المعرَّف يعود منها فلا يُقرأ من حالةٍ لم تُحدَّث بعد. */
      let targetId = formData.id;
      if (!targetId || opts?.saveFirst) {
        const saved = await handleSave();
        if (!saved) return;
        targetId = saved;
      }
      /* T-PAYFULL2: هذا النداء يرحّل الفاتورة أيضاً حين تكون مسودة، فيلزمه سؤال
         «الاستلام مع الترحيل» نفسه — وإلّا قرّر الإعدادُ العام وحده مصير المخزن
         لأن المستخدم دفع بدل أن يرحّل. وبعد الحفظ لا قبله: إلغاءُ السؤال يترك
         المسودة محفوظةً كما يفعل مسار الترحيل المجرّد. */
      let receiveOnPost: boolean | undefined;
      if (!isPosted) {
        const answer = await askReceiveChoice();
        if (answer === null) return;
        receiveOnPost = answer;
      }
      const result = await purchaseInvoiceApi.pay(Number(targetId), {
        cash: payCash || undefined,
        cash_account_id: payCashAccountId,
        cheques: payCheques.map((c) => ({
          cheque_number: c.cheque_number,
          amount: c.amount,
          bank_name: c.bank_name || undefined,
          due_date: c.due_date || null,
        })),
        from_on_account: payment.onAccountPlan.map((row) => ({
          payment_id: row.payment_id,
          amount: String(row.amount),
        })),
        post_invoice: !isPosted,
        ...(receiveOnPost !== undefined ? { receive_on_post: receiveOnPost } : {}),
      });
      clientLogger.info("purchase_invoice.paid", {
        invoiceId: targetId, paymentId: result.payment_id,
      });
      resetPayInputs();
      setPayAdvancesNonce((n) => n + 1);
      setAccMsg("تم تسجيل الدفعة وترحيل سند الصرف، وخُصِم من متبقي الفاتورة.");
      await reloadInvoice(targetId);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setPaying(false);
    }
  };

  const focusPayPanel = () => {
    if (!formData.supplierId) { toast("اختر المورد أولاً.", "error"); return; }
    if (isPosted && supplierRemaining <= 0.009) {
      toast("الفاتورة مسدَّدة بالكامل — لا متبقٍّ.", "info");
      return;
    }
    payPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    payCashInputRef.current?.focus();
  };

  /**
   * «مدفوعة» — الحالة الغالبة أن تُدفع الفاتورة كاملةً، وكتابةُ المبلغ يدوياً
   * كانت ضريبةً عليها.
   *
   * T-PAYFULL3 (قرار المالك، عدلَ عن «تعبئة فقط»): على **المسودة** الزرّ
   * **يسجّل دفعةً غير مرحّلة** بكامل المتبقّي — نيّةٌ تُحفظ على الفاتورة وتظهر
   * في جدول دفعاتها موسومةً، وتتجسّد سند صرفٍ واحداً عند الترحيل
   * (`settle_attached_purchase_intent`). لا قيدَ يُكتب الآن: مالٌ سجّله
   * المستخدم لا مالٌ تحرّك في الدفاتر — وهذا بالضبط ما تعنيه «غير مرحّلة».
   *
   * وعلى **المرحّلة** لا وجود لهذه الحالة أصلاً (سندٌ أو لا شيء)، فيبقى الزرّ
   * تعبئةً والتنفيذ بـ«تسجيل دفعة».
   */
  const fillPayFull = async () => {
   /* T-PAYFULL5: مُعالِج نقرةٍ غير متزامن بلا مصيدة = فشلٌ صامت — الاستثناء
      يصير «رفضاً غير معالَج» في الطرفية ولا يرى المستخدم شيئاً. */
   /* حارسُ تداخُل — الضغطة أثناء حفظٍ أو دفعٍ جارٍ تُهمَل بهدوء. */
   if (saving || paying) return;
   try {
    clientLogger.info("purchase_invoice.pay_full_clicked", {
      invoiceId: formData.id, isPosted, base: payableTotal,
    });
    if (!formData.supplierId) { toast("اختر المورد أولاً.", "error"); return; }

    /* المرحّلة: لا وجود لدفعةٍ «غير مرحّلة» عليها أصلاً — ما بعد الترحيل سندٌ
       أو لا شيء. فيبقى الزرّ هنا تعبئةً، والتنفيذ بـ«تسجيل دفعة». */
    if (isPosted) {
      const remaining = payment.remainingBefore;
      if (remaining <= 0.009) {
        toast("الفاتورة مسدَّدة بالكامل — لا متبقٍّ.", "info");
        return;
      }
      setPayCash(remaining.toFixed(2));
      payPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      payCashInputRef.current?.focus();
      toast(
        `عُبِّئ المتبقّي ${formatMoney(remaining)} — اضغط «تسجيل دفعة» لتنفيذها.`,
        "success",
      );
      return;
    }
    if (payableTotal <= 0.009) {
      toast("لا مبلغ بعد — أضف بنود الفاتورة ثم اضغط «مدفوعة».", "info");
      return;
    }

    /* T-PAYFULL4 — المبلغ يُشتقّ من **رقم الخادم** بعد الحفظ لا من رقم الشاشة.
     *
     * نقطة تعليق النيّة ترفض ما يتجاوز إجمالي الفاتورة **المخزَّن** (تعيد حسابه
     * من البنود)، فكان يكفي فارقُ قرشٍ بين الحسبتين ليردّ الطلب ويبدو الزرّ
     * كأنه لم يعمل. مرآة جانب البيع. */
    const savedId = await handleSave();
    if (!savedId) return; // `handleSave` عرض السبب
    const dto = lastSavedRef.current;
    if (!dto) { toast("تعذّرت قراءة الفاتورة بعد الحفظ.", "error"); return; }
    const grand = Number(dto.payable_total ?? dto.grand_total ?? 0);
    const paidNow = Number(dto.amount_paid ?? 0);
    const draftCheques = (dto.cheques || []).filter((c) => c.status === "Draft");
    const chequesTotal = draftCheques.reduce((sum, c) => sum + Number(c.amount || 0), 0);
    const target = Math.max(grand - paidNow - chequesTotal, 0);
    if (target <= 0.009) {
      toast("الفاتورة مغطّاة بالكامل — لا متبقٍّ.", "info");
      return;
    }
    if (Math.abs(target - Number(dto.attached_cash_amount || 0)) <= 0.009) {
      toast("المسودة عليها دفعة تغطّي إجماليها — لا متبقٍّ.", "info");
      return;
    }
    /* T-PAYFULL7 — سلّم صندوقٍ حتميّ (مرآة البيع): صندوق اللوحة يُملأ بـeffect
       متأخّرٍ عن الشاشة، فضغطةٌ سريعة كانت تُرفض «لا صندوق» وصندوقُ الفاتورة
       ظاهرٌ في رأسها. المصادر تُقرأ مباشرةً لا عبر حالةٍ وسيطة. */
    const cashAccount =
      payCashAccountId
      ?? (formData.paymentType === "cash" ? formData.cashOrBankAccountId ?? null : null)
      ?? dto.attached_cash_account
      ?? purchaseDefaultCashAccountId
      ?? pickDefaultCashAccount({
        boxes: cashBoxes,
        currency: formData.currency,
        userDefaultBoxId: myDefaultBoxId,
      }).accountId;
    if (!cashAccount) {
      toast("لا صندوق افتراضي — اختر حساب الصندوق أو البنك في لوحة الدفع.", "error");
      focusPayPanel();
      return;
    }
    await writeIntent(
      {
        cash: target,
        cashAccountId: cashAccount,
        cheques: draftCheques.map((c) => ({
          cheque_number: c.cheque_number,
          amount: Number(c.amount).toFixed(2),
          due_date: c.due_date || null,
          bank_name: c.bank_name || "",
        })),
      },
      `سُجِّلت دفعة ${formatMoney(target)} غير مرحّلة — تتحوّل إلى سند صرف عند ترحيل الفاتورة.`,
      // المعرّف بالقيمة من الحفظ أعلاه — لا من حالةٍ لم تصل بعد.
      { targetId: savedId },
    );
    /* والدليل حيث ينظر المستخدم: صفُّ الدفعة في جدول دفعات المستند. */
    paymentsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
   } catch (e) {
    const m = humanizeThrown(e, "تعذّر تسجيل الدفعة");
    clientLogger.error("purchase_invoice.pay_full_failed", { message: m });
    toast(m, "error");
   }
  };

  /* T-PAYFULL: الوصول من زرّ «مدفوعة» في قائمة الفواتير. مرّةً واحدة وبحارس
     `ref` — لا عند كل إعادة رسم، ولا بعد أن يعدّل المستخدم الخانة بنفسه.
     الانتظار حتى يصل الصندوق الافتراضي: بلا حسابٍ تكون اللوحة معبّأة ومقفلة. */
  const payFullAppliedRef = useRef(false);
  useEffect(() => {
    if (!autoFillPayFull || payFullAppliedRef.current) return;
    if (!formData.id || !formData.supplierId || !showPayPanel) return;
    if (!payCashAccountId) return;
    payFullAppliedRef.current = true;
    void fillPayFull();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFillPayFull, formData.id, formData.supplierId, showPayPanel, payCashAccountId]);

  /* T-PCTX: تبويبات السياق تُعرض في **وضع العرض** أيضاً — وهو الوضع الذي تُفتح
     به الفاتورة المرحّلة، أي بالضبط الحالة التي يُسأل فيها «ماذا فعلت هذه
     الفاتورة بالمخزن وبحساب المورّد؟». كان `tabs={viewMode ? [] : [...]}`
     يُسقط التبويبات كلَّها هناك، فيصير كلّ ما نضيفه إلى المحرّر غير قابل
     للوصول على الفاتورة النهائية. */
  const contextTabs = (formData.id && Number(formData.id) > 0) ? [
    {
      key: "stock_impact",
      label: "حركة المخزون",
      content: (
        <InvoiceStockTab
          invoiceId={Number(formData.id)}
          api={purchaseInvoiceContextApi}
          side="supplier"
        />
      ),
    },
    {
      key: "supplier_ledger",
      label: "حساب المورّد",
      content: (
        <InvoicePartnerLedgerTab
          invoiceId={Number(formData.id)}
          api={purchaseInvoiceContextApi}
          side="supplier"
        />
      ),
    },
    {
      key: "attachments",
      label: "المرفقات",
      content: (
        <InvoiceAttachmentsTab
          invoiceId={Number(formData.id)}
          api={purchaseInvoiceContextApi}
          readOnly={readOnly}
        />
      ),
    },
  ] : [];

  /* T-INTENT: جدول دفعات الفاتورة — نفس مكوّن البيع بمفردات المورّد، ويظهر في
     وضعَي التحرير والعرض كي يرى صاحبُ المسودة دفعتَه فور تسجيلها. */
  const paymentsSection = formData.isReturn ? null : (
    <InvoicePaymentsSection
      sectionRef={paymentsSectionRef}
      side="supplier"
      posted={(formData.paymentDetails || []).map((p) => ({
        id: p.id,
        payment_date: p.paymentDate,
        allocated_amount: p.amount,
        is_posted: p.isPosted,
        journal: p.journalId ?? null,
      }))}
      intentCash={intentIsAuto ? autoCashIntent : intentCash}
      intentAuto={intentIsAuto}
      intentCashAccountLabel={(() => {
        // التلقائية تُصرف من صندوق رأس الفاتورة؛ وإلا فمن حساب النيّة المحفوظة.
        const accId = intentIsAuto && formData.cashOrBankAccountId
          ? Number(formData.cashOrBankAccountId)
          : intentCashAccountId;
        return accId
          ? allAccounts.find((a) => Number(a.id) === accId)?.name || undefined
          : undefined;
      })()}
      intentCheques={intentCheques}
      settlement={settlement}
      paid={Number(formData.amountPaid) || 0}
      editable={!isPosted && canPerm("purchase.payment.create")}
      busy={paying}
      onAddPayment={focusPayPanel}
      onEditIntent={editIntent}
      onRemoveIntentCash={removeIntentCash}
      onRemoveIntentCheque={removeIntentCheque}
      onOpenVoucher={(paymentId) => {
        const path = entityPathForReference("SUPPLIER_PAYMENT", paymentId);
        if (path) openInNewTab(path);
      }}
    />
  );

  const payPanel = !showPayPanel ? null : (
    <DocumentPaymentPanel
      side="supplier"
      onSaveIntent={saveIntentFromPanel}
      derived={payment}
      input={paymentInput}
      isPosted={isPosted}
      busy={paying}
      panelRef={payPanelRef}
      cashInputRef={payCashInputRef}
      chequesOpen={payChequesOpen}
      onToggleCheques={() => setPayChequesOpen((v) => !v)}
      onCashChange={setPayCash}
      onFromBalanceChange={setPayFromBalance}
      onAddCheque={() => {
        setPayChequesOpen(true);
        setPayCheques((rows) => [...rows, {
          key: `chq-${rows.length}-${rows.length ? rows[rows.length - 1].key : "0"}`,
          cheque_number: "", bank_name: "", due_date: "", amount: "",
        }]);
      }}
      onPatchCheque={(key, patch) =>
        setPayCheques((rows) => rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
      }
      onRemoveCheque={(key) => setPayCheques((rows) => rows.filter((r) => r.key !== key))}
      onFillCashShortfall={() =>
        setPayCash(((Number(payCash) || 0) + payment.cashShortfall).toFixed(2))
      }
      onFillFull={() => setPayCash(payment.remainingBefore.toFixed(2))}
      // T-INTENT: المخرج الثاني من حارس الفاتورة النقدية — كان جانب البيع وحده
      // يمرّره، فيقف مشترٍ لا يملك تغطية الفاتورة كاملةً أمام طريق مسدود لا
      // مخرج منه إلا «أكمل المبلغ».
      onMakeCredit={() => {
        setFormData((prev) => ({ ...prev, paymentType: "credit" }));
        dirtyRef.current = true;
        toast("صارت الفاتورة آجلة على ذمم المورّد — احفظ ثم أكمل الدفع.", "info");
      }}
      onSubmit={() => void submitPayment()}
      cashAccountField={(
        <AccountTreeField
          className="ktra-input"
          accounts={allAccounts}
          value={payCashAccountId ?? ""}
          purpose="cash"
          disabled={paying}
          allowClear={false}
          onChange={(id) => setPayCashAccountId(id ?? null)}
          placeholder="الصندوق / البنك"
          title="حساب الصندوق أو البنك للدفع"
        />
      )}
    />
  );

  /* T-PSIMPL: رقم المسودّة التالي — قراءةٌ واحدة عند فتح فاتورة جديدة. */
  useEffect(() => {
    if (formData.id) return;
    let cancelled = false;
    purchaseInvoiceApi.nextNumber()
      .then((n) => { if (!cancelled) setNextNumberPreview(n); })
      .catch(() => { if (!cancelled) setNextNumberPreview(""); });
    return () => { cancelled = true; };
  }, [formData.id]);

  /** T-PSIMPL: ينسخ الفاتورة إلى مسودّة جديدة ويفتحها — بلا ترحيلٍ ولا استلام. */
  const handleDuplicate = async () => {
    if (!formData.id) return;
    setDuplicating(true);
    try {
      const clone = await purchaseInvoiceApi.duplicate(Number(formData.id));
      toast(`أُنشئت مسودّة جديدة برقم ${clone.invoice_number}.`, "success");
      clientLogger.info("purchase_invoice.duplicated", {
        sourceId: formData.id, cloneId: clone.id,
      });
      dirtyRef.current = false;
      await reloadInvoice(clone.id);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setDuplicating(false);
    }
  };

  const handleSaveAndPost = async () => {
    clientLogger.info("invoice.save_and_post_requested", {
      invoiceType: "purchase",
      existingInvoice: Boolean(formData.id),
    });
    /* T-PAYFULL2 — اللوحة معبّأة ⇒ الزرّ الأساسي يسجّل الدفعة معها.
     *
     * كان «حفظ وترحيل» يحفظ ويرحّل ويترك المبلغ المكتوب في الخانة بلا مصير:
     * يضغط المالك «مدفوعة» ثم الزرّ الأساسي، فتُرحَّل الفاتورة **غير مدفوعة**
     * والرقم يبقى معلّقاً في شاشةٍ تبدو كأنها نفّذته. زرّان متجاوران أحدهما
     * يبتلع عمل الآخر.
     *
     * لا مسار ثانٍ ولا حارس مكرَّر: `pay/` يحمل `post_invoice` أصلاً، فنداءٌ
     * واحد ذرّي يحفظ ويرحّل ويُخرج سند الصرف — أو لا شيء.
     */
    if (!isPosted && payment.canSubmit) {
      await submitPayment({ saveFirst: true });
      return;
    }
    const savedId = await handleSave();
    if (!savedId || !(await handlePost(savedId))) return;
    clientLogger.info("invoice.save_and_post_completed", {
      invoiceType: "purchase",
      invoiceId: savedId,
    });
  };

  // فاتورة محلية مرحّلة لم تُستلَم بضاعتها كلها ⇒ يظهر مسارا الاستلام.
  const canReceiveGoods =
    Boolean(formData.id)
    && isPosted
    && !formData.isReturn
    && formData.invoiceType !== "international"
    && !formData.shipment
    && !formData.dealId
    && !formData.clearanceId
    && formData.receiptStatus !== "received";

  const toolbarActions: KitToolbarAction[] = [
    ...(invoicePermissions.canSave ? [{ key: "save", label: saving ? "...تخزين" : "تخزين (F12)", icon: saving ? <Loader2 className="animate-spin" /> : <Save />, onClick: !saving && !isPosted ? () => { handleSave(); dirtyRef.current = false; } : undefined, disabled: saving || isPosted } as KitToolbarAction] : []),
    ...(invoicePermissions.canSaveAndPost ? [{
      key: "save-and-post",
      label: saving || posting ? "...حفظ وترحيل" : "حفظ وترحيل",
      icon: saving || posting ? <Loader2 className="animate-spin" /> : <CheckCircle2 />,
      onClick: !saving && !posting && !isPosted && !formData.isHistorical
        ? () => void handleSaveAndPost()
        : undefined,
      disabled: saving || posting || isPosted || Boolean(formData.isHistorical),
      separatorBefore: true,
    } as KitToolbarAction] : []),
    ...(viewMode && !formData.isHistorical && invoicePermissions.canSave ? [{
      key: "edit",
      label: "تحرير",
      icon: <Pencil />,
      // مرحّلة: التعديل ممنوع محاسبياً حتى التراجع عن الترحيل — نُبقي الزر ظاهراً
      // لاكتشافه، ونوجّه المستخدم بدل إخفائه (المالك: «كبسة تحرير اختفت»).
      onClick: () => {
        if (isPosted) {
          toast("الفاتورة مرحّلة — اضغط «تراجع عن الترحيل» أولاً لتعديلها.", "info");
          return;
        }
        setViewMode(false);
      },
      separatorBefore: true,
    } as KitToolbarAction] : []),
    ...(canPerm("purchase.invoice.create")
      ? [{ key: "new", label: "جديدة", icon: <Plus />, onClick: guardedNew, separatorBefore: true } as KitToolbarAction]
      : []),
    // T-PSIMPL: «نسخ» — مرآة نظيرتها في البيع. فواتير المورّد الواحد تتكرّر
    // شهرياً، وكانت تُعاد كتابتها بندًا بندًا.
    ...(canPerm("purchase.invoice.create") && formData.id ? [{
      key: "duplicate",
      label: duplicating ? "...نسخ" : "نسخ",
      icon: duplicating ? <Loader2 className="animate-spin" /> : <Copy />,
      onClick: duplicating ? undefined : () => void handleDuplicate(),
      disabled: duplicating,
    } as KitToolbarAction] : []),
    ...(invoicePermissions.canPost ? [{
      key: "post",
      label: posting ? "...ترحيل" : "ترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Send />,
      onClick: canPostDocument && !posting ? () => void handlePost() : undefined,
      disabled: !canPostDocument || posting,
      separatorBefore: true,
    } as KitToolbarAction] : []),
    ...(!readOnly && formData.shipment && formData.id && formData.currency === "ILS" ? [{
      key: "recalculate",
      label: recalcBusy ? "..." : "إعادة حساب التكلفة",
      icon: recalcBusy ? <Loader2 className="animate-spin" /> : <RefreshCw />,
      onClick: formData.isPosted ? undefined : () => void handleRecalculateLanded(),
      disabled: recalcBusy || formData.isPosted,
      separatorBefore: true,
    } as KitToolbarAction] : []),
    // T-PERM: «تراجع عن الترحيل» يظهر فقط لمن يملك الصلاحية (الخادم يفرضها أيضاً).
    ...(canPerm("purchase.invoice.unpost") ? [{
      key: "unpost",
      label: posting ? "...تراجع" : "تراجع عن الترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Undo2 />,
      onClick: isPosted && !posting ? () => void handleUnpost() : undefined,
      disabled: !isPosted || posting,
    } as KitToolbarAction] : []),
    ...(canPerm("purchase.payment.create") && (isPosted || invoicePermissions.canSaveAndPost) ? [{
      // T-APPAY: زرٌّ واحد باسمٍ واحد على الجانبين — «تسجيل دفعة» — يُنزِل
      // المستخدم إلى اللوحة داخل المستند بدل نافذةٍ تُلزمه بالترحيل أوّلاً.
      key: "voucher",
      label: isPosted && supplierRemaining <= 0 ? "مسدَّدة" : "تسجيل دفعة",
      icon: <Banknote />,
      onClick: !(isPosted && supplierRemaining <= 0) ? () => focusPayPanel() : undefined,
      disabled: isPosted && supplierRemaining <= 0,
      separatorBefore: true,
    } as KitToolbarAction] : []),
    // T-PAYFULL: الطريق القصير بجوار الطريق المفصَّل — «مدفوعة» تعبّئ المتبقّي
    // كاملاً، و«تسجيل دفعة» تُبقي الجزئي والشيكات على حالهما.
    ...(canPerm("purchase.payment.create") && (isPosted || invoicePermissions.canSaveAndPost) ? [{
      key: "pay-full",
      label: isPosted && supplierRemaining <= 0 ? "مسدَّدة" : "مدفوعة",
      icon: <Wallet />,
      onClick: !(isPosted && supplierRemaining <= 0) ? () => void fillPayFull() : undefined,
      disabled: isPosted && supplierRemaining <= 0,
    } as KitToolbarAction] : []),
    // الاستلام: نافذة سريعة تُنشئ إرسالية بالبنود المؤشَّرة، أو المحرّر الكامل
    // في شاشة الإرساليات بالفاتورة نفسها مربوطةً مسبقاً.
    ...(canReceiveGoods ? [{
      key: "receive",
      label: "استلام",
      icon: <PackageCheck />,
      onClick: () => setShowReceive(true),
      separatorBefore: true,
    } as KitToolbarAction] : []),
    ...(canReceiveGoods ? [{
      key: "new-receipt",
      label: "إرسالية جديدة",
      icon: <Truck />,
      onClick: () => openInNewTab(`/purchase-receipts/new?invoice=${formData.id}`),
    } as KitToolbarAction] : []),
    { key: "print", label: "طباعة (F2)", icon: <Printer />, onClick: () => setShowPrintView(true), separatorBefore: true },
    // DOC-SHARE: المشاركة تلزمها فاتورة محفوظة — الرابط يشير إلى صفٍّ في القاعدة.
    // وجمهور هذه الصفحة **المورّد**، فصلاحيتها `purchase.document.share` لا
    // صلاحية المبيعات: الخادم يفرضها، وهذا الزرّ يقود إليها لا يقرّرها.
    {
      key: "share",
      label: "مشاركة",
      icon: <Share2 />,
      disabled: !formData.id,
      onClick: () => setShowShareModal(true),
    },
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: guardedCancel, danger: true, separatorBefore: true },
  ];

  const saveErrorBanner = saveError ? (
    <div className="ktra-banner ktra-banner--err" role="alert" data-testid="save-error">
      <AlertCircle className="h-4 w-4 shrink-0" />
      {/* `message` يحمل أسطر الحقول مُسمّاة أصلاً (عبر `humanizeDrfError`)، وما
          له حقل مرئي يُعرض بجانبه كذلك عبر `fld`. تكرارها هنا بلا تسمية كان
          يُري المستخدم السطر مرتين، إحداهما بلا اسم حقل. */}
      <span>{saveError.message}</span>
    </div>
  ) : null;

  const accBanner = (accErr || accMsg) ? (
    <div className={`ktra-banner ${accErr ? "ktra-banner--err" : "ktra-banner--ok"}`}>
      {accErr ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{accErr || accMsg}</span>
    </div>
  ) : null;

  /* ISSUE #120: الحفظ المحلي فشل فعلاً (حصّة ممتلئة، تصفّح خاص…) — لافتةٌ
     لاصقة تطلب حفظاً يدوياً بدل الانتظار الصامت حتى تحاول المغادرة. الصمتُ
     عن فشلٍ نعرفه أسوأُ من التحذير (issue #109 §١٠)، فهذه تظهر فوراً لا عند
     المغادرة وحدها — الحارس المقلوب أعلاه (`draftSaveFailed`) يعترض المغادرة
     أيضاً في هذه الحالة، لكن هذه اللافتة هي ما يراه المستخدم وهو لا يزال هنا. */
  const draftSaveFailedBanner = draftSaveFailed && !effectiveReadOnly ? (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="draft-save-failed-banner"
      className="sticky top-0 z-40 flex items-center gap-2 border-b border-red-200 bg-red-100 px-4 py-2 text-sm font-medium text-red-800"
    >
      <AlertCircle className="h-4 w-4 shrink-0" />
      <span>تعذّر حفظ نسخة محلية من هذا المستند — اضغط «حفظ» يدوياً كي لا يضيع عملك.</span>
    </div>
  ) : null;

  /* ISSUE #118: شريط الاستعادة التلقائية — بلا لافتة تسأل. المحتوى مُطبَّقٌ
     على النموذج فعلاً (`onRestoreDraft`) قبل أن يصل هذا الشريط أصلاً؛ هو
     إخبارٌ لا سؤال، ومعه «تراجع» وحده. */
  const draftRestoreBanner = draftBanner ? (
    <div
      className="ktra-banner ktra-banner--warn"
      role="status"
      data-testid="draft-restored-banner"
    >
      <Info className="h-4 w-4 shrink-0" />
      <span>
        {draftBanner.eligibility === "restore" &&
          `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "stale" &&
          /* issue #119 §٩: الختمان معاً — متى عُدِّل المستند فعلياً ومتى حُفظت المسودّة محلياً — كي يقرّر المستخدم بمعلومتين لا واحدة. */
          `تغيّر المستند بعد مسودتك (عُدِّل ${formatTimeValue(formData.updatedAt)}، ومسودتُك ${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "posted" &&
          `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(draftBanner.updatedAt)}) لهذا المستند المرحَّل — للاطّلاع فقط.`}
      </span>
      {draftBanner.eligibility === "restore" && (
        <button
          type="button"
          className="ktra-toolbtn"
          onClick={handleUndoDraft}
          data-testid="draft-restored-undo"
        >
          <Undo2 className="h-4 w-4" />
          تراجع
        </button>
      )}
      {draftBanner.eligibility === "stale" && (
        <>
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={() => onRestoreDraft(draftBanner.payload)}
            data-testid="draft-stale-preview"
          >
            استعرض مسودتي
          </button>
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={() => void discardDraft()}
            data-testid="draft-stale-discard"
          >
            تجاهلها
          </button>
        </>
      )}
    </div>
  ) : null;

  /* شريط اليتامى (issue #119 §٧): مسودّات مستندٍ جديد أخرى لنفس النوع تُركت
     في تبويبات أخرى — تاريخ كلٍّ وسطر محتواها الأوّل كي تُميَّز، بلا استعادة
     (الاستعادة محصورة بمسودّة هذا التبويب/المستند نفسه). */
  const orphanDraftsBanner = orphanDrafts.length > 0 && !orphanBarDismissed ? (
    <div
      className="ktra-banner"
      role="status"
      data-testid="orphan-drafts-banner"
    >
      <Info className="h-4 w-4 shrink-0" />
      <div className="flex flex-col gap-1">
        <span>{orphanDraftsBannerText(orphanDrafts.length)}</span>
        <ul className="list-disc pr-4 text-xs">
          {orphanDrafts.map((o) => (
            <li key={o.key}>
              {formatTimeValue(o.updatedAt)} — {o.previewLine || "—"}
            </li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        className="ktra-toolbtn"
        onClick={() => setOrphanBarDismissed(true)}
        data-testid="orphan-drafts-dismiss"
      >
        <X className="h-4 w-4" />
        إخفاء
      </button>
    </div>
  ) : null;

  /* ───────────── العرض المستندي (شراء محلية / دولية) ─────────────
     يشترك المساران في هذا النموذج، فالعرض واحد ويتبدّل عنوانه ورسومه حسب النوع. */
  const invCurrency = formData.currency || "ILS";
  const invMoney = (n: number) => `${fmt(n)} ${invCurrency}`;
  const invItems = (formData.items || []).filter((i) => (i.name || "").trim() || i.itemId);
  const invFees = (formData.fees || []).filter((f) => Number(f.amount) > 0);

  const invoiceDocumentView = (
    <KitDocumentView<InvoiceItem>
      title={
        formData.isReturn
          ? "مرتجع شراء (إرجاع للمورد)"
          : isInternationalInvoice
            ? "فاتورة شراء دولية"
            : "فاتورة شراء"
      }
      subtitle={isInternationalInvoice ? "INTERNATIONAL PURCHASE INVOICE" : "PURCHASE INVOICE"}
      documentNumber={formData.invoiceNumber || (formData.id ? `#${formData.id}` : "مسودة")}
      status={
        formData.isPosted
          ? { label: "مرحّلة", tone: "ok" }
          : { label: "مسودة", tone: "warn" }
      }
      metrics={[
        { label: "إجمالي المستحق", value: invMoney(payableTotal), tone: "info" },
        { label: "المدفوع المرحّل", value: invMoney(Number(formData.amountPaid) || 0), tone: "ok" },
        ...(settlement.pendingIntent > 0.009
          ? [{
            label: "دفعة غير مرحّلة",
            value: invMoney(settlement.pendingIntent),
            tone: "warn" as const,
          }]
          : []),
        // T-RECVIS: «المتبقي» صار يعني شيئين على شاشةٍ واحدة منذ ظهور باقي
        // الاستلام — فالمالي يقول «للدفع» والكمّي يقول «الاستلام».
        { label: "المتبقي للدفع", value: invMoney(settlement.remainingAfterIntent), tone: "warn" },
        {
          label: "حالة الدفع",
          value: settlement.intentCoversAll
            ? "مدفوعة — غير مرحّلة"
            : (formData.paymentStatusDisplay || "غير مدفوعة"),
        },
        ...(showReceiptColumns ? [
          {
            label: `الاستلام — ${formData.receiptStatusDisplay || "غير مستلمة"}`,
            value: receiptSummaryText,
            tone: (receiptProgress && receiptProgress.remaining > 0
              ? "warn" : "ok") as "warn" | "ok",
          },
        ] : []),
      ]}
      parties={[
        {
          title: "المورد",
          fields: [
            { label: "الاسم", value: formData.supplierName || "—" },
            ...(formData.supplierInvoiceNumber
              ? [{ label: "رقم فاتورة المورد", value: formData.supplierInvoiceNumber }]
              : []),
          ],
        },
      ]}
      meta={[
        { label: "تاريخ الفاتورة", value: formData.invoiceDate || "—" },
        { label: "العملة", value: invCurrency },
        ...(formData.exchangeRate
          ? [{ label: "سعر الصرف", value: String(formData.exchangeRate) }]
          : []),
        ...(formData.journalId ? [{ label: "قيد اليومية", value: `#${formData.journalId}` }] : []),
      ]}
      columns={[
        {
          key: "name",
          header: "المنتج",
          render: (r) => (
            <div>
              <span className="font-semibold">{r.name || "—"}</span>
              {r.specifications && (
                <span className="block text-[11px] text-[var(--color-text-muted)]">{r.specifications}</span>
              )}
            </div>
          ),
        },
        { key: "qty", header: "الكمية", width: "80px", align: "center", numeric: true, render: (r) => formatQuantity(r.quantity) },
        // T-RECVIS: وضع العرض هو ما تفتح عليه الفاتورة افتراضياً — فالعمودان
        // هنا لا في شبكة التحرير وحدها، وإلا بقي الباقي مخفيّاً عن القارئ.
        ...(showReceiptColumns
          ? [
              {
                key: "receivedQty", header: "مستلَم", width: "90px",
                align: "center" as const, numeric: true,
                render: (r: InvoiceItem) => formatQuantity(r.receivedQuantity || 0),
              },
              {
                key: "remainingQty", header: "باقي الاستلام", width: "110px",
                align: "center" as const, numeric: true, render: remainingCell,
              },
            ]
          : []),
        { key: "price", header: "سعر الوحدة", width: "110px", align: "left", numeric: true, render: (r) => fmt(r.unitPrice) },
        { key: "total", header: "الإجمالي", width: "120px", align: "left", numeric: true, render: (r) => <b>{fmt(r.totalPrice)}</b> },
        ...(isInternationalInvoice
          ? [
              {
                key: "landed",
                header: "التكلفة النهائية/وحدة (₪)",
                width: "140px",
                align: "left" as const,
                numeric: true,
                render: (r: InvoiceItem) => (r.landedUnitPriceIls ? fmt(r.landedUnitPriceIls) : "—"),
              },
            ]
          : []),
      ]}
      rows={invItems}
      rowKey={(r, i) => r.id || i}
      emptyRowsHint="لا توجد بنود في الفاتورة"
      /* ملخّص التكاليف كامل داخل المستند (يُرفع لأعلى بدل دوك سفلي عالق مع فراغ
         فوقه — طلب المالك «ليش ما ترفعو فوق»). نفس تفصيل الدوك تماماً. */
      totals={
        formData.conversionMetadata?.line_meta
          ? [
              { label: costLabels.merchandiseBase, value: fmt(formData.conversionMetadata.line_meta.subtotal_merch_ils ?? formData.conversionMetadata.deal_total_ils ?? 0) },
              ...(!formData.shippingIncluded
                ? [{ label: "الشحن داخل المنشأ", value: fmt(formData.conversionMetadata.line_meta.internal_shipping_ils || 0) }]
                : []),
              { label: "تكلفة الشحن الدولي", value: fmt(formData.conversionMetadata.line_meta.deal_ship_allocated_ils || 0) },
              { label: "تكلفة التخليص", value: fmt(formData.conversionMetadata.line_meta.deal_clearance_allocated_ils || 0) },
              { label: "تكلفة النقل", value: fmt(formData.conversionMetadata.deal_local_shipping_from_clearance_ils || 0) },
              ...(transferCommissionsIls > 0
                ? [{ label: "عمولات تحويل الدفعات", value: fmt(transferCommissionsIls) }]
                : []),
              ...((Number(formData.discountAmount) || 0) > 0
                ? [{ label: "الخصم", value: fmt(Number(formData.discountAmount) || 0) }]
                : []),
              { label: "المجموع قبل الضريبة", value: fmt((Number(formData.subtotal) || 0) + transferCommissionsIls) },
              { label: "الضريبة المضافة", value: fmt(Number(formData.taxAmount) || 0) },
              ...invFees.map((fee) => ({ label: fee.description || "رسم إضافي", value: fmt(Number(fee.amount) || 0) })),
              { label: "إجمالي المستحق بعد الضريبة والرسوم", value: fmt(payableTotal), emphasis: true },
              { label: "المدفوع المرحّل", value: fmt(Number(formData.amountPaid) || 0) },
              ...(settlement.pendingIntent > 0.009
                ? [{ label: "دفعة غير مرحّلة", value: fmt(settlement.pendingIntent) }]
                : []),
              { label: "المتبقي للدفع", value: fmt(settlement.remainingAfterIntent), tone: "warn" },
              { label: "رصيد المورد قبل احتساب المتبقي (بالعملة الأساسية)", value: fmt(Number(formData.partnerBalanceBeforeInvoice) || 0) },
              { label: "رصيد المورد الحالي بعد احتسابه (بالعملة الأساسية)", value: fmt(Number(formData.partnerBalanceAfterInvoice) || 0), emphasis: true },
              { label: "إجمالي الكمية", value: formatQuantity(totalQty) },
              ...(showReceiptColumns
                ? [{ label: "باقي الاستلام", value: formatQuantity(receiptProgress!.remaining) }]
                : []),
            ]
          : [
              { label: "مجموع البنود (قبل الخصم)", value: fmt(ilsMerchandiseBase - (formData.shippingIncluded ? 0 : formData.shippingCost || 0)) },
              ...((Number(formData.discountAmount) || 0) > 0
                ? [{ label: "الخصم", value: fmt(Number(formData.discountAmount) || 0) }]
                : []),
              { label: "المجموع قبل الضريبة", value: fmt(Number(formData.subtotal) || 0) },
              { label: "الضريبة المضافة", value: fmt(Number(formData.taxAmount) || 0) },
              ...invFees.map((fee) => ({ label: fee.description || "رسم إضافي", value: fmt(Number(fee.amount) || 0) })),
              { label: "إجمالي المستحق بعد الضريبة والرسوم", value: fmt(payableTotal), emphasis: true },
              { label: "المدفوع المرحّل", value: fmt(Number(formData.amountPaid) || 0) },
              ...(settlement.pendingIntent > 0.009
                ? [{ label: "دفعة غير مرحّلة", value: fmt(settlement.pendingIntent) }]
                : []),
              { label: "المتبقي للدفع", value: fmt(settlement.remainingAfterIntent), tone: "warn" },
              { label: "رصيد المورد قبل احتساب المتبقي (بالعملة الأساسية)", value: fmt(Number(formData.partnerBalanceBeforeInvoice) || 0) },
              { label: "رصيد المورد الحالي بعد احتسابه (بالعملة الأساسية)", value: fmt(Number(formData.partnerBalanceAfterInvoice) || 0), emphasis: true },
              { label: "إجمالي الكمية", value: formatQuantity(totalQty) },
              ...(showReceiptColumns
                ? [{ label: "باقي الاستلام", value: formatQuantity(receiptProgress!.remaining) }]
                : []),
            ]
      }
      sections={[
        {
          key: "payments",
          title: `تفاصيل دفعات المورد (${formData.paymentDetails?.length || 0})`,
          content: formData.paymentDetails?.length ? (
            <KitViewTable<NonNullable<Invoice["paymentDetails"]>[number]>
              columns={[
                { key: "voucher", header: "السند", render: (p) => `${p.source === "supplier_payment" ? "سند صرف" : "دفعة فاتورة"} #${p.id}` },
                { key: "date", header: "التاريخ", width: "110px", render: (p) => formatDateLocalized(p.paymentDate) },
                { key: "account", header: "الصندوق/البنك", render: (p) => p.cashOrBankAccountName || "—" },
                { key: "amount", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (p) => `${fmt(p.amount)} ${p.currencyCode}` },
                { key: "status", header: "الحالة", width: "100px", render: (p) => p.isPosted ? "مرحّل" : "غير مرحّل" },
                { key: "journal", header: "القيد", width: "90px", render: (p) => p.journalId ? `#${p.journalId}` : "—" },
              ]}
              rows={formData.paymentDetails}
              rowKey={(p) => `${p.source}-${p.id}`}
              showIndex={false}
            />
          ) : "لا توجد دفعات مرتبطة بهذه الفاتورة.",
        },
        ...(invFees.length > 0
          ? [
              {
                key: "fees",
                title: `الرسوم (${invFees.length})`,
                content: (
                  <KitViewTable<(typeof invFees)[number]>
                    columns={[
                      { key: "desc", header: "البيان", render: (f) => f.description || "—" },
                      { key: "acc", header: "الحساب", width: "160px", render: (f) => f.expenseAccountName || "—" },
                      {
                        key: "cap",
                        header: "يُرسمل على المخزون",
                        width: "130px",
                        align: "center",
                        render: (f) => (f.capitalizeToInventory ? "نعم" : "لا"),
                      },
                      { key: "amt", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (f) => fmt(Number(f.amount) || 0) },
                    ]}
                    rows={invFees}
                    rowKey={(f, i) => f.id || i}
                    showIndex={false}
                    emptyHint="لا توجد رسوم"
                  />
                ),
              },
            ]
          : []),
        ...(formData.notes
          ? [{ key: "notes", title: "ملاحظات", content: formData.notes }]
          : []),
      ]}
    />
  );

  return (
    <div
      id="purchase-invoice-print"
      dir="rtl"
    >
    <KitDocumentShell
      gridFitContent={viewMode}
      title={formData.isReturn
        ? "مرتجع شراء (إرجاع للمورد)"
        : isInternationalInvoice ? "فاتورة شراء دولية" : "فاتورة الشراء"}
      state={
        formData.id
          ? `${formData.isReturn ? "مرتجع" : isInternationalInvoice ? "فاتورة دولية" : "فاتورة"} ${formData.invoiceNumber || `#${formData.id}`}`
          : (formData.isReturn ? "مرتجع جديد" : isInternationalInvoice ? "فاتورة دولية جديدة" : "فاتورة جديدة")
      }
      company={
        formData.glPurchaseReceiptJournalId != null ? `قيد محاسبي #${formData.glPurchaseReceiptJournalId}` : undefined
      }
      nav={nav}
      actions={toolbarActions}

      header={viewMode ? undefined : (
        <>
          {fld(
            "رقم الفاتورة",
            <input
              className="ktra-input"
              readOnly
              // T-PSIMPL: المسودّة تعرض الرقم **التالي** بدل «— جديدة —» — كان
              // المستخدم لا يعرف رقم مستنده حتى يحفظه. مُلمَّحٌ أنه مبدئي:
              // الرقم النهائي يحسمه الخادم عند الحفظ (دفتر ترقيم مقفول).
              value={
                formData.id
                  ? `#${formData.invoiceNumber || formData.id}`
                  : nextNumberPreview
                    ? `${nextNumberPreview} (مبدئي)`
                    : "— جديدة —"
              }
            />
          )}
          {fld(
            "التاريخ",
            <KitDatePicker
              className="ktra-input"
              disabled={effectiveReadOnly}
              value={formData.invoiceDate || ""}
              onChange={(val) => handleUpdateFinancial("invoiceDate", val)}
            />
          )}
          {showAdv("doc.due-date", Boolean(formData.dealInfo?.dueDate)) && fld(
            "تاريخ الاستحقاق",
            <KitDatePicker
              className="ktra-input"
              disabled={effectiveReadOnly}
              value={formData.dealInfo?.dueDate || ""}
              onChange={(val) => handleDealInfoUpdate("dueDate", val)}
            />
          )}
          {fld(
            "رقم المستند",
            <input
              className="ktra-input"
              disabled={effectiveReadOnly}
              value={formData.supplierInvoiceNumber || ""}
              onChange={(e) => handleUpdateFinancial("supplierInvoiceNumber", e.target.value)}
              placeholder="رقم فاتورة المورد"
            />
            ,
            fe("supplier_invoice_number")
          )}
          {/* تكافؤ مع محرر المبيعات: الماسح يُدخل المنتج مباشرةً بلا فتح المنتقي. */}
          {fld(
            "بحث سريع / باركود (F6)",
            <input
              className="ktra-input"
              data-ktra-field="barcode"
              disabled={effectiveReadOnly}
              value={barcodeQuery}
              onChange={(e) => setBarcodeQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                e.preventDefault();
                void handleBarcodeEnter(barcodeQuery);
              }}
              placeholder="الاسم/SKU/الباركود ⏎"
            />
          )}
          {fld(
            "المورد",
            <div className="ktra-pickfield">
              <input
                className="ktra-input ktra-input--hl"
                data-ktra-field="supplier"
                data-ktra-key="1"
                readOnly
                disabled={effectiveReadOnly}
                value={selectedSupplier ? `#${selectedSupplier.id}` : ""}
                placeholder="+ للفهرس"
                onClick={() => !readOnly && !formData.isHistorical && setShowSupplierPicker(true)}
              />
              <button
                type="button"
                className="ktra-ellipsis"
                disabled={effectiveReadOnly}
                onClick={() => setShowSupplierPicker(true)}
                title="فهرس الموردين (+)"
              >
                …
              </button>
            </div>,
            fe("supplier")
          )}
          {fld(
            "الاسم",
            /* T-SEARCH: كان صندوقاً للعرض فقط، فاختيارُ المورّد يمرّ بالفهرس
               الكامل وحده — بينما جانب البيع يكتب اسم عميله ويجده. الآن يُكتب
               ويُبحَث بالاسم والهاتف والرقم، ويُنشأ مورّد جديد من مكانه. */
            <KitAutocomplete
              value={headerSupplierName || ""}
              options={supplierOptions}
              disabled={effectiveReadOnly}
              placeholder="اكتب اسم المورّد…"
              onPick={(id) => {
                const sup = suppliers.find((x) => String(x.id) === String(id));
                if (!sup) return;
                setFormData((prev) => ({
                  ...prev, supplierId: sup.id, factoryName: sup.tradeName,
                }));
                markDirty();
              }}
              onShowMore={() => setShowSupplierPicker(true)}
              onFreeText={() => setShowAddSupplierModal(true)}
              createLabel={(t) => `إضافة «${t}» كمورّد جديد`}
            />
          )}
          {showAdv("doc.currency", (formData.currency || "ILS") !== "ILS") && fld(
            "العملة",
            <select
              className="ktra-input"
              disabled={effectiveReadOnly}
              value={formData.currency || "ILS"}
              onChange={(e) => handleUpdateFinancial("currency", e.target.value)}
            >
              <option value="USD">USD — دولار</option>
              <option value="ILS">ILS — شيكل</option>
            </select>
          )}
          {formData.currency === "ILS" && showAdv("doc.tax", invoiceHasTax) && fld(
            "نسبة الضريبة %",
            <input
              className="ktra-input"
              data-ktra-key="1"
              data-purchase-tax-rate="true"
              type="number"
              min={0}
              max={100}
              step={0.01}
              disabled={effectiveReadOnly}
              value={formData.taxRate || 0}
              onChange={(e) => handleUpdateFinancial("taxRate", Number(e.target.value))}
            />
          )}
          {showAdv("doc.licensed-dealer", Boolean(formData.dealInfo?.licensedDealerNo)) && fld(
            "مشتغل مرخص",
            <input
              className="ktra-input"
              disabled={effectiveReadOnly}
              value={formData.dealInfo?.licensedDealerNo || ""}
              onChange={(e) => handleDealInfoUpdate("licensedDealerNo", e.target.value)}
              placeholder="رقم المشتغل المرخص"
            />
          )}
          {formData.dealNumber && fld(
            "رقم الصفقة",
            <input
              className="ktra-input"
              readOnly
              value={formData.dealNumber}
            />
          )}
          {/* T-PLINEAGE: الفاتورة كانت صامتة عن أصلها — الآن تقول من أين جاءت
              وتفتح المستند الأب (والجدّ إن كانت الطلبية نفسها وليدة عرض). */}
          {formData.sourceDocument && fld(
            formData.sourceDocument.kind === "order" ? "أُنشئت من طلبية شراء" : "أُنشئت من عرض سعر",
            <div className="flex flex-col gap-1">
              <button
                type="button"
                data-testid="open-source-document"
                className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-3 text-xs font-bold text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
                title={`فتح المستند المصدر ${formData.sourceDocument.number}`}
                onClick={() => openInNewTab(
                  `/price-offers?doc=${formData.sourceDocument!.kind === "order" ? "order" : "quote"}-${formData.sourceDocument!.id}`
                )}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                <span>فتح المستند المصدر</span>
                <b dir="ltr">{formData.sourceDocument.number}</b>
              </button>
              {formData.sourceDocument.originNumber && (
                <span className="text-[10px] text-[var(--ktra-ink-soft)]">
                  الطلبية نفسها من عرض السعر {formData.sourceDocument.originNumber}
                </span>
              )}
            </div>
          )}
          {shipmentLinkId && fld(
            "الشحنة المرتبطة",
            <div className="flex items-center">
              <button
                type="button"
                data-testid="open-linked-shipment"
                className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-3 text-xs font-bold text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
                aria-label={`فتح رحلة الشحنة ${shipmentDisplayNumber}`}
                title={`فتح رحلة الشحنة ${shipmentDisplayNumber}`}
                onClick={() => openInNewTab(`/import-flow/${encodeURIComponent(shipmentLinkId)}`)}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                <span>فتح رحلة الشحنة</span>
                <b dir="ltr">{shipmentDisplayNumber}</b>
              </button>
            </div>
          )}
          {formData.importLogistics && fld(
            "رقم التخليص",
            <input
              className="ktra-input"
              readOnly
              value={String(formData.importLogistics.clearanceId || "")}
            />
          )}
          <label className="ktra-field ktra-field--inline">
            <input
              type="checkbox"
              disabled={effectiveReadOnly}
              checked={formData.shippingIncluded || false}
              onChange={(e) => handleUpdateFinancial("shippingIncluded", e.target.checked)}
            />
            <span className="ktra-field-label" style={{ flex: "unset" }}>
              الأسعار تشمل ض.ق.م
            </span>
          </label>
          {/* T-INTENT: نقدي/آجل في الرأس — مرآة مفتاح فاتورة البيع. كان مدفوناً
              في تبويب المحاسبة وحده، فيدفع المشتري وهو لا يرى نوع فاتورته. */}
          <label className="ktra-field ktra-field--inline">
            <input
              type="checkbox"
              data-testid="purchase-payment-type"
              disabled={effectiveReadOnly}
              checked={formData.paymentType === "cash"}
              onChange={(e) => {
                setFormData((prev) => ({
                  ...prev,
                  paymentType: e.target.checked ? "cash" : "credit",
                }));
                markDirty();
              }}
            />
            <span className="ktra-field-label" style={{ flex: "unset" }}>
              نقدي
            </span>
            <span
              className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-bold ${
                formData.paymentType === "cash"
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-slate-100 text-slate-700"
              }`}
            >
              {formData.paymentType === "cash" ? "تُدفع فوراً" : "على ذمم المورّد"}
            </span>
          </label>
          {/* T-PAYFULL2: صندوق الفاتورة النقدية — ظاهرٌ حيث يُقرَّر نوعها.
              الخادم يشترطه، فإخفاؤه كان يحوّل علامةً واحدة إلى رفضٍ بلا مخرج. */}
          {formData.paymentType === "cash" && (
            <div className="ktra-field ktra-field--inline min-w-[15rem]" data-testid="purchase-cash-account">
              <span className="ktra-field-label" style={{ flex: "unset" }}>الصندوق</span>
              <AccountTreeField
                className="ktra-input"
                accounts={allAccounts}
                value={formData.cashOrBankAccountId ?? ""}
                purpose="cash"
                disabled={effectiveReadOnly}
                allowClear={false}
                onChange={(id) => {
                  setFormData((prev) => ({ ...prev, cashOrBankAccountId: id ?? null }));
                  markDirty();
                }}
                placeholder="الصندوق / البنك"
                title="صندوق تسوية الفاتورة النقدية"
              />
            </div>
          )}
        </>
      )}
      activeTab={activeTabKey}
      onTabChange={setActiveTabKey}
      /* T-SIMPL2: التبويبات المتقدّمة (الرسوم/الأقساط/الصفقة/السجلّات/القيد)
         تُطوى في الوضع السهل ويبقى جوهر الفاتورة: بياناتها وبنودها وملاحظاتها
         ومرفقاتها. الغلاف يتتبّع التبويب **بالمفتاح** لا بالفهرس، فطيُّ تبويبٍ
         لا يقفز بالمستخدم. و«حسابات الرسوم» تعود متى حملت مبلغاً فعلاً. */
      tabs={viewMode ? [
        // تبويبٌ أوّل خاملٌ عمداً: الغلاف يُفعّل الأوّل، فلو كان «حركة المخزون»
        // لجَلَب لكل فتحة فاتورة — والكسل شرط لا تحسين. نفس ترتيب محرّر البيع.
        { key: "notes", label: "الملاحظات", content: notesTab },
        ...(showAdv("doc.advanced-tabs") ? contextTabs : contextTabs.filter((t) => t.key === "attachments")),
      ] : [
        { key: "basic", label: "بيانات الفاتورة", content: basicInfoTab },
        { key: "items", label: "البنود والمنتجات", content: itemsTab },
        ...(showAdv("doc.advanced-tabs", feesTotal > 0)
          ? [{ key: "fees", label: `حسابات الرسوم${feesTotal > 0 ? ` (${formatMoney(feesTotal)})` : ""}`, content: feesTab }]
          : []),
        ...(showAdv("doc.advanced-tabs")
          ? [
              { key: "installments", label: "أقساط الدفع", content: installmentsTab },
              { key: "dealinfo", label: "معلومات الصفقة", content: dealInfoTab },
            ]
          : []),
        { key: "notes", label: "الملاحظات", content: notesTab },
        { key: "attachments", label: "المرفقات", content: attachmentsTab },
        ...(showAdv("doc.advanced-tabs")
          ? [
              { key: "activity", label: "سجل النشاطات", content: activityTab },
              { key: "other", label: "بيانات أخرى", content: otherTab },
            ]
          : []),
        // M2: المحاسبة والقيد + الحركات المالية inline داخل المحرر (توحيداً مع المبيعات).
        // T-SIMPL2: وكلّها متقدّمة — تُطوى في الوضع السهل وتبقى المرفقات أعلاه.
        ...(showAdv("doc.advanced-tabs") && formData.id && Number(formData.id) > 0 ? [
          {
            key: "accounting",
            label: "المحاسبة والقيد",
            content: (
              <div className="ktra-legacy-tab">
                <PurchaseInvoiceAccountingPanel
                  invoiceId={Number(formData.id)}
                  readOnly={readOnly}
                  onPosted={() => { void reloadInvoice(); if (onSave) onSave({ id: String(formData.id) }); }}
                />
              </div>
            ),
          },
          {
            key: "financial_movements",
            label: "الحركات المالية المرتبطة",
            content: (
              <DocumentPaymentsTab
                referenceType="PURCHASE_INVOICE"
                referenceId={Number(formData.id)}
                searchQuery={formData.invoiceNumber}
              />
            ),
          },
          /* T-PCTX — تبويبات السياق. تُلحق **آخر** القائمة: الغلاف يتتبّع
             التبويب بالفهرس، فإدراج تبويب في الوسط يقفز بالمستخدم. ولا شيء
             منها يُجلَب حتى يُفتح تبويبه (الغلاف يركّب المحتوى النشط وحده).
             ومصدرها `contextTabs` نفسه المستعمل في وضع العرض — قائمةٌ واحدة. */
          ...contextTabs.filter((t) => t.key !== "attachments"),
          {
            key: "activity_log",
            label: "سجل النشاط",
            content: <EntityActivityLog entityType="purchase_invoice" entityId={Number(formData.id)} defaultOpen />,
          },
        ] : []),
      ]}
      totals={viewMode ? undefined : (
        formData.conversionMetadata?.line_meta ? (
          <>
            <div className="ktra-total-row">
              <span>{costLabels.merchandiseBase}</span>
              <span className="ktra-total-value">{fmt(formData.conversionMetadata.line_meta.subtotal_merch_ils ?? formData.conversionMetadata.deal_total_ils ?? 0)}</span>
            </div>
            {/* الشحن داخل المنشأ مخصوم من البضاعة أعلاه؛ عند تضمينه بالأسعار لا يُعرض كسطر مستقل */}
            {!formData.shippingIncluded && (
              <div className="ktra-total-row">
                <span>الشحن داخل المنشأ</span>
                <span className="ktra-total-value">{fmt(formData.conversionMetadata.line_meta.internal_shipping_ils || 0)}</span>
              </div>
            )}
            <div className="ktra-total-row">
              <span>تكلفة الشحن الدولي</span>
              <span className="ktra-total-value">{fmt(formData.conversionMetadata.line_meta.deal_ship_allocated_ils || 0)}</span>
            </div>
            <div className="ktra-total-row">
              <span>تكلفة التخليص</span>
              <span className="ktra-total-value">{fmt(formData.conversionMetadata.line_meta.deal_clearance_allocated_ils || 0)}</span>
            </div>
            <div className="ktra-total-row">
              <span>تكلفة النقل</span>
              <span className="ktra-total-value">{fmt(formData.conversionMetadata.deal_local_shipping_from_clearance_ils || 0)}</span>
            </div>
            {/* عمولات تحويل دفعات الصفقة — كانت محسوبة في تكلفة المنتج وأساس ض.ق.م بلا سطر ظاهر هنا */}
            {transferCommissionsIls > 0 && (
              <div className="ktra-total-row">
                <span>عمولات تحويل الدفعات</span>
                <span className="ktra-total-value">{fmt(transferCommissionsIls)}</span>
              </div>
            )}
            <div className="border-t border-gray-400 my-1 w-full" style={{ borderStyle: "dashed", borderColor: "rgba(0,0,0,0.15)" }} />
            {(formData.discountAmount || 0) > 0 && (
              <div className="ktra-total-row">
                <span>الخصم</span>
                <span className="ktra-total-value">{fmt(formData.discountAmount || 0)}</span>
              </div>
            )}
            {/* T-SIMPL2: سطرا الضريبة يُطويان في الوضع السهل — ويعودان متى
                احتُسبت ضريبةٌ فعلاً، فلا يختفي فرقٌ في المبلغ عن دافعه. */}
            {showAdv("doc.tax", invoiceHasTax) && (
              <>
                <div className="ktra-total-row">
                  <span>المجموع قبل الضريبة</span>
                  <span className="ktra-total-value">{fmt((formData.subtotal || 0) + transferCommissionsIls)}</span>
                </div>
                <div className="ktra-total-row">
                  <span>الضريبة المضافة</span>
                  <span className="ktra-total-value">{fmt(formData.taxAmount || 0)}</span>
                </div>
              </>
            )}
            {(formData.fees || []).map((fee, index) => (
              <div className="ktra-total-row" key={fee.id || index}>
                <span>{fee.description || "رسم إضافي"}</span>
                <span className="ktra-total-value">{fmt(fee.amount || 0)}</span>
              </div>
            ))}
            <div className="ktra-total-row ktra-total-row--grand">
              <span>إجمالي المستحق بعد الضريبة والرسوم</span>
              <span className="ktra-total-value">{fmt(payableTotal)}</span>
            </div>
            <div className="ktra-total-row">
              <span>إجمالي الكمية</span>
              <span className="ktra-total-value">{formatQuantity(totalQty)}</span>
            </div>
            {showReceiptColumns && (
              <div className="ktra-total-row">
                <span>باقي الاستلام</span>
                <span className="ktra-total-value">{formatQuantity(receiptProgress!.remaining)}</span>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="ktra-total-row">
              <span>مجموع البنود (قبل الخصم)</span>
              <span className="ktra-total-value">{fmt(ilsMerchandiseBase - (formData.shippingIncluded ? 0 : formData.shippingCost || 0))}</span>
            </div>
            {(formData.discountAmount || 0) > 0 && (
              <div className="ktra-total-row">
                <span>الخصم</span>
                <span className="ktra-total-value">{fmt(formData.discountAmount || 0)}</span>
              </div>
            )}
            {showAdv("doc.tax", invoiceHasTax) && (
              <>
                <div className="ktra-total-row">
                  <span>المجموع قبل الضريبة</span>
                  <span className="ktra-total-value">{fmt(formData.subtotal || 0)}</span>
                </div>
                <div className="ktra-total-row">
                  <span>الضريبة المضافة</span>
                  <span className="ktra-total-value">{fmt(formData.taxAmount || 0)}</span>
                </div>
              </>
            )}
            {(formData.fees || []).map((fee, index) => (
              <div className="ktra-total-row" key={fee.id || index}>
                <span>{fee.description || "رسم إضافي"}</span>
                <span className="ktra-total-value">{fmt(fee.amount || 0)}</span>
              </div>
            ))}
            <div className="ktra-total-row ktra-total-row--grand">
              <span>إجمالي المستحق بعد الضريبة والرسوم</span>
              <span className="ktra-total-value">{fmt(payableTotal)}</span>
            </div>
            <div className="ktra-total-row">
              <span>إجمالي الكمية</span>
              <span className="ktra-total-value">{formatQuantity(totalQty)}</span>
            </div>
            {showReceiptColumns && (
              <div className="ktra-total-row">
                <span>باقي الاستلام</span>
                <span className="ktra-total-value">{formatQuantity(receiptProgress!.remaining)}</span>
              </div>
            )}
          </>
        )
      )}
      status={
        <>
          <span className="ktra-status-item">المستخدم <b>{currentUser?.name || "—"}</b></span>
          <span className="ktra-status-item">رقم القيد <b>{formData.glPurchaseReceiptJournalId ?? "—"}</b></span>
          {formData.importLogistics && (
            <span className="ktra-status-item">رقم الحركة <b>{formData.importLogistics.shipmentNumber || "—"}</b></span>
          )}
          <span className="ktra-status-item">الحالة <b>{formData.isPosted ? "مرحّلة" : formData.isHistorical ? "مؤرشفة" : formData.id ? "مسودة" : "جديدة"}</b></span>
          <span className="ktra-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
          <span className="ktra-status-item">{effectiveReadOnly ? "للقراءة فقط" : "قابل للتعديل ✓"}</span>
          {/* issue #109 §٦: مؤشّر دائم كي لا يضغط المستخدم «حفظ» احتياطاً كل دقيقة. */}
          {draftSavedAt && !effectiveReadOnly && (
            <span className="ktra-status-item" data-testid="draft-saved-indicator">
              مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
            </span>
          )}
        </>
      }
    >
      {draftSaveFailedBanner}
      {saveErrorBanner}
      {accBanner}
      {draftRestoreBanner}
      {orphanDraftsBanner}
      {/* وضع القراءة: مستند مُنسَّق بدل شبكة الإدخال المعطّلة. */}
      {viewMode && invoiceDocumentView}
      {/* الشجرة انتقلت إلى الشريط الجانبي (aside) ليرتفع لأعلى المستند. */}
      <div style={{ flex: 1, minWidth: 0, display: viewMode ? "none" : "flex", flexDirection: "column" }}>
          {isShipmentLinkedImport && (
            <div
              data-testid="import-inclusive-cost-note"
              className="mb-2 flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-950"
            >
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
              <span>
                <b>تكلفة البند شاملة لتكاليف الاستيراد الموزعة:</b>{" "}
                البضاعة والشحن والجمارك والتخليص والنقل. لا تشمل ض.ق.م والرسوم الإضافية؛
                التكلفة النهائية بعدها تظهر في العمود الأخير وفي تبويب «البنود والمنتجات».
              </span>
            </div>
          )}
          <KitGrid<InvoiceItem>
            columns={itemColumns}
            rows={formData.items || []}
            getCell={itemGetCell}
            getRowKey={(r) => r.id}
            onChange={effectiveReadOnly ? undefined : itemOnChange}
            onAddRow={effectiveReadOnly ? undefined : addRow}
            emptyHint="لا توجد بنود — أضف منتجاً من الشجرة أو اكتب اسمه"
          />
          {!readOnly && !formData.isHistorical && (
            <button type="button" className="ktra-addrow" onClick={addRow}>
              <Plus className="h-3 w-3" /> إضافة سطر
            </button>
          )}
          {(Object.entries(costWarnings) as [string, CostWarning][]).map(([rowId, w]) => (
            <div
              key={rowId}
              role="alert"
              style={{
                display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                margin: "4px 0", padding: "6px 10px", borderRadius: 4,
                background: "var(--ktra-warn-bg, #fff7e6)",
                border: "1px solid var(--ktra-warn, #e0a800)",
                color: "var(--ktra-ink)", fontSize: "var(--ktra-fs-sm)",
              }}
            >
              <AlertCircle style={{ width: 14, height: 14, color: "var(--ktra-warn, #e0a800)" }} />
              <span>
                هذا السعر سيغيّر متوسط تكلفة «<b>{w.name}</b>» من <b>{formatMoney(w.from)}</b> إلى{" "}
                <b>{formatMoney(w.to)}</b>.
              </span>
              <button
                type="button"
                className="ktra-toolbtn"
                style={{ fontWeight: 600 }}
                onClick={() => openInNewTab(`/product-cost?product=${w.productId}`)}
              >
                تكلفة المنتجات
              </button>
            </div>
          ))}
        </div>
        {/* T-APPAY: لوحة الدفع خارج حاوية الإدخال قصداً — الفاتورة المرحّلة
            تُفتح في وضع العرض حيث تلك الحاوية مخفيّة، ودفعُها من هنا نفسه. */}
        {paymentsSection}
        {payPanel}
    </KitDocumentShell>

    {/* فهرس الموردين */}
    <KitIndexPicker<Supplier>
      open={showSupplierPicker}
      title="فهرس الموردين"
      rows={suppliers}
      columns={[
        { key: "id", header: "الرقم", width: "70px", value: (r) => r.id },
        { key: "tradeName", header: "الاسم التجاري", value: (r) => r.tradeName || "" },
        { key: "city", header: "المدينة", value: (r) => r.city || "" },
      ]}
      getRowKey={(r) => r.id}
      searchValue={(r) => `${r.id} ${r.tradeName || ""} ${r.city || ""}`}
      actionButton={
        <button
          type="button"
          onClick={() => setShowAddSupplierModal(true)}
          className="flex items-center gap-1 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
        >
          <Plus className="w-4 h-4" /> إضافة مورد
        </button>
      }
      onSelect={(r) => {
        setFormData((prev) => ({ ...prev, supplierId: r.id, factoryName: r.tradeName }));
        setShowSupplierPicker(false);
        markDirty();
      }}
      onClose={() => setShowSupplierPicker(false)}
    />

    {showAddSupplierModal && (
      <SupplierModal
        isOpen={showAddSupplierModal}
        onClose={() => setShowAddSupplierModal(false)}
        onSaveSuccess={(newSupplier) => {
          setShowAddSupplierModal(false);
          setFormData((prev) => ({ ...prev, supplierId: newSupplier.id, factoryName: newSupplier.tradeName || newSupplier.alias || "" }));
          setShowSupplierPicker(false);
          markDirty();
        }}
      />
    )}

    {showItemSearch && (
      <ItemSearchModal
        isOpen={showItemSearch}
        initialSearch={pickerQuery}
        onClose={() => { setShowItemSearch(false); setPickerQuery(""); }}
        onSelectItem={handleItemSelect}
        items={allDbItems}
        supplierId={formData.supplierId}
        onItemCreated={(it) =>
          setAllDbItems((prev) =>
            prev.some((p) => String(p.id) === String(it.id)) ? prev : [it, ...prev]
          )
        }
      />
    )}

    {inlineCreate && (
      <ItemQuickCreateModal
        isOpen
        initialName={inlineCreate.name}
        onClose={() => setInlineCreate(null)}
        onSaved={(newProduct) => {
          const item = productToItem(newProduct);
          setAllDbItems((prev) =>
            prev.some((p) => String(p.id) === String(item.id)) ? prev : [item, ...prev]
          );
          applyItemAt(inlineCreate.rowIndex, item);
          setInlineCreate(null);
        }}
      />
    )}

    {previewImage && (
      <div className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center p-4" onClick={() => setPreviewImage(null)}>
        <img src={previewImage} alt="Preview" className="max-w-full max-h-full rounded-lg" />
        <button onClick={() => setPreviewImage(null)} className="absolute top-4 right-4 text-white p-2 ktra-bg-panel rounded-full">
          <ArrowRight className="w-6 h-6 rotate-180" />
        </button>
      </div>
    )}

    {/* DEF-007/008: بطاقة المنتج المشتركة — «موافق» يُدرج المنتج في فاتورة الشراء. */}
    {quickEditProductId != null && (
      <ItemQuickEditModal
        productId={quickEditProductId}
        onClose={() => setQuickEditProductId(null)}
        onSaved={applyProductUpdate}
      />
    )}

    {cardProductId != null && (() => {
      const it = allDbItems.find((x) => String(x.id) === String(cardProductId));
      return (
        <ProductCardModal
          productId={cardProductId}
          productName={it ? it.name : undefined}
          addMode={!(!cardCanAdd || effectiveReadOnly || !it)}
          suggestedPrice={cardSuggestedPrice}
          priceSource={cardSuggestedPrice != null ? "last_invoice" : "default"}
          onConfirm={(!cardCanAdd || effectiveReadOnly || !it) ? undefined : (opts) => {
            const price = opts?.unitPrice ?? cardSuggestedPrice ?? 0;
            applyItemAt(null, it, price, opts?.quantity);
          }}
          onProductSaved={applyProductUpdate}
          onClose={() => setCardProductId(null)}
        />
      );
    })()}
    {/* T-SERIAL: أرقام وحدات البند — الكمية تتبع عدد الأرقام (قاعدة المالك:
        تبدأ برقم والعدد يقود الأكواد، فلا تُدخل الكمية مرتين). */}
    {serialRowIndex != null && (() => {
      const row = (formData.items || [])[serialRowIndex];
      if (!row) return null;
      return (
        <SerialEntryModal
          mode="capture"
          productId={Number(row.itemId)}
          productName={row.name || `#${row.itemId}`}
          quantity={Number(row.quantity) || 0}
          value={row.serials ?? []}
          required={serialMode === "required"}
          readOnly={effectiveReadOnly}
          onClose={() => setSerialRowIndex(null)}
          onSave={(entered) => {
            const items = [...(formData.items || [])];
            const target = { ...items[serialRowIndex], serials: entered };
            // قائمة فارغة لا تصفّر الكمية — المستخدم مسح الأرقام لا البند.
            if (entered.length > 0) {
              target.quantity = entered.length;
              target.totalPrice = roundSqlMoney2(entered.length * (target.unitPrice || 0));
            }
            items[serialRowIndex] = target;
            recalculateTotals({ items });
            markDirty();
            setSerialRowIndex(null);
          }}
        />
      );
    })()}
      {showPrintView && (
        <InvoicePrintView
          invoice={formData as Invoice}
          currentUser={currentUser}
          supplier={selectedSupplier}
          onClose={() => setShowPrintView(false)}
        />
      )}
      {formData.id != null && (
        <ShareDocumentModal
          open={showShareModal}
          onClose={() => setShowShareModal(false)}
          docType="purchase_invoice"
          docId={Number(formData.id)}
          docLabel={`فاتورة شراء ${formData.invoiceNumber || `#${formData.id}`}`}
          partyName={selectedSupplier?.tradeName}
        />
      )}
      {/* استلام سريع: يُنشئ إرسالية بالبنود المؤشَّرة (كلها افتراضياً). */}
      {showReceive && formData.id && (
        <ReceiveGoodsModal
          invoiceId={Number(formData.id)}
          invoiceNumber={formData.invoiceNumber}
          onClose={() => setShowReceive(false)}
          onReceived={() => {
            setShowReceive(false);
            toast("تم استلام البضاعة وإنشاء الإرسالية.", "success");
            void reloadInvoice();
          }}
        />
      )}
    </div>
  );
};
