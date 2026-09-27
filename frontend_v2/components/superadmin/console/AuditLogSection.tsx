import React, { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  listPlatformAudit, type AuditSeverity, type PlatformAuditFilters, type PlatformAuditResponse,
} from "../../../services/platformAdminApi";
import { formatDateTimeValue } from "../../../utils/formatDate";
import { formatNumber } from "../../../utils/formatNumber";
import { ErrorBox, LoadingRow, Pill, SectionHeader, companyPath, errorText } from "./consoleShared";

const SEVERITY_LABELS: Record<AuditSeverity, string> = {
  info: "عادي",
  warning: "تنبيه",
  high: "عالي الخطورة",
};

const SEVERITY_TONES: Record<AuditSeverity, string> = {
  info: "",
  warning: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
  high: "border-red-300 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300",
};

const EMPTY: PlatformAuditFilters = { page: 1, action: "", severity: "", date_from: "", date_to: "", q: "" };

/** التفاصيل المخزّنة كقيم مقروءة: «المفتاح: القيمة» — لا JSON خام أمام القارئ. */
const metadataText = (metadata: Record<string, unknown>) =>
  Object.entries(metadata ?? {})
    .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
    .join(" · ");

/**
 * SA-1/SA-5 — سجل تدقيق المنصة: كل فعلٍ لفريق كترا على الشركات والمنصة (منح، إيقاف،
 * خطط، حدود، دخول دعم، دخول فاشل). للقراءة فقط — السجلّ لا يُعدَّل ولا يُحذف في الخادم.
 */
export const AuditLogSection: React.FC = () => {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<PlatformAuditFilters>(EMPTY);
  const [data, setData] = useState<PlatformAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (current: PlatformAuditFilters) => {
    setLoading(true);
    setError(null);
    try {
      setData(await listPlatformAudit(current));
    } catch (cause) {
      setError(errorText(cause, "تعذّر تحميل سجل التدقيق"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(filters); }, [filters, load]);

  // البحث النصّي يُرسَل بعد توقّف الكتابة — لا نداءً لكل حرف.
  const [search, setSearch] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => (current.q === search ? current : { ...current, q: search, page: 1 }));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [search]);

  const patch = (next: Partial<PlatformAuditFilters>) => setFilters((current) => ({ ...current, ...next, page: next.page ?? 1 }));
  const pages = data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1;
  const page = filters.page ?? 1;

  return (
    <div>
      <SectionHeader
        title="سجل التدقيق"
        subtitle="كل ما فعله فريق كترا على المنصة والشركات — لا يُعدَّل ولا يُحذف"
        loading={loading}
        onRefresh={() => void load(filters)}
      />
      <div className="mb-3 flex flex-wrap items-end gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
        <input
          aria-label="بحث في السجل"
          className="ktra-input h-9 min-w-56 flex-1"
          placeholder="ابحث باسم الفاعل أو الشركة أو السبب"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select aria-label="الحدث" className="ktra-input h-9" value={filters.action ?? ""} onChange={(event) => patch({ action: event.target.value })}>
          <option value="">كل الأحداث</option>
          {(data?.events ?? []).map((event) => <option key={event.action} value={event.action}>{event.label}</option>)}
        </select>
        <select aria-label="الخطورة" className="ktra-input h-9" value={filters.severity ?? ""} onChange={(event) => patch({ severity: event.target.value })}>
          <option value="">كل الدرجات</option>
          {(Object.keys(SEVERITY_LABELS) as AuditSeverity[]).map((key) => <option key={key} value={key}>{SEVERITY_LABELS[key]}</option>)}
        </select>
        <label className="text-xs ktra-text-soft">
          من
          <input type="date" className="ktra-input mr-1 h-9" value={filters.date_from ?? ""} onChange={(event) => patch({ date_from: event.target.value })} />
        </label>
        <label className="text-xs ktra-text-soft">
          إلى
          <input type="date" className="ktra-input mr-1 h-9" value={filters.date_to ?? ""} onChange={(event) => patch({ date_to: event.target.value })} />
        </label>
      </div>
      <ErrorBox message={error} onRetry={() => void load(filters)} />

      {loading && !data ? <LoadingRow /> : data && (
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
          <table className="w-full min-w-[980px] text-sm">
            <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
              <tr>
                <th className="px-3 py-2 text-right">الوقت</th>
                <th className="px-3 py-2 text-right">الحدث</th>
                <th className="px-3 py-2 text-right">الفاعل</th>
                <th className="px-3 py-2 text-right">الشركة / المستخدم</th>
                <th className="px-3 py-2 text-right">السبب والتفاصيل</th>
                <th className="px-3 py-2 text-right">العنوان</th>
              </tr>
            </thead>
            <tbody>
              {data.results.length === 0 ? (
                <tr><td colSpan={6} className="px-3 py-10 text-center ktra-text-soft">لا أحداث تطابق هذا البحث</td></tr>
              ) : data.results.map((row) => (
                <tr key={row.id} className="border-t border-[var(--color-border)] align-top">
                  <td className="px-3 py-2 whitespace-nowrap">{formatDateTimeValue(row.created_at)}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col items-start gap-1">
                      <span className="font-semibold text-[var(--color-text)]">{row.action_label}</span>
                      {row.severity !== "info" && <Pill tone={SEVERITY_TONES[row.severity]}>{SEVERITY_LABELS[row.severity]}</Pill>}
                    </div>
                  </td>
                  <td className="px-3 py-2">{row.actor || "—"}</td>
                  <td className="px-3 py-2">
                    {row.tenant_id ? (
                      <button type="button" onClick={() => navigate(companyPath(row.tenant_id as number))} className="hover:underline">{row.tenant}</button>
                    ) : row.tenant || "—"}
                    {row.target_user && <span className="block text-xs ktra-text-soft">{row.target_user}</span>}
                  </td>
                  <td className="px-3 py-2">
                    {row.reason && <span className="block">{row.reason}</span>}
                    {Object.keys(row.metadata ?? {}).length > 0 && (
                      <span className="block text-xs ktra-text-soft">{metadataText(row.metadata)}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs ktra-text-soft" title={row.trace_id ? `Trace ID: ${row.trace_id}` : undefined}>
                    {row.ip_address || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-[var(--color-border)] px-4 py-2 text-xs ktra-text-soft">
            <span>{formatNumber(data.count)} حدث · صفحة {formatNumber(page)} من {formatNumber(pages)}</span>
            <div className="flex gap-1">
              <button type="button" className="ktra-iconbtn" disabled={page <= 1} onClick={() => patch({ page: page - 1 })} aria-label="الصفحة السابقة">
                <ChevronRight className="h-4 w-4" />
              </button>
              <button type="button" className="ktra-iconbtn" disabled={page >= pages} onClick={() => patch({ page: page + 1 })} aria-label="الصفحة التالية">
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
