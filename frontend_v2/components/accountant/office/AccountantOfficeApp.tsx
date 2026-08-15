import React, { useCallback, useEffect, useState } from 'react';
import { Briefcase, CalendarClock, LayoutDashboard, LogOut, Scale, Settings, ShieldCheck, Users } from 'lucide-react';

import type { User } from '../../../types';
import { AccountantProfilePage } from '../AccountantProfilePage';
import { EngagementRevokedGuard } from '../EngagementRevokedGuard';
import { OfficeAgendaPage } from './OfficeAgendaPage';
import { OfficeClientFilePage } from './OfficeClientFilePage';
import { OfficeClientsPage } from './OfficeClientsPage';
import { OfficeDashboardPage } from './OfficeDashboardPage';
import { OfficeExternalClientPage } from './OfficeExternalClientPage';
import { OfficeSettingsPage } from './OfficeSettingsPage';

type OfficeView = 'dashboard' | 'clients' | 'client' | 'practice' | 'agenda' | 'settings' | 'profile';

const NAV: { key: OfficeView; label: string; icon: React.ReactNode }[] = [
  { key: 'dashboard', label: 'لوحة المكتب', icon: <LayoutDashboard className="h-5 w-5" /> },
  { key: 'clients', label: 'زبائني', icon: <Users className="h-5 w-5" /> },
  { key: 'agenda', label: 'المواعيد والمهام', icon: <CalendarClock className="h-5 w-5" /> },
  { key: 'settings', label: 'إعدادات المكتب', icon: <Settings className="h-5 w-5" /> },
  { key: 'profile', label: 'ملفي المهني', icon: <ShieldCheck className="h-5 w-5" /> },
];

const TITLES: Record<OfficeView, string> = {
  dashboard: 'لوحة المكتب',
  clients: 'زبائن المكتب',
  client: 'ملف زبون',
  practice: 'ملف زبون المكتب',
  agenda: 'المواعيد والمهام',
  settings: 'إعدادات المكتب',
  profile: 'ملفي المهني',
};

/** القسم الذي يُضاء في القائمة حين تكون الشاشة صفحةً فرعية منه. */
const NAV_PARENT: Partial<Record<OfficeView, OfficeView>> = {
  client: 'clients',
  practice: 'clients',
};

const CLIENT_PATH = /^\/office\/clients\/(\d+)/;
const PRACTICE_PATH = /^\/office\/practice\/(\d+)/;

/**
 * قشرة مكتب المحاسبة القانونية — **واجهة مستقلة تماماً** عن النظام التجاري:
 * قائمتها وهيدرها وصفحاتها خاصة بها، ولا يظهر فيها أي عنصر تشغيلي (مخزون،
 * فواتير جديدة، نقاط بيع…). المكتب يقرأ دفاتر زبائنه ويحلّلها، ويكتب سجلّه هو
 * (زبائنه وبرامجه ومواعيده) — وهذان بابان لا باب واحد.
 */
