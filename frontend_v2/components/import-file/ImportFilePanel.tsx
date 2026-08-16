import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  Check,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { usePermissions } from "@/contexts/PermissionsContext";
import { useToast } from "@/contexts/ToastContext";
import { useConfirm } from "@/contexts/ConfirmContext";
import { clientLogger } from "@/services/logger";
import {
  attachImportFileDocument,
  createImportFileItem,
  deleteImportFileDocument,
  deleteImportFileItem,
  fetchDealImportFile,
  updateImportFileItem,
  uploadImportFileDocument,
  type ImportFileDocumentRow,
  type ImportFileItemRow,
  type ImportFilePayload,
} from "@/services/importFileApi";
import {
  IMPORT_JOURNEY_STAGES,
  type ImportStageKey,
} from "@/components/import-flow/importJourneyGuidance";
import { formatNumber } from "@/utils/formatNumber";
import { formatDateLocalized } from "@/utils/formatDate";
import { openInNewTab } from "@/utils/openInNewTab";

/**
 * لوحة ملف الاستيراد داخل الصفقة — ما يجب أن يُرفع وما يجب أن يُفعل، بمراحله.
 *
 * ثلاث قواعد تحكم هذه الشاشة:
 *
 * - **النِسَب تُعرض ولا تُحسب.** `progress` لكل مرحلة وللملف كله يأتي من الخادم
 *   (`import_file/services.py` — `stage_progress`)، وهو نفسه الذي تقرؤه شارة
 *   مرشد الرحلة. حسابه هنا من البنود كان يعني مصدراً ثالثاً لرقمٍ له مصدر واحد.
 * - **حالة المستند مشتقّة من مرفقه.** فلا خانة اختيار على صفّ مستند — الخادم
 *   يردّها 400 أصلاً؛ الخانة لبنود المهامّ وحدها.
 * - **الصفّ المشتقّ (سعر الشحن) يُقرأ ولا يُرفع.** مصدره بطاقة الشحنة، والملاحظة
 *   تقول أين يُدخَل بدل ترك المستخدم يبحث عن زر رفعٍ لا وجود له.
 *
 * الرفع يمرّ بمسار المنصة القائم (`services/importFileApi.uploadImportFileDocument`
 * → `POST /api/media/upload/`) ثم يُسجَّل رابطه — لا مسار رفع ثانٍ ولا مكوّن مرفقات ثانٍ.
 */

interface ImportFilePanelProps {
  /** معرّف الصفقة (PK الرقمي) — الملف ملف صفقة، والشحنة تُقرأ منها. */
  dealId: number;
}

/**
 * أين يرسو البند المخصّص الجديد — القاعدة نفسها التي يمشي عليها الكتالوج
 * (`import_file/catalog.py`): وثائق الشحن والتخليص والنقل وثائق **شحنة**،
 * والشحنة تحمل عدة صفقات، فرفعةٌ واحدة تُكمل ملفاتها جميعاً. وما قبل الشحنة
 * (العرض، الصفقة، دفعاتها) خاصٌّ بالصفقة وحدها.
 */
const SHIPMENT_ANCHORED_STAGES: ReadonlySet<string> = new Set<ImportStageKey>([
  "shipment", "freight", "clearance", "local", "invoice",
]);

const errorText = (error: unknown): string =>
  (error as Error)?.message || "تعذّر إتمام العملية.";

/** حجم الملف بالكيلوبايت — عبر المنسّق الموحّد لا بـ`toFixed` محلي. */
const sizeLabel = (bytes: number): string =>
  bytes > 0 ? `${formatNumber(bytes / 1024, { maxDecimals: 1 })} ك.ب` : "";

