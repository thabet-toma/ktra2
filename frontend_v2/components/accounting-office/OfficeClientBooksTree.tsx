/**
 * #286/ب — قسمُ «شجرةُ حساب الزبون» في إعدادات المكتب.
 *
 * الدفترُ ينسخ شجرتَه **نسخةً واحدة** عند إنشائه (من نسخة المكتب وإلا من شجرة
 * المنصّة)، فلا مرجعَ حيّ إلى القالب: ما يُضاف هنا يخصّ زبوناً واحداً ولا يغيّر
 * شجرةَ غيره. والنقطةُ القائمة وحدها تُستعمل — `client-books/<client_id>/accounts/`
 * قراءةً وإضافةً — **ولا نقطةَ شجرةٍ على مستوى المكتب** لأنها غيرُ مبنية في
 * الجزء أ، فلا تُخترع.
 *
 * والقراءةُ لكل من يرى الزبون، والإضافةُ بـ`office.clients.write` وحده (والخادمُ
 * يحكم على أيّ حال). والحسابُ المضافُ `is_system=false` دائماً — حسابُ المكتب لا
 * حسابُ المنصّة.
 *
 * **ونسبةُ الحساب تُقرأ وتُكتب من هنا (#287/١ و٢)**: `rates` على كل سطر من
 * `accounts/` تُعرض مع شارة «راجع» التي يحكمها الخادم، وتصنيفُ الحساب يُختار من
 * لائحة نظامه (`client-books/rates/`) — والفراغُ يُرجعه إلى الافتراض. وتغييرُ
 * التصنيف يمرّ بـ`accounts/<code>/rates/` وحدها، فيعود السطرُ من ردّها لا من
 * تخمينِ الواجهة.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  addBookAccount,
  getBookRates,
  getClientBook,
  listBookAccounts,
  listClientBooks,
  setBookAccountRates,
  type BookAccountRow,
  type BookRatesPayload,
  type ClientBookRow,
} from '../../services/accountingOfficeApi';
import {
  accountVatNeedsReview,
  accountVatRateText,
} from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import { officeInputClass, officePrimaryButtonClass } from './OfficeUi';

const statusOf = (failure: unknown): number | undefined =>
  (failure as { status?: number } | null)?.status;

const EMPTY_DRAFT = { code: '', name: '', parent_code: '', account_type: '' };

export const OfficeClientBooksTree: React.FC = () => {
  const toast = useToast();
  const { can } = usePermissions();
  const canWrite = can('office.clients.write');

  const [clients, setClients] = useState<ClientBookRow[] | null>(null);
  const [clientsError, setClientsError] = useState('');
  const [clientId, setClientId] = useState<number | null>(null);
  const [book, setBook] = useState<ClientBookRow | null>(null);
  const [noBook, setNoBook] = useState(false);
  const [accounts, setAccounts] = useState<BookAccountRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  // #287/١ و٢: لائحةُ النسب (تصنيفاتُ النظام) وحالةُ حفظ تصنيفٍ لحسابٍ واحد.
  const [rates, setRates] = useState<BookRatesPayload | null>(null);
  const [ratesError, setRatesError] = useState('');
  const [rateBusy, setRateBusy] = useState('');

  useEffect(() => {
    let cancelled = false;
    setClientsError('');
    // **ذوو الدفاتر وحدهم**: زبونٌ بلا دفترٍ لا شجرةَ له، فالمنتقي كان يُغرِق
    // القائمةَ بزبائن لا يملكون شيئاً يُعرض — والدفترُ يُفتح من تبويب «الدفتر».
    listClientBooks()
      .then((rows) => {
        if (!cancelled) setClients(rows);
      })
      .catch((failure) => {
        if (!cancelled) {
          setClients([]);
          setClientsError(humanizeThrown(failure, 'تعذّر تحميل دفاتر الزبائن.'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (clientId === null) {
      setBook(null);
      setAccounts(null);
      setNoBook(false);
      setError('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    setNoBook(false);
    setAccounts(null);
    Promise.all([getClientBook(clientId), listBookAccounts(clientId)])
      .then(([bookRow, accountRows]) => {
        if (cancelled) return;
        setBook(bookRow);
        setAccounts(accountRows);
      })
      .catch((failure) => {
        if (cancelled) return;
        setBook(null);
        setAccounts(null);
        // 404 = لا دفترَ لهذا الزبون — حالةٌ تُقال، لا خطأٌ يُعرض.
        setNoBook(statusOf(failure) === 404);
        setError(statusOf(failure) === 404
          ? ''
          : humanizeThrown(failure, 'تعذّر تحميل شجرة الحساب.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, reloadToken]);

  const typeChoices = useMemo(() => book?.account_type_choices ?? [], [book]);
  const rows = accounts ?? [];
  // الحسابُ المعطَّل يبقى في الشجرة للقراءة، ولا يُختار أباً لحسابٍ جديد.
  const parentChoices = useMemo(
    () => rows.filter((account) => account.is_active),
    [rows],
  );
  const writable = Boolean(book?.writable);
  const canAdd = canWrite && writable;
  // تصنيفاتُ لائحة نظام الزبون — الأولُ لكل كود (الصفوفُ ثلاثةٌ لكل تصنيف).
  const categoryChoices = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of rates?.rows ?? []) {
      if (row.code && !seen.has(row.code)) seen.set(row.code, row.label);
    }
    return [...seen.entries()].map(([value, label]) => ({ value, label }));
  }, [rates]);

  /** #287/٢: تصنيفُ الحساب في اللائحة — الفراغُ يُرْجعه إلى الافتراض. */
  const changeCategory = useCallback(async (code: string, category: string) => {
    if (clientId === null) return;
    setRateBusy(code);
    try {
      const saved = await setBookAccountRates(clientId, code, {
        rate_category: category,
      });
      setAccounts((current) => (current ?? []).map((row) => (
        row.code === code
          ? {
            ...row,
            rate_category: saved.rate_category,
            rate_category_label: saved.rates.vat.label,
            rates: saved.rates,
          }
          : row
      )));
      toast(`تحدّث تصنيف الحساب ${code}`, 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ تصنيف الحساب.'), 'error');
    } finally {
      setRateBusy('');
    }
  }, [clientId, toast]);

  // لائحةُ النسب بنظام الزبون — تُقرأ بعد معرفة نظامه من سطر الدفتر.
  useEffect(() => {
    // **وتُفرَّغ قبل القراءة**: تبديلُ الزبون من نظامٍ إلى آخر كان يُبقي لائحةَ
    // الأوّل (ورقمَ «راجع» الخاصّ بها) حتى يصل الجديد، فيُعرض تصنيفٌ لا يخصّ
    // الشجرةَ المعروضة.
    setRates(null);
    setRatesError('');
    const system = book?.tax_system;
    if (!system) {
      return;
    }
    let cancelled = false;
    getBookRates(system)
      .then((payload) => {
        if (!cancelled) setRates(payload);
      })
      .catch((failure) => {
        if (!cancelled) {
          setRates(null);
          setRatesError(humanizeThrown(failure, 'تعذّر تحميل لائحة النسب.'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [book?.tax_system, reloadToken]);

  const add = useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    if (clientId === null) return;
    setBusy(true);
    try {
      const created = await addBookAccount(clientId, {
        code: draft.code.trim(),
        name: draft.name.trim(),
        parent_code: draft.parent_code,
        account_type: draft.account_type,
      });
      setAccounts(
        [...rows, created].sort((left, right) => left.code.localeCompare(right.code)),
      );
      setDraft(EMPTY_DRAFT);
      toast(`انضاف الحساب ${created.code}`, 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إضافة الحساب.'), 'error');
    } finally {
      setBusy(false);
    }
  }, [clientId, draft, rows, toast]);

  return (
    <div>
      <h3 className="text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
        شجرةُ حساب الزبون
      </h3>
      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
        لكل زبونٍ شجرتُه المنسوخة عند فتح دفتره — إضافةُ حسابٍ هنا تخصّه وحده ولا
        تمسّ شجرةَ غيره، والحسابُ المضافُ لا يُحذف.
      </p>

      {clientsError ? (
        <p role="alert" className="mt-2 text-[12px] font-medium text-rose-600 dark:text-rose-400">
          {clientsError}
        </p>
      ) : clients === null ? (
        <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>
      ) : clients.length === 0 ? (
        <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">
          ما في دفاتر زبائن بعد — يُفتح الدفترُ من تبويب «الدفتر» في ملفّ الزبون.
        </p>
      ) : (
        <>
          <label className="mt-2 block text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
            الزبون
            <select
              value={clientId ?? ''}
              onChange={(event) => {
                const raw = event.target.value;
                setClientId(raw === '' ? null : Number(raw));
                setDraft(EMPTY_DRAFT);
              }}
              className={`${officeInputClass} mt-1 block w-full sm:w-72`}
            >
              <option value="">— اختر زبوناً —</option>
              {clients.map((client) => (
                <option key={client.client_id} value={client.client_id}>
                  {client.client_name}
                </option>
              ))}
            </select>
          </label>

          {clientId === null ? (
            <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">
              اختر زبوناً لعرض شجرته.
            </p>
          ) : loading ? (
            <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>
          ) : error ? (
            <div className="mt-2">
              <p role="alert" className="text-[12px] font-medium text-rose-600 dark:text-rose-400">
                {error}
              </p>
              <button
                type="button"
                onClick={() => setReloadToken((token) => token + 1)}
                className="mt-2 text-[11px] font-medium text-teal-700 hover:underline dark:text-teal-400"
              >
                أعد المحاولة
              </button>
            </div>
          ) : noBook ? (
            <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">
              ما في دفتر لهذا الزبون — الدفتر يُنشأ مرّةً واحدة قبل أن تُضاف حساباتُه.
            </p>
          ) : (
            <>
              {!writable ? (
                <p className="mt-2 text-[11px] font-medium text-amber-800 dark:text-amber-300">
                  خدمة مسك الدفاتر موقوفة لهذا الزبون — الشجرة تُقرأ ولا تُضاف إليها حسابات.
                </p>
              ) : null}
              <div className="mt-2 max-h-72 overflow-auto">
                {ratesError ? (
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <p
                      role="alert"
                      className="text-[11px] font-medium text-rose-600 dark:text-rose-400"
                    >
                      {ratesError}
                    </p>
                    <button
                      type="button"
                      onClick={() => setReloadToken((token) => token + 1)}
                      className="text-[11px] font-medium text-teal-700 hover:underline dark:text-teal-400"
                    >
                      أعد المحاولة
                    </button>
                  </div>
                ) : null}
                {rates && rates.review_count > 0 ? (
                  <p className="mb-1 text-[11px] font-medium text-amber-800 dark:text-amber-300">
                    {rates.review_count} نسبة في لائحة النسب غيرُ مؤكَّدة («راجع») — لا
                    تُستعمل في حساب حتى يؤكّدها المكتب.
                  </p>
                ) : null}
                <table className="w-full min-w-[560px] text-start">
                  <thead>
                    <tr className="border-b border-slate-200 text-[10.5px] font-medium text-slate-400 dark:border-slate-700 dark:text-slate-500">
                      <th className="px-1 py-2 font-medium">الكود</th>
                      <th className="px-1 py-2 font-medium">الاسم</th>
                      <th className="px-1 py-2 font-medium">النوع</th>
                      <th className="px-1 py-2 font-medium">الحساب الأب</th>
                      <th className="px-1 py-2 font-medium">الفئة</th>
                      <th className="px-1 py-2 font-medium">ض.ق.م</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((account) => (
                      <tr
                        key={account.code}
                        className="border-b border-slate-100 last:border-b-0 dark:border-slate-800"
                      >
                        <td className="px-1 py-1.5 text-[11.5px] font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                          {account.code}
                        </td>
                        <td className="px-1 py-1.5 text-[11.5px] text-slate-600 dark:text-slate-300">
                          {account.name}
                        </td>
                        <td className="px-1 py-1.5 text-[11.5px] text-slate-500 dark:text-slate-400">
                          {account.account_type_label}
                        </td>
                        <td className="px-1 py-1.5 text-[11.5px] tabular-nums text-slate-500 dark:text-slate-400">
                          {account.parent_code || '—'}
                        </td>
                        <td className="px-1 py-1.5 text-[11.5px] text-slate-500 dark:text-slate-400">
                          {canAdd && rates ? (
                            <select
                              value={account.rate_category}
                              aria-label={`تصنيف الحساب ${account.code} في لائحة النسب`}
                              disabled={rateBusy === account.code}
                              onChange={(event) => {
                                void changeCategory(account.code, event.target.value);
                              }}
                              className={`${officeInputClass} block w-40`}
                            >
                              <option value="">— الافتراض —</option>
                              {categoryChoices.map((choice) => (
                                <option key={choice.value} value={choice.value}>
                                  {choice.label}
                                </option>
                              ))}
                            </select>
                          ) : (
                            account.rate_category_label || '—'
                          )}
                        </td>
                        <td className="px-1 py-1.5 text-[11.5px] text-slate-600 dark:text-slate-300">
                          <span className="inline-flex items-center gap-1">
                            <span className="tabular-nums">
                              {accountVatRateText(account) || '—'}
                            </span>
                            {/* #287/١: «راجع» من نسب الحساب نفسها — لا حسابَ هنا. */}
                            {accountVatNeedsReview(account) ? (
                              <span
                                title={`نسبة ض.ق.م غير مؤكَّدة — المصدر: ${
                                  account.rates?.vat?.source_label || '—'
                                }`}
                                className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
                              >
                                راجع
                              </span>
                            ) : null}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {canAdd ? (
                <form
                  onSubmit={(event) => { void add(event); }}
                  className="mt-3 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40"
                >
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    الكود
                    <input
                      value={draft.code}
                      onChange={(event) => setDraft({ ...draft, code: event.target.value })}
                      required
                      maxLength={20}
                      className={`${officeInputClass} mt-1 block w-24 tabular-nums`}
                    />
                  </label>
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    الاسم
                    <input
                      value={draft.name}
                      onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                      required
                      maxLength={200}
                      className={`${officeInputClass} mt-1 block w-56`}
                    />
                  </label>
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    النوع
                    <select
                      value={draft.account_type}
                      onChange={(event) => setDraft({ ...draft, account_type: event.target.value })}
                      required
                      className={`${officeInputClass} mt-1 block w-36`}
                    >
                      <option value="">— النوع —</option>
                      {typeChoices.map((choice) => (
                        <option key={choice.value} value={choice.value}>{choice.label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                    الحساب الأب (اختياري)
                    <select
                      value={draft.parent_code}
                      onChange={(event) => setDraft({ ...draft, parent_code: event.target.value })}
                      className={`${officeInputClass} mt-1 block w-56`}
                    >
                      <option value="">— بلا أب —</option>
                      {parentChoices.map((account) => (
                        <option key={account.code} value={account.code}>
                          {account.code} — {account.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="submit"
                    disabled={busy || !draft.account_type}
                    className={`${officePrimaryButtonClass} disabled:opacity-50`}
                  >
                    {busy ? '…' : 'أضف حساباً'}
                  </button>
                </form>
              ) : null}
            </>
          )}
        </>
      )}
    </div>
  );
};