export const AccountantOfficeApp: React.FC<{
  user: User;
  onLogout: () => void;
  onExitToPlatform?: () => void;
}> = ({ user, onLogout, onExitToPlatform }) => {
  const [view, setView] = useState<OfficeView>('dashboard');
  const [client, setClient] = useState<{ tenantId: number; name: string } | null>(null);
  const [practiceClientId, setPracticeClientId] = useState<number | null>(null);

  const syncPath = useCallback((next: OfficeView, opened?: { tenantId?: number; practiceId?: number }) => {
    const path = next === 'client' && opened?.tenantId
      ? `/office/clients/${opened.tenantId}`
      : next === 'practice' && opened?.practiceId
        ? `/office/practice/${opened.practiceId}`
        : next === 'dashboard' ? '/office' : `/office/${next}`;
    if (window.location.pathname !== path) window.history.pushState({}, '', path);
  }, []);

  useEffect(() => {
    const restore = () => {
      const path = window.location.pathname;
      const clientMatch = CLIENT_PATH.exec(path);
      if (clientMatch) {
        const tenantId = Number(clientMatch[1]);
        setClient((current) => current?.tenantId === tenantId ? current : { tenantId, name: '' });
        setView('client');
        return;
      }
      const practiceMatch = PRACTICE_PATH.exec(path);
      if (practiceMatch) {
        setPracticeClientId(Number(practiceMatch[1]));
        setView('practice');
        return;
      }
      setView(
        path.startsWith('/office/profile') ? 'profile'
          : path.startsWith('/office/agenda') ? 'agenda'
            : path.startsWith('/office/settings') ? 'settings'
              : path.startsWith('/office/clients') ? 'clients' : 'dashboard',
      );
    };
    restore();
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);

  /** فتح دفاتر شركة على المنصة — الشركة المختارة تُثبَّت لنداءات ملف الزبون. */
  const openClient = (row: { tenant_id: number; company_name: string }) => {
    const opened = { tenantId: row.tenant_id, name: row.company_name };
    localStorage.setItem('tenantId', String(row.tenant_id));
    localStorage.removeItem('branchId');
    setClient(opened);
    setView('client');
    syncPath('client', { tenantId: row.tenant_id });
  };

  /** فتح ملف زبون المكتب — سجلٌّ هوياتي لا شركة، فلا يُلمَس `tenantId` هنا. */
  const openPracticeClient = (clientId: number) => {
    setPracticeClientId(clientId);
    setView('practice');
    syncPath('practice', { practiceId: clientId });
  };

  const go = (next: OfficeView) => {
    setView(next);
    syncPath(next);
  };

  const backToClients = () => { setClient(null); setPracticeClientId(null); go('clients'); };

  const activeNav = (key: OfficeView) => view === key || NAV_PARENT[view] === key;

  return (
    <div dir="rtl" className="min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 flex-col justify-between bg-slate-900 p-5 text-slate-100 lg:flex">
          <div>
            <div className="flex items-center gap-3 border-b border-slate-800 pb-5">
              <span className="rounded-xl bg-indigo-600 p-2"><Scale className="h-6 w-6" /></span>
              <div>
                <p className="text-sm font-black">مكتب المحاسبة القانونية</p>
                <p className="text-xs text-slate-400">{user.name}</p>
              </div>
            </div>
            <nav className="mt-5 space-y-1" aria-label="أقسام المكتب">
              {NAV.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => go(item.key)}
                  aria-current={view === item.key}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-right font-bold transition ${
                    activeNav(item.key) ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  {item.icon}
                  <span className="flex-1">{item.label}</span>
                </button>
              ))}
            </nav>
          </div>
          <div className="space-y-2 border-t border-slate-800 pt-4">
            {onExitToPlatform && (
              <button type="button" onClick={() => onExitToPlatform()} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-right text-sm font-bold text-amber-300 hover:bg-slate-800">
                <Briefcase className="h-4 w-4" /> العودة للوحة المنصة
              </button>
            )}
            <button type="button" onClick={onLogout} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-right text-sm font-bold text-slate-300 hover:bg-slate-800">
              <LogOut className="h-4 w-4" /> تسجيل الخروج
            </button>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900">
            <div>
              <h1 className="text-lg font-black">{TITLES[view]}</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                واجهة المحاسب القانوني — مستقلة عن أنظمة الشركات التجارية
              </p>
            </div>
            <nav className="flex flex-wrap gap-2 lg:hidden" aria-label="تنقّل المكتب">
              {NAV.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => go(item.key)}
                  className={`rounded-lg px-3 py-2 text-sm font-bold ${
                    activeNav(item.key) ? 'bg-indigo-700 text-white' : 'border border-slate-300 dark:border-slate-700'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>
          </header>

          <main className="min-w-0 flex-1 p-4 sm:p-6">
            {view === 'dashboard' && (
              <OfficeDashboardPage
                onOpenClient={openClient}
                onGoToClients={() => go('clients')}
                onGoToAgenda={() => go('agenda')}
                onOpenPracticeClient={openPracticeClient}
              />
            )}
            {view === 'clients' && (
              <OfficeClientsPage onOpenClient={openClient} onOpenPracticeClient={openPracticeClient} />
            )}
            {view === 'client' && client && (
              <OfficeClientFilePage
                tenantId={client.tenantId}
                companyName={client.name || 'ملف الزبون'}
                onBack={backToClients}
              />
            )}
            {view === 'practice' && practiceClientId !== null && (
              <OfficeExternalClientPage
                clientId={practiceClientId}
                onBack={backToClients}
                onOpenPlatformFile={openClient}
              />
            )}
            {view === 'agenda' && (
              <OfficeAgendaPage
                onOpenPlatformClient={openClient}
                onOpenPracticeClient={openPracticeClient}
              />
            )}
            {view === 'settings' && <OfficeSettingsPage />}
            {view === 'profile' && <AccountantProfilePage />}
          </main>

          {/* إلغاء الشركة لارتباطنا أثناء العمل ⇒ حوار مانع وعودة لقائمة الزبائن */}
          <EngagementRevokedGuard onReturn={() => { setClient(null); go('dashboard'); }} />
        </div>
      </div>
    </div>
  );
};

export default AccountantOfficeApp;
