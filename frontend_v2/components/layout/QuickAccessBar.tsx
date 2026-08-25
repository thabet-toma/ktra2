import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { AppView } from '../../types';
import { Breadcrumb } from './Breadcrumb';
import { IMPORT_GUIDE_SLOT_ID } from '../../utils/importGuidePref';
import {
  QUICK_BAR_EVENT,
  QUICK_BAR_REGION_ID,
  readQuickBarOpen,
  writeQuickBarOpen,
} from '../../utils/quickBarPref';
import {
  getQuickShortcuts,
  iconForShortcut,
  labelForShortcut,
  QUICK_SHORTCUTS_EVENT,
  type ShortcutIconName,
} from '../../utils/quickShortcuts';
import {
  ArrowLeftRight,
  BarChart3,
  BookOpen,
  Boxes,
  Building2,
  ClipboardList,
  FileText,
  Handshake,
  History,
  Home,
  Package,
  ReceiptText,
  Ship,
  ShoppingCart,
  Truck,
  Users,
  WalletCards,
  Zap,
  type LucideIcon,
} from 'lucide-react';

/**
 * **شريط الوصول السريع** — الشريط الأفقي أعلى المحتوى: زرّ «رجوع» ومسار الشاشة،
 * ثم بطاقات الاختصارات المُهيّأة، ثم مرسى زرّ «مرشد الرحلة». يُطوى ويُبسط بضغطة.
 *
 * ⚠ لا يُخلط بـ`ActionBarRail` — ذاك «شريط الإجراءات» (إنشاء/طباعة/تحديث) رفٌّ
 * عائم قابل للإرساء على الحواف. هذا شريط **وصول** لا **إجراء**: وجهته التنقّل.
 *
 * ### لماذا يُطوى أصلاً
 * الشريط يحجز ~52px من ارتفاع كل شاشة طوال اليوم، ومَن حفظ طريقه لا يقرأ
 * مساره ولا يضغط اختصاراته. النمط مأخوذ من طيّ شريط أوامر Office
 * (`Ctrl+F1` — يبقي اللسان ويُخفي الأوامر) ومن الأشرطة الجانبية القابلة للطيّ
 * في أدوات اليوم؛ ومرفوضٌ منه **الإخفاء التلقائي** (Auto-hide): حالةٌ يسهل
 * نسيان أنك فعّلتها فتبدو الواجهة معطوبة. فالمطويّ هنا يترك **لساناً مرئياً
 * دائماً** — لا حالة لا يُخرَج منها.
 *
 * ### القرارات المُلزِمة
 * - **المرسى لا يُفكَّك عند الطيّ**: `ImportJourneyGuide` يمسك عقدة المرسى
 *   بـ`getElementById` مرّةً ويصبّ فيها `createPortal`. حذفُ العقدة يترك
 *   البوابة تصبّ في عقدةٍ منفصلة عن الصفحة ⇒ زرّ «مرشد الرحلة» يختفي ولا يعود
 *   بالبسط. لذلك الطيّ ارتفاعٌ صفر (`grid-template-rows: 0fr`) لا `display:none`
 *   ولا إزالة من الشجرة.
 * - **`inert` مع الإخفاء**: بلا هذا يبقى المطويّ في مسار `Tab` — يقفز التركيز
 *   إلى أزرار لا يراها أحد.
 * - الحركة تُلغى عند `prefers-reduced-motion`.
 */

const SHORTCUT_ICONS: Record<ShortcutIconName, LucideIcon> = {
  home: Home,
  'sales-invoice': ReceiptText,
  'purchase-invoice': ShoppingCart,
  quotation: FileText,
  'supplier-offer': ClipboardList,
  items: Boxes,
  suppliers: Building2,
  customers: Users,
  'stock-movements': ArrowLeftRight,
  journal: BookOpen,
  cashboxes: WalletCards,
  reports: BarChart3,
  'import-offers': ClipboardList,
  'international-invoices': FileText,
  deals: Handshake,
  shipments: Ship,
  'old-invoices': History,
  'local-shipping': Truck,
  clearance: FileText,
  'import-flow': Package,
  zap: Zap,
};

