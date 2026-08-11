import React, { useState, useEffect, useCallback, useMemo } from "react";
import { formatMoney } from "../../utils/formatNumber";
import {
  ArrowLeft,
  ArrowDownLeft,
  ArrowUpRight,
  Ban,
  BookMarked,
  Wallet,
} from "lucide-react";
import { CashBox, CashBoxTransaction } from "../../types";
import { cashBoxTransactionsService } from "../../services/firestoreService";
import { accountingApi } from "../../services/accountingApi";
import { DepositModal } from "./modals/DepositModal";
import {
  formatDateLocalized,
  formatDateValue,
  formatTimeValue,
  formatWeekdayName,
} from "../../utils/formatDate";

interface CashBoxStatementProps {
  cashBox: CashBox;
  onBack: () => void;
}

type GlRow = {
  id: number;
  date: string;
  journal_id: number;
  description: string;
  ref_type?: string | null;
  ref_id?: string | null;
  debit: number;
  credit: number;
  balance: number;
};

const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  const dayName = formatWeekdayName(date);
  const datePart = formatDateValue(date);
  const timePart = formatTimeValue(date);
  return { dayName, datePart, timePart };
};

export const CashBoxStatement: React.FC<CashBoxStatementProps> = ({
  cashBox,
  onBack,
}) => {
  const [transactions, setTransactions] = useState<CashBoxTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDepositModalOpen, setIsDepositModalOpen] = useState(false);

  const [glAccountId, setGlAccountId] = useState<number | null>(null);
  const [glLoading, setGlLoading] = useState(false);
  const [glError, setGlError] = useState<string | null>(null);
  const [glRows, setGlRows] = useState<GlRow[]>([]);
  const [glMeta, setGlMeta] = useState<{
    account_name?: string;
    account_code?: string;
    opening_balance?: number;
    closing_balance?: number;
  }>({});

  const resolveLedgerAccount = useCallback(async () => {
    try {
      const rows = await accountingApi.getCashBoxLedgers();
      const link = rows.find((r) => String(r.external_id) === String(cashBox.id));
      setGlAccountId(link?.account_id ?? null);
    } catch {
      setGlAccountId(null);
    }
  }, [cashBox.id]);

  const loadGl = useCallback(async () => {
    if (!glAccountId) {
      setGlRows([]);
      setGlError(null);
      return;
    }
    setGlLoading(true);
    setGlError(null);
    try {
      const end = new Date();
      end.setFullYear(end.getFullYear() + 1);
      const start = new Date();
      start.setFullYear(start.getFullYear() - 5);
      const data = await accountingApi.getGeneralLedger({
        account_id: String(glAccountId),
        start_date: start.toISOString().slice(0, 10),
        end_date: end.toISOString().slice(0, 10),
        include_unposted: "true",
      });
      setGlMeta({
        account_name: data.account_name,
        account_code: data.account_code,
        opening_balance: Number(data.opening_balance ?? 0),
        closing_balance: Number(data.closing_balance ?? 0),
      });
      setGlRows(Array.isArray(data.transactions) ? data.transactions : []);
    } catch (e) {
      setGlError(e instanceof Error ? e.message : "تعذر تحميل دفتر الأستاذ");
      setGlRows([]);
    } finally {
      setGlLoading(false);
    }
  }, [glAccountId]);

  useEffect(() => {
    const unsubscribe =
      cashBoxTransactionsService.subscribeToTransactions(
        cashBox.id,
        (data) => {
          setTransactions(data);
          setLoading(false);
        }
      );
    return () => unsubscribe();
  }, [cashBox.id]);

  useEffect(() => {
    setGlRows([]);
    setGlError(null);
    setGlMeta({});
    setGlAccountId(null);
    void resolveLedgerAccount();
  }, [cashBox.id, resolveLedgerAccount]);

  useEffect(() => {
    if (glAccountId) void loadGl();
  }, [glAccountId, loadGl]);

  type MergedRow =
    | { kind: "cash"; sort: number; tx: CashBoxTransaction }
    | { kind: "gl"; sort: number; row: GlRow };

  const mergedRows = useMemo(() => {
    const out: MergedRow[] = [];
    const cashAsc = [...transactions].reverse();
    for (const tx of cashAsc) {
      const t = new Date(tx.date).getTime();
      out.push({ kind: "cash", sort: Number.isNaN(t) ? 0 : t, tx });
    }
    for (const row of glRows) {
      const t = new Date(`${row.date}T12:00:00`).getTime() + (row.journal_id % 1000) * 0.001;
      out.push({ kind: "gl", sort: t, row });
    }
    out.sort((a, b) => a.sort - b.sort);
    return out;
  }, [transactions, glRows]);

  const getTransactionIcon = (type: string) => {
    switch (type) {
      case "deposit":
        return <ArrowDownLeft className="w-5 h-5 text-green-600" />;
      case "withdrawal":
        return <ArrowUpRight className="w-5 h-5 text-red-600" />;
      default:
        return <Ban className="w-5 h-5 text-[var(--color-text-muted)]" />;
    }
  };

  const getTransactionLabel = (type: string) => {
    switch (type) {
      case "deposit":
        return "إيداع";
      case "withdrawal":
        return "سحب";
      case "adjustment":
        return "تسوية";
      default:
        return type;
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center">
          <button
            onClick={onBack}
            className="p-2 ml-2 hover:bg-[var(--color-surface-3)] rounded-full transition"
          >
            <ArrowLeft className="w-6 h-6 dark:text-white" />
          </button>
          <div>
            <h1 className="text-2xl font-bold dark:text-white">{cashBox.name}</h1>
            <p className="text-sm text-[var(--color-text-muted)]">كشف الصندوق + دفتر الأستاذ العام</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-left">
            <p className="text-xs text-[var(--color-text-muted)]">الرصيد الحالي (الصندوق)</p>
            <p className="text-2xl font-bold text-blue-600">
              {cashBox.currentBalance.toLocaleString()}
              <span className="text-sm mr-1">{cashBox.currency}</span>
            </p>
          </div>
          <button
            onClick={() => setIsDepositModalOpen(true)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition flex items-center"
          >
            <ArrowDownLeft className="w-4 h-4 ml-2" />
            إيداع
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <h2 className="text-lg font-bold text-[var(--color-text)] flex items-center gap-2">
          <Wallet className="w-5 h-5 text-blue-600" />
          حركات الصندوق والقيود
        </h2>
        <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
          دمج سجل الصندوق (Firestore) مع أسطر دفتر الأستاذ لحساب النقدية المربوط بالصندوق — ترتيب زمني واحد.
          إيداع جديد يُنشئ حركة صندوق وقيداً (مدين الصندوق، دائن رأس المال) عند توفر الربط المحاسبي والفترة
          المفتوحة.
        </p>
      </div>

      <div className="bg-[var(--color-surface)] rounded-xl shadow border border-[var(--color-border)] overflow-hidden">
        {!glAccountId ? (
          <div className="px-4 py-2 border-b border-amber-100 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-950/20 text-xs text-amber-900 dark:text-amber-100">
            لا يوجد حساب GL مربوط — تظهر حركات الصندوق فقط. اربط الصندوق من قائمة الصناديق لعرض القيود
            وإنشاء قيد الإيداع تلقائياً.
          </div>
        ) : (
          <div className="px-4 py-3 flex flex-wrap gap-4 text-sm border-b border-[var(--color-border)] bg-slate-50/80 dark:bg-slate-900/40">
            <div className="flex items-center gap-1">
              <BookMarked className="w-4 h-4 text-[var(--color-primary)] shrink-0" />
              <span className="text-[var(--color-text-muted)]">الحساب: </span>
              <span className="font-mono font-bold">{glMeta.account_code || "—"}</span>{" "}
              <span className="font-semibold">{glMeta.account_name || ""}</span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">رصيد افتتاحي (GL): </span>
              <span className="font-bold tabular-nums">
                {formatMoney(glMeta.opening_balance ?? 0)}
              </span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">رصيد ختامي (GL): </span>
              <span className="font-bold tabular-nums text-[var(--color-primary)] dark:text-[var(--color-primary)]">
                {formatMoney(glMeta.closing_balance ?? 0)}
              </span>
            </div>
          </div>
        )}
        {glAccountId && glLoading ? (
          <div className="p-10 text-center text-[var(--color-text-muted)]">جاري تحميل دفتر الأستاذ...</div>
        ) : glAccountId && glError ? (
          <div className="p-8 text-center text-red-600 text-sm">{glError}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="bg-[var(--color-surface-3)] text-[var(--color-text-muted)] text-xs uppercase">
                <tr>
                  <th className="px-3 py-2">التاريخ</th>
                  <th className="px-3 py-2">المصدر</th>
                  <th className="px-3 py-2">البيان</th>
                  <th className="px-3 py-2">مرجع</th>
                  <th className="px-3 py-2">مدين</th>
                  <th className="px-3 py-2">دائن</th>
                  <th className="px-3 py-2">رصيد</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-10 text-center text-[var(--color-text-muted)]">
                      جاري التحميل...
                    </td>
                  </tr>
                ) : mergedRows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-10 text-center text-[var(--color-text-muted)]">
                      لا توجد حركات في الجدول الموحّد
                    </td>
                  </tr>
                ) : (
                  mergedRows.map((item) => {
                    if (item.kind === "cash") {
                      const tx = item.tx;
                      const { dayName, datePart, timePart } = formatDate(tx.date);
                      const isDep = tx.type === "deposit";
                      const isWith = tx.type === "withdrawal";
                      const adjPos = tx.type === "adjustment" && tx.amount >= 0;
                      const adjNeg = tx.type === "adjustment" && tx.amount < 0;
                      return (
                        <tr
                          key={`c-${tx.id}`}
                          className="hover:bg-blue-50/50 dark:hover:bg-gray-700/40 bg-blue-50/20 dark:bg-blue-950/10"
                        >
                          <td className="px-3 py-2 text-[var(--color-text)]">
                            <div className="flex flex-col leading-tight text-xs">
                              <span className="font-semibold">{dayName}</span>
                              <span>{datePart}</span>
                              <span className="text-[var(--color-text-muted)]">{timePart}</span>
                            </div>
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-1">
                              {getTransactionIcon(tx.type)}
                              <span className="text-xs font-semibold">
                                صندوق — {getTransactionLabel(tx.type)}
                              </span>
                            </div>
                          </td>
                          <td className="px-3 py-2 max-w-[260px] truncate" title={tx.description}>
                            {tx.description}
                          </td>
                          <td
                            className="px-3 py-2 text-xs text-[var(--color-text-muted)] font-mono truncate max-w-[120px]"
                            title={tx.reference}
                          >
                            {tx.reference || "—"}
                          </td>
                          <td className="px-3 py-2 tabular-nums text-green-700 dark:text-green-400 font-semibold">
                            {isDep || adjPos
                              ? Math.abs(tx.amount).toLocaleString(undefined, { maximumFractionDigits: 2 })
                              : "—"}
                          </td>
                          <td className="px-3 py-2 tabular-nums text-red-700 dark:text-red-400 font-semibold">
                            {isWith || adjNeg
                              ? Math.abs(tx.amount).toLocaleString(undefined, { maximumFractionDigits: 2 })
                              : "—"}
                          </td>
                          <td className="px-3 py-2 font-bold tabular-nums text-xs text-[var(--color-text)]">
                            {tx.balanceAfter != null ? tx.balanceAfter.toLocaleString() : "—"}
                            <span className="block font-normal text-[10px] text-[var(--color-text-muted)]">رصيد صندوق</span>
                          </td>
                        </tr>
                      );
                    }
                    const row = item.row;
                    return (
                      <tr key={`g-${row.id}`} className="hover:bg-[var(--color-primary-hover)]/40 dark:hover:bg-gray-700/40">
                        <td className="px-3 py-2 whitespace-nowrap font-mono text-xs">{formatDateLocalized(row.date)}</td>
                        <td className="px-3 py-2 text-xs font-semibold text-[var(--color-primary)] dark:text-[var(--color-primary)]">
                          قيد #{row.journal_id}
                        </td>
                        <td className="px-3 py-2 max-w-[280px] truncate" title={row.description}>
                          {row.description}
                        </td>
                        <td className="px-3 py-2 text-xs text-[var(--color-text-muted)] truncate max-w-[120px]">
                          {[row.ref_type, row.ref_id].filter(Boolean).join(" ") || "—"}
                        </td>
                        <td className="px-3 py-2 tabular-nums text-green-700 dark:text-green-400">
                          {Number(row.debit) > 0
                            ? Number(row.debit).toLocaleString(undefined, { maximumFractionDigits: 2 })
                            : "—"}
                        </td>
                        <td className="px-3 py-2 tabular-nums text-red-700 dark:text-red-400">
                          {Number(row.credit) > 0
                            ? Number(row.credit).toLocaleString(undefined, { maximumFractionDigits: 2 })
                            : "—"}
                        </td>
                        <td className="px-3 py-2 font-bold tabular-nums dark:text-white text-xs">
                          {formatMoney(row.balance)}
                          <span className="block font-normal text-[10px] text-[var(--color-text-muted)]">رصيد GL</span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <DepositModal
        isOpen={isDepositModalOpen}
        onClose={() => setIsDepositModalOpen(false)}
        cashBox={cashBox}
        onDepositComplete={() => void loadGl()}
      />
    </div>
  );
};
