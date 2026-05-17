import React, { useEffect, useState, useCallback, useRef } from "react";
import { accountingApi } from "../../services/accountingApi";
import {
  Plus,
  Search,
  CheckCircle,
  FileText,
  Loader2,
  Undo2,
  Filter,
  RefreshCw,
} from "lucide-react";

export interface JournalListItem {
  id: number;
  transaction_date: string | null;
  description?: string | null;
  reference_type?: string | null;
  reference_id?: number | null;
  reference_summary?: string | null;
  deal_ref_number?: string | null;
  is_posted: boolean;
  currency_code?: string | null;
  exchange_rate?: string | number;
  tenant_name?: string | null;
  source_label?: string | null;
}

function refTypeLabel(rt: string | null | undefined): string {
  const t = (rt || "").trim();
  const map: Record<string, string> = {
    LOGISTICS_PAYMENT: "دفعة لوجستية",
    PURCHASE_RECEIPT: "استلام مخزون",
    JOURNAL_REVERSAL: "عكس قيد",
    LOGISTICS_EXPENSE: "مصروف لوجستي",
    LOGISTICS_SHIPMENT: "شحنة دولية",
    LOGISTICS_CLEARANCE_PAYMENT: "دفعة تخليص",
    SALES_INVOICE: "فاتورة مبيعات",
    SALES_DELIVERY_COGS: "تكلفة بضاعة مباعة",
    CUSTOMER_PAYMENT: "تحصيل عميل",
    PURCHASE_INVOICE: "فاتورة شراء",
    MANUAL: "قيد يدوي",
  };
  return map[t] || (t ? t : "عام / يدوي");
}

function formatTxDate(raw: string | null | undefined): string {
  if (!raw) return "—";
  const s = String(raw).slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, d] = s.split("-");
    return `${d}/${m}/${y}`;
  }
  try {
    return new Date(raw).toLocaleDateString("ar-EG", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return raw;
  }
}

interface Props {
  onNew: () => void;
  onOpen: (id: number, dealRefNumber?: string | null, referenceSummary?: string | null) => void;
  onNavigateToDeal?: (dealRefNumber: string) => void;
}

