import type { AccountantEngagement, EngagementStatus } from '../types/accountant';

export const ENGAGEMENT_STATUS_LABELS: Record<EngagementStatus, string> = {
  pending: 'قيد الانتظار',
  active: 'نشط',
  suspended: 'معلّق',
  revoked: 'ملغى',
  declined: 'مرفوض',
  expired: 'منتهي',
};

export const ENGAGEMENT_STATUS_TONES: Record<EngagementStatus, string> = {
  pending: 'bg-amber-100 text-amber-800',
  active: 'bg-emerald-100 text-emerald-800',
  suspended: 'bg-orange-100 text-orange-800',
  revoked: 'bg-slate-200 text-slate-700',
  declined: 'bg-red-100 text-red-800',
  expired: 'bg-red-100 text-red-800',
};

export const invitationExpired = (
  value: Pick<AccountantEngagement, 'invitation_expires_at'>,
  now = Date.now(),
): boolean => !!value.invitation_expires_at && Date.parse(value.invitation_expires_at) <= now;

export const accountantEngagementActions = (
  value: Pick<AccountantEngagement, 'status' | 'initiated_by'>,
): string[] => {
  if (value.status === 'pending') {
    return value.initiated_by === 'accountant' ? ['withdraw'] : ['accept'];
  }
  return value.status === 'active' ? ['resign'] : [];
};

export const engagementErrorCode = (error: unknown): string => {
  const value = error as { data?: { code?: string }; code?: string };
  return value?.data?.code || value?.code || '';
};

export const normalizeScope = (scope: string[]): string[] =>
  [...new Set(scope.map((key) => key.trim()).filter(Boolean))].sort();

