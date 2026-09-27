import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, Plus, Search, TriangleAlert } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  getPlatformDashboard, getPlatformUsage, updatePlatformCompany,
  type PlatformDashboardData, type PlatformUsageResponse,
} from "../../../services/platformAdminApi";
import { useToast } from "../../../contexts/ToastContext";
import { COMPANY_STATUS_LABELS } from "../PlatformCompanyPanel";
import { formatBytes } from "../../../utils/formatBytes";
import { formatDateTimeValue, formatDateValue } from "../../../utils/formatDate";
import { formatNumber } from "../../../utils/formatNumber";
import {
  filterCompanies, filterFromSearch, isEnding, type CompanyFilter, type ConsoleUsage,
} from "../../../utils/platformConsole";
import {
  ErrorBox, LoadingRow, Pill, STATUS_TONES, SectionHeader, companyPath, errorText,
} from "./consoleShared";
import { CreateCompanyDialog } from "./CreateCompanyDialog";

const activityLabel = (value: string | null) => (value ? formatDateValue(value) : "لا نشاط مسجَّل");

/**
 * SA-6 — جدول الشركات: بحث بالاسم أو الرقم، وفلاتر (حالة، خطة، خاملة، قرب الحد،
 * تنتهي قريباً)، وترتيب بالحجم. الصف يفتح صفحة الشركة الكاملة — لا نافذة فوق جدول.
 * الفلتر يسكن الرابط (`?status=…`) فبطاقات «نظرة عامة» تفتحه جاهزاً ويُحفظ ويُشارَك.
 */