const SHORTCUT_ICON_COLORS: Record<ShortcutIconName, string> = {
  home: 'text-blue-600 dark:text-blue-400',
  'sales-invoice': 'text-emerald-600 dark:text-emerald-400',
  'purchase-invoice': 'text-amber-600 dark:text-amber-400',
  quotation: 'text-violet-600 dark:text-violet-400',
  'supplier-offer': 'text-rose-600 dark:text-rose-400',
  items: 'text-cyan-600 dark:text-cyan-400',
  suppliers: 'text-orange-600 dark:text-orange-400',
  customers: 'text-indigo-600 dark:text-indigo-400',
  'stock-movements': 'text-teal-600 dark:text-teal-400',
  journal: 'text-fuchsia-600 dark:text-fuchsia-400',
  cashboxes: 'text-green-600 dark:text-green-400',
  reports: 'text-sky-600 dark:text-sky-400',
  'import-offers': 'text-lime-600 dark:text-lime-400',
  'international-invoices': 'text-purple-600 dark:text-purple-400',
  deals: 'text-pink-600 dark:text-pink-400',
  shipments: 'text-blue-500 dark:text-blue-300',
  'old-invoices': 'text-stone-600 dark:text-stone-400',
  'local-shipping': 'text-amber-500 dark:text-amber-300',
  clearance: 'text-red-600 dark:text-red-400',
  'import-flow': 'text-emerald-500 dark:text-emerald-300',
  zap: 'text-slate-600 dark:text-slate-300',
};

interface QuickAccessBarProps {
  activeView: AppView;
  onNavigate: (view: AppView, targetId?: string) => void;
  /** مسار قائمة الشاشة الحالية — وجهةُ «رجوع» حين لا سابقة في هذا التبويب. */
  listPath?: string;
  /** صاحب التفضيل: الطيّ يُحفظ باسمه لا باسم الجهاز. */
  userId: string;
}

