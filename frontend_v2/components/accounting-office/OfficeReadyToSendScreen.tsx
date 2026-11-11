import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  dismissReminders,
  getOfficeSettings,
  getReadyToSend,
  listOfficeMembers,
  markRemindersManual,
  markRemindersSent,
  postponeReminder,
  type OfficeMemberRow,
  type OfficeSettingsPayload,
  type ReadyToSendMessage,
  type ReadyToSendPayload,
} from '../../services/accountingOfficeApi';
import {
  commonTaxSystem,
  filterReadyToSendMessages,
  nextDayIso,
  obligationBadgeClass,
  officeSizeOf,
  officeWhatsappLink,
  readyToSendItemKeys,
  readyToSendMessageKey,
  readyToSendTypeChips,
  showsOfficeAssignment,
} from '../../utils/accountingOffice';
import { formatDateLocalized, todayIso } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/** أسماءُ زبائن الرسالة بلا تكرار — رسالةُ شخصٍ قد تحمل بنودَ زبونين. */
function clientNamesOf(message: ReadyToSendMessage): string {
  const names: string[] = [];
  message.items.forEach((item) => {
    if (!names.includes(item.client_name)) names.push(item.client_name);
  });
  return names.join(' · ');
}

/** فتراتُ بنود الرسالة بلا تكرار — نصُّ الخادم كما وصل. */
function periodLabelsOf(message: ReadyToSendMessage): string {
  const labels: string[] = [];
  message.items.forEach((item) => {
    if (item.period_label && !labels.includes(item.period_label)) {
      labels.push(item.period_label);
    }
  });
  return labels.join(' · ');
}

/** أزواج (زبون × نوع) في رسالة — «أجّل» وحدةُ تأجيلها الزوجُ لا الرسالة. */
function postponePairsOf(
  message: ReadyToSendMessage,
): { client_id: number; reminder_type: string }[] {
  const seen = new Set<string>();
  const pairs: { client_id: number; reminder_type: string }[] = [];
  message.items.forEach((item) => {
    const key = `${item.client_id}|${item.reminder_type}`;
    if (seen.has(key)) return;
    seen.add(key);
    pairs.push({ client_id: item.client_id, reminder_type: item.reminder_type });
  });
  return pairs;
}

/** إسقاطُ مسوّدة رسالةٍ بمفتاحها — تكرارُ الكتلة في مكانين يفترق يوماً. */
function withoutDraft(
  drafts: Record<string, string>,
  key: string,
): Record<string, string> {
  const next = { ...drafts };
  delete next[key];
  return next;
}

/**
 * ISSUE #280/ب — «جاهز للإرسال»: رسالةٌ واحدةٌ لكل **شخصٍ** في اليوم، فيها كلُّ
 * ما يخصّه بلغته، وأفعالُها الأربعة.
 *
 * **الخادمُ هو الحكم**: القائمةُ تُحسب عند القراءة (الحالة والتاريخ والإيقاع
 * والحواجز)، فما ظهر هنا حان وقتُه فعلاً. وكلُّ فعلٍ ناجحٍ يُعيد قراءتها، فلا
 * حالةَ موازية له في الشاشة. والتعديلُ المحلّيُّ على النصّ هو ما يُرسَل ويُسجَّل
 * (`body`)، فلا يُسجَّل نصٌّ غيرُ الذي خرج.
 *
 * **والرقمُ يُصاغ للواتساب في `officeWhatsappLink` وحدها**: مفتاحُ الدولة يُقرأ
 * من نظام الزبون، وكلُّ بندٍ يحمل نظامَ **زبونه** (`tax_system`). ورسالةُ شخصٍ
 * واحدٍ قد تجمع زبونين بنظامين مختلفين، فتمرّر الشاشةُ نظامَها المشترك وحده
 * (`commonTaxSystem`) — وحين تختلف أو تغيب يُمرَّر `null`: الجوالُ الفلسطينيّ/
 * الإسرائيليّ والدوليُّ يُصاغون بلا مفتاح دولة، والأرضيُّ وحده يعود `null`
 * فيُقفل الزرُّ بنصّه («رقم غير صالح للواتساب») ولا يُخمَّن مفتاحُ بلد.
 *
 * **والنصُّ الفارغُ رسالةٌ لا زرّ**: زرُّ الواتساب و«نعم» يُقفلان على نصٍّ فارغ،
 * فلا يُفتح `wa.me?text=` فارغٌ ولا يُسجَّل في سجلٍّ لا يُمحى إرسالٌ بلا نص.
 *
 * **والكتابةُ بمفتاحها خادمياً** (`office.clients.write`): من لا يملكه يرى
 * النصَّ ويفتح الواتساب ولا يسجّل شيئاً — والتسجيلُ ثلاثةُ أفعالٍ تُخفى عنه.
 */
