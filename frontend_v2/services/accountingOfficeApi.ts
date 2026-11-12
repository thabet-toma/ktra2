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
  apiGetForBlob,
  apiGetForText,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostFormData,
  apiPostObject,
  apiPutObject,
} from './restApi';
import { resolveTenantId } from '../utils/tenantContext';
import type {
  ApplyPackageResult,
  AppointmentConfirmation,
  AppointmentsListPayload,
  CalendarPayload,
  ClientAppointmentsPayload,
  BookAccountRow,
  BookEntryRow,
  BookReportPeriod,
  ClientBookChoicesPayload,
  ClientBookReportKind,
  ClientBookReportShare,
  ClientBookReportsPayload,
  ClientBookRow,
  ClientDocumentsPayload,
  ClientEventsPayload,
  ClientEventRow,
  ClientObligationsPayload,
  ClientTaskRow,
  ClientServiceRow,
  ClientServicesPayload,
  DashboardPayload,
  DeadlineRuleOverrideRow,
  DeadlineRuleRow,
  DocumentFileRow,
  DocumentRowPayload,
  OfficeAlertRow,
  OfficeAlertsPayload,
  OfficeAppointmentRow,
  OfficeCustomRulesPayload,
  OfficeDocumentItemsPayload,
  OfficeDocumentItemRow,
  OfficeServiceRow,
  ObligationRow,
  PendingEntryPayload,
  PendingEntryRow,
  ServicePackageRow,
  ServiceSuggestion,
  SettingRow,
  TodayFilter,
  TodayPayload,
} from '../utils/accountingOffice';

export type {
  ApplyPackageResult,
  AppointmentConfirmation,
  AppointmentsListPayload,
  CalendarDeadlineRow,
  CalendarPayload,
  ClientAppointmentsPayload,
  BookAccountRow,
  BookChoice,
  BookEntryLineRow,
  BookEntryRow,
  BookReportPeriod,
  ClientBookChoicesPayload,
  ClientBookReportKind,
  ClientBookReportShare,
  ClientBookReportsPayload,
  ClientBookRow,
  ClientDocumentsPayload,
  ClientEventRow,
  ClientEventsPayload,
  ClientObligationsPayload,
  ClientServiceFrequencyRow,
  ClientServiceRow,
  ClientServicesPayload,
  ClientTaskRow,
  DeadlineRuleOverrideRow,
  DeadlineRuleRow,
  DocumentCell,
  DocumentChoice,
  DocumentFileRow,
  DocumentItemRow,
  DocumentProgress,
  DocumentRetentionRow,
  DocumentRowPayload,
  DashboardPayload,
  DashboardStaffRow,
  DashboardThresholds,
  DashboardWaiting,
  DashboardWaitingGroup,
  EventKindChoice,
  ObligationBadge,
  ObligationRow,
  OfficeAlertRow,
  OfficeAlertsPayload,
  OfficeAppointmentRow,
  OfficeCustomRuleRow,
  OfficeCustomRulesPayload,
  OfficeDocumentItemRow,
  OfficeDocumentItemsPayload,
  OfficeServiceRow,
  PendingDocument,
  PendingEntryPayload,
  PendingEntryRow,
  ServicePackageRow,
  ServiceSuggestion,
  SettingRow,
  TodayCounters,
  TodayFilter,
  TodayPayload,
} from '../utils/accountingOffice';

const BASE = 'accounting-office/';
const CLIENTS = `${BASE}clients/`;
const CONTACTS = `${BASE}contacts/`;
const SERVICES = `${BASE}services/`;
const PACKAGES = `${BASE}packages/`;
const SETTINGS = `${BASE}settings/`;
const CALENDAR = `${BASE}calendar/`;
const DEADLINE_RULES = `${BASE}deadline-rules/`;
const CUSTOM_RULES = `${BASE}custom-rules/`;
const TODAY = `${BASE}today/`;
const OBLIGATIONS = `${BASE}obligations/`;
const TASKS = `${BASE}tasks/`;
const ALERTS = `${BASE}alerts/`;
const DOCUMENTS = `${BASE}documents/`;
const DOCUMENT_FILES = `${BASE}document-files/`;
const DOCUMENT_ITEMS = `${BASE}document-items/`;
// #280: «جاهز للإرسال» وأفعالها، وسجلُّ التذكيرات (إلحاقيّ)، ونصوصُ المكتب، وعطلُه.
const READY_TO_SEND = `${BASE}ready-to-send/`;
const REMINDER_LOG = `${BASE}reminder-log/`;
const REMINDER_TEMPLATES = `${BASE}reminder-templates/`;
const OFFICE_HOLIDAYS = `${BASE}office-holidays/`;
// #281: المواعيد — حجزٌ وأفعالُه. `client` على الجمع يُعيد تبويبَ ملفّ الزبون.
const APPOINTMENTS = `${BASE}appointments/`;
// #286: دفترُ الزبون — الدفاترُ وشجرتُها وحركاتُها و«للإدخال» (الجزء أ، خادمياً).
const CLIENT_BOOKS = `${BASE}client-books/`;
// #283/ب: الدفعاتُ ومستنداها — إشعارُ قبضٍ لكل دفعة، وكشفُ حسابٍ لفترة.
const FEE_PAYMENTS = `${BASE}fees/payments/`;
const FEE_LEDGER = `${BASE}fees/ledger/`;

const tenantOpts = () => ({ tenantId: resolveTenantId() });

export interface TaxCard {
  id: number;
  entity_type: string;
  entity_type_label: string;
  vat_classification: string;
  vat_classification_label: string;
  /**
   * DecimalField يُسلسَل نصّاً — لا تحوّله إلى float في العرض.
   * **و`null` معناها «لا تملك رؤية المبالغ»** (#272): الخادم يرسل المبلغ فارغاً
   * لعضوٍ بلا `office.amounts.view`، فتعرض الشاشة «—» ولا ترسله في الحفظ.
   */
  annual_sales: string | null;
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
  /** الموظف المسؤول (#272) — للقراءة وحدها؛ التحويلُ لنقطته `assign/`. */
  responsible_id: number | null;
  responsible_name: string;
  /**
   * «اللي عليه» من الدالّة الواحدة (#283) — `string` بالخانتين، و`null` لعضوٍ لا
   * يرى المبالغ. الخادمُ يرسلها في القائمة والتفصيل، وكانت هنا بلا نوع.
   */
  due?: string | null;
  /**
   * علامةُ حجب التسليم (#283/ج) — **مفتاحٌ غائبٌ حين لا حجب**: الإعدادُ مطفأً
   * هو سلوكُ اليوم، فلا يظهر حقلٌ فارغ. `label` نصُّ الخادم («لم يُسلَّم بعد»).
   */
  delivery?: { label: string } | null;
  created_at: string;
  updated_at: string;
}

/** عضوُ المكتب كما يعيده `tenants/companies/<id>/members/` (متاحٌ لكل عضو). */
export interface OfficeMemberRow {
  membership_id: number;
  user_id: number;
  username: string;
  full_name: string;
  role: string;
}

