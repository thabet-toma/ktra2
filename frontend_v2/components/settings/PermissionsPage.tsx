/**
 * T-PERM — شاشة الصلاحيات: مصفوفة (دور × صلاحية) على نمط الأنظمة الاحترافية.
 *
 * الافتراضات تأتي من الخادم (core/access.py)، وما يُغيَّر هنا يُحفظ تجاوزاً
 * لهذه الشركة وحدها. عمود «مدير» مقفل — مالك الشركة يملك كل شيء ولا يُقفل
 * خارج نظامه. «استعادة الافتراضي» تمسح كل التجاوزات.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RotateCcw, Save, ShieldCheck } from "lucide-react";
import {
  changeMemberRole,
  getPermissionMembers,
  getPermissionsMatrix,
  resetPermissionsMatrix,
  saveMemberPermissions,
  savePermissionsMatrix,
  setMemberGrantAll,
  type PermissionMember,
  type PermissionsMatrix,
} from "../../services/permissionsApi";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { humanizeDrfError } from "../../utils/drfError";
import { memberOverrideForCheckbox } from "../../utils/viewPermissions";
import { AseelDocumentShell, type AseelToolbarAction } from "../aseel";

type Draft = Record<string, Record<string, boolean>>;

export const PermissionsPage: React.FC = () => {
  const [data, setData] = useState<PermissionsMatrix | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { reload: reloadMyPermissions } = usePermissions();
  const confirm = useConfirm();
  const toast = useToast();

  const [tab, setTab] = useState<"role" | "member">("role");
  const [members, setMembers] = useState<PermissionMember[]>([]);
  const [activeMember, setActiveMember] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [res, mem] = await Promise.all([
        getPermissionsMatrix(),
        getPermissionMembers().catch(() => [] as PermissionMember[]),
      ]);
      setData(res);
      setDraft(JSON.parse(JSON.stringify(res.matrix)));
      setMembers(mem);
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /** تغيير دور العضو — يُعيد تحميل صفّه فتظهر صلاحياته الفعلية الجديدة فوراً. */
  const handleRoleChange = async (m: PermissionMember, role: string) => {
    if (role === m.role) return;
    setSaving(true);
    setErr(null);
    try {
      await changeMemberRole(m.membership_id, role);
      const fresh = await getPermissionMembers();
      setMembers(fresh);
      reloadMyPermissions();
      toast("تم تغيير دور الموظف.", "success");
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSaving(false);
    }
  };

  /**
   * خانة اختيار للصلاحية الفردية: مؤشَّرة = ممنوحة فعلياً. ما وافق دوره لا
   * يُخزَّن تجاوزاً (`memberOverrideForCheckbox` تُرجع null فيُحذف).
   */
  const toggleMemberPermission = async (
    m: PermissionMember,
    key: string,
    nextChecked: boolean,
  ) => {
    const roleAllowed = !!data?.matrix[m.role]?.[key];
    setSaving(true);
    setErr(null);
    try {
      const updated = await saveMemberPermissions(m.membership_id, [
        { permission_key: key, allowed: memberOverrideForCheckbox(roleAllowed, nextChecked) },
      ]);
      setMembers((prev) =>
        prev.map((x) => (x.membership_id === updated.membership_id ? updated : x)),
      );
      reloadMyPermissions();
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSaving(false);
    }
  };

  /** «كل الصلاحيات» لهذا العضو — وإزالتها تعيده لما يمليه دوره (تُستأذن). */
  const toggleMemberGrantAll = async (m: PermissionMember, nextChecked: boolean) => {
    if (!nextChecked) {
      const ok = await confirm({
        message: `إعادة ${m.name} إلى صلاحيات دوره؟ ستُحذف كل تخصيصاته الفردية.`,
        confirmText: "إعادة للدور",
        danger: true,
      });
      if (!ok) return;
    }
    setSaving(true);
    setErr(null);
    try {
      const updated = await setMemberGrantAll(m.membership_id, nextChecked);
      setMembers((prev) =>
        prev.map((x) => (x.membership_id === updated.membership_id ? updated : x)),
      );
      reloadMyPermissions();
      toast(
        nextChecked ? `مُنح ${m.name} كل الصلاحيات.` : `أُعيد ${m.name} إلى صلاحيات دوره.`,
        "success",
      );
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSaving(false);
    }
  };

  /** التغييرات فقط (فرق المسودّة عن المحفوظ) — لا نرسل المصفوفة كاملة. */
  const changes = useMemo(() => {
    if (!data) return [];
    const out: { role: string; permission_key: string; allowed: boolean }[] = [];
    for (const role of Object.keys(draft)) {
      if (role === "manager") continue;
      for (const key of Object.keys(draft[role] || {})) {
        if (draft[role][key] !== data.matrix[role]?.[key]) {
          out.push({ role, permission_key: key, allowed: draft[role][key] });
        }
      }
    }
    return out;
  }, [draft, data]);

  const toggle = (role: string, key: string) => {
    if (role === "manager") return;
    setDraft((prev) => ({
      ...prev,
      [role]: { ...prev[role], [key]: !prev[role]?.[key] },
    }));
  };

  const handleSave = async () => {
    if (!changes.length) return;
    setSaving(true);
    setErr(null);
    try {
      const res = await savePermissionsMatrix(changes);
      setData(res);
      setDraft(JSON.parse(JSON.stringify(res.matrix)));
      reloadMyPermissions();
      toast("تم حفظ الصلاحيات.", "success");
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    const ok = await confirm({
      message: "استعادة الصلاحيات الافتراضية لكل الأدوار؟ ستُحذف كل التخصيصات في هذه الشركة.",
      confirmText: "استعادة الافتراضي",
      danger: true,
    });
    if (!ok) return;
    setSaving(true);
    try {
      const res = await resetPermissionsMatrix();
      setData(res);
      setDraft(JSON.parse(JSON.stringify(res.matrix)));
      reloadMyPermissions();
      toast("أُعيدت الصلاحيات إلى الافتراضي.", "success");
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSaving(false);
    }
  };

  const toolbarActions: AseelToolbarAction[] = [
    {
      key: "save",
      label: saving ? "..." : `حفظ${changes.length ? ` (${changes.length})` : ""}`,
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: handleSave,
      disabled: saving || !changes.length,
    },
    {
      key: "reset",
      label: "استعادة الافتراضي",
      icon: <RotateCcw />,
      onClick: handleReset,
      disabled: saving,
    },
  ];

  /** الصلاحيات مجمّعة حسب القسم — كما يعرضها الكتالوج على الخادم. */
  const groups = useMemo(() => {
    const map = new Map<string, typeof data.permissions>();
    for (const p of data?.permissions || []) {
      if (!map.has(p.group)) map.set(p.group, []);
      map.get(p.group)!.push(p);
    }
    return Array.from(map.entries());
  }, [data]);

  const inner = (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-4" dir="rtl">
      <div
        className="aseel-banner"
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "var(--aseel-surface-2, #f4ede0)" }}
      >
        <ShieldCheck className="w-4 h-4" style={{ color: "var(--aseel-ink-soft)" }} />
        <span style={{ fontSize: 12 }}>
          حدّد ما يملكه كل دور. عمود «مدير» مقفل (مالك الشركة يملك كل شيء).
          الإنفاذ على الخادم — إخفاء الزر وحده لا يكفي.
        </span>
      </div>

      {err && (
        <div className="rounded-md border border-[var(--color-danger)] bg-[color-mix(in_srgb,var(--color-danger)_8%,transparent)] px-3 py-2 text-sm">
          {err}
        </div>
      )}

      {loading && !data && (
        <div className="flex items-center gap-2 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> جارٍ التحميل…
        </div>
      )}

      {/* تبويبان: القاعدة العامة (الدور) ثم الاستثناء الفردي (الموظف). */}
      <div className="flex gap-2 border-b aseel-border-soft">
        {([["role", "حسب الدور"], ["member", "حسب الموظف"]] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`px-3 py-2 text-sm ${tab === k ? "font-bold border-b-2 border-[var(--color-primary)] text-[var(--color-primary)]" : "text-[var(--color-text-muted)]"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "member" && data && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {members.filter((m) => m.role !== "manager").map((m) => (
              <button
                key={m.membership_id}
                onClick={() => setActiveMember(m.membership_id)}
                className={`px-3 py-1.5 rounded-md border text-sm ${activeMember === m.membership_id ? "border-[var(--color-primary)] text-[var(--color-primary)] font-bold" : "aseel-border-soft"}`}
              >
                {m.name}
                <span className="text-[10px] mr-2 opacity-70">
                  {data.roles.find((r) => r.key === m.role)?.label || m.role}
                </span>
                {m.grant_all ? (
                  <span className="text-[10px] mr-2 text-[var(--color-primary)]">
                    (كل الصلاحيات)
                  </span>
                ) : Object.keys(m.overrides).length > 0 && (
                  <span className="text-[10px] mr-2 text-[var(--color-primary)]">
                    ({Object.keys(m.overrides).length} مخصّص)
                  </span>
                )}
              </button>
            ))}
            {members.filter((m) => m.role !== "manager").length === 0 && (
              <span className="text-sm text-[var(--color-text-muted)]">
                لا يوجد أعضاء غير المديرين في هذه الشركة.
              </span>
            )}
          </div>

          {activeMember != null && (() => {
            const m = members.find((x) => x.membership_id === activeMember);
            if (!m) return null;
            return (
              <div className="space-y-3">
                {/* الدور أولاً (القاعدة العامة) ثم الاستثناءات الفردية تحته. */}
                <div className="flex items-center gap-2 rounded-lg border aseel-border-soft p-3">
                  <span className="text-sm font-semibold">دور {m.name}:</span>
                  <select
                    className="rounded-md border aseel-border-soft aseel-bg-field px-2 py-1 text-sm"
                    value={m.role}
                    disabled={saving}
                    onChange={(e) => void handleRoleChange(m, e.target.value)}
                  >
                    {data.roles.map((r) => (
                      <option key={r.key} value={r.key}>{r.label}</option>
                    ))}
                  </select>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    تغيير الدور يبدّل القاعدة العامة؛ الاستثناءات أدناه تبقى كما هي.
                  </span>
                  <label className="flex items-center gap-2 text-sm font-semibold mr-auto">
                    <input
                      type="checkbox"
                      checked={m.grant_all}
                      disabled={saving}
                      onChange={(e) => void toggleMemberGrantAll(m, e.target.checked)}
                    />
                    كل الصلاحيات
                  </label>
                </div>
                <p className="text-xs text-[var(--color-text-muted)]">
                  الخانة المؤشَّرة = الصلاحية ممنوحة لهذا الموظف. ما خالف دوره
                  يُحفظ تخصيصاً له وحده (مُعلَّم بإطار)، وما وافقه يعود للدور.
                </p>
                {groups.map(([group, perms]) => (
                  <div key={group} className="rounded-lg border aseel-border-soft overflow-x-auto">
                    <table className="w-full text-sm" style={{ minWidth: 480 }}>
                      <thead>
                        <tr className="aseel-bg-panel">
                          <th className="p-2 text-right font-semibold">{group}</th>
                          <th className="p-2 text-center font-semibold w-40">الحالة</th>
                        </tr>
                      </thead>
                      <tbody>
                        {perms.map((p) => {
                          const ovr = m.overrides[p.key];
                          const effective = m.effective.includes(p.key);
                          return (
                            <tr key={p.key} className="border-t aseel-border-soft">
                              <td className="p-2 text-right">{p.label}</td>
                              <td className="p-2 text-center">
                                <input
                                  type="checkbox"
                                  checked={effective}
                                  disabled={saving}
                                  onChange={(e) =>
                                    void toggleMemberPermission(m, p.key, e.target.checked)
                                  }
                                  title={ovr === undefined ? "افتراضي الدور" : "مخصّص لهذا الموظف"}
                                  style={ovr !== undefined ? { outline: "2px solid var(--color-primary)" } : undefined}
                                />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      )}

      {tab === "role" && data && groups.map(([group, perms]) => (
        <div key={group} className="rounded-lg border aseel-border-soft overflow-x-auto">
          <table className="w-full text-sm" style={{ minWidth: 640 }}>
            <thead>
              <tr className="aseel-bg-panel">
                <th className="p-2 text-right font-semibold">{group}</th>
                {data.roles.map((r) => (
                  <th key={r.key} className="p-2 text-center font-semibold whitespace-nowrap">
                    {r.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {perms.map((p) => (
                <tr key={p.key} className="border-t aseel-border-soft">
                  <td className="p-2 text-right">{p.label}</td>
                  {data.roles.map((r) => {
                    const on = !!draft[r.key]?.[p.key];
                    const isDefault =
                      on === (data.defaults[r.key] || []).includes(p.key);
                    return (
                      <td key={r.key} className="p-2 text-center">
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={r.key === "manager" || saving}
                          onChange={() => toggle(r.key, p.key)}
                          title={isDefault ? "افتراضي" : "مخصّص لهذه الشركة"}
                          style={!isDefault ? { outline: "2px solid var(--color-primary)" } : undefined}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="الصلاحيات والأدوار"
        state="مصفوفة (دور × صلاحية) لهذه الشركة"
        actions={toolbarActions}
        header={<></>}
      >
        {inner}
      </AseelDocumentShell>
    </div>
  );
};

export default PermissionsPage;
