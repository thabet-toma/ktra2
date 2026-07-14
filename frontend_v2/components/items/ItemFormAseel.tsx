/**
 * N5-T4 — ItemFormAseel (F6) — inside-out نمط Aseel مع 6 صفحات
 * المرجع: المخازن.txt:11-25، القالب: SalesInvoiceEditor.tsx
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
  products: SqlProduct[];
  onSaved: () => void;
  onCancel: () => void;
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
  description: string; location: string;
  uom_primary: string; uom2: string; uom2_factor: string;
  uom3: string; uom3_factor: string;
  min_stock_level: string; max_stock_level: string; reorder_level: string;
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
  description: "", location: "",
  uom_primary: "عدد", uom2: "", uom2_factor: "1",
  uom3: "", uom3_factor: "1",
  min_stock_level: "", max_stock_level: "", reorder_level: "",
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

export const ItemFormAseel: React.FC<Props> = ({ productId, duplicateId, products, onSaved, onCancel }) => {
  const [form, setForm] = useState<FormState>(blankForm());
  const [currentId, setCurrentId] = useState<number | null>(productId);
  // W10: صنف موجود (تعديل) — اسمه يُحرَّر مباشرةً بحقل نصّي بدل منتقي «اختر/أضف»
  // الذي كان يحبس الاسم في قائمة منسدلة (نقر «+» يمسح القيمة) فيبدو «غير قابل للتعديل».
  const isExistingProduct = productId != null;
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lastKey, setLastKey] = useState("—");
  const [dsUploading, setDsUploading] = useState(false);

  const handleDatasheetUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
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

  const applyProduct = useCallback((p: Record<string, unknown>, isDuplicate = false) => {
    setForm((prev) => ({
      ...prev,
      sku: isDuplicate ? "" : String(p.sku ?? ""),
      catalog_no: isDuplicate ? "" : String(p.catalog_no ?? p.barcode ?? ""),
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
      category: p.category ? Number(p.category) : null,
      category_name: String(p.category_name ?? ""),
      item_type: String(p.item_type ?? "goods"),
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
        category: categoryId,
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
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: onCancel, danger: true },
  ];

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

  const tabPrices = (
    <div style={{ padding: "8px 4px" }}>
      {pendingN8("هذه القيم تُعرَض ولكن لا تُحفَظ بعد — تَنتظر N8-T9 (ProductPriceTier migration).")}
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
        title="كارت الصنف"
        state={currentId ? `صنف #${currentId}` : "صنف جديد"}
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
          </>
        }
        tabs={[
          { key: "general", label: "بيانات عامة", content: tabGeneral },
          { key: "balances", label: "الأرصدة والحركات", content: tabBalances },
          { key: "prices", label: "أسعار البيع والشراء", content: tabPrices },
          { key: "trading", label: "بيانات المتاجرة", content: tabTrading },
          { key: "other", label: "بيانات أخرى", content: tabOther },
          { key: "mfg", label: "معادلات التصنيع", content: tabManufacturing },
        ]}
        totals={
          <div style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)", padding: "4px 0" }}>
            سعر البيع فئة 1:{" "}
            <b>{form.sale_tiers[0]?.price || "0"} {form.sale_tiers[0]?.currency || "ILS"}</b>
          </div>
        }
        status={
          <>
            <span className="aseel-status-item">رقم الصنف <b>{currentId ?? "—"}</b></span>
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
