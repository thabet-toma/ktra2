import React, { useCallback, useEffect, useState } from "react";
import {
  BadgeCheck, Banknote, Building2, CalendarClock, CheckCircle2, CirclePause, FileStack,
  HardDrive, Hourglass, LifeBuoy, TriangleAlert, Users,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getPlatformDashboard, getPlatformUsage, listPendingAccountants, listPlanPricing,
  listPlatformSupportAccess,
  type PlanPricingRow, type PlatformDashboardData, type PlatformUsageResponse,
} from "../../../services/platformAdminApi";
import { formatBytes } from "../../../utils/formatBytes";
import { formatDateTimeValue, formatDateValue } from "../../../utils/formatDate";
import { formatMoney, formatNumber } from "../../../utils/formatNumber";
import {
  ErrorBox, InsightCard, InsightList, LoadingRow, SectionHeader, StatCard, companyPath,
  consolePath, errorText,
} from "./consoleShared";
import { expectedMrr, TRIAL_WARNING_DAYS } from "../../../utils/platformConsole";

/** «آخر نشاط» بلا حدث مسجَّل ليس تاريخاً فارغاً — هو خبرٌ في ذاته. */
const activityLabel = (value: string | null) => (value ? formatDateValue(value) : "لا نشاط مسجَّل");

interface Secondary {
  usage: PlatformUsageResponse | null;
  pricing: PlanPricingRow[] | null;
  pendingSupport: number | null;
  activeSupport: number | null;
  pendingAccountants: number | null;
}

const EMPTY_SECONDARY: Secondary = {
  usage: null, pricing: null, pendingSupport: null, activeSupport: null, pendingAccountants: null,
};

const settledValue = <T,>(result: PromiseSettledResult<T>): T | null =>
  result.status === "fulfilled" ? result.value : null;

/**
 * SA-5 — «نظرة عامة»: ما يحتاج انتباهاً اليوم أولاً (طلبات دعم، محاسبون،
 * تجارب تنتهي، قرب الحدود)، ثم حجم المنصة. كل رقمٍ زرٌّ إلى قائمته. النداءات
 * الثانوية تفشل وحدها ولا تُسقط اللوحة — `allSettled` لا `all`.
 */
