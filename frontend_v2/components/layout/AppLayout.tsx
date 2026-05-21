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
  User as UserIcon,
  Calendar,
} from 'lucide-react';
import { VIEW_LABELS } from './Breadcrumb';

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

  const currentViewLabel = VIEW_LABELS[activeView] || activeView;

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
      {/* M5-T1: شريط العنوان العلوي بنمط الأصيل
           اسم الشركة + السنة المالية يُؤخذان من بيانات المستخدم/التينانت إن وُجدت
           وإلا يظهر اسم عام مع السنة الحالية — بلا hard-code يكسر multi-tenant. */}
      <div className="aseel-titlebar flex-shrink-0">
        <div className="aseel-company">
          {(user as any).tenantName || 'K.T.R.A العالمية'}
          {' '}[ السنة المالية {new Date().getFullYear()} ]
        </div>
        <div className="aseel-title-grp">
          <span className="aseel-title-chip">{currentViewLabel}</span>
        </div>
        <div className="flex items-center gap-2 ms-auto">
          <GlobalSearch userRole={user.role} onNavigate={onNavigate} />
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
          </div>

          <main className="app-content overflow-auto flex-1">
            {children}
          </main>
        </div>
      </div>

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
        <div className="ms-auto aseel-status-item">
          <span className="text-green-600">● متصل</span>
        </div>
      </div>
    </div>
  );
};