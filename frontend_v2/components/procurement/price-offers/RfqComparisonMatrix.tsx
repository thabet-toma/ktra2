/**
 * ISSUE #116 (مواصفة #108 §٨) — مصفوفة الموردين: شاشةٌ مستقلّة تُفتح عند
 * الطلب، صفٌّ لكل بند وعمودٌ لكل موردٍ ردّ فعلياً. **لا تُفرَض على شاشة
 * الطلبية اليومية** (`PurchaseRFQForm.tsx`) — تنكسر أفقياً وتُثقل ما يُستعمل
 * كلَّ يوم؛ زرٌّ في شريطها يفتحها فوق الشاشة كطبقةٍ كاملة.
 *
 * **ثلاثة أعمدة مثبَّتة أفقياً** (الصنف · الكمية · السعر التقديريّ) — بـ
 * `sticky` و`start-*` (المنطقيّ لا `left`) على نمط `AttendancePage.tsx`،
 * فلا ينقلب الاتجاه في RTL (درس `T-WIN`: `left/right` الخام يحتاج قلب إشارة
 * يدوياً، بينما `inset-inline-start` يحسمه المتصفح).
 *
 * **خطُّ الأساس هنا التقديريّ لا «أقل سعر»** — الفرق عن عمود العرض الواحد
 * (#113) مقصود: هناك تُحاكَم المورّد إلى تاريخك، وهنا تُحاكَم الموردين إلى
 * هدفك. النسبة المئوية الملوّنة تُحسب هنا بنفس الدالّة النقيّة المُختبَرة
 * (`computeDeltaPercent`, #113) — لا نسخة ثانية من القاعدة: تُعيد `null`
 * بلا سعرٍ تقديريّ (أو بتقديريّ صفر)، فيُعرض سعر المورد **عارياً بلا نسبة
 * ولا لون** — مقارنةٌ مُختلَقة أسوأ من غيابها.
 *
 * بندٌ لم يُسعَّر (لا تقديريّ) أو لم يُسعّره موردٌ بعينه يُعرَض **فارغاً لا
 * صفراً** («—»). الإجمالي المعروض لكل مورد **البضاعة وحدها** —
 * `goods_total_base` من الخادم، ولا حقل شحنٍ في الاستجابة أصلاً.
 *
 * **ISSUE #133 غ٣ (مواصفة #130 §١):** نصّ المورّد (`notes`) وتعليقُنا
 * الداخليّ (`internal_notes`) يظهران معاً في كلّ خليّة — منفصلَين بصرياً
 * ونصّاً («المورّد:» مقابل تعليقٍ بلا بادئة، بكاتبه وتاريخه) لا مدموجَين:
 * دمجُهما هو بعينه محو الأصل الذي بُني السكيمة لمنعه. نصّ المورّد **للقراءة
 * فقط** هنا كما في كل سطحٍ آخر؛ التعليق يُكتب من هذه الشاشة عبر
 * `setSupplierQuotationLineInternalNote` — لا عبر محرّر العروض
 * (`PriceOfferForm.tsx`، الذي يحذف السطور ويعيد إنشاءها عند كل حفظ، فهو
 * أخطر نقطةٍ ممكنةٍ لحقلٍ يُراد له أن يبقى مربوطاً بسطره). **`PriceOfferForm
 * .tsx` لا يعرض أياً من الملاحظتين اليوم** — فجوةٌ معروفة ومؤجَّلة عمداً، لا
 * سهواً.
 */
import React, { useEffect, useState } from "react";
import { X, Loader2, AlertCircle, Award, MessageSquare, Check } from "lucide-react";
import {
  awardPurchaseRfq,
  getRfqComparison,
  setSupplierQuotationLineInternalNote,
  type PurchaseRFQAwardResult,
  type RfqComparisonDto,
  type SupplierQuotationEntrySource,
} from "../../../services/procurementDocumentsApi";
import { computeDeltaPercent } from "../../../utils/purchasePriceHint";
import { formatMoney, formatNumber } from "../../../utils/formatNumber";
import { useToast } from "../../../contexts/ToastContext";
import { useConfirm } from "../../../contexts/ConfirmContext";

