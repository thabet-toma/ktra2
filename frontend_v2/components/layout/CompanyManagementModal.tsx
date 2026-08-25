import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Save, Trash2, UserPlus, X } from "lucide-react";
import { apiGetObject, apiPatchObject, apiPostObject } from "../../services/restApi";
import type { Tenant, CompanyMembership } from "../../contexts/CompanyContext";
import { useConfirm } from "../../contexts/ConfirmContext";

/** task12 M4 — إدارة الشركة: إعادة التسمية + الأعضاء والأدوار.
 * كانت الشركة بلا أي واجهة تعديل/أعضاء (CompanySwitcher = إنشاء وتبديل فقط). */

type MemberRow = {
  membership_id: number;
  user_id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  is_default: boolean;
  can_access_import: boolean;
};

export const ROLE_LABELS: Record<string, string> = {
  manager: "مدير",
  accountant: "محاسب",
  // T-PERM: دورا الموظف المتخصّص — صلاحياتهما تُضبط من شاشة «الصلاحيات والأدوار».
  sales: "موظف مبيعات",
  procurement: "موظف مشتريات",
  staff: "موظف",
  viewer: "مستعرض (قراءة فقط)",
};

interface Props {
  isOpen: boolean;
  onClose: () => void;
  memberships: CompanyMembership[];
  initialTenantId: number;
  /** بعد إعادة التسمية — لتحديث القائمة والاسم بأعلى الشاشة */
  onChanged: () => Promise<void> | void;
}

