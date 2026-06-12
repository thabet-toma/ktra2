/**
 * M0-T3 — AseelDocumentShell
 * Reusable presentational frame for every Aseel document screen:
 * title bar + command toolbar (with record navigation) + header field band
 * + lines/grid area + bottom tab strip + totals dock + status bar.
 * ZERO business logic — everything is a slot/prop. Consumed by M1+ screens.
 * Reference: docs/aseel_reference/invoices.txt 51–192 + owner screenshots.
 */
import React, { useMemo, useState } from 'react';
import {
  ChevronRight,
  ChevronLeft,
  ChevronsRight,
  ChevronsLeft,
} from 'lucide-react';
import type { RecordNavigation } from './useRecordNavigation';

export interface AseelToolbarAction {
  key: string;
  label: string;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  danger?: boolean;
  /** insert a separator BEFORE this action */
  separatorBefore?: boolean;
}

export interface AseelTab {
  key: string;
  label: string;
  content: React.ReactNode;
}

export interface AseelDocumentShellProps {
  /** Screen title chip, e.g. «فواتير الشراء». */
  title: string;
  /** Red doc-state line, e.g. «فاتورة جديدة» / «مرحّلة #12». */
  state?: string;
  /** Company / fiscal-year line, e.g. «الشركة العامة للزهور [ السنة المالية 1996 ]». */
  company?: string;
  /** Record navigation (from useRecordNavigation). Omit to hide nav group. */
  nav?: RecordNavigation;
  /** Command actions (add/save/delete/cancel/print/receipt/...). */
  actions?: AseelToolbarAction[];
  /** Header field band (labelled inputs). */
  header: React.ReactNode;
  /** Lines / grid area. */
  children: React.ReactNode;
  /** Bottom tab strip (notes / accounts / other). */
  tabs?: AseelTab[];
  /** Totals & payment dock (right side of the bottom area). */
  totals?: React.ReactNode;
  /** Status bar items (user / journal no / movement no / ...). */
  status?: React.ReactNode;
  /** Initial tab key (defaults to first tab). */
  initialTab?: string;
  /** Controlled active tab key. */
  activeTab?: string;
  /** Fired when active tab changes (for controlled mode). */
  onTabChange?: (key: string) => void;
}

/** task11 M6: يكتشف children الفارغة (null / <></> / مصفوفات فارغة).
 * صفحات كثيرة مرّرت محتواها الرئيسي كـ tab سفلي (مقيد بـ max-height:220px)
 * وتركت منطقة gridwrap المرنة فارغة — فظهر فراغ أبيض ضخم وسط الشاشة
 * والمحتوى مكبوس بالأسفل. عند غياب محتوى رئيسي حقيقي، تُعرض الـ tabs
 * ولوحتها داخل المنطقة المرنة بكامل الارتفاع. */
const isEmptyNode = (node: React.ReactNode): boolean => {
  if (node == null || node === false || node === '') return true;
  if (Array.isArray(node)) return node.every(isEmptyNode);
  if (React.isValidElement(node) && node.type === React.Fragment) {
    return isEmptyNode((node.props as { children?: React.ReactNode }).children);
  }
  return false;
};

const navBtn = (
  label: string,
  icon: React.ReactNode,
  onClick: (() => void) | undefined,
  disabled: boolean,
) => (
  <button
    type="button"
    className="aseel-toolbtn"
    onClick={onClick}
    disabled={disabled || !onClick}
    title={label}
  >
    {icon}
    <span>{label}</span>
  </button>
);

export const AseelDocumentShell: React.FC<AseelDocumentShellProps> = ({
  title,
  state,
  company,
  nav,
  actions = [],
  header,
  children,
  tabs = [],
  totals,
  status,
  initialTab,
  activeTab: controlledTab,
  onTabChange,
}) => {
  const initIdx = useMemo(() => {
    if (initialTab) { const i = tabs.findIndex((t) => t.key === initialTab); if (i >= 0) return i; }
    return 0;
  }, [initialTab, tabs]);
  const [localTab, setLocalTab] = useState(initIdx);
  const activeIdx = controlledTab != null ? tabs.findIndex((t) => t.key === controlledTab) : localTab;
  const effectiveIdx = activeIdx >= 0 ? activeIdx : 0;
  const tab = tabs[effectiveIdx];

  // task11 M6: بلا محتوى رئيسي حقيقي → الـ tabs تشغل المنطقة المرنة كاملة
  const tabsInMain = tabs.length > 0 && isEmptyNode(children);

  const tabStrip = tabs.length > 0 && (
    <div className="aseel-tabs" role="tablist">
      {tabs.map((t, i) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={i === effectiveIdx}
          className={`aseel-tab${i === effectiveIdx ? ' aseel-tab--active' : ''}`}
          onClick={() => {
            if (controlledTab != null) { onTabChange?.(t.key); }
            else { setLocalTab(i); }
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="aseel-doc" data-skin="aseel">
      {/* Title bar */}
      <div className="aseel-titlebar">
        <div className="aseel-company">{company}</div>
        <div className="aseel-title-grp">
          <span className="aseel-title-chip">{title}</span>
          {state && <span className="aseel-title-state">{state}</span>}
        </div>
      </div>

      {/* Command toolbar */}
      <div className="aseel-toolbar" role="toolbar" aria-label={title}>
        {nav && (
          <>
            <div className="aseel-toolgrp">
              {navBtn('الأول', <ChevronsRight />, nav.first, !nav.canPrev)}
              {navBtn('السابق', <ChevronRight />, nav.prev, !nav.canPrev)}
              {navBtn('التالي', <ChevronLeft />, nav.next, !nav.canNext)}
              {navBtn('الأخير', <ChevronsLeft />, nav.last, nav.total === 0)}
            </div>
            <div className="aseel-toolsep" />
          </>
        )}
        <div className="aseel-toolgrp">
          {actions.map((a) => (
            <React.Fragment key={a.key}>
              {a.separatorBefore && <div className="aseel-toolsep" />}
              <button
                type="button"
                className={`aseel-toolbtn${a.danger ? ' aseel-toolbtn--danger' : ''}`}
                onClick={a.onClick}
                disabled={a.disabled || !a.onClick}
                title={a.label}
              >
                {a.icon}
                <span>{a.label}</span>
              </button>
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Header field band */}
      <div className="aseel-headband">{header}</div>

      {/* Lines / grid — task13 M3: تدفق طبيعي بلا سكرول داخلي (سكرولر
          الصفحة الوحيد في main.app-content) */}
      <div className="aseel-gridwrap">
        {tabsInMain ? (
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
            {tabStrip}
            <div className="aseel-tabpanel" role="tabpanel" style={{ flex: '1 0 auto' }}>
              {tab?.content}
            </div>
          </div>
        ) : (
          children
        )}
      </div>

      {/* Bottom: tabs + totals dock (الـ tabs هنا فقط عندما يوجد محتوى رئيسي) */}
      {((tabs.length > 0 && !tabsInMain) || totals) && (
        <div className="aseel-bottom">
          {tabs.length > 0 && !tabsInMain && (
            <div className="aseel-tabscol">
              {tabStrip}
              <div className="aseel-tabpanel" role="tabpanel">
                {tab?.content}
              </div>
            </div>
          )}
          {totals && <div className="aseel-totals">{totals}</div>}
        </div>
      )}

      {/* Status bar */}
      {status && <div className="aseel-statusbar">{status}</div>}
    </div>
  );
};