interface Props {
  rfqId: number;
  rfqNumber: string | null;
  /** الترسية متاحة فقط لطلبيةٍ ما زالت `sent` — استدعاءٌ من `PurchaseRFQForm`. */
  canAward: boolean;
  /**
   * ISSUE #133 غ١ (قرار المالك 2026-09-04): بالاستيراد الترسية تقبل العرض
   * وتُغلق الطلبية عليه فقط — التحويل إلى صفقة خطوةٌ لاحقة منفصلة؛ بالشراء
   * المحلّي تُنتَج فاتورة أو أمر شراء فوراً. الفرق يصل هنا **مسمّىً بغرضه**
   * من `PurchaseRFQForm` (حيث النطاق معروف) لا فحصَ نطاقٍ ضمنياً هنا.
   */
  awardStopsAtAcceptedOffer: boolean;
  onClose: () => void;
  onAwarded: (result: PurchaseRFQAwardResult) => void;
}

/** ISSUE #122: من كتب أسعار هذا العمود — نصّاً لا لوناً وحده. */
const ENTRY_SOURCE_LABELS: Record<SupplierQuotationEntrySource, string> = {
  supplier_link: "سعّره بنفسه",
  manual: "أُدخل عنه",
};

const ENTRY_SOURCE_BADGE_CLASS: Record<SupplierQuotationEntrySource, string> = {
  supplier_link: "rounded-full border border-emerald-300 bg-emerald-50 px-1.5 py-px text-[9px] font-medium text-emerald-800",
  manual: "rounded-full border border-amber-300 bg-amber-50 px-1.5 py-px text-[9px] font-medium text-amber-800",
};

const SUPPLIER_COL_WIDTH = 190;
const FROZEN_WIDTHS = { product: 220, quantity: 90, estimated: 150 };
const FROZEN_STARTS = {
  product: 0,
  quantity: FROZEN_WIDTHS.product,
  estimated: FROZEN_WIDTHS.product + FROZEN_WIDTHS.quantity,
};

/** ISSUE #133 غ٣: مفتاح خليّة التعليق الداخليّ — مورّدٌ × بند. */
const internalNoteKey = (supplierId: number, lineId: number) => `${supplierId}:${lineId}`;

