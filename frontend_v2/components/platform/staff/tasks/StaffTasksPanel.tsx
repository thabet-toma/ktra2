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
  type PlatformEmployeeNote,
  type PlatformTask,
  type PlatformTaskAssignment,
  type PlatformTaskSubmission,
  type PlatformWorkspaceNote,
} from '../../../../services/platformTasksApi';
import { TaskFileDrawer } from './TaskFileDrawer';
import { CcCard, CcEmpty, CcSectionTitle } from '../../ui';

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
  /**
   * الفعلُ الجاري، **بمفتاحٍ مُسمّىً لا برقمٍ عارٍ**.
   *
   * كان رقماً، وثلاثةُ أفعالٍ تكتبه من جدولين: `accept`/`showTask` بمعرّف
   * الإسناد و`claim` بمعرّف المهمّة. فإسنادٌ رقمُه ٥ ومهمّةُ مجمَعٍ رقمُها ٥
   * يتقاسمان القيمةَ نفسَها، ويُعطَّل زرٌّ في بطاقةٍ لا شأنَ لها بالفعل الجاري.
   * والبادئةُ تفصل الفضاءين فصلاً لا يعتمد على تباعد الأرقام.
   */
  const [busy, setBusy] = useState<string | null>(null);
  const assignmentKey = (assignment: PlatformTaskAssignment) => `assignment-${assignment.id}`;
  const taskKey = (task: PlatformTask) => `task-${task.id}`;
  const [noteBody, setNoteBody] = useState('');
  const [noteTask, setNoteTask] = useState('');
  const [noteBusy, setNoteBusy] = useState(false);
  const [selected, setSelected] = useState<{ task: PlatformTask; assignment: PlatformTaskAssignment } | null>(null);

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
  /**
   * ملاحظاتُ المدير **على هذه المهمّة** — تُقرأ كاملةً في ملفّ المهمّة (#213-ب)،
   * وهذه تكتفي بإشارةٍ على البطاقة تدلّ عليها.
   *
   * والقائمةُ أسفلَ الشاشة تعرضها كلَّها — على مهمّةٍ وعموميّةً — كلٌّ مسمّاةً
   * بمهمّتها، فلا تختفي ملاحظةٌ لأنّ صاحبَها لم يفتح ملفّ مهمّتها. والخادمُ لا
   * يُرسل إلّا ما `visibility=EMPLOYEE` له.
   */
  const managerNotesFor = (taskId: number) => employeeNotes.filter((note) => note.task === taskId);

  const accept = async (assignment: PlatformTaskAssignment) => {
    setBusy(assignmentKey(assignment));
    try { await acceptPlatformTaskAssignment(assignment.id); toast('تم قبول المهمة.', 'success'); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر قبول المهمة.'), 'error'); }
    finally { setBusy(null); }
  };
  const claim = async (task: PlatformTask) => {
    setBusy(taskKey(task));
    try { await claimPlatformTask(task.id); toast('تم استلام المهمة من المجمّع.', 'success'); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر استلام المهمة؛ قد يكون حدّ المطالبين اكتمل.'), 'error'); }
    finally { setBusy(null); }
  };
  const showTask = async (assignment: PlatformTaskAssignment) => {
    setBusy(assignmentKey(assignment));
    try { setSelected({ task: await getPlatformTask(assignment.task), assignment }); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر فتح ملفّ المهمة.'), 'error'); }
    finally { setBusy(null); }
  };
  const saveNote = async (event: React.FormEvent) => {
    event.preventDefault(); if (!noteBody.trim()) return;
    setNoteBusy(true);
    try { await createPlatformWorkspaceNote(noteBody.trim(), noteTask ? Number(noteTask) : null); toast('تمت إضافة الملاحظة.', 'success'); setNoteBody(''); setNoteTask(''); await load(); }
    catch (caught: unknown) { toast(messageOf(caught, 'تعذّر حفظ الملاحظة.'), 'error'); }
    finally { setNoteBusy(false); }
  };

  return (
    <div className="space-y-6 text-[var(--staff-text)]" dir="rtl">
      {/* 1. مهامي الداخلية */}
      <CcCard className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
        <CcSectionTitle
          title="مهامي الداخلية"
          subtitle="افتح ملف المهمة للمراسلات والملفات والتسليم."
          badge={assignments.length}
          action={
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="rounded-xl border border-[var(--staff-line)] bg-black/20 px-3 py-1.5 text-xs font-semibold text-[var(--staff-text)] hover:bg-black/40 transition disabled:opacity-50"
            >
              تحديث
            </button>
          }
          className="mb-4 text-[var(--staff-text)]"
        />

        {loading ? (
          <p className="text-sm text-[var(--staff-muted)]">جارٍ التحميل...</p>
        ) : assignments.length === 0 ? (
          <CcEmpty title="لا توجد مهام مسندة إليك الآن" hint="ستظهر هنا المهام المسندة إليك فور تكليفك بها." />
        ) : (
          <div className="space-y-3">
            {assignments.map((assignment) => {
              const review = reviewFor(assignment);
              // «شخصيّةٌ لا عامّة» **نطاقُ الإسناد** لا إجباريّتُه: الجماعيّةُ تكون إجباريّةً
              // أيضاً، فلو قُرئت الإجباريّةُ شخصيّةً لقالت البطاقةُ «جماعية» و«شخصية» معاً.
              const audienceLabel = assignment.task_audience === 'INDIVIDUAL' ? 'مهمة خاصة بك وحدك' : 'مهمة جماعية';
              return (
                <CcCard key={assignment.id} className="rounded-xl border border-[var(--staff-line)] bg-black/10 p-4 transition hover:border-cyan-500/40">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-bold text-[var(--staff-text)] text-sm sm:text-base">{assignment.task_title}</h3>
                      <p className="mt-1 text-xs text-[var(--staff-muted)]">
                        الحالة: {assignment.status_display} · الإسناد #{formatNumber(assignment.id)} · الاستحقاق: {dateLabel(assignment.task_due_date)}
                      </p>
                      <div className="mt-2.5 flex flex-wrap gap-2">
                        <span className="rounded-md border border-[var(--staff-line)] px-2 py-0.5 text-xs font-semibold text-[var(--staff-text)]">
                          {audienceLabel}
                        </span>
                        <span className="rounded-md border border-[var(--staff-line)] px-2 py-0.5 text-xs font-semibold text-[var(--staff-text)]">
                          {assignment.is_mandatory ? 'إجبارية — مقبولة تلقائياً، لا يلزمك قبولها' : 'اختيارية — لك أن تقبلها'}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void showTask(assignment)}
                      disabled={busy === assignmentKey(assignment)}
                      className="text-xs font-bold text-cyan-300 hover:text-cyan-200 underline disabled:opacity-50 shrink-0"
                    >
                      التفاصيل
                    </button>
                  </div>

                  {review && (
                    <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-[var(--staff-text)]">
                      <p className="font-semibold text-amber-300">قرار المدير: {review.decision_display}</p>
                      {review.reviewer_notes && <p className="mt-1 text-xs text-[var(--staff-muted)]">ملاحظته: {review.reviewer_notes}</p>}
                    </div>
                  )}

                  {managerNotesFor(assignment.task).length > 0 && (
                    <p className="mt-2 text-xs text-cyan-300">توجد ملاحظات من المدير في ملف المهمة.</p>
                  )}

                  {assignment.status === 'OFFERED' && (
                    <button
                      type="button"
                      onClick={() => void accept(assignment)}
                      disabled={busy === assignmentKey(assignment)}
                      className="mt-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-950 shadow-sm transition disabled:opacity-50"
                    >
                      {busy === assignmentKey(assignment) ? 'جارٍ القبول...' : 'أقبلها'}
                    </button>
                  )}

                  {assignment.status === 'SUBMITTED' && (
                    <p className="mt-3 text-sm font-semibold text-amber-300">بانتظار مراجعة المدير.</p>
                  )}
                </CcCard>
              );
            })}
          </div>
        )}
      </CcCard>

      {/* 2. سجلّ تسليماتي وقرارات المدير */}
      <CcCard className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
        <CcSectionTitle
          title="سجلّ تسليماتي وقرارات المدير"
          subtitle="رفض تسليم مهمة المجمّع يعيدها إلى المجمّع ويسحب إسنادك، فيبقى القرار وملاحظته هنا."
          badge={submissions.length}
          className="mb-4 text-[var(--staff-text)]"
        />

        <div className="space-y-3">
          {submissions.length === 0 ? (
            <CcEmpty title="لم تسلّم مهمة بعد" hint="ستظهر هنا تسليماتك للمهام وقرارات المدير وملاحظاته." />
          ) : (
            submissions.map((submission) => (
              <CcCard key={submission.id} className="rounded-xl border border-[var(--staff-line)] bg-black/10 p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-bold text-sm text-[var(--staff-text)]">{submission.task_title}</p>
                  <span className="text-xs text-[var(--staff-muted)]">{dateLabel(submission.created_at)}</span>
                </div>
                <p className="mt-1.5 text-xs sm:text-sm text-[var(--staff-muted)]">{submission.body || 'سُلّمت بلا ملاحظات.'}</p>
                {submission.decision ? (
                  <p className="mt-2 text-xs sm:text-sm font-semibold text-[var(--staff-text)]">
                    قرار المدير: <span className="text-cyan-300">{submission.decision_display}</span>
                    {submission.reviewer_name ? ` — ${submission.reviewer_name}` : ''}
                    {submission.reviewer_notes ? ` · ${submission.reviewer_notes}` : ''}
                  </p>
                ) : (
                  <p className="mt-2 text-xs font-semibold text-amber-300">بانتظار مراجعة المدير.</p>
                )}
              </CcCard>
            ))
          )}
        </div>
      </CcCard>

      {/* 3. مهام المجمّع المتاحة */}
      <CcCard className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
        <CcSectionTitle
          title="مهام المجمّع المتاحة"
          subtitle="استلم المهمة أولاً؛ عندها يفتح لك ملفها ورفع ملفات العمل."
          badge={openTasks.length}
          className="mb-4 text-[var(--staff-text)]"
        />

        <div className="space-y-3">
          {openTasks.length === 0 ? (
            <CcEmpty title="لا توجد مهمة مجمّع متاحة" hint="لا توجد مهام مطروحة في المجمّع حالياً." />
          ) : (
            openTasks.map((task) => {
              const isFull = task.claim_limit !== null && task.claimed_count >= task.claim_limit;
              return (
                <CcCard key={task.id} className="rounded-xl border border-[var(--staff-line)] bg-black/10 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-bold text-sm sm:text-base text-[var(--staff-text)]">{task.title}</h3>
                      <p className="mt-1 text-xs text-[var(--staff-muted)]">
                        طالب بها {formatNumber(task.claimed_count)}{task.claim_limit === null ? '' : ` من حد ${formatNumber(task.claim_limit)}`} · الحالة: {task.status_display} · الاستحقاق: {dateLabel(task.due_date)}
                      </p>
                    </div>
                    {isFull ? (
                      <p className="text-xs font-bold text-amber-300 shrink-0">بلغت حدّ المطالبين.</p>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void claim(task)}
                        disabled={busy === taskKey(task)}
                        className="rounded-xl bg-cyan-500 hover:bg-cyan-400 px-4 py-2 text-xs font-bold text-slate-950 shadow-sm transition disabled:opacity-50 shrink-0"
                      >
                        {busy === taskKey(task) ? 'جارٍ الاستلام...' : 'أستلمها'}
                      </button>
                    )}
                  </div>
                </CcCard>
              );
            })
          )}
        </div>
      </CcCard>

      {/* 4. لوحات الملاحظات */}
      <section className="grid gap-6 lg:grid-cols-2">
        <CcCard className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
          <CcSectionTitle title="ملاحظاتي في مساحة العمل" className="mb-4 text-[var(--staff-text)]" />
          <form onSubmit={saveNote} className="space-y-3">
            <label className="block text-xs font-semibold text-[var(--staff-text)]">
              المهمة
              <select
                value={noteTask}
                onChange={(event) => setNoteTask(event.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--staff-line)] bg-black/10 px-3 py-2 text-xs text-[var(--staff-text)] focus:outline-none focus:ring-1 focus:ring-cyan-500"
              >
                <option value="">ملاحظة عامة</option>
                {assignments.map((assignment) => (
                  <option key={assignment.id} value={assignment.task}>{assignment.task_title}</option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-semibold text-[var(--staff-text)]">
              الملاحظة
              <textarea
                required
                value={noteBody}
                onChange={(event) => setNoteBody(event.target.value)}
                className="mt-1 min-h-24 w-full rounded-lg border border-[var(--staff-line)] bg-black/10 p-2.5 text-xs text-[var(--staff-text)] placeholder:text-[var(--staff-muted)] focus:outline-none focus:ring-1 focus:ring-cyan-500"
                placeholder="اكتب ملاحظتك هنا..."
              />
            </label>
            <button
              type="submit"
              disabled={noteBusy}
              className="rounded-xl bg-cyan-500 hover:bg-cyan-400 px-4 py-2 text-xs font-bold text-slate-950 shadow-sm transition disabled:opacity-50"
            >
              {noteBusy ? 'جارٍ الحفظ...' : 'أضف ملاحظة'}
            </button>
          </form>

          <div className="mt-4 space-y-2">
            {workspaceNotes.map((note) => (
              <div key={note.id} className="rounded-lg border border-[var(--staff-line)] bg-black/10 p-3 text-xs text-[var(--staff-text)]">
                <p>{note.body}</p>
                <span className="mt-1.5 block text-[10px] text-[var(--staff-muted)] font-mono" dir="ltr">{dateLabel(note.created_at)}</span>
              </div>
            ))}
          </div>
        </CcCard>

        <CcCard className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
          <CcSectionTitle title="ملاحظات المدير عليّ" badge={employeeNotes.length} className="mb-4 text-[var(--staff-text)]" />
          <div className="space-y-3">
            {employeeNotes.length === 0 ? (
              <CcEmpty title="لا توجد ملاحظات ظاهرة لك" hint="ستظهر هنا أي ملاحظات شخصية أو مهنية يوجهها المدير إليك." />
            ) : (
              employeeNotes.map((note) => (
                <CcCard key={note.id} className="rounded-xl border border-[var(--staff-line)] bg-black/10 p-3.5">
                  <p className="text-xs sm:text-sm text-[var(--staff-text)] leading-relaxed">{note.body}</p>
                  <p className="mt-2 text-[11px] text-[var(--staff-muted)]">
                    <span className="font-semibold text-cyan-300">{note.author_name}</span> · {note.task ? note.task_title : 'ملاحظة عامة'} · {dateLabel(note.created_at)}
                  </p>
                </CcCard>
              ))
            )}
          </div>
        </CcCard>
      </section>

      {selected && <TaskFileDrawer task={selected.task} assignment={selected.assignment} onClose={() => setSelected(null)} onChanged={load} />}
    </div>
  );
};
