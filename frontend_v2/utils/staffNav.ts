import type { LucideIcon } from 'lucide-react';
import { Building2, CalendarDays, ChartNoAxesCombined, ClipboardList, House, UsersRound, UserRound } from 'lucide-react';

export type StaffNavKey = 'home' | 'tasks' | 'companies' | 'meetings' | 'performance' | 'profile' | 'crm';

export interface StaffNavItem {
  key: StaffNavKey;
  path: string;
  label: string;
  icon: LucideIcon;
}

export const staffNav: readonly StaffNavItem[] = [
  { key: 'home', path: '/staff/home', label: 'الرئيسية', icon: House },
  // «العملاء» ثانياً كما في نموذج المالك البصريّ (لوحة التحكم ثمّ العملاء) — لا
  // آخرَ القائمة: هذا هو عملُ المسوّق اليوميّ، وموضعُه في الشريط يقول ذلك.
  { key: 'crm', path: '/staff/crm', label: 'العملاء', icon: UsersRound },
  { key: 'tasks', path: '/staff/tasks', label: 'مهامي', icon: ClipboardList },
  { key: 'companies', path: '/staff/companies', label: 'شركاتي', icon: Building2 },
  { key: 'meetings', path: '/staff/meetings', label: 'اجتماعاتي', icon: CalendarDays },
  { key: 'performance', path: '/staff/performance', label: 'أدائي', icon: ChartNoAxesCombined },
  { key: 'profile', path: '/staff/profile', label: 'ملفي الشخصي', icon: UserRound },
];

export function staffRouteForKey(key: StaffNavKey): string {
  return staffNav.find((item) => item.key === key)?.path ?? '/staff/home';
}

export function staffRouteForPath(pathname: string): string {
  return staffNav.find((item) => item.path === pathname)?.path ?? '/staff/home';
}
