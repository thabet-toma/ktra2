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
import React, { useState } from 'react';
import { AseelSpinner, AseelEmptyState } from './AseelStates';

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
};

export function AseelDenseTable<T>({
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
}: AseelDenseTableProps<T>) {
  const totalCols = columns.length + (selectable ? 1 : 0);
  const [hoveredKey, setHoveredKey] = useState<string | number | null>(null);

  const handleSort = (col: DenseColumn<T>) => {
    if (!col.sortable || !onSort) return;
    const newDir = sortKey === col.key && sortDir === 'asc' ? 'desc' : 'asc';
    onSort(col.key, newDir);
  };

  const getAlign = (col: DenseColumn<T>) => {
    if (col.align) return col.align;
    if (col.numeric) return 'right';
    return 'left';
  };

  return (
    <div className={`aseel-dense-table ${className}`}>
      <table className="aseel-grid" data-variant="list">
        <thead>
          <tr>
            {selectable && <th style={{ width: '32px' }}></th>}
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width, textAlign: getAlign(col) as any }}
                className={col.sortable && onSort ? 'aseel-sortable' : ''}
                onClick={() => handleSort(col)}
              >
                {col.header}
                {sortKey === col.key && (
                  <span className="aseel-sort-indicator">{sortDir === 'asc' ? '▲' : '▼'}</span>
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
                onClick={() => onRowClick?.(row)}
                onDoubleClick={() => onRowDoubleClick?.(row)}
                onMouseEnter={() => setHoveredKey(key)}
                onMouseLeave={() => setHoveredKey(null)}
              >
                {selectable && (
                  <td>
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
                    className={col.numeric ? 'aseel-num' : ''}
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
