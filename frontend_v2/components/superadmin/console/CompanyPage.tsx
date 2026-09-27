import React, { useCallback, useEffect, useState } from "react";
import {
  Activity, ArrowRight, FileStack, HardDrive, LogIn, Send, Siren, Users, XCircle,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  emergencySupportAccess, endSupportAccess, getPlatformCompany, getPlatformCompanyUsage,
  listCompanySupportAccess, requestSupportAccess,
  type CompanyUsageResponse, type PlatformCompanyDetail, type SupportAccessGrant, type SupportScope,
} from "../../../services/platformAdminApi";
import { useAuth } from "../../../contexts/AuthContext";
import { useConfirm } from "../../../contexts/ConfirmContext";
import { useToast } from "../../../contexts/ToastContext";
import { PlatformCompanyPanel, COMPANY_STATUS_LABELS, type CompanyPanelTab } from "../PlatformCompanyPanel";
import { formatBytes } from "../../../utils/formatBytes";
import { formatDateTimeValue, formatDateValue } from "../../../utils/formatDate";
import { formatNumber } from "../../../utils/formatNumber";
import {
  SUPPORT_DEFAULT_HOURS, SUPPORT_DURATIONS, SUPPORT_SCOPE_LABELS, SUPPORT_STATUS_LABELS,
  supportDurationLabel, supportStatusTone,
} from "../../../utils/supportAccessLabels";
import {
  ErrorBox, LoadingRow, Panel, PanelHead, Pill, STATUS_TONES, StatCard, companyPath, consolePath,
  enterSupportSession, errorText,
} from "./consoleShared";

type Tab = "summary" | "usage" | "support" | CompanyPanelTab;

const TABS: { key: Tab; label: string }[] = [
  { key: "summary", label: "ملخص" },
  { key: "usage", label: "الاستخدام" },
  { key: "plan", label: "الخطة والاشتراك" },
  { key: "modules", label: "الوحدات" },
  { key: "limits", label: "الحدود والتخزين" },
  { key: "members", label: "الأعضاء والفروع" },
  { key: "support", label: "الدخول والدعم" },
  { key: "activity", label: "السجل" },
];

const PANEL_TABS: CompanyPanelTab[] = ["plan", "modules", "limits", "members", "activity"];

const isTab = (value: string | null): value is Tab => TABS.some((tab) => tab.key === value);

/** إذنٌ ساري طلبه **هذا** المستخدم — الإذن شخصيّ في الخادم (`active_grant`)، فلا دخول بإذن زميل. */
const myActiveGrant = (grants: SupportAccessGrant[], userId: number | undefined) =>
  grants.find((grant) => grant.status === "active" && grant.requested_by_id === userId);

