/**
 * مودال تسليم بضاعة فاتورة مبيعات للعميل (إرسالية).
 *
 * يعرض كل بنود الفاتورة القابلة للتسليم — الكل مؤشَّر بالكمية المتبقية افتراضياً
 * — ويختار المستخدم ما سُلِّم فعلاً والمستودع الذي خرج منه، فينعكس على المخزون
 * (حركة OUT) ويُرحَّل قيد تكلفة المبيعات للمُسلَّم وحده، وتتحدث حالة التسليم.
 *
 * مرآة ReceiveGoodsModal للجانب الشرائي.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Truck, X } from "lucide-react";
import { getDeliveryLines, deliverInvoiceLines } from "../../services/salesApi";
import { inventoryApi } from "../../services/inventoryApi";

interface WarehouseDto {
  id: number;
  name: string;
  is_default?: boolean;
  is_active?: boolean;
}

interface Props {
  invoiceId: number;
  invoiceNumber?: string;
  onClose: () => void;
  onDelivered: (message: string) => void;
}

interface Row {
  line_id: number;
  name: string;
  ordered: number;
  delivered: number;
  remaining: number;
  qty: number;
  selected: boolean;
  warehouse_id: number | null;
}

export const DeliverGoodsModal: React.FC<Props> = ({
  invoiceId,
  invoiceNumber,
  onClose,
  onDelivered,
}) => {
  const [warehouses, setWarehouses] = useState<WarehouseDto[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [number, setNumber] = useState(invoiceNumber || "");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [whs, data] = await Promise.all([
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<WarehouseDto[]>,
        getDeliveryLines(invoiceId),
      ]);
      setWarehouses(whs);
      const defaultWh = whs.find((w) => w.is_default)?.id ?? whs[0]?.id ?? null;
      setNumber(data.invoice_number || invoiceNumber || "");
      setRows(
        (data.lines || []).map((l) => {
          const ordered = Number(l.quantity) || 0;
          const delivered = Number(l.delivered_quantity) || 0;
          const remaining = Math.max(0, Number(l.remaining_quantity) || 0);
          return {
            line_id: l.line_id,
            name: l.product_name,
            ordered,
            delivered,
            remaining,
            qty: remaining,
            // الكل مفعَّل افتراضياً — التسليم الكامل هو الحالة الغالبة.
            selected: remaining > 0,
            warehouse_id: defaultWh,
          };
        })
      );
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

  const selectableCount = useMemo(
    () => rows.filter((r) => r.remaining > 0).length,
    [rows]
  );
  const allSelected = useMemo(
    () => selectableCount > 0 && rows.every((r) => r.remaining <= 0 || r.selected),
    [rows, selectableCount]
  );
  const hasDeliverable = useMemo(
    () => rows.some((r) => r.selected && r.qty > 0 && r.remaining > 0),
    [rows]
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
        .filter((r) => r.selected && r.qty > 0 && r.remaining > 0)
        .map((r) => ({
          line_id: r.line_id,
          quantity: r.qty,
          ...(r.warehouse_id ? { warehouse_id: r.warehouse_id } : {}),
        }));
      if (!lines.length) {
        setError("اختر بنداً واحداً على الأقل بكمية أكبر من صفر.");
        setSaving(false);
        return;
      }
      const res = await deliverInvoiceLines(invoiceId, lines, notes);
      onDelivered(
        `إرسالية #${res.delivery_id} — ${res.delivery_status_display || "تم التسليم"}`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر التسليم");
    } finally {
      setSaving(false);
    }
  };

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
              <Truck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold ktra-text-ink dark:text-white">
                تسليم البضاعة للعميل
              </h3>
              <p className="text-xs ktra-text-soft">فاتورة {number}</p>
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

          {loading ? (
            <div className="flex items-center gap-2 justify-center py-10 ktra-text-soft">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>جارٍ التحميل…</span>
            </div>
          ) : rows.length === 0 ? (
            <div className="py-10 text-center ktra-text-soft text-sm">
              لا توجد بنود ذات صنف مخزون قابلة للتسليم في هذه الفاتورة.
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
                    <th className="px-3 py-2 text-right font-medium">الصنف</th>
                    <th className="px-2 py-2 text-center font-medium">المفوتر</th>
                    <th className="px-2 py-2 text-center font-medium">المسلَّم</th>
                    <th className="px-2 py-2 text-center font-medium">المتبقي</th>
                    <th className="px-2 py-2 text-center font-medium w-24">تسليم</th>
                    <th className="px-3 py-2 text-right font-medium">المستودع</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => {
                    const done = r.remaining <= 0;
                    return (
                      <tr key={r.line_id} className="border-t ktra-border-soft">
                        <td className="px-2 py-2 text-center">
                          <input
                            type="checkbox"
                            checked={r.selected}
                            disabled={done}
                            onChange={(e) =>
                              updateRow(idx, { selected: e.target.checked })
                            }
                            aria-label={`تسليم ${r.name}`}
                          />
                        </td>
                        <td className="px-3 py-2 ktra-text-ink dark:ktra-text-soft">
                          {r.name}
                          {done && (
                            <span className="block text-[11px] ktra-text-soft">
                              مسلَّم بالكامل
                            </span>
                          )}
                        </td>
                        <td className="px-2 py-2 text-center font-mono">{r.ordered}</td>
                        <td className="px-2 py-2 text-center font-mono">{r.delivered}</td>
                        <td className="px-2 py-2 text-center font-mono">{r.remaining}</td>
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
                            <option value="">—</option>
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

          <label className="block">
            <span className="block text-xs ktra-text-soft mb-1">
              ملاحظات الإرسالية (اختياري)
            </span>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full h-9 px-2 border ktra-border-soft rounded ktra-bg-field dark:ktra-bg-panel"
              placeholder="اسم المستلم / رقم المركبة…"
            />
          </label>

          <div className="flex items-center justify-end gap-3 pt-2 border-t ktra-border-soft">
            <button
              onClick={onClose}
              className="px-4 py-2 ktra-text-ink dark:ktra-text-soft ktra-bg-panel rounded-lg"
            >
              إلغاء
            </button>
            <button
              onClick={submit}
              disabled={saving || loading || !hasDeliverable}
              className="flex items-center gap-2 px-5 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Truck className="w-4 h-4" />
              )}
              تأكيد التسليم
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DeliverGoodsModal;
