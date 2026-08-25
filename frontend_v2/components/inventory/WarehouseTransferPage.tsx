/**
 * T-I1 — مستند تحويل بضاعة بين مستودعين.
 * إنشاء + ترحيل (صرف من المصدر/استلام في الوجهة بالتكلفة المتوسطة، صافي صفري على
 * إجمالي الشركة). يعتمد على /api/inventory/warehouse-transfers/.
 */
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { inventoryApi } from "../../services/inventoryApi";
import { KitDocumentShell, type KitToolbarAction } from "../kit";
import { Plus, Save, Send, Trash2, RefreshCw, X } from "lucide-react";
import { formatDateLocalized } from "../../utils/formatDate";

type Wh = { id: number; name: string; code?: string };
type Prod = { id: number; sku: string; name_ar?: string; name_en?: string };
type Line = { product: number | ""; quantity: string };
type TransferRow = {
  id: number; transfer_number: string; transfer_date: string;
  source_warehouse_name?: string; dest_warehouse_name?: string; is_posted: boolean;
};

const prodLabel = (p?: Prod) => (p ? `${p.sku} — ${p.name_ar || p.name_en || ""}` : "");

export const WarehouseTransferPage: React.FC = () => {
  const navigate = useNavigate();
  const today = new Date().toISOString().slice(0, 10);
  const [warehouses, setWarehouses] = useState<Wh[]>([]);
  const [products, setProducts] = useState<Prod[]>([]);
  const [rows, setRows] = useState<TransferRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  // form
  const [date, setDate] = useState(today);
  const [source, setSource] = useState<number | "">("");
  const [dest, setDest] = useState<number | "">("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<Line[]>([{ product: "", quantity: "1" }]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [whs, prods, transfers] = await Promise.all([
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<Wh[]>,
        inventoryApi.getProducts() as Promise<Prod[]>,
        inventoryApi.getWarehouseTransfers() as Promise<TransferRow[]>,
      ]);
      setWarehouses(whs || []);
      setProducts((Array.isArray(prods) ? prods : []) as Prod[]);
      setRows(transfers || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const updateLine = (i: number, patch: Partial<Line>) =>
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  const addLine = () => setLines((ls) => [...ls, { product: "", quantity: "1" }]);
  const removeLine = (i: number) => setLines((ls) => (ls.length <= 1 ? ls : ls.filter((_, idx) => idx !== i)));

  const resetForm = () => {
    setDate(today); setSource(""); setDest(""); setNotes("");
    setLines([{ product: "", quantity: "1" }]); setShowForm(false);
  };

  const saveAndPost = async () => {
    setErr(null); setMsg(null);
    if (!source || !dest) { setErr("اختر مستودع المصدر والوجهة"); return; }
    if (source === dest) { setErr("المصدر والوجهة متطابقان"); return; }
    const filled = lines.filter((l) => l.product !== "" && Number(l.quantity) > 0);
    if (!filled.length) { setErr("أضف بنداً واحداً على الأقل بكمية > 0"); return; }
    setSaving(true);
    try {
      const created = await inventoryApi.createWarehouseTransfer({
        transfer_date: date,
        source_warehouse: source,
        dest_warehouse: dest,
        notes,
        lines: filled.map((l) => ({ product: l.product, quantity: l.quantity })),
      });
      await inventoryApi.postWarehouseTransfer(created.id);
      setMsg("✓ تم إنشاء التحويل وترحيله");
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
      await inventoryApi.postWarehouseTransfer(id);
      setMsg("✓ تم الترحيل");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  const actions: KitToolbarAction[] = [
    { key: "new", label: showForm ? "إخفاء النموذج" : "تحويل جديد", icon: <Plus />, onClick: () => setShowForm((s) => !s) },
    { key: "refresh", label: "تحديث", icon: <RefreshCw className={loading ? "animate-spin" : ""} />, onClick: () => void load(), separatorBefore: true },
    { key: "back", label: "عودة", icon: <X />, onClick: () => navigate(-1), danger: true, separatorBefore: true },
  ];

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <KitDocumentShell title="تحويل بين المستودعات" state={`${rows.length} مستند`} actions={actions}>
        <div style={{ padding: 8 }}>
          {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: 8 }}>{err}</div>}
          {msg && <div className="ktra-banner" style={{ marginBottom: 8, color: "var(--ktra-ok,#2d7d46)" }}>{msg}</div>}

          {showForm && (
            <div className="ktra-bg-panel" style={{ border: "1px solid var(--ktra-border)", borderRadius: 6, padding: 10, marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                <label className="ktra-field"><span className="ktra-field-label">التاريخ</span>
                  <input type="date" className="ktra-input" value={date} onChange={(e) => setDate(e.target.value)} /></label>
                <label className="ktra-field"><span className="ktra-field-label">من مستودع</span>
                  <select className="ktra-input" value={source} onChange={(e) => setSource(e.target.value ? Number(e.target.value) : "")}>
                    <option value="">—</option>
                    {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select></label>
                <label className="ktra-field"><span className="ktra-field-label">إلى مستودع</span>
                  <select className="ktra-input" value={dest} onChange={(e) => setDest(e.target.value ? Number(e.target.value) : "")}>
                    <option value="">—</option>
                    {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select></label>
                <label className="ktra-field" style={{ flex: 1, minWidth: 160 }}><span className="ktra-field-label">ملاحظات</span>
                  <input className="ktra-input" value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
              </div>

              <table className="ktra-grid" data-variant="list" style={{ marginBottom: 8 }}>
                <thead><tr><th>الصنف</th><th style={{ width: 120 }}>الكمية</th><th style={{ width: 40 }}></th></tr></thead>
                <tbody>
                  {lines.map((l, i) => (
                    <tr key={i}>
                      <td>
                        <select className="ktra-input" style={{ width: "100%" }} value={l.product}
                          onChange={(e) => updateLine(i, { product: e.target.value ? Number(e.target.value) : "" })}>
                          <option value="">— اختر صنفاً —</option>
                          {products.map((p) => <option key={p.id} value={p.id}>{prodLabel(p)}</option>)}
                        </select>
                      </td>
                      <td><input type="number" min="0" step="any" className="ktra-input" style={{ width: "100%" }}
                        value={l.quantity} onChange={(e) => updateLine(i, { quantity: e.target.value })} /></td>
                      <td style={{ textAlign: "center" }}>
                        <button className="ktra-iconbtn" onClick={() => removeLine(i)} title="حذف"><Trash2 className="h-3 w-3" /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="ktra-toolbtn" onClick={addLine}><Plus className="h-4 w-4" /> سطر</button>
                <button className="ktra-toolbtn" onClick={saveAndPost} disabled={saving} style={{ marginInlineStart: "auto" }}>
                  {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} حفظ وترحيل
                </button>
              </div>
            </div>
          )}

          <table className="ktra-grid" data-variant="list">
            <thead><tr><th style={{ width: 60 }}>#</th><th style={{ width: 110 }}>الرقم</th><th style={{ width: 110 }}>التاريخ</th><th>من</th><th>إلى</th><th style={{ width: 110 }}>الحالة</th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={6} style={{ textAlign: "center", padding: 16, color: "var(--ktra-ink-soft)" }}>لا تحويلات</td></tr>}
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>{r.transfer_number || "—"}</td>
                  <td>{formatDateLocalized(r.transfer_date)}</td>
                  <td>{r.source_warehouse_name}</td>
                  <td>{r.dest_warehouse_name}</td>
                  <td>
                    {r.is_posted ? <span style={{ color: "var(--ktra-ok,#2d7d46)", fontWeight: 600 }}>مُرحَّل</span>
                      : <button className="ktra-toolbtn" onClick={() => postExisting(r.id)}><Send className="h-3 w-3" /> ترحيل</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </KitDocumentShell>
    </div>
  );
};

export default WarehouseTransferPage;
