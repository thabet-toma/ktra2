/**
 * T-I2 — مستند جرد فعلي (جرد).
 * إنشاء + ترحيل: يسوّي رصيد كل صنف ليطابق العدّ (ADJUST_IN/OUT) ويُنشئ قيد فرق
 * الجرد (المخزون ↔ ت.ب.م). يعتمد على /api/inventory/stocktakes/.
 */
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import { AseelDocumentShell, AseelAutocomplete, type AseelToolbarAction } from "../aseel";
import { ProductCardModal } from "../shared/ProductCardModal";
import { formatQuantity } from "../../utils/formatNumber";
import { clientLogger } from "../../services/logger";
import { Plus, Send, Trash2, RefreshCw, X, List, Save, Printer, Info } from "lucide-react";

type Wh = { id: number; name: string };
type Prod = { id: number; sku: string; name_ar?: string; name_en?: string; quantity_on_hand?: string };
// sys/variance: لقطة محفوظة تُستخدم فقط عند عرض جرد مُرحَّل (read-only)؛ في المسودة
// يُحسب الفرق حياً من رصيد النظام الحالي.
type Line = { product: number | ""; counted_quantity: string; sys?: string; variance?: string; selected?: boolean };
// أوضاع فلتر مراجعة الجرد: الكل / المعدود / غير المعدود / الفروقات فقط.
type FilterMode = "all" | "counted" | "uncounted" | "variance";
const FILTER_OPTIONS: { value: FilterMode; label: string }[] = [
  { value: "all", label: "الكل" },
  { value: "counted", label: "المعدود فقط" },
  { value: "uncounted", label: "غير المعدود فقط" },
  { value: "variance", label: "الفروقات فقط" },
];
// لاحقة عنوان الطباعة حسب الفلتر (الكل بلا لاحقة).
const FILTER_PRINT_SUFFIX: Record<FilterMode, string> = {
  all: "", counted: " — المعدود", uncounted: " — غير المعدود", variance: " — الفروقات فقط",
};
type StocktakeRow = {
  id: number; stocktake_number: string; stocktake_date: string;
  warehouse_name?: string | null; is_posted: boolean; journal?: number | null;
};

const prodLabel = (p?: Prod) => (p ? `${p.sku} — ${p.name_ar || p.name_en || ""}` : "");

/** يُنسّق كمية/فرقاً نصياً مع تشذيب الأصفار الزائدة (255.0000 ⇒ 255، 2.5000 ⇒ 2.5). */
const trimNum = (n: number) => formatQuantity(n, "0");
/** يُنسّق رصيداً قادماً من الـ API (نص مثل "6.00000") للعرض؛ يُرجع "—" إذا غاب. */
const trimQty = (v: unknown) =>
  v === null || v === undefined || v === "" ? "—" : formatQuantity(v, "—");

/**
 * يستخرج مقاس الإطار (عرض/نسبة/قطر مثل 255/65/15 أو 31/10.5/15) من اسم الصنف
 * لتجميع المقاسات المتطابقة بجانب بعضها — دون الحاجة لكود مخصّص. النمط مشدَّد على
 * أبعاد إطار معقولة (عرض 2-3 خانات، نسبة 1-2، قطر خانتان) كي لا تُلتقط أرقام أو
 * تواريخ عادية بالخطأ. يُرجع null لأي اسم لا يحوي مقاساً (الأصناف العادية) ⇒ تُرتَّب
 * هذه بترتيب الكود الطبيعي، فلا يتأثر أصحاب الأصناف غير العجال.
 */
const tireSizeKey = (name: string): { d: number; w: number; a: number } | null => {
  // حدّان (?<!\d) و (?!\d) يجعلان المقاس «رمزاً مستقلاً» فلا يُلتقط جزء من رقم أطول
  // أو تاريخ (مثل 12/5/2024 ⇒ القطر 2024 من 4 خانات يفشل) ولا من 1255/65/15.
  const m = (name || "").match(/(?<!\d)(\d{2,3})\s*\/\s*(\d{1,2}(?:\.\d)?)\s*\/\s*(\d{2}(?:\.\d)?)(?!\d)/);
  if (!m) return null;
  return { w: parseFloat(m[1]), a: parseFloat(m[2]), d: parseFloat(m[3]) };
};

