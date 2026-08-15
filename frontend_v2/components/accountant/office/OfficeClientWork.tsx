import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarPlus, CheckCircle2, FileUp, Paperclip, Pencil, Plus, Trash2 } from 'lucide-react';

import {
  createPracticeProgram,
  createPracticeTask,
  deletePracticeDocument,
  deletePracticeProgram,
  deletePracticeTask,
  listPracticeDocuments,
  listPracticePrograms,
  listPracticeTasks,
  updatePracticeProgram,
  updatePracticeTask,
  uploadPracticeDocument,
  type PracticeDocumentRecord,
  type PracticeProgramFrequency,
  type PracticeProgramRecord,
  type PracticeProgramStatus,
  type PracticeTaskKind,
  type PracticeTaskRecord,
} from '../../../services/accountantPracticeApi';
import { useConfirm } from '../../../contexts/ConfirmContext';
import { useToast } from '../../../contexts/ToastContext';
import { formatDateTimeValue, formatDateValue } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import {
  OfficeBadge,
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeField,
  OfficeInput,
  OfficeModal,
  OfficeSelect,
  OfficeSkeleton,
  OfficeTextarea,
} from './OfficeUi';

/**
 * أقسام العمل داخل ملف الزبون: برامج المراجعة، المستندات، المواعيد. الثلاثة
 * تشترك نمطاً واحداً — قائمة، نموذج إضافة، وحالة فارغة تقول ماذا يُفعل — وتعيش
 * هنا معاً كي لا تتشظّى قاعدة «كل حالة لها طريق عودة» على ثلاثة ملفات.
 */

export const PROGRAM_FREQUENCIES: Record<PracticeProgramFrequency, string> = {
  annual: 'سنوي',
  monthly: 'شهري',
  once: 'مرة واحدة',
};

export const PROGRAM_STATUSES: Record<PracticeProgramStatus, string> = {
  planned: 'مخطط',
  in_progress: 'قيد التنفيذ',
  done: 'منجز',
};

const PROGRAM_STATUS_TONES: Record<PracticeProgramStatus, string> = {
  planned: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
  in_progress: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  done: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
};

export const TASK_KINDS: Record<PracticeTaskKind, string> = {
  appointment: 'موعد',
  deadline: 'استحقاق',
};

/** رسالة الخادم عربية جاهزة؛ النص العام احتياطٌ لانقطاع الشبكة وحده. */
const failure = (caught: unknown, fallback: string) => (caught as Error)?.message || fallback;

/** ISO ← قيمة `datetime-local` بالتوقيت المحلي (لا UTC، وإلا انزاحت الساعة). */
const toLocalInput = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const defaultTaskDue = (): string => {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(9, 0, 0, 0);
  return toLocalInput(date.toISOString());
};

const overdueTone = (isOverdue: boolean) =>
  isOverdue ? 'text-red-700 dark:text-red-300 font-black' : 'text-slate-600 dark:text-slate-300';

// ── برامج المراجعة ───────────────────────────────────────────────────────────

type ProgramDraft = {
  service_type: string;
  frequency: PracticeProgramFrequency;
  team_note: string;
  due_date: string;
  status: PracticeProgramStatus;
  notes: string;
};

