import { apiGetObject, apiPostObject } from './restApi';

const ROOT = 'platform/ops/presence/';

export interface PresenceHeartbeat {
  recorded: boolean;
  reason?: string;
  date?: string;
  active_seconds?: number;
  active_hours?: number;
}

export interface PresenceDay {
  date: string;
  hours: number;
}

export interface PresenceLog {
  employee_id: number;
  period_year: number;
  period_month: number;
  today: { date: string; active_seconds: number; active_hours: number };
  is_applicable: boolean;
  factor: number;
  days_counted: number;
  total_hours: number;
  min_hours_per_day: number;
  day_cap_percent: number;
  days: PresenceDay[];
  score_before?: number | null;
  score_after?: number | null;
}

/** نبضةُ حضور — بلا معامِلٍ إطلاقاً: الخادمُ يشتقّ الموظّفَ من الجلسة. */
export const sendPresenceHeartbeat = () =>
  apiPostObject<PresenceHeartbeat>(`${ROOT}heartbeat/`, {});

export const getPresenceLog = (params: { employee?: number; year?: number; month?: number } = {}) =>
  apiGetObject<PresenceLog>(`${ROOT}log/`, {
    query: { employee: params.employee, year: params.year, month: params.month },
  });