export const StocktakePage: React.FC = () => {
  const navigate = useNavigate();
  const today = new Date().toISOString().slice(0, 10);
  const [warehouses, setWarehouses] = useState<Wh[]>([]);
  const [products, setProducts] = useState<Prod[]>([]);
  const [rows, setRows] = useState<StocktakeRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [date, setDate] = useState(today);
  const [warehouse, setWarehouse] = useState<number | "">("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<Line[]>([{ product: "", counted_quantity: "", selected: false }]);
  const [saving, setSaving] = useState(false);
  // فلتر المراجعة: الكل / المعدود / غير المعدود / الفروقات فقط — للعرض والطباعة.
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  // بطاقة الصنف (مودال مشترك) — تُفتح بالنقر على زر المعلومات بجانب الصنف.
  const [cardProductId, setCardProductId] = useState<number | null>(null);
  // فتح مستند محفوظ: editingId = معرّف الجرد المفتوح (null = إنشاء جديد)؛
  // editingPosted = هل هو مُرحَّل (عرض فقط، لا تعديل).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingPosted, setEditingPosted] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [whs, prods, takes] = await Promise.all([
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<Wh[]>,
        inventoryApi.getProducts() as Promise<Prod[]>,
        inventoryApi.getStocktakes() as Promise<StocktakeRow[]>,
      ]);
      setWarehouses(whs || []);
      setProducts((Array.isArray(prods) ? prods : []) as Prod[]);
      setRows(takes || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const prodById = (id: number | "") => products.find((p) => p.id === Number(id));

  // فرق السطر = المعدودة − رصيد النظام. يُرجع null إذا لم تُعَدّ بعد (خانة فارغة)
  // كي لا يُحسب الفراغ صفراً (السطر غير المعدود لا يُرحَّل ولا يُصفِّر الصنف).
  const lineDiff = (l: Line): number | null => {
    if (String(l.counted_quantity).trim() === "") return null;
    const cnt = Number(l.counted_quantity);
    if (Number.isNaN(cnt)) return null;
    const sys = Number(prodById(l.product)?.quantity_on_hand ?? 0);
    return cnt - sys;
  };

  // رصيد النظام المعروض: لقطة المستند عند العرض المُرحَّل، وإلا الرصيد الحالي الحي.
  const lineSys = (l: Line): string =>
    editingPosted ? trimQty(l.sys) : trimQty(prodById(l.product)?.quantity_on_hand);
  // الفرق المعروض: المخزَّن عند العرض المُرحَّل، وإلا المحسوب حياً من رصيد النظام.
  const lineVariance = (l: Line): number | null =>
    editingPosted ? (l.variance != null ? Number(l.variance) : null) : lineDiff(l);

  // هل يطابق السطر الفلتر الحالي — مصدر حقيقة واحد للعرض والطباعة (DRY).
  // الأسطر الفارغة (بلا صنف) لا تطابق أي فلتر مقيّد؛ في وضع «الكل» تبقى ظاهرة للإضافة.
  const matchesFilter = (l: Line): boolean => {
    if (l.product === "") return false;
    const counted = String(l.counted_quantity).trim() !== "";
    switch (filterMode) {
      case "counted": return counted;
      case "uncounted": return !counted;
      case "variance": { const d = lineVariance(l); return d !== null && d !== 0; }
      default: return true;
    }
  };

  // ملخص المراجعة: كم صنفاً عُدّ، كم منها فرقه ≠ 0، وكم أُدرج بلا عدّ بعد.
  const { countedCount, varianceCount, uncountedCount } = useMemo(() => {
    let counted = 0, variance = 0, uncounted = 0;
    for (const l of lines) {
      if (l.product === "") continue;
      if (String(l.counted_quantity).trim() === "") { uncounted++; continue; }
      counted++;
      const d = lineVariance(l);
      if (d !== null && d !== 0) variance++;
    }
    return { countedCount: counted, varianceCount: variance, uncountedCount: uncounted };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, products, editingPosted]);

  // ترتيب الأصناف بحيث تتجاور المقاسات المتطابقة (مثل 255/65/15 بمختلف الشركات)؛
  // الأصناف بلا مقاس تُرتَّب أخيراً أبجدياً. مشتق من الاسم — بلا كود مخصّص.
  const sortedProducts = useMemo(() => {
    const nameOf = (p: Prod) => p.name_ar || p.name_en || p.sku;
    // ترتيب الكود الطبيعي (000073 < 000087) — هو الترتيب الافتراضي لمن لا مقاس لهم.
    const byCode = (a: Prod, b: Prod) =>
      (a.sku || "").localeCompare(b.sku || "", undefined, { numeric: true });
    return [...products].sort((x, y) => {
      const kx = tireSizeKey(nameOf(x)), ky = tireSizeKey(nameOf(y));
      // كلاهما بمقاس ⇒ تجميع المقاسات المتطابقة (ثم بالكود داخل المقاس الواحد).
      if (kx && ky) {
        return (kx.d - ky.d) || (kx.w - ky.w) || (kx.a - ky.a) || byCode(x, y);
      }
      // ذو المقاس يسبق عديم المقاس؛ والباقي (الأصناف العادية) بترتيب الكود.
      if (kx) return -1;
      if (ky) return 1;
      return byCode(x, y);
    });
  }, [products]);

  // خيارات المنتقي بالبحث: يطابق الاسم (يحوي المقاس) ثم الكود/الرصيد.
  const productOptions = useMemo(
    () => sortedProducts.map((p) => ({
      id: p.id,
      label: p.name_ar || p.name_en || p.sku,
      sub: `${p.sku}${p.quantity_on_hand != null ? ` · رصيد ${trimQty(p.quantity_on_hand)}` : ""}`,
    })),
    [sortedProducts],
  );
  // خيارات «القفز لصنف»: الكود أولاً في التسمية كي تطابق الكتابة فوراً (startsWith)
  // فيكفي كتابة الكود + Enter للقفز للصنف المطابق.
  const locateOptions = useMemo(
    () => sortedProducts.map((p) => ({
      id: p.id,
      label: `${p.sku} — ${p.name_ar || p.name_en || ""}`.trim(),
      sub: p.quantity_on_hand != null ? `رصيد ${trimQty(p.quantity_on_hand)}` : "",
    })),
    [sortedProducts],
  );

  // يُنزل القائمة على سطر الصنف ويضع المؤشّر في خانة الكمية (للعدّ من ورقة بترتيب مختلف).
  const locateProduct = (id: number) => {
    const el = document.querySelector<HTMLInputElement>(`[data-qty-for="${id}"]`);
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      el.focus();
      el.select();
    }
  };

  const updateLine = (i: number, patch: Partial<Line>) =>
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  const addLine = () => setLines((ls) => [...ls, { product: "", counted_quantity: "", selected: false }]);
  const removeLine = (i: number) => setLines((ls) => (ls.length <= 1 ? ls : ls.filter((_, idx) => idx !== i)));

  const loadAllProducts = () => {
    if (sortedProducts.length === 0) return;
    // الإدراج بالترتيب المُجمَّع بالمقاس ليسهل العدّ (المتطابقات متجاورة).
    // الكمية المعدودة تبدأ فارغة عمداً — يعبّئها المستخدم بالعدّ الفعلي (لا تُملأ
    // برصيد النظام كي لا يُرحَّل صنف بلا عدّ فعلي).
    const newLines = sortedProducts.map((p) => ({
      product: p.id,
      counted_quantity: "",
      selected: false,
    }));
    setLines(newLines);
  };

  const resetForm = () => {
    setDate(today); setWarehouse(""); setNotes(""); setFilterMode("all");
    setLines([{ product: "", counted_quantity: "", selected: false }]); setShowForm(false);
    setEditingId(null); setEditingPosted(false);
  };

  // فتح مستند جرد محفوظ للعرض/المتابعة: المسودة تُفتح للتعديل، والمُرحَّل للعرض فقط.
  const openStocktake = async (id: number) => {
    setErr(null); setMsg(null);
    try {
      const d = await inventoryApi.getStocktake(id);
      setDate(d.stocktake_date || today);
      setWarehouse(d.warehouse ?? "");
      setNotes(d.notes || "");
      setLines((d.lines || []).map((ln: any) => ({
        product: ln.product,
        counted_quantity: ln.counted_quantity != null ? trimNum(Number(ln.counted_quantity)) : "",
        sys: ln.system_quantity != null ? trimNum(Number(ln.system_quantity)) : undefined,
        variance: ln.variance != null ? String(ln.variance) : undefined,
        selected: false,
      })));
      setEditingId(id);
      setEditingPosted(!!d.is_posted);
      setFilterMode("all");
      setShowForm(true);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل فتح المستند");
    }
  };

  // حفظ الجرد: post=false ⇒ مسودة فقط (تُرحَّل لاحقاً من القائمة)، post=true ⇒ حفظ وترحيل.
  const save = async (post: boolean) => {
    setErr(null); setMsg(null);
    // يُرحَّل فقط ما عُدّ فعلاً: سطر بصنف + خانة معدودة غير فارغة. الأصناف المُدرَجة
    // بلا عدّ تُترك كما هي في النظام (لا تُصفَّر) — السلوك الاحترافي للجرد الجزئي.
    const filled = lines.filter((l) => l.product !== "" && String(l.counted_quantity).trim() !== "");
    if (!filled.length) { setErr("أدخل الكمية المعدودة لصنف واحد على الأقل"); return; }
    setSaving(true);
    try {
      const payload = {
        stocktake_date: date,
        warehouse: warehouse || null,
        notes,
        lines: filled.map((l) => ({ product: l.product, counted_quantity: l.counted_quantity })),
      };
      // مستند مفتوح ⇒ تحديث (PATCH)، وإلا إنشاء جديد.
      const doc = editingId != null
        ? await inventoryApi.updateStocktake(editingId, payload)
        : await inventoryApi.createStocktake(payload);
      if (post) await inventoryApi.postStocktake(doc.id);
      setMsg(post
        ? "✓ تم حفظ الجرد وترحيله (تسوية المخزون + قيد الفرق)"
        : editingId != null
          ? "✓ تم تحديث المسودة (بدون ترحيل)"
          : "✓ تم حفظ الجرد كمسودة (بدون ترحيل) — يمكنك ترحيله لاحقاً من القائمة");
      resetForm();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const postExisting = async (id: number) => {
    setErr(null); setMsg(null);
    try {
      await inventoryApi.postStocktake(id);
      setMsg("✓ تم الترحيل");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  // طباعة ورقة نتيجة الجرد — تحترم التحديد اليدوي (أو الفلتر كوضع افتراضي).
  const printSheet = () => {
    const explicitSelection = lines.some(l => l.selected);
    const rows = lines.filter((l) => l.product !== "").filter((l) => {
      if (explicitSelection) return l.selected;
      return matchesFilter(l);
    });
    if (!rows.length) { setErr("لا أصناف للطباعة (راجع الفلتر أو حدد أصنافاً)"); return; }
    const whName = warehouses.find((w) => w.id === Number(warehouse))?.name || "كل المخزون";
    const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
    const body = rows.map((l) => {
      const p = prodById(l.product);
      const name = p ? (p.name_ar || p.name_en || p.sku) : "—";
      const sysRaw = lineSys(l);
      const sys = sysRaw === "—" ? "—" : trimNum(Number(sysRaw));
      const cnt = String(l.counted_quantity).trim() === "" ? "—" : trimNum(Number(l.counted_quantity));
      const d = lineVariance(l);
      const diffTxt = d === null ? "—" : d > 0 ? `+${trimNum(d)}` : trimNum(d);
      const color = d === null || d === 0 ? "#555" : d > 0 ? "#15803d" : "#b91c1c";
      return `<tr><td>${esc(p?.sku || "")}</td><td style="text-align:right">${esc(name)}</td>`
        + `<td>${sys}</td><td>${cnt}</td><td style="color:${color};font-weight:700">${diffTxt}</td></tr>`;
    }).join("");
    const html = `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">`
      + `<title>نتيجة الجرد ${esc(date)}</title><style>`
      + `body{font-family:'Segoe UI',Tahoma,sans-serif;padding:18px;color:#111}`
      + `h1{font-size:18px;margin:0 0 4px}.meta{font-size:12px;color:#555;margin-bottom:12px}`
      + `table{width:100%;border-collapse:collapse;font-size:13px}`
      + `th,td{border:1px solid #bbb;padding:6px 8px;text-align:center}`
      + `th{background:#f0f0f0}@media print{button{display:none}}`
      + `</style></head><body>`
      + `<h1>نتيجة الجرد${FILTER_PRINT_SUFFIX[filterMode]}</h1>`
      + `<div class="meta">التاريخ: ${esc(date)} · المستودع: ${esc(whName)}`
      + `${notes ? ` · ملاحظات: ${esc(notes)}` : ""} · عدد الأصناف: ${rows.length}</div>`
      + `<table><thead><tr><th>الكود</th><th>الصنف</th><th>رصيد النظام</th><th>المعدودة</th><th>الفرق</th></tr></thead>`
      + `<tbody>${body}</tbody></table>`
      + `<script>window.onload=function(){window.print()}</script></body></html>`;
    const win = window.open("", "_blank", "width=900,height=700");
    if (!win) { setErr("تعذّر فتح نافذة الطباعة (قد يكون المتصفح يحجب النوافذ المنبثقة)"); return; }
    win.document.write(html);
    win.document.close();
  };

  const actions: AseelToolbarAction[] = [
    { key: "new", label: showForm ? "إخفاء النموذج" : "جرد جديد", icon: <Plus />, onClick: () => { if (showForm) setShowForm(false); else { resetForm(); setShowForm(true); } } },
    { key: "refresh", label: "تحديث", icon: <RefreshCw className={loading ? "animate-spin" : ""} />, onClick: () => void load(), separatorBefore: true },
    { key: "back", label: "عودة", icon: <X />, onClick: () => navigate(-1), danger: true, separatorBefore: true },
  ];

  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell title="الجرد (جرد المخزون)" state={`${rows.length} مستند`} actions={actions}>
        <div style={{ padding: 8 }}>
          {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: 8 }}>{err}</div>}
          {msg && <div className="aseel-banner" style={{ marginBottom: 8, color: "var(--aseel-ok,#2d7d46)" }}>{msg}</div>}

          {showForm && (
            <div className="aseel-bg-panel" style={{ border: "1px solid var(--aseel-border)", borderRadius: 6, padding: 10, marginBottom: 12 }}>
              {editingId != null && (
                <div className="aseel-banner" style={{ marginBottom: 8, color: editingPosted ? "#b45309" : "var(--aseel-ink)" }}>
                  {editingPosted
                    ? `عرض جرد مُرحَّل #${editingId} — للقراءة فقط (لا يمكن تعديله)`
                    : `تعديل مسودة جرد #${editingId} — راجع ثم احفظ أو رحّل`}
                </div>
              )}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                <label className="aseel-field"><span className="aseel-field-label">التاريخ</span>
                  <input type="date" className="aseel-input" value={date} disabled={editingPosted} onChange={(e) => setDate(e.target.value)} /></label>
                <label className="aseel-field"><span className="aseel-field-label">المستودع</span>
                  <select className="aseel-input" value={warehouse} disabled={editingPosted} onChange={(e) => setWarehouse(e.target.value ? Number(e.target.value) : "")}>
                    <option value="">— كل المخزون —</option>
                    {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select></label>
                <label className="aseel-field" style={{ flex: 1, minWidth: 160 }}><span className="aseel-field-label">ملاحظات</span>
                  <input className="aseel-input" value={notes} disabled={editingPosted} onChange={(e) => setNotes(e.target.value)} /></label>
              </div>

              {/* قفز لصنف: اكتب الكود/الاسم → اختر أو Enter ⇒ تنزل القائمة على الصنف والمؤشّر بخانة الكمية */}
              {!editingPosted && (
              <div id="stocktake-locate" style={{ marginBottom: 8, maxWidth: 480 }}>
                <span className="aseel-field-label">🔎 قفز لصنف (اكتب الكود ثم Enter — للعدّ بأي ترتيب)</span>
                <AseelAutocomplete
                  value=""
                  options={locateOptions}
                  onPick={(id) => locateProduct(Number(id))}
                  placeholder="اكتب رقم/اسم الصنف… ثم Enter للقفز إليه"
                  maxResults={12}
                />
              </div>
              )}

              {/* ملخص المراجعة + فلتر العرض (الكل/المعدود/غير المعدود/الفروقات) للعرض والطباعة */}
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 6, fontSize: 13 }}>
                <span style={{ color: "var(--aseel-ink-soft)" }}>
                  معدود: <b>{countedCount}</b> · فروقات: <b style={{ color: varianceCount ? "#b45309" : undefined }}>{varianceCount}</b> · غير معدود: <b>{uncountedCount}</b>
                </span>
                <label style={{ display: "inline-flex", alignItems: "center", gap: 6, marginInlineStart: "auto" }} title="تصفية الأصناف المعروضة (لا تؤثر على التحديد اليدوي)">
                  <span className="aseel-field-label">تصفية</span>
                  <select className="aseel-input" style={{ width: "auto" }} value={filterMode}
                    onChange={(e) => {
                      const mode = e.target.value as FilterMode;
                      setFilterMode(mode);
                      clientLogger.info("stocktake.filter", { mode });
                    }}>
                    {FILTER_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
                <button className="aseel-toolbtn" onClick={printSheet} title="طباعة ورقة نتيجة الجرد (تحترم الفلتر)"><Printer className="h-4 w-4" /> طباعة</button>
              </div>

              <table className="aseel-grid" data-variant="list" style={{ marginBottom: 8 }}>
                <thead><tr>
                  <th style={{ width: 36, textAlign: "center" }}>
                    <input type="checkbox" onChange={(e) => {
                      const checked = e.target.checked;
                      setLines(ls => ls.map(l => ({ ...l, selected: checked })));
                    }} title="تحديد/إلغاء تحديد الكل للطباعة" />
                  </th>
                  <th>الصنف</th>
                  <th style={{ width: "15%" }}>رصيد النظام</th>
                  <th style={{ width: "25%" }}>الكمية المعدودة</th>
                  <th style={{ width: "15%" }}>الفرق</th>
                  <th style={{ width: 40 }}></th>
                </tr></thead>
                <tbody>
                  {lines.map((l, i) => {
                    const p = prodById(l.product);
                    const d = lineVariance(l);
                    // الفلتر يُخفي ما لا يطابق الوضع المختار؛ وضع «الكل» يُبقي كل الأسطر
                    // (بما فيها الفارغة للإضافة). الأسطر المقيّدة تُخفي الفارغة تلقائياً.
                    if (filterMode !== "all" && !matchesFilter(l)) return null;
                    const diffColor = d === null || d === 0 ? "var(--aseel-ink-soft)" : d > 0 ? "#15803d" : "#b91c1c";
                    return (
                      <tr key={i}>
                        <td style={{ textAlign: "center" }}>
                          {l.product !== "" && (
                            <input 
                              type="checkbox" 
                              checked={!!l.selected} 
                              onChange={(e) => updateLine(i, { selected: e.target.checked })} 
                              title="تحديد للطباعة"
                            />
                          )}
                        </td>
                        <td>
                          {l.product !== "" ? (
                            // الصنف المختار يُعرض كاسم ثابت (غير قابل للتعديل) كي لا يتغيّر
                            // اسمه أو يُمحى بالخطأ؛ زر المعلومات يفتح بطاقة الصنف.
                            <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-start" }}>
                              {/* اسم الصنف قابل للنقر — يفتح بطاقة الصنف (كرت الصنف). */}
                              <button
                                type="button"
                                className="text-blue-700 hover:underline text-right"
                                style={{ fontWeight: 600, background: "none", border: "none", padding: 0, cursor: "pointer" }}
                                onClick={() => setCardProductId(Number(l.product))}
                                title={p ? `بطاقة الصنف: ${p.sku} — ${p.name_ar || p.name_en || ""}` : "بطاقة الصنف"}
                              >
                                {p ? (p.name_ar || p.name_en || p.sku) : "—"}
                              </button>
                              <button className="aseel-iconbtn" onClick={() => setCardProductId(Number(l.product))} title="بطاقة الصنف"><Info className="h-3 w-3" /></button>
                            </div>
                          ) : (
                            <AseelAutocomplete
                              value=""
                              options={productOptions}
                              onPick={(id) => updateLine(i, { product: Number(id) })}
                              onInfo={(id) => setCardProductId(Number(id))}
                              placeholder="اكتب المقاس أو الاسم أو الكود للبحث…"
                            />
                          )}
                        </td>
                        <td style={{ textAlign: "center", color: "var(--aseel-ink-soft)" }}>{lineSys(l)}</td>
                        <td><input type="number" min="0" step="any" className="aseel-input" style={{ width: "100%" }}
                          data-qty-for={l.product}
                          value={l.counted_quantity}
                          placeholder="عدّ…"
                          disabled={editingPosted}
                          onChange={(e) => updateLine(i, { counted_quantity: e.target.value })}
                          onKeyDown={(e) => {
                            // بعد كتابة العدد + Enter ⇒ يرجع المؤشّر لمربع البحث للصنف التالي.
                            if (e.key === "Enter") {
                              e.preventDefault();
                              document.querySelector<HTMLInputElement>("#stocktake-locate input")?.focus();
                            }
                          }} /></td>
                        <td style={{ textAlign: "center", fontWeight: 700, color: diffColor }}>
                          {d === null ? "—" : d > 0 ? `+${trimNum(d)}` : trimNum(d)}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          {!editingPosted && (
                            <button className="aseel-iconbtn" onClick={() => removeLine(i)} title="حذف"><Trash2 className="h-3 w-3" /></button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {editingPosted ? (
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="aseel-toolbtn" onClick={resetForm} style={{ marginInlineStart: "auto" }}><X className="h-4 w-4" /> إغلاق</button>
                </div>
              ) : (
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="aseel-toolbtn" onClick={addLine}><Plus className="h-4 w-4" /> سطر</button>
                  <button className="aseel-toolbtn" onClick={loadAllProducts} title="إدراج كافة الأصناف المسجلة"><List className="h-4 w-4" /> إدراج كل الأصناف</button>
                  <button className="aseel-toolbtn" onClick={() => void save(false)} disabled={saving} style={{ marginInlineStart: "auto" }} title="حفظ كمسودة بدون ترحيل — تُرحَّل لاحقاً من القائمة">
                    {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} حفظ
                  </button>
                  <button className="aseel-toolbtn" onClick={() => void save(true)} disabled={saving} title="حفظ وترحيل فوراً (تسوية المخزون + قيد الفرق)">
                    {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} حفظ وترحيل
                  </button>
                </div>
              )}
            </div>
          )}

          <table className="aseel-grid" data-variant="list">
            <thead><tr><th style={{ width: 60 }}>#</th><th style={{ width: 110 }}>الرقم</th><th style={{ width: 110 }}>التاريخ</th><th>المستودع</th><th style={{ width: 200 }}>الحالة</th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={5} style={{ textAlign: "center", padding: 16, color: "var(--aseel-ink-soft)" }}>لا عمليات جرد</td></tr>}
              {rows.map((r) => (
                // النقر على السطر يفتح المستند: المسودة للتعديل والمُرحَّل للعرض.
                <tr key={r.id} onClick={() => void openStocktake(r.id)} style={{ cursor: "pointer" }} title="انقر لفتح المستند">
                  <td>#{r.id}</td>
                  <td>{r.stocktake_number || "—"}</td>
                  <td>{r.stocktake_date}</td>
                  <td>{r.warehouse_name || "كل المخزون"}</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <button className="aseel-toolbtn" onClick={(e) => { e.stopPropagation(); void openStocktake(r.id); }}>
                        {r.is_posted ? "عرض" : "فتح"}
                      </button>
                      {r.is_posted
                        ? <span style={{ color: "var(--aseel-ok,#2d7d46)", fontWeight: 600 }}>مُرحَّل {r.journal ? `#${r.journal}` : ""}</span>
                        : <button className="aseel-toolbtn" onClick={(e) => { e.stopPropagation(); void postExisting(r.id); }}><Send className="h-3 w-3" /> ترحيل</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AseelDocumentShell>
      {cardProductId != null && (
        <ProductCardModal productId={cardProductId} onClose={() => setCardProductId(null)} />
      )}
    </div>
  );
};

export default StocktakePage;
