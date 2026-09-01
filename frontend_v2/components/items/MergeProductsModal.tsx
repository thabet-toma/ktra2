/**
 * #24: ضمّ منتجاتٍ محدَّدة تحت منتج واحد يختاره المستخدم صراحةً — لا اقتراح
 * آلي هنا إطلاقاً (لا تشابه أسماء، لا هدفٌ مُختار سلفاً). المعاينة (`buildMergePreview`،
 * `utils/productMerge.ts`) تُظهر قبل أي طلبٍ للخادم: من سينتقل، تحت أيّ منتج،
 * وأن أسماءهم ستُطبَّع على اسم الهدف (القرار المسجَّل على #24) — فلا مفاجآت
 * بعد التأكيد. الرفض معلَّلٌ لكل عضوٍ برفضه (وحدة القياس أو التتبّع التسلسلي
 * فقط — #13)، والمرفوضون لا يُرسَلون للخادم أصلاً.
 *
 * دلتا ٢: بعد أن يتوحّد الاسم، البراند وحده يميّز صفوف المنتج في المنتقي
 * («اسم المنتج (البراند)») — فحقل براندٍ لكل صفّ هنا (الهدف كأي عضوٍ آخر)،
 * مُعبَّأً بالبراند الحالي إن وُجد وفارغاً غير ذلك — **بلا أي تخمين**. تصادم
 * برانداتٍ (فراغين معاً أيضاً) يُعرَض تحذيراً (`findBrandCollisions`) لا منعاً:
 * البراند الفارغ مسموحٌ عمداً، يُسمَّى لاحقاً من كرت المنتج إن أراد المستخدم.
 */
import React, { useEffect, useMemo, useState } from "react";
import { X, Merge, AlertTriangle } from "lucide-react";
import { inventoryApi, type MergeProductsResult } from "../../services/inventoryApi";
import { useToast } from "../../contexts/ToastContext";
import { humanizeThrown } from "../../utils/drfError";
import { buildMergePreview, findBrandCollisions, type MergeCandidate } from "../../utils/productMerge";

export interface MergeProductsModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** المنتجات المُحدَّدة من الجدول — خامٌ يُشتقّ منه `MergeCandidate`. */
  candidates: MergeCandidate[];
  onMerged: (result: MergeProductsResult & { targetName: string }) => void;
}

