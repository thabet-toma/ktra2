/**
 * ISSUE #271 — عميل API موديول مكتب المحاسبة.
 *
 * مرآة `accounting_office/views.py`: كلُّ نقطةٍ تحت `/api/accounting-office/`
 * وكلُّها خلف بوابة الترخيص خادمياً — فالـ404 هنا يعني «الوحدة غير مفعّلة»، لا
 * «المسار خطأ». والواجهة تُخفي السطح أصلاً عبر `VIEW_MODULES`
 * (`utils/viewPermissions.ts`) فتصير الحالة رسالةً لا شاشةً بيضاء.
 */
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
  apiPutObject,
} from './restApi';
import { resolveTenantId } from '../utils/tenantContext';
import type { SettingRow } from '../utils/accountingOffice';

export type { SettingRow };

const BASE = 'accounting-office/';
const CLIENTS = `${BASE}clients/`;
const CONTACTS = `${BASE}contacts/`;
const SETTINGS = `${BASE}settings/`;

const tenantOpts = () => ({ tenantId: resolveTenantId() });

export interface TaxCard {
  id: number;
  entity_type: string;
  entity_type_label: string;
  vat_classification: string;
  vat_classification_label: string;
  /** DecimalField يُسلسَل نصّاً — لا تحوّله إلى float في العرض. */
  annual_sales: string;
  has_employees: boolean;
  employees_count: number;
  is_self_employed: boolean;
  tax_system: string | null;
  entity_type_choices: { value: string; label: string }[];
  vat_classification_choices: { value: string; label: string }[];
  updated_at: string;
}

export interface OfficeClientRow {
  id: number;
  name: string;
  tax_file_number: string;
  status: 'active' | 'ended';
  status_label: string;
  ended_on: string | null;
  notes: string;
  tax_system: string | null;
  tax_system_label: string;
  tax_card: TaxCard | null;
  created_at: string;
  updated_at: string;
}

export interface ContactRow {
  id: number;
  name: string;
  phone: string;
  language: 'ar' | 'he';
  language_label: string;
  created_at: string;
  updated_at: string;
}

export interface ClientContactRow {
  id: number;
  is_primary: boolean;
  created_at: string;
  contact: ContactRow;
}

export interface ReminderRecipientRow {
  reminder_type: string;
  label: string;
  is_fallback: boolean;
  recipient: {
    contact_id: number;
    name: string;
    phone: string;
    language: string;
  } | null;
}

export interface OfficeSettingsPayload {
  first_run_required: boolean;
  missing_settings: string[];
  groups: { id: string; label: string }[];
  settings: SettingRow[];
}

export interface ClientSettingsPayload {
  client: number;
  settings: SettingRow[];
}

export interface OfficeClientListFilters {
  q?: string;
  status?: 'active' | 'ended' | 'all';
}

export const listOfficeClients = (
  filters: OfficeClientListFilters = {},
): Promise<OfficeClientRow[]> =>
  apiGetList<OfficeClientRow>(CLIENTS, {
    ...tenantOpts(),
    query: {
      q: filters.q?.trim() || undefined,
      status: filters.status ?? undefined,
    },
  });

export const getOfficeClient = (id: number): Promise<OfficeClientRow> =>
  apiGetObject<OfficeClientRow>(`${CLIENTS}${id}/`, tenantOpts());

export const createOfficeClient = (payload: {
  name: string;
  tax_file_number?: string;
  notes?: string;
}): Promise<OfficeClientRow> => apiPostObject<OfficeClientRow>(CLIENTS, payload, tenantOpts());

export const updateOfficeClient = (
  id: number,
  payload: Partial<Pick<OfficeClientRow, 'name' | 'tax_file_number' | 'notes'>>,
): Promise<OfficeClientRow> =>
  apiPatchObject<OfficeClientRow>(`${CLIENTS}${id}/`, payload, tenantOpts());

export const endOfficeClient = (id: number): Promise<OfficeClientRow> =>
  apiPostObject<OfficeClientRow>(`${CLIENTS}${id}/end/`, {}, tenantOpts());

export const reactivateOfficeClient = (id: number): Promise<OfficeClientRow> =>
  apiPostObject<OfficeClientRow>(`${CLIENTS}${id}/reactivate/`, {}, tenantOpts());

export const getTaxCard = (clientId: number): Promise<TaxCard> =>
  apiGetObject<TaxCard>(`${CLIENTS}${clientId}/tax-card/`, tenantOpts());

