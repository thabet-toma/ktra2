import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  createOfficeService,
  createServicePackage,
  deleteServicePackage,
  getOfficeSettings,
  listCustomizingClients,
  listOfficeMembers,
  listOfficeServices,
  listServicePackages,
  resetOfficeSetting,
  setOfficeSetting,
  updateOfficeService,
  updateServicePackage,
  type OfficeClientRow,
  type OfficeMemberRow,
  type OfficeServiceRow,
  type OfficeSettingsPayload,
  type ServicePackageRow,
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
  formatOfficeAmount,
  missingFirstRunLabels,
  officeAssignableRoles,
  officeRoleLabel,
  officeSizeOf,
  showsOfficeAssignment,
} from '../../utils/accountingOffice';
import { userRoleLabel } from '../../utils/userRoleLabel';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import { SettingControl } from './SettingControl';
import {
  OfficeCard,
  OfficeError,
  OfficeSkeleton,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

type CustomizingClient = Pick<OfficeClientRow, 'id' | 'name' | 'status' | 'status_label'>;

/** مسوّدةُ باقةٍ في مجموعة «الخدمات والباقات» — `id === null` تعني باقةً جديدة. */
interface PackageDraft {
  id: number | null;
  name: string;
  price: string;
  services: number[];
}

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
  const confirm = useConfirm();
  const { can } = usePermissions();
  const [payload, setPayload] = useState<OfficeSettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Record<string, CustomizingClient[] | undefined>>({});
  const [members, setMembers] = useState<OfficeMemberRow[]>([]);
  const [roles, setRoles] = useState<{ key: string; label: string }[]>([]);
  const [overrideRows, setOverrideRows] = useState<Record<number, PermissionMember>>({});
  const [savingMember, setSavingMember] = useState<number | null>(null);

  // ── الخدمات والباقات (#273) ─────────────────────────────────────────────
  const [catalog, setCatalog] = useState<OfficeServiceRow[]>([]);
  const [packages, setPackages] = useState<ServicePackageRow[]>([]);
  const [servicesLoading, setServicesLoading] = useState(true);
  const [servicesError, setServicesError] = useState('');
  const [newServiceName, setNewServiceName] = useState('');
  const [serviceDraft, setServiceDraft] = useState<{ id: number; name: string } | null>(null);
  const [packageDraft, setPackageDraft] = useState<PackageDraft | null>(null);

  const canEditRoles = can('admin.members.manage');
  const canEditOverrides = can('admin.permissions.manage');
  const canSeeAmounts = can('office.amounts.view');

  /**
   * خدماتُ محرّر الباقة: **المفعّلةُ وحدها**، إضافةً إلى ما اختِير سابقاً وهو
   * معطَّل — وإلا اختفت خدمةٌ من باقةٍ قائمة عند تعطيلها فحُفظت الباقةُ بلا أن
   * يراها الموظف. والمعطَّلةُ تُعلَّم «معطّلة» كي لا تُختار عن جهل.
   */
  const packageServiceChoices = useMemo(
    () =>
      catalog.filter(
        (row) => row.is_active || Boolean(packageDraft?.services.includes(row.id)),
      ),
    [catalog, packageDraft],
  );

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

  /**
   * الكتالوج والباقات (#273): تُقرأ لكل عضو، وتُكتب بـ`office.settings.manage`.
   * وكتالوجُ الخادم يزرع الخمسة الافتراضية عند أول قراءة — لا زرعَ في الواجهة.
   *
   * `alive` تُمرَّر من التبويب/الجبل: ردٌّ وصل بعد تفكيك الشاشة لا يكتب فوق حالةٍ
   * أحدث، والخطأُ يُعرض في الكرت بزرّ «أعد المحاولة» لا كتنبيهٍ عابرٍ يضيع.
   */
  const loadServices = useCallback((alive?: () => boolean) => {
    setServicesError('');
    setServicesLoading(true);
    const still = () => !alive || alive();
    Promise.all([listOfficeServices(), listServicePackages()])
      .then(([catalogRows, packageRows]) => {
        if (!still()) return;
        setCatalog(catalogRows);
        setPackages(packageRows);
      })
      .catch((failure) => {
        if (!still()) return;
        setServicesError(humanizeThrown(failure, 'تعذّر تحميل الخدمات والباقات.'));
      })
      .finally(() => {
        if (still()) setServicesLoading(false);
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadServices(() => !cancelled);
    return () => {
      cancelled = true;
    };
  }, [loadServices]);

  const toggleService = async (row: OfficeServiceRow) => {
    try {
      const updated = await updateOfficeService(row.id, { is_active: !row.is_active });
      setCatalog((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      toast(updated.is_active ? 'فُعّلت الخدمة' : 'عُطّلت الخدمة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تغيير تفعيل الخدمة.'), 'error');
    }
  };

  const saveServiceName = async (row: OfficeServiceRow) => {
    if (!serviceDraft || !serviceDraft.name.trim()) return;
    try {
      const updated = await updateOfficeService(row.id, { name: serviceDraft.name.trim() });
      setCatalog((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setServiceDraft(null);
      toast('حُدّث اسم الخدمة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تعديل اسم الخدمة.'), 'error');
    }
  };

  const addService = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newServiceName.trim()) return;
    try {
      const created = await createOfficeService({ name: newServiceName.trim() });
      setCatalog((prev) => [...prev, created]);
      setNewServiceName('');
      toast('أُضيفت الخدمة إلى الكتالوج', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إضافة الخدمة.'), 'error');
    }
  };

  const toggleDraftService = (serviceId: number) => {
    setPackageDraft((prev) => {
      if (!prev) return prev;
      const chosen = prev.services.includes(serviceId)
        ? prev.services.filter((id) => id !== serviceId)
        : [...prev.services, serviceId];
      return { ...prev, services: chosen };
    });
  };

  /**
   * حفظُ الباقة: `suggested_price` **لا تُرسل** لمن لا يملك رؤية المبالغ — الخادم
   * يردّ 403 على كتابتها، وإرسالُ `null` يحمل المفتاح نفسه فيُرفض كذلك.
   */
  const savePackage = async () => {
    if (!packageDraft || !packageDraft.name.trim()) return;
    const body: { name: string; services: number[]; suggested_price?: string | null } = {
      name: packageDraft.name.trim(),
      services: packageDraft.services,
    };
    if (canSeeAmounts) {
      body.suggested_price = packageDraft.price.trim() === '' ? null : packageDraft.price.trim();
    }
    try {
      const saved = packageDraft.id === null
        ? await createServicePackage(body)
        : await updateServicePackage(packageDraft.id, body);
      setPackages((prev) => {
        const others = prev.filter((row) => row.id !== saved.id);
        return [...others, saved].sort((a, b) => a.name.localeCompare(b.name, 'ar'));
      });
      setPackageDraft(null);
      toast('حُفظت الباقة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ الباقة.'), 'error');
    }
  };

  const removePackage = async (row: ServicePackageRow) => {
    const ok = await confirm({
      title: 'حذف الباقة',
      message:
        `تُحذف باقة «${row.name}» من القوالب. خدماتُ الزبائن التي طُبّقت عليها سابقاً لا تتغيّر.`,
      confirmText: 'احذف الباقة',
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteServicePackage(row.id);
      setPackages((prev) => prev.filter((item) => item.id !== row.id));
      toast('حُذفت الباقة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حذف الباقة.'), 'error');
    }
  };

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

      <OfficeCard title="الخدمات والباقات">
        {servicesError ? (
          <OfficeError
            message={servicesError}
            onRetry={() => loadServices()}
          />
        ) : servicesLoading ? (
          <OfficeSkeleton />
        ) : (
          <>
        <h3 className="text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
          كتالوج الخدمات
        </h3>
        <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
          الخمسةُ الافتراضية تُزرع تلقائياً. عطّل ما لا تقدّمه، وأضِف ما تقدّمه — والخدمةُ
          المستعملة لا تُحذف، تُعطَّل فيبقى تاريخُ من اشتراها.
        </p>
        <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          {catalog.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-2 py-2">
              {serviceDraft?.id === row.id ? (
                <>
                  <input
                    value={serviceDraft.name}
                    onChange={(event) =>
                      setServiceDraft({ id: row.id, name: event.target.value })
                    }
                    className={`${officeInputClass} w-48`}
                  />
                  <button
                    type="button"
                    onClick={() => saveServiceName(row)}
                    className={officePrimaryButtonClass}
                  >
                    احفظ
                  </button>
                  <button
                    type="button"
                    onClick={() => setServiceDraft(null)}
                    className={officeSecondaryButtonClass}
                  >
                    إلغاء
                  </button>
                </>
              ) : (
                <>
                  <span
                    className={
                      row.is_active
                        ? 'text-[12.5px] font-semibold text-slate-800 dark:text-slate-100'
                        : 'text-[12.5px] font-semibold text-slate-400 line-through dark:text-slate-500'
                    }
                  >
                    {row.name}
                  </span>
                  {row.is_builtin ? (
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                      افتراضية
                    </span>
                  ) : null}
                  {canManageSettings ? (
                    <div className="ms-auto flex items-center gap-3">
                      <label className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-600 dark:text-slate-300">
                        <input
                          type="checkbox"
                          checked={row.is_active}
                          onChange={() => toggleService(row)}
                          aria-label={`تفعيل ${row.name}`}
                          className="size-4 rounded border-slate-300"
                        />
                        مفعّلة
                      </label>
                      <button
                        type="button"
                        onClick={() => setServiceDraft({ id: row.id, name: row.name })}
                        className="text-[10.5px] font-medium text-teal-700 hover:underline dark:text-teal-400"
                      >
                        عدّل الاسم
                      </button>
                    </div>
                  ) : null}
                </>
              )}
            </li>
          ))}
        </ul>
        {canManageSettings ? (
          <form onSubmit={addService} className="mt-3 flex flex-wrap items-center gap-2">
            <input
              value={newServiceName}
              onChange={(event) => setNewServiceName(event.target.value)}
              placeholder="خدمة جديدة…"
              aria-label="خدمة جديدة"
              className={`${officeInputClass} w-56`}
            />
            <button type="submit" className={officePrimaryButtonClass}>
              أضف خدمة
            </button>
          </form>
        ) : null}

        <h3 className="mt-6 text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
          الباقات الجاهزة
        </h3>
        <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
          قالبٌ يعبّئ خدمات الزبون بكبسةٍ ثم تُعدَّل — نسخٌ لا ربط: تعديلُ الباقة بعدها
          لا يمسّ زبوناً.
        </p>
        {packages.length === 0 ? (
          <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">
            لا باقةَ بعد. اجمع خدماتٍ في باقةٍ وسعرٍ مقترحٍ اختياريّ.
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
            {packages.map((row) => (
              <li key={row.id} className="py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                    {row.name}
                  </span>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10.5px] tabular-nums text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    السعر المقترح: {formatOfficeAmount(row.suggested_price)}
                  </span>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    {row.services.length === 0
                      ? 'بلا خدمات'
                      : row.services.map((service) => service.name).join('، ')}
                  </span>
                  {canManageSettings ? (
                    <div className="ms-auto flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() =>
                          setPackageDraft({
                            id: row.id,
                            name: row.name,
                            price: row.suggested_price ?? '',
                            services: row.services.map((service) => service.id),
                          })
                        }
                        className="text-[10.5px] font-medium text-teal-700 hover:underline dark:text-teal-400"
                      >
                        عدّل
                      </button>
                      <button
                        type="button"
                        onClick={() => removePackage(row)}
                        className="text-[10.5px] font-medium text-rose-600 hover:underline dark:text-rose-400"
                      >
                        احذف
                      </button>
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}

        {canManageSettings ? (
          packageDraft ? (
            <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                  اسم الباقة
                  <input
                    value={packageDraft.name}
                    onChange={(event) =>
                      setPackageDraft({ ...packageDraft, name: event.target.value })
                    }
                    className={`${officeInputClass} mt-1 block w-full`}
                  />
                </label>
                {canSeeAmounts ? (
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    السعر المقترح (اختياري)
                    <input
                      value={packageDraft.price}
                      onChange={(event) =>
                        setPackageDraft({ ...packageDraft, price: event.target.value })
                      }
                      inputMode="decimal"
                      className={`${officeInputClass} mt-1 block w-full tabular-nums`}
                    />
                  </label>
                ) : null}
              </div>
              <fieldset className="mt-3">
                <legend className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                  خدمات الباقة
                </legend>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {packageServiceChoices.map((service) => (
                    <label
                      key={service.id}
                      className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    >
                      <input
                        type="checkbox"
                        checked={packageDraft.services.includes(service.id)}
                        onChange={() => toggleDraftService(service.id)}
                        className="size-3.5 rounded border-slate-300"
                      />
                      {service.name}
                      {service.is_active ? null : (
                        <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 text-[9.5px] font-semibold text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                          معطّلة
                        </span>
                      )}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="mt-3 flex items-center gap-2">
                <button type="button" onClick={savePackage} className={officePrimaryButtonClass}>
                  احفظ الباقة
                </button>
                <button
                  type="button"
                  onClick={() => setPackageDraft(null)}
                  className={officeSecondaryButtonClass}
                >
                  إلغاء
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() =>
                setPackageDraft({ id: null, name: '', price: '', services: [] })
              }
              className={`mt-3 ${officeSecondaryButtonClass}`}
            >
              باقة جديدة
            </button>
          )
        ) : null}
          </>
        )}
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
