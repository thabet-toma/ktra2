/**
 * N1-T3 — AseelReportTable<T>
 * للـreports: شريط فلاتر + أعمدة رقمية + footer مجاميع + export CSV.
 * Reference: docs/aseel_reference/reports.txt 1–30.
 */
import React from 'react';
import { AseelSpinner, AseelEmptyState } from './AseelStates';

export type ReportColumn<T> = {
  key: string;
  header: string;
  width?: string;
  align?: 'left' | 'center' | 'right';
  render?: (row: T) => React.ReactNode;
  numeric?: boolean;
};

export type AseelReportTableProps<T> = {
  filterBar?: React.ReactNode;
  columns: ReportColumn<T>[];
  rows: T[];
  totals?: Record<string, string | number>;
  exportable?: boolean;
  onExport?: () => void;
  className?: string;
  /** Stable row key. Falls back to row index if omitted. */
  getRowKey?: (row: T, idx: number) => string | number;
  /** Message when rows is empty. Defaults to "لا توجد بيانات في النطاق المحدد". */
  emptyHint?: React.ReactNode;
  /** Show loading state instead of empty hint while fetching. */
  loading?: boolean;
};

export function AseelReportTable<T>({
  filterBar,
  columns,
  rows,
  totals,
  exportable,
  onExport,
  className = '',
  getRowKey,
  emptyHint = 'لا توجد بيانات في النطاق المحدد',
  loading = false,
}: AseelReportTableProps<T>) {
  const getAlign = (col: ReportColumn<T>) => {
    if (col.align) return col.align;
    if (col.numeric) return 'right';
    return 'left';
  };

  const handleExport = () => {
    if (onExport) {
      onExport();
      return;
    }
    // Default CSV export
    const headers = columns.map((c) => c.header);
    const csvRows = [
      headers.join(','),
      ...rows.map((row) =>
        columns
          .map((col) => {
            const val = col.render ? String(col.render(row)) : String((row as any)[col.key] ?? '');
            return `"${val.replace(/"/g, '""')}"`;
          })
          .join(',')
      ),
    ];
    if (totals) {
      const totalRow = columns.map((col) =>
        totals[col.key] !== undefined ? String(totals[col.key]) : ''
      );
      csvRows.push(totalRow.map((v) => `"${v}"`).join(','));
    }
    const bom = '\uFEFF';
    const blob = new Blob([bom + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'report.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={`aseel-report-table ${className}`}>
      <table className="aseel-grid" data-variant="report">
        <thead style={{ position: 'sticky', top: 0, zIndex: 10, background: 'var(--aseel-surface)', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          {(filterBar || exportable) && (
            <tr>
              <td colSpan={columns.length} style={{ padding: 0, border: 'none', borderBottom: '1px solid var(--aseel-border-soft)' }}>
                <div className="aseel-report-toolbar" style={{ border: 'none', borderRadius: 0, margin: 0 }}>
                  {filterBar}
                  {exportable && (
                    <button className="aseel-btn" onClick={handleExport} title="تصدير CSV">
                      تصدير
                    </button>
                  )}
                </div>
              </td>
            </tr>
          )}
          <tr style={{ background: 'var(--aseel-table-head)' }}>
            {columns.map((col) => (
              <th key={col.key} style={{ width: col.width, textAlign: getAlign(col) as any, top: 0 }}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && rows.length === 0 && (
            <tr className="aseel-row--empty">
              <td colSpan={columns.length}><AseelSpinner /></td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr className="aseel-row--empty">
              <td colSpan={columns.length}><AseelEmptyState hint={typeof emptyHint === 'string' ? emptyHint : undefined} /></td>
            </tr>
          )}
          {rows.map((row, idx) => (
            <tr key={getRowKey ? getRowKey(row, idx) : idx}>
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{ textAlign: getAlign(col) as any }}
                  className={col.numeric ? 'aseel-num' : ''}
                >
                  {col.render ? col.render(row) : String((row as any)[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
          {totals && rows.length > 0 && (
            <tr className="aseel-row--total">
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{ textAlign: getAlign(col) as any }}
                  className={col.numeric ? 'aseel-num' : ''}
                >
                  {totals[col.key] !== undefined ? String(totals[col.key]) : ''}
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
