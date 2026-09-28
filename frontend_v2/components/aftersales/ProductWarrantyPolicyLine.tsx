import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { listWarrantyPolicies, type WarrantyPolicyRow } from "../../services/afterSalesApi";
import { usePermissions } from "../../contexts/PermissionsContext";

/**
 * #231 — خلاصة سياسة الكفالة على كرت المنتج، للقراءة فقط: التعديل من شاشة
 * سياسات الكفالة (رابطٌ إليها لا نموذجٌ هنا). لا مصدر آخر لبيانات السياسة على
 * الكرت — حقلا المنتج القديمان حُذفا؛ السياسة صفٌّ مستقل في `after_sales`.
 *
 * تظهر فقط حين تملك الشركة ترخيص الوحدة والمستخدم صلاحية `aftersales.warranty.view`
 * — البيانات نفسها تأتي من نقطةٍ محروسة بالبوابة ذاتها، فلا تسريب لشركةٍ
 * غير مرخّصة عبر مسارٍ آخر.
 */

interface Props {
  productId: number;
}

/** شرط الظهور نفسه في موضعين: هنا (المكوّن) وفي `ItemForm.tsx` (تسمية الحقل) —
 * بلا هذا الاستخراج يُخاطر أحد الموضعين بتعليق تسمية «كفالة» على كرتٍ لشركةٍ
 * غير مرخّصة حتى لو ارتدّ المكوّن نفسه فارغاً (قصة المستخدم ٢٠ تمنعه صراحةً). */
export function useProductWarrantyPolicyVisible(): boolean {
  const { modules, can } = usePermissions();
  return Boolean(modules["after_sales"]) && can("aftersales.warranty.view");
}

export const ProductWarrantyPolicyLine: React.FC<Props> = ({ productId }) => {
  const allowed = useProductWarrantyPolicyVisible();

  const [policy, setPolicy] = useState<WarrantyPolicyRow | null | undefined>(undefined);

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    listWarrantyPolicies({ product: productId })
      .then((rows) => { if (!cancelled) setPolicy(rows[0] || null); })
      .catch(() => { if (!cancelled) setPolicy(null); });
    return () => { cancelled = true; };
  }, [allowed, productId]);

  if (!allowed) return null;

  const summary = (() => {
    if (policy === undefined) return "جارٍ التحميل…";
    if (!policy) return "بلا سياسة كفالة — لا بطاقة تُصدَر تلقائياً عند بيع هذا البراند";
    const parts: string[] = [];
    if (policy.dealer_months) parts.push(`تاجر ${policy.dealer_months} شهراً`);
    if (policy.manufacturer_months) {
      parts.push(
        `مصنع ${policy.manufacturer_months} شهراً${policy.manufacturer_warrantor_name ? ` — ${policy.manufacturer_warrantor_name}` : ""}`,
      );
    }
    if (policy.supplier_months) parts.push(`مورّد ${policy.supplier_months} شهراً`);
    const methodPart = policy.method_label;
    return `${parts.join(" · ") || "بلا مدّة فعّالة"} · ${methodPart}`;
  })();

  return (
    <span className="flex min-h-[30px] flex-wrap items-center gap-1.5">
      <ShieldCheck className="h-3.5 w-3.5 text-[var(--color-text-muted)]" />
      <span className="text-sm text-[var(--color-text)]">{summary}</span>
      <Link to="/after-sales?settings=policies" className="text-[var(--color-primary)] underline">
        سياسات الكفالة
      </Link>
    </span>
  );
};

export default ProductWarrantyPolicyLine;