export const MergeProductsModal: React.FC<MergeProductsModalProps> = ({
  isOpen, onClose, candidates, onMerged,
}) => {
  const toast = useToast();
  const [targetId, setTargetId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // دلتا ٢: مسوّدة براند لكل صفّ — مفتاحها معرّف المنتج. تُعبَّأ من البراند
  // الحالي عند كل فتحٍ للنافذة (لا اقتراح، لا تخمين — نسخ القيمة القائمة فقط).
  const [brandDrafts, setBrandDrafts] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!isOpen) return;
    setBrandDrafts(Object.fromEntries(candidates.map((c) => [c.id, c.brand || ""])));
  }, [isOpen, candidates]);

  const preview = useMemo(
    () => (targetId != null ? buildMergePreview(candidates, targetId) : null),
    [candidates, targetId],
  );

  const nameById = useMemo(
    () => new Map(candidates.map((c) => [c.id, c.name])), [candidates],
  );

  // التصادم يُحسب على من سينضمّ فعلياً فقط (الهدف + القابلون للضمّ) — المرفوض
  // يبقى صفّاً مستقلاً فبراندُه لا يتصادم مع أحد.
  const brandCollisions = useMemo(() => {
    if (!preview) return [];
    return findBrandCollisions([
      { id: preview.target.id, brand: brandDrafts[preview.target.id] ?? "" },
      ...preview.movable.map((m) => ({ id: m.id, brand: brandDrafts[m.id] ?? "" })),
    ]);
  }, [preview, brandDrafts]);

  if (!isOpen) return null;

  const handleClose = () => {
    if (busy) return;
    setTargetId(null);
    setError(null);
    onClose();
  };

  const handleConfirm = async () => {
    if (!preview || preview.movable.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const memberIds = [preview.target.id, ...preview.movable.map((m) => m.id)];
      const brands: Record<number, string> = {};
      for (const id of memberIds) {
        const value = (brandDrafts[id] ?? "").trim();
        if (value) brands[id] = value;
      }
      const result = await inventoryApi.mergeProducts(
        preview.target.id, preview.movable.map((m) => m.id), brands,
      );
      toast(`تمّ ضمّ ${result.merged_product_ids.length} منتجاً تحت «${preview.target.name}».`, "success");
      onMerged({ ...result, targetName: preview.target.name });
      setTargetId(null);
      onClose();
    } catch (e: unknown) {
      setError(humanizeThrown(e, "تعذّر تنفيذ الضمّ"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" dir="rtl">
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-lg bg-[var(--color-surface)] p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-base font-bold ktra-text-ink">
            <Merge className="h-4 w-4" /> ضمّ {candidates.length} منتجات تحت منتجٍ واحد
          </h3>
          <button type="button" onClick={handleClose} className="ktra-iconbtn" aria-label="إغلاق">
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mb-3 text-xs ktra-text-soft">
          اختر أيّ المنتجات المُحدَّدة يبقى «الهدف» — الباقون ينتقلون تحته، ويحتفظ كلٌّ
          برصيده وتكلفته وحركاته وفواتيره كما هي. بلا حركة مخزون وبلا قيد محاسبي.
        </p>

        <div className="min-h-0 flex-1 overflow-auto rounded border border-[var(--ktra-border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--ktra-border)] bg-[var(--color-surface-2)]">
                <th className="w-10 p-2 text-center">الهدف</th>
                <th className="p-2 text-start">المنتج</th>
                <th className="p-2 text-start" style={{ width: 150 }}>البراند</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.id} className="border-b border-[var(--ktra-border)] last:border-0">
                  <td className="p-2 text-center">
                    <input
                      type="radio"
                      name="merge-target"
                      className="h-4 w-4"
                      checked={targetId === c.id}
                      onChange={() => setTargetId(c.id)}
                      aria-label={`اجعل «${c.name}» الهدف`}
                    />
                  </td>
                  <td className="p-2 ktra-text-ink">{c.name}</td>
                  <td className="p-2">
                    <input
                      type="text"
                      className="ktra-input h-8 w-full"
                      value={brandDrafts[c.id] ?? ""}
                      onChange={(e) => setBrandDrafts((d) => ({ ...d, [c.id]: e.target.value }))}
                      placeholder="بلا براند"
                      aria-label={`براند «${c.name}»`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {preview && (
          <div className="mt-3 space-y-2 text-xs">
            {preview.movable.length > 0 && (
              <div className="ktra-banner ktra-banner--ok" style={{ flexDirection: "column", alignItems: "flex-start" }}>
                <p className="mb-1 font-bold">
                  سينتقل {preview.movable.length} منتجاً تحت «{preview.target.name}»:
                </p>
                <ul className="list-inside list-disc space-y-0.5">
                  {preview.movable.map((m) => <li key={m.id}>{m.name}</li>)}
                </ul>
                <p className="mt-1 ktra-text-soft">
                  وستُعاد تسمية كلٍّ منهم إلى «{preview.renamedTo}» — كل برانداتٍ منتجٍ
                  واحد تحمل اسماً واحداً في هذا النظام.
                </p>
              </div>
            )}
            {preview.blocked.length > 0 && (
              <div className="ktra-banner ktra-banner--err" style={{ flexDirection: "column", alignItems: "flex-start" }}>
                <p className="mb-1 flex items-center gap-1 font-bold">
                  <AlertTriangle className="h-3.5 w-3.5" /> {preview.blocked.length} يُمنع ضمّهم:
                </p>
                <ul className="list-inside list-disc space-y-0.5">
                  {preview.blocked.map((b) => <li key={b.id}>{b.name} — {b.reason}</li>)}
                </ul>
              </div>
            )}
            {/* دلتا ٢: تحذيرٌ لا منع — البراند الفارغ مسموحٌ عمداً، لكن صفوفاً
                متطابقة (حتى فراغين معاً) تفقد وسيلة تمييزها في المنتقي بعد
                توحيد الاسم، وهذا بالضبط ما يمنعه هذا الحقل. */}
            {brandCollisions.length > 0 && (
              <div className="ktra-banner ktra-banner--warn" style={{ flexDirection: "column", alignItems: "flex-start" }}>
                <p className="mb-1 flex items-center gap-1 font-bold">
                  <AlertTriangle className="h-3.5 w-3.5" /> صفوفٌ ستظهر متطابقةً بلا وسيلة تمييز:
                </p>
                <ul className="list-inside list-disc space-y-0.5">
                  {brandCollisions.map((group) => (
                    <li key={group.brand || "—"}>
                      {group.brand ? `البراند «${group.brand}»` : "بلا براند"}: {" "}
                      {group.ids.map((id) => nameById.get(id) ?? `#${id}`).join("، ")}
                    </li>
                  ))}
                </ul>
                <p className="mt-1 ktra-text-soft">
                  يمكنك المتابعة — البراند اختياري ويمكن تسميته لاحقاً من كرت المنتج —
                  لكن هذه الصفوف ستُعرض متطابقةً تماماً في منتقي المستندات حتى تُسمَّى.
                </p>
              </div>
            )}
          </div>
        )}

        {error && <div className="ktra-banner ktra-banner--err mt-3">{error}</div>}

        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="ktra-btn" onClick={handleClose} disabled={busy}>إلغاء</button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            onClick={() => void handleConfirm()}
            disabled={busy || !preview || preview.movable.length === 0}
          >
            {busy ? "جارٍ الضمّ…" : preview ? `ضمّ ${preview.movable.length} منتجاً` : "اختر الهدف أولاً"}
          </button>
        </div>
      </div>
    </div>
  );
};
