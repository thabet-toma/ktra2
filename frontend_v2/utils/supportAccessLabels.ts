/** SA-2/SA-8 — تسميات إذن دخول فريق كترا: مصدرٌ واحد لشاشة المنصة وشاشة الشركة. */

export const SUPPORT_SCOPE_LABELS: Record<string, string> = {
  read_only: "قراءة فقط",
  full: "كامل (قراءة وتعديل)",
};

export const SUPPORT_STATUS_LABELS: Record<string, string> = {
  pending: "بانتظار موافقة الشركة",
  active: "ساري",
  rejected: "مرفوض",
  revoked: "مسحوب",
  cancelled: "ملغى",
  expired: "منتهٍ",
};

/** المدد المسموحة في الخادم (`DURATION_HOURS`) — الافتراض 24 ساعة. نصوصها نفسها في
 * بريد الشركة (`core/support_access.py` — `_hours_label`) والنطاق من `SupportAccessGrant.SCOPES`. */
export const SUPPORT_DURATIONS: { hours: number; label: string }[] = [
  { hours: 4, label: "4 ساعات" },
  { hours: 24, label: "يوم واحد" },
  { hours: 168, label: "أسبوع" },
];

export const SUPPORT_DEFAULT_HOURS = 24;

export const supportDurationLabel = (hours: number): string =>
  SUPPORT_DURATIONS.find((row) => row.hours === hours)?.label ?? `${hours} ساعة`;

/** ألوان الحالة (Tailwind) — الساري أخضر، المعلّق كهرماني، والباقي رمادي. */
export const supportStatusTone = (status: string): string => {
  if (status === "active") return "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300";
  if (status === "pending") return "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300";
  if (status === "rejected" || status === "revoked") return "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300";
  return "border-[var(--color-border)] bg-[var(--color-surface-2)] ktra-text-soft";
};
