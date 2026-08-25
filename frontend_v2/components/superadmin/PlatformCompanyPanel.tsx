import React, { useCallback, useEffect, useState } from "react";
import {
  ChevronDown, ChevronLeft, Loader2, RotateCcw, Save, ShieldOff, ShieldCheck, Trash2,
  UserPlus, X,
} from "lucide-react";

import {
  addPlatformCompanyMember, getPlatformCompany, getPlatformCompanyActivity, listCompanyLimits,
  listCompanyModules, removePlatformCompanyMember, setCompanyLimit, setCompanyModule,
  setPlatformUserActive, updatePlatformCompany, updatePlatformCompanyMember,
  type PlatformActivityRow, type PlatformCompanyDetail, type PlatformCompanyMember,
  type PlatformCompanyPatch, type PlatformLimitRow, type PlatformModuleRow,
} from "../../services/platformAdminApi";
import { ROLE_LABELS } from "../layout/CompanyManagementModal";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatBytes } from "../../utils/formatBytes";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
// شكل الحركة الواحدة (شارة الإجراء · اسم النوع · صيغة الوقت) مصدره واحد مع سجل
// المستند والصفحة العامة — لا صيغة ثالثة تخصّ لوحة المنصة.
import { actionMeta, entityLabel, formatActivityTime } from "../activity/activityMeta";

/** لوحة تحكم الشركة — سوبر أدمن المنصة فقط.
 * كانت صلاحيات المنصة موزّعة على «إدارة الشركة» (نافذة المدير) فلا يطال السوبر
 * أدمن إلا الشركات التي هو مديرٌ فيها. هنا يدير أي شركة: الخطة، الحالة،
 * وحدة الاستيراد، والأعضاء (دور/استيراد/إيقاف حساب/إخراج). */

export const COMPANY_STATUS_LABELS: Record<string, string> = {
  Active: "فعالة",
  Trial: "تجريبية",
  Suspended: "موقوفة",
};

export const COMPANY_PLAN_LABELS: Record<string, string> = {
  Trial: "تجريبية",
  Basic: "أساسية",
  Pro: "احترافية",
  Enterprise: "مؤسسية",
};

interface Props {
  companyId: number;
  onClose: () => void;
  /** بعد أي تغيير — لتحديث أرقام اللوحة وجدول الشركات */
  onChanged: () => void;
}