export const CompanyManagementModal: React.FC<Props> = ({ isOpen, onClose, memberships, initialTenantId, onChanged }) => {
  const [activeTenantId, setActiveTenantId] = useState(initialTenantId);
  const activeMembership = memberships.find(m => m.tenant.TenantID === activeTenantId) || memberships[0];
  const tenant = activeMembership?.tenant;
  const myRole = activeMembership?.role || "staff";

  const isManager = myRole === "manager";
  const confirm = useConfirm();
  // تفعيل وحدة الاستيراد للشركة صار في لوحة تحكم السوبر أدمن (PlatformCompanyPanel)؛
  // هنا يبقى توزيعها على الأعضاء — وهي مهمة مدير الشركة.
  const importEnabled = !!tenant?.import_enabled;
  const showImportCol = isManager && importEnabled;
  const [name, setName] = useState(tenant?.CompanyName || "");
  const [savingName, setSavingName] = useState(false);
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [newMember, setNewMember] = useState("");
  const [newRole, setNewRole] = useState("staff");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [addBusy, setAddBusy] = useState(false);

  const base = tenant ? `tenants/companies/${tenant.TenantID}` : "";

  const loadMembers = useCallback(async () => {
    setMembersLoading(true);
    setError(null);
    try {
      setMembers(await apiGetObject<MemberRow[]>(`${base}/members/`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل الأعضاء");
    } finally {
      setMembersLoading(false);
    }
  }, [base]);

  useEffect(() => {
    if (isOpen && initialTenantId) {
      setActiveTenantId(initialTenantId);
    }
  }, [isOpen, initialTenantId]);

  useEffect(() => {
    if (!isOpen || !tenant) return;
    setName(tenant.CompanyName);
    setError(null);
    setInfo(null);
    void loadMembers();
  }, [isOpen, tenant?.TenantID, loadMembers]);

  if (!isOpen || !tenant) return null;

  const run = async (fn: () => Promise<void>, okMsg?: string) => {
    setError(null);
    setInfo(null);
    try {
      await fn();
      if (okMsg) setInfo(okMsg);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleRename = () =>
    run(async () => {
      if (!name.trim() || name.trim() === tenant.CompanyName) return;
      setSavingName(true);
      try {
        await apiPatchObject(`${base}/`, { CompanyName: name.trim() });
        await onChanged();
      } finally {
        setSavingName(false);
      }
    }, "تم حفظ اسم الشركة.");

  const handleAdd = () =>
    run(async () => {
      if (!newMember.trim()) return;
      setAddBusy(true);
      try {
        await apiPostObject(`${base}/members/`, { username_or_email: newMember.trim(), role: newRole });
        setNewMember("");
        await loadMembers();
      } finally {
        setAddBusy(false);
      }
    }, "تمت إضافة العضو.");

  const handleRoleChange = (m: MemberRow, role: string) =>
    run(async () => {
      setBusyId(m.membership_id);
      try {
        await apiPostObject(`${base}/members/change-role/`, { membership_id: m.membership_id, role });
        await loadMembers();
      } finally {
        setBusyId(null);
      }
    });

  const handleToggleMemberImport = (m: MemberRow, next: boolean) =>
    run(async () => {
      setBusyId(m.membership_id);
      try {
        await apiPostObject(`${base}/members/set-import-access/`, {
          membership_id: m.membership_id,
          can_access_import: next,
        });
        await loadMembers();
      } finally {
        setBusyId(null);
      }
    });

  const handleRemove = (m: MemberRow) =>
    run(async () => {
      if (!(await confirm({ title: "إزالة عضو", message: `إزالة ${m.username} من «${tenant.CompanyName}»؟`, confirmText: "إزالة" }))) return;
      setBusyId(m.membership_id);
      try {
        await apiPostObject(`${base}/members/remove/`, { membership_id: m.membership_id });
        await loadMembers();
      } finally {
        setBusyId(null);
      }
    });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4" dir="rtl">
      <div className="w-full max-w-2xl rounded-2xl bg-[var(--ktra-bg,white)] border border-[var(--ktra-border,#ddd)] shadow-2xl p-6 max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold" style={{ color: "var(--ktra-ink)" }}>إدارة الشركة:</h3>
            <select
              value={activeTenantId}
              onChange={(e) => setActiveTenantId(Number(e.target.value))}
              className="px-3 py-1.5 text-sm font-bold rounded-lg border border-[var(--ktra-border,#ddd)] bg-[var(--ktra-panel,#fafafa)] focus:outline-none focus:ring-2 focus:ring-[var(--ktra-accent)]"
              style={{ color: "var(--ktra-ink)" }}
            >
              {memberships.filter(m => m.role === "manager").map(m => (
                <option key={m.tenant.TenantID} value={m.tenant.TenantID}>
                  {m.tenant.CompanyName}
                </option>
              ))}
            </select>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded-lg hover:bg-[var(--ktra-panel-hover,#f3f3f3)] opacity-70 hover:opacity-100" aria-label="إغلاق">
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && <div className="p-3 mb-3 text-xs bg-red-50 text-red-700 rounded-lg border border-red-200 font-semibold">{error}</div>}
        {info && <div className="p-3 mb-3 text-xs bg-green-50 text-green-700 rounded-lg border border-green-200 font-semibold">{info}</div>}

        {/* اسم الشركة */}
        <div className="mb-6">
          <label className="text-xs font-bold opacity-80 block mb-1.5" htmlFor="company-rename">اسم الشركة</label>
          <div className="flex gap-2">
            <input
              id="company-rename"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!isManager || savingName}
              className="flex-1 px-3 py-2 text-sm rounded-lg border border-[var(--ktra-border,#ddd)] bg-[var(--ktra-panel,#fafafa)] focus:outline-none focus:ring-2 focus:ring-[var(--ktra-accent,#1857a4)]"
            />
            {isManager && (
              <button
                type="button"
                onClick={() => void handleRename()}
                disabled={savingName || !name.trim() || name.trim() === tenant.CompanyName}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold text-white rounded-lg bg-[var(--ktra-accent,#1857a4)] disabled:opacity-50"
              >
                {savingName ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                حفظ
              </button>
            )}
          </div>
          {!isManager && <p className="text-[11px] opacity-60 mt-1">تعديل الاسم متاح لمدير الشركة فقط.</p>}
        </div>

        {/* الأعضاء */}
        <div>
          <h4 className="text-sm font-bold mb-2" style={{ color: "var(--ktra-ink)" }}>الأعضاء والأدوار ({members.length})</h4>

          {isManager && (
            <div className="flex flex-wrap gap-2 mb-3 items-end">
              <div className="flex-1 min-w-[180px]">
                <label className="text-[11px] font-bold opacity-70 block mb-1" htmlFor="add-member-ident">البريد الإلكتروني أو اسم المستخدم</label>
                <input
                  id="add-member-ident"
                  type="text"
                  value={newMember}
                  onChange={(e) => setNewMember(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--ktra-border,#ddd)] bg-[var(--ktra-panel,#fafafa)]"
                  disabled={addBusy}
                  placeholder="أدخل البريد أو اسم المستخدم بدقة"
                  autoComplete="off"
                  spellCheck={false}
                  aria-describedby="add-member-help"
                />
                <p id="add-member-help" className="text-[11px] opacity-60 mt-1">
                  حفاظاً على الخصوصية، لا يعرض النظام حسابات المنصة ولا يقترحها تلقائياً.
                </p>
              </div>
              <div>
                <label className="text-[11px] font-bold opacity-70 block mb-1" htmlFor="add-member-role">الدور</label>
                <select
                  id="add-member-role"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="px-3 py-2 text-sm rounded-lg border border-[var(--ktra-border,#ddd)] bg-[var(--ktra-panel,#fafafa)]"
                  disabled={addBusy}
                >
                  {Object.entries(ROLE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => void handleAdd()}
                disabled={addBusy || !newMember.trim()}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold text-white rounded-lg bg-[var(--ktra-accent,#1857a4)] disabled:opacity-50"
              >
                {addBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
                إضافة عضو
              </button>
            </div>
          )}

          {membersLoading ? (
            <div className="flex items-center gap-2 py-6 justify-center text-sm opacity-70">
              <Loader2 className="w-4 h-4 animate-spin" /> جاري تحميل الأعضاء…
            </div>
          ) : (
            <table className="w-full text-sm border border-[var(--ktra-border,#ddd)] rounded-lg overflow-hidden">
              <thead>
                <tr className="bg-[var(--ktra-panel,#f5f5f5)] text-right">
                  <th className="px-3 py-2 font-bold">المستخدم</th>
                  <th className="px-3 py-2 font-bold">البريد</th>
                  <th className="px-3 py-2 font-bold w-44">الدور</th>
                  {showImportCol && <th className="px-3 py-2 font-bold w-20 text-center">استيراد</th>}
                  {isManager && <th className="px-3 py-2 w-12" />}
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.membership_id} className="border-t border-[var(--ktra-border-soft,#eee)]">
                    <td className="px-3 py-2">
                      <div className="font-semibold">{m.full_name || m.username}</div>
                      {m.full_name && <div className="text-[11px] opacity-60">{m.username}</div>}
                    </td>
                    <td className="px-3 py-2 text-[12px] opacity-80">{m.email || "—"}</td>
                    <td className="px-3 py-2">
                      {isManager ? (
                        <select
                          value={m.role}
                          onChange={(e) => void handleRoleChange(m, e.target.value)}
                          disabled={busyId === m.membership_id}
                          className="w-full px-2 py-1.5 text-sm rounded-lg border border-[var(--ktra-border,#ddd)] bg-[var(--ktra-panel,#fafafa)]"
                          aria-label={`دور ${m.username}`}
                        >
                          {Object.entries(ROLE_LABELS).map(([k, v]) => (
                            <option key={k} value={k}>{v}</option>
                          ))}
                        </select>
                      ) : (
                        <span>{ROLE_LABELS[m.role] || m.role}</span>
                      )}
                    </td>
                    {showImportCol && (
                      <td className="px-3 py-2 text-center">
                        {m.role === "manager" ? (
                          <span className="text-[11px] opacity-60" title="المدير يملك صلاحية الاستيراد ضمناً">ضمناً</span>
                        ) : (
                          <input
                            type="checkbox"
                            checked={!!m.can_access_import}
                            disabled={busyId === m.membership_id}
                            onChange={(e) => void handleToggleMemberImport(m, e.target.checked)}
                            aria-label={`صلاحية استيراد ${m.username}`}
                          />
                        )}
                      </td>
                    )}
                    {isManager && (
                      <td className="px-3 py-2 text-center">
                        <button
                          type="button"
                          onClick={() => void handleRemove(m)}
                          disabled={busyId === m.membership_id}
                          className="p-1.5 rounded-lg text-red-600 hover:bg-red-50 disabled:opacity-50"
                          title={`إزالة ${m.username}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
                {members.length === 0 && (
                  <tr><td colSpan={3 + (isManager ? 1 : 0) + (showImportCol ? 1 : 0)} className="px-3 py-6 text-center opacity-60">لا يوجد أعضاء</td></tr>
                )}
              </tbody>
            </table>
          )}
          {isManager && (
            <p className="text-[11px] opacity-60 mt-2">
              لا يمكن إزالة أو تخفيض آخر مدير. المستخدم الجديد يجب أن يكون مسجلاً في المنصة أولاً (صفحة إنشاء حساب).
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
