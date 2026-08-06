import React, { useEffect, useMemo, useRef, useState } from "react";
import { ImagePlus, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";

import {
  createDevelopmentNote, deleteDevelopmentNote, listDevelopmentNotes,
  updateDevelopmentNote, type DevelopmentNote, type DevelopmentNoteImage,
  type DevelopmentNoteWrite,
} from "../../services/platformAdminApi";
import { cloudinaryService } from "../../services/cloudinaryService";
import {
  autoFitColumnWidth, columnWidthsKey, nextColumnWidth, nextRowHeight,
  readSizes, rowHeightsKey, writeSizes, type SizeMap,
} from "../../utils/columnWidths";
import {
  COLLAPSED_DESCRIPTION_LINES, isNoteDone, sortDevelopmentNotes,
} from "../../utils/developmentNotes";
import { AseelDateInput } from "../aseel/AseelDateInput";


const emptyNote = (position: number): DevelopmentNoteWrite => ({
  title: "",
  description: "",
  status: "todo",
  priority: "medium",
  images: [],
  due_date: null,
  position,
});

const cellClass = "w-full border-0 bg-transparent px-2 py-2 text-sm text-[var(--color-text)] outline-none focus:bg-[var(--color-surface-2)] focus:ring-1 focus:ring-inset focus:ring-[var(--color-primary)]";

/**
 * ⚠ `styles/index.css` فيه قاعدة **خارج الطبقات** (`tbody td`) تفرض حشوةً
 * ومحاذاةً وسطى، وهي تتقدّم على أدوات Tailwind مهما كتبنا في className.
 * لذلك خلايا هذه الورقة تُضبط بأنماط سطرية: الحشوة داخل الحقول لا في الخلية،
 * والمحاذاة للأعلى. و`height: 1px` حيلة معروفة تجعل `height:100%` للطفل
 * ينحلّ إلى ارتفاع الصف الفعلي فيملأ الوصف الخلية بلا فجوة.
 */
const CELL_STYLE: React.CSSProperties = { padding: 0, verticalAlign: "top" };
const FILL_CELL_STYLE: React.CSSProperties = { ...CELL_STYLE, height: "1px" };
/** تلوين المكتملة بأسلوب سطري — قاعدة `tbody tr:hover` الخارجية تغلب الأصناف. */
const DONE_TINT = "color-mix(in srgb, var(--color-success) 12%, transparent)";

type NoteColumn = {
  key: string; header: string; fixed?: number; center?: boolean;
  /** أرضية العرض التلقائي — عمود فقرات لا يُخنق لأن أسطره قصيرة. */
  floor?: number;
};

/** أعمدة الورقة بترتيبها — المفاتيح نفسها تُستعمل في حفظ العروض. */
const COLUMNS: NoteColumn[] = [
  { key: "index", header: "#", fixed: 52, center: true },
  { key: "actions", header: "إجراءات", fixed: 104, center: true },
  { key: "title", header: "العنوان", floor: 180 },
  { key: "description", header: "الوصف", floor: 300 },
  { key: "images", header: "صور توضيحية", fixed: 170 },
  { key: "status", header: "الحالة", fixed: 130 },
  { key: "priority", header: "الأولوية", fixed: 115 },
  { key: "due_date", header: "الموعد", fixed: 140 },
];

const SCOPE = "/super-admin/development-notes";
const WIDTHS_KEY = columnWidthsKey(SCOPE, COLUMNS.map((column) => column.key));
const HEIGHTS_KEY = rowHeightsKey(SCOPE);

const STATUS_OPTIONS: { value: DevelopmentNote["status"]; label: string }[] = [
  { value: "todo", label: "قيد الانتظار" },
  { value: "in_progress", label: "قيد التنفيذ" },
  { value: "done", label: "مكتملة" },
];

const PRIORITY_OPTIONS: { value: DevelopmentNote["priority"]; label: string }[] = [
  { value: "low", label: "منخفضة" },
  { value: "medium", label: "متوسطة" },
  { value: "high", label: "عالية" },
];

const priorityClass: Record<DevelopmentNote["priority"], string> = {
  low: "aseel-text-soft",
  medium: "",
  high: "font-semibold text-red-600",
};

/** الخادم يعيد `images` دائماً — الحارس لواجهة تسبق خادمها لحظةَ النشر. */
const normalize = (note: DevelopmentNote): DevelopmentNote =>
  ({ ...note, images: note.images ?? [] });

type Lightbox = { noteId: number | "new"; index: number };

export const DevelopmentNotesPage: React.FC = () => {
  const [notes, setNotes] = useState<DevelopmentNote[]>([]);
  const [draft, setDraft] = useState<DevelopmentNoteWrite>(() => emptyNote(0));
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | "new" | null>(null);
  const [uploadingId, setUploadingId] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [colWidths, setColWidths] = useState<SizeMap>(() => readSizes(WIDTHS_KEY));
  const [rowHeights, setRowHeights] = useState<SizeMap>(() => readSizes(HEIGHTS_KEY));
  const [lightbox, setLightbox] = useState<Lightbox | null>(null);
  const [expanded, setExpanded] = useState<Record<number | "new", boolean>>(
    {} as Record<number | "new", boolean>,
  );
  const draftTitleRef = useRef<HTMLInputElement>(null);
  const descriptionRefs = useRef(new Map<string, HTMLTextAreaElement>());
  /** هل قُصّ وصف كل صف فعلاً؟ يُقاس بعد كل رسم — النص والعرض والارتفاع كلها تغيّره. */
  const [clipped, setClipped] = useState<Record<string, boolean>>({});

  // كل ما يغيّر القصّ في التبعيات: النص، وعرض العمود، وارتفاع الصف، والطيّ.
  useEffect(() => {
    const measured: Record<string, boolean> = {};
    descriptionRefs.current.forEach((element, key) => {
      measured[key] = element.scrollHeight > element.clientHeight + 1;
    });
    setClipped((current) => {
      const keys = new Set([...Object.keys(current), ...Object.keys(measured)]);
      for (const key of keys) {
        if (current[key] !== measured[key]) return measured;
      }
      return current;
    });
  }, [notes, draft.description, colWidths, rowHeights, expanded]);

  const load = () => {
    setLoading(true);
    setError(null);
    listDevelopmentNotes()
      .then((rows) => setNotes(sortDevelopmentNotes(rows.map(normalize))))
      .catch((cause) => setError(cause instanceof Error ? cause.message : "تعذّر تحميل الملاحظات"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  // عرض العمود يكبر مع أطول نص فيه ما لم يضبطه المستخدم بالسحب.
  const autoWidths = useMemo(() => {
    const titles = [...notes.map((note) => note.title), draft.title];
    const descriptions = [...notes.map((note) => note.description), draft.description];
    return {
      title: autoFitColumnWidth("العنوان", titles),
      description: autoFitColumnWidth("الوصف", descriptions),
    } as Record<string, number>;
  }, [notes, draft.title, draft.description]);

  const widthOf = (column: NoteColumn) =>
    colWidths[column.key]
    ?? column.fixed
    ?? Math.max(column.floor ?? 0, autoWidths[column.key] ?? 160);
  const tableWidth = COLUMNS.reduce((total, column) => total + widthOf(column), 0);

  const startResize = (event: React.MouseEvent, column: NoteColumn) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = widthOf(column);
    const rtl = getComputedStyle(event.currentTarget as HTMLElement).direction === "rtl";
    const onMove = (moveEvent: MouseEvent) => {
      setColWidths((current) => ({
        ...current, [column.key]: nextColumnWidth(startWidth, moveEvent.clientX - startX, rtl),
      }));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      setColWidths((current) => { writeSizes(WIDTHS_KEY, current); return current; });
    };
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  /** نقرتان على المقبض = إعادة العمود للعرض التلقائي (كما في Excel). */
  const autoFit = (columnKey: string) => {
    setColWidths((current) => {
      const rest = { ...current };
      delete rest[columnKey];
      writeSizes(WIDTHS_KEY, rest);
      return rest;
    });
  };

  /** ارتفاع الصف: يُسحب من حدّه السفلي في عمود الترقيم — تماماً كصفوف Excel. */
  const startRowResize = (event: React.MouseEvent, rowKey: number | "new") => {
    event.preventDefault();
    const row = (event.currentTarget as HTMLElement).closest("tr");
    if (!row) return;
    const startY = event.clientY;
    const startHeight = row.getBoundingClientRect().height;
    const onMove = (moveEvent: MouseEvent) => {
      setRowHeights((current) => ({
        ...current, [rowKey]: nextRowHeight(startHeight, moveEvent.clientY - startY),
      }));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      setRowHeights((current) => { writeSizes(HEIGHTS_KEY, current); return current; });
    };
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const autoFitRow = (rowKey: number | "new") => {
    setRowHeights((current) => {
      const rest = { ...current };
      delete rest[rowKey];
      writeSizes(HEIGHTS_KEY, rest);
      return rest;
    });
  };

  /** خلية الترقيم = رأس الصف: رقمه ومقبض ارتفاعه. `label` رقم الصف الظاهر لا معرّفه. */
  const rowHandleCell = (
    rowKey: number | "new", label: string, content: React.ReactNode, className: string,
  ) => (
    <td
      style={{ padding: "0.5rem 0.25rem", verticalAlign: "middle" }}
      className={`relative border-l border-[var(--color-border)] text-center ${className}`}
    >
      {content}
      <span
        onMouseDown={(event) => startRowResize(event, rowKey)}
        onDoubleClick={() => autoFitRow(rowKey)}
        role="separator"
        aria-label={`تغيير ارتفاع الصف ${label}`}
        title="اسحب لتغيير ارتفاع الصف · نقرتان لإعادته تلقائياً"
        className="absolute inset-x-0 bottom-0 h-1.5 cursor-row-resize select-none hover:bg-[var(--color-primary)]"
      />
    </td>
  );

  const patchLocal = <K extends keyof DevelopmentNote>(id: number, key: K, value: DevelopmentNote[K]) => {
    setNotes((current) => current.map((note) => note.id === id ? { ...note, [key]: value } : note));
  };

  const applySaved = (saved: DevelopmentNote) => {
    setNotes((current) => sortDevelopmentNotes(
      current.map((row) => row.id === saved.id ? normalize(saved) : row),
    ));
  };

  const save = async (note: DevelopmentNote) => {
    setSavingId(note.id);
    setError(null);
    try {
      applySaved(await updateDevelopmentNote(note.id, {
        title: note.title, description: note.description, status: note.status,
        priority: note.priority, images: note.images,
        due_date: note.due_date || null, position: note.position,
      }));
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
      setNotes((current) => sortDevelopmentNotes([...current, normalize(created)]));
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

  /** الصور تُحفظ فور تغيّرها — رفعٌ ينتظر زر الحفظ صورةٌ معرَّضة للضياع. */
  const persistImages = async (note: DevelopmentNote, images: DevelopmentNoteImage[]) => {
    patchLocal(note.id, "images", images);
    setSavingId(note.id);
    try {
      applySaved(await updateDevelopmentNote(note.id, { images }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل حفظ صور الملاحظة");
    } finally {
      setSavingId(null);
    }
  };

  const addImages = async (target: DevelopmentNote | "new", files: FileList | null) => {
    if (!files || files.length === 0) return;
    const noteId = target === "new" ? "new" : target.id;
    setUploadingId(noteId);
    setError(null);
    try {
      const urls = await cloudinaryService.uploadMultipleFiles(Array.from(files));
      const uploaded = urls.map((url) => ({ url, caption: "" }));
      if (target === "new") {
        setDraft((current) => ({ ...current, images: [...current.images, ...uploaded] }));
      } else {
        await persistImages(target, [...target.images, ...uploaded]);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "فشل رفع الصورة");
    } finally {
      setUploadingId(null);
    }
  };

  const removeImage = (target: DevelopmentNote | "new", index: number) => {
    if (target === "new") {
      setDraft((current) => ({
        ...current, images: current.images.filter((_, at) => at !== index),
      }));
      return;
    }
    void persistImages(target, target.images.filter((_, at) => at !== index));
  };

  const setCaption = (target: DevelopmentNote | "new", index: number, caption: string) => {
    const next = (images: DevelopmentNoteImage[]) =>
      images.map((image, at) => at === index ? { ...image, caption } : image);
    if (target === "new") {
      setDraft((current) => ({ ...current, images: next(current.images) }));
    } else {
      patchLocal(target.id, "images", next(target.images));
    }
  };

  const imageCell = (target: DevelopmentNote | "new", images: DevelopmentNoteImage[], label: string) => {
    const noteId = target === "new" ? "new" : target.id;
    return (
      <div className="flex flex-wrap items-center gap-1 p-1">
        {images.map((image, index) => (
          <button
            key={`${image.url}-${index}`} type="button"
            onClick={() => setLightbox({ noteId, index })}
            title={image.caption || "معاينة الصورة"}
            aria-label={`معاينة صورة ${index + 1} — ${label}`}
            className="h-11 w-11 overflow-hidden rounded border border-[var(--color-border)] hover:ring-2 hover:ring-[var(--color-primary)]"
          >
            <img src={image.url} alt={image.caption || label} className="h-full w-full object-cover" />
          </button>
        ))}
        <label
          className="aseel-text-soft flex h-11 w-11 cursor-pointer items-center justify-center rounded border border-dashed border-[var(--color-border)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
          title="إدراج صورة توضيحية"
        >
          {uploadingId === noteId
            ? <RefreshCw className="h-4 w-4 animate-spin" />
            : <ImagePlus className="h-4 w-4" />}
          <input
            type="file" accept="image/*" multiple className="sr-only"
            aria-label={`إدراج صورة — ${label}`}
            onChange={(event) => {
              void addImages(target, event.target.files);
              event.target.value = "";
            }}
          />
        </label>
      </div>
    );
  };

  /**
   * الوصف يظهر مقصوصاً بثلاثة أسطر، وتفاصيله كاملةً خلف «عرض المزيد» — كي لا
   * يبتلع صفٌّ واحد طويل الورقةَ كلها. القصّ يتبع عرض العمود الحالي.
   */
  const descriptionCell = (
    rowKey: number | "new", value: string, label: string, onChange: (next: string) => void,
  ) => {
    const open = expanded[rowKey] ?? false;
    return (
      // `flex-1` يجعل الوصف يملأ ارتفاع الصف مهما علا (بيدٍ أو بسبب خلية أطول)
      // فلا تبقى فجوة بيضاء تحته.
      <div className="flex h-full flex-col">
        <textarea
          ref={(element) => {
            if (element) descriptionRefs.current.set(String(rowKey), element);
            else descriptionRefs.current.delete(String(rowKey));
          }}
          aria-label={label} rows={COLLAPSED_DESCRIPTION_LINES}
          // المطويّ يتّكل على `rows` وحدها فيقصّ عند سطرٍ كامل مهما تغيّر حجم الخط،
          // و`pb-0` تمنع ظهور رأس السطر الرابع داخل الحشوة السفلية (النص يفيض فيها).
          className={`${cellClass} min-h-0 flex-1 resize-none overflow-hidden ${open ? "[field-sizing:content]" : "pb-0"}`}
          value={value} onChange={(event) => onChange(event.target.value)}
        />
        {(open || clipped[String(rowKey)]) && (
          <button
            type="button"
            aria-label={`${open ? "عرض أقل" : "عرض المزيد"} — ${label}`}
            className="shrink-0 whitespace-nowrap px-2 pb-1 text-start text-xs font-medium text-[var(--color-primary)] hover:underline"
            onClick={() => setExpanded((current) => ({ ...current, [rowKey]: !open }))}
          >
            {open ? "عرض أقل" : "عرض المزيد"}
          </button>
        )}
      </div>
    );
  };

  const lightboxTarget: DevelopmentNote | "new" | null = lightbox === null
    ? null
    : lightbox.noteId === "new"
      ? "new"
      : notes.find((note) => note.id === lightbox.noteId) ?? null;
  const lightboxImages = lightboxTarget === null
    ? []
    : lightboxTarget === "new" ? draft.images : lightboxTarget.images;
  const lightboxImage = lightbox === null ? undefined : lightboxImages[lightbox.index];

  const doneCount = notes.filter(isNoteDone).length;

  return (
    <main className="p-4 md:p-6" dir="rtl">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text)]">ملاحظات التطوير</h1>
          <p className="text-sm aseel-text-soft">
            ورقة عمل قابلة للتحرير: اسحب حافة العنوان لتغيير عرض العمود، وحدَّ الصف السفلي من عمود
            الترقيم لتغيير ارتفاعه (نقرتان = تلقائي)، وأدرج صوراً توضيحية لكل ملاحظة.
            المكتملة تُلوَّن بالأخضر وتنزل لآخر القائمة.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[var(--color-surface-2)] px-3 py-1 text-xs aseel-text-soft">
            {notes.length} ملاحظة · {doneCount} مكتملة
          </span>
          <button type="button" onClick={() => draftTitleRef.current?.focus()} className="aseel-btn aseel-btn--primary"><Plus className="h-4 w-4" /> إنشاء ملاحظة</button>
          <button type="button" onClick={load} className="aseel-iconbtn" aria-label="تحديث ملاحظات التطوير" title="تحديث"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
        </div>
      </header>
      {error && <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        {/* العرض 100% مع أرضية = الجدول يملأ الإطار فلا يبقى فراغ جانبي، ويسكرول عند الضيق */}
        <table className="border-collapse text-sm" style={{ tableLayout: "fixed", width: "100%", minWidth: `${tableWidth}px` }}>
          <colgroup>
            {COLUMNS.map((column) => (
              <col key={column.key} style={{ width: `${widthOf(column)}px` }} />
            ))}
          </colgroup>
          <thead className="sticky top-0 z-10 bg-[var(--color-surface-2)] aseel-text-soft"><tr>
            {COLUMNS.map((column) => (
              <th
                key={column.key}
                className={`relative border-l border-[var(--color-border)] px-2 py-2 ${column.center ? "text-center" : "text-right"}`}
              >
                {column.header}
                <span
                  onMouseDown={(event) => startResize(event, column)}
                  onDoubleClick={() => autoFit(column.key)}
                  role="separator"
                  aria-label={`تغيير عرض عمود ${column.header}`}
                  title="اسحب لتغيير عرض العمود · نقرتان لإعادته تلقائياً"
                  className="absolute top-0 h-full w-1.5 cursor-col-resize select-none hover:bg-[var(--color-primary)]"
                  style={{ insetInlineEnd: 0 }}
                />
              </th>
            ))}
          </tr></thead>
          <tbody>
            {notes.map((note, index) => {
              const done = isNoteDone(note);
              return (
                <tr
                  key={note.id}
                  style={{
                    height: rowHeights[note.id] ? `${rowHeights[note.id]}px` : undefined,
                    backgroundColor: done ? DONE_TINT : undefined,
                  }}
                  className="border-t border-[var(--color-border)]"
                >
                  {rowHandleCell(note.id, String(index + 1), index + 1, done ? "font-medium text-green-700" : "aseel-text-soft")}
                  <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><div className="flex justify-center gap-1 p-1.5"><button type="button" className="aseel-iconbtn" onClick={() => void save(note)} disabled={savingId === note.id} aria-label={`حفظ ${note.title}`} title="حفظ"><Save className="h-4 w-4" /></button><button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => void remove(note)} disabled={savingId === note.id} aria-label={`حذف ${note.title}`} title="حذف"><Trash2 className="h-4 w-4" /></button></div></td>
                  <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><input aria-label={`عنوان الملاحظة ${index + 1}`} className={`${cellClass} ${done ? "font-medium text-green-800 dark:text-green-300" : ""}`} value={note.title} onChange={(e) => patchLocal(note.id, "title", e.target.value)} /></td>
                  <td style={FILL_CELL_STYLE} className="border-l border-[var(--color-border)]">{descriptionCell(note.id, note.description, `وصف الملاحظة ${index + 1}`, (next) => patchLocal(note.id, "description", next))}</td>
                  <td style={CELL_STYLE} className="border-l border-[var(--color-border)]">{imageCell(note, note.images ?? [], `الملاحظة ${index + 1}`)}</td>
                  <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><select aria-label={`حالة الملاحظة ${index + 1}`} className={`${cellClass} ${done ? "font-semibold text-green-700 dark:text-green-300" : ""}`} value={note.status} onChange={(e) => {
                    // الحالة تُحفظ فور اختيارها كي تُلوَّن المكتملة وتنزل لآخر القائمة حالاً.
                    const status = e.target.value as DevelopmentNote["status"];
                    patchLocal(note.id, "status", status);
                    void save({ ...note, status });
                  }}>{STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></td>
                  <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><select aria-label={`أولوية الملاحظة ${index + 1}`} className={`${cellClass} ${priorityClass[note.priority]}`} value={note.priority} onChange={(e) => patchLocal(note.id, "priority", e.target.value as DevelopmentNote["priority"])}>{PRIORITY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></td>
                  <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><AseelDateInput aria-label={`موعد الملاحظة ${index + 1}`} className={cellClass} value={note.due_date || ""} onChange={(value) => patchLocal(note.id, "due_date", value || null)} /></td>
                </tr>
              );
            })}
            <tr
              style={{ height: rowHeights.new ? `${rowHeights.new}px` : undefined }}
              className="border-t-2 border-[var(--color-primary)] bg-[var(--color-surface-2)]"
            >
              {rowHandleCell("new", "الجديد", <Plus className="mx-auto h-4 w-4" />, "aseel-text-soft")}
              <td style={CELL_STYLE} className="border-l border-[var(--color-border)] text-center"><button type="button" onClick={() => void add()} disabled={savingId === "new"} className="aseel-btn aseel-btn--primary"><Plus className="h-4 w-4" /> إضافة</button></td>
              <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><input ref={draftTitleRef} aria-label="عنوان ملاحظة جديدة" className={cellClass} placeholder="ملاحظة تطوير جديدة" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") void add(); }} /></td>
              <td style={FILL_CELL_STYLE} className="border-l border-[var(--color-border)]">{descriptionCell("new", draft.description, "وصف ملاحظة جديدة", (next) => setDraft({ ...draft, description: next }))}</td>
              <td style={CELL_STYLE} className="border-l border-[var(--color-border)]">{imageCell("new", draft.images, "ملاحظة جديدة")}</td>
              <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><select aria-label="حالة ملاحظة جديدة" className={cellClass} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as DevelopmentNoteWrite["status"] })}>{STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></td>
              <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><select aria-label="أولوية ملاحظة جديدة" className={cellClass} value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: e.target.value as DevelopmentNoteWrite["priority"] })}>{PRIORITY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></td>
              <td style={CELL_STYLE} className="border-l border-[var(--color-border)]"><AseelDateInput aria-label="موعد ملاحظة جديدة" className={cellClass} value={draft.due_date || ""} onChange={(value) => setDraft({ ...draft, due_date: value || null })} /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs aseel-text-soft">استخدم Tab للتنقّل بين الخلايا، ثم زر الحفظ في أول الصف. الصور وتغيير الحالة يُحفظان فوراً.</p>

      {lightbox !== null && lightboxTarget !== null && lightboxImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          role="dialog" aria-modal="true" aria-label="معاينة صورة الملاحظة"
          onClick={() => setLightbox(null)}
        >
          <div
            className="flex max-h-full w-full max-w-3xl flex-col gap-3 overflow-auto rounded-lg bg-[var(--color-surface)] p-4"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm aseel-text-soft">صورة {lightbox.index + 1} من {lightboxImages.length}</span>
              <div className="flex items-center gap-2">
                <button
                  type="button" className="aseel-iconbtn aseel-iconbtn--danger" title="حذف الصورة"
                  aria-label="حذف الصورة"
                  onClick={() => { removeImage(lightboxTarget, lightbox.index); setLightbox(null); }}
                ><Trash2 className="h-4 w-4" /></button>
                <button type="button" className="aseel-iconbtn" title="إغلاق" aria-label="إغلاق المعاينة" onClick={() => setLightbox(null)}><X className="h-4 w-4" /></button>
              </div>
            </div>
            <img src={lightboxImage.url} alt={lightboxImage.caption || "صورة توضيحية"} className="max-h-[65vh] w-full rounded object-contain" />
            <input
              aria-label="تعليق الصورة" placeholder="تعليق توضيحي للصورة (اختياري)"
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)]"
              value={lightboxImage.caption}
              onChange={(event) => setCaption(lightboxTarget, lightbox.index, event.target.value)}
            />
            {lightboxTarget !== "new" && (
              <button
                type="button" className="aseel-btn aseel-btn--primary self-start"
                onClick={() => void persistImages(lightboxTarget, lightboxTarget.images)}
              ><Save className="h-4 w-4" /> حفظ التعليق</button>
            )}
          </div>
        </div>
      )}
    </main>
  );
};
