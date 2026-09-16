import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { useToast } from '../../../../contexts/ToastContext';
import { formatDateTimeValue, formatDateValue } from '../../../../utils/formatDate';
import { formatNumber } from '../../../../utils/formatNumber';
import {
  acceptPlatformTaskAssignment,
  createPlatformEmployeeNote,
  createPlatformWorkspaceNote,
  getPlatformTask,
  getPlatformTaskAttachmentFile,
  getPlatformTaskThread,
  listPlatformTaskAssignments,
  submitPlatformTaskAssignment,
  uploadPlatformTaskAttachment,
  type PlatformEmployeeNoteVisibility,
  type PlatformTask,
  type PlatformTaskAssignment,
  type PlatformTaskAttachment,
  type PlatformTaskAttachmentKind,
  type PlatformTaskThreadEvent,
} from '../../../../services/platformTasksApi';
import { CcCard } from '../../ui/CcCard';
import { CcEmpty } from '../../ui/CcEmpty';
import { CcPill } from '../../ui/CcPill';

interface TaskFileDrawerProps {
  task: PlatformTask;
  /** إسناد الرائي إن كان موظفاً — `null` للمدير. */
  assignment?: PlatformTaskAssignment | null;
  isManager?: boolean;
  onClose: () => void;
  onChanged?: () => void | Promise<void>;
}

const messageOf = (caught: unknown, fallback: string) => caught instanceof Error ? caught.message : fallback;
const dateLabel = (value: string | null | undefined) => value ? formatDateValue(value) : '—';

/**
 * قيمةُ `PlatformTaskAttachment.Kind.WORK` كما يرسلها الخادم — **صغيرةً**.
 *
 * وهي ثابتٌ مكتوبٌ بنوعِه لا نصٌّ حرٌّ في موضع المقارنة: نصٌّ حرٌّ بحالةِ أحرفٍ
 * خاطئةٍ (`'WORK'`) يجعل الترشيحَ كاذباً **دائماً** بلا أن يبلّغ `tsc` — لأنّ
 * `Pick<..., 'kind'>` هنا يعبر عبر واجهةٍ وسيطةٍ فلا تُقارَن الحرفيّةُ بالاتّحاد
 * مباشرةً. والتصريحُ بالنوع يجعل الخطأَ خطأَ ترجمةٍ لا عطباً صامتاً.
 */
const WORK_KIND: PlatformTaskAttachmentKind = 'work';

const eventLabel = (event: PlatformTaskThreadEvent) => {
  if (event.type === 'attachment') return 'مرفق';
  if (event.type === 'manager_note') return 'ملاحظة المدير';
  if (event.type === 'employee_note') return 'ملاحظة الموظف';
  if (event.type === 'submission') return 'تسليم';
  // ‏`decision_display` من الخادم لا قاموسٌ هنا: قاموسٌ ثانٍ يتخلّف عن
  // `choices` أوّلَ ما يُضاف قرارٌ، فيظهر الرمزُ الإنجليزيُّ الخامُّ للمستخدم.
  return event.decision_display || 'مراجعة';
};

