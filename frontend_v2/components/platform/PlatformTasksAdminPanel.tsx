import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../contexts/ConfirmContext';
import { useToast } from '../../contexts/ToastContext';
import { formatDateTimeValue, formatDateValue } from '../../utils/formatDate';
import { formatNumber } from '../../utils/formatNumber';
import {
  createPlatformEmployeeNote,
  createPlatformTask,
  listPlatformEmployeeNotes,
  listPlatformEmployees,
  listPlatformTaskAssignments,
  listPlatformTaskSubmissions,
  listPlatformTasks,
  listPlatformWorkspaceNotes,
  reviewPlatformTaskSubmission,
  type PlatformEmployee,
  type PlatformEmployeeNote,
  type PlatformEmployeeNoteVisibility,
  type PlatformTask,
  type PlatformTaskAssignment,
  type PlatformTaskAudience,
  type PlatformTaskPriority,
  type PlatformTaskReviewDecision,
  type PlatformTaskSubmission,
  type PlatformWorkspaceNote,
} from '../../services/platformTasksApi';

const messageOf = (caught: unknown, fallback: string) => caught instanceof Error ? caught.message : fallback;
const dateLabel = (value: string | null | undefined) => value ? formatDateValue(value) : '—';
const audienceOptions: Array<{ value: PlatformTaskAudience; label: string }> = [
  { value: 'INDIVIDUAL', label: 'موظف واحد' }, { value: 'SPECIFIC', label: 'موظفون محددون' }, { value: 'ALL', label: 'كل الموظفين' }, { value: 'OPEN', label: 'يختار الموظف' },
];

