/**
 * FEAT-3/4 — LedgerTable: مكوّن واحد قابل لإعادة الاستخدام لقوائم الحركات ذات
 * «الرصيد الجاري». يستهلكه دفتر حركات الصنف (qty in/out) وكشف حساب الشريك
 * (Debit/Credit) عبر تمرير الأعمدة كبارامتر — لا تفريع للمكوّن.
 *
 * مراجع المستندات قابلة للنقر عبر مُحلِّل المراجع المشترك
 * (`utils/entityLinks.invoicePathForReference`).
 */
import React from "react";
import { useNavigate } from "react-router-dom";
import { invoicePathForReference } from "../../utils/entityLinks";

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
}

/** خلية مرجع مستند قابلة للنقر — مصدر حقيقة واحد لكل البطاقات. */
export const DocRefCell: React.FC<{
  referenceType?: string | null;
  referenceId?: number | null;
  label?: React.ReactNode;
}> = ({ referenceType, referenceId, label }) => {
  const navigate = useNavigate();
  const path = invoicePathForReference(referenceType, referenceId);
  const text = label ?? (referenceId != null ? `#${referenceId}` : "—");
  if (!path) return <span>{text}</span>;
  return (
    <button
      type="button"
      onClick={() => navigate(path)}
      className="text-[var(--aseel-accent,#2563eb)] underline hover:opacity-80"
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
}: LedgerTableProps<Row>) {
  const canPaginate = onPage != null && limit != null && count != null;
  const hasPrev = canPaginate && offset > 0;
  const hasNext = canPaginate && offset + (limit ?? 0) < (count ?? 0);

  return (
    <div className="aseel-dense-table overflow-x-auto" dir="rtl">
      <table className="w-full text-sm">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                style={{ textAlign: c.align ?? "right" }}
                className="px-2 py-1 border-b border-[var(--aseel-border)] bg-[var(--aseel-head,#f2f0e4)] font-bold"
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length} className="p-4 text-center text-[var(--aseel-ink-soft)]">
                جاري التحميل…
              </td>
            </tr>
          ) : error ? (
            <tr>
              <td colSpan={columns.length} className="p-4 text-center text-[var(--aseel-danger)]">
                {error}
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="p-4 text-center text-[var(--aseel-ink-soft)]">
                {emptyText}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} className="border-b border-[var(--aseel-border)] hover:bg-black/5">
                {columns.map((c) => (
                  <td key={c.key} style={{ textAlign: c.align ?? "right" }} className="px-2 py-1">
                    {c.render
                      ? c.render(row)
                      : String((row as Record<string, unknown>)[c.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
        {summaryRow && (
          <tfoot>
            {summaryRow}
          </tfoot>
        )}
      </table>

      {canPaginate && (count ?? 0) > (limit ?? 0) && (
        <div className="flex items-center justify-between p-2 text-sm">
          <span className="text-[var(--aseel-ink-soft)]">
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
