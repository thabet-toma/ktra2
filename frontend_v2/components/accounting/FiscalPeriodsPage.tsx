import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { FiscalPeriodDto } from "../../types/accounting";
import {
  CalendarDays,
  Plus,
  Lock,
  Unlock,
  Loader2,
  AlertTriangle,
} from "lucide-react";

export const FiscalPeriodsPage: React.FC = () => {
  const [periods, setPeriods] = useState<FiscalPeriodDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newYear, setNewYear] = useState(new Date().getFullYear().toString());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await accountingApi.getFiscalPeriods();
      setPeriods(data as FiscalPeriodDto[]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createYear = async () => {
    const y = parseInt(newYear, 10);
    if (!y || y < 2000 || y > 2100) return;
    setBusy(true);
    try {
      await accountingApi.createFiscalYear(y);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const togglePeriod = async (p: FiscalPeriodDto) => {
    setBusy(true);
    try {
      if (p.is_closed) {
        await accountingApi.reopenFiscalPeriod(p.id);
      } else {
        await accountingApi.closeFiscalPeriod(p.id);
      }
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const fmtDate = (d: string) => {
    const [y, m, day] = d.split("-");
    return `${day}/${m}/${y}`;
  };

  return (
    <div className="p-6 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-3 mb-6">
        <CalendarDays className="w-7 h-7 text-[var(--color-primary)] dark:text-[var(--color-primary)]" />
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
          الفترات المالية
        </h1>
      </div>

      {err && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg border border-red-200 dark:border-red-800 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {err}
        </div>
      )}

      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 p-5 mb-6">
        <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-300 mb-3">
          إنشاء سنة مالية جديدة
        </h2>
        <div className="flex items-center gap-3">
          <input
            type="number"
            min={2000}
            max={2100}
            value={newYear}
            onChange={(e) => setNewYear(e.target.value)}
            className="w-32 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 text-center"
          />
          <button
            onClick={createYear}
            disabled={busy}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg disabled:opacity-50 transition-colors"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            إنشاء FY {newYear}
          </button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
          يناير 1 — ديسمبر 31 (سنة ميلادية كاملة)
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary)]" />
        </div>
      ) : periods.length === 0 ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          لا توجد فترات مالية مسجلة
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-600">
                <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  الاسم
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  من
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  إلى
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  الحالة
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  إجراء
                </th>
              </tr>
            </thead>
            <tbody>
              {periods.map((p) => (
                <tr
                  key={p.id}
                  className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">
                    {p.name}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600 dark:text-slate-300">
                    {fmtDate(p.start_date)}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600 dark:text-slate-300">
                    {fmtDate(p.end_date)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {p.is_closed ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
                        <Lock className="w-3 h-3" /> مغلقة
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                        <Unlock className="w-3 h-3" /> مفتوحة
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => togglePeriod(p)}
                      disabled={busy}
                      className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors disabled:opacity-50 ${
                        p.is_closed
                          ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                          : "bg-amber-500 hover:bg-amber-600 text-white"
                      }`}
                    >
                      {p.is_closed ? "إعادة فتح" : "إغلاق"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
