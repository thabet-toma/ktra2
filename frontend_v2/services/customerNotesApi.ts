/**
 * ملاحظات/تذكيرات بطاقة الزبون (CRM) — عميل REST رقيق حول restApi.
 * الـ backend: partners.CustomerNoteViewSet (منطاق بالشركة عبر X-Tenant-Id).
 */
import { apiDelete, apiGetList, apiPatchObject, apiPostObject } from './restApi';
import { resolveTenantId } from '../utils/tenantContext';

/** أولوية الملاحظة — «عاجل» تُنبّه عند أي معاملة للطرف بعد حلول موعدها. */
export type CustomerNotePriority = 'urgent' | 'medium' | 'normal';

export interface CustomerNote {
  id: number;
  partner: number;
  title: string;
  body: string;
  remind_on: string | null;
  is_done: boolean;
  priority: CustomerNotePriority;
  priority_display?: string;
  created_by_name?: string;
  created_at: string;
  updated_at: string;
}

/** ملاحظة عاجلة مستحقة على طرف — تُعرَض داخل شاشات المعاملات. */
export interface PartnerNoteAlertRow {
  id: number;
  title: string;
  body: string;
  remind_on: string;
  priority: CustomerNotePriority;
  priority_display: string;
}

/** سطر تذكير مستحق (من reminders-due/) — يُغذّي مولّد إشعارات الموقع. */
export interface CustomerNoteReminder {
  id: number;
  title: string;
  remind_on: string;
  partner_id: number;
  partner_name: string;
}

export function listCustomerNotes(partnerId: number | string): Promise<CustomerNote[]> {
  return apiGetList<CustomerNote>('customer-notes/', {
    tenantId: resolveTenantId(),
    query: { partner: partnerId },
  });
}

export function createCustomerNote(input: {
  partner: number;
  title: string;
  body?: string;
  remind_on?: string | null;
  priority?: CustomerNotePriority;
}): Promise<CustomerNote> {
  return apiPostObject<CustomerNote>('customer-notes/', input, { tenantId: resolveTenantId() });
}

export function updateCustomerNote(
  id: number,
  patch: Partial<Pick<CustomerNote, 'title' | 'body' | 'remind_on' | 'is_done' | 'priority'>>,
): Promise<CustomerNote> {
  return apiPatchObject<CustomerNote>(`customer-notes/${id}/`, patch, { tenantId: resolveTenantId() });
}

export function deleteCustomerNote(id: number): Promise<void> {
  return apiDelete(`customer-notes/${id}/`, { tenantId: resolveTenantId() });
}

export function fetchDueCustomerNoteReminders(): Promise<CustomerNoteReminder[]> {
  return apiGetList<CustomerNoteReminder>('customer-notes/reminders-due/', { tenantId: resolveTenantId() });
}

/** ملاحظات «عاجل» المستحقة على هذا الطرف — تُستدعى من شاشات المعاملات. */
export function fetchPartnerNoteAlerts(
  partnerId: number | string,
): Promise<PartnerNoteAlertRow[]> {
  return apiGetList<PartnerNoteAlertRow>('customer-notes/alerts/', {
    tenantId: resolveTenantId(),
    query: { partner: partnerId },
  });
}
