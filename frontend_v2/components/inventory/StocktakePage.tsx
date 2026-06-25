/**
 * T-I2 — مستند جرد فعلي (جرد).
 * إنشاء + ترحيل: يسوّي رصيد كل صنف ليطابق العدّ (ADJUST_IN/OUT) ويُنشئ قيد فرق
 * الجرد (المخزون ↔ ت.ب.م). يعتمد على /api/inventory/stocktakes/.
 */
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import { AseelDocumentShell, AseelAutocomplete, type AseelToolbarAction } from "../aseel";
import { Plus, Send, Trash2, RefreshCw, X, List, Save } from "lucide-react";

type Wh = { id: number; name: string };
type Prod = { id: number; sku: string; name_ar?: string; name_en?: string; quantity_on_hand?: string };
type Line = { product: number | ""; counted_quantity: string };
type StocktakeRow = {
  id: number; stocktake_number: string; stocktake_date: string;
  warehouse_name?: string | null; is_posted: boolean; journal?: number | null;
};

const prodLabel = (p?: Prod) => (p ? `${p.sku} — ${p.name_ar || p.name_en || ""}` : "");

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
  const [lines, setLines] = useState<Line[]>([{ product: "", counted_quantity: "0" }]);
  const [saving, setSaving] = useState(false);

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
      sub: `${p.sku}${p.quantity_on_hand != null ? ` · رصيد ${p.quantity_on_hand}` : ""}`,
    })),
    [sortedProducts],
  );
  // خيارات «القفز لصنف»: الكود أولاً في التسمية كي تطابق الكتابة فوراً (startsWith)
  // فيكفي كتابة الكود + Enter للقفز للصنف المطابق.
  const locateOptions = useMemo(
    () => sortedProducts.map((p) => ({
      id: p.id,
      label: `${p.sku} — ${p.name_ar || p.name_en || ""}`.trim(),
      sub: p.quantity_on_hand != null ? `رصيد ${p.quantity_on_hand}` : "",
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
  const addLine = () => setLines((ls) => [...ls, { product: "", counted_quantity: "0" }]);
  const removeLine = (i: number) => setLines((ls) => (ls.length <= 1 ? ls : ls.filter((_, idx) => idx !== i)));

  const loadAllProducts = () => {
    if (sortedProducts.length === 0) return;
    // الإدراج بالترتيب المُجمَّع بالمقاس ليسهل العدّ (المتطابقات متجاورة).
    const newLines = sortedProducts.map((p) => ({
      product: p.id,
      counted_quantity: p.quantity_on_hand || "0",
    }));
    setLines(newLines);
  };

  const resetForm = () => {
    setDate(today); setWarehouse(""); setNotes("");
    setLines([{ product: "", counted_quantity: "0" }]); setShowForm(false);
  };

  // حفظ الجرد: post=false ⇒ مسودة فقط (تُرحَّل لاحقاً من القائمة)، post=true ⇒ حفظ وترحيل.
  const save = async (post: boolean) => {
    setErr(null); setMsg(null);
    const filled = lines.filter((l) => l.product !== "");
    if (!filled.length) { setErr("أضف بنداً واحداً على الأقل"); return; }
    setSaving(true);
    try {
      const created = await inventoryApi.createStocktake({
        stocktake_date: date,
        warehouse: warehouse || null,
        notes,
        lines: filled.map((l) => ({ product: l.product, counted_quantity: l.counted_quantity || "0" })),
      });
      if (post) await inventoryApi.postStocktake(created.id);
      setMsg(post
        ? "✓ تم إنشاء الجرد وترحيله (تسوية المخزون + قيد الفرق)"
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

  const actions: AseelToolbarAction[] = [
    { key: "new", label: showForm ? "إخفاء النموذج" : "جرد جديد", icon: <Plus />, onClick: () => setShowForm((s) => !s) },
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
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                <label className="aseel-field"><span className="aseel-field-label">التاريخ</span>
                  <input type="date" className="aseel-input" value={date} onChange={(e) => setDate(e.target.value)} /></label>
                <label className="aseel-field"><span className="aseel-field-label">المستودع</span>
                  <select className="aseel-input" value={warehouse} onChange={(e) => setWarehouse(e.target.value ? Number(e.target.value) : "")}>
                    <option value="">— كل المخزون —</option>
                    {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select></label>
                <label className="aseel-field" style={{ flex: 1, minWidth: 160 }}><span className="aseel-field-label">ملاحظات</span>
                  <input className="aseel-input" value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
              </div>

              {/* قفز لصنف: اكتب الكود/الاسم → اختر أو Enter ⇒ تنزل القائمة على الصنف والمؤشّر بخانة الكمية */}
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

              <table className="aseel-grid" data-variant="list" style={{ marginBottom: 8 }}>
                <thead><tr><th>الصنف</th><th style={{ width: 110 }}>رصيد النظام</th><th style={{ width: 120 }}>الكمية المعدودة</th><th style={{ width: 40 }}></th></tr></thead>
                <tbody>
                  {lines.map((l, i) => {
                    const p = prodById(l.product);
                    return (
                      <tr key={i}>
                        <td>
                          <AseelAutocomplete
                            value={p ? (p.name_ar || p.name_en || p.sku) : ""}
                            options={productOptions}
                            onPick={(id) => updateLine(i, { product: Number(id) })}
                            placeholder="اكتب المقاس أو الاسم أو الكود للبحث…"
                          />
                        </td>
                        <td style={{ textAlign: "center", color: "var(--aseel-ink-soft)" }}>{p?.quantity_on_hand ?? "—"}</td>
                        <td><input type="number" min="0" step="any" className="aseel-input" style={{ width: "100%" }}
                          data-qty-for={l.product}
                          value={l.counted_quantity}
                          onChange={(e) => updateLine(i, { counted_quantity: e.target.value })}
                          onKeyDown={(e) => {
                            // بعد كتابة العدد + Enter ⇒ يرجع المؤشّر لمربع البحث للصنف التالي.
                            if (e.key === "Enter") {
                              e.preventDefault();
                              document.querySelector<HTMLInputElement>("#stocktake-locate input")?.focus();
                            }
                          }} /></td>
                        <td style={{ textAlign: "center" }}>
                          <button className="aseel-iconbtn" onClick={() => removeLine(i)} title="حذف"><Trash2 className="h-3 w-3" /></button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
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
            </div>
          )}

          <table className="aseel-grid" data-variant="list">
            <thead><tr><th style={{ width: 60 }}>#</th><th style={{ width: 110 }}>الرقم</th><th style={{ width: 110 }}>التاريخ</th><th>المستودع</th><th style={{ width: 140 }}>الحالة</th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={5} style={{ textAlign: "center", padding: 16, color: "var(--aseel-ink-soft)" }}>لا عمليات جرد</td></tr>}
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>{r.stocktake_number || "—"}</td>
                  <td>{r.stocktake_date}</td>
                  <td>{r.warehouse_name || "كل المخزون"}</td>
                  <td>
                    {r.is_posted ? <span style={{ color: "var(--aseel-ok,#2d7d46)", fontWeight: 600 }}>مُرحَّل {r.journal ? `#${r.journal}` : ""}</span>
                      : <button className="aseel-toolbtn" onClick={() => postExisting(r.id)}><Send className="h-3 w-3" /> ترحيل</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AseelDocumentShell>
    </div>
  );
};

export default StocktakePage;
