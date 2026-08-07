/**
 * N1-T2 — AseelDenseTable<T>
 * List page table — يَستبدل DataGrid في صفحات الإدارة.
 * Props:
 *   - columns: { key, header, width?, align?, render?, sortable?, numeric? }[]
 *   - rows: T[]
 *   - getRowKey: (r) => string|number
 *   - onRowClick?, onRowDoubleClick?
 *   - selectable? + selectedKey? + onSelect?
 *   - onSort? + sortKey? + sortDir?
 *   - footer?: ReactNode (totals row)
 *   - pagination?: { page, pageSize, total, onChange }
 * Reference: docs/aseel_reference/accounting.txt 48–69.
 */
import React, { useState, useRef } from 'react';
import { AseelSpinner, AseelEmptyState } from './AseelStates';
import {
  columnWidthsKey, nextColumnWidth, readSizes, writeSizes,
  type SizeMap,
} from '../../utils/columnWidths';

export type DenseColumn<T> = {
  key: string;
  header: string;
  width?: string;
  align?: 'left' | 'center' | 'right';
  render?: (row: T, rowIndex: number) => React.ReactNode;
  sortable?: boolean;
  numeric?: boolean;
};

export type DensePagination = {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
};

export type AseelDenseTableProps<T> = {
  columns: DenseColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  onRowDoubleClick?: (row: T) => void;
  selectable?: boolean;
  selectedKey?: string | number | null;
  onSelect?: (key: string | number | null) => void;
  onSort?: (key: string, dir: 'asc' | 'desc') => void;
  sortKey?: string;
  sortDir?: 'asc' | 'desc';
  footer?: React.ReactNode;
  pagination?: DensePagination;
  className?: string;
  /** Message shown when rows is empty. Defaults to "لا توجد سجلات". */
  emptyHint?: React.ReactNode;
  /** Show "جاري التحميل…" instead of empty hint while data is loading. */
  loading?: boolean;
  /** Key on each row that holds a HEX color string for row-level text-color override. */
  rowColorKey?: string;
  /** Show export CSV button in top-right. */
  exportable?: boolean;
  /** Filename for CSV export (without .csv). */
  exportFilename?: string;
  /** T-G1: drag-to-resize column widths (Excel-like). Default true. */
  resizable?: boolean;
};