export const PlatformTasksAdminPanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [tasks, setTasks] = useState<PlatformTask[]>([]);
  const [assignments, setAssignments] = useState<PlatformTaskAssignment[]>([]);
  const [submissions, setSubmissions] = useState<PlatformTaskSubmission[]>([]);
  const [employees, setEmployees] = useState<PlatformEmployee[]>([]);
  // ملاحظاتُ المدير وملاحظاتُ الموظّفين **تُقرأ هنا**: لوحةٌ تكتب ولا تقرأ تُخفي
  // `MANAGER_ONLY` عن الجهة الوحيدة التي كُتبت لها، وتُخفي ملاحظةَ الموظّف على
  // مهمّته عن الجهة التي وُجدت لتقرأها.
  const [managerNotes, setManagerNotes] = useState<PlatformEmployeeNote[]>([]);
  const [staffNotes, setStaffNotes] = useState<PlatformWorkspaceNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [noteSaving, setNoteSaving] = useState(false);
  const [title, setTitle] = useState(''); const [description, setDescription] = useState(''); const [priority, setPriority] = useState<PlatformTaskPriority>('MEDIUM'); const [dueDate, setDueDate] = useState(''); const [audience, setAudience] = useState<PlatformTaskAudience>('INDIVIDUAL'); const [employeeIds, setEmployeeIds] = useState<string[]>([]); const [claimLimit, setClaimLimit] = useState('');
  const [selectedSubmission, setSelectedSubmission] = useState<PlatformTaskSubmission | null>(null); const [reviewDecision, setReviewDecision] = useState<PlatformTaskReviewDecision>('APPROVED_FULL'); const [reviewNotes, setReviewNotes] = useState('');
  const [noteEmployee, setNoteEmployee] = useState(''); const [noteBody, setNoteBody] = useState(''); const [visibility, setVisibility] = useState<PlatformEmployeeNoteVisibility>('EMPLOYEE');
  // المهمّةُ المفتوحة **بمعرّفها لا بنسختها**: بعد كلّ `load()` تُشتقُّ من القائمة
  // الجديدة، فلا يبقى الدرجُ يعرض عنواناً أو حالةً قديمة بعد إضافة ملاحظة.
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [taskNoteEmployee, setTaskNoteEmployee] = useState(''); const [taskNoteBody, setTaskNoteBody] = useState(''); const [taskNoteVisibility, setTaskNoteVisibility] = useState<PlatformEmployeeNoteVisibility>('EMPLOYEE'); const [taskNoteSaving, setTaskNoteSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const [nextTasks, nextAssignments, nextSubmissions, nextEmployees, nextManagerNotes, nextStaffNotes] = await Promise.all([listPlatformTasks(), listPlatformTaskAssignments(), listPlatformTaskSubmissions(), listPlatformEmployees(), listPlatformEmployeeNotes(), listPlatformWorkspaceNotes()]); setTasks(nextTasks); setAssignments(nextAssignments); setSubmissions(nextSubmissions); setEmployees(nextEmployees); setManagerNotes(nextManagerNotes); setStaffNotes(nextStaffNotes); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر تحميل إدارة المهام.'), 'error'); }
    finally { setLoading(false); }
  }, [toast]);
  useEffect(() => { void load(); }, [load]);

  const assignmentsFor = (taskId: number) => assignments.filter((assignment) => assignment.task === taskId);
  const pendingSubmissions = useMemo(() => submissions.filter((submission) => !submission.decision), [submissions]);
  const notesRequired = reviewDecision === 'APPROVED_PARTIAL' || reviewDecision === 'REJECTED';
  const employeeLabel = (employee: PlatformEmployee) => employee.status === 'ACTIVE' ? employee.username : `${employee.username} (${employee.status === 'SUSPENDED' ? 'موقوف' : 'خارج الخدمة'})`;
  const shownManagerNotes = useMemo(() => noteEmployee ? managerNotes.filter((note) => note.employee === Number(noteEmployee)) : managerNotes, [managerNotes, noteEmployee]);
  const selectSubmission = (submission: PlatformTaskSubmission) => { setSelectedSubmission(submission); setReviewDecision('APPROVED_FULL'); setReviewNotes(''); };
  const selectedTask = useMemo(() => tasks.find((task) => task.id === selectedTaskId) ?? null, [tasks, selectedTaskId]);
  const submissionsFor = (taskId: number) => submissions.filter((submission) => submission.task === taskId);
  /**
   * خيطُ الحديث على المهمّة — ملاحظاتُ الإدارة وملاحظاتُ الموظّف **مدموجةً
   * بالوقت**، لا قائمتين متجاورتين: الردُّ على ملاحظةٍ لا يُقرأ إن كان في عمودٍ
   * آخر. والفرزُ على `created_at` النصّيّ صحيحٌ لأنّه ISO-8601 من الخادم.
   */
  const threadFor = (taskId: number) => [
    ...managerNotes.filter((note) => note.task === taskId).map((note) => ({ key: `manager-${note.id}`, author: note.author_name || 'الإدارة', body: note.body, at: note.created_at, fromManager: true, badge: note.visibility_display })),
    ...staffNotes.filter((note) => note.task === taskId).map((note) => ({ key: `staff-${note.id}`, author: note.employee_name, body: note.body, at: note.created_at, fromManager: false, badge: '' })),
  ].sort((first, second) => second.at.localeCompare(first.at));
  const openTask = (task: PlatformTask) => {
    setSelectedTaskId(task.id);
    // الافتراضُ أوّلُ المُسنَد إليهم: الحالةُ الغالبةُ مهمّةٌ لموظّفٍ واحد،
    // فاختيارٌ يدويٌّ من قائمةٍ بعنصرٍ واحدٍ خطوةٌ بلا معنى.
    const first = assignmentsFor(task.id)[0];
    setTaskNoteEmployee(first ? String(first.employee) : '');
    setTaskNoteBody(''); setTaskNoteVisibility('EMPLOYEE');
  };

  const create = async (event: React.FormEvent) => {
    event.preventDefault(); if (!title.trim()) return;
    setCreating(true);
    try {
      const selectedIds = employeeIds.map(Number); const input = { title, description: description || undefined, priority, due_date: dueDate || null, audience, ...(audience === 'INDIVIDUAL' || audience === 'SPECIFIC' ? { employee_ids: selectedIds } : {}), ...(audience === 'OPEN' ? { claim_limit: claimLimit ? Number(claimLimit) : null } : {}) };
      await createPlatformTask(input); toast('تم إنشاء المهمة وإرسالها بحسب جمهورها.', 'success'); setTitle(''); setDescription(''); setPriority('MEDIUM'); setDueDate(''); setEmployeeIds([]); setClaimLimit(''); await load();
    } catch (caught: unknown) { toast(messageOf(caught, 'تعذّر إنشاء المهمة.'), 'error'); }
    finally { setCreating(false); }
  };
  const review = async (event: React.FormEvent) => {
    event.preventDefault(); if (!selectedSubmission || (notesRequired && !reviewNotes.trim())) return;
    if (reviewDecision === 'REJECTED' && !(await confirm({ title: 'رفض التسليم', message: 'الرفض يعيد الإسناد للموظف، أو يعيد مهمة المجمّع إلى المجمّع. هل تريد المتابعة؟', confirmText: 'ارفض التسليم', danger: true }))) return;
    setReviewing(true);
    try { await reviewPlatformTaskSubmission(selectedSubmission.id, reviewDecision, reviewNotes); toast(reviewDecision === 'APPROVED_PARTIAL' ? 'تم القبول: مقبول، والعمل مستمرّ.' : 'تم تسجيل قرار المراجعة.', 'success'); setSelectedSubmission(null); setReviewNotes(''); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّرت مراجعة التسليم.'), 'error'); }
    finally { setReviewing(false); }
  };
  const saveTaskNote = async (event: React.FormEvent) => {
    event.preventDefault(); if (!selectedTask || !taskNoteEmployee || !taskNoteBody.trim()) return;
    setTaskNoteSaving(true);
    try { await createPlatformEmployeeNote(Number(taskNoteEmployee), taskNoteBody, taskNoteVisibility, selectedTask.id); toast('تمت إضافة ملاحظتك على المهمة.', 'success'); setTaskNoteBody(''); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر حفظ الملاحظة على المهمة.'), 'error'); }
    finally { setTaskNoteSaving(false); }
  };
  const saveEmployeeNote = async (event: React.FormEvent) => {
    event.preventDefault(); if (!noteEmployee || !noteBody.trim()) return;
    setNoteSaving(true);
    try { await createPlatformEmployeeNote(Number(noteEmployee), noteBody, visibility); toast('تمت إضافة ملاحظة الموظف.', 'success'); setNoteBody(''); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر حفظ ملاحظة الموظف.'), 'error'); }
    finally { setNoteSaving(false); }
  };

  return <div className="space-y-6" dir="rtl">
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">إنشاء مهمة داخلية</h2><p className="mt-1 text-sm text-slate-500">اختر الجمهور؛ لا تظهر إلا الحقول المرتبطة باختيارك.</p><form onSubmit={create} className="mt-5 grid gap-4 md:grid-cols-2"><label className="text-sm font-semibold text-slate-700 md:col-span-2">العنوان<input required value={title} onChange={(event) => setTitle(event.target.value)} className="ktra-input mt-1 w-full" /></label><label className="text-sm font-semibold text-slate-700 md:col-span-2">الوصف<textarea value={description} onChange={(event) => setDescription(event.target.value)} className="ktra-input mt-1 min-h-24 w-full" /></label><label className="text-sm font-semibold text-slate-700">الأولوية<select value={priority} onChange={(event) => setPriority(event.target.value as PlatformTaskPriority)} className="ktra-input mt-1 w-full"><option value="LOW">منخفضة</option><option value="MEDIUM">متوسطة</option><option value="HIGH">عالية</option><option value="URGENT">عاجلة</option></select></label><label className="text-sm font-semibold text-slate-700">تاريخ الاستحقاق<input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} className="ktra-input mt-1 w-full" /></label><label className="text-sm font-semibold text-slate-700 md:col-span-2">الجمهور<select value={audience} onChange={(event) => { setAudience(event.target.value as PlatformTaskAudience); setEmployeeIds([]); setClaimLimit(''); }} className="ktra-input mt-1 w-full">{audienceOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      {audience === 'INDIVIDUAL' && <label className="text-sm font-semibold text-slate-700 md:col-span-2">الموظف<select required value={employeeIds[0] || ''} onChange={(event) => setEmployeeIds(event.target.value ? [event.target.value] : [])} className="ktra-input mt-1 w-full"><option value="">اختر موظفاً</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employeeLabel(employee)}</option>)}</select></label>}
      {audience === 'SPECIFIC' && <label className="text-sm font-semibold text-slate-700 md:col-span-2">الموظفون المحددون<select required multiple value={employeeIds} onChange={(event) => setEmployeeIds(Array.from(event.target.selectedOptions, (option: HTMLOptionElement) => option.value))} className="ktra-input mt-1 min-h-32 w-full">{employees.map((employee) => <option key={employee.id} value={employee.id}>{employeeLabel(employee)}</option>)}</select><span className="mt-1 block text-xs font-normal text-slate-500">استخدم Ctrl أو ⌘ لاختيار أكثر من موظف.</span></label>}
      {audience === 'OPEN' && <label className="text-sm font-semibold text-slate-700 md:col-span-2">حد المطالبات <span className="font-normal text-slate-500">(اختياري)</span><input type="number" min="1" value={claimLimit} onChange={(event) => setClaimLimit(event.target.value)} className="ktra-input mt-1 w-full" /></label>}
      <div className="md:col-span-2"><button type="submit" disabled={creating} className="ktra-btn disabled:opacity-50">{creating ? 'جارٍ الإنشاء...' : 'إنشاء المهمة'}</button></div></form></section>

    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-black text-slate-900">جدول المهام</h2><p className="mt-1 text-sm text-slate-500">اضغط صفَّ المهمة لفتحها: مَن أُسندت إليه، وتسليماته، وملاحظاتك عليها.</p></div><button type="button" onClick={() => void load()} disabled={loading} className="ktra-btn disabled:opacity-50">تحديث</button></div><div className="mt-4 overflow-x-auto"><table className="min-w-full text-right text-sm"><thead className="border-b border-slate-200 text-xs text-slate-500"><tr><th className="p-2">المهمة</th><th className="p-2">الحالة</th><th className="p-2">نطاق الإسناد</th><th className="p-2">المُسنَد إليهم</th><th className="p-2">سُلّم</th><th className="p-2">الاستحقاق</th><th className="p-2"><span className="sr-only">فتح المهمة</span></th></tr></thead><tbody>{tasks.map((task) => {
      const taskAssignments = assignmentsFor(task.id);
      const submitted = taskAssignments.filter((assignment) => assignment.status === 'SUBMITTED' || assignment.status === 'COMPLETED').length;
      // **الاسمُ لا العدد.** كان العمودُ يعرض «١» بجانب «موظّفٌ واحد» (وهو وصفُ
      // النطاق لا اسمَ أحد)، فالجدولُ كلُّه لا يقول لمن أُسندت المهمة — وهي
      // أوّلُ شكوى المالك على هذه الشاشة.
      const names = taskAssignments.map((assignment) => assignment.employee_name).filter(Boolean);
      return <tr key={task.id} onClick={() => openTask(task)} className={`cursor-pointer border-b border-slate-100 transition hover:bg-blue-50 ${selectedTaskId === task.id ? 'bg-blue-50' : ''}`}>
        <td className="p-2 font-semibold text-slate-800"><button type="button" onClick={(event) => { event.stopPropagation(); openTask(task); }} className="text-right text-blue-700 underline-offset-2 hover:underline">{task.title}</button><span className="mr-1 text-xs font-normal text-slate-400">#{formatNumber(task.id)}</span></td>
        <td className="p-2 text-slate-600">{task.status_display}</td>
        <td className="p-2 text-slate-600">{task.audience_display}</td>
        <td className="p-2 text-slate-600" title={names.join('، ')}>{names.length === 0 ? <span className="text-amber-700">لم تُسنَد بعد</span> : <span>{names.slice(0, 2).join('، ')}{names.length > 2 ? ` +${formatNumber(names.length - 2)}` : ''}</span>}</td>
        <td className="p-2 text-slate-600">{formatNumber(submitted)}</td>
        <td className="p-2 text-slate-600">{dateLabel(task.due_date)}</td>
        <td className="p-2"><span className="text-xs font-bold text-blue-700">فتح</span></td>
      </tr>;
    })}</tbody></table>{!loading && tasks.length === 0 && <p className="py-5 text-sm text-slate-500">لا توجد مهام بعد.</p>}</div></section>

    {selectedTask && <section className="rounded-xl border border-blue-200 bg-white p-4 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-black text-slate-900">{selectedTask.title}<span className="mr-2 text-sm font-normal text-slate-400">#{formatNumber(selectedTask.id)}</span></h2>
          <p className="mt-1 text-sm text-slate-600">{selectedTask.description || 'لا يوجد وصف.'}</p>
          <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500"><span>الحالة: {selectedTask.status_display}</span><span>الأولوية: {selectedTask.priority_display}</span><span>نطاق الإسناد: {selectedTask.audience_display}</span><span>الاستحقاق: {dateLabel(selectedTask.due_date)}</span><span>أنشأها: {selectedTask.created_by_name || '—'}</span></p>
        </div>
        <button type="button" onClick={() => setSelectedTaskId(null)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-600 hover:bg-slate-50">إغلاق</button>
      </div>

      <div className="mt-5 grid gap-6 xl:grid-cols-2">
        <div>
          <h3 className="text-sm font-black text-slate-900">المُسنَد إليهم</h3>
          <div className="mt-3 space-y-2">{assignmentsFor(selectedTask.id).length === 0 ? <p className="text-sm text-slate-500">لم تُسنَد لأحد بعد.</p> : assignmentsFor(selectedTask.id).map((assignment) => <article key={assignment.id} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-bold text-slate-800">{assignment.employee_name}</span><span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">{assignment.status_display}</span></div><p className="mt-1 text-xs text-slate-500">أُسندت {dateLabel(assignment.offered_at)}{assignment.accepted_at ? ` · قبلها ${dateLabel(assignment.accepted_at)}` : ''}{assignment.submitted_at ? ` · سلّمها ${dateLabel(assignment.submitted_at)}` : ''}</p></article>)}</div>

          <h3 className="mt-5 text-sm font-black text-slate-900">التسليمات</h3>
          <div className="mt-3 space-y-2">{submissionsFor(selectedTask.id).length === 0 ? <p className="text-sm text-slate-500">لا تسليم بعد.</p> : submissionsFor(selectedTask.id).map((submission) => <article key={submission.id} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-bold text-slate-800">{submission.employee_name}</span><span className="text-xs text-slate-400">{dateLabel(submission.created_at)}</span></div><p className="mt-1 text-sm text-slate-700">{submission.body || 'سُلّمت بلا ملاحظات.'}</p><p className="mt-1 text-xs font-bold text-slate-600">{submission.decision ? `قرارك: ${submission.decision_display}` : 'بانتظار مراجعتك.'}</p></article>)}</div>
        </div>

        <div>
          <h3 className="text-sm font-black text-slate-900">ملاحظات هذه المهمة</h3>
          <p className="mt-1 text-xs text-slate-500">ملاحظاتك وملاحظات الموظف في خيط واحد مرتّب بالوقت — أحدثها أولاً.</p>
          <form onSubmit={saveTaskNote} className="mt-3 space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-3">
            <label className="block text-sm font-semibold text-slate-700">الموظف<select required value={taskNoteEmployee} onChange={(event) => setTaskNoteEmployee(event.target.value)} className="ktra-input mt-1 w-full"><option value="">اختر موظفاً</option>{assignmentsFor(selectedTask.id).map((assignment) => <option key={assignment.id} value={assignment.employee}>{assignment.employee_name}</option>)}</select></label>
            <fieldset><legend className="text-sm font-semibold text-slate-700">الرؤية</legend><div className="mt-2 flex gap-4 text-sm text-slate-700"><label><input type="radio" name="task-note-visibility" checked={taskNoteVisibility === 'EMPLOYEE'} onChange={() => setTaskNoteVisibility('EMPLOYEE')} /> يراها الموظف</label><label><input type="radio" name="task-note-visibility" checked={taskNoteVisibility === 'MANAGER_ONLY'} onChange={() => setTaskNoteVisibility('MANAGER_ONLY')} /> للمدير فقط</label></div></fieldset>
            <label className="block text-sm font-semibold text-slate-700">الملاحظة<textarea required value={taskNoteBody} onChange={(event) => setTaskNoteBody(event.target.value)} className="ktra-input mt-1 min-h-20 w-full" /></label>
            {/* الخادمُ يرفض ملاحظةً على مهمّةٍ ليست مُسندةً لصاحبها؛ فالزرُّ مقفولٌ
                قبل الإسناد بدل أن يُرسِل طلباً يُردّ بـ٤٠٠. */}
            <button type="submit" disabled={taskNoteSaving || assignmentsFor(selectedTask.id).length === 0} className="ktra-btn disabled:opacity-50">{taskNoteSaving ? 'جارٍ الحفظ...' : 'أضف ملاحظة على المهمة'}</button>
            {assignmentsFor(selectedTask.id).length === 0 && <p className="text-xs font-semibold text-amber-700">الملاحظة تُكتب لموظف أُسندت إليه المهمة — أسنِدها أولاً.</p>}
          </form>
          <div className="mt-4 space-y-2">{threadFor(selectedTask.id).length === 0 ? <p className="text-sm text-slate-500">لا ملاحظات على هذه المهمة بعد.</p> : threadFor(selectedTask.id).map((note) => <article key={note.key} className={`rounded-lg border p-3 ${note.fromManager ? 'border-blue-200 bg-blue-50' : 'border-slate-200'}`}><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-bold text-slate-800">{note.author}{note.fromManager ? ' — الإدارة' : ''}</span><span className="text-xs text-slate-400">{note.badge ? `${note.badge} · ` : ''}{formatDateTimeValue(note.at)}</span></div><p className="mt-1 text-sm text-slate-700">{note.body}</p></article>)}</div>
        </div>
      </div>
    </section>}


    <section className="grid gap-6 xl:grid-cols-2"><div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">تسليمات بانتظار المراجعة</h2><div className="mt-4 space-y-3">{pendingSubmissions.length === 0 ? <p className="text-sm text-slate-500">لا توجد تسليمات معلقة.</p> : pendingSubmissions.map((submission) => <button type="button" key={submission.id} onClick={() => selectSubmission(submission)} className="w-full rounded-lg border border-slate-200 p-3 text-right transition hover:border-blue-400"><p className="font-semibold text-slate-800">{submission.task_title}</p><p className="mt-1 text-sm text-slate-600">{submission.employee_name}: {submission.body || 'سُلّمت بلا ملاحظات.'}</p><p className="mt-1 text-xs text-slate-400">{dateLabel(submission.created_at)}</p></button>)}</div>{selectedSubmission && <form onSubmit={review} className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-4"><h3 className="font-bold text-slate-900">مراجعة: {selectedSubmission.task_title}</h3><p className="mt-2 text-sm text-slate-700">تسليم الموظف: {selectedSubmission.body || 'بلا ملاحظات.'}</p><div className="mt-3 flex flex-wrap gap-2">{([{ value: 'APPROVED_FULL', label: 'مقبول مكتمل' }, { value: 'APPROVED_PARTIAL', label: 'مقبول، والعمل مستمرّ' }, { value: 'REJECTED', label: 'مرفوض ويعاد مفتوحاً' }] as Array<{ value: PlatformTaskReviewDecision; label: string }>).map((choice) => <button type="button" key={choice.value} onClick={() => setReviewDecision(choice.value)} className={`rounded-lg border px-3 py-2 text-sm font-bold ${reviewDecision === choice.value ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-700'}`}>{choice.label}</button>)}</div>{reviewDecision === 'APPROVED_PARTIAL' && <p className="mt-3 text-sm text-amber-700">مقبول، والعمل مستمرّ: سيعود الإسناد إلى قيد التنفيذ ليُسلَّم ثانيةً.</p>}<label className="mt-3 block text-sm font-semibold text-slate-700">ملاحظات المراجعة {notesRequired && <span className="text-red-600">(إلزامية)</span>}<textarea id="task-reviewer-notes" required={notesRequired} value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} className="ktra-input mt-1 min-h-24 w-full" /></label><button type="submit" disabled={reviewing || (notesRequired && !reviewNotes.trim())} className="ktra-btn mt-3 disabled:opacity-50">{reviewing ? 'جارٍ الحفظ...' : 'ثبّت قرار المراجعة'}</button></form>}</div>
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">ملاحظة على موظف</h2><p className="mt-1 text-sm text-slate-500">«ظاهرة للموظف» تظهر له، و«للمدير فقط» تبقى داخل الإدارة.</p><form onSubmit={saveEmployeeNote} className="mt-4 space-y-3"><label className="block text-sm font-semibold text-slate-700">الموظف<select required value={noteEmployee} onChange={(event) => setNoteEmployee(event.target.value)} className="ktra-input mt-1 w-full"><option value="">اختر موظفاً</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employeeLabel(employee)}</option>)}</select></label><fieldset><legend className="text-sm font-semibold text-slate-700">الرؤية</legend><div className="mt-2 flex gap-4 text-sm text-slate-700"><label><input type="radio" name="employee-note-visibility" checked={visibility === 'EMPLOYEE'} onChange={() => setVisibility('EMPLOYEE')} /> ظاهرة للموظف</label><label><input type="radio" name="employee-note-visibility" checked={visibility === 'MANAGER_ONLY'} onChange={() => setVisibility('MANAGER_ONLY')} /> للمدير فقط</label></div></fieldset><label className="block text-sm font-semibold text-slate-700">الملاحظة<textarea required value={noteBody} onChange={(event) => setNoteBody(event.target.value)} className="ktra-input mt-1 min-h-24 w-full" /></label><button type="submit" disabled={noteSaving} className="ktra-btn disabled:opacity-50">{noteSaving ? 'جارٍ الحفظ...' : 'أضف الملاحظة'}</button></form><div className="mt-5 border-t border-slate-200 pt-4"><h3 className="text-sm font-black text-slate-900">الملاحظات المكتوبة{noteEmployee ? ' على الموظف المختار' : ''}</h3><div className="mt-3 space-y-2">{shownManagerNotes.length === 0 ? <p className="text-sm text-slate-500">لا توجد ملاحظات بعد.</p> : shownManagerNotes.map((note) => <article key={note.id} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className={`rounded-md px-2 py-0.5 text-xs font-bold ${note.visibility === 'MANAGER_ONLY' ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>{note.visibility_display}</span><span className="text-xs text-slate-400">{note.author_name} · {dateLabel(note.created_at)}</span></div><p className="mt-2 text-sm text-slate-700">{note.body}</p></article>)}</div></div></div></section>

    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">ملاحظات الموظفين في مساحة عملهم</h2><p className="mt-1 text-sm text-slate-500">ما يكتبه الموظف على مهمة أُسندت إليه أو ملاحظةً عمومية.</p><div className="mt-4 space-y-2">{staffNotes.length === 0 ? <p className="text-sm text-slate-500">لا توجد ملاحظات بعد.</p> : staffNotes.map((note) => <article key={note.id} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-bold text-slate-800">{note.employee_name}</span><span className="text-xs text-slate-400">{note.task ? note.task_title : 'ملاحظة عمومية'} · {dateLabel(note.created_at)}</span></div><p className="mt-2 text-sm text-slate-700">{note.body}</p></article>)}</div></section>
  </div>;
};
