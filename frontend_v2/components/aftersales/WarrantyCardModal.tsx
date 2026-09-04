import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CalendarPlus, Info, Loader2, ShieldCheck, Trash2, Undo2, X } from "lucide-react";
import {
  createWarrantyCard,
  deleteWarrantyCard,
  extendWarrantyCard,
  updateWarrantyCard,
  type WarrantyCardDraft,
  type WarrantyCardRow,
} from "../../services/afterSalesApi";
import { deriveWarrantyEnd, warrantyRemainingText, warrantyStatusLabel } from "../../utils/warranty";
import { formatDateValue, formatTimeValue, todayIso } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { formatProductPrimaryName } from "../../utils/productDisplayName";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { warrantyPillClass } from "./warrantyStatus";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";
import { orphanDraftsBannerText } from "../../utils/documentDraft";

/**
 * THA-24 م2 — بطاقة كفالة واحدة: إنشاء يدوية، تعديل، تمديد، حذف.
 *
 * **البطاقة التلقائية ليست وثيقةً بشرية**: أنشأها ترحيل فاتورة البيع من وحدة
 * مُرقَّمة بعينها، فتعديل نسبها باليد يجعلها تكذب على فاتورتها. الخادم يقصر
 * التعديل عليها على تاريخ الانتهاء والملاحظات وكفالة المورد؛ هنا تُعطَّل بقية
 * الحقول كي لا يكتشف المستخدم القاعدة برسالة خطأ بعد أن يملأ نموذجاً.
 *
 * الحالة (سارية/منتهية) لا تُدخَل ولا تُحفَظ — يحسبها الخادم من تاريخ الانتهاء
 * عند كل قراءة، ونحن نعرضها.
 */

interface ProductOption {
  id: number;
  display_name?: string;
  name_ar?: string;
  name_en?: string;
  sku?: string;
  warranty_months?: number | null;
  supplier_warranty_months?: number | null;
}

interface PartnerOption {
  id: number;
  name: string;
  phone?: string;
}

interface Props {
  /** بطاقة قائمة للعرض والتعديل، أو `null` لبطاقة يدوية جديدة. */
  card: WarrantyCardRow | null;
  canManage: boolean;
  products: ProductOption[];
  customers: PartnerOption[];
  suppliers: PartnerOption[];
  onClose: () => void;
  /** يُنادى بعد كل تغيير فعلي كي تُعيد الشاشة تحميل الجدول. */
  onChanged: () => void;
}

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const fieldClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] " +
  "disabled:opacity-60";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const emptyDraft = (): WarrantyCardDraft => ({
  product: null,
  device_name: "",
  serial: "",
  partner: null,
  customer_name: "",
  customer_phone: "",
  start_date: todayIso(),
  duration_months: null,
  end_date: null,
  supplier: null,
  supplier_warranty_end_date: null,
  notes: "",
});

const draftOf = (card: WarrantyCardRow): WarrantyCardDraft => ({
  product: card.product,
  device_name: card.device_name,
  serial: card.serial,
  partner: card.partner,
  customer_name: card.customer_name,
  customer_phone: card.customer_phone,
  start_date: card.start_date,
  duration_months: card.duration_months || null,
  end_date: card.end_date,
  supplier: card.supplier,
  supplier_warranty_end_date: card.supplier_warranty_end_date,
  notes: card.notes,
});

