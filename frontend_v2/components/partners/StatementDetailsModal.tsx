import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, Loader2, FileText, ExternalLink } from "lucide-react";
import {
  getSalesInvoice,
  getCustomerPayment,
  type SalesInvoiceDetail,
  type CustomerPaymentRow,
} from "../../services/salesApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import type { PurchaseInvoiceDto } from "../../types/purchaseInvoice";
import { referenceTypeLabel, invoicePathForReference } from "../../utils/entityLinks";
import { formatMoney } from "../../utils/formatNumber";
import { clientLogger } from "../../services/logger";

/**
 * كشف الحساب — «تفاصيل الحركة»: نافذة تعرض تفاصيل السطر حسب نوعه:
 *  - فاتورة بيع/شراء ⇒ البنود المُباعة/المشتراة (الصنف، الكمية، السعر، الإجمالي).
 *  - سند قبض ⇒ تفاصيل الدفعة (المبلغ، التاريخ، التوزيع على الفواتير).
 *  - غير ذلك ⇒ ملخّص مقروء + رابط فتح المستند إن وُجد.
 * يعيد استخدام الجالبات القائمة (DRY) — لا نقطة نهاية جديدة.
 */
export interface StatementMovement {
  reference_type: string | null;
  reference_id: number | null;
  description: string;
  date: string | null;
  debit: string;
  credit: string;
}

type Kind = "sales" | "purchase" | "customer_payment" | "other";

function kindOf(t?: string | null): Kind {
  const u = (t || "").toUpperCase();
  if (
    u.includes("SALES_INVOICE") ||
    u.includes("SALES_DELIVERY") ||
    u === "SALE" ||
    u === "STOCK_ISSUE"
  )
    return "sales";
  if (u.includes("PURCHASE_INVOICE") || u === "PURCHASE_RECEIPT") return "purchase";
  if (u === "CUSTOMER_PAYMENT") return "customer_payment";
  return "other";
}

const th = "px-2 py-1 text-right font-bold border-b border-[var(--aseel-border)] bg-[var(--aseel-head,#f2f0e4)]";
const td = "px-2 py-1 text-right border-b border-[var(--aseel-border)]";

