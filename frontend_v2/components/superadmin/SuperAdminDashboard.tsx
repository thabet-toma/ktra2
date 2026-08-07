import React, { useEffect, useState } from "react";
import {
  Building2, CheckCircle2, CirclePause, ClipboardList, RefreshCw, Settings2,
  ShieldCheck, Trash2, UserPlus, Users,
} from "lucide-react";

import {
  getPlatformDashboard, grantSuperAdmin, listPendingAccountants, listSuperAdmins,
  openAccountantWorkspace, revokeSuperAdmin, updatePlatformCompany, verifyAccountant,
  type PlatformAccountantProfile, type PlatformDashboardData, type PlatformSuperAdmin,
} from "../../services/platformAdminApi";
import {
  COMPANY_PLAN_LABELS, COMPANY_STATUS_LABELS, PlatformCompanyPanel,
} from "./PlatformCompanyPanel";
import { enterOfficeShell } from "../../utils/officeShell";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import type { AppView } from "../../types";
import { formatDateValue } from "../../utils/formatDate";


interface Props {
  onNavigate: (view: AppView) => void;
}

const statusLabel = (status: string) => COMPANY_STATUS_LABELS[status] || status;

export const SuperAdminDashboard: React.FC<Props> = ({ onNavigate }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [data, setData] = useState<PlatformDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [admins, setAdmins] = useState<PlatformSuperAdmin[]>([]);
  const [identifier, setIdentifier] = useState("");
  const [granting, setGranting] = useState(false);
  const [assigningExample, setAssigningExample] = useState(false);
  /** الشركة المفتوحة في لوحة التحكم (خطة/حالة/استيراد/أعضاء) */
  const [managedCompanyId, setManagedCompanyId] = useState<number | null>(null);
  /** ق6: التحقق المهني للمحاسبين قرار يدوي لسوبر أدمن المنصة. */
  const [pendingAccountants, setPendingAccountants] = useState<PlatformAccountantProfile[]>([]);
  const [accountantBusy, setAccountantBusy] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState<Record<number, string>>({});
  const [openingWorkspace, setOpeningWorkspace] = useState(false);

  const loadAdmins = () => {
    listSuperAdmins()
      .then(setAdmins)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "تعذّر تحميل قائمة السوبر أدمن"));
  };

  /** يفتح واجهة المحاسب القانوني لحساب السوبر أدمن نفسه ثم ينقله إليها فوراً. */
  const openAccountantView = async () => {
    setOpeningWorkspace(true);
    try {
      const result = await openAccountantWorkspace();
      // تُحفظ الشركة التجارية الحالية قبل تبديلها بالمكتب، فترجع كما هي عند
      // «العودة للوحة المنصة».
      enterOfficeShell();
      localStorage.setItem("tenantId", String(result.office.tenant_id));
      localStorage.removeItem("branchId");
      toast(`جاهز: ${result.office.name}. تُفتح الآن واجهة مكتب المحاسبة.`, "success");
      window.location.assign("/office");
    } catch (cause) {
      setOpeningWorkspace(false);
      toast(cause instanceof Error ? cause.message : "تعذّر فتح واجهة المحاسب.", "error");
    }
  };

  const loadPendingAccountants = () => {
    listPendingAccountants()
      .then((res) => setPendingAccountants(res.results))
      .catch(() => setPendingAccountants([]));
  };

  const decideAccountant = async (
    profile: PlatformAccountantProfile,
    decision: "approve" | "reject" | "bar",
  ) => {
    const reason = (rejectReason[profile.id] || "").trim();
    if (decision !== "approve" && !reason) {
      toast("سبب القرار مطلوب عند الرفض أو المنع.", "error");
      return;
    }
    setAccountantBusy(profile.id);
    try {
      await verifyAccountant(profile.id, decision, reason);
      toast(decision === "approve" ? "وُثِّق ملف المحاسب." : "سُجِّل القرار.", "success");
      loadPendingAccountants();
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّر تنفيذ القرار.", "error");
    } finally {
      setAccountantBusy(null);
    }
  };

  const load = () => {
    setLoading(true);
    setError(null);
    loadAdmins();
    loadPendingAccountants();
    getPlatformDashboard()
      .then(setData)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "تعذّر تحميل لوحة المنصة"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const grant = async () => {
    const value = identifier.trim();
    if (!value) return;
    setGranting(true);
    setError(null);
    try {
      const added = await grantSuperAdmin(value);
      setAdmins((current) => [...current.filter((row) => row.id !== added.id), added]);
      setIdentifier("");
      toast(`صار «${added.full_name}» سوبر أدمن`, "success");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّرت الترقية");
    } finally {
      setGranting(false);
    }
  };

  const revoke = async (admin: PlatformSuperAdmin) => {
    const ok = await confirm({
      title: "سحب صلاحية السوبر أدمن",
      message: `سيفقد «${admin.full_name}» الوصول إلى إدارة المنصة. الحساب وعضويات الشركات تبقى كما هي.`,
      confirmText: "سحب",
      danger: true,
    });
    if (!ok) return;
    setError(null);
    try {
      await revokeSuperAdmin(admin.id);
      setAdmins((current) => current.filter((row) => row.id !== admin.id));
      toast("تم سحب الصلاحية", "success");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر سحب الصلاحية");
    }
  };

  const assignExampleCompany = async (value: string) => {
    const current = data?.company_rows.find((company) => company.is_example);
    const nextId = value ? Number(value) : null;
    if ((current?.id ?? null) === nextId) return;
    setAssigningExample(true);
    setError(null);
    try {
      if (nextId !== null) {
        await updatePlatformCompany(nextId, { is_example: true });
        toast("تم تعيين شركة المثال وإتاحتها لكل المستخدمين", "success");
      } else if (current) {
        await updatePlatformCompany(current.id, { is_example: false });
        toast("تم إلغاء تعيين شركة المثال", "success");
      }
      load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر تعيين شركة المثال");
    } finally {
      setAssigningExample(false);
    }
  };

  if (loading && !data) {
    return <div className="p-8 text-center aseel-text-soft" role="status">جارٍ تحميل لوحة المنصة…</div>;
  }
  if (error && !data) {
    return (
      <div className="p-8 text-center" role="alert">
        <p className="text-red-600">{error}</p>
        <button type="button" onClick={load} className="aseel-btn aseel-btn-primary mt-3">إعادة المحاولة</button>
      </div>
    );
  }
  if (!data) return null;

  const cards = [
    { label: "إجمالي الشركات", value: data.companies.total, icon: Building2, tone: "text-blue-600 bg-blue-50 dark:bg-blue-950/30" },
    { label: "الشركات الفعالة", value: data.companies.active, icon: CheckCircle2, tone: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30" },
    { label: "الشركات الموقوفة", value: data.companies.suspended, icon: CirclePause, tone: "text-amber-600 bg-amber-50 dark:bg-amber-950/30" },
    { label: "المستخدمون النشطون", value: data.users.active, icon: Users, tone: "text-sky-600 bg-sky-50 dark:bg-sky-950/30" },
  ];

  return (
    <main className="p-4 md:p-6" dir="rtl">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white">
            <ShieldCheck className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-xl font-bold text-[var(--color-text)]">لوحة تحكم السوبر أدمن</h1>
            <p className="text-sm aseel-text-soft">نظرة تشغيلية على المنصة والشركات، منفصلة عن لوحة الشركة</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => onNavigate("development-notes")} className="aseel-btn aseel-btn-primary">
            <ClipboardList className="h-4 w-4" aria-hidden="true" /> ملاحظات التطوير
          </button>
          <button type="button" onClick={load} className="aseel-iconbtn" title="تحديث" aria-label="تحديث لوحة المنصة">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </header>

      {error && <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>}

      <section aria-label="مؤشرات المنصة" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, tone }) => (
          <article key={label} className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className={`flex h-10 w-10 items-center justify-center rounded-md ${tone}`}><Icon className="h-5 w-5" /></span>
            <div><p className="text-xs aseel-text-soft">{label}</p><p className="text-2xl font-bold text-[var(--color-text)]">{value}</p></div>
          </article>
        ))}
      </section>

      <section aria-label="سوبر أدمن المنصة" className="mt-5 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-3">
          <div>
            <h2 className="font-bold text-[var(--color-text)]">سوبر أدمن المنصة</h2>
            <p className="text-xs aseel-text-soft">ترقية مستخدم مسجَّل باسمه أو بريده — بلا إنشاء حساب ولا كلمة سر</p>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="super-admin-identifier" className="sr-only">اسم المستخدم أو البريد</label>
            <input
              id="super-admin-identifier"
              className="aseel-input h-9 w-56"
              placeholder="اسم المستخدم أو البريد"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void grant(); }}
            />
            <button type="button" onClick={() => void grant()} disabled={granting || !identifier.trim()} className="aseel-btn aseel-btn-primary">
              <UserPlus className="h-4 w-4" aria-hidden="true" /> ترقية
            </button>
          </div>
        </div>
        <ul className="divide-y divide-[var(--color-border)]">
          {admins.length === 0 ? (
            <li className="px-4 py-6 text-center aseel-text-soft">لا سوبر أدمن مسجَّل بعد</li>
          ) : admins.map((admin) => (
            <li key={admin.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
              <div>
                <p className="font-semibold text-[var(--color-text)]">{admin.full_name}</p>
                <p className="text-xs aseel-text-soft">{admin.username}{admin.email ? ` · ${admin.email}` : ""}</p>
              </div>
              {admin.removable ? (
                <button type="button" onClick={() => void revoke(admin)} className="aseel-iconbtn text-red-600" title="سحب الصلاحية" aria-label={`سحب صلاحية ${admin.full_name}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
              ) : (
                <span className="text-xs aseel-text-soft">مثبَّت في إعدادات المنصة</span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="بوابة المحاسب القانوني" className="mt-5 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h2 className="font-bold text-[var(--color-text)]">واجهة شركة المحاسبة القانونية</h2>
            <p className="text-xs aseel-text-soft">
              تفتح لحسابك ملفاً مهنياً موثَّقاً ومكتب محاسبة مرخَّصاً، فتدخل الواجهة كما يراها المحاسب
              وترسل منها طلب ارتباط لأي شركة مسجَّلة عندنا لتراجع بياناتها.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void openAccountantView()}
            disabled={openingWorkspace}
            className="aseel-btn aseel-btn-primary"
          >
            {openingWorkspace ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            افتح واجهة المحاسب القانوني
          </button>
        </div>
      </section>

      <section aria-label="ملفات المحاسبين بانتظار التحقق" className="mt-5 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="border-b border-[var(--color-border)] px-4 py-3">
          <h2 className="font-bold text-[var(--color-text)]">توثيق المحاسبين القانونيين ({pendingAccountants.length})</h2>
          <p className="text-xs aseel-text-soft">
            التوثيق يدوي (ق6): تحقّق من الرخصة والرقم الضريبي وعنوان العمل قبل القبول. «منع» يوقف ارتباطه بأي شركة (م116.2).
          </p>
        </div>
        <ul className="divide-y divide-[var(--color-border)]">
          {pendingAccountants.length === 0 ? (
            <li className="px-4 py-6 text-center aseel-text-soft">لا ملفات بانتظار التحقق</li>
          ) : pendingAccountants.map((profile) => (
            <li key={profile.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-[16rem]">
                <p className="font-semibold text-[var(--color-text)]">{profile.full_name}</p>
                <p className="text-xs aseel-text-soft">
                  {profile.email} · ضريبي {profile.tax_registration_number}
                  {profile.license_number ? ` · رخصة ${profile.license_number}` : ""}
                </p>
                <p className="text-[11px] aseel-text-soft">{profile.business_address}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  className="aseel-input h-9 w-56"
                  placeholder="سبب الرفض/المنع"
                  aria-label={`سبب قرار ${profile.full_name}`}
                  value={rejectReason[profile.id] || ""}
                  onChange={(event) => setRejectReason((current) => ({ ...current, [profile.id]: event.target.value }))}
                />
                <button type="button" disabled={accountantBusy === profile.id} onClick={() => void decideAccountant(profile, "approve")} className="aseel-btn aseel-btn-primary">توثيق</button>
                <button type="button" disabled={accountantBusy === profile.id} onClick={() => void decideAccountant(profile, "reject")} className="aseel-btn">رفض</button>
                <button type="button" disabled={accountantBusy === profile.id} onClick={() => void decideAccountant(profile, "bar")} className="aseel-btn text-red-600">منع</button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-5 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-3">
          <div><h2 className="font-bold text-[var(--color-text)]">الشركات</h2><p className="text-xs aseel-text-soft">{data.memberships} عضوية عبر المنصة · «تحكم» يفتح إعدادات الشركة وأعضاءها</p></div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="platform-example-company" className="mb-1 block text-xs font-bold text-[var(--color-text)]">تعيين الشركة المثال</label>
              <select
                id="platform-example-company"
                className="aseel-input h-9 min-w-56"
                value={data.company_rows.find((company) => company.is_example)?.id ?? ""}
                disabled={assigningExample}
                onChange={(event) => void assignExampleCompany(event.target.value)}
              >
                <option value="">بدون شركة مثال</option>
                {data.company_rows.map((company) => (
                  <option key={company.id} value={company.id}>{company.name}</option>
                ))}
              </select>
            </div>
            <span className="pb-2 text-xs aseel-text-soft">تجريبية: {data.companies.trial} · مستخدمون: {data.users.total}</span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="bg-[var(--color-surface-2)] aseel-text-soft"><tr>
              <th className="px-3 py-2 text-right">الشركة</th><th className="px-3 py-2 text-right">الخطة</th>
              <th className="px-3 py-2 text-right">الحالة</th><th className="px-3 py-2 text-center">الأعضاء</th>
              <th className="px-3 py-2 text-center">الاستيراد</th><th className="px-3 py-2 text-right">تاريخ الإنشاء</th>
              <th className="px-3 py-2 text-center">تحكم</th>
            </tr></thead>
            <tbody>
              {data.company_rows.length === 0 ? (
                <tr><td colSpan={7} className="px-3 py-10 text-center aseel-text-soft">لا توجد شركات بعد</td></tr>
              ) : data.company_rows.map((company) => (
                <tr key={company.id} className="border-t border-[var(--color-border)] hover:bg-[var(--color-surface-2)]">
                  <td className="px-3 py-2 font-semibold text-[var(--color-text)]">{company.name}{company.is_example ? " (مثال)" : ""}</td>
                  <td className="px-3 py-2">{COMPANY_PLAN_LABELS[company.plan] || company.plan}</td>
                  <td className="px-3 py-2">{statusLabel(company.status)}</td>
                  <td className="px-3 py-2 text-center">{company.member_count}</td>
                  <td className="px-3 py-2 text-center">{company.import_enabled ? "مفعّل" : "غير مفعّل"}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{formatDateValue(company.created_at)}</td>
                  <td className="px-3 py-2 text-center">
                    <button
                      type="button"
                      onClick={() => setManagedCompanyId(company.id)}
                      className="aseel-btn"
                      title={`تحكم بـ${company.name}`}
                      aria-label={`تحكم بـ${company.name}`}
                    >
                      <Settings2 className="h-4 w-4" aria-hidden="true" /> تحكم
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {managedCompanyId !== null && (
        <PlatformCompanyPanel
          companyId={managedCompanyId}
          onClose={() => setManagedCompanyId(null)}
          onChanged={load}
        />
      )}
    </main>
  );
};
