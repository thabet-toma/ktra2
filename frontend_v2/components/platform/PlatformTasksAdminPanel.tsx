import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../contexts/ConfirmContext';
import { useToast } from '../../contexts/ToastContext';
import { formatDateValue } from '../../utils/formatDate';
import { formatNumber } from '../../utils/formatNumber';
import {
  createPlatformEmployeeNote,
  createPlatformTask,
  getPlatformTaskBoard,
  uploadPlatformTaskAttachment,
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
  type PlatformTaskBoardRow,
  type PlatformTaskPriority,
  type PlatformTaskReviewDecision,
  type PlatformTaskSubmission,
  type PlatformWorkspaceNote,
} from '../../services/platformTasksApi';
import { TaskFileDrawer } from './staff/tasks/TaskFileDrawer';

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
  const [managerNotes, setManagerNotes] = useState<PlatformEmployeeNote[]>([]);
  const [boardRows, setBoardRows] = useState<PlatformTaskBoardRow[]>([]);
  const [staffNotes, setStaffNotes] = useState<PlatformWorkspaceNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [noteSaving, setNoteSaving] = useState(false);
  const [title, setTitle] = useState(''); const [description, setDescription] = useState(''); const [priority, setPriority] = useState<PlatformTaskPriority>('MEDIUM'); const [dueDate, setDueDate] = useState(''); const [audience, setAudience] = useState<PlatformTaskAudience>('INDIVIDUAL'); const [employeeIds, setEmployeeIds] = useState<string[]>([]); const [claimLimit, setClaimLimit] = useState(''); const [mandatory, setMandatory] = useState(false); const [briefFiles, setBriefFiles] = useState<File[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [boardEmployee, setBoardEmployee] = useState<number | null>(null);
  const [selectedSubmission, setSelectedSubmission] = useState<PlatformTaskSubmission | null>(null); const [reviewDecision, setReviewDecision] = useState<PlatformTaskReviewDecision>('APPROVED_FULL'); const [reviewNotes, setReviewNotes] = useState('');
  const [noteEmployee, setNoteEmployee] = useState(''); const [noteBody, setNoteBody] = useState(''); const [visibility, setVisibility] = useState<PlatformEmployeeNoteVisibility>('EMPLOYEE');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextTasks, nextAssignments, nextSubmissions, nextEmployees, nextManagerNotes, board, nextStaffNotes] = await Promise.all([
        listPlatformTasks(), listPlatformTaskAssignments(), listPlatformTaskSubmissions(), listPlatformEmployees(), listPlatformEmployeeNotes(), getPlatformTaskBoard(), listPlatformWorkspaceNotes(),
      ]);
      setTasks(nextTasks); setAssignments(nextAssignments); setSubmissions(nextSubmissions); setEmployees(nextEmployees); setManagerNotes(nextManagerNotes); setBoardRows(board.rows); setStaffNotes(nextStaffNotes);
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر تحميل إدارة المهام.'), 'error');
    } finally { setLoading(false); }
  }, [toast]);
  useEffect(() => { void load(); }, [load]);

  const assignmentsFor = (taskId: number) => assignments.filter((assignment) => assignment.task === taskId);
  const selectedTask = useMemo(() => tasks.find((task) => task.id === selectedTaskId) ?? null, [tasks, selectedTaskId]);
  const filteredTasks = useMemo(() => boardEmployee === null ? tasks : tasks.filter((task) => assignmentsFor(task.id).some((assignment) => assignment.employee === boardEmployee)), [assignments, boardEmployee, tasks]);
  const pendingSubmissions = useMemo(() => submissions.filter((submission) => !submission.decision), [submissions]);
  const notesRequired = reviewDecision === 'APPROVED_PARTIAL' || reviewDecision === 'REJECTED';
  const mandatoryEligible = audience === 'SPECIFIC' || audience === 'ALL';
  // ملاحظاتُ المدير تُرشَّح على الموظّف المختار حين يُختار — ومن غيرِ ذلك تُقرأ
  // كلُّها: لوحةٌ تكتب ولا تقرأ تُخفي `MANAGER_ONLY` عن الجهة الوحيدة التي كُتبت لها.
  const shownManagerNotes = useMemo(() => noteEmployee ? managerNotes.filter((note) => note.employee === Number(noteEmployee)) : managerNotes, [managerNotes, noteEmployee]);
  // **عطبٌ سابقٌ لـ#213** كان يقارن `'ACTIVE'` و`'SUSPENDED'` بأحرفٍ كبيرة،
  // وقيمُ `PlatformEmployee.Status` صغيرةٌ (`active` · `on_leave` · `offboarded`)
  // ولا وجودَ لـ`suspended` أصلاً — فكان **كلُّ** موظّفٍ يُعرَض «(خارج الخدمة)»
  // في منتقي إنشاء المهمّة. والنصُّ الآن من الخادم كسائر نصوص `choices`.
  const employeeLabel = (employee: PlatformEmployee) => employee.status === 'active' ? employee.username : `${employee.username} (${employee.status_display})`;
  const openTask = (task: PlatformTask) => { setSelectedTaskId(task.id); };

  const create = async (event: React.FormEvent) => {
    event.preventDefault(); if (!title.trim()) return;
    setCreating(true);
    try {
      const selectedIds = employeeIds.map(Number);
      const created = await createPlatformTask({ title, description: description || undefined, priority, due_date: dueDate || null, audience, ...(audience === 'INDIVIDUAL' || audience === 'SPECIFIC' ? { employee_ids: selectedIds } : {}), ...(audience === 'OPEN' ? { claim_limit: claimLimit ? Number(claimLimit) : null } : {}), ...(mandatoryEligible ? { is_mandatory: mandatory } : {}) });
      // **الشرحُ يُرفع مع المهمّة لا بعدها**: الإسنادُ يقع لحظةَ الإنشاء ويصل
      // الموظّفَ فوراً، فمهمّةٌ تُنشأ ثمّ تُفتَح ثمّ يُرفَق شرحُها تعني أنّ البلاغَ
      // سبق الشرح. والرفعُ يحتاج معرّفَ المهمّة فيأتي بعد ردِّ الإنشاء مباشرةً؛
      // وفشلُه لا يُلغي مهمّةً وقعت — يُبلَّغ بأنّها قامت وأنّ الملفّ لم يصعد.
      const failed: string[] = [];
      for (const file of briefFiles) {
        try { await uploadPlatformTaskAttachment(created.id, file); }
        catch { failed.push(file.name); }
      }
      toast(failed.length === 0 ? 'تم إنشاء المهمة وإرسالها بحسب جمهورها.' : `أُنشئت المهمة، وتعذّر رفع: ${failed.join('، ')} — أعد رفعه من ملف المهمة.`, failed.length === 0 ? 'success' : 'error');
      setTitle(''); setDescription(''); setPriority('MEDIUM'); setDueDate(''); setEmployeeIds([]); setClaimLimit(''); setMandatory(false); setBriefFiles([]); await load();
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
  const saveEmployeeNote = async (event: React.FormEvent) => {
    event.preventDefault(); if (!noteEmployee || !noteBody.trim()) return;
    setNoteSaving(true);
    try { await createPlatformEmployeeNote(Number(noteEmployee), noteBody.trim(), visibility); toast('تمت إضافة ملاحظة الموظف.', 'success'); setNoteBody(''); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر حفظ ملاحظة الموظف.'), 'error'); }
    finally { setNoteSaving(false); }
  };

  return <div className="space-y-6" dir="rtl">
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">إنشاء مهمة داخلية</h2><p className="mt-1 text-sm text-slate-500">اختر الجمهور؛ الفردية إجبارية دائماً والمجمّع اختيارية دائماً.</p><form onSubmit={create} className="mt-5 grid gap-4 md:grid-cols-2"><label className="text-sm font-semibold text-slate-700 md:col-span-2">العنوان<input required value={title} onChange={(event) => setTitle(event.target.value)} className="ktra-input mt-1 w-full" /></label><label className="text-sm font-semibold text-slate-700 md:col-span-2">الوصف<textarea value={description} onChange={(event) => setDescription(event.target.value)} className="ktra-input mt-1 min-h-24 w-full" /></label><label className="text-sm font-semibold text-slate-700">الأولوية<select value={priority} onChange={(event) => setPriority(event.target.value as PlatformTaskPriority)} className="ktra-input mt-1 w-full"><option value="LOW">منخفضة</option><option value="MEDIUM">متوسطة</option><option value="HIGH">عالية</option><option value="URGENT">عاجلة</option></select></label><label className="text-sm font-semibold text-slate-700">تاريخ الاستحقاق<input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} className="ktra-input mt-1 w-full" /></label><label className="text-sm font-semibold text-slate-700 md:col-span-2">الجمهور<select value={audience} onChange={(event) => { setAudience(event.target.value as PlatformTaskAudience); setEmployeeIds([]); setClaimLimit(''); setMandatory(false); }} className="ktra-input mt-1 w-full">{audienceOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>{audience === 'INDIVIDUAL' && <label className="text-sm font-semibold text-slate-700 md:col-span-2">الموظف<select required value={employeeIds[0] || ''} onChange={(event) => setEmployeeIds(event.target.value ? [event.target.value] : [])} className="ktra-input mt-1 w-full"><option value="">اختر موظفاً</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employeeLabel(employee)}</option>)}</select></label>}{audience === 'SPECIFIC' && <label className="text-sm font-semibold text-slate-700 md:col-span-2">الموظفون المحددون<select required multiple value={employeeIds} onChange={(event) => setEmployeeIds(Array.from(event.target.selectedOptions, (option: HTMLOptionElement) => option.value))} className="ktra-input mt-1 min-h-32 w-full">{employees.map((employee) => <option key={employee.id} value={employee.id}>{employeeLabel(employee)}</option>)}</select></label>}{audience === 'OPEN' && <label className="text-sm font-semibold text-slate-700 md:col-span-2">حد المطالبات <span className="font-normal text-slate-500">(اختياري)</span><input type="number" min="1" value={claimLimit} onChange={(event) => setClaimLimit(event.target.value)} className="ktra-input mt-1 w-full" /></label>}{mandatoryEligible && <fieldset className="md:col-span-2"><legend className="text-sm font-semibold text-slate-700">نوع الإسناد</legend><div className="mt-2 flex flex-wrap gap-4 text-sm text-slate-700"><label><input type="radio" name="mandatory" checked={mandatory} onChange={() => setMandatory(true)} /> إجبارية — تقبل تلقائياً</label><label><input type="radio" name="mandatory" checked={!mandatory} onChange={() => setMandatory(false)} /> اختيارية — يقرر الموظف قبولها</label></div></fieldset>}<div className="md:col-span-2"><label className="block text-sm font-semibold text-slate-700">ملفات وصور الشرح <span className="font-normal text-slate-500">(تُرفع مع المهمة)</span><input type="file" multiple onChange={(event) => setBriefFiles(Array.from(event.target.files || []))} className="ktra-input mt-1 w-full" /></label>{briefFiles.length > 0 && <p className="mt-1 text-xs text-slate-500">{formatNumber(briefFiles.length)} ملف: {briefFiles.map((file) => file.name).join('، ')}</p>}</div><div className="md:col-span-2"><button type="submit" disabled={creating} className="ktra-btn disabled:opacity-50">{creating ? 'جارٍ الإنشاء...' : 'إنشاء المهمة'}</button></div></form></section>

    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-black text-slate-900">من معه ماذا</h2><p className="mt-1 text-sm text-slate-500">اضغط صف الموظف لتصفية جدول المهام عليه. ومن أُوقف وبيده عمل يبقى هنا بشارة حالته.</p></div>{boardEmployee !== null && <button type="button" onClick={() => setBoardEmployee(null)} className="ktra-btn">إلغاء التصفية</button>}</div><div className="mt-4 overflow-x-auto"><table className="min-w-full text-right text-sm"><thead className="border-b border-slate-200 text-xs text-slate-500"><tr>{['الموظف', 'معروضة', 'مقبولة', 'منها إجبارية', 'قيد التنفيذ', 'سُلّمت', 'اكتملت', 'أُعيدت', 'متأخرة', 'الإجمالي'].map((heading) => <th key={heading} className="p-2">{heading}</th>)}</tr></thead><tbody>{boardRows.map((row) => <tr key={row.employee} onClick={() => setBoardEmployee((current) => current === row.employee ? null : row.employee)} className={`cursor-pointer border-b border-slate-100 transition hover:bg-blue-50 ${boardEmployee === row.employee ? 'bg-blue-50' : ''}`}><td className="p-2 font-semibold text-slate-800"><button type="button" onClick={(event) => { event.stopPropagation(); setBoardEmployee((current) => current === row.employee ? null : row.employee); }} className="text-right text-blue-700 underline-offset-2 hover:underline">{row.employee_name}</button>{row.employee_status !== 'active' && <span className="mr-2 rounded-md bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-800">{row.employee_status_display}</span>}</td><td className="p-2 text-slate-600">{formatNumber(row.offered)}</td><td className="p-2 text-slate-600">{formatNumber(row.accepted)}</td><td className="p-2 text-slate-600" title="أُسندت بلا خيار — مقبولة تلقائياً، لا لأن الموظف اختارها">{formatNumber(row.mandatory)}</td><td className="p-2 text-slate-600">{formatNumber(row.in_progress)}</td><td className="p-2 text-slate-600">{formatNumber(row.submitted)}</td><td className="p-2 text-slate-600">{formatNumber(row.completed)}</td><td className="p-2 text-slate-600">{formatNumber(row.returned)}</td><td className={`p-2 font-bold ${row.overdue > 0 ? 'text-amber-700' : 'text-slate-600'}`}>{formatNumber(row.overdue)}</td><td className="p-2 font-bold text-slate-800">{formatNumber(row.total)}</td></tr>)}</tbody></table>{!loading && boardRows.length === 0 && <p className="py-5 text-sm text-slate-500">لا توجد بيانات للوح بعد.</p>}</div></section>

    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-black text-slate-900">جدول المهام</h2><p className="mt-1 text-sm text-slate-500">اضغط صف المهمة لفتح ملفها الكامل.</p></div><button type="button" onClick={() => void load()} disabled={loading} className="ktra-btn disabled:opacity-50">تحديث</button></div><div className="mt-4 overflow-x-auto"><table className="min-w-full text-right text-sm"><thead className="border-b border-slate-200 text-xs text-slate-500"><tr><th className="p-2">المهمة</th><th className="p-2">الحالة</th><th className="p-2">النطاق</th><th className="p-2">النوع</th><th className="p-2">المسند إليهم</th><th className="p-2">سُلّم</th><th className="p-2">الاستحقاق</th></tr></thead><tbody>{filteredTasks.map((task) => { const taskAssignments = assignmentsFor(task.id); const submitted = taskAssignments.filter((assignment) => assignment.status === 'SUBMITTED' || assignment.status === 'COMPLETED').length; const names = taskAssignments.map((assignment) => assignment.employee_name).filter(Boolean); return <tr key={task.id} onClick={() => openTask(task)} className={`cursor-pointer border-b border-slate-100 transition hover:bg-blue-50 ${selectedTaskId === task.id ? 'bg-blue-50' : ''}`}><td className="p-2 font-semibold text-slate-800"><button type="button" onClick={(event) => { event.stopPropagation(); openTask(task); }} className="text-right text-blue-700 underline-offset-2 hover:underline">{task.title}</button><span className="mr-1 text-xs font-normal text-slate-400">#{formatNumber(task.id)}</span></td><td className="p-2 text-slate-600">{task.status_display}</td><td className="p-2 text-slate-600">{task.audience_display}</td><td className="p-2 text-slate-600">{task.is_mandatory ? 'إجبارية' : 'اختيارية'}</td><td className="p-2 text-slate-600" title={names.join('، ')}>{names.length === 0 ? <span className="text-amber-700">لم تُسند بعد</span> : <span>{names.slice(0, 2).join('، ')}{names.length > 2 ? ` +${formatNumber(names.length - 2)}` : ''}</span>}</td><td className="p-2 text-slate-600">{formatNumber(submitted)}</td><td className="p-2 text-slate-600">{dateLabel(task.due_date)}</td></tr>; })}</tbody></table>{!loading && filteredTasks.length === 0 && <p className="py-5 text-sm text-slate-500">لا توجد مهام مطابقة.</p>}</div></section>

    <section className="grid gap-6 xl:grid-cols-2"><div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">تسليمات بانتظار المراجعة</h2><div className="mt-4 space-y-3">{pendingSubmissions.length === 0 ? <p className="text-sm text-slate-500">لا توجد تسليمات معلقة.</p> : pendingSubmissions.map((submission) => <button key={submission.id} type="button" onClick={() => { setSelectedSubmission(submission); setReviewDecision('APPROVED_FULL'); setReviewNotes(''); }} className="block w-full rounded-lg border border-slate-200 p-3 text-right"><span className="font-bold text-slate-800">{submission.task_title} — {submission.employee_name}</span><span className="mt-1 block text-xs text-slate-500">{dateLabel(submission.created_at)}</span><span className="mt-2 block text-sm text-slate-600">{submission.body || 'سُلّمت بلا ملاحظات.'}</span></button>)}</div>{selectedSubmission && <form onSubmit={review} className="mt-4 space-y-3 rounded-lg border border-slate-200 p-3"><p className="text-sm font-bold text-slate-800">مراجعة: {selectedSubmission.task_title}</p><div className="flex flex-wrap gap-2">{([{ value: 'APPROVED_FULL', label: 'مقبول مكتمل' }, { value: 'APPROVED_PARTIAL', label: 'مقبول، والعمل مستمرّ' }, { value: 'REJECTED', label: 'مرفوض ويعاد مفتوحاً' }] as Array<{ value: PlatformTaskReviewDecision; label: string }>).map((choice) => <button type="button" key={choice.value} onClick={() => setReviewDecision(choice.value)} className={`rounded-lg border px-3 py-2 text-sm font-bold ${reviewDecision === choice.value ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-700'}`}>{choice.label}</button>)}</div>{reviewDecision === 'APPROVED_PARTIAL' && <p className="text-sm text-amber-700">مقبول، والعمل مستمرّ: سيعود الإسناد إلى قيد التنفيذ ليُسلَّم ثانيةً.</p>}{reviewDecision === 'REJECTED' && <p className="text-sm text-amber-700">الرفض يعيد الإسناد للموظف، ويعيد مهمة المجمّع إلى المجمّع.</p>}<label className="block text-sm text-slate-700">ملاحظات المراجعة{notesRequired && ' (مطلوبة)'}<textarea id="task-reviewer-notes" required={notesRequired} value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} className="ktra-input mt-1 min-h-20 w-full" /></label><button type="submit" disabled={reviewing || (notesRequired && !reviewNotes.trim())} className="ktra-btn disabled:opacity-50">{reviewing ? 'جارٍ الحفظ...' : 'ثبّت قرار المراجعة'}</button></form>}</div><div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">ملاحظة عامة للموظف</h2><form onSubmit={saveEmployeeNote} className="mt-4 space-y-3"><label className="block text-sm font-semibold text-slate-700">الموظف<select required value={noteEmployee} onChange={(event) => setNoteEmployee(event.target.value)} className="ktra-input mt-1 w-full"><option value="">اختر موظفاً</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employeeLabel(employee)}</option>)}</select></label><fieldset><legend className="text-sm font-semibold text-slate-700">الرؤية</legend><label className="ml-4 text-sm text-slate-700"><input type="radio" name="general-visibility" checked={visibility === 'EMPLOYEE'} onChange={() => setVisibility('EMPLOYEE')} /> يراها الموظف</label><label className="text-sm text-slate-700"><input type="radio" name="general-visibility" checked={visibility === 'MANAGER_ONLY'} onChange={() => setVisibility('MANAGER_ONLY')} /> للمدير فقط</label></fieldset><label className="block text-sm font-semibold text-slate-700">الملاحظة<textarea required value={noteBody} onChange={(event) => setNoteBody(event.target.value)} className="ktra-input mt-1 min-h-20 w-full" /></label><button type="submit" disabled={noteSaving} className="ktra-btn disabled:opacity-50">{noteSaving ? 'جارٍ الحفظ...' : 'أضف الملاحظة'}</button></form><div className="mt-4 space-y-2">{shownManagerNotes.length === 0 ? <p className="text-sm text-slate-500">لا توجد ملاحظات بعد.</p> : shownManagerNotes.map((note) => <article key={note.id} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className={`rounded-md px-2 py-0.5 text-xs font-bold ${note.visibility === 'MANAGER_ONLY' ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>{note.visibility_display}</span><span className="text-xs text-slate-500">{note.author_name} · {note.task ? note.task_title : 'ملاحظة عامة'} · {dateLabel(note.created_at)}</span></div><p className="mt-2 text-sm text-slate-700">{note.body}</p></article>)}</div></div></section>
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"><h2 className="text-lg font-black text-slate-900">ملاحظات الموظفين في مساحة عملهم</h2><p className="mt-1 text-sm text-slate-500">ما يكتبه الموظف على مهمة أُسندت إليه أو ملاحظةً عمومية — والعمومية لا تظهر في ملف أي مهمة.</p><div className="mt-4 space-y-2">{staffNotes.length === 0 ? <p className="text-sm text-slate-500">لا توجد ملاحظات بعد.</p> : staffNotes.map((note) => <article key={note.id} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-bold text-slate-800">{note.employee_name}</span><span className="text-xs text-slate-500">{note.task ? note.task_title : 'ملاحظة عمومية'} · {dateLabel(note.created_at)}</span></div><p className="mt-2 text-sm text-slate-700">{note.body}</p></article>)}</div></section>

    {selectedTask && <TaskFileDrawer task={selectedTask} isManager onClose={() => setSelectedTaskId(null)} onChanged={load} />}
  </div>;
};
