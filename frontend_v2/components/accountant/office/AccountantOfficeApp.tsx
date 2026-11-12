import React, { useCallback, useEffect, useState } from 'react';
import { Briefcase, CreditCard, LogOut, Scale, ShieldCheck, Users } from 'lucide-react';

import type { User } from '../../../types';
import { AccountantProfilePage } from '../AccountantProfilePage';
import { EngagementRevokedGuard } from '../EngagementRevokedGuard';
import { PlanLimitReachedGuard } from '../../PlanLimitReachedGuard';
import { OfficeClientFilePage } from './OfficeClientFilePage';
import { OfficeClientsPage } from './OfficeClientsPage';

type OfficeView = 'companies' | 'client' | 'profile';

/**
 * وجهةُ «خطّتي» من قشرة المكتب — المسارُ العامّ المستقلّ `/pricing`.
 *
 * **لماذا لا `/settings#my-plan`** (وجهةُ الحارس في التطبيق الرئيس): `App.tsx`
 * تُرجع هذه القشرة **باكراً** لحساب المحاسب على كل مسارٍ داخليّ، فـ`/settings`
 * لا تُصيَّر له إطلاقاً والمرساةُ لا تصل. و**لماذا لا `pushState`**: القشرةُ
 * تقرأ المسارَ على `popstate` وحدَه، و`pushState` لا يُطلق حدثاً فلا يتغيّر
 * المعروض — يتغيّر العنوانُ وحدَه. و`/pricing` مسارٌ مسجَّلٌ في `index.tsx`
 * **خارج** شجرة المصادقة، فيُصيَّر لأيّ زائرٍ ولحساب المكتب كما يُصيَّر للزوّار؛
 * وانتقالٌ كاملٌ إليه هو نفسُ نمط «العودة للوحة المنصة» في هذه القشرة.
 */
const PRICING_PATH = '/pricing';

/** الخروجُ من القشرة إلى مسارٍ مسجَّلٍ خارجها — انتقالٌ كامل، لا `pushState`. */
const openPricing = () => { window.location.assign(PRICING_PATH); };

const NAV: { key: OfficeView; label: string; icon: React.ReactNode }[] = [
  { key: 'companies', label: 'شركاتي المرتبطة', icon: <Users className="h-5 w-5" /> },
  { key: 'profile', label: 'ملفي المهني', icon: <ShieldCheck className="h-5 w-5" /> },
];

const TITLES: Record<OfficeView, string> = {
  companies: 'شركاتي المرتبطة',
  client: 'ملف الزبون',
  profile: 'ملفي المهني',
};

/** القسم الذي يُضاء في القائمة حين تكون الشاشة صفحةً فرعية منه. */
const NAV_PARENT: Partial<Record<OfficeView, OfficeView>> = {
  client: 'companies',
};

const CLIENT_PATH = /^\/office\/clients\/(\d+)/;

/**
 * قشرة بوابة المحاسب — **واجهة مستقلة تماماً** عن النظام التجاري: قائمتها
 * وهيدرها وصفحاتها خاصة بها، ولا يظهر فيها أي عنصر تشغيلي (مخزون، فواتير جديدة،
 * نقاط بيع…).
 *
 * #291: قُلّمت على بابين وشاشةٍ فرعية — «شركاتي المرتبطة» و«ملفي المهني» وملفّ
 * الزبون المالي الذي يُفتح من القائمة. لوحةُ المكتب والأجندة والبرامج والمهام
 * وإعدادات المكتب وسجلّ الزبائن الخارجي كلها حُذفت مع الطبقة القديمة.
 *
 * وفي رأسها بابُ «خطّتي»: يخرج من القشرة إلى `/pricing` المسجَّل خارجها، ونفسُ
 * الوجهة يعطيها حارسُ حدّ الخطّة بزرِّه «عرض خطّتي» (211-P).
 */
export const AccountantOfficeApp: React.FC<{
  user: User;
  onLogout: () => void;
  onExitToPlatform?: () => void;
}> = ({ user, onLogout, onExitToPlatform }) => {
  const [view, setView] = useState<OfficeView>('companies');
  const [client, setClient] = useState<{ tenantId: number; name: string } | null>(null);

  const syncPath = useCallback((next: OfficeView, opened?: { tenantId?: number }) => {
    const path = next === 'client' && opened?.tenantId
      ? `/office/clients/${opened.tenantId}`
      : next === 'companies' ? '/office' : `/office/${next}`;
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
      setView(path.startsWith('/office/profile') ? 'profile' : 'companies');
    };
    restore();
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);

  /** فتح ملف زبون — الشركة المختارة تُثبَّت لنداءات ملف الزبون. */
  const openClient = (row: { tenant_id: number; company_name: string }) => {
    const opened = { tenantId: row.tenant_id, name: row.company_name };
    localStorage.setItem('tenantId', String(row.tenant_id));
    localStorage.removeItem('branchId');
    setClient(opened);
    setView('client');
    syncPath('client', { tenantId: row.tenant_id });
  };

  const go = (next: OfficeView) => {
    setClient(null);
    setView(next);
    syncPath(next);
  };

  const backToClients = () => { setClient(null); go('companies'); };

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
            <button
              type="button"
              onClick={openPricing}
              className="inline-flex items-center gap-2 rounded-xl border border-indigo-300 px-4 py-2 text-sm font-black text-indigo-700 transition hover:bg-indigo-50 dark:border-indigo-700 dark:text-indigo-300 dark:hover:bg-slate-800"
            >
              <CreditCard className="h-4 w-4" /> خطّتي
            </button>
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
            {view === 'companies' && <OfficeClientsPage onOpenClient={openClient} />}
            {view === 'client' && client && (
              <OfficeClientFilePage
                tenantId={client.tenantId}
                companyName={client.name || 'ملف الزبون'}
                onBack={backToClients}
              />
            )}
            {view === 'profile' && <AccountantProfilePage />}
          </main>

          {/* إلغاء الشركة لارتباطنا أثناء العمل ⇒ حوار مانع وعودة لقائمة الشركات */}
          <EngagementRevokedGuard onReturn={() => { setClient(null); go('companies'); }} />

          {/* 211-P: بلوغُ حدّ الخطّة ⇒ حوارٌ مانعٌ بوجهةٍ تعمل في هذه القشرة
              (`/pricing` عبر `onViewPlan`)، لا حوارٍ يقود إلى `/settings#my-plan`
              التي لا تُصيَّر لهذا الحساب أصلاً. */}
          <PlanLimitReachedGuard onViewPlan={openPricing} />
        </div>
      </div>
    </div>
  );
};

export default AccountantOfficeApp;