export const AccountingJournalListPage: React.FC<Props> = ({
  onNew,
  onOpen,
  onNavigateToDeal,
}) => {
  const [rows, setRows] = useState<JournalListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [refType, setRefType] = useState("");
  const [posting, setPosting] = useState<number | null>(null);
  const [reversing, setReversing] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [postErr, setPostErr] = useState<string | null>(null);
  const searchRef = useRef(search);
  searchRef.current = search;

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {};
      if (dateFrom.trim()) params.date_from = dateFrom.trim();
      if (dateTo.trim()) params.date_to = dateTo.trim();
      if (refType.trim()) params.reference_type = refType.trim();
      const sq = searchRef.current.trim();
      if (sq) params.search = sq;

      const data = (await accountingApi.getJournals(
        Object.keys(params).length ? params : undefined
      )) as JournalListItem[];
      setRows(data);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, refType]);

  useEffect(() => {
    void load();
  }, [load]);

  const handlePost = async (id: number) => {
    if (!confirm("ترحيل القيد؟ لا يمكن التعديل بعد الترحيل.")) return;
    setPostErr(null);
    setPosting(id);
    try {
      await accountingApi.postJournal(id);
      setRows((r) =>
        r.map((j) => (j.id === id ? { ...j, is_posted: true } : j))
      );
    } catch (e: unknown) {
      setPostErr(e instanceof Error ? e.message : "فشل الترحيل");
    } finally {
      setPosting(null);
    }
  };

  const handleReverse = async (id: number) => {
    if (
      !confirm(
        "إنشاء قيد عكسي (مدين↔دائن) لهذا القيد المرحّل؟ سيُنشأ قيد جديد مرحّل."
      )
    )
      return;
    setPostErr(null);
    setReversing(id);
    try {
      await accountingApi.reverseJournal(id);
      await load();
    } catch (e: unknown) {
      setPostErr(e instanceof Error ? e.message : "فشل العكس");
    } finally {
      setReversing(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-gradient-to-l from-slate-800 to-slate-900 text-white rounded-xl shadow">
        <div className="flex items-center gap-3">
          <FileText className="w-8 h-8 text-slate-300" />
          <div>
            <h1 className="text-lg font-bold">دفتر اليومية</h1>
            <p className="text-xs text-slate-400">
              قيود مرحّلة ومسودات — بحث برقم الصفقة أو البيان أو نوع المرجع
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onNew}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          قيد جديد
        </button>
      </div>

      <div className="flex flex-col gap-3 bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="flex flex-wrap items-end gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              placeholder="بحث: رقم القيد، مرجع، نص البيان، أو رقم صفقة (D-…)"
              className="w-full border rounded-lg pr-10 pl-3 py-2 text-sm dark:bg-gray-900 dark:border-gray-600"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
            />
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <Filter className="w-4 h-4 text-gray-500 hidden sm:block" />
            <div>
              <label className="block text-[10px] text-gray-500 mb-0.5">
                من تاريخ
              </label>
              <input
                type="date"
                className="border rounded-lg px-2 py-1.5 text-sm dark:bg-gray-900 dark:border-gray-600"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-[10px] text-gray-500 mb-0.5">
                إلى تاريخ
              </label>
              <input
                type="date"
                className="border rounded-lg px-2 py-1.5 text-sm dark:bg-gray-900 dark:border-gray-600"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-[10px] text-gray-500 mb-0.5">
                نوع المرجع
              </label>
              <select
                className="border rounded-lg px-2 py-1.5 text-sm min-w-[160px] dark:bg-gray-900 dark:border-gray-600"
                value={refType}
                onChange={(e) => setRefType(e.target.value)}
              >
                <option value="">الكل</option>
                <option value="LOGISTICS_PAYMENT">دفعات صفقات</option>
                <option value="PURCHASE_RECEIPT">استلام مخزون</option>
                <option value="LOGISTICS_EXPENSE">مصاريف لوجستية</option>
                <option value="JOURNAL_REVERSAL">قيود عكسية</option>
              </select>
            </div>
            <button
              type="button"
              onClick={() => load()}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-slate-700 text-white text-sm hover:bg-slate-600"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              تطبيق
            </button>
          </div>
        </div>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}
      {postErr && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200 text-sm border border-red-200 dark:border-red-800">
          {postErr}
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-gray-500">جاري التحميل…</div>
      ) : (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50 text-gray-600 dark:text-gray-400">
              <tr>
                <th className="text-right p-3 font-semibold whitespace-nowrap">
                  رقم القيد
                </th>
                <th className="text-right p-3 font-semibold whitespace-nowrap">
                  التاريخ
                </th>
                <th className="text-right p-3 font-semibold whitespace-nowrap">
                  نوع المرجع
                </th>
                <th className="text-right p-3 font-semibold min-w-[200px]">
                  مرتبط بـ (صفقة / مصدر)
                </th>
                <th className="text-right p-3 font-semibold min-w-[220px]">
                  البيان الكامل
                </th>
                <th className="text-right p-3 font-semibold whitespace-nowrap">
                  مرجع #
                </th>
                <th className="text-right p-3 font-semibold whitespace-nowrap">
                  الحالة
                </th>
                <th className="text-right p-3 font-semibold w-44">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((j) => (
                <tr
                  key={j.id}
                  className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50/80 dark:hover:bg-gray-900/30 align-top"
                >
                  <td className="p-3 font-mono whitespace-nowrap">{j.id}</td>
                  <td className="p-3 whitespace-nowrap dir-ltr text-right">
                    <span>{formatTxDate(j.transaction_date)}</span>
                    {j.currency_code && j.currency_code !== "ILS" && (
                      <span className="mr-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
                        {j.currency_code}
                      </span>
                    )}
                  </td>
                  <td className="p-3 text-xs">
                    <div className="flex flex-col gap-0.5">
                      <span className="font-medium text-slate-700 dark:text-slate-200">
                        {j.source_label || refTypeLabel(j.reference_type)}
                      </span>
                      {j.tenant_name && (
                        <span className="text-[10px] text-slate-500 dark:text-slate-400">
                          {j.tenant_name}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="p-3 text-xs max-w-xs">
                    {j.deal_ref_number && onNavigateToDeal ? (
                      <button
                        type="button"
                        onClick={() => onNavigateToDeal(j.deal_ref_number!)}
                        className="text-right whitespace-pre-wrap break-words text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 hover:underline transition-colors font-medium"
                        title={`فتح الصفقة ${j.deal_ref_number}`}
                      >
                        {j.reference_summary?.trim() || j.deal_ref_number}
                      </button>
                    ) : (
                      <span className="text-blue-900 dark:text-blue-200 whitespace-pre-wrap break-words">
                        {j.reference_summary?.trim() || "—"}
                      </span>
                    )}
                  </td>
                  <td className="p-3 text-xs text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-words max-w-md">
                    {j.description?.trim() || "—"}
                  </td>
                  <td className="p-3 font-mono text-xs whitespace-nowrap">
                    {j.reference_id ?? "—"}
                  </td>
                  <td className="p-3 whitespace-nowrap">
                    {j.is_posted ? (
                      <span className="text-emerald-600 dark:text-emerald-400 text-xs font-medium">
                        مرحّل
                      </span>
                    ) : (
                      <span className="text-slate-600 dark:text-slate-300 text-xs font-medium">
                        مسودة
                      </span>
                    )}
                  </td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => onOpen(j.id, j.deal_ref_number, j.reference_summary)}
                        className="px-2 py-1 text-xs rounded-lg bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200"
                      >
                        فتح
                      </button>
                      {!j.is_posted && (
                        <button
                          type="button"
                          disabled={posting === j.id}
                          onClick={() => handlePost(j.id)}
                          className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200 disabled:opacity-50"
                        >
                          {posting === j.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <CheckCircle className="w-3 h-3" />
                          )}
                          ترحيل
                        </button>
                      )}
                      {j.is_posted && (
                        <button
                          type="button"
                          disabled={reversing === j.id}
                          onClick={() => handleReverse(j.id)}
                          className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg bg-violet-100 dark:bg-violet-900/40 text-violet-800 dark:text-violet-200 disabled:opacity-50"
                        >
                          {reversing === j.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <Undo2 className="w-3 h-3" />
                          )}
                          عكس
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && (
            <p className="p-8 text-center text-gray-500">
              لا قيود تطابق الفلاتر الحالية
            </p>
          )}
        </div>
      )}
    </div>
  );
};
