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
  /** Raw value for CSV export (plain digits, dot decimal). Falls back to row[key] for numeric columns, else the rendered text. */
  exportValue?: (row: T) => string | number;
};

export type AseelReportTableProps<T> = {
  filterBar?: React.ReactNode;
  columns: ReportColumn<T>[];
  rows: T[];
  totals?: Record<string, string | number>;
  exportable?: boolean;
  onExport?: () => void;
  /** Filename (without .csv) for the default CSV export. Defaults to "report". */
  exportFilename?: string;
  className?: string;
  /** Stable row key. Falls back to row index if omitted. */
  getRowKey?: (row: T, idx: number) => string | number;
  /** Message when rows is empty. Defaults to "لا توجد بيانات في النطاق المحدد". */
  emptyHint?: React.ReactNode;
  /** Show loading state instead of empty hint while fetching. */
  loading?: boolean;
  /** التنقيب: نقر الصف يفتح تفصيله (ميزان المراجعة ← الأستاذ العام). */
  onRowClick?: (row: T) => void;
  /** تلميح الصف القابل للنقر — يشرح إلى أين يقود قبل النقر. */
  rowTitle?: string;
};

export function AseelReportTable<T>({
  filterBar,
  columns,
  rows,
  totals,
  exportable,
  onExport,
  exportFilename = 'report',
  className = '',
  getRowKey,
  emptyHint = 'لا توجد بيانات في النطاق المحدد',
  loading = false,
  onRowClick,
  rowTitle,
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
    // التصدير يخرج أرقاماً يعيد المحاسب حسابها، لا نصوصاً معروضة.
    // `render` قد يعيد عنصر React (عمود الكود صار رابطاً للتنقيب) — و`String()`
    // عليه تعطي "[object Object]"، فلا يُقبل إلا ناتج بدائي.
    const cellText = (col: ReportColumn<T>, row: T): string => {
      if (col.exportValue) return String(col.exportValue(row));
      if (col.numeric) return String(row?.[col.key] ?? '');
      if (col.render) {
        const out = col.render(row);
        if (typeof out === 'string' || typeof out === 'number') return String(out);
      }
      return String(row?.[col.key] ?? '');
    };

    // مجاميع الصف الأخير تصل منسّقةً للعرض (فواصل آلاف). الرقم المنسَّق لا
    // يُعاد حسابه في Excel، فتُنزع الفواصل حين تكون القيمة رقماً منسَّقاً بالكامل.
    const rawTotal = (value: unknown): string => {
      const text = String(value ?? '');
      return /^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(text) ? text.replace(/,/g, '') : text;
    };

    const headers = columns.map((c) => c.header);
    const csvRows = [
      headers.join(','),
      ...rows.map((row) =>
        columns
          .map((col) => `"${cellText(col, row).replace(/"/g, '""')}"`)
          .join(',')
      ),
    ];
    if (totals) {
      const totalRow = columns.map((col) =>
        totals[col.key] !== undefined ? rawTotal(totals[col.key]) : ''
      );
      csvRows.push(totalRow.map((v) => `"${v}"`).join(','));
    }
    const bom = '\uFEFF';
    const blob = new Blob([bom + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${exportFilename}.csv`;
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
            <tr
              key={getRowKey ? getRowKey(row, idx) : idx}
              title={onRowClick ? rowTitle : undefined}
              style={onRowClick ? { cursor: 'pointer' } : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onRowClick(row);
                      }
                    }
                  : undefined
              }
            >
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
