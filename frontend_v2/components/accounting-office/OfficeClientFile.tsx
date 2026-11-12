import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  addClientService,
  applyServicePackage,
  assignOfficeClient,
  assignTask,
  changeClientServiceFrequency,
  closePriorObligations,
  createContact,
  deleteContact,
  endOfficeClient,
  getClientObligations,
  getClientReminderLog,
  getClientSettings,
  getContactConsent,
  getOfficeClient,
  linkClientContact,
  listClientContacts,
  listClientServices,
  listContacts,
  listOfficeMembers,
  listOfficeServices,
  listReminderRecipients,
  listServicePackages,
  promoteClientContact,
  reactivateOfficeClient,
  resetClientSetting,
  setClientSetting,
  setContactConsent,
  setReminderRecipient,
  stopClientService,
  suggestClientService,
  undoReminderLog,
  unlinkClientContact,
  updateContact,
  updateOfficeClient,
  updateTaxCard,
  type ClientContactRow,
  type ClientObligationsPayload,
  type ClientReminderLogPayload,
  type ClientServicesPayload,
  type ContactConsentPayload,
  type ContactRow,
  type OfficeClientRow,
  type OfficeMemberRow,
  type OfficeServiceRow,
  type ReminderLogRow,
  type ReminderRecipientRow,
  type ServicePackageRow,
  type ServiceSuggestion,
  type SettingRow,
  type TaxCard,
} from '../../services/accountingOfficeApi';
import {
  AMOUNT_MASK,
  applyPackageSummary,
  canUndoReminderRow,
  frequencyAfterSuggestion,
  availableServicesForClient,
  clientServiceStatusClass,
  clientStatusBadgeClass,
  customizedSettingCount,
  firstOfMonth,
  firstOfNextMonth,
  formatOfficeAmount,
  frequencyLabelFrom,
  reminderLogKindClass,
  revertedReminderLogIds,
  shortIsoDate,
  showsOfficeAssignment,
  visibleClientSettings,
  bookMonthFromSearch,
  clientTabFromSearch,
  taskIdFromSearch,
  officeTaskAnchorId,
  CLIENT_TAB_PARAM,
  type ClientTabKey,
} from '../../utils/accountingOffice';
import { formatDateValue, formatDateTimeValue, todayIso } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import { OfficeClientAppointments } from './OfficeClientAppointments';
import { OfficeClientAccount } from './OfficeClientAccount';
import { OfficeClientBook } from './OfficeClientBook';
import { OfficeClientDocuments } from './OfficeClientDocuments';
import { OfficeClientEvents } from './OfficeClientEvents';
import {
  OfficeClientFees,
  OfficeClientStatementButton,
} from './OfficeClientFees';
import { OfficeObligationRow } from './OfficeObligationRow';
import { SettingControl } from './SettingControl';
import {
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

type TabKey = ClientTabKey;

const TABS: { key: TabKey; label: string }[] = [
  { key: 'tax-card', label: 'البطاقة الضريبية' },
  // #275: ما تولّد من التزاماتٍ وشغلاتٍ لهذا الزبون — بالحالة والأفعال.
  { key: 'obligations', label: 'الالتزامات والشغلات' },
  { key: 'services', label: 'الخدمات' },
  { key: 'contacts', label: 'جهات الاتصال' },
  // #278: شبكةُ الأشهر × البنود والقائمةُ السنوية — بعد «جهات الاتصال» كالنموذج.
  { key: 'documents', label: 'الأوراق' },
  // #280/ب: سجلُّ كل تذكيرٍ أُرسل أو كلّمناه — قراءةٌ وتصحيحٌ، بلا تعديلٍ ولا حذف.
  { key: 'reminder-log', label: 'سجلّ التذكيرات' },
  { key: 'notes', label: 'ملاحظات' },
  // #281: المواعيدُ — قبل «الدفتر»، كترتيبها في `CLIENT_TAB_KEYS`.
  { key: 'appointments', label: 'المواعيد' },
  // #283/ب: الأتعابُ — الدفعاتُ بإشعارِ قبضٍ لكلٍّ (والكشفُ من رأس الملفّ).
  { key: 'fees', label: 'الأتعاب' },
  // #282/أ٢/٢: «الحساب» — «اللي عليه» وفواتيره ورصيده ورقمُ ملفّه الضريبيّ.
  { key: 'account', label: 'الحساب' },
  // #286/ب: حركاتُ دفتر الزبون وإدخالُها — آخراً كموضعه في `CLIENT_TAB_KEYS`.
  { key: 'book', label: 'الدفتر' },
];

/** أثرُ «آخر فترة مش علينا» — جملةٌ واحدة في التأكيد وتحت خانة نموذج الإيقاف. */
const LAST_PERIOD_NOT_OURS_EFFECT = 'ما بتتولّد، واللي منتظر منها بيصير «مش لازم هالفترة».';

/** مسوّدةُ «أضف خدمة» — التواريخُ افتراضاتٌ يراها الموظف قبل الحفظ.
 *
 * `responsible_from` **شهرٌ** (`YYYY-MM`) لأن الحقل `input[type=month]`: المكتبُ
 * مسؤولٌ عن فترةٍ كاملة، والخدمةُ تُرسَل `YYYY-MM-01`.
 */
interface AddServiceDraft {
  service: string;
  starts_on: string;
  responsible_from: string;
  frequency: string;
  /** `true` حين غيّر الموظفُ الدوريةَ من القائمة بيده — فلا يكتب المقترحُ فوقها. */
  frequencyTouched: boolean;
}

const EMPTY_ADD_DRAFT: AddServiceDraft = {
  service: '', starts_on: '', responsible_from: '', frequency: '', frequencyTouched: false,
};

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
  const [searchParams, setSearchParams] = useSearchParams();
  // #276: جرسُ التنبيهات يفتح الملفَّ على تبويبه (`?tab=obligations`) — قراءةٌ
  // عند التركيب وتتبّعٌ بعدها (قد يكون الملفُّ مفتوحاً على تبويبٍ آخر)، وكتابةٌ
  // عند كل اختيار فيبقى العنوانُ صادقاً بعد التحديث.
  const tabFromUrl = clientTabFromSearch(`?${searchParams.toString()}`);
  // #276: التنبيهُ يحمل شغلتَه (`?task=`) فيُمرَّر إليها ويُبرز — وإلا فتح الملفُّ
  // على أوّل السطر وحده.
  const targetTaskId = taskIdFromSearch(`?${searchParams.toString()}`);
  const [tab, setTab] = useState<TabKey>(tabFromUrl ?? 'tax-card');
  useEffect(() => {
    if (tabFromUrl) setTab(tabFromUrl);
  }, [tabFromUrl]);
  const selectTab = useCallback((next: TabKey) => {
    setTab(next);
    const params = new URLSearchParams(searchParams);
    params.set(CLIENT_TAB_PARAM, next);
    setSearchParams(params, { replace: true });
  }, [searchParams, setSearchParams]);
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

  // ── تبويب «الخدمات» (#273) ─────────────────────────────────────────────
  const [clientServices, setClientServices] = useState<ClientServicesPayload | null>(null);
  const [catalog, setCatalog] = useState<OfficeServiceRow[]>([]);
  const [packages, setPackages] = useState<ServicePackageRow[]>([]);
  const [servicesError, setServicesError] = useState('');
  const [addDraft, setAddDraft] = useState<AddServiceDraft | null>(null);
  const [suggestion, setSuggestion] = useState<ServiceSuggestion | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [editingFrequency, setEditingFrequency] = useState<number | null>(null);
  const [frequencyDraft, setFrequencyDraft] = useState({ frequency: '', effective_from: '' });
  const [stopping, setStopping] = useState<number | null>(null);
  const [stopDate, setStopDate] = useState('');
  const [stopLastPeriodOurs, setStopLastPeriodOurs] = useState(true);
  const [packageChoice, setPackageChoice] = useState('');
  // عدّادُ طلبات الاقتراح: يمنع ردَّ اختيارٍ قديم أن يكتب فوق أحدث منه.
  const suggestionSeq = useRef(0);
  // ── تبويب «الالتزامات والشغلات» (#275) ─────────────────────────────────
  const [obligations, setObligations] = useState<ClientObligationsPayload | null>(null);
  const [obligationsLoading, setObligationsLoading] = useState(false);
  const [obligationsError, setObligationsError] = useState('');
  const [obligationsToken, setObligationsToken] = useState(0);
  const [closingPrior, setClosingPrior] = useState(false);
  const [assigningTask, setAssigningTask] = useState<number | null>(null);
  // ── سجلّ التذكيرات وموافقة الجهات (#280/ب) ──────────────────────────────
  const [reminderLog, setReminderLog] = useState<ClientReminderLogPayload | null>(null);
  const [reminderLogLoading, setReminderLogLoading] = useState(false);
  const [reminderLogError, setReminderLogError] = useState('');
  const [reminderLogToken, setReminderLogToken] = useState(0);
  /** إذنُ كل جهةٍ **فُتح محرّرُها** — يُقرأ عند الفتح أوّلاً، ثم يُحدَّث برسالة الردّ. */
  const [consents, setConsents] = useState<Record<number, ContactConsentPayload>>({});
  const [consentEdit, setConsentEdit] = useState<number | null>(null);
  /** جهةٌ يجري جلبُ إذنها الآن — لتعطيل زرّها وحدها. */
  const [consentBusy, setConsentBusy] = useState<number | null>(null);
  const [consentDraft, setConsentDraft] = useState<{ types: string[]; channel: string }>({
    types: [],
    channel: '',
  });
  /** معرّفاتُ الصفوف التي أبطلها صفُّ `undo` — تُحسب مرّةً لا في كل سطر. */
  const revertedLogIds = useMemo(
    () => revertedReminderLogIds(reminderLog?.rows ?? []),
    [reminderLog],
  );
  /** إعادةُ قراءة السجلّ بعد كل تصحيح — الصفُّ لا يُعدَّل، فيُقرأ ما كُتب. */
  const reloadReminderLog = useCallback(() => {
    setReminderLogToken((token) => token + 1);
  }, []);

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

  // ── أفعالُ تبويب «الالتزامات والشغلات» (#275) ─────────────────────────
  /** الخادمُ هو الحكم: كلُّ فعلٍ ناجحٍ يُعيد قراءة الشغلات والالتزامات. */
  const reloadObligations = useCallback(() => {
    setObligationsToken((token) => token + 1);
  }, []);

  /** «هدول انقدّموا قبل ما يجي علينا» — بتأكيدٍ صريح، ويقال كم أُغلق. */
  const closePrior = async () => {
    const ok = await confirm({
      title: 'هدول انقدّموا قبل ما يجي علينا',
      message:
        'تُسكَّت كلُّ الالتزامات المنتظِرة التي انتهت فترتُها قبل اليوم، بلا تاريخ تقديمٍ ولا رقم: لم نقدّمها نحن، بل وجدناها مقدَّمة. تُراجَع واحدةً واحدةً بعدها.',
      confirmText: 'أغلقها',
    });
    if (!ok) return;
    setClosingPrior(true);
    try {
      const result = await closePriorObligations(clientId);
      toast(
        result.closed
          ? `أُغلق ${result.closed} التزاماً سابقاً`
          : 'لا التزامات منتظِرة قبل اليوم',
        'success',
      );
      reloadObligations();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إغلاق الالتزامات السابقة.'), 'error');
    } finally {
      setClosingPrior(false);
    }
  };

  /** تحويلُ شغلةٍ — بمفتاح `office.clients.assign`، و`null` يعيد الوراثة. */
  const changeTaskAssignee = async (taskId: number, raw: string) => {
    setAssigningTask(taskId);
    try {
      await assignTask(taskId, raw ? Number(raw) : null);
      reloadObligations();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحويل الشغلة.'), 'error');
    } finally {
      setAssigningTask(null);
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

  // ── أفعالُ الإذن والسجلّ (#280/ب) ──────────────────────────────────────
  /**
   * تطبيقُ ردّ الإذن على **القائمة والذاكرة معاً**: حقلُ الجهة في `links` هو ما
   * يعرضه السطر، فبلا تحديثه يبقى العرض على حالةٍ قديمةٍ بعد الحفظ أو السحب.
   * (وليس طلبَ قراءةٍ ثانٍ: الردُّ نفسه يحمل الحقولَ كلَّها.)
   */
  const applyConsent = (payload: ContactConsentPayload) => {
    setConsents((prev) => ({ ...prev, [payload.contact_id]: payload }));
    setLinks((prev) => prev.map((link) => (
      link.contact.id === payload.contact_id
        ? {
            ...link,
            contact: {
              ...link.contact,
              reminders_consent: payload.reminders_consent,
              consent_types: payload.consent_types,
              consent_on: payload.consent_on,
              consent_channel: payload.consent_channel,
              consent_channel_label: payload.consent_channel_label,
              consent_withdrawn_on: payload.consent_withdrawn_on,
              consent_withdrawn_by: payload.consent_withdrawn_by,
            },
          }
        : link
    )));
  };

  /**
   * فتحُ محرّر الموافقة لجهةٍ **بعينها**: `contacts/<id>/consent/` تُطلب هنا
   * وحدها لأنها وحدها ترسل اختيارات الأنواع والقناة وتسمياتها، وتُخزَّن بمفتاح
   * المعرّف فلا تُقرأ مرّةً ثانية. وأنواعُ المسوّدة هي الحالية — **لا افتراضَ
   * محليّ**، والفراغُ يمنع الحفظ (الخادم يقبله، لكنه «أذن بلا نوعٍ فيُهمَل»).
   */
  const openConsent = async (contactId: number) => {
    if (consentEdit === contactId) {
      setConsentEdit(null);
      return;
    }
    const cached = consents[contactId];
    if (cached) {
      setConsentDraft({ types: [...cached.consent_types], channel: cached.consent_channel });
      setConsentEdit(contactId);
      return;
    }
    setConsentBusy(contactId);
    try {
      const payload = await getContactConsent(contactId);
      setConsents((prev) => ({ ...prev, [payload.contact_id]: payload }));
      setConsentDraft({ types: [...payload.consent_types], channel: payload.consent_channel });
      setConsentEdit(contactId);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحميل إذن الجهة.'), 'error');
    } finally {
      setConsentBusy(null);
    }
  };

  const saveConsent = async (contactId: number) => {
    if (consentDraft.types.length === 0) return;
    try {
      applyConsent(await setContactConsent(contactId, {
        consent: true,
        types: consentDraft.types,
        channel: consentDraft.channel,
      }));
      setConsentEdit(null);
      toast('سُجّلت الموافقة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تسجيل الموافقة.'), 'error');
    }
  };

  /** السحبُ لا يمحو الإذن: يبقى تاريخُه ومَن سحبه في السطر نفسه. */
  const withdrawConsent = async (contactId: number) => {
    const ok = await confirm({
      title: 'سحب الموافقة',
      message:
        'ما بينبعت له تذكيرٌ بعد اليوم، ويبقى تاريخُ إذنه ومَن سحبه مسجَّلين. تقدر تسجّل موافقةً جديدة في أيّ وقت.',
      confirmText: 'اسحب الموافقة',
      danger: true,
    });
    if (!ok) return;
    try {
      applyConsent(await setContactConsent(contactId, { consent: false }));
      toast('سُحبت الموافقة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر سحب الموافقة.'), 'error');
    }
  };

  /** «ما انبعتت» على صفٍّ في السجلّ — صفُّ `undo` جديدٌ والأصلُ يبقى. */
  const undoLogRow = async (row: ReminderLogRow) => {
    const ok = await confirm({
      title: 'ما انبعتت؟',
      message:
        `يُسجَّل صفٌّ جديدٌ بأن تذكير «${row.recipient_name || 'بلا اسم'}» ما انبعتت، فيخرج من العدّاد ولا يُحسب من الحدّ. الأصلُ يبقى في السجلّ.`,
      confirmText: 'نعم، ما انبعتت',
      cancelText: 'لا',
    });
    if (!ok) return;
    try {
      await undoReminderLog(row.id);
      reloadReminderLog();
      toast('سُجّل «ما انبعتت»', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تسجيل «ما انبعتت».'), 'error');
    }
  };

  // ── الخدمات والباقات (#273) ────────────────────────────────────────────
  //
  // التبويبُ يجلب حالته عند فتحه: الكتالوج والباقات لا لازمة لهما في البطاقة
  // والملاحظات، وطلبُهما مع كل فتح ملفّ يجعل الشاشة أثقل بلا مقابل.
  const refreshClientServices = useCallback(async (alive?: () => boolean) => {
    setServicesError('');
    try {
      const payload = await listClientServices(clientId);
      // إلغاءُ التبويب: ردٌّ وصل بعد خروجه لا يكتب فوق حالةٍ أحدث.
      if (alive && !alive()) return;
      setClientServices(payload);
    } catch (failure) {
      if (alive && !alive()) return;
      setServicesError(humanizeThrown(failure, 'تعذّر تحميل خدمات الزبون.'));
    }
  }, [clientId]);

  // تبويبُ «الالتزامات والشغلات» يُطلب عند فتحه وحده — لا مع كل فتحِ ملفّ.
  useEffect(() => {
    if (tab !== 'obligations') return;
    let cancelled = false;
    setObligationsLoading(true);
    setObligationsError('');
    getClientObligations(clientId)
      .then((payload) => {
        if (!cancelled) setObligations(payload);
      })
      .catch((failure) => {
        if (!cancelled) {
          setObligations(null);
          setObligationsError(humanizeThrown(failure, 'تعذّر تحميل التزامات الزبون.'));
        }
      })
      .finally(() => {
        if (!cancelled) setObligationsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, clientId, obligationsToken]);

  useEffect(() => {
    if (tab !== 'services') return;
    let cancelled = false;
    const alive = () => !cancelled;
    refreshClientServices(alive);
    Promise.all([listOfficeServices(), listServicePackages()])
      .then(([catalogRows, packageRows]) => {
        if (cancelled) return;
        setCatalog(catalogRows);
        setPackages(packageRows);
      })
      .catch((failure) => {
        if (!cancelled) {
          toast(humanizeThrown(failure, 'تعذّر تحميل كتالوج الخدمات.'), 'error');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tab, refreshClientServices, toast]);

  /**
   * سجلُّ التذكيرات (#280/ب): يُطلب عند فتح تبويبه وحده كأخيه «الالتزامات».
   * الأحدثُ أوّلاً من الخادم، وكلُّ صفٍّ **لا يُعدَّل ولا يُحذف** — التصحيحُ صفٌّ
   * جديدٌ يشير إلى ما يُبطله، فيُعاد قراءةُ السجلّ بعد كلِّ تصحيح.
   */
  useEffect(() => {
    if (tab !== 'reminder-log') return;
    let cancelled = false;
    setReminderLogLoading(true);
    setReminderLogError('');
    getClientReminderLog(clientId)
      .then((payload) => {
        if (!cancelled) setReminderLog(payload);
      })
      .catch((failure) => {
        if (!cancelled) {
          setReminderLog(null);
          setReminderLogError(humanizeThrown(failure, 'تعذّر تحميل سجلّ التذكيرات.'));
        }
      })
      .finally(() => {
        if (!cancelled) setReminderLogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, clientId, reminderLogToken]);

  // #276: وصلنا من تنبيهٍ يحمل شغلةً بعينها ⇒ يُمرَّر إليها بعد وصول التزاماتها —
  // **مرّةً لكل هدف**: `obligations` يُستبدل بعد كل فعلٍ على أي شغلة، ولولا السجلّ
  // لعادت الصفحةُ إلى الهدف مع كل حفظٍ أو تبديل تبويب ما دام `?task=` في العنوان.
  const scrolledTaskId = useRef<number | null>(null);
  useEffect(() => {
    if (targetTaskId === null) {
      scrolledTaskId.current = null;
      return;
    }
    if (tab !== 'obligations' || obligations === null) return;
    if (scrolledTaskId.current === targetTaskId) return;
    const element = document.getElementById(officeTaskAnchorId(targetTaskId));
    if (!element) return;
    element.scrollIntoView({ block: 'center', behavior: 'smooth' });
    scrolledTaskId.current = targetTaskId;
  }, [tab, targetTaskId, obligations]);

  /** الاقتراحُ يُطلب عند اختيار الخدمة أو تغيير تاريخ البدء — ثم يؤكّده الموظف. */
  const loadSuggestion = useCallback(
    async (serviceId: string, startsOn: string) => {
      const chosen = catalog.find((row) => String(row.id) === serviceId);
      if (!chosen) {
        setSuggestion(null);
        return;
      }
      // عدّادُ طلبات: اختيارٌ سريعٌ لخدمتين لا يجعل ردَّ الأولى يكتب فوق الثانية.
      const seq = ++suggestionSeq.current;
      setSuggesting(true);
      try {
        const payload = await suggestClientService(clientId, chosen.code, startsOn || undefined);
        if (seq !== suggestionSeq.current) return;
        setSuggestion(payload);
        setAddDraft((prev) =>
          prev
            ? { ...prev, frequency: frequencyAfterSuggestion(prev, payload.frequency) }
            : prev,
        );
      } catch (failure) {
        if (seq !== suggestionSeq.current) return;
        setSuggestion(null);
        toast(humanizeThrown(failure, 'تعذّر اقتراح الدورية.'), 'error');
      } finally {
        if (seq === suggestionSeq.current) setSuggesting(false);
      }
    },
    [catalog, clientId, toast],
  );

  const openAddService = () => {
    const today = todayIso();
    setAddDraft({
      ...EMPTY_ADD_DRAFT,
      starts_on: today,
      // الحقلُ شهرٌ (`input[type=month]`) والخدمةُ تُرسَل أولَ الشهر.
      responsible_from: firstOfMonth(today).slice(0, 7),
    });
    setSuggestion(null);
  };

  const submitAddService = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!addDraft || !addDraft.service) return;
    try {
      setClientServices(await addClientService(clientId, {
        service: Number(addDraft.service),
        starts_on: addDraft.starts_on || undefined,
        responsible_from: addDraft.responsible_from
          ? `${addDraft.responsible_from}-01`
          : undefined,
        // فارغةٌ ⇒ `null`: الخادم يستعمل المقترحَ من البطاقة، ويرفض 400 إن لم يوجد مقترح.
        frequency: addDraft.frequency || null,
      }));
      setAddDraft(null);
      setSuggestion(null);
      toast('أُضيفت الخدمة بدوريتها', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إضافة الخدمة.'), 'error');
    }
  };

  const startFrequencyChange = (row: { id: number; frequency: string | null }) => {
    setEditingFrequency(row.id);
    setStopping(null);
    setFrequencyDraft({
      frequency: row.frequency ?? '',
      // الشهرُ القادم: اليومُ قد يكون تاريخَ سريانٍ مسجَّلاً فيرفضه الخادم.
      effective_from: firstOfNextMonth(todayIso()),
    });
  };

  const submitFrequencyChange = async (rowId: number) => {
    if (!frequencyDraft.frequency || !frequencyDraft.effective_from) return;
    try {
      setClientServices(await changeClientServiceFrequency(clientId, rowId, frequencyDraft));
      setEditingFrequency(null);
      toast('حُفظت الدورية الجديدة من تاريخ سريانها', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تغيير الدورية.'), 'error');
    }
  };

  const startStop = (rowId: number) => {
    setStopping(rowId);
    setEditingFrequency(null);
    setStopDate(todayIso());
    setStopLastPeriodOurs(true);
  };

  const submitStop = async (row: { id: number; service: { name: string } }) => {
    if (!stopDate) return;
    const ok = await confirm({
      title: 'إيقاف الخدمة',
      message:
        `تتوقّف «${row.service.name}» بتاريخ ${formatDateValue(stopDate)}، ويبقى تاريخها كاملاً — لا يُحذف شيء.`
        + (stopLastPeriodOurs
          ? ''
          : ` وآخر فترة مش علينا: ${LAST_PERIOD_NOT_OURS_EFFECT}`),
      confirmText: 'أوقف الخدمة',
      danger: true,
    });
    if (!ok) return;
    try {
      setClientServices(
        await stopClientService(clientId, row.id, stopDate, stopLastPeriodOurs),
      );
      setStopping(null);
      toast('أُوقفت الخدمة وبقي تاريخها', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إيقاف الخدمة.'), 'error');
    }
  };

  const applyPackage = async () => {
    if (!packageChoice) return;
    try {
      const result = await applyServicePackage(clientId, Number(packageChoice));
      // باقةٌ لم تُضف شيئاً خبرٌ لا خطأ — «error» كان يلوّن رسالةً صحيحة بالأحمر.
      toast(applyPackageSummary(result), result.added.length ? 'success' : 'info');
      setPackageChoice('');
      await refreshClientServices();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تطبيق الباقة.'), 'error');
    }
  };

  /**
   * سطرُ إذن التذكير لجهةٍ واحدة (#280/ب): الحالةُ والأنواعُ وتاريخُها وطريقُها
   * **من حقول الجهة في القائمة نفسها** (`ContactRow` مع `links`) — بلا طلبِ
   * شبكةٍ لكل جهة. وتسمياتُ الأنواع من مستلِمي التذكير المحمَّلين (نصُّ الخادم)،
   * والقيمةُ الخام احتياطاً، فلا جدولَ تسمياتٍ محليّاً.
   *
   * و`contacts/<id>/consent/` تُطلب عند **فتح المحرّر لجهةٍ بعينها** وحدها لأنها
   * وحدها ترسل اختيارات الأنواع والقناة، فالمحرّرُ لا يُرسم بلا وصولها.
   * والقراءةُ لكل عضو (من يرسل يقرأ ما سيرسل)، والكتابةُ بمفتاح الكتابة وحده.
   */
  const renderConsent = (contact: ContactRow) => {
    const consent = consents[contact.id];
    const opening = consentBusy === contact.id;
    const withdrawn = !contact.reminders_consent && contact.consent_withdrawn_on !== null;
    const typeLabels = contact.consent_types.map((value) => (
      recipients.find((row) => row.reminder_type === value)?.label ?? value
    ));
    return (
      <div className="mt-1.5 rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5 dark:border-slate-800 dark:bg-slate-800/40">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px]">
          <span
            className={
              contact.reminders_consent
                ? 'rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300'
                : 'rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400'
            }
          >
            {contact.reminders_consent
              ? 'موافق يستلم تذكيرات'
              : 'ما وافق يستلم تذكيرات'}
          </span>
          {typeLabels.length > 0 ? (
            <span className="text-slate-600 dark:text-slate-300">
              {typeLabels.join(' · ')}
            </span>
          ) : null}
          {contact.consent_on ? (
            <span className="text-slate-500 dark:text-slate-400">
              من {formatDateValue(contact.consent_on)}
            </span>
          ) : null}
          {contact.consent_channel_label ? (
            <span className="text-slate-500 dark:text-slate-400">
              — {contact.consent_channel_label}
            </span>
          ) : null}
          {withdrawn ? (
            <span className="text-rose-600 dark:text-rose-400">
              سُحبت {formatDateValue(contact.consent_withdrawn_on)}
              {contact.consent_withdrawn_by ? ` — ${contact.consent_withdrawn_by.name}` : ''}
            </span>
          ) : null}
          {canWrite ? (
            <span className="ms-auto flex items-center gap-2">
              <button
                type="button"
                disabled={opening}
                onClick={() => openConsent(contact.id)}
                aria-expanded={consentEdit === contact.id}
                className="font-medium text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-400"
              >
                {opening ? 'جاري الفتح…' : 'سجّل الموافقة'}
              </button>
              {contact.reminders_consent ? (
                <button
                  type="button"
                  onClick={() => withdrawConsent(contact.id)}
                  className="font-medium text-rose-600 hover:underline dark:text-rose-400"
                >
                  سحب الموافقة
                </button>
              ) : null}
            </span>
          ) : null}
        </div>

        {canWrite && consent && consentEdit === contact.id ? (
          <div className="mt-2 border-t border-slate-200 pt-2 dark:border-slate-700">
            <fieldset>
              <legend className="text-[10.5px] font-semibold text-slate-600 dark:text-slate-300">
                أنواع التذكير
              </legend>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                {consent.type_choices.map((choice) => {
                  const checked = consentDraft.types.includes(choice.value);
                  return (
                    <label
                      key={choice.value}
                      className="flex items-center gap-1 text-[10.5px] text-slate-600 dark:text-slate-300"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => setConsentDraft((prev) => ({
                          ...prev,
                          types: checked
                            ? prev.types.filter((value) => value !== choice.value)
                            : [...prev.types, choice.value],
                        }))}
                        className="size-3.5 rounded border-slate-300"
                      />
                      {choice.label}
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <label className="text-[10.5px] font-semibold text-slate-600 dark:text-slate-300">
                طريقة الإذن
                <select
                  value={consentDraft.channel}
                  onChange={(event) =>
                    setConsentDraft((prev) => ({ ...prev, channel: event.target.value }))
                  }
                  className={`${officeInputClass} mt-1 block h-8`}
                >
                  <option value="">— بلا تحديد —</option>
                  {consent.channel_choices.map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={consentDraft.types.length === 0}
                onClick={() => saveConsent(contact.id)}
                className={officePrimaryButtonClass}
              >
                احفظ الموافقة
              </button>
              <button
                type="button"
                onClick={() => setConsentEdit(null)}
                className={officeSecondaryButtonClass}
              >
                إلغاء
              </button>
            </div>
            {consentDraft.types.length === 0 ? (
              <p className="mt-1 text-[10px] font-medium text-amber-700 dark:text-amber-400">
                اختر نوعاً واحداً على الأقل — إذنٌ بلا نوعٍ لا يُرسَل له شيء.
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    );
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
          <div className="flex flex-wrap items-center gap-2">
            {/* #283/ب: كشفُ الحساب من رأس الملفّ — منتقيُ فترةٍ ثم طباعةٌ أو مشاركة. */}
            <OfficeClientStatementButton clientId={clientId} canWrite={canWrite} />
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
        </div>
      </header>
      <div className="border-b border-slate-200 dark:border-slate-700">
        <div className="-mb-px flex gap-1 overflow-x-auto">
          {TABS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              onClick={() => selectTab(entry.key)}
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
                عدد العاملين
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

      {tab === 'obligations' ? (
        <div className="space-y-4">
          {/* #277: «صار حدث» — خبرٌ يولّد التزامَه، وقائمتُه لا تُمحى. */}
          <OfficeClientEvents
            clientId={clientId}
            canWrite={canWrite}
            onRecorded={reloadObligations}
            onError={(message) => toast(message, 'error')}
          />
          {obligationsError ? (
            <OfficeError
              message={obligationsError}
              onRetry={reloadObligations}
            />
          ) : obligationsLoading ? (
            <OfficeSkeleton rows={4} />
          ) : !obligations || obligations.tasks.length === 0 ? (
            <OfficeEmpty
              title="لا شغلات بعد"
              hint="تُولَّد الشغلات من خدمات الزبون ولائحة المواعيد حين تنتهي فترتُها — تُحدَّث صباح كل يوم."
            />
          ) : (
            <>
              {canWrite ? (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11.5px] text-slate-500 dark:text-slate-400">
                    الشغلاتُ من الأحدث فترةً، وكلُّ التزاماتها في كلّ الحالات.
                  </p>
                  <button
                    type="button"
                    disabled={closingPrior}
                    onClick={closePrior}
                    className={officeSecondaryButtonClass}
                  >
                    هدول انقدّموا قبل ما يجي علينا
                  </button>
                </div>
              ) : null}

              {obligations.tasks.map((task) => (
                <div
                  key={task.id}
                  id={officeTaskAnchorId(task.id)}
                  className={
                    targetTaskId === task.id
                      ? 'rounded-xl ring-2 ring-amber-400 dark:ring-amber-500'
                      : undefined
                  }
                >
                  <OfficeCard>
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2 dark:border-slate-800">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12.5px] font-bold text-slate-900 dark:text-slate-100">
                          {task.period_label}
                        </span>
                        <span className="text-[10.5px] font-medium text-slate-500 dark:text-slate-400">
                          {task.service.name}
                        </span>
                        <span className="text-[10.5px] tabular-nums text-slate-500 dark:text-slate-400">
                          داخلي {shortIsoDate(task.internal_deadline)}
                        </span>
                      </div>
                      {canAssign && showsResponsible ? (
                        <label className="flex items-center gap-2 text-[11px] font-medium text-slate-600 dark:text-slate-300">
                          المسؤول
                          <select
                            value={task.assignee ? String(task.assignee.id) : ''}
                            disabled={assigningTask === task.id}
                            onChange={(event) =>
                              changeTaskAssignee(task.id, event.target.value)
                            }
                            className={`${officeInputClass} h-8`}
                          >
                            <option value="">مسؤول الزبون</option>
                            {members.map((member) => (
                              <option key={member.user_id} value={member.user_id}>
                                {member.full_name || member.username}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : task.assignee ? (
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">
                          {task.assignee.name}
                        </span>
                      ) : null}
                    </div>

                    <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
                      {task.obligations.map((obligation) => (
                        <li key={obligation.id} className="py-2">
                          <OfficeObligationRow
                            obligation={obligation}
                            day={obligations.day}
                            directionChoices={obligations.direction_choices}
                            canWrite={canWrite}
                            canSeeAmounts={canSeeAmounts}
                            onChanged={reloadObligations}
                            onError={(message) => toast(message, 'error')}
                            showStatus
                            dates="official-actual"
                          />
                        </li>
                      ))}
                    </ul>
                  </OfficeCard>
                </div>
              ))}
            </>
          )}
        </div>
      ) : null}

      {tab === 'services' ? (
        <div className="space-y-4">
          <OfficeCard
            title="خدمات الزبون"
            actions={
              canWrite ? (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={openAddService}
                    className={officeSecondaryButtonClass}
                  >
                    أضف خدمة
                  </button>
                  {packages.length > 0 ? (
                    <>
                      <select
                        value={packageChoice}
                        onChange={(event) => setPackageChoice(event.target.value)}
                        aria-label="باقة جاهزة"
                        className={`${officeInputClass} h-8`}
                      >
                        <option value="">— باقة جاهزة —</option>
                        {packages.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={!packageChoice}
                        onClick={applyPackage}
                        className={officeSecondaryButtonClass}
                      >
                        طبّق باقة
                      </button>
                    </>
                  ) : null}
                </div>
              ) : undefined
            }
          >
            {servicesError ? (
              <div className="flex flex-wrap items-center gap-2">
                <p role="alert" className="text-[12px] font-medium text-rose-700 dark:text-rose-300">
                  {servicesError}
                </p>
                <button
                  type="button"
                  onClick={() => refreshClientServices()}
                  className={officeSecondaryButtonClass}
                >
                  أعد المحاولة
                </button>
              </div>
            ) : clientServices === null ? (
              <p className="text-[12px] text-slate-500 dark:text-slate-400">
                جارٍ التحميل…
              </p>
            ) : clientServices.services.length === 0 ? (
              <OfficeEmpty
                title="لا خدمةَ لهذا الزبون بعد"
                hint="أضِف خدمةً من الكتالوج، أو طبّق باقةً جاهزة ثم عدّلها."
              />
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {clientServices.services.map((row) => (
                  <li key={row.id} className="py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                        {row.service.name}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${clientServiceStatusClass(row.status)}`}
                      >
                        {row.status_label}
                      </span>
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">
                        من {formatDateValue(row.starts_on)}
                        {row.ends_on
                          ? ` إلى ${formatDateValue(row.ends_on)}`
                          : ' — حتى الآن'}
                      </span>
                      {row.ends_on && !row.last_period_ours ? (
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">
                          آخر فترة مش علينا
                        </span>
                      ) : null}
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">
                        المكتب مسؤول من {formatDateValue(row.responsible_from)}
                      </span>
                      {row.frequency ? (
                        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10.5px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {row.frequency_label} من {formatDateValue(row.frequency_from)}
                        </span>
                      ) : null}
                      {canWrite && row.is_active ? (
                        <div className="ms-auto flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => startFrequencyChange(row)}
                            className="text-[10.5px] font-medium text-teal-700 hover:underline dark:text-teal-400"
                          >
                            غيّر الدورية من…
                          </button>
                          {/* صفٌّ له `ends_on` (ولو مستقبليّ) موقوفٌ مُسبقاً: لا إيقافَ ثانٍ. */}
                          {row.ends_on ? null : (
                            <button
                              type="button"
                              onClick={() => startStop(row.id)}
                              className="text-[10.5px] font-medium text-rose-600 hover:underline dark:text-rose-400"
                            >
                              أوقف بتاريخ…
                            </button>
                          )}
                        </div>
                      ) : null}
                    </div>

                    {row.frequencies.length > 1 ? (
                      <details className="mt-1.5">
                        <summary className="cursor-pointer text-[10.5px] text-slate-500 dark:text-slate-400">
                          تاريخ الدوريات ({row.frequencies.length})
                        </summary>
                        <ul className="mt-1 space-y-0.5">
                          {row.frequencies.map((entry) => (
                            <li
                              key={entry.id}
                              className="text-[10.5px] text-slate-500 dark:text-slate-400"
                            >
                              من {formatDateValue(entry.effective_from)} — {entry.frequency_label}
                              {entry.suggested && entry.suggested !== entry.frequency
                                ? ` (المقترح وقتها: ${frequencyLabelFrom(
                                    clientServices.frequency_choices,
                                    entry.suggested,
                                  )})`
                                : ''}
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : null}

                    {editingFrequency === row.id ? (
                      <div className="mt-2 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-800/40">
                        <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                          الدورية الجديدة
                          <select
                            value={frequencyDraft.frequency}
                            onChange={(event) =>
                              setFrequencyDraft({
                                ...frequencyDraft, frequency: event.target.value,
                              })
                            }
                            className={`${officeInputClass} mt-1 block`}
                          >
                            <option value="">— اختر —</option>
                            {clientServices.frequency_choices.map((choice) => (
                              <option key={choice.value} value={choice.value}>
                                {choice.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                          سارية من
                          <input
                            type="date"
                            value={frequencyDraft.effective_from}
                            onChange={(event) =>
                              setFrequencyDraft({
                                ...frequencyDraft, effective_from: event.target.value,
                              })
                            }
                            className={`${officeInputClass} mt-1 block tabular-nums`}
                          />
                        </label>
                        <button
                          type="button"
                          onClick={() => submitFrequencyChange(row.id)}
                          className={officePrimaryButtonClass}
                        >
                          احفظ
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingFrequency(null)}
                          className={officeSecondaryButtonClass}
                        >
                          إلغاء
                        </button>
                        <p className="w-full text-[10.5px] text-slate-500 dark:text-slate-400">
                          ما قبل هذا التاريخ يبقى بدوريته — التغييرُ يسري من تاريخٍ ولقدّام.
                        </p>
                      </div>
                    ) : null}

                    {stopping === row.id ? (
                      <div className="mt-2 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-800/40">
                        <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                          أوقف بتاريخ
                          <input
                            type="date"
                            value={stopDate}
                            onChange={(event) => setStopDate(event.target.value)}
                            className={`${officeInputClass} mt-1 block tabular-nums`}
                          />
                        </label>
                        <label className="inline-flex items-center gap-2 pb-2 text-[11.5px] text-slate-700 dark:text-slate-200">
                          <input
                            type="checkbox"
                            checked={stopLastPeriodOurs}
                            onChange={(event) => setStopLastPeriodOurs(event.target.checked)}
                            className="size-4 rounded border-slate-300"
                          />
                          آخر فترة علينا
                        </label>
                        <button
                          type="button"
                          onClick={() => submitStop(row)}
                          className="rounded-lg border border-rose-200 bg-white px-3 py-2 text-[12px] font-medium text-rose-700 dark:border-rose-900 dark:bg-slate-900 dark:text-rose-300"
                        >
                          أوقف الخدمة
                        </button>
                        <button
                          type="button"
                          onClick={() => setStopping(null)}
                          className={officeSecondaryButtonClass}
                        >
                          إلغاء
                        </button>
                        <p className="w-full text-[10.5px] text-slate-500 dark:text-slate-400">
                          شيل العلامة إذا آخر فترة قبل الإيقاف مش على المكتب — {LAST_PERIOD_NOT_OURS_EFFECT}
                        </p>
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </OfficeCard>

          {canWrite && addDraft ? (
            <OfficeCard title="أضف خدمة">
              <form onSubmit={submitAddService} className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    الخدمة
                    <select
                      value={addDraft.service}
                      onChange={(event) => {
                        const value = event.target.value;
                        // خدمةٌ أخرى ⇒ مقترحٌ آخر، فيعود اختيارُ الموظف لمقترحها.
                        setAddDraft({ ...addDraft, service: value, frequencyTouched: false });
                        loadSuggestion(value, addDraft.starts_on);
                      }}
                      required
                      className={`${officeInputClass} mt-1 block w-full`}
                    >
                      <option value="">— اختر خدمة —</option>
                      {availableServicesForClient(catalog, clientServices?.services ?? []).map(
                        (row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    تبدأ في
                    <input
                      type="date"
                      value={addDraft.starts_on}
                      onChange={(event) => {
                        const value = event.target.value;
                        setAddDraft({ ...addDraft, starts_on: value });
                        if (addDraft.service) loadSuggestion(addDraft.service, value);
                      }}
                      className={`${officeInputClass} mt-1 block w-full tabular-nums`}
                    />
                  </label>
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    من أيّ فترةٍ المكتب مسؤول؟
                    <input
                      type="month"
                      value={addDraft.responsible_from}
                      onChange={(event) =>
                        setAddDraft({ ...addDraft, responsible_from: event.target.value })
                      }
                      className={`${officeInputClass} mt-1 block w-full tabular-nums`}
                    />
                  </label>
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    الدورية
                    <select
                      value={addDraft.frequency}
                      onChange={(event) =>
                        setAddDraft({
                          ...addDraft, frequency: event.target.value, frequencyTouched: true,
                        })
                      }
                      className={`${officeInputClass} mt-1 block w-full`}
                    >
                      <option value="">— اختر —</option>
                      {(suggestion?.frequency_choices
                        ?? clientServices?.frequency_choices
                        ?? []
                      ).map((choice) => (
                        <option key={choice.value} value={choice.value}>
                          {choice.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {suggesting ? (
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    جارٍ اقتراح الدورية…
                  </p>
                ) : suggestion ? (
                  <p className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-[11.5px] text-teal-900 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-200">
                    {suggestion.frequency
                      ? `المقترح: ${suggestion.frequency_label} — ${suggestion.reason}`
                      : `لا اقتراحَ تلقائياً — ${suggestion.reason}. اختر الدورية بنفسك.`}
                  </p>
                ) : null}

                <div className="flex items-center gap-2">
                  <button type="submit" className={officePrimaryButtonClass}>
                    أضف الخدمة
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAddDraft(null);
                      setSuggestion(null);
                    }}
                    className={officeSecondaryButtonClass}
                  >
                    إلغاء
                  </button>
                </div>
              </form>
            </OfficeCard>
          ) : null}
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
                    {/* #280/ب: موافقةُ التذكير على الجهة — تحت بياناتها مباشرةً. */}
                    {renderConsent(link.contact)}
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

      {tab === 'documents' ? (
        // #278: كلُّ شيءٍ في المكوّن — الشبكةُ والملفات والتخصيص، والملفُّ يرسمه.
        <OfficeClientDocuments
          clientId={clientId}
          canWrite={canWrite}
          taxSystem={client.tax_system}
        />
      ) : null}

      {tab === 'reminder-log' ? (
        <div className="space-y-4">
          {reminderLogError ? (
            <OfficeError message={reminderLogError} onRetry={reloadReminderLog} />
          ) : reminderLogLoading ? (
            <OfficeSkeleton rows={4} />
          ) : !reminderLog || reminderLog.rows.length === 0 ? (
            <OfficeEmpty
              title="ما في تذكيرات مسجّلة لهذا الزبون."
              hint="كلُّ إرسالٍ أو مكالمةٍ تُسجَّل هنا — ولا تُمحى: التصحيحُ صفٌّ جديد."
            />
          ) : (
            <OfficeCard title="سجلّ التذكيرات">
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                الأحدثُ أوّلاً. السجلُّ لا يُمحى: «ما انبعتت» يكتب صفاً جديداً ويُخرج
                الأصلَ من العدّ.
              </p>
              <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
                {reminderLog.rows.map((row) => {
                  const reverted = revertedLogIds.has(row.id);
                  return (
                    <li key={row.id} className="py-2.5">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-[10.5px] tabular-nums text-slate-500 dark:text-slate-400">
                          {formatDateTimeValue(row.created_at)}
                        </span>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${reminderLogKindClass(row.kind)}`}
                        >
                          {row.kind_label}
                        </span>
                        {reverted ? (
                          <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500 line-through dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                            أُلغي
                          </span>
                        ) : null}
                        <span className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                          {row.reminder_type_label}
                        </span>
                        {row.channel_label ? (
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            {row.channel_label}
                          </span>
                        ) : null}
                      </div>

                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500 dark:text-slate-400">
                        <span>
                          {row.recipient_name || '— بلا مستلِم —'}
                          {row.recipient_phone ? ` · ${row.recipient_phone}` : ''}
                        </span>
                        {row.period_label ? <span>{row.period_label}</span> : null}
                        {/* #280/ب: «وما يخصّه» — لقطةُ أسماء بنود الأوراق وقت
                            الإرسال كما حفظها الخادم. صفّا «شيل» و«ما انبعتت»
                            بلا نصّ، فهما المرجعُ الوحيد لبنود الزبون حينها. */}
                        {row.subject.document_item_names?.length ? (
                          <span>{row.subject.document_item_names.join('، ')}</span>
                        ) : null}
                        {row.created_by ? <span>{row.created_by.name}</span> : null}
                      </div>

                      {row.reason ? (
                        <p className="mt-1 text-[11px] text-slate-600 dark:text-slate-300">
                          السبب: {row.reason}
                        </p>
                      ) : null}

                      {row.body ? (
                        <details className="mt-1">
                          <summary className="cursor-pointer text-[10.5px] text-slate-500 dark:text-slate-400">
                            النصّ كما أُرسل
                          </summary>
                          <p className="mt-1 whitespace-pre-line rounded-lg border border-slate-100 bg-slate-50 p-2 text-[11.5px] leading-6 text-slate-700 dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-200">
                            {row.body}
                          </p>
                        </details>
                      ) : null}

                      {canWrite && canUndoReminderRow(row, revertedLogIds) ? (
                        <button
                          type="button"
                          onClick={() => undoLogRow(row)}
                          className="mt-1 text-[10.5px] font-medium text-rose-600 hover:underline dark:text-rose-400"
                        >
                          ما انبعتت
                        </button>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </OfficeCard>
          )}
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

      {/* #281: المواعيدُ — حجزٌ وتأكيدٌ وتأجيلٌ وإلغاء (قبل «الدفتر» في
          `CLIENT_TAB_KEYS`، وتبويبُها بالترتيب نفسه في `TABS`). */}
      {tab === 'appointments' ? (
        <OfficeClientAppointments
          clientId={clientId}
          canWrite={canWrite}
          taxSystem={client.tax_system}
        />
      ) : null}

      {tab === 'fees' ? (
        // #283/ب: دفعاتُ الزبون بإشعارِ قبضٍ لكلٍّ — والطباعةُ والرابطُ من الخادم.
        <OfficeClientFees clientId={clientId} canWrite={canWrite} />
      ) : null}

      {tab === 'account' ? (
        // #282/أ٢/٢: «الحساب» — نداءٌ واحدٌ يُعيد «اللي عليه» وفواتيره من
        // `payments.client_due`، ورقمُ الملفّ من رأس الملفّ المحمَّل أصلاً.
        <OfficeClientAccount clientId={clientId} taxFileNumber={client.tax_file_number} />
      ) : null}

      {tab === 'book' ? (
        // #286/ب: الحركاتُ والإدخال والعكس. الكتابةُ بشرطين لا يُدمجان: مفتاحُ
        // الزبائن، ونشاطُ خدمة مسك الدفاتر (`writable` — والخادم يردّ 400).
        <OfficeClientBook
          clientId={clientId}
          canWrite={canWrite}
          canSeeAmounts={canSeeAmounts}
          month={bookMonthFromSearch(`?${searchParams.toString()}`)}
        />
      ) : null}
    </div>
  );
};
