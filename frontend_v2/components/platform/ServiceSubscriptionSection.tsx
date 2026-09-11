import React, { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, Loader2, RotateCcw } from "lucide-react";

import {
  activateExistingSubscription,
  activatePaidSubscription,
  cancelServiceSubscription,
  listServiceSubscriptions,
  listSubscriptionEvents,
  resumeServiceSubscription,
  startServiceTrial,
  suspendServiceSubscription,
  updateSubscriptionSettings,
  withdrawScheduledCancellation,
  type BillingCustomerOption,
  type ServiceSubscriptionEventRow,
  type ServiceSubscriptionRow,
} from "../../services/platformOpsApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  ACTIONS_REQUIRING_BILLING_CUSTOMER,
  describePlatformOpsError,
  formatEngagementCount,
  formatTrialRemainingLabel,
  getAllowedSubscriptionActions,
  validateCommercialNumbers,
  type SubscriptionAction,
} from "../../utils/platformSubscriptionManagement";
import { BillingCustomerPicker } from "./BillingCustomerPicker";

interface Props {
  companyId: number;
}

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لإدارة اشتراك هذه الشركة.", "تعذّر إتمام العملية.");

/** بطاقة خدمة الإدخال داخل لوحة تحكّم الشركة — التذكرة 210-A. */
export const ServiceSubscriptionSection: React.FC<Props> = ({ companyId }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [subscription, setSubscription] = useState<ServiceSubscriptionRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [eventsOpen, setEventsOpen] = useState(false);
  const [events, setEvents] = useState<ServiceSubscriptionEventRow[] | null>(null);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState({
    plan: "", monthly_fee: "", included_quota: "", overage_unit_price: "",
  });
  const [editingSettings, setEditingSettings] = useState(false);
  const [settingsReason, setSettingsReason] = useState("");
  const [cancelChoiceOpen, setCancelChoiceOpen] = useState(false);
  // عميل الفوترة والباقة للتفعيل المدفوع أو التحويل — يُختاران قبل أن يُفعَّل الزر.
  const [activationCustomer, setActivationCustomer] = useState<BillingCustomerOption | null>(null);
  const [activationPlan, setActivationPlan] = useState("");
  const [changingCustomer, setChangingCustomer] = useState(false);
  const [customerReason, setCustomerReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listServiceSubscriptions({ company: companyId });
      const row = rows[0] ?? null;
      setSubscription(row);
      setActivationCustomer(null);
      setActivationPlan("");
      setChangingCustomer(false);
      setCustomerReason("");
      setSettingsReason("");
      if (row) {
        setSettingsDraft({
          plan: row.plan,
          monthly_fee: row.monthly_fee,
          included_quota: String(row.included_quota),
          overage_unit_price: row.overage_unit_price,
        });
      }
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setEventsOpen(false); setEvents(null); }, [companyId]);

  const run = async (action: () => Promise<unknown>, okMsg: string): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast(okMsg, "success");
      setReason("");
      setEvents(null);
      setEventsOpen(false);
      await load();
      return true;
    } catch (cause) {
      const message = displayError(cause);
      // تعارض حالة: أعد قراءة الصف كي تُعرض الأفعال الصحيحة، ثم أبقِ سبب التعارض ظاهراً (`load` يمسح الخطأ أولاً).
      if ((cause as { status?: number } | null)?.status === 409) await load();
      setError(message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const loadEvents = useCallback(async () => {
    if (!subscription) return;
    setEventsLoading(true);
    try {
      setEvents(await listSubscriptionEvents(subscription.id));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setEventsLoading(false);
    }
  }, [subscription]);

  const toggleEvents = () => {
    const next = !eventsOpen;
    setEventsOpen(next);
    if (next && events === null) void loadEvents();
  };

  const requireReason = (): string | null => {
    const trimmed = reason.trim();
    if (!trimmed) {
      setError("السبب مطلوب لهذا الإجراء.");
      return null;
    }
    return trimmed;
  };

  const status = subscription?.status ?? null;
  const hasSchedule = Boolean(subscription?.scheduled_cancellation_date);
  const allowed = getAllowedSubscriptionActions(status, hasSchedule);
  const needsActivationForm = allowed.some((action) => ACTIONS_REQUIRING_BILLING_CUSTOMER.includes(action));
  const showsCurrentCustomer = status === "active" || status === "suspended";

  const onAction = async (action: SubscriptionAction) => {
    const plan = activationPlan.trim() || undefined;
    if (action === "start_trial") {
      await run(() => startServiceTrial(companyId, plan), "بدأت تجربة الشركة على خدمة الإدخال.");
    } else if (action === "activate_paid" || action === "convert_to_paid") {
      if (!activationCustomer) {
        setError("اختر عميل الفوترة قبل التفعيل المدفوع.");
        return;
      }
      const customerId = activationCustomer.id;
      if (!subscription) {
        await run(() => activatePaidSubscription(companyId, customerId, plan), "تم تفعيل اشتراك مدفوع للشركة.");
      } else {
        await run(
          () => activateExistingSubscription(subscription.id, customerId, plan),
          action === "convert_to_paid" ? "تحوّلت التجربة إلى اشتراك مدفوع." : "أُعيد تفعيل الاشتراك المدفوع.",
        );
      }
    } else if (action === "suspend" && subscription) {
      const value = requireReason();
      if (!value) return;
      const confirmed = await confirm({
        title: "تعليق اشتراك الخدمة",
        message: `سيُعلَّق معه ${formatEngagementCount(subscription.active_engagements_count)}.`,
        confirmText: "تعليق الاشتراك",
        danger: true,
      });
      if (!confirmed) return;
      await run(() => suspendServiceSubscription(subscription.id, value), "تم تعليق الاشتراك.");
    } else if (action === "resume" && subscription) {
      await run(() => resumeServiceSubscription(subscription.id), "تم استئناف الاشتراك.");
    } else if (action === "cancel" && subscription) {
      if (!requireReason()) return;
      setCancelChoiceOpen(true);
    } else if (action === "withdraw_cancellation" && subscription) {
      await run(() => withdrawScheduledCancellation(subscription.id), "تم سحب جدولة الإلغاء.");
    } else if (action === "edit_settings") {
      setEditingSettings((current) => !current);
    }
  };

  const saveSettings = async () => {
    if (!subscription) return;
    if (!settingsDraft.plan.trim()) {
      setError("أدخل الباقة قبل الحفظ.");
      return;
    }
    // نفس حارس الأرقام الذي تستعمله مسودة السياسة — حقل فارغ ليس صفراً.
    const numbersError = validateCommercialNumbers({
      monthly_fee: settingsDraft.monthly_fee,
      included_quota: settingsDraft.included_quota,
      overage_unit_price: settingsDraft.overage_unit_price,
    });
    if (numbersError) { setError(numbersError); return; }
    const monthlyFee = Number(settingsDraft.monthly_fee);
    const overageUnitPrice = Number(settingsDraft.overage_unit_price);
    const quota = Number(settingsDraft.included_quota);
    // تُرسل الحقول التي تغيّرت وحدها — حدث التدقيق لا يسجّل قيماً لم تتبدل.
    const changes: Parameters<typeof updateSubscriptionSettings>[1] = {};
    if (settingsDraft.plan.trim() !== subscription.plan) changes.plan = settingsDraft.plan.trim();
    if (monthlyFee !== Number(subscription.monthly_fee)) changes.monthly_fee = settingsDraft.monthly_fee;
    if (quota !== subscription.included_quota) changes.included_quota = quota;
    if (overageUnitPrice !== Number(subscription.overage_unit_price)) {
      changes.overage_unit_price = settingsDraft.overage_unit_price;
    }
    if (Object.keys(changes).length === 0) {
      setError("لا تغييرات للحفظ.");
      return;
    }
    const changeReason = settingsReason.trim();
    if (!changeReason) {
      setError("اكتب سبب تعديل شروط هذا الاشتراك.");
      return;
    }
    const saved = await run(
      () => updateSubscriptionSettings(subscription.id, { ...changes, reason: changeReason }),
      "تم حفظ الإعدادات التجارية.",
    );
    if (saved) setEditingSettings(false);
  };

  const replaceBillingCustomer = (customer: BillingCustomerOption | null) => {
    if (!subscription) return;
    // الاشتراك المدفوع لا يبقى بلا عميل: «إزالة» تفتح البحث عن بديل ولا تُفرغ الحقل على الخادم.
    if (!customer) {
      setChangingCustomer(true);
      return;
    }
    // تغيير عميل الفوترة تعديلٌ لشروط الاشتراك كغيره — يلزمه سبب يُحفظ في حدث التدقيق.
    const changeReason = customerReason.trim();
    if (!changeReason) {
      setError("اكتب سبب تغيير عميل الفوترة قبل اختيار العميل الجديد.");
      return;
    }
    void run(
      () => updateSubscriptionSettings(subscription.id, { billing_customer: customer.id, reason: changeReason }),
      "تم تحديث عميل الفوترة.",
    );
  };

  return (
    <section aria-label="خدمة الإدخال" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
      <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">خدمة الإدخال والمتابعة</h3>

      {error && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
          <button type="button" onClick={() => void load()} className="mr-2 underline">إعادة المحاولة</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm ktra-text-soft" role="status">
          <Loader2 className="h-4 w-4 animate-spin" /> جارٍ تحميل حالة الخدمة…
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold text-[var(--color-text)]">
              الحالة: {subscription ? subscription.status_display : "غير مفعّلة"}
            </span>
            {subscription?.status === "trial" && (
              <span className="text-xs ktra-text-soft">
                {formatTrialRemainingLabel(subscription.trial_ends_at)}
              </span>
            )}
            {subscription?.scheduled_cancellation_date && (
              <span className="text-xs font-semibold text-amber-600">
                إلغاء مجدول — آخر يوم خدمة {formatDateValue(subscription.scheduled_cancellation_date)}
              </span>
            )}
          </div>

          {subscription && (
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <p>الباقة: {subscription.plan}</p>
              <p>الرسم الشهري: {formatNumber(subscription.monthly_fee)}</p>
              <p>الحصة: {formatNumber(subscription.consumed_quota)} / {formatNumber(subscription.included_quota)}</p>
              <p>سعر الزائد: {formatNumber(subscription.overage_unit_price)}</p>
            </div>
          )}

          {showsCurrentCustomer && subscription && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-bold ktra-text-soft">عميل الفوترة</p>
              {changingCustomer && (
                <input
                  className="ktra-input mb-1 h-8 w-full"
                  value={customerReason}
                  onChange={(event) => setCustomerReason(event.target.value)}
                  placeholder="سبب تغيير عميل الفوترة (إلزامي)"
                  maxLength={500}
                  disabled={busy}
                />
              )}
              <BillingCustomerPicker
                value={changingCustomer ? null : subscription.billing_customer}
                valueLabel={subscription.billing_customer_name}
                onChange={replaceBillingCustomer}
                subscriptionId={subscription.id}
                disabled={busy}
              />
            </div>
          )}

          {needsActivationForm && (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-bold ktra-text-soft">عميل الفوترة للاشتراك المدفوع</p>
                <BillingCustomerPicker
                  value={activationCustomer?.id ?? null}
                  valueLabel={activationCustomer?.name ?? null}
                  onChange={setActivationCustomer}
                  // التحويل يتحقّق بشركة فوترة لقطة التجربة؛ التفعيل الجديد أو إعادة التفعيل
                  // بشركة فوترة نسخة السياسة السارية **لنفس الخطة المطلوبة** — لا العامّة.
                  subscriptionId={status === "trial" && subscription ? subscription.id : undefined}
                  plan={activationPlan.trim() || undefined}
                  disabled={busy}
                />
              </div>
              {status === "trial" && subscription ? (
                <p className="self-end text-xs ktra-text-soft">
                  التحويل يُبقي خطة التجربة «{subscription.plan}» وأسعارها الملتقطة.
                </p>
              ) : (
                <label className="space-y-1 text-xs">
                  <span className="font-bold ktra-text-soft">الخطة</span>
                  <input
                    className="ktra-input h-8 w-full"
                    value={activationPlan}
                    onChange={(event) => setActivationPlan(event.target.value)}
                    placeholder="standard"
                    maxLength={50}
                    disabled={busy}
                  />
                </label>
              )}
            </div>
          )}

          {editingSettings && subscription && (
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {([
                ["plan", "الباقة"],
                ["monthly_fee", "الرسم الشهري"],
                ["included_quota", "الحصة"],
                ["overage_unit_price", "سعر الزائد"],
              ] as const).map(([field, label]) => (
                <label key={field} className="space-y-1 text-xs">
                  <span className="ktra-text-soft">{label}</span>
                  <input
                    className="ktra-input h-8 w-full"
                    value={settingsDraft[field]}
                    onChange={(event) => setSettingsDraft((current) => ({ ...current, [field]: event.target.value }))}
                  />
                </label>
              ))}
              <p className="col-span-2 text-[11px] ktra-text-soft sm:col-span-4">
                تعديل شروط هذا الاشتراك وحده استثناء عن نسخة سياسته، ويسري على أول فوترة شهرية تصدر بعد الحفظ.
              </p>
              <input
                className="ktra-input col-span-2 h-8 sm:col-span-4"
                value={settingsReason}
                onChange={(event) => setSettingsReason(event.target.value)}
                placeholder="سبب التعديل (إلزامي)"
                maxLength={500}
                disabled={busy}
              />
              <button type="button" onClick={saveSettings} disabled={busy} className="ktra-btn ktra-btn-primary col-span-2">
                حفظ الإعدادات التجارية
              </button>
            </div>
          )}

          {(allowed.includes("suspend") || allowed.includes("cancel")) && (
            <input
              className="ktra-input mt-3 h-9 w-full"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="سبب التعليق أو الإلغاء"
              disabled={busy}
            />
          )}

          {cancelChoiceOpen && subscription && (
            <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <p>اختر طريقة الإلغاء. الإلغاء الفوري سيعلّق معه {formatEngagementCount(subscription.active_engagements_count)}.</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" className="ktra-btn" disabled={busy} onClick={() => {
                  const value = requireReason();
                  if (!value) return;
                  setCancelChoiceOpen(false);
                  void run(() => cancelServiceSubscription(subscription.id, value), "جُدول الإلغاء لنهاية الدورة الحالية.");
                }}>جدولة الإلغاء لنهاية الدورة</button>
                {/* لا `ktra-btn` هنا: خلفيتها خارج طبقات Tailwind فتغلب `bg-red-600` ويبقى الزر المدمّر بلون عادي. */}
                <button
                  type="button"
                  className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void (async () => {
                    const value = requireReason();
                    if (!value) return;
                    const confirmed = await confirm({
                      title: "إلغاء فوري",
                      message: `سيُعلَّق معه ${formatEngagementCount(subscription.active_engagements_count)} الآن.`,
                      confirmText: "إلغاء فوري",
                      danger: true,
                    });
                    if (!confirmed) return;
                    setCancelChoiceOpen(false);
                    await run(() => cancelServiceSubscription(subscription.id, value, true), "تم الإلغاء فوراً.");
                  })()}
                >
                  إلغاء فوري
                </button>
                <button type="button" className="ktra-btn" onClick={() => setCancelChoiceOpen(false)}>تراجع</button>
              </div>
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            {allowed.map((action) => {
              const blockedOnCustomer = ACTIONS_REQUIRING_BILLING_CUSTOMER.includes(action) && !activationCustomer;
              return (
                <button
                  key={action}
                  type="button"
                  disabled={busy || blockedOnCustomer}
                  title={blockedOnCustomer ? "اختر عميل الفوترة أولاً" : undefined}
                  onClick={() => void onAction(action)}
                  className="ktra-btn disabled:opacity-50"
                >
                  {ACTION_LABEL[action]}
                </button>
              );
            })}
          </div>

          {subscription && (
            <div className="mt-4">
              <button
                type="button"
                onClick={toggleEvents}
                aria-expanded={eventsOpen}
                className="flex w-full items-center justify-between gap-2 text-right text-xs font-bold ktra-text-soft"
              >
                سجل الأحداث
                {eventsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
              </button>
              {eventsOpen && (
                eventsLoading ? (
                  <div className="flex items-center gap-2 py-3 text-xs ktra-text-soft">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> جارٍ التحميل…
                  </div>
                ) : !events || events.length === 0 ? (
                  <p className="py-3 text-xs ktra-text-soft">لا أحداث بعد.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-xs">
                    {events.map((event) => (
                      <li key={event.id} className="border-t border-[var(--color-border)] pt-1">
                        <span className="font-semibold">{event.action_display}</span>
                        {" — "}
                        {formatDateValue(event.created_at)}
                        {event.reason && <span className="ktra-text-soft"> · {event.reason}</span>}
                      </li>
                    ))}
                    <li className="pt-1">
                      <button
                        type="button"
                        onClick={() => void loadEvents()}
                        className="ktra-iconbtn"
                        aria-label="تحديث سجل الأحداث"
                        title="تحديث سجل الأحداث"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  </ul>
                )
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
};

const ACTION_LABEL: Record<SubscriptionAction, string> = {
  start_trial: "ابدأ تجربة",
  activate_paid: "فعّل اشتراكاً مدفوعاً",
  convert_to_paid: "حوّل إلى اشتراك مدفوع",
  suspend: "تعليق",
  resume: "استئناف",
  cancel: "إلغاء",
  withdraw_cancellation: "سحب الإلغاء المجدول",
  edit_settings: "تعديل الإعدادات التجارية",
};