const UsageTab: React.FC<{ usage: CompanyUsageResponse | null; error: string | null }> = ({ usage, error }) => {
  if (error) return <ErrorBox message={error} />;
  if (!usage) return <LoadingRow />;
  const groups: { kind: "movement" | "document"; title: string }[] = [
    { kind: "movement", title: "الحركات" },
    { kind: "document", title: "المستندات" },
  ];
  return (
    <div className="space-y-4">
      <p className="text-xs ktra-text-soft">
        محسوبٌ الآن ({formatDateTimeValue(usage.computed_at)}) · «هذا الشهر» بتاريخ المستند نفسه · القيود المسودة لا تُعدّ.
      </p>
      {groups.map((group) => (
        <Panel key={group.kind} label={group.title}>
          <PanelHead title={group.title} />
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
              <tr>
                <th className="px-3 py-2 text-right">النوع</th>
                <th className="px-3 py-2 text-center">الكل</th>
                <th className="px-3 py-2 text-center">هذا الشهر</th>
              </tr>
            </thead>
            <tbody>
              {usage.counter_catalog.filter((counter) => counter.kind === group.kind).map((counter) => (
                <tr key={counter.key} className="border-t border-[var(--color-border)]">
                  <td className="px-3 py-2">{counter.label}</td>
                  <td className="px-3 py-2 text-center">{formatNumber(usage.counters[counter.key]?.total ?? 0)}</td>
                  <td className="px-3 py-2 text-center">{formatNumber(usage.counters[counter.key]?.month ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ))}
    </div>
  );
};

const SupportTab: React.FC<{
  company: PlatformCompanyDetail;
  grants: SupportAccessGrant[];
  onChanged: () => void;
}> = ({ company, grants, onChanged }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const { currentUser } = useAuth();
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState<SupportScope>("read_only");
  const [hours, setHours] = useState(SUPPORT_DEFAULT_HOURS);
  const [busy, setBusy] = useState(false);
  const mine = myActiveGrant(grants, Number(currentUser?.id));
  const myPending = grants.find((grant) => grant.status === "pending" && grant.requested_by_id === Number(currentUser?.id));

  const submit = async (emergency: boolean) => {
    const text = reason.trim();
    if (!text) {
      toast("اكتب سبب الدخول — تراه الشركة ويُحفظ في سجل التدقيق.", "error");
      return;
    }
    if (emergency) {
      const ok = await confirm({
        title: "دخول طارئ بلا انتظار موافقة",
        message: `تدخل «${company.name}» فوراً بصلاحية كاملة لأربع ساعات، وتُبلَّغ الشركة الآن، ويُسجَّل بخطورة عالية. استعمله لعطلٍ يوقف عمل العميل فقط.`,
        confirmText: "دخول طارئ",
        danger: true,
      });
      if (!ok) return;
    }
    setBusy(true);
    try {
      const grant = emergency
        ? await emergencySupportAccess(company.id, text)
        : await requestSupportAccess(company.id, text, scope, hours);
      setReason("");
      toast(emergency ? "فُتح دخول طارئ — تستطيع الدخول الآن." : "أُرسل الطلب للشركة — تدخل بعد موافقتها.", "success");
      onChanged();
      if (emergency && grant.status === "active") enterSupportSession(grant);
    } catch (cause) {
      toast(errorText(cause, "تعذّر إرسال الطلب."), "error");
    } finally {
      setBusy(false);
    }
  };

  const end = async (grant: SupportAccessGrant) => {
    try {
      await endSupportAccess(grant.id);
      toast(grant.status === "pending" ? "سُحب الطلب." : "أُنهي الإذن.", "success");
      onChanged();
    } catch (cause) {
      toast(errorText(cause, "تعذّر الإنهاء."), "error");
    }
  };

  return (
    <div className="space-y-4">
      {mine ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-950/30">
          <p className="text-sm font-semibold text-emerald-900 dark:text-emerald-200">
            لديك إذن {SUPPORT_SCOPE_LABELS[mine.scope] || mine.scope} ساري حتى {formatDateTimeValue(mine.expires_at)}
            {mine.is_emergency ? " (طارئ)" : ""}.
          </p>
          <div className="flex gap-2">
            <button type="button" onClick={() => enterSupportSession(mine)} className="ktra-btn ktra-btn-primary">
              <LogIn className="h-4 w-4" /> دخول الشركة
            </button>
            <button type="button" onClick={() => void end(mine)} className="ktra-btn">إنهاء الإذن</button>
          </div>
        </div>
      ) : (
        <Panel label="طلب دخول">
          <PanelHead
            title="طلب دخول للدعم"
            hint="لا دخول إلى بيانات شركة بلا إذنها. الطلب يصل مالكها ومديريها بالبريد وفي لوحتهم، ويقرّرون المدة والنطاق."
          />
          <div className="space-y-3 p-4">
            {myPending && (
              <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
                طلبك بتاريخ {formatDateTimeValue(myPending.created_at)} ما زال بانتظار الشركة.
              </p>
            )}
            <div>
              <label htmlFor="support-reason" className="mb-1 block text-xs font-bold ktra-text-soft">السبب (إلزامي — تراه الشركة)</label>
              <textarea
                id="support-reason"
                className="ktra-input min-h-20 w-full"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder="مثال: تذكرة دعم — فرق في رصيد المخزون بعد الجرد"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="support-scope" className="mb-1 block text-xs font-bold ktra-text-soft">النطاق</label>
                <select id="support-scope" className="ktra-input h-9 w-full" value={scope} onChange={(event) => setScope(event.target.value as SupportScope)}>
                  <option value="read_only">{SUPPORT_SCOPE_LABELS.read_only}</option>
                  <option value="full">{SUPPORT_SCOPE_LABELS.full}</option>
                </select>
              </div>
              <div>
                <label htmlFor="support-hours" className="mb-1 block text-xs font-bold ktra-text-soft">المدة</label>
                <select id="support-hours" className="ktra-input h-9 w-full" value={hours} onChange={(event) => setHours(Number(event.target.value))}>
                  {SUPPORT_DURATIONS.map((row) => <option key={row.hours} value={row.hours}>{row.label}</option>)}
                </select>
              </div>
            </div>
            <p className="text-[11px] ktra-text-soft">
              حتى بالإذن الكامل لا يستطيع فريق الدعم إدارة الأعضاء والصلاحيات، ولا التصدير، ولا إعدادات الربط الضريبي.
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={busy || !!myPending} onClick={() => void submit(false)} className="ktra-btn ktra-btn-primary">
                <Send className="h-4 w-4" /> إرسال الطلب
              </button>
              <button type="button" disabled={busy} onClick={() => void submit(true)} className="ktra-btn text-red-600">
                <Siren className="h-4 w-4" /> دخول طارئ
              </button>
            </div>
          </div>
        </Panel>
      )}

      <Panel label="سجل الأذونات">
        <PanelHead title="سجل الأذونات" hint="آخر خمسين طلباً على هذه الشركة من كل فريق المنصة" />
        {grants.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm ktra-text-soft">لم يُطلب دخولٌ إلى هذه الشركة بعد.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                <tr>
                  <th className="px-3 py-2 text-right">الطالب</th>
                  <th className="px-3 py-2 text-right">السبب</th>
                  <th className="px-3 py-2 text-right">النطاق والمدة</th>
                  <th className="px-3 py-2 text-right">الحالة</th>
                  <th className="px-3 py-2 text-right">التاريخ</th>
                  <th className="px-3 py-2" aria-label="إجراء" />
                </tr>
              </thead>
              <tbody>
                {grants.map((grant) => (
                  <tr key={grant.id} className="border-t border-[var(--color-border)]">
                    <td className="px-3 py-2">{grant.requested_by}{grant.is_emergency ? " (طارئ)" : ""}</td>
                    <td className="px-3 py-2">{grant.reason}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {SUPPORT_SCOPE_LABELS[grant.scope || grant.requested_scope]} · {supportDurationLabel(grant.requested_hours)}
                    </td>
                    <td className="px-3 py-2">
                      <Pill tone={supportStatusTone(grant.status)} title={grant.decision_note || undefined}>
                        {SUPPORT_STATUS_LABELS[grant.status] || grant.status}
                      </Pill>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{formatDateTimeValue(grant.created_at)}</td>
                    <td className="px-3 py-2 text-center">
                      {(grant.status === "pending" || grant.status === "active") && (
                        <button type="button" onClick={() => void end(grant)} className="ktra-iconbtn text-red-600" aria-label={grant.status === "pending" ? "سحب الطلب" : "إنهاء الإذن"} title={grant.status === "pending" ? "سحب الطلب" : "إنهاء الإذن"}>
                          <XCircle className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
};

/**
 * SA-6 — صفحة الشركة الكاملة في لوحة المنصة (بدل النافذة فوق الجدول): رأسٌ ثابت
 * بهويتها وحالتها وزرّ الدخول، ثم تبويبات. التبويب يسكن الرابط (`?tab=`) فيُحفظ ويُشارَك.
 * أقسام الإعدادات والوحدات والحدود والأعضاء والسجل هي نفسها في `PlatformCompanyPanel`
 * مرسومةً مضمَّنة — نسخةٌ واحدة من كل منطق تحكّم.
 */
export const CompanyPage: React.FC<{ companyId: number }> = ({ companyId }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser } = useAuth();
  const [company, setCompany] = useState<PlatformCompanyDetail | null>(null);
  const [usage, setUsage] = useState<CompanyUsageResponse | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [grants, setGrants] = useState<SupportAccessGrant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const requested = new URLSearchParams(location.search).get("tab");
  const tab: Tab = isTab(requested) ? requested : "summary";

  const load = useCallback(async () => {
    setError(null);
    setUsageError(null);
    const [detail, usageResult, grantResult] = await Promise.allSettled([
      getPlatformCompany(companyId), getPlatformCompanyUsage(companyId), listCompanySupportAccess(companyId),
    ]);
    if (detail.status === "fulfilled") setCompany(detail.value);
    else setError(errorText(detail.reason, "تعذّر تحميل الشركة"));
    // ردٌّ ناقص (خادم أقدم بلا SA-3) يُسقط تبويبه وحده لا الصفحة.
    if (usageResult.status === "fulfilled" && Array.isArray(usageResult.value?.counter_catalog)) setUsage(usageResult.value);
    else setUsageError(usageResult.status === "rejected" ? errorText(usageResult.reason, "تعذّر حساب الاستخدام") : "الاستخدام غير متاح.");
    if (grantResult.status === "fulfilled") setGrants(grantResult.value?.results ?? []);
  }, [companyId]);

  useEffect(() => { void load(); }, [load]);

  if (!company) {
    return error ? (
      <div>
        <ErrorBox message={error} onRetry={() => void load()} />
        <button type="button" onClick={() => navigate(consolePath("companies"))} className="ktra-btn">
          <ArrowRight className="h-4 w-4" /> كل الشركات
        </button>
      </div>
    ) : <LoadingRow label="جارٍ تحميل الشركة…" />;
  }

  const mine = myActiveGrant(grants, Number(currentUser?.id));
  const pendingCount = grants.filter((grant) => grant.status === "pending").length;

  return (
    <div>
      <button type="button" onClick={() => navigate(consolePath("companies"))} className="mb-3 inline-flex items-center gap-1 text-sm ktra-text-soft hover:text-[var(--color-text)]">
        <ArrowRight className="h-4 w-4" /> كل الشركات
      </button>

      <header className="mb-4 flex flex-wrap items-start justify-between gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-bold text-[var(--color-text)]">{company.name}</h2>
            <span className="text-xs ktra-text-soft">#{company.id}</span>
            <Pill tone={STATUS_TONES[company.status]}>{COMPANY_STATUS_LABELS[company.status] || company.status}</Pill>
            <Pill>{company.plan_label || company.plan}</Pill>
            {company.is_example && <Pill>مثال</Pill>}
          </div>
          <p className="mt-1 text-xs ktra-text-soft">
            أُنشئت {formatDateValue(company.created_at)} · آخر نشاط {company.last_activity_at ? formatDateValue(company.last_activity_at) : "لا نشاط مسجَّل"}
            {company.subscription_ends_at ? ` · الاشتراك حتى ${formatDateValue(company.subscription_ends_at)}` : " · اشتراك بلا تاريخ انتهاء"}
          </p>
        </div>
        {mine ? (
          <button type="button" onClick={() => enterSupportSession(mine)} className="ktra-btn ktra-btn-primary">
            <LogIn className="h-4 w-4" /> دخول الشركة ({SUPPORT_SCOPE_LABELS[mine.scope] || mine.scope})
          </button>
        ) : (
          <button type="button" onClick={() => navigate(companyPath(company.id, "support"))} className="ktra-btn">
            <LogIn className="h-4 w-4" /> طلب دخول
          </button>
        )}
      </header>

      <nav aria-label="أقسام الشركة" className="mb-4 flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => navigate(companyPath(company.id, item.key === "summary" ? undefined : item.key), { replace: true })}
            aria-current={tab === item.key ? "page" : undefined}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-semibold ${tab === item.key ? "border-[var(--color-primary)] text-[var(--color-primary-emphasis)]" : "border-transparent ktra-text-soft hover:text-[var(--color-text)]"}`}
          >
            {item.label}
            {item.key === "support" && pendingCount > 0 && (
              <span className="mr-1 rounded-full bg-amber-500 px-1.5 text-[10px] text-white">{formatNumber(pendingCount)}</span>
            )}
          </button>
        ))}
      </nav>

      {tab === "summary" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="المستندات" value={usage ? formatNumber(usage.documents_total) : "—"}
              hint={usage ? `هذا الشهر: ${formatNumber(usage.documents_month)}` : undefined}
              icon={FileStack} tone="text-teal-600 bg-teal-50 dark:bg-teal-950/30"
              onClick={() => navigate(companyPath(company.id, "usage"))} />
            <StatCard label="الحركات" value={usage ? formatNumber(usage.movements_total) : "—"}
              hint={usage ? `هذا الشهر: ${formatNumber(usage.movements_month)}` : undefined}
              icon={Activity} tone="text-indigo-600 bg-indigo-50 dark:bg-indigo-950/30"
              onClick={() => navigate(companyPath(company.id, "usage"))} />
            <StatCard label="الأعضاء" value={formatNumber(company.members.length)}
              hint={usage ? `نشطون خلال 30 يوماً: ${formatNumber(usage.active_users_30d)}` : undefined}
              icon={Users} tone="text-sky-600 bg-sky-50 dark:bg-sky-950/30"
              onClick={() => navigate(companyPath(company.id, "members"))} />
            <StatCard label="التخزين" value={formatBytes(company.storage_bytes)}
              hint={`الفروع: ${formatNumber(company.branches.length)}`}
              icon={HardDrive} tone="text-slate-600 bg-slate-100 dark:bg-slate-800/60"
              onClick={() => navigate(companyPath(company.id, "limits"))} />
          </div>
          {usageError && <ErrorBox message={usageError} />}
          {usage?.last_document_date && (
            <p className="text-sm ktra-text-soft">آخر مستند بتاريخ {formatDateValue(usage.last_document_date)}.</p>
          )}
          {pendingCount > 0 && (
            <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
              {formatNumber(pendingCount)} طلب دخول بانتظار موافقة الشركة.
            </p>
          )}
        </div>
      )}

      {tab === "usage" && <UsageTab usage={usage} error={usageError} />}
      {tab === "support" && <SupportTab company={company} grants={grants} onChanged={() => void load()} />}
      {PANEL_TABS.includes(tab as CompanyPanelTab) && (
        <PlatformCompanyPanel
          key={tab}
          companyId={company.id}
          embedded
          tab={tab as CompanyPanelTab}
          onClose={() => navigate(consolePath("companies"))}
          onChanged={() => void load()}
        />
      )}
    </div>
  );
};
