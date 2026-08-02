import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bell, Check, Loader2, Plus, Trash2, Undo2, User } from 'lucide-react';
import {
  CustomerNote,
  CustomerNotePriority,
  createCustomerNote,
  deleteCustomerNote,
  listCustomerNotes,
  listTargetNotes,
  updateCustomerNote,
} from '../../services/customerNotesApi';
import type { PlatformNoteTarget } from '../../utils/entityLinks';
import { runCustomerNoteReminders } from '../../services/customerNoteReminders';
import { formatDateLocalized } from '../../utils/formatDate';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../contexts/ConfirmContext';

/** شارة الأولوية — «عاجل» هي وحدها التي تُنبّه عند معاملات الطرف. */
const PRIORITY_META: Record<CustomerNotePriority, { label: string; cls: string; rank: number }> = {
  urgent: { label: 'عاجل', cls: 'bg-red-600 text-white', rank: 0 },
  medium: { label: 'متوسط', cls: 'bg-amber-500 text-white', rank: 1 },
  normal: { label: 'عادي', cls: 'bg-[var(--color-surface-3)] text-[var(--color-text-muted)]', rank: 2 },
};

function priorityMeta(priority?: CustomerNotePriority) {
  return PRIORITY_META[priority || 'normal'] ?? PRIORITY_META.normal;
}

/** فرق أيام التقويم بين اليوم وتاريخ (موجب = مستقبلي، سالب = فائت). */
function daysUntil(iso: string): number {
  const d = new Date(iso.slice(0, 10) + 'T12:00:00');
  if (Number.isNaN(d.getTime())) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86400000);
}