export interface ContactRow {
  id: number;
  name: string;
  phone: string;
  language: 'ar' | 'he';
  language_label: string;
  /**
   * إذنُ التذكير على الجهة نفسها (#280) — تقرؤه من `ContactSerializer` في
   * `clients/<pk>/contacts/` مباشرةً، فلا طلبَ لكل جهةٍ لعرض حالتها. والكتابةُ
   * بفعلها وحده (`contacts/<id>/consent/`) لأنها تمرّ بحارس الخدمة.
   */
  reminders_consent: boolean;
  consent_types: string[];
  consent_on: string | null;
  consent_channel: string;
  consent_channel_label: string;
  consent_withdrawn_on: string | null;
  consent_withdrawn_by: { id: number; name: string } | null;
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

// ── التذكيرات والرسائل (#280) ────────────────────────────────────────────────
/** اختيارٌ من الخادم: قيمةٌ وتسمية — لا جدولَ تسمياتٍ ثانٍ في الواجهة. */
export interface ReminderChoice {
  value: string;
  label: string;
}

/** إذنُ التذكير كما يُقرأ ويُعدَّل: مَن ومتى وكيف، ومن سحبه. */
export interface ContactConsentPayload {
  contact_id: number;
  name: string;
  reminders_consent: boolean;
  consent_types: string[];
  consent_types_labels: string[];
  consent_on: string | null;
  consent_channel: string;
  consent_channel_label: string;
  consent_withdrawn_on: string | null;
  consent_withdrawn_by: { id: number; name: string } | null;
  type_choices: ReminderChoice[];
  channel_choices: ReminderChoice[];
}

/** سطرُ نصِّ تذكيرٍ: الفعليُّ والافتراضيُّ وعلمُ التخصيص. */
export interface ReminderTemplateRow {
  reminder_type: string;
  reminder_type_label: string;
  language: 'ar' | 'he';
  language_label: string;
  body: string;
  default_body: string;
  is_custom: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface ReminderTemplatesPayload {
  placeholders: string[];
  rows: ReminderTemplateRow[];
}

/** بندٌ في رسالةِ «جاهز للإرسال» — بمفاتيح الأفعال كما يسمّيها الخادم. */
export interface ReadyToSendItem {
  client_id: number;
  client_name: string;
  /**
   * نظامُ **الزبون صاحب البند** الضريبيّ (`PS`/`IL`) أو `null` — #280/ب.
   * يُقرأ منه مفتاحُ دولة الأرضيّ في `officeWhatsappLink`، ولا يُخمَّن نظامٌ
   * واحدٌ للمستلِم: رسالةُ شخصٍ قد تجمع بندَي زبونين بنظامين مختلفين.
   */
  tax_system: string | null;
  reminder_type: string;
  reminder_type_label: string;
  badge: string;
  period_start: string;
  period_end: string;
  period_label: string;
  missing_list: string[];
  missing_codes: string[];
  step: number;
  max: number;
  due_date: string;
  /**
   * #282/أ٢: بندُ فاتورة الأتعاب المركَّب على التذكير — رقمُها ومبلغُها
   * واستحقاقُها ورابطُ ورقتها. `null` لبندٍ ليس فاتورة (أوراقٌ ومواعيد).
   * **`id` هو مفتاحُ صفّ البند**: ورقتان في يومٍ واحدٍ تتشاركان الفترة.
   */
  invoice: ReadyToSendInvoice | null;
  subject: { document_item_codes: string[] };
}

export interface ReadyToSendInvoice {
  id: number;
  number: string;
  title: string;
  kind: string;
  total: string;
  tax_total: string;
  issued_on: string;
  due_on: string;
  reason: string;
  /** رقمُ الفاتورة الأصل التي يخصمها الإشعارُ الدائن — فارغٌ لغيره. */
  original_number: string;
  url: string;
}

export interface ReadyToSendRecipient {
  contact_id: number;
  name: string;
  phone: string;
  /** `false` ⇒ الشاشةُ تُخفي زرَّ الواتساب وتُبقي «كلّمناه». */
  has_phone: boolean;
  language: 'ar' | 'he';
  language_label: string;
}

export interface ReadyToSendMessage {
  recipient: ReadyToSendRecipient;
  items: ReadyToSendItem[];
  body: string;
}

export interface ReadyToSendPayload {
  day: string;
  merge_daily: boolean;
  reminder_type: string | null;
  messages: ReadyToSendMessage[];
  placeholders: string[];
}

/** الصفُّ الذي يُرسَل في الأفعال — **بطرفَي الفترة**: المفتاحُ تاريخان لا تاريخ. */
export interface ReadyToSendItemKey {
  client_id: number;
  reminder_type: string;
  period_start: string;
  period_end: string;
}

/** سطرُ سجلّ التذكيرات — **لا يُعدَّل ولا يُحذف**: التصحيحُ صفٌّ جديد. */
export interface ReminderLogRow {
  id: number;
  client: { id: number; name: string };
  contact_id: number | null;
  recipient_name: string;
  recipient_phone: string;
  reminder_type: string;
  reminder_type_label: string;
  kind: string;
  kind_label: string;
  channel: string;
  channel_label: string;
  body: string;
  period_start: string | null;
  period_end: string | null;
  period_label: string;
  subject: { document_item_codes?: string[]; document_item_names?: string[] };
  reason: string;
  reverts_id: number | null;
  created_by: { id: number; name: string } | null;
  created_at: string;
}

export interface ReminderLogPayload {
  rows: ReminderLogRow[];
  limit: number;
}

export interface ClientReminderLogPayload extends ReminderLogPayload {
  client: { id: number; name: string };
}

export interface ReminderPostponeRow {
  id: number;
  client_id: number;
  reminder_type: string;
  reminder_type_label: string;
  until: string | null;
  reason: string;
  created_at: string;
}

export interface OfficeHolidayRow {
  id: number;
  date: string;
  name: string;
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
  /** #289: زبائنُ موظّفٍ واحد — كبسةُ صفّه في لوحة صاحب المكتب. */
  responsible?: number;
}

export const listOfficeClients = (
  filters: OfficeClientListFilters = {},
): Promise<OfficeClientRow[]> =>
  apiGetList<OfficeClientRow>(CLIENTS, {
    ...tenantOpts(),
    query: {
      q: filters.q?.trim() || undefined,
      status: filters.status ?? undefined,
      responsible: filters.responsible ?? undefined,
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

/**
 * تحويلُ الزبون لموظّفٍ آخر (#272) — يتطلّب `office.clients.assign` خادمياً،
 * ويُسجَّل الحدثُ في سجلّ النشاط (من ← إلى). والقراءةُ من `responsible_name`.
 *
 * **و`responsible` اسمُ الحقل** (#289) كاسم عمود النموذج؛ والخادمُ يقبل `user`
 * القديم بعده كي لا ينكسر عميلٌ قائم. والموظفُ الجديد عضوٌ بدور مكتبٍ وإلا 400.
 */
export const assignOfficeClient = (id: number, userId: number): Promise<OfficeClientRow> =>
  apiPostObject<OfficeClientRow>(
    `${CLIENTS}${id}/assign/`,
    { responsible: userId },
    tenantOpts(),
  );

/** أعضاء المكتب — المصدرُ الوحيد لمنتقي «حوّل» وقسم «الموظفون والأدوار». */
export const listOfficeMembers = (): Promise<OfficeMemberRow[]> =>
  apiGetList<OfficeMemberRow>(`tenants/companies/${resolveTenantId()}/members/`, tenantOpts());

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

// ── كتالوج الخدمات (#273) ───────────────────────────────────────────────
/** الكتالوج بأسطرِه الخمسة الافتراضية — يُزرع خادمياً عند أول قراءة. */
export const listOfficeServices = (): Promise<OfficeServiceRow[]> =>
  apiGetList<OfficeServiceRow>(SERVICES, tenantOpts());

export const createOfficeService = (payload: {
  name: string;
  position?: number;
}): Promise<OfficeServiceRow> => apiPostObject<OfficeServiceRow>(SERVICES, payload, tenantOpts());

export const updateOfficeService = (
  id: number,
  payload: Partial<Pick<OfficeServiceRow, 'name' | 'is_active' | 'position'>>,
): Promise<OfficeServiceRow> =>
  apiPatchObject<OfficeServiceRow>(`${SERVICES}${id}/`, payload, tenantOpts());

// ── الباقات (#273) ──────────────────────────────────────────────────────
export const listServicePackages = (): Promise<ServicePackageRow[]> =>
  apiGetList<ServicePackageRow>(PACKAGES, tenantOpts());

export const createServicePackage = (payload: {
  name: string;
  suggested_price?: string | null;
  services?: number[];
}): Promise<ServicePackageRow> => apiPostObject<ServicePackageRow>(PACKAGES, payload, tenantOpts());

export const updateServicePackage = (
  id: number,
  payload: {
    name?: string;
    suggested_price?: string | null;
    services?: number[];
  },
): Promise<ServicePackageRow> =>
  apiPatchObject<ServicePackageRow>(`${PACKAGES}${id}/`, payload, tenantOpts());

export const deleteServicePackage = (id: number): Promise<void> =>
  apiDelete(`${PACKAGES}${id}/`, tenantOpts());

// ── خدمات الزبون (#273) ─────────────────────────────────────────────────
export const listClientServices = (clientId: number): Promise<ClientServicesPayload> =>
  apiGetObject<ClientServicesPayload>(`${CLIENTS}${clientId}/services/`, tenantOpts());

/** الاقتراحُ وسببُه — نقطةُ قراءةٍ لا كتابة: الموظف يؤكّد أو يغيّر بعدها. */
export const suggestClientService = (
  clientId: number,
  serviceCode: string,
  onDate?: string,
): Promise<ServiceSuggestion> =>
  apiGetObject<ServiceSuggestion>(`${CLIENTS}${clientId}/services/suggest/`, {
    ...tenantOpts(),
    query: { service: serviceCode, on: onDate || undefined },
  });

export const addClientService = (
  clientId: number,
  payload: {
    service: number;
    starts_on?: string;
    responsible_from?: string;
    frequency?: string | null;
  },
): Promise<ClientServicesPayload> =>
  apiPostObject<ClientServicesPayload>(`${CLIENTS}${clientId}/services/`, payload, tenantOpts());

export const changeClientServiceFrequency = (
  clientId: number,
  serviceRowId: number,
  payload: { frequency: string; effective_from: string },
): Promise<ClientServicesPayload> =>
  apiPostObject<ClientServicesPayload>(
    `${CLIENTS}${clientId}/services/${serviceRowId}/frequency/`, payload, tenantOpts(),
  );

export const stopClientService = (
  clientId: number,
  serviceRowId: number,
  endsOn: string,
  lastPeriodOurs = true,
): Promise<ClientServicesPayload> =>
  apiPostObject<ClientServicesPayload>(
    `${CLIENTS}${clientId}/services/${serviceRowId}/stop/`,
    { ends_on: endsOn, last_period_ours: lastPeriodOurs },
    tenantOpts(),
  );

export const applyServicePackage = (
  clientId: number,
  packageId: number,
): Promise<ApplyPackageResult> =>
  apiPostObject<ApplyPackageResult>(
    `${CLIENTS}${clientId}/apply-package/`, { package: packageId }, tenantOpts(),
  );

// ── التقويم ولائحة المواعيد (#274) ──────────────────────────────────────
//
// **قراءتان لا كتابة**: التقويمُ محسوبٌ عند كل طلب ولا يُحفظ منه شيء، ولذلك لا
// نقطةَ حفظٍ هنا. والمدى يُطلب بعرض الشاشة وحده لا بسنةٍ كاملة.
export const getOfficeCalendar = (filters: {
  from: string;
  to: string;
  client?: number | null;
  member?: number | null;
  rule?: string | null;
}): Promise<CalendarPayload> =>
  apiGetObject<CalendarPayload>(CALENDAR, {
    ...tenantOpts(),
    query: {
      from: filters.from,
      to: filters.to,
      client: filters.client ?? undefined,
      member: filters.member ?? undefined,
      rule: filters.rule?.trim() || undefined,
    },
  });

/** أسطرُ لائحة المواعيد السارية — لفلتر «النوع» ولعرض اللائحة نفسها. */
export const listDeadlineRules = (
  system: 'PS' | 'IL',
): Promise<{ system: string; rules: DeadlineRuleRow[] }> =>
  apiGetObject(`${DEADLINE_RULES}`, { ...tenantOpts(), query: { system } });

// ── «اليوم» والالتزامات والشغلات (#275) ─────────────────────────────────
//
// **الخادم هو الحكم**: كلُّ فعلٍ يعيد السطرَ المحدَّث بالشكل نفسه، فتُحدَّث
// الشاشةُ من ردّه بدل تخمين الحالة، والعدّاداتُ تُعاد قراءتها من `today/`.
// والمبلغُ لا يُرسَل من عضوٍ لا يراه: الخادم يردّ 403، والشاشةُ تُخفيه أوّلاً.
export const getOfficeToday = (filter: TodayFilter = ''): Promise<TodayPayload> =>
  apiGetObject<TodayPayload>(TODAY, {
    ...tenantOpts(),
    query: { filter: filter || undefined },
  });

// ── لوحة صاحب المكتب (#289) ─────────────────────────────────────────────
//
// **دورٌ لا مفتاح**: المحاسبُ يأخذ 403 من الخادم، والشاشةُ تُظهر رسالتَه كما هي
// (`humanizeThrown`) — لا تُخفي الصفحةَ ولا تدّعي أنها لك.
const DASHBOARD = `${BASE}dashboard/`;

export const getOfficeDashboard = (): Promise<DashboardPayload> =>
  apiGetObject<DashboardPayload>(DASHBOARD, tenantOpts());

/** ردُّ «اعتمد الكل» — الشاشةُ تقرأ `approved` وحدَه، والباقي حمولةُ النقطة القائمة. */
export interface ApproveAllFeeDraftsResult {
  approved: number;
  remaining: number;
  drafts: unknown[];
}

/** «اعتمد الكل» على المسودّات المنتظرة — **النقطةُ القائمة** نفسُها لا نسخةً. */
export const approveAllFeeDrafts = (note = ''): Promise<ApproveAllFeeDraftsResult> =>
  apiPostObject<ApproveAllFeeDraftsResult>(
    `${BASE}fees/drafts/approve-all/`,
    note ? { note } : {},
    tenantOpts(),
  );

export const submitObligation = (
  id: number,
  payload: { submitted_on?: string; number?: string } = {},
): Promise<ObligationRow> =>
  apiPostObject<ObligationRow>(`${OBLIGATIONS}${id}/submit/`, payload, tenantOpts());

export const markObligationNotRequired = (id: number): Promise<ObligationRow> =>
  apiPostObject<ObligationRow>(`${OBLIGATIONS}${id}/not-required/`, {}, tenantOpts());

export const reopenObligation = (id: number): Promise<ObligationRow> =>
  apiPostObject<ObligationRow>(`${OBLIGATIONS}${id}/reopen/`, {}, tenantOpts());

/** `amount: null` يمسح المبلغَ والاتجاه — و`direction` مطلوبٌ مع المبلغ. */
export const setObligationAmount = (
  id: number,
  payload: { amount: string | null; direction: string },
): Promise<ObligationRow> =>
  apiPostObject<ObligationRow>(`${OBLIGATIONS}${id}/amount/`, payload, tenantOpts());

export const setObligationClientPaid = (
  id: number,
  paid: boolean,
): Promise<ObligationRow> =>
  apiPostObject<ObligationRow>(
    `${OBLIGATIONS}${id}/client-paid/`, { paid }, tenantOpts(),
  );

/** تحويلُ شغلةٍ — `null` يُعيدها إلى وراثة مسؤول الزبون. الردُّ سطرُ الشغلة. */
export const assignTask = (
  id: number,
  assignee: number | null,
): Promise<Omit<ClientTaskRow, 'obligations'>> =>
  apiPostObject<Omit<ClientTaskRow, 'obligations'>>(
    `${TASKS}${id}/assign/`, { assignee }, tenantOpts(),
  );

export const getClientObligations = (clientId: number): Promise<ClientObligationsPayload> =>
  apiGetObject<ClientObligationsPayload>(
    `${CLIENTS}${clientId}/obligations/`, tenantOpts(),
  );

/** «هدول انقدّموا قبل ما يجي علينا» — يعيد عددَ ما أُغلق. */
export const closePriorObligations = (
  clientId: number,
  before?: string,
): Promise<{ closed: number }> =>
  apiPostObject<{ closed: number }>(
    `${CLIENTS}${clientId}/obligations/close-prior/`,
    before ? { before } : {},
    tenantOpts(),
  );

// ── الجرس (#276) ────────────────────────────────────────────────────────
//
// **كلُّ عضوٍ يرى تنبيهاته هو فقط** خادمياً — لا معاملَ `user` هنا ولا مفتاحَ
// إضافياً. والقراءةُ تُسقط المحسوم، فما يصل جاهزٌ للعرض والعدّادُ `unseen` معه.
export const getOfficeAlerts = (): Promise<OfficeAlertsPayload> =>
  apiGetObject<OfficeAlertsPayload>(ALERTS, tenantOpts());

/** «شفته» — يُرجع السطرَ المحدَّث (`seen: true`)، والقراءةُ التالية تُنقص العدّاد. */
export const markOfficeAlertSeen = (id: number): Promise<OfficeAlertRow> =>
  apiPostObject<OfficeAlertRow>(`${ALERTS}${id}/seen/`, {}, tenantOpts());

/** «شفتهم كلهم» — `{"seen": n}` عددُ ما كُتب له وقتُ الشوفة. */
export const markAllOfficeAlertsSeen = (): Promise<{ seen: number }> =>
  apiPostObject<{ seen: number }>(`${ALERTS}seen-all/`, {}, tenantOpts());

// ── تعديل المكتب على اللائحة، والتمديد، والتزامات المكتب، والأحداث (#277) ──
//
// **الكتابةُ بمفتاحها خادمياً**: اللائحةُ والتزاماتُ المكتب بـ
// `office.settings.manage` (403 لغيره)، والأحداثُ والتمديد بـ`office.clients.write`.
// والقراءةُ تُرجع الحمولة كاملةً بعد كل تعديل، فتحدّث الشاشةُ من ردّ الخادم بدل
// تخمين الحال.
export const setDeadlineRuleOverride = (
  payload: {
    system: 'PS' | 'IL';
    code: string;
    rule_day?: number | null;
    rule_month?: number | null;
    electronic_extension_days?: number | null;
    note?: string;
  },
): Promise<{
  override: DeadlineRuleOverrideRow;
  changed_obligations: number;
}> => apiPostObject(`${DEADLINE_RULES}override/`, payload, tenantOpts());

/** «رجّع للمنصة» — صفُّ `cleared` في السجلّ؛ لا حذفَ لتعديلٍ سابق. */
export const clearDeadlineRuleOverride = (
  system: 'PS' | 'IL',
  code: string,
): Promise<{ override: DeadlineRuleOverrideRow; changed_obligations: number }> =>
  apiPostObject(`${DEADLINE_RULES}clear-override/`, { system, code }, tenantOpts());

/** «أُبقي تاريخي» — لقطةٌ من النسخة الجديدة فتصير السارية ويسقط التنبيه. */
export const keepDeadlineRuleOverride = (
  system: 'PS' | 'IL',
  code: string,
): Promise<{ override: DeadlineRuleOverrideRow; changed_obligations: number }> =>
  apiPostObject(`${DEADLINE_RULES}keep-override/`, { system, code }, tenantOpts());

export const listOfficeCustomRules = (): Promise<OfficeCustomRulesPayload> =>
  apiGetObject<OfficeCustomRulesPayload>(CUSTOM_RULES, tenantOpts());

export const createOfficeCustomRule = (payload: {
  name: string;
  service: number;
  cadence: string;
  rule_kind: string;
  rule_day?: number | null;
  rule_month?: number | null;
}): Promise<OfficeCustomRulesPayload> =>
  apiPostObject<OfficeCustomRulesPayload>(CUSTOM_RULES, payload, tenantOpts());

export const updateOfficeCustomRule = (
  id: number,
  payload: {
    name?: string;
    service?: number;
    cadence?: string;
    rule_kind?: string;
    rule_day?: number | null;
    rule_month?: number | null;
    is_active?: boolean;
  },
): Promise<OfficeCustomRulesPayload> =>
  apiPatchObject<OfficeCustomRulesPayload>(`${CUSTOM_RULES}${id}/`, payload, tenantOpts());

/** أحداثُ الزبون وأنواعُها المفعّلة — حمولةٌ واحدة تكفي تبويبَ «الالتزامات». */
export const getClientEvents = (clientId: number): Promise<ClientEventsPayload> =>
  apiGetObject<ClientEventsPayload>(`${CLIENTS}${clientId}/events/`, tenantOpts());

export const recordClientEvent = (
  clientId: number,
  payload: { kind: string; occurred_on: string; note?: string },
): Promise<{ event: ClientEventRow; obligations: ObligationRow[] }> =>
  apiPostObject(`${CLIENTS}${clientId}/events/`, payload, tenantOpts());

/** «مدّد» — تاريخٌ وملاحظة، والردُّ سطرُ الالتزام المحدَّث. */
export const extendObligation = (
  id: number,
  payload: { until: string; note: string },
): Promise<ObligationRow> =>
  apiPostObject<ObligationRow>(`${OBLIGATIONS}${id}/extend/`, payload, tenantOpts());

export const clearObligationExtension = (id: number): Promise<ObligationRow> =>
  apiPostObject<ObligationRow>(
    `${OBLIGATIONS}${id}/clear-extension/`, {}, tenantOpts(),
  );

// ── قائمة الأوراق (#278) ────────────────────────────────────────────────────

/** شبكةُ سنةٍ لزبون — `year` تُهمَل إن غابت فيختار الخادمُ سنةَ اليوم. */
export const getClientDocuments = (
  clientId: number,
  year?: number,
): Promise<ClientDocumentsPayload> =>
  apiGetObject<ClientDocumentsPayload>(`${CLIENTS}${clientId}/documents/`, {
    ...tenantOpts(),
    query: { year: year ?? undefined },
  });

/** تسجيلُ حالة ورقة — «وصلت» تحتاج `channel` وإلا 400 من الخادم. */
export const setDocumentStatus = (
  rowId: number,
  payload: { status: string; channel?: string },
): Promise<DocumentRowPayload> =>
  apiPostObject<DocumentRowPayload>(
    `${DOCUMENTS}${rowId}/status/`, payload, tenantOpts(),
  );

/** ملفاتُ ورقةٍ — **بلا رابط تخزين**: التقديمُ من نقطة التنزيل وحدها. */
export const listDocumentFiles = (rowId: number): Promise<DocumentFileRow[]> =>
  apiGetList<DocumentFileRow>(`${DOCUMENTS}${rowId}/files/`, tenantOpts());

/**
 * رفعُ ملف ورقةٍ multipart بحقول נספח ז.
 *
 * `FormData` لأن الملفَّ يُرسَل ككائن، والـ`Content-Type` لا يُضبط يدوياً —
 * المتصفحُ يضيف الـboundary.
 */
export const uploadDocumentFile = (
  rowId: number,
  input: {
    file: File;
    document_type?: string;
    issuer_registration?: string;
    document_date?: string;
    document_number?: string;
    is_copy?: boolean;
  },
): Promise<DocumentFileRow> => {
  const form = new FormData();
  form.append('file', input.file);
  if (input.document_type) form.append('document_type', input.document_type);
  if (input.issuer_registration) {
    form.append('issuer_registration', input.issuer_registration);
  }
  if (input.document_date) form.append('document_date', input.document_date);
  if (input.document_number) form.append('document_number', input.document_number);
  if (input.is_copy === false) form.append('is_copy', 'false');
  return apiPostFormData<DocumentFileRow>(
    `${DOCUMENTS}${rowId}/files/`, form, tenantOpts(),
  );
};

export const deleteDocumentFile = (id: number): Promise<void> =>
  apiDelete(`${DOCUMENT_FILES}${id}/`, tenantOpts());

/** تنزيلُ الملف بايتاتٍ — الرابط لا يصل الواجهة أصلاً. */
export const downloadDocumentFile = (id: number): Promise<Blob> =>
  apiGetForBlob(`${DOCUMENT_FILES}${id}/download/`, tenantOpts());

/** قالبُ البنود لِنظام — ومع `clientId` يُضاف خيارُ الزبون على كل بند. */
export const getDocumentItems = (
  system: string,
  clientId?: number,
): Promise<OfficeDocumentItemsPayload> =>
  apiGetObject<OfficeDocumentItemsPayload>(DOCUMENT_ITEMS, {
    ...tenantOpts(),
    query: { system, client: clientId ?? undefined },
  });

/** «ضمن القائمة» على بندٍ في قالب المكتب — بمفتاح `office.settings.manage`. */
export const setOfficeDocumentChoice = (payload: {
  item_code: string;
  included: boolean;
}): Promise<OfficeDocumentItemsPayload & { item_code: string; included: boolean }> =>
  apiPostObject(`${DOCUMENT_ITEMS}choice/`, payload, tenantOpts());

export const createOfficeDocumentItem = (payload: {
  system: string;
  name: string;
  cadence: string;
  service_codes?: string[];
  is_active?: boolean;
}): Promise<OfficeDocumentItemsPayload> =>
  apiPostObject<OfficeDocumentItemsPayload>(DOCUMENT_ITEMS, payload, tenantOpts());

export const updateOfficeDocumentItem = (
  id: number,
  payload: {
    name?: string;
    cadence?: string;
    service_codes?: string[];
    is_active?: boolean;
  },
): Promise<OfficeDocumentItemsPayload> =>
  apiPatchObject<OfficeDocumentItemsPayload>(
    `${DOCUMENT_ITEMS}${id}/`, payload, tenantOpts(),
  );

/** خيارُ الزبون على بند — يغلب قالبَ المكتب، والردُّ قائمةُ بنوده. */
export const setClientDocumentChoice = (
  clientId: number,
  payload: { item_code: string; included: boolean },
): Promise<{
  item_code: string;
  included: boolean;
  items: OfficeDocumentItemRow[];
}> =>
  apiPostObject(`${CLIENTS}${clientId}/document-choice/`, payload, tenantOpts());


// ── التذكيرات والرسائل (#280) ────────────────────────────────────────────────

/** إذنُ الجهة على التذكير — مفتاحُ الكتابة نفسه (`office.clients.write`). */
export const getContactConsent = (contactId: number): Promise<ContactConsentPayload> =>
  apiGetObject<ContactConsentPayload>(
    `${CONTACTS}${contactId}/consent/`, tenantOpts(),
  );

export const setContactConsent = (
  contactId: number,
  payload: { consent: boolean; types?: string[]; channel?: string },
): Promise<ContactConsentPayload> =>
  apiPostObject<ContactConsentPayload>(
    `${CONTACTS}${contactId}/consent/`, payload, tenantOpts(),
  );

/** نصوصُ التذكير: قراءةٌ لكل عضو — ومن يرسل يقرأ ما سيرسل. */
export const getReminderTemplates = (): Promise<ReminderTemplatesPayload> =>
  apiGetObject<ReminderTemplatesPayload>(REMINDER_TEMPLATES, tenantOpts());

/** بديلُ المكتب عن نصّ المنصّة — بمفتاح `office.settings.manage`. */
export const setReminderTemplate = (
  reminderType: string,
  language: string,
  body: string,
): Promise<ReminderTemplatesPayload> =>
  apiPutObject<ReminderTemplatesPayload>(
    `${REMINDER_TEMPLATES}${reminderType}/${language}/`, { body }, tenantOpts(),
  );

/** «ارجع للافتراضي» = حذفُ البديل — لا كتابةُ الافتراضيِّ مكانه. */
export const resetReminderTemplate = (
  reminderType: string,
  language: string,
): Promise<void> =>
  apiDelete(`${REMINDER_TEMPLATES}${reminderType}/${language}/`, tenantOpts());

/** «جاهز للإرسال» — رسالةٌ لكل شخصٍ في اليوم (أو لكل بندٍ بلا تجميع). */
export const getReadyToSend = (
  params: { day?: string; reminder_type?: string; assignee?: number } = {},
): Promise<ReadyToSendPayload> =>
  apiGetObject<ReadyToSendPayload>(READY_TO_SEND, {
    ...tenantOpts(),
    query: {
      day: params.day,
      reminder_type: params.reminder_type,
      assignee: params.assignee,
    },
  });

/** «انبعثت»: صفٌّ لكل بندٍ بالنصّ نفسه — والسجلُّ لا يُعدَّل بعدها. */
export const markRemindersSent = (payload: {
  contact_id: number;
  body: string;
  channel?: string;
  items: ReadyToSendItemKey[];
}): Promise<{ rows: ReminderLogRow[] }> =>
  apiPostObject(`${READY_TO_SEND}sent/`, payload, tenantOpts());

/** «كلّمناه» — `phone` أو `in_person` وحدهما. */
export const markRemindersManual = (payload: {
  contact_id: number;
  body?: string;
  channel: 'phone' | 'in_person';
  items: ReadyToSendItemKey[];
}): Promise<{ rows: ReminderLogRow[] }> =>
  apiPostObject(`${READY_TO_SEND}manual/`, payload, tenantOpts());

/** «شيل لهذه المرة» — يُعيد المؤقّت ولا يُعدّ في الحدّ الأقصى. */
export const dismissReminders = (payload: {
  items: ReadyToSendItemKey[];
  reason?: string;
}): Promise<{ rows: ReminderLogRow[] }> =>
  apiPostObject(`${READY_TO_SEND}dismiss/`, payload, tenantOpts());

/** «أجّل التذكير لتاريخ…» — و`until=null` يمسح التأجيل. */
export const postponeReminder = (payload: {
  client_id: number;
  reminder_type: string;
  until: string | null;
  reason?: string;
}): Promise<ReminderPostponeRow> =>
  apiPostObject<ReminderPostponeRow>(`${READY_TO_SEND}postpone/`, payload, tenantOpts());

/** سجلُّ المكتب — الأحدثُ أوّلاً. */
export const getReminderLog = (): Promise<ReminderLogPayload> =>
  apiGetObject<ReminderLogPayload>(REMINDER_LOG, tenantOpts());

/** سجلُّ زبونٍ واحدٍ لتبويب ملفّه. */
export const getClientReminderLog = (
  clientId: number,
): Promise<ClientReminderLogPayload> =>
  apiGetObject<ClientReminderLogPayload>(
    `${CLIENTS}${clientId}/reminder-log/`, tenantOpts(),
  );

/** «ما انبعتت» — صفُّ `undo` جديدٌ يشير إلى ما يُبطله، والأصلُ يبقى. */
export const undoReminderLog = (id: number): Promise<{ row: ReminderLogRow }> =>
  apiPostObject(`${REMINDER_LOG}${id}/undo/`, {}, tenantOpts());

/** عطلُ المكتب — تُقرأ لكل عضو وتُكتب بمفتاح الإعدادات. */
export const getOfficeHolidays = (): Promise<OfficeHolidayRow[]> =>
  apiGetObject<OfficeHolidayRow[]>(OFFICE_HOLIDAYS, tenantOpts());

export const createOfficeHoliday = (payload: {
  date: string;
  name?: string;
}): Promise<OfficeHolidayRow> =>
  apiPostObject<OfficeHolidayRow>(OFFICE_HOLIDAYS, payload, tenantOpts());

export const deleteOfficeHoliday = (id: number): Promise<void> =>
  apiDelete(`${OFFICE_HOLIDAYS}${id}/`, tenantOpts());

// ── المواعيد (#281) ─────────────────────────────────────────────────────
//
// **كلُّ فعلٍ يعيد السطرَ المحدَّث** بالشكل نفسه، فتُقرأ الحالةُ من ردّ الخادم لا
// من تخمين الواجهة. و`client` وحدها تُعيد تبويبَ ملفّ الزبون (بمنتقي الأنواع)،
// و`day` وحدها تُعيد مواعيدَ يومٍ، وغيابُهما كلَّ ما يراه العضو.
export const listClientAppointments = (
  clientId: number,
  day?: string,
): Promise<ClientAppointmentsPayload> =>
  apiGetObject<ClientAppointmentsPayload>(APPOINTMENTS, {
    ...tenantOpts(),
    query: { client: clientId, day: day || undefined },
  });

export const listDayAppointments = (day?: string): Promise<AppointmentsListPayload> =>
  apiGetObject<AppointmentsListPayload>(APPOINTMENTS, {
    ...tenantOpts(),
    query: { day: day || undefined },
  });

export const createAppointment = (payload: {
  client_id: number;
  kind: string;
  scheduled_at: string;
  note?: string;
}): Promise<OfficeAppointmentRow> =>
  apiPostObject<OfficeAppointmentRow>(APPOINTMENTS, payload, tenantOpts());

/** «ابعت تأكيد»: يكتب صفَّ السجلّ ويُعيد النصَّ والرقم لفتح واتساب به. */
export const confirmAppointment = (
  id: number,
  body?: string,
): Promise<AppointmentConfirmation> =>
  apiPostObject<AppointmentConfirmation>(
    `${APPOINTMENTS}${id}/confirm/`, body ? { body } : {}, tenantOpts(),
  );

export const rescheduleAppointment = (
  id: number,
  scheduledAt: string,
  note?: string,
): Promise<{ appointment: OfficeAppointmentRow }> =>
  apiPostObject(
    `${APPOINTMENTS}${id}/reschedule/`,
    { scheduled_at: scheduledAt, note },
    tenantOpts(),
  );

export const cancelAppointment = (
  id: number,
): Promise<{ appointment: OfficeAppointmentRow }> =>
  apiPostObject(`${APPOINTMENTS}${id}/cancel/`, {}, tenantOpts());

export const completeAppointment = (
  id: number,
): Promise<{ appointment: OfficeAppointmentRow }> =>
  apiPostObject(`${APPOINTMENTS}${id}/done/`, {}, tenantOpts());

// ── دفترُ الزبون (#286/ب) ────────────────────────────────────────────────────
//
// مرآةُ `OfficeClientBookViewSet`: مسارُه مفتاحُه **معرّفُ الزبون** لا معرّفُ
// الدفتر (دفترٌ واحد لكل زبون)، ولا سنةَ إلا في قائمة الحركات — الغيابُ «كلُّ
// السنوات»، وهو ما يحتاجه اشتقاقُ «للإدخال» (ورقةٌ قد تُدخل بحركةٍ في سنة أخرى).
// والقوائمُ تُقرأ بـ`apiGetObject` لا `apiGetList`: كاشُ الأوفلاين على حركاتٍ
// ودفترٍ يُظهر تاريخاً قديماً في شاشةٍ تُكتب فيها — والقراءةُ يجب أن تكون حيّة.

/** بندٌ في طلب إنشاء الحركة — **`null` للمبلغ الفارغ**: الخادم يرفض `''` 400. */
export interface BookEntryLineWrite {
  account_code: string;
  debit: string | null;
  credit: string | null;
  side_party: string;
}

export interface BookEntryWrite {
  entry_date: string;
  kind: string;
  memo?: string;
  documents?: number[];
  lines: BookEntryLineWrite[];
}

/** كلُّ دفترٍ يراه العضو — بلا قوائم الأنواع (المسارُ المفرد وحده يحملها). */
export const listClientBooks = (): Promise<ClientBookRow[]> =>
  apiGetObject<ClientBookRow[]>(CLIENT_BOOKS, tenantOpts());

/** دفترُ زبونٍ واحد — و404 حين لا دفترَ له (خدمةُ مسك الدفاتر ليست نشطة). */
export const getClientBook = (clientId: number): Promise<ClientBookRow> =>
  apiGetObject<ClientBookRow>(`${CLIENT_BOOKS}${clientId}/`, tenantOpts());

/**
 * تسمياتُ الأنواع الثلاثة من النموذج: نوعا الدفتر، وأنواعُ الحركة، وأنواعُ الحساب.
 *
 * `book_kinds` **لا يحملها أيّ ردٍّ آخر**: `kind_label` في سطر الدفتر يسمّي النوعَ
 * الحاليَّ وحده، وهذه تحتاجها شاشةُ الفتح ومنتقي الانتقال معاً.
 */
export const getClientBookChoices = (): Promise<ClientBookChoicesPayload> =>
  apiGetObject<ClientBookChoicesPayload>(`${CLIENT_BOOKS}choices/`, tenantOpts());

/** دفترٌ جديد لزبونٍ بلا دفتر — بمفتاح `office.clients.write`، والشروطُ تحكمها الخدمة. */
export const createClientBook = (payload: {
  client_id: number;
  kind: string;
  opened_on?: string;
}): Promise<ClientBookRow> =>
  apiPostObject<ClientBookRow>(CLIENT_BOOKS, payload, tenantOpts());

/** شجرةُ حساب الزبون — تُقرأ لكل من يرى الزبون. */
export const listBookAccounts = (clientId: number): Promise<BookAccountRow[]> =>
  apiGetObject<BookAccountRow[]>(`${CLIENT_BOOKS}${clientId}/accounts/`, tenantOpts());

/** حسابٌ يضيفه المكتب لشجرة زبون — بمفتاح `office.clients.write`. */
export const addBookAccount = (
  clientId: number,
  payload: {
    code: string;
    name: string;
    parent_code?: string;
    account_type: string;
  },
): Promise<BookAccountRow> =>
  apiPostObject<BookAccountRow>(
    `${CLIENT_BOOKS}${clientId}/accounts/`, payload, tenantOpts(),
  );

/** حركاتُ الدفتر — بلا `year` تُعاد كلُّ السنوات. */
export const listBookEntries = (
  clientId: number,
  year?: number,
): Promise<BookEntryRow[]> =>
  apiGetObject<BookEntryRow[]>(`${CLIENT_BOOKS}${clientId}/entries/`, {
    ...tenantOpts(),
    query: { year: year ?? undefined },
  });

/** إدخالُ حركة — الرقمُ والتوازنُ والترقيمُ أحكامُ خادمٍ لا واجهة. */
export const createBookEntry = (
  clientId: number,
  payload: BookEntryWrite,
): Promise<BookEntryRow> =>
  apiPostObject<BookEntryRow>(
    `${CLIENT_BOOKS}${clientId}/entries/`, payload, tenantOpts(),
  );

/** التصحيحُ بحركةٍ عكسية — الأصلُ يبقى، وأوراقُه تعود إلى «للإدخال». */
export const reverseBookEntry = (
  clientId: number,
  entryId: number,
  payload: { memo?: string; entry_date?: string | null } = {},
): Promise<BookEntryRow> =>
  apiPostObject<BookEntryRow>(
    `${CLIENT_BOOKS}${clientId}/entries/${entryId}/reverse/`, payload, tenantOpts(),
  );

/** انتقالُ نوع الدفتر — الشروطُ الثلاثةُ في الخدمة، والرسالةُ تصل من الخادم. */
export const changeClientBookKind = (
  clientId: number,
  kind: string,
): Promise<ClientBookRow> =>
  apiPostObject<ClientBookRow>(
    `${CLIENT_BOOKS}${clientId}/kind/`, { kind }, tenantOpts(),
  );

/**
 * «للإدخال»: أوراقٌ واصلةٌ بلا حركةٍ حيّة، مجمَّعةً بالزبون والشهر — مشتقّةً في
 * الخادم. **تُقرأ في شاشة «اليوم» وحدها** (`total` للعدّاد، والصفوفُ لكبستها)؛
 * وأوراقُ شهرٍ داخل تبويب الدفتر تُشتقّ من شبكة الأوراق لا من هنا.
 */
export const getPendingEntry = (): Promise<PendingEntryPayload> =>
  apiGetObject<PendingEntryPayload>(`${CLIENT_BOOKS}pending-entry/`, tenantOpts());

// ── تقاريرُ دفتر الزبون ومستخرجاتها (#288/ب-١) ──────────────────────────────
//
// **ولا حسابَ في الواجهة**: الأنواعُ والأرقامُ والمجاميعُ من الخادم، وهذه الطبقةَ
// تنقل الطلبَ وتردّ ما وصل. و«PDF» يُصنع من حوار الطباعة في المتصفح: الخادمُ
// يُصيِّر الورقة، والواجهةُ تفتحها في نافذةٍ تطبع نفسها.

/**
 * فترةُ التقرير في استعلام — `from`/`to` فقط، وبلا `?` حين تخلو.
 *
 * `apiGetForBlob` لا يعرف `query` (بايتاتٌ لا JSON)، فالسلسلةُ تُبنى هنا بدل
 * توسيع توقيعٍ مشتركٍ لنداءٍ واحد.
 */
const periodQuery = (period: BookReportPeriod): string => {
  const query = new URLSearchParams();
  if (period.from) query.set('from', period.from);
  if (period.to) query.set('to', period.to);
  const text = query.toString();
  return text ? `?${text}` : '';
};

/** الأنواعُ المتاحةُ لنوع دفتر هذا الزبون — القاعدةُ في الخادم لا في الشاشة. */
export const getClientBookReports = (
  clientId: number,
): Promise<ClientBookReportsPayload> =>
  apiGetObject<ClientBookReportsPayload>(
    `${CLIENT_BOOKS}${clientId}/reports/`, tenantOpts(),
  );

/** تقريرٌ واحدٌ ملفَّ Excel — بايتاتٌ تُنزَّل مباشرةً. */
export const downloadClientBookReportXlsx = (
  clientId: number,
  kind: string,
  period: BookReportPeriod,
): Promise<Blob> =>
  apiGetForBlob(
    `${CLIENT_BOOKS}${clientId}/reports/${kind}/export.xlsx${periodQuery(period)}`,
    tenantOpts(),
  );

/** الدفترُ كاملاً: مصنَّفٌ فيه ورقةٌ لكل تقريرٍ متاح. */
export const downloadClientBookXlsx = (
  clientId: number,
  period: BookReportPeriod,
): Promise<Blob> =>
  apiGetForBlob(
    `${CLIENT_BOOKS}${clientId}/export.xlsx${periodQuery(period)}`, tenantOpts(),
  );

/** ورقةُ التقرير HTML كما يصيِّرها الخادم — تُكتب في نافذةٍ تطبع نفسها. */
export const getClientBookReportPrint = (
  clientId: number,
  kind: string,
  period: BookReportPeriod,
): Promise<string> =>
  apiGetForText(
    `${CLIENT_BOOKS}${clientId}/reports/${kind}/print/${periodQuery(period)}`,
    tenantOpts(),
  );

/**
 * رابطُ مشاركةٍ للتقرير — `POST` بمفتاح الكتابة، ويردّ 400 إن أُطفئ إعدادُ
 * «رابط PDF للتقارير» برسالةٍ عربية من الخادم (`humanizeThrown` يعرضها).
 */
export const shareClientBookReport = (
  clientId: number,
  kind: string,
  period: BookReportPeriod,
): Promise<ClientBookReportShare> =>
  apiPostObject<ClientBookReportShare>(
    `${CLIENT_BOOKS}${clientId}/reports/${kind}/share/`, { ...period }, tenantOpts(),
  );


// ── المستندان (#283/ب): إشعارُ القبض وكشفُ الحساب ───────────────────────────
//
// **الطباعةُ بياناتٌ لا صفحة**: `.../print/` يعيد الحمولة، والواجهةُ تُصيِّرها
// بـ`utils/printReport.ts` كسائر شاشات الطباعة — لأن تبويباً جديداً على مسار
// خادمٍ لا يحمل ترويسةَ المصادقة فيردّ 401. والرابطُ العامّ (`share`) للمشاركة.
//
// وكلُّ مبلغٍ `string | null`: `DecimalField` يُسلسَل نصّاً، و`null` تعني «لا
// رؤيةَ للمبالغ» (#272) فتعرض الشاشة «—» ولا تحوّله إلى صفر.

/** سطرُ دفعةٍ من `fees/payments/` — شكلُ `payments.payment_row` كما هو. */
export interface FeePaymentRow {
  id: number;
  client: { id: number; name: string };
  method: string;
  method_label: string;
  amount: string | null;
  paid_at: string;
  note: string;
  /** الرقمُ المخزَّن من `FeeReceiptSequence` — يُقرأ ولا يُولَّد عند العرض. */
  receipt_number: string;
  created_by: { id: number; name: string } | null;
  created_at: string;
  allocations: {
    id: number;
    draft: { id: number; year: number; month: number };
    amount: string | null;
  }[];
  due: string | null;
  credit: string | null;
  journal_entry: number | null;
}

/** حمولةُ الإشعار المطبوعة — `receipt_payload` في الخادم. */
export interface FeeReceiptPayload {
  title: string;
  number: string;
  date: string;
  client: { id: number; name: string };
  amount: string | null;
  method: string;
  method_label: string;
  /** ورقةُ الشيك في الدفاتر إن وُجدت — `null` لغير الشيك أو دفعةٍ بلا ترحيل. */
  cheque: { number: string; bank_name: string; due_date: string | null } | null;
  note: string;
  allocations: { draft: number; period_label: string; amount: string | null }[];
  due: string | null;
  credit: string | null;
  office: { name: string };
}

/** حركةٌ في كشف الحساب: فاتورةٌ (+) أو دفعةٌ/شطبٌ (−) ورصيدُها الجاري. */
export interface FeeStatementMovement {
  kind: string;
  kind_label: string;
  id: number;
  date: string;
  label: string;
  amount: string | null;
  balance: string | null;
}

/** حمولةُ كشف الحساب المطبوعة — `statement_payload` في الخادم. */
export interface FeeStatementPayload {
  title: string;
  client: { id: number; name: string };
  from: string | null;
  to: string | null;
  opening_balance: string | null;
  closing_balance: string | null;
  due: string | null;
  credit: string | null;
  totals: {
    invoices: string | null;
    payments: string | null;
    write_offs: string | null;
    movements: string | null;
  };
  rows: FeeStatementMovement[];
  groups: {
    invoices: Record<string, unknown>[];
    payments: Record<string, unknown>[];
    write_offs: Record<string, unknown>[];
  };
  office: { name: string };
}

/** رابطٌ عامٌّ حيٌّ لمستند أتعاب — `{url, expires_at}` من `docshare`. */
export interface FeeDocumentShare {
  url: string;
  expires_at: string;
}

/** دفعاتُ الزبون — تُقرأ بفلتر `client` وحده (والترقيمُ في الاستعلام). */
export const listFeePayments = (clientId?: number): Promise<FeePaymentRow[]> =>
  apiGetObject<FeePaymentRow[]>(FEE_PAYMENTS, {
    ...tenantOpts(),
    query: { client: clientId },
  });

/** بياناتُ إشعار القبض للطباعة — **لا تُستهلك رقمٌ** عندها. */
export const printFeePayment = (paymentId: number): Promise<FeeReceiptPayload> =>
  apiGetObject<FeeReceiptPayload>(`${FEE_PAYMENTS}${paymentId}/print/`, tenantOpts());

/** رابطُ الإشعار العامّ — يُعاد الحيّ القائم إن وُجد. */
export const shareFeePayment = (paymentId: number): Promise<FeeDocumentShare> =>
  apiPostObject<FeeDocumentShare>(
    `${FEE_PAYMENTS}${paymentId}/share/`, {}, tenantOpts(),
  );

/** كشفُ حساب الزبون لفترة — `period_from`/`period_to` اختياريان (كلُّ الحركات). */
export const printFeeStatement = (
  clientId: number,
  period?: { periodFrom?: string; periodTo?: string },
): Promise<FeeStatementPayload> =>
  apiGetObject<FeeStatementPayload>(`${FEE_LEDGER}print/`, {
    ...tenantOpts(),
    query: {
      client: clientId,
      period_from: period?.periodFrom,
      period_to: period?.periodTo,
    },
  });

/** إصدارُ كشف حسابٍ ورابطِه العامّ — الصفُّ يُكتب في الخادم مع الرابط. */
export const shareFeeStatement = (
  clientId: number,
  period?: { periodFrom?: string; periodTo?: string },
): Promise<FeeDocumentShare> =>
  apiPostObject<FeeDocumentShare>(
    `${FEE_LEDGER}share/`,
    {
      client: clientId,
      period_from: period?.periodFrom,
      period_to: period?.periodTo,
    },
    tenantOpts(),
  );
