import React, { useEffect, useState } from 'react';
import { Menu, Search } from 'lucide-react';

import type { MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
import { sendPresenceHeartbeat } from '../../../services/platformPresenceApi';
import { formatPresenceClock } from '../../../utils/presenceClock';
import { PlatformNotificationBell } from '../PlatformNotificationBell';

interface StaffTopBarProps {
  profile: MyPlatformEmployeeProfile | null;
  searchTerm: string;
  onSearch: (term: string) => void;
  onOpenDrawer: () => void;
}

/**
 * عدّادُ حضورِ اليوم — **من دفتر الخادم لا من ساعة المتصفّح** (#212 212-D).
 *
 * قبل هذه التذكرة كان العدّادُ يقيس «هذه الجلسة» من `sessionStorage`: يصفَّر
 * بإعادة التحميل، ويختلف بين لسانين، ولا يعرفه التقييمُ ولا يراه المدير. وقرارُ
 * المالك أنّ المطلوبَ «توتال الوقت الي قعدو عالمنصة» باليوم وأنّه **يؤثّر على
 * التقييم** — وذلك لا يُبنى على رقمٍ يملكه المتصفّح.
 *
 * والنبضةُ تتوقّف حين يغيب اللسان (`visibilityState`): «قعد على المنصّة» حضورٌ
 * لا لسانٌ منسيٌّ مفتوحٌ طوالَ الليل. والخادمُ يجمع الفجواتَ المتقاربةَ وحدَها،
 * فالعودةُ بعد ساعاتٍ لا تُحتسَب حضوراً.
 */
export const StaffPresenceTimer: React.FC = () => {
  const [seconds, setSeconds] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const beat = async () => {
      // لسانٌ مخفيٌّ لا ينبض — ولا يُصفَّر العدّادُ المعروض، فالوقتُ المسجَّل باقٍ.
      if (document.visibilityState === 'hidden') return;
      try {
        const result = await sendPresenceHeartbeat();
        if (alive && result.recorded && typeof result.active_seconds === 'number') {
          setSeconds(result.active_seconds);
        }
      } catch {
        /* فشلُ نبضةٍ لا يُفرغ العدّاد: آخرُ قيمةٍ معروفةٍ أصدقُ من صفرٍ مُلفَّق. */
      }
    };
    void beat();
    const interval = window.setInterval(() => void beat(), 60000);
    return () => { alive = false; window.clearInterval(interval); };
  }, []);

  return <div className="hidden rounded-xl bg-white/5 px-3 py-1.5 text-center sm:block" title="مجموع وقتك على المنصة اليوم"><p className="text-[10px] font-semibold text-[var(--staff-muted)]">حضورك اليوم</p><p className="font-mono text-sm font-extrabold text-slate-50" dir="ltr">{seconds === null ? '--:--' : formatPresenceClock(seconds)}</p></div>;
};

export const StaffTopBar: React.FC<StaffTopBarProps> = ({ profile, searchTerm, onSearch, onOpenDrawer }) => {
  const [value, setValue] = useState(searchTerm);
  useEffect(() => setValue(searchTerm), [searchTerm]);
  const submit = (event: React.FormEvent) => { event.preventDefault(); onSearch(value.trim()); };
  return <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--staff-line)] bg-[var(--staff-rail)] px-4"><button type="button" onClick={onOpenDrawer} className="rounded-lg p-2 text-[var(--staff-muted)] hover:bg-white/5 hover:text-cyan-300 lg:hidden" aria-label="فتح القائمة"><Menu className="h-5 w-5" /></button><form onSubmit={submit} className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-[var(--staff-line)] bg-white/5 px-3"><Search className="h-4 w-4 shrink-0 text-[var(--staff-muted)]" /><input value={value} onChange={(event) => setValue(event.target.value)} className="h-9 min-w-0 flex-1 bg-transparent text-sm text-slate-50 outline-none placeholder:text-[var(--staff-muted)]" placeholder="ابحث في مهامك وشركاتك" aria-label="ابحث في أوامر العمل والشركات" /></form><PlatformNotificationBell /><StaffPresenceTimer /><div className="hidden min-w-0 text-right sm:block"><p className="truncate text-sm font-bold text-slate-50">{profile?.username || 'موظف كترا'}</p><p className="truncate text-xs text-[var(--staff-muted)]">{profile?.job_title || 'فريق العمليات'}</p></div><span className="mr-auto text-sm font-extrabold tracking-[0.16em] text-cyan-300" dir="ltr">KATRA</span></header>;
};

export default StaffTopBar;