export const TaskFileDrawer: React.FC<TaskFileDrawerProps> = ({ task, assignment = null, isManager = false, onClose, onChanged }) => {
  const toast = useToast();
  const [currentTask, setCurrentTask] = useState(task);
  const [events, setEvents] = useState<PlatformTaskThreadEvent[]>([]);
  const [assignments, setAssignments] = useState<PlatformTaskAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [workspaceBody, setWorkspaceBody] = useState('');
  const [submissionBody, setSubmissionBody] = useState('');
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<number[]>([]);
  const [noteEmployee, setNoteEmployee] = useState('');
  const [managerBody, setManagerBody] = useState('');
  const [visibility, setVisibility] = useState<PlatformEmployeeNoteVisibility>('EMPLOYEE');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextTask, thread, nextAssignments] = await Promise.all([
        getPlatformTask(task.id),
        getPlatformTaskThread(task.id),
        isManager ? listPlatformTaskAssignments() : Promise.resolve<PlatformTaskAssignment[]>([]),
      ]);
      const taskAssignments = nextAssignments.filter((item) => item.task === task.id);
      setCurrentTask(nextTask);
      setEvents(thread.events);
      setAssignments(taskAssignments);
      // الافتراضُ أوّلُ **المُسنَد إليهم في هذه المهمّة**: الحالةُ الغالبةُ مهمّةٌ
      // لموظّفٍ واحد، فاختيارٌ يدويٌّ من قائمةٍ بعنصرٍ واحدٍ خطوةٌ بلا معنى. وكان
      // يُقرأ من الإسنادات كلِّها، فيقع الافتراضُ على صاحب مهمّةٍ أخرى — قيمةٌ
      // خارج خيارات القائمة تظهر فارغةً، ولو أُرسلت لردّها الخادمُ.
      setNoteEmployee((current) => current || (taskAssignments[0] ? String(taskAssignments[0].employee) : ''));
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر تحميل ملفّ المهمة.'), 'error');
    } finally {
      setLoading(false);
    }
  }, [isManager, task.id, toast]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setCurrentTask(task); }, [task]);

  /**
   * ما **يصلح** أن يُرسَل مع تسليمٍ: ملفُّ عملٍ لم يُرسَل بعد.
   *
   * و`kind === 'WORK'` شرطٌ لا زينة: `submit_platform_task` تنقل `WORK` وحدَها،
   * فملفٌّ رافق تسليماً سابقاً (`DELIVERY`) يُعرَض للاختيار ثمّ **يُتجاهَل بصمت**
   * — لا خطأ ولا أثر، وهو أسوأُ ما يُعرَض لمستخدم.
   */
  const workAttachments = useMemo(() => events.flatMap((event) => event.type === 'attachment' && event.employee !== null
    ? event.attachments.filter((attachment) => attachment.employee !== null && attachment.kind === WORK_KIND)
    : []), [events]);

  const changed = async () => {
    await load();
    await onChanged?.();
  };

  const openAttachment = async (attachment: Pick<PlatformTaskAttachment, 'id' | 'name'>) => {
    const popup = window.open('about:blank', '_blank');
    if (!popup) {
      toast('حظر المتصفّح نافذة فتح الملف.', 'error');
      return;
    }
    setBusy(`open-${attachment.id}`);
    try {
      const blob = await getPlatformTaskAttachmentFile(currentTask.id, attachment.id);
      const objectUrl = URL.createObjectURL(blob);
      popup.document.title = attachment.name || 'ملف المهمة';
      const viewer = popup.document.createElement('iframe');
      viewer.src = objectUrl;
      viewer.title = attachment.name;
      viewer.width = '100%';
      viewer.height = String(Math.max(popup.innerHeight - 24, 480));
      viewer.setAttribute('frameborder', '0');
      popup.document.body.replaceChildren(viewer);
      popup.opener = null;
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (caught: unknown) {
      popup.close();
      toast(messageOf(caught, 'تعذّر فتح الملف.'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy('upload');
    try {
      await uploadPlatformTaskAttachment(currentTask.id, file);
      toast(isManager ? 'تم إرفاق ملفّ الشرح.' : 'تم رفع ملفّ العمل.', 'success');
      await changed();
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر رفع الملف.'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const saveWorkspaceNote = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!workspaceBody.trim()) return;
    setBusy('workspace-note');
    try {
      await createPlatformWorkspaceNote(workspaceBody.trim(), currentTask.id);
      setWorkspaceBody('');
      toast('تمت إضافة الملاحظة.', 'success');
      await changed();
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر حفظ الملاحظة.'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const accept = async () => {
    if (!assignment) return;
    setBusy('accept');
    try {
      await acceptPlatformTaskAssignment(assignment.id);
      toast('تم قبول المهمة.', 'success');
      await changed();
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر قبول المهمة.'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!assignment) return;
    setBusy('submit');
    try {
      await submitPlatformTaskAssignment(assignment.id, submissionBody.trim(), selectedAttachmentIds);
      setSubmissionBody('');
      setSelectedAttachmentIds([]);
      toast('تم تسليم المهمة للمراجعة.', 'success');
      await changed();
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر تسليم المهمة.'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const saveManagerNote = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!noteEmployee || !managerBody.trim()) return;
    setBusy('manager-note');
    try {
      await createPlatformEmployeeNote(Number(noteEmployee), managerBody.trim(), visibility, currentTask.id);
      setManagerBody('');
      toast('تمت إضافة ملاحظة المهمة.', 'success');
      await changed();
    } catch (caught: unknown) {
      toast(messageOf(caught, 'تعذّر حفظ ملاحظة المهمة.'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const canSubmit = !!assignment && ['ACCEPTED', 'IN_PROGRESS', 'RETURNED'].includes(assignment.status);
  const mandatory = assignment ? assignment.is_mandatory : currentTask.is_mandatory;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-3 sm:p-6 flex items-center justify-center sm:justify-end" dir="rtl" role="dialog" aria-modal="true" aria-label="ملف المهمة">
      <section className="mr-auto flex h-full w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] shadow-2xl">
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--staff-line)] p-5">
          <div>
            <h2 className="text-lg font-bold text-[var(--staff-text)] flex items-center gap-2">
              <span>{currentTask.title}</span>
              <span className="font-mono text-xs font-normal text-[var(--staff-muted)]">#{formatNumber(currentTask.id)}</span>
            </h2>
            <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
              <CcPill tone={currentTask.status === 'COMPLETED' ? 'success' : 'accent'}>
                {currentTask.status_display}
              </CcPill>
              <CcPill tone={currentTask.priority === 'URGENT' || currentTask.priority === 'HIGH' ? 'danger' : currentTask.priority === 'MEDIUM' ? 'warning' : 'neutral'}>
                {currentTask.priority_display}
              </CcPill>
              <span className="text-[var(--staff-muted)]">الاستحقاق: {dateLabel(currentTask.due_date)}</span>
              <span className="text-[var(--staff-muted)]">·</span>
              <span className="text-[var(--staff-muted)]">{mandatory ? 'إجبارية' : 'اختيارية'}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[var(--staff-line)] bg-cc-surface px-3 py-1.5 text-sm font-semibold text-[var(--staff-text)] hover:bg-cc-surface-2 transition"
          >
            إغلاق
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto p-5">
          {/* شرح المدير */}
          <CcCard className="border-[var(--staff-line)] bg-[var(--staff-panel)]">
            <h3 className="text-sm font-bold text-[var(--staff-text)]">شرح المدير</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[var(--staff-muted)]">
              {currentTask.description || 'لا يوجد وصف.'}
            </p>
            {currentTask.brief_attachments.length > 0 && (
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
                {currentTask.brief_attachments.map((attachment) => (
                  <div key={attachment.id} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--staff-line)] bg-black/20 p-2.5 text-sm text-[var(--staff-text)]">
                    <span className="truncate text-xs font-medium">{attachment.name}</span>
                    <button
                      type="button"
                      onClick={() => void openAttachment(attachment)}
                      disabled={busy === `open-${attachment.id}`}
                      className="shrink-0 text-xs font-semibold text-cyan-300 hover:text-cyan-200 underline disabled:opacity-50"
                    >
                      افتح
                    </button>
                  </div>
                ))}
              </div>
            )}
            {isManager && (
              <label className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--staff-line)] bg-cc-surface px-3 py-2 text-xs font-semibold text-[var(--staff-text)] hover:bg-cc-surface-2 transition">
                <span>{busy === 'upload' ? 'جارٍ الرفع...' : 'أرفق شرحاً'}</span>
                <input
                  type="file"
                  className="sr-only"
                  disabled={busy === 'upload'}
                  onChange={(event) => {
                    void upload(event.target.files?.[0]);
                    event.currentTarget.value = '';
                  }}
                />
              </label>
            )}
          </CcCard>

          {/* خيط المهمة / Chat bubbles */}
          <section className="space-y-3">
            <h3 className="text-sm font-bold text-[var(--staff-text)]">خيط المهمة</h3>
            {loading ? (
              <p className="text-sm text-[var(--staff-muted)]">جارٍ التحميل...</p>
            ) : events.length === 0 ? (
              <CcEmpty title="لا أحداث على المهمة بعد." hint="ستظهر هنا الملاحظات والتسليمات والتحديثات." />
            ) : (
              <div className="space-y-3 pt-1">
                {events.map((event, index) => {
                  const isIncomingManager = event.author_role === 'manager';
                  return (
                    <div
                      key={`${event.type}-${event.at}-${index}`}
                      className={`flex flex-col ${isIncomingManager ? 'items-start' : 'items-end'}`}
                    >
                      <article
                        className={`max-w-[85%] rounded-2xl p-3.5 shadow-sm ${
                          isIncomingManager
                            ? 'rounded-tr-none bg-cc-surface-2 border border-cc-border text-cc-text'
                            : 'rounded-tl-none bg-emerald-950/40 border border-emerald-500/30 text-cc-text'
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1.5">
                          <CcPill
                            tone={isIncomingManager ? 'accent' : 'success'}
                          >
                            {eventLabel(event)}
                          </CcPill>
                          <span className="text-xs font-bold text-cc-text">{event.author_name}</span>
                        </div>

                        {event.body && (
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-cc-text/90">{event.body}</p>
                        )}

                        {event.attachments.length > 0 && (
                          <div className="mt-2.5 grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {event.attachments.map((attachment) => (
                              <div
                                key={attachment.id}
                                className="flex items-center justify-between gap-2 rounded-lg border border-[var(--staff-line)] bg-black/25 px-2.5 py-1.5 text-xs text-cc-text"
                              >
                                <span className="truncate">{attachment.name}</span>
                                <button
                                  type="button"
                                  onClick={() => void openAttachment(attachment)}
                                  disabled={busy === `open-${attachment.id}`}
                                  className="shrink-0 text-cyan-300 hover:text-cyan-200 underline font-medium disabled:opacity-50"
                                >
                                  افتح
                                </button>
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="mt-2.5 flex items-center justify-start text-[10px] text-[var(--staff-muted)]">
                          <time className="font-mono">{formatDateTimeValue(event.at)}</time>
                        </div>
                      </article>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* مساحة عملي */}
          {assignment && !isManager && (
            <CcCard className="space-y-4 border-[var(--staff-line)] bg-[var(--staff-panel)]">
              <h3 className="text-sm font-bold text-[var(--staff-text)]">مساحة عملي</h3>

              <div className="flex flex-wrap items-center gap-2.5">
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--staff-line)] bg-cc-surface px-3 py-2 text-xs font-semibold text-[var(--staff-text)] hover:bg-cc-surface-2 transition">
                  <span>{busy === 'upload' ? 'جارٍ الرفع...' : 'ارفع ملفاً'}</span>
                  <input
                    type="file"
                    className="sr-only"
                    disabled={busy === 'upload'}
                    onChange={(event) => {
                      void upload(event.target.files?.[0]);
                      event.currentTarget.value = '';
                    }}
                  />
                </label>
                {assignment.status === 'OFFERED' && (
                  <button
                    type="button"
                    onClick={() => void accept()}
                    disabled={busy === 'accept'}
                    className="rounded-lg bg-cyan-500 px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
                  >
                    {busy === 'accept' ? 'جارٍ القبول...' : 'أقبلها'}
                  </button>
                )}
              </div>

              <form onSubmit={saveWorkspaceNote} className="space-y-2">
                <label className="block text-xs font-semibold text-[var(--staff-text)]">
                  أضف ملاحظة
                  <textarea
                    required
                    value={workspaceBody}
                    onChange={(event) => setWorkspaceBody(event.target.value)}
                    className="mt-1 min-h-20 w-full rounded-lg border border-[var(--staff-line)] bg-black/20 p-2 text-xs text-[var(--staff-text)] placeholder:text-[var(--staff-muted)] focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    placeholder="اكتب ملاحظة أو استفساراً حول هذه المهمة..."
                  />
                </label>
                <button
                  type="submit"
                  disabled={busy === 'workspace-note'}
                  className="rounded-lg border border-[var(--staff-line)] bg-cc-surface px-3 py-1.5 text-xs font-semibold text-[var(--staff-text)] hover:bg-cc-surface-2 transition disabled:opacity-50"
                >
                  {busy === 'workspace-note' ? 'جارٍ الحفظ...' : 'أضف الملاحظة'}
                </button>
              </form>

              {canSubmit && (
                <form onSubmit={submit} className="space-y-3 rounded-xl border border-[var(--staff-line)] bg-black/15 p-3.5">
                  <h4 className="text-xs font-bold text-[var(--staff-text)]">تسليم المهمة</h4>
                  <label className="block text-xs font-medium text-[var(--staff-text)]">
                    ملاحظات التسليم
                    <textarea
                      value={submissionBody}
                      onChange={(event) => setSubmissionBody(event.target.value)}
                      className="mt-1 min-h-20 w-full rounded-lg border border-[var(--staff-line)] bg-black/20 p-2 text-xs text-[var(--staff-text)] placeholder:text-[var(--staff-muted)] focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      placeholder="صف ما تم إنجازه أو أي تفاصيل تخص التسليم..."
                    />
                  </label>
                  <div>
                    <p className="text-xs font-semibold text-[var(--staff-text)]">ملفات العمل المرفوعة</p>
                    {workAttachments.length === 0 ? (
                      <p className="mt-1 text-xs text-[var(--staff-muted)]">ارفع ملفاً أولاً إن أردت إرساله مع التسليم.</p>
                    ) : (
                      <div className="mt-2 space-y-2">
                        {workAttachments.map((attachment) => (
                          <label key={attachment.id} className="flex items-center gap-2 text-xs text-[var(--staff-text)]">
                            <input
                              type="checkbox"
                              checked={selectedAttachmentIds.includes(attachment.id)}
                              onChange={(event) =>
                                setSelectedAttachmentIds((ids) =>
                                  event.target.checked ? [...ids, attachment.id] : ids.filter((id) => id !== attachment.id)
                                )
                              }
                            />
                            <span>{attachment.name}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    type="submit"
                    disabled={busy === 'submit'}
                    className="rounded-lg bg-emerald-500 px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
                  >
                    {busy === 'submit' ? 'جارٍ التسليم...' : 'سلّم المهمة'}
                  </button>
                </form>
              )}
            </CcCard>
          )}

          {/* توجيه ملاحظة للموظف (المدير) */}
          {isManager && (
            <CcCard className="border-[var(--staff-line)] bg-[var(--staff-panel)]">
              <h3 className="text-sm font-bold text-[var(--staff-text)]">ملاحظة للموظف</h3>
              <form onSubmit={saveManagerNote} className="mt-3 space-y-3">
                <label className="block text-xs font-semibold text-[var(--staff-text)]">
                  الموظف
                  <select
                    required
                    value={noteEmployee}
                    onChange={(event) => setNoteEmployee(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-[var(--staff-line)] bg-black/20 p-2 text-xs text-[var(--staff-text)] focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  >
                    <option value="">اختر موظفاً</option>
                    {assignments.map((assignment) => (
                      <option key={assignment.id} value={assignment.employee} className="bg-slate-900 text-slate-100">
                        {assignment.employee_name} · {assignment.status_display}
                      </option>
                    ))}
                  </select>
                </label>
                <fieldset>
                  <legend className="text-xs font-semibold text-[var(--staff-text)]">الرؤية</legend>
                  <div className="mt-1 flex items-center gap-4">
                    <label className="text-xs text-[var(--staff-text)] flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="task-file-visibility"
                        checked={visibility === 'EMPLOYEE'}
                        onChange={() => setVisibility('EMPLOYEE')}
                      />
                      <span>يراها الموظف</span>
                    </label>
                    <label className="text-xs text-[var(--staff-text)] flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="task-file-visibility"
                        checked={visibility === 'MANAGER_ONLY'}
                        onChange={() => setVisibility('MANAGER_ONLY')}
                      />
                      <span>للمدير فقط</span>
                    </label>
                  </div>
                </fieldset>
                <label className="block text-xs font-semibold text-[var(--staff-text)]">
                  الملاحظة
                  <textarea
                    required
                    value={managerBody}
                    onChange={(event) => setManagerBody(event.target.value)}
                    className="mt-1 min-h-20 w-full rounded-lg border border-[var(--staff-line)] bg-black/20 p-2 text-xs text-[var(--staff-text)] placeholder:text-[var(--staff-muted)] focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    placeholder="اكتب توجيهاً أو ملاحظة للموظف..."
                  />
                </label>
                <button
                  type="submit"
                  disabled={busy === 'manager-note' || assignments.length === 0}
                  className="rounded-lg border border-[var(--staff-line)] bg-cc-surface px-3 py-1.5 text-xs font-semibold text-[var(--staff-text)] hover:bg-cc-surface-2 transition disabled:opacity-50"
                >
                  {busy === 'manager-note' ? 'جارٍ الحفظ...' : 'أضف الملاحظة'}
                </button>
                {assignments.length === 0 && (
                  <p className="text-xs text-[var(--staff-muted)]">لا يمكن توجيه ملاحظة قبل إسناد المهمة.</p>
                )}
              </form>
            </CcCard>
          )}
        </div>
      </section>
    </div>
  );
};
