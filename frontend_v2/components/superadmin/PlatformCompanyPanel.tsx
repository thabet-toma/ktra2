import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Save, ShieldOff, ShieldCheck, Trash2, UserPlus, X } from "lucide-react";

import {
  addPlatformCompanyMember, getPlatformCompany, removePlatformCompanyMember,
  setPlatformUserActive, updatePlatformCompany, updatePlatformCompanyMember,
  type PlatformCompanyDetail, type PlatformCompanyMember, type PlatformCompanyPatch,
} from "../../services/platformAdminApi";
import { ROLE_LABELS } from "../layout/CompanyManagementModal";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";

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
  const [form, setForm] = useState<Required<PlatformCompanyPatch>>({
    name: "", plan: "Basic", status: "Trial", import_enabled: false,
  });
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [newRole, setNewRole] = useState("staff");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPlatformCompany(companyId);
      setDetail(data);
      setForm({
        name: data.name, plan: data.plan, status: data.status,
        import_enabled: data.import_enabled,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر تحميل بيانات الشركة");
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { void load(); }, [load]);

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
  );

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
            <p className="text-xs aseel-text-soft">
              صلاحيات سوبر أدمن — تسري على هذه الشركة دون الحاجة لعضوية فيها
            </p>
          </div>
          <button type="button" onClick={onClose} className="aseel-iconbtn" aria-label="إغلاق">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>
          )}

          {loading && !detail ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm aseel-text-soft" role="status">
              <Loader2 className="h-4 w-4 animate-spin" /> جارٍ تحميل بيانات الشركة…
            </div>
          ) : !detail ? null : (
            <>
              <section aria-label="إعدادات الشركة" className="rounded-lg border border-[var(--color-border)] p-3">
                <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">إعدادات الشركة</h3>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="sm:col-span-3">
                    <label htmlFor="platform-company-name" className="mb-1 block text-xs font-bold aseel-text-soft">اسم الشركة</label>
                    <input
                      id="platform-company-name"
                      className="aseel-input h-9 w-full"
                      value={form.name}
                      onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                    />
                  </div>
                  <div>
                    <label htmlFor="platform-company-plan" className="mb-1 block text-xs font-bold aseel-text-soft">خطة الاشتراك</label>
                    <select
                      id="platform-company-plan"
                      className="aseel-input h-9 w-full"
                      value={form.plan}
                      onChange={(event) => setForm((current) => ({ ...current, plan: event.target.value }))}
                    >
                      {Object.entries(COMPANY_PLAN_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="platform-company-status" className="mb-1 block text-xs font-bold aseel-text-soft">حالة الشركة</label>
                    <select
                      id="platform-company-status"
                      className="aseel-input h-9 w-full"
                      value={form.status}
                      onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}
                    >
                      {Object.entries(COMPANY_STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
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
                  <p className="text-[11px] aseel-text-soft">
                    الشركة الموقوفة يُمنع أعضاؤها من الوصول إلى بياناتها حتى إعادة التفعيل. تعطيل وحدة الاستيراد يخفي قائمة الاستيراد وقسم «تكاليف الاستيراد» عن كل أعضائها.
                  </p>
                  <button
                    type="button"
                    onClick={() => void saveCompany()}
                    disabled={saving || !dirty}
                    className="aseel-btn aseel-btn-primary"
                  >
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} حفظ
                  </button>
                </div>
              </section>

              <section aria-label="أعضاء الشركة" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
                <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                  <h3 className="text-sm font-bold text-[var(--color-text)]">الأعضاء ({detail.members.length})</h3>
                  <div className="flex flex-wrap items-end gap-2">
                    <div>
                      <label htmlFor="platform-member-identifier" className="mb-1 block text-[11px] font-bold aseel-text-soft">اسم المستخدم أو البريد</label>
                      <input
                        id="platform-member-identifier"
                        className="aseel-input h-9 w-56"
                        value={identifier}
                        onChange={(event) => setIdentifier(event.target.value)}
                        placeholder="حساب مسجَّل في المنصة"
                        autoComplete="off"
                        spellCheck={false}
                      />
                    </div>
                    <div>
                      <label htmlFor="platform-member-role" className="mb-1 block text-[11px] font-bold aseel-text-soft">الدور</label>
                      <select
                        id="platform-member-role"
                        className="aseel-input h-9"
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
                      className="aseel-btn aseel-btn-primary"
                    >
                      {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />} إضافة
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-sm">
                    <thead className="bg-[var(--color-surface-2)] aseel-text-soft">
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
                        <tr><td colSpan={5} className="px-3 py-8 text-center aseel-text-soft">لا أعضاء في هذه الشركة</td></tr>
                      ) : detail.members.map((member) => (
                        <tr key={member.membership_id} className="border-t border-[var(--color-border)]">
                          <td className="px-3 py-2">
                            <div className="font-semibold text-[var(--color-text)]">{member.full_name || member.username}</div>
                            <div className="text-[11px] aseel-text-soft">{member.email || member.username}</div>
                          </td>
                          <td className="px-3 py-2">
                            <select
                              className="aseel-input h-8 w-full"
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
                              <span className="text-[11px] aseel-text-soft" title="المدير يملك صلاحية الاستيراد ضمناً">ضمناً</span>
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
                                className={`aseel-iconbtn ${member.is_active ? "text-amber-600" : "text-emerald-600"}`}
                                title={member.is_active ? `إيقاف حساب ${member.username}` : `تفعيل حساب ${member.username}`}
                                aria-label={member.is_active ? `إيقاف حساب ${member.username}` : `تفعيل حساب ${member.username}`}
                              >
                                {member.is_active ? <ShieldOff className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                              </button>
                              <button
                                type="button"
                                onClick={() => void removeMember(member)}
                                disabled={busyId === member.membership_id}
                                className="aseel-iconbtn text-red-600"
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
                <p className="mt-2 text-[11px] aseel-text-soft">
                  «إيقاف الحساب» يمنع الدخول إلى المنصة كلها، و«الإخراج» يزيل العضوية من هذه الشركة فقط. لا يمكن إخراج أو تخفيض آخر مدير قبل تعيين بديل.
                </p>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
