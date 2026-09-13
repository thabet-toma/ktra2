import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { useToast } from '../../../../contexts/ToastContext';
import { formatDateValue } from '../../../../utils/formatDate';
import { formatNumber } from '../../../../utils/formatNumber';
import {
  acceptPlatformTaskAssignment,
  claimPlatformTask,
  createPlatformWorkspaceNote,
  getPlatformTask,
  listPlatformEmployeeNotes,
  listPlatformTaskAssignments,
  listPlatformTaskSubmissions,
  listPlatformTasks,
  listPlatformWorkspaceNotes,
  submitPlatformTaskAssignment,
  type PlatformEmployeeNote,
  type PlatformTask,
  type PlatformTaskAssignment,
  type PlatformTaskSubmission,
  type PlatformWorkspaceNote,
} from '../../../../services/platformTasksApi';

const messageOf = (caught: unknown, fallback: string) => caught instanceof Error ? caught.message : fallback;
const dateLabel = (value: string | null | undefined) => value ? formatDateValue(value) : '—';

export const StaffTasksPanel: React.FC = () => {
  const toast = useToast();
  const [tasks, setTasks] = useState<PlatformTask[]>([]);
  const [assignments, setAssignments] = useState<PlatformTaskAssignment[]>([]);
  const [submissions, setSubmissions] = useState<PlatformTaskSubmission[]>([]);
  const [employeeNotes, setEmployeeNotes] = useState<PlatformEmployeeNote[]>([]);
  const [workspaceNotes, setWorkspaceNotes] = useState<PlatformWorkspaceNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [submissionBodies, setSubmissionBodies] = useState<Record<number, string>>({});
  const [noteBody, setNoteBody] = useState('');
  const [noteTask, setNoteTask] = useState('');
  const [noteBusy, setNoteBusy] = useState(false);
  const [selectedTask, setSelectedTask] = useState<PlatformTask | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextTasks, nextAssignments, nextSubmissions, nextEmployeeNotes, nextWorkspaceNotes] = await Promise.all([
        listPlatformTasks(), listPlatformTaskAssignments(), listPlatformTaskSubmissions(), listPlatformEmployeeNotes(), listPlatformWorkspaceNotes(),
      ]);
      setTasks(nextTasks); setAssignments(nextAssignments); setSubmissions(nextSubmissions); setEmployeeNotes(nextEmployeeNotes); setWorkspaceNotes(nextWorkspaceNotes);
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر تحميل مهامك الداخلية.'), 'error');
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { void load(); }, [load]);

  const assignmentsByTask = useMemo(() => new Map(assignments.map((assignment) => [assignment.task, assignment])), [assignments]);
  const openTasks = useMemo(() => tasks.filter((task) => task.audience === 'OPEN' && !assignmentsByTask.has(task.id)), [assignmentsByTask, tasks]);
  const reviewFor = (assignment: PlatformTaskAssignment) => submissions.find((submission) => submission.task === assignment.task && submission.decision);

  const accept = async (assignment: PlatformTaskAssignment) => {
    setBusy(assignment.id);
    try { await acceptPlatformTaskAssignment(assignment.id); toast('تم قبول المهمة.', 'success'); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر قبول المهمة.'), 'error'); }
    finally { setBusy(null); }
  };
  const submit = async (assignment: PlatformTaskAssignment) => {
    setBusy(assignment.id);
    try { await submitPlatformTaskAssignment(assignment.id, submissionBodies[assignment.id] || ''); toast('تم تسليم المهمة للمراجعة.', 'success'); setSubmissionBodies((items) => ({ ...items, [assignment.id]: '' })); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر تسليم المهمة.'), 'error'); }
    finally { setBusy(null); }
  };
  const claim = async (task: PlatformTask) => {
    setBusy(task.id);
    try { await claimPlatformTask(task.id); toast('تم استلام المهمة من المجمّع.', 'success'); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر استلام المهمة؛ قد يكون حد المطالبات اكتمل.'), 'error'); }
    finally { setBusy(null); }
  };
  const showTask = async (id: number) => {
    setBusy(id);
    try { setSelectedTask(await getPlatformTask(id)); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر فتح تفاصيل المهمة.'), 'error'); }
    finally { setBusy(null); }
  };
  const saveNote = async (event: React.FormEvent) => {
    event.preventDefault(); if (!noteBody.trim()) return;
    setNoteBusy(true);
    try { await createPlatformWorkspaceNote(noteBody, noteTask ? Number(noteTask) : null); toast('تمت إضافة الملاحظة.', 'success'); setNoteBody(''); setNoteTask(''); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر حفظ الملاحظة.'), 'error'); }
    finally { setNoteBusy(false); }
  };

  return <div className="space-y-6" dir="rtl">
    <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-bold text-[var(--staff-text)]">مهامّي الداخليّة</h2><p className="mt-1 text-sm text-[var(--staff-muted)]">اقبل المهمة، سجّل ملاحظات التسليم، وراجع رد المدير هنا.</p></div><button type="button" onClick={() => void load()} disabled={loading} className="rounded-xl border border-[var(--staff-line)] px-3 py-2 text-sm text-[var(--staff-text)] disabled:opacity-50">تحديث</button></div>
      {loading ? <p className="text-sm text-[var(--staff-muted)]">جارٍ التحميل...</p> : assignments.length === 0 ? <p className="text-sm text-[var(--staff-muted)]">لا توجد مهام مسندة إليك الآن.</p> : <div className="space-y-3">{assignments.map((assignment) => {
        const review = reviewFor(assignment); const canSubmit = ['ACCEPTED', 'IN_PROGRESS', 'RETURNED'].includes(assignment.status);
        return <article key={assignment.id} className="rounded-xl border border-[var(--staff-line)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-bold text-[var(--staff-text)]">{assignment.task_title}</h3><p className="mt-1 text-xs text-[var(--staff-muted)]">الحالة: {assignment.status_display} · الإسناد #{formatNumber(assignment.id)}</p></div><button type="button" onClick={() => void showTask(assignment.task)} disabled={busy === assignment.task} className="text-xs text-cyan-300 underline disabled:opacity-50">التفاصيل</button></div>
          {review && <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-[var(--staff-text)]"><p className="font-semibold">قرار المدير: {review.decision_display}</p>{review.reviewer_notes && <p className="mt-1 text-[var(--staff-muted)]">ملاحظته: {review.reviewer_notes}</p>}</div>}
          {assignment.status === 'OFFERED' && <button type="button" onClick={() => void accept(assignment)} disabled={busy === assignment.id} className="mt-3 rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-50">{busy === assignment.id ? 'جارٍ القبول...' : 'أقبلها'}</button>}
          {canSubmit && <form onSubmit={(event) => { event.preventDefault(); void submit(assignment); }} className="mt-3 space-y-2"><label className="block text-sm text-[var(--staff-text)]">ملاحظات التسليم <span className="text-[var(--staff-muted)]">(اختيارية)</span><textarea value={submissionBodies[assignment.id] || ''} onChange={(event) => setSubmissionBodies((items) => ({ ...items, [assignment.id]: event.target.value }))} className="mt-1 min-h-20 w-full rounded-lg border border-[var(--staff-line)] bg-black/10 p-2 text-sm text-[var(--staff-text)]" /></label><button type="submit" disabled={busy === assignment.id} className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-50">{busy === assignment.id ? 'جارٍ التسليم...' : 'أسلّم المهمة'}</button></form>}
          {assignment.status === 'SUBMITTED' && <p className="mt-3 text-sm text-amber-300">بانتظار مراجعة المدير.</p>}
        </article>;
      })}</div>}
      {selectedTask && <div className="mt-4 rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-4"><div className="flex items-start justify-between gap-3"><div><h3 className="font-bold text-[var(--staff-text)]">{selectedTask.title}</h3><p className="mt-1 text-sm text-[var(--staff-muted)]">{selectedTask.description || 'لا يوجد وصف.'}</p><p className="mt-2 text-xs text-[var(--staff-muted)]">الاستحقاق: {dateLabel(selectedTask.due_date)}</p></div><button type="button" onClick={() => setSelectedTask(null)} className="text-sm text-cyan-300">إغلاق</button></div></div>}
    </section>

    <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><h2 className="text-lg font-bold text-[var(--staff-text)]">مهام المجمّع المتاحة</h2><p className="mt-1 text-sm text-[var(--staff-muted)]">تستطيع استلام المهمة التي تركها المدير متاحة للموظفين.</p><div className="mt-4 space-y-3">{openTasks.length === 0 ? <p className="text-sm text-[var(--staff-muted)]">لا توجد مهمة مجمّع متاحة.</p> : openTasks.map((task) => { const isFull = task.claim_limit !== null && task.claimed_count >= task.claim_limit; return <article key={task.id} className="rounded-xl border border-[var(--staff-line)] p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-bold text-[var(--staff-text)]">{task.title}</h3><p className="mt-1 text-xs text-[var(--staff-muted)]">طالب بها {formatNumber(task.claimed_count)}{task.claim_limit === null ? '' : ` من حد ${formatNumber(task.claim_limit)}`} · الحالة: {task.status_display} · الاستحقاق: {dateLabel(task.due_date)}</p></div>{isFull ? <p className="text-sm font-bold text-amber-300">بلغت حدَّ المطالبين.</p> : <button type="button" onClick={() => void claim(task)} disabled={busy === task.id} className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-50">{busy === task.id ? 'جارٍ الاستلام...' : 'أستلمها'}</button>}</div></article>; })}</div></section>

    <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><h2 className="text-lg font-bold text-[var(--staff-text)]">سجلّ تسليماتي وقرارات المدير</h2><p className="mt-1 text-sm text-[var(--staff-muted)]">رفض تسليم مهمة المجمّع يعيدها إلى المجمّع ويسحب إسنادك، فيبقى القرار وملاحظته هنا.</p><div className="mt-4 space-y-3">{submissions.length === 0 ? <p className="text-sm text-[var(--staff-muted)]">لم تسلّم مهمة بعد.</p> : submissions.map((submission) => <article key={submission.id} className="rounded-xl border border-[var(--staff-line)] p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold text-[var(--staff-text)]">{submission.task_title}</h3><span className="text-xs text-[var(--staff-muted)]">{dateLabel(submission.created_at)}</span></div><p className="mt-2 text-sm text-[var(--staff-muted)]">تسليمي: {submission.body || 'سلّمتها بلا ملاحظات.'}</p>{submission.decision ? <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm"><p className="font-semibold text-[var(--staff-text)]">قرار المدير: {submission.decision_display}{submission.reviewer_name ? ` — ${submission.reviewer_name}` : ''}</p>{submission.reviewer_notes && <p className="mt-1 text-[var(--staff-muted)]">ملاحظته: {submission.reviewer_notes}</p>}</div> : <p className="mt-3 text-sm text-amber-300">بانتظار مراجعة المدير.</p>}</article>)}</div></section>

    <section className="grid gap-6 lg:grid-cols-2"><div className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><h2 className="text-lg font-bold text-[var(--staff-text)]">ملاحظاتي في مساحة العمل</h2><form onSubmit={saveNote} className="mt-4 space-y-3"><label className="block text-sm text-[var(--staff-text)]">المهمة <select value={noteTask} onChange={(event) => setNoteTask(event.target.value)} className="mt-1 w-full rounded-lg border border-[var(--staff-line)] bg-black/10 p-2 text-[var(--staff-text)]"><option value="">ملاحظة عمومية</option>{assignments.map((assignment) => <option key={assignment.id} value={assignment.task}>{assignment.task_title}</option>)}</select></label><label className="block text-sm text-[var(--staff-text)]">الملاحظة<textarea required value={noteBody} onChange={(event) => setNoteBody(event.target.value)} className="mt-1 min-h-24 w-full rounded-lg border border-[var(--staff-line)] bg-black/10 p-2 text-[var(--staff-text)]" /></label><button type="submit" disabled={noteBusy} className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-50">{noteBusy ? 'جارٍ الحفظ...' : 'أضف ملاحظة'}</button></form><div className="mt-4 space-y-2">{workspaceNotes.map((note) => <p key={note.id} className="rounded-lg border border-[var(--staff-line)] p-3 text-sm text-[var(--staff-text)]">{note.body}<span className="mr-2 text-xs text-[var(--staff-muted)]">{dateLabel(note.created_at)}</span></p>)}</div></div>
      <div className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><h2 className="text-lg font-bold text-[var(--staff-text)]">ملاحظات المدير عليّ</h2><div className="mt-4 space-y-3">{employeeNotes.length === 0 ? <p className="text-sm text-[var(--staff-muted)]">لا توجد ملاحظات ظاهرة لك.</p> : employeeNotes.map((note) => <article key={note.id} className="rounded-xl border border-[var(--staff-line)] p-3"><p className="text-sm text-[var(--staff-text)]">{note.body}</p><p className="mt-2 text-xs text-[var(--staff-muted)]">{note.author_name} · {dateLabel(note.created_at)}</p></article>)}</div></div></section>
  </div>;
};
