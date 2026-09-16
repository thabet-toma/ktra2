import React, { useEffect, useState } from 'react';
import { Menu, Search } from 'lucide-react';

import { usePlatformPresenceHeartbeat } from '../../../hooks/usePlatformPresenceHeartbeat';
import type { MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
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
 *
 * والحلقةُ نفسُها في `hooks/usePlatformPresenceHeartbeat.ts` منذ 212-N1، لأنّ
 * قشرةَ الشركة تركّبها أيضاً: الموظّفُ يعمل هناك لا هنا.
 */
export const StaffPresenceTimer: React.FC = () => {
  // داخلَ القشرةِ لا شرط: `StaffShell` لا يصيّر شيئاً إلّا لمن يملك بابَ المنصّة.
  const seconds = usePlatformPresenceHeartbeat(true);

  return (
    <div
      className="hidden sm:flex items-center gap-2 rounded-full border border-cc-border bg-cc-surface-2/80 px-3 py-1 text-xs shadow-sm"
      title="مجموع وقتك على المنصة اليوم"
    >
      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
      <span className="text-[11px] font-semibold text-cc-text-muted">حضور اليوم:</span>
      <span className="font-mono text-xs font-black text-cc-text" dir="ltr">
        {seconds === null ? '--:--' : formatPresenceClock(seconds)}
      </span>
    </div>
  );
};

export const StaffTopBar: React.FC<StaffTopBarProps> = ({
  profile,
  searchTerm,
  onSearch,
  onOpenDrawer,
}: StaffTopBarProps) => {
  const [value, setValue] = useState(searchTerm);
  useEffect(() => setValue(searchTerm), [searchTerm]);
  const submit = (event: React.FormEvent) => { event.preventDefault(); onSearch(value.trim()); };

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-cc-border bg-[var(--staff-rail)] px-4">
      <button
        type="button"
        onClick={onOpenDrawer}
        className="rounded-lg p-2 text-cc-text-muted hover:bg-white/5 hover:text-sky-300 lg:hidden"
        aria-label="فتح القائمة"
      >
        <Menu className="h-5 w-5" />
      </button>

      <form
        onSubmit={submit}
        className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-cc-border bg-cc-surface-2/60 px-3 transition-colors focus-within:border-sky-500/50 focus-within:ring-1 focus-within:ring-sky-500/30"
      >
        <Search className="h-4 w-4 shrink-0 text-cc-text-muted" />
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="h-9 min-w-0 flex-1 bg-transparent text-sm text-cc-text outline-none placeholder:text-cc-text-muted"
          placeholder="ابحث في مهامك وشركاتك"
          aria-label="ابحث في أوامر العمل والشركات"
        />
      </form>

      <PlatformNotificationBell />
      <StaffPresenceTimer />

      <div className="hidden min-w-0 text-right sm:block">
        <p className="truncate text-sm font-bold text-cc-text">{profile?.username || 'موظف كترا'}</p>
        <p className="truncate text-xs text-cc-text-muted">{profile?.job_title || 'فريق العمليات'}</p>
      </div>

      <span className="mr-auto text-sm font-extrabold tracking-[0.16em] text-sky-400" dir="ltr">
        KATRA
      </span>
    </header>
  );
};

export default StaffTopBar;
