import React, { useEffect, useMemo, useState } from "react";
import { apiGetList, apiGetObject, apiPostObject } from "../../services/restApi";
import { SqlDataPageShell } from "./SqlDataPageShell";
import {
  Handshake,
  DollarSign,
  Clock3,
  CheckCircle2,
  Eye,
  ChevronDown,
  Calendar,
  Package,
  FileText,
} from "lucide-react";

type DealRow = {
  id: number;
  ref_number?: string;
  order_date?: string;
  total_amount?: string | number;
  status?: string;
  partner?: any;
  partner_name?: string;
  description?: string | null;
  payment_status?: string;
  items?: Array<{ id: number; product_name?: string; quantity?: string | number; unit_price?: string | number; total_price?: string | number; notes?: string | null }>;
  payments?: Array<{ id: number; title?: string; amount?: string | number; status?: string; due_date?: string | null; transfer_date?: string | null }>;
};
type PartnerOption = { id: number; name?: string; partner_type?: string };

export function SqlDealsPage() {
  const [rows, setRows] = useState<DealRow[]>([]);
  const [partners, setPartners] = useState<PartnerOption[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<DealRow | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [savingCreate, setSavingCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    ref_number: "",
    partner: "",
    order_date: new Date().toISOString().slice(0, 10),
    status: "Open",
    description: "",
  });

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setErr(null);
    apiGetList<DealRow>("logistics/deals/", { tenantId: 1 })
      .then((data) => mounted && setRows(data))
      .catch((e) => mounted && setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    apiGetList<PartnerOption>("partners/", { tenantId: 1 })
      .then((list) => setPartners(list))
      .catch(() => setPartners([]));
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (statusFilter !== "all" && (r.status || "") !== statusFilter) return false;
      if (!s) return true;
      const partnerName = r.partner?.name || r.partner_name || "";
      const txt = `${r.ref_number || ""} ${partnerName} ${r.status || ""} ${r.payment_status || ""} ${r.description || ""}`.toLowerCase();
      return txt.includes(s);
    });
  }, [rows, q, statusFilter]);

  const stats = useMemo(() => {
    const total = rows.length;
    const totalAmount = rows.reduce((sum, r) => sum + Number(r.total_amount || 0), 0);
    const active = rows.filter((r) => {
      const s = (r.status || "").toLowerCase();
      return !s.includes("closed") && !s.includes("cancel");
    }).length;
    const paid = rows.filter((r) => (r.payment_status || "").toLowerCase().includes("paid")).length;
    return { total, totalAmount, active, paid };
  }, [rows]);

  const statuses = useMemo(() => {
    const s = Array.from(new Set(rows.map((r) => r.status).filter(Boolean) as string[]));
    return s;
  }, [rows]);

  const statusClass = (status?: string) => {
    const s = (status || "").toLowerCase();
    if (s.includes("open")) return "bg-amber-50 text-amber-700 border-amber-200";
    if (s.includes("close")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (s.includes("ship")) return "bg-blue-50 text-blue-700 border-blue-200";
    return "bg-gray-50 text-gray-700 border-gray-200";
  };

  const paymentStatusClass = (status?: string) => {
    const s = (status || "").toLowerCase();
    if (s.includes("fully")) return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (s.includes("part")) return "bg-orange-50 text-orange-700 border-orange-200";
    if (s.includes("unpaid")) return "bg-red-50 text-red-700 border-red-200";
    return "bg-gray-50 text-gray-700 border-gray-200";
  };

  const statusLabel = (status?: string) => {
    const s = (status || "").toLowerCase();
    if (!s) return "-";
    if (s.includes("open")) return "نشطة";
    if (s.includes("close")) return "مغلقة";
    if (s.includes("cancel")) return "ملغاة";
    if (s.includes("ship")) return "قيد الشحن";
    if (s.includes("complete")) return "مكتملة";
    return status || "-";
  };

  const paymentStatusLabel = (status?: string) => {
    const s = (status || "").toLowerCase();
    if (!s) return "-";
    if (s.includes("fully")) return "مدفوعة كلياً";
    if (s.includes("part")) return "مدفوعة جزئياً";
    if (s.includes("unpaid")) return "غير مدفوعة";
    if (s.includes("paid")) return "مدفوعة";
    if (s.includes("confirm")) return "بانتظار التأكيد";
    return status || "-";
  };

  const openDeal = async (row: DealRow) => {
    setSelected(row);
    setDetailsOpen(true);
    setLoadingDetail(true);
    try {
      const data = await apiGetObject<DealRow>(`logistics/deals/${row.id}/`, { tenantId: 1 });
      setSelected(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingDetail(false);
    }
  };

  const refreshDeals = async () => {
    setLoading(true);
    try {
      const data = await apiGetList<DealRow>("logistics/deals/", { tenantId: 1 });
      setRows(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDeal = async () => {
    if (!createForm.ref_number.trim()) {
      setErr("رقم الصفقة مطلوب.");
      return;
    }
    if (!createForm.partner) {
      setErr("اختر المورد أولاً.");
      return;
    }
    setSavingCreate(true);
    setErr(null);
    try {
      await apiPostObject("logistics/deals/", {
        ref_number: createForm.ref_number.trim(),
        partner: Number(createForm.partner),
        order_date: createForm.order_date,
        status: createForm.status,
        description: createForm.description || null,
        currency: 1,
        items: [],
        payments: [],
      }, { tenantId: 1 });
      setCreateOpen(false);
      setCreateForm({
        ref_number: "",
        partner: "",
        order_date: new Date().toISOString().slice(0, 10),
        status: "Open",
        description: "",
      });
      await refreshDeals();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingCreate(false);
    }
  };

  const formatDate = (dateString?: string | null) => {
    if (!dateString) return "-";
    const d = new Date(dateString);
    if (Number.isNaN(d.getTime())) return String(dateString);
    return d.toLocaleDateString("en-GB");
  };

  const formatMoney = (amount: any) => {
    const n = Number(amount || 0);
    if (!Number.isFinite(n)) return String(amount ?? "-");
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  return (
    <>
    <SqlDataPageShell
      title="إدارة الصفقات"
      subtitle="اضغط على أي صفقة لرؤية التفاصيل الكاملة."
      actions={
        <div className="flex gap-2">
          <button
            onClick={() => setCreateOpen(true)}
            className="px-3 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700"
          >
            + صفقة جديدة
          </button>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="بحث برقم/مورد/حالة..."
            className="w-72 max-w-[70vw] px-3 py-2 border rounded-lg text-sm"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border rounded-lg text-sm"
          >
            <option value="all">كل الحالات</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      }
    >
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b bg-gray-50/70">
        <div className="bg-white border rounded-lg p-3">
          <div className="text-xs text-gray-500">إجمالي الصفقات</div>
          <div className="text-xl font-bold flex items-center gap-2"><Handshake className="w-4 h-4 text-blue-600" />{stats.total}</div>
        </div>
        <div className="bg-white border rounded-lg p-3">
          <div className="text-xs text-gray-500">القيمة الإجمالية</div>
          <div className="text-xl font-bold flex items-center gap-2"><DollarSign className="w-4 h-4 text-emerald-600" />{stats.totalAmount.toLocaleString()}</div>
        </div>
        <div className="bg-white border rounded-lg p-3">
          <div className="text-xs text-gray-500">الصفقات النشطة</div>
          <div className="text-xl font-bold flex items-center gap-2"><Clock3 className="w-4 h-4 text-amber-600" />{stats.active}</div>
        </div>
        <div className="bg-white border rounded-lg p-3">
          <div className="text-xs text-gray-500">صفقات بها دفعات</div>
          <div className="text-xl font-bold flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-green-600" />{stats.paid}</div>
        </div>
      </div>

      {err ? (
        <div className="p-4 text-sm text-red-700 bg-red-50 border-b border-red-100">
          {err}
        </div>
      ) : null}

      <div className="p-3 space-y-2">
        {loading ? (
          <div className="p-4 text-gray-500 text-sm">جارِ التحميل...</div>
        ) : filtered.length === 0 ? (
          <div className="p-4 text-gray-500 text-sm">لا يوجد بيانات.</div>
        ) : (
          filtered.map((r) => (
            <div
              key={r.id}
              className="border rounded-xl p-3 bg-white hover:bg-gray-50 transition shadow-sm"
            >
              <div
                className="flex items-center justify-between gap-3 cursor-pointer"
                onClick={() => setExpandedId((prev) => (prev === r.id ? null : r.id))}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="font-bold text-sm">{r.ref_number || "-"}</div>
                    <span className={`px-2 py-1 rounded-full text-[11px] border ${statusClass(r.status)}`}>
                      {statusLabel(r.status)}
                    </span>
                    <span className={`px-2 py-1 rounded-full text-[11px] border ${paymentStatusClass(r.payment_status)}`}>
                      {paymentStatusLabel(r.payment_status)}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1 flex items-center gap-3">
                    <span className="inline-flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {r.order_date || "-"}
                    </span>
                    <span>{r.partner?.name || r.partner_name || "-"}</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-sm">{String(r.total_amount ?? "-")}</div>
                  <div className="text-xs text-gray-500">USD</div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    openDeal(r);
                  }}
                  className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border text-sm hover:bg-gray-100"
                >
                  <Eye className="w-4 h-4" />
                  إدارة كاملة
                </button>
                <ChevronDown
                  className={`w-4 h-4 text-gray-500 transition-transform ${expandedId === r.id ? "rotate-180" : ""}`}
                />
              </div>
              {expandedId === r.id && (
                <div className="mt-3 pt-3 border-t grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">المورد</div>
                    <div className="font-medium">{r.partner?.name || r.partner_name || "-"}</div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">الوصف</div>
                    <div className="font-medium line-clamp-2">{r.description || "-"}</div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">الإجمالي</div>
                    <div className="font-bold text-blue-700">{String(r.total_amount ?? "-")}</div>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </SqlDataPageShell>
    {detailsOpen && (
      <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-3" onClick={() => setDetailsOpen(false)}>
        <div className="bg-gray-100 rounded-xl w-full max-w-6xl max-h-[92vh] overflow-auto" onClick={(e) => e.stopPropagation()} dir="rtl">
          <div className="sticky top-0 z-10 bg-white border-b px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2 font-bold text-gray-900">
              <FileText className="w-4 h-4 text-blue-700" />
              تفاصيل الصفقة
            </div>
            <button className="px-3 py-1 text-sm rounded border bg-white hover:bg-gray-50" onClick={() => setDetailsOpen(false)}>إغلاق</button>
          </div>

          <div className="p-4">
            {loadingDetail ? (
              <div className="text-sm text-gray-500">جار تحميل تفاصيل الصفقة...</div>
            ) : !selected ? (
              <div className="text-sm text-gray-500">تعذر تحميل التفاصيل.</div>
            ) : (
              (() => {
                const paidTotal = (selected.payments || []).reduce((sum, p) => sum + Number(p.amount || 0), 0);
                const total = Number(selected.total_amount || 0);
                const remaining = Math.max(0, total - paidTotal);
                return (
                  <div className="w-full bg-white border rounded-xl shadow-sm p-4 space-y-4">
                    <div className="flex justify-between items-center border-b-2 border-gray-800 pb-3">
                      <div className="flex gap-3 items-center">
                        <div className="bg-gray-900 text-white p-2 rounded-lg">
                          <FileText className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="text-lg font-black text-gray-900">تقرير صفقة شامل</h3>
                          <p className="text-[11px] font-bold text-gray-500">INTERNAL DEAL REPORT</p>
                        </div>
                      </div>
                      <div className="text-left text-xs space-y-1">
                        <div className="flex gap-2 justify-end"><span className="font-bold text-gray-900">{selected.ref_number || "-"}</span> <span className="text-gray-500">REF:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium text-gray-800">{formatDate(selected.order_date)}</span> <span className="text-gray-500">DATE:</span></div>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
                        <span className="text-[10px] text-gray-500 font-bold block mb-1">الحالة</span>
                        <span className="text-sm font-bold">{statusLabel(selected.status)}</span>
                      </div>
                      <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
                        <span className="text-[10px] text-gray-500 font-bold block mb-1">التاريخ</span>
                        <span className="text-sm font-bold">{formatDate(selected.order_date)}</span>
                      </div>
                      <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
                        <span className="text-[10px] text-gray-500 font-bold block mb-1">المورد</span>
                        <span className="text-sm font-bold truncate">{selected.partner_name || selected.partner?.name || "-"}</span>
                      </div>
                      <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
                        <span className="text-[10px] text-gray-500 font-bold block mb-1">الإجمالي</span>
                        <span className="text-sm font-black text-green-700">{formatMoney(selected.total_amount)}</span>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                      <div className="lg:col-span-2 border border-gray-300 rounded-lg overflow-hidden">
                        <div className="bg-gray-100 px-3 py-2 border-b border-gray-300 font-bold">بنود المنتجات</div>
                        <div className="overflow-auto">
                          <table className="min-w-[820px] w-full text-sm">
                            <thead className="bg-gray-800 text-white text-[11px]">
                              <tr>
                                <th className="text-right px-3 py-2 border-b">الصنف</th>
                                <th className="text-right px-3 py-2 border-b">الكمية</th>
                                <th className="text-right px-3 py-2 border-b">سعر الوحدة</th>
                                <th className="text-right px-3 py-2 border-b">الإجمالي</th>
                                <th className="text-right px-3 py-2 border-b">ملاحظات</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(selected.items || []).length === 0 ? (
                                <tr><td className="px-3 py-4 text-gray-500" colSpan={5}>لا توجد بنود.</td></tr>
                              ) : (
                                (selected.items || []).map((it) => (
                                  <tr key={it.id} className="hover:bg-gray-50">
                                    <td className="px-3 py-2 border-b">{it.product_name || "-"}</td>
                                    <td className="px-3 py-2 border-b">{String(it.quantity ?? "-")}</td>
                                    <td className="px-3 py-2 border-b">{formatMoney(it.unit_price)}</td>
                                    <td className="px-3 py-2 border-b font-bold">{formatMoney(it.total_price)}</td>
                                    <td className="px-3 py-2 border-b text-gray-600">{it.notes || "-"}</td>
                                  </tr>
                                ))
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <div className="border border-gray-300 rounded-lg overflow-hidden h-fit shadow-sm">
                        <div className="bg-gray-800 text-white px-3 py-2 text-center font-bold">الملخص المالي النهائي</div>
                        <div className="p-3 space-y-2 text-sm">
                          <div className="flex justify-between border-b border-gray-100 pb-1">
                            <span className="text-gray-500">إجمالي المدفوعات:</span>
                            <span className="font-mono font-bold text-emerald-700">{formatMoney(paidTotal)}</span>
                          </div>
                          <div className="flex justify-between border-b border-gray-100 pb-1">
                            <span className="text-gray-500">الإجمالي:</span>
                            <span className="font-mono font-bold">{formatMoney(total)}</span>
                          </div>
                          <div className="flex justify-between pt-1 text-red-600 font-bold">
                            <span>المبلغ المتبقي:</span>
                            <span className="font-mono">{formatMoney(remaining)}</span>
                          </div>
                          <div className="flex justify-between pt-1 text-blue-700 font-bold">
                            <span>حالة الدفع:</span>
                            <span>{paymentStatusLabel(selected.payment_status)}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="border border-gray-300 rounded-lg overflow-hidden">
                      <div className="bg-gray-100 px-3 py-2 border-b border-gray-300 font-bold flex justify-between items-center">
                        <span>الدفعات</span>
                        <span className="text-[11px] bg-white px-2 py-0.5 rounded border border-gray-200">{(selected.payments || []).length} دفعة</span>
                      </div>
                      <div className="overflow-auto">
                        <table className="min-w-[820px] w-full text-sm">
                          <thead className="bg-gray-50 text-gray-700">
                            <tr>
                              <th className="text-right px-3 py-2 border-b">العنوان</th>
                              <th className="text-right px-3 py-2 border-b">المبلغ</th>
                              <th className="text-right px-3 py-2 border-b">الحالة</th>
                              <th className="text-right px-3 py-2 border-b">الاستحقاق</th>
                              <th className="text-right px-3 py-2 border-b">تاريخ التحويل</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(selected.payments || []).length === 0 ? (
                              <tr><td className="px-3 py-4 text-gray-500" colSpan={5}>لا توجد دفعات.</td></tr>
                            ) : (
                              (selected.payments || []).map((p) => (
                                <tr key={p.id} className="hover:bg-gray-50">
                                  <td className="px-3 py-2 border-b">{p.title || "-"}</td>
                                  <td className="px-3 py-2 border-b font-bold">{formatMoney(p.amount)}</td>
                                  <td className="px-3 py-2 border-b">{paymentStatusLabel(p.status)}</td>
                                  <td className="px-3 py-2 border-b">{formatDate(p.due_date)}</td>
                                  <td className="px-3 py-2 border-b">{formatDate(p.transfer_date)}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                );
              })()
            )}
          </div>
        </div>
      </div>
    )}
    {createOpen && (
      <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-3" onClick={() => setCreateOpen(false)}>
        <div className="bg-white rounded-xl w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
          <div className="px-4 py-3 border-b flex items-center justify-between">
            <div className="font-bold">إضافة صفقة جديدة</div>
            <button className="px-3 py-1 text-sm rounded border" onClick={() => setCreateOpen(false)}>إغلاق</button>
          </div>
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">رقم الصفقة</label>
              <input
                value={createForm.ref_number}
                onChange={(e) => setCreateForm((s) => ({ ...s, ref_number: e.target.value }))}
                className="w-full px-3 py-2 border rounded-lg text-sm"
                placeholder="D-0104"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">التاريخ</label>
              <input
                type="date"
                value={createForm.order_date}
                onChange={(e) => setCreateForm((s) => ({ ...s, order_date: e.target.value }))}
                className="w-full px-3 py-2 border rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">المورد</label>
              <select
                value={createForm.partner}
                onChange={(e) => setCreateForm((s) => ({ ...s, partner: e.target.value }))}
                className="w-full px-3 py-2 border rounded-lg text-sm"
              >
                <option value="">اختر المورد</option>
                {partners.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name || `#${p.id}`}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">الحالة</label>
              <select
                value={createForm.status}
                onChange={(e) => setCreateForm((s) => ({ ...s, status: e.target.value }))}
                className="w-full px-3 py-2 border rounded-lg text-sm"
              >
                <option value="Open">Open</option>
                <option value="Shipped">Shipped</option>
                <option value="Closed">Closed</option>
                <option value="Cancelled">Cancelled</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-600 mb-1">الوصف</label>
              <textarea
                value={createForm.description}
                onChange={(e) => setCreateForm((s) => ({ ...s, description: e.target.value }))}
                className="w-full px-3 py-2 border rounded-lg text-sm min-h-[90px]"
                placeholder="وصف مختصر للصفقة"
              />
            </div>
          </div>
          <div className="px-4 py-3 border-t flex justify-end gap-2">
            <button className="px-4 py-2 text-sm rounded border" onClick={() => setCreateOpen(false)}>
              إلغاء
            </button>
            <button
              className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
              onClick={handleCreateDeal}
              disabled={savingCreate}
            >
              {savingCreate ? "جارٍ الحفظ..." : "حفظ الصفقة"}
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  );
}