/** شارة حالة الملاحظة — منجز/متأخر/اليوم/قادم/ملاحظة. */
function noteBadge(n: CustomerNote): { label: string; cls: string } {
  if (n.is_done) return { label: 'منجز', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' };
  if (!n.remind_on) return { label: 'ملاحظة', cls: 'bg-[var(--color-surface-3)] text-[var(--color-text-muted)]' };
  const d = daysUntil(n.remind_on);
  if (d < 0) return { label: `متأخر ${Math.abs(d)} يوم`, cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' };
  if (d === 0) return { label: 'اليوم', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' };
  if (d === 1) return { label: 'غداً', cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' };
  return { label: `بعد ${d} يوم`, cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' };
}

export interface CustomerNotesTabProps {
  customerId?: string;
  /** هدف عام داخل المنصة؛ يُستخدم عندما لا تكون الملاحظة مرتبطة بطرف. */
  target?: PlatformNoteTarget;
  /** معرّف ملاحظة لتحديدها/التمرير إليها (عند الوصول من إشعار تذكير). */
  focusNoteId?: string | null;
}

export const CustomerNotesTab: React.FC<CustomerNotesTabProps> = ({ customerId, target, focusNoteId }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [notes, setNotes] = useState<CustomerNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<{
    title: string; body: string; remind_on: string; priority: CustomerNotePriority;
  }>({
    title: '', body: '', remind_on: '', priority: 'normal',
  });
  const focusRef = useRef<HTMLDivElement | null>(null);

  // العاجل أولاً ثم المتوسط، والمنجز في الذيل — الترتيب داخل الأولوية يبقى الأحدث أولاً.
  const orderedNotes = useMemo(
    () => [...notes].sort((a, b) => {
      if (a.is_done !== b.is_done) return a.is_done ? 1 : -1;
      return priorityMeta(a.priority).rank - priorityMeta(b.priority).rank;
    }),
    [notes],
  );

  const load = useCallback(() => {
    setLoading(true);
    const request = customerId
      ? listCustomerNotes(customerId)
      : target
        ? listTargetNotes(target)
        : Promise.resolve([]);
    request
      .then((rows) => { setNotes(rows); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [customerId, target?.target_id, target?.target_type]);

  useEffect(() => { load(); }, [load]);

  // تمرير/تحديد الملاحظة القادمة من إشعار — بعد اكتمال التحميل.
  useEffect(() => {
    if (!focusNoteId || loading) return;
    const t = setTimeout(() => {
      focusRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
    return () => clearTimeout(t);
  }, [focusNoteId, loading, notes]);

  const handleAdd = async () => {
    const title = form.title.trim();
    if (!title) { toast('اكتب عنوان الملاحظة.', 'error'); return; }
    setSaving(true);
    try {
      const created = await createCustomerNote({
        ...(customerId
          ? { partner: Number(customerId) }
          : target || {}),
        title,
        body: form.body.trim(),
        remind_on: form.remind_on || null,
        priority: form.priority,
      });
      setNotes((prev) => [created, ...prev]);
      setForm({ title: '', body: '', remind_on: '', priority: 'normal' });
      toast('أُضيفت الملاحظة.', 'success');
      // تذكير مستحق اليوم/فائت ⇒ ادفع إشعار الموقع فوراً (لا انتظار لإعادة التحميل).
      if (created.remind_on && !created.is_done && daysUntil(created.remind_on) <= 0) {
        void runCustomerNoteReminders(localStorage.getItem('userId') || 'self');
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : 'تعذّر حفظ الملاحظة.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const toggleDone = async (n: CustomerNote) => {
    try {
      const updated = await updateCustomerNote(n.id, { is_done: !n.is_done });
      setNotes((prev) => prev.map((x) => (x.id === n.id ? updated : x)));
    } catch (e) {
      toast(e instanceof Error ? e.message : 'تعذّر التحديث.', 'error');
    }
  };

  const remove = async (n: CustomerNote) => {
    if (!(await confirm({ message: `حذف الملاحظة «${n.title}»؟`, confirmText: 'حذف', danger: true }))) return;
    try {
      await deleteCustomerNote(n.id);
      setNotes((prev) => prev.filter((x) => x.id !== n.id));
      toast('حُذفت الملاحظة.', 'success');
    } catch (e) {
      toast(e instanceof Error ? e.message : 'تعذّر الحذف.', 'error');
    }
  };

  return (
    <div className="p-4" dir="rtl">
      {/* نموذج إضافة ملاحظة/تذكير */}
      <div className="border border-[var(--aseel-border)] rounded-lg p-3 mb-4 bg-[var(--color-surface,#fff)]">
        <div className="flex items-center gap-2 mb-2 text-sm font-bold text-[var(--aseel-ink)]">
          <Plus className="w-4 h-4 text-[var(--aseel-accent,#2563eb)]" />
          ملاحظة / تذكير جديد
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <input
            className="aseel-input md:col-span-2"
            placeholder="العنوان (مثال: متابعة دفعة مستحقة)"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <label className="flex items-center gap-1.5 text-xs text-[var(--aseel-ink-soft)]">
            الأولوية
            <select
              className="aseel-input flex-1"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value as CustomerNotePriority })}
              title="«عاجل» مع يوم تذكير ⇒ تنبيه لكل مستخدم عند أي معاملة لهذا الطرف"
            >
              <option value="normal">عادي</option>
              <option value="medium">متوسط</option>
              <option value="urgent">عاجل</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs text-[var(--aseel-ink-soft)]">
            <Bell className="w-3.5 h-3.5" />
            <input
              type="date"
              className="aseel-input flex-1"
              value={form.remind_on}
              onChange={(e) => setForm({ ...form, remind_on: e.target.value })}
              title="يوم التذكير (اختياري) — يظهر في إشعارات الموقع"
            />
          </label>
          <textarea
            className="aseel-input md:col-span-3"
            rows={2}
            placeholder="تفاصيل الملاحظة (اختياري)"
            value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })}
            style={{ resize: 'vertical' }}
          />
        </div>
        <div className="flex justify-end mt-2">
          <button
            type="button"
            onClick={handleAdd}
            disabled={saving}
            className="aseel-toolbtn flex items-center gap-1.5"
            style={{ padding: '5px 16px', fontWeight: 700 }}
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            إضافة
          </button>
        </div>
      </div>

      {/* القائمة (خط زمني) */}
      {loading ? (
        <div className="flex items-center gap-2 text-[var(--aseel-ink-soft)] p-4">
          <Loader2 className="w-4 h-4 animate-spin" /> جاري التحميل…
        </div>
      ) : error ? (
        <div className="text-[var(--aseel-danger,#c00)] p-4">{error}</div>
      ) : notes.length === 0 ? (
        <div className="text-center text-[var(--aseel-ink-soft)] p-10">
          لا توجد ملاحظات بعد {customerId ? 'لهذا الطرف' : 'لهذا الهدف'}. ابدأ بإضافة ملاحظة أو تذكير أعلاه.
        </div>
      ) : (
        <div className="space-y-2">
          {orderedNotes.map((n) => {
            const badge = noteBadge(n);
            const prio = priorityMeta(n.priority);
            const isFocus = focusNoteId != null && String(n.id) === String(focusNoteId);
            return (
              <div
                key={n.id}
                ref={isFocus ? focusRef : undefined}
                className={`border rounded-lg p-3 transition-shadow ${
                  isFocus
                    ? 'border-[var(--aseel-accent,#2563eb)] ring-2 ring-[var(--aseel-accent,#2563eb)]/40 shadow'
                    : 'border-[var(--aseel-border)]'
                } ${n.is_done ? 'opacity-70' : ''}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${prio.cls}`}
                        title={
                          n.priority === 'urgent'
                            ? 'تظهر كتنبيه لكل مستخدم عند أي معاملة لهذا الطرف بعد حلول موعدها'
                            : undefined
                        }
                      >
                        {prio.label}
                      </span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${badge.cls}`}>
                        {badge.label}
                      </span>
                      <h4 className={`text-sm font-bold text-[var(--aseel-ink)] ${n.is_done ? 'line-through' : ''}`}>
                        {n.title}
                      </h4>
                    </div>
                    {n.body && (
                      <p className="text-xs text-[var(--aseel-ink-soft)] mt-1 whitespace-pre-wrap">{n.body}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1.5 text-[10px] text-[var(--aseel-ink-soft)]">
                      {n.remind_on && (
                        <span className="flex items-center gap-1"><Bell className="w-3 h-3" />{formatDateLocalized(n.remind_on)}</span>
                      )}
                      <span className="flex items-center gap-1"><User className="w-3 h-3" />{n.created_by_name || '—'}</span>
                      <span>{formatDateLocalized(n.created_at)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => toggleDone(n)}
                      title={n.is_done ? 'إلغاء الإنجاز' : 'وضع كمنجز'}
                      className="p-1.5 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
                    >
                      {n.is_done ? <Undo2 className="w-4 h-4" /> : <Check className="w-4 h-4 text-emerald-600" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(n)}
                      title="حذف"
                      className="p-1.5 rounded-md text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
