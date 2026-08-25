/**
 * N5-T4 — ItemForm (F6) — inside-out نمط Kit مع 6 صفحات
 * المرجع: المخازن.txt:11-25، القالب: SalesInvoiceEditor.tsx
 *
 * كرت الصنف الموحّد: صار هذا المكوّن هو الكرت الوحيد — الإضافة والتعديل والعرض.
 * تبويبات «نظرة عامة» و«الفواتير المرتبطة» و«حركة المخزون» تأتي من
 * `useProductInsights` (كانت حبيسة صفحة `ProductProfilePage` المنفصلة).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct } from "../../types/inventory";
import {
  KitDocumentShell,
  useKitKeymap,
  useRecordNavigation,
  type KitToolbarAction,
} from "../kit";
import { Plus, Save, Trash2, X, Loader2, AlertCircle, CheckCircle2, Upload, FileText } from "lucide-react";
import { CategoryPicker } from "../inventory/CategoryPicker";
import { ValuePicker } from "../inventory/ValuePicker";
import { accountingApi } from "../../services/accountingApi";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import type { AccountNodeLike } from "../../utils/accountTree";
import { cloudinaryService } from "../../services/cloudinaryService";
import { usePasteZone } from "../../utils/clipboardImage";
import { useProductInsights } from "./ProductInsightTabs";
import { SupplierCodesTab } from "./SupplierCodesTab";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { completeEan13, ean13Svg, isValidEan13, printBarcodeLabels } from "../../utils/barcode";

type Props = {
  productId: number | null;
  duplicateId?: number | null;
  /** سجلّات التنقّل (Ctrl+PgUp/PgDn) — تُترك فارغة حين يُفتح الكرت بمساره المباشر. */
  products: SqlProduct[];
  onSaved: () => void;
  onCancel: () => void;
  /** أزرار إضافية على الشريط (مثل «تكلفة المنتجات» حين يُفتح الكرت كصفحة). */
  extraActions?: KitToolbarAction[];
  /** نصّ زر الإلغاء — «عودة» حين يكون الكرت صفحة قائمة بذاتها. */
  cancelLabel?: string;
  /** التبويب الابتدائي (روابط «ذكر لمنتج» تفتح حركة المخزون مباشرةً). */
  initialTab?: string;
};

type CategoryNode = { id: number; name: string; parent: number | null };

/** شريحة سعر — العملة معرّفٌ من جدول العملات لا رمزٌ نصّي (الخادم يريد PK). */
type PriceTier = { price: string; currency: number | null; tax_inclusive: boolean };
const blankTier = (): PriceTier => ({ price: "", currency: null, tax_inclusive: false });

const TIER_COUNT = 5;
const numOrNull = (v: unknown): number | null =>
  v == null || v === "" ? null : Number(v);

type ServerTier = {
  tier_type: string; tier_number: number;
  price: string | number; currency: number; tax_inclusive?: boolean;
};

/** صفوف الخادم المسطّحة ← خمس شرائح مرتّبة بالرقم (الفجوات تبقى فارغة). */
const tiersFromServer = (raw: unknown, type: "sale" | "purchase"): PriceTier[] => {
  const rows = Array.isArray(raw) ? (raw as ServerTier[]) : [];
  const out = Array.from({ length: TIER_COUNT }, blankTier);
  for (const row of rows) {
    if (row?.tier_type !== type) continue;
    const index = Number(row.tier_number) - 1;
    if (index < 0 || index >= TIER_COUNT) continue;
    out[index] = {
      price: row.price != null ? String(row.price) : "",
      currency: numOrNull(row.currency),
      tax_inclusive: Boolean(row.tax_inclusive),
    };
  }
  return out;
};

/**
 * الشرائح ← حمولة الخادم. الشريحة بلا سعرٍ موجب أو بلا عملة **تُحذف**: الخادم
 * يعتبر الحمولة وصفاً للحالة النهائية، والصفّ الفارغ ليس سعراً بل غياب سعر.
 */
const tiersToPayload = (
  sale: PriceTier[], purchase: PriceTier[],
): Array<Record<string, unknown>> => {
  const out: Array<Record<string, unknown>> = [];
  const push = (tiers: PriceTier[], type: "sale" | "purchase") => {
    tiers.forEach((tier, index) => {
      const price = tier.price.trim();
      if (!price || Number(price) <= 0 || tier.currency == null) return;
      out.push({
        tier_type: type, tier_number: index + 1,
        price: Number(price), currency: tier.currency,
        tax_inclusive: tier.tax_inclusive,
      });
    });
  };
  push(sale, "sale");
  push(purchase, "purchase");
  return out;
};

// الداتا شيت: المحفوظ له id (للحذف من SQL/Cloudinary)، والمرفوع حديثاً id=null.
type DatasheetRef = { id: number | null; url: string };

