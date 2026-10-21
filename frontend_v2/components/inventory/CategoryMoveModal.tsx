/**
 * C3 — نافذة نقل واحدة لحالتين: منتجاتٌ إلى تصنيف، وتصنيفٌ تحت أبٍ آخر.
 *
 * الحالتان تختلفان في **معنى الفراغ**: منتجٌ بلا تصنيف ليس تصنيفاً رئيسياً،
 * والتصنيف الرئيسي ليس «بلا تصنيف» — فيُقال ذلك صراحةً لا يُترك تخميناً: سطرٌ
 * تحت المنتقي في حالة التصنيف، وخانةُ «إزالة التصنيف» في حالة المنتج. وخيارات
 * حالة التصنيف تُصفّى بـ`eligibleParents` (العقدة وأحفادها خارج القائمة) فيمنع
 * الواجهةُ ما يرفضه الخادم أصلاً، بدل أن يصطدم المستخدم برسالة حلقةٍ بعد
 * اختياره.
 *
 * والفراغ في «المنتج» ليس مجرّد حقلٍ فارغ: `category` حقلُ عائلة — نقلُ براندٍ
 * واحد ينقل كل براندات المنتج، ومنتجٌ له أكثر من براند يُحذَّر قبل النقل. وإفراغ
 * المنتقي ليس اختياراً هناك — «بدون تصنيف» قرارٌ صريحٌ بالخانة، كي لا تمسح
 * مسحةٌ عابرة تصنيفَ منتجٍ بلا سؤال.
 */
import React, { useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, AlertTriangle, X } from "lucide-react";
import { CategoryTreeSelect, type CategoryTreeOption } from "./CategoryTreeSelect";
import { eligibleParents } from "../../utils/categoryTree";
import { formatNumber } from "../../utils/formatNumber";

export type CategoryMoveMode = "products" | "category";

type Props = {
  mode: CategoryMoveMode;
  title: string;
  /** القائمة الكاملة — التصفية للحالة الثانية تجري هنا لا عند المستدعي. */
  categories: CategoryTreeOption[];
  /** في حالة التصنيف: العقدة المنقولة (تُستبعد هي وأحفادها من الخيارات). */
  excludeCategoryId?: number | null;
  /** القيمة الحالية: `null` منتجٌ بلا تصنيف، و`undefined` مجموعةٌ مختلطة (الجدول). */
  initialValue: number | null | undefined;
  /** في حالة المنتجات: عدد براندات العائلة وقت الفتح (1 = بلا تحذير). */
  brandCount?: number;
  onConfirm: (target: number | null) => Promise<void>;
  onClose: () => void;
};