export const updateTaxCard = (clientId: number, payload: Partial<TaxCard>): Promise<TaxCard> =>
  apiPatchObject<TaxCard>(`${CLIENTS}${clientId}/tax-card/`, payload, tenantOpts());

// ── جهات الاتصال ────────────────────────────────────────────────────────
/** بحثٌ بالاسم أو الهاتف — يُغذّي منتقي الجهات عند ربط واحدةٍ بزبون. */
export const listContacts = (q?: string): Promise<ContactRow[]> =>
  apiGetList<ContactRow>(CONTACTS, {
    ...tenantOpts(),
    query: { q: q?.trim() || undefined },
  });

export const createContact = (payload: {
  name: string;
  phone?: string;
  language?: 'ar' | 'he';
}): Promise<ContactRow> => apiPostObject<ContactRow>(CONTACTS, payload, tenantOpts());

export const updateContact = (
  id: number,
  payload: Partial<Pick<ContactRow, 'name' | 'phone' | 'language'>>,
): Promise<ContactRow> => apiPatchObject<ContactRow>(`${CONTACTS}${id}/`, payload, tenantOpts());

export const deleteContact = (id: number): Promise<void> =>
  apiDelete(`${CONTACTS}${id}/`, tenantOpts());

export const listClientContacts = (clientId: number): Promise<ClientContactRow[]> =>
  apiGetList<ClientContactRow>(`${CLIENTS}${clientId}/contacts/`, tenantOpts());

export const linkClientContact = (
  clientId: number,
  contactId: number,
  isPrimary = false,
): Promise<ClientContactRow> =>
  apiPostObject<ClientContactRow>(
    `${CLIENTS}${clientId}/contacts/`,
    { contact: contactId, is_primary: isPrimary },
    tenantOpts(),
  );

export const unlinkClientContact = (clientId: number, contactId: number): Promise<void> =>
  apiDelete(`${CLIENTS}${clientId}/contacts/${contactId}/`, tenantOpts());

export const promoteClientContact = (
  clientId: number,
  contactId: number,
): Promise<ClientContactRow> =>
  apiPostObject<ClientContactRow>(
    `${CLIENTS}${clientId}/contacts/${contactId}/primary/`, {}, tenantOpts(),
  );

// ── مستلِمو التذكيرات ───────────────────────────────────────────────────
export const listReminderRecipients = (clientId: number): Promise<ReminderRecipientRow[]> =>
  apiGetList<ReminderRecipientRow>(`${CLIENTS}${clientId}/reminders/`, tenantOpts());

export const setReminderRecipient = (
  clientId: number,
  reminderType: string,
  contactId: number | null,
): Promise<ReminderRecipientRow[]> =>
  apiPostObject<ReminderRecipientRow[]>(
    `${CLIENTS}${clientId}/reminders/`,
    { reminder_type: reminderType, contact: contactId },
    tenantOpts(),
  );

// ── الإعدادات ───────────────────────────────────────────────────────────
export const getOfficeSettings = (): Promise<OfficeSettingsPayload> =>
  apiGetObject<OfficeSettingsPayload>(SETTINGS, tenantOpts());

export const setOfficeSetting = (key: string, value: unknown): Promise<SettingRow> =>
  apiPutObject<SettingRow>(`${SETTINGS}${key}/`, { value }, tenantOpts());

export const resetOfficeSetting = (key: string): Promise<void> =>
  apiDelete(`${SETTINGS}${key}/`, tenantOpts());

export const listCustomizingClients = (
  key: string,
): Promise<Pick<OfficeClientRow, 'id' | 'name' | 'status' | 'status_label'>[]> =>
  apiGetList(`${SETTINGS}${key}/clients/`, tenantOpts());

export const getClientSettings = (clientId: number): Promise<ClientSettingsPayload> =>
  apiGetObject<ClientSettingsPayload>(`${CLIENTS}${clientId}/settings/`, tenantOpts());

export const setClientSetting = (
  clientId: number,
  key: string,
  value: unknown,
): Promise<SettingRow> =>
  apiPutObject<SettingRow>(`${CLIENTS}${clientId}/settings/${key}/`, { value }, tenantOpts());

export const resetClientSetting = (clientId: number, key: string): Promise<void> =>
  apiDelete(`${CLIENTS}${clientId}/settings/${key}/`, tenantOpts());
