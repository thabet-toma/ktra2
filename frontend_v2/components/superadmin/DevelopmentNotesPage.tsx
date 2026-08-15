import React, { useEffect, useMemo, useState } from "react";
import {
  ChevronDown, ImagePlus, MessageSquare, Pencil, Plus, RefreshCw, Save, Send,
  Trash2, X,
} from "lucide-react";

import {
  addDevelopmentNoteComment, createDevelopmentNote, deleteDevelopmentNote,
  deleteDevelopmentNoteComment, listDevelopmentNotes, updateDevelopmentNote,
  type DevelopmentNote, type DevelopmentNoteComment, type DevelopmentNoteImage,
  type DevelopmentNoteWrite,
} from "../../services/platformAdminApi";
import { cloudinaryService } from "../../services/cloudinaryService";
import {
  NOTE_PRIORITY_LABELS, NOTE_STATUS_LABELS, isNoteDone, sortDevelopmentNotes,
} from "../../utils/developmentNotes";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { useConfirm } from "../../contexts/ConfirmContext";
import { AseelDateInput } from "../aseel/AseelDateInput";
import { AseelDenseTable } from "../aseel";
import type { DenseColumn } from "../aseel";

/** ملاحظة جديدة: التاريخ يُملأ بتاريخ اليوم تلقائياً — يُعدَّل إن أراد المستخدم. */
const emptyNote = (): DevelopmentNoteWrite => ({
  title: "",
  description: "",
  status: "todo",
  priority: "medium",
  images: [],
  due_date: todayIso(),
});

const STATUS_OPTIONS = Object.entries(NOTE_STATUS_LABELS) as
  [DevelopmentNote["status"], string][];
const PRIORITY_OPTIONS = Object.entries(NOTE_PRIORITY_LABELS) as
  [DevelopmentNote["priority"], string][];

/**
 * ألوان الشارات بـ`color-mix` على متغيّرات السمة — تنقلب مع الوضع الداكن بلا
 * كتلة ثانية، وتبقى مقروءة على السطحين. (قاعدة `tbody td` غير المُطبَّقة في
 * `styles/index.css` تغلب أصناف Tailwind على الخلية نفسها، لا على أبنائها —
 * فكل تنسيق هنا يجلس داخل عنصر ابن.)
 */
const TONES = {
  neutral: "var(--color-text-muted)",
  info: "var(--color-primary)",
  success: "var(--color-success)",
  danger: "#dc2626",
} as const;

type Tone = keyof typeof TONES;

const STATUS_TONE: Record<DevelopmentNote["status"], Tone> = {
  todo: "neutral", in_progress: "info", done: "success",
};
const PRIORITY_TONE: Record<DevelopmentNote["priority"], Tone> = {
  low: "neutral", medium: "info", high: "danger",
};

const Badge: React.FC<{ tone: Tone; children: React.ReactNode }> = ({ tone, children }) => (
  <span
    className="inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold"
    style={{
      color: TONES[tone],
      backgroundColor: `color-mix(in srgb, ${TONES[tone]} 14%, transparent)`,
      border: `1px solid color-mix(in srgb, ${TONES[tone]} 32%, transparent)`,
    }}
  >
    {children}
  </span>
);

const fieldLabel = "mb-1 block text-xs font-semibold text-[var(--color-text-muted)]";
const fieldInput = "w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)] focus:ring-1 focus:ring-[var(--color-primary)]";

/** الملاحظة المفتوحة في النافذة: `"new"` = إضافة، أو ملاحظة قائمة للتعديل. */
type EditorTarget = { mode: "new" } | { mode: "edit"; note: DevelopmentNote };

/**
 * الحقلان المتداخلان يصلان `null` من عقود قديمة أو من ردّ لم يُسلسِلهما، وكل
 * الشاشة تقرؤهما مباشرةً — فالتطبيع مرّة واحدة عند الدخول أأمن من فحصٍ في كل
 * موضع عرض.
 */
const hydrate = (note: DevelopmentNote): DevelopmentNote => ({
  ...note, images: note.images ?? [], comments: note.comments ?? [],
});

