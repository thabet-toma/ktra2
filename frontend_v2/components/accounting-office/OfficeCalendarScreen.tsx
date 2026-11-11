import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  confirmAppointment,
  createAppointment,
  getOfficeCalendar,
  getOfficeSettings,
  listDeadlineRules,
  listOfficeClients,
  listOfficeMembers,
  type CalendarDeadlineRow,
  type DeadlineRuleRow,
  type OfficeClientRow,
  type OfficeMemberRow,
  type OfficeSettingsPayload,
} from '../../services/accountingOfficeApi';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  CLIENT_APPOINTMENTS_TAB,
  CLIENT_TAB_PARAM,
  appointmentConfirmationView,
  clientFilePath,
  groupAppointmentsByDay,
  groupDeadlinesByDay,
  isExpectedDeadline,
  isOpenAppointment,
  monthGrid,
  nextMonthKey,
  obligationOriginLabel,
  officeSizeOf,
  periodLabel,
  previousMonthKey,
  shiftWeek,
  showsOfficeAssignment,
  uniqueDeadlineRules,
  weekDays,
  weekRange,
  type CalendarDay,
  type OfficeAppointmentRow,
  type SettingChoice,
} from '../../utils/accountingOffice';
import { monthKeyLabel, monthKeyOf } from '../../utils/monthKey';
import { formatDateLocalized, todayIso, WEEKDAYS_AR } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { OfficeCard, OfficeEmpty, OfficeError, OfficeSkeleton, officeInputClass, officePrimaryButtonClass, officeSecondaryButtonClass } from './OfficeUi';

type CalendarMode = 'month' | 'week';

/** أسطرُ لائحة نظامٍ — فشلُ الطلب يُفرغ هذا النظامَ وحده ولا يُسقط الشاشة. */
const loadRules = (system: 'PS' | 'IL'): Promise<DeadlineRuleRow[]> =>
  listDeadlineRules(system)
    .then((result) => result.rules)
    .catch(() => []);

/**
 * ISSUE #274 — التقويم: مواعيدُ الزبائن المحسوبة من لائحة المنصّة.
 *
 * **لا يُحفظ شيء ولذلك لا زرّ حفظ**: كلُّ سطرٍ هنا محسوبٌ عند القراءة من
 * `calendar/`، فتصحيحُ سطرٍ في اللائحة يغيّر الشاشةَ في الطلب التالي بلا إعادة
 * توليد. و«المتوقَّع» وسمٌ ثابتٌ في هذه التذكرة (لا سطرَ محفوظاً بعد)، و«تقديري»
 * يعني سنةً بلا لائحةٍ منشورة — والتنبيه («الموعد يوم جمعة») نصُّ الخادم كما وصل.
 *
 * **والمدى يُطلب بعرض الشاشة وحده**: شهرٌ = شبكةُ الشهر (ثلاثةٌ إلى ستّة أسابيع)،
 * وأسبوعٌ = سبعةُ أيام — والطلبُ يُلغى بمجرّد تغيّر المدى أو الفلتر، فلا يصل ردُّ
 * عرضٍ سابقٍ فوق عرضٍ حاليّ.
 */
