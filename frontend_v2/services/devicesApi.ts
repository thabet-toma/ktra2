/**
 * THA-45 M2 — عميل REST لوحدة «تسجيل وتتبع الأجهزة الحساسة».
 *
 * الخادم `device_registry/views.py`: كل نقطة تفتح ببوابة الترخيص فترد **404** لا
 * 403 على شركةٍ غير مرخّصة — فالفشل هنا يُقرأ «لا وجود للوحدة»، وهو المقصود.
 *
 * الوحدة محايدة مالياً بالكامل: لا قيد ولا حساب ولا فاتورة، فلا استيراد هنا من
 * أي خدمة محاسبية ولا بثّ لأي حدث مالي.
 */
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiGetPagedList,
  apiPatchObject,
  apiPostObject,
  type PagedList,
} from "./restApi";
import { cloudinaryService } from "./cloudinaryService";
import { resolveTenantId } from "../utils/tenantContext";

const BASE = "devices/records/";

const tenantOpts = () => ({ tenantId: resolveTenantId() });

/** حالة تتبع الجهاز — مرآة `SensitiveDevice.STATUSES` في الخادم. */
export type DeviceStatus = "registered" | "in_check" | "delivered";

export const DEVICE_STATUSES: { key: DeviceStatus; label: string }[] = [
  { key: "registered", label: "مسجَّل" },
  { key: "in_check", label: "في الفحص" },
  { key: "delivered", label: "تم التسليم" },
];

export interface SensitiveDeviceRow {
  id: number;
  customer_name: string;
  customer_phone: string;
  model_name: string;
  serial_number: string;
  imei: string;
  technical_notes: string;
  photo_url: string;
  status: DeviceStatus;
  status_label: string;
  created_by: number | null;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  deleted_by_name: string;
  is_deleted: boolean;
}

/** سجل سابق بنفس الـIMEI داخل الشركة نفسها — تنبيهٌ لا منع. */
export interface DeviceDuplicateMatch {
  id: number;
  created_at: string;
  customer_name: string;
  status: DeviceStatus;
  status_label: string;
}

export interface DeviceCreateResult extends SensitiveDeviceRow {
  duplicate_of: DeviceDuplicateMatch[];
}

export interface ImeiCheckResult {
  valid: boolean;
  is_duplicate: boolean;
  matches: DeviceDuplicateMatch[];
}

export type DeviceAuditAction =
  | "register" | "update" | "status" | "delete" | "restore" | "view" | "search";

export interface DeviceAuditRow {
  id: number;
  device: number | null;
  action: DeviceAuditAction;
  action_label: string;
  actor: number | null;
  actor_name: string;
  details: Record<string, unknown>;
  ip: string;
  created_at: string;
}

export interface DeviceDraft {
  customer_name: string;
  customer_phone: string;
  model_name: string;
  serial_number: string;
  imei: string;
  technical_notes: string;
  photo_url: string;
  status?: DeviceStatus;
}

export interface DeviceListFilters {
  q?: string;
  status?: DeviceStatus | "";
  date_from?: string;
  date_to?: string;
  include_deleted?: boolean;
}

/**
 * القائمة مُرقَّمة دائماً (`page`) — سجلّ أمني لا يُحذف منه شيء ينمو بلا سقف،
 * وجلبه كاملاً في كل بحث كان سيثقل الجهاز المحمول عند الكاونتر.
 */
export function listDevices(
  filters: DeviceListFilters = {},
  page = 1,
  pageSize = 25,
): Promise<PagedList<SensitiveDeviceRow>> {
  return apiGetPagedList<SensitiveDeviceRow>(BASE, {
    ...tenantOpts(),
    query: {
      page,
      page_size: pageSize,
      q: filters.q?.trim() || undefined,
      status: filters.status || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      include_deleted: filters.include_deleted ? 1 : undefined,
    },
  });
}

export function getDevice(id: number): Promise<SensitiveDeviceRow> {
  return apiGetObject<SensitiveDeviceRow>(`${BASE}${id}/`, tenantOpts());
}

/** الإنشاء ينجح مع التكرار ويعيد `duplicate_of` — القرار للمستخدم لا للخادم. */
export function createDevice(draft: DeviceDraft): Promise<DeviceCreateResult> {
  return apiPostObject<DeviceCreateResult>(BASE, draft, tenantOpts());
}

export function updateDevice(
  id: number,
  patch: Partial<DeviceDraft>,
): Promise<SensitiveDeviceRow> {
  return apiPatchObject<SensitiveDeviceRow>(`${BASE}${id}/`, patch, tenantOpts());
}

/** حذف ناعم — الصف يبقى في الجدول ويُسترجَع بـ{@link restoreDevice}. */
export function deleteDevice(id: number): Promise<void> {
  return apiDelete(`${BASE}${id}/`, tenantOpts());
}

export function restoreDevice(id: number): Promise<SensitiveDeviceRow> {
  return apiPostObject<SensitiveDeviceRow>(`${BASE}${id}/restore/`, {}, tenantOpts());
}

/** فحص فوري: صحة الرقم + سجلات الشركة نفسها الحاملة له (لا تُرى شركة أخرى). */
export function checkImei(imei: string): Promise<ImeiCheckResult> {
  return apiGetObject<ImeiCheckResult>(
    `${BASE}check_imei/?imei=${encodeURIComponent(imei)}`,
    tenantOpts(),
  );
}

/** اقتراحات الموديل من سجلات الشركة نفسها — بلا أي ربط بمنتجات المخزون. */
export function listDeviceModelNames(): Promise<string[]> {
  return apiGetList<string>(`${BASE}model_names/`, tenantOpts());
}

export function listDeviceAudit(id: number): Promise<DeviceAuditRow[]> {
  return apiGetList<DeviceAuditRow>(`${BASE}${id}/audit/`, tenantOpts());
}

/**
 * صورة الجهاز عبر نقطة الوسائط القائمة (`POST /api/media/upload/`) — نخزّن
 * الرابط نصاً كما هو عُرف المنصة. في التطوير بلا مفاتيح Cloudinary ترد 503،
 * والصورة اختيارية فلا يتعطّل التسجيل.
 */
export function uploadDevicePhoto(file: File): Promise<string> {
  return cloudinaryService.uploadFile(file);
}
