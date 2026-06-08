import React, { useCallback, useState } from 'react';
import { AseelCalculatorPopover } from './AseelCalculatorPopover';

export interface AseelGridColumn<T> {
  key: string;
  header: string;
  width?: string;
  align?: 'right' | 'center' | 'left';
  readOnly?: boolean;
  type?: 'text' | 'number';
  /** Custom static cell (e.g. an index-picker button). Overrides editor. */
  render?: (row: T, rowIndex: number) => React.ReactNode;
}

export interface AseelGridProps<T> {
  columns: AseelGridColumn<T>[];
  rows: T[];
  getCell: (row: T, key: string) => string | number | null | undefined;
  getRowKey: (row: T, index: number) => string | number;
  onChange?: (rowIndex: number, key: string, value: string) => void;
  onAddRow?: () => void;
  selectedIndex?: number;
  onSelectRow?: (index: number) => void;
  variant?: 'items' | 'journal';
  emptyHint?: string;
}

export function AseelGrid<T>({
  columns,
  rows,
  getCell,
  getRowKey,
  onChange,
  onAddRow,
  selectedIndex,
  onSelectRow,
  variant = 'items',
  emptyHint = 'لا توجد بنود — ابدأ الإدخال',
}: AseelGridProps<T>) {
  const [calcState, setCalcState] = useState<{
    rowIndex: number;
    columnKey: string;
    initialValue: string | number;
    x: number;
    y: number;
  } | null>(null);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>, rowIndex: number) => {
      const td = (e.target as HTMLElement).closest('td');
      const tr = td?.parentElement as HTMLTableRowElement | null;
      if (!tr) return;
      const colIndex = td ? Array.prototype.indexOf.call(tr.children, td) : -1;

      const focusCell = (r: number, c: number) => {
        const table = tr.closest('table');
        const targetRow = table?.querySelectorAll('tbody tr')[r] as
          | HTMLTableRowElement
          | undefined;
        const cell = targetRow?.children[c] as HTMLElement | undefined;
        const input = cell?.querySelector('input,select') as
          | HTMLElement
          | undefined;
        input?.focus();
      };

      if (e.key === 'Enter' || e.key === 'ArrowDown') {
        e.preventDefault();
        if (rowIndex === rows.length - 1 && onAddRow) onAddRow();
        focusCell(rowIndex + 1, colIndex);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (rowIndex > 0) focusCell(rowIndex - 1, colIndex);
      }
    },
    [rows.length, onAddRow],
  );

  const handleDoubleClick = (
    e: React.MouseEvent<HTMLInputElement>,
    ri: number,
    columnKey: string,
    currentVal: any
  ) => {
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    setCalcState({
      rowIndex: ri,
      columnKey: columnKey,
      initialValue: currentVal ?? '',
      x: rect.left,
      y: rect.bottom + window.scrollY,
    });
  };

  return (
    <div className="relative">
      <table className="aseel-grid" data-variant={variant}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ width: c.width }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{ textAlign: 'center', color: 'var(--aseel-ink-soft)', padding: '14px' }}
              >
                {emptyHint}
              </td>
            </tr>
          ) : (
            rows.map((row, ri) => (
              <tr
                key={getRowKey(row, ri)}
                className={ri === selectedIndex ? 'aseel-row--sel' : undefined}
                onMouseDown={() => onSelectRow?.(ri)}
              >
                {columns.map((c) => {
                  const val = getCell(row, c.key);
                  const alignClass =
                    c.align === 'left' || c.type === 'number' ? 'aseel-num' : undefined;
                  return (
                    <td key={c.key} className={alignClass} style={{ textAlign: c.align }}>
                      {c.render ? (
                        c.render(row, ri)
                      ) : c.readOnly || !onChange ? (
                        <span>{val ?? ''}</span>
                      ) : (
                        <input
                          data-aseel-key="1"
                          inputMode={c.type === 'number' ? 'decimal' : undefined}
                          value={val == null ? '' : String(val)}
                          onChange={(e) => onChange(ri, c.key, e.target.value)}
                          onKeyDown={(e) => handleKeyDown(e, ri)}
                          onDoubleClick={
                            c.type === 'number'
                              ? (e) => handleDoubleClick(e, ri, c.key, val)
                              : undefined
                          }
                        />
                      )}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>

      {calcState && (
        <AseelCalculatorPopover
          initialValue={calcState.initialValue}
          x={calcState.x}
          y={calcState.y}
          onConfirm={(result) => {
            if (onChange) {
              onChange(calcState.rowIndex, calcState.columnKey, String(result));
            }
            setCalcState(null);
          }}
          onClose={() => setCalcState(null)}
        />
      )}
    </div>
  );
}
