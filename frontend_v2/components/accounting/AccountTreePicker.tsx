/**
 * T-DEFACC — اختيار الحساب من شجرة الحسابات، لا من قائمة مسطّحة.
 * كل شاشة كانت تعرض الحسابات في `<select>` واحد يتتابع فيه الأب والابن بلا
 * ترتيب ولا مسار، فيتعذّر تمييز «صندوق فرع أ» عن «صندوق فرع ب». هنا تُفتح
 * الشجرة نفسها: طيّ وفتح، بحث يكشف مسار المطابق، واختيار من الورقة مباشرة.
 *
 * `AccountTreeField` هو البديل المباشر لأي `<select>` حساب في الموقع.
 * منطق الشجرة نفسه في `utils/accountTree` (مُختبَر على حدة).
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronLeft, X } from 'lucide-react';

import {
  accountLabel,
  ancestorIdsOf,
  buildAccountIndex,
  visibleAccountRows,
  type AccountNodeLike,
} from '../../utils/accountTree';

export interface AccountTreePickerProps {
  open: boolean;
  accounts: AccountNodeLike[];
  /** الحساب المختار حالياً — تُفتح الشجرة عليه. */
  value?: number | null;
  title?: string;
  /** الحسابات القابلة للاختيار؛ البقية تبقى للتصفّح فقط (آباء الشجرة). */
  isSelectable?: (account: AccountNodeLike) => boolean;
  onSelect: (account: AccountNodeLike) => void;
  onClose: () => void;
}

const rowIsSelectable = (
  account: AccountNodeLike,
  isSelectable?: (a: AccountNodeLike) => boolean,
) => (isSelectable ? isSelectable(account) : true);

