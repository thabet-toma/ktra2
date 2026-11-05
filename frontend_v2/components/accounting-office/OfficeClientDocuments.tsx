/**
 * #278 — تبويبُ «الأوراق» في ملفّ الزبون: شبكةُ الأشهر × البنود.
 *
 * **الخادمُ يعرف الحالة، والشاشةُ ترسم**: الصفوفُ تُولَّد في «حدّث المكتب»
 * (`client_documents` قراءةٌ خالصة)، والخاناتُ تحمل `status_label` والقناة
 * وتاريخَ الوصول — فلا تسميةَ حالةٍ هنا.
 *
 * **الملفُّ لا يغيّر الحالة** (قرار #278/D4): الرفعُ والحذفُ يمسّان `files` وحدها،
 * و`load()` بعد كل فعلٍ يعيد عددَ الملفات من الخادم لا من عدٍّ محليّ.
 *
 * والصرفُ خالصٌ في `utils/accountingOffice.ts` (`documentGridRows`،
 * `documentCellTone`، `documentMissingBar`)، والاتصالُ في `accountingOfficeApi.ts`.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  deleteDocumentFile,
  downloadDocumentFile,
  getClientDocuments,
  getDocumentItems,
  listDocumentFiles,
  setClientDocumentChoice,
  setDocumentStatus,
  uploadDocumentFile,
  type ClientDocumentsPayload,
  type DocumentFileRow,
  type OfficeDocumentItemRow,
} from '../../services/accountingOfficeApi';
import {
  documentCellClass,
  documentCellGlyph,
  documentCellTitle,
  documentFileTag,
  documentGridRows,
  documentMissingBar,
  documentMonthColumns,
  documentStatusChipClass,
  documentStatusChoicesFor,
  documentYearOptions,
  shortIsoDate,
} from '../../utils/accountingOffice';
import { todayIso } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeCard,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/** حالةُ اللوح: أربعةُ أزرارٍ للحالة، وواحدُ سؤالٍ للقناة بعد «وصلت». */
const RECEIVED_STATUSES = new Set(['received', 'partial']);

const EMPTY_UPLOAD = {
  document_type: '',
  issuer_registration: '',
  document_date: '',
  document_number: '',
  is_copy: true,
};

