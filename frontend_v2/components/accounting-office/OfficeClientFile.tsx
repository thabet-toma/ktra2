import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  assignOfficeClient,
  createContact,
  deleteContact,
  endOfficeClient,
  getClientSettings,
  getOfficeClient,
  linkClientContact,
  listClientContacts,
  listContacts,
  listOfficeMembers,
  listReminderRecipients,
  promoteClientContact,
  reactivateOfficeClient,
  resetClientSetting,
  setClientSetting,
  setReminderRecipient,
  unlinkClientContact,
  updateContact,
  updateOfficeClient,
  updateTaxCard,
  type ClientContactRow,
  type ContactRow,
  type OfficeClientRow,
  type OfficeMemberRow,
  type ReminderRecipientRow,
  type SettingRow,
  type TaxCard,
} from '../../services/accountingOfficeApi';
import {
  AMOUNT_MASK,
  clientStatusBadgeClass,
  customizedSettingCount,
  formatOfficeAmount,
  showsOfficeAssignment,
  visibleClientSettings,
} from '../../utils/accountingOffice';
import { formatDateValue } from '../../utils/formatDate';
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

type TabKey = 'tax-card' | 'contacts' | 'notes';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'tax-card', label: 'البطاقة الضريبية' },
  { key: 'contacts', label: 'جهات الاتصال' },
  { key: 'notes', label: 'ملاحظات' },
];

const EMPTY_CARD: TaxCard = {
  id: 0,
  entity_type: '',
  entity_type_label: '',
  vat_classification: '',
  vat_classification_label: '',
  annual_sales: '0',
  has_employees: false,
  employees_count: 0,
  is_self_employed: false,
  tax_system: null,
  entity_type_choices: [],
  vat_classification_choices: [],
  updated_at: '',
};

const statusOf = (failure: unknown): number | undefined =>
  (failure as { status?: number } | null)?.status;

/**
 * ISSUE #271 — ملفّ الزبون: رأسُه وثلاثةُ تبويباتٍ لا غير الآن.
 *
 * **الرأس** يقول ما يهمّ قبل أيّ كبسة: الحالة، والنظامُ الضريبيّ **الفعليّ** بعد
 * المحلّل، وتاريخُ الإنهاء إن وُجد. وزرُّ «أنهِ» لا يحذف شيئاً: الزبون يبقى
 * ببطاقته وجهاته، و«أعِد نشاطاً» يُرجعه — والـAPI لا يعرف `DELETE` لهذا المورد.
 * والاسمُ ورقمُ الملف الضريبي يُحرَّران من الرأس بـ«عدّل».
 *
 * **وإعدادُ الزبون يُحفظ بلا إعادة تحميل**: كانت كلُّ كبسة «احفظ» تجلب الملفّ
 * كلَّه فتمسح تعديلاً غير محفوظٍ في البطاقة أو الملاحظات. اليوم يُحدَّث سطرُ
 * الإعداد والرأسُ وحدهما — إلا `tax_system` فيُعاد جلبه لأن اختيارات
 * البطاقة تغيّرت وقد فُرّغ بعضها.
 *
 * **والصلاحيات تُخفي ولا تحمي** (#272): كلُّ زرِّ كتابةٍ يختفي بلا
 * `office.clients.write`، و«حوّل» بلا `office.clients.assign`، والخادم يردّ 403
 * على كلٍّ منها على أيّ حال. والمبلغُ `null` (بلا «يرى المبالغ») يُعرض «—»، ولا
 * يُرسَل في الحفظ — فلا يُمحى المخزَّن بحفظ عضوٍ لا يراه.
 */
