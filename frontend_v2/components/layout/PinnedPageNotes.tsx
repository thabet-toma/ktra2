import React, { useState } from 'react';
import { Check, ChevronDown, ChevronUp, Loader2, Pin } from 'lucide-react';
import { CustomerNote, updateCustomerNote } from '../../services/customerNotesApi';
import { useToast } from '../../contexts/ToastContext';
import { formatDateLocalized } from '../../utils/formatDate';
import { formatNumber } from '../../utils/formatNumber';
import {
  isLongNoteBody,
  pinnedNotesSummary,
  readPinnedNotesCollapsed,
  writePinnedNotesCollapsed,
} from '../../utils/pinnedPageNotes';

interface PinnedPageNotesProps {
  /** الملاحظات المثبّتة غير المنجزة لهذه الصفحة (يشتقّها AppLayout من طلب واحد). */
  notes: CustomerNote[];
  userId: string | number;
  /** مفتاح الصفحة (المسار وحده) — يحدّد مفتاح الطيّ المحفوظ. */
  pathname: string;
  /** يفتح نافذة «ملاحظات وتذكيرات الصفحة» الكاملة. */
  onOpenAll: () => void;
  /** بعد «منجز» — ليعيد AppLayout الجلب فيختفي المنجز من الشريط والشارة معاً. */
  onChanged: () => void;
}

/**
 * ملاحظة صفحة مثبّتة تظهر تلقائياً بالأصفر أعلى الصفحة لكل مستخدمي الشركة بدل أن
 * تبقى خلف زر. نمط Odoo 18.3 (شريط غير حاجب بدل نافذة منبثقة) مع تثبيتٍ صريح،
 * و«منجز»، وطيٍّ يتذكّره كل مستخدم لكل صفحة. لا شيء يُرسم بلا ملاحظات.
 * يُركَّب في AppLayout بـ`key={pathname}` فتُقرأ حالة الطيّ مرة لكل صفحة.
 */
export const PinnedPageNotes: React.FC<PinnedPageNotesProps> = ({
  notes, userId, pathname, onOpenAll, onChanged,
}) => {
  const toast = useToast();
  const [collapsed, setCollapsed] = useState(
    () => readPinnedNotesCollapsed(() => localStorage, userId, pathname),
  );
  const [expandedBodies, setExpandedBodies] = useState<ReadonlySet<number>>(new Set());
  const [busyId, setBusyId] = useState<number | null>(null);

  if (notes.length === 0) return null;

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    writePinnedNotesCollapsed(() => localStorage, userId, pathname, next);
  };

  const toggleBody = (id: number) => {
    setExpandedBodies((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const markDone = async (note: CustomerNote) => {
    setBusyId(note.id);
    try {
      await updateCustomerNote(note.id, { is_done: true });
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'تعذّر تحديث الملاحظة.', 'error');
    } finally {
      setBusyId(null);
    }
  };

  const shell = 'mx-3 mt-3 rounded-lg border border-amber-300 bg-amber-50 text-amber-950 '
    + 'dark:border-amber-700/60 dark:bg-amber-900/20 dark:text-amber-100';

  return (
    <section
      role="region"
      aria-label="ملاحظات مثبّتة على الصفحة"
      data-testid="pinned-page-notes"
      className={shell}
      dir="rtl"
    >
      <div className="flex items-center gap-2 px-3 py-1.5">
        <Pin className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
        {collapsed ? (
          <span className="min-w-0 flex-1 truncate text-sm font-bold">
            {pinnedNotesSummary(notes.length, formatNumber(notes.length, { maxDecimals: 0 }))}
          </span>
        ) : (
          <span className="min-w-0 flex-1 text-xs font-bold text-amber-800 dark:text-amber-300">
            ملاحظات مثبّتة على هذه الصفحة
          </span>
        )}
        <button
          type="button"
          onClick={onOpenAll}
          className="rounded-md px-2 py-1 text-xs font-bold text-amber-900 hover:bg-amber-100 dark:text-amber-100 dark:hover:bg-amber-900/40"
        >
          كل الملاحظات
        </button>
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'توسيع الملاحظات المثبّتة' : 'طيّ الملاحظات المثبّتة'}
          title={collapsed ? 'توسيع' : 'طيّ'}
          className="rounded-md p-1 text-amber-900 hover:bg-amber-100 dark:text-amber-100 dark:hover:bg-amber-900/40"
        >
          {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
        </button>
      </div>

      {!collapsed && (
        <ul className="divide-y divide-amber-200 border-t border-amber-200 dark:divide-amber-700/40 dark:border-amber-700/40">
          {notes.map((note) => {
            const long = isLongNoteBody(note.body);
            const bodyOpen = expandedBodies.has(note.id);
            return (
              <li key={note.id} className="flex items-start gap-3 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {note.priority === 'urgent' && (
                      <span className="rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-bold text-white">
                        عاجل
                      </span>
                    )}
                    <h4 className="text-sm font-bold">{note.title}</h4>
                  </div>
                  {note.body && (
                    <>
                      <p
                        className={`mt-0.5 whitespace-pre-wrap text-xs ${
                          long && !bodyOpen ? 'line-clamp-3' : ''
                        }`}
                      >
                        {note.body}
                      </p>
                      {long && (
                        <button
                          type="button"
                          onClick={() => toggleBody(note.id)}
                          className="mt-0.5 text-xs font-bold text-amber-800 underline dark:text-amber-300"
                        >
                          {bodyOpen ? 'أقل' : 'المزيد'}
                        </button>
                      )}
                    </>
                  )}
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 text-[10px] text-amber-800 dark:text-amber-300">
                    {note.created_by_name && <span>{note.created_by_name}</span>}
                    <span>{formatDateLocalized(note.created_at)}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => markDone(note)}
                  disabled={busyId === note.id}
                  className="flex shrink-0 items-center gap-1 rounded-md border border-amber-400 bg-white/60 px-2 py-1 text-xs font-bold text-amber-950 hover:bg-white disabled:opacity-60 dark:border-amber-600 dark:bg-amber-950/40 dark:text-amber-100 dark:hover:bg-amber-950/70"
                >
                  {busyId === note.id
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : <Check className="h-3.5 w-3.5" />}
                  منجز
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
