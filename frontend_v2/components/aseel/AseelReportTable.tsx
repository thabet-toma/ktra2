/**
 * N1-T3 — AseelReportTable<T>
 * للـreports: شريط فلاتر + أعمدة رقمية + footer مجاميع + export CSV.
 * Reference: docs/aseel_reference/reports.txt 1–30.
 */
import React from 'react';

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
};

export function AseelReportTable<T>({
  filterBar,
  columns,
  rows,
  totals,
  exportable,
  onExport,
  className = '',
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
      {(filterBar || exportable) && (
        <div className="aseel-report-toolbar">
          {filterBar}
          {exportable && (
            <button className="aseel-btn" onClick={handleExport} title="تصدير CSV">
              تصدير
            </button>
          )}
        </div>
      )}
      <table className="aseel-grid" data-variant="report">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} style={{ width: col.width, textAlign: getAlign(col) as any }}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
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
          {totals && (
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
