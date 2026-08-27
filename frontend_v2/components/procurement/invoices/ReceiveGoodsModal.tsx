/**
 * مودال استلام بضاعة فاتورة شراء محلية إلى المخزن.
 *
 * يحدد المستخدم لكل بند: الكمية المراد استلامها + المستودع الذي تذهب إليه،
 * فينعكس على المخزون (حركة IN) ويُرحَّل قيد الاستلام، وتتحدث حالة الاستلام.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, PackageCheck, X } from "lucide-react";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { getReceivableLines } from "@/services/goodsReceiptsApi";
import { inventoryApi } from "@/services/inventoryApi";

interface WarehouseDto {
  id: number;
  name: string;
  is_default?: boolean;
  is_active?: boolean;
}

interface Props {
  /** معرّف الفاتورة — البنود تُجلب دائماً طازجة من الخادم. */
  invoiceId: number;
  invoiceNumber?: string;
  onClose: () => void;
  onReceived: () => void;
}

interface Row {
  item_id: number;
  name: string;
  ordered: number;
  received: number;
  remaining: number;
  qty: number;
  /** مؤشَّر افتراضياً لكل بند له متبقٍ — الاستلام الكامل هو الحالة الغالبة. */
  selected: boolean;
  warehouse_id: number | null;
}