export const ImportFilePanel: React.FC<ImportFilePanelProps> = ({ dealId }) => {
  const { can } = usePermissions();
  const toast = useToast();
  const confirm = useConfirm();
  const canManage = can("importfile.file.manage");

  const [file, setFile] = useState<ImportFilePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  /** البند الجاري تعديله — يعطّل أزراره وحدها لا الشاشة كلها. */
  const [busyItemId, setBusyItemId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [draftStage, setDraftStage] = useState<ImportStageKey>("shipment");
  const [draftType, setDraftType] = useState<"document" | "task">("document");
  const [draftLabel, setDraftLabel] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    fetchDealImportFile(dealId)
      .then((data) => {
        setFile(data);
        setError(null);
      })
      .catch((e) => {
        // 404 هنا تعني «الوحدة غير مرخّصة» لا «صفقة غير موجودة» — الحارس يردّها
        // قبل أي استعلام (`import_file/views.py`). التبويب نفسه محروس بالعَلَم،
        // فالوصول إلى هنا بلا ترخيص يعني تبدّل الترخيص أثناء الجلسة.
        setError(errorText(e));
        clientLogger.info("import_file.load_failed", { dealId, message: errorText(e) });
      })
      .finally(() => setLoading(false));
  }, [dealId]);

  useEffect(load, [load]);

  /** كل تعديل يُعيد قراءة الملف: النِسَب تُحسب في الخادم، ومزامنتها يدوياً هنا تفترق. */
  const run = async (itemId: number, action: () => Promise<unknown>, done: string) => {
    setBusyItemId(itemId);
    try {
      await action();
      toast(done, "success");
      load();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusyItemId(null);
    }
  };

  const handleUpload = async (item: ImportFileItemRow, picked: FileList | null) => {
    const chosen = picked?.[0];
    if (!chosen || item.id == null) return;
    await run(
      item.id,
      async () => {
        const url = await uploadImportFileDocument(chosen);
        await attachImportFileDocument(item.id as number, {
          url,
          filename: chosen.name,
          mime_type: chosen.type,
          size_bytes: chosen.size,
        });
      },
      `تم رفع «${chosen.name}».`,
    );
  };

  const handleRemoveDocument = async (item: ImportFileItemRow, doc: ImportFileDocumentRow) => {
    const ok = await confirm({
      title: "حذف المستند",
      message: `سيُحذف «${doc.filename || "الملف"}» من الملف ومن التخزين نهائياً، ويعود البند «${item.label}» ناقصاً.`,
      danger: true,
      confirmText: "حذف",
    });
    if (!ok || item.id == null) return;
    await run(item.id, () => deleteImportFileDocument(doc.id), "تم حذف المستند.");
  };

  const handleRemoveItem = async (item: ImportFileItemRow) => {
    const ok = await confirm({
      title: "حذف البند",
      message: `سيُحذف البند «${item.label}» ومرفقاته من ملف هذه الصفقة.`,
      danger: true,
      confirmText: "حذف",
    });
    if (!ok || item.id == null) return;
    await run(item.id, () => deleteImportFileItem(item.id as number), "تم حذف البند.");
  };

  const handleToggleDone = (item: ImportFileItemRow) => {
    if (item.id == null) return;
    void run(
      item.id,
      () => updateImportFileItem(item.id as number, { done: !item.done }),
      item.done ? "أُعيدت المهمّة غير منجزة." : "تم إنجاز المهمّة.",
    );
  };

  const handleToggleRequired = (item: ImportFileItemRow) => {
    if (item.id == null) return;
    void run(
      item.id,
      () => updateImportFileItem(item.id as number, { required: !item.required }),
      item.required ? "خرج البند من حساب الاكتمال." : "دخل البند حساب الاكتمال.",
    );
  };

  const handleAdd = async () => {
    const label = draftLabel.trim();
    if (!label || !file) return;
    // المرساة تُختار بمرحلة البند لا بمكان الضغط — القاعدة نفسها في الكتالوج.
    const onShipment = SHIPMENT_ANCHORED_STAGES.has(draftStage) && file.shipment !== null;
    setAdding(true);
    try {
      await createImportFileItem({
        ...(onShipment ? { shipment: file.shipment!.id } : { deal: file.deal.id }),
        stage: draftStage,
        item_type: draftType,
        label,
      });
      setDraftLabel("");
      toast(
        onShipment
          ? "أُضيف البند على الشحنة — يظهر في ملف كل صفقاتها."
          : "أُضيف البند إلى ملف هذه الصفقة.",
        "success",
      );
      load();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setAdding(false);
    }
  };

  if (loading && !file) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-sm text-[var(--color-text-muted)]">
        <Loader2 className="h-4 w-4 animate-spin" />
        جارٍ فتح ملف الاستيراد…
      </div>
    );
  }

  if (error && !file) {
    return (
      <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
        <span className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          {error}
        </span>
        <button
          type="button"
          onClick={load}
          className="rounded border border-red-300 px-2 py-1 text-xs hover:bg-red-100 dark:border-red-800 dark:hover:bg-red-900/40"
        >
          إعادة المحاولة
        </button>
      </div>
    );
  }

  if (!file) return null;

  return (
    <div dir="rtl" className="flex flex-col gap-3">
      <header className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
        <span className="text-sm font-bold text-[var(--color-text)]">ملف الاستيراد</span>
        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-semibold text-blue-800 dark:bg-blue-900/40 dark:text-blue-200">
          الأوراق المكتملة {file.progress.done} من {file.progress.total}
        </span>
        {file.shipment && (
          <span className="text-[11px] text-[var(--color-text-muted)]">
            ضمن الشحنة {file.shipment.shipment_number} — وثائق الشحن تُرفع مرّة واحدة لكل صفقاتها.
          </span>
        )}
        <button
          type="button"
          onClick={() => openInNewTab("/import-file/guide")}
          className="ms-auto flex items-center gap-1 rounded border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
          title="شرح كل مستند: ما هو، ولماذا يُطلب، ومن يصدره"
        >
          <BookOpen className="h-3.5 w-3.5" />
          ما هذه المستندات؟
        </button>
        <button
          type="button"
          onClick={load}
          className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
          title="تحديث"
          aria-label="تحديث ملف الاستيراد"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </header>

      {file.stages.map((stage) => (
        <section key={stage.stage} className="rounded-lg border border-[var(--color-border)]">
          <div className="flex items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5">
            <span className="text-xs font-bold text-[var(--color-text)]">{stage.label}</span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                stage.progress.done >= stage.progress.total
                  ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
                  : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
              }`}
            >
              {stage.progress.done} من {stage.progress.total}
            </span>
          </div>

          <ul className="divide-y divide-[var(--color-border)]">
            {stage.items.map((item) => (
              <li
                key={item.id ?? item.kind}
                className="flex flex-wrap items-start gap-2 px-3 py-2"
              >
                {/* المهمّة تُعلَّم يدوياً؛ المستند يكتمل بمرفقه فلا خانة له. */}
                {item.item_type === "task" && canManage ? (
                  <input
                    type="checkbox"
                    checked={item.done}
                    disabled={busyItemId === item.id}
                    onChange={() => handleToggleDone(item)}
                    className="mt-1 h-4 w-4 accent-emerald-600"
                    aria-label={`إنجاز: ${item.label}`}
                  />
                ) : (
                  <span
                    className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-white ${
                      item.is_done ? "bg-emerald-500" : "bg-[var(--color-surface-3)]"
                    }`}
                    aria-hidden="true"
                  >
                    {item.is_done && <Check className="h-3 w-3" />}
                  </span>
                )}

                <div className="min-w-[12rem] flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={`text-xs font-semibold ${item.required ? "text-[var(--color-text)]" : "text-[var(--color-text-muted)]"}`}>
                      {item.label}
                    </span>
                    {!item.required && (
                      <span className="rounded bg-[var(--color-surface-3)] px-1 text-[9px] text-[var(--color-text-muted)]">
                        اختياري — خارج حساب الاكتمال
                      </span>
                    )}
                    {item.is_custom && (
                      <span className="rounded bg-[var(--color-surface-3)] px-1 text-[9px] text-[var(--color-text-muted)]">مخصّص</span>
                    )}
                    {item.derived && (
                      <span className="rounded bg-blue-100 px-1 text-[9px] text-blue-800 dark:bg-blue-900/40 dark:text-blue-200">
                        من بيانات الشحنة
                      </span>
                    )}
                  </div>
                  {item.note && (
                    <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--color-text-muted)]">{item.note}</p>
                  )}

                  {item.documents.length > 0 && (
                    <ul className="mt-1 flex flex-col gap-1">
                      {item.documents.map((doc) => (
                        <li key={doc.id} className="flex items-center gap-2 rounded bg-[var(--color-surface-2)] px-2 py-1">
                          <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--color-text-muted)]" />
                          <a
                            href={doc.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="truncate text-[11px] font-medium text-blue-700 hover:underline dark:text-blue-300"
                            title="فتح الملف في تبويب جديد"
                          >
                            {doc.filename || "ملف مرفوع"}
                          </a>
                          <span className="text-[10px] text-[var(--color-text-muted)]">
                            {[sizeLabel(doc.size_bytes), doc.uploaded_by_name, formatDateLocalized(doc.uploaded_at)]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                          {canManage && (
                            <button
                              type="button"
                              onClick={() => void handleRemoveDocument(item, doc)}
                              disabled={busyItemId === item.id}
                              className="ms-auto rounded p-0.5 text-[var(--color-text-muted)] hover:text-red-600 disabled:opacity-50"
                              title="حذف المستند"
                              aria-label={`حذف ${doc.filename || "المستند"}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {canManage && !item.derived && (
                  <div className="flex items-center gap-1">
                    {item.item_type === "document" && item.id != null && (
                      <>
                        <input
                          id={`import-file-upload-${item.id}`}
                          type="file"
                          className="hidden"
                          disabled={busyItemId === item.id}
                          onChange={(event) => {
                            void handleUpload(item, event.target.files);
                            event.target.value = "";
                          }}
                        />
                        <label
                          htmlFor={`import-file-upload-${item.id}`}
                          className="flex cursor-pointer items-center gap-1 rounded border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-text)] hover:bg-[var(--color-surface-3)]"
                        >
                          {busyItemId === item.id
                            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            : <Upload className="h-3.5 w-3.5" />}
                          رفع
                        </label>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => handleToggleRequired(item)}
                      disabled={busyItemId === item.id}
                      className="rounded border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] disabled:opacity-50"
                      title={item.required
                        ? "يخرج من حساب الاكتمال ويبقى في الملف"
                        : "يعود إلى حساب الاكتمال"}
                    >
                      {item.required ? "غير مطلوب" : "مطلوب"}
                    </button>
                    {item.is_custom && (
                      <button
                        type="button"
                        onClick={() => void handleRemoveItem(item)}
                        disabled={busyItemId === item.id}
                        className="rounded p-1 text-[var(--color-text-muted)] hover:text-red-600 disabled:opacity-50"
                        title="حذف البند المخصّص"
                        aria-label={`حذف البند ${item.label}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}

      {canManage && (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-dashed border-[var(--color-border)] px-3 py-2">
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] font-semibold text-[var(--color-text-muted)]">المرحلة</span>
            <select
              value={draftStage}
              onChange={(event) => setDraftStage(event.target.value as ImportStageKey)}
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs"
            >
              {IMPORT_JOURNEY_STAGES.map((s) => (
                <option key={s.key} value={s.key}>{s.order}. {s.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[10px] font-semibold text-[var(--color-text-muted)]">النوع</span>
            <select
              value={draftType}
              onChange={(event) => setDraftType(event.target.value as "document" | "task")}
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs"
            >
              <option value="document">مستند يُرفع</option>
              <option value="task">مهمّة تُنجَز</option>
            </select>
          </label>
          <label className="flex min-w-[14rem] flex-1 flex-col gap-0.5">
            <span className="text-[10px] font-semibold text-[var(--color-text-muted)]">اسم البند</span>
            <input
              value={draftLabel}
              onChange={(event) => setDraftLabel(event.target.value)}
              placeholder="مثال: شهادة فحص المطابقة"
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs"
            />
          </label>
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={adding || !draftLabel.trim()}
            className="flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            أضف بنداً
          </button>
          {SHIPMENT_ANCHORED_STAGES.has(draftStage) && file.shipment && (
            <p className="basis-full text-[10px] text-[var(--color-text-muted)]">
              بنود هذه المرحلة تُضاف على الشحنة {file.shipment.shipment_number} فتظهر في ملف كل صفقاتها.
            </p>
          )}
        </div>
      )}
    </div>
  );
};
