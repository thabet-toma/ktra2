import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useConfirm } from "../../contexts/ConfirmContext";
import {
  Trash2,
  Save,
  Loader2,
  Printer,
  Share2,
  Info,
  X,
  Search,
} from "lucide-react";
import {
  listQuotationsPage,
  getQuotation,
  createQuotation,
  updateQuotation,
  deleteQuotation,
  convertQuotation,
  cancelQuotation,
  getCustomerPriceList,
  getReservedStock,
  getSalesSettings,
  type SalesQuotationRow,
  type SalesQuotationDetail,
  type ReservedStockRow,
} from "../../services/salesApi";
import { useToast } from "../../contexts/ToastContext";
import { ConvertTargetDialog } from "./ConvertTargetDialog";
import { accountingApi } from "../../services/accountingApi";
import { apiGetList } from "../../services/restApi";
import { listPickerProducts } from "../../services/inventoryApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { formatTimeValue } from "../../utils/formatDate";
import { computeInvoiceTotals, type LineInput } from "../../utils/salesInvoiceMath";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";
import { DocumentDraftBanners } from "../shared/DocumentDraftBanners";
import type { SqlProduct } from "../../types/inventory";
import {
  useRecordNavigation,
  useKitKeymap,
  KitAutocomplete,
} from "../kit";
import { ShareDocumentModal } from "../shared/ShareDocumentModal";
import { ProductCardModal } from "../shared/ProductCardModal";
import { SalesProductPickerModal, type SalesProductPickerItem, formatProductPrimaryName } from "./SalesProductPickerModal";
import { ItemQuickEditModal } from "../items/ItemQuickEditModal";
import { ItemQuickCreateModal } from "../items/ItemQuickCreateModal";
import { eventBus } from "../../utils/eventBus";
import { usePriceVisibility } from "../../contexts/PriceVisibilityContext";
import { getPickerFieldVisibility } from "../../utils/pickerFieldVisibility";
import { stockBadgeFor } from "../../utils/stockBadge";
import { availableForSale, buildReservationIndex, totalReserved } from "../../utils/reservedStock";
import { openInNewTab } from "../../utils/openInNewTab";
import { productProfilePath } from "../../utils/entityLinks";
import { SalesOrdersPage } from "./SalesOrdersPage";
import {
  CommercialDocumentEditor,
  type CommercialHeaderField,
  type CommercialLineColumn,
  type CommercialToolbarAction,
} from "../shared/CommercialDocumentEditor";
import {
  CommercialDocumentsList,
  type CommercialListColumn,
} from "../shared/CommercialDocumentsList";

type Partner = { id: number; name: string };
/** نسبة ضريبة من شجرة الحسابات — الحقل على البند مفتاحُها لا نسبتها المئوية. */
type TaxRateRow = { id: number; name: string; rate: string | number; direction?: string };
type Product = SalesProductPickerItem & { name: string; unit_price?: string };

type LineState = {
  id?: number;
  product_id: string;
  product_name: string;
  quantity: string;
  unit_price: string;
  discount: string;
  tax_rate: string;
  total: string;
  /** T-PICKUNIFY (#147): سعرٌ لمَسه المستخدم (كتابةً، أو من بطاقة المنتج، أو
   *  من مسودّة مستعادة) — لا يُعاد تسعيره تلقائياً عند تبديل الزبون. */
  priceTouched?: boolean;
};

/** ISSUE #121: حمولة المسودّة المحلية — خفيفة تكفي وحدها لإعادة بناء الشاشة
 *  (issue #118)، لا صلة بحمولة الحفظ الخادمية التي يبنيها `handleSave`. */
interface SalesQuotationDraftPayload {
  formCustomer: string;
  formDate: string;
  formValidUntil: string;
  formNotes: string;
  formIsActive: boolean;
  formPricesIncludeTax: boolean;
  formCustomerAddress: string;
  formCustomerTaxNumber: string;
  formDiscount: string;
  formLines: LineState[];
}