export const CompaniesSection: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [data, setData] = useState<PlatformDashboardData | null>(null);
  const [usage, setUsage] = useState<PlatformUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [assigningExample, setAssigningExample] = useState(false);
  const [creating, setCreating] = useState(false);
  const filter = useMemo(() => filterFromSearch(location.search), [location.search]);

  const load = useCallback(async (refreshUsage = false) => {
    setLoading(true);
    setError(null);
    const [dashboard, usageResult] = await Promise.allSettled([
      getPlatformDashboard(), getPlatformUsage(refreshUsage),
    ]);
    if (dashboard.status === "fulfilled") setData(dashboard.value);
    else setError(errorText(dashboard.reason, "تعذّر تحميل الشركات"));
    if (usageResult.status === "fulfilled") setUsage(usageResult.value);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const setFilter = (patch: Partial<CompanyFilter>) => {
    const next = { ...filter, ...patch };
    const params = new URLSearchParams();
    if (next.q) params.set("q", next.q);
    if (next.status) params.set("status", next.status);
    if (next.plan) params.set("plan", next.plan);
    if (next.flag) params.set("filter", next.flag);
    if (next.sort !== "created") params.set("sort", next.sort);
    const query = params.toString();
    navigate(`${location.pathname}${query ? `?${query}` : ""}`, { replace: true });
  };

  const usageById = useMemo(() => {
    const map = new Map<number, ConsoleUsage>();
    usage?.results?.forEach((row) => map.set(row.tenant_id, row));
    return map;
  }, [usage]);

  const rows = useMemo(
    () => (data ? filterCompanies(data.company_rows, usageById, filter) : []),
    [data, usageById, filter],
  );

  const assignExampleCompany = async (value: string) => {
    const current = data?.company_rows.find((company) => company.is_example);
    const nextId = value ? Number(value) : null;
    if ((current?.id ?? null) === nextId) return;
    setAssigningExample(true);
    try {
      if (nextId !== null) {
        await updatePlatformCompany(nextId, { is_example: true });
        toast("تم تعيين شركة المثال وإتاحتها لكل المستخدمين", "success");
      } else if (current) {
        await updatePlatformCompany(current.id, { is_example: false });
        toast("تم إلغاء تعيين شركة المثال", "success");
      }
      await load();
    } catch (cause) {
      toast(errorText(cause, "تعذّر تعيين شركة المثال"), "error");
    } finally {
      setAssigningExample(false);
    }
  };

  if (loading && !data) return <LoadingRow label="جارٍ تحميل الشركات…" />;
  if (!data) return <ErrorBox message={error} onRetry={() => void load()} />;

  return (
    <div>
      <SectionHeader
        title="الشركات"
        subtitle={`${formatNumber(data.companies.total)} شركة · ${formatNumber(data.memberships)} عضوية — الصف يفتح صفحة الشركة`}
        loading={loading}
        onRefresh={() => void load(true)}
      >
        <label htmlFor="platform-example-company" className="sr-only">الشركة المثال</label>
        <select
          id="platform-example-company"
          className="ktra-input h-9 min-w-48"
          value={data.company_rows.find((company) => company.is_example)?.id ?? ""}
          disabled={assigningExample}
          onChange={(event) => void assignExampleCompany(event.target.value)}
          title="الشركة المثال — تُتاح لكل المستخدمين للتجربة"
        >
          <option value="">بدون شركة مثال</option>
          {data.company_rows.map((company) => (
            <option key={company.id} value={company.id}>مثال: {company.name}</option>
          ))}
        </select>
        <button type="button" className="ktra-btn ktra-btn-primary" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" aria-hidden="true" /> إنشاء شركة لعميل
        </button>
      </SectionHeader>
      <ErrorBox message={error} />
      <CreateCompanyDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(companyId) => { setCreating(false); navigate(companyPath(companyId)); }}
      />

      <div className="mb-3 flex flex-wrap items-end gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
        <div className="relative min-w-56 flex-1">
          <label htmlFor="companies-search" className="sr-only">بحث</label>
          <Search className="pointer-events-none absolute right-2.5 top-2.5 h-4 w-4 ktra-text-soft" aria-hidden="true" />
          <input
            id="companies-search"
            className="ktra-input h-9 w-full pr-8"
            placeholder="ابحث باسم الشركة أو رقمها"
            value={filter.q}
            onChange={(event) => setFilter({ q: event.target.value })}
          />
        </div>
        <select aria-label="الحالة" className="ktra-input h-9" value={filter.status} onChange={(event) => setFilter({ status: event.target.value })}>
          <option value="">كل الحالات</option>
          {Object.entries(COMPANY_STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select aria-label="الخطة" className="ktra-input h-9" value={filter.plan} onChange={(event) => setFilter({ plan: event.target.value })}>
          <option value="">كل الخطط</option>
          {(data.plan_choices ?? []).map((choice) => <option key={choice.key} value={choice.key}>{choice.label}</option>)}
        </select>
        <select aria-label="تنبيه" className="ktra-input h-9" value={filter.flag} onChange={(event) => setFilter({ flag: event.target.value as CompanyFilter["flag"] })}>
          <option value="">بلا تنبيه محدد</option>
          <option value="idle">خاملة 30 يوماً</option>
          <option value="near">قريبة من حدّ خطتها</option>
          <option value="ending">اشتراك ينتهي قريباً</option>
        </select>
        <select aria-label="الترتيب" className="ktra-input h-9" value={filter.sort} onChange={(event) => setFilter({ sort: event.target.value as CompanyFilter["sort"] })}>
          <option value="created">الأحدث إنشاءً</option>
          <option value="name">الاسم</option>
          <option value="documents">الأكثر مستندات</option>
          <option value="movements">الأكثر حركات</option>
          <option value="activity">آخر نشاط</option>
        </select>
        <span className="pb-2 text-xs ktra-text-soft">
          {formatNumber(rows.length)} من {formatNumber(data.company_rows.length)}
          {usage?.computed_at ? ` · الاستخدام محسوب ${formatDateTimeValue(usage.computed_at)}` : ""}
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <table className="w-full min-w-[1100px] text-sm">
          <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
            <tr>
              <th className="px-3 py-2 text-right">الشركة</th>
              <th className="px-3 py-2 text-right">الخطة والحالة</th>
              <th className="px-3 py-2 text-center">الأعضاء</th>
              {/* النافذة في العنوان: إجمالي تاريخي و«هذا الشهر» تحته — رقمٌ بلا نافذة يكذب بصمت. */}
              <th className="px-3 py-2 text-center">المستندات<span className="block text-[10px] font-normal">الكل / هذا الشهر</span></th>
              <th className="px-3 py-2 text-center">الحركات<span className="block text-[10px] font-normal">الكل / هذا الشهر</span></th>
              <th className="px-3 py-2 text-center">التخزين</th>
              <th className="px-3 py-2 text-right">آخر نشاط</th>
              <th className="px-3 py-2 text-right">الإنشاء</th>
              <th className="px-3 py-2" aria-label="فتح" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={9} className="px-3 py-10 text-center ktra-text-soft">لا شركات تطابق هذا البحث</td></tr>
            ) : rows.map((company) => {
              const used = usageById.get(company.id);
              return (
                <tr
                  key={company.id}
                  className="cursor-pointer border-t border-[var(--color-border)] hover:bg-[var(--color-surface-2)]"
                  onClick={() => navigate(companyPath(company.id))}
                >
                  <td className="px-3 py-2">
                    {/* المحتوى داخل عنصر ابن: قاعدة `tbody td` في `styles/index.css` تغلب أصناف الخلية. */}
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-[var(--color-text)]">{company.name}</span>
                      <span className="text-[11px] ktra-text-soft">#{company.id}</span>
                      {company.is_example && <Pill>مثال</Pill>}
                      {company.near_limit.length > 0 && (
                        <Pill
                          tone="border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                          title={company.near_limit.map((row) => `${row.label}: ${formatNumber(row.usage)} من ${formatNumber(row.limit)}`).join(" · ")}
                        >
                          <TriangleAlert className="h-3 w-3" aria-hidden="true" /> {company.near_limit[0].label}
                        </Pill>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-1">
                      <span>{company.plan_label || company.plan}</span>
                      <Pill tone={STATUS_TONES[company.status]}>{COMPANY_STATUS_LABELS[company.status] || company.status}</Pill>
                      {isEnding(company) && (
                        <Pill tone="border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                          {company.subscription_expired ? "منتهٍ" : `باقٍ ${formatNumber(company.subscription_days_left)} يوم`}
                        </Pill>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-center">{formatNumber(company.member_count)}</td>
                  <td className="px-3 py-2 text-center whitespace-nowrap">
                    {used ? `${formatNumber(used.documents_total)} / ${formatNumber(used.documents_month)}` : "—"}
                  </td>
                  <td className="px-3 py-2 text-center whitespace-nowrap">
                    {used ? `${formatNumber(used.movements_total)} / ${formatNumber(used.movements_month)}` : "—"}
                  </td>
                  <td className="px-3 py-2 text-center whitespace-nowrap" title={`${formatNumber(company.storage_asset_count)} ملف مسجَّل`}>
                    {formatBytes(company.storage_bytes)}
                  </td>
                  <td
                    className="px-3 py-2 whitespace-nowrap"
                    title={`آخر دخول: ${company.last_login_at ? formatDateValue(company.last_login_at) : "لا دخول مسجَّل"}`}
                  >{activityLabel(company.last_activity_at)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{formatDateValue(company.created_at)}</td>
                  <td className="px-3 py-2 text-center">
                    <button
                      type="button"
                      className="ktra-iconbtn"
                      aria-label={`فتح ${company.name}`}
                      onClick={(event) => { event.stopPropagation(); navigate(companyPath(company.id)); }}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
