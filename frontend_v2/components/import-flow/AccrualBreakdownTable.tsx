/**
 * جدول بنود لقطة استحقاق — مصدر العرض الوحيد لـ«سجل الاستحقاق» (شاشة الاستيراد)
 * ولنافذة «تفاصيل الحركة» في كشف الحساب:
 *  - تعديل بفرق ⇒ البند / قبل / بعد / الفرق (النقص أخضر، الزيادة أحمر، «جديد» و«محذوف» بوسم)
 *    وصفّ إجماليّ يساوي فرق القيد.
 *  - الأصل (أو لقطة بلا فرق) ⇒ البند / النوع / المبلغ وإجماليها.
 */
import React from "react";
import { formatMoney } from "@/utils/formatNumber";
import {
  accrualTypeLabel, diffRowBadge, diffRowClass, diffTotals, signedMoney, toCents,
  type AccrualSnapshot,
} from "@/utils/accrualBreakdown";

const th = "border-b border-[var(--color-border)] bg-[var(--color-surface-3)] px-2 py-1 text-right font-bold";
const td = "border-b border-[var(--color-border)] px-2 py-1 text-right";

export const AccrualBreakdownTable: React.FC<{ snapshot: AccrualSnapshot }> = ({ snapshot }) => {
  if (snapshot.diff && snapshot.diff.length > 0) {
    const totals = diffTotals(snapshot.diff);
    return (
      <table className="w-full border-collapse text-xs" data-testid="accrual-diff-table">
        <thead>
          <tr>
            <th className={th}>البند</th>
            <th className={th}>قبل</th>
            <th className={th}>بعد</th>
            <th className={th}>الفرق</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.diff.map((r, i) => {
            const badge = diffRowBadge(r.status);
            return (
              <tr key={`${r.label}-${i}`} className={r.status === "removed" ? "text-[var(--color-text-muted)]" : ""}>
                <td className={td}>
                  <span className={r.status === "removed" ? "line-through" : ""}>{r.label || accrualTypeLabel(r.type)}</span>
                  {badge && (
                    <span
                      className={`ms-1 rounded px-1 text-[10px] font-bold ${
                        r.status === "new" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                      }`}
                    >
                      {badge}
                    </span>
                  )}
                </td>
                <td className={`${td} ktra-num`}>{formatMoney(r.before)}</td>
                <td className={`${td} ktra-num`}>{formatMoney(r.after)}</td>
                <td className={`${td} ktra-num font-semibold ${diffRowClass(r.difference)}`}>
                  <span dir="ltr" className="inline-block">{signedMoney(r.difference)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="font-bold">
            <td className={td}>الإجمالي</td>
            <td className={`${td} ktra-num`}>{formatMoney(totals.before / 100)}</td>
            <td className={`${td} ktra-num`}>{formatMoney(totals.after / 100)}</td>
            <td className={`${td} ktra-num ${diffRowClass(String(totals.difference / 100))}`}>
              <span dir="ltr" className="inline-block">{signedMoney(totals.difference / 100)}</span>
            </td>
          </tr>
        </tfoot>
      </table>
    );
  }

  const sumCents = snapshot.lines.reduce((acc, l) => acc + toCents(l.amount), 0);
  return (
    <table className="w-full border-collapse text-xs" data-testid="accrual-lines-table">
      <thead>
        <tr>
          <th className={th}>البند</th>
          <th className={th}>النوع</th>
          <th className={th}>المبلغ</th>
        </tr>
      </thead>
      <tbody>
        {snapshot.lines.map((l, i) => (
          <tr key={`${l.label}-${i}`}>
            <td className={td}>{l.label || accrualTypeLabel(l.type)}</td>
            <td className={td}>{accrualTypeLabel(l.type)}</td>
            <td className={`${td} ktra-num`}>{formatMoney(l.amount)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr className="font-bold">
          <td className={td} colSpan={2}>الإجمالي</td>
          <td className={`${td} ktra-num`}>{formatMoney(sumCents / 100)}</td>
        </tr>
      </tfoot>
    </table>
  );
};

export default AccrualBreakdownTable;
