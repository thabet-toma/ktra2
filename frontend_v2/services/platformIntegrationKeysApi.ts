/**
 * عميلُ واجهة برمجة تطبيقات مفاتيح قنوات الإدخال (التذكرة 210-E، القصة ٣١).
 *
 * الظهرُ الخلفيُّ كان جاهزاً كاملاً بلا مستدعٍ — هذا الملفُّ يفتح البابَ فقط.
 * الرمزُ الخامُّ يظهر **مرّةً واحدةً** في ردّ `issue`/`rotate` ولا يُخزَّن هنا ولا
 * يُطلَب مجدداً؛ فشلُ نسخه لا يعيد كشفه (§٢) — البديلُ الوحيدُ إصدارُ مفتاحٍ آخر.
 */
import { apiGetObject, apiPostObject } from "./restApi";

export type IntegrationChannel = "whatsapp" | "telegram" | "email" | "api" | "webhook" | "portal";
export type IntegrationKeyStatus = "active" | "revoked";

export const INTEGRATION_CHANNELS: IntegrationChannel[] = [
  "whatsapp", "telegram", "email", "api", "webhook", "portal",
];

/** خياراتُ نموذج الإصدار وحدها — العرضُ الفعليُّ لمفتاحٍ قائمٍ من `channel_display` الخادميّ دوماً. */
export const INTEGRATION_CHANNEL_FORM_LABELS: Record<IntegrationChannel, string> = {
  whatsapp: "واتساب",
  telegram: "تيليجرام",
  email: "بريد إلكتروني",
  api: "واجهة برمجية (API)",
  webhook: "ويب هوك",
  portal: "بوابة",
};

export interface IntegrationKeyRow {
  id: number;
  tenant: number;
  company_name: string;
  channel: IntegrationChannel;
  channel_display: string;
  status: IntegrationKeyStatus;
  status_display: string;
  name: string;
  revoked_at: string | null;
  revocation_reason: string;
  rotated_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IntegrationKeyIssuedRow extends IntegrationKeyRow {
  /** الرمزُ الخامُّ — يظهر في هذا الردّ وحدَه، لا في أيّ استعلامٍ لاحق. */
  raw_token: string;
}

const unwrapRows = <T>(data: { results: T[]; count?: number } | T[]): T[] =>
  Array.isArray(data) ? data : data?.results || [];

export const listIntegrationKeys = async (): Promise<IntegrationKeyRow[]> =>
  unwrapRows(
    await apiGetObject<{ results: IntegrationKeyRow[]; count?: number } | IntegrationKeyRow[]>(
      "platform/ops/integration-keys/",
    ),
  );

export const issueIntegrationKey = (input: { tenant: number; channel: IntegrationChannel; name?: string }) =>
  apiPostObject<IntegrationKeyIssuedRow>("platform/ops/integration-keys/issue/", {
    tenant: input.tenant,
    channel: input.channel,
    name: input.name || "",
  });

export const rotateIntegrationKey = (keyId: number) =>
  apiPostObject<IntegrationKeyIssuedRow>(`platform/ops/integration-keys/${keyId}/rotate/`, {});

export const revokeIntegrationKey = (keyId: number, reason: string) =>
  apiPostObject<IntegrationKeyRow>(`platform/ops/integration-keys/${keyId}/revoke/`, { reason });
