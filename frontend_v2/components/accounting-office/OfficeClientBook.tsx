import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  changeClientBookKind,
  createBookEntry,
  getClientBook,
  getClientDocuments,
  listBookAccounts,
  listBookEntries,
  reverseBookEntry,
  type BookEntryRow,
  type BookEntryWrite,
  type ClientBookRow,
  type ClientDocumentsPayload,
} from '../../services/accountingOfficeApi';
import {
  bookDraftProblem,
  bookKindOn,
  bookedDocumentIds,
  entryDateForMonth,
  formatOfficeAmount,
  isLiveBookEntry,
  multipleDocumentsAllowed,
  nextBookKind,
  pendingMonthDocuments,
  type BookAccountRow,
  type BookDraftProblem,
  type BookLineDraft,
} from '../../utils/accountingOffice';
import { formatDateValue, todayIso } from '../../utils/formatDate';
import { monthKeyLabel, monthKeyOf } from '../../utils/monthKey';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

const statusOf = (failure: unknown): number | undefined =>
  (failure as { status?: number } | null)?.status;

/** بندٌ فارغٌ لمسوّدة جديدة — الحسابُ والمبلغُ يكتبهما الموظف. */
const EMPTY_LINE: BookLineDraft = {
  account_code: '', debit: '', credit: '', side_party: '',
};

/** سطرٌ لم يُكتب فيه شيء — يُهمَل عند الإرسال وعند المطالبة بحسابٍ له. */
function lineWritten(line: BookLineDraft): boolean {
  return line.account_code.trim() !== ''
    || line.debit.trim() !== ''
    || line.credit.trim() !== '';
}

/**
 * عِلَلُ المسوّدة كما تُقال — الرموزُ من `bookDraftProblem` والنصُّ هنا وحده.
 *
 * النصوصُ الثلاثةُ الأولى والأخيرةُ هي رسائلُ الخادم نفسها (في `_prepare_lines`
 * و`_assert_balanced`)، فلا نرسل ما نعلم أنه سيُردّ.
 */
const DRAFT_PROBLEM_TEXT: Record<Exclude<BookDraftProblem, ''>, string> = {
  'no-lines': 'الحركة تحتاج بنداً واحداً على الأقل.',
  'no-account': 'لكل بندٍ حساب — اختره من شجرة الزبون.',
  'no-side': 'لكل بندٍ طرفٌ واحد: مدينٌ أو دائن.',
  'two-sides': 'طرفٌ واحد لكل بند — مدينٌ أو دائن لا الاثنان.',
  invalid: 'مبلغٌ غير رقميّ: أرقامٌ بفاصلة عشريةٍ واحدة، بخانتين على الأكثر.',
  unbalanced: 'الحركة المزدوجة لا بدّ أن تتوازن: مجموع المدين = مجموع الدائن.',
};

/** «معكوسة» أم «عكس» — حالةٌ لا يرسل لها الخادم تسمية، والفرقُ يهمّ القارئ. */
function entryStateLabel(entry: BookEntryRow): string {
  if (entry.reverses !== null) return 'عكس';
  if (entry.reversed_by !== null) return 'معكوسة';
  return '';
}

/**
 * #286/ب — تبويبُ «الدفتر» في ملفّ الزبون: حركاتُ دفتره وإدخالُها.
 *
 * **والشكلُ كلُّه من الخادم**: نوعُ الدفتر وطريقةُ الإدخال ونوعُ الحركة ونوعُ
 * الحساب تصل نصوصاً (`kind_label` · `entry_method_label` · `kind_choices` ·
 * `account_type_choices`)، فلا جدولَ تسمياتٍ هنا يفترق عن النموذج عند أول تعديل.
 *
 * **وشرطان لا يُدمجان**: `writable` تعني «خدمةُ مسك الدفاتر نشطة» (إيقافُها
 * يمنع الكتابة 400 ويُبقي القراءة)، و`canWrite` تعني «يملك `office.clients.write`»،
 * و`canSeeAmounts` ثالثهما: من لا يرى المبالغ لا يكتبها (403) — فالنموذجُ يُقفل
 * برسالته بدل إرسالِ ما سيُرفض.
 *
 * **و«للإدخال» مشتقٌّ لا مخزَّن** (د9): أوراقُ الشهر الواصلةُ التي لا رابطَ حيّاً
 * لها، تُشتقّ من شبكة الأوراق (#278) وحركاتِ الدفتر معاً — فلا نقطةَ جديدة.
 */
