import React, { useEffect, useMemo, useState } from "react";
import { ImagePlus, Pencil, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";

import {
  createDevelopmentNote, deleteDevelopmentNote, listDevelopmentNotes,
  updateDevelopmentNote, type DevelopmentNote, type DevelopmentNoteImage,
  type DevelopmentNoteWrite,
} from "../../services/platformAdminApi";
import { cloudinaryService } from "../../services/cloudinaryService";
import {
  NOTE_PRIORITY_LABELS, NOTE_STATUS_LABELS, isNoteDone, sortDevelopmentNotes,
} from "../../utils/developmentNotes";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
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

  const load = () => {
    setLoading(true);
    setError(null);
    listDevelopmentNotes()
      .then((rows) => setNotes(sortDevelopmentNotes(rows.map(
        (note) => ({ ...note, images: note.images ?? [] }),
      ))))
      .catch((cause) => setError(cause instanceof Error ? cause.message : "تعذّر تحميل الملاحظات"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const counts = useMemo(() => ({
    total: notes.length,
    done: notes.filter(isNoteDone).length,
    open: notes.filter((note) => !isNoteDone(note)).length,
  }), [notes]);

  const openNew = () => {
    setForm(emptyNote());
    setPreview(null);
    setEditor({ mode: "new" });
  };

  const openEdit = (note: DevelopmentNote) => {
    setForm({
      title: note.title, description: note.description, status: note.status,
      priority: note.priority, images: note.images ?? [], due_date: note.due_date,
    });
    setPreview(null);
    setEditor({ mode: "edit", note });
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
        (row) => row.id === saved.id ? { ...saved, images: saved.images ?? [] } : row,
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
          (row) => row.id === saved.id ? { ...saved, images: saved.images ?? [] } : row,
        )));
      } else {
        const created = await createDevelopmentNote(payload);
        // الأحدث يذهب لآخر القائمة — الفرز نفسه الذي يطبّقه الخادم.
        setNotes((current) => sortDevelopmentNotes(
          [...current, { ...created, images: created.images ?? [] }],
        ));
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

  const addImages = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const urls = await cloudinaryService.uploadMultipleFiles(Array.from(files));
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

  const columns: DenseColumn<DevelopmentNote>[] = [
    {
      key: "seq", header: "#", width: "52px", align: "center",
      render: (_note, index) => (
        <span className="text-xs text-[var(--color-text-muted)]">{index + 1}</span>
      ),
    },
    {
      key: "title", header: "الملاحظة",
      render: (note) => (
        <div className="py-0.5">
          <div className={`font-semibold ${isNoteDone(note) ? "text-[var(--color-text-muted)] line-through" : "text-[var(--color-text)]"}`}>
            {note.title}
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
      key: "status", header: "الحالة", width: "136px", align: "center",
      render: (note) => (
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
            مرتَّبة من الأقدم إلى الأحدث، والمكتملة تنزل لآخر القائمة.
            الإضافة والتعديل من نافذة واحدة، وتغيير الحالة من الجدول يُحفظ فوراً.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[var(--color-surface-2)] px-3 py-1 text-xs aseel-text-soft">
            {counts.total} ملاحظة · {counts.open} مفتوحة · {counts.done} مكتملة
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

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2">
        <AseelDenseTable<DevelopmentNote>
          columns={columns}
          rows={notes}
          getRowKey={(note) => note.id}
          onRowDoubleClick={openEdit}
          loading={loading}
          emptyHint="لا توجد ملاحظات تطوير بعد — ابدأ بزر «إضافة ملاحظة»."
        />
      </div>
      <p className="mt-2 text-xs aseel-text-soft">
        نقرتان على الصف تفتحان الملاحظة للتعديل.
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
