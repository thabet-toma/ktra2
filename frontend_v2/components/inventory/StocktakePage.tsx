/**
 * T-I2 — مستند جرد فعلي (جرد).
 * إنشاء + ترحيل: يسوّي رصيد كل صنف ليطابق العدّ (ADJUST_IN/OUT) ويُنشئ قيد فرق
 * الجرد (المخزون ↔ ت.ب.م). يعتمد على /api/inventory/stocktakes/.
 */
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import { AseelDocumentShell, type AseelToolbarAction } from "../aseel";
import { Plus, Send, Trash2, RefreshCw, X, List } from "lucide-react";

type Wh = { id: number; name: string };
type Prod = { id: number; sku: string; name_ar?: string; name_en?: string; quantity_on_hand?: string };
type Line = { product: number | ""; counted_quantity: string };
type StocktakeRow = {
  id: number; stocktake_number: string; stocktake_date: string;
  warehouse_name?: string | null; is_posted: boolean; journal?: number | null;
};

const prodLabel = (p?: Prod) => (p ? `${p.sku} — ${p.name_ar || p.name_en || ""}` : "");

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
  const updateLine = (i: number, patch: Partial<Line>) =>
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  const addLine = () => setLines((ls) => [...ls, { product: "", counted_quantity: "0" }]);
  const removeLine = (i: number) => setLines((ls) => (ls.length <= 1 ? ls : ls.filter((_, idx) => idx !== i)));

  const loadAllProducts = () => {
    if (products.length === 0) return;
    const newLines = products.map((p) => ({
      product: p.id,
      counted_quantity: p.quantity_on_hand || "0",
    }));
    setLines(newLines);
  };

  const resetForm = () => {
    setDate(today); setWarehouse(""); setNotes("");
    setLines([{ product: "", counted_quantity: "0" }]); setShowForm(false);
  };

  const saveAndPost = async () => {
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
      await inventoryApi.postStocktake(created.id);
      setMsg("✓ تم إنشاء الجرد وترحيله (تسوية المخزون + قيد الفرق)");
      resetForm();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ/الترحيل");
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

              <table className="aseel-grid" data-variant="list" style={{ marginBottom: 8 }}>
                <thead><tr><th>الصنف</th><th style={{ width: 110 }}>رصيد النظام</th><th style={{ width: 120 }}>الكمية المعدودة</th><th style={{ width: 40 }}></th></tr></thead>
                <tbody>
                  {lines.map((l, i) => {
                    const p = prodById(l.product);
                    return (
                      <tr key={i}>
                        <td>
                          <select className="aseel-input" style={{ width: "100%" }} value={l.product}
                            onChange={(e) => updateLine(i, { product: e.target.value ? Number(e.target.value) : "" })}>
                            <option value="">— اختر صنفاً —</option>
                            {products.map((pp) => <option key={pp.id} value={pp.id}>{prodLabel(pp)}</option>)}
                          </select>
                        </td>
                        <td style={{ textAlign: "center", color: "var(--aseel-ink-soft)" }}>{p?.quantity_on_hand ?? "—"}</td>
                        <td><input type="number" min="0" step="any" className="aseel-input" style={{ width: "100%" }}
                          value={l.counted_quantity} onChange={(e) => updateLine(i, { counted_quantity: e.target.value })} /></td>
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
                <button className="aseel-toolbtn" onClick={saveAndPost} disabled={saving} style={{ marginInlineStart: "auto" }}>
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