export function AccountTreePicker({
  open,
  accounts,
  value,
  title = 'اختيار حساب من الشجرة',
  isSelectable,
  onSelect,
  onClose,
}: AccountTreePickerProps) {
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [cursor, setCursor] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);

  const index = useMemo(() => buildAccountIndex(accounts), [accounts]);
  const rows = useMemo(
    () => visibleAccountRows(accounts, index, { query, expanded }),
    [accounts, index, query, expanded],
  );

  // الفتح يكشف مسار الحساب المختار؛ وبلا اختيار تُفتح المستويات العليا فقط.
  useEffect(() => {
    if (!open) return;
    setQuery('');
    const next = new Set<number>(ancestorIdsOf(index, value ?? null));
    if (next.size === 0) {
      for (const root of index.childrenOf.get(null) ?? []) {
        next.add(root.id);
        for (const child of index.childrenOf.get(root.id) ?? []) next.add(child.id);
      }
    }
    setExpanded(next);
    const timer = window.setTimeout(() => searchRef.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [open, value, index]);

  useEffect(() => {
    // المؤشّر يبدأ على الحساب المختار إن كان ظاهراً.
    const at = rows.findIndex((r) => r.account.id === value);
    setCursor(at >= 0 ? at : 0);
    // يُعاد الضبط عند كل فتح/بحث فقط — لا مع كل إعادة رسم.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, query]);

  useEffect(() => {
    setCursor((c) => Math.min(c, Math.max(0, rows.length - 1)));
  }, [rows.length]);

  const toggle = useCallback((id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const commit = useCallback(
    (account: AccountNodeLike | undefined) => {
      if (!account) return;
      if (!rowIsSelectable(account, isSelectable)) return;
      onSelect(account);
    },
    [isSelectable, onSelect],
  );

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, rows.length - 1));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const row = rows[cursor];
      if (row && !rowIsSelectable(row.account, isSelectable) && row.hasChildren) {
        toggle(row.account.id);
      } else {
        commit(row?.account);
      }
      return;
    }
    // في RTL: السهم الأيسر يفتح الفرع والأيمن يطويه.
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      const row = rows[cursor];
      if (!row?.hasChildren) return;
      e.preventDefault();
      const wantOpen = e.key === 'ArrowLeft';
      if (wantOpen !== row.expanded) toggle(row.account.id);
    }
  };

  return (
    <div
      className="aseel-picker-mask"
      data-aseel-modal="1"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="aseel-picker"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={onKeyDown}
      >
        <div className="aseel-picker-head">
          <span>{title}</span>
          <button type="button" className="aseel-toolbtn" onClick={onClose} aria-label="إغلاق">
            <X />
          </button>
        </div>
        <div style={{ padding: '6px 10px' }}>
          <input
            ref={searchRef}
            className="aseel-input"
            placeholder="بحث بالكود أو الاسم… (↑↓ تنقّل · ← فتح · → طيّ · Enter اختيار · Esc خروج)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ width: '100%' }}
          />
        </div>
        <div className="aseel-picker-body" role="tree">
          {rows.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '14px' }}>لا نتائج</div>
          ) : (
            rows.map((row, i) => {
              const selectable = rowIsSelectable(row.account, isSelectable);
              return (
                <div
                  key={row.account.id}
                  role="treeitem"
                  aria-level={row.depth + 1}
                  aria-expanded={row.hasChildren ? row.expanded : undefined}
                  aria-selected={row.account.id === value}
                  className={`aseel-tree-row${i === cursor ? ' aseel-row--sel' : ''}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '3px 8px',
                    paddingInlineStart: `${8 + row.depth * 16}px`,
                    cursor: selectable ? 'pointer' : 'default',
                    opacity: selectable ? 1 : 0.75,
                    fontWeight: row.hasChildren ? 600 : 400,
                    background:
                      row.account.id === value ? 'var(--aseel-sel-bg, #dbeafe)' : undefined,
                  }}
                  onMouseDown={() => setCursor(i)}
                  onClick={() => {
                    if (row.hasChildren && !selectable) toggle(row.account.id);
                  }}
                  onDoubleClick={() => commit(row.account)}
                >
                  {row.hasChildren ? (
                    <button
                      type="button"
                      className="aseel-toolbtn"
                      aria-label={row.expanded ? 'طيّ' : 'فتح'}
                      style={{ padding: 0, width: '16px', height: '16px' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggle(row.account.id);
                      }}
                    >
                      {row.expanded ? <ChevronDown size={14} /> : <ChevronLeft size={14} />}
                    </button>
                  ) : (
                    <span style={{ display: 'inline-block', width: '16px' }} />
                  )}
                  <span className="font-mono" style={{ minWidth: '78px' }}>
                    {row.account.code}
                  </span>
                  <span style={{ flex: 1 }}>{row.account.name}</span>
                  {selectable && (
                    <button
                      type="button"
                      className="aseel-toolbtn"
                      onClick={(e) => {
                        e.stopPropagation();
                        commit(row.account);
                      }}
                    >
                      اختيار
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
        <div className="aseel-picker-foot">{rows.length} حساب ظاهر</div>
      </div>
    </div>
  );
}

export interface AccountTreeFieldProps {
  accounts: AccountNodeLike[];
  value: number | '' | null;
  onChange: (accountId: number | null, account: AccountNodeLike | null) => void;
  placeholder?: string;
  title?: string;
  disabled?: boolean;
  className?: string;
  isSelectable?: (account: AccountNodeLike) => boolean;
  /** يسمح بتفريغ الحقل (زر ×). */
  allowClear?: boolean;
}

/** بديل `<select>` الحساب: زر يعرض الحساب المختار ويفتح الشجرة. */
export function AccountTreeField({
  accounts,
  value,
  onChange,
  placeholder = '— اختر حساباً —',
  title,
  disabled,
  className,
  isSelectable,
  allowClear = true,
}: AccountTreeFieldProps) {
  const [open, setOpen] = useState(false);
  const selectedId = value === '' || value == null ? null : Number(value);
  const selected = useMemo(
    () => accounts.find((a) => a.id === selectedId) ?? null,
    [accounts, selectedId],
  );

  return (
    <>
      <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
        <button
          type="button"
          className={className ?? 'aseel-input'}
          disabled={disabled}
          onClick={() => setOpen(true)}
          style={{ flex: 1, textAlign: 'start', overflow: 'hidden', whiteSpace: 'nowrap' }}
          title={selected ? accountLabel(selected) : placeholder}
        >
          {selected ? accountLabel(selected) : placeholder}
        </button>
        {allowClear && selected && !disabled && (
          <button
            type="button"
            className="aseel-toolbtn"
            aria-label="مسح الحساب"
            onClick={() => onChange(null, null)}
          >
            <X size={14} />
          </button>
        )}
      </div>
      <AccountTreePicker
        open={open}
        accounts={accounts}
        value={selectedId}
        title={title}
        isSelectable={isSelectable}
        onSelect={(account) => {
          onChange(account.id, account);
          setOpen(false);
        }}
        onClose={() => setOpen(false)}
      />
    </>
  );
}
