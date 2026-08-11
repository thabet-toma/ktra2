/**
 * N5-T4 — ItemFormAseel (F6) — inside-out نمط Aseel مع 6 صفحات
 * المرجع: المخازن.txt:11-25، القالب: SalesInvoiceEditor.tsx
 *
 * كرت الصنف الموحّد: صار هذا المكوّن هو الكرت الوحيد — الإضافة والتعديل والعرض.
 * تبويبات «نظرة عامة» و«الفواتير المرتبطة» و«حركة المخزون» تأتي من
 * `useProductInsights` (كانت حبيسة صفحة `ProductProfilePage` المنفصلة).
 */
import React, { useCallback, useEffect, useState } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct } from "../../types/inventory";
import {
  AseelDocumentShell,
  AseelGrid,
  useAseelKeymap,
  useRecordNavigation,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../aseel";
import { Plus, Save, Trash2, X, Loader2, AlertCircle, CheckCircle2, Info, Upload, FileText } from "lucide-react";
import { CategoryPicker } from "../inventory/CategoryPicker";
import { ValuePicker } from "../inventory/ValuePicker";
import { cloudinaryService } from "../../services/cloudinaryService";
import { usePasteImageUpload } from "../../utils/clipboardImage";
import { useProductInsights } from "./ProductInsightTabs";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { completeEan13, ean13Svg, isValidEan13, printBarcodeLabels } from "../../utils/barcode";

const pendingN8 = (msg: string) => (
  <div className="aseel-banner" style={{
    background: "color-mix(in srgb, var(--aseel-warn, #b8800a) 12%, transparent)",
    color: "var(--aseel-warn, #b8800a)",
    border: "1px solid color-mix(in srgb, var(--aseel-warn, #b8800a) 30%, transparent)",
    marginBottom: 6,
  }}>
    <Info className="h-4 w-4 shrink-0" />
    <span>{msg}</span>
  </div>
);

type Props = {
  productId: number | null;
  duplicateId?: number | null;
  /** سجلّات التنقّل (Ctrl+PgUp/PgDn) — تُترك فارغة حين يُفتح الكرت بمساره المباشر. */
  products: SqlProduct[];
  onSaved: () => void;
  onCancel: () => void;
  /** أزرار إضافية على الشريط (مثل «تكلفة المنتجات» حين يُفتح الكرت كصفحة). */
  extraActions?: AseelToolbarAction[];
  /** نصّ زر الإلغاء — «عودة» حين يكون الكرت صفحة قائمة بذاتها. */
  cancelLabel?: string;
  /** التبويب الابتدائي (روابط «ذكر لمنتج» تفتح حركة المخزون مباشرةً). */
  initialTab?: string;
};

type PriceTier = { price: string; currency: string; tax_inclusive: boolean };
const blankTier = (): PriceTier => ({ price: "0", currency: "ILS", tax_inclusive: false });

type ComponentLine = { key: string; component_sku: string; quantity: string };
const newCmpKey = () => `cmp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

// الداتا شيت: المحفوظ له id (للحذف من SQL/Cloudinary)، والمرفوع حديثاً id=null.
type DatasheetRef = { id: number | null; url: string };
const extractDatasheets = (p: Record<string, unknown>): DatasheetRef[] =>
  Array.isArray(p.attachments)
    ? (p.attachments as Array<{ id?: number; file_path?: string; file_type?: string }>)
        .filter((a) => a?.file_type === "Datasheet" && a?.file_path)
        .map((a) => ({ id: typeof a.id === "number" ? a.id : null, url: a.file_path as string }))
    : [];

type FormState = {
  sku: string; catalog_no: string; name_ar: string; name_en: string;
  brand: string;
  /** T-SERIAL: باركود الصنف (EAN-13) — فريد داخل الشركة، يحرسه الخادم. */
  barcode: string;
  /** T-SERIAL: تتبّع وحدات الصنف بأرقام تسلسلية. */
  is_serialized: boolean;
  /** THA-24: سياسة كفالة الزبون بالأشهر — فارغ = بلا كفالة، فلا بطاقة تلقائية. */
  warranty_months: string;
  /** THA-24: كفالة المورد لنا بالأشهر — تُحسب من تاريخ فاتورة الشراء. */
  supplier_warranty_months: string;
  description: string; location: string;
  uom_primary: string; uom2: string; uom2_factor: string;
  uom3: string; uom3_factor: string;
  min_stock_level: string; max_stock_level: string; reorder_level: string;
  /** سعر البيع الافتراضي المحفوظ على الصنف (بجانب سعر التكلفة المحسوب). */
  sale_price: string;
  sale_tiers: PriceTier[];
  purchase_tiers: PriceTier[];
  sale_account: string; sale_return_account: string;
  purchase_account: string; purchase_return_account: string;
  supplier_account: string; ending_inventory_account: string;
  category: number | null; category_name: string; item_type: string;
  bonus_after_qty: string; bonus_every_qty: string;
  components: ComponentLine[];
  datasheets: DatasheetRef[];
};

const blankForm = (): FormState => ({
  sku: "", catalog_no: "", name_ar: "", name_en: "",
  brand: "",
  barcode: "", is_serialized: false,
  warranty_months: "", supplier_warranty_months: "",
  description: "", location: "",
  uom_primary: "عدد", uom2: "", uom2_factor: "1",
  uom3: "", uom3_factor: "1",
  min_stock_level: "", max_stock_level: "", reorder_level: "",
  sale_price: "",
  sale_tiers: Array.from({ length: 5 }, blankTier),
  purchase_tiers: Array.from({ length: 5 }, blankTier),
  sale_account: "", sale_return_account: "",
  purchase_account: "", purchase_return_account: "",
  supplier_account: "", ending_inventory_account: "",
  category: null, category_name: "", item_type: "goods",
  bonus_after_qty: "", bonus_every_qty: "1",
  components: [],
  datasheets: [],
});

const fld = (label: string, node: React.ReactNode, span?: number) => (
  <label className="aseel-field" style={span ? { gridColumn: `span ${span}` } : {}}>
    <span className="aseel-field-label">{label}</span>
    {node}
  </label>
);

const ITEM_TYPES = [
  { v: "goods", l: "بضاعة" }, { v: "service", l: "خدمات" },
  { v: "work", l: "عمل" }, { v: "asset", l: "أصل" },
  { v: "composite", l: "تجميعي" },
];

export const ItemFormAseel: React.FC<Props> = ({
  productId, duplicateId, products, onSaved, onCancel, extraActions = [], cancelLabel = "إلغاء",
  initialTab,
}) => {
  const [form, setForm] = useState<FormState>(blankForm());
  const [currentId, setCurrentId] = useState<number | null>(productId);
  // الجزء القرائي من الكرت (نظرة عامة/فواتير/حركة/أرقام تسلسلية) — يتبع الصنف المعروض.
  const insights = useProductInsights(currentId, { isSerialized: form.is_serialized });
  // W10: صنف موجود (تعديل) — اسمه يُحرَّر مباشرةً بحقل نصّي بدل منتقي «اختر/أضف»
  // الذي كان يحبس الاسم في قائمة منسدلة (نقر «+» يمسح القيمة) فيبدو «غير قابل للتعديل».
  const isExistingProduct = productId != null;
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lastKey, setLastKey] = useState("—");
  const [dsUploading, setDsUploading] = useState(false);

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

  // لصق صورة من الحافظة (Ctrl+V) بدل رفعها كملف.
  usePasteImageUpload((files) => { void uploadDatasheetFile(files[0]); }, !dsUploading);

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
      catalog_no: isDuplicate ? "" : String(p.catalog_no ?? ""),
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
      description: String(p.description ?? ""),
      location: String(p.location ?? ""),
      uom_primary: String(p.uom_primary ?? "عدد"),
      min_stock_level: p.min_stock_level != null ? String(p.min_stock_level) : "",
      max_stock_level: p.max_stock_level != null ? String(p.max_stock_level) : "",
      reorder_level: p.reorder_level != null ? String(p.reorder_level) : "",
      sale_price: p.sale_price != null ? String(p.sale_price) : "",
      category: p.category ? Number(p.category) : null,
      category_name: String(p.category_name ?? ""),
      // is_service هو حقل الخادم الفعلي (يوجّه الترحيل لحساب مبيعات الخدمات)؛
      // «نوع الصنف» في الواجهة يُشتقّ منه لا من حقل item_type غير الموجود خادمياً.
      item_type: p.is_service ? "service" : "goods",
      sale_tiers: (p.sale_tiers as PriceTier[] | undefined) ?? prev.sale_tiers,
      purchase_tiers: (p.purchase_tiers as PriceTier[] | undefined) ?? prev.purchase_tiers,
      sale_account: String(p.sale_account_override ?? ""),
      sale_return_account: String(p.sale_return_account_override ?? ""),
      purchase_account: String(p.purchase_account_override ?? ""),
      purchase_return_account: String(p.purchase_return_account_override ?? ""),
      supplier_account: String(p.supplier_account_override ?? ""),
      ending_inventory_account: String(p.ending_inventory_account_override ?? ""),
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
      // التصنيف الفعلي للمنتج = تصنيف فرعي اسمه اسم المنتج: إن وُجد نستخدمه (فيُحفظ
      // المنتج بجانب إخوته)، وإلا نُنشئه تحت التصنيف الأب المختار (شجرة بأي عمق).
      const name = (form.name_ar || form.name_en || "").trim();
      let categoryId: number | null = form.category;
      try {
        const cats = await inventoryApi.getCategories() as Array<{ id: number; name: string }>;
        const existing = cats.find((c) => (c.name || "").trim() === name);
        if (existing) {
          categoryId = existing.id;
        } else if (name) {
          const createdCat = await inventoryApi.createCategory({ name, parent: form.category || null }) as { id: number };
          categoryId = createdCat.id;
        }
      } catch { /* تعذّر — نستخدم التصنيف المختار كما هو */ }

      // ProductSerializer.Meta.fields only — أي حقول إضافية سيَتجاهلها DRF بصمت.
      const payload: Record<string, unknown> = {
        name_ar: form.name_ar || null,
        name_en: form.name_en || null,
        brand: form.brand.trim(),
        min_stock_level: form.min_stock_level ? Number(form.min_stock_level) : null,
        // سعر البيع: فارغ = لا سعر محفوظ (البطاقة ترجع لآخر سعر بيع فعلي).
        sale_price: form.sale_price.trim() ? Number(form.sale_price) : null,
        category: categoryId,
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

  useAseelKeymap({
    F12: () => { setLastKey("F12 حفظ"); if (!saving) void handleSave(); },
    Escape: () => { setLastKey("Esc إلغاء"); onCancel(); },
    CtrlIns: () => { setLastKey("Ctrl+Ins جديد"); setForm(blankForm()); setCurrentId(null); },
    CtrlHome: () => { setLastKey("Ctrl+Home"); nav.first(); },
    CtrlEnd: () => { setLastKey("Ctrl+End"); nav.last(); },
    CtrlPageUp: () => { setLastKey("Ctrl+PgUp"); nav.prev(); },
    CtrlPageDown: () => { setLastKey("Ctrl+PgDn"); nav.next(); },
  }, { enabled: true });

  const toolbarActions: AseelToolbarAction[] = [
    { key: "new", label: "إضافة", icon: <Plus />, onClick: () => { setForm(blankForm()); setCurrentId(null); } },
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: !saving ? () => void handleSave() : undefined, disabled: saving },
    ...extraActions,
    { key: "cancel", label: cancelLabel, icon: <X />, onClick: onCancel, danger: true },
  ];

  // صنف جديد يفتح على حقول الإدخال؛ الصنف المحفوظ يفتح على نظرته العامة.
  const openingTab = initialTab ?? (productId == null ? "general" : "overview");

  const banner = (err || msg) ? (
    <div className={`aseel-banner ${err ? "aseel-banner--err" : "aseel-banner--ok"}`}>
      {err ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{err || msg}</span>
    </div>
  ) : null;

  // ── صفحة 1: بيانات عامة ──
  const tabGeneral = (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, padding: "8px 4px" }}>
      {fld("رقم الصنف (يولد تلقائياً إن ترك فارغاً)", <input className="aseel-input aseel-input--hl" value={form.sku}
        onChange={(e) => patch("sku", e.target.value)} placeholder="تلقائي..." />)}
      {fld("رقم الكتلوج", <input className="aseel-input" value={form.catalog_no}
        onChange={(e) => patch("catalog_no", e.target.value)} />)}
      {fld("نوع الصنف", <select className="aseel-input" value={form.item_type}
        onChange={(e) => patch("item_type", e.target.value)}>
        {ITEM_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
      </select>)}
      {/* T-SERIAL: الباركود — توليد (من رقم مكتوب أو عشوائي) ومعاينة وطباعة ملصق. */}
      {fld("الباركود (EAN-13)",
        <div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <input className="aseel-input" style={{ flex: "1 1 170px", direction: "ltr", minWidth: 150 }}
              value={form.barcode} onChange={(e) => patch("barcode", e.target.value)}
              placeholder="اكتب رقماً ثم «إكمال»، أو ولّد تلقائياً" inputMode="numeric" />
            <button type="button" className="aseel-addrow" style={{ margin: 0 }}
              title="يُكمل الرقم المكتوب إلى 13 خانة بخانة تحقق سليمة"
              onClick={handleCompleteBarcode}>إكمال</button>
            <button type="button" className="aseel-addrow" style={{ margin: 0 }}
              title="باركود عشوائي غير مستخدم في هذه الشركة"
              disabled={barcodeBusy} onClick={() => void handleGenerateBarcode()}>
              {barcodeBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              توليد تلقائي
            </button>
          </div>
          {barcodeValue && !barcodeValid && (
            <div style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-warn, #b8800a)", marginTop: 4 }}>
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
                <span style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>عدد النسخ</span>
                <input className="aseel-input" type="number" min="1" max="200" style={{ width: 70 }}
                  value={labelCopies} onChange={(e) => setLabelCopies(e.target.value)} />
                <button type="button" className="aseel-addrow" style={{ margin: 0 }}
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
          <span style={{ fontSize: "var(--aseel-fs-sm)" }}>
            {form.item_type === "service"
              ? "الخدمة بلا وحدات تُتتبَّع"
              : "كل وحدة برقمها — يظهر تبويب «الأرقام التسلسلية»"}
          </span>
        </span>)}
      {/* THA-24: سياسة الكفالة — بجانب التتبّع بالرقم التسلسلي لأن البطاقة
          التلقائية لا تُنشأ إلا لوحدةٍ مُرقَّمة: المدة بلا تتبّعٍ بالأرقام تبقى
          سياسةً تُقرأ عند الاستقبال يدوياً. فارغ = بلا كفالة. */}
      {fld("كفالة الزبون (أشهر)",
        <input className="aseel-input" type="number" min="0" max="600" step="1"
          value={form.warranty_months}
          placeholder="فارغ = بلا كفالة"
          title="تُنشأ بطاقة كفالة تلقائياً لكل وحدة مُرقَّمة تُباع من هذا الصنف، بدايتها تاريخ فاتورة البيع"
          onChange={(e) => patch("warranty_months", e.target.value)} />)}
      {fld("كفالة المورد لنا (أشهر)",
        <input className="aseel-input" type="number" min="0" max="600" step="1"
          value={form.supplier_warranty_months}
          placeholder="فارغ = بلا كفالة مورد"
          title="تُحسب من تاريخ فاتورة الشراء — يراها موظف الكاونتر فلا تتحمّل الشركة كلفة يتحمّلها المورد"
          onChange={(e) => patch("supplier_warranty_months", e.target.value)} />)}
      {fld(isExistingProduct ? "اسم المنتج" : "اسم المنتج (اختر موجوداً لبراند آخر، أو اكتب جديداً)",
        isExistingProduct
          ? <input className="aseel-input" value={form.name_ar}
              onChange={(e) => patch("name_ar", e.target.value)} placeholder="اسم المنتج" />
          : <ValuePicker value={form.name_ar} onChange={(v) => patch("name_ar", v)}
              fetchOptions={inventoryApi.getProductNames}
              emptyLabel="— اختر منتجاً —" addPlaceholder="مثال: 195/65/15" addTitle="منتج جديد" />, 2)}
      {fld("اسم الصنف (إنجليزي)", <input className="aseel-input" value={form.name_en}
        onChange={(e) => patch("name_en", e.target.value)} />)}
      {fld("البراند (يظهر بين قوسين)",
        <ValuePicker value={form.brand} onChange={(b) => patch("brand", b)}
          fetchOptions={inventoryApi.getBrands}
          emptyLabel="— بدون براند —" addPlaceholder="مثال: روك بيلد" addTitle="إضافة براند جديد" />)}
      {fld("تفصيل / بيان الصنف", <input className="aseel-input" value={form.description}
        onChange={(e) => patch("description", e.target.value)} />, 2)}
      {fld("الموقع (الرف)", <input className="aseel-input" value={form.location}
        onChange={(e) => patch("location", e.target.value)} />)}
      {fld("تحت أي تصنيف (الأب — عند منتج جديد يُنشأ فرعي باسمه)",
        <CategoryPicker value={form.category} onChange={(id, name) => {
          patch("category", id);
          if (name) patch("category_name", name);
        }} />)}
      {fld("الوحدة الرئيسية", <input className="aseel-input" value={form.uom_primary}
        onChange={(e) => patch("uom_primary", e.target.value)} placeholder="عدد، كيلو، لتر…" />)}
      {fld("وحدة 2", <input className="aseel-input" value={form.uom2}
        onChange={(e) => patch("uom2", e.target.value)} />)}
      {fld("معامل الوحدة 2", <input className="aseel-input" type="number" min="0" step="0.001"
        value={form.uom2_factor} onChange={(e) => patch("uom2_factor", e.target.value)} />)}
      {fld("وحدة 3", <input className="aseel-input" value={form.uom3}
        onChange={(e) => patch("uom3", e.target.value)} />)}
      {fld("معامل الوحدة 3", <input className="aseel-input" type="number" min="0" step="0.001"
        value={form.uom3_factor} onChange={(e) => patch("uom3_factor", e.target.value)} />)}
      {fld("ملفات الداتا شيت (PDF أو صور)",
        <div>
          <label className="aseel-input" style={{
            display: "inline-flex", alignItems: "center", gap: 6, cursor: dsUploading ? "wait" : "pointer",
            width: "max-content",
          }}>
            {dsUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            <span>{dsUploading ? "...جارٍ الرفع" : "رفع ملف"}</span>
            <input type="file" accept="application/pdf,image/*" hidden disabled={dsUploading}
              onChange={handleDatasheetUpload} />
          </label>
          {form.datasheets.length === 0 ? (
            <span style={{ marginInlineStart: 8, color: "var(--aseel-ink-soft)", fontSize: "var(--aseel-fs-sm)" }}>
              لا ملفات بعد
            </span>
          ) : (
            <ul style={{ listStyle: "none", margin: "6px 0 0", padding: 0, display: "grid", gap: 4 }}>
              {form.datasheets.map((d, i) => (
                <li key={d.url} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  <a href={d.url} target="_blank" rel="noreferrer"
                    style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {decodeURIComponent(d.url.split("/").pop() || d.url)}
                  </a>
                  {d.id == null && (
                    <span style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-warn, #b8800a)" }}>
                      (غير محفوظ)
                    </span>
                  )}
                  <button type="button" className="aseel-iconbtn aseel-iconbtn--danger"
                    title="حذف الملف" onClick={() => void handleDatasheetRemove(i)}>
                    <Trash2 className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>, 3)}
    </div>
  );

  // ── صفحة 2: الأرصدة والحركات ──
  const tabBalances = (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, padding: "8px 4px" }}>
      {fld("رصيد أول المدة", <input className="aseel-input" readOnly value="(محسوب — غير قابل للتعديل)" />)}
      {fld("مجموع الحركات الواردة", <input className="aseel-input" readOnly value="(تلقائي)" />)}
      {fld("مجموع الحركات الصادرة", <input className="aseel-input" readOnly value="(تلقائي)" />)}
      {fld("رصيد الصنف الحالي", <input className="aseel-input" readOnly value="(تلقائي)" />)}
      {fld("الحد الأدنى", <input className="aseel-input" type="number" min="0" step="0.001"
        value={form.min_stock_level} onChange={(e) => patch("min_stock_level", e.target.value)} />)}
      {fld("الحد الأقصى", <input className="aseel-input" type="number" min="0" step="0.001"
        value={form.max_stock_level} onChange={(e) => patch("max_stock_level", e.target.value)} />)}
      {fld("حد إعادة الطلب", <input className="aseel-input" type="number" min="0" step="0.001"
        value={form.reorder_level} onChange={(e) => patch("reorder_level", e.target.value)} />)}
      {fld("تاريخ آخر حركة", <input className="aseel-input" readOnly value="(تلقائي)" />)}
      <div style={{ gridColumn: "1/-1", fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>
        ملاحظة: جميع حركات المخازن ذات التاريخ قبل بداية الفترة المالية ترحل إلى رصيد أول المدة.
        للوصول إلى ثوابت المجموعة اضغط زر «ثوابت المجموعة» في الشريط العلوي أو المفتاح F11.
      </div>
    </div>
  );

  // ── صفحة 3: أسعار البيع والشراء (5+5) ──
  const tierTable = (
    tiers: PriceTier[], label: string,
    onUpdate: (i: number, k: keyof PriceTier, v: string | boolean) => void
  ) => (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontWeight: 600, fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)", marginBottom: 4, paddingRight: 4 }}>
        {label}
      </div>
      <table className="aseel-grid">
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
              <td className="aseel-num">{i + 1}</td>
              <td>
                <input className="aseel-input" type="number" min="0" step="0.01"
                  value={t.price} onChange={(e) => onUpdate(i, "price", e.target.value)} />
              </td>
              <td>
                <input className="aseel-input" value={t.currency}
                  onChange={(e) => onUpdate(i, "currency", e.target.value)} placeholder="ILS" />
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
  const profitTone = previewProfit == null ? "var(--aseel-ink)"
    : previewProfit < 0 ? "var(--aseel-danger,#c00)" : "var(--aseel-ok,#267346)";

  const tabPrices = (
    <div style={{ padding: "8px 4px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginBottom: 14 }}>
        {fld("سعر البيع العام (يدوي)",
          <input className="aseel-input aseel-input--hl" type="number" min="0" step="0.01"
            value={form.sale_price} onChange={(e) => patch("sale_price", e.target.value)}
            title="يُقترح في مستند البيع فقط للزبون الذي لا عرض سعر له ولا شراء سابق لهذا الصنف"
            placeholder="للزبون بلا عرض ولا شراء سابق" />)}
        {fld("سعر التكلفة (متوسط — محسوب)",
          <input className="aseel-input" readOnly value={formatMoney(insights.profile?.avg_cost ?? "", "—")} />)}
        {fld("الربح للوحدة",
          <input className="aseel-input" readOnly style={{ color: profitTone, fontWeight: 600 }}
            value={previewProfit != null ? formatMoney(previewProfit) : "—"} />)}
        {fld("هامش الربح %",
          <input className="aseel-input" readOnly style={{ color: profitTone }}
            value={previewMargin != null ? `${formatMoney(previewMargin)}%` : "—"} />)}
        {fld("آخر سعر بيع (فاتورة مرحّلة)",
          <input className="aseel-input" readOnly
            value={formatMoney(insights.profile?.last_sale_price ?? "", "—")} />)}
        {fld("آخر سعر شراء (فاتورة مرحّلة)",
          <input className="aseel-input" readOnly
            value={formatMoney(insights.profile?.last_purchase_price ?? "", "—")} />)}
      </div>
      {pendingN8("فئات الأسعار الخمس تُعرَض ولكن لا تُحفَظ بعد — تَنتظر N8-T9 (ProductPriceTier migration).")}
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
  const tabTrading = (
    <div style={{ padding: "8px 4px" }}>
      {pendingN8("حقول overrides الحسابات لا تُحفَظ بعد — تَنتظر N8-T10.")}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 8 }}>
      {fld("حساب البيع", <input className="aseel-input" value={form.sale_account}
        onChange={(e) => patch("sale_account", e.target.value)} placeholder="رقم الحساب (+ فهرس)" />)}
      {fld("حساب مرجع البيع", <input className="aseel-input" value={form.sale_return_account}
        onChange={(e) => patch("sale_return_account", e.target.value)} />)}
      {fld("حساب الشراء", <input className="aseel-input" value={form.purchase_account}
        onChange={(e) => patch("purchase_account", e.target.value)} />)}
      {fld("حساب مرجع الشراء", <input className="aseel-input" value={form.purchase_return_account}
        onChange={(e) => patch("purchase_return_account", e.target.value)} />)}
      {fld("حساب المورد", <input className="aseel-input" value={form.supplier_account}
        onChange={(e) => patch("supplier_account", e.target.value)} />)}
      {fld("حساب بضاعة آخر المدة", <input className="aseel-input" value={form.ending_inventory_account}
        onChange={(e) => patch("ending_inventory_account", e.target.value)} />)}
      <div style={{ gridColumn: "1/-1", fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>
        اترك الحقل فارغاً لاستخدام القيم الافتراضية من ثوابت المجموعة. استخدم + لفهرس الحسابات.
      </div>
      </div>
    </div>
  );

  // ── صفحة 5: بيانات أخرى ──
  const tabOther = (
    <div style={{ padding: "8px 4px" }}>
      {pendingN8("الكميات الإضافية لا تُحفَظ بعد — حقل backend غير متوفّر.")}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 8 }}>
        {fld("إضافي بعد الكمية", <input className="aseel-input" type="number" min="0" step="1"
          value={form.bonus_after_qty} onChange={(e) => patch("bonus_after_qty", e.target.value)} />)}
        {fld("إضافي كل كمية", <input className="aseel-input" type="number" min="1" step="1"
          value={form.bonus_every_qty} onChange={(e) => patch("bonus_every_qty", e.target.value)} />)}
        <div style={{ gridColumn: "1/-1", fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>
          مثال: إضافي 1 بعد كل 10 وحدات مشتراة.
        </div>
      </div>
    </div>
  );

  // ── صفحة 6: معادلات التصنيع ──
  const cmpColumns: AseelGridColumn<ComponentLine>[] = [
    { key: "seq", header: "مسلسل", width: "55px", align: "center", readOnly: true },
    { key: "component_sku", header: "رقم الصنف (المكوّن)", width: "200px" },
    { key: "quantity", header: "الكمية", width: "100px", align: "center", type: "number" },
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const cmpGetCell = (row: ComponentLine, key: string): string | number => {
    const idx = form.components.findIndex((c) => c.key === row.key);
    if (key === "seq") return idx + 1;
    if (key === "component_sku") return row.component_sku;
    if (key === "quantity") return row.quantity;
    return "";
  };

  cmpColumns[3].render = (row: ComponentLine) => (
    <button type="button" className="aseel-iconbtn aseel-iconbtn--danger"
      onClick={() => patch("components", form.components.filter((c) => c.key !== row.key))}>
      <Trash2 className="h-3 w-3" />
    </button>
  );

  const tabManufacturing = (
    <div style={{ padding: "8px 4px" }}>
      <AseelGrid<ComponentLine>
        columns={cmpColumns}
        rows={form.components}
        getCell={cmpGetCell}
        getRowKey={(c) => c.key}
        onChange={(rowIdx, key, val) => {
          const next = [...form.components];
          if (key === "component_sku") next[rowIdx] = { ...next[rowIdx], component_sku: val };
          if (key === "quantity") next[rowIdx] = { ...next[rowIdx], quantity: val };
          patch("components", next);
        }}
        onAddRow={() => patch("components", [...form.components, { key: newCmpKey(), component_sku: "", quantity: "1" }])}
        emptyHint="لا توجد مكوّنات — أضف صنفاً داخلاً في التصنيع"
      />
      <button type="button" className="aseel-addrow" onClick={() =>
        patch("components", [...form.components, { key: newCmpKey(), component_sku: "", quantity: "1" }])
      }>
        <Plus className="h-3 w-3" /> إضافة مكوّن
      </button>
    </div>
  );

  return (
    <div dir="rtl">
      <AseelDocumentShell
        title="كرت الصنف"
        state={currentId ? `صنف #${currentId}` : "صنف جديد"}
        initialTab={openingTab}
        nav={nav}
        actions={toolbarActions}
        header={
          <>
            {fld("رقم الصنف", <input className="aseel-input" readOnly
              value={currentId ? `#${currentId}` : "— جديد —"} />)}
            {fld("SKU", <input className="aseel-input aseel-input--hl" value={form.sku}
              onChange={(e) => patch("sku", e.target.value)} />)}
            {fld("الاسم", <input className="aseel-input" readOnly
              value={form.name_ar || form.name_en || "—"} />)}
            {fld("التصنيف", <input className="aseel-input" readOnly value={form.category_name || "—"} />)}
            {fld("نوع الصنف", <input className="aseel-input" readOnly
              value={ITEM_TYPES.find((t) => t.v === form.item_type)?.l ?? form.item_type} />)}
            {/* الأرقام القيادية في شريط الرأس — تُرى قبل فتح أي تبويب. */}
            {fld("سعر البيع", <input className="aseel-input" readOnly
              value={formatMoney(insights.profile?.effective_sale_price ?? form.sale_price, "—")} />)}
            {fld("سعر التكلفة", <input className="aseel-input" readOnly
              value={formatMoney(insights.profile?.avg_cost ?? "", "—")} />)}
            {fld("الرصيد", <input className="aseel-input" readOnly
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
          { key: "mfg", label: "معادلات التصنيع", content: tabManufacturing },
          // آخر القائمة: تفعيل التتبّع يُلحق تبويباً ولا يزحزح فهرس تبويب قائم
          // (الغلاف يتتبّع النشط بالفهرس) — فيبقى المستخدم حيث هو.
          ...(insights.serialsTab ? [insights.serialsTab] : []),
        ]}
        totals={
          <div style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)", padding: "4px 0", display: "grid", gap: 2 }}>
            <div>سعر البيع: <b style={{ color: "var(--aseel-ink)" }}>
              {formatMoney(insights.profile?.effective_sale_price ?? form.sale_price, "—")}</b></div>
            <div>سعر التكلفة: <b style={{ color: "var(--aseel-ink)" }}>
              {formatMoney(insights.profile?.avg_cost ?? "", "—")}</b></div>
            <div>الربح للوحدة: <b style={{ color: profitTone }}>
              {formatMoney(insights.profile?.profit_per_unit ?? (previewProfit ?? ""), "—")}</b></div>
          </div>
        }
        status={
          <>
            <span className="aseel-status-item">رقم الصنف <b>{currentId ?? "—"}</b></span>
            <span className="aseel-status-item">الرصيد <b>{formatQuantity(insights.profile?.quantity_on_hand ?? "", "—")}</b></span>
            <span className="aseel-status-item">المتاح <b>{formatQuantity(insights.profile?.available_quantity ?? "", "—")}</b></span>
            <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="aseel-status-item">آخر مفتاح <b>{lastKey}</b></span>
          </>
        }
      >
        {banner}
      </AseelDocumentShell>
    </div>
  );
};
