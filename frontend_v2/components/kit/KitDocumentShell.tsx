/**
 * M0-T3 — KitDocumentShell
 * Reusable presentational frame for every Kit document screen:
 * title bar + command toolbar (with record navigation) + header field band
 * + lines/grid area + bottom tab strip + totals dock + status bar.
 * ZERO business logic — everything is a slot/prop. Consumed by M1+ screens.
 * Reference: docs/aseel_reference/invoices.txt 51–192 + owner screenshots.
 */
import React, { useState } from 'react';
import {
  ChevronRight,
  ChevronLeft,
  ChevronsRight,
  ChevronsLeft,
} from 'lucide-react';
import type { RecordNavigation } from './useRecordNavigation';
import { resolveActiveTabKey } from '../../utils/tabSelection';

export interface KitToolbarAction {
  key: string;
  label: string;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  danger?: boolean;
  /** insert a separator BEFORE this action */
  separatorBefore?: boolean;
}

export interface KitTab {
  key: string;
  label: string;
  content: React.ReactNode;
}

export interface KitDocumentShellProps {
  /** Screen title chip, e.g. «فواتير الشراء». */
  title: string;
  /** Red doc-state line, e.g. «فاتورة جديدة» / «مرحّلة #12». */
  state?: string;
  /** Company / fiscal-year line, e.g. «الشركة العامة للزهور [ السنة المالية 1996 ]». */
  company?: string;
  /** Record navigation (from useRecordNavigation). Omit to hide nav group. */
  nav?: RecordNavigation;
  /** Command actions (add/save/delete/cancel/print/receipt/...). */
  actions?: KitToolbarAction[];
  /** Header field band (labelled inputs). Optional — when omitted the band is
   *  skipped entirely (G5: نموذج الصفقة صار بلا شبكة علوية، التبويبات هي المصدر). */
  header?: React.ReactNode;
  /** Optional full-height right rail spanning the header band + grid (e.g. الشجرة).
   *  When provided, the header + grid are wrapped in a column beside this rail so
   *  it rises to the very top of the document instead of starting below the header. */
  aside?: React.ReactNode;
  /** Lines / grid area. */
  children: React.ReactNode;
  /** عند true: منطقة الشبكة تأخذ ارتفاع محتواها فقط بدل الامتداد لملء الفراغ
   *  (يمنع فراغاً أبيض ضخماً أسفل مستند عرض قصير — بند واحد مثلاً). استخدمه
   *  لوضع العرض القرائي (viewMode)، لا لشبكة الإدخال التي يجب أن تملأ الصفحة. */
  gridFitContent?: boolean;
  /** Bottom tab strip (notes / accounts / other). */
  tabs?: KitTab[];
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
    className="ktra-toolbtn"
    onClick={onClick}
    disabled={disabled || !onClick}
    title={label}
  >
    {icon}
    <span>{label}</span>
  </button>
);

export const KitDocumentShell: React.FC<KitDocumentShellProps> = ({
  title,
  state,
  company,
  nav,
  actions = [],
  header,
  aside,
  children,
  gridFitContent = false,
  tabs = [],
  totals,
  status,
  initialTab,
  activeTab: controlledTab,
  onTabChange,
}) => {
  // التتبّع بالمعرّف لا بالفهرس (utils/tabSelection.ts): كان الغلاف يحفظ رقم
  // التبويب، فإدراجُ تبويبٍ في الوسط وقت التشغيل يزيح كل ما بعده ويقفز
  // بالمستخدم إلى شاشة أخرى. و`initialTab` صار يُطبَّق متى ظهر تبويبه لا في
  // أول رسمة وحدها — الشاشات التي تبني تبويباتها بعد الجلب كانت تُسقط الرابط
  // العميق (`?tab=`) بصمت لأن المصفوفة كانت فارغة لحظة تهيئة الحالة.
  const [pickedTab, setPickedTab] = useState<string | null>(null);
  const activeKey = controlledTab != null
    ? resolveActiveTabKey(tabs, controlledTab)
    : resolveActiveTabKey(tabs, pickedTab, initialTab);
  const tab = tabs.find((t) => t.key === activeKey);

  // task11 M6: بلا محتوى رئيسي حقيقي → الـ tabs تشغل المنطقة المرنة كاملة
  const tabsInMain = tabs.length > 0 && isEmptyNode(children);

  const tabStrip = tabs.length > 0 && (
    <div className="ktra-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={t.key === activeKey}
          className={`ktra-tab${t.key === activeKey ? ' ktra-tab--active' : ''}`}
          onClick={() => {
            if (controlledTab != null) { onTabChange?.(t.key); }
            else { setPickedTab(t.key); }
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="ktra-doc">
      {/* Title bar */}
      <div className="ktra-titlebar">
        <div className="ktra-title-grp">
          <span className="ktra-title-chip">{title}</span>
          {state && <span className="ktra-title-state">{state}</span>}
        </div>
        <div className="ktra-company">{company}</div>
      </div>

      {/* Command toolbar */}
      <div className="ktra-toolbar" role="toolbar" aria-label={title}>
        {nav && (
          <>
            <div className="ktra-toolgrp">
              {navBtn('الأول', <ChevronsRight />, nav.first, !nav.canPrev)}
              {navBtn('السابق', <ChevronRight />, nav.prev, !nav.canPrev)}
              {navBtn('التالي', <ChevronLeft />, nav.next, !nav.canNext)}
              {navBtn('الأخير', <ChevronsLeft />, nav.last, nav.total === 0)}
            </div>
            <div className="ktra-toolsep" />
          </>
        )}
        <div className="ktra-toolgrp">
          {actions.map((a) => (
            <React.Fragment key={a.key}>
              {a.separatorBefore && <div className="ktra-toolsep" />}
              <button
                type="button"
                className={`ktra-toolbtn${a.danger ? ' ktra-toolbtn--danger' : ''}`}
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

      {/* Header field band + lines/grid — task13 M3: تدفق طبيعي بلا سكرول داخلي
          (سكرولر الصفحة الوحيد في main.app-content). عند تمرير `aside` تُغلَّف هذه
          المنطقة في عمود بجانب الشريط الجانبي ليرتفع لأعلى المستند. */}
      {(() => {
        const band = header ? <div className="ktra-headband">{header}</div> : null;
        const grid = (
          <div className={`ktra-gridwrap${gridFitContent && !tabsInMain ? ' ktra-gridwrap--fit' : ''}`}>
            {tabsInMain ? (
              <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
                {tabStrip}
                <div className="ktra-tabpanel" role="tabpanel" style={{ flex: '1 0 auto' }}>
                  {tab?.content}
                </div>
              </div>
            ) : (
              children
            )}
          </div>
        );
        return aside ? (
          <div className="ktra-doc-mainrow">
            {aside}
            <div className="ktra-doc-maincol">
              {band}
              {grid}
            </div>
          </div>
        ) : (
          <>
            {band}
            {grid}
          </>
        );
      })()}

      {/* Bottom: tabs + totals dock (الـ tabs هنا فقط عندما يوجد محتوى رئيسي) */}
      {((tabs.length > 0 && !tabsInMain) || totals) && (
        <div className="ktra-bottom">
          {tabs.length > 0 && !tabsInMain && (
            <div className="ktra-tabscol">
              {tabStrip}
              <div className="ktra-tabpanel" role="tabpanel">
                {tab?.content}
              </div>
            </div>
          )}
          {totals && <div className="ktra-totals">{totals}</div>}
        </div>
      )}

      {/* Status bar */}
      {status && <div className="ktra-statusbar">{status}</div>}
    </div>
  );
};
