/**
 * FEAT-3/4 — LedgerTable: مكوّن واحد قابل لإعادة الاستخدام لقوائم الحركات ذات
 * «الرصيد الجاري». يستهلكه دفتر حركات المنتج (qty in/out) وكشف حساب الشريك
 * (Debit/Credit) عبر تمرير الأعمدة كبارامتر — لا تفريع للمكوّن.
 *
 * مراجع المستندات قابلة للنقر عبر مُحلِّل المراجع المشترك
 * (`utils/entityLinks.invoicePathForReference`).
 */
import React from "react";
import { useNavigate } from "react-router-dom";
import { entityPathForReference } from "../../utils/entityLinks";

export interface LedgerColumn<Row = Record<string, unknown>> {
  key: string;
  header: string;
  align?: "left" | "center" | "right";
  render?: (row: Row) => React.ReactNode;
}

export interface LedgerTableProps<Row = Record<string, unknown>> {
  columns: LedgerColumn<Row>[];
  rows: Row[];
  loading?: boolean;
  error?: string | null;
  count?: number;
  limit?: number;
  offset?: number;
  onPage?: (newOffset: number) => void;
  emptyText?: string;
  summaryRow?: React.ReactNode;
  /** تمييز لوني للصف حسب نوع الحركة (كشف الحساب: فاتورة أحمر، سند أخضر). */
  rowClassName?: (row: Row) => string;
  /**
   * مفتاح الربط: الصفوف ذات المفتاح نفسه تُعرَض متجاورة داخل إطار واحد
   * (فاتورة + سندها). مرساة كل مجموعة موضع أول ظهور لها فيبقى ترتيب الصفحة
   * محفوظاً، والصف بلا مفتاح يبقى مفرداً بلا إطار.
   */
  rowGroupKey?: (row: Row) => string | null | undefined;
}

/** خلية مرجع مستند قابلة للنقر — مصدر حقيقة واحد لكل البطاقات. */
export const DocRefCell: React.FC<{
  referenceType?: string | null;
  referenceId?: number | null;
  label?: React.ReactNode;
}> = ({ referenceType, referenceId, label }) => {
  const navigate = useNavigate();
  const path = entityPathForReference(referenceType, referenceId);
  const text = label ?? (referenceId != null ? `#${referenceId}` : "—");
  if (!path) return <span>{text}</span>;
  return (
    <button
      type="button"
      onClick={() => navigate(path)}
      className="text-[var(--ktra-accent,#2563eb)] underline hover:opacity-80"
    >
      {text}
    </button>
  );
};

export function LedgerTable<Row = Record<string, unknown>>({
  columns,
  rows,
  loading,
  error,
  count,
  limit,
  offset = 0,
  onPage,
  emptyText = "لا توجد حركات.",
  summaryRow,
  rowClassName,
  rowGroupKey,
}: LedgerTableProps<Row>) {
  const canPaginate = onPage != null && limit != null && count != null;
  const hasPrev = canPaginate && offset > 0;
  const hasNext = canPaginate && offset + (limit ?? 0) < (count ?? 0);

  // الصفوف مجمَّعة بالمفتاح مع الحفاظ على ترتيب أول ظهور لكل مجموعة.
  const groups = React.useMemo(() => {
    const order: string[] = [];
    const map = new Map<string, Row[]>();
    rows.forEach((row, i) => {
      const key = (rowGroupKey ? rowGroupKey(row) : null) || `__solo_${i}`;
      if (!map.has(key)) {
        map.set(key, []);
        order.push(key);
      }
      map.get(key)!.push(row);
    });
    return order.map((key) => ({ key, rows: map.get(key)! }));
  }, [rows, rowGroupKey]);

  const renderRow = (row: Row, key: React.Key) => (
    <tr
      key={key}
      className={`border-b border-[var(--ktra-border)] hover:bg-black/5 ${
        rowClassName ? rowClassName(row) : ""
      }`}
    >
      {columns.map((c) => (
        <td key={c.key} style={{ textAlign: c.align ?? "right" }} className="px-2 py-1">
          {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "")}
        </td>
      ))}
    </tr>
  );

  return (
    <div className="ktra-dense-table overflow-x-auto" dir="rtl">
      <table className="w-full text-sm">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                style={{ textAlign: c.align ?? "right" }}
                className="px-2 py-1 border-b border-[var(--ktra-border)] bg-[var(--ktra-head,#f2f0e4)] font-bold"
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        {loading || error || rows.length === 0 ? (
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="p-4 text-center text-[var(--ktra-ink-soft)]">
                  جاري التحميل…
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={columns.length} className="p-4 text-center text-[var(--ktra-danger)]">
                  {error}
                </td>
              </tr>
            ) : (
              <tr>
                <td colSpan={columns.length} className="p-4 text-center text-[var(--ktra-ink-soft)]">
                  {emptyText}
                </td>
              </tr>
            )}
          </tbody>
        ) : (
          // كل مجموعة في <tbody> مستقل: المجموعة المترابطة تأخذ إطاراً يفصلها بصرياً.
          groups.map((group) => (
            <tbody
              key={group.key}
              className={
                group.rows.length > 1
                  ? "border-2 border-[var(--ktra-accent,#2563eb)]"
                  : undefined
              }
            >
              {group.rows.map((row, i) => renderRow(row, `${group.key}-${i}`))}
            </tbody>
          ))
        )}
        {summaryRow && (
          <tfoot>
            {summaryRow}
          </tfoot>
        )}
      </table>

      {canPaginate && (count ?? 0) > (limit ?? 0) && (
        <div className="flex items-center justify-between p-2 text-sm">
          <span className="text-[var(--ktra-ink-soft)]">
            {offset + 1}–{Math.min(offset + (limit ?? 0), count ?? 0)} من {count}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!hasPrev}
              onClick={() => onPage?.(Math.max(offset - (limit ?? 0), 0))}
              className="px-3 py-1 border rounded disabled:opacity-40"
            >
              السابق
            </button>
            <button
              type="button"
              disabled={!hasNext}
              onClick={() => onPage?.(offset + (limit ?? 0))}
              className="px-3 py-1 border rounded disabled:opacity-40"
            >
              التالي
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default LedgerTable;
