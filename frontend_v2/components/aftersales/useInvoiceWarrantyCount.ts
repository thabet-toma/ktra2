import { useEffect, useState } from "react";
import { listWarrantyCards } from "../../services/afterSalesApi";
import { usePermissions } from "../../contexts/PermissionsContext";

/**
 * #238 — عدد بطاقات الكفالة القابلة للطباعة على فاتورة بيعٍ مرحَّلة. `0` يُخفي
 * زرّ «اطبع كفالات الفاتورة» وشريطه، وهو كذلك لشركةٍ بلا ترخيص الوحدة أو لمن لا
 * يملك `aftersales.warranty.view` (الشرطان نفسهما في `ProductWarrantyPolicyLine`)،
 * ولمرجع البيع (لا كفالة تُصدَر عليه).
 *
 * `refreshKey` يُعيد الجلب بعد أن يتغيّر ما تُعدّ عليه البطاقات (ترحيل جديد).
 */
export function useInvoiceWarrantyCount(
  invoiceId: number | null,
  isPosted: boolean,
  isReturn: boolean,
  refreshKey: unknown,
): number {
  const { modules, can } = usePermissions();
  const allowed =
    Boolean(modules["after_sales"]) && can("aftersales.warranty.view")
    && isPosted && !isReturn && invoiceId != null;
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!allowed || invoiceId == null) {
      setCount(0);
      return;
    }
    let cancelled = false;
    // `live=1` يعدّ على الخادم — `count` الترقيم هو العدد، مهما كثرت البطاقات.
    listWarrantyCards({ sales_invoice: invoiceId, live: true }, 1, 1)
      .then((paged) => { if (!cancelled) setCount(paged.count); })
      .catch(() => { if (!cancelled) setCount(0); });
    return () => { cancelled = true; };
  }, [allowed, invoiceId, refreshKey]);

  return count;
}
