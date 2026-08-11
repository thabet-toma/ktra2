import React, { useState, useEffect } from 'react';
import { Sidebar } from '../Sidebar';
import { User, AppView } from '../../types';
import {
  Breadcrumb,
} from './Breadcrumb';
import {
  DensitySwitch,
} from './DensitySwitch';
import {
  ThemeToggle,
} from './ThemeToggle';
import { PriceVisibilityToggle } from './PriceVisibilityToggle';
import {
  GlobalSearch,
} from './GlobalSearch';
import {
  CompanySwitcher,
} from './CompanySwitcher';
import {
  BranchSwitcher,
} from './BranchSwitcher';
import { AseelCalculatorButton } from '../aseel';
import { GlobalActionBar } from './GlobalActionBar';
import { GlobalContextMenu } from './GlobalContextMenu';
import { NotificationCenter } from '../notifications/NotificationCenter';
import { WhatsNewButton } from './WhatsNewButton';
import { CustomerNotesTab } from '../partners/CustomerNotesTab';
// استيراد مباشر لا عبر barrel الـimport-flow: البرميل يجرّ ImportDocumentScreen
// كاملةً إلى حزمة القشرة ويُبطل تقسيم الحِزَم.
import { ImportJourneyGuide } from '../import-flow/ImportJourneyGuide';
import { platformNoteTarget, type PlatformNoteTarget } from '../../utils/entityLinks';
import {
  User as UserIcon,
  Calendar,
  Sparkles,
  LogOut,
  Copy,
  SlidersHorizontal,
  Home,
  ReceiptText,
  ShoppingCart,
  FileText,
  ClipboardList,
  Boxes,
  Building2,
  Users,
  ArrowLeftRight,
  BookOpen,
  WalletCards,
  BarChart3,
  Zap,
  Handshake,
  Ship,
  History,
  Truck,
  Package,
  NotebookPen,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { formatDateValue } from "../../utils/formatDate";
import {
  getQuickShortcuts,
  iconForShortcut,
  labelForShortcut,
  QUICK_SHORTCUTS_EVENT,
  type ShortcutIconName,
} from '../../utils/quickShortcuts';

interface AppLayoutProps {
  user: User;
  activeView: AppView;
  onNavigate: (view: AppView, targetId?: string) => void;
  children: React.ReactNode;
  /** N0-T5: callback لفتح صفحة ثوابت المجموعة (F11). */
  onOpenGroupConstants?: () => void;
}

const SHORTCUT_ICONS: Record<ShortcutIconName, LucideIcon> = {
  home: Home,
  "sales-invoice": ReceiptText,
  "purchase-invoice": ShoppingCart,
  quotation: FileText,
  "supplier-offer": ClipboardList,
  items: Boxes,
  suppliers: Building2,
  customers: Users,
  "stock-movements": ArrowLeftRight,
  journal: BookOpen,
  cashboxes: WalletCards,
  reports: BarChart3,
  "import-offers": ClipboardList,
  "international-invoices": FileText,
  deals: Handshake,
  shipments: Ship,
  "old-invoices": History,
  "local-shipping": Truck,
  clearance: FileText,
  "import-flow": Package,
  zap: Zap,
};

const SHORTCUT_ICON_COLORS: Record<ShortcutIconName, string> = {
  home: "text-blue-600 dark:text-blue-400",
  "sales-invoice": "text-emerald-600 dark:text-emerald-400",
  "purchase-invoice": "text-amber-600 dark:text-amber-400",
  quotation: "text-violet-600 dark:text-violet-400",
  "supplier-offer": "text-rose-600 dark:text-rose-400",
  items: "text-cyan-600 dark:text-cyan-400",
  suppliers: "text-orange-600 dark:text-orange-400",
  customers: "text-indigo-600 dark:text-indigo-400",
  "stock-movements": "text-teal-600 dark:text-teal-400",
  journal: "text-fuchsia-600 dark:text-fuchsia-400",
  cashboxes: "text-green-600 dark:text-green-400",
  reports: "text-sky-600 dark:text-sky-400",
  "import-offers": "text-lime-600 dark:text-lime-400",
  "international-invoices": "text-purple-600 dark:text-purple-400",
  deals: "text-pink-600 dark:text-pink-400",
  shipments: "text-blue-500 dark:text-blue-300",
  "old-invoices": "text-stone-600 dark:text-stone-400",
  "local-shipping": "text-amber-500 dark:text-amber-300",
  clearance: "text-red-600 dark:text-red-400",
  "import-flow": "text-emerald-500 dark:text-emerald-300",
  zap: "text-slate-600 dark:text-slate-300",
};

export const AppLayout: React.FC<AppLayoutProps> = ({
  user,
  activeView,
  onNavigate,
  children,
  onOpenGroupConstants,
}) => {
  const { logout } = useAuth();
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');
  const [notesTarget, setNotesTarget] = useState<PlatformNoteTarget | null>(null);

  const openPlatformNotes = () => {
    const heading = document.querySelector<HTMLElement>('main h1, main h2, main h3')
      ?.textContent?.trim();
    setNotesTarget(platformNoteTarget(
      window.location.pathname,
      window.location.search,
      heading || document.title || 'الصفحة الحالية',
    ));
  };
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

  // N0-T5: F11 global keymap → يفتح GroupConstantsPage كـ modal portal
  useEffect(() => {
    if (!onOpenGroupConstants) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'F11') {
        e.preventDefault();
        onOpenGroupConstants();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onOpenGroupConstants]);

  return (
    <div className="app-shell flex flex-col h-screen overflow-hidden bg-[var(--color-surface)]" data-density={density}>
      {/* task13 M6: حُذف chip العنوان (كان يكرر تسمية الشريط الجانبي والـ breadcrumb)
           ونُقلت «السنة المالية» إلى شريط الحالة السفلي بجانب المستخدم/الدور. */}
      <div className="aseel-titlebar aseel-app-chrome flex-shrink-0">
        <div className="aseel-company flex items-center gap-3">
          <CompanySwitcher />
          <BranchSwitcher />
          
          {/* T-N1: المساعد الذكي */}
          <button
            type="button"
            onClick={() => onNavigate('smart-assistant')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-medium transition-colors ${
              activeView === 'smart-assistant'
                ? 'bg-[var(--color-primary)] text-white'
                : 'text-[var(--color-primary-emphasis)] hover:bg-[var(--color-surface-2)]'
            }`}
            title="المساعد الذكي"
          >
            <Sparkles className="w-4 h-4" />
            <span className="hidden sm:inline">المساعد الذكي</span>
          </button>
          
          {/* شريط الإجراءات السريعة */}
          <GlobalActionBar user={user} onNavigate={onNavigate} />
        </div>
        <div className="flex items-center gap-3 ms-auto">
          {/* العناصر المنقولة من الشريط السفلي */}
          <div className="hidden xl:flex items-center gap-2 text-xs text-[var(--color-text-muted)] border-e border-[var(--color-border)] pe-3 me-1">
            <UserIcon className="w-3.5 h-3.5" />
            <span className="font-semibold text-[var(--color-text)]">{user.name}</span>
            <span className="text-[var(--color-border)]">|</span>
            <span>الدور: {user.role === 'manager' ? 'مدير' : user.role === 'procurement' ? 'مشتريات' : 'موظف'}</span>
            <span className="text-[var(--color-border)]">|</span>
            <Calendar className="w-3.5 h-3.5" />
            <span>{formatDateValue(new Date())}</span>
            <span className="text-[var(--color-border)]">|</span>
            <span>السنة المالية {new Date().getFullYear()}</span>
          </div>

          <GlobalSearch userRole={user.role} onNavigate={onNavigate} />
          {/* ما الجديد — لوحة تشرح آخر التحديثات */}
          <WhatsNewButton />
          <button
            type="button"
            onClick={openPlatformNotes}
            className="flex items-center justify-center rounded-md p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
            title="ملاحظة / تذكير على الصفحة الحالية"
            aria-label="ملاحظة أو تذكير على الصفحة الحالية"
          >
            <NotebookPen className="h-4 w-4" />
          </button>
          {/* إشعارات الموقع (الجرس) — تذكيرات الزبائن/الشحنات */}
          <NotificationCenter currentUserId={user.id} onNavigate={onNavigate} />
          {/* ثوابت المجموعة — زر مرئي بديل للمفتاح F11 */}
          {onOpenGroupConstants && (
            <button
              type="button"
              onClick={onOpenGroupConstants}
              className="p-1.5 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)] transition-colors flex items-center justify-center"
              title="ثوابت المجموعة (F11)"
              aria-label="ثوابت المجموعة"
            >
              <SlidersHorizontal className="w-4 h-4" />
            </button>
          )}
          {/* task16 E15: حاسبة بأيقونة — تفتح عند الطلب فقط */}
          <AseelCalculatorButton />
          <DensitySwitch value={density} onChange={setDensity} />
          <PriceVisibilityToggle />
          <ThemeToggle />
          <button
            onClick={() => window.open(window.location.href, '_blank')}
            className="p-1.5 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)] transition-colors flex items-center justify-center"
            title="فتح في علامة تبويب جديدة (تكرار الصفحة)"
            aria-label="تكرار الصفحة"
          >
            <Copy className="w-4 h-4" />
          </button>
          <div className="w-px h-4 bg-[var(--color-border)] mx-1"></div>
          <button
            onClick={() => {
              if (window.confirm('هل تريد تأكيد تسجيل الخروج؟')) {
                logout();
              }
            }}
            className="p-1.5 rounded-md text-[var(--color-danger)] hover:bg-[color-mix(in_srgb,var(--color-danger)_10%,transparent)] transition-colors flex items-center justify-center"
            title="تسجيل الخروج"
            aria-label="تسجيل الخروج"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="app-workspace flex flex-1 min-h-0 overflow-hidden">
        <Sidebar user={user} activeView={activeView} setView={onNavigate} />

        <div className="app-main flex flex-col flex-1 min-w-0">
          {/* شريط التنقل السريع */}
          <div className="aseel-toolbar relative flex-shrink-0 overflow-hidden">
            <div
              className="pointer-events-none absolute inset-0 bg-gradient-to-l from-sky-100/90 via-blue-50/90 to-cyan-100/80 dark:from-slate-900 dark:via-blue-950/80 dark:to-cyan-950/70"
              aria-hidden="true"
            />
            <div className="aseel-toolgrp relative z-10">
              <Breadcrumb activeView={activeView} />
            </div>
            {/* task16 D14: اختصارات الوصول السريع القابلة للتهيئة */}
            {shortcuts.filter(v => v !== 'dashboard' && v !== activeView).length > 0 && (
              <div className="aseel-toolgrp relative z-10 flex items-center gap-1.5 py-1 ms-4" title="اختصارات سريعة (تُهيّأ من الإعدادات)">
                {shortcuts.filter(v => v !== 'dashboard' && v !== activeView).map((v) => {
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
          </div>
          <main className="app-content overflow-auto flex-1">
            {children}
          </main>
        </div>
      </div>

      {/* مرشد رحلة الاستيراد — يرافق المستخدم في كل الشاشات حتى الفاتورة الدولية */}
      <ImportJourneyGuide />

      {/* قائمة زر الفأرة اليمنى العامّة — تعمل في كامل الموقع (تُستثنى الحقول والقوائم الموضعية) */}
      <GlobalContextMenu user={user} onNavigate={onNavigate} />
      {notesTarget && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-3"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setNotesTarget(null);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="platform-notes-title"
            className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl"
          >
            <header className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
              <div>
                <h2 id="platform-notes-title" className="text-sm font-bold">ملاحظات وتذكيرات الصفحة</h2>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{notesTarget.target_label}</p>
              </div>
              <button
                type="button"
                autoFocus
                className="aseel-toolbtn"
                onClick={() => setNotesTarget(null)}
                aria-label="إغلاق ملاحظات الصفحة"
              >
                إغلاق
              </button>
            </header>
            <div className="overflow-y-auto">
              <CustomerNotesTab target={notesTarget} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
};
