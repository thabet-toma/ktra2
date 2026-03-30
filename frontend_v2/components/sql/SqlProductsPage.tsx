import React, { useEffect, useMemo, useState } from "react";
import { apiGetList } from "../../services/restApi";
import { SqlDataPageShell } from "./SqlDataPageShell";
import { Package, Eye, Hash, Tag } from "lucide-react";

type ProductRow = {
  id: number;
  sku?: string;
  name_ar?: string;
  hs_code?: string | null;
  category?: any;
  is_active?: boolean;
};

export function SqlProductsPage() {
  const [rows, setRows] = useState<ProductRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ProductRow | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setErr(null);
    apiGetList<ProductRow>("inventory/products/", { tenantId: 1 })
      .then((data) => {
        if (!mounted) return;
        setRows(data);
      })
      .catch((e) => {
        if (!mounted) return;
        setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter((r) => {
      const txt = `${r.sku || ""} ${r.name_ar || ""} ${r.hs_code || ""}`.toLowerCase();
      return txt.includes(s);
    });
  }, [rows, q]);

  return (
    <>
    <SqlDataPageShell
      title="الأصناف"
      subtitle="بيانات الأصناف من قاعدة البيانات."
      actions={
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="بحث بالاسم/sku/HS..."
          className="w-72 max-w-[70vw] px-3 py-2 border rounded-lg text-sm"
        />
      }
    >
      {err ? (
        <div className="p-4 text-sm text-red-700 bg-red-50 border-b border-red-100">
          {err}
        </div>
      ) : null}

      <div className="p-4 border-b bg-gray-50/70 grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white border rounded-lg p-3">
          <div className="text-xs text-gray-500">إجمالي الأصناف</div>
          <div className="text-xl font-bold flex items-center gap-2"><Package className="w-4 h-4 text-blue-600" />{rows.length}</div>
        </div>
        <div className="bg-white border rounded-lg p-3">
          <div className="text-xs text-gray-500">فعالة</div>
          <div className="text-xl font-bold">{rows.filter((x) => x.is_active !== false).length}</div>
        </div>
      </div>

      <div className="p-3 space-y-2">
        {loading ? (
          <div className="p-4 text-gray-500 text-sm">جارِ التحميل...</div>
        ) : filtered.length === 0 ? (
          <div className="p-4 text-gray-500 text-sm">لا يوجد بيانات.</div>
        ) : (
          filtered.map((r) => (
            <div key={r.id} className="border rounded-xl p-3 bg-white hover:bg-gray-50 transition">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-bold text-sm truncate">{r.name_ar || "-"}</div>
                  <div className="text-xs text-gray-500 mt-1 flex items-center gap-2">
                    <span className="inline-flex items-center gap-1"><Hash className="w-3 h-3" />{r.sku || "-"}</span>
                    <span className="inline-flex items-center gap-1"><Tag className="w-3 h-3" />HS: {r.hs_code || "-"}</span>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setSelected(r);
                    setDetailsOpen(true);
                  }}
                  className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border text-sm hover:bg-gray-100"
                >
                  <Eye className="w-4 h-4" />
                  عرض التفاصيل
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </SqlDataPageShell>
    {detailsOpen && (
      <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-3" onClick={() => setDetailsOpen(false)}>
        <div className="bg-white rounded-xl w-full max-w-2xl max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
          <div className="sticky top-0 bg-white border-b px-4 py-3 flex items-center justify-between">
            <div className="font-bold">تفاصيل الصنف</div>
            <button className="px-3 py-1 text-sm rounded border" onClick={() => setDetailsOpen(false)}>إغلاق</button>
          </div>
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">ID:</span> {selected?.id || "-"}</div>
            <div><span className="text-gray-500">SKU:</span> {selected?.sku || "-"}</div>
            <div><span className="text-gray-500">الاسم:</span> {selected?.name_ar || "-"}</div>
            <div><span className="text-gray-500">HS Code:</span> {selected?.hs_code || "-"}</div>
            <div><span className="text-gray-500">الحالة:</span> {selected?.is_active === false ? "غير نشط" : "نشط"}</div>
          </div>
        </div>
      </div>
    )}
    </>
  );
}

