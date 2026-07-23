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
import { NotificationCenter } from '../notifications/NotificationCenter';
import { WhatsNewButton } from './WhatsNewButton';
import {
  User as UserIcon,
  Calendar,
  Zap,
  Sparkles,
  LogOut,
  Copy,
  SlidersHorizontal,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import {
  getQuickShortcuts,
  labelForShortcut,
  QUICK_SHORTCUTS_EVENT,
} from '../../utils/quickShortcuts';

interface AppLayoutProps {
  user: User;
  activeView: AppView;
  onNavigate: (view: AppView, targetId?: string) => void;
  children: React.ReactNode;
  /** N0-T5: callback لفتح صفحة ثوابت المجموعة (F11). */
  onOpenGroupConstants?: () => void;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  user,
  activeView,
  onNavigate,
  children,
  onOpenGroupConstants,
}) => {
  const { logout } = useAuth();
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');
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
            <span>{new Date().toLocaleDateString('ar-EG')}</span>
            <span className="text-[var(--color-border)]">|</span>
            <span>السنة المالية {new Date().getFullYear()}</span>
          </div>

          <GlobalSearch userRole={user.role} onNavigate={onNavigate} />
          {/* ما الجديد — لوحة تشرح آخر التحديثات */}
          <WhatsNewButton />
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
          <div className="aseel-toolbar flex-shrink-0">
            <div className="aseel-toolgrp">
              <Breadcrumb activeView={activeView} />
            </div>
            {/* task16 D14: اختصارات الوصول السريع القابلة للتهيئة */}
            {shortcuts.filter(v => v !== 'dashboard' && v !== activeView).length > 0 && (
              <div className="aseel-toolgrp flex items-center gap-1 ms-4" title="اختصارات سريعة (تُهيّأ من الإعدادات)">
                <Zap className="w-3.5 h-3.5 text-[var(--color-primary-emphasis)]" />
                {shortcuts.filter(v => v !== 'dashboard' && v !== activeView).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => onNavigate(v)}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      activeView === v
                        ? 'bg-[var(--color-primary)] text-white'
                        : 'text-[var(--color-text)] hover:bg-[var(--color-surface-2)]'
                    }`}
                  >
                    {labelForShortcut(v)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <main className="app-content overflow-auto flex-1">
            {children}
          </main>
        </div>
      </div>

    </div>
  );
};
