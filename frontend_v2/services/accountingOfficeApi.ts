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
  CalendarPayload,
  ClientDocumentsPayload,
  ClientEventsPayload,
  ClientEventRow,
  ClientObligationsPayload,
  ClientTaskRow,
  ClientServiceRow,
  ClientServicesPayload,
  DeadlineRuleOverrideRow,
  DeadlineRuleRow,
  DocumentFileRow,
  DocumentRowPayload,
  OfficeAlertRow,
  OfficeAlertsPayload,
  OfficeCustomRulesPayload,
  OfficeDocumentItemsPayload,
  OfficeDocumentItemRow,
  OfficeServiceRow,
  ObligationRow,
  ServicePackageRow,
  ServiceSuggestion,
  SettingRow,
  TodayFilter,
  TodayPayload,
} from '../utils/accountingOffice';

export type {
  ApplyPackageResult,
  CalendarDeadlineRow,
  CalendarPayload,
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
  EventKindChoice,
  ObligationBadge,
  ObligationRow,
  OfficeAlertRow,
  OfficeAlertsPayload,
  OfficeCustomRuleRow,
  OfficeCustomRulesPayload,
  OfficeDocumentItemRow,
  OfficeDocumentItemsPayload,
  OfficeServiceRow,
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

/**
 * تحويلُ الزبون لموظّفٍ آخر (#272) — يتطلّب `office.clients.assign` خادمياً،
 * ويُسجَّل الحدثُ في سجلّ النشاط (من ← إلى). والقراءةُ من `responsible_name`.
 */
export const assignOfficeClient = (id: number, userId: number): Promise<OfficeClientRow> =>
  apiPostObject<OfficeClientRow>(`${CLIENTS}${id}/assign/`, { user: userId }, tenantOpts());

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
