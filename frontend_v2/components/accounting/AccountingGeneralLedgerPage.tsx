import React, { useState, useEffect, useCallback, useRef } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { AccountingAccount, GeneralLedgerResponse } from "../../types/accounting";
import { BookOpen, Search } from "lucide-react";

export interface AccountingGeneralLedgerPageProps {
  initialAccountId?: number | null;
  onInitialAccountConsumed?: () => void;
}

export const AccountingGeneralLedgerPage: React.FC<AccountingGeneralLedgerPageProps> = ({
  initialAccountId,
  onInitialAccountConsumed,
}) => {
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [accountId, setAccountId] = useState("");
  const today = new Date();
  const [start, setStart] = useState(`${today.getFullYear()}-01-01`);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [unposted, setUnposted] = useState(false);
  const [data, setData] = useState<GeneralLedgerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const appliedInitial = useRef<number | null>(null);

  useEffect(() => {
    accountingApi
      .getAccounts()
      .then((a) =>
        setAccounts((a as AccountingAccount[]).filter((x) => x.is_active))
      )
      .catch(() => setAccounts([]));
  }, []);

  useEffect(() => {
    if (initialAccountId == null) {
      appliedInitial.current = null;
      return;
    }
    if (appliedInitial.current === initialAccountId) return;
    appliedInitial.current = initialAccountId;
    setAccountId(String(initialAccountId));
    onInitialAccountConsumed?.();
    // تشغيل التقرير تلقائياً عند الانتقال من شجرة الحسابات
    void (async () => {
      setLoading(true);
      setErr(null);
      try {
        const params: Record<string, string> = {
          account_id: String(initialAccountId),
          start_date: `${new Date().getFullYear()}-01-01`,
          end_date: new Date().toISOString().split("T")[0],
        };
        const res = await accountingApi.getGeneralLedger(params);
        setData(res as GeneralLedgerResponse);
      } catch (e: unknown) {
        setErr(e instanceof Error ? e.message : "فشل التقرير");
        setData(null);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialAccountId]);

  const run = useCallback(async () => {
    if (!accountId) {
      setErr("اختر حساباً");
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {
        account_id: accountId,
        start_date: start,
        end_date: end,
      };
      if (unposted) params.include_unposted = "true";
      const res = await accountingApi.getGeneralLedger(params);
      setData(res as GeneralLedgerResponse);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [accountId, start, end, unposted]);

  const fmt = (n: number) =>
    Number(n).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 p-4 bg-gradient-to-l from-[var(--color-primary)] to-slate-900 text-white rounded-xl">
        <BookOpen className="w-8 h-8 text-[var(--color-primary)]" />
        <div>
          <h1 className="text-lg font-bold">الأستاذ العام</h1>
          <p className="text-xs text-[var(--color-primary)]">حركة حساب مع الرصيد الجاري</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 items-end bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs text-gray-500 mb-1">الحساب</label>
          <select
            className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
          >
            <option value="">— اختر —</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.code} — {a.name}
              </option>
            ))}
          </select>
        </div>
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
        <label className="flex items-center gap-2 text-sm pb-2">
          <input
            type="checkbox"
            checked={unposted}
            onChange={(e) => setUnposted(e.target.checked)}
          />
          غير المرحّل
        </label>
        <button
          type="button"
          onClick={run}
          className="flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm"
        >
          <Search className="w-4 h-4" />
          عرض
        </button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 text-sm">
          {err}
        </div>
      )}

      {loading ? (
        <div className="py-16 text-center text-gray-500">جاري التحميل…</div>
      ) : data ? (
        <div className="space-y-3">
          <div className="p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
            <p className="font-bold">
              {data.account_code} — {data.account_name}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              رصيد افتتاحي: {fmt(Number(data.opening_balance))} — رصيد
              ختامي: {fmt(Number(data.closing_balance))}
            </p>
          </div>
          <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900/50">
                <tr>
                  <th className="text-right p-2">التاريخ</th>
                  <th className="text-right p-2">اليومية</th>
                  <th className="text-right p-2">البيان</th>
                  <th className="text-right p-2">مدين</th>
                  <th className="text-right p-2">دائن</th>
                  <th className="text-right p-2">الرصيد</th>
                </tr>
              </thead>
              <tbody>
                {data.transactions.map((t) => (
                  <tr
                    key={t.id}
                    className="border-t border-gray-100 dark:border-gray-700"
                  >
                    <td className="p-2 whitespace-nowrap">{t.date}</td>
                    <td className="p-2 font-mono">{t.journal_id}</td>
                    <td className="p-2 max-w-xs truncate">{t.description}</td>
                    <td className="p-2">{fmt(Number(t.debit))}</td>
                    <td className="p-2">{fmt(Number(t.credit))}</td>
                    <td className="p-2 font-medium">
                      {fmt(Number(t.balance))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.transactions.length === 0 && (
              <p className="p-6 text-center text-gray-500">لا حركات</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
};
