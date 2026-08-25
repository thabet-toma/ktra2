/**
 * M0-T6 — KitIndexPicker
 * Unified popup index (حسابات / أصناف / عملات) opened from a field via `+`
 * or the «…» affordance. Search + keyboard stepping (`*` next, `-` prev),
 * Enter selects, Esc closes — exactly the Kit index behaviour.
 * Generic & presentational: parent supplies columns + rows + handlers.
 * Reference: invoices.txt 81–83, 96; accounting.txt 188–189; shipments 38–80.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';

export interface KitIndexColumn<T> {
  key: string;
  header: string;
  width?: string;
  value: (row: T) => string | number;
}

export interface KitIndexPickerProps<T> {
  open: boolean;
  title: string;
  rows: T[];
  columns: KitIndexColumn<T>[];
  getRowKey: (row: T) => string | number;
  /** keys searched by the filter box */
  searchValue?: (row: T) => string;
  onSelect: (row: T) => void;
  onClose: () => void;
  /** Custom button rendered next to the search box (e.g. Add Item) */
  actionButton?: React.ReactNode;
  /** T-QUICKPARTY: عند عدم وجود نتيجة يصير سطر «لا نتائج» نفسه زرَّ إنشاء
   *  يحمل ما كُتب في البحث. الإنشاء يجب أن يكون حيث انتهى البحث لا في زرٍّ
   *  يبحث عنه المستخدم في مكان آخر. */
  onCreate?: (query: string) => void;
  /** نص سطر الإنشاء — الافتراضي «إضافة «النص»». */
  createLabel?: (query: string) => string;
}

export function KitIndexPicker<T>({
  open,
  title,
  rows,
  columns,
  getRowKey,
  searchValue,
  onSelect,
  onClose,
  actionButton,
  onCreate,
  createLabel,
}: KitIndexPickerProps<T>) {
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQ('');
      setSel(0);
      // focus search on next frame
      const id = window.setTimeout(() => searchRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
  }, [open]);

  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const needle = q.trim().toLowerCase();
    const get = searchValue ?? ((r: T) => columns.map((c) => c.value(r)).join(' '));
    return rows.filter((r) => get(r).toString().toLowerCase().includes(needle));
  }, [q, rows, columns, searchValue]);

  useEffect(() => {
    setSel((s) => Math.min(s, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  if (!open) return null;

  /** بحثٌ بلا نتيجة + نصٌّ مكتوب = الإنشاء هو الإجراء الوحيد المتبقّي. */
  const canCreate = !!onCreate && filtered.length === 0 && q.trim().length > 0;

  const commit = (row: T | undefined) => {
    if (row) onSelect(row);
    else if (canCreate) onCreate!(q.trim());
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown' || e.key === '*') {
      e.preventDefault();
      setSel((s) => Math.min(s + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp' || e.key === '-') {
      e.preventDefault();
      setSel((s) => Math.max(s - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      commit(filtered[sel]);
    }
  };

  return (
    <div
      className="ktra-picker-mask"
      data-ktra-modal="1"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="ktra-picker" role="dialog" aria-modal="true" aria-label={title} onKeyDown={onKeyDown}>
        <div className="ktra-picker-head">
          <span>{title}</span>
          <button type="button" className="ktra-toolbtn" onClick={onClose} aria-label="إغلاق">
            <X />
          </button>
        </div>
        <div style={{ padding: '6px 10px', display: 'flex', gap: '8px' }}>
          <input
            ref={searchRef}
            className="ktra-input"
            placeholder="بحث… (Enter اختيار · * تالي · - سابق · Esc خروج)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1 }}
          />
          {actionButton}
        </div>
        <div className="ktra-picker-body">
          <table className="ktra-grid">
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
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} style={{ textAlign: 'center', padding: '14px' }}>
                    {canCreate ? (
                      <button
                        type="button"
                        className="ktra-autocomplete-row ktra-autocomplete-row--create"
                        onClick={() => onCreate!(q.trim())}
                      >
                        {createLabel ? createLabel(q.trim()) : `إضافة «${q.trim()}»`}
                      </button>
                    ) : (
                      'لا نتائج'
                    )}
                  </td>
                </tr>
              ) : (
                filtered.map((row, i) => (
                  <tr
                    key={getRowKey(row)}
                    className={i === sel ? 'ktra-row--sel' : undefined}
                    onMouseDown={() => setSel(i)}
                    onDoubleClick={() => commit(row)}
                  >
                    {columns.map((c) => (
                      <td key={c.key}>{c.value(row)}</td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="ktra-picker-foot">
          {filtered.length} سجل · المحدد {filtered.length ? sel + 1 : 0}
        </div>
      </div>
    </div>
  );
}
