import { useEffect, useState } from "react";
import { inventoryApi } from "../services/inventoryApi";
import type { ProductNameMatch } from "../services/inventoryApi";

/**
 * #21: «هذا موجود — أضف براند؟» — اقتراحٌ لا منع، لموضعَين: كرتُ المنتج الجديد
 * (`ItemForm`) والإنشاءُ السريع من المستندات (`ItemQuickCreateModal`). كانت القاعدةُ
 * داخل الكرت وحدَه، فالإنشاءُ السريع — أكثرُ أبواب التسجيل استعمالاً في العمل
 * اليوميّ — كان يسجّل الاسمَ الموجود منتجاً منفصلاً بلا أيّ تنبيه.
 *
 * مُؤجَّلٌ 400ms فلا يطلب الخادم مع كلّ ضغطة. و`enabled=false` (منتجٌ محفوظ) يُطفئه
 * تماماً: منتجٌ محفوظٌ يطابق نفسَه دائماً. والردُّ المتأخّرُ لاسمٍ تغيّر لا يُكتب —
 * كان يُكتب قبل نقل القاعدة إلى هنا.
 *
 * الاقتراحُ يحمل `family_id` أو `product_id` (منتجٌ قديمٌ بلا أب) — يُمرَّر إلى
 * `utils/brandActions` (`brandTargetOf` / `attachBrandToExisting`) كما هو.
 */
export function useProductNameOffer(name: string, enabled: boolean) {
  const [offer, setOffer] = useState<ProductNameMatch | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const clean = name.trim();

  useEffect(() => {
    if (!enabled || !clean) { setOffer(null); return; }
    let active = true;
    const t = setTimeout(() => {
      inventoryApi.checkProductName(clean)
        .then((match) => { if (active) setOffer(match); })
        .catch(() => { if (active) setOffer(null); });
    }, 400);
    return () => { active = false; clearTimeout(t); };
  }, [clean, enabled]);

  // اسمٌ جديد يُلغي رفض الاقتراح السابق — تجاهلٌ لاسمٍ بعينه لا لكلّ الاقتراحات.
  useEffect(() => { setDismissed(false); }, [clean]);

  return {
    /** الاقتراحُ الظاهر — `null` إن لا تطابق أو رفضه المستخدم لهذا الاسم. */
    offer: dismissed ? null : offer,
    dismiss: () => setDismissed(true),
    clear: () => setOffer(null),
  };
}
