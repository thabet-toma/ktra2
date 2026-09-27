import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, ShieldCheck } from "lucide-react";

import {
  listPendingAccountants, openAccountantWorkspace, verifyAccountant,
  type PlatformAccountantProfile,
} from "../../../services/platformAdminApi";
import { useToast } from "../../../contexts/ToastContext";
import { enterOfficeShell } from "../../../utils/officeShell";
import { formatDateValue } from "../../../utils/formatDate";
import { formatNumber } from "../../../utils/formatNumber";
import { ErrorBox, LoadingRow, Panel, PanelHead, SectionHeader, errorText } from "./consoleShared";

/** SA-5 — توثيق المحاسبين القانونيين (ق6: قرار يدوي) + باب واجهة المحاسب لسوبر أدمن. */
export const AccountantsSection: React.FC = () => {
  const toast = useToast();
  const [profiles, setProfiles] = useState<PlatformAccountantProfile[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [openingWorkspace, setOpeningWorkspace] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProfiles((await listPendingAccountants()).results);
    } catch (cause) {
      setError(errorText(cause, "تعذّر تحميل ملفات المحاسبين"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const decide = async (profile: PlatformAccountantProfile, decision: "approve" | "reject" | "bar") => {
    const reason = (reasons[profile.id] || "").trim();
    if (decision !== "approve" && !reason) {
      toast("سبب القرار مطلوب عند الرفض أو المنع.", "error");
      return;
    }
    setBusy(profile.id);
    try {
      await verifyAccountant(profile.id, decision, reason);
      toast(decision === "approve" ? "وُثِّق ملف المحاسب." : "سُجِّل القرار.", "success");
      void load();
    } catch (cause) {
      toast(errorText(cause, "تعذّر تنفيذ القرار."), "error");
    } finally {
      setBusy(null);
    }
  };

  /** يفتح واجهة المحاسب القانوني لحساب السوبر أدمن نفسه ثم ينقله إليها فوراً. */
  const openAccountantView = async () => {
    setOpeningWorkspace(true);
    try {
      const result = await openAccountantWorkspace();
      // تُحفظ الشركة التجارية الحالية قبل تبديلها بالمكتب، فترجع كما هي عند «العودة للوحة المنصة».
      enterOfficeShell();
      localStorage.setItem("tenantId", String(result.office.tenant_id));
      localStorage.removeItem("branchId");
      toast(`جاهز: ${result.office.name}. تُفتح الآن واجهة مكتب المحاسبة.`, "success");
      window.location.assign("/office");
    } catch (cause) {
      setOpeningWorkspace(false);
      toast(errorText(cause, "تعذّر فتح واجهة المحاسب."), "error");
    }
  };

  return (
    <div>
      <SectionHeader
        title="توثيق المحاسبين"
        subtitle="التوثيق يدوي: تحقّق من الرخصة والرقم الضريبي وعنوان العمل قبل القبول. «منع» يوقف ارتباطه بأي شركة"
        loading={loading}
        onRefresh={() => void load()}
      />
      <ErrorBox message={error} onRetry={() => void load()} />

      <Panel label="ملفات بانتظار التحقق" className="mb-4">
        <PanelHead title={`بانتظار التحقق (${formatNumber(profiles?.length ?? 0)})`} />
        {loading && !profiles ? <LoadingRow /> : (
          <ul className="divide-y divide-[var(--color-border)]">
            {(profiles ?? []).length === 0 ? (
              <li className="px-4 py-6 text-center ktra-text-soft">لا ملفات بانتظار التحقق</li>
            ) : (profiles ?? []).map((profile) => (
              <li key={profile.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-[16rem]">
                  <p className="font-semibold text-[var(--color-text)]">{profile.full_name}</p>
                  <p className="text-xs ktra-text-soft">
                    {profile.email} · ضريبي {profile.tax_registration_number}
                    {profile.license_number ? ` · رخصة ${profile.license_number}` : ""}
                    {` · سُجِّل ${formatDateValue(profile.created_at)}`}
                  </p>
                  <p className="text-[11px] ktra-text-soft">{profile.business_address}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    className="ktra-input h-9 w-56"
                    placeholder="سبب الرفض/المنع"
                    aria-label={`سبب قرار ${profile.full_name}`}
                    value={reasons[profile.id] || ""}
                    onChange={(event) => setReasons((current) => ({ ...current, [profile.id]: event.target.value }))}
                  />
                  <button type="button" disabled={busy === profile.id} onClick={() => void decide(profile, "approve")} className="ktra-btn ktra-btn-primary">توثيق</button>
                  <button type="button" disabled={busy === profile.id} onClick={() => void decide(profile, "reject")} className="ktra-btn">رفض</button>
                  <button type="button" disabled={busy === profile.id} onClick={() => void decide(profile, "bar")} className="ktra-btn text-red-600">منع</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel label="واجهة المحاسب القانوني">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h3 className="font-bold text-[var(--color-text)]">واجهة شركة المحاسبة القانونية</h3>
            <p className="text-xs ktra-text-soft">
              تفتح لحسابك ملفاً مهنياً موثَّقاً ومكتب محاسبة مرخَّصاً، فتدخل الواجهة كما يراها المحاسب.
            </p>
          </div>
          <button type="button" onClick={() => void openAccountantView()} disabled={openingWorkspace} className="ktra-btn ktra-btn-primary">
            {openingWorkspace ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            افتح واجهة المحاسب القانوني
          </button>
        </div>
      </Panel>
    </div>
  );
};