export const CategoryMoveModal: React.FC<Props> = ({
  mode, title, categories, excludeCategoryId, initialValue, brandCount, onConfirm, onClose,
}) => {
  const [value, setValue] = useState<number | null>(initialValue ?? null);
  const [clearToNone, setClearToNone] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // كلّ فتحٍ يبدأ من القيمة الحالية — لا مسوّدة اختيارٍ من فتحٍ سابق.
  useEffect(() => {
    setValue(initialValue ?? null);
    setClearToNone(false);
    setError(null);
  }, [initialValue, mode, excludeCategoryId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // منتقي التصنيف يستهلك Esc بـ`preventDefault()` وهو يغلق قائمته، فيصل
      // الحدث إلى هنا موسوماً — نتركه حينها: القائمة وحدها تُغلق لا النافذة.
      if (event.key === "Escape" && !event.defaultPrevented && !saving) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [saving, onClose]);

  const options = useMemo(
    () => (mode === "category" && excludeCategoryId != null
      ? eligibleParents(categories, excludeCategoryId)
      : categories),
    [mode, categories, excludeCategoryId],
  );

  const nullMeaning = mode === "products" ? "بدون تصنيف" : "تصنيف رئيسي (بلا أب)";
  // «بدون تصنيف» في المنتج قرارٌ صريحٌ بالخانة، لا حالةُ منتقٍ فارغ؛ فنصُّ
  // حقل المنتقي يدعو إلى اختيار الهدف بدل أن يُسمّي الفراغ اختياراً.
  const placeholder = mode === "products" ? "اختر التصنيف الهدف…" : nullMeaning;

  // في المنتج: «بدون تصنيف» قرارٌ صريحٌ بالخانة لا إفراغُ منتقٍ عابر؛ وخانةُ
  // الإزالة تُخفى لمنتجٍ بلا تصنيف (لا شيء يُزال)، وتُعرض لمجموعةٍ مختلطة
  // (`undefined`) لأن بينها ما له تصنيف.
  const showClear = mode === "products" && initialValue !== null;
  const target = mode === "products" && clearToNone ? null : value;
  // وفي التصنيف: إفراغُ المنتقي هو اختيارُ «تصنيف رئيسي» كما كان — يكفي أن
  // يختلف عن الأب الحالي.
  const canConfirm = mode === "products"
    ? clearToNone || (value !== null && value !== initialValue)
    : value !== initialValue;

  const confirm = async () => {
    if (saving || !canConfirm) return;
    setSaving(true);
    setError(null);
    try {
      await onConfirm(target);
      onClose();
    } catch (reason: unknown) {
      // خطأ الخادم يُعرض هنا ولا يُبتلع: المستخدم يصحّح ويعيد المحاولة والنافذة
      // باختيارها كما هو.
      setError(reason instanceof Error ? reason.message : "تعذّر النقل");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="ktra-overlay-mask fixed inset-0 z-[90] flex items-center justify-center p-4"
      dir="rtl"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="category-move-title"
        className="w-full max-w-md overflow-hidden rounded-lg border border-[var(--ktra-border)] bg-[var(--ktra-panel)] shadow-xl"
      >
        <div className="flex items-center gap-2 border-b border-[var(--ktra-border-soft)] px-4 py-3">
          <ArrowRightLeft className="h-4 w-4 shrink-0 text-[var(--ktra-ink-soft)]" />
          <h2 id="category-move-title" className="min-w-0 flex-1 truncate font-bold text-[var(--ktra-ink)]">
            {title}
          </h2>
          <button
            type="button"
            className="ktra-iconbtn"
            onClick={onClose}
            disabled={saving}
            aria-label="إغلاق نافذة النقل"
            title="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 p-4">
          <CategoryTreeSelect
            mode="single"
            categories={options}
            value={value}
            onChange={(id) => setValue(id)}
            placeholder={placeholder}
            disabled={saving || clearToNone}
          />

          {showClear && (
            <label className="flex items-center gap-2 text-xs text-[var(--ktra-ink)]">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-[var(--ktra-accent)]"
                checked={clearToNone}
                disabled={saving}
                onChange={(event) => setClearToNone(event.target.checked)}
              />
              إزالة التصنيف (بدون تصنيف)
            </label>
          )}

          {mode === "category" && (
            <p className="text-xs text-[var(--ktra-ink-soft)]">
              إفراغ الاختيار يعني «{nullMeaning}».
            </p>
          )}

          {mode === "products" && (brandCount ?? 1) > 1 && (
            <div className="ktra-banner ktra-banner--warn flex items-start gap-1.5 text-xs">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                ينتقل المنتج كلّه ببراندَاته الـ{formatNumber(brandCount)} — التصنيف للمنتج لا لهذا البراند وحده
              </span>
            </div>
          )}

          {error && (
            <div role="alert" className="ktra-banner ktra-banner--err text-sm">
              {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-[var(--ktra-border-soft)] bg-[var(--ktra-surface-2)] px-4 py-3">
          <button type="button" className="ktra-btn" onClick={onClose} disabled={saving}>
            إلغاء
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            onClick={() => void confirm()}
            disabled={saving || !canConfirm}
          >
            {saving ? "جارٍ النقل…" : "نقل"}
          </button>
        </div>
      </div>
    </div>
  );
};