export const SalesQuotationsPage: React.FC = () => {
  const confirm = useConfirm();
  const toast = useToast();
  // T-ORDERS: صلاحية العرض ومدة الحجز وإظهار الحذف — كلها من إعدادات الشركة.
  const [quotationValidDays, setQuotationValidDays] = useState(14);
  const [allowDelete, setAllowDelete] = useState(true);
  // العرض المطلوب تحويله — يفتح حوار «طلبية أم فاتورة؟» داخل الموقع (لا حوار متصفح).
  const [convertId, setConvertId] = useState<number | null>(null);
  const [shareId, setShareId] = useState<number | null>(null);
  const [quotations, setQuotations] = useState<SalesQuotationRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [page, setPage] = useState(1);
  const [totalQuotations, setTotalQuotations] = useState(0);
  const pageSize = 50;

  // Form state
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formCustomer, setFormCustomer] = useState("");
  const [formDate, setFormDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [formValidUntil, setFormValidUntil] = useState("");
  const [formNotes, setFormNotes] = useState("");
  // N4-T6: حقول إضافية per spec — فعال checkbox + prices include VAT
  const [formIsActive, setFormIsActive] = useState(true);
  const [formPricesIncludeTax, setFormPricesIncludeTax] = useState(false);
  const [formCustomerAddress, setFormCustomerAddress] = useState("");
  const [formCustomerTaxNumber, setFormCustomerTaxNumber] = useState("");
  const [formLines, setFormLines] = useState<LineState[]>([{
    id: undefined, product_id: "", product_name: "", quantity: "1", unit_price: "", discount: "0", tax_rate: "0", total: "0"
  }]);

  // خصم المستند («خصم الفاتورة») — يُعلَن على رأس العرض لا على بنوده.
  const [formDiscount, setFormDiscount] = useState("0");

  // ISSUE #121: علامة «لُمِس» — تُرفَع مزامنةً داخل كل معالج تعديل مستخدم (لا
  // مشتقّة داخل useEffect؛ حالةٌ مشتقّة تفوّت بالضبط حالة «عُدِّل ثم غادر»).
  const [touched, setTouched] = useState(false);
  const markTouched = () => setTouched(true);
  const [taxRates, setTaxRates] = useState<TaxRateRow[]>([]);
  // بطاقة المنتج المشتركة — تكلفة الصنف وأسعاره دون مغادرة العرض.
  const [cardProductId, setCardProductId] = useState<number | null>(null);

  const [productPickerLineIdx, setProductPickerLineIdx] = useState<number | null>(null);
  // T-SEARCH: نصُّ البحث المنقول إلى الفهرس الكامل عند «+N أخرى» — نفس فاتورة البيع.
  const [pickerQuery, setPickerQuery] = useState("");
  // ISSUE #147 US48: «+ إضافة كمنتج جديد» للنصّ الذي كتبه البائع بلا تطابق —
  // خلافاً لشاشة الشراء لا يوجد بندٌ نصّي بلا منتج هنا؛ الإنشاء يُدرج المنتج
  // في السطر نفسه فوراً (نفس نمط «خدمة» في فاتورة البيع).
  const [quickCreateLineIdx, setQuickCreateLineIdx] = useState<number | null>(null);
  const [quickCreateName, setQuickCreateName] = useState("");

  // معاينة بنود العرض داخل القائمة (طيّ/فتح) — لتُرى البنود بلا فتح النموذج.
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedLines, setExpandedLines] = useState<
    Record<number, Array<{ name: string; quantity: string; unit_price: string; line_total: string }>>
  >({});

  // ISSUE #147 M4: تعديل سريع لمنتج من داخل منتقي البند — نفس قلم باقي المستندات.
  const [quickEditProductId, setQuickEditProductId] = useState<number | null>(null);
  const applyProductUpdate = useCallback((updated: Record<string, unknown>) => {
    const row = updated as { id?: number };
    if (!row?.id) return;
    setProducts((prev) => prev.map((p) => {
      if (p.id !== row.id) return p;
      const merged = { ...p, ...updated } as Product;
      merged.name = (updated as any).name_ar || (updated as any).name_en || (updated as any).sku || merged.name;
      return merged;
    }));
  }, []);

  /* ISSUE #147 M4: سعر هذا الزبون تحديداً (آخر فاتورة/عرض سعر/سعر عام) — سلّمٌ
   * واحد من الخادم (`sales.services.pricing.customer_price_list`)، نفس الذي
   * تقرأه فاتورة البيع. تُجلَب دفعةً واحدة عند اختيار الزبون وتُخزَّن مؤقتاً
   * بمفتاحه كي لا يُعاد الجلب عند التنقل ذهاباً وإياباً بين الزبائن. بلا زبونٍ
   * مختار: لا خريطة ولا حقل سعرٍ في المنتقي إطلاقاً — راجع القرار §B.5.
   * `exclude_quotation`: العرض المفتوح للتحرير يُستبعد من رتبة عروضه هو —
   * وإلا لاقترح على نفسه رقمه هو كأنه تاريخٌ سابق للزبون. */
  const customerPriceCacheRef = useRef<Map<string, Map<number, { price: string; source: "last_invoice" | "quote" | "default"; source_label: string }>>>(new Map());
  const [customerPriceMap, setCustomerPriceMap] = useState<
    Map<number, { price: string; source: "last_invoice" | "quote" | "default"; source_label: string }>
  >(new Map());
  useEffect(() => {
    if (!formCustomer) { setCustomerPriceMap(new Map()); return; }
    const cacheKey = selectedId != null ? `${formCustomer}:x${selectedId}` : formCustomer;
    const cached = customerPriceCacheRef.current.get(cacheKey);
    if (cached) { setCustomerPriceMap(cached); return; }
    let alive = true;
    getCustomerPriceList(formCustomer, selectedId != null ? { excludeQuotation: selectedId } : undefined)
      .then((rows) => {
        if (!alive) return;
        const m = new Map<number, { price: string; source: "last_invoice" | "quote" | "default"; source_label: string }>();
        for (const r of rows) {
          // #147: **وجودُ السعر لا كونُه موجباً** — سطرٌ بِيع فعلاً بصفر
          // (هديّة، أو بندٌ مجّانيّ ضمن صفقة) رقمٌ حقيقيٌّ في تاريخ هذا
          // الزبون، وإسقاطُه يجعل الشاشة تقول «لا سابقة» وهي كاذبة. القاعدة
          // الذهبية «فارغٌ يبقى فارغاً» تمنع اختلاقَ صفرٍ لا وجود له، لا
          // إخفاءَ صفرٍ موجود. (فاتورة البيع ما زالت على `> 0` — فارقٌ
          // سابقٌ لهذه المواصفة، يُحسَم على حدة.)
          if (r.price != null && String(r.price).trim() !== "") {
            m.set(r.product_id, { price: String(r.price), source: r.source, source_label: r.source_label });
          }
        }
        customerPriceCacheRef.current.set(cacheKey, m);
        setCustomerPriceMap(m);
      })
      .catch(() => { if (alive) setCustomerPriceMap(new Map()); });
    return () => { alive = false; };
  }, [formCustomer, selectedId]);

  /* ISSUE #147 M4: عند تبديل الزبون بعد وجود بنود، أعِد تسعير الأسطر غير
   * المَلموسة فقط من الخريطة أعلاه المحمَّلة أصلاً — بلا أي نداء شبكة جديد
   * لكل سطر (خلافاً لفاتورة البيع). أول تحميل/فتح مستندٍ محفوظ ليس «تبديلاً»
   * من المستخدم؛ `openQuotation`/`resetForm` يُصفّران `prevCustomerRef` قبل
   * التعبئة كي لا يُقرأ فتح عرضٍ آخر كأنه تبديل زبون يدوي يمسح أسعاره المحفوظة. */
  const prevCustomerRef = useRef<string | null>(null);
  const customerChangedRef = useRef(false);
  useEffect(() => {
    if (prevCustomerRef.current === null) { prevCustomerRef.current = formCustomer; return; }
    if (prevCustomerRef.current === formCustomer) return;
    prevCustomerRef.current = formCustomer;
    customerChangedRef.current = true;
  }, [formCustomer]);
  useEffect(() => {
    if (!customerChangedRef.current) return;
    customerChangedRef.current = false;
    setFormLines((prev) => prev.map((l) => {
      if (!l.product_id || l.priceTouched) return l;
      const cp = customerPriceMap.get(Number(l.product_id));
      return { ...l, unit_price: cp ? cp.price : "" };
    }));
  }, [customerPriceMap]);

  // ISSUE #133/#147: نفس دالّة سياسة الحقول التي تخدم فاتورة البيع — سياق «بيع».
  const { visible: profitVisible } = usePriceVisibility();
  const pickerVisibility = useMemo(() => getPickerFieldVisibility("sale", profitVisible), [profitVisible]);

  /* T-RESERVEVIS: الحجوزات السارية — نفس صفوف «تقرير المحجوزات» التي يحرسها
     الخادم عند تأكيد طلبية أخرى، فـ«المتاح للبيع» في المنتقي ليس تخميناً. */
  const [reservationRows, setReservationRows] = useState<ReservedStockRow[]>([]);
  useEffect(() => {
    let alive = true;
    getReservedStock()
      .then((rows) => { if (alive) setReservationRows(rows); })
      .catch(() => { if (alive) setReservationRows([]); });
    return () => { alive = false; };
  }, []);
  const reservationIndex = useMemo(
    () => buildReservationIndex(reservationRows, formCustomer ? Number(formCustomer) : null),
    [reservationRows, formCustomer],
  );

  /* ISSUE #147 M4: خيارات المنتقي المدمج — نفس بناء فاتورة البيع (`itemOptions`
   * في `SalesInvoiceEditor.tsx`): سعرُ هذا الزبون بمصدره، شارة المخزون، والمتاح
   * بعد الحجز. بلا زبون: لا `price`/`priceLabel` إطلاقاً — لا سعرَ عاماً بديلاً
   * هنا (خلافاً للفاتورة)، لأن عمود «سعر هذا الزبون» يكذب إن ظهر بلا زبون. */
  const itemOptions = useMemo(
    () => products.map((p) => {
      const cp = formCustomer ? customerPriceMap.get(p.id) : undefined;
      const indicativePurchasePrice = pickerVisibility.indicativePurchasePrice
        ? {
            value: p.indicative_purchase_price != null
              ? formatMoney(Number(p.indicative_purchase_price))
              : "—",
            label: p.indicative_purchase_price_source || "",
          }
        : undefined;
      const entry = reservationIndex.get(p.id);
      const reserved = totalReserved(entry);
      const onHand = Number(p.quantity_on_hand || 0);
      return {
        id: p.id,
        label: formatProductPrimaryName(p),
        badge: pickerVisibility.stockBadge ? stockBadgeFor(p) : undefined,
        sub: p.is_service
          ? "خدمة — بلا مخزون"
          : reserved > 0
          ? `الرصيد: ${formatQuantity(onHand)} · محجوز: ${formatQuantity(reserved)} · المتاح للبيع: ${formatQuantity(availableForSale(onHand, entry))}`
          : `الرصيد: ${formatQuantity(onHand)}`,
        price: cp ? formatMoney(Number(cp.price)) : undefined,
        priceLabel: cp
          ? (cp.source === "quote" ? "عرض سعر" : cp.source === "default" ? "سعر عام" : "آخر بيع")
          : undefined,
        indicativePurchasePrice,
        keywords: [p.sku, p.barcode].filter(Boolean).join(" ").toLowerCase(),
      };
    }),
    [products, customerPriceMap, formCustomer, pickerVisibility, reservationIndex],
  );

  // Kit Navigation
  const [showPartnerPicker, setShowPartnerPicker] = useState(false);

  // تحميل عرض سعر وفتح نموذجه (يعرض البنود) — مصدر واحد يخدم «تعديل» ورقم العرض
  // والرابط العميق (?open=) القادم من شارة الفاتورة.
  const openQuotation = useCallback(async (id: number) => {
    try {
      const detail = await getQuotation(id);
      setSelectedId(detail.id);
      // ISSUE #147 M4: تحميلٌ من الخادم ليس «تبديل زبون» من المستخدم — تُضبط
      // القيمة المرجعية مباشرةً على زبون هذا العرض (لا `null`: فتح عرضٍ آخر
      // بنفس الزبون لا يُغيّر حالة formCustomer فلا يُشغَّل أثر إعادة الضبط).
      prevCustomerRef.current = String(detail.customer);
      setFormCustomer(String(detail.customer));
      setFormDate(detail.quotation_date?.slice(0, 10) || "");
      setFormValidUntil(detail.valid_until?.slice(0, 10) || "");
      setFormNotes(detail.notes || "");
      setFormDiscount(String(detail.discount_amount ?? "0"));
      setFormLines((detail.lines || []).map((l) => ({
        id: l.id,
        product_id: String(l.product),
        product_name: l.product_name || "",
        quantity: l.quantity,
        unit_price: l.unit_price,
        discount: l.line_discount || "0",
        tax_rate: String(l.tax_rate || 0),
        total: l.line_total,
      })));
      // تعبئةٌ من الخادم — لا تُعامَل كتعديل مستخدم (issue #121).
      setTouched(false);
      setShowForm(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  }, []);

  const nav = useRecordNavigation<SalesQuotationRow>({
    items: quotations,
    getId: (q) => q.id || 0,
    currentId: selectedId,
    onSelect: async (id) => {
      if (id === null) {
        resetForm();
        setShowForm(true);
      } else {
        await openQuotation(Number(id));
      }
    },
  });

  // رابط عميق: فتح عرض محدد عند وصول ?open=<id> (من شارة «عرض السعر» بالفاتورة).
  const location = useLocation();
  useEffect(() => {
    const mOpen = location.search.match(/[?&]open=(\d+)/);
    if (mOpen) {
      void openQuotation(Number(mOpen[1]));
      return;
    }
    const isNew = location.search.match(/[?&]action=new/);
    if (isNew) {
      setShowForm(true);
      setSelectedId(null);
      const mCust = location.search.match(/[?&]customer_id=(\d+)/);
      if (mCust) {
        setFormCustomer(mCust[1]);
      }
    }
  }, [location.search, openQuotation]);

  // طيّ/فتح معاينة البنود داخل القائمة — يجلب البنود عند أول فتح ويخزّنها.
  const toggleExpand = useCallback(async (id: number) => {
    setExpandedId((cur) => (cur === id ? null : id));
    if (expandedLines[id]) return;
    try {
      const detail = await getQuotation(id);
      const rows = (detail.lines || []).map((l) => {
        const pr = products.find((p) => String(p.id) === String(l.product));
        return {
          name: l.product_name || (pr ? formatProductPrimaryName(pr) : `#${l.product}`),
          quantity: l.quantity,
          unit_price: l.unit_price,
          line_total: l.line_total,
        };
      });
      setExpandedLines((prev) => ({ ...prev, [id]: rows }));
    } catch { /* تجاهل — تبقى الرسالة «جارٍ التحميل» ثم تُعاد المحاولة عند الطيّ/الفتح */ }
  }, [expandedLines, products]);

  // M4-T5: Kit keyboard shortcuts — real handlers.
  useKitKeymap({
    F2: () => window.print(),
    F5: () => loadQuotations(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-ktra-field="search"]');
      el?.focus();
    },
    F12: () => handleSave(),
    Escape: () => {
      if (showPartnerPicker) { setShowPartnerPicker(false); return; }
      setShowForm(false);
      setSelectedId(null);
    },
    plus: () => {
      if (document.activeElement?.getAttribute('data-ktra-key') === '1') {
        setShowPartnerPicker(true);
      }
    },
    // N0-T11: Ctrl+nav handlers
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => { setSelectedId(null); setShowForm(true); },
  });

  const loadQuotations = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const qs = await listQuotationsPage({ page, page_size: pageSize });
      setQuotations(qs.results || []);
      setTotalQuotations(qs.count);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [page]);

  const loadMasterData = useCallback(async () => {
    try {
      // task16 E17: منتقي المنتج في عرض السعر كان يحمّل شجرة الحسابات
      // (getAccounts) بدل المنتجات — يُصحَّح إلى منتجات المخزون (inventory/products).
      const tenantId = resolveTenantId();
      const [parts, prods, taxes] = await Promise.all([
        // T-PARTYPURE: عرض سعر بيع = زبائن فقط.
        accountingApi.getPartners("Customer") as Promise<Partner[]>,
        listPickerProducts<SqlProduct & { sale_price?: string; selling_price?: string }>(
          tenantId,
        ),
        // نسب ضريبة المبيعات — عمود «الضريبة» على البند مفتاحُها لا نسبتها.
        accountingApi.getTaxRates() as Promise<TaxRateRow[]>,
      ]);
      setPartners(parts || []);
      setTaxRates(
        (taxes || []).filter((t) => {
          const d = (t.direction || "both").toLowerCase();
          return d === "sales" || d === "both";
        }),
      );
      setProducts(
        (prods || []).map((p: any) => ({
          id: p.id,
          sku: p.sku || "",
          barcode: p.barcode,
          quantity_on_hand: String(p.available_quantity ?? p.quantity_on_hand ?? "0"),
          name_ar: p.name_ar || p.name || "",
          name_en: p.name_en || "",
          name: p.name_ar || p.name_en || p.name || p.sku || `#${p.id}`,
          unit_price: p.sale_price ?? p.selling_price ?? p.unit_price ?? "",
          // ISSUE #147 M4: كانت تُسقَط هنا فتصل شارة المخزون والسعر التقديري
          // معدومةً دائماً إلى المنتقي المدمج.
          stock_status: p.stock_status ?? null,
          is_service: p.is_service ?? false,
          indicative_purchase_price: p.indicative_purchase_price ?? null,
          indicative_purchase_price_source: p.indicative_purchase_price_source ?? null,
        }))
      );
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  }, []);

  useEffect(() => {
    void loadQuotations();
  }, [loadQuotations]);

  useEffect(() => { void loadMasterData(); }, [loadMasterData]);

  // T-ORDERS: صلاحية العرض وإظهار «حذف» من إعدادات الشركة (لا قيم مثبّتة بالكود).
  useEffect(() => {
    let alive = true;
    getSalesSettings()
      .then((st) => {
        if (!alive) return;
        setQuotationValidDays(Number(st.quotation_valid_days ?? 14));
        setAllowDelete(st.allow_document_delete !== false);
      })
      .catch(() => { /* الافتراضيات تكفي */ });
    return () => { alive = false; };
  }, []);

  /** T-ORDERS: العرض فعّال افتراضياً حتى (اليوم + أيام الإعداد، 14 يوماً). */
  const defaultValidUntil = useCallback((from?: string) => {
    if (!quotationValidDays) return "";
    const base = from ? new Date(from) : new Date();
    base.setDate(base.getDate() + quotationValidDays);
    return base.toISOString().slice(0, 10);
  }, [quotationValidDays]);

  const resetForm = () => {
    setSelectedId(null);
    // ISSUE #147 M4: عرضٌ جديد يبدأ صفحةً بيضاء — لا «تبديل زبون» يُعاد به تسعير شيء.
    prevCustomerRef.current = "";
    setFormCustomer("");
    setFormDate(new Date().toISOString().slice(0, 10));
    setFormValidUntil(defaultValidUntil());
    setFormNotes("");
    setFormDiscount("0");
    setFormLines([{
      id: undefined, product_id: "", product_name: "", quantity: "1", unit_price: "", discount: "0", tax_rate: "0", total: "0"
    }]);
    setTouched(false);
  };

  const handleAddLine = () => {
    markTouched();
    setFormLines([...formLines, {
      id: undefined, product_id: "", product_name: "", quantity: "1", unit_price: "", discount: "0", tax_rate: "0", total: "0"
    }]);
  };

  const handleRemoveLine = (idx: number) => {
    if (formLines.length > 1) {
      markTouched();
      setFormLines(formLines.filter((_, i) => i !== idx));
    }
  };

  const handleLineChange = (idx: number, field: string, value: string) => {
    // ISSUE #147 M4: تحرير السعر يدوياً يُلمَس فلا يُعاد تسعيره عند تبديل الزبون.
    if (field === "unit_price") { handleLineUpdate(idx, { unit_price: value, priceTouched: true }); return; }
    handleLineUpdate(idx, { [field]: value });
  };

  const handleLineUpdate = (idx: number, updates: Partial<LineState>) => {
    markTouched();
    setFormLines((prev) => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], ...updates };
      // Recalculate total
      const qty = Number(updated[idx].quantity) || 0;
      const price = Number(updated[idx].unit_price) || 0;
      const disc = Number(updated[idx].discount) || 0;
      // إجمالي السطر = الصافي بلا ضريبة — نفس ما يخزّنه الخادم في `line_total`،
      // فلا يتبدّل الرقم على الشاشة بعد الحفظ وإعادة الفتح. الضريبة وخصم
      // المستند يظهران في صندوق الإجماليات وحده.
      updated[idx].total = String(qty * price - disc);
      return updated;
    });
  };

  const handleSave = async () => {
    if (!formCustomer) {
      setErr("يرجى اختيار العميل");
      return;
    }
    // البنود بلا منتج تُستبعد؛ يجب وجود بند واحد صالح على الأقل.
    const validLines = formLines.filter((l) => l.product_id);
    if (validLines.length === 0) {
      setErr("أضف منتجاً واحداً على الأقل للعرض.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const body = {
        customer: Number(formCustomer),
        // N4-T6 new fields (backend may ignore unknown keys)
        is_active: formIsActive,
        prices_include_tax: formPricesIncludeTax,
        customer_address: formCustomerAddress || null,
        customer_tax_number: formCustomerTaxNumber || null,
        quotation_date: formDate,
        valid_until: formValidUntil || null,
        notes: formNotes,
        discount_amount: Number(formDiscount) || 0,
        lines: validLines.map((l) => ({
          product: Number(l.product_id),
          quantity: l.quantity,
          unit_price: l.unit_price,
          line_discount: l.discount,
          // tax_rate مفتاح أجنبي لنسبة ضريبة — 0/فارغ يعني «بلا ضريبة» ⇒ null (لا 0).
          tax_rate: l.tax_rate && Number(l.tax_rate) > 0 ? Number(l.tax_rate) : null,
        })),
      };
      if (selectedId) {
        await updateQuotation(selectedId, body);
      } else {
        await createQuotation(body);
      }
      resetForm();
      setShowForm(false);
      await loadQuotations();
      // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      void discardDraft();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  /** T-ORDERS: التحويل يختار وجهته — طلبية (تحجز الكمية) أو فاتورة. */
  const handleConvert = async (id: number, target: "invoice" | "order") => {
    setConvertId(null);
    try {
      const result = await convertQuotation(id, target);
      toast(
        target === "order"
          ? `تم التحويل — طلبية رقم ${result.order?.order_number ?? ""}`
          : `تم التحويل — فاتورة رقم ${result.invoice?.invoice_number ?? ""}`,
        "success",
      );
      await loadQuotations();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحويل");
    }
  };

  /** إلغاء بلا حذف — المستند وسجلّه يبقيان. */
  const handleCancel = async (id: number) => {
    if (!(await confirm({
      title: "إلغاء عرض السعر",
      message: "سيُعلَّم العرض «ملغى» ويبقى في السجل (لن يُحذف). متابعة؟",
      confirmText: "إلغاء العرض",
    }))) return;
    try {
      await cancelQuotation(id);
      toast("تم إلغاء العرض", "success");
      await loadQuotations();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الإلغاء");
    }
  };

  const handleDelete = async (id: number) => {
    if (!(await confirm({ title: "حذف عرض السعر", message: "هل أنت متأكد من حذف هذا العرض؟" }))) return;
    try {
      await deleteQuotation(id);
      await loadQuotations();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const statusLabel = (s: string) => {
    const map: Record<string, string> = {
      draft: "مسودة",
      sent: "مُرسل",
      accepted: "مقبول",
      rejected: "مرفوض",
      converted: "مُحوَّل",
      cancelled: "ملغى",
      expired: "منتهي الصلاحية",
    };
    return map[s] || s;
  };

  const statusColor = (s: string) => {
    const map: Record<string, string> = {
      draft: "ktra-bg-panel ktra-text-ink",
      sent: "ktra-bg-accent-bg ktra-text-accent",
      accepted: "bg-green-100 text-green-700",
      rejected: "ktra-bg-panel ktra-text-state",
      converted: "ktra-bg-panel ktra-text-ink",
      cancelled: "bg-amber-100 text-amber-700",
      expired: "ktra-bg-panel ktra-text-soft",
    };
    return map[s] || "ktra-bg-panel ktra-text-ink";
  };

  const lineDiscountTotal = formLines.reduce((sum, line) => sum + (Number(line.discount) || 0), 0);
  const grossSubtotal = formLines.reduce(
    (sum, line) => sum + (Number(line.quantity) || 0) * (Number(line.unit_price) || 0),
    0,
  );
  /** المفتاح ← النسبة المئوية؛ البند يحمل مفتاح نسبة الضريبة لا النسبة نفسها. */
  const taxRateMap = useMemo(() => {
    const map = new Map<number, number>();
    taxRates.forEach((rate) => map.set(rate.id, Number(rate.rate)));
    return map;
  }, [taxRates]);
  /**
   * إجماليات العرض من وحدة حساب الفاتورة نفسها (`computeInvoiceTotals`): خصم
   * المستند يُوزَّع على البنود ثم تُحسب الضريبة على الصافي المخصوم. مصدرٌ واحد
   * ⇒ لا ينحرف إجمالي العرض عن إجمالي فاتورته بعد التحويل.
   */
  const totals = useMemo(
    () =>
      computeInvoiceTotals(
        formLines.map<LineInput>((line) => ({
          quantity: line.quantity,
          unit_price: line.unit_price,
          line_discount: line.discount,
          tax_rate_id:
            line.tax_rate && Number(line.tax_rate) > 0 ? Number(line.tax_rate) : null,
        })),
        taxRateMap,
        formDiscount,
      ),
    [formLines, taxRateMap, formDiscount],
  );
  const selectedQuotation = quotations.find((quotation) => quotation.id === selectedId);

  /* ISSUE #121: مسودّة محلية (IndexedDB، issue #118) — هذه الشاشة لا تحفظ
   * شيئاً محلياً اليوم. الحمولة كائنٌ خفيف يكفي وحده لإعادة بناء الشاشة؛ لا
   * صلة بحمولة الحفظ الخادمية التي يبنيها `handleSave`. */
  const draftPayload = useMemo<SalesQuotationDraftPayload>(
    () => ({
      formCustomer,
      formDate,
      formValidUntil,
      formNotes,
      formIsActive,
      formPricesIncludeTax,
      formCustomerAddress,
      formCustomerTaxNumber,
      formDiscount,
      formLines,
    }),
    [
      formCustomer, formDate, formValidUntil, formNotes, formIsActive,
      formPricesIncludeTax, formCustomerAddress, formCustomerTaxNumber,
      formDiscount, formLines,
    ],
  );

  const onRestoreDraft = useCallback((restored: SalesQuotationDraftPayload) => {
    // ISSUE #147 M4: استعادةٌ ليست «تبديل زبون» يُعاد به تسعير شيء.
    prevCustomerRef.current = restored.formCustomer;
    setFormCustomer(restored.formCustomer);
    setFormDate(restored.formDate);
    setFormValidUntil(restored.formValidUntil);
    setFormNotes(restored.formNotes);
    setFormIsActive(restored.formIsActive);
    setFormPricesIncludeTax(restored.formPricesIncludeTax);
    setFormCustomerAddress(restored.formCustomerAddress);
    setFormCustomerTaxNumber(restored.formCustomerTaxNumber);
    setFormDiscount(restored.formDiscount);
    // ISSUE #147 M4 §B.7: سعرٌ من مسودّة مستعادة يُعامَل «ملموساً» — لا يجوز
    // أن يمحوه أول تبديل زبونٍ لاحق يظنّه سعراً تلقائياً لم يُقرَّر بعد.
    setFormLines(restored.formLines.map((l) => (l.product_id ? { ...l, priceTouched: true } : l)));
    // استعادةٌ من مسودّة تعني اختلافاً عن آخر نسخة محفوظة — تُسجَّل «ملموسة».
    setTouched(true);
  }, []);

  const draftApi = useDocumentDraft<SalesQuotationDraftPayload>({
    docType: "sales_quotation",
    docId: selectedId,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    // لا حقل `is_posted` حقيقي لعرض السعر — الحالتان النهائيتان («محوَّل»/«ملغى»)
    // تُعامَلان معاملة «مرحَّل»: اطّلاعٌ على المسودّة فقط بلا استعادةٍ تلقائية،
    // فمستندٌ انتهى أمره لا يُعاد فتحه لتعديل صامت.
    isPosted: !!selectedQuotation && (selectedQuotation.status === "converted" || selectedQuotation.status === "cancelled"),
    // ختمُ الخادم لحظةَ فتح المستند — كان المُسلسِل لا يكشف `updated_at`
    // فسقط فحصُ «تغيّر المستند بعد مسودتك» (#109 §٩)؛ كُشف ووُصِل.
    docUpdatedAt: selectedQuotation?.updated_at ?? null,
  });
  const { draftSavedAt, draftSaveFailed, discardDraft } = draftApi;

  /* ISSUE #120: الحارسُ مقلوب — يعترض المغادرةَ فقط إن فشل الحفظُ المحلّيّ فعلاً. */
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

  /** «تراجع» على شريط الاستعادة: يعيد الشاشة إلى حالتها المحفوظة ويمسح المسودّة. */
  const handleUndoDraft = useCallback(() => {
    if (selectedId != null) void openQuotation(selectedId);
    else resetForm();
    void discardDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, discardDraft]);

  // DOC-SHARE: نافذة واحدة تخدم الفرعين (المحرّر والقائمة). عرضٌ ما زال
  // مسودة: إنشاء الرابط هو إرساله فعلياً، والنافذة تُنبّه قبل الضغط.
  const sharedQuotation = quotations.find((quotation) => quotation.id === shareId);
  const shareModal = shareId != null ? (
    <ShareDocumentModal
      open
      onClose={() => setShareId(null)}
      docType="sales_quotation"
      docId={shareId}
      docLabel={`عرض سعر ${sharedQuotation?.quotation_number ?? ""}`.trim()}
      partyName={sharedQuotation?.customer_name || undefined}
      warnDraftWillBeSent={sharedQuotation?.status === "draft"}
      onShared={() => void loadQuotations()}
    />
  ) : null;
  const toolbarActions: CommercialToolbarAction[] = [
    {
      key: "save",
      label: saving ? "جاري الحفظ…" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: saving ? undefined : () => void handleSave(),
      disabled: saving,
    },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: () => { setShowForm(false); setSelectedId(null); },
      danger: true,
      separatorBefore: true,
    },
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => window.print() },
    // DOC-SHARE: الرابط يشير إلى صفٍّ محفوظ — عرضٌ لم يُحفظ بعد لا رابط له.
    {
      key: "share",
      label: "مشاركة",
      icon: <Share2 />,
      disabled: selectedId == null,
      onClick: () => setShareId(selectedId),
    },
  ];
  const headerFields: CommercialHeaderField[] = [
    {
      key: "number",
      label: "رقم العرض",
      control: <input className="ktra-input ktra-input--hl" readOnly
        value={selectedQuotation?.quotation_number || (selectedId ? `#${selectedId}` : "تلقائي")} />,
    },
    {
      key: "date",
      label: "التاريخ",
      control: <input className="ktra-input" type="date" value={formDate}
        onChange={(event) => { markTouched(); setFormDate(event.target.value); }} />,
    },
    {
      key: "validUntil",
      label: "صالح حتى",
      control: <input className="ktra-input" type="date" value={formValidUntil}
        onChange={(event) => { markTouched(); setFormValidUntil(event.target.value); }} />,
    },
    {
      key: "type",
      label: "نوع المستند",
      control: <input className="ktra-input" readOnly value="عرض سعر صادر للزبون" />,
    },
    {
      key: "customer",
      label: "الزبون / الحساب",
      control: (
        <select className="ktra-input" value={formCustomer}
          onChange={(event) => { markTouched(); setFormCustomer(event.target.value); }} data-ktra-key="1">
          <option value="">— اختر الزبون —</option>
          {partners.map((partner) => (
            <option key={partner.id} value={partner.id}>{partner.name}</option>
          ))}
        </select>
      ),
    },
    {
      key: "customerName",
      label: "الاسم",
      control: <input className="ktra-input" readOnly
        value={partners.find((partner) => String(partner.id) === formCustomer)?.name || ""} />,
    },
    {
      key: "address",
      label: "عنوان الزبون",
      control: <input className="ktra-input" data-testid="quotation-customer-address" value={formCustomerAddress}
        onChange={(event) => { markTouched(); setFormCustomerAddress(event.target.value); }} />,
    },
    {
      key: "taxNumber",
      label: "الرقم الضريبي",
      control: <input className="ktra-input font-mono" value={formCustomerTaxNumber}
        onChange={(event) => { markTouched(); setFormCustomerTaxNumber(event.target.value); }} />,
    },
    {
      key: "status",
      label: "الحالة",
      control: <input className="ktra-input" readOnly
        value={selectedQuotation ? statusLabel(selectedQuotation.status) : "مسودة"} />,
    },
  ];
  const editorColumns: CommercialLineColumn<LineState>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    {
      /* ISSUE #147 M4: كانت هذه الخلية زرّاً يفتح المودال العريض وحده — مسارٌ
         مختلف عن كل شاشة بيع أخرى (فاتورة البيع). الآن نفس `KitAutocomplete`
         المشترك: كتابة ← قائمة مرشَّحة تحمل سعر هذا الزبون بمصدره، مع (i)
         لبطاقة المنتج وقلمٍ لتعديله سريعاً. المودال العريض يبقى خلف أيقونة
         البحث لمن يريد الفهرس الكامل — لا يُحذف. */
      key: "name",
      header: "وصف المنتج",
      width: "35%",
      render: (line, index) => (
        <div className="flex w-full items-center gap-1">
          <KitAutocomplete
            value={line.product_name || ""}
            options={itemOptions}
            placeholder="اكتب اسم المنتج…"
            onPick={(id) => {
              const pid = Number(id);
              const product = products.find((item) => item.id === pid);
              const cp = formCustomer ? customerPriceMap.get(pid) : undefined;
              handleLineUpdate(index, {
                product_id: String(pid),
                product_name: product ? formatProductPrimaryName(product) : `#${pid}`,
                // ISSUE #147 §B.4: لا رتبة سعرٍ لهذا الزبون ⇒ فارغ، لا صفر ولا سعرٌ عام مخمَّن.
                unit_price: cp ? cp.price : "",
                // منتجٌ جديد على السطر ⇒ سعرٌ تلقائيٌّ جديد لم يلمسه أحد بعد.
                priceTouched: false,
              });
            }}
            onInfo={(id) => setCardProductId(Number(id))}
            onEdit={(id) => setQuickEditProductId(Number(id))}
            onShowMore={(q) => { setPickerQuery(q); setProductPickerLineIdx(index); }}
            onFreeText={(text) => { setQuickCreateName(text); setQuickCreateLineIdx(index); }}
            createLabel={(text) => `إضافة «${text}» كمنتج جديد`}
          />
          {/* بطاقة المنتج المشتركة: التكلفة وسعر البيع وآخر سعر شراء/بيع والربح
              وحركة الصنف — نفس البطاقة التي في فاتورة البيع، فلا يُسعَّر العرض
              على العمياء. */}
          {line.product_id && Number(line.product_id) > 0 && (
            <button type="button" className="ktra-iconbtn"
              title="بطاقة المنتج — التكلفة والأسعار"
              onClick={() => setCardProductId(Number(line.product_id))}>
              <Info className="h-3.5 w-3.5" />
            </button>
          )}
          <button type="button" className="ktra-iconbtn"
            title="فهرس المنتجات الكامل"
            onClick={() => setProductPickerLineIdx(index)}>
            <Search className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
    { key: "quantity", header: "الكمية", width: "90px", align: "center", type: "number" },
    { key: "unit_price", header: "سعر الوحدة", width: "110px", align: "center", type: "number" },
    /* «خصم البند» صراحةً — تمييزاً له عن «الخصم» في صندوق الإجماليات (خصم العرض كلّه). */
    { key: "discount", header: "خصم البند", width: "90px", align: "center", type: "number" },
    {
      /* الحقل مفتاح `TaxRate` لا نسبة مئوية: كتابة «16» كانت تعني «النسبة رقم 16»
         فتُحفظ نسبةٌ أخرى (أو يُرفض الحفظ)، والشاشة تحسب 16% وهماً. المنتقي
         يمنع الأمرين معاً. */
      key: "tax_rate",
      header: "الضريبة",
      width: "130px",
      align: "center",
      render: (line, index) => (
        <select
          className="ktra-input"
          value={line.tax_rate && Number(line.tax_rate) > 0 ? line.tax_rate : ""}
          onChange={(event) => handleLineChange(index, "tax_rate", event.target.value || "0")}
        >
          <option value="">بدون</option>
          {taxRates.map((rate) => (
            <option key={rate.id} value={rate.id}>{rate.name} ({rate.rate}%)</option>
          ))}
        </select>
      ),
    },
    { key: "total", header: "الإجمالي", width: "110px", align: "center", readOnly: true },
    {
      key: "del",
      header: "",
      width: "36px",
      align: "center",
      render: (_line, index) => (
        <button type="button" className="ktra-iconbtn ktra-iconbtn--danger"
          onClick={() => handleRemoveLine(index)} title="حذف السطر">
          <Trash2 className="h-3 w-3" />
        </button>
      ),
    },
  ];
  const listColumns: CommercialListColumn<SalesQuotationRow>[] = [
    {
      key: "quotation_number",
      header: "رقم العرض",
      width: "130px",
      render: (quotation) => (
        <button type="button" className="ktra-text-accent hover:underline"
          onClick={() => void toggleExpand(quotation.id)}>
          {expandedId === quotation.id ? "▾ " : "▸ "}{quotation.quotation_number}
        </button>
      ),
    },
    { key: "customer", header: "الزبون", render: (quotation) => <>{quotation.customer_name || "—"}</> },
    { key: "date", header: "التاريخ", width: "110px", render: (quotation) => <>{quotation.quotation_date}</> },
    { key: "valid", header: "صالحة حتى", width: "110px", render: (quotation) => <>{quotation.valid_until || "—"}</> },
    { key: "total", header: "الإجمالي", width: "120px", numeric: true,
      render: (quotation) => <>{Number(quotation.grand_total).toLocaleString()}</> },
    {
      key: "status",
      header: "الحالة",
      width: "110px",
      render: (quotation) => (
        <span className={`rounded px-2 py-0.5 text-xs ${statusColor(quotation.status)}`}>
          {statusLabel(quotation.status)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "210px",
      render: (quotation) => (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button onClick={() => void openQuotation(quotation.id)} className="ktra-text-accent hover:underline">تعديل</button>
          <button onClick={() => setShareId(quotation.id)} className="text-blue-600 hover:underline">مشاركة</button>
          {quotation.status !== "converted" && quotation.status !== "cancelled" && (
            <>
              <button onClick={() => setConvertId(quotation.id)} className="text-green-600 hover:underline">تحويل</button>
              <button onClick={() => void handleCancel(quotation.id)} className="text-amber-600 hover:underline">إلغاء</button>
            </>
          )}
          {allowDelete && (
            <button onClick={() => void handleDelete(quotation.id)} className="ktra-text-state hover:underline">حذف</button>
          )}
        </div>
      ),
    },
  ];

  if (showForm) {
    return (
      <CommercialDocumentEditor<LineState>
        title="عرض سعر بيع"
        state={selectedQuotation ? `${statusLabel(selectedQuotation.status)} — ${selectedQuotation.quotation_number}` : "مسودة — عرض جديد"}
        nav={nav}
        actions={toolbarActions}
        headerFields={headerFields}
        lines={formLines}
        lineColumns={editorColumns}
        getLineCell={(line, key) => {
          const index = formLines.indexOf(line);
          if (key === "seq") return index + 1;
          if (key === "quantity") return line.quantity;
          if (key === "unit_price") return line.unit_price;
          if (key === "discount") return line.discount;
          if (key === "tax_rate") return line.tax_rate;
          if (key === "total") return formatMoney(line.total);
          return "";
        }}
        getLineKey={(line, index) => line.id ?? `new-${index}`}
        onLineChange={(index, key, value) => handleLineChange(index, key, value)}
        onAddLine={handleAddLine}
        banner={
          <>
            <DocumentDraftBanners draft={draftApi} onApplyDraft={onRestoreDraft} onUndo={handleUndoDraft} isTouched={touched} />
            {err ? <div className="ktra-banner ktra-banner--err">{err}</div> : null}
          </>
        }
        tabs={[
          {
            key: "notes",
            label: "الملاحظات",
            content: <div className="px-1 py-2">
              <textarea className="ktra-input w-full" rows={4} value={formNotes}
                onChange={(event) => { markTouched(); setFormNotes(event.target.value); }} placeholder="ملاحظات العرض…" />
            </div>,
          },
          {
            key: "settings",
            label: "إعدادات العرض",
            content: <div className="flex flex-wrap gap-4 px-1 py-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={formIsActive}
                  onChange={(event) => { markTouched(); setFormIsActive(event.target.checked); }} />
                العرض فعّال
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={formPricesIncludeTax}
                  onChange={(event) => { markTouched(); setFormPricesIncludeTax(event.target.checked); }} />
                الأسعار تشمل ض.ق.م
              </label>
              {formValidUntil && new Date(formValidUntil) < new Date() && (
                <span className="text-xs font-semibold ktra-text-state">منتهي الصلاحية</span>
              )}
            </div>,
          },
        ]}
        totals={
          <>
            <div className="ktra-total-row"><span>مجموع البنود</span><span className="ktra-total-value">{formatMoney(grossSubtotal)}</span></div>
            {/* خصم البنود يبقى مقروءاً حين يوجد — كي لا يُخلط بخصم العرض. */}
            {lineDiscountTotal > 0 && (
              <div className="ktra-total-row"><span>خصم البنود</span><span className="ktra-total-value">{formatMoney(lineDiscountTotal)}</span></div>
            )}
            {/* خصم العرض (خصم المستند) — يُكتب هنا ويسبق الضريبة، كما في الفاتورة. */}
            <div className="ktra-total-row">
              <span>الخصم</span>
              <input
                className="ktra-input ktra-total-input"
                type="number"
                step="0.01"
                min="0"
                value={formDiscount}
                onChange={(event) => { markTouched(); setFormDiscount(event.target.value); }}
                title="خصم على العرض كلّه — لخصم بندٍ بعينه استعمل عمود «الخصم» في السطر"
              />
            </div>
            {Number(formDiscount) > 0 && (
              <div className="ktra-total-row"><span>بعد الخصم</span><span className="ktra-total-value">{formatMoney(totals.subtotalExclTax)}</span></div>
            )}
            <div className="ktra-total-row"><span>الضريبة</span><span className="ktra-total-value">{formatMoney(totals.taxAmount)}</span></div>
            <div className="ktra-total-row ktra-total-row--grand"><span>إجمالي العرض</span><span className="ktra-total-value">{formatMoney(totals.grandTotal)}</span></div>
          </>
        }
        status={<>
          <span className="ktra-status-item">عدد المنتجات <b>{formLines.length}</b></span>
          <span className="ktra-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
          {/* issue #109 §٦: مؤشّر دائم — لا حفظٌ خادميّ فوريّ في هذه الشاشة. */}
          {draftSavedAt && (
            <span className="ktra-status-item" data-testid="draft-saved-indicator">
              مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
            </span>
          )}
        </>}
        overlay={<>
          {shareModal}
          {cardProductId != null && (
            <ProductCardModal
              productId={cardProductId}
              productName={products.find((item) => item.id === cardProductId)?.name}
              onClose={() => setCardProductId(null)}
            />
          )}
          {quickEditProductId != null && (
            <ItemQuickEditModal
              productId={quickEditProductId}
              onClose={() => setQuickEditProductId(null)}
              onSaved={applyProductUpdate}
              onOpenFullCard={() => openInNewTab(productProfilePath(quickEditProductId))}
            />
          )}
          {/* ISSUE #147 US48: النصّ المكتوب بلا تطابق يصبح منتجاً حقيقياً —
              الحقل مفتاحٌ أجنبي إجباري هنا، خلافاً لبند الشراء النصّي الحر. */}
          {quickCreateLineIdx !== null && (
            <ItemQuickCreateModal
              isOpen
              initialName={quickCreateName}
              onClose={() => setQuickCreateLineIdx(null)}
              onSaved={(created: any) => {
                const idx = quickCreateLineIdx;
                setQuickCreateLineIdx(null);
                if (!created?.id) return;
                const mapped: Product = {
                  id: created.id,
                  sku: created.sku || "",
                  barcode: created.barcode,
                  quantity_on_hand: String(created.quantity_on_hand ?? "0"),
                  name_ar: created.name_ar || created.name || "",
                  name_en: created.name_en || "",
                  name: created.name_ar || created.name_en || created.sku || `#${created.id}`,
                  unit_price: created.sale_price ?? created.selling_price ?? "",
                  stock_status: created.stock_status ?? null,
                  is_service: created.is_service ?? false,
                  indicative_purchase_price: created.indicative_purchase_price ?? null,
                  indicative_purchase_price_source: created.indicative_purchase_price_source ?? null,
                };
                setProducts((prev) => [...prev, mapped]);
                // الشاشة الأم تحمل قائمة المنتجات — نُعلمها كي تُحدّثها من الخادم.
                try { eventBus.publish("products", resolveTenantId()); } catch { /* غير حرج */ }
                // نفس مدخل onPick تماماً — بما في ذلك بحث سعر هذا الزبون (سيعود
                // فارغاً حكماً لمنتجٍ جديد، لا صفراً: القرار §B.4).
                const cp = formCustomer ? customerPriceMap.get(created.id) : undefined;
                if (idx !== null) {
                  handleLineUpdate(idx, {
                    product_id: String(created.id),
                    product_name: mapped.name,
                    unit_price: cp ? cp.price : "",
                    priceTouched: false,
                  });
                }
              }}
            />
          )}
          {productPickerLineIdx !== null ? (
          <SalesProductPickerModal
            isOpen
            products={products}
            // T-SEARCH: يفتح على نفس ما كتبه المستخدم — «+N أخرى» ينقل الاستعلام
            // بدل أن يبدأ من صفحة بيضاء (نفس فاتورة البيع).
            initialSearch={pickerQuery}
            onSelect={(productId) => {
              const product = products.find((item) => item.id === productId);
              const cp = formCustomer ? customerPriceMap.get(productId) : undefined;
              handleLineUpdate(productPickerLineIdx, {
                product_id: String(productId),
                priceTouched: false,
                ...(product ? {
                  product_name: formatProductPrimaryName(product),
                  // ISSUE #147 §B.4: لا رتبة سعرٍ لهذا الزبون ⇒ فارغ، لا سعرٌ عام مخمَّن.
                  unit_price: cp ? cp.price : "",
                } : {}),
              });
              setProductPickerLineIdx(null);
            }}
            onClose={() => setProductPickerLineIdx(null)}
          />
          ) : null}
        </>}
      />
    );
  }

  const detailPanel = expandedId != null ? (
    <div className="border-t ktra-border-soft p-3">
      {!expandedLines[expandedId] ? (
        <div className="text-xs ktra-text-soft">جارٍ تحميل البنود…</div>
      ) : expandedLines[expandedId].length === 0 ? (
        <div className="text-xs ktra-text-soft">لا بنود في هذا العرض.</div>
      ) : (
        <table className="ktra-grid text-xs" data-variant="list">
          <thead><tr><th>المنتج</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr></thead>
          <tbody>
            {expandedLines[expandedId].map((line, index) => (
              <tr key={index}>
                <td>{line.name}</td>
                <td>{formatQuantity(line.quantity)}</td>
                <td>{Number(line.unit_price).toLocaleString()}</td>
                <td>{Number(line.line_total).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  ) : undefined;

  return (
    <>
      {/* issue #146: اليتامى يُبحث عنها هنا — قبل فتح أي نموذج، لا داخله وحده. */}
      <DocumentDraftBanners
        draft={draftApi}
        onApplyDraft={(payload) => { onRestoreDraft(payload); setShowForm(true); }}
        onUndo={handleUndoDraft}
        isTouched={touched}
      />
      <CommercialDocumentsList<SalesQuotationRow>
        title="عروض وطلبيات البيع"
        state="عروض الأسعار"
        rows={quotations}
        columns={listColumns}
        getRowKey={(quotation) => quotation.id}
        loading={loading}
        error={err}
        emptyHint="لا توجد عروض"
        countLabel={`${quotations.length} من ${totalQuotations} عرض`}
        onNew={() => { resetForm(); setShowForm(true); }}
        onReload={() => void loadQuotations()}
        newLabel="عرض جديد"
        nav={nav}
        onRowDoubleClick={(quotation) => void openQuotation(quotation.id)}
        pagination={totalQuotations > pageSize ? {
          page,
          pageSize,
          total: totalQuotations,
          onChange: setPage,
        } : undefined}
        detailPanel={detailPanel}
      />
      {convertId != null && (
        <ConvertTargetDialog
          title="تحويل عرض السعر"
          onPick={(target) => void handleConvert(convertId, target)}
          onClose={() => setConvertId(null)}
        />
      )}
      {shareModal}
    </>
  );
};

export const SalesDocumentsPage: React.FC<{
  initialTab?: "quotations" | "orders";
}> = ({ initialTab = "quotations" }) => {
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => setActiveTab(initialTab), [initialTab]);

  return (
    <div dir="rtl" className="flex h-full min-h-0 flex-col gap-3 p-3">
      <div className="flex w-fit items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1">
        <button
          type="button"
          onClick={() => setActiveTab("quotations")}
          className={`rounded-md px-4 py-2 text-sm font-semibold ${
            activeTab === "quotations"
              ? "bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
              : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
          }`}
        >
          عروض الأسعار
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("orders")}
          className={`rounded-md px-4 py-2 text-sm font-semibold ${
            activeTab === "orders"
              ? "bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
              : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
          }`}
        >
          طلبيات الزبائن
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {activeTab === "quotations" ? <SalesQuotationsPage /> : <SalesOrdersPage />}
      </div>
    </div>
  );
};
