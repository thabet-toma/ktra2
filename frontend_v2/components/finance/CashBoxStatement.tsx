import React, { useState, useEffect, useCallback, useMemo } from "react";
import { formatMoney } from "../../utils/formatNumber";
import {
  ArrowLeft,
  ArrowDownLeft,
  ArrowUpRight,
  BookMarked,
  Wallet,
} from "lucide-react";
import { CashBox } from "../../types";
import {
  accountingApi,
  type CashBoxLedgerLink,
  type CashBoxStatement as CashBoxStatementDto,
} from "../../services/accountingApi";
import { DepositModal } from "./modals/DepositModal";
import { formatDateLocalized } from "../../utils/formatDate";

interface CashBoxStatementProps {
  cashBox: CashBox;
  onBack: () => void;
}

/** T-CASHBOX M4 — كشف الصندوق من مصدرٍ واحد: دفتر الأستاذ.
 *
 * كانت الشاشة تجلب مصدرين — سجلّ الصندوق في المرآة وأسطر الأستاذ — وتدمجهما في
 * المتصفح بترتيبٍ مُلفَّق: الأستاذ مثبَّت على `T12:00:00` ثم يُزاد
 * `journal_id ‰ 1000 × 0.001` لفضّ التعادل. فحركةُ صندوقٍ في الثانية بعد الظهر
 * تسبق قيداً من اليوم نفسه أو تليه بحسب رقمه لا بحسب وقته، وعمود «الرصيد» كان
 * عمودين مختلفين في عمود واحد («رصيد صندوق» و«رصيد GL») لا رصيداً جارياً.
 *
 * الآن: `GET cash-box-accounts/{id}/statement/` يعيد الافتتاحي والصفوف برصيدها
 * الجاري والختامي — محسوبةً في الخادم بترتيب `(تاريخ، قيد، سطر)` مستقر.
 */
