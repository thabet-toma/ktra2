/**
 * منتقي فاتورة بواجهة قائمة الفواتير — لا قائمة منسدلة بالأرقام.
 *
 * المالك لا يعرف الفاتورة برقمها، فيختارها كما يراها في شاشتها: رقم/تاريخ/الطرف/
 * الإجمالي/الحالة مع بحث فوري. مشترك بين إرساليات الشراء والبيع.
 */
import React, { useMemo, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";

export type PickableInvoice = {
  id: number;
  number: string;
  date?: string | null;
  partnerName?: string;
  total?: string | number | null;
  statusLabel?: string;
  /** ملاحظة ثانوية تحت الرقم (الباقي غير المستلم مثلاً). */
  hint?: string;
  /**
   * تُعرض ولا تُختار — الفاتورة موجودة لكنها لا تقبل المستند (سُلِّمت بالكامل
   * مثلاً). إخفاؤها يترك القائمة فارغة بلا سبب ظاهر، فنعرضها بسببها في `hint`.
   */
  disabled?: boolean;
};

interface Props {
  title: string;
  rows: PickableInvoice[];
  loading?: boolean;
  error?: string | null;
  partnerHeader: string;
  emptyHint: string;
  onPick: (invoice: PickableInvoice) => void;
  onClose: () => void;
}

export const InvoicePickerModal: React.FC<Props> = ({
  title,
  rows,
  loading,
  error,
  partnerHeader,
  emptyHint,
  onPick,
  onClose,
}) => {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) =>
      `${r.number} ${r.partnerName || ""} ${r.hint || ""}`.toLowerCase().includes(q)
    );
  }, [rows, query]);

  return (
    <div
      dir="rtl"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-3xl max-h-[88vh] flex flex-col rounded-2xl aseel-bg-field dark:aseel-bg-panel shadow-xl border aseel-border-soft">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b aseel-border-soft">
          <h3 className="text-base sm:text-lg font-bold aseel-text-ink dark:text-white">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="p-2 aseel-text-soft hover:aseel-bg-panel rounded-lg"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-4 sm:px-6 py-3 border-b aseel-border-soft">
          <label className="relative block">
            <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 right-3 aseel-text-soft" />
            <input
              autoFocus
              className="aseel-input w-full ps-3 pe-9"
              placeholder="بحث برقم الفاتورة أو الاسم…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-3">
          {error && (
            <div className="aseel-banner aseel-banner--err" role="alert">
              {error}
            </div>
          )}
          {loading ? (
            <div className="flex items-center gap-2 justify-center py-10 aseel-text-soft">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>جارٍ التحميل…</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-10 text-center aseel-text-soft text-sm">{emptyHint}</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="aseel-bg-panel aseel-text-soft text-xs">
                <tr>
                  <th className="px-3 py-2 text-right font-medium">رقم الفاتورة</th>
                  <th className="px-3 py-2 text-center font-medium">التاريخ</th>
                  <th className="px-3 py-2 text-right font-medium">{partnerHeader}</th>
                  <th className="px-3 py-2 text-left font-medium">الإجمالي</th>
                  <th className="px-3 py-2 text-center font-medium">الحالة</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    className={
                      r.disabled
                        ? "border-t aseel-border-soft opacity-60 cursor-not-allowed"
                        : "border-t aseel-border-soft cursor-pointer hover:aseel-bg-panel"
                    }
                    onClick={() => !r.disabled && onPick(r)}
                    onDoubleClick={() => !r.disabled && onPick(r)}
                  >
                    <td className="px-3 py-2 font-mono text-xs aseel-text-ink dark:aseel-text-soft">
                      {r.number}
                      {r.hint && (
                        <span className="block text-[11px] aseel-text-soft">{r.hint}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center text-xs">
                      {formatDateLocalized(r.date) || "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">{r.partnerName || "—"}</td>
                    <td className="px-3 py-2 text-left font-mono text-xs">
                      {formatMoney(r.total, "—")}
                    </td>
                    <td className="px-3 py-2 text-center text-[11px] aseel-text-soft">
                      {r.statusLabel || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default InvoicePickerModal;
