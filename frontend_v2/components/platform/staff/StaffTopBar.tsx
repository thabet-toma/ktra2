import React, { useEffect, useState } from 'react';
import { Menu, Search } from 'lucide-react';

import type { MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
import { formatNumber } from '../../../utils/formatNumber';
import { PlatformNotificationBell } from '../PlatformNotificationBell';

interface StaffTopBarProps {
  profile: MyPlatformEmployeeProfile | null;
  searchTerm: string;
  onSearch: (term: string) => void;
  onOpenDrawer: () => void;
}

// هذا عداد الجلسة الحالية، لا مجموع اليوم؛ مجموع اليوم يحتاج دفتراً خادمياً في التذكرة 212-D.
export const StaffSessionTimer: React.FC = () => {
  const [startedAt] = useState(() => {
    const key = 'ktra.staff.session.started-at';
    const now = Date.now();
    // التخزينُ قد يرمي لا يعيد `null` (نافذةٌ خاصّة · متصفّحٌ يحجب بيانات الموقع)،
    // والرميُ هنا داخلَ مُهيّئ `useState` يُسقط القشرةَ كلَّها لا العدّادَ وحدَه.
    try {
      const stored = Number(window.sessionStorage.getItem(key));
      if (Number.isFinite(stored) && stored > 0) return stored;
      window.sessionStorage.setItem(key, String(now));
    } catch {
      /* بلا تخزينٍ يبدأ العدّادُ من فتح هذه الشاشة — ولا يتعطّل شيء. */
    }
    return now;
  });
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 60000);
    return () => window.clearInterval(interval);
  }, []);

  const totalMinutes = Math.max(0, Math.floor((now - startedAt) / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const part = (value: number) => formatNumber(value, { maxDecimals: 0 }).padStart(2, '0');
  return <div className="hidden rounded-xl bg-white/5 px-3 py-1.5 text-center sm:block"><p className="text-[10px] font-semibold text-[var(--staff-muted)]">جلستك الحالية</p><p className="font-mono text-sm font-extrabold text-slate-50" dir="ltr">{part(hours)}:{part(minutes)}</p></div>;
};

export const StaffTopBar: React.FC<StaffTopBarProps> = ({ profile, searchTerm, onSearch, onOpenDrawer }) => {
  const [value, setValue] = useState(searchTerm);
  useEffect(() => setValue(searchTerm), [searchTerm]);
  const submit = (event: React.FormEvent) => { event.preventDefault(); onSearch(value.trim()); };
  return <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--staff-line)] bg-[var(--staff-rail)] px-4"><button type="button" onClick={onOpenDrawer} className="rounded-lg p-2 text-[var(--staff-muted)] hover:bg-white/5 hover:text-cyan-300 lg:hidden" aria-label="فتح القائمة"><Menu className="h-5 w-5" /></button><form onSubmit={submit} className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-[var(--staff-line)] bg-white/5 px-3"><Search className="h-4 w-4 shrink-0 text-[var(--staff-muted)]" /><input value={value} onChange={(event) => setValue(event.target.value)} className="h-9 min-w-0 flex-1 bg-transparent text-sm text-slate-50 outline-none placeholder:text-[var(--staff-muted)]" placeholder="ابحث في مهامك وشركاتك" aria-label="ابحث في أوامر العمل والشركات" /></form><PlatformNotificationBell /><StaffSessionTimer /><div className="hidden min-w-0 text-right sm:block"><p className="truncate text-sm font-bold text-slate-50">{profile?.username || 'موظف كترا'}</p><p className="truncate text-xs text-[var(--staff-muted)]">{profile?.job_title || 'فريق العمليات'}</p></div><span className="mr-auto text-sm font-extrabold tracking-[0.16em] text-cyan-300" dir="ltr">KATRA</span></header>;
};

export default StaffTopBar;
