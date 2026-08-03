import React, { useEffect, useRef, useState } from "react";
import { Plus, RefreshCw, Save, Trash2 } from "lucide-react";

import {
  createDevelopmentNote, deleteDevelopmentNote, listDevelopmentNotes,
  updateDevelopmentNote, type DevelopmentNote, type DevelopmentNoteWrite,
} from "../../services/platformAdminApi";
import { AseelDateInput } from "../aseel/AseelDateInput";


const emptyNote = (position: number): DevelopmentNoteWrite => ({
  title: "",
  description: "",
  status: "todo",
  priority: "medium",
  assignee: "",
  due_date: null,
  position,
});

const cellClass = "w-full min-w-28 border-0 bg-transparent px-2 py-2 text-sm text-[var(--color-text)] outline-none focus:bg-[var(--color-surface-2)] focus:ring-1 focus:ring-inset focus:ring-[var(--color-primary)]";

export const DevelopmentNotesPage: React.FC = () => {
  const [notes, setNotes] = useState<DevelopmentNote[]>([]);
  const [draft, setDraft] = useState<DevelopmentNoteWrite>(() => emptyNote(0));
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const draftTitleRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    listDevelopmentNotes()
      .then(setNotes)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "تعذّر تحميل الملاحظات"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const patchLocal = <K extends keyof DevelopmentNote>(id: number, key: K, value: DevelopmentNote[K]) => {
    setNotes((current) => current.map((note) => note.id === id ? { ...note, [key]: value } : note));
  };

  const save = async (note: DevelopmentNote) => {
    setSavingId(note.id);
    setError(null);
    try {
      const saved = await updateDevelopmentNote(note.id, {
        title: note.title, description: note.description, status: note.status,
        priority: note.priority, assignee: note.assignee,
        due_date: note.due_date || null, position: note.position,
      });
      setNotes((current) => current.map((row) => row.id === note.id ? saved : row));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل حفظ الملاحظة");
    } finally {
      setSavingId(null);
    }
  };

  const add = async () => {
    if (!draft.title.trim()) {
      setError("اكتب عنوان ملاحظة التطوير أولاً.");
      return;
    }
    setSavingId("new");
    setError(null);
    try {
      const created = await createDevelopmentNote({ ...draft, title: draft.title.trim() });
      setNotes((current) => [...current, created]);
      setDraft(emptyNote(notes.length + 1));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل إضافة الملاحظة");
    } finally {
      setSavingId(null);
    }
  };

  const remove = async (note: DevelopmentNote) => {
    if (!window.confirm(`حذف ملاحظة «${note.title}»؟`)) return;
    setSavingId(note.id);
    try {
      await deleteDevelopmentNote(note.id);
      setNotes((current) => current.filter((row) => row.id !== note.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل حذف الملاحظة");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <main className="p-4 md:p-6" dir="rtl">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-xl font-bold text-[var(--color-text)]">ملاحظات التطوير</h1><p className="text-sm aseel-text-soft">جدول منصّي قابل للتحرير والحفظ مثل ورقة العمل</p></div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => draftTitleRef.current?.focus()} className="aseel-btn aseel-btn--primary"><Plus className="h-4 w-4" /> إنشاء ملاحظة</button>
          <button type="button" onClick={load} className="aseel-iconbtn" aria-label="تحديث ملاحظات التطوير" title="تحديث"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
        </div>
      </header>
      {error && <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <table className="w-full min-w-[1050px] border-collapse text-sm">
          <thead className="bg-[var(--color-surface-2)] aseel-text-soft"><tr>
            <th className="w-12 border-l border-[var(--color-border)] px-2 py-2 text-center">#</th>
            <th className="w-24 border-l border-[var(--color-border)] px-2 py-2 text-center">إجراءات</th>
            <th className="border-l border-[var(--color-border)] px-2 py-2 text-right">العنوان</th>
            <th className="border-l border-[var(--color-border)] px-2 py-2 text-right">الوصف</th>
            <th className="border-l border-[var(--color-border)] px-2 py-2 text-right">الحالة</th>
            <th className="border-l border-[var(--color-border)] px-2 py-2 text-right">الأولوية</th>
            <th className="border-l border-[var(--color-border)] px-2 py-2 text-right">المسؤول</th>
            <th className="border-l border-[var(--color-border)] px-2 py-2 text-right">الموعد</th>
          </tr></thead>
          <tbody>
            {notes.map((note, index) => (
              <tr key={note.id} className="border-t border-[var(--color-border)]">
                <td className="border-l border-[var(--color-border)] px-2 text-center aseel-text-soft">{index + 1}</td>
                <td className="border-l border-[var(--color-border)] px-2 py-1"><div className="flex justify-center gap-1"><button type="button" className="aseel-iconbtn" onClick={() => void save(note)} disabled={savingId === note.id} aria-label={`حفظ ${note.title}`} title="حفظ"><Save className="h-4 w-4" /></button><button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => void remove(note)} disabled={savingId === note.id} aria-label={`حذف ${note.title}`} title="حذف"><Trash2 className="h-4 w-4" /></button></div></td>
                <td className="border-l border-[var(--color-border)]"><input aria-label={`عنوان الملاحظة ${index + 1}`} className={cellClass} value={note.title} onChange={(e) => patchLocal(note.id, "title", e.target.value)} /></td>
                <td className="border-l border-[var(--color-border)]"><textarea aria-label={`وصف الملاحظة ${index + 1}`} rows={3} className={`${cellClass} min-h-20 min-w-64 resize-none overflow-hidden [field-sizing:content]`} value={note.description} onChange={(e) => patchLocal(note.id, "description", e.target.value)} /></td>
                <td className="border-l border-[var(--color-border)]"><select aria-label={`حالة الملاحظة ${index + 1}`} className={cellClass} value={note.status} onChange={(e) => patchLocal(note.id, "status", e.target.value as DevelopmentNote["status"])}><option value="todo">قيد الانتظار</option><option value="in_progress">قيد التنفيذ</option><option value="done">مكتملة</option></select></td>
                <td className="border-l border-[var(--color-border)]"><select aria-label={`أولوية الملاحظة ${index + 1}`} className={cellClass} value={note.priority} onChange={(e) => patchLocal(note.id, "priority", e.target.value as DevelopmentNote["priority"])}><option value="low">منخفضة</option><option value="medium">متوسطة</option><option value="high">عالية</option></select></td>
                <td className="border-l border-[var(--color-border)]"><input aria-label={`مسؤول الملاحظة ${index + 1}`} className={cellClass} value={note.assignee} onChange={(e) => patchLocal(note.id, "assignee", e.target.value)} /></td>
                <td className="border-l border-[var(--color-border)]"><AseelDateInput aria-label={`موعد الملاحظة ${index + 1}`} className={cellClass} value={note.due_date || ""} onChange={(value) => patchLocal(note.id, "due_date", value || null)} /></td>
              </tr>
            ))}
            <tr className="border-t-2 border-[var(--color-primary)] bg-[var(--color-surface-2)]">
              <td className="border-l border-[var(--color-border)] px-2 text-center"><Plus className="mx-auto h-4 w-4" /></td>
              <td className="border-l border-[var(--color-border)] px-2 py-1 text-center"><button type="button" onClick={() => void add()} disabled={savingId === "new"} className="aseel-btn aseel-btn--primary"><Plus className="h-4 w-4" /> إضافة</button></td>
              <td className="border-l border-[var(--color-border)]"><input ref={draftTitleRef} aria-label="عنوان ملاحظة جديدة" className={cellClass} placeholder="ملاحظة تطوير جديدة" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") void add(); }} /></td>
              <td className="border-l border-[var(--color-border)]"><textarea aria-label="وصف ملاحظة جديدة" rows={3} className={`${cellClass} min-h-20 min-w-64 resize-none overflow-hidden [field-sizing:content]`} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></td>
              <td className="border-l border-[var(--color-border)]"><select aria-label="حالة ملاحظة جديدة" className={cellClass} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as DevelopmentNoteWrite["status"] })}><option value="todo">قيد الانتظار</option><option value="in_progress">قيد التنفيذ</option><option value="done">مكتملة</option></select></td>
              <td className="border-l border-[var(--color-border)]"><select aria-label="أولوية ملاحظة جديدة" className={cellClass} value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: e.target.value as DevelopmentNoteWrite["priority"] })}><option value="low">منخفضة</option><option value="medium">متوسطة</option><option value="high">عالية</option></select></td>
              <td className="border-l border-[var(--color-border)]"><input aria-label="مسؤول ملاحظة جديدة" className={cellClass} value={draft.assignee} onChange={(e) => setDraft({ ...draft, assignee: e.target.value })} /></td>
              <td className="border-l border-[var(--color-border)]"><AseelDateInput aria-label="موعد ملاحظة جديدة" className={cellClass} value={draft.due_date || ""} onChange={(value) => setDraft({ ...draft, due_date: value || null })} /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs aseel-text-soft">استخدم Tab للتنقّل بين الخلايا، ثم زر الحفظ في نهاية الصف.</p>
    </main>
  );
};
