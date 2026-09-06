/**
 * issue #146 — شريط مسودّات المستند المشترك: فشل الحفظ، الاستعادة، واليتامى.
 *
 * ٢٤ محرِّراً كانت تبني نفس ثلاثة شرائط بنسخٍ يدوي عن `SalesInvoiceEditor`
 * الأصلية — أيّ تعديل (كهذا: جعل اليتيم قابلاً للفتح والحذف) كان يعني ٢٤
 * تعديلاً متطابقاً. المكوّن هنا هو الفصل الوحيد؛ استدعاء المحرِّر أربع خصائص:
 * ناتج `useDocumentDraft` كاملاً، ودالّة تطبيق حمولةٍ على حالة الشاشة، ودالّة
 * «تراجع»، وعلامة «لُمِس» الحالية.
 *
 * «إخفاء» شريط اليتامى إخفاءٌ محليٌّ بلا مسّ المسودّات — يعيش هنا داخلياً
 * (لا حاجة لحالةٍ مكرَّرة في كل محرِّر) ويعود ظاهراً عند إعادة تركيب المكوّن
 * (شاشة جديدة).
 */
import React, { useState } from "react";
import { AlertTriangle, FolderOpen, Info, Trash2, Undo2, X } from "lucide-react";
import { useConfirm } from "../../contexts/ConfirmContext";
import { formatTimeValue } from "../../utils/formatDate";
import { orphanDraftsBannerText, wouldOpeningOrphanClobberUnsavedWork } from "../../utils/documentDraft";
import type { UseDocumentDraftResult } from "../../hooks/useDocumentDraft";

export interface DocumentDraftBannersProps<TPayload> {
  /** ناتج `useDocumentDraft` كاملاً — استدعاءٌ واحدٌ يكفي الشاشة. */
  draft: UseDocumentDraftResult<TPayload>;
  /** يطبّق حمولة مسودّة على حالة الشاشة — نفس `onRestore` الذي مرَّره المحرِّر للخطّاف. */
  onApplyDraft: (payload: TPayload) => void;
  /** «تراجع» على شريط الاستعادة: يعيد الشاشة لحالتها المحفوظة ويمسح المسودّة. */
  onUndo: () => void;
  /** علامة «لُمِس» الحالية — تحكم تحذير «سيستبدل عملك الحالي» عند فتح يتيم. */
  isTouched: boolean;
  /**
   * الشاشة للقراءة فقط (مرحَّلة، مقفلة، أو بلا صلاحية تحرير) — يُخفي شريط
   * **فشل الحفظ** وحده.
   *
   * ليس زينةً ولا حقلاً تجميلياً: خمسةٌ من المحرِّرات كانت تحرس هذا الشريط
   * بشرطها الخاص قبل توحيدها هنا (`!readOnly` · `!effectiveReadOnly` ·
   * `!isReadOnly` · `!isLocked` · `!posted`)، وإسقاطُ الحرس عند الاستخراج
   * كان يجعل الشاشةَ المقفلة تصرخ «اضغط تخزين يدوياً» بينما لا زرَّ تخزينٍ
   * فيها أصلاً — نصيحةٌ لا يمكن اتّباعها. شريطا الاستعادة واليتامى لا يتأثّران:
   * قراءةُ مسودّةٍ قديمة أو حذفُها مشروعان ولو كان المستند مقفلاً.
   */
  readOnly?: boolean;
}