export const OfficeClientBook: React.FC<{
  clientId: number;
  canWrite: boolean;
  canSeeAmounts: boolean;
  /** الشهرُ المطلوب من «للإدخال» (`?month=YYYY-MM`) — يفتح الإدخالَ عليه. */
  month: string | null;
}> = ({ clientId, canWrite, canSeeAmounts, month }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const today = todayIso();

  const [book, setBook] = useState<ClientBookRow | null>(null);
  const [entries, setEntries] = useState<BookEntryRow[]>([]);
  const [accounts, setAccounts] = useState<BookAccountRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [noBook, setNoBook] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [busy, setBusy] = useState(false);

  const [formOpen, setFormOpen] = useState(month !== null);
  const [draftDate, setDraftDate] = useState(
    entryDateForMonth(month ?? monthKeyOf(today), today),
  );
  const [draftKind, setDraftKind] = useState('');
  const [draftMemo, setDraftMemo] = useState('');
  const [draftLines, setDraftLines] = useState<BookLineDraft[]>([EMPTY_LINE]);
  const [draftMonth, setDraftMonth] = useState(month ?? monthKeyOf(today));
  const [draftDocuments, setDraftDocuments] = useState<number[]>([]);
  const [formError, setFormError] = useState('');

  const [documents, setDocuments] = useState<ClientDocumentsPayload | null>(null);
  const [documentsYear, setDocumentsYear] = useState<number | null>(null);
  const [documentsError, setDocumentsError] = useState('');

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setNoBook(false);
    Promise.all([
      getClientBook(clientId),
      listBookEntries(clientId),
      listBookAccounts(clientId),
    ])
      .then(([bookRow, entryRows, accountRows]) => {
        if (cancelled) return;
        setBook(bookRow);
        setEntries(entryRows);
        setAccounts(accountRows);
      })
      .catch((failure) => {
        if (cancelled) return;
        // 404 = لا دفترَ لهذا الزبون (أو لا يراه العضو) — حالةٌ لا خطأُ شبكة.
        setBook(null);
        setEntries([]);
        setAccounts([]);
        setNoBook(statusOf(failure) === 404);
        setError(statusOf(failure) === 404
          ? ''
          : humanizeThrown(failure, 'تعذّر تحميل دفتر الزبون.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, reloadToken]);

  // فتحُ الإدخال على شهر ورقةٍ جاءت من «للإدخال» — والحالةُ تُضبط مرّةً لكل شهر.
  useEffect(() => {
    if (!month) return;
    setFormOpen(true);
    setDraftMonth(month);
    setDraftDate(entryDateForMonth(month, today));
  }, [month, today]);

  // أوراقُ سنةِ الشهر المختار — تُقرأ عند فتح النموذج وعند تغيّر السنة وحدها.
  const wantedYear = formOpen && draftMonth ? Number(draftMonth.slice(0, 4)) : null;
  useEffect(() => {
    if (wantedYear === null || !Number.isFinite(wantedYear)) return;
    let cancelled = false;
    setDocumentsYear(null);
    setDocumentsError('');
    setDocuments(null);
    getClientDocuments(clientId, wantedYear)
      .then((payload) => {
        if (cancelled) return;
        setDocuments(payload);
        setDocumentsYear(wantedYear);
      })
      .catch((failure) => {
        if (!cancelled) setDocumentsError(humanizeThrown(failure, 'تعذّر تحميل أوراق الشهر.'));
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, wantedYear, reloadToken]);

  const booked = useMemo(() => bookedDocumentIds(entries), [entries]);
  const pendingDocuments = useMemo(
    () => (documents ? pendingMonthDocuments(documents, booked, draftMonth) : []),
    [documents, booked, draftMonth],
  );

  const doubleEntry = book ? bookKindOn(book, draftDate) === 'double' : false;
  const problem = bookDraftProblem(draftLines, { doubleEntry });
  const targetKind = book ? nextBookKind(book) : null;
  const targetKindLabel = targetKind
    ? (book?.kind_choices ?? []).find((choice) => choice.value === targetKind)?.label ?? ''
    : '';

  const openForm = useCallback(() => {
    setFormOpen(true);
    setFormError('');
    if (!draftDate) setDraftDate(entryDateForMonth(draftMonth, today));
  }, [draftDate, draftMonth, today]);

  const resetDraft = useCallback(() => {
    setDraftKind('');
    setDraftMemo('');
    setDraftLines([EMPTY_LINE]);
    setDraftDocuments([]);
    setFormError('');
  }, []);

  const submit = useCallback(async () => {
    if (!book || problem !== '' || !draftDate || !draftKind) return;
    const written = draftLines.filter(lineWritten);
    const payload: BookEntryWrite = {
      entry_date: draftDate,
      kind: draftKind,
      memo: draftMemo,
      documents: draftDocuments,
      lines: written.map((line) => ({
        account_code: line.account_code.trim(),
        // `''` مبلغٌ فاسدٌ عند الخادم (400) — الفارغُ `null` كما في المُسلسِل.
        debit: line.debit.trim() === '' ? null : line.debit.trim(),
        credit: line.credit.trim() === '' ? null : line.credit.trim(),
        side_party: line.side_party,
      })),
    };
    setBusy(true);
    setFormError('');
    try {
      const created = await createBookEntry(clientId, payload);
      toast(`انكتبت الحركة رقم ${created.number} في سنة ${created.year}`, 'success');
      resetDraft();
      setFormOpen(false);
      reload();
    } catch (failure) {
      setFormError(humanizeThrown(failure, 'تعذّر إدخال الحركة.'));
    } finally {
      setBusy(false);
    }
  }, [
    book, clientId, draftDate, draftDocuments, draftKind, draftLines, draftMemo,
    problem, reload, resetDraft, toast,
  ]);

  const reverse = useCallback(async (entry: BookEntryRow) => {
    const approved = await confirm({
      title: 'اعكس الحركة',
      message: `تُكتب حركةٌ مقابلةٌ للحركة رقم ${entry.number} بتاريخها نفسه. الأصلُ يبقى في الدفتر، وتعود أوراقُه إلى «للإدخال» — فلا يُحذف شيء.`,
      confirmText: 'اعكس',
    });
    if (!approved) return;
    setBusy(true);
    try {
      const reversal = await reverseBookEntry(clientId, entry.id);
      toast(`انكتب العكسُ رقم ${reversal.number}`, 'success');
      reload();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر عكس الحركة.'), 'error');
    } finally {
      setBusy(false);
    }
  }, [clientId, confirm, reload, toast]);

  const changeKind = useCallback(async () => {
    if (!book || !targetKind) return;
    const approved = await confirm({
      title: 'غيّر نوع الدفتر',
      message: 'ينتقل الدفترُ إلى النوع الآخر من بداية سنةٍ نظيفة: يُرفض التغيير في سنة فتح الدفتر أو إن وُجدت حركاتٌ في السنة الجارية. والرجوعُ إلى البسيط مرفوضٌ دائماً — حكمُ الشروط كلِّها في الخادم.',
      confirmText: 'غيّر النوع',
    });
    if (!approved) return;
    setBusy(true);
    try {
      const updated = await changeClientBookKind(clientId, targetKind);
      toast(`صار نوعُ الدفتر: ${updated.kind_label}`, 'success');
      // الشجرةُ تُكمَّل بالحسابات الناقصة في الخادم — فتُقرأ من جديد.
      reload();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تغيير نوع الدفتر.'), 'error');
    } finally {
      setBusy(false);
    }
  }, [book, clientId, confirm, reload, targetKind, toast]);

  const writable = Boolean(book?.writable);
  const canEdit = canWrite && writable;
  const canEnter = canEdit && canSeeAmounts;

  if (loading && !book) return <OfficeSkeleton />;
  if (error) return <OfficeError message={error} onRetry={reload} />;
  if (noBook) {
    return (
      <OfficeEmpty
        title="ما في دفتر لهذا الزبون."
        hint="دفترُ الزبون يُنشأ مرّةً واحدة لكل زبون، ثم تُدخل حركاته هنا."
      />
    );
  }
  if (!book) return null;

  return (
    <div className="space-y-4">
      <OfficeCard
        title="الدفتر"
        actions={
          canEdit && targetKind ? (
            <button
              type="button"
              onClick={changeKind}
              disabled={busy}
              className={`${officeSecondaryButtonClass} disabled:opacity-50`}
            >
              {targetKindLabel ? `حوّل إلى ${targetKindLabel}` : 'غيّر نوع الدفتر'}
            </button>
          ) : null
        }
      >
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {book.kind_label}
          </span>
          {book.kind_changed_on ? (
            <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
              صار {book.kind_label} من {formatDateValue(book.kind_changed_on)}
            </span>
          ) : null}
          {book.entry_method_label ? (
            <span className="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 font-medium text-teal-800 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300">
              الإدخال: {book.entry_method_label}
            </span>
          ) : null}
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            مفتوح من {formatDateValue(book.opened_on)}
          </span>
          {writable ? (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
              قابل للكتابة
            </span>
          ) : (
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
              للقراءة — مسك الدفاتر موقوف
            </span>
          )}
        </div>
        {!writable ? (
          <p className="mt-2 text-[11px] font-medium text-amber-800 dark:text-amber-300">
            خدمة مسك الدفاتر موقوفة لهذا الزبون: الحركات تُقرأ ولا تُكتب، والخادم يردّ كل
            إدخالٍ أو عكسٍ 400.
          </p>
        ) : null}
      </OfficeCard>

      <OfficeCard
        title="الحركات"
        actions={
          canEnter ? (
            <button type="button" onClick={openForm} className={officePrimaryButtonClass}>
              + إدخال حركة
            </button>
          ) : null
        }
      >
        {canWrite && writable && !canSeeAmounts ? (
          <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] font-medium text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
            لا تكتب مبلغاً لا تراه: صلاحية «يرى المبالغ» غير ممنوحة لدورك، والخادم يردّ
            الإدخال 403.
          </p>
        ) : null}

        {canEnter && formOpen ? (
          <form
            onSubmit={(event) => { event.preventDefault(); void submit(); }}
            className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40"
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                التاريخ
                <input
                  type="date"
                  value={draftDate}
                  onChange={(event) => setDraftDate(event.target.value)}
                  required
                  className={`${officeInputClass} mt-1 block w-full tabular-nums`}
                />
              </label>
              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                نوع الحركة
                <select
                  value={draftKind}
                  onChange={(event) => setDraftKind(event.target.value)}
                  required
                  className={`${officeInputClass} mt-1 block w-full`}
                >
                  <option value="">— اختر النوع —</option>
                  {(book.kind_choices ?? []).map((choice) => (
                    <option key={choice.value} value={choice.value}>{choice.label}</option>
                  ))}
                </select>
              </label>
              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300 sm:col-span-2">
                البيان
                <input
                  value={draftMemo}
                  onChange={(event) => setDraftMemo(event.target.value)}
                  className={`${officeInputClass} mt-1 block w-full`}
                />
              </label>
            </div>

            <div className="mt-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[11.5px] font-semibold text-slate-700 dark:text-slate-200">
                  البنود
                </span>
                <span className="text-[10.5px] font-medium text-slate-500 dark:text-slate-400">
                  {doubleEntry ? 'دفتر مزدوج: المدين = الدائن' : 'دفتر بسيط: طرفٌ واحد لكل بند'}
                </span>
              </div>
              <div className="mt-1 space-y-2">
                {draftLines.map((line, index) => (
                  <div
                    key={index}
                    className="grid gap-2 sm:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))_auto]"
                  >
                    <select
                      value={line.account_code}
                      onChange={(event) => {
                        const next = [...draftLines];
                        next[index] = { ...line, account_code: event.target.value };
                        setDraftLines(next);
                      }}
                      className={officeInputClass}
                      aria-label={`حساب البند ${index + 1}`}
                    >
                      <option value="">— الحساب —</option>
                      {accounts.map((account) => (
                        <option key={account.code} value={account.code}>
                          {account.code} — {account.name}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      inputMode="decimal"
                      placeholder="مدين"
                      value={line.debit}
                      onChange={(event) => {
                        const next = [...draftLines];
                        next[index] = { ...line, debit: event.target.value };
                        setDraftLines(next);
                      }}
                      className={`${officeInputClass} tabular-nums`}
                      aria-label={`مدين البند ${index + 1}`}
                    />
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      inputMode="decimal"
                      placeholder="دائن"
                      value={line.credit}
                      onChange={(event) => {
                        const next = [...draftLines];
                        next[index] = { ...line, credit: event.target.value };
                        setDraftLines(next);
                      }}
                      className={`${officeInputClass} tabular-nums`}
                      aria-label={`دائن البند ${index + 1}`}
                    />
                    <input
                      placeholder="الطرف"
                      value={line.side_party}
                      onChange={(event) => {
                        const next = [...draftLines];
                        next[index] = { ...line, side_party: event.target.value };
                        setDraftLines(next);
                      }}
                      className={officeInputClass}
                      aria-label={`طرف البند ${index + 1}`}
                    />
                    <button
                      type="button"
                      onClick={() => setDraftLines(draftLines.filter((_, at) => at !== index))}
                      disabled={draftLines.length === 1}
                      className="rounded-lg border border-rose-200 bg-white px-2 py-1 text-[11px] font-medium text-rose-700 disabled:opacity-40 dark:border-rose-900 dark:bg-slate-900 dark:text-rose-300"
                      aria-label={`احذف البند ${index + 1}`}
                    >
                      حذف
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setDraftLines([...draftLines, EMPTY_LINE])}
                className={`mt-2 ${officeSecondaryButtonClass}`}
              >
                + بند
              </button>
            </div>

            <div className="mt-3 rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[11.5px] font-semibold text-slate-700 dark:text-slate-200">
                  أوراق للحركة
                </span>
                <input
                  type="month"
                  value={draftMonth}
                  onChange={(event) => {
                    setDraftMonth(event.target.value);
                    setDraftDocuments([]);
                    setDraftDate(entryDateForMonth(event.target.value, today));
                  }}
                  className={officeInputClass}
                  aria-label="شهر الأوراق"
                />
              </div>
              <p className="mt-1 text-[10.5px] font-medium text-slate-500 dark:text-slate-400">
                {draftMonth ? monthKeyLabel(draftMonth) : '—'} · أوراق الشهر الواصلة التي لم
                تدخل حركةً حيّة.
                {multipleDocumentsAllowed(book.entry_method)
                  ? ''
                  : ` وضعُ «${book.entry_method_label}»: ورقة واحدة لكل حركة.`}
              </p>
              {documentsError ? (
                <p className="mt-1 text-[11px] font-medium text-rose-600 dark:text-rose-400">
                  {documentsError}
                </p>
              ) : documentsYear === null ? (
                <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">…</p>
              ) : pendingDocuments.length === 0 ? (
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  ما في أوراق بانتظار الإدخال في هذا الشهر.
                </p>
              ) : (
                <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
                  {pendingDocuments.map((document) => (
                    <li key={document.row_id} className="flex items-center gap-2 py-1.5">
                      <input
                        type="checkbox"
                        id={`book-document-${document.row_id}`}
                        checked={draftDocuments.includes(document.row_id)}
                        onChange={() => {
                          setDraftDocuments((current) => {
                            if (!multipleDocumentsAllowed(book.entry_method)) {
                              return current.includes(document.row_id) ? [] : [document.row_id];
                            }
                            return current.includes(document.row_id)
                              ? current.filter((id) => id !== document.row_id)
                              : [...current, document.row_id];
                          });
                        }}
                        className="h-3.5 w-3.5 rounded border-slate-300 text-teal-700"
                      />
                      <label
                        htmlFor={`book-document-${document.row_id}`}
                        className="min-w-0 text-[11.5px] font-medium text-slate-700 dark:text-slate-200"
                      >
                        {document.name}
                        {document.received_on ? (
                          <span className="ms-1 text-[10.5px] font-normal text-slate-500 dark:text-slate-400">
                            · وصل {formatDateValue(document.received_on)}
                          </span>
                        ) : null}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {problem !== '' ? (
              <p className="mt-2 text-[11px] font-medium text-amber-800 dark:text-amber-300">
                {DRAFT_PROBLEM_TEXT[problem]}
              </p>
            ) : null}
            {formError ? (
              <p className="mt-2 text-[11px] font-medium text-rose-600 dark:text-rose-400">
                {formError}
              </p>
            ) : null}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={busy || problem !== '' || !draftDate || !draftKind}
                className={`${officePrimaryButtonClass} disabled:opacity-50`}
              >
                {busy ? '…' : 'أدخل الحركة'}
              </button>
              <button
                type="button"
                onClick={() => { setFormOpen(false); resetDraft(); }}
                className={officeSecondaryButtonClass}
              >
                إلغاء
              </button>
            </div>
          </form>
        ) : null}

        {entries.length === 0 ? (
          <OfficeEmpty
            title="ما في حركات في هذا الدفتر بعد."
            hint="الحركة الأولى تكتب رقمها بترقيمٍ متّصلٍ لكل سنة — لا فجوات ولا حذف."
          />
        ) : (
          <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
            <table className="w-full min-w-[680px] text-right">
              <thead>
                <tr className="border-b border-slate-200 text-[10.5px] font-medium text-slate-400 dark:border-slate-700 dark:text-slate-500">
                  <th className="px-1 py-2 font-medium">الرقم</th>
                  <th className="px-1 py-2 font-medium">السنة</th>
                  <th className="px-1 py-2 font-medium">التاريخ</th>
                  <th className="px-1 py-2 font-medium">النوع</th>
                  <th className="px-1 py-2 font-medium">البيان</th>
                  <th className="px-1 py-2 font-medium">مدين</th>
                  <th className="px-1 py-2 font-medium">دائن</th>
                  <th className="px-1 py-2 font-medium">أوراق</th>
                  <th className="px-1 py-2" />
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const state = entryStateLabel(entry);
                  return (
                    <tr
                      key={entry.id}
                      className="border-b border-slate-100 last:border-b-0 dark:border-slate-800"
                    >
                      <td className="px-1 py-2 text-[11.5px] font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                        {entry.number}
                      </td>
                      <td className="px-1 py-2 text-[11.5px] tabular-nums text-slate-500 dark:text-slate-400">
                        {entry.year}
                      </td>
                      <td className="whitespace-nowrap px-1 py-2 text-[11.5px] tabular-nums text-slate-600 dark:text-slate-300">
                        {formatDateValue(entry.entry_date)}
                      </td>
                      <td className="px-1 py-2 text-[11.5px] text-slate-600 dark:text-slate-300">
                        <span className="flex flex-wrap items-center gap-1">
                          {entry.kind_label}
                          {state ? (
                            <span className="rounded-full border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                              {state}
                            </span>
                          ) : null}
                        </span>
                      </td>
                      <td className="px-1 py-2 text-[11.5px] text-slate-600 dark:text-slate-300">
                        {entry.memo || '—'}
                      </td>
                      <td className="px-1 py-2 text-[11.5px] tabular-nums text-slate-700 dark:text-slate-200">
                        {formatOfficeAmount(entry.total_debit)}
                      </td>
                      <td className="px-1 py-2 text-[11.5px] tabular-nums text-slate-700 dark:text-slate-200">
                        {formatOfficeAmount(entry.total_credit)}
                      </td>
                      <td className="px-1 py-2 text-[11.5px] tabular-nums text-slate-500 dark:text-slate-400">
                        {entry.documents.length || '—'}
                      </td>
                      <td className="px-1 py-2 text-end">
                        {canEnter && isLiveBookEntry(entry) ? (
                          <button
                            type="button"
                            onClick={() => void reverse(entry)}
                            disabled={busy}
                            className="rounded-lg border border-rose-200 bg-white px-2 py-1 text-[11px] font-medium text-rose-700 disabled:opacity-40 dark:border-rose-900 dark:bg-slate-900 dark:text-rose-300"
                          >
                            اعكس
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </OfficeCard>
    </div>
  );
};
