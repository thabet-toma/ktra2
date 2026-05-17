import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { VatReportResponse } from "../../types/accounting";
import { Receipt, Search, TrendingUp, TrendingDown, AlertCircle } from "lucide-react";

export const AccountingVatReportPage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(() => {
    const d = new Date(today.getFullYear(), today.getMonth(), 1);
    return d.toISOString().split("T")[0];
  });
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [data, setData] = useState<VatReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<"input" | "output">("output");

  const fetch = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await accountingApi.getVatReport({
        start_date: start,
        end_date: end,
      });
      setData(resp as VatReportResponse);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const fmt = (n: number | undefined | null) =>
    (Number(n) || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const inputBalance = data?.input.balance || 0;
  const outputPayable = data?.output.balance_payable || 0;
  const net = data?.net_payable || 0;

  const lines = tab === "input" ? data?.input_lines || [] : data?.output_lines || [];

  return (
    <div className="space-y-4" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 p-4 bg-gradient-to-l from-rose-900 to-slate-900 text-white rounded-xl">
        <Receipt className="w-8 h-8 text-rose-300" />
        <div>
          <h1 className="text-lg font-bold">تقرير ضريبة القيمة المضافة (VAT)</h1>
          <p className="text-xs text-rose-200">
            مقارنة مدخلات مقابل مخرجات — صافي المستحق للدولة
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 items-end bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
        <div>
          <label className="block text-xs text-gray-500 mb-1">من</label>
          <input
            type="date"
            className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">إلى</label>
          <input
            type="date"
            className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        <button
          type="button"
          onClick={fetch}
          className="flex items-center gap-2 px-4 py-2 bg-rose-600 text-white rounded-lg text-sm"
        >
          <Search className="w-4 h-4" />
          تحديث
        </button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 text-sm flex gap-2 items-center">
          <AlertCircle className="w-4 h-4" />
          {err}
        </div>
      )}

      {/* ملخّص */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-xl border border-blue-200 dark:border-blue-900/40 bg-blue-50/60 dark:bg-blue-900/10 p-4">
          <div className="flex items-center gap-2 text-blue-700 dark:text-blue-300 text-xs font-semibold mb-1">
            <TrendingDown className="w-4 h-4" />
            ضريبة مدخلات (قابلة للخصم)
          </div>
          <div className="text-2xl font-bold text-blue-900 dark:text-blue-200">
            {fmt(inputBalance)}
          </div>
          <div className="text-[11px] text-blue-700/70 mt-1">
            {data?.input.accounts.map((a) => `${a.code} ${a.name}`).join(" · ") ||
              "—"}
          </div>
        </div>

        <div className="rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50/60 dark:bg-rose-900/10 p-4">
          <div className="flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs font-semibold mb-1">
            <TrendingUp className="w-4 h-4" />
            ضريبة مخرجات (مستحقة)
          </div>
          <div className="text-2xl font-bold text-rose-900 dark:text-rose-200">
            {fmt(outputPayable)}
          </div>
          <div className="text-[11px] text-rose-700/70 mt-1">
            {data?.output.accounts.map((a) => `${a.code} ${a.name}`).join(" · ") ||
              "—"}
          </div>
        </div>

        <div
          className={`rounded-xl border p-4 ${
            net >= 0
              ? "border-amber-200 dark:border-amber-900/40 bg-amber-50/60 dark:bg-amber-900/10"
              : "border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/60 dark:bg-emerald-900/10"
          }`}
        >
          <div
            className={`text-xs font-semibold mb-1 ${
              net >= 0 ? "text-amber-700" : "text-emerald-700"
            }`}
          >
            {net >= 0 ? "صافي المستحق للحكومة" : "رصيد دائن (قابل للاسترداد)"}
          </div>
          <div
            className={`text-2xl font-bold ${
              net >= 0
                ? "text-amber-900 dark:text-amber-200"
                : "text-emerald-900 dark:text-emerald-200"
            }`}
          >
            {fmt(Math.abs(net))}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">
            = مخرجات − مدخلات
          </div>
        </div>
      </div>

      {/* علامات تبويب */}
      <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
        <button
          type="button"
          className={`px-4 py-2 text-sm font-medium ${
            tab === "output"
              ? "border-b-2 border-rose-600 text-rose-700 dark:text-rose-300"
              : "text-gray-500"
          }`}
          onClick={() => setTab("output")}
        >
          حركات ضريبة المخرجات ({data?.output_lines.length || 0})
        </button>
        <button
          type="button"
          className={`px-4 py-2 text-sm font-medium ${
            tab === "input"
              ? "border-b-2 border-blue-600 text-blue-700 dark:text-blue-300"
              : "text-gray-500"
          }`}
          onClick={() => setTab("input")}
        >
          حركات ضريبة المدخلات ({data?.input_lines.length || 0})
        </button>
      </div>

      {loading ? (
        <div className="py-16 text-center text-gray-500">جاري التحميل…</div>
      ) : (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th className="text-right p-3">التاريخ</th>
                <th className="text-right p-3">قيد #</th>
                <th className="text-right p-3">مرجع</th>
                <th className="text-right p-3">الحساب</th>
                <th className="text-right p-3">الوصف</th>
                <th className="text-right p-3">الشريك</th>
                <th className="text-right p-3">مدين</th>
                <th className="text-right p-3">دائن</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((ln, idx) => (
                <tr
                  key={`${ln.journal_id}-${idx}`}
                  className="border-t border-gray-100 dark:border-gray-700"
                >
                  <td className="p-2">{ln.date || "—"}</td>
                  <td className="p-2 font-mono">#{ln.journal_id}</td>
                  <td className="p-2 text-xs text-gray-500">
                    {ln.reference_type}
                    {ln.reference_id ? `#${ln.reference_id}` : ""}
                  </td>
                  <td className="p-2 font-mono">{ln.account_code}</td>
                  <td className="p-2">{ln.description}</td>
                  <td className="p-2">{ln.partner || "—"}</td>
                  <td className="p-2 text-right">{fmt(ln.debit)}</td>
                  <td className="p-2 text-right">{fmt(ln.credit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {lines.length === 0 && !loading && (
            <p className="p-8 text-center text-gray-500">لا توجد حركات في الفترة</p>
          )}
        </div>
      )}
    </div>
  );
};