// الداتا شيت يقبل PDF وصوراً معاً، ولا يُحتفَظ بنوع MIME بعد الرفع — فالامتداد في
// الرابط هو ما يميّز الصورة، لتُعرض مصغَّرةً بدل اسم ملفٍ لا يقول شيئاً عن محتواه.
const IMAGE_URL_PATTERN = /\.(png|jpe?g|gif|webp|bmp|svg)(\?|#|$)/i;
const isImageUrl = (url: string): boolean => IMAGE_URL_PATTERN.test(url);
const extractDatasheets = (p: Record<string, unknown>): DatasheetRef[] =>
  Array.isArray(p.attachments)
    ? (p.attachments as Array<{ id?: number; file_path?: string; file_type?: string }>)
        .filter((a) => a?.file_type === "Datasheet" && a?.file_path)
        .map((a) => ({ id: typeof a.id === "number" ? a.id : null, url: a.file_path as string }))
    : [];

type FormState = {
  sku: string; name_ar: string; name_en: string;
  brand: string;
  /** T-REORDER: «النوع» — موديلات النوع الواحد بدائلُ بعضها في البيع والطلب. */
  variant_group: string;
  /** T-SERIAL: باركود الصنف (EAN-13) — فريد داخل الشركة، يحرسه الخادم. */
  barcode: string;
  /** T-SERIAL: تتبّع وحدات الصنف بأرقام تسلسلية. */
  is_serialized: boolean;
  /** THA-24: سياسة كفالة الزبون بالأشهر — فارغ = بلا كفالة، فلا بطاقة تلقائية. */
  warranty_months: string;
  /** THA-24: كفالة المورد لنا بالأشهر — تُحسب من تاريخ فاتورة الشراء. */
  supplier_warranty_months: string;
  /** بيانٌ داخلي — منفصل عن وصف المتجر الذي يراه العالم. */
  description: string;
  /** موقع التخزين (رفّ/ممر) — إرشادي بلا أثر مخزني. */
  storage_location: string;
  /** وحدة القياس — معرّفٌ من جدول الوحدات لا نصّ حرّ: النصّ لم يكن يُحفظ أصلاً. */
  uom_id: number | null;
  uom2: number | null; uom2_factor: string;
  uom3: number | null; uom3_factor: string;
  min_stock_level: string; max_stock_level: string;
  /** سعر البيع الافتراضي المحفوظ على الصنف (بجانب سعر التكلفة المحسوب). */
  sale_price: string;
  sale_tiers: PriceTier[];
  purchase_tiers: PriceTier[];
  sale_account: number | null; sale_return_account: number | null;
  purchase_account: number | null; purchase_return_account: number | null;
  supplier_account: number | null; ending_inventory_account: number | null;
  category: number | null; category_name: string; item_type: string;
  datasheets: DatasheetRef[];
};

const blankForm = (): FormState => ({
  sku: "", name_ar: "", name_en: "",
  brand: "",
  variant_group: "",
  barcode: "", is_serialized: false,
  warranty_months: "", supplier_warranty_months: "",
  description: "", storage_location: "",
  uom_id: null, uom2: null, uom2_factor: "",
  uom3: null, uom3_factor: "",
  min_stock_level: "", max_stock_level: "",
  sale_price: "",
  sale_tiers: Array.from({ length: 5 }, blankTier),
  purchase_tiers: Array.from({ length: 5 }, blankTier),
  sale_account: null, sale_return_account: null,
  purchase_account: null, purchase_return_account: null,
  supplier_account: null, ending_inventory_account: null,
  category: null, category_name: "", item_type: "goods",
  datasheets: [],
});

const fld = (label: string, node: React.ReactNode, span?: number) => (
  <label className="ktra-field" style={span ? { gridColumn: `span ${span}` } : {}}>
    <span className="ktra-field-label">{label}</span>
    {node}
  </label>
);

const ITEM_TYPES = [
  { v: "goods", l: "بضاعة" }, { v: "service", l: "خدمات" },
  { v: "work", l: "عمل" }, { v: "asset", l: "أصل" },
  { v: "composite", l: "تجميعي" },
];

export const ItemForm: React.FC<Props> = ({
  productId, duplicateId, products, onSaved, onCancel, extraActions = [], cancelLabel = "إلغاء",
  initialTab,
}) => {
  const [form, setForm] = useState<FormState>(blankForm());
  const [currentId, setCurrentId] = useState<number | null>(productId);
  // الجزء القرائي من الكرت (نظرة عامة/فواتير/حركة/أرقام تسلسلية) — يتبع الصنف المعروض.
  const insights = useProductInsights(currentId, { isSerialized: form.is_serialized });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lastKey, setLastKey] = useState("—");
  const [dsUploading, setDsUploading] = useState(false);
  const datasheetRef = useRef<HTMLDivElement>(null);
  // T-ITEMS M1: الكشف التدريجي — «بيانات عامة» تفتح على الحقول التي تلزم كل
  // صنف، وما دونها خلف زرٍّ واحد. المستخدم المتقدّم يفتحه مرّةً ويبقى مفتوحاً
  // ما دام الكرت مفتوحاً.
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [uoms, setUoms] = useState<Array<{ id: number; name_ar: string; name_en: string; code: string }>>([]);
  const [categories, setCategories] = useState<CategoryNode[]>([]);

  const [currencies, setCurrencies] = useState<Array<{ CurrencyID: number; CurrencyCode: string }>>([]);
  const [accounts, setAccounts] = useState<AccountNodeLike[]>([]);

  useEffect(() => {
    inventoryApi.getUoms().then(setUoms).catch(() => setUoms([]));
    // العملات لشرائح الأسعار، والحسابات لتجاوزات الترحيل — كلاهما صار يُحفظ.
    accountingApi.getCurrencies().then(setCurrencies).catch(() => setCurrencies([]));
    accountingApi.getAccounts().then(setAccounts).catch(() => setAccounts([]));
  }, []);

  // مسار التصنيف المختار — يُعرض قبل الحفظ («سيُحفظ تحت: أ ‹ ب») كي لا يبقى
  // موضع الصنف في الشجرة مفاجأةً تُكتشف بعد الحفظ.
  const loadCategories = useCallback(() => {
    inventoryApi.getCategories().then(setCategories).catch(() => setCategories([]));
  }, []);
  useEffect(() => { loadCategories(); }, [loadCategories]);

  const categoryPath = React.useMemo(() => {
    if (form.category == null) return null;
    const byId: Record<number, CategoryNode> = {};
    for (const c of categories) byId[c.id] = c;
    const names: string[] = [];
    const seen = new Set<number>();
    let node: CategoryNode | undefined = byId[form.category];
    // الصعود محروسٌ بـ`seen`: بياناتٌ قديمة قد تحمل حلقةً سبقت حارس الخادم.
    while (node && !seen.has(node.id)) {
      seen.add(node.id);
      names.unshift(node.name);
      node = node.parent != null ? byId[node.parent] : undefined;
    }
    return names.length ? names.join(" ‹ ") : (form.category_name || null);
  }, [form.category, form.category_name, categories]);

  const uploadDatasheetFile = async (file: File) => {
    setDsUploading(true); setErr(null); setMsg(null);
    try {
      const url = await cloudinaryService.uploadFile(file);
      setForm((f) => ({ ...f, datasheets: [...f.datasheets, { id: null, url }] }));
      setMsg("تم رفع الملف — احفظ (F12) لتخزين الرابط.");
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : "فشل رفع الملف");
    } finally {
      setDsUploading(false);
    }
  };

  const handleDatasheetUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    await uploadDatasheetFile(file);
  };

  // لصق صورة من الحافظة (Ctrl+V) بدل رفعها كملف — المنطقة معرَّفة بحقل الداتا شيت
  // نفسه، واللصق في أي مكان آخر من الكرت يصلها أيضاً (لا منطقة أخرى تزاحمها).
  usePasteZone(datasheetRef, (files) => { void uploadDatasheetFile(files[0]); }, { enabled: !dsUploading });

  const handleDatasheetRemove = async (index: number) => {
    const item = form.datasheets[index];
    if (!item) return;
    // المحفوظ (له id) يُحذف من الخادم (SQL + Cloudinary)؛ المرفوع حديثاً يُزال من القائمة فقط.
    if (item.id != null && currentId != null) {
      try {
        await inventoryApi.removeDatasheet(currentId, item.id);
      } catch (ex: unknown) {
        setErr(ex instanceof Error ? ex.message : "فشل حذف الملف");
        return;
      }
    }
    setForm((f) => ({ ...f, datasheets: f.datasheets.filter((_, j) => j !== index) }));
  };

  const patch = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  // ── T-SERIAL: الباركود ─────────────────────────────────────────────────
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const [labelCopies, setLabelCopies] = useState("1");
  const barcodeValue = form.barcode.trim();
  const barcodeValid = isValidEan13(barcodeValue);

  /** رقم كتبه المستخدم → EAN-13 كامل. القاعدة محلّية: خانة التحقق حسابٌ لا استعلام. */
  const handleCompleteBarcode = () => {
    const out = completeEan13(form.barcode);
    if (!out) { setErr("اكتب رقماً أولاً، أو استخدم «توليد تلقائي»."); return; }
    setErr(null);
    patch("barcode", out.code);
    setMsg(`${out.note} احفظ (F12) لتثبيته على الصنف.`);
  };

  /** رقم عشوائي غير مستخدم — خادمي عمداً: التفرّد يُفحص على قاعدة البيانات لا على الشاشة. */
  const handleGenerateBarcode = async () => {
    setBarcodeBusy(true); setErr(null); setMsg(null);
    try {
      const barcode = await inventoryApi.generateBarcode();
      patch("barcode", barcode);
      setMsg("وُلِّد باركود غير مستخدم — احفظ (F12) لتثبيته على الصنف.");
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : "تعذّر توليد الباركود");
    } finally {
      setBarcodeBusy(false);
    }
  };

  const handlePrintLabels = () => {
    if (!barcodeValid) { setErr("لا يمكن طباعة ملصق بلا باركود صالح."); return; }
    const ok = printBarcodeLabels([{
      barcode: barcodeValue,
      name: form.name_ar || form.name_en || form.sku || "—",
      sku: form.sku || null,
      price: formatMoney(insights.profile?.effective_sale_price ?? form.sale_price, ""),
    }], Number(labelCopies) || 1);
    if (!ok) setErr("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة");
    else setErr(null);
  };

  const applyProduct = useCallback((p: Record<string, unknown>, isDuplicate = false) => {
    setForm((prev) => ({
      ...prev,
      sku: isDuplicate ? "" : String(p.sku ?? ""),
      // الباركود يميّز صنفاً واحداً في الشركة — النسخة تبدأ بلا باركود لا بباركود أخيها.
      barcode: isDuplicate ? "" : String(p.barcode ?? ""),
      is_serialized: Boolean(p.is_serialized),
      // الكفالة سياسة الصنف لا حالة نسخةٍ منه — تُنسَخ مع النسخة لبراند آخر.
      warranty_months: p.warranty_months != null ? String(p.warranty_months) : "",
      supplier_warranty_months:
        p.supplier_warranty_months != null ? String(p.supplier_warranty_months) : "",
      // التكرار (براند آخر): الاسم والتصنيف يبقيان كما هما، فيُحفظ المنتج تحت نفس
      // التصنيف بجانب إخوته؛ يُفرّغ البراند فقط ليكتبه المستخدم.
      name_ar: String(p.name_ar ?? ""),
      name_en: isDuplicate ? "" : String(p.name_en ?? ""),
      brand: isDuplicate ? "" : String(p.brand ?? ""),
      variant_group: String(p.variant_group ?? ""),
      description: String(p.description ?? ""),
      storage_location: String(p.storage_location ?? ""),
      uom_id: p.uom_id != null ? Number(p.uom_id) : null,
      uom2: p.uom2 != null ? Number(p.uom2) : null,
      uom2_factor: p.uom2_factor != null ? String(p.uom2_factor) : "",
      uom3: p.uom3 != null ? Number(p.uom3) : null,
      uom3_factor: p.uom3_factor != null ? String(p.uom3_factor) : "",
      min_stock_level: p.min_stock_level != null ? String(p.min_stock_level) : "",
      max_stock_level: p.max_stock_level != null ? String(p.max_stock_level) : "",
      sale_price: p.sale_price != null ? String(p.sale_price) : "",
      category: p.category ? Number(p.category) : null,
      category_name: String(p.category_name ?? ""),
      // is_service هو حقل الخادم الفعلي (يوجّه الترحيل لحساب مبيعات الخدمات)؛
      // «نوع الصنف» في الواجهة يُشتقّ منه لا من حقل item_type غير الموجود خادمياً.
      item_type: p.is_service ? "service" : "goods",
      // الشرائح تصل مسطّحةً من الخادم؛ توزَّع على الخمس بحسب رقمها.
      sale_tiers: tiersFromServer(p.price_tiers, "sale"),
      purchase_tiers: tiersFromServer(p.price_tiers, "purchase"),
      sale_account: numOrNull(p.sale_account_override),
      sale_return_account: numOrNull(p.sale_return_account_override),
      purchase_account: numOrNull(p.purchase_account_override),
      purchase_return_account: numOrNull(p.purchase_return_account_override),
      supplier_account: numOrNull(p.supplier_account_override),
      ending_inventory_account: numOrNull(p.ending_inventory_account_override),
      // الداتا شيت مرفقات المنتج (file_type='Datasheet') — لا تُنسَخ عند التكرار.
      datasheets: isDuplicate ? [] : extractDatasheets(p),
    }));
    setCurrentId(isDuplicate ? null : Number(p.id));
    setErr(null); setMsg(isDuplicate ? "أنت الآن تقوم بإضافة صنف جديد كنسخة من صنف آخر. قم بتغيير البراند أو الاسم." : null);
  }, []);

  useEffect(() => {
    if (duplicateId != null) {
      inventoryApi.getProduct(duplicateId).then(p => applyProduct(p, true)).catch((e: unknown) => {
        setErr(e instanceof Error ? e.message : "فشل التحميل للنسخ");
      });
      return;
    }
    if (productId == null) { setForm(blankForm()); setCurrentId(null); return; }
    inventoryApi.getProduct(productId).then(p => applyProduct(p, false)).catch((e: unknown) => {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    });
  }, [productId, duplicateId, applyProduct]);

  const handleSave = async () => {
    if (!form.name_ar.trim() && !form.name_en.trim()) { setErr("اسم الصنف مطلوب."); return; }
    setSaving(true); setErr(null); setMsg(null);
    try {
      // T-ITEMS M1: الصنف يُحفَظ تحت التصنيف المختار حرفياً.
      // كان هنا إنشاءٌ صامت لتصنيفٍ باسم الصنف نفسه يُجعل المختارُ أباً له —
      // بمطابقة نصّية على تصنيفات الشركة كلها وخطأٍ مبتلَع — فلا يعرف المستخدم
      // أين حُفظ صنفه ولا لماذا امتلأت شجرته بتصنيفاتٍ لم يُنشئها. التجميع
      // يقوم به «النوع» (`variant_group`) وهو حقلٌ ظاهر يُكتب بقصد.
      const categoryId: number | null = form.category;

      // ProductSerializer.Meta.fields only — أي حقول إضافية سيَتجاهلها DRF بصمت.
      const payload: Record<string, unknown> = {
        name_ar: form.name_ar || null,
        name_en: form.name_en || null,
        brand: form.brand.trim(),
        variant_group: form.variant_group.trim(),
        min_stock_level: form.min_stock_level ? Number(form.min_stock_level) : null,
        // T-REORDER: الحدّ الأقصى كان يُكتب في الشاشة ولا يُرسَل قطّ — حقلٌ ميّت
        // يظنّ المستخدم أنه ضبطه. صار حقلاً حقيقياً على النموذج ويُرسَل هنا.
        max_stock_level: form.max_stock_level ? Number(form.max_stock_level) : null,
        // سعر البيع: فارغ = لا سعر محفوظ (البطاقة ترجع لآخر سعر بيع فعلي).
        sale_price: form.sale_price.trim() ? Number(form.sale_price) : null,
        category: categoryId,
        // M0: وحدة القياس صارت قابلة للكتابة على الخادم — كانت تُبتلع بصمت.
        uom_id: form.uom_id,
        // T-ITEMS M5: حقولٌ كانت تُعرض ولا تُحفظ — صارت حقيقية (بهجرة).
        uom2: form.uom2,
        uom2_factor: form.uom2_factor.trim() ? Number(form.uom2_factor) : null,
        uom3: form.uom3,
        uom3_factor: form.uom3_factor.trim() ? Number(form.uom3_factor) : null,
        description: form.description.trim() || null,
        storage_location: form.storage_location.trim() || null,
        sale_account_override: form.sale_account,
        sale_return_account_override: form.sale_return_account,
        purchase_account_override: form.purchase_account,
        purchase_return_account_override: form.purchase_return_account,
        supplier_account_override: form.supplier_account,
        ending_inventory_account_override: form.ending_inventory_account,
        // الشرائح تصف الحالة النهائية: ما لم يُرسَل يُحذف خادمياً.
        price_tiers: tiersToPayload(form.sale_tiers, form.purchase_tiers),
        // is_service: الحقل الفعلي الذي يقرأه الترحيل المحاسبي (مبيعات خدمات لا بضاعة).
        is_service: form.item_type === "service",
        // T-SERIAL: الباركود فارغ = null لا "" — كي لا يتصادم صنفان بلا باركود.
        barcode: form.barcode.trim() || null,
        is_serialized: form.is_serialized,
        // THA-24: فارغ = null لا 0 — «بلا كفالة» و«كفالة صفر شهر» شيء واحد،
        // وnull هو ما يقرأه محرّك الكفالة فلا يُنشئ بطاقة.
        warranty_months: form.warranty_months.trim() ? Number(form.warranty_months) : null,
        supplier_warranty_months: form.supplier_warranty_months.trim()
          ? Number(form.supplier_warranty_months) : null,
        // روابط الداتا شيت — يلتقطها الخادم في _handle_attachments (خارج حقول الـserializer).
        datasheet_urls: form.datasheets.map((d) => d.url),
      };
      if (form.sku.trim()) payload.sku = form.sku.trim();
      let savedId: number;
      if (currentId) {
        await inventoryApi.updateProduct(currentId, payload);
        savedId = currentId;
        setMsg("تم الحفظ.");
      } else {
        const created = await inventoryApi.createProduct(payload) as Record<string, unknown>;
        savedId = Number(created.id);
        setCurrentId(savedId);
        setMsg(`تم إنشاء الصنف ${created.sku}.`);
      }
      // زامن معرّفات الداتا شيت بعد الحفظ: الرفوعات الجديدة صارت صفوفاً محفوظة لها id
      // (فيعمل زر الحذف من الخادم دون إعادة تحميل الصفحة). التزامن ليس حرجاً إن فشل.
      try {
        const refreshed = await inventoryApi.getProduct(savedId) as Record<string, unknown>;
        patch("datasheets", extractDatasheets(refreshed));
      } catch { /* تجاهل */ }
      // النظرة العامة تُقرأ من الخادم — أعِد تحميلها كي يظهر سعر البيع الجديد وربحه.
      insights.reload();
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const nav = useRecordNavigation<SqlProduct>({
    items: products, getId: (p) => p.id, currentId,
    onSelect: (id) => {
      if (id == null) { setForm(blankForm()); setCurrentId(null); return; }
      inventoryApi.getProduct(Number(id)).then(p => applyProduct(p, false)).catch((e: unknown) => {
        setErr(e instanceof Error ? e.message : "فشل التحميل");
      });
    },
  });

  useKitKeymap({
    F12: () => { setLastKey("F12 حفظ"); if (!saving) void handleSave(); },
    Escape: () => { setLastKey("Esc إلغاء"); onCancel(); },
    CtrlIns: () => { setLastKey("Ctrl+Ins جديد"); setForm(blankForm()); setCurrentId(null); },
    CtrlHome: () => { setLastKey("Ctrl+Home"); nav.first(); },
    CtrlEnd: () => { setLastKey("Ctrl+End"); nav.last(); },
    CtrlPageUp: () => { setLastKey("Ctrl+PgUp"); nav.prev(); },
    CtrlPageDown: () => { setLastKey("Ctrl+PgDn"); nav.next(); },
  }, { enabled: true });

  const toolbarActions: KitToolbarAction[] = [
    { key: "new", label: "إضافة", icon: <Plus />, onClick: () => { setForm(blankForm()); setCurrentId(null); } },
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: !saving ? () => void handleSave() : undefined, disabled: saving },
    ...extraActions,
    { key: "cancel", label: cancelLabel, icon: <X />, onClick: onCancel, danger: true },
  ];

  // صنف جديد يفتح على حقول الإدخال؛ الصنف المحفوظ يفتح على نظرته العامة.
  const openingTab = initialTab ?? (productId == null ? "general" : "overview");
  /**
   * THA-411: الكرت يتتبّع تبويبه النشط **بالمفتاح** لا بفهرس الغلاف.
   * تبويب «الأرقام التسلسلية» يُلحق بعد وصول بيانات الصنف (`is_serialized`)، وفهرس
   * الغلاف يُثبَّت عند أول رسم — فرابطٌ يقصده (`/products/{id}?tab=serials`) كان
   * يهبط على أول تبويب. المفتاح يصمد حتى لو تأخّر تبويبه، والنقر يبقى كما هو.
   */
  const [activeTab, setActiveTab] = useState(openingTab);

  const banner = (err || msg) ? (
    <div className={`ktra-banner ${err ? "ktra-banner--err" : "ktra-banner--ok"}`}>
      {err ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{err || msg}</span>
    </div>
  ) : null;

  // ── صفحة 1: بيانات عامة ──
  const tabGeneral = (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, padding: "8px 4px" }}>
      {/* ── الوضع البسيط: ما يلزم كلَّ صنف ────────────────────────────────
          الترتيب هو ترتيب الإدخال الفعلي: من يفتح الكرت يكتب الاسم فالتصنيف
          فالوحدة فالسعر ثم يحفظ. الباقي خلف «متقدم» — كشفٌ تدريجي لا إخفاء:
          الحقل موجود لمن يريده، وغائبٌ عمّن لا يريده. */}
      {fld("اسم الصنف",
        <input className="ktra-input ktra-input--hl" value={form.name_ar}
          onChange={(e) => patch("name_ar", e.target.value)} placeholder="اسم الصنف" />, 2)}
      {fld("اسم الصنف (إنجليزي)", <input className="ktra-input" value={form.name_en}
        onChange={(e) => patch("name_en", e.target.value)} />)}
      {fld("التصنيف",
        <CategoryPicker value={form.category} onChange={(id, name) => {
          patch("category", id);
          patch("category_name", name ?? "");
        }} />)}
      {fld("وحدة القياس",
        <select className="ktra-input" value={form.uom_id ?? ""}
          onChange={(e) => patch("uom_id", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— بدون وحدة —</option>
          {uoms.map((u) => (
            <option key={u.id} value={u.id}>{u.name_ar || u.name_en || u.code}</option>
          ))}
        </select>)}
      {fld("سعر البيع", <input className="ktra-input" type="number" min="0" step="0.01"
        value={form.sale_price} placeholder="فارغ = بلا سعر محفوظ"
        title="سعرٌ عام يدوي — يسبقه في الفاتورة آخر سعر بيع لهذا الزبون وعرضُ سعره"
        onChange={(e) => patch("sale_price", e.target.value)} />)}
      {fld("نوع الصنف", <select className="ktra-input" value={form.item_type}
        onChange={(e) => patch("item_type", e.target.value)}>
        {ITEM_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
      </select>)}
      {fld("رقم الصنف (يولد تلقائياً إن ترك فارغاً)", <input className="ktra-input" value={form.sku}
        onChange={(e) => patch("sku", e.target.value)} placeholder="تلقائي..." />)}
      {/* مِفصل الكشف التدريجي — صفٌّ كامل كي يُقرأ كفاصلٍ لا كحقل. */}
      <div style={{ gridColumn: "1 / -1", marginTop: 4 }}>
        <button type="button" className="ktra-addrow" style={{ margin: 0 }}
          aria-expanded={showAdvanced}
          onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? "▾ إخفاء المتقدم" : "▸ متقدم (باركود، براند، نوع، حدود مخزون، كفالات، ملفات)"}
        </button>
      </div>
      {!showAdvanced ? null : <>
      {/* T-SERIAL: الباركود — توليد (من رقم مكتوب أو عشوائي) ومعاينة وطباعة ملصق. */}
      {fld("الباركود (EAN-13)",
        <div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <input className="ktra-input" style={{ flex: "1 1 170px", direction: "ltr", minWidth: 150 }}
              value={form.barcode} onChange={(e) => patch("barcode", e.target.value)}
              placeholder="اكتب رقماً ثم «إكمال»، أو ولّد تلقائياً" inputMode="numeric" />
            <button type="button" className="ktra-addrow" style={{ margin: 0 }}
              title="يُكمل الرقم المكتوب إلى 13 خانة بخانة تحقق سليمة"
              onClick={handleCompleteBarcode}>إكمال</button>
            <button type="button" className="ktra-addrow" style={{ margin: 0 }}
              title="باركود عشوائي غير مستخدم في هذه الشركة"
              disabled={barcodeBusy} onClick={() => void handleGenerateBarcode()}>
              {barcodeBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              توليد تلقائي
            </button>
          </div>
          {barcodeValue && !barcodeValid && (
            <div style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-warn, #b8800a)", marginTop: 4 }}>
              ليس باركود EAN-13 صالحاً (13 رقماً بخانة تحقق) — اضغط «إكمال» لتصحيحه.
              يُحفَظ كما هو، لكن لا ملصق له.
            </div>
          )}
          {barcodeValid && (
            <div style={{ marginTop: 6 }}>
              {/* المُدخَل أرقام فقط (isValidEan13) والمُخرَج نصّ SVG من الوحدة نفسها. */}
              <div style={{ direction: "ltr", lineHeight: 0 }}
                dangerouslySetInnerHTML={{ __html: ean13Svg(barcodeValue, { moduleWidth: 1.6, barHeight: 38, fontSize: 9 }) }} />
              <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
                <span style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)" }}>عدد النسخ</span>
                <input className="ktra-input" type="number" min="1" max="200" style={{ width: 70 }}
                  value={labelCopies} onChange={(e) => setLabelCopies(e.target.value)} />
                <button type="button" className="ktra-addrow" style={{ margin: 0 }}
                  onClick={handlePrintLabels}>طباعة ملصق</button>
              </div>
            </div>
          )}
        </div>, 2)}
      {/* T-SERIAL: التتبّع بالرقم التسلسلي — بجانب «نوع الصنف» (is_service) لأنهما
          معاً يحدّدان ما إذا كان للصنف وحدات مادّية تُتتبَّع أصلاً. */}
      {/* غلاف span لا label: `fld` يلفّ الحقل بـ<label> أصلاً، و<label> داخل
          <label> يوصّل النقرة مرّتين فيعود المربّع كما كان — أي زرّ لا يعمل. */}
      {fld("تتبّع بالرقم التسلسلي",
        <span style={{ display: "flex", alignItems: "center", gap: 6, minHeight: 30 }}>
          <input type="checkbox" checked={form.is_serialized}
            disabled={form.item_type === "service"}
            onChange={(e) => patch("is_serialized", e.target.checked)} />
          <span style={{ fontSize: "var(--ktra-fs-sm)" }}>
            {form.item_type === "service"
              ? "الخدمة بلا وحدات تُتتبَّع"
              : "كل وحدة برقمها — يظهر تبويب «الأرقام التسلسلية»"}
          </span>
        </span>)}
      {/* THA-24: سياسة الكفالة — بجانب التتبّع بالرقم التسلسلي لأن البطاقة
          التلقائية لا تُنشأ إلا لوحدةٍ مُرقَّمة: المدة بلا تتبّعٍ بالأرقام تبقى
          سياسةً تُقرأ عند الاستقبال يدوياً. فارغ = بلا كفالة. */}
      {fld("كفالة الزبون (أشهر)",
        <input className="ktra-input" type="number" min="0" max="600" step="1"
          value={form.warranty_months}
          placeholder="فارغ = بلا كفالة"
          title="تُنشأ بطاقة كفالة تلقائياً لكل وحدة مُرقَّمة تُباع من هذا الصنف، بدايتها تاريخ فاتورة البيع"
          onChange={(e) => patch("warranty_months", e.target.value)} />)}
      {fld("كفالة المورد لنا (أشهر)",
        <input className="ktra-input" type="number" min="0" max="600" step="1"
          value={form.supplier_warranty_months}
          placeholder="فارغ = بلا كفالة مورد"
          title="تُحسب من تاريخ فاتورة الشراء — يراها موظف الكاونتر فلا تتحمّل الشركة كلفة يتحمّلها المورد"
          onChange={(e) => patch("supplier_warranty_months", e.target.value)} />)}
      {fld("البراند (يظهر بين قوسين)",
        <ValuePicker value={form.brand} onChange={(b) => patch("brand", b)}
          fetchOptions={inventoryApi.getBrands}
          emptyLabel="— بدون براند —" addPlaceholder="مثال: روك بيلد" addTitle="إضافة براند جديد" />)}
      {/* T-REORDER: «النوع» كان حقلاً خادمياً كاملاً (`variant_group`) بنقطته
          الجاهزة (`products/groups/`) ولا مدخلَ له في أي شاشة — فبقي فارغاً على
          كل صنفٍ في كل شركة، وبفراغه يسقط تجميعُ الموديلات على اسم الصنف: كل
          صنفٍ نوعٌ بذاته، فلا بدائل في الفاتورة ولا قرار «مؤجَّل» في تقرير
          التجديد. هذا هو مدخله. */}
      {fld("النوع / المجموعة (موديلات النوع الواحد بدائلُ بعضها)",
        <ValuePicker value={form.variant_group} onChange={(g) => patch("variant_group", g)}
          fetchOptions={inventoryApi.getGroups}
          emptyLabel="— بدون نوع —" addPlaceholder="مثال: ايفون 14 برو" addTitle="نوع جديد" />)}
      {fld("ملفات الداتا شيت (PDF أو صور)",
        <div ref={datasheetRef}>
          <label className="ktra-input" style={{
            display: "inline-flex", alignItems: "center", gap: 6, cursor: dsUploading ? "wait" : "pointer",
            width: "max-content",
          }}>
            {dsUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            <span>{dsUploading ? "...جارٍ الرفع" : "رفع ملف"}</span>
            <input type="file" accept="application/pdf,image/*" hidden disabled={dsUploading}
              onChange={handleDatasheetUpload} />
          </label>
          <span style={{ marginInlineStart: 8, color: "var(--ktra-ink-soft)", fontSize: "var(--ktra-fs-sm)" }}>
            أو الصق الصورة (Ctrl+V)
          </span>
          {form.datasheets.length === 0 ? (
            <span style={{ marginInlineStart: 8, color: "var(--ktra-ink-soft)", fontSize: "var(--ktra-fs-sm)" }}>
              لا ملفات بعد
            </span>
          ) : (
            <ul style={{ listStyle: "none", margin: "6px 0 0", padding: 0, display: "grid", gap: 4 }}>
              {form.datasheets.map((d, i) => (
                <li key={d.url} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  {isImageUrl(d.url) ? (
                    <img src={d.url} alt="معاينة الملف" style={{
                      width: 28, height: 28, objectFit: "cover", borderRadius: 4,
                      flexShrink: 0, border: "1px solid var(--ktra-line, #d7d7d7)",
                    }} />
                  ) : (
                    <FileText className="h-3.5 w-3.5 shrink-0" />
                  )}
                  <a href={d.url} target="_blank" rel="noreferrer"
                    style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {decodeURIComponent(d.url.split("/").pop() || d.url)}
                  </a>
                  {d.id == null && (
                    <span style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-warn, #b8800a)" }}>
                      (غير محفوظ)
                    </span>
                  )}
                  <button type="button" className="ktra-iconbtn ktra-iconbtn--danger"
                    title="حذف الملف" onClick={() => void handleDatasheetRemove(i)}>
                    <Trash2 className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>, 3)}
      </>}
      {/* معاينة موضع الحفظ — تُقرأ قبل الضغط لا بعده. */}
      <div style={{
        gridColumn: "1 / -1", marginTop: 4, fontSize: "var(--ktra-fs-sm)",
        color: "var(--ktra-ink-soft)",
      }}>
        سيُحفظ تحت: <b style={{ color: "var(--ktra-ink)" }}>{categoryPath || "بدون تصنيف"}</b>
      </div>
    </div>
  );

  // ── صفحة 2: الأرصدة والحركات ──
  const tabBalances = (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, padding: "8px 4px" }}>
      {fld("رصيد أول المدة", <input className="ktra-input" readOnly value="(محسوب — غير قابل للتعديل)" />)}
      {fld("مجموع الحركات الواردة", <input className="ktra-input" readOnly value="(تلقائي)" />)}
      {fld("مجموع الحركات الصادرة", <input className="ktra-input" readOnly value="(تلقائي)" />)}
      {fld("رصيد الصنف الحالي", <input className="ktra-input" readOnly value="(تلقائي)" />)}
      {fld("الحد الأدنى", <input className="ktra-input" type="number" min="0" step="1"
        value={form.min_stock_level} onChange={(e) => patch("min_stock_level", e.target.value)} />)}
      {fld("الحد الأقصى", <input className="ktra-input" type="number" min="0" step="1"
        value={form.max_stock_level} onChange={(e) => patch("max_stock_level", e.target.value)} />)}
      {fld("تاريخ آخر حركة", <input className="ktra-input" readOnly value="(تلقائي)" />)}
      <div style={{ gridColumn: "1/-1", fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)" }}>
        ملاحظة: جميع حركات المخازن ذات التاريخ قبل بداية الفترة المالية ترحل إلى رصيد أول المدة.
        للوصول إلى ثوابت المجموعة اضغط زر «ثوابت المجموعة» في الشريط العلوي أو المفتاح F11.
      </div>
    </div>
  );

  // ── صفحة 3: أسعار البيع والشراء (5+5) ──
  const tierTable = (
    tiers: PriceTier[], label: string,
    onUpdate: (i: number, k: keyof PriceTier, v: string | number | boolean | null) => void
  ) => (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontWeight: 600, fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)", marginBottom: 4, paddingRight: 4 }}>
        {label}
      </div>
      <table className="ktra-grid">
        <thead>
          <tr>
            <th style={{ width: 45 }}>#</th>
            <th>السعر</th>
            <th style={{ width: 80 }}>العملة</th>
            <th style={{ width: 110 }}>يشمل ض.ق.م</th>
          </tr>
        </thead>
        <tbody>
          {tiers.map((t, i) => (
            <tr key={i}>
              <td className="ktra-num">{i + 1}</td>
              <td>
                <input className="ktra-input" type="number" min="0" step="0.01"
                  value={t.price} onChange={(e) => onUpdate(i, "price", e.target.value)} />
              </td>
              <td>
                <select className="ktra-input" value={t.currency ?? ""}
                  onChange={(e) => onUpdate(i, "currency", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">—</option>
                  {currencies.map((c) => (
                    <option key={c.CurrencyID} value={c.CurrencyID}>{c.CurrencyCode}</option>
                  ))}
                </select>
              </td>
              <td style={{ textAlign: "center" }}>
                <input type="checkbox" checked={t.tax_inclusive}
                  onChange={(e) => onUpdate(i, "tax_inclusive", e.target.checked)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  // سعر البيع المحفوظ مقابل التكلفة المحسوبة — الربح والهامش يُحسبان فوراً أثناء
  // الكتابة (معاينة فقط؛ القيمة المعتمدة بعد الحفظ تأتي من الخادم في «نظرة عامة»).
  const avgCost = Number(insights.profile?.avg_cost ?? 0);
  const salePriceNum = form.sale_price.trim() ? Number(form.sale_price) : null;
  const previewProfit = salePriceNum != null && Number.isFinite(salePriceNum) ? salePriceNum - avgCost : null;
  const previewMargin = previewProfit != null && salePriceNum ? (previewProfit / salePriceNum) * 100 : null;
  const profitTone = previewProfit == null ? "var(--ktra-ink)"
    : previewProfit < 0 ? "var(--ktra-danger,#c00)" : "var(--ktra-ok,#267346)";

  const tabPrices = (
    <div style={{ padding: "8px 4px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginBottom: 14 }}>
        {fld("سعر البيع العام (يدوي)",
          <input className="ktra-input ktra-input--hl" type="number" min="0" step="0.01"
            value={form.sale_price} onChange={(e) => patch("sale_price", e.target.value)}
            title="يُقترح في مستند البيع فقط للزبون الذي لا عرض سعر له ولا شراء سابق لهذا الصنف"
            placeholder="للزبون بلا عرض ولا شراء سابق" />)}
        {fld("سعر التكلفة (متوسط — محسوب)",
          <input className="ktra-input" readOnly value={formatMoney(insights.profile?.avg_cost ?? "", "—")} />)}
        {fld("الربح للوحدة",
          <input className="ktra-input" readOnly style={{ color: profitTone, fontWeight: 600 }}
            value={previewProfit != null ? formatMoney(previewProfit) : "—"} />)}
        {fld("هامش الربح %",
          <input className="ktra-input" readOnly style={{ color: profitTone }}
            value={previewMargin != null ? `${formatMoney(previewMargin)}%` : "—"} />)}
        {fld("آخر سعر بيع (فاتورة مرحّلة)",
          <input className="ktra-input" readOnly
            value={formatMoney(insights.profile?.last_sale_price ?? "", "—")} />)}
        {fld("آخر سعر شراء (فاتورة مرحّلة)",
          <input className="ktra-input" readOnly
            value={formatMoney(insights.profile?.last_purchase_price ?? "", "—")} />)}
      </div>
      <div style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)", marginBottom: 6 }}>
        الشريحة الأولى للبيع تدخل تسعير الفواتير حين لا يكون للزبون عرضُ سعرٍ ولا شراءٌ
        سابق. الصفّ بلا سعرٍ أو بلا عملة لا يُحفَظ.
      </div>
      {tierTable(form.sale_tiers, "أسعار البيع (5 فئات)", (i, k, v) => {
        const next = [...form.sale_tiers];
        next[i] = { ...next[i], [k]: v };
        patch("sale_tiers", next);
      })}
      {tierTable(form.purchase_tiers, "أسعار الشراء (5 فئات)", (i, k, v) => {
        const next = [...form.purchase_tiers];
        next[i] = { ...next[i], [k]: v };
        patch("purchase_tiers", next);
      })}
    </div>
  );

  // ── صفحة 4: بيانات المتاجرة ──
  // T-ITEMS M5: كانت حقولاً نصّية حرّة بلافتة «لا تُحفَظ». صارت منتقياتِ حسابٍ
  // حقيقية تُحفَظ على الصنف — والخادم يرفض حساباً من شركة أخرى.
  const accountField = (
    label: string, key: keyof FormState, title: string,
  ) => fld(label,
    <AccountTreeField
      accounts={accounts}
      value={form[key] as number | null}
      onChange={(id) => patch(key, id as FormState[typeof key])}
      title={title}
      placeholder="— الافتراضي من التصنيف —"
    />);

  const tabTrading = (
    <div style={{ padding: "8px 4px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 8 }}>
        {accountField("حساب البيع", "sale_account", "يسبق حساب إيرادات التصنيف عند ترحيل بيع هذا الصنف")}
        {accountField("حساب مرتجع البيع", "sale_return_account", "حساب مرتجع المبيعات لهذا الصنف")}
        {accountField("حساب الشراء", "purchase_account", "حساب المشتريات لهذا الصنف")}
        {accountField("حساب مرتجع الشراء", "purchase_return_account", "حساب مرتجع المشتريات لهذا الصنف")}
        {accountField("حساب المورد", "supplier_account", "حساب المورد الافتراضي لهذا الصنف")}
        {accountField("حساب بضاعة آخر المدة", "ending_inventory_account", "حساب المخزون لهذا الصنف")}
        <div style={{ gridColumn: "1/-1", fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)" }}>
          اترك الحقل فارغاً ليُستعمل حساب التصنيف الافتراضي.
        </div>
      </div>
    </div>
  );

  // ── صفحة 5: بيانات أخرى ──
  const tabOther = (
    <div style={{ padding: "8px 4px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 8 }}>
        {fld("بيان الصنف (داخلي)",
          <input className="ktra-input" value={form.description}
            title="وصفٌ داخلي — غير وصف المتجر الذي يراه الزبون"
            onChange={(e) => patch("description", e.target.value)} />, 2)}
        {fld("موقع التخزين (رفّ/ممر)",
          <input className="ktra-input" value={form.storage_location}
            placeholder="مثال: A-3"
            title="إرشادي — لا رصيد عليه ولا حركة مخزون"
            onChange={(e) => patch("storage_location", e.target.value)} />)}
        {/* T-ITEMS M5: وحدتان إضافيتان بمعاملَي تحويلٍ إلى الوحدة الرئيسية. */}
        {fld("الوحدة الثانية",
          <select className="ktra-input" value={form.uom2 ?? ""}
            onChange={(e) => patch("uom2", e.target.value ? Number(e.target.value) : null)}>
            <option value="">— بدون —</option>
            {uoms.map((u) => <option key={u.id} value={u.id}>{u.name_ar || u.name_en || u.code}</option>)}
          </select>)}
        {fld("معامل الوحدة الثانية",
          <input className="ktra-input" type="number" min="0" step="0.001"
            value={form.uom2_factor} placeholder="كم وحدةً رئيسية فيها؟"
            onChange={(e) => patch("uom2_factor", e.target.value)} />)}
        {fld("الوحدة الثالثة",
          <select className="ktra-input" value={form.uom3 ?? ""}
            onChange={(e) => patch("uom3", e.target.value ? Number(e.target.value) : null)}>
            <option value="">— بدون —</option>
            {uoms.map((u) => <option key={u.id} value={u.id}>{u.name_ar || u.name_en || u.code}</option>)}
          </select>)}
        {fld("معامل الوحدة الثالثة",
          <input className="ktra-input" type="number" min="0" step="0.001"
            value={form.uom3_factor} placeholder="كم وحدةً رئيسية فيها؟"
            onChange={(e) => patch("uom3_factor", e.target.value)} />)}
        <div style={{ gridColumn: "1/-1", fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)" }}>
          المعامل = كم وحدةً رئيسية داخل الوحدة الإضافية (كرتونة = 12 قطعة ⇒ 12).
        </div>
      </div>
    </div>
  );

  // T-ITEMS M5: تبويب «معادلات التصنيع» أُزيل. لم يكن يُحفظ إطلاقاً (لا نموذج
  // ولا نقطة)، والتصنيع في المنتجات الاحترافية موديولٌ قائم بذاته (Odoo MRP:
  // أوامر تصنيع ومراحل واستهلاك مخزون) لا حقلٌ في كرت الصنف — فبناؤه قرارٌ
  // مستقل لا تفصيلٌ داخل هذه المهمة.

  return (
    <div dir="rtl">
      <KitDocumentShell
        title="كرت الصنف"
        state={currentId ? `صنف #${currentId}` : "صنف جديد"}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        nav={nav}
        actions={toolbarActions}
        header={
          <>
            {/* T-ITEMS M1: شريط الهوية يُحرَّر في مكانه.
                كان مرايا readOnly: فتحُ الكرت لتغيير الاسم يوجب النزول إلى
                التبويب الرابع والبحث عنه بين الباركود والكفالات — وهو أوّل ما
                يُفتح الكرت لأجله. الاسم رأسُ النموذج كما في Odoo. */}
            {fld("رقم الصنف", <input className="ktra-input" readOnly
              value={currentId ? `#${currentId}` : "— جديد —"} />)}
            {fld("SKU", <input className="ktra-input ktra-input--hl" value={form.sku}
              onChange={(e) => patch("sku", e.target.value)} />)}
            {fld("اسم الصنف", <input className="ktra-input ktra-input--hl" value={form.name_ar}
              onChange={(e) => patch("name_ar", e.target.value)}
              placeholder="اسم الصنف" autoFocus={productId == null} />, 2)}
            {fld("التصنيف",
              <CategoryPicker value={form.category} onChange={(id, name) => {
                patch("category", id);
                patch("category_name", name ?? "");
              }} />)}
            {fld("نوع الصنف", <select className="ktra-input" value={form.item_type}
              onChange={(e) => patch("item_type", e.target.value)}>
              {ITEM_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
            </select>)}
            {/* الأرقام القيادية في شريط الرأس — تُرى قبل فتح أي تبويب. */}
            {fld("سعر البيع", <input className="ktra-input" readOnly
              value={formatMoney(insights.profile?.effective_sale_price ?? form.sale_price, "—")} />)}
            {fld("سعر التكلفة", <input className="ktra-input" readOnly
              value={formatMoney(insights.profile?.avg_cost ?? "", "—")} />)}
            {fld("الرصيد", <input className="ktra-input" readOnly
              value={formatQuantity(insights.profile?.quantity_on_hand ?? "", "—")} />)}
          </>
        }
        tabs={[
          // النظرة العامة أولاً: فتح الكرت يعرض حالة الصنف كاملة قبل أي تحرير.
          ...insights.tabs,
          { key: "general", label: "بيانات عامة", content: tabGeneral },
          { key: "balances", label: "الأرصدة والحركات", content: tabBalances },
          { key: "prices", label: "أسعار البيع والشراء", content: tabPrices },
          { key: "trading", label: "بيانات المتاجرة", content: tabTrading },
          { key: "other", label: "بيانات أخرى", content: tabOther },
          // T-SUPSKU: رقم الصنف عند كل مورّد — كان يُحشَر في «الاسم بالإنجليزية».
          // ثابتٌ في القائمة لا مشروط: تبويبٌ يظهر ويختفي وقت التشغيل يزحزح
          // الفهرس فيقفز المستخدم (الغلاف يتتبّع النشط بالفهرس).
          { key: "supplier_codes", label: "أرقام الموردين",
            content: <SupplierCodesTab productId={currentId} /> },
          // آخر القائمة: تفعيل التتبّع يُلحق تبويباً ولا يزحزح فهرس تبويب قائم
          // (الغلاف يتتبّع النشط بالفهرس) — فيبقى المستخدم حيث هو.
          ...(insights.serialsTab ? [insights.serialsTab] : []),
        ]}
        totals={
          <div style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)", padding: "4px 0", display: "grid", gap: 2 }}>
            <div>سعر البيع: <b style={{ color: "var(--ktra-ink)" }}>
              {formatMoney(insights.profile?.effective_sale_price ?? form.sale_price, "—")}</b></div>
            <div>سعر التكلفة: <b style={{ color: "var(--ktra-ink)" }}>
              {formatMoney(insights.profile?.avg_cost ?? "", "—")}</b></div>
            <div>الربح للوحدة: <b style={{ color: profitTone }}>
              {formatMoney(insights.profile?.profit_per_unit ?? (previewProfit ?? ""), "—")}</b></div>
          </div>
        }
        status={
          <>
            <span className="ktra-status-item">رقم الصنف <b>{currentId ?? "—"}</b></span>
            <span className="ktra-status-item">الرصيد <b>{formatQuantity(insights.profile?.quantity_on_hand ?? "", "—")}</b></span>
            <span className="ktra-status-item">المتاح <b>{formatQuantity(insights.profile?.available_quantity ?? "", "—")}</b></span>
            <span className="ktra-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="ktra-status-item">آخر مفتاح <b>{lastKey}</b></span>
          </>
        }
      >
        {banner}
      </KitDocumentShell>
    </div>
  );
};