export const OverviewSection: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<PlatformDashboardData | null>(null);
  const [secondary, setSecondary] = useState<Secondary>(EMPTY_SECONDARY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [dashboard, usage, pricing, pending, active, accountants] = await Promise.allSettled([
      getPlatformDashboard(),
      getPlatformUsage(),
      listPlanPricing(),
      listPlatformSupportAccess("pending"),
      listPlatformSupportAccess("active"),
      listPendingAccountants(),
    ]);
    if (dashboard.status === "fulfilled") setData(dashboard.value);
    else setError(errorText(dashboard.reason, "تعذّر تحميل لوحة المنصة"));
    setSecondary({
      usage: settledValue(usage),
      pricing: settledValue(pricing)?.results ?? null,
      pendingSupport: settledValue(pending)?.results?.length ?? null,
      activeSupport: settledValue(active)?.results?.length ?? null,
      pendingAccountants: settledValue(accountants)?.count ?? null,
    });
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading && !data) return <LoadingRow label="جارٍ تحميل لوحة المنصة…" />;
  if (!data) return <ErrorBox message={error} onRetry={() => void load()} />;

  const openCompany = (id: number) => navigate(companyPath(id));
  const trialsEnding = data.company_rows.filter(
    (row) => row.subscription_days_left !== null && row.subscription_days_left <= TRIAL_WARNING_DAYS
      && row.status !== "Suspended",
  );
  const mrr = Array.isArray(secondary.pricing) ? expectedMrr(data.company_rows, secondary.pricing) : null;
  const usageTotals = secondary.usage?.results?.reduce(
    (acc, row) => ({
      movements: acc.movements + row.movements_month,
      documents: acc.documents + row.documents_month,
    }),
    { movements: 0, documents: 0 },
  );
  const countOrDash = (value: number | null) => (value === null ? "—" : formatNumber(value));

  return (
    <div>
      <SectionHeader
        title="نظرة عامة"
        subtitle="ما يحتاج انتباهك اليوم، ثم حجم المنصة — كل بطاقة تفتح قائمتها"
        loading={loading}
        onRefresh={() => void load()}
      />
      <ErrorBox message={error} />

      <section aria-label="يحتاج انتباهاً" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="طلبات دخول بانتظار الشركات"
          value={countOrDash(secondary.pendingSupport)}
          hint={`أذونات سارية الآن: ${countOrDash(secondary.activeSupport)}`}
          icon={LifeBuoy}
          tone="text-rose-600 bg-rose-50 dark:bg-rose-950/30"
          onClick={() => navigate(consolePath("support-access"))}
        />
        <StatCard
          label="محاسبون بانتظار التوثيق"
          value={countOrDash(secondary.pendingAccountants)}
          icon={BadgeCheck}
          tone="text-violet-600 bg-violet-50 dark:bg-violet-950/30"
          onClick={() => navigate(consolePath("accountants"))}
        />
        <StatCard
          label={`اشتراكات تنتهي خلال ${formatNumber(TRIAL_WARNING_DAYS)} أيام`}
          value={formatNumber(trialsEnding.length)}
          hint="أو انتهت ولم تُجدَّد"
          icon={Hourglass}
          tone="text-amber-600 bg-amber-50 dark:bg-amber-950/30"
          onClick={() => navigate(`${consolePath("companies")}?filter=ending`)}
        />
        <StatCard
          label="الإيراد الشهري المتوقَّع"
          value={mrr === null ? "—" : `${formatMoney(mrr)} ₪`}
          hint="الشركات الفعّالة × سعر خطتها — تقدير لا تحصيل"
          icon={Banknote}
          tone="text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30"
          onClick={() => navigate(consolePath("plans"))}
        />
      </section>

      <section aria-label="مؤشرات المنصة" className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="إجمالي الشركات" value={formatNumber(data.companies.total)} icon={Building2}
          tone="text-blue-600 bg-blue-50 dark:bg-blue-950/30" onClick={() => navigate(consolePath("companies"))} />
        <StatCard label="الشركات الفعالة" value={formatNumber(data.companies.active)}
          hint={`تجريبية: ${formatNumber(data.companies.trial)}`} icon={CheckCircle2}
          tone="text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30"
          onClick={() => navigate(`${consolePath("companies")}?status=Active`)} />
        <StatCard label="الشركات الموقوفة" value={formatNumber(data.companies.suspended)} icon={CirclePause}
          tone="text-amber-600 bg-amber-50 dark:bg-amber-950/30"
          onClick={() => navigate(`${consolePath("companies")}?status=Suspended`)} />
        <StatCard label="المستخدمون النشطون" value={formatNumber(data.users.active)}
          hint={`من ${formatNumber(data.users.total)} حساب · ${formatNumber(data.memberships)} عضوية`}
          icon={Users} tone="text-sky-600 bg-sky-50 dark:bg-sky-950/30" />
      </section>

      {usageTotals && (
        <section aria-label="حجم العمل هذا الشهر" className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <StatCard label="حركات هذا الشهر (قيود مرحّلة + مخزون)" value={formatNumber(usageTotals.movements)}
            hint={secondary.usage ? `آخر تحديث: ${formatDateTimeValue(secondary.usage.computed_at)}` : undefined}
            icon={FileStack} tone="text-indigo-600 bg-indigo-50 dark:bg-indigo-950/30"
            onClick={() => navigate(`${consolePath("companies")}?sort=movements`)} />
          <StatCard label="مستندات هذا الشهر" value={formatNumber(usageTotals.documents)}
            hint="فواتير وسندات وعروض وطلبيات وإشعارات وصفقات وشحنات"
            icon={FileStack} tone="text-teal-600 bg-teal-50 dark:bg-teal-950/30"
            onClick={() => navigate(`${consolePath("companies")}?sort=documents`)} />
        </section>
      )}

      {/* مؤشرات التشغيل قسمٌ مستقل: ردٌّ بلا `kpis` (خادم أقدم) يُسقط هذا القسم وحده. */}
      {data.kpis && (
        <section aria-label="مؤشرات التشغيل" className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
          <InsightCard
            title={`بلا نشاط ${formatNumber(data.kpis.idle_companies.days)} يوماً`}
            value={formatNumber(data.kpis.idle_companies.count)}
            caption="لم يُسجَّل لها أي فعل (غير العرض) منذ هذه المدة"
            icon={CalendarClock}
            tone="text-slate-600 bg-slate-100 dark:bg-slate-800/60"
          >
            <InsightList
              empty="كل الشركات تحرّكت خلال المدة"
              onOpen={openCompany}
              rows={data.kpis.idle_companies.companies.map((company) => ({
                id: company.id,
                name: company.name,
                hint: activityLabel(company.last_activity_at),
                title: `آخر نشاط: ${activityLabel(company.last_activity_at)}`,
              }))}
            />
          </InsightCard>

          <InsightCard
            title="أعلى استهلاك للتخزين"
            value={formatBytes(data.storage?.ledger_total_bytes ?? 0)}
            caption="إجمالي سجلّ البايتات على المنصة — أعلى خمس شركات"
            icon={HardDrive}
            tone="text-indigo-600 bg-indigo-50 dark:bg-indigo-950/30"
          >
            <InsightList
              empty="لا بايتات مقيسة بعد في السجلّ"
              onOpen={openCompany}
              rows={data.kpis.top_storage.map((company) => ({
                id: company.id,
                name: company.name,
                hint: formatBytes(company.storage_bytes),
                title: `${formatNumber(company.storage_asset_count)} ملف`,
              }))}
            />
          </InsightCard>

          <InsightCard
            title="قريبة من حدّ الخطة"
            value={formatNumber(data.kpis.near_limit_companies.count)}
            caption="بلغ استهلاكها أربعة أخماس أحد حدود خطتها — الأقرب أولاً"
            icon={TriangleAlert}
            tone="text-amber-600 bg-amber-50 dark:bg-amber-950/30"
          >
            <InsightList
              empty="لا شركة قاربت حدّاً من حدودها"
              onOpen={openCompany}
              rows={data.kpis.near_limit_companies.companies.map((company) => ({
                id: company.id,
                name: company.name,
                hint: `${company.label} ${formatNumber(company.usage)}/${formatNumber(company.limit)}`,
                title: `${company.label}: ${formatNumber(company.usage)} من ${formatNumber(company.limit)}`,
              }))}
            />
          </InsightCard>
        </section>
      )}

      {/* بايتات `tenant = NULL`: رفوعات المنصة وما لم يُنسب. تُسمّى بما هي — «غير منسوب»
          محجوزة لتقرير `backfill_tenant_assets` — وتُخفى عند الصفر. */}
      {(data.storage?.unattributed_bytes ?? 0) > 0 && (
        <p className="mt-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text)]">
          تخزين مرفوع لا يخصّ شركة بعينها:{" "}
          <span className="font-bold">{formatBytes(data.storage.unattributed_bytes)}</span>
          <span className="block text-xs ktra-text-soft">
            رفوعات على مستوى المنصة (صور ملاحظات التطوير ومستندات مكتب المحاسبة) وملفات وصلت بلا شركة.
          </span>
        </p>
      )}
    </div>
  );
};
