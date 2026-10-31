import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  getOfficeSettings,
  listCustomizingClients,
  listOfficeMembers,
  resetOfficeSetting,
  setOfficeSetting,
  type OfficeClientRow,
  type OfficeMemberRow,
  type OfficeSettingsPayload,
} from '../../services/accountingOfficeApi';
import {
  changeMemberRole,
  getPermissionMembers,
  getPermissionRoles,
  saveMemberPermissions,
  type PermissionMember,
} from '../../services/permissionsApi';
import {
  OFFICE_OWNER_ROLE,
  clientFilePath,
  missingFirstRunLabels,
  officeAssignableRoles,
  officeRoleLabel,
  officeSizeOf,
  showsOfficeAssignment,
} from '../../utils/accountingOffice';
import { userRoleLabel } from '../../utils/userRoleLabel';
import { humanizeThrown } from '../../utils/drfError';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import { SettingControl } from './SettingControl';
import { OfficeCard, OfficeError, OfficeSkeleton, officeInputClass } from './OfficeUi';

type CustomizingClient = Pick<OfficeClientRow, 'id' | 'name' | 'status' | 'status_label'>;

/** المفتاحان اللذان يُمنحان لكل عضو على حدة (#272) — تجاوزُ عضوٍ لا جدولَ جديد. */
const MEMBER_OFFICE_KEYS = [
  { key: 'office.clients.all', label: 'يرى زبائن غيره' },
  { key: 'office.amounts.view', label: 'يرى المبالغ' },
] as const;

/**
 * ISSUE #271 — شاشة إعدادات المكتب، بمجموعة «المكتب» وحدها الآن.
 *
 * لكل إعداد: قيمته الفعلية، و«ارجع للافتراضي» (حين يملك افتراضيًا فعلاً —
 * `can_reset`)، و«مخصَّص عند N زبون» يُكبَس فيعرض القائمة، وكلُّ اسمٍ فيها رابطٌ
 * يفتح ملفّ الزبون. والثلاثةُ من السجلّ نفسه: `value_label` و`can_reset`
 * و`client_customization_count` يحسبها الخادم، فلا حسابَ موازياً هنا يفترق عنه.
 *
 * وتخصيصُ الزبون **ليس** هنا: مكانه ملفّه — الإعدادُ المكتبيّ سقفٌ، والتخصيص
 * استثناءٌ يُرى حيث يُقرأ الزبون.
 *
 * **وقسم «الموظفون والأدوار» (#272)** يظهر لمن يملك `office.settings.manage`
 * وفي مكتبٍ فيه أكثر من شخص. أدوارُه الأربعة على الكتالوج القائم — بلا محرّكٍ
 * موازياً: تغييرُ الدور عبر `members/change-role/`، والمفتاحان عبر
 * `permissions/member/` (خدماتُ الواجهة القائمة، ونقاطُ الـAPI القائمة). ولأن
 * هاتين النقطتين محميّتان بـ`admin.members.manage` و`admin.permissions.manage`،
 * تبقى الكتابةُ ظاهرةً لمن يملكهما وحده — والمالكُ (`manager`) يملك كل شيء
 * ولا يُغيَّر دوره.
 */
