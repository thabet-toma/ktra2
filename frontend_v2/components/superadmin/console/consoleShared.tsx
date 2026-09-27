import React from "react";
import { Loader2, RefreshCw } from "lucide-react";

import type { SupportAccessGrant } from "../../../services/platformAdminApi";
import { clientLogger } from "../../../services/logger";
import { storedTenantId } from "../../../utils/tenantContext";
import { writeSupportSession } from "../../../utils/supportSession";
import { formatNumber } from "../../../utils/formatNumber";

/** SA-5 — مسارات لوحة المنصة: كلها تحت `/super-admin/*` ويرسمها `SuperAdminConsole`. */
export const CONSOLE_BASE = "/super-admin";
export const consolePath = (section = "") => (section ? `${CONSOLE_BASE}/${section}` : CONSOLE_BASE);
export const companyPath = (companyId: number, tab?: string) =>
  `${CONSOLE_BASE}/companies/${companyId}${tab ? `?tab=${tab}` : ""}`;

export const errorText = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

/** رأس كل قسم: عنوان + شرح سطر + أزرار (تحديث وغيره) في مكانٍ واحد ثابت. */
export const SectionHeader: React.FC<{
  title: string;
  subtitle?: string;
  loading?: boolean;
  onRefresh?: () => void;
  children?: React.ReactNode;
}> = ({ title, subtitle, loading, onRefresh, children }) => (
  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
    <div>
      <h2 className="text-lg font-bold text-[var(--color-text)]">{title}</h2>
      {subtitle && <p className="text-sm ktra-text-soft">{subtitle}</p>}
    </div>
    <div className="flex flex-wrap items-center gap-2">
      {children}
      {onRefresh && (
        <button type="button" onClick={onRefresh} className="ktra-iconbtn" title="تحديث" aria-label={`تحديث ${title}`}>
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      )}
    </div>
  </div>
);

export const ErrorBox: React.FC<{ message: string | null; onRetry?: () => void }> = ({ message, onRetry }) =>
  message ? (
    <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      <span>{message}</span>
      {onRetry && <button type="button" onClick={onRetry} className="ktra-btn">إعادة المحاولة</button>}
    </div>
  ) : null;

export const LoadingRow: React.FC<{ label?: string }> = ({ label = "جارٍ التحميل…" }) => (
  <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm ktra-text-soft">
    <Loader2 className="h-4 w-4 animate-spin" /> {label}
  </div>
);

export const Panel: React.FC<{ label: string; className?: string; children: React.ReactNode }> = ({ label, className = "", children }) => (
  <section aria-label={label} className={`overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] ${className}`}>
    {children}
  </section>
);

export const PanelHead: React.FC<{ title: string; hint?: string; children?: React.ReactNode }> = ({ title, hint, children }) => (
  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-3">
    <div>
      <h3 className="font-bold text-[var(--color-text)]">{title}</h3>
      {hint && <p className="text-xs ktra-text-soft">{hint}</p>}
    </div>
    {children}
  </div>
);

/** بطاقة رقم: عنوان + قيمة + سطر شرح، ويمكن أن تكون زرّاً ينقل إلى تفصيلها. */
export const StatCard: React.FC<{
  label: string;
  value: string;
  hint?: string;
  icon: React.ElementType;
  tone: string;
  onClick?: () => void;
}> = ({ label, value, hint, icon: Icon, tone, onClick }) => {
  const body = (
    <>
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${tone}`}>
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 text-right">
        <p className="text-xs ktra-text-soft">{label}</p>
        <p className="text-2xl font-bold text-[var(--color-text)]">{value}</p>
        {hint && <p className="text-[11px] ktra-text-soft">{hint}</p>}
      </div>
    </>
  );
  const frame = "flex w-full items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4";
  return onClick ? (
    <button type="button" onClick={onClick} className={`${frame} transition-colors hover:border-[var(--color-primary)]`}>{body}</button>
  ) : (
    <article className={frame}>{body}</article>
  );
};

/** خمسة أسماء ثم «+N» — البطاقة تقول مَن، لا تستنسخ الجدول. */
const MAX_LISTED = 5;

export interface InsightEntry {
  id: number;
  name: string;
  hint: string;
  title?: string;
}

export const InsightList: React.FC<{ rows: InsightEntry[]; empty: string; onOpen?: (id: number) => void }> = ({ rows, empty, onOpen }) => {
  if (rows.length === 0) return <p className="mt-2 text-xs ktra-text-soft">{empty}</p>;
  const shown = rows.slice(0, MAX_LISTED);
  const rest = rows.length - shown.length;
  return (
    <ul className="mt-2 space-y-1">
      {shown.map((row) => (
        <li key={row.id} className="flex items-center justify-between gap-2 text-xs" title={row.title}>
          {onOpen ? (
            <button type="button" onClick={() => onOpen(row.id)} className="truncate text-right text-[var(--color-text)] hover:underline">{row.name}</button>
          ) : (
            <span className="truncate text-[var(--color-text)]">{row.name}</span>
          )}
          <span className="shrink-0 ktra-text-soft">{row.hint}</span>
        </li>
      ))}
      {rest > 0 && <li className="text-xs ktra-text-soft">+{formatNumber(rest)} شركة أخرى</li>}
    </ul>
  );
};

export const InsightCard: React.FC<{
  title: string;
  value: string;
  caption: string;
  icon: React.ElementType;
  tone: string;
  children: React.ReactNode;
}> = ({ title, value, caption, icon: Icon, tone, children }) => (
  <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
    <div className="flex items-center gap-3">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${tone}`}>
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-xs ktra-text-soft">{title}</p>
        <p className="text-2xl font-bold text-[var(--color-text)]">{value}</p>
      </div>
    </div>
    <p className="mt-2 text-[11px] ktra-text-soft">{caption}</p>
    {children}
  </article>
);

export const STATUS_TONES: Record<string, string> = {
  Active: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
  Trial: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300",
  Suspended: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300",
};

export const Pill: React.FC<{ tone?: string; title?: string; children: React.ReactNode }> = ({ tone, title, children }) => (
  <span
    title={title}
    className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold ${tone || "border-[var(--color-border)] bg-[var(--color-surface-2)] ktra-text-soft"}`}
  >
    {children}
  </span>
);

/**
 * دخول الشركة بإذن دعمٍ ساري (SA-7): تُحفظ الجلسة والشركة الحالية للعودة، ثم تحميلٌ
 * كامل كي يُحلّ كل سياق الشركة (صلاحيات، فروع، وحدات) من جديد تحت الإذن.
 */
export const enterSupportSession = (grant: SupportAccessGrant) => {
  if (!grant.expires_at || (grant.scope !== "read_only" && grant.scope !== "full")) return;
  writeSupportSession({
    grantId: grant.id,
    tenantId: grant.tenant_id,
    tenantName: grant.tenant_name,
    scope: grant.scope,
    isEmergency: grant.is_emergency,
    expiresAt: grant.expires_at,
    returnTenantId: storedTenantId(),
  });
  localStorage.setItem("tenantId", String(grant.tenant_id));
  localStorage.removeItem("branchId");
  clientLogger.info("support_access.session_entered", { grantId: grant.id, tenantId: grant.tenant_id });
  window.location.assign("/dashboard");
};
