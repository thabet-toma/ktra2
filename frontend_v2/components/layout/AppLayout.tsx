import React, { useState } from 'react';
import { Sidebar } from '../Sidebar';
import { User, AppView } from '../../types';
import {
  Breadcrumb,
  BreadcrumbItem,
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

interface AppLayoutProps {
  user: User;
  activeView: AppView;
  onNavigate: (view: AppView, targetId?: string) => void;
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  user,
  activeView,
  onNavigate,
  children,
}) => {
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-surface)]" data-density={density}>
      <Sidebar user={user} activeView={activeView} setView={onNavigate} />

      <div className="flex flex-col flex-1 min-w-0">
        <header className="app-header flex items-center gap-3 px-4">
          <Breadcrumb activeView={activeView} />
          <div className="ms-auto flex items-center gap-2">
            <GlobalSearch userRole={user.role} onNavigate={onNavigate} />
            <DensitySwitch value={density} onChange={setDensity} />
            <ThemeToggle />
          </div>
        </header>

        <main className="app-content overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
};