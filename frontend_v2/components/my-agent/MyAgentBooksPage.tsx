import React, { useState, useEffect, useCallback } from "react";
import {
  getMyBooksTabData,
  suspendAgentAccess,
  type MyBooksTabData,
} from "../../services/myAgentApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  getHealthStatusMeta,
  formatActivityCountNotice,
  formatRatingSampleNotice,
  formatReworkDiagnosticNotice,
} from "../../utils/agentBooks";
import { AgentRatingCard } from "./AgentRatingCard";
import { QuotaUsageCard } from "./QuotaUsageCard";
import {
  UserCheck,
  ShieldAlert,
  Clock,
  AlertTriangle,
  Info,
  RefreshCw,
  XCircle,
} from "lucide-react";

export const MyAgentBooksPage: React.FC = () => {
  const [data, setData] = useState<MyBooksTabData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSuspending, setIsSuspending] = useState<boolean>(false);

  const confirm = useConfirm();
  const toast = useToast();

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setData(await getMyBooksTabData());
    } catch (err: any) {
      setError(err?.message || "تعذر تحميل بيانات تبويب «من يمسك دفاتري».");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleSuspend = async (engagementId?: number, agentName?: string) => {
    if (!data?.can_suspend) return;
    const ok = await confirm({
      title: "تعليق وصول الوكيل",
      message: agentName
        ? `هل أنت متأكد من تعليق وصول الوكيل (${agentName}) لدفاتر شركتك؟ سيتم إيقاف صلاحيات الوصول فوراً في النظام.`
        : "هل أنت متأكد من تعليق وصول الوكيل لدفاتر شركتك؟ سيتم إيقاف صلاحيات الوصول فوراً في النظام.",
      confirmText: "نعم، علّق الوصول",
      cancelText: "إلغاء",
    });
    if (!ok) return;

    try {
      setIsSuspending(true);
      const res = await suspendAgentAccess(engagementId, "تعليق وصول الوكيل بطلب من صاحب الشركة");
      toast(res.detail || "تم تعليق وصول الوكيل بنجاح.", "success");
      await loadData();
    } catch (err: any) {
      toast(err?.message || "تعذر تعليق وصول الوكيل.", "error");
    } finally {
      setIsSuspending(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex flex-col items-center justify-center min-h-[400px] text-slate-500 dark:text-slate-400 space-y-3">
        <RefreshCw className="w-8 h-8 animate-spin text-emerald-600" />
        <p className="text-sm font-medium">جاري تحميل بيانات الوكيل ودفاتر الشركة...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="p-4 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 flex items-start space-x-3 space-x-reverse">
          <XCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
          <div className="space-y-1">
            <h3 className="font-semibold text-sm">خطأ في التحميل</h3>
            <p className="text-xs">{error || "تعذر العثور على بيانات."}</p>
            <button
              onClick={() => void loadData()}
              className="mt-2 text-xs font-semibold underline hover:no-underline"
            >
              إعادة المحاولة
            </button>
          </div>
        </div>
      </div>
    );
  }

  const { agents, service_date, granted_memberships, activity_log, total_activities_count, activity_page_cap, health_scores, can_suspend } = data;
  const serviceMeta = getHealthStatusMeta(health_scores?.service_health?.status);
  const customerMeta = getHealthStatusMeta(health_scores?.customer_cooperation?.status);

  const sampleNotice = formatRatingSampleNotice(
    health_scores?.ratings_sample?.size ?? 0,
    health_scores?.ratings_sample?.min_sample_size ?? 5,
    health_scores?.ratings_sample?.counts_against_score ?? false,
  );

  const reworkNotice = formatReworkDiagnosticNotice(
    health_scores?.rework_diagnostic?.cancelled_work_orders ?? 0,
  );

  const activityNotice = formatActivityCountNotice(total_activities_count, activity_page_cap);

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6 text-right" dir="rtl">
      {/* الترويسة الرئيسية */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <UserCheck className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
            من يمسك دفاتري
          </h1>
          <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mt-1">
            متابعة الوكيل المعتمد لدفاتر الشركة، سجل الأنشطة والعمليات، ودرجتي صحة الخدمة وتعاون العميل.
          </p>
        </div>

        {can_suspend && agents.length === 1 && (
          <button
            type="button"
            onClick={() => void handleSuspend(agents[0].engagement_id, agents[0].name)}
            disabled={isSuspending}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 text-xs md:text-sm font-semibold text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/60 transition disabled:opacity-50"
          >
            <ShieldAlert className="w-4 h-4" />
            {isSuspending ? "جاري التعليق..." : "تعليق وصول الوكيل"}
          </button>
        )}
      </div>

      {/* بطاقةٌ لكلّ وكيلٍ نشط — قصّة ٤٩ تسأل «مَن يعمل على شركتي الآن» بالاسم،
          وفرادةُ الارتباط على (موظف، شركة) فقد يكونون أكثر من واحد. */}
      {agents.length === 0 ? (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
          <div className="p-6 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-dashed border-slate-300 dark:border-slate-700 text-center space-y-2">
            <Info className="w-8 h-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              لا وكيلَ مرتبطٌ بشركتك حاليّاً
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              لم يتم تعيين موظف من المنصة كوكيل لإدارة دفاتر شركتك في الوقت الحالي.
            </p>
          </div>
        </div>
      ) : (
        agents.map((agentRow) => (
          <AgentRatingCard
            key={agentRow.id}
            agent={agentRow}
            serviceDate={service_date}
            canSuspend={can_suspend}
            onSuspend={() => void handleSuspend(agentRow.engagement_id, agentRow.name)}
          />
        ))
      )}

      <QuotaUsageCard />

      {/* درجتا الصحة منفصلتان تماماً */}
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-200">
            مؤشرات الصحة والأداء (منفصلتان)
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            درجة صحة الخدمة تقيس أداء الوكيل، ودرجة تعاون الزبون تقيس استجابة الشركة — لا دمج ولا متوسط مشترك.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* صحة الخدمة */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                صحة الخدمة (Service Health)
              </span>
              <span
                className={`px-2.5 py-0.5 text-xs font-bold rounded-full border ${serviceMeta.colorClass} ${serviceMeta.bgClass} ${serviceMeta.borderClass}`}
              >
                {serviceMeta.label}
              </span>
            </div>

            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-slate-900 dark:text-slate-100">
                {health_scores?.service_health?.score != null
                  ? `${formatNumber(health_scores.service_health.score)}%`
                  : "—"}
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400">من {formatNumber(100)}</span>
            </div>

            {health_scores?.service_health?.top_reasons && health_scores.service_health.top_reasons.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-slate-100 dark:border-slate-800">
                <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 block">
                  أهم العوامل المؤثرة:
                </span>
                <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-400">
                  {health_scores.service_health.top_reasons.slice(0, 3).map((reason, idx) => (
                    <li key={idx} className="flex items-start gap-1.5">
                      <span className="text-emerald-500">•</span>
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* تعاون الزبون */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                تعاون الزبون (Customer Cooperation)
              </span>
              <span
                className={`px-2.5 py-0.5 text-xs font-bold rounded-full border ${customerMeta.colorClass} ${customerMeta.bgClass} ${customerMeta.borderClass}`}
              >
                {customerMeta.label}
              </span>
            </div>

            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-slate-900 dark:text-slate-100">
                {health_scores?.customer_cooperation?.score != null
                  ? `${formatNumber(health_scores.customer_cooperation.score)}%`
                  : "—"}
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400">من {formatNumber(100)}</span>
            </div>

            {health_scores?.customer_cooperation?.top_reasons && health_scores.customer_cooperation.top_reasons.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-slate-100 dark:border-slate-800">
                <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 block">
                  أهم العوامل المؤثرة:
                </span>
                <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-400">
                  {health_scores.customer_cooperation.top_reasons.slice(0, 3).map((reason, idx) => (
                    <li key={idx} className="flex items-start gap-1.5">
                      <span className="text-blue-500">•</span>
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* إشعارات العينة والتشخيص */}
        <div className="space-y-2">
          {sampleNotice && (
            <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-400 flex items-center gap-2">
              <Info className="w-4 h-4 text-slate-500 flex-shrink-0" />
              <span>{sampleNotice}</span>
            </div>
          )}

          {reworkNotice && (
            <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
              <span>{reworkNotice}</span>
            </div>
          )}
        </div>
      </div>

      {/* جدول العضويات الممنوحة للوكيل */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm space-y-3">
        <h2 className="text-base font-semibold text-slate-800 dark:text-slate-200">
          صلاحيات الوصول الممنوحة في الشركة
        </h2>

        {granted_memberships.length === 0 ? (
          <p className="text-xs text-slate-500 dark:text-slate-400 py-3">
            لا توجد سجلات منح صلاحيات حالية.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-right">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400">
                  <th className="py-2.5 px-3">المستخدم</th>
                  <th className="py-2.5 px-3">الصلاحية قبل</th>
                  <th className="py-2.5 px-3">الصلاحية بعد</th>
                  <th className="py-2.5 px-3">مَن نفّذ</th>
                  <th className="py-2.5 px-3">تاريخ المنح</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {granted_memberships.map((mem) => (
                  <tr key={mem.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                    <td className="py-2.5 px-3 font-medium text-slate-800 dark:text-slate-200">
                      {mem.target_user_name || "—"}
                    </td>
                    <td className="py-2.5 px-3 text-slate-600 dark:text-slate-400">
                      {mem.role_before_display || "—"}
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-emerald-700 dark:text-emerald-300">
                      {mem.role_after_display || "—"}
                    </td>
                    <td className="py-2.5 px-3 text-slate-600 dark:text-slate-400">
                      {mem.acting_employee_name || "—"}
                    </td>
                    <td className="py-2.5 px-3 text-slate-500 dark:text-slate-400">
                      {formatDateTimeValue(mem.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* سجل نشاط الوكيل */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-slate-800 dark:text-slate-200">
              سجل نشاط الوكيل في الشركة
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              يُسجل الحركات المالية والإدارية الفعلية للوكيل داخل دفاتر شركتك حصراً (مستبعداً العرض والدخول).
            </p>
          </div>

          <span className="text-xs text-slate-500 dark:text-slate-400 font-mono">
            إجمالي الحركات: {formatNumber(total_activities_count)}
          </span>
        </div>

        {activityNotice && (
          <div className="p-2.5 rounded-md bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-300 text-xs flex items-center gap-1.5">
            <Info className="w-4 h-4 flex-shrink-0" />
            <span>{activityNotice}</span>
          </div>
        )}

        {activity_log.length === 0 ? (
          <p className="text-xs text-slate-500 dark:text-slate-400 py-4 text-center">
            لا توجد حركات مسجلة للوكيل في الشركة بعد.
          </p>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {activity_log.map((act) => (
              <div
                key={act.id}
                className="py-3 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 text-xs"
              >
                {/* الوصفُ وحدَه: الخادمُ صاغه جملةً عربيّةً تحمل الفعلَ واسمَ المستند
                    بمعجم هذه الشركة و«من ماذا إلى ماذا». وعرضُ `action`/`entity_type`
                    الخامَّين يريه مفاتيحَ نظامٍ («update»/«sales_invoice»)، وتعريبُهما
                    هنا نسخةٌ ثانيةٌ من خريطةٍ تسكن الخادم وتنزاح عنها بصمت. */}
                <div className="space-y-1">
                  <p className="font-medium text-slate-800 dark:text-slate-200 leading-relaxed">
                    {act.description}
                  </p>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    نفّذها: {act.actor_name}
                  </span>
                </div>

                <div className="flex items-center gap-1 text-slate-400 dark:text-slate-500 whitespace-nowrap text-[11px]">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{formatDateTimeValue(act.timestamp)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