export const RfqComparisonMatrix: React.FC<Props> = ({
  rfqId, rfqNumber, canAward, awardStopsAtAcceptedOffer, onClose, onAwarded,
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [data, setData] = useState<RfqComparisonDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [awardingSupplierId, setAwardingSupplierId] = useState<number | null>(null);
  // ISSUE #133 غ٣: خليّة التعليق الداخليّ التي تُحرَّر الآن، ومسوَّدتها.
  const [editingNoteKey, setEditingNoteKey] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [savingNoteKey, setSavingNoteKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getRfqComparison(rfqId)
      .then((res) => { if (!cancelled) setData(res); })
      .catch((e: unknown) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "تعذّر تحميل المقارنة");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rfqId]);

  const handleAward = async (supplierId: number, supplierName: string) => {
    const ok = await confirm({
      title: "ترسية الطلبية",
      message: awardStopsAtAcceptedOffer
        ? `سيُقبَل عرض «${supplierName}» وتُغلَق الطلبية عليه. لا فاتورة ولا أمر شراء الآن — حوّل العرض المقبول إلى صفقة استيراد من شاشة العروض متى جهّزت الشحن. لا يمكن التراجع بعد الترسية.`
        : `سيتمّ إرساء كامل الطلبية على «${supplierName}» — تُنتَج فاتورة أو أمر شراء بحسب إعدادات الشراء. لا يمكن التراجع بعد الترسية.`,
      confirmText: "ترسية",
      danger: false,
    });
    if (!ok) return;
    setAwardingSupplierId(supplierId);
    try {
      const result = await awardPurchaseRfq(rfqId, supplierId);
      toast(
        awardStopsAtAcceptedOffer
          ? `قُبل عرض ${supplierName} — حوّله إلى صفقة استيراد متى جهّزت.`
          : `تمّت ترسية الطلبية على ${supplierName}.`,
        "success",
      );
      onAwarded(result);
      onClose();
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "تعذّرت الترسية", "error");
    } finally {
      setAwardingSupplierId(null);
    }
  };

  /**
   * ISSUE #133 غ٣: يحفظ تعليقنا على سطرٍ بعينه من عرض مورّدٍ بعينه — سطرٌ
   * واحدٌ فقط، لا يمسّ نصّ المورّد ولا بقية سطور العرض. يُحدِّث الحالة
   * محلياً بعد النجاح بدل إعادة تحميل المصفوفة كاملةً.
   */
  const handleSaveInternalNote = async (
    supplierId: number,
    lineId: number,
    quotationId: number,
    quotationLineId: number,
  ) => {
    const key = internalNoteKey(supplierId, lineId);
    setSavingNoteKey(key);
    try {
      const saved = await setSupplierQuotationLineInternalNote(
        quotationId, quotationLineId, noteDraft.trim(),
      );
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          suppliers: prev.suppliers.map((s) => (
            s.supplier_id !== supplierId ? s : {
              ...s,
              internal_notes: {
                ...s.internal_notes,
                [String(lineId)]: {
                  text: saved.internal_note ?? "",
                  by: saved.internal_note_by_name ?? "",
                  at: saved.internal_note_at ?? null,
                },
              },
            }
          )),
        };
      });
      setEditingNoteKey(null);
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "تعذّر حفظ التعليق", "error");
    } finally {
      setSavingNoteKey(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex flex-col ktra-bg-field">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
        <h2 className="text-sm font-semibold">
          مقارنة الموردين {rfqNumber ? `— ${rfqNumber}` : ""}
        </h2>
        <button type="button" className="ktra-iconbtn" onClick={onClose} aria-label="إغلاق">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-3">
        {loading && (
          <div className="flex items-center justify-center gap-2 py-16 ktra-text-soft">
            <Loader2 className="h-5 w-5 animate-spin" /> جارٍ تحميل المقارنة…
          </div>
        )}
        {err && !loading && (
          <div className="ktra-banner ktra-banner--err">
            <AlertCircle className="h-4 w-4 shrink-0" /> <span>{err}</span>
          </div>
        )}
        {!loading && !err && data && (
          data.suppliers.length === 0 ? (
            <p className="ktra-hint py-8 text-center">لا عروض وصلت بعد لهذه الطلبية.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
              <table className="text-xs" style={{ borderCollapse: "separate" }}>
                <thead>
                  <tr className="bg-[var(--color-surface-2)] text-[var(--color-text-muted)]">
                    <th
                      className="sticky z-10 border-e border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-start"
                      style={{ insetInlineStart: FROZEN_STARTS.product, width: FROZEN_WIDTHS.product, minWidth: FROZEN_WIDTHS.product }}
                    >
                      الصنف
                    </th>
                    <th
                      className="sticky z-10 border-e border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-center"
                      style={{ insetInlineStart: FROZEN_STARTS.quantity, width: FROZEN_WIDTHS.quantity, minWidth: FROZEN_WIDTHS.quantity }}
                    >
                      الكمية
                    </th>
                    <th
                      className="sticky z-10 border-e-2 border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-center"
                      style={{ insetInlineStart: FROZEN_STARTS.estimated, width: FROZEN_WIDTHS.estimated, minWidth: FROZEN_WIDTHS.estimated, boxShadow: "2px 0 4px -2px rgba(0,0,0,.15)" }}
                    >
                      السعر التقديري
                    </th>
                    {data.suppliers.map((s) => (
                      <th key={s.supplier_id} className="p-2 text-center" style={{ width: SUPPLIER_COL_WIDTH, minWidth: SUPPLIER_COL_WIDTH }}>
                        <div className="flex flex-col items-center gap-1">
                          <span className="font-semibold">{s.supplier_name}</span>
                          <span className="ktra-text-soft text-[10px]">
                            {s.currency_code} · {s.quotation_number}
                          </span>
                          {/* ISSUE #122: عمودٌ سعّره المورّد بنفسه وعمودٌ أدخلناه عنه
                              ليسا سواءً في الثقة — شارةٌ عرضيّةٌ صرف بلا أيّ حساب.
                              حقلٌ اختياريّ: خادمٌ لا يرسله لا يُظهر شارةً كاذبة. */}
                          {s.entry_source && (
                            <span className={ENTRY_SOURCE_BADGE_CLASS[s.entry_source]}>
                              {ENTRY_SOURCE_LABELS[s.entry_source]}
                            </span>
                          )}
                          {/* ISSUE #133 غ٣: ملاحظته العامة على الطلبية كلّها —
                              «هذا ما عندي بدل ما طلبت» على مستوى الطلبية لا سطر. */}
                          {s.general_note && (
                            <span
                              className="max-w-full truncate text-[10px] italic ktra-text-soft"
                              title={s.general_note}
                            >
                              «{s.general_note}»
                            </span>
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.lines.map((line) => {
                    const estimated = line.estimated_price != null ? Number(line.estimated_price) : null;
                    return (
                      <tr key={line.id} className="border-t border-[var(--color-border)]">
                        <td
                          className="sticky z-10 border-e border-[var(--color-border)] bg-[var(--color-surface)] p-2"
                          style={{ insetInlineStart: FROZEN_STARTS.product, width: FROZEN_WIDTHS.product, minWidth: FROZEN_WIDTHS.product }}
                        >
                          {line.name}
                        </td>
                        <td
                          className="sticky z-10 border-e border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-center"
                          style={{ insetInlineStart: FROZEN_STARTS.quantity, width: FROZEN_WIDTHS.quantity, minWidth: FROZEN_WIDTHS.quantity }}
                        >
                          {formatNumber(line.quantity)} {line.unit_of_measure}
                        </td>
                        <td
                          className="sticky z-10 border-e-2 border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-center"
                          style={{ insetInlineStart: FROZEN_STARTS.estimated, width: FROZEN_WIDTHS.estimated, minWidth: FROZEN_WIDTHS.estimated, boxShadow: "2px 0 4px -2px rgba(0,0,0,.15)" }}
                        >
                          {estimated != null ? formatMoney(estimated) : <span className="ktra-text-soft">—</span>}
                        </td>
                        {data.suppliers.map((s) => {
                          const raw = s.prices[String(line.id)];
                          const price = raw != null ? Number(raw) : null;
                          const delta = price != null ? computeDeltaPercent(price, estimated) : null;
                          // ISSUE #133 غ٣: ملاحظته على هذا البند تحديداً —
                          // «هذا ما عندي بدل ما طلبت» على مستوى السطر.
                          const note = s.notes?.[String(line.id)];
                          const internal = s.internal_notes?.[String(line.id)] ?? null;
                          const quotationLineId = s.quotation_line_ids?.[String(line.id)];
                          const noteKey = internalNoteKey(s.supplier_id, line.id);
                          const isEditing = editingNoteKey === noteKey;
                          const isSaving = savingNoteKey === noteKey;
                          return (
                            <td key={s.supplier_id} className="p-2 text-center">
                              {price == null ? (
                                <span className="ktra-text-soft">—</span>
                              ) : (
                                <div className="flex flex-col items-center leading-tight">
                                  <span>{formatMoney(price)}</span>
                                  {delta != null && (
                                    <span
                                      className="text-[10px] font-semibold"
                                      style={{ color: delta > 0 ? "var(--ktra-danger, #c00)" : "var(--ktra-ok, #267346)" }}
                                    >
                                      {delta > 0 ? "+" : ""}{formatNumber(delta, { maxDecimals: 1 })}%
                                    </span>
                                  )}
                                  {/* ISSUE #133 غ٣: نصّ المورّد نفسه — للقراءة
                                      فقط، ومنسوبٌ صراحةً له لا مدموجاً بتعليقنا. */}
                                  {note && (
                                    <span
                                      className="mt-0.5 max-w-full truncate text-[10px] italic ktra-text-soft"
                                      title={`المورّد: ${note}`}
                                    >
                                      المورّد: «{note}»
                                    </span>
                                  )}
                                  {/* تعليقنا الداخليّ — منفصلٌ بصرياً عن نصّ
                                      المورّد أعلاه، بكاتبه وتاريخه. */}
                                  {isEditing ? (
                                    <div className="mt-1 flex w-full max-w-[170px] flex-col items-stretch gap-1">
                                      <textarea
                                        className="w-full rounded border border-[var(--color-border)] p-1 text-[10px]"
                                        rows={2}
                                        value={noteDraft}
                                        autoFocus
                                        onChange={(e) => setNoteDraft(e.target.value)}
                                        placeholder="تعليقك الداخليّ…"
                                      />
                                      <div className="flex justify-center gap-1">
                                        <button
                                          type="button"
                                          className="ktra-iconbtn h-5 w-5"
                                          disabled={isSaving || quotationLineId == null}
                                          onClick={() => quotationLineId != null && void handleSaveInternalNote(
                                            s.supplier_id, line.id, s.quotation_id, quotationLineId,
                                          )}
                                          aria-label="حفظ التعليق"
                                        >
                                          {isSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                                        </button>
                                        <button
                                          type="button"
                                          className="ktra-iconbtn h-5 w-5"
                                          onClick={() => setEditingNoteKey(null)}
                                          aria-label="إلغاء"
                                        >
                                          <X className="h-3 w-3" />
                                        </button>
                                      </div>
                                    </div>
                                  ) : (
                                    <button
                                      type="button"
                                      className="mt-0.5 flex max-w-full items-center gap-1 truncate text-[10px] text-[var(--color-text-muted)] hover:underline"
                                      onClick={() => {
                                        setEditingNoteKey(noteKey);
                                        setNoteDraft(internal?.text ?? "");
                                      }}
                                      title={internal?.text ? `${internal.text} — ${internal.by || "—"}` : "أضف تعليقاً داخلياً"}
                                    >
                                      <MessageSquare className="h-2.5 w-2.5 shrink-0" />
                                      {internal?.text
                                        ? <span className="truncate">{internal.text}</span>
                                        : <span className="italic">أضف تعليقاً…</span>}
                                    </button>
                                  )}
                                </div>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-[var(--color-border)] bg-[var(--color-surface-2)] font-semibold">
                    <td
                      className="sticky z-10 border-e border-[var(--color-border)] bg-[var(--color-surface-2)] p-2"
                      style={{ insetInlineStart: FROZEN_STARTS.product, width: FROZEN_WIDTHS.product }}
                    >
                      إجماليّ البضاعة
                    </td>
                    <td
                      className="sticky z-10 border-e border-[var(--color-border)] bg-[var(--color-surface-2)] p-2"
                      style={{ insetInlineStart: FROZEN_STARTS.quantity, width: FROZEN_WIDTHS.quantity }}
                    />
                    <td
                      className="sticky z-10 border-e-2 border-[var(--color-border)] bg-[var(--color-surface-2)] p-2"
                      style={{ insetInlineStart: FROZEN_STARTS.estimated, width: FROZEN_WIDTHS.estimated, boxShadow: "2px 0 4px -2px rgba(0,0,0,.15)" }}
                    />
                    {data.suppliers.map((s) => (
                      <td key={s.supplier_id} className="p-2 text-center">
                        <div className="flex flex-col items-center gap-1.5">
                          <span>{formatMoney(s.goods_total_base)}</span>
                          {canAward && (
                            <button
                              type="button"
                              className="ktra-btn ktra-btn-primary gap-1 px-2 py-1 text-[11px]"
                              disabled={awardingSupplierId != null}
                              onClick={() => void handleAward(s.supplier_id, s.supplier_name)}
                            >
                              {awardingSupplierId === s.supplier_id
                                ? <Loader2 className="h-3 w-3 animate-spin" />
                                : <Award className="h-3 w-3" />}
                              ترسية
                            </button>
                          )}
                        </div>
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  );
};