export function AseelDenseTable<T extends Record<string, any>>({
  columns,
  rows,
  getRowKey,
  onRowClick,
  onRowDoubleClick,
  selectable,
  selectedKey,
  onSelect,
  onSort,
  sortKey,
  sortDir,
  footer,
  pagination,
  className = '',
  emptyHint = 'لا توجد سجلات',
  loading = false,
  rowColorKey,
  exportable = false,
  exportFilename = 'export',
  resizable = true,
}: AseelDenseTableProps<T>) {
  const totalCols = columns.length + (selectable ? 1 : 0);
  const [hoveredKey, setHoveredKey] = useState<string | number | null>(null);

  // 1. حساب مفتاح فريد للجدول dựa على المسار والأعمدة للحفظ التلقائي
  const storageKey = React.useMemo(() => {
    if (typeof window === "undefined") return "";
    return columnWidthsKey(window.location.pathname, columns.map(c => c.key));
  }, [columns]);

  // 2. التهيئة من localStorage (T-G1 + Persistence)
  const [colWidths, setColWidths] = useState<SizeMap>(() => readSizes(storageKey));

  const startResize = (e: React.MouseEvent, colKey: string) => {
    e.preventDefault();
    e.stopPropagation();
    const th = (e.currentTarget as HTMLElement).closest('th') as HTMLElement | null;
    if (!th) return;
    const startX = e.clientX;
    const startW = th.getBoundingClientRect().width;
    // RTL: السحب لليسار يزيد العرض — نعكس الإشارة حسب اتجاه الجدول.
    const rtl = getComputedStyle(th).direction === 'rtl';
    const onMove = (ev: MouseEvent) => {
      setColWidths((prev) => ({
        ...prev, [colKey]: nextColumnWidth(startW, ev.clientX - startX, rtl),
      }));
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      // 3. الحفظ عند التغيير (نهاية السحب)
      setColWidths(prev => {
        writeSizes(storageKey, prev);
        return prev;
      });
    };
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  const handleSort = (col: DenseColumn<T>) => {
    if (!col.sortable || !onSort) return;
    const newDir = sortKey === col.key && sortDir === 'asc' ? 'desc' : 'asc';
    onSort(col.key, newDir);
  };

  // التطبيق كله RTL (`<html dir="rtl">`) فبداية السطر هي اليمين. الافتراضي
  // السابق `left` كان نمطاً سطرياً يغلب كل قاعدة CSS، فيدفع النص العربي لحافة
  // الخلية الخطأ في كل صفحة قائمة. الأرقام تبقى يميناً (عرف الأصيل + `.aseel-num`).
  const getAlign = (col: DenseColumn<T>) => col.align ?? 'right';

  const handleExport = () => {
    const headers = columns.map((c) => c.header);
    const csvRows = [
      headers.join(','),
      ...rows.map((row) =>
        columns
          .map((col) => {
            const val = col.render ? String(col.render(row, 0)) : String(row[col.key] ?? '');
            return `"${val.replace(/"/g, '""')}"`;
          })
          .join(',')
      ),
    ];
    if (footer && typeof footer === 'string') {
      csvRows.push(`"${footer}"`);
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
    <div className={`aseel-dense-table ${className}`}>
      {exportable && rows.length > 0 && (
        <div className="aseel-dense-toolbar">
          <button className="aseel-btn" onClick={handleExport} title="تصدير CSV" style={{ marginRight: 'auto' }}>
            تصدير
          </button>
        </div>
      )}
      <table className="aseel-grid" data-variant="list">
        <thead>
          <tr>
            {selectable && <th className="aseel-print-hidden" style={{ width: '32px' }}></th>}
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  width: colWidths[col.key] != null ? `${colWidths[col.key]}px` : col.width,
                  textAlign: getAlign(col) as any,
                  position: resizable ? 'relative' : undefined,
                }}
                className={[
                  col.sortable && onSort ? 'aseel-sortable' : '',
                  col.key === 'actions' ? 'aseel-print-hidden' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => handleSort(col)}
              >
                {col.header}
                {sortKey === col.key && (
                  <span className="aseel-sort-indicator">{sortDir === 'asc' ? '▲' : '▼'}</span>
                )}
                {resizable && (
                  // T-G1: مقبض سحب لتغيير عرض العمود (Excel-like) عند الحافة الطرفية.
                  <span
                    onMouseDown={(e) => startResize(e, col.key)}
                    onClick={(e) => e.stopPropagation()}
                    title="اسحب لتغيير عرض العمود"
                    style={{
                      position: 'absolute',
                      insetInlineEnd: 0,
                      top: 0,
                      height: '100%',
                      width: '6px',
                      cursor: 'col-resize',
                      userSelect: 'none',
                      zIndex: 1,
                    }}
                  />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && rows.length === 0 && (
            <tr className="aseel-row--empty">
              <td colSpan={totalCols}><AseelSpinner /></td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr className="aseel-row--empty">
              <td colSpan={totalCols}><AseelEmptyState hint={typeof emptyHint === 'string' ? emptyHint : undefined} /></td>
            </tr>
          )}
          {rows.map((row, idx) => {
            const key = getRowKey(row);
            const isSelected = selectedKey === key;
            const isHovered = hoveredKey === key;
            return (
              <tr
                key={key}
                className={[
                  isSelected ? 'aseel-row--selected' : '',
                  isHovered ? 'aseel-row--hover' : '',
                ].filter(Boolean).join(' ')}
                style={rowColorKey && row[rowColorKey] ? { color: row[rowColorKey] } : undefined}
                onClick={() => onRowClick?.(row)}
                onDoubleClick={() => onRowDoubleClick?.(row)}
                onMouseEnter={() => setHoveredKey(key)}
                onMouseLeave={() => setHoveredKey(null)}
              >
                {selectable && (
                  <td className="aseel-print-hidden">
                    <input
                      type="radio"
                      checked={isSelected}
                      onChange={() => onSelect?.(key)}
                    />
                  </td>
                )}
                {columns.map((col) => (
                  <td
                    key={col.key}
                    style={{ textAlign: getAlign(col) as any }}
                    className={[
                      col.numeric ? 'aseel-num' : '',
                      col.key === 'actions' ? 'aseel-print-hidden' : '',
                    ].filter(Boolean).join(' ')}
                  >
                    {col.render ? col.render(row, idx) : String((row as any)[col.key] ?? '')}
                  </td>
                ))}
              </tr>
            );
          })}
          {footer && (
            <tr className="aseel-row--total">
              <td colSpan={totalCols}>{footer}</td>
            </tr>
          )}
        </tbody>
      </table>
      {pagination && (
        <div className="aseel-pagination">
          <button
            disabled={pagination.page <= 1}
            onClick={() => pagination.onChange(pagination.page - 1)}
          >
            السابق
          </button>
          <span>
            صفحة {pagination.page} من {Math.ceil(pagination.total / pagination.pageSize)}
            ({pagination.total} سجل)
          </span>
          <button
            disabled={pagination.page >= Math.ceil(pagination.total / pagination.pageSize)}
            onClick={() => pagination.onChange(pagination.page + 1)}
          >
            التالي
          </button>
        </div>
      )}
    </div>
  );
}