export const OfficeClientFile: React.FC<{
  clientId: number;
  officeSize: string | null;
  onBack: () => void;
  onMissing: () => void;
}> = ({ clientId, officeSize, onBack, onMissing }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const canWrite = can('office.clients.write');
  const canAssign = can('office.clients.assign');
  const canSeeAmounts = can('office.amounts.view');
  const showsResponsible = showsOfficeAssignment(officeSize);
  const [client, setClient] = useState<OfficeClientRow | null>(null);
  const [settings, setSettings] = useState<SettingRow[]>([]);
  const [links, setLinks] = useState<ClientContactRow[]>([]);
  const [recipients, setRecipients] = useState<ReminderRecipientRow[]>([]);
  const [pickerContacts, setPickerContacts] = useState<ContactRow[]>([]);
  const [pickerQuery, setPickerQuery] = useState('');
  const [tab, setTab] = useState<TabKey>('tax-card');
  const [card, setCard] = useState<TaxCard>(EMPTY_CARD);
  const [savedCard, setSavedCard] = useState<TaxCard>(EMPTY_CARD);
  const [notes, setNotes] = useState('');
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [identityDraft, setIdentityDraft] = useState({ name: '', tax_file_number: '' });
  const [editingContact, setEditingContact] = useState<number | null>(null);
  const [contactDraft, setContactDraft] = useState({ name: '', phone: '', language: 'ar' as 'ar' | 'he' });
  const [newContact, setNewContact] = useState({ name: '', phone: '', language: 'ar' as 'ar' | 'he' });
  const [members, setMembers] = useState<OfficeMemberRow[]>([]);
  const [assigning, setAssigning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // `onMissing` تصل دالّةً جديدة مع كل رسمٍ للأب. لو دخلت في تبعيّات `load`
  // لأُعيد التحميل مع كل رسم، فتُمسح تعديلاتُ البطاقة والملاحظات غير المحفوظة.
  // فتُحفظ في مرجع، ويبقى `load` معتمداً على `clientId` وحده.
  const onMissingRef = useRef(onMissing);
  useEffect(() => {
    onMissingRef.current = onMissing;
  }, [onMissing]);

  const applyClient = useCallback((row: OfficeClientRow) => {
    setClient(row);
    setCard(row.tax_card ?? EMPTY_CARD);
    setSavedCard(row.tax_card ?? EMPTY_CARD);
    setNotes(row.notes);
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    return Promise.all([getOfficeClient(clientId), getClientSettings(clientId)])
      .then(([row, clientSettings]) => {
        applyClient(row);
        setSettings(clientSettings.settings);
      })
      .catch((failure) => {
        if (statusOf(failure) === 404) {
          onMissingRef.current();
          return;
        }
        setError(humanizeThrown(failure, 'تعذّر تحميل ملفّ الزبون.'));
      })
      .finally(() => setLoading(false));
  }, [applyClient, clientId]);

  useEffect(() => {
    load();
  }, [load]);

  const refreshSettings = useCallback(() => {
    return getClientSettings(clientId)
      .then((payload) => setSettings(payload.settings))
      .catch((failure) => toast(humanizeThrown(failure, 'تعذّر تحديث الإعدادات.'), 'error'));
  }, [clientId, toast]);

  const refreshHeader = useCallback(() => {
    return getOfficeClient(clientId)
      .then((row) => setClient(row))
      .catch((failure) => toast(humanizeThrown(failure, 'تعذّر تحديث رأس الملفّ.'), 'error'));
  }, [clientId, toast]);

  /**
   * الروابطُ والمستلِمون: يُجلبان عند تغيّر الزبون وبعد كلّ ربطٍ أو فكٍّ أو ترقيةٍ
   * أو حذف. **ولا يعتمدان على نصّ البحث** — كان كلُّ حرفٍ يُطلق ثلاثة طلبات ويفوز
   * آخرها وصولاً لا آخرها إرسالاً.
   */
  const refreshLinks = useCallback(async () => {
    try {
      const [clientLinks, reminderRows] = await Promise.all([
        listClientContacts(clientId),
        listReminderRecipients(clientId),
      ]);
      setLinks(clientLinks);
      setRecipients(reminderRows);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحديث جهات الاتصال.'), 'error');
    }
  }, [clientId, toast]);

  useEffect(() => {
    refreshLinks();
  }, [refreshLinks]);

  /**
   * أعضاءُ الشركة لمنتقي «حوّل» — يُجلبون حين يملك العضو `office.clients.assign`
   * وفي مكتبٍ فيه أكثر من شخص. و«شخص واحد» لا منتقيَ فيه أصلاً.
   */
  useEffect(() => {
    if (!canAssign || !showsResponsible) return;
    let cancelled = false;
    listOfficeMembers()
      .then((rows) => {
        if (!cancelled) setMembers(rows);
      })
      .catch((failure) => {
        if (!cancelled) {
          toast(humanizeThrown(failure, 'تعذّر تحميل أعضاء المكتب.'), 'error');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canAssign, showsResponsible, toast]);

  /** التحويلُ فعلٌ مُسجَّل خادمياً (من ← إلى) — والردُّ يحمل المسؤول الجديد. */
  const transfer = async (userId: number) => {
    if (!userId) return;
    setAssigning(true);
    try {
      setClient(await assignOfficeClient(clientId, userId));
      toast('حُوّل الزبون إلى موظّفٍ آخر', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحويل الزبون.'), 'error');
    } finally {
      setAssigning(false);
    }
  };

  /** بحثُ المنتقي في أثره المستقلّ: تأخيرٌ 250مث وتجاهلُ الردود خارج الترتيب. */
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      listContacts(pickerQuery)
        .then((rows) => {
          if (!cancelled) setPickerContacts(rows);
        })
        .catch((failure) => {
          if (!cancelled) toast(humanizeThrown(failure, 'تعذّر تحميل جهات الاتصال.'), 'error');
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [pickerQuery, toast]);

  const available = useMemo(() => {
    const linkedIds = new Set(links.map((link) => link.contact.id));
    return pickerContacts.filter((contact) => !linkedIds.has(contact.id));
  }, [pickerContacts, links]);

  const cardDirty = useMemo(
    () => JSON.stringify(card) !== JSON.stringify(savedCard),
    [card, savedCard],
  );
  const notesDirty = client ? notes !== client.notes : false;

  const saveCard = async () => {
    try {
      const updated = await updateTaxCard(clientId, {
        entity_type: card.entity_type,
        vat_classification: card.vat_classification,
        // المبلغُ لا يُرسَل لمن لا يملك رؤيته: إرسالُه يمحو المخزَّن أو يردّ 403 بلا داعٍ.
        // والحكمُ للصلاحية لا لفراغ القيمة: من يملكها ومسح الحقل يُرسَل كما هو.
        ...(canSeeAmounts ? { annual_sales: card.annual_sales ?? '' } : {}),
        has_employees: card.has_employees,
        employees_count: card.employees_count,
        is_self_employed: card.is_self_employed,
      });
      setCard(updated);
      setSavedCard(updated);
      toast('حُفظت البطاقة الضريبية', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ البطاقة.'), 'error');
    }
  };

  const toggleStatus = async () => {
    if (!client) return;
    if (client.status === 'active') {
      const ok = await confirm({
        title: 'إنهاء الزبون',
        message:
          'تتوقّف تذكيراته وفواتيره وشغلاته الجديدة، ويبقى كلُّ شيء (بطاقته وجهاته وملاحظاته وتاريخه)، ويعود نشطاً متى شئت.',
        confirmText: 'أنهِ الزبون',
        danger: true,
      });
      if (!ok) return;
    }
    try {
      const updated =
        client.status === 'active'
          ? await endOfficeClient(client.id)
          : await reactivateOfficeClient(client.id);
      setClient(updated);
      toast(updated.status === 'ended' ? 'أُنهي الزبون وبقي كلُّ شيء' : 'رجع الزبون نشطاً', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تغيير حالة الزبون.'), 'error');
    }
  };

  const saveNotes = async () => {
    try {
      const updated = await updateOfficeClient(clientId, { notes });
      setClient(updated);
      toast('حُفظت الملاحظات', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ الملاحظات.'), 'error');
    }
  };

  const startEditIdentity = () => {
    if (!client) return;
    setIdentityDraft({ name: client.name, tax_file_number: client.tax_file_number });
    setEditingIdentity(true);
  };

  /**
   * الاسمُ ورقمُ الملف وحدهما: يُحدَّث `client` من الردّ، **ولا تُمسّ** البطاقةُ
   * ولا الملاحظات — `applyClient` كانت ستمسح مسوّدتيهما غير المحفوظتين.
   */
  const saveIdentity = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!identityDraft.name.trim()) return;
    try {
      const updated = await updateOfficeClient(clientId, {
        name: identityDraft.name.trim(),
        tax_file_number: identityDraft.tax_file_number.trim(),
      });
      setClient(updated);
      setEditingIdentity(false);
      toast('حُفظ اسم الزبون ورقم ملفّه', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ اسم الزبون ورقم ملفّه.'), 'error');
    }
  };

  /**
   * حفظ تخصيص إعداد: يُحدَّث سطرُه وحده. و`tax_system` استثناءٌ مقصود —
   * تغييره يُفرّغ في الخادم ما لا يصلح في النظام الجديد، فتُجلَب البطاقة ثانيةً.
   * والسؤالُ **قبل** الحفظ: إلغاؤه يجب ألّا يترك النظامَ مغيَّراً وبطاقةً قديمة.
   */
  const confirmCardWillChange = async (): Promise<boolean> => {
    if (!cardDirty) return true;
    return confirm({
      title: 'تغيير النظام الضريبي',
      message:
        'تغيّر اختيارات البطاقة الضريبية، وقد يُفرَّغ منها ما لا يصلح في النظام الجديد. لديك تعديلات غير محفوظة في البطاقة ستُفقد — أتابع؟',
      confirmText: 'تابع وأحدّث البطاقة',
      danger: true,
    });
  };

  /**
   * بعد تغيير النظام: البطاقةُ والرأسُ من الخادم — **ولا تُمسّ الملاحظات**.
   * `applyClient` تكتب الملاحظات أيضاً، فكان تغييرُ النظام يمسح مسوّدةً غير محفوظة.
   */
  const reloadCardFromServer = useCallback(async () => {
    try {
      const row = await getOfficeClient(clientId);
      setClient(row);
      setCard(row.tax_card ?? EMPTY_CARD);
      setSavedCard(row.tax_card ?? EMPTY_CARD);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحديث البطاقة بعد تغيير النظام.'), 'error');
    }
  }, [clientId, toast]);

  const saveSetting = async (setting: SettingRow, value: unknown) => {
    const systemChange = setting.key === 'tax_system';
    if (systemChange && !(await confirmCardWillChange())) return;
    try {
      const row = await setClientSetting(clientId, setting.key, value);
      setSettings((prev) =>
        prev.map((item) =>
          item.key === setting.key
            ? { ...item, ...row, label: item.label, client_label: item.client_label }
            : item,
        ),
      );
      toast('حُفظ تخصيص الزبون', 'success');
      // `reloadCardFromServer` تكتب الرأس أيضاً — نداءُ الاثنين جلبٌ مكرّرٌ للمورد نفسه.
      if (systemChange) await reloadCardFromServer();
      else refreshHeader();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ تخصيص الزبون.'), 'error');
      throw failure; // ليُظهره `SettingControl` تحت السطر نفسه
    }
  };

  const resetSetting = async (setting: SettingRow) => {
    const systemChange = setting.key === 'tax_system';
    if (systemChange && !(await confirmCardWillChange())) return;
    try {
      await resetClientSetting(clientId, setting.key);
      await refreshSettings();
      toast('رجع الإعداد إلى قيمة المكتب', 'success');
      if (systemChange) await reloadCardFromServer();
      else refreshHeader();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر الرجوع إلى إعداد المكتب.'), 'error');
      throw failure;
    }
  };

  const addExistingContact = async (contactId: number) => {
    try {
      await linkClientContact(clientId, contactId);
      await refreshLinks();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر ربط الجهة.'), 'error');
    }
  };

  const addNewContact = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newContact.name.trim()) return;
    try {
      const created = await createContact({
        name: newContact.name.trim(),
        phone: newContact.phone.trim(),
        language: newContact.language,
      });
      await linkClientContact(clientId, created.id);
      setNewContact({ name: '', phone: '', language: 'ar' });
      await refreshLinks();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إنشاء الجهة.'), 'error');
    }
  };

  const startEditContact = (contact: ContactRow) => {
    setEditingContact(contact.id);
    setContactDraft({
      name: contact.name,
      phone: contact.phone,
      language: contact.language,
    });
  };

  const saveContactEdit = async (contactId: number) => {
    try {
      const updated = await updateContact(contactId, {
        name: contactDraft.name.trim(),
        phone: contactDraft.phone.trim(),
        language: contactDraft.language,
      });
      setEditingContact(null);
      // سطرُ المنتقي يُحدَّث بالقيمة الراجعة — وإلا بقي الاسمُ القديم ظاهراً فيه.
      setPickerContacts((prev) =>
        prev.map((row) => (row.id === updated.id ? updated : row)),
      );
      await refreshLinks();
      toast('حُدّثت الجهة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تعديل الجهة.'), 'error');
    }
  };

  const removeContact = async (contact: ContactRow) => {
    const ok = await confirm({
      title: 'حذف الجهة',
      message: `تُحذف «${contact.name}» من دفتر جهات المكتب نهائياً. لا تُحذف وهي مربوطةٌ بزبون.`,
      confirmText: 'احذف الجهة',
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteContact(contact.id);
      // `available` مشتقّةٌ من `pickerContacts`، فحذفُ الصفّ منها هو ما يُخفيه
      // فوراً — `refreshLinks` وحدها تُحدّث الروابط لا نتيجة البحث.
      setPickerContacts((prev) => prev.filter((row) => row.id !== contact.id));
      await refreshLinks();
      toast('حُذفت الجهة', 'success');
    } catch (failure) {
      // الخادم يرفض حذف جهةٍ مربوطةٍ بزبونٍ آخر برسالةٍ صريحة.
      toast(humanizeThrown(failure, 'تعذّر حذف الجهة.'), 'error');
    }
  };

  const promote = async (contactId: number) => {
    try {
      await promoteClientContact(clientId, contactId);
      await refreshLinks();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تعيين الجهة الرئيسية.'), 'error');
    }
  };

  const unlink = async (contactId: number) => {
    try {
      await unlinkClientContact(clientId, contactId);
      await refreshLinks();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر فكّ ربط الجهة.'), 'error');
    }
  };

  const assignRecipient = async (reminderType: string, contactId: number | null) => {
    try {
      setRecipients(await setReminderRecipient(clientId, reminderType, contactId));
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تعيين المستلِم.'), 'error');
    }
  };

  if (loading && !client) return <OfficeSkeleton />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!client) return null;

  const visible = visibleClientSettings(settings, client.tax_system);
  const customizedCount = customizedSettingCount(visible);

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <button
          type="button"
          onClick={onBack}
          className="mb-2 text-[11.5px] font-medium text-teal-700 hover:underline dark:text-teal-400"
        >
          ← رجوع إلى الزبائن
        </button>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            {editingIdentity ? (
              <form onSubmit={saveIdentity} className="flex flex-wrap items-end gap-3">
                <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                  الاسم
                  <input
                    value={identityDraft.name}
                    onChange={(event) =>
                      setIdentityDraft({ ...identityDraft, name: event.target.value })
                    }
                    required
                    className={`${officeInputClass} mt-1 block w-64`}
                  />
                </label>
                <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                  رقم الملف الضريبي (اختياري)
                  <input
                    value={identityDraft.tax_file_number}
                    onChange={(event) =>
                      setIdentityDraft({ ...identityDraft, tax_file_number: event.target.value })
                    }
                    className={`${officeInputClass} mt-1 block w-48 tabular-nums`}
                  />
                </label>
                <button type="submit" className={officePrimaryButtonClass}>
                  احفظ
                </button>
                <button
                  type="button"
                  onClick={() => setEditingIdentity(false)}
                  className={officeSecondaryButtonClass}
                >
                  إلغاء
                </button>
              </form>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-[22px] font-bold leading-8 text-slate-900 dark:text-slate-100">
                  {client.name}
                </h1>
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${clientStatusBadgeClass(client.status)}`}
                >
                  {client.status_label}
                </span>
                {customizedCount > 0 ? (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                    {customizedCount} إعداد مخصَّص
                  </span>
                ) : null}
                {canWrite ? (
                  <button
                    type="button"
                    onClick={startEditIdentity}
                    className="text-[10.5px] font-medium text-slate-600 hover:underline dark:text-slate-300"
                  >
                    عدّل
                  </button>
                ) : null}
              </div>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                {client.tax_system_label}
              </span>
              {client.tax_file_number ? (
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-medium tabular-nums text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  ملف {client.tax_file_number}
                </span>
              ) : null}
              {client.ended_on ? (
                <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                  منتهٍ بتاريخ {formatDateValue(client.ended_on)}
                </span>
              ) : null}
              {/* الموظف المسؤول — لا يُعرض في مكتب «شخص واحد». */}
              {showsResponsible ? (
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  المسؤول: {client.responsible_name || '— بلا مسؤول —'}
                </span>
              ) : null}
            </div>
            {/* «حوّل» لأصحاب `office.clients.assign` وحدهم — وقائمةُ أعضاء الشركة. */}
            {canAssign && showsResponsible ? (
              <label className="mt-2 inline-flex items-center gap-2 text-[11px] font-medium text-slate-600 dark:text-slate-300">
                حوّل إلى
                <select
                  value=""
                  disabled={assigning}
                  onChange={(event) => {
                    void transfer(Number(event.target.value));
                  }}
                  className={`${officeInputClass} h-8`}
                >
                  <option value="">— اختر موظفاً —</option>
                  {members.map((member) => (
                    <option key={member.user_id} value={member.user_id}>
                      {member.full_name || member.username}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
          {canWrite ? (
            <button
              type="button"
              onClick={toggleStatus}
              className={
                client.status === 'active'
                  ? 'rounded-lg border border-rose-200 bg-white px-3 py-2 text-[12px] font-medium text-rose-700 dark:border-rose-900 dark:bg-slate-900 dark:text-rose-300'
                  : officePrimaryButtonClass
              }
            >
              {client.status === 'active' ? 'أنهِ الزبون' : 'أعِد نشاطاً'}
            </button>
          ) : null}
        </div>
      </header>

      <div className="border-b border-slate-200 dark:border-slate-700">
        <div className="-mb-px flex gap-1 overflow-x-auto">
          {TABS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              onClick={() => setTab(entry.key)}
              aria-current={tab === entry.key ? 'page' : undefined}
              className={
                tab === entry.key
                  ? 'shrink-0 border-b-2 border-teal-700 px-3 py-2.5 text-[12px] font-semibold text-teal-800 dark:border-teal-400 dark:text-teal-300'
                  : 'shrink-0 border-b-2 border-transparent px-3 py-2.5 text-[12px] font-medium text-slate-500 dark:text-slate-400'
              }
            >
              {entry.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'tax-card' ? (
        <div className="space-y-4">
          <OfficeCard title="البطاقة الضريبية">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                نوع الكيان
                <select
                  value={card.entity_type}
                  onChange={(event) => setCard({ ...card, entity_type: event.target.value })}
                  className={`${officeInputClass} mt-1 block w-full`}
                >
                  <option value="">— لم يُحدَّد —</option>
                  {card.entity_type_choices.map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                تصنيف ق.م
                <select
                  value={card.vat_classification}
                  onChange={(event) => setCard({ ...card, vat_classification: event.target.value })}
                  className={`${officeInputClass} mt-1 block w-full`}
                >
                  <option value="">— لم يُحدَّد —</option>
                  {card.vat_classification_choices.map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                المبيعات السنوية
                {/* من لا يملك رؤية المبالغ يرى «—» ولا يُرسَل في الحفظ (#272). */}
                {canSeeAmounts ? (
                  <input
                    value={card.annual_sales ?? ''}
                    onChange={(event) => setCard({ ...card, annual_sales: event.target.value })}
                    inputMode="decimal"
                    className={`${officeInputClass} mt-1 block w-full tabular-nums`}
                  />
                ) : (
                  <input
                    value={formatOfficeAmount(card.annual_sales)}
                    readOnly
                    disabled
                    aria-label={`المبيعات السنوية ${AMOUNT_MASK}`}
                    className={`${officeInputClass} mt-1 block w-full tabular-nums`}
                  />
                )}
              </label>

              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                عدد الموظفين
                <input
                  type="number"
                  min={0}
                  value={card.employees_count}
                  onChange={(event) =>
                    setCard({ ...card, employees_count: Number(event.target.value || 0) })
                  }
                  className={`${officeInputClass} mt-1 block w-full tabular-nums`}
                />
              </label>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-4 text-[12px] text-slate-700 dark:text-slate-200">
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={card.has_employees}
                  onChange={(event) => setCard({ ...card, has_employees: event.target.checked })}
                  className="size-4 rounded border-slate-300"
                />
                له موظفون
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={card.is_self_employed}
                  onChange={(event) => setCard({ ...card, is_self_employed: event.target.checked })}
                  className="size-4 rounded border-slate-300"
                />
                עצמאי يدفع ביטוח לאומי
              </label>
              {canWrite ? (
                <button type="button" onClick={saveCard} className={`ms-auto ${officePrimaryButtonClass}`}>
                  احفظ البطاقة
                </button>
              ) : null}
            </div>
          </OfficeCard>

          <OfficeCard title="إعدادات هذا الزبون">
            {visible.map((setting) => (
              <div key={setting.key}>
                {setting.is_customized ? (
                  <span className="mt-3 inline-block rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                    مخصَّص لهذا الزبون
                  </span>
                ) : null}
                <SettingControl
                  setting={setting}
                  value={setting.value}
                  canReset={setting.is_customized === true}
                  resetLabel="ارجع لإعداد المكتب"
                  disabled={!canWrite}
                  onReset={() => resetSetting(setting)}
                  onSave={(value) => saveSetting(setting, value)}
                />
              </div>
            ))}
          </OfficeCard>
        </div>
      ) : null}

      {tab === 'contacts' ? (
        <div className="space-y-4">
          <OfficeCard title="جهات الزبون">
            {links.length === 0 ? (
              <p className="text-[12px] text-slate-500 dark:text-slate-400">
                لا جهة مربوطة بعد — اربط واحدة أدناه.
              </p>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {links.map((link) => (
                  <li key={link.id} className="py-2">
                    {editingContact === link.contact.id ? (
                      <div className="flex flex-wrap items-end gap-2">
                        <input
                          value={contactDraft.name}
                          onChange={(event) =>
                            setContactDraft({ ...contactDraft, name: event.target.value })
                          }
                          className={`${officeInputClass} w-48`}
                        />
                        <input
                          value={contactDraft.phone}
                          onChange={(event) =>
                            setContactDraft({ ...contactDraft, phone: event.target.value })
                          }
                          className={`${officeInputClass} w-36 tabular-nums`}
                        />
                        <select
                          value={contactDraft.language}
                          onChange={(event) =>
                            setContactDraft({
                              ...contactDraft,
                              language: event.target.value as 'ar' | 'he',
                            })
                          }
                          className={`${officeInputClass} w-24`}
                        >
                          <option value="ar">عربي</option>
                          <option value="he">عبري</option>
                        </select>
                        <button
                          type="button"
                          onClick={() => saveContactEdit(link.contact.id)}
                          className={officePrimaryButtonClass}
                        >
                          احفظ
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingContact(null)}
                          className={officeSecondaryButtonClass}
                        >
                          إلغاء
                        </button>
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                          {link.contact.name}
                        </span>
                        <span className="text-[11.5px] tabular-nums text-slate-500 dark:text-slate-400">
                          {link.contact.phone || 'بلا رقم'}
                        </span>
                        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {link.contact.language_label}
                        </span>
                        {link.is_primary ? (
                          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
                            رئيسية
                          </span>
                        ) : canWrite ? (
                          <button
                            type="button"
                            onClick={() => promote(link.contact.id)}
                            className="text-[10.5px] font-medium text-teal-700 hover:underline dark:text-teal-400"
                          >
                            اجعلها الرئيسية
                          </button>
                        ) : null}
                        {canWrite ? (
                          <div className="ms-auto flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => startEditContact(link.contact)}
                              className="text-[10.5px] font-medium text-slate-600 hover:underline dark:text-slate-300"
                            >
                              عدّل
                            </button>
                            <button
                              type="button"
                              onClick={() => unlink(link.contact.id)}
                              className="text-[10.5px] font-medium text-rose-600 hover:underline dark:text-rose-400"
                            >
                              افكّ الربط
                            </button>
                          </div>
                        ) : null}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40">
              <p className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                اربط جهة قائمة
              </p>
              <input
                value={pickerQuery}
                onChange={(event) => setPickerQuery(event.target.value)}
                placeholder="ابحث بالاسم أو الهاتف…"
                className={`${officeInputClass} mt-1 block w-64`}
              />
              {available.length === 0 ? (
                <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                  لا جهة مطابقة غير مربوطة.
                </p>
              ) : (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {available.map((contact) => (
                    <li
                      key={contact.id}
                      className="flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] dark:border-slate-700 dark:bg-slate-900"
                    >
                      <button
                        type="button"
                        disabled={!canWrite}
                        onClick={() => addExistingContact(contact.id)}
                        className="font-medium text-slate-700 hover:underline disabled:no-underline dark:text-slate-200"
                      >
                        {contact.name}
                      </button>
                      {canWrite ? (
                        <button
                          type="button"
                          onClick={() => removeContact(contact)}
                          title="حذف الجهة من دفتر المكتب"
                          className="text-rose-600 hover:underline dark:text-rose-400"
                        >
                          ×
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {canWrite ? (
              <form
                onSubmit={addNewContact}
                className="mt-4 flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40"
              >
                <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                  جهة جديدة
                  <input
                    value={newContact.name}
                    onChange={(event) => setNewContact({ ...newContact, name: event.target.value })}
                    required
                    className={`${officeInputClass} mt-1 block w-48`}
                  />
                </label>
                <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                  الهاتف
                  <input
                    value={newContact.phone}
                    onChange={(event) => setNewContact({ ...newContact, phone: event.target.value })}
                    className={`${officeInputClass} mt-1 block w-36 tabular-nums`}
                  />
                </label>
                <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                  اللغة
                  <select
                    value={newContact.language}
                    onChange={(event) =>
                      setNewContact({ ...newContact, language: event.target.value as 'ar' | 'he' })
                    }
                    className={`${officeInputClass} mt-1 block w-24`}
                  >
                    <option value="ar">عربي</option>
                    <option value="he">عبري</option>
                  </select>
                </label>
                <button type="submit" className={officePrimaryButtonClass}>
                  أضف واربط
                </button>
              </form>
            ) : null}
          </OfficeCard>

          <OfficeCard title="مستلِم كل نوع تذكير">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 text-[10.5px] font-medium text-slate-400 dark:border-slate-700 dark:text-slate-500">
                  <th className="py-2 text-start">النوع</th>
                  <th className="py-2 text-start">المستلِم</th>
                  <th className="py-2 text-start">التعيين</th>
                </tr>
              </thead>
              <tbody>
                {recipients.map((row) => (
                  <tr
                    key={row.reminder_type}
                    className="border-b border-slate-100 last:border-b-0 dark:border-slate-800"
                  >
                    <td className="py-2 text-[12px] font-medium text-slate-700 dark:text-slate-200">
                      {row.label}
                    </td>
                    <td className="py-2 text-[12px] text-slate-600 dark:text-slate-300">
                      {row.recipient ? row.recipient.name : '— لا جهة رئيسية —'}
                      {row.is_fallback ? (
                        <span className="ms-1 text-[10px] text-slate-400 dark:text-slate-500">
                          (الرئيسية)
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2">
                      <select
                        value={
                          row.is_fallback || !row.recipient ? '' : String(row.recipient.contact_id)
                        }
                        disabled={!canWrite}
                        onChange={(event) =>
                          assignRecipient(
                            row.reminder_type,
                            event.target.value === '' ? null : Number(event.target.value),
                          )
                        }
                        className={`${officeInputClass} h-8`}
                      >
                        <option value="">حسب الرئيسية</option>
                        {links.map((link) => (
                          <option key={link.id} value={link.contact.id}>
                            {link.contact.name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </OfficeCard>
        </div>
      ) : null}

      {tab === 'notes' ? (
        <OfficeCard title="ملاحظات">
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={8}
            readOnly={!canWrite}
            className="w-full rounded-lg border border-slate-200 bg-white p-3 text-[12.5px] text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          {canWrite ? (
            <div className="mt-3 flex items-center justify-end gap-2">
              {notesDirty ? (
                <span className="text-[11px] font-medium text-amber-700 dark:text-amber-400">
                  تعديلات غير محفوظة
                </span>
              ) : null}
              <button type="button" onClick={saveNotes} className={officePrimaryButtonClass}>
                احفظ الملاحظات
              </button>
            </div>
          ) : null}
        </OfficeCard>
      ) : null}
    </div>
  );
};