export const StatementDetailsModal: React.FC<{
  movement: StatementMovement | null;
  onClose: () => void;
}> = ({ movement, onClose }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sales, setSales] = useState<SalesInvoiceDetail | null>(null);
  const [purchase, setPurchase] = useState<PurchaseInvoiceDto | null>(null);
  const [payment, setPayment] = useState<CustomerPaymentRow | null>(null);

  const kind = kindOf(movement?.reference_type);
  const refId = movement?.reference_id ?? null;

  useEffect(() => {
    if (!movement) return;
    setSales(null);
    setPurchase(null);
    setPayment(null);
    setError(null);
    if (refId == null || kind === "other") return;
    setLoading(true);
    clientLogger.info("statement.details_open", { kind, refId });
    const done = () => setLoading(false);
    if (kind === "sales") {
      getSalesInvoice(refId).then(setSales).catch((e) => setError(e instanceof Error ? e.message : String(e))).finally(done);
    } else if (kind === "purchase") {
      purchaseInvoiceApi.get(refId).then(setPurchase).catch((e) => setError(e instanceof Error ? e.message : String(e))).finally(done);
    } else if (kind === "customer_payment") {
      getCustomerPayment(refId).then(setPayment).catch((e) => setError(e instanceof Error ? e.message : String(e))).finally(done);
    }
  }, [movement, kind, refId]);

  if (!movement) return null;

  const path = invoicePathForReference(movement.reference_type, movement.reference_id);
  const title = `${referenceTypeLabel(movement.reference_type)}${refId != null ? ` #${refId}` : ""}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      dir="rtl"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-2xl border border-gray-200 dark:border-gray-700 max-h-[85vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center sticky top-0 bg-white dark:bg-gray-800">
          <h2 className="text-base font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-500" />
            {title}
          </h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 rounded-full" aria-label="إغلاق">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-3 text-sm">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-[var(--aseel-ink-soft)]">
            <span>التاريخ: <b className="text-[var(--aseel-ink)]">{movement.date || "—"}</b></span>
            <span>مدين: <b className="text-[var(--aseel-ink)] aseel-num">{movement.debit}</b></span>
            <span>دائن: <b className="text-[var(--aseel-ink)] aseel-num">{movement.credit}</b></span>
          </div>
          {movement.description && (
            <div className="text-[var(--aseel-ink-soft)]">البيان: <span className="text-[var(--aseel-ink)]">{movement.description}</span></div>
          )}

          {loading && (
            <div className="flex items-center gap-2 text-[var(--aseel-ink-soft)] py-4">
              <Loader2 className="w-4 h-4 animate-spin" /> جاري تحميل التفاصيل…
            </div>
          )}
          {error && <div className="text-[var(--aseel-danger)] py-2">{error}</div>}

          {/* فاتورة مبيعات — البنود المُباعة */}
          {!loading && sales && (
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className={th}>الصنف</th>
                  <th className={th}>الكمية</th>
                  <th className={th}>السعر</th>
                  <th className={th}>الإجمالي</th>
                </tr>
              </thead>
              <tbody>
                {sales.lines.map((l) => (
                  <tr key={l.id}>
                    <td className={td}>{l.product_name || `#${l.product}`}</td>
                    <td className={`${td} aseel-num`}>{l.quantity}</td>
                    <td className={`${td} aseel-num`}>{formatMoney(l.unit_price)}</td>
                    <td className={`${td} aseel-num`}>{formatMoney(l.line_total_excl_tax)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* فاتورة مشتريات — البنود المشتراة */}
          {!loading && purchase && (
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className={th}>الصنف</th>
                  <th className={th}>الكمية</th>
                  <th className={th}>السعر</th>
                  <th className={th}>الإجمالي</th>
                </tr>
              </thead>
              <tbody>
                {(purchase.items || []).map((it, i) => (
                  <tr key={it.id ?? i}>
                    <td className={td}>{it.product_name || it.name || `#${it.product ?? ""}`}</td>
                    <td className={`${td} aseel-num`}>{it.quantity}</td>
                    <td className={`${td} aseel-num`}>{formatMoney(it.unit_price)}</td>
                    <td className={`${td} aseel-num`}>{formatMoney(it.total_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* سند قبض — تفاصيل الدفعة وتوزيعها */}
          {!loading && payment && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-x-6 gap-y-1">
                <span className="text-[var(--aseel-ink-soft)]">المبلغ المقبوض: <b className="text-[var(--aseel-ink)] aseel-num">{formatMoney(payment.amount)}</b></span>
                <span className="text-[var(--aseel-ink-soft)]">تاريخ القبض: <b className="text-[var(--aseel-ink)]">{payment.payment_date || "—"}</b></span>
              </div>
              {payment.notes && (
                <div className="text-[var(--aseel-ink-soft)]">ملاحظات: <span className="text-[var(--aseel-ink)]">{payment.notes}</span></div>
              )}
              {payment.allocations && payment.allocations.length > 0 ? (
                <table className="w-full border-collapse">
                  <thead>
                    <tr>
                      <th className={th}>الفاتورة المُسددة</th>
                      <th className={th}>المبلغ المخصّص</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payment.allocations.map((a, i) => (
                      <tr key={a.id ?? i}>
                        <td className={td}>فاتورة #{a.invoice}</td>
                        <td className={`${td} aseel-num`}>{formatMoney(a.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-[var(--aseel-ink-soft)]">دفعة على الحساب (بلا تخصيص لفاتورة محددة).</div>
              )}
            </div>
          )}

          {/* أنواع أخرى — ملخّص + رابط المستند إن وُجد */}
          {!loading && kind === "other" && !error && (
            <div className="text-[var(--aseel-ink-soft)] py-2">
              لا تتوفر بنود تفصيلية لهذا النوع من الحركات. يظهر الملخّص أعلاه.
            </div>
          )}

          {path && (
            <div className="pt-2">
              <button
                type="button"
                onClick={() => navigate(path)}
                className="inline-flex items-center gap-1.5 text-[var(--aseel-accent,#2563eb)] underline hover:opacity-80"
              >
                <ExternalLink className="w-4 h-4" /> فتح المستند الكامل
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StatementDetailsModal;
