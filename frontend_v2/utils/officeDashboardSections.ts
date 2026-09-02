/**
 * ISSUE #58 — لوحة المكتب: ثلاثة عناصر لا رابع (قيد المالك).
 *
 * سجلّ الأقسام الثابت يحرس ألّا يُضاف قسمٌ رابع بصمت، ودالّة الملخّص هنا نقيّة
 * تشتقّ عدّادات كل قسم من حمولة الخادم (`accountant_portal.practice.practice_dashboard`)
 * بلا عرض — الشاشة تستهلكها ولا تُعيد حسابها.
 */

export const OFFICE_DASHBOARD_SECTIONS = ['clients', 'deadlines', 'unpaid_fees'] as const;

export type OfficeDashboardSection = (typeof OFFICE_DASHBOARD_SECTIONS)[number];

export type OfficeClientBookType = 'managed' | 'engaged' | 'hybrid' | 'unlinked';

export interface OfficeDashboardClientRow {
  id: number;
  trade_name: string;
  status: 'active' | 'archived';
  client_type: OfficeClientBookType;
  last_activity: string;
}

/** بند أجندة — نفس شكل `PracticeDeadlineItem` (`services/accountantPracticeApi.ts`)
 *  حرفياً؛ لا نستورده هنا كي لا تدور الوحدتان على بعضهما (الخدمة تستورد هذا
 *  الملف بالفعل لأجل `OfficeDashboardPayload`) — التوافق بنيويّ لا بالاسم. */
export interface OfficeDashboardDeadlineItem {
  kind: 'program' | 'appointment' | 'deadline' | 'filing';
  id: number | null;
  title: string;
  client_id: number | null;
  client_name: string;
  tenant_id: number | null;
  due_date: string;
  status: string;
  days_left: number;
  is_overdue: boolean;
}

export interface OfficeDashboardFeeInvoice {
  invoice_id: number;
  invoice_number: string;
  tenant_id: number;
  customer_id: number | null;
  customer_name: string;
  invoice_date: string;
  remaining: string;
}

export interface OfficeDashboardPayload {
  clients: OfficeDashboardClientRow[];
  deadlines: {
    items: OfficeDashboardDeadlineItem[];
    totals: { count: number; overdue: number; due_soon: number };
  };
  unpaid_fees: {
    invoices: OfficeDashboardFeeInvoice[];
    total: string;
  };
}

export interface OfficeDashboardSummary {
  clientsTotal: number;
  clientsByType: Record<OfficeClientBookType, number>;
  deadlinesOverdue: number;
  deadlinesDueSoon: number;
  unpaidFeesTotal: string;
  unpaidFeesCount: number;
}

/** تسمية حالة الدفتر بالعربية — مرآة `PracticeClient.client_type` (ISSUE #52). */
export const OFFICE_CLIENT_TYPE_LABELS: Record<OfficeClientBookType, string> = {
  managed: 'دفتر مُدار',
  engaged: 'مربوط بإذنه',
  hybrid: 'مُدار ومربوط',
  unlinked: 'خارجي',
};

export const OFFICE_CLIENT_TYPE_TONES: Record<OfficeClientBookType, string> = {
  managed: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200',
  engaged: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  hybrid: 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-200',
  unlinked: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
};

export function summarizeOfficeDashboard(payload: OfficeDashboardPayload): OfficeDashboardSummary {
  const clientsByType: Record<OfficeClientBookType, number> = {
    managed: 0, engaged: 0, hybrid: 0, unlinked: 0,
  };
  for (const row of payload.clients) {
    clientsByType[row.client_type] += 1;
  }
  return {
    clientsTotal: payload.clients.length,
    clientsByType,
    deadlinesOverdue: payload.deadlines.totals.overdue,
    deadlinesDueSoon: payload.deadlines.totals.due_soon,
    unpaidFeesTotal: payload.unpaid_fees.total,
    unpaidFeesCount: payload.unpaid_fees.invoices.length,
  };
}
