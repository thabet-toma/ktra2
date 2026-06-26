import React, { useCallback, useEffect, useRef } from 'react';

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
  const containerRef = useRef<HTMLDivElement>(null);
  const prevRowsLength = useRef(rows.length);

  useEffect(() => {
    if (rows.length > prevRowsLength.current) {
      setTimeout(() => {
        if (containerRef.current) {
          containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
      }, 10);
    }
    prevRowsLength.current = rows.length;
  }, [rows.length]);
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, rowIndex: number) => {
      const target = e.target as HTMLElement;
      if (target.tagName !== 'INPUT' && target.tagName !== 'SELECT') return;

      const td = target.closest('td');
      const tr = td?.parentElement as HTMLTableRowElement | null;
      if (!tr) return;
      const colIndex = td ? Array.prototype.indexOf.call(tr.children, td) : -1;

      const focusCell = (r: number, c: number) => {
        const table = tr.closest('table');
        const targetRow = table?.querySelectorAll('tbody tr')[r] as
          | HTMLTableRowElement
          | undefined;
        const cell = targetRow?.children[c] as HTMLElement | undefined;
        const input = cell?.querySelector('input,select,button') as
          | HTMLElement
          | undefined;
        input?.focus();
      };

      if (e.key === 'Enter') {
        const isCombobox = target.getAttribute('role') === 'combobox';
        const isExpanded = target.getAttribute('aria-expanded') === 'true';
        if (isCombobox && !isExpanded) return;

        e.preventDefault();
        const currentKey = columns[colIndex]?.key;

        if (currentKey === 'product' || currentKey === 'name' || currentKey === 'itemId') {
          const qtyIndex = columns.findIndex(c => c.key === 'quantity' || c.key === 'qty');
          if (qtyIndex !== -1) {
            focusCell(rowIndex, qtyIndex);
            return;
          }
        }

        if (currentKey === 'quantity' || currentKey === 'qty') {
          const priceIndex = columns.findIndex(c => c.key === 'unit_price' || c.key === 'unitPrice' || c.key === 'price');
          if (priceIndex !== -1) {
            focusCell(rowIndex, priceIndex);
            return;
          }
        }

        if (currentKey === 'unit_price' || currentKey === 'unitPrice' || currentKey === 'price') {
          let productIndex = columns.findIndex(c => c.key === 'product' || c.key === 'name');
          if (productIndex === -1) {
             productIndex = columns.findIndex(c => c.key === 'itemId');
          }
          if (productIndex !== -1) {
            if (rowIndex === rows.length - 1 && onAddRow) onAddRow();
            setTimeout(() => focusCell(rowIndex + 1, productIndex), 50);
            return;
          }
        }

        if (rowIndex === rows.length - 1 && onAddRow) onAddRow();
        setTimeout(() => focusCell(rowIndex + 1, colIndex), 50);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (rowIndex === rows.length - 1 && onAddRow) onAddRow();
        setTimeout(() => focusCell(rowIndex + 1, colIndex), 50);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (rowIndex > 0) focusCell(rowIndex - 1, colIndex);
      }
    },
    [rows.length, onAddRow, columns],
  );

  return (
    <div ref={containerRef} className="relative flex-1 overflow-y-auto min-h-0" style={{ zIndex: 0 }}>
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
                onKeyDown={(e) => handleKeyDown(e, ri)}
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
                          id={`aseel-grid-input-${ri}-${c.key}`}
                          data-aseel-key="1"
                          inputMode={c.type === 'number' ? 'decimal' : undefined}
                          value={val == null ? '' : String(val)}
                          onChange={(e) => onChange(ri, c.key, e.target.value)}
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
    </div>
  );
}
