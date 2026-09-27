import React, { useEffect, useState } from "react";

import { Modal } from "../../ui";
import { useToast } from "../../../contexts/ToastContext";
import {
  createPlatformCompany, getCompanyCreationOptions,
  type CompanyCreationInput, type CompanyCreationOptions,
} from "../../../services/platformAdminApi";
import { formatNumber } from "../../../utils/formatNumber";
import { ErrorBox, LoadingRow, errorText } from "./consoleShared";

type FieldErrors = Partial<Record<keyof CompanyCreationInput | "detail", string>>;

const EMPTY: CompanyCreationInput = { name: "", owner_email: "", template: "general", plan: "Trial" };

const fieldClass = "ktra-input h-9 w-full";
const labelClass = "mb-1 block text-xs font-bold ktra-text-soft";

/**
 * SA-9 — شركة لعميل من اللوحة. الخادم ينشئها عبر `create_company` نفسها والمالك
 * مديرها؛ المالك حسابٌ مسجَّل (لا دعوات حسابات عامة في المنتج)، ورفضُ بريدٍ بلا حساب
 * يقول للسوبر أدمن ما يطلبه من العميل بدل خطأٍ خام.
 */
export const CreateCompanyDialog: React.FC<{
  open: boolean;
  onClose: () => void;
  onCreated: (companyId: number) => void;
}> = ({ open, onClose, onCreated }) => {
  const toast = useToast();
  const [options, setOptions] = useState<CompanyCreationOptions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState<CompanyCreationInput>(EMPTY);
  const [trialDays, setTrialDays] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || options) return;
    let cancelled = false;
    getCompanyCreationOptions()
      .then((result) => {
        if (cancelled) return;
        setOptions(result);
        setTrialDays(String(result.default_trial_days));
      })
      .catch((cause) => { if (!cancelled) setLoadError(errorText(cause, "تعذّر تحميل خيارات الإنشاء")); });
    return () => { cancelled = true; };
  }, [open, options]);

  const close = () => {
    if (saving) return;
    setForm(EMPTY);
    setEndsAt("");
    setErrors({});
    if (options) setTrialDays(String(options.default_trial_days));
    onClose();
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    const payload: CompanyCreationInput = { ...form, name: form.name.trim(), owner_email: form.owner_email.trim() };
    if (form.plan === "Trial" && trialDays) payload.trial_days = Number(trialDays);
    if (form.plan !== "Trial" && endsAt) payload.subscription_ends_at = endsAt;
    try {
      const company = await createPlatformCompany(payload);
      toast(`أُنشئت «${company.name}» وأُبلغ مالكها`, "success");
      setForm(EMPTY);
      setEndsAt("");
      onCreated(company.id);
    } catch (cause) {
      const fieldErrors = (cause as { fieldErrors?: Record<string, string> }).fieldErrors ?? {};
      const known: FieldErrors = {};
      (["name", "owner_email", "template", "plan", "trial_days", "subscription_ends_at"] as const).forEach((key) => {
        if (fieldErrors[key]) known[key] = fieldErrors[key];
      });
      if (Object.keys(known).length === 0) known.detail = errorText(cause, "تعذّر إنشاء الشركة");
      setErrors(known);
    } finally {
      setSaving(false);
    }
  };

  const fieldError = (key: keyof FieldErrors) =>
    errors[key] ? <p role="alert" className="mt-1 text-xs text-red-600">{errors[key]}</p> : null;

  return (
    <Modal
      open={open}
      onClose={close}
      title="إنشاء شركة لعميل"
      footer={(
        <>
          <button type="button" className="ktra-btn" onClick={close} disabled={saving}>إلغاء</button>
          <button type="submit" form="create-company-form" className="ktra-btn ktra-btn-primary" disabled={saving || !options}>
            {saving ? "جارٍ الإنشاء…" : "إنشاء الشركة"}
          </button>
        </>
      )}
    >
      {!options ? (
        loadError ? <ErrorBox message={loadError} /> : <LoadingRow />
      ) : (
        <form id="create-company-form" onSubmit={(event) => void submit(event)} className="space-y-3" dir="rtl">
          <ErrorBox message={errors.detail ?? null} />
          <div>
            <label htmlFor="new-company-name" className={labelClass}>اسم الشركة</label>
            <input id="new-company-name" className={fieldClass} required value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })} />
            {fieldError("name")}
          </div>
          <div>
            <label htmlFor="new-company-owner" className={labelClass}>بريد المالك (حسابه المسجَّل في كترا)</label>
            <input id="new-company-owner" type="email" dir="ltr" className={fieldClass} required value={form.owner_email}
              onChange={(event) => setForm({ ...form, owner_email: event.target.value })} />
            {fieldError("owner_email") ?? (
              <p className="mt-1 text-xs ktra-text-soft">يصير مدير الشركة ويصله بريدٌ بأنها جاهزة. ليس له حساب؟ يسجّل أولاً من صفحة كترا الرئيسية.</p>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="new-company-template" className={labelClass}>نوع النشاط</label>
              <select id="new-company-template" className={fieldClass} value={form.template}
                onChange={(event) => setForm({ ...form, template: event.target.value })}>
                {options.templates.map((row) => <option key={row.key} value={row.key}>{row.label}</option>)}
              </select>
              {fieldError("template")}
            </div>
            <div>
              <label htmlFor="new-company-plan" className={labelClass}>الخطة</label>
              <select id="new-company-plan" className={fieldClass} value={form.plan}
                onChange={(event) => setForm({ ...form, plan: event.target.value })}>
                {options.plans.map((row) => <option key={row.key} value={row.key}>{row.label}</option>)}
              </select>
              {fieldError("plan")}
            </div>
          </div>
          {form.plan === "Trial" ? (
            <div>
              <label htmlFor="new-company-trial" className={labelClass}>
                مدة التجربة بالأيام (حتى {formatNumber(options.max_trial_days)})
              </label>
              <input id="new-company-trial" type="number" min={1} max={options.max_trial_days} className={fieldClass}
                value={trialDays} onChange={(event) => setTrialDays(event.target.value)} />
              {fieldError("trial_days")}
            </div>
          ) : (
            <div>
              <label htmlFor="new-company-ends" className={labelClass}>انتهاء الاشتراك (اتركه فارغاً لاشتراكٍ بلا انتهاء)</label>
              <input id="new-company-ends" type="date" className={fieldClass} value={endsAt}
                onChange={(event) => setEndsAt(event.target.value)} />
              {fieldError("subscription_ends_at")}
            </div>
          )}
        </form>
      )}
    </Modal>
  );
};