export const OfficeReadyToSendScreen: React.FC = () => {
  const toast = useToast();
  const { can } = usePermissions();
  const canWrite = can('office.clients.write');
  const [payload, setPayload] = useState<ReadyToSendPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);
  const [typeFilter, setTypeFilter] = useState('');
  const [assignee, setAssignee] = useState<number | null>(null);
  const [settings, setSettings] = useState<OfficeSettingsPayload | null>(null);
  const [members, setMembers] = useState<OfficeMemberRow[]>([]);
  // مسوّدةُ النصّ لكل رسالة بمفتاحها المشتقّ من محتواها — لا بفهرسها.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [askedKey, setAskedKey] = useState<string | null>(null);
  const [postponeKey, setPostponeKey] = useState<string | null>(null);
  const [postponeDate, setPostponeDate] = useState('');
  const [dismissKey, setDismissKey] = useState<string | null>(null);
  const [dismissReason, setDismissReason] = useState('');
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const officeSize = settings ? officeSizeOf(settings.settings) : null;
  // فلترُ الموظف لمن **يرى زبائن غيره** وفقط: «شخص واحد» لا موظفَ سواه،
  // وبلا `office.clients.all` يرى زبائنه وحدهم فالفلترُ يُضيّق بلا معنى.
  const showsAssigneeFilter = showsOfficeAssignment(officeSize) && can('office.clients.all');
  const day = payload?.day ?? todayIso();
  const messages = payload?.messages ?? [];
  const chips = useMemo(() => readyToSendTypeChips(messages), [messages]);
  const shown = useMemo(
    () => filterReadyToSendMessages(messages, typeFilter),
    [messages, typeFilter],
  );

  /**
   * رقاقةُ نوعٍ اختفت بعد فعلٍ (آخرُ رسالةٍ منه أُرسلت) ⇒ يعود الفلترُ «الكل».
   * بلا هذا يبقى الفلترُ على نوعٍ لا رسائلَ له فتبدو القائمةُ فارغةً وهي ليست.
   */
  useEffect(() => {
    if (!typeFilter) return;
    if (chips.some((chip) => chip.value === typeFilter)) return;
    setTypeFilter('');
  }, [chips, typeFilter]);

  useEffect(() => {
    let cancelled = false;
    getOfficeSettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!showsAssigneeFilter) return;
    let cancelled = false;
    listOfficeMembers()
      .then((rows) => {
        if (!cancelled) setMembers(rows);
      })
      .catch((failure) => {
        if (!cancelled) {
          toast(humanizeThrown(failure, 'تعذّر تحميل موظفي المكتب.'), 'error');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showsAssigneeFilter, toast]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getReadyToSend(assignee === null ? {} : { assignee })
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((failure) => {
        if (!cancelled) {
          // لا تُعرض رسائلُ طلبٍ سابق مع رسالة الفشل.
          setPayload(null);
          setError(humanizeThrown(failure, 'تعذّر تحميل الرسائل الجاهزة.'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [assignee, refreshToken]);

  const reload = useCallback(() => setRefreshToken((token) => token + 1), []);

  /** نصُّ الرسالة المعروض — المسوّدةُ إن عُدّل، وإلا نصُّ الخادم. */
  const bodyOf = (message: ReadyToSendMessage): string => {
    const key = readyToSendMessageKey(message);
    return drafts[key] ?? message.body;
  };

  const closePanels = (key: string) => {
    setEditingKey((current) => (current === key ? null : current));
    setAskedKey((current) => (current === key ? null : current));
    setPostponeKey((current) => (current === key ? null : current));
    setDismissKey((current) => (current === key ? null : current));
  };

  /** كلُّ فعلٍ ناجح: يُغلق لوحَه، يُسقط مسوّدتَه، ويُعيد قراءة القائمة. */
  const act = async (key: string, run: () => Promise<unknown>, done: string) => {
    setBusyKey(key);
    try {
      await run();
      closePanels(key);
      setDrafts((prev) => withoutDraft(prev, key));
      toast(done, 'success');
      reload();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تنفيذ الفعل.'), 'error');
    } finally {
      setBusyKey(null);
    }
  };

  const startEdit = (message: ReadyToSendMessage) => {
    const key = readyToSendMessageKey(message);
    if (editingKey === key) {
      setEditingKey(null);
      // «إلغاء التعديل» يُسقط المسوّدةَ ويعيد نصَّ الخادم — لا يُبقيها مخفيّةً.
      setDrafts((prev) => withoutDraft(prev, key));
      return;
    }
    setDrafts((prev) => ({ ...prev, [key]: prev[key] ?? message.body }));
    setEditingKey(key);
  };

  /**
   * «ابعت على واتساب»: يفتح المحادثةَ بالنصّ الحالي في تبويبٍ جديد، ثم يسأل
   * «انبعتت؟» — والسؤالُ لا يظهر لمن لا يملك تسجيلَ الجواب. والرابطُ يُبنى مرّةً
   * في البطاقة (للقفل والفتح معاً) فلا حسابان يفترقان.
   */
  const openWhatsapp = (message: ReadyToSendMessage, link: string | null) => {
    if (!link) return;
    window.open(link, '_blank', 'noopener');
    if (canWrite) setAskedKey(readyToSendMessageKey(message));
  };

  const startPostpone = (message: ReadyToSendMessage) => {
    const key = readyToSendMessageKey(message);
    if (postponeKey === key) {
      setPostponeKey(null);
      return;
    }
    setPostponeDate(nextDayIso(day));
    setDismissKey(null);
    setPostponeKey(key);
  };

  const startDismiss = (message: ReadyToSendMessage) => {
    const key = readyToSendMessageKey(message);
    if (dismissKey === key) {
      setDismissKey(null);
      return;
    }
    setDismissReason('');
    setPostponeKey(null);
    setDismissKey(key);
  };

  const renderCard = (message: ReadyToSendMessage) => {
    const key = readyToSendMessageKey(message);
    // النصُّ المعروض هو ما سيُرسل ويُسجَّل — والرابطُ يبنى منه مرّةً للقفل والفتح.
    const body = bodyOf(message);
    const empty = !body.trim();
    const link = officeWhatsappLink(
      message.recipient.phone,
      commonTaxSystem(message.items),
      body,
    );
    const busy = busyKey === key;
    const editing = editingKey === key;
    const clientNames = clientNamesOf(message);
    const periodLabels = periodLabelsOf(message);
    return (
      <article
        key={key}
        className="rounded-xl border border-slate-200 bg-white p-3.5 dark:border-slate-700 dark:bg-slate-900"
      >
        <header className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-[13.5px] font-semibold text-slate-900 dark:text-slate-100">
              {message.recipient.name}
            </h2>
            <p className="mt-0.5 text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
              {message.recipient.phone || 'بلا رقم'}
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {message.recipient.language_label}
          </span>
        </header>

        {clientNames ? (
          <p className="mt-1.5 text-[11.5px] text-slate-600 dark:text-slate-300">{clientNames}</p>
        ) : null}

        {/* الشاراتُ من البند نفسه: تسميةُ النوع ونصُّ الفترة من الخادم، واللونُ من
            مفتاح الشارة (`badge`) كما في «اليوم» — لا جدولَ ألوانٍ ثانٍ. */}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {message.items.map((item) => (
            <span
              key={`${item.client_id}|${item.reminder_type}|${item.period_start}|${item.period_end}`}
              className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${obligationBadgeClass(item.badge)}`}
            >
              {item.reminder_type_label}
            </span>
          ))}
        </div>
        {periodLabels ? (
          <p className="mt-1 text-[10.5px] text-slate-500 dark:text-slate-400">{periodLabels}</p>
        ) : null}

        <div className="mt-2.5 flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500">
            معاينة الرسالة
          </span>
          <button
            type="button"
            onClick={() => startEdit(message)}
            aria-expanded={editing}
            className="text-[10.5px] font-semibold text-teal-700 hover:underline dark:text-teal-400"
          >
            {editing ? 'إلغاء التعديل' : 'عدّل'}
          </button>
        </div>
        {editing ? (
          <textarea
            value={body}
            onChange={(event) => {
              const value = event.target.value;
              setDrafts((prev) => ({ ...prev, [key]: value }));
            }}
            rows={7}
            aria-label={`نصّ الرسالة إلى ${message.recipient.name}`}
            className="mt-1.5 w-full rounded-2xl border border-slate-200 bg-white p-3 text-[12px] leading-6 text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        ) : (
          <p className="mt-1.5 whitespace-pre-line rounded-2xl rounded-tr-sm border border-emerald-100 bg-emerald-50 p-3 text-[12px] leading-6 text-slate-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-slate-100">
            {body}
          </p>
        )}

        <button
          type="button"
          disabled={!link || empty || busy}
          onClick={() => openWhatsapp(message, link)}
          className={`mt-3 w-full ${officePrimaryButtonClass}`}
        >
          ابعت على واتساب
        </button>
        {empty ? (
          <p className="mt-1 text-[10.5px] font-medium text-amber-700 dark:text-amber-400">
            النصّ فارغ — اكتب الرسالة قبل الإرسال
          </p>
        ) : null}
        {link ? null : (
          <p className="mt-1 text-[10.5px] font-medium text-slate-500 dark:text-slate-400">
            رقم غير صالح للواتساب
          </p>
        )}

        {canWrite ? (
          <>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                disabled={busy}
                onClick={() => act(
                  key,
                  () => markRemindersManual({
                    contact_id: message.recipient.contact_id,
                    body,
                    channel: 'phone',
                    items: readyToSendItemKeys(message),
                  }),
                  'سُجّل أنه ذُكِّر بالتلفون',
                )}
                className={`flex-1 ${officeSecondaryButtonClass}`}
              >
                ذكّرته بالتلفون
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => act(
                  key,
                  () => markRemindersManual({
                    contact_id: message.recipient.contact_id,
                    body,
                    channel: 'in_person',
                    items: readyToSendItemKeys(message),
                  }),
                  'سُجّل أنه ذُكِّر بالزيارة',
                )}
                className={officeSecondaryButtonClass}
              >
                بالزيارة
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => startPostpone(message)}
                aria-expanded={postponeKey === key}
                className={officeSecondaryButtonClass}
              >
                أجّل
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => startDismiss(message)}
                aria-expanded={dismissKey === key}
                className={officeSecondaryButtonClass}
              >
                شيل
              </button>
            </div>

            {askedKey === key ? (
              <div
                role="status"
                className="mt-2 rounded-lg border border-teal-200 bg-teal-50 p-2 dark:border-teal-900 dark:bg-teal-950/40"
              >
                <p className="text-[11.5px] font-semibold text-teal-900 dark:text-teal-200">
                  انبعتت؟
                </p>
                <div className="mt-1.5 flex items-center gap-2">
                  <button
                    type="button"
                    disabled={busy || empty}
                    onClick={() => act(
                      key,
                      () => markRemindersSent({
                        contact_id: message.recipient.contact_id,
                        body,
                        items: readyToSendItemKeys(message),
                      }),
                      'سُجّل الإرسال في السجلّ',
                    )}
                    className={officePrimaryButtonClass}
                  >
                    نعم
                  </button>
                  <button
                    type="button"
                    onClick={() => setAskedKey(null)}
                    className={officeSecondaryButtonClass}
                  >
                    لا
                  </button>
                </div>
              </div>
            ) : null}

            {postponeKey === key ? (
              <div className="mt-2 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-800/40">
                <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                  أجّل إلى
                  <input
                    type="date"
                    value={postponeDate}
                    min={nextDayIso(day)}
                    onChange={(event) => setPostponeDate(event.target.value)}
                    className={`${officeInputClass} mt-1 block tabular-nums`}
                  />
                </label>
                <button
                  type="button"
                  disabled={busy || !postponeDate || postponeDate <= day}
                  onClick={() => act(
                    key,
                    () => Promise.all(
                      postponePairsOf(message).map((pair) => postponeReminder({
                        ...pair,
                        until: postponeDate,
                      })),
                    ),
                    'أُجّل التذكير',
                  )}
                  className={officePrimaryButtonClass}
                >
                  أجّل
                </button>
                <button
                  type="button"
                  onClick={() => setPostponeKey(null)}
                  className={officeSecondaryButtonClass}
                >
                  إلغاء
                </button>
              </div>
            ) : null}

            {dismissKey === key ? (
              <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-800/40">
                <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                  السبب (اختياري)
                  <input
                    value={dismissReason}
                    onChange={(event) => setDismissReason(event.target.value)}
                    // سقفُ الحقل في `ReadyToSendDismissSerializer` — تجاوزُه 400.
                    maxLength={300}
                    className={`${officeInputClass} mt-1 block w-full`}
                  />
                </label>
                <div className="mt-2 flex items-center gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => act(
                      key,
                      () => dismissReminders({
                        items: readyToSendItemKeys(message),
                        reason: dismissReason.trim() || undefined,
                      }),
                      'أُزيل لهذه المرة',
                    )}
                    className={officePrimaryButtonClass}
                  >
                    شيل لهذه المرة
                  </button>
                  <button
                    type="button"
                    onClick={() => setDismissKey(null)}
                    className={officeSecondaryButtonClass}
                  >
                    إلغاء
                  </button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </article>
    );
  };

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-4 md:p-5 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">
              جاهز للإرسال
            </h1>
            <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
              {payload?.day ? `${formatDateLocalized(payload.day)} — ` : ''}
              رسالة وحدة لكل شخص — بتنفتح على واتساب.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-teal-200 bg-teal-50 px-2.5 py-1 text-[11px] font-bold tabular-nums text-teal-700 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300">
              {messages.length} جاهزة
            </span>
            <button type="button" onClick={reload} className={officeSecondaryButtonClass}>
              حدّث
            </button>
          </div>
        </div>

        {/* الرقائقُ أفقيةٌ تتمرّر على الجوال كالنموذج: حوافُّ الحاوية تُعاكس
            حشوةَ الرأس كي يبلغ التمريرُ الحافّةَ ولا يُقصّ أوّلُ رقاقة. */}
        {chips.length > 0 ? (
          <div className="-mx-4 mt-3 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] md:-mx-5 md:px-5">
            {chips.map((chip) => (
              <button
                key={chip.value || 'all'}
                type="button"
                onClick={() => setTypeFilter(chip.value)}
                aria-pressed={typeFilter === chip.value}
                className={
                  typeFilter === chip.value
                    ? 'shrink-0 rounded-full bg-teal-700 px-3 py-1 text-[11.5px] font-semibold text-white'
                    : 'shrink-0 rounded-full border border-slate-200 px-3 py-1 text-[11.5px] font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300'
                }
              >
                {chip.label}
                <span className="ms-1 tabular-nums opacity-80">{chip.count}</span>
              </button>
            ))}
          </div>
        ) : null}

        {showsAssigneeFilter ? (
          <label className="mt-3 inline-flex items-center gap-2 text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الموظف
            <select
              value={assignee === null ? '' : String(assignee)}
              onChange={(event) => setAssignee(
                event.target.value === '' ? null : Number(event.target.value),
              )}
              className={`${officeInputClass} h-8`}
            >
              <option value="">كل الموظفين</option>
              {members.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.full_name || member.username}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </header>

      {error ? <OfficeError message={error} onRetry={reload} /> : null}

      {loading ? (
        <OfficeSkeleton rows={4} />
      ) : !error && shown.length === 0 ? (
        <OfficeEmpty
          title="ما في رسائل جاهزة اليوم."
          hint="تُحسب من الأوراق الناقصة وإيقاع التذكير — وتظهر أوّل يومٍ مسموح بعد يوم الراحة أو العطلة."
        />
      ) : (
        <div className="flex flex-col gap-2.5">{shown.map(renderCard)}</div>
      )}
    </div>
  );
};