export const CashBoxStatement: React.FC<CashBoxStatementProps> = ({
  cashBox,
  onBack,
}) => {
  const [link, setLink] = useState<CashBoxLedgerLink | null | undefined>(undefined);
  const [statement, setStatement] = useState<CashBoxStatementDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDepositModalOpen, setIsDepositModalOpen] = useState(false);
  const [depositDirection, setDepositDirection] = useState<"in" | "out">("in");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLink(undefined);
    accountingApi.getCashBoxLedgers()
      .then((rows) => {
        if (cancelled) return;
        setLink(rows.find((r) => String(r.external_id) === String(cashBox.id)) ?? null);
      })
      .catch(() => { if (!cancelled) setLink(null); });
    return () => { cancelled = true; };
  }, [cashBox.id]);

  const load = useCallback(async () => {
    if (!link) {
      setStatement(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // بلا مدى: الكشف كامل من أول حركة — لا نافذة مقفولة تُخفي القديم بصمت.
      setStatement(await accountingApi.getCashBoxStatement(link.id, {
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل كشف الصندوق");
      setStatement(null);
    } finally {
      setLoading(false);
    }
  }, [link, startDate, endDate]);

  useEffect(() => { void load(); }, [load]);

  const currency = link?.currency_code || cashBox.currency || "";
  const money = useCallback(
    (v: string | number) => `${formatMoney(Number(v) || 0)}${currency ? ` ${currency}` : ""}`,
    [currency],
  );

  const rows = useMemo(() => statement?.rows ?? [], [statement]);

  const openAdjust = (direction: "in" | "out") => {
    setDepositDirection(direction);
    setIsDepositModalOpen(true);
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
            <p className="text-sm text-[var(--color-text-muted)]">
              كشف الصندوق — من دفتر الأستاذ
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-left">
            {/* الرصيد من الدفاتر لا من الحقل المخزّن في المرآة — ذاك يبقى صفراً
                فتختلف القائمة عن الكشف لنفس الصندوق. */}
            <p className="text-xs text-[var(--color-text-muted)]">الرصيد الحالي</p>
            <p className="text-2xl font-bold text-blue-600 tabular-nums">
              {statement ? money(statement.closing_balance) : "—"}
            </p>
          </div>
          <button
            onClick={() => openAdjust("in")}
            disabled={!link}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition flex items-center disabled:opacity-50"
          >
            <ArrowDownLeft className="w-4 h-4 ml-2" />
            إيداع
          </button>
          <button
            onClick={() => openAdjust("out")}
            disabled={!link}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition flex items-center disabled:opacity-50"
          >
            <ArrowUpRight className="w-4 h-4 ml-2" />
            سحب
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <h2 className="text-lg font-bold text-[var(--color-text)] flex items-center gap-2">
          <Wallet className="w-5 h-5 text-blue-600" />
          حركات الصندوق
        </h2>
        <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
          كل حركة على حساب الصندوق في دفتر الأستاذ، برصيدٍ جارٍ حقيقي. الإيداع
          والسحب يُنشئان قيداً واحداً فوراً (مدين/دائن الصندوق مقابل رأس المال).
        </p>
      </div>

      <div className="bg-[var(--color-surface)] rounded-xl shadow border border-[var(--color-border)] overflow-hidden">
        {link === null ? (
          <div className="px-4 py-3 border-b border-amber-100 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-950/20 text-xs text-amber-900 dark:text-amber-100">
            هذا الصندوق بلا حساب في شجرة الحسابات — صندوقٌ قديم من قبل توحيد
            الإنشاء. شغّل أمر <span className="font-mono">backfill_cash_boxes</span>{" "}
            لربطه، فالصناديق الجديدة يُنشأ حسابها معها.
          </div>
        ) : (
          <div className="px-4 py-3 flex flex-wrap items-end gap-4 text-sm border-b border-[var(--color-border)] bg-slate-50/80 dark:bg-slate-900/40">
            <div className="flex items-center gap-1">
              <BookMarked className="w-4 h-4 text-[var(--color-primary)] shrink-0" />
              <span className="text-[var(--color-text-muted)]">الحساب: </span>
              <span className="font-mono font-bold">{link?.account_code || "—"}</span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">رصيد افتتاحي: </span>
              <span className="font-bold tabular-nums">
                {statement ? money(statement.opening_balance) : "—"}
              </span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">رصيد ختامي: </span>
              <span className="font-bold tabular-nums text-[var(--color-primary)]">
                {statement ? money(statement.closing_balance) : "—"}
              </span>
            </div>
            <div className="flex items-end gap-2 ms-auto">
              <label className="flex flex-col text-xs text-[var(--color-text-muted)]">
                من
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="mt-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
                />
              </label>
              <label className="flex flex-col text-xs text-[var(--color-text-muted)]">
                إلى
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="mt-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
                />
              </label>
              {(startDate || endDate) && (
                <button
                  type="button"
                  onClick={() => { setStartDate(""); setEndDate(""); }}
                  className="rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
                >
                  الكل
                </button>
              )}
            </div>
          </div>
        )}

        {error ? (
          <div className="p-8 text-center text-red-600 text-sm">{error}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="bg-[var(--color-surface-3)] text-[var(--color-text-muted)] text-xs uppercase">
                <tr>
                  <th className="px-3 py-2">التاريخ</th>
                  <th className="px-3 py-2">القيد</th>
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
                ) : rows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-10 text-center text-[var(--color-text-muted)]">
                      لا توجد حركات على هذا الصندوق
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => (
                    <tr
                      key={row.journal_line_id}
                      className="hover:bg-[var(--color-primary-hover)]/40 dark:hover:bg-gray-700/40"
                    >
                      <td className="px-3 py-2 whitespace-nowrap font-mono text-xs">
                        {formatDateLocalized(row.date)}
                      </td>
                      <td className="px-3 py-2 text-xs font-semibold text-[var(--color-primary)]">
                        قيد #{row.journal_id}
                      </td>
                      <td className="px-3 py-2 max-w-[280px] truncate" title={row.description}>
                        {row.description}
                      </td>
                      <td className="px-3 py-2 text-xs text-[var(--color-text-muted)] truncate max-w-[140px]">
                        {[row.reference_type, row.reference_id].filter(Boolean).join(" ") || "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-green-700 dark:text-green-400">
                        {Number(row.debit) > 0 ? formatMoney(Number(row.debit)) : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-red-700 dark:text-red-400">
                        {Number(row.credit) > 0 ? formatMoney(Number(row.credit)) : "—"}
                      </td>
                      <td className="px-3 py-2 font-bold tabular-nums dark:text-white text-xs">
                        {formatMoney(Number(row.balance))}
                      </td>
                    </tr>
                  ))
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
        cashBoxLedgerId={link?.id ?? null}
        direction={depositDirection}
        onDepositComplete={() => void load()}
      />
    </div>
  );
};
