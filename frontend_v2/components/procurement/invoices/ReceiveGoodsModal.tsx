/**
 * مودال استلام بضاعة فاتورة شراء محلية إلى المخزن.
 *
 * يحدد المستخدم لكل بند: الكمية المراد استلامها + المستودع الذي تذهب إليه،
 * فينعكس على المخزون (حركة IN) ويُرحَّل قيد الاستلام، وتتحدث حالة الاستلام.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, PackageCheck, X } from "lucide-react";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { inventoryApi } from "@/services/inventoryApi";
import type { PurchaseInvoiceDto } from "@/types/purchaseInvoice";

interface WarehouseDto {
  id: number;
  name: string;
  is_default?: boolean;
  is_active?: boolean;
}

interface Props {
  invoice: PurchaseInvoiceDto;
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
  warehouse_id: number | null;
}

export const ReceiveGoodsModal: React.FC<Props> = ({
  invoice,
  onClose,
  onReceived,
}) => {
  const [warehouses, setWarehouses] = useState<WarehouseDto[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // إعادة جلب الفاتورة لضمان معرّفات بنود حديثة — تعديل الفاتورة يحذف
      // البنود ويعيد إنشاءها (معرّفات جديدة)، فالنسخة الممرّرة قد تكون قديمة.
      const [whs, fresh] = await Promise.all([
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<
          WarehouseDto[]
        >,
        purchaseInvoiceApi.get(invoice.id as number),
      ]);
      setWarehouses(whs);
      const defaultWh =
        whs.find((w) => w.is_default)?.id ?? whs[0]?.id ?? null;
      const productRows: Row[] = (fresh.items || [])
        .filter((it) => it.product)
        .map((it) => {
          const ordered = Number(it.quantity) || 0;
          const received = Number(it.received_quantity) || 0;
          const remaining = Math.max(0, ordered - received);
          return {
            item_id: it.id as number,
            name: it.product_name || it.name,
            ordered,
            received,
            remaining,
            qty: remaining,
            warehouse_id: defaultWh,
          };
        });
      setRows(productRows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر تحميل المستودعات");
    } finally {
      setLoading(false);
    }
  }, [invoice]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateRow = (idx: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const hasReceivable = useMemo(
    () => rows.some((r) => r.qty > 0 && r.remaining > 0),
    [rows]
  );

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const lines = rows
        .filter((r) => r.qty > 0 && r.warehouse_id)
        .map((r) => ({
          item_id: r.item_id,
          quantity: r.qty,
          warehouse_id: r.warehouse_id as number,
        }));
      if (!lines.length) {
        setError("حدّد كمية ومستودعاً لبند واحد على الأقل.");
        setSaving(false);
        return;
      }
      await purchaseInvoiceApi.receive(invoice.id as number, lines);
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
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl aseel-bg-field dark:aseel-bg-panel shadow-xl border aseel-border-soft">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b aseel-border-soft sticky top-0 aseel-bg-field dark:aseel-bg-panel">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-[var(--color-primary)] text-white rounded-xl">
              <PackageCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold aseel-text-ink dark:text-white">
                استلام البضاعة للمخزن
              </h3>
              <p className="text-xs aseel-text-soft">
                فاتورة {invoice.invoice_number}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 aseel-text-soft hover:aseel-bg-panel rounded-lg"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 sm:p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg aseel-bg-panel aseel-text-state text-sm border aseel-border-soft">
              {error}
            </div>
          )}
          {noWarehouses && (
            <div className="p-3 rounded-lg aseel-bg-panel aseel-text-ink text-sm border aseel-border-soft">
              لا توجد مستودعات نشطة. أنشئ مستودعاً من صفحة إدارة المستودعات أولاً.
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 justify-center py-10 aseel-text-soft">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>جارٍ التحميل…</span>
            </div>
          ) : rows.length === 0 ? (
            <div className="py-10 text-center aseel-text-soft text-sm">
              لا توجد بنود ذات صنف مخزون قابلة للاستلام في هذه الفاتورة.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border aseel-border-soft">
              <table className="w-full text-sm min-w-[480px]">
                <thead className="aseel-bg-panel aseel-text-soft text-xs">
                  <tr>
                    <th className="px-3 py-2 text-right font-medium">الصنف</th>
                    <th className="px-2 py-2 text-center font-medium">المطلوب</th>
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
                        className="border-t aseel-border-soft"
                      >
                        <td className="px-3 py-2 aseel-text-ink dark:aseel-text-soft">
                          {r.name}
                          {done && (
                            <span className="block text-[11px] aseel-text-soft">
                              مستلَم بالكامل
                            </span>
                          )}
                        </td>
                        <td className="px-2 py-2 text-center font-mono">
                          {r.ordered}
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
                            disabled={done}
                            onChange={(e) => {
                              const v = Math.max(
                                0,
                                Math.min(r.remaining, Number(e.target.value) || 0)
                              );
                              updateRow(idx, { qty: v });
                            }}
                            className="w-20 h-9 px-2 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-right disabled:opacity-50"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <select
                            value={r.warehouse_id ?? ""}
                            disabled={done}
                            onChange={(e) =>
                              updateRow(idx, {
                                warehouse_id: e.target.value
                                  ? Number(e.target.value)
                                  : null,
                              })
                            }
                            className="w-full h-9 px-2 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel disabled:opacity-50"
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

          <div className="flex items-center justify-end gap-3 pt-2 border-t aseel-border-soft">
            <button
              onClick={onClose}
              className="px-4 py-2 aseel-text-ink dark:aseel-text-soft aseel-bg-panel rounded-lg"
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