export const WarrantyCardModal: React.FC<Props> = ({
  card, canManage, products, customers, suppliers, onClose, onChanged,
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [draft, setDraft] = useState<WarrantyCardDraft>(() =>
    card ? draftOf(card) : emptyDraft());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [extendMonths, setExtendMonths] = useState("");
  const [extendReason, setExtendReason] = useState("");

  /* ISSUE #121: مسودّة محلية (IndexedDB) — «لُمِس» يُرفَع مزامنةً داخل كل
   * معالج تعديلٍ حقيقي (patch/pickProduct/pickCustomer وحقول التمديد)، لا
   * داخل useEffect مبنيٍّ على الحمولة. لا تُرفع عند التعبئة البرمجية من
   * `card` (الأسفل) ولا عند الاستعادة الناجحة (تُرفع صراحةً هناك). */
  const [touched, setTouched] = useState(false);

  /* بطاقتان يُعاد فيهما ضبط `draft`/`extendMonths`/`extendReason` تلقائياً
   * لا بفعل المستخدم: (١) تغيّر `card` (بطاقة أخرى، أو نفس البطاقة بمرجعٍ
   * جديد بعد `onChanged()`)، و(٢) نجاح `extend()` الذي يُصفّر حقول التمديد
   * ويحدّث `draft` من نسخة الخادم. الحارس هنا يحمي الأولى فقط: قراءة
   * المسودّة من IndexedDB غيرُ متزامنة، فلو تغيّر مرجع `card` (تحديثٌ خلفي في
   * القائمة) بعد استعادةٍ ناجحة، يمحو هذا الأثر مسودّةً استُعيدت للتوّ. مرّةً
   * واحدة لكل استعادة — راجع `AccountingJournalEntryPage.tsx` (issue #121). */
  const draftRestoredRef = useRef(false);

  useEffect(() => {
    if (draftRestoredRef.current) {
      draftRestoredRef.current = false;
      return;
    }
    setDraft(card ? draftOf(card) : emptyDraft());
    setExtendMonths("");
    setExtendReason("");
    setErr(null);
    // تعبئةٌ من الخادم — لا تُعامَل كتعديل مستخدم (issue #121).
    setTouched(false);
  }, [card]);

  const isAuto = card?.source === "auto_sale";
  // البطاقة التلقائية: النسب والزبون والمنتج من الفاتورة، لا يُحرَّرون هنا.
  const lineageLocked = isAuto || !canManage;

  const patch = <K extends keyof WarrantyCardDraft>(key: K, value: WarrantyCardDraft[K]) => {
    setTouched(true);
    setDraft((d) => ({ ...d, [key]: value }));
  };

  /** اختيار المنتج يجلب سياسته: المدة الفارغة تُملأ منها، والمملوءة لا تُداس. */
  const pickProduct = (productId: number | null) => {
    setTouched(true);
    const product = products.find((p) => p.id === productId);
    setDraft((d) => ({
      ...d,
      product: productId,
      duration_months:
        d.duration_months || (product?.warranty_months ?? null) || null,
    }));
  };

  /** اختيار الزبون يلتقط اسمه وهاتفه لقطةً — البطاقة وثيقة لحظتها. */
  const pickCustomer = (partnerId: number | null) => {
    setTouched(true);
    const partner = customers.find((p) => p.id === partnerId);
    setDraft((d) => ({
      ...d,
      partner: partnerId,
      customer_name: partner ? partner.name : d.customer_name,
      customer_phone: partner?.phone || d.customer_phone,
    }));
  };

  const previewEnd = useMemo(
    () => deriveWarrantyEnd(draft.start_date, draft.duration_months, draft.end_date),
    [draft.start_date, draft.duration_months, draft.end_date],
  );

  const problems = useMemo(() => {
    const list: string[] = [];
    if (!draft.serial.trim() && !draft.device_name.trim() && !draft.product) {
      list.push("حدّد الرقم التسلسلي أو اسم الجهاز أو المنتج");
    }
    if (!draft.start_date) list.push("تاريخ بدء الكفالة مطلوب");
    if (!draft.duration_months && !previewEnd) {
      list.push("حدّد مدة الكفالة بالأشهر أو تاريخ انتهائها");
    }
    if (previewEnd && draft.start_date && previewEnd < draft.start_date) {
      list.push("تاريخ الانتهاء قبل تاريخ البدء");
    }
    return list;
  }, [draft, previewEnd]);

  /* ── ISSUE #121: مسودّة محلية (IndexedDB) — بطاقة الكفالة لا تحفظ شيئاً
   * محلياً اليوم. الحمولة كائنٌ خفيف يكفي وحده لإعادة بناء الشاشة (`draft` +
   * حقول تمديدٍ لم تُرسَل بعد) — لا صلة بحمولة الحفظ الخادمية التي يبنيها
   * `save`/`extend` بنفسيهما. حقلا التمديد (`extendMonths`/`extendReason`)
   * إدخال مستخدمٍ حقيقي مثل `draft` تماماً، فيدخلان الحمولة معه. */
  const draftPayload = useMemo(
    () => ({ draft, extendMonths, extendReason }),
    [draft, extendMonths, extendReason],
  );

  const onRestoreDraft = useCallback(
    (restored: { draft: WarrantyCardDraft; extendMonths: string; extendReason: string }) => {
      setDraft(restored.draft);
      setExtendMonths(restored.extendMonths);
      setExtendReason(restored.extendReason);
      // استعادةٌ من مسودّة تعني اختلافاً عن آخر نسخة محفوظة — تُسجَّل «ملموسة»
      // فوراً كي يبقى الحارس وسياسة الحفظ متّسقين مع ما يراه المستخدم فعلاً.
      setTouched(true);
      draftRestoredRef.current = true;
    },
    [],
  );

  const {
    draftSavedAt,
    draftSaveFailed,
    restoredBanner: draftBanner,
    discardDraft,
    orphanDrafts,
  } = useDocumentDraft<{ draft: WarrantyCardDraft; extendMonths: string; extendReason: string }>({
    docType: "warranty_card",
    docId: card?.id ?? null,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    // لا مفهوم «ترحيل» محاسبي على هذه الشاشة، لكن `!canManage` تُقفل كل
    // الحقول فعلياً (الحفظ والحذف والتمديد كلّها مشروطة بها) فتصير هي الحالة
    // «عرضٌ فقط» التي يعنيها العقد — شريط اطّلاعٍ بلا استعادةٍ تلقائية.
    isPosted: !canManage,
    docUpdatedAt: card?.updated_at ?? null,
  });

  /* ISSUE #120: الحارسُ مقلوب — يعترض المغادرةَ فقط إن فشل الحفظُ المحلّيّ فعلاً. */
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (draftSaveFailed) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [draftSaveFailed]);

  /** شريط اليتامى (issue #119 §٧) — إخفاءٌ محليّ بلا مسّ المسودّات نفسها. */
  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);

  /** «تراجع» على شريط الاستعادة: يعيد البطاقة إلى نسختها المحفوظة ويمسح المسودّة. */
  const handleUndoDraft = useCallback(() => {
    setDraft(card ? draftOf(card) : emptyDraft());
    setExtendMonths("");
    setExtendReason("");
    setTouched(false);
    void discardDraft();
  }, [card, discardDraft]);

  const save = async () => {
    if (problems.length > 0) {
      setErr(problems.join(" · "));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const payload: WarrantyCardDraft = {
        ...draft,
        device_name: draft.device_name.trim(),
        serial: draft.serial.trim(),
        customer_name: draft.customer_name.trim(),
        customer_phone: draft.customer_phone.trim(),
        // ما كتبه المستخدم بيده وحده يُرسَل. المعاينة المشتقّة (`previewEnd`)
        // تبقى معاينة: إرسالها كان يجعل الواجهة مؤلّفةً ثانيةً لتاريخٍ الخادمُ
        // مؤلّفه — تتفق القاعدتان اليوم، وأول انحراف بينهما يمرّ صامتاً.
        end_date: draft.end_date || null,
      };
      if (card) {
        // التلقائية: لا نرسل إلا ما يقبله الخادم عليها، فلا نصطدم بحارسه.
        await updateWarrantyCard(
          card.id,
          isAuto
            ? {
                end_date: payload.end_date,
                supplier_warranty_end_date: payload.supplier_warranty_end_date,
                notes: payload.notes,
              }
            : payload,
        );
        toast("تم حفظ بطاقة الكفالة", "success");
      } else {
        await createWarrantyCard(payload);
        toast("تم إنشاء بطاقة كفالة يدوية", "success");
      }
      setTouched(false);
      // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      void discardDraft();
      onChanged();
      onClose();
    } catch (e) {
      setErr(messageOf(e, "تعذّر حفظ البطاقة"));
    } finally {
      setBusy(false);
    }
  };

  const extend = async () => {
    if (!card) return;
    const months = Number(extendMonths);
    if (!Number.isFinite(months) || months <= 0) {
      setErr("حدّد عدد الأشهر المضافة (رقم أكبر من صفر)");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const saved = await extendWarrantyCard(card.id, {
        months,
        reason: extendReason.trim() || undefined,
      });
      setDraft(draftOf(saved));
      setExtendMonths("");
      setExtendReason("");
      setTouched(false);
      // التمديد تغييرٌ فعليٌّ مرحَّلٌ على نفس البطاقة — انتهت وظيفة المسودّة
      // المحلية هنا تماماً كنجاح `save` (issue #118 §٥)، لا إعادة ضبطٍ خلفية.
      void discardDraft();
      toast(`تم التمديد حتى ${formatDateValue(saved.end_date)}`, "success");
      onChanged();
    } catch (e) {
      setErr(messageOf(e, "تعذّر تمديد الكفالة"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!card) return;
    const ok = await confirm({
      title: "حذف بطاقة الكفالة",
      message: `ستُحذف بطاقة «${card.serial || card.device_name || card.product_name}» نهائياً. البطاقات التلقائية لا تُحذف هكذا — تُحذف مع التراجع عن ترحيل فاتورتها.`,
      confirmText: "حذف البطاقة",
      cancelText: "تراجع",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await deleteWarrantyCard(card.id);
      toast("تم حذف البطاقة", "success");
      onChanged();
      onClose();
    } catch (e) {
      setErr(messageOf(e, "تعذّر حذف البطاقة"));
      setBusy(false);
    }
  };

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label={card ? "بطاقة كفالة" : "بطاقة كفالة يدوية جديدة"}
      className="fixed inset-0 z-[70] flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
    >
      <div className="w-full max-w-3xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
          <div className="flex min-w-0 items-center gap-2">
            <ShieldCheck className="h-5 w-5 shrink-0 text-[var(--color-primary)]" />
            <span className="truncate font-bold text-[var(--color-text)]">
              {card
                ? `${card.serial || card.device_name || card.product_name} — ${card.source_label}`
                : "بطاقة كفالة يدوية جديدة"}
            </span>
            {card && (
              <span className={warrantyPillClass(card.status, card.days_remaining)}>
                {warrantyStatusLabel(card.status)}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="إغلاق"
            aria-label="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ISSUE #120: الحفظ المحلي فشل فعلاً — لافتةٌ لاصقة تطلب حفظاً يدوياً.
         * لا تُعرض على بطاقةٍ عرضٍ فقط (`!canManage` ⇒ `isPosted`): لا زر «حفظ»
         * فيها أصلاً يمكن الضغط عليه. */}
        {draftSaveFailed && canManage && (
          <div
            role="alert"
            aria-live="assertive"
            data-testid="draft-save-failed-banner"
            className="sticky top-0 z-40 flex items-center gap-2 border-b border-red-200 bg-red-100 px-4 py-2 text-sm font-medium text-red-800"
          >
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>تعذّر حفظ نسخة محلية من هذا المستند — اضغط «حفظ» يدوياً كي لا يضيع عملك.</span>
          </div>
        )}

        {/* ISSUE #118: شريط الاستعادة التلقائية — بلا لافتة تسأل. المحتوى
         * مُطبَّقٌ على النموذج فعلاً (`onRestoreDraft`) قبل أن يصل هذا الشريط أصلاً. */}
        {draftBanner && (
          <div className="ktra-banner ktra-banner--warn" role="status" data-testid="draft-restored-banner">
            <Info className="h-4 w-4 shrink-0" />
            <span>
              {draftBanner.eligibility === "restore" &&
                `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(draftBanner.updatedAt)})`}
              {draftBanner.eligibility === "stale" &&
                `تغيّر المستند بعد مسودتك (مسودتُك ${formatTimeValue(draftBanner.updatedAt)})`}
              {draftBanner.eligibility === "posted" &&
                `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(draftBanner.updatedAt)}) لهذا المستند المرحَّل — للاطّلاع فقط.`}
            </span>
            {draftBanner.eligibility === "restore" && (
              <button type="button" className="ktra-toolbtn" onClick={handleUndoDraft} data-testid="draft-restored-undo">
                <Undo2 className="h-4 w-4" /> تراجع
              </button>
            )}
            {draftBanner.eligibility === "stale" && (
              <>
                <button type="button" className="ktra-toolbtn" onClick={() => onRestoreDraft(draftBanner.payload)} data-testid="draft-stale-preview">استعرض مسودتي</button>
                <button type="button" className="ktra-toolbtn" onClick={() => void discardDraft()} data-testid="draft-stale-discard">تجاهلها</button>
              </>
            )}
          </div>
        )}

        {/* شريط اليتامى (issue #119 §٧) — فقط على بطاقةٍ جديدة (`docId` فارغ). */}
        {!card && orphanDrafts.length > 0 && !orphanBarDismissed && (
          <div className="ktra-banner" role="status" data-testid="orphan-drafts-banner">
            <Info className="h-4 w-4 shrink-0" />
            <div className="flex flex-col gap-1">
              <span>{orphanDraftsBannerText(orphanDrafts.length)}</span>
              <ul className="list-disc pr-4 text-xs">
                {orphanDrafts.map((o) => <li key={o.key}>{formatTimeValue(o.updatedAt)} — {o.previewLine || "—"}</li>)}
              </ul>
            </div>
            <button type="button" className="ktra-toolbtn" onClick={() => setOrphanBarDismissed(true)} data-testid="orphan-drafts-dismiss">
              <X className="h-4 w-4" /> إخفاء
            </button>
          </div>
        )}

        <div className="space-y-4 p-3 md:p-4">
          {err && (
            <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          )}

          {isAuto && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-[var(--color-text-muted)]">
              بطاقة تلقائية من ترحيل فاتورة البيع
              {card?.sales_invoice_number ? ` ${card.sales_invoice_number}` : ""} — يُعدَّل
              عليها تاريخ الانتهاء والملاحظات وكفالة المورد فقط. لتغيير الباقي: تراجع عن
              ترحيل الفاتورة.
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className={labelClass} htmlFor="warranty-product">المنتج</label>
              <select
                id="warranty-product"
                className={fieldClass}
                disabled={lineageLocked}
                value={draft.product ?? ""}
                onChange={(e) => pickProduct(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— بلا منتج من المخزون —</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>{formatProductPrimaryName(p)}</option>
                ))}
              </select>
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-device-name">اسم الجهاز (لجهازٍ لم نبعه)</label>
              <input
                id="warranty-device-name"
                className={fieldClass}
                disabled={lineageLocked}
                value={draft.device_name}
                onChange={(e) => patch("device_name", e.target.value)}
                placeholder="اسم الجهاز أو وصفه"
              />
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-serial">الرقم التسلسلي</label>
              <input
                id="warranty-serial"
                className={fieldClass}
                autoComplete="off"
                disabled={lineageLocked}
                value={draft.serial}
                onChange={(e) => patch("serial", e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }}
                placeholder="امسح الباركود أو اكتب الرقم"
              />
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-partner">الزبون</label>
              <select
                id="warranty-partner"
                className={fieldClass}
                disabled={lineageLocked}
                value={draft.partner ?? ""}
                onChange={(e) => pickCustomer(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— زبون غير مسجَّل —</option>
                {customers.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-customer-name">اسم الزبون (لقطة)</label>
              <input
                id="warranty-customer-name"
                className={fieldClass}
                disabled={lineageLocked}
                value={draft.customer_name}
                onChange={(e) => patch("customer_name", e.target.value)}
              />
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-customer-phone">هاتف الزبون</label>
              <input
                id="warranty-customer-phone"
                className={fieldClass}
                inputMode="tel"
                disabled={lineageLocked}
                value={draft.customer_phone}
                onChange={(e) => patch("customer_phone", e.target.value)}
              />
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-start">بداية الكفالة</label>
              <input
                id="warranty-start"
                type="date"
                className={fieldClass}
                disabled={lineageLocked}
                value={draft.start_date}
                onChange={(e) => patch("start_date", e.target.value)}
              />
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-months">المدة (أشهر)</label>
              <input
                id="warranty-months"
                type="number"
                min="0"
                max="600"
                className={fieldClass}
                disabled={lineageLocked}
                value={draft.duration_months ?? ""}
                onChange={(e) => {
                  setTouched(true);
                  const months = e.target.value ? Number(e.target.value) : null;
                  // المدة تُعيد اشتقاق النهاية على البطاقة اليدوية: من غيّر المدة
                  // يقصد نهايةً جديدة، وإبقاء القديمة يجعل الحقلين يتناقضان.
                  setDraft((d) => ({ ...d, duration_months: months, end_date: null }));
                }}
              />
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-end">نهاية الكفالة</label>
              <input
                id="warranty-end"
                type="date"
                className={fieldClass}
                disabled={!canManage}
                value={draft.end_date || previewEnd}
                onChange={(e) => patch("end_date", e.target.value || null)}
              />
              {!draft.end_date && previewEnd && (
                <span className="mt-1 block text-[11px] text-[var(--color-text-muted)]">
                  مشتقّ من المدة: {formatDateValue(previewEnd)}
                </span>
              )}
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-supplier">المورد</label>
              <select
                id="warranty-supplier"
                className={fieldClass}
                disabled={!canManage}
                value={draft.supplier ?? ""}
                onChange={(e) => patch("supplier", e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— بلا مورد —</option>
                {suppliers.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className={labelClass} htmlFor="warranty-supplier-end">نهاية كفالة المورد لنا</label>
              <input
                id="warranty-supplier-end"
                type="date"
                className={fieldClass}
                disabled={!canManage}
                value={draft.supplier_warranty_end_date || ""}
                onChange={(e) => patch("supplier_warranty_end_date", e.target.value || null)}
              />
              {card?.supplier_warranty_active && (
                <span className="mt-1 block text-[11px] text-emerald-700 dark:text-emerald-400">
                  ما زالت بكفالة المورد — لا تتحمّل الشركة كلفة إصلاحها.
                </span>
              )}
            </div>

            <div className="sm:col-span-2 lg:col-span-3">
              <label className={labelClass} htmlFor="warranty-notes">الملاحظات</label>
              <textarea
                id="warranty-notes"
                rows={3}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-sm text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60"
                disabled={!canManage}
                value={draft.notes}
                onChange={(e) => patch("notes", e.target.value)}
              />
            </div>
          </div>

          {card && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-[var(--color-text)]">
                <CalendarPlus className="h-4 w-4 text-[var(--color-primary)]" />
                <span className="font-bold">تمديد الكفالة مجاملةً</span>
                <span className="text-[11px] text-[var(--color-text-muted)]">
                  تنتهي {formatDateValue(card.end_date)} · {warrantyRemainingText(card.status, card.days_remaining)}
                </span>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  className={`${fieldClass} sm:w-40`}
                  type="number"
                  min="1"
                  max="600"
                  disabled={!canManage || busy}
                  placeholder="أشهر تُضاف"
                  aria-label="عدد الأشهر المضافة"
                  value={extendMonths}
                  onChange={(e) => { setTouched(true); setExtendMonths(e.target.value); }}
                />
                <input
                  className={`${fieldClass} flex-1`}
                  disabled={!canManage || busy}
                  placeholder="سبب التمديد (يُوثَّق في الملاحظات)"
                  aria-label="سبب التمديد"
                  value={extendReason}
                  onChange={(e) => { setTouched(true); setExtendReason(e.target.value); }}
                />
                <button
                  type="button"
                  onClick={() => void extend()}
                  disabled={!canManage || busy || !extendMonths}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-bold text-[var(--color-text)] hover:bg-[var(--color-surface-3)] disabled:opacity-50 sm:w-32"
                >
                  تمديد
                </button>
              </div>
              {extendMonths && Number(extendMonths) > 0 && (
                <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                  ستنتهي بعد التمديد في{" "}
                  {formatDateValue(deriveWarrantyEnd(card.end_date, Number(extendMonths)))}
                  {" "}({formatNumber(Number(extendMonths))} شهراً)
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-[var(--color-border)] p-3 sm:flex-row sm:items-center">
          {draftSavedAt && (
            <span className="ktra-status-item sm:me-auto" data-testid="draft-saved-indicator">
              مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
            </span>
          )}
          {card && !isAuto && canManage && (
            <button
              type="button"
              onClick={() => void remove()}
              disabled={busy}
              className="inline-flex items-center justify-center gap-1 rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/30 sm:w-40"
            >
              <Trash2 className="h-4 w-4" /> حذف
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50 sm:w-32"
          >
            إغلاق
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={!canManage || busy}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            حفظ
          </button>
        </div>
      </div>
    </div>
  );
};

export default WarrantyCardModal;
