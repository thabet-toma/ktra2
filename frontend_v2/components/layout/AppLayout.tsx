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
import {
  User as UserIcon,
  Calendar,
  Zap,
} from 'lucide-react';
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
    <div className="flex flex-col h-screen overflow-hidden bg-[var(--color-surface)]" data-density={density} data-skin="aseel">
      {/* task13 M6: حُذف chip العنوان (كان يكرر تسمية الشريط الجانبي والـ breadcrumb)
           ونُقلت «السنة المالية» إلى شريط الحالة السفلي بجانب المستخدم/الدور. */}
      <div className="aseel-titlebar flex-shrink-0">
        <div className="aseel-company flex items-center gap-3">
          <CompanySwitcher />
          <BranchSwitcher />
        </div>
        <div className="flex items-center gap-2 ms-auto">
          <GlobalSearch userRole={user.role} onNavigate={onNavigate} />
          {/* task16 E15: حاسبة بأيقونة — تفتح عند الطلب فقط */}
          <AseelCalculatorButton />
          <DensitySwitch value={density} onChange={setDensity} />
          <ThemeToggle />
        </div>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <Sidebar user={user} activeView={activeView} setView={onNavigate} />

        <div className="flex flex-col flex-1 min-w-0">
          {/* شريط التنقل السريع */}
          <div className="aseel-toolbar flex-shrink-0">
            <div className="aseel-toolgrp">
              <Breadcrumb activeView={activeView} />
            </div>
            {/* task16 D14: اختصارات الوصول السريع القابلة للتهيئة */}
            {shortcuts.length > 0 && (
              <div className="aseel-toolgrp ms-auto flex items-center gap-1" title="اختصارات سريعة (تُهيّأ من الإعدادات)">
                <Zap className="w-3.5 h-3.5 text-[var(--color-primary)]" />
                {shortcuts.map((v) => (
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

      {/* task18 DEF-A2: شريط الإجراءات العام الدائم (شريط الأدوات السفلي) */}
      <GlobalActionBar user={user} onNavigate={onNavigate} />

      {/* M5-T1: شريط الحالة السفلي بنمط الأصيل */}
      <div className="aseel-statusbar flex-shrink-0">
        <div className="aseel-status-item">
          <UserIcon className="w-3 h-3" />
          <span>{user.name}</span>
        </div>
        <div className="aseel-status-item">
          <span className="text-gray-400">|</span>
        </div>
        <div className="aseel-status-item">
          <span>الدور: {user.role === 'manager' ? 'مدير' : user.role === 'procurement' ? 'مشتريات' : 'موظف'}</span>
        </div>
        <div className="aseel-status-item">
          <span className="text-gray-400">|</span>
        </div>
        <div className="aseel-status-item">
          <Calendar className="w-3 h-3" />
          <span>{new Date().toLocaleDateString('ar-EG')}</span>
        </div>
        <div className="aseel-status-item">
          <span className="text-gray-400">|</span>
        </div>
        <div className="aseel-status-item">
          <span>السنة المالية {new Date().getFullYear()}</span>
        </div>
        <div className="ms-auto aseel-status-item">
          <span className="text-green-600">● متصل</span>
        </div>
      </div>
    </div>
  );
};