export const ReceiveGoodsModal: React.FC<Props> = ({
  invoiceId,
  invoiceNumber,
  onClose,
  onReceived,
}) => {
  const [warehouses, setWarehouses] = useState<WarehouseDto[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [number, setNumber] = useState(invoiceNumber || "");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // البنود تُجلب طازجة دائماً: المعرّفات صارت ثابتة عبر التعديل (المطابقة
      // بالمعرّف في `PurchaseInvoiceSerializer._sync_items`)، لكن الكميات
      // المستلَمة قد تكون تغيّرت منذ آخر عرض — ونافذةٌ تعرض باقياً بائتاً
      // تطلب من الخادم ما لا يقبله.
      const [whs, fresh] = await Promise.all([
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<
          WarehouseDto[]
        >,
        getReceivableLines(invoiceId),
      ]);
      setWarehouses(whs);
      setNumber(fresh.invoice_number || invoiceNumber || "");
      const defaultWh =
        whs.find((w) => w.is_default)?.id ?? whs[0]?.id ?? null;
      const productRows: Row[] = (fresh.lines || []).map((l) => {
        const ordered = Number(l.quantity) || 0;
        const received = Number(l.received_quantity) || 0;
        const remaining = Math.max(0, Number(l.remaining_quantity) || 0);
        return {
          item_id: l.item_id,
          name: l.product_name || l.name,
          ordered,
          received,
          remaining,
          qty: remaining,
          selected: remaining > 0,
          warehouse_id: defaultWh,
        };
      });
      setRows(productRows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر تحميل بنود الفاتورة");
    } finally {
      setLoading(false);
    }
  }, [invoiceId, invoiceNumber]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateRow = (idx: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const hasReceivable = useMemo(
    () => rows.some((r) => r.selected && r.qty > 0 && r.remaining > 0),
    [rows]
  );

  const selectableCount = useMemo(
    () => rows.filter((r) => r.remaining > 0).length,
    [rows]
  );
  const allSelected = useMemo(
    () => selectableCount > 0 && rows.every((r) => r.remaining <= 0 || r.selected),
    [rows, selectableCount]
  );
  const toggleAll = (checked: boolean) =>
    setRows((rs) =>
      rs.map((r) => (r.remaining > 0 ? { ...r, selected: checked } : r))
    );

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const lines = rows
        .filter((r) => r.selected && r.qty > 0 && r.warehouse_id)
        .map((r) => ({
          item_id: r.item_id,
          quantity: r.qty,
          warehouse_id: r.warehouse_id as number,
        }));
      if (!lines.length) {
        setError("اختر بنداً واحداً على الأقل بكمية ومستودع.");
        setSaving(false);
        return;
      }
      await purchaseInvoiceApi.receive(invoiceId, lines);
      onReceived();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر الاستلام");
    } finally {
      setSaving(false);
    }
  };

  const noWarehouses = !loading && warehouses.length === 0;

  return (
    <div
      dir="rtl"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl ktra-bg-field dark:ktra-bg-panel shadow-xl border ktra-border-soft">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b ktra-border-soft sticky top-0 ktra-bg-field dark:ktra-bg-panel">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-[var(--color-primary)] text-white rounded-xl">
              <PackageCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold ktra-text-ink dark:text-white">
                استلام البضاعة للمخزن
              </h3>
              <p className="text-xs ktra-text-soft">
                فاتورة {number}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 ktra-text-soft hover:ktra-bg-panel rounded-lg"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 sm:p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg ktra-bg-panel ktra-text-state text-sm border ktra-border-soft">
              {error}
            </div>
          )}
          {noWarehouses && (
            <div className="p-3 rounded-lg ktra-bg-panel ktra-text-ink text-sm border ktra-border-soft">
              لا توجد مستودعات نشطة. أنشئ مستودعاً من صفحة إدارة المستودعات أولاً.
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 justify-center py-10 ktra-text-soft">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>جارٍ التحميل…</span>
            </div>
          ) : rows.length === 0 ? (
            <div className="py-10 text-center ktra-text-soft text-sm">
              لا توجد بنود مرتبطة بمنتج مخزني قابلة للاستلام في هذه الفاتورة.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border ktra-border-soft">
              <table className="w-full text-sm min-w-[480px]">
                <thead className="ktra-bg-panel ktra-text-soft text-xs">
                  <tr>
                    <th className="px-2 py-2 text-center font-medium w-10">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        disabled={selectableCount === 0}
                        onChange={(e) => toggleAll(e.target.checked)}
                        aria-label="تحديد الكل"
                      />
                    </th>
                    <th className="px-3 py-2 text-right font-medium">المنتج</th>
                    <th className="px-2 py-2 text-center font-medium">المطلوب</th>
                    <th className="px-2 py-2 text-center font-medium">المستلَم</th>
                    <th className="px-2 py-2 text-center font-medium">المتبقي</th>
                    <th className="px-2 py-2 text-center font-medium w-24">استلام</th>
                    <th className="px-3 py-2 text-right font-medium">المستودع</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => {
                    const done = r.remaining <= 0;
                    return (
                      <tr
                        key={r.item_id}
                        className="border-t ktra-border-soft"
                      >
                        <td className="px-2 py-2 text-center">
                          <input
                            type="checkbox"
                            checked={r.selected}
                            disabled={done}
                            onChange={(e) =>
                              updateRow(idx, { selected: e.target.checked })
                            }
                            aria-label={`استلام ${r.name}`}
                          />
                        </td>
                        <td className="px-3 py-2 ktra-text-ink dark:ktra-text-soft">
                          {r.name}
                          {done && (
                            <span className="block text-[11px] ktra-text-soft">
                              مستلَم بالكامل
                            </span>
                          )}
                        </td>
                        <td className="px-2 py-2 text-center font-mono">
                          {r.ordered}
                        </td>
                        <td className="px-2 py-2 text-center font-mono">
                          {r.received}
                        </td>
                        <td className="px-2 py-2 text-center font-mono">
                          {r.remaining}
                        </td>
                        <td className="px-2 py-2">
                          <input
                            type="number"
                            min={0}
                            max={r.remaining}
                            step="0.0001"
                            value={r.qty}
                            disabled={done || !r.selected}
                            onChange={(e) => {
                              const v = Math.max(
                                0,
                                Math.min(r.remaining, Number(e.target.value) || 0)
                              );
                              updateRow(idx, { qty: v });
                            }}
                            className="w-20 h-9 px-2 border ktra-border-soft rounded ktra-bg-field dark:ktra-bg-panel text-right disabled:opacity-50"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <select
                            value={r.warehouse_id ?? ""}
                            disabled={done || !r.selected}
                            onChange={(e) =>
                              updateRow(idx, {
                                warehouse_id: e.target.value
                                  ? Number(e.target.value)
                                  : null,
                              })
                            }
                            className="w-full h-9 px-2 border ktra-border-soft rounded ktra-bg-field dark:ktra-bg-panel disabled:opacity-50"
                          >
                            {warehouses.map((w) => (
                              <option key={w.id} value={w.id}>
                                {w.name}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2 border-t ktra-border-soft">
            <button
              onClick={onClose}
              className="px-4 py-2 ktra-text-ink dark:ktra-text-soft ktra-bg-panel rounded-lg"
            >
              إلغاء
            </button>
            <button
              onClick={submit}
              disabled={saving || loading || !hasReceivable || noWarehouses}
              className="flex items-center gap-2 px-5 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <PackageCheck className="w-4 h-4" />
              )}
              تأكيد الاستلام
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReceiveGoodsModal;
