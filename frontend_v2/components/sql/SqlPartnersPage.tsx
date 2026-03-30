import React, { useEffect, useMemo, useState } from "react";
import { apiGetList } from "../../services/restApi";
import { SqlDataPageShell } from "./SqlDataPageShell";
import { Users, Eye, Phone, Mail } from "lucide-react";

type PartnerRow = {
  id: number;
  name: string;
  partner_type?: string;
  phone?: string | null;
  email?: string | null;
  linked_account?: any;
};

export function SqlPartnersPage() {
  const [rows, setRows] = useState<PartnerRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PartnerRow | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string>("all");

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setErr(null);
    apiGetList<PartnerRow>("partners/", { tenantId: 1 })
      .then((data) => mounted && setRows(data))
      .catch((e) => mounted && setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (typeFilter !== "all" && (r.partner_type || "") !== typeFilter) return false;
      if (!s) return true;
      const txt = `${r.name || ""} ${r.partner_type || ""} ${r.phone || ""} ${r.email || ""}`.toLowerCase();
      return txt.includes(s);
    });
  }, [rows, q, typeFilter]);

  const partnerTypes = useMemo(() => Array.from(new Set(rows.map((x) => x.partner_type).filter(Boolean) as string[])), [rows]);

  return (
    <>
    <SqlDataPageShell
      title="الموردين والشركاء"
      subtitle="بيانات الموردين والشركاء من قاعدة البيانات."
      actions={
        <div className="flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="بحث بالاسم/النوع/الهاتف..."
            className="w-72 max-w-[70vw] px-3 py-2 border rounded-lg text-sm"
          />
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-2 border rounded-lg text-sm"
          >
            <option value="all">كل الأنواع</option>
            {partnerTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      }
    >
      {err ? (
        <div className="p-4 text-sm text-red-700 bg-red-50 border-b border-red-100">
          {err}
        </div>
      ) : null}

      <div className="p-4 border-b bg-gray-50/70">
        <div className="bg-white border rounded-lg p-3 inline-block">
          <div className="text-xs text-gray-500">إجمالي الموردين/الشركاء</div>
          <div className="text-xl font-bold flex items-center gap-2"><Users className="w-4 h-4 text-blue-600" />{rows.length}</div>
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
                  <div className="font-bold text-sm">{r.name}</div>
                  <div className="text-xs text-gray-500 mt-1">{r.partner_type || "-"}</div>
                  <div className="text-xs text-gray-500 mt-1 flex flex-wrap gap-2">
                    <span className="inline-flex items-center gap-1"><Phone className="w-3 h-3" />{r.phone || "-"}</span>
                    <span className="inline-flex items-center gap-1"><Mail className="w-3 h-3" />{r.email || "-"}</span>
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
            <div className="font-bold">تفاصيل المورد/الشريك</div>
            <button className="px-3 py-1 text-sm rounded border" onClick={() => setDetailsOpen(false)}>إغلاق</button>
          </div>
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">ID:</span> {selected?.id || "-"}</div>
            <div><span className="text-gray-500">الاسم:</span> {selected?.name || "-"}</div>
            <div><span className="text-gray-500">النوع:</span> {selected?.partner_type || "-"}</div>
            <div><span className="text-gray-500">الهاتف:</span> {selected?.phone || "-"}</div>
            <div><span className="text-gray-500">البريد:</span> {selected?.email || "-"}</div>
            <div><span className="text-gray-500">الحساب المرتبط:</span> {selected?.linked_account?.code ? `${selected.linked_account.code} - ${selected.linked_account.name}` : "-"}</div>
          </div>
        </div>
      </div>
    )}
    </>
  );
}