export const OfficeSettingsScreen: React.FC = () => {
  const toast = useToast();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const [payload, setPayload] = useState<OfficeSettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Record<string, CustomizingClient[] | undefined>>({});
  const [members, setMembers] = useState<OfficeMemberRow[]>([]);
  const [roles, setRoles] = useState<{ key: string; label: string }[]>([]);
  const [overrideRows, setOverrideRows] = useState<Record<number, PermissionMember>>({});
  const [savingMember, setSavingMember] = useState<number | null>(null);

  const canEditRoles = can('admin.members.manage');
  const canEditOverrides = can('admin.permissions.manage');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getOfficeSettings()
      .then(setPayload)
      .catch((failure) => setError(humanizeThrown(failure, 'تعذّر تحميل إعدادات المكتب.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (key: string, value: unknown) => {
    try {
      await setOfficeSetting(key, value);
      toast('حُفظ الإعداد', 'success');
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ الإعداد.'), 'error');
      throw failure; // `SettingControl` يعرضه تحت السطر نفسه
    }
  };

  const reset = async (key: string) => {
    try {
      await resetOfficeSetting(key);
      toast('رجع الإعداد إلى الافتراضي', 'success');
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر الرجوع إلى الافتراضي.'), 'error');
      throw failure;
    }
  };

  const toggleClients = async (key: string) => {
    if (expanded[key]) {
      setExpanded((prev) => ({ ...prev, [key]: undefined }));
      return;
    }
    try {
      const rows = await listCustomizingClients(key);
      setExpanded((prev) => ({ ...prev, [key]: rows }));
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحميل قائمة الزبائن المخصِّصين.'), 'error');
    }
  };

  const officeSize = useMemo(
    () => (payload ? officeSizeOf(payload.settings) : null),
    [payload],
  );
  // «شخص واحد» لا قسمَ أدوارٍ فيه — صاحبُ المكتب يعرف موظفيه (ولا موظفين).
  const showsStaff = showsOfficeAssignment(officeSize);
  const canManageSettings = can('office.settings.manage');

  const roleLabelOf = useCallback(
    (role: string) =>
      officeRoleLabel(
        role,
        roles.find((entry) => entry.key === role)?.label ?? userRoleLabel(role),
      ),
    [roles],
  );

  /**
   * موظفو المكتب وأدوارُهم — من نقاط الـAPI القائمة ولا شيء غيرها:
   * `tenants/companies/<id>/members/` للقائمة (متاحةٌ لكل عضو)،
   * و`permissions/roles/` لمفردة الأدوار المرشَّحة بترخيص الوحدة،
   * و`permissions/members/` لتجاوزات الأعضاء ومفاتيحهم الفعلية.
   */
  const loadStaff = useCallback(() => {
    if (!canManageSettings || !showsStaff) return;
    listOfficeMembers()
      .then(setMembers)
      .catch((failure) => toast(humanizeThrown(failure, 'تعذّر تحميل موظفي المكتب.'), 'error'));
    getPermissionRoles()
      .then(setRoles)
      .catch(() => {
        /* التسميةُ تسقط إلى مصدرها العامّ (`userRoleLabel`) ولا تُخفي القسم. */
      });
    if (!canEditOverrides) return;
    getPermissionMembers()
      .then((rows) => {
        setOverrideRows(
          Object.fromEntries(rows.map((row) => [row.membership_id, row])),
        );
      })
      .catch((failure) => {
        toast(humanizeThrown(failure, 'تعذّر تحميل مفاتيح الموظفين.'), 'error');
      });
  }, [canEditOverrides, canManageSettings, showsStaff, toast]);

  useEffect(() => {
    loadStaff();
  }, [loadStaff]);

  const changeRole = async (member: OfficeMemberRow, role: string) => {
    if (!role || role === member.role) return;
    setSavingMember(member.membership_id);
    try {
      await changeMemberRole(member.membership_id, role);
      setMembers((prev) =>
        prev.map((row) => (row.membership_id === member.membership_id ? { ...row, role } : row)),
      );
      toast('حُفظ دور الموظف', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تغيير دور الموظف.'), 'error');
    } finally {
      setSavingMember(null);
    }
  };

  /**
   * مفتاحُ عضوٍ واحد: النقرُ يكتب تجاوزاً صريحاً (`allowed` = عكس الحالة الفعلية).
   * والحالةُ المعروضة من `effective` التي يحسبها الخادم — لا حسابَ موازياً هنا.
   *
   * **ولا نكتب بلا صفٍّ محمَّل**: بلا `current` كنا نقرأ «غير ممنوح» فنمنح مفتاحاً
   * ممنوحاً بدل أن نقلبه. والمربّعُ معطَّلٌ حتى يصل صفُّه (أدناه) احتياطاً ثانياً.
   */
  const toggleMemberKey = async (member: OfficeMemberRow, key: string) => {
    const current = overrideRows[member.membership_id];
    if (!current) return;
    const granted = current.effective.includes(key);
    setSavingMember(member.membership_id);
    try {
      const updated = await saveMemberPermissions(member.membership_id, [
        { permission_key: key, allowed: !granted },
      ]);
      setOverrideRows((prev) => ({ ...prev, [member.membership_id]: updated }));
      toast('حُفظ مفتاح الموظف', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ مفتاح الموظف.'), 'error');
    } finally {
      setSavingMember(null);
    }
  };

  if (loading && !payload) return <OfficeSkeleton />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!payload) return null;

  const officeGroup = payload.settings.filter((setting) => setting.group === 'office');
  // التسمية من `payload.groups` وحدها — لا نصٌّ احتياطيّ يفترق عن السجلّ.
  const groupLabel = payload.groups.find((group) => group.id === 'office')?.label ?? '';

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <h1 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">
          إعدادات المكتب
        </h1>
        <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
          هذه قيم المكتب، وكلُّ زبونٍ يرثها ما لم يُخصَّص له غيرها. التخصيصُ يُدار من
          ملفّ الزبون.
        </p>
        {payload.first_run_required ? (
          <p
            role="status"
            className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] font-medium text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
          >
            لم يكتمل أول تشغيل بعد — اختر{' '}
            {missingFirstRunLabels(payload.missing_settings, payload.settings).join(' و')}.
          </p>
        ) : null}
      </header>

      <OfficeCard title={groupLabel}>
        {officeGroup.map((setting) => {
          const clients = expanded[setting.key];
          const count = setting.client_customization_count ?? 0;
          return (
            <div key={setting.key}>
              <SettingControl
                setting={setting}
                value={setting.value}
                canReset={setting.can_reset === true}
                disabled={!canManageSettings}
                onReset={() => reset(setting.key)}
                onSave={(value) => save(setting.key, value)}
              />
              {/* إعدادٌ مكتبيٌّ فقط (`office_size`) لا يُخصَّص لزبون — «مخصَّص عند 0» كذبٌ عنه. */}
              {setting.levels.includes('client') ? (
                <div className="pb-3">
                  <button
                    type="button"
                    onClick={() => toggleClients(setting.key)}
                    disabled={count === 0}
                    className="text-[11px] font-medium text-teal-700 disabled:text-slate-400 dark:text-teal-400 dark:disabled:text-slate-600"
                  >
                    مخصَّص عند {count} زبون
                    {count > 0 ? (clients ? ' — أخفِ القائمة' : ' — اعرضهم') : ''}
                  </button>
                  {clients ? (
                    clients.length === 0 ? (
                      <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                        لا زبونَ خصّص هذا الإعداد.
                      </p>
                    ) : (
                      <ul className="mt-1.5 flex flex-wrap gap-1.5">
                        {clients.map((client) => (
                          <li key={client.id}>
                            <button
                              type="button"
                              onClick={() => navigate(clientFilePath(client.id))}
                              className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600 hover:border-teal-300 hover:text-teal-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:text-teal-300"
                            >
                              {client.name} · {client.status_label}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </OfficeCard>

      {canManageSettings && showsStaff ? (
        <OfficeCard title="الموظفون والأدوار">
          {!canEditRoles && !canEditOverrides ? (
            <p className="mb-2 text-[11px] text-slate-500 dark:text-slate-400">
              العرض فقط: منحُ الأدوار يتطلّب «إدارة الأعضاء»، ومنحُ المفتاحين يتطلّب
              «إدارة الصلاحيات» — والمالك يملكهما.
            </p>
          ) : null}
          {members.length === 0 ? (
            <p className="text-[12px] text-slate-500 dark:text-slate-400">
              لا موظفَ غيرك في هذا المكتب بعد.
            </p>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 text-[10.5px] font-medium text-slate-400 dark:border-slate-700 dark:text-slate-500">
                  <th className="py-2 text-start">الموظف</th>
                  <th className="py-2 text-start">الدور</th>
                  {MEMBER_OFFICE_KEYS.map((entry) => (
                    <th key={entry.key} className="py-2 text-start">
                      {entry.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {members.map((member) => {
                  // المالكُ (`manager`) يملك كل شيء ولا يُغيَّر دوره ولا مفاتيحه.
                  const isOwner = member.role === OFFICE_OWNER_ROLE;
                  const row = overrideRows[member.membership_id];
                  const options = officeAssignableRoles(roles, officeSize, member.role);
                  const busy = savingMember === member.membership_id;
                  return (
                    <tr
                      key={member.membership_id}
                      className="border-b border-slate-100 last:border-b-0 dark:border-slate-800"
                    >
                      <td className="py-2 text-[12px] font-medium text-slate-700 dark:text-slate-200">
                        {member.full_name || member.username}
                      </td>
                      <td className="py-2">
                        {isOwner ? (
                          <span className="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[10.5px] font-semibold text-teal-800 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300">
                            {roleLabelOf(member.role)}
                          </span>
                        ) : canEditRoles && options.length > 0 ? (
                          <select
                            value={member.role}
                            disabled={busy}
                            aria-label={`دور ${member.full_name || member.username}`}
                            onChange={(event) => {
                              void changeRole(member, event.target.value);
                            }}
                            className={`${officeInputClass} h-8`}
                          >
                            {options.map((option) => (
                              <option key={option.key} value={option.key}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10.5px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            {roleLabelOf(member.role)}
                          </span>
                        )}
                      </td>
                      {MEMBER_OFFICE_KEYS.map((entry) => (
                        <td key={entry.key} className="py-2">
                          {isOwner ? (
                            <span className="text-[11px] text-slate-400 dark:text-slate-500">
                              كل الصلاحيات
                            </span>
                          ) : canEditOverrides ? (
                            <input
                              type="checkbox"
                              checked={row ? row.effective.includes(entry.key) : false}
                              disabled={busy || !row}
                              aria-label={`${entry.label} — ${member.full_name || member.username}`}
                              onChange={() => {
                                void toggleMemberKey(member, entry.key);
                              }}
                              className="size-4 rounded border-slate-300"
                            />
                          ) : (
                            <span className="text-[11px] text-slate-400 dark:text-slate-500">—</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </OfficeCard>
      ) : null}
    </div>
  );
};