export const QuickAccessBar: React.FC<QuickAccessBarProps> = ({
  activeView,
  onNavigate,
  listPath,
  userId,
}) => {
  const [open, setOpen] = useState(() => readQuickBarOpen(window.localStorage, userId));

  // task16 D14: اختصارات الوصول السريع (قابلة للتهيئة من الإعدادات)
  const [shortcuts, setShortcuts] = useState<AppView[]>(() => getQuickShortcuts());
  useEffect(() => {
    const refresh = () => setShortcuts(getQuickShortcuts());
    window.addEventListener(QUICK_SHORTCUTS_EVENT, refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener(QUICK_SHORTCUTS_EVENT, refresh);
      window.removeEventListener('storage', refresh);
    };
  }, []);

  /* تبديل المستخدم على الجهاز نفسه يُعيد قراءة تفضيله هو — لا يرث طيّ سابقه.
     و`storage` يُبقي تبويبات المتصفّح على رأيٍ واحد. */
  useEffect(() => {
    const refresh = () => setOpen(readQuickBarOpen(window.localStorage, userId));
    refresh();
    window.addEventListener(QUICK_BAR_EVENT, refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener(QUICK_BAR_EVENT, refresh);
      window.removeEventListener('storage', refresh);
    };
  }, [userId]);

  /* الحفظ والبثّ **خارج** مُحدِّث الحالة: React يستدعي المُحدِّث مرّتين في وضع
     التطوير الصارم، فأثرٌ جانبيّ بداخله يكتب `0` ثم يعيد `1` فوقها — الشريط
     يُطوى ويُبسط في الضغطة الواحدة ولا يُحفظ شيء. */
  const toggle = React.useCallback(() => {
    const next = !readQuickBarOpen(window.localStorage, userId);
    writeQuickBarOpen(window.localStorage, userId, next);
    setOpen(next);
    window.dispatchEvent(new CustomEvent(QUICK_BAR_EVENT));
  }, [userId]);

  /* `Ctrl+F1` — نفس وتر طيّ شريط الأوامر في Office. لا يصطدم بـ`F1` المجرّد في
     شاشات المستندات: `useKitKeymap` يتجاهل المفاتيح الوظيفية مع Ctrl. */
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'F1' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        toggle();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toggle]);

  const visibleShortcuts = shortcuts.filter((v) => v !== 'dashboard' && v !== activeView);

  return (
    <div className="flex-shrink-0" data-quick-bar={open ? 'open' : 'collapsed'}>
      <div
        id={QUICK_BAR_REGION_ID}
        aria-hidden={!open}
        inert={!open}
        className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        }`}
      >
        <div className="min-h-0 overflow-hidden">
          {/* شريط التنقل السريع */}
          <div className="ktra-toolbar relative overflow-hidden">
            <div
              className="pointer-events-none absolute inset-0 bg-gradient-to-l from-sky-100/90 via-blue-50/90 to-cyan-100/80 dark:from-slate-900 dark:via-blue-950/80 dark:to-cyan-950/70"
              aria-hidden="true"
            />
            <div className="ktra-toolgrp relative z-10">
              <Breadcrumb activeView={activeView} listPath={listPath} />
            </div>
            {visibleShortcuts.length > 0 && (
              <div className="ktra-toolgrp relative z-10 ms-4 flex items-center gap-1.5 py-1" title="اختصارات سريعة (تُهيّأ من الإعدادات)">
                {visibleShortcuts.map((v) => {
                  const iconName = iconForShortcut(v);
                  const ShortcutIcon = SHORTCUT_ICONS[iconName];
                  return (
                    <button
                      key={v}
                      type="button"
                      onClick={() => onNavigate(v)}
                      className="group flex min-w-[4.75rem] flex-col items-center justify-center gap-1 rounded-lg border border-blue-100/80 bg-white/75 px-2.5 py-1.5 text-[11px] font-semibold text-[var(--color-text)] shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-white hover:shadow-md dark:border-blue-900/60 dark:bg-slate-900/55 dark:hover:border-blue-700 dark:hover:bg-slate-900"
                    >
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/80 bg-white/90 shadow-inner transition-transform group-hover:scale-105 dark:border-slate-700 dark:bg-slate-800/90">
                        <ShortcutIcon className={`h-5 w-5 ${SHORTCUT_ICON_COLORS[iconName]}`} />
                      </span>
                      <span className="whitespace-nowrap">{labelForShortcut(v)}</span>
                    </button>
                  );
                })}
              </div>
            )}
            {/* مرسى زرّ «مرشد الرحلة» — يملؤه ImportJourneyGuide بـportal حين
                يكون مطويّاً ومتاحاً لهذا المستخدم، ويبقى فارغاً بلا عرض للآخرين. */}
            <div id={IMPORT_GUIDE_SLOT_ID} className="ktra-toolgrp relative z-10 ms-2 flex items-center py-1" />
            <button
              type="button"
              onClick={toggle}
              aria-expanded={open}
              aria-controls={QUICK_BAR_REGION_ID}
              aria-label="طيّ شريط الوصول السريع"
              title="طيّ شريط الوصول السريع (Ctrl+F1)"
              data-testid="quick-bar-collapse"
              className="relative z-10 ms-auto flex items-center gap-1 self-center rounded-lg border border-transparent px-2 py-1 text-[11px] font-semibold text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-border)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
            >
              <ChevronUp className="h-4 w-4" />
              <span className="hidden sm:inline">طيّ الشريط</span>
            </button>
          </div>
        </div>
      </div>

      {/* اللسان — الأثر الوحيد الباقي للشريط المطويّ، ومَخرجه الوحيد أيضاً.
          يظهر مطويّاً فقط كي لا يزاحم الشريط المبسوط بسطرٍ ثانٍ. */}
      {!open && (
        <button
          type="button"
          onClick={toggle}
          aria-expanded={false}
          aria-controls={QUICK_BAR_REGION_ID}
          aria-label="إظهار شريط الوصول السريع"
          title="إظهار شريط الوصول السريع (Ctrl+F1)"
          data-testid="quick-bar-lip"
          className="group flex w-full items-center justify-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-2)] py-1 transition-colors hover:bg-[var(--color-surface-3)]"
        >
          <span className="h-1 w-10 rounded-full bg-[var(--color-border)] transition-colors group-hover:bg-[var(--color-primary)]" />
          <ChevronDown className="h-3 w-3 text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-primary)]" />
          <span className="h-1 w-10 rounded-full bg-[var(--color-border)] transition-colors group-hover:bg-[var(--color-primary)]" />
        </button>
      )}
    </div>
  );
};