export const OfficeCalendarScreen: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();
  // الخادمُ هو الحكم: هذا العلم يُخفي زرَّ الحجز ولا يحمي — الكتابةُ 403 بلا مفتاحها.
  const { can } = usePermissions();
  const canBook = can('office.clients.write');
  const [mode, setMode] = useState<CalendarMode>('month');
  const [anchor, setAnchor] = useState<string>(todayIso);
  const [settings, setSettings] = useState<OfficeSettingsPayload | null>(null);
  const [clients, setClients] = useState<OfficeClientRow[]>([]);
  const [members, setMembers] = useState<OfficeMemberRow[]>([]);
  const [rules, setRules] = useState<DeadlineRuleRow[]>([]);
  const [clientFilter, setClientFilter] = useState('');
  const [memberFilter, setMemberFilter] = useState('');
  const [ruleFilter, setRuleFilter] = useState('');
  const [rows, setRows] = useState<CalendarDeadlineRow[]>([]);
  // #281: مواعيدُ المدى — تُرسم في اليوم نفسه مع التزاماته.
  const [appointmentRows, setAppointmentRows] = useState<OfficeAppointmentRow[]>([]);
  // #281: الحجزُ من التقويم — الزبونُ يختاره الموظّف، والصفحةُ تحمل أنواع المواعيد.
  const [kindChoices, setKindChoices] = useState<SettingChoice[]>([]);
  const [bookingOpen, setBookingOpen] = useState(false);
  const [bookClient, setBookClient] = useState('');
  const [bookKind, setBookKind] = useState('');
  const [bookSlot, setBookSlot] = useState('');
  const [bookNote, setBookNote] = useState('');
  const [bookBusy, setBookBusy] = useState(false);
  // #281: «ابعت تأكيد» من التقويم — الموعدُ المحجوز هنا يُؤكَّد من هنا، لا من
  // ملفّ الزبون وحده. والسطرُ العائد من الخادم يُستبدل في الحالة بلا إعادة تحميل.
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [confirmation, setConfirmation] = useState<{ body: string; link: string | null } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);

  const monthKey = monthKeyOf(anchor);
  const week = useMemo(() => weekRange(anchor), [anchor]);
  // المدى المعروض وحده — الشبكةُ تشمل أطراف الشهرين المجاورين فتُطلب أيضاً.
  const range = useMemo(() => {
    if (mode === 'week') return week;
    const grid = monthGrid(monthKey);
    if (!grid.length) return { start: `${monthKey}-01`, end: `${monthKey}-01` };
    const flat = grid.flat();
    return { start: flat[0].date, end: flat[flat.length - 1].date };
  }, [mode, monthKey, week]);

  /** مراجعُ الشاشة مرّةً واحدة: حجمُ المكتب والزبائن والموظفون وأسطرُ اللائحة. */
  useEffect(() => {
    let cancelled = false;
    getOfficeSettings()
      .then(async (payload) => {
        if (cancelled) return;
        setSettings(payload);
        const [clientRows, memberRows, palestinianRules, israeliRules] = await Promise.all([
          listOfficeClients({ status: 'active' }).catch(() => []),
          listOfficeMembers().catch(() => []),
          // أسطرُ النظامين معاً: المكتبُ قد يضمّ زبائن من الفلسطينيّ والإسرائيليّ،
          // وفشلُ أحدهما يُفرغ حصّتَه وحدها.
          loadRules('PS'),
          loadRules('IL'),
        ]);
        if (cancelled) return;
        setClients(clientRows);
        setMembers(memberRows);
        setRules([...palestinianRules, ...israeliRules]);
      })
      .catch((failure) => {
        if (!cancelled) setError(humanizeThrown(failure, 'تعذّر تحميل إعدادات المكتب.'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getOfficeCalendar({
      from: range.start,
      to: range.end,
      client: clientFilter ? Number(clientFilter) : null,
      member: memberFilter ? Number(memberFilter) : null,
      rule: ruleFilter || null,
    })
      .then((payload) => {
        if (!cancelled) {
          setRows(payload.rows);
          setAppointmentRows(payload.appointments ?? []);
          setKindChoices(payload.kind_choices ?? []);
          setBookKind((current) => current || payload.kind_choices?.[0]?.value || '');
        }
      })
      .catch((failure) => {
        if (!cancelled) {
          // لا تُعرَض صفوفُ طلبٍ سابق مع رسالة الفشل: الشاشةُ تقول «تعذّر» وتُخلي
          // الشبكة، فلا يُقرأ تقويمٌ قديم كأنه نتيجةُ الطلب الجديد.
          setRows([]);
          setError(humanizeThrown(failure, 'تعذّر تحميل التقويم.'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range.start, range.end, clientFilter, memberFilter, ruleFilter, refreshToken]);

  const retry = useCallback(() => setRefreshToken((token) => token + 1), []);

  /** حجزٌ من التقويم (#281): الزبونُ يختاره الموظّف — لا يحجز بنفسه. */
  const book = useCallback(async () => {
    if (!bookClient || !bookSlot) {
      toast('اختر الزبون ووقت الموعد.', 'error');
      return;
    }
    setBookBusy(true);
    try {
      await createAppointment({
        client_id: Number(bookClient),
        kind: bookKind,
        scheduled_at: bookSlot,
        note: bookNote.trim(),
      });
      setBookNote('');
      setBookingOpen(false);
      toast('انحجز الموعد.', 'success');
      retry();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حجز الموعد.'), 'error');
    } finally {
      setBookBusy(false);
    }
  }, [bookClient, bookKind, bookNote, bookSlot, retry, toast]);

  const toggleBooking = useCallback(() => {
    if (!bookingOpen) {
      // اليومُ المعروض أوّلاً في الحقل — لا حجزٌ في يومٍ لا يراه الموظف.
      setBookSlot(`${anchor}T09:00`);
    }
    setBookingOpen((open) => !open);
  }, [anchor, bookingOpen]);

  /**
   * «ابعت تأكيد» للتقويم (#281) — **الدالّةُ نفسها** التي يناديها ملفّ الزبون
   * (`confirmAppointment`)، فالمنطقُ في الخادم ونسخةٌ واحدة في الواجهة.
   *
   * والسطرُ العائد يحمل `confirmed_at` الجديد، فيُستبدل في الحالة فوراً: لا طلبَ
   * إعادة تحميلٍ للشبكة كلها. ورفضُ الخادم (زبونٌ بلا جهةٍ بهاتف) يصل نصُّه من
   * `humanizeThrown` فيُقرأ سببه لا «تعذّر» مبهمة.
   */
  const confirmSlot = useCallback(
    async (slot: OfficeAppointmentRow) => {
      setConfirmingId(slot.id);
      try {
        const result = await confirmAppointment(slot.id);
        setAppointmentRows((rows) =>
          rows.map((row) =>
            row.id === result.appointment.id ? result.appointment : row,
          ),
        );
        setConfirmation(appointmentConfirmationView(result));
        toast('تسجّل التأكيد — الرسالةُ جاهزة.', 'success');
      } catch (failure) {
        toast(
          humanizeThrown(failure, 'تعذّر تسجيل التأكيد — تحقّق من جهة الزبون ورقمها.'),
          'error',
        );
      } finally {
        setConfirmingId(null);
      }
    },
    [toast],
  );

  const goToday = useCallback(() => setAnchor(todayIso()), []);
  const shift = useCallback(
    (direction: -1 | 1) => {
      if (mode === 'week') {
        setAnchor(shiftWeek(anchor, direction));
        return;
      }
      setAnchor(
        direction === 1
          ? `${nextMonthKey(monthKey)}-01`
          : `${previousMonthKey(monthKey)}-01`,
      );
    },
    [anchor, mode, monthKey],
  );

  const byDay = useMemo(() => groupDeadlinesByDay(rows), [rows]);
  const appointmentsByDay = useMemo(
    () => groupAppointmentsByDay(appointmentRows), [appointmentRows],
  );
  // «النوع» بلا تكرارٍ بالكود: نفسُ السطر منشورٌ في 2026 و2027، فيُعرض مرّةً.
  const ruleOptions = useMemo(() => uniqueDeadlineRules(rules), [rules]);
  // يومُ الطلب يُقرأ مرّةً — لا قراءةَ ساعةٍ في كل خليّة.
  const today = useMemo(() => todayIso(), []);
  const officeSize = settings ? officeSizeOf(settings.settings) : null;
  const showsMemberFilter = showsOfficeAssignment(officeSize);
  const heading =
    mode === 'week'
      ? `${formatDateLocalized(week.start)} — ${formatDateLocalized(week.end)}`
      : monthKeyLabel(monthKey);

  const renderItem = (row: CalendarDeadlineRow) => {
    const expected = isExpectedDeadline(row);
    return (
      <button
        key={`${row.client.id}-${row.rule.code}-${row.period_start}`}
        type="button"
        onClick={() => navigate(clientFilePath(row.client.id))}
        className={`w-full rounded-lg border px-2 py-1.5 text-start text-[11px] transition ${
          expected
            ? 'border-slate-200 bg-slate-50 opacity-60 hover:opacity-100 dark:border-slate-700 dark:bg-slate-800/40'
            : 'border-teal-200 bg-teal-50 hover:border-teal-300 dark:border-teal-900 dark:bg-teal-950/40'
        }`}
      >
        <span className="block truncate font-semibold text-slate-800 dark:text-slate-100">
          {row.client.name}
        </span>
        <span className="block truncate text-slate-600 dark:text-slate-300">{row.rule.name}</span>
        <span className="mt-0.5 flex flex-wrap items-center gap-1">
          <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            {row.period_label || periodLabel(row.period_start, row.period_end)}
          </span>
          {expected ? (
            <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700 dark:bg-slate-700 dark:text-slate-200">
              متوقَّع
            </span>
          ) : null}
          {row.estimated ? (
            <span
              title="سنة بلا لائحةٍ منشورة — الموعد مقيسٌ على آخر لائحة"
              className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900 dark:bg-amber-950/50 dark:text-amber-200"
            >
              تقديري
            </span>
          ) : null}
          {/* #277: شارةُ الأصل — «من المكتب» و«حدث» وحدَهما، والرسميُّ بلا شارة. */}
          {obligationOriginLabel(row) ? (
            <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              {obligationOriginLabel(row)}
            </span>
          ) : null}
          {row.rule.needs_review ? (
            <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800 dark:bg-rose-950/50 dark:text-rose-200">
              راجع
            </span>
          ) : null}
        </span>
        {row.warnings.map((warning) => (
          <span
            key={warning}
            className="mt-1 block text-[10.5px] font-medium text-amber-800 dark:text-amber-300"
          >
            ⚠ {warning}
          </span>
        ))}
      </button>
    );
  };

  const renderDay = (day: CalendarDay, compact: boolean) => {
    const items = byDay[day.date] ?? [];
    // #281: مواعيدُ اليوم نفسه — قبل الالتزامات لأنه ما حُجز بوقته لا ما يجب عمله.
    const slots = appointmentsByDay[day.date] ?? [];
    const isToday = day.date === today;
    return (
      <div
        key={day.date}
        className={`min-h-[92px] space-y-1 border-slate-100 p-1.5 dark:border-slate-800 ${
          day.inMonth ? '' : 'bg-slate-50/60 opacity-70 dark:bg-slate-800/30'
        } ${isToday ? 'ring-1 ring-inset ring-teal-400' : ''}`}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] font-semibold tabular-nums text-slate-500 dark:text-slate-400">
            {day.date.slice(8)}
          </span>
          {!compact && items.length + slots.length ? (
            <span className="text-[10px] text-slate-400 dark:text-slate-500">
              {items.length + slots.length}
            </span>
          ) : null}
        </div>
        {slots.map((slot) => (
          <div key={`appointment-${slot.id}`} className="space-y-1">
            <button
              type="button"
              onClick={() => navigate(`${clientFilePath(slot.client.id)}&${CLIENT_TAB_PARAM}=${CLIENT_APPOINTMENTS_TAB}`)}
              className="w-full rounded-lg border border-teal-300 bg-white px-2 py-1.5 text-start text-[11px] transition hover:border-teal-400 dark:border-teal-800 dark:bg-slate-900"
            >
              <span className="block truncate font-semibold text-slate-800 dark:text-slate-100">
                {slot.client.name}
              </span>
              <span className="mt-0.5 flex flex-wrap items-center gap-1">
                <span className="rounded-full bg-teal-50 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-teal-800 dark:bg-teal-950/40 dark:text-teal-200">
                  {slot.time}
                </span>
                <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                  {slot.kind_label}
                </span>
                {slot.confirmed_at ? (
                  <span className="rounded-full bg-teal-50 px-1.5 py-0.5 text-[10px] font-semibold text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">
                    تأكيد مسجَّل
                  </span>
                ) : null}
              </span>
            </button>
            {/* الحجزُ من التقويم كان يترك التأكيدَ في ملفّ الزبون وحده. */}
            {canBook && isOpenAppointment(slot) && !slot.confirmed_at ? (
              <button
                type="button"
                onClick={() => confirmSlot(slot)}
                disabled={confirmingId === slot.id}
                className="w-full rounded-md border border-teal-200 px-1.5 py-1 text-[10px] font-semibold text-teal-800 transition hover:border-teal-400 disabled:opacity-60 dark:border-teal-900 dark:text-teal-200"
              >
                {confirmingId === slot.id ? 'يسجّل…' : 'ابعت تأكيد'}
              </button>
            ) : null}
          </div>
        ))}
        {items.map(renderItem)}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">التقويم</h1>
            <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
              مواعيدُ الالتزامات محسوبةٌ من لائحة المنصّة — لا شيء يُحفظ هنا، وتعديلُ سطرٍ في
              اللائحة يظهر فوراً.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => shift(-1)} className={officeSecondaryButtonClass}>
              السابق
            </button>
            <button type="button" onClick={goToday} className={officeSecondaryButtonClass}>
              اليوم
            </button>
            <button type="button" onClick={() => shift(1)} className={officeSecondaryButtonClass}>
              التالي
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 dark:border-slate-700">
            {(['month', 'week'] as CalendarMode[]).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setMode(key)}
                className={
                  mode === key
                    ? 'rounded-md bg-teal-50 px-2.5 py-1 text-[11.5px] font-semibold text-teal-800 dark:bg-teal-950/40 dark:text-teal-300'
                    : 'rounded-md px-2.5 py-1 text-[11.5px] font-medium text-slate-500 dark:text-slate-400'
                }
              >
                {key === 'month' ? 'شهري' : 'أسبوعي'}
              </button>
            ))}
          </div>

          {/* «شخص واحد» لا موظفَ غيره في المكتب — فلترُ الموظف يُخفى بالقاعدة نفسها. */}
          {showsMemberFilter ? (
            <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
              الموظف
              <select
                value={memberFilter}
                onChange={(event) => setMemberFilter(event.target.value)}
                className={`${officeInputClass} mt-1 block w-44`}
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

          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الزبون
            <select
              value={clientFilter}
              onChange={(event) => setClientFilter(event.target.value)}
              className={`${officeInputClass} mt-1 block w-56`}
            >
              <option value="">كل الزبائن</option>
              {clients.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.name}
                </option>
              ))}
            </select>
          </label>

          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            النوع
            <select
              value={ruleFilter}
              onChange={(event) => setRuleFilter(event.target.value)}
              className={`${officeInputClass} mt-1 block w-64`}
            >
              <option value="">كل الأنواع</option>
              {ruleOptions.map((rule) => (
                <option key={rule.code} value={rule.code}>
                  {rule.name}
                  {rule.is_generated ? '' : ' (لا يُولَّد)'}
                </option>
              ))}
            </select>
          </label>

          <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-300">
            {heading}
          </span>
        </div>

        {/* #281: الحجزُ من التقويم — الموعدُ يُسجَّل من هنا كما يُسجَّل من الملف. */}
        {canBook ? (
          <div className="mt-3">
            <button
              type="button"
              onClick={toggleBooking}
              className={bookingOpen ? officePrimaryButtonClass : officeSecondaryButtonClass}
            >
              {bookingOpen ? 'إغلاق الحجز' : 'احجز موعداً'}
            </button>
            {bookingOpen ? (
              <div className="mt-2 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2.5 dark:border-slate-700">
                <label className="flex flex-col gap-1 text-[11px] text-slate-600 dark:text-slate-300">
                  الزبون
                  <select
                    value={bookClient}
                    onChange={(event) => setBookClient(event.target.value)}
                    className={officeInputClass}
                  >
                    <option value="">اختر زبوناً</option>
                    {clients.map((client) => (
                      <option key={client.id} value={client.id}>
                        {client.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-slate-600 dark:text-slate-300">
                  النوع
                  <select
                    value={bookKind}
                    onChange={(event) => setBookKind(event.target.value)}
                    className={officeInputClass}
                  >
                    {kindChoices.map((choice) => (
                      <option key={choice.value} value={choice.value}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-slate-600 dark:text-slate-300">
                  الوقت
                  <input
                    type="datetime-local"
                    value={bookSlot}
                    onChange={(event) => setBookSlot(event.target.value)}
                    className={officeInputClass}
                  />
                </label>
                <label className="flex min-w-[160px] flex-1 flex-col gap-1 text-[11px] text-slate-600 dark:text-slate-300">
                  ملاحظة
                  <input
                    type="text"
                    value={bookNote}
                    maxLength={300}
                    onChange={(event) => setBookNote(event.target.value)}
                    className={officeInputClass}
                  />
                </label>
                <button
                  type="button"
                  onClick={book}
                  disabled={bookBusy || !bookClient || !bookSlot}
                  className={officePrimaryButtonClass}
                >
                  احجز
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        {/* نصُّ التأكيد كما بناه الخادم — والرابطُ من `appointmentConfirmationView`. */}
        {confirmation ? (
          <div className="mt-3 rounded-lg border border-teal-200 bg-teal-50 p-2.5 dark:border-teal-900 dark:bg-teal-950/40">
            <div className="flex items-start justify-between gap-2">
              <p className="whitespace-pre-line text-[11.5px] text-teal-900 dark:text-teal-100">
                {confirmation.body}
              </p>
              <button
                type="button"
                onClick={() => setConfirmation(null)}
                className="shrink-0 text-[11px] font-semibold text-teal-800 hover:underline dark:text-teal-200"
              >
                إخفاء
              </button>
            </div>
            {confirmation.link ? (
              <a
                href={confirmation.link}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block rounded-lg bg-teal-700 px-3 py-1.5 text-[11.5px] font-semibold text-white hover:bg-teal-800"
              >
                افتح واتساب
              </a>
            ) : (
              <p className="mt-1 text-[10.5px] text-teal-800 dark:text-teal-200">
                لا رابطَ واتساب — رقمُ الجهة أرضيٌّ ونظامُ الزبون غير معروف.
              </p>
            )}
          </div>
        ) : null}
      </header>

      {error ? <OfficeError message={error} onRetry={retry} /> : null}

      {loading ? (
        <OfficeSkeleton rows={6} />
      ) : rows.length === 0 && !error ? (
        <OfficeEmpty
          title="لا مواعيد في هذا المدى"
          hint="جرّب شهراً آخر، أو أوسع الفلاتر — المواعيد تُحسب من خدمات الزبون ولائحة المنصّة."
        />
      ) : mode === 'month' ? (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <div className="grid grid-cols-7 border-b border-slate-200 text-center text-[10.5px] font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
            {WEEKDAYS_AR.map((label) => (
              <div key={label} className="py-1.5">
                {label}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 divide-x divide-slate-100 dark:divide-slate-800">
            {monthGrid(monthKey).flat().map((day) => renderDay(day, false))}
          </div>
        </div>
      ) : (
        <OfficeCard>
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {weekDays(anchor).map((date) => renderDay({ date, inMonth: true }, true))}
          </div>
        </OfficeCard>
      )}
    </div>
  );
};