export const PlatformCompanyPanel: React.FC<Props> = ({ companyId, onClose, onChanged }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [detail, setDetail] = useState<PlatformCompanyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Required<Omit<PlatformCompanyPatch, "is_example">>>({
    name: "", plan: "Basic", status: "Trial", import_enabled: false,
    subscription_ends_at: null,
  });
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [newRole, setNewRole] = useState("staff");
  const [adding, setAdding] = useState(false);
  const [modules, setModules] = useState<PlatformModuleRow[]>([]);
  const [moduleBusy, setModuleBusy] = useState<string | null>(null);
  // T-PLANLIMITS: حدود الخطة — الحقل يحمل النص المكتوب حتى الحفظ («» = بلا حدّ).
  const [limits, setLimits] = useState<PlatformLimitRow[]>([]);
  const [limitDraft, setLimitDraft] = useState<Record<string, string>>({});
  const [limitBusy, setLimitBusy] = useState<string | null>(null);
  // «آخر الحركات» — تُجلب عند أول فتح للقسم لا مع فتح اللوحة: اللوحة تفتح على ثلاثة
  // نداءات أصلاً، ومئةُ صفٍّ لا يطلبها كل قارئ حِملٌ لا يدفعه من جاء يبدّل خطة.
  // `feed === null` تعني «لم تُجلب بعد» وتميّزها عن «جُلبت فكانت فارغة».
  const [feedOpen, setFeedOpen] = useState(false);
  const [feed, setFeed] = useState<PlatformActivityRow[] | null>(null);
  const [feedLoading, setFeedLoading] = useState(false);
  const [feedError, setFeedError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, moduleState, limitState] = await Promise.all([
        getPlatformCompany(companyId),
        listCompanyModules(companyId),
        listCompanyLimits(companyId),
      ]);
      setDetail(data);
      // وحدة الاستيراد القديمة لها خانتها في «إعدادات الشركة» أعلاه — لا نكرّر ضبطها.
      setModules(moduleState.results.filter((module) => !module.legacy));
      setLimits(limitState.results);
      setLimitDraft(Object.fromEntries(limitState.results.map((row) => [
        row.key, row.effective === null ? "" : String(row.effective),
      ])));
      setForm({
        name: data.name, plan: data.plan, status: data.status,
        import_enabled: data.import_enabled,
        subscription_ends_at: data.subscription_ends_at,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر تحميل بيانات الشركة");
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { void load(); }, [load]);

  /** شركة أخرى = سجلٌّ آخر: يُطوى ويُفرَّغ فلا تُقرأ حركات الشركة السابقة تحت اسم الجديدة. */
  useEffect(() => {
    setFeedOpen(false);
    setFeed(null);
    setFeedError(null);
  }, [companyId]);

  const loadFeed = useCallback(async () => {
    setFeedLoading(true);
    setFeedError(null);
    try {
      const data = await getPlatformCompanyActivity(companyId);
      setFeed(data.results ?? []);
    } catch (cause) {
      setFeedError(cause instanceof Error ? cause.message : "تعذّر تحميل آخر الحركات");
    } finally {
      setFeedLoading(false);
    }
  }, [companyId]);

  /** أول فتح يجلب، وما بعده طيٌّ وبسطٌ بلا نداء — والإخفاق يُعاد منه بزرّ صريح. */
  const toggleFeed = () => {
    const next = !feedOpen;
    setFeedOpen(next);
    if (next && feed === null && !feedLoading) void loadFeed();
  };

  const run = async (fn: () => Promise<void>, okMsg?: string) => {
    setError(null);
    try {
      await fn();
      if (okMsg) toast(okMsg, "success");
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const dirty = !!detail && (
    form.name !== detail.name || form.plan !== detail.plan
    || form.status !== detail.status || form.import_enabled !== detail.import_enabled
    || form.subscription_ends_at !== detail.subscription_ends_at
  );

  // T-TRIAL: «كم بقي» يأتي محسوباً من الخادم (`subscription_days_left`) ولا
  // يُحسب هنا: حسابُه في المتصفّح يجعله يتبع ساعة جهاز السوبر أدمن، فيقرأ يوماً
  // والحارس يقرأ غيره. لذلك تاريخٌ عُدّل ولم يُحفظ لا رقم له — «يُطبَّق عند الحفظ».
  const expiryHint = (() => {
    if (!detail) return "";
    if (!form.subscription_ends_at) {
      return form.plan === "Trial"
        ? "بلا تاريخ — يُضبط تلقائياً بعد ١٤ يوماً عند الحفظ"
        : "بلا تاريخ انتهاء";
    }
    if (form.subscription_ends_at !== detail.subscription_ends_at) {
      return "يُطبَّق عند الحفظ";
    }
    const left = detail.subscription_days_left;
    if (left === null) return "";
    if (left < 0) return `منتهٍ منذ ${formatNumber(-left, { maxDecimals: 0 })} يوماً — الشركة للقراءة فقط`;
    if (left === 0) return "اليوم آخر يوم عمل";
    return `يتبقّى ${formatNumber(left, { maxDecimals: 0 })} يوماً`;
  })();

  const saveCompany = () =>
    run(async () => {
      if (!detail || !dirty) return;
      setSaving(true);
      try {
        await updatePlatformCompany(companyId, form);
        await load();
      } finally {
        setSaving(false);
      }
    }, "تم حفظ إعدادات الشركة.");

  const addMember = () =>
    run(async () => {
      const value = identifier.trim();
      if (!value) return;
      setAdding(true);
      try {
        await addPlatformCompanyMember(companyId, value, newRole);
        setIdentifier("");
        await load();
      } finally {
        setAdding(false);
      }
    }, "تمت إضافة العضو.");

  const patchMember = (member: PlatformCompanyMember, patch: { role?: string; can_access_import?: boolean }) =>
    run(async () => {
      setBusyId(member.membership_id);
      try {
        await updatePlatformCompanyMember(companyId, member.membership_id, patch);
        await load();
      } finally {
        setBusyId(null);
      }
    });

  const removeMember = (member: PlatformCompanyMember) =>
    run(async () => {
      const ok = await confirm({
        title: "إخراج عضو من الشركة",
        message: `سيفقد «${member.full_name || member.username}» وصوله إلى «${detail?.name}». حسابه على المنصة يبقى كما هو.`,
        confirmText: "إخراج",
        danger: true,
      });
      if (!ok) return;
      setBusyId(member.membership_id);
      try {
        await removePlatformCompanyMember(companyId, member.membership_id);
        await load();
      } finally {
        setBusyId(null);
      }
    }, "تم إخراج العضو.");

  const toggleModule = (module: PlatformModuleRow, enabled: boolean) =>
    run(async () => {
      if (!enabled && module.module_key === "accountant_portal") {
        const ok = await confirm({
          title: "تعطيل بوابة المحاسب",
          message:
            "ستختفي شاشات البوابة وصلاحياتها عن هذه الشركة فوراً، وتتوقف ارتباطات محاسبيها عن العمل. "
            + "البيانات تبقى كما هي وتعود بإعادة التفعيل.",
          confirmText: "تعطيل",
          danger: true,
        });
        if (!ok) return;
      }
      setModuleBusy(module.module_key);
      try {
        await setCompanyModule(companyId, module.module_key, enabled, module.plan_note);
        await load();
      } finally {
        setModuleBusy(null);
      }
    }, "تم تحديث ترخيص الوحدة.");

  /** حفظ حدّ واحد — الحقل الفارغ يعني «بلا حدّ» صراحةً لهذه الشركة. */
  const saveLimit = (row: PlatformLimitRow) =>
    run(async () => {
      const raw = (limitDraft[row.key] ?? "").trim();
      const parsed = raw === "" ? null : Number(raw);
      if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) {
        setError(`قيمة «${row.label}» يجب أن تكون رقماً موجباً أو فارغة (بلا حدّ).`);
        return;
      }
      setLimitBusy(row.key);
      try {
        await setCompanyLimit(companyId, row.key, { max_value: parsed });
        await load();
      } finally {
        setLimitBusy(null);
      }
    }, "تم حفظ حدّ الخطة.");

  /** استعادة افتراضي الخطة — يحذف التجاوز فتتبع الشركة خطتها من جديد. */
  const resetLimit = (row: PlatformLimitRow) =>
    run(async () => {
      setLimitBusy(row.key);
      try {
        await setCompanyLimit(companyId, row.key, { reset: true });
        await load();
      } finally {
        setLimitBusy(null);
      }
    }, "عاد الحدّ إلى افتراضي الخطة.");

  const toggleAccount = (member: PlatformCompanyMember) =>
    run(async () => {
      const next = !member.is_active;
      if (!next) {
        const ok = await confirm({
          title: "إيقاف حساب",
          message: `سيُمنع «${member.full_name || member.username}» من تسجيل الدخول إلى المنصة كلياً (كل شركاته). بياناته وعضوياته تبقى كما هي.`,
          confirmText: "إيقاف الحساب",
          danger: true,
        });
        if (!ok) return;
      }
      setBusyId(member.membership_id);
      try {
        await setPlatformUserActive(member.user_id, next);
        await load();
      } finally {
        setBusyId(null);
      }
    });

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" dir="rtl">
      <div className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl">
        <header className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
          <div>
            <h2 className="font-bold text-[var(--color-text)]">
              تحكم المنصة بالشركة{detail ? `: ${detail.name}` : ""}
            </h2>
            <p className="text-xs ktra-text-soft">
              صلاحيات سوبر أدمن — تسري على هذه الشركة دون الحاجة لعضوية فيها
            </p>
            {detail && (
              <p className="mt-1 text-[11px] ktra-text-soft">
                التخزين المستهلَك:{" "}
                <span className="font-bold text-[var(--color-text)]">{formatBytes(detail.storage_bytes)}</span>
                {" · "}آخر نشاط:{" "}
                {detail.last_activity_at ? formatDateValue(detail.last_activity_at) : "لا نشاط مسجَّل"}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="ktra-iconbtn" aria-label="إغلاق">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>
          )}

          {loading && !detail ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm ktra-text-soft" role="status">
              <Loader2 className="h-4 w-4 animate-spin" /> جارٍ تحميل بيانات الشركة…
            </div>
          ) : !detail ? null : (
            <>
              <section aria-label="إعدادات الشركة" className="rounded-lg border border-[var(--color-border)] p-3">
                <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">إعدادات الشركة</h3>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="sm:col-span-3">
                    <label htmlFor="platform-company-name" className="mb-1 block text-xs font-bold ktra-text-soft">اسم الشركة</label>
                    <input
                      id="platform-company-name"
                      className="ktra-input h-9 w-full"
                      value={form.name}
                      onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                    />
                  </div>
                  <div>
                    <label htmlFor="platform-company-plan" className="mb-1 block text-xs font-bold ktra-text-soft">خطة الاشتراك</label>
                    <select
                      id="platform-company-plan"
                      className="ktra-input h-9 w-full"
                      value={form.plan}
                      onChange={(event) => setForm((current) => ({ ...current, plan: event.target.value }))}
                    >
                      {Object.entries(COMPANY_PLAN_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="platform-company-status" className="mb-1 block text-xs font-bold ktra-text-soft">حالة الشركة</label>
                    <select
                      id="platform-company-status"
                      className="ktra-input h-9 w-full"
                      value={form.status}
                      onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}
                    >
                      {Object.entries(COMPANY_STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="platform-company-expiry" className="mb-1 block text-xs font-bold ktra-text-soft">تاريخ انتهاء الاشتراك</label>
                    <input
                      id="platform-company-expiry"
                      type="date"
                      className="ktra-input h-9 w-full"
                      value={form.subscription_ends_at ?? ""}
                      onChange={(event) => setForm((current) => ({
                        ...current, subscription_ends_at: event.target.value || null,
                      }))}
                    />
                    <p className="mt-1 text-[11px] ktra-text-soft">{expiryHint}</p>
                  </div>
                  <div className="flex items-end">
                    <label className="flex cursor-pointer items-center gap-2 text-sm font-bold text-[var(--color-text)]">
                      <input
                        type="checkbox"
                        checked={form.import_enabled}
                        onChange={(event) => setForm((current) => ({ ...current, import_enabled: event.target.checked }))}
                      />
                      وحدة الاستيراد
                    </label>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] ktra-text-soft">
                    الشركة الموقوفة يُمنع أعضاؤها من الوصول إلى بياناتها حتى إعادة التفعيل. تعطيل وحدة الاستيراد يخفي قائمة الاستيراد وقسم «تكاليف الاستيراد» عن كل أعضائها.
                  </p>
                  <button
                    type="button"
                    onClick={() => void saveCompany()}
                    disabled={saving || !dirty}
                    className="ktra-btn ktra-btn-primary"
                  >
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} حفظ
                  </button>
                </div>
              </section>

              <section aria-label="وحدات الشركة المرخَّصة" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
                <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">الوحدات المرخَّصة</h3>
                <div className="space-y-2">
                  {modules.length === 0 ? (
                    <p className="text-xs ktra-text-soft">لا وحدات إضافية — وحدة الاستيراد تُضبط من «إعدادات الشركة» أعلاه.</p>
                  ) : modules.map((module) => (
                    <div
                      key={module.module_key}
                      className="flex flex-wrap items-center justify-between gap-3 rounded border border-[var(--color-border)] px-3 py-2"
                    >
                      <div className="min-w-[14rem]">
                        <p className="text-sm font-bold text-[var(--color-text)]">{module.label}</p>
                        <p className="text-[11px] ktra-text-soft">
                          {module.plans.length ? `الخطط: ${module.plans.join("، ")}` : "بلا خطة محددة"}
                          {module.plan_note ? ` · ${module.plan_note}` : ""}
                        </p>
                        {module.plan_allows === false && (
                          <p className="text-[11px] font-semibold text-amber-600">
                            خارج خطة الشركة الحالية — يُرخَّص استثناءً فقط
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <label className="flex cursor-pointer items-center gap-2 text-sm font-bold text-[var(--color-text)]">
                          <input
                            type="checkbox"
                            checked={module.enabled}
                            disabled={moduleBusy === module.module_key}
                            onChange={(event) => void toggleModule(module, event.target.checked)}
                            aria-label={`ترخيص ${module.label}`}
                          />
                          {module.enabled ? "مفعّلة" : "معطّلة"}
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-[11px] ktra-text-soft">
                  الشركة غير المرخَّصة لا ترى مسارات الوحدة ولا صلاحياتها ولا تُحمَّل شاشاتها في متصفحها.
                  واجهة المكتب نفسها تُفتح من لوحة المنصة بزرّ «افتح واجهة المحاسب القانوني».
                </p>
              </section>

              <section aria-label="حدود خطة الشركة" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
                <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">
                  حدود الاستخدام ({COMPANY_PLAN_LABELS[detail.plan] || detail.plan})
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                      <tr>
                        <th className="px-3 py-2 text-right">البند</th>
                        <th className="px-3 py-2 text-center w-28">افتراضي الخطة</th>
                        <th className="px-3 py-2 text-center w-28">المستهلَك</th>
                        <th className="px-3 py-2 text-center w-32">الحدّ لهذه الشركة</th>
                        <th className="px-3 py-2 text-center w-28">إجراءات</th>
                      </tr>
                    </thead>
                    <tbody>
                      {limits.map((row) => {
                        const over = row.effective !== null && row.usage > row.effective;
                        return (
                          <tr key={row.key} className="border-t border-[var(--color-border)]">
                            <td className="px-3 py-2">
                              <div className="font-semibold text-[var(--color-text)]">{row.label}</div>
                              <div className="text-[11px] ktra-text-soft">
                                {row.unit} · {row.period_label}
                                {row.has_override ? " · مخصّص لهذه الشركة" : ""}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-center ktra-text-soft">
                              {row.plan_default === null ? "بلا حدّ" : row.plan_default}
                            </td>
                            <td className={`px-3 py-2 text-center ${over ? "font-bold text-amber-600" : ""}`}>
                              {row.usage}
                            </td>
                            <td className="px-3 py-2">
                              <input
                                className="ktra-input h-8 w-full text-center"
                                type="number"
                                min={0}
                                inputMode="numeric"
                                value={limitDraft[row.key] ?? ""}
                                placeholder="بلا حدّ"
                                disabled={limitBusy === row.key}
                                onChange={(event) => setLimitDraft((current) => ({
                                  ...current, [row.key]: event.target.value,
                                }))}
                                aria-label={`حدّ ${row.label}`}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex items-center justify-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => void saveLimit(row)}
                                  disabled={limitBusy === row.key}
                                  className="ktra-iconbtn text-emerald-600"
                                  title={`حفظ حدّ ${row.label}`}
                                  aria-label={`حفظ حدّ ${row.label}`}
                                >
                                  {limitBusy === row.key
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <Save className="h-4 w-4" />}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void resetLimit(row)}
                                  disabled={limitBusy === row.key || !row.has_override}
                                  className="ktra-iconbtn"
                                  title={`استعادة افتراضي الخطة لـ${row.label}`}
                                  aria-label={`استعادة افتراضي الخطة لـ${row.label}`}
                                >
                                  <RotateCcw className="h-4 w-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[11px] ktra-text-soft">
                  الحقل الفارغ = بلا حدّ لهذه الشركة. تغيير الخطة يغيّر الافتراضيات، والقيمة المخصّصة هنا تبقى فوقها حتى تُستعاد.
                  عند بلوغ الحدّ يُرفض الإنشاء برسالة واضحة للمستخدم؛ إضافة عضو من هذه اللوحة لا يحدّها الحدّ.
                </p>
              </section>

              <section aria-label="أعضاء الشركة" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
                <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                  <h3 className="text-sm font-bold text-[var(--color-text)]">الأعضاء ({detail.members.length})</h3>
                  <div className="flex flex-wrap items-end gap-2">
                    <div>
                      <label htmlFor="platform-member-identifier" className="mb-1 block text-[11px] font-bold ktra-text-soft">اسم المستخدم أو البريد</label>
                      <input
                        id="platform-member-identifier"
                        className="ktra-input h-9 w-56"
                        value={identifier}
                        onChange={(event) => setIdentifier(event.target.value)}
                        placeholder="حساب مسجَّل في المنصة"
                        autoComplete="off"
                        spellCheck={false}
                      />
                    </div>
                    <div>
                      <label htmlFor="platform-member-role" className="mb-1 block text-[11px] font-bold ktra-text-soft">الدور</label>
                      <select
                        id="platform-member-role"
                        className="ktra-input h-9"
                        value={newRole}
                        onChange={(event) => setNewRole(event.target.value)}
                      >
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      onClick={() => void addMember()}
                      disabled={adding || !identifier.trim()}
                      className="ktra-btn ktra-btn-primary"
                    >
                      {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />} إضافة
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-sm">
                    <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                      <tr>
                        <th className="px-3 py-2 text-right">المستخدم</th>
                        <th className="px-3 py-2 text-right w-44">الدور</th>
                        <th className="px-3 py-2 text-center w-20">استيراد</th>
                        <th className="px-3 py-2 text-center w-28">الحساب</th>
                        <th className="px-3 py-2 text-center w-24">إجراءات</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.members.length === 0 ? (
                        <tr><td colSpan={5} className="px-3 py-8 text-center ktra-text-soft">لا أعضاء في هذه الشركة</td></tr>
                      ) : detail.members.map((member) => (
                        <tr key={member.membership_id} className="border-t border-[var(--color-border)]">
                          <td className="px-3 py-2">
                            <div className="font-semibold text-[var(--color-text)]">{member.full_name || member.username}</div>
                            <div className="text-[11px] ktra-text-soft">{member.email || member.username}</div>
                          </td>
                          <td className="px-3 py-2">
                            <select
                              className="ktra-input h-8 w-full"
                              value={member.role}
                              disabled={busyId === member.membership_id}
                              onChange={(event) => void patchMember(member, { role: event.target.value })}
                              aria-label={`دور ${member.username}`}
                            >
                              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                              ))}
                            </select>
                          </td>
                          <td className="px-3 py-2 text-center">
                            {member.role === "manager" ? (
                              <span className="text-[11px] ktra-text-soft" title="المدير يملك صلاحية الاستيراد ضمناً">ضمناً</span>
                            ) : (
                              <input
                                type="checkbox"
                                checked={member.can_access_import}
                                disabled={busyId === member.membership_id || !detail.import_enabled}
                                onChange={(event) => void patchMember(member, { can_access_import: event.target.checked })}
                                aria-label={`صلاحية استيراد ${member.username}`}
                                title={detail.import_enabled ? "" : "فعّل وحدة الاستيراد للشركة أولاً"}
                              />
                            )}
                          </td>
                          <td className="px-3 py-2 text-center">
                            <span className={member.is_active ? "text-emerald-600" : "text-red-600 font-semibold"}>
                              {member.is_active ? "نشط" : "موقوف"}
                            </span>
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex items-center justify-center gap-1">
                              <button
                                type="button"
                                onClick={() => void toggleAccount(member)}
                                disabled={busyId === member.membership_id}
                                className={`ktra-iconbtn ${member.is_active ? "text-amber-600" : "text-emerald-600"}`}
                                title={member.is_active ? `إيقاف حساب ${member.username}` : `تفعيل حساب ${member.username}`}
                                aria-label={member.is_active ? `إيقاف حساب ${member.username}` : `تفعيل حساب ${member.username}`}
                              >
                                {member.is_active ? <ShieldOff className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                              </button>
                              <button
                                type="button"
                                onClick={() => void removeMember(member)}
                                disabled={busyId === member.membership_id}
                                className="ktra-iconbtn text-red-600"
                                title={`إخراج ${member.username} من الشركة`}
                                aria-label={`إخراج ${member.username} من الشركة`}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[11px] ktra-text-soft">
                  «إيقاف الحساب» يمنع الدخول إلى المنصة كلها، و«الإخراج» يزيل العضوية من هذه الشركة فقط. لا يمكن إخراج أو تخفيض آخر مدير قبل تعيين بديل.
                </p>
              </section>

              <section aria-label="فروع الشركة" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
                <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">
                  الفروع ({detail.branches.length})
                </h3>
                {detail.branches.length === 0 ? (
                  <p className="text-xs ktra-text-soft">لا فروع</p>
                ) : (
                  <ul className="flex flex-wrap gap-2">
                    {detail.branches.map((branch) => (
                      <li
                        key={branch.id}
                        className="rounded border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text)]"
                      >
                        <span className="font-semibold">{branch.name}</span>
                        {branch.code && <span className="text-[11px] ktra-text-soft"> · {branch.code}</span>}
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-[11px] ktra-text-soft">
                  الفروع تُنشأ وتُعدَّل من داخل الشركة نفسها — تُقرأ هنا فقط، وعددها يحدّه بند «الفروع» في «حدود الاستخدام» أعلاه.
                </p>
              </section>

              <section aria-label="آخر حركات الشركة" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
                <button
                  type="button"
                  onClick={toggleFeed}
                  aria-expanded={feedOpen}
                  className="flex w-full items-center justify-between gap-2 text-right"
                >
                  <h3 className="text-sm font-bold text-[var(--color-text)]">آخر الحركات</h3>
                  <span className="flex items-center gap-1 text-[11px] ktra-text-soft">
                    {feedOpen ? "إخفاء" : "عرض آخر 100 حركة"}
                    {feedOpen
                      ? <ChevronDown className="h-4 w-4" />
                      : <ChevronLeft className="h-4 w-4" />}
                  </span>
                </button>

                {feedOpen && (
                  <div className="mt-3">
                    {feedLoading ? (
                      <div className="flex items-center justify-center gap-2 py-6 text-sm ktra-text-soft" role="status">
                        <Loader2 className="h-4 w-4 animate-spin" /> جارٍ تحميل آخر الحركات…
                      </div>
                    ) : feedError ? (
                      <div
                        className="flex flex-wrap items-center justify-between gap-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                        role="alert"
                      >
                        <span>{feedError}</span>
                        <button type="button" onClick={() => void loadFeed()} className="ktra-btn">
                          <RotateCcw className="h-4 w-4" /> إعادة المحاولة
                        </button>
                      </div>
                    ) : !feed || feed.length === 0 ? (
                      <p className="py-6 text-center text-sm ktra-text-soft">
                        لا حركات مسجَّلة لهذه الشركة — أحداث فتح المستندات لا تُحتسب.
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[640px] text-sm">
                          <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                            <tr>
                              <th className="px-3 py-2 text-right w-40">التاريخ</th>
                              <th className="px-3 py-2 text-right w-40">المستخدم</th>
                              <th className="px-3 py-2 text-right w-28">الإجراء</th>
                              <th className="px-3 py-2 text-right">المستند</th>
                            </tr>
                          </thead>
                          <tbody>
                            {feed.map((row, index) => {
                              const meta = actionMeta(row.action);
                              return (
                                <tr key={`${row.timestamp}-${index}`} className="border-t border-[var(--color-border)]">
                                  <td className="px-3 py-2 whitespace-nowrap ktra-text-soft">
                                    {formatActivityTime(row.timestamp)}
                                  </td>
                                  <td className="px-3 py-2">{row.user_name}</td>
                                  <td className="px-3 py-2">
                                    <span className={`rounded-full px-2 py-0.5 text-xs ${meta.badge}`}>
                                      {row.action_label || meta.label}
                                    </span>
                                  </td>
                                  <td className="px-3 py-2">
                                    <div className="text-[var(--color-text)]">
                                      {entityLabel(row.entity_type)}
                                      {row.entity_label ? ` ${row.entity_label}` : ""}
                                    </div>
                                    {row.description && (
                                      <div className="text-[11px] ktra-text-soft">{row.description}</div>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                <p className="mt-2 text-[11px] ktra-text-soft">
                  آخر مئة حركة على الشركة — تشمل ما فعله سوبر أدمن بها (الخطة، الحالة، الحدود، الوحدات). السجل الكامل مكانه صفحة «سجل النشاط» داخل الشركة.
                </p>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