export function DocumentDraftBanners<TPayload>({
  draft,
  onApplyDraft,
  onUndo,
  isTouched,
  readOnly = false,
}: DocumentDraftBannersProps<TPayload>) {
  const confirm = useConfirm();
  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);
  const {
    draftSaveFailed,
    restoredBanner,
    discardDraft,
    orphanDrafts,
    loadOrphanDraft,
    deleteOrphanDraft,
  } = draft;

  /* فتح يتيم: عملٌ غير محفوظ على الشاشة الآن يُستبدَل بلا رجعة — نفس القاعدة
   * التي تحرس الحذف والإغلاق (issue #118–#121): تحذيرٌ صريح قبل أي استبدال. */
  const openOrphan = async (key: string) => {
    if (
      wouldOpeningOrphanClobberUnsavedWork({ isTouched }) &&
      !(await confirm({
        title: "فتح مسودّة أخرى",
        message: "لديك تعديلٌ غير محفوظ على الشاشة الآن — فتح هذه المسودّة يستبدله. متابعة؟",
        confirmText: "فتح المسودّة",
        danger: true,
      }))
    ) {
      return;
    }
    const payload = await loadOrphanDraft(key);
    if (payload) onApplyDraft(payload);
  };

  /* حذف يتيم: مَحوٌ لا رجعة فيه — تأكيدٌ صريح دائماً، بلا استثناء لشاشةٍ بلا لمسة. */
  const deleteOrphan = async (key: string) => {
    if (
      !(await confirm({
        title: "حذف المسودّة",
        message: "سيُحذف محتوى هذه المسودّة نهائياً ولا يمكن التراجع. متابعة؟",
        confirmText: "حذف",
        danger: true,
      }))
    ) {
      return;
    }
    await deleteOrphanDraft(key);
  };

  return (
    <>
      {draftSaveFailed && !readOnly && (
        <div
          role="alert"
          aria-live="assertive"
          data-testid="draft-save-failed-banner"
          className="sticky top-0 z-40 flex items-center gap-2 border-b border-red-200 bg-red-100 px-4 py-2 text-sm font-medium text-red-800"
        >
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>تعذّر حفظ نسخة محلية من هذا المستند — اضغط «تخزين» يدوياً كي لا يضيع عملك.</span>
        </div>
      )}
      {restoredBanner && (
        <div className="ktra-banner ktra-banner--warn" role="status" data-testid="draft-restored-banner">
          <Info className="h-4 w-4 shrink-0" />
          <span>
            {restoredBanner.eligibility === "restore" &&
              `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(restoredBanner.updatedAt)})`}
            {restoredBanner.eligibility === "stale" &&
              `تغيّر المستند بعد مسودتك (مسودتُك ${formatTimeValue(restoredBanner.updatedAt)})`}
            {restoredBanner.eligibility === "posted" &&
              `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(restoredBanner.updatedAt)}) لهذا المستند المنتهي — للاطّلاع فقط.`}
          </span>
          {restoredBanner.eligibility === "restore" && (
            <button type="button" className="ktra-toolbtn" onClick={onUndo} data-testid="draft-restored-undo">
              <Undo2 className="h-4 w-4" /> تراجع
            </button>
          )}
          {restoredBanner.eligibility === "stale" && (
            <>
              <button
                type="button"
                className="ktra-toolbtn"
                onClick={() => onApplyDraft(restoredBanner.payload)}
                data-testid="draft-stale-preview"
              >
                استعرض مسودتي
              </button>
              <button
                type="button"
                className="ktra-toolbtn"
                onClick={() => void discardDraft()}
                data-testid="draft-stale-discard"
              >
                تجاهلها
              </button>
            </>
          )}
        </div>
      )}
      {orphanDrafts.length > 0 && !orphanBarDismissed && (
        <div className="ktra-banner" role="status" data-testid="orphan-drafts-banner">
          <Info className="h-4 w-4 shrink-0" />
          <div className="flex flex-col gap-1">
            <span>{orphanDraftsBannerText(orphanDrafts.length)}</span>
            <ul className="list-disc pr-4 text-xs">
              {orphanDrafts.map((o) => (
                <li key={o.key} className="flex flex-wrap items-center gap-2 py-0.5">
                  <span>{formatTimeValue(o.updatedAt)} — {o.previewLine || "—"}</span>
                  <button
                    type="button"
                    className="ktra-toolbtn"
                    onClick={() => void openOrphan(o.key)}
                    data-testid="orphan-draft-open"
                  >
                    <FolderOpen className="h-3.5 w-3.5" /> فتح
                  </button>
                  <button
                    type="button"
                    className="ktra-toolbtn"
                    onClick={() => void deleteOrphan(o.key)}
                    data-testid="orphan-draft-delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> حذف
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={() => setOrphanBarDismissed(true)}
            data-testid="orphan-drafts-dismiss"
          >
            <X className="h-4 w-4" /> إخفاء
          </button>
        </div>
      )}
    </>
  );
}
