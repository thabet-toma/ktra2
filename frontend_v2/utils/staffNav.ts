import type { LucideIcon } from 'lucide-react';
import { Building2, CalendarDays, ChartNoAxesCombined, ClipboardList, House, UserRound } from 'lucide-react';

export type StaffNavKey = 'home' | 'tasks' | 'companies' | 'meetings' | 'performance' | 'profile';

export interface StaffNavItem {
  key: StaffNavKey;
  path: string;
  label: string;
  icon: LucideIcon;
}

export const staffNav: readonly StaffNavItem[] = [
  { key: 'home', path: '/staff/home', label: 'الرئيسية', icon: House },
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
