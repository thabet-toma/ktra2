import React, { useCallback, useEffect, useState } from "react";
import { Trash2, UserPlus } from "lucide-react";

import {
  grantSuperAdmin, listSuperAdmins, revokeSuperAdmin, type PlatformSuperAdmin,
} from "../../../services/platformAdminApi";
import { useConfirm } from "../../../contexts/ConfirmContext";
import { useToast } from "../../../contexts/ToastContext";
import { ErrorBox, LoadingRow, Panel, PanelHead, SectionHeader, errorText } from "./consoleShared";

/** SA-5 — «مديرو المنصة»: ترقية مستخدم مسجَّل وسحبها. كل منح وسحب في سجل التدقيق. */
export const AdminsSection: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [admins, setAdmins] = useState<PlatformSuperAdmin[] | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [granting, setGranting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAdmins(await listSuperAdmins());
    } catch (cause) {
      setError(errorText(cause, "تعذّر تحميل قائمة السوبر أدمن"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const grant = async () => {
    const value = identifier.trim();
    if (!value) return;
    setGranting(true);
    try {
      const added = await grantSuperAdmin(value);
      setAdmins((current) => [...(current ?? []).filter((row) => row.id !== added.id), added]);
      setIdentifier("");
      toast(`صار «${added.full_name}» سوبر أدمن`, "success");
    } catch (cause) {
      toast(errorText(cause, "تعذّرت الترقية"), "error");
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
    try {
      await revokeSuperAdmin(admin.id);
      setAdmins((current) => (current ?? []).filter((row) => row.id !== admin.id));
      toast("تم سحب الصلاحية", "success");
    } catch (cause) {
      toast(errorText(cause, "تعذّر سحب الصلاحية"), "error");
    }
  };

  return (
    <div>
      <SectionHeader
        title="مديرو المنصة"
        subtitle="ترقية مستخدم مسجَّل باسمه أو بريده — بلا إنشاء حساب ولا كلمة سر"
        loading={loading}
        onRefresh={() => void load()}
      />
      <ErrorBox message={error} onRetry={() => void load()} />
      <Panel label="سوبر أدمن المنصة">
        <PanelHead title="سوبر أدمن المنصة">
          <div className="flex items-center gap-2">
            <label htmlFor="super-admin-identifier" className="sr-only">اسم المستخدم أو البريد</label>
            <input
              id="super-admin-identifier"
              className="ktra-input h-9 w-56"
              placeholder="اسم المستخدم أو البريد"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void grant(); }}
            />
            <button type="button" onClick={() => void grant()} disabled={granting || !identifier.trim()} className="ktra-btn ktra-btn-primary">
              <UserPlus className="h-4 w-4" aria-hidden="true" /> ترقية
            </button>
          </div>
        </PanelHead>
        {loading && !admins ? <LoadingRow /> : (
          <ul className="divide-y divide-[var(--color-border)]">
            {(admins ?? []).length === 0 ? (
              <li className="px-4 py-6 text-center ktra-text-soft">لا سوبر أدمن مسجَّل بعد</li>
            ) : (admins ?? []).map((admin) => (
              <li key={admin.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                <div>
                  <p className="font-semibold text-[var(--color-text)]">{admin.full_name}</p>
                  <p className="text-xs ktra-text-soft">{admin.username}{admin.email ? ` · ${admin.email}` : ""}</p>
                </div>
                {admin.removable ? (
                  <button type="button" onClick={() => void revoke(admin)} className="ktra-iconbtn text-red-600" title="سحب الصلاحية" aria-label={`سحب صلاحية ${admin.full_name}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                ) : (
                  <span className="text-xs ktra-text-soft">مثبَّت في إعدادات المنصة</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
};