const ProgramForm: React.FC<{
  clientId: number;
  serviceTypes: string[];
  defaultDueDays: number;
  program?: PracticeProgramRecord;
  onClose: () => void;
  onSaved: () => void;
}> = ({ clientId, serviceTypes, defaultDueDays, program, onClose, onSaved }) => {
  const toast = useToast();
  const [draft, setDraft] = useState<ProgramDraft>({
    service_type: program?.service_type || serviceTypes[0] || '',
    frequency: program?.frequency || 'monthly',
    team_note: program?.team_note || '',
    due_date: program?.due_date || '',
    status: program?.status || 'planned',
    notes: program?.notes || '',
  });
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.service_type) {
      setError('اختر نوع الخدمة — تُعرَّف الأنواع في إعدادات المكتب.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const saved = program
        ? (await updatePracticeProgram(program.id, { ...draft, due_date: draft.due_date || null })).program
        : (await createPracticeProgram({
          client_id: clientId,
          ...draft,
          due_date: draft.due_date || undefined,
        })).program;
      // المرفق جزء من النموذج في الشاشة، لكنه رفعٌ مستقل بعد وجود البرنامج —
      // فشلُه لا يُلغي البرنامج المحفوظ، ويُقال صراحةً بدل أن يُبتلع.
      if (file) {
        try {
          await uploadPracticeDocument({ clientId, file, programId: saved.id });
        } catch (caught) {
          toast(failure(caught, 'حُفظ البرنامج، وتعذّر رفع المرفق.'), 'error');
        }
      }
      toast(program ? 'حُفظ البرنامج.' : 'أُضيف برنامج المراجعة.', 'success');
      onSaved();
    } catch (caught) {
      setError(failure(caught, 'تعذّر حفظ البرنامج.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <OfficeModal
      title={program ? 'تعديل برنامج مراجعة' : 'برنامج مراجعة جديد'}
      onClose={onClose}
      wide
      footer={(
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-slate-300 px-5 py-2.5 font-bold dark:border-slate-700">إلغاء</button>
          <button type="submit" form="office-program-form" disabled={saving} className="rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50">
            {saving ? 'جارٍ الحفظ…' : 'حفظ'}
          </button>
        </>
      )}
    >
      <form id="office-program-form" onSubmit={submit} className="space-y-4">
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}
        {serviceTypes.length === 0 && (
          <p className="rounded-xl bg-amber-50 p-3 text-sm font-bold text-amber-800">
            لا أنواع خدمات معرَّفة — أضفها من «إعدادات المكتب» أولاً.
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <OfficeField label="نوع الخدمة" required hint="الأنواع من إعدادات المكتب.">
            {(id) => (
              <OfficeSelect id={id} value={draft.service_type} onChange={(event) => setDraft({ ...draft, service_type: event.target.value })}>
                <option value="">— اختر —</option>
                {serviceTypes.map((type) => <option key={type} value={type}>{type}</option>)}
              </OfficeSelect>
            )}
          </OfficeField>
          <OfficeField label="توقيت تقديم الخدمة">
            {(id) => (
              <OfficeSelect id={id} value={draft.frequency} onChange={(event) => setDraft({ ...draft, frequency: event.target.value as PracticeProgramFrequency })}>
                {Object.entries(PROGRAM_FREQUENCIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </OfficeSelect>
            )}
          </OfficeField>
          <OfficeField label="الفريق المكلّف بالبرنامج">
            {(id) => <OfficeInput id={id} value={draft.team_note} onChange={(event) => setDraft({ ...draft, team_note: event.target.value })} />}
          </OfficeField>
          <OfficeField
            label="موعد الانتهاء"
            hint={draft.due_date ? undefined : `إن تُرك فارغاً يُحسب تلقائياً بعد ${formatNumber(defaultDueDays)} يوماً من اليوم.`}
          >
            {(id) => <OfficeInput id={id} type="date" value={draft.due_date} onChange={(event) => setDraft({ ...draft, due_date: event.target.value })} />}
          </OfficeField>
          <OfficeField label="الحالة">
            {(id) => (
              <OfficeSelect id={id} value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as PracticeProgramStatus })}>
                {Object.entries(PROGRAM_STATUSES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </OfficeSelect>
            )}
          </OfficeField>
          <OfficeField label="مرفق (تقرير الفترة السابقة مثلاً)" hint="اختياري — ويمكن رفع غيره لاحقاً من «المستندات».">
            {(id) => (
              <OfficeInput
                id={id}
                type="file"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
                className="file:ml-3 file:rounded-lg file:border-0 file:bg-slate-200 file:px-3 file:py-1.5 file:text-sm file:font-bold dark:file:bg-slate-800 dark:file:text-slate-200"
              />
            )}
          </OfficeField>
        </div>
        <OfficeField label="ملاحظات">
          {(id) => <OfficeTextarea id={id} rows={3} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} />}
        </OfficeField>
      </form>
    </OfficeModal>
  );
};

export const ProgramsPanel: React.FC<{
  clientId: number;
  serviceTypes: string[];
  defaultDueDays: number;
  onChanged?: () => void;
}> = ({ clientId, serviceTypes, defaultDueDays, onChanged }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [programs, setPrograms] = useState<PracticeProgramRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState<{ open: boolean; program?: PracticeProgramRecord }>({ open: false });

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listPracticePrograms({ clientId })
      .then((res) => setPrograms(res.results))
      .catch(() => setError('تعذّر تحميل برامج المراجعة.'))
      .finally(() => setLoading(false));
  }, [clientId]);

  useEffect(load, [load]);

  const setStatus = async (program: PracticeProgramRecord, status: PracticeProgramStatus) => {
    try {
      await updatePracticeProgram(program.id, { status });
      load();
      onChanged?.();
    } catch (caught) {
      toast(failure(caught, 'تعذّر تغيير حالة البرنامج.'), 'error');
    }
  };

  const remove = async (program: PracticeProgramRecord) => {
    const ok = await confirm({
      title: 'حذف البرنامج',
      message: `سيُحذف برنامج «${program.service_type}» نهائياً. المستندات المرفقة به تبقى في ملف الزبون.`,
      confirmText: 'حذف',
    });
    if (!ok) return;
    try {
      await deletePracticeProgram(program.id);
      toast('حُذف البرنامج.', 'success');
      load();
      onChanged?.();
    } catch (caught) {
      toast(failure(caught, 'تعذّر حذف البرنامج.'), 'error');
    }
  };

  return (
    <>
      <OfficeCard
        title={`برامج المراجعة (${formatNumber(programs.length)})`}
        actions={(
          <button type="button" onClick={() => setForm({ open: true })} className="flex items-center gap-2 rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">
            <Plus className="h-4 w-4" />برنامج جديد
          </button>
        )}
      >
        {loading ? <OfficeSkeleton rows={3} /> : error ? <OfficeError message={error} onRetry={load} /> : programs.length === 0 ? (
          <OfficeEmpty title="لا برامج بعد" hint="البرنامج يربط الخدمة بموعدها، فتظهر في «المواعيد والمهام» تلقائياً." />
        ) : (
          <ul className="space-y-3">
            {programs.map((program) => (
              <li key={program.id} className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-black text-slate-900 dark:text-white">{program.service_type}</p>
                    <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                      {PROGRAM_FREQUENCIES[program.frequency]}
                      {program.team_note && ` · الفريق: ${program.team_note}`}
                    </p>
                    {program.notes && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{program.notes}</p>}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <OfficeBadge tone={PROGRAM_STATUS_TONES[program.status]}>{PROGRAM_STATUSES[program.status]}</OfficeBadge>
                    <span className={`text-sm ${overdueTone(program.is_overdue)}`}>
                      {program.due_date
                        ? `${program.is_overdue ? 'تأخّر منذ' : 'ينتهي في'} ${formatDateValue(program.due_date)}`
                        : 'بلا موعد'}
                    </span>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {program.status !== 'done' && (
                    <button type="button" onClick={() => void setStatus(program, program.status === 'planned' ? 'in_progress' : 'done')} className="flex items-center gap-1.5 rounded-lg border border-emerald-600 px-3 py-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-300">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {program.status === 'planned' ? 'ابدأ التنفيذ' : 'أنجِز'}
                    </button>
                  )}
                  {program.status === 'done' && (
                    <button type="button" onClick={() => void setStatus(program, 'in_progress')} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold dark:border-slate-700">
                      أعِد فتحه
                    </button>
                  )}
                  <button type="button" onClick={() => setForm({ open: true, program })} className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold dark:border-slate-700">
                    <Pencil className="h-3.5 w-3.5" />تعديل
                  </button>
                  <button type="button" onClick={() => void remove(program)} className="flex items-center gap-1.5 rounded-lg border border-red-300 px-3 py-1.5 text-xs font-bold text-red-700" >
                    <Trash2 className="h-3.5 w-3.5" />حذف
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </OfficeCard>

      {form.open && (
        <ProgramForm
          clientId={clientId}
          serviceTypes={serviceTypes}
          defaultDueDays={defaultDueDays}
          program={form.program}
          onClose={() => setForm({ open: false })}
          onSaved={() => { setForm({ open: false }); load(); onChanged?.(); }}
        />
      )}
    </>
  );
};

// ── المستندات ────────────────────────────────────────────────────────────────

export const DocumentsPanel: React.FC<{ clientId: number }> = ({ clientId }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [documents, setDocuments] = useState<PracticeDocumentRecord[]>([]);
  const [programs, setPrograms] = useState<PracticeProgramRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [programId, setProgramId] = useState('');
  const [uploading, setUploading] = useState(false);
  // إعادة بناء حقل الملف بعد الرفع — بلا مفتاح متغيّر يبقى اسم الملف القديم معروضاً.
  const [fileKey, setFileKey] = useState(0);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([listPracticeDocuments({ clientId }), listPracticePrograms({ clientId })])
      .then(([documentsRes, programsRes]) => {
        setDocuments(documentsRes.results);
        setPrograms(programsRes.results);
      })
      .catch(() => setError('تعذّر تحميل مستندات الزبون.'))
      .finally(() => setLoading(false));
  }, [clientId]);

  useEffect(load, [load]);

  const programName = useMemo(
    () => new Map(programs.map((program) => [program.id, program.service_type])),
    [programs],
  );

  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    try {
      await uploadPracticeDocument({
        clientId,
        file,
        name: name.trim() || undefined,
        programId: programId ? Number(programId) : null,
      });
      toast('رُفع المستند إلى ملف الزبون.', 'success');
      setFile(null);
      setName('');
      setProgramId('');
      setFileKey((key) => key + 1);
      load();
    } catch (caught) {
      toast(failure(caught, 'تعذّر رفع المستند.'), 'error');
    } finally {
      setUploading(false);
    }
  };

  const remove = async (document: PracticeDocumentRecord) => {
    const ok = await confirm({
      title: 'حذف المستند',
      message: `سيُحذف «${document.name}» من ملف الزبون.`,
      confirmText: 'حذف',
    });
    if (!ok) return;
    try {
      await deletePracticeDocument(document.id);
      toast('حُذف المستند.', 'success');
      load();
    } catch (caught) {
      toast(failure(caught, 'تعذّر حذف المستند.'), 'error');
    }
  };

  return (
    <div className="space-y-5">
      <OfficeCard title="رفع مستند">
        <form onSubmit={upload} className="grid items-end gap-4 sm:grid-cols-4">
          <OfficeField label="الملف" required className="sm:col-span-2">
            {(id) => (
              <OfficeInput
                key={fileKey}
                id={id}
                type="file"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
                className="file:ml-3 file:rounded-lg file:border-0 file:bg-slate-200 file:px-3 file:py-1.5 file:text-sm file:font-bold dark:file:bg-slate-800 dark:file:text-slate-200"
              />
            )}
          </OfficeField>
          <OfficeField label="الاسم" hint="يُترك فارغاً ⇒ اسم الملف.">
            {(id) => <OfficeInput id={id} value={name} onChange={(event) => setName(event.target.value)} />}
          </OfficeField>
          <OfficeField label="مرتبط ببرنامج">
            {(id) => (
              <OfficeSelect id={id} value={programId} onChange={(event) => setProgramId(event.target.value)}>
                <option value="">— بلا برنامج —</option>
                {programs.map((program) => <option key={program.id} value={program.id}>{program.service_type}</option>)}
              </OfficeSelect>
            )}
          </OfficeField>
          <button type="submit" disabled={!file || uploading} className="flex items-center justify-center gap-2 rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50 sm:col-span-4 sm:w-fit">
            <FileUp className="h-4 w-4" />{uploading ? 'جارٍ الرفع…' : 'ارفع'}
          </button>
        </form>
      </OfficeCard>

      <OfficeCard title={`مستندات الزبون (${formatNumber(documents.length)})`}>
        {loading ? <OfficeSkeleton rows={3} /> : error ? <OfficeError message={error} onRetry={load} /> : documents.length === 0 ? (
          <OfficeEmpty title="لا مستندات بعد" hint="ارفع عقداً أو تقريراً سابقاً ليبقى في ملف الزبون." />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {documents.map((document) => (
              <li key={document.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <a href={document.url} target="_blank" rel="noreferrer" className="flex items-center gap-2 font-bold text-indigo-700 hover:underline dark:text-indigo-300">
                    <Paperclip className="h-4 w-4" />{document.name}
                  </a>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {formatDateTimeValue(document.uploaded_at)}
                    {document.program_id && ` · ${programName.get(document.program_id) || 'برنامج'}`}
                  </p>
                </div>
                <button type="button" onClick={() => void remove(document)} aria-label={`حذف ${document.name}`} className="rounded-lg border border-red-300 p-2 text-red-700">
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </OfficeCard>
    </div>
  );
};

// ── المواعيد والمهام ─────────────────────────────────────────────────────────

const TaskForm: React.FC<{
  clientId?: number;
  clients: { id: number; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}> = ({ clientId, clients, onClose, onSaved }) => {
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [dueAt, setDueAt] = useState(defaultTaskDue());
  const [kind, setKind] = useState<PracticeTaskKind>('appointment');
  const [client, setClient] = useState(clientId ? String(clientId) : '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setError('عنوان الموعد مطلوب.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await createPracticeTask({
        title: title.trim(),
        due_at: dueAt,
        kind,
        client_id: client ? Number(client) : null,
      });
      toast('أُضيف الموعد إلى أجندة المكتب.', 'success');
      onSaved();
    } catch (caught) {
      setError(failure(caught, 'تعذّر حفظ الموعد.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <OfficeModal
      title="موعد جديد"
      onClose={onClose}
      footer={(
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-slate-300 px-5 py-2.5 font-bold dark:border-slate-700">إلغاء</button>
          <button type="submit" form="office-task-form" disabled={saving} className="rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50">
            {saving ? 'جارٍ الحفظ…' : 'حفظ'}
          </button>
        </>
      )}
    >
      <form id="office-task-form" onSubmit={submit} className="space-y-4">
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}
        <OfficeField label="العنوان" required>
          {(id) => <OfficeInput id={id} value={title} onChange={(event) => setTitle(event.target.value)} autoFocus />}
        </OfficeField>
        <div className="grid gap-4 sm:grid-cols-2">
          <OfficeField label="الموعد" required>
            {(id) => <OfficeInput id={id} type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />}
          </OfficeField>
          <OfficeField label="النوع">
            {(id) => (
              <OfficeSelect id={id} value={kind} onChange={(event) => setKind(event.target.value as PracticeTaskKind)}>
                {Object.entries(TASK_KINDS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </OfficeSelect>
            )}
          </OfficeField>
        </div>
        {clientId === undefined && (
          <OfficeField label="الزبون" hint="اختياري — موعد المكتب لا يلزمه زبون.">
            {(id) => (
              <OfficeSelect id={id} value={client} onChange={(event) => setClient(event.target.value)}>
                <option value="">— بلا زبون —</option>
                {clients.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </OfficeSelect>
            )}
          </OfficeField>
        )}
      </form>
    </OfficeModal>
  );
};

export const TasksPanel: React.FC<{
  clientId?: number;
  clients?: { id: number; name: string }[];
  onChanged?: () => void;
}> = ({ clientId, clients = [], onChanged }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [tasks, setTasks] = useState<PracticeTaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showDone, setShowDone] = useState(false);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listPracticeTasks({ clientId, status: showDone ? undefined : 'open' })
      .then((res) => setTasks(res.results))
      .catch(() => setError('تعذّر تحميل المواعيد.'))
      .finally(() => setLoading(false));
  }, [clientId, showDone]);

  useEffect(load, [load]);

  const toggle = async (task: PracticeTaskRecord) => {
    try {
      await updatePracticeTask(task.id, { status: task.status === 'done' ? 'open' : 'done' });
      load();
      onChanged?.();
    } catch (caught) {
      toast(failure(caught, 'تعذّر تحديث الموعد.'), 'error');
    }
  };

  const remove = async (task: PracticeTaskRecord) => {
    const ok = await confirm({ title: 'حذف الموعد', message: `سيُحذف «${task.title}».`, confirmText: 'حذف' });
    if (!ok) return;
    try {
      await deletePracticeTask(task.id);
      toast('حُذف الموعد.', 'success');
      load();
      onChanged?.();
    } catch (caught) {
      toast(failure(caught, 'تعذّر حذف الموعد.'), 'error');
    }
  };

  return (
    <>
      <OfficeCard
        title={`المواعيد (${formatNumber(tasks.length)})`}
        actions={(
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm font-bold text-slate-600 dark:text-slate-300">
              <input type="checkbox" checked={showDone} onChange={(event) => setShowDone(event.target.checked)} className="h-4 w-4" />
              أظهر المنجزة
            </label>
            <button type="button" onClick={() => setFormOpen(true)} className="flex items-center gap-2 rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">
              <CalendarPlus className="h-4 w-4" />موعد جديد
            </button>
          </div>
        )}
      >
        {loading ? <OfficeSkeleton rows={3} /> : error ? <OfficeError message={error} onRetry={load} /> : tasks.length === 0 ? (
          <OfficeEmpty title="لا مواعيد مفتوحة" hint="أضف موعداً ليظهر في «مواعيد قريبة» على لوحة المكتب." />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {tasks.map((task) => (
              <li key={task.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className={`font-bold ${task.status === 'done' ? 'text-slate-400 line-through' : 'text-slate-900 dark:text-white'}`}>
                    {task.title}
                  </p>
                  <p className={`mt-1 text-xs ${overdueTone(task.is_overdue)}`}>
                    {TASK_KINDS[task.kind]} · {formatDateTimeValue(task.due_at)}
                    {task.client_name && ` · ${task.client_name}`}
                    {task.is_overdue && ' · متأخّر'}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={() => void toggle(task)} className="rounded-lg border border-emerald-600 px-3 py-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-300">
                    {task.status === 'done' ? 'أعِد فتحه' : 'أنجِز'}
                  </button>
                  <button type="button" onClick={() => void remove(task)} aria-label={`حذف ${task.title}`} className="rounded-lg border border-red-300 p-2 text-red-700">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </OfficeCard>

      {formOpen && (
        <TaskForm
          clientId={clientId}
          clients={clients}
          onClose={() => setFormOpen(false)}
          onSaved={() => { setFormOpen(false); load(); onChanged?.(); }}
        />
      )}
    </>
  );
};
