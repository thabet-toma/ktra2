import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { ExchangeRateDto, CurrencyDto } from "../../types/accounting";
import {
  ArrowLeftRight,
  Plus,
  Trash2,
  Loader2,
  AlertTriangle,
} from "lucide-react";

export const ExchangeRatesPage: React.FC = () => {
  const [rates, setRates] = useState<ExchangeRateDto[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [fromCur, setFromCur] = useState("");
  const [toCur, setToCur] = useState("");
  const [rate, setRate] = useState("");
  const [effDate, setEffDate] = useState(
    new Date().toISOString().split("T")[0]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [r, c] = await Promise.all([
        accountingApi.getExchangeRates(),
        accountingApi.getCurrencies(),
      ]);
      setRates(r as ExchangeRateDto[]);
      setCurrencies(c as CurrencyDto[]);
      if (!fromCur && c.length > 0) {
        const usd = (c as CurrencyDto[]).find((x) => x.Code === "USD");
        const ils = (c as CurrencyDto[]).find((x) => x.IsBaseCurrency);
        if (usd) setFromCur(String(usd.CurrencyID));
        if (ils) setToCur(String(ils.CurrencyID));
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addRate = async () => {
    if (!fromCur || !toCur || !rate || !effDate) return;
    if (fromCur === toCur) {
      setErr("لا يمكن اختيار نفس العملة");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.createExchangeRate({
        from_currency: Number(fromCur),
        to_currency: Number(toCur),
        rate: parseFloat(rate),
        effective_date: effDate,
      });
      setRate("");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const deleteRate = async (id: number) => {
    if (!confirm("حذف سعر الصرف؟")) return;
    setBusy(true);
    try {
      await accountingApi.deleteExchangeRate(id);
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
    <div className="p-6 max-w-5xl mx-auto" dir="rtl">
      <div className="flex items-center gap-3 mb-6">
        <ArrowLeftRight className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
          أسعار الصرف
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
          إضافة سعر صرف
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              من عملة
            </label>
            <select
              value={fromCur}
              onChange={(e) => setFromCur(e.target.value)}
              className="w-36 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100"
            >
              <option value="">—</option>
              {currencies.map((c) => (
                <option key={c.CurrencyID} value={c.CurrencyID}>
                  {c.Code} — {c.Name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              إلى عملة
            </label>
            <select
              value={toCur}
              onChange={(e) => setToCur(e.target.value)}
              className="w-36 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100"
            >
              <option value="">—</option>
              {currencies.map((c) => (
                <option key={c.CurrencyID} value={c.CurrencyID}>
                  {c.Code} — {c.Name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              سعر الصرف
            </label>
            <input
              type="number"
              step="0.000001"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              placeholder="3.650000"
              className="w-36 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              تاريخ السريان
            </label>
            <input
              type="date"
              value={effDate}
              onChange={(e) => setEffDate(e.target.value)}
              className="w-40 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100"
            />
          </div>
          <button
            onClick={addRate}
            disabled={busy || !fromCur || !toCur || !rate}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg disabled:opacity-50 transition-colors"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            إضافة
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
        </div>
      ) : rates.length === 0 ? (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          لا توجد أسعار صرف مسجلة
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-600">
                <th className="text-right px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  من
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  إلى
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  سعر الصرف
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  تاريخ السريان
                </th>
                <th className="text-center px-4 py-3 font-semibold text-slate-600 dark:text-slate-300">
                  حذف
                </th>
              </tr>
            </thead>
            <tbody>
              {rates.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-100">
                    {r.from_currency_code}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600 dark:text-slate-300">
                    {r.to_currency_code}
                  </td>
                  <td className="px-4 py-3 text-center font-mono text-slate-800 dark:text-slate-100">
                    {Number(r.rate).toFixed(6)}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600 dark:text-slate-300">
                    {fmtDate(r.effective_date)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => deleteRate(r.id)}
                      disabled={busy}
                      className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors disabled:opacity-50"
                    >
                      <Trash2 className="w-4 h-4" />
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
