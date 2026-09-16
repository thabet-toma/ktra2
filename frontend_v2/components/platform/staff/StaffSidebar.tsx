import React from 'react';
import { ChevronRight, LogOut, Menu, ShieldCheck } from 'lucide-react';

import type { MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
import { staffNav, type StaffNavKey } from '../../../utils/staffNav';
import { CcAvatar, CcCard } from '../ui';

interface StaffSidebarProps {
  activeKey: StaffNavKey;
  collapsed: boolean;
  drawerOpen: boolean;
  profile: MyPlatformEmployeeProfile | null;
  onNavigate: (key: StaffNavKey) => void;
  onToggleCollapsed: () => void;
  onCloseDrawer: () => void;
}

export const StaffSidebar: React.FC<StaffSidebarProps> = ({
  activeKey,
  collapsed,
  drawerOpen,
  profile,
  onNavigate,
  onToggleCollapsed,
  onCloseDrawer,
}: StaffSidebarProps) => {
  const name = profile?.username || 'موظف كترا';
  const title = profile?.job_title || 'فريق العمليات';
  const sidebarWidth = collapsed ? 'lg:w-16' : 'lg:w-60';

  const nav = (
    <>
      <div className={`flex h-20 items-center border-b border-cc-border px-3 ${collapsed ? 'justify-center' : 'gap-3'}`}>
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-l from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/20">
          <ShieldCheck className="h-5 w-5" />
        </span>
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-base font-extrabold text-cc-text">كترا</p>
            <p className="text-xs text-cc-text-muted">فريق العمليات</p>
          </div>
        )}
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="mr-auto hidden rounded-lg p-2 text-cc-text-muted hover:bg-white/5 hover:text-sky-300 lg:inline-flex"
          aria-label="طي الشريط الجانبي"
        >
          <ChevronRight className={`h-4 w-4 transition ${collapsed ? 'rotate-180' : ''}`} />
        </button>
        <button
          type="button"
          onClick={onCloseDrawer}
          className="mr-auto rounded-lg p-2 text-cc-text-muted hover:bg-white/5 hover:text-sky-300 lg:hidden"
          aria-label="إغلاق القائمة"
        >
          <Menu className="h-4 w-4" />
        </button>
      </div>

      <nav className="flex-1 space-y-1 p-3" aria-label="تنقل موظف كترا">
        {staffNav.map((item) => {
          const Icon = item.icon;
          const active = activeKey === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onNavigate(item.key)}
              title={collapsed ? item.label : undefined}
              aria-current={active ? 'page' : undefined}
              className={`group flex h-11 w-full items-center rounded-xl px-3 text-right text-sm font-bold transition-all duration-150 ${
                collapsed ? 'justify-center' : 'gap-3'
              } ${
                active
                  ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30 shadow-sm'
                  : 'text-cc-text-muted hover:bg-white/5 hover:text-cc-text border border-transparent'
              }`}
            >
              <Icon className={`h-5 w-5 shrink-0 transition-colors ${active ? 'text-sky-400' : 'text-cc-text-muted group-hover:text-cc-text'}`} />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      <div className={`m-3 ${collapsed ? 'hidden' : ''}`}>
        <CcCard className="p-3">
          <div className="flex items-center gap-2.5">
            <CcAvatar name={name} photoUrl={profile?.photo_url} size="md" presence="online" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-cc-text">{name}</p>
              <p className="truncate text-xs text-cc-text-muted">{title}</p>
            </div>
          </div>
          <p className="mt-2.5 flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            متصل الآن
          </p>
          {/* مخرجٌ إلى نظام الشركة — **وليس تزييناً.**

              صار زرُّ الشريط الجانبيّ في التطبيق ينتقل إلى `/staff` انتقالاً كاملاً
              (212-I)، وهذه القشرةُ لا تحمل شريطَ التطبيق ولا يجوز أن تحمله
              (`test_the_staff_shell_never_imports_the_company_sidebar`). فبلا هذا
              الزرّ تكون ضغطةٌ واحدةٌ **بلا رجعة**: الموظّفُ الذي له عضويّةٌ في شركةٍ
              أيضاً يخرج من نظامها ولا طريقَ يعيده إلّا كتابةُ العنوان بيده — وهي
              الحالةُ التي تمنعها بوّابةُ الجودة الرابعة: «لا حالةَ يُوصَل إليها ولا
              يستطيع المستخدمُ الرجوعَ منها».

              والانتقالُ كاملٌ لا `navigate`: الوجهةُ خارجُ موجّهِ هذه القشرة. */}
          <button
            type="button"
            onClick={() => { window.location.assign('/'); }}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-cc-border px-3 py-2 text-xs font-bold text-cc-text-muted transition hover:bg-white/5 hover:text-sky-300"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            نظام الشركة
          </button>
        </CcCard>
      </div>
    </>
  );

  return (
    <>
      <aside className={`hidden shrink-0 flex-col border-l border-cc-border bg-[var(--staff-rail)] transition-[width] lg:flex ${sidebarWidth}`}>
        {nav}
      </aside>
      {drawerOpen && (
        <>
          <button type="button" onClick={onCloseDrawer} className="fixed inset-0 z-40 bg-slate-950/60 lg:hidden" aria-label="إغلاق القائمة" />
          <aside className="fixed inset-y-0 right-0 z-50 flex w-60 flex-col border-l border-cc-border bg-[var(--staff-rail)] shadow-xl shadow-black/40 lg:hidden">
            {nav}
          </aside>
        </>
      )}
    </>
  );
};

export default StaffSidebar;