export const DevelopmentNotesPage: React.FC = () => {
  const confirm = useConfirm();
  const [notes, setNotes] = useState<DevelopmentNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [form, setForm] = useState<DevelopmentNoteWrite>(emptyNote);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<number | null>(null);
  const [doneOpen, setDoneOpen] = useState(true);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentBusy, setCommentBusy] = useState(false);
  // خطأ الردّ يُعرض داخل النافذة لا في شريط الصفحة خلفها — الشريط لا يُرى وقتها.
  const [commentError, setCommentError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    listDevelopmentNotes()
      .then((rows) => setNotes(sortDevelopmentNotes(rows.map(hydrate))))
      .catch((cause) => setError(cause instanceof Error ? cause.message : "تعذّر تحميل الملاحظات"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  /** قسمان مستقلّان: الترتيب داخل كلٍّ منهما هو ترتيب الخادم نفسه بلا فرزٍ ثانٍ. */
  const openNotes = useMemo(() => notes.filter((note) => !isNoteDone(note)), [notes]);
  const doneNotes = useMemo(() => notes.filter(isNoteDone), [notes]);

  const openNew = () => {
    setForm(emptyNote());
    setPreview(null);
    setCommentDraft("");
    setCommentError(null);
    setEditor({ mode: "new" });
  };

  const openEdit = (note: DevelopmentNote) => {
    setForm({
      title: note.title, description: note.description, status: note.status,
      priority: note.priority, images: note.images ?? [], due_date: note.due_date,
    });
    setPreview(null);
    setCommentDraft("");
    setCommentError(null);
    setEditor({ mode: "edit", note: hydrate(note) });
  };

  /** تغيير الحالة من الجدول يُحفظ فوراً — المكتملة تنزل لآخر القائمة حالاً. */
  const changeStatus = async (note: DevelopmentNote, status: DevelopmentNote["status"]) => {
    setNotes((current) => sortDevelopmentNotes(
      current.map((row) => row.id === note.id ? { ...row, status } : row),
    ));
    setBusy(true);
    setError(null);
    try {
      const saved = await updateDevelopmentNote(note.id, { status });
      setNotes((current) => sortDevelopmentNotes(current.map(
        (row) => row.id === saved.id ? hydrate(saved) : row,
      )));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل حفظ حالة الملاحظة");
      load();
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!form.title.trim()) {
      setError("اكتب عنوان ملاحظة التطوير أولاً.");
      return;
    }
    setBusy(true);
    setError(null);
    const payload: DevelopmentNoteWrite = { ...form, title: form.title.trim() };
    try {
      if (editor?.mode === "edit") {
        const saved = await updateDevelopmentNote(editor.note.id, payload);
        setNotes((current) => sortDevelopmentNotes(current.map(
          (row) => row.id === saved.id ? hydrate(saved) : row,
        )));
      } else {
        const created = await createDevelopmentNote(payload);
        // مكانها يتحدّد بالأولوية ثم التاريخ — الفرز نفسه الذي يطبّقه الخادم.
        setNotes((current) => sortDevelopmentNotes([...current, hydrate(created)]));
      }
      setEditor(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل حفظ الملاحظة");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (note: DevelopmentNote) => {
    const ok = await confirm({
      title: "حذف ملاحظة تطوير",
      message: `سيُحذف «${note.title}» نهائياً مع صوره التوضيحية.`,
      confirmText: "حذف",
    });
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await deleteDevelopmentNote(note.id);
      setNotes((current) => current.filter((row) => row.id !== note.id));
      setEditor(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل حذف الملاحظة");
    } finally {
      setBusy(false);
    }
  };

  /**
   * الردود تعيش في نسختين: صفّ الجدول والنافذة المفتوحة فوقه. تحديثهما معاً من
   * ردّ الخادم وحده يبقيهما متطابقتين بلا إعادة تحميل القائمة كلها.
   */
  const applyComments = (
    noteId: number,
    update: (comments: DevelopmentNoteComment[]) => DevelopmentNoteComment[],
  ) => {
    setNotes((current) => current.map(
      (row) => row.id === noteId ? { ...row, comments: update(row.comments ?? []) } : row,
    ));
    setEditor((current) => current?.mode === "edit" && current.note.id === noteId
      ? { mode: "edit", note: { ...current.note, comments: update(current.note.comments ?? []) } }
      : current);
  };

  /** الإرسال مستقلّ عن زر حفظ الملاحظة — الردّ يُثبَّت فور كتابته. */
  const sendComment = async (note: DevelopmentNote) => {
    const body = commentDraft.trim();
    if (!body) {
      setCommentError("اكتب نصّ الردّ أولاً.");
      return;
    }
    setCommentBusy(true);
    setCommentError(null);
    try {
      const created = await addDevelopmentNoteComment(note.id, body);
      applyComments(note.id, (comments) => [...comments, created]);
      setCommentDraft("");
    } catch (cause) {
      setCommentError(cause instanceof Error ? cause.message : "فشل إرسال الردّ");
    } finally {
      setCommentBusy(false);
    }
  };

  const removeComment = async (note: DevelopmentNote, comment: DevelopmentNoteComment) => {
    const ok = await confirm({
      title: "حذف ردّ",
      message: "سيُحذف هذا الردّ نهائياً من الملاحظة.",
      confirmText: "حذف",
    });
    if (!ok) return;
    setCommentBusy(true);
    setCommentError(null);
    try {
      await deleteDevelopmentNoteComment(note.id, comment.id);
      applyComments(note.id, (comments) => comments.filter((row) => row.id !== comment.id));
    } catch (cause) {
      setCommentError(cause instanceof Error ? cause.message : "فشل حذف الردّ");
    } finally {
      setCommentBusy(false);
    }
  };

  const addImages = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      // `platform`: صورة ملاحظة تطوير أصلٌ للمنصة لا للشركة النشطة في ترويسة
      // السوبر أدمن — بلا هذا النطاق تُحمَّل بايتاتها على شركةٍ لا شأن لها بها.
      const urls = await cloudinaryService.uploadMultipleFiles(Array.from(files), "platform");
      setForm((current) => ({
        ...current, images: [...current.images, ...urls.map((url) => ({ url, caption: "" }))],
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل رفع الصورة");
    } finally {
      setUploading(false);
    }
  };

  const patchImage = (index: number, patch: Partial<DevelopmentNoteImage>) => {
    setForm((current) => ({
      ...current,
      images: current.images.map((image, at) => at === index ? { ...image, ...patch } : image),
    }));
  };

  const dropImage = (index: number) => {
    setForm((current) => ({
      ...current, images: current.images.filter((_, at) => at !== index),
    }));
    setPreview(null);
  };

  /** خلية الحالة — تبقى قابلة للتغيير في القسمين معاً فالإنجاز قرار قابل للتراجع. */
  const statusSelect = (note: DevelopmentNote) => (
    <select
      aria-label={`حالة الملاحظة ${note.title}`}
      className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-1.5 py-1 text-xs font-semibold text-[var(--color-text)]"
      style={{ color: TONES[STATUS_TONE[note.status]] }}
      disabled={busy}
      value={note.status}
      onChange={(event) => void changeStatus(
        note, event.target.value as DevelopmentNote["status"],
      )}
    >
      {STATUS_OPTIONS.map(([value, label]) => (
        <option key={value} value={value}>{label}</option>
      ))}
    </select>
  );

  const buildColumns = (section: "open" | "done"): DenseColumn<DevelopmentNote>[] => [
    {
      key: "seq", header: "#", width: "62px", align: "center",
      render: (note, index) => (
        // شريط الأولوية على حافة الصف: داخل عنصر ابن لأن قاعدة `tbody td` غير
        // المُطبَّقة في `styles/index.css` تغلب أصناف Tailwind على الخلية نفسها.
        <span className="flex items-center gap-2">
          <span
            aria-hidden className="inline-block h-6 w-[3px] shrink-0 rounded-full"
            style={{ backgroundColor: TONES[PRIORITY_TONE[note.priority]] }}
          />
          <span className="text-xs text-[var(--color-text-muted)]">
            {formatNumber(index + 1)}
          </span>
        </span>
      ),
    },
    {
      key: "title", header: "الملاحظة",
      render: (note) => (
        <div className="py-0.5">
          <div className="flex items-center gap-2">
            <span className={`font-semibold ${isNoteDone(note) ? "text-[var(--color-text-muted)] line-through" : "text-[var(--color-text)]"}`}>
              {note.title}
            </span>
            {note.comments.length > 0 && (
              <span
                className="inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-semibold"
                title={`${formatNumber(note.comments.length)} ردّ على الملاحظة`}
                style={{
                  color: TONES.info,
                  backgroundColor: `color-mix(in srgb, ${TONES.info} 12%, transparent)`,
                }}
              >
                <MessageSquare className="h-3 w-3" />
                {formatNumber(note.comments.length)}
              </span>
            )}
          </div>
          {note.description.trim() && (
            // سطران يكفيان للتمييز، والنص كاملاً في نافذة التعديل — فلا يبتلع
            // وصفٌ واحد طويل الجدولَ كله كما كان في الورقة السابقة.
            <p className="mt-1 line-clamp-2 whitespace-pre-line text-xs leading-5 text-[var(--color-text-muted)]">
              {note.description}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "status", header: "الحالة", width: section === "done" ? "152px" : "136px",
      align: "center",
      render: (note) => section === "open" ? statusSelect(note) : (
        <div className="flex flex-col items-center gap-1 py-0.5">
          <Badge tone="success">تم تنفيذها ✓</Badge>
          <span className="whitespace-nowrap text-[11px] text-[var(--color-text-muted)]">
            {/* المكتملة قبل إضافة `completed_at` تصل بلا ختم — «غير مسجَّل»
                جوابٌ صادق، ولا يجوز تلفيقه من `updated_at`. */}
            {note.completed_at ? formatDateLocalized(note.completed_at) : "تاريخ غير مسجَّل"}
          </span>
          {statusSelect(note)}
        </div>
      ),
    },
    {
      key: "priority", header: "الأولوية", width: "104px", align: "center",
      render: (note) => (
        <Badge tone={PRIORITY_TONE[note.priority]}>{NOTE_PRIORITY_LABELS[note.priority]}</Badge>
      ),
    },
    {
      key: "due_date", header: "الموعد", width: "116px", align: "center",
      render: (note) => (
        <span className="whitespace-nowrap text-xs text-[var(--color-text-muted)]">
          {note.due_date ? formatDateLocalized(note.due_date) : "—"}
        </span>
      ),
    },
    {
      key: "images", header: "صور توضيحية", width: "112px", align: "center",
      render: (note) => {
        const images = note.images ?? [];
        if (images.length === 0) {
          return <span className="text-xs text-[var(--color-text-muted)]">—</span>;
        }
        return (
          <button
            type="button"
            className="mx-auto flex items-center gap-1.5"
            aria-label={`صور الملاحظة ${note.title}`}
            onClick={() => openEdit(note)}
          >
            <img
              src={images[0].url} alt={images[0].caption || note.title}
              className="h-8 w-8 rounded border border-[var(--color-border)] object-cover"
            />
            <span className="text-xs text-[var(--color-text-muted)]">{images.length}</span>
          </button>
        );
      },
    },
    {
      key: "created", header: "أُضيفت", width: "116px", align: "center",
      render: (note) => (
        <span className="whitespace-nowrap text-xs text-[var(--color-text-muted)]">
          {formatDateLocalized(note.created_at)}
        </span>
      ),
    },
    {
      key: "actions", header: "إجراءات", width: "96px", align: "center",
      render: (note) => (
        <div className="flex items-center justify-center gap-1">
          <button
            type="button" className="aseel-iconbtn" disabled={busy}
            aria-label={`تعديل ${note.title}`} title="تعديل"
            onClick={(event) => { event.stopPropagation(); openEdit(note); }}
          ><Pencil className="h-4 w-4" /></button>
          <button
            type="button" className="aseel-iconbtn aseel-iconbtn--danger" disabled={busy}
            aria-label={`حذف ${note.title}`} title="حذف"
            onClick={(event) => { event.stopPropagation(); void remove(note); }}
          ><Trash2 className="h-4 w-4" /></button>
        </div>
      ),
    },
  ];

  const previewImage = preview === null ? undefined : form.images[preview];

  return (
    <main className="p-4 md:p-6" dir="rtl">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text)]">ملاحظات التطوير</h1>
          <p className="text-sm aseel-text-soft">
            الأهمّ أولاً ثم الأقدم داخل الأولوية الواحدة، والمكتملة في قسمٍ مستقلّ.
            الإضافة والتعديل من نافذة واحدة، وتغيير الحالة من الجدول يُحفظ فوراً.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[var(--color-surface-2)] px-3 py-1 text-xs aseel-text-soft">
            {formatNumber(notes.length)} ملاحظة · {formatNumber(openNotes.length)} مفتوحة
            · {formatNumber(doneNotes.length)} مكتملة
          </span>
          <button type="button" onClick={openNew} className="aseel-btn aseel-btn-primary">
            <Plus className="h-4 w-4" /> إضافة ملاحظة
          </button>
          <button
            type="button" onClick={load} className="aseel-iconbtn"
            aria-label="تحديث ملاحظات التطوير" title="تحديث"
          ><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
        </div>
      </header>

      {error && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </div>
      )}

      <section>
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-sm font-bold text-[var(--color-text)]">
            قيد العمل ({formatNumber(openNotes.length)})
          </h2>
          <span className="h-px flex-1 bg-[var(--color-border)]" />
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2">
          <AseelDenseTable<DevelopmentNote>
            columns={buildColumns("open")}
            rows={openNotes}
            getRowKey={(note) => note.id}
            onRowDoubleClick={openEdit}
            loading={loading}
            emptyHint="لا توجد ملاحظات مفتوحة — ابدأ بزر «إضافة ملاحظة»."
          />
        </div>
      </section>

      <div className="my-5 border-t-2 border-dashed border-[var(--color-border)]" />

      <section>
        <button
          type="button" aria-expanded={doneOpen}
          className="mb-2 flex w-full items-center gap-2 text-right"
          onClick={() => setDoneOpen((current) => !current)}
          title={doneOpen ? "طيّ المكتملة" : "عرض المكتملة"}
        >
          {/* في RTL يشير الشيفرون المطوي لليسار — جهة الانفتاح. */}
          <ChevronDown className={`h-4 w-4 text-[var(--color-text-muted)] transition-transform ${doneOpen ? "" : "rotate-90"}`} />
          <h2 className="text-sm font-bold text-[var(--color-text)]">
            تم تنفيذها ({formatNumber(doneNotes.length)})
          </h2>
          <span className="h-px flex-1 bg-[var(--color-border)]" />
        </button>
        {doneOpen && (
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2">
            <AseelDenseTable<DevelopmentNote>
              columns={buildColumns("done")}
              rows={doneNotes}
              getRowKey={(note) => note.id}
              onRowDoubleClick={openEdit}
              loading={loading}
              emptyHint="لم تُنجَز أي ملاحظة بعد."
            />
          </div>
        )}
      </section>

      <p className="mt-2 text-xs aseel-text-soft">
        نقرتان على الصف تفتحان الملاحظة للتعديل والردّ عليها.
      </p>

      {editor !== null && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          dir="rtl"
          onMouseDown={(event) => { if (event.target === event.currentTarget) setEditor(null); }}
        >
          <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <h2 className="font-bold text-[var(--color-text)]">
                {editor.mode === "edit" ? "تعديل ملاحظة تطوير" : "ملاحظة تطوير جديدة"}
              </h2>
              <button
                type="button" className="aseel-iconbtn" aria-label="إغلاق النافذة" title="إغلاق"
                onClick={() => setEditor(null)}
              ><X className="h-4 w-4" /></button>
            </div>

            <div className="space-y-4 p-4">
              <div>
                <label className={fieldLabel} htmlFor="note-title">العنوان *</label>
                <input
                  id="note-title" className={fieldInput} autoFocus
                  placeholder="عنوان مختصر يوضّح المطلوب"
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </div>

              <div>
                <label className={fieldLabel} htmlFor="note-description">الوصف</label>
                <textarea
                  id="note-description" className={`${fieldInput} min-h-40 leading-6`} rows={7}
                  placeholder="اشرح الملاحظة بالتفصيل: أين تظهر، وما المتوقّع، وما يحدث فعلاً."
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className={fieldLabel} htmlFor="note-status">الحالة</label>
                  <select
                    id="note-status" className={fieldInput} value={form.status}
                    onChange={(event) => setForm({
                      ...form, status: event.target.value as DevelopmentNoteWrite["status"],
                    })}
                  >
                    {STATUS_OPTIONS.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={fieldLabel} htmlFor="note-priority">الأولوية</label>
                  <select
                    id="note-priority" className={fieldInput} value={form.priority}
                    onChange={(event) => setForm({
                      ...form, priority: event.target.value as DevelopmentNoteWrite["priority"],
                    })}
                  >
                    {PRIORITY_OPTIONS.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <span className={fieldLabel}>الموعد</span>
                  <AseelDateInput
                    aria-label="موعد الملاحظة" className={fieldInput}
                    value={form.due_date || ""}
                    onChange={(value) => setForm({ ...form, due_date: value || null })}
                  />
                </div>
              </div>

              <div>
                <span className={fieldLabel}>صور توضيحية</span>
                <div className="flex flex-wrap items-start gap-2">
                  {form.images.map((image, index) => (
                    <button
                      key={`${image.url}-${index}`} type="button"
                      onClick={() => setPreview(index)}
                      title={image.caption || "معاينة الصورة"}
                      aria-label={`معاينة صورة ${index + 1}`}
                      className="h-20 w-20 overflow-hidden rounded-lg border border-[var(--color-border)] hover:ring-2 hover:ring-[var(--color-primary)]"
                    >
                      <img
                        src={image.url} alt={image.caption || "صورة توضيحية"}
                        className="h-full w-full object-cover"
                      />
                    </button>
                  ))}
                  <label
                    className="flex h-20 w-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
                    title="إدراج صورة توضيحية"
                  >
                    {uploading
                      ? <RefreshCw className="h-5 w-5 animate-spin" />
                      : <ImagePlus className="h-5 w-5" />}
                    <span className="text-[11px]">إدراج صورة</span>
                    <input
                      type="file" accept="image/*" multiple className="sr-only"
                      aria-label="إدراج صورة توضيحية"
                      onChange={(event) => {
                        void addImages(event.target.files);
                        event.target.value = "";
                      }}
                    />
                  </label>
                </div>
              </div>

              {editor.mode === "edit" ? (
                <div className="border-t border-[var(--color-border)] pt-4">
                  <span className={fieldLabel}>
                    الردود ({formatNumber(editor.note.comments.length)})
                  </span>
                  <div className="space-y-2">
                    {editor.note.comments.length === 0 && (
                      <p className="text-xs aseel-text-soft">
                        لا ردود بعد — اكتب أول ردّ على هذه الملاحظة.
                      </p>
                    )}
                    {editor.note.comments.map((comment) => {
                      // ردّ من غير صاحب الملاحظة يُلوَّن أحمر — نقاشٌ وارد لا صدى
                      // لصاحبها، فيُميَّز بلمحة واحدة.
                      const tone: Tone =
                        comment.created_by !== editor.note.created_by ? "danger" : "neutral";
                      return (
                        <div
                          key={comment.id}
                          className="rounded-lg border px-3 py-2"
                          style={{
                            borderColor: `color-mix(in srgb, ${TONES[tone]} 32%, transparent)`,
                            backgroundColor: `color-mix(in srgb, ${TONES[tone]} 8%, transparent)`,
                          }}
                        >
                          <div className="mb-1 flex items-center justify-between gap-2">
                            <span
                              className="text-xs font-semibold"
                              style={{ color: TONES[tone] }}
                            >
                              {comment.created_by_name || "مستخدم محذوف"}
                              <span className="mx-2 font-normal text-[var(--color-text-muted)]">
                                {formatDateLocalized(comment.created_at)}
                              </span>
                            </span>
                            <button
                              type="button" className="aseel-iconbtn aseel-iconbtn--danger"
                              disabled={commentBusy}
                              aria-label={`حذف ردّ ${comment.created_by_name}`} title="حذف الردّ"
                              onClick={() => void removeComment(editor.note, comment)}
                            ><Trash2 className="h-3.5 w-3.5" /></button>
                          </div>
                          <p className="whitespace-pre-line text-sm leading-6 text-[var(--color-text)]">
                            {comment.body}
                          </p>
                        </div>
                      );
                    })}
                  </div>

                  {commentError && (
                    <div className="mt-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">
                      {commentError}
                    </div>
                  )}

                  <div className="mt-2 flex items-end gap-2">
                    <textarea
                      aria-label="نص الردّ" rows={2}
                      className={`${fieldInput} min-h-[52px] leading-6`}
                      placeholder="اكتب ردّك… (Ctrl+Enter للإرسال)"
                      value={commentDraft}
                      disabled={commentBusy}
                      onChange={(event) => setCommentDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                          event.preventDefault();
                          void sendComment(editor.note);
                        }
                      }}
                    />
                    <button
                      type="button" className="aseel-btn aseel-btn-primary whitespace-nowrap"
                      disabled={commentBusy}
                      onClick={() => void sendComment(editor.note)}
                    >
                      <Send className="h-4 w-4" />
                      {commentBusy ? "جارٍ الإرسال…" : "إرسال"}
                    </button>
                  </div>
                  <p className="mt-1 text-[11px] aseel-text-soft">
                    الردّ يُحفظ فور إرساله — مستقلّاً عن زر حفظ الملاحظة.
                  </p>
                </div>
              ) : (
                <p className="border-t border-[var(--color-border)] pt-4 text-xs aseel-text-soft">
                  الردود تُفتح بعد حفظ الملاحظة.
                </p>
              )}
            </div>

            <div className="sticky bottom-0 flex items-center justify-between gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              {editor.mode === "edit" ? (
                <button
                  type="button" className="aseel-btn text-red-600" disabled={busy}
                  onClick={() => void remove(editor.note)}
                ><Trash2 className="h-4 w-4" /> حذف</button>
              ) : <span />}
              <div className="flex items-center gap-2">
                <button type="button" className="aseel-btn" onClick={() => setEditor(null)}>إلغاء</button>
                <button
                  type="button" className="aseel-btn aseel-btn-primary" disabled={busy}
                  onClick={() => void submit()}
                >
                  <Save className="h-4 w-4" />
                  {busy ? "جاري الحفظ…" : editor.mode === "edit" ? "حفظ التعديلات" : "إضافة الملاحظة"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {previewImage && preview !== null && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4"
          role="dialog" aria-modal="true" aria-label="معاينة صورة الملاحظة"
          onClick={() => setPreview(null)}
        >
          <div
            className="flex max-h-full w-full max-w-3xl flex-col gap-3 overflow-auto rounded-lg bg-[var(--color-surface)] p-4"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm aseel-text-soft">
                صورة {preview + 1} من {form.images.length}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button" className="aseel-iconbtn aseel-iconbtn--danger"
                  title="حذف الصورة" aria-label="حذف الصورة"
                  onClick={() => dropImage(preview)}
                ><Trash2 className="h-4 w-4" /></button>
                <button
                  type="button" className="aseel-iconbtn" title="إغلاق"
                  aria-label="إغلاق المعاينة" onClick={() => setPreview(null)}
                ><X className="h-4 w-4" /></button>
              </div>
            </div>
            <img
              src={previewImage.url} alt={previewImage.caption || "صورة توضيحية"}
              className="max-h-[65vh] w-full rounded object-contain"
            />
            <input
              aria-label="تعليق الصورة" placeholder="تعليق توضيحي للصورة (اختياري)"
              className={fieldInput}
              value={previewImage.caption}
              onChange={(event) => patchImage(preview, { caption: event.target.value })}
            />
            <p className="text-xs aseel-text-soft">
              الصور والتعليقات تُحفظ مع الملاحظة عند الضغط على زر الحفظ.
            </p>
          </div>
        </div>
      )}
    </main>
  );
};