export const OfficeClientDocuments: React.FC<{
  clientId: number;
  canWrite: boolean;
  /** نظامُ الزبون — لوحُ «تخصيص القائمة» يقرأ بنوده وحدها. */
  taxSystem: string | null;
}> = ({ clientId, canWrite, taxSystem }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const currentYear = Number(todayIso().slice(0, 4));
  const [year, setYear] = useState(currentYear);
  const [payload, setPayload] = useState<ClientDocumentsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<{ itemCode: string; month: string } | null>(null);
  const [files, setFiles] = useState<DocumentFileRow[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [upload, setUpload] = useState({ ...EMPTY_UPLOAD });
  const [uploadBusy, setUploadBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [customOpen, setCustomOpen] = useState(false);
  const [customItems, setCustomItems] = useState<OfficeDocumentItemRow[] | null>(null);
  const [customBusy, setCustomBusy] = useState(false);
  // سنويّة: صفٌّ وقناةٌ في انتظار الاختيار — كالحالة في الشبكة.
  const [annualPending, setAnnualPending] = useState<{ rowId: number; status: string } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getClientDocuments(clientId, year)
      .then((next) => setPayload(next))
      .catch((failure) => {
        setPayload(null);
        setError(humanizeThrown(failure, 'تعذّر تحميل أوراق الزبون.'));
      })
      .finally(() => setLoading(false));
  }, [clientId, year]);

  useEffect(() => {
    load();
  }, [load]);

  const gridRows = useMemo(
    () => (payload ? documentGridRows(payload) : []),
    [payload],
  );
  const months = useMemo(
    () => (payload ? documentMonthColumns(payload.months) : []),
    [payload],
  );
  const missing = useMemo(
    () => (payload ? documentMissingBar(payload) : null),
    [payload],
  );
  const statusChoices = useMemo(
    () => (payload ? documentStatusChoicesFor(payload.status_choices, false) : []),
    [payload],
  );
  const annualStatusChoices = useMemo(
    () => (payload ? documentStatusChoicesFor(payload.status_choices, true) : []),
    [payload],
  );

  const selectedCell = useMemo(() => {
    if (!selected || !payload) return null;
    const item = payload.items.find((entry) => entry.item_code === selected.itemCode);
    const cell = item?.cells.find((entry) => entry.month === selected.month);
    return item && cell ? { item, cell } : null;
  }, [payload, selected]);
  const selectedRowId = selectedCell?.cell.row_id ?? null;

  const loadFiles = useCallback((rowId: number) => {
    setFilesLoading(true);
    listDocumentFiles(rowId)
      .then((rows) => setFiles(rows))
      .catch((failure) => {
        setFiles([]);
        toast(humanizeThrown(failure, 'تعذّر تحميل ملفات الورقة.'), 'error');
      })
      .finally(() => setFilesLoading(false));
  }, [toast]);

  useEffect(() => {
    setPendingStatus(null);
    if (selectedRowId === null) {
      setFiles([]);
      return;
    }
    loadFiles(selectedRowId);
  }, [selectedRowId, loadFiles]);

  /** إرسالُ حالةٍ لصفٍّ بعينه — الشبكةُ والسنويّ يمرّان من هنا. */
  const applyStatus = async (rowId: number, status: string, channel?: string) => {
    setSaving(true);
    try {
      await setDocumentStatus(rowId, { status, channel });
      setPendingStatus(null);
      setAnnualPending(null);
      toast('حُفظت حالة الورقة', 'success');
      load();
      if (selectedRowId === rowId) loadFiles(rowId);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ الحالة.'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const chooseStatus = (rowId: number, status: string, annual = false) => {
    if (RECEIVED_STATUSES.has(status)) {
      if (annual) setAnnualPending({ rowId, status });
      else setPendingStatus(status);
      return;
    }
    applyStatus(rowId, status);
  };

  const sendUpload = async () => {
    if (!selectedRowId) return;
    const file = fileInput.current?.files?.[0];
    if (!file) {
      toast('اختر ملفاً أولاً.', 'error');
      return;
    }
    setUploadBusy(true);
    try {
      await uploadDocumentFile(selectedRowId, {
        file,
        document_type: upload.document_type.trim(),
        issuer_registration: upload.issuer_registration.trim(),
        document_date: upload.document_date || undefined,
        document_number: upload.document_number.trim(),
        is_copy: upload.is_copy,
      });
      toast('رُفع الملف', 'success');
      setUpload({ ...EMPTY_UPLOAD });
      if (fileInput.current) fileInput.current.value = '';
      loadFiles(selectedRowId);
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر رفع الملف.'), 'error');
    } finally {
      setUploadBusy(false);
    }
  };

  const openFile = async (file: DocumentFileRow) => {
    try {
      const blob = await downloadDocumentFile(file.id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تنزيل الملف.'), 'error');
    }
  };

  const removeFile = async (file: DocumentFileRow) => {
    const ok = await confirm({
      title: 'حذف الملف',
      message: `يُحذف ملف «${file.file_name || file.document_type}» نهائياً. حالةُ الورقة لا تتغيّر.`,
      confirmText: 'احذف الملف',
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteDocumentFile(file.id);
      toast('حُذف الملف', 'success');
      if (selectedRowId) loadFiles(selectedRowId);
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حذف الملف.'), 'error');
    }
  };

  const openCustomize = async () => {
    setCustomOpen(true);
    if (customItems !== null || !taxSystem) return;
    setCustomBusy(true);
    try {
      const next = await getDocumentItems(taxSystem, clientId);
      setCustomItems(next.items);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحميل بنود الأوراق.'), 'error');
    } finally {
      setCustomBusy(false);
    }
  };

  const toggleCustom = async (item: OfficeDocumentItemRow) => {
    const effective = item.client_included ?? item.included;
    setCustomBusy(true);
    try {
      const next = await setClientDocumentChoice(clientId, {
        item_code: item.item_code,
        included: !effective,
      });
      setCustomItems(next.items);
      toast('حُفظ خيار الزبون', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ خيار الزبون.'), 'error');
    } finally {
      setCustomBusy(false);
    }
  };

  if (loading && payload === null) {
    return <p className="text-[11.5px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>;
  }
  if (error) {
    return (
      <div>
        <p className="text-[12px] font-medium text-rose-600 dark:text-rose-400">{error}</p>
        <button type="button" onClick={load} className={`mt-2 ${officeSecondaryButtonClass}`}>
          أعد المحاولة
        </button>
      </div>
    );
  }
  if (!payload) return null;

  return (
    <div className="space-y-4">
      <OfficeCard
        title={`أوراق الزبون — ${payload.year}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
              السنة
              <select
                value={year}
                onChange={(event) => {
                  setSelected(null);
                  setYear(Number(event.target.value));
                }}
                className={`ms-1.5 ${officeInputClass}`}
              >
                {documentYearOptions(payload).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
            {canWrite && taxSystem ? (
              <button
                type="button"
                onClick={openCustomize}
                className={officeSecondaryButtonClass}
              >
                تخصيص القائمة
              </button>
            ) : null}
          </div>
        }
      >
        {/* دليلُ الألوان الأربعة — النصُّ من الخادم. */}
        <div className="flex flex-wrap items-center gap-1.5">
          {payload.status_choices.map((choice) => (
            <span
              key={choice.value}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${documentStatusChipClass(choice.value)}`}
            >
              {choice.label}
            </span>
          ))}
        </div>

        {months.length === 0 ? (
          <p className="mt-4 text-[11.5px] text-slate-500 dark:text-slate-400">
            {payload.annual.length === 0
              ? 'لا قائمةَ أوراقٍ لهذه السنة بعد — تُحفظ القائمةُ بعد انتهاء الشهر في «حدّث المكتب».'
              : 'لا صفوفَ شهرية لهذه السنة بعد.'}
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full table-fixed border-separate border-spacing-0">
              <thead>
                <tr>
                  <th className="w-[168px] border-b border-slate-200 pb-2 text-start text-[10.5px] font-medium text-slate-400 dark:border-slate-700 dark:text-slate-500">
                    البند
                  </th>
                  {months.map((month) => (
                    <th
                      key={month.iso}
                      className="border-b border-slate-200 pb-2 text-center text-[10.5px] font-medium text-slate-500 dark:border-slate-700 dark:text-slate-400"
                    >
                      {month.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gridRows.map((row) => (
                  <tr key={row.item_code}>
                    <th className="border-b border-slate-100 py-1.5 text-start text-[11.5px] font-medium text-slate-700 dark:border-slate-800 dark:text-slate-300">
                      {row.name}
                    </th>
                    {row.cells.map((cell) => {
                      const active = selected?.itemCode === row.item_code
                        && selected?.month === cell.month;
                      return (
                        <td
                          key={`${row.item_code}-${cell.month}`}
                          className="border-b border-slate-100 px-1 py-1.5 dark:border-slate-800"
                        >
                          <button
                            type="button"
                            disabled={cell.row_id === null}
                            onClick={() => setSelected({
                              itemCode: row.item_code,
                              month: cell.month,
                            })}
                            aria-label={documentCellTitle(cell)}
                            title={documentCellTitle(cell)}
                            className={`grid h-8 w-full place-items-center rounded-md border transition disabled:cursor-default ${documentCellClass(cell)} ${
                              active ? 'ring-2 ring-teal-500 dark:ring-teal-400' : ''
                            }`}
                          >
                            <span className="text-[11px] font-bold">
                              {documentCellGlyph(cell)}
                            </span>
                            {cell.files_count ? (
                              <span className="text-[9px] font-semibold tabular-nums">
                                {cell.files_count}
                              </span>
                            ) : null}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* سطرُ تفاصيل الخانة المختارة، وتحته ملفاتُها. */}
        {selectedCell && selectedCell.cell.row_id !== null ? (
          <div className="mt-3 space-y-3 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-900">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <p className="text-[11px] font-bold text-slate-900 dark:text-slate-100">
                {selectedCell.item.name}
                <span className="ms-1.5 font-medium text-slate-400">
                  · {selectedCell.cell.status_label}
                </span>
              </p>
              {selectedCell.cell.received_on ? (
                <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500 dark:text-slate-400">
                  <span>
                    وصلت
                    <b className="ms-1 font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                      {shortIsoDate(selectedCell.cell.received_on)}
                    </b>
                  </span>
                  <span>{selectedCell.cell.channel_label}</span>
                  {selectedCell.cell.received_by_name ? (
                    <span>
                      سجّلها
                      <b className="ms-1 font-semibold text-slate-700 dark:text-slate-200">
                        {selectedCell.cell.received_by_name}
                      </b>
                    </span>
                  ) : null}
                </p>
              ) : null}
              {canWrite ? (
                <div className="ms-auto flex flex-wrap items-center gap-1.5">
                  {statusChoices.map((choice) => (
                    <button
                      key={choice.value}
                      type="button"
                      disabled={saving}
                      onClick={() => chooseStatus(selectedCell.cell.row_id as number, choice.value)}
                      className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-600 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                    >
                      {choice.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            {pendingStatus ? (
              <div className="flex flex-wrap items-center gap-2 rounded-md bg-slate-50 px-2 py-1.5 dark:bg-slate-800">
                <span className="text-[10.5px] font-semibold text-slate-700 dark:text-slate-200">
                  كيف وصلت؟
                </span>
                {payload.channel_choices.map((choice) => (
                  <button
                    key={choice.value}
                    type="button"
                    disabled={saving}
                    onClick={() => applyStatus(
                      selectedCell.cell.row_id as number, pendingStatus, choice.value,
                    )}
                    className="rounded-full bg-teal-700 px-2.5 py-0.5 text-[10px] font-semibold text-white disabled:opacity-50"
                  >
                    {choice.label}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setPendingStatus(null)}
                  className="text-[10px] font-medium text-slate-500 dark:text-slate-400"
                >
                  إلغاء
                </button>
              </div>
            ) : null}

            <div>
              <p className="text-[10.5px] font-semibold text-slate-500 dark:text-slate-400">
                الملفات
              </p>
              {filesLoading ? (
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>
              ) : files.length === 0 ? (
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  لا ملفَّ مرفوعاً لهذه الورقة.
                </p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {files.map((file) => (
                    <li
                      key={file.id}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-slate-200 px-2 py-1 text-[10.5px] dark:border-slate-700"
                    >
                      <span className="font-semibold text-slate-800 dark:text-slate-200">
                        {file.document_type}
                      </span>
                      {file.document_number ? (
                        <span className="text-slate-500 dark:text-slate-400">
                          رقم {file.document_number}
                        </span>
                      ) : null}
                      {file.document_date ? (
                        <span className="text-slate-500 dark:text-slate-400">
                          بتاريخ {shortIsoDate(file.document_date)}
                        </span>
                      ) : null}
                      {documentFileTag(file) ? (
                        <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9.5px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                          {documentFileTag(file)}
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => openFile(file)}
                        className="ms-auto font-semibold text-teal-700 dark:text-teal-400"
                      >
                        افتح الملف
                      </button>
                      {canWrite ? (
                        <button
                          type="button"
                          onClick={() => removeFile(file)}
                          className="font-semibold text-rose-600 dark:text-rose-400"
                        >
                          احذف
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}

              {canWrite ? (
                <div className="mt-2 grid gap-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800 md:grid-cols-2">
                  <label className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                    الملف (PDF أو صورة، حتى ١٠ ميجابايت)
                    <input
                      ref={fileInput}
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,.webp"
                      className="mt-1 block w-full text-[10.5px]"
                    />
                  </label>
                  <label className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                    نوع المستند
                    <input
                      value={upload.document_type}
                      onChange={(event) => setUpload({ ...upload, document_type: event.target.value })}
                      placeholder={selectedCell.item.name}
                      className={`mt-1 w-full ${officeInputClass}`}
                    />
                  </label>
                  <label className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                    رقم تسجيل المُصدر
                    <input
                      value={upload.issuer_registration}
                      onChange={(event) => setUpload({ ...upload, issuer_registration: event.target.value })}
                      className={`mt-1 w-full ${officeInputClass}`}
                    />
                  </label>
                  <label className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                    رقم المستند
                    <input
                      value={upload.document_number}
                      onChange={(event) => setUpload({ ...upload, document_number: event.target.value })}
                      className={`mt-1 w-full ${officeInputClass}`}
                    />
                  </label>
                  <label className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                    تاريخ المستند
                    <input
                      type="date"
                      value={upload.document_date}
                      onChange={(event) => setUpload({ ...upload, document_date: event.target.value })}
                      className={`mt-1 w-full ${officeInputClass}`}
                    />
                  </label>
                  <label className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={upload.is_copy}
                      onChange={(event) => setUpload({ ...upload, is_copy: event.target.checked })}
                    />
                    صورة — الأصل عند الزبون
                  </label>
                  <div className="md:col-span-2">
                    <button
                      type="button"
                      onClick={sendUpload}
                      disabled={uploadBusy}
                      className={officePrimaryButtonClass}
                    >
                      {uploadBusy ? 'جارٍ الرفع…' : 'ارفع الملف'}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* الشريطُ الكهرمانيّ: ما ينقص آخرَ شهر. */}
        {missing ? (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900 dark:bg-amber-950/40">
            <p className="text-[11px] font-medium text-amber-800 dark:text-amber-200">
              ناقص لشهر {missing.monthLabel}: {missing.names.join(' + ')}
            </p>
            <span className="text-[10.5px] font-bold tabular-nums text-amber-700 dark:text-amber-300">
              {missing.counts}
            </span>
          </div>
        ) : null}

        {payload.retention.length ? (
          <p className="mt-3 border-t border-slate-100 pt-2 text-[10px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
            مددُ الحفظ:{' '}
            {payload.retention.map((rule) => rule.text).join(' · ')}
          </p>
        ) : null}
      </OfficeCard>

      {payload.annual.length ? (
        <OfficeCard title={`القائمة السنوية ${payload.year}`}>
          <div className="grid gap-3 md:grid-cols-3">
            {payload.annual.map((row) => (
              <div
                key={row.row_id}
                className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[12px] font-semibold text-slate-900 dark:text-slate-100">
                    {row.name}
                  </p>
                  <span className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    {row.status_label}
                  </span>
                </div>
                <p className="mt-1 text-[10.5px] text-slate-500 dark:text-slate-400">
                  {row.period_label}
                  {row.received_on
                    ? ` — وصلت ${shortIsoDate(row.received_on)}${row.channel_label ? ` · ${row.channel_label}` : ''}`
                    : ''}
                </p>
                {row.files && row.files.length ? (
                  <ul className="mt-1.5 space-y-1">
                    {row.files.map((file) => (
                      <li key={file.id} className="flex items-center gap-2 text-[10.5px]">
                        <button
                          type="button"
                          onClick={() => openFile(file)}
                          className="text-teal-700 dark:text-teal-400"
                        >
                          {file.document_type}
                        </button>
                        {canWrite ? (
                          <button
                            type="button"
                            onClick={() => removeFile(file)}
                            className="ms-auto text-rose-600 dark:text-rose-400"
                          >
                            احذف
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {canWrite ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {annualStatusChoices.map((choice) => (
                      <button
                        key={choice.value}
                        type="button"
                        disabled={saving}
                        onClick={() => chooseStatus(row.row_id, choice.value, true)}
                        className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-600 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                      >
                        {choice.label}
                      </button>
                    ))}
                  </div>
                ) : null}
                {annualPending && annualPending.rowId === row.row_id ? (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 rounded-md bg-slate-50 px-2 py-1 dark:bg-slate-800">
                    <span className="text-[10px] font-semibold text-slate-700 dark:text-slate-200">
                      كيف وصلت؟
                    </span>
                    {payload.channel_choices.map((choice) => (
                      <button
                        key={choice.value}
                        type="button"
                        disabled={saving}
                        onClick={() => applyStatus(
                          row.row_id, annualPending.status, choice.value,
                        )}
                        className="rounded-full bg-teal-700 px-2 py-0.5 text-[9.5px] font-semibold text-white disabled:opacity-50"
                      >
                        {choice.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </OfficeCard>
      ) : null}

      {customOpen ? (
        <OfficeCard title="تخصيص القائمة">
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            خيارُ الزبون يغلب قالبَ المكتب: بندٌ داخلٌ هنا يُطلب له ولو لم تنطبق
            شروطه، وخارجٌ لا يُطلب.
          </p>
          {customBusy && customItems === null ? (
            <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>
          ) : (
            <ul className="mt-2 grid gap-1.5 md:grid-cols-2">
              {(customItems ?? []).map((item) => {
                const effective = item.client_included ?? item.included;
                return (
                  <li
                    key={item.item_code}
                    className="flex items-center gap-2 rounded-md border border-slate-100 px-2 py-1 text-[11px] dark:border-slate-800"
                  >
                    <span className="font-medium text-slate-700 dark:text-slate-300">
                      {item.name}
                    </span>
                    <span className="text-[9.5px] text-slate-400 dark:text-slate-500">
                      {item.cadence_label}
                    </span>
                    <button
                      type="button"
                      disabled={customBusy}
                      onClick={() => toggleCustom(item)}
                      aria-pressed={effective}
                      className={`ms-auto rounded-full border px-2 py-0.5 text-[10px] font-semibold disabled:opacity-50 ${
                        effective
                          ? 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300'
                          : 'border-slate-200 text-slate-500 dark:border-slate-700 dark:text-slate-400'
                      }`}
                    >
                      {effective ? 'ضمن القائمة' : 'خارج القائمة'}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <button
            type="button"
            onClick={() => setCustomOpen(false)}
            className={`mt-3 ${officeSecondaryButtonClass}`}
          >
            إغلاق
          </button>
        </OfficeCard>
      ) : null}
    </div>
  );
};
