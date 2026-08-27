/**
 * إدارة المستودعات — إنشاء/تعديل/تعطيل المستودعات لكل شركة.
 * المستودع وجهة استلام البضاعة وبُعد على حركات المخزون.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  Boxes, FolderOpen, Loader2, Plus, RefreshCw, Save, Star,
  Warehouse as WhIcon, X,
} from "lucide-react";
import {
  inventoryApi,
  type WarehouseStockDetail,
} from "../../services/inventoryApi";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";

interface WarehouseDto {
  id: number;
  name: string;
  code?: string;
  location?: string;
  is_default?: boolean;
  is_active?: boolean;
}

export const WarehousesManager: React.FC = () => {
  const [items, setItems] = useState<WarehouseDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [location, setLocation] = useState("");
  const [selectedWarehouse, setSelectedWarehouse] = useState<WarehouseDto | null>(null);
  const [detail, setDetail] = useState<WarehouseStockDetail | null>(null);
  const [detailName, setDetailName] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailErr, setDetailErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setItems((await inventoryApi.getWarehouses()) as WarehouseDto[]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async () => {
    if (!name.trim()) {
      setErr("اسم المستودع مطلوب.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await inventoryApi.createWarehouse({
        name: name.trim(),
        code: code.trim(),
        location: location.trim(),
      });
      setName("");
      setCode("");
      setLocation("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر الإضافة");
    } finally {
      setBusy(false);
    }
  };

  const makeDefault = async (w: WarehouseDto) => {
    setBusy(true);
    try {
      await inventoryApi.updateWarehouse(w.id, { is_default: true });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر التحديث");
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (w: WarehouseDto) => {
    setBusy(true);
    try {
      if (w.is_active) await inventoryApi.deleteWarehouse(w.id);
      else await inventoryApi.updateWarehouse(w.id, { is_active: true });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر التحديث");
    } finally {
      setBusy(false);
    }
  };

  const openWarehouse = async (warehouse: WarehouseDto) => {
    setSelectedWarehouse(warehouse);
    setDetailName(warehouse.name);
    setDetail(null);
    setDetailErr(null);
    setDetailLoading(true);
    try {
      setDetail(await inventoryApi.getWarehouseStock(warehouse.id));
    } catch (e) {
      setDetailErr(e instanceof Error ? e.message : "تعذر تحميل تفاصيل المستودع");
    } finally {
      setDetailLoading(false);
    }
  };

  const saveWarehouseName = async () => {
    if (!selectedWarehouse || !detailName.trim()) {
      setDetailErr("اسم المستودع مطلوب.");
      return;
    }
    setBusy(true);
    setDetailErr(null);
    try {
      const updated = await inventoryApi.updateWarehouse(selectedWarehouse.id, {
        name: detailName.trim(),
      }) as WarehouseDto;
      setSelectedWarehouse(updated);
      setDetailName(updated.name);
      setItems((rows) => rows.map((row) => (
        row.id === updated.id ? { ...row, ...updated } : row
      )));
      setDetail((current) => current ? {
        ...current,
        warehouse: { ...current.warehouse, name: updated.name },
      } : current);
    } catch (e) {
      setDetailErr(e instanceof Error ? e.message : "تعذر تعديل اسم المستودع");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      dir="rtl"
      className="rounded-xl border ktra-border-soft ktra-bg-field dark:ktra-bg-panel p-4 space-y-4"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-bold ktra-text-ink dark:text-white">
          <WhIcon className="w-5 h-5" />
          المستودعات
        </div>
        <button
          onClick={load}
          className="p-2 ktra-text-soft hover:ktra-bg-panel rounded-lg"
          title="تحديث"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {err && (
        <div className="p-2.5 rounded-lg ktra-bg-panel ktra-text-state text-sm border ktra-border-soft">
          {err}
        </div>
      )}

      {/* نموذج إضافة */}
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px_1fr_auto] gap-2 items-end">
        <input
          className="h-10 px-3 border ktra-border-soft rounded-lg ktra-bg-field dark:ktra-bg-panel"
          placeholder="اسم المستودع *"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="h-10 px-3 border ktra-border-soft rounded-lg ktra-bg-field dark:ktra-bg-panel"
          placeholder="الرمز"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <input
          className="h-10 px-3 border ktra-border-soft rounded-lg ktra-bg-field dark:ktra-bg-panel"
          placeholder="الموقع (اختياري)"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <button
          onClick={add}
          disabled={busy}
          className="h-10 flex items-center justify-center gap-1.5 px-4 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          إضافة
        </button>
      </div>

      {/* القائمة */}
      <div className="overflow-x-auto rounded-lg border ktra-border-soft">
        <table className="w-full text-sm min-w-[420px]">
          <thead className="ktra-bg-panel ktra-text-soft text-xs">
            <tr>
              <th className="px-3 py-2 text-right font-medium">المستودع</th>
              <th className="px-3 py-2 text-right font-medium">الرمز</th>
              <th className="px-3 py-2 text-center font-medium">افتراضي</th>
              <th className="px-3 py-2 text-center font-medium">الحالة</th>
              <th className="px-3 py-2 text-center font-medium">التفاصيل</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center ktra-text-soft">
                  <Loader2 className="w-4 h-4 animate-spin inline" /> جارٍ التحميل…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center ktra-text-soft">
                  لا مستودعات بعد — أضف الأول من النموذج أعلاه.
                </td>
              </tr>
            ) : (
              items.map((w) => (
                <tr
                  key={w.id}
                  className={`border-t ktra-border-soft ${
                    w.is_active ? "" : "opacity-50"
                  } hover:ktra-bg-panel`}
                  onDoubleClick={() => void openWarehouse(w)}
                >
                  <td className="px-3 py-2 ktra-text-ink dark:ktra-text-soft">
                    {w.name}
                    {w.location && (
                      <span className="block text-[11px] ktra-text-soft">{w.location}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono ktra-text-soft">{w.code || "—"}</td>
                  <td className="px-3 py-2 text-center">
                    {w.is_default ? (
                      <Star className="w-4 h-4 inline text-[var(--color-primary)]" fill="currentColor" />
                    ) : (
                      <button
                        onClick={() => makeDefault(w)}
                        disabled={busy || !w.is_active}
                        className="text-xs ktra-text-soft hover:underline disabled:opacity-40"
                      >
                        تعيين
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <button
                      onClick={() => toggleActive(w)}
                      disabled={busy}
                      className="text-xs hover:underline ktra-text-soft"
                    >
                      {w.is_active ? "تعطيل" : "تفعيل"}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-center">
                    <button
                      type="button"
                      onClick={() => void openWarehouse(w)}
                      className="inline-flex items-center gap-1 text-xs ktra-text-accent hover:underline"
                    >
                      <FolderOpen className="h-4 w-4" />
                      فتح
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {selectedWarehouse && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          dir="rtl"
          role="dialog"
          aria-modal="true"
          aria-label={`تفاصيل ${selectedWarehouse.name}`}
        >
          <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border ktra-border-soft ktra-bg-field shadow-2xl dark:ktra-bg-panel">
            <div className="flex items-center justify-between border-b ktra-border-soft px-4 py-3">
              <div className="flex items-center gap-2 font-bold ktra-text-ink dark:text-white">
                <WhIcon className="h-5 w-5" />
                تفاصيل المستودع
              </div>
              <button
                type="button"
                onClick={() => setSelectedWarehouse(null)}
                className="rounded-lg p-2 ktra-text-soft hover:ktra-bg-panel"
                aria-label="إغلاق"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4 overflow-y-auto p-4">
              {detailErr && (
                <div className="ktra-banner ktra-banner--err" role="alert">
                  {detailErr}
                </div>
              )}

              <div className="grid grid-cols-1 items-end gap-2 sm:grid-cols-[1fr_auto]">
                <label className="ktra-field">
                  <span className="ktra-field-label">اسم المستودع</span>
                  <input
                    className="ktra-input"
                    value={detailName}
                    onChange={(event) => setDetailName(event.target.value)}
                    disabled={busy}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void saveWarehouseName()}
                  disabled={busy || !detailName.trim()}
                  className="ktra-toolbtn h-10 disabled:opacity-50"
                >
                  {busy
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <Save className="h-4 w-4" />}
                  حفظ الاسم
                </button>
              </div>

              {detailLoading ? (
                <div className="flex items-center justify-center gap-2 py-12 ktra-text-soft">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  جارٍ تحميل المنتجات…
                </div>
              ) : detail && (
                <>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border ktra-border-soft ktra-bg-panel p-3">
                      <div className="flex items-center gap-2 text-xs ktra-text-soft">
                        <Boxes className="h-4 w-4" />
                        عدد المنتجات ذات الرصيد
                      </div>
                      <div className="mt-1 text-xl font-bold ktra-text-ink dark:text-white">
                        {detail.item_count}
                      </div>
                    </div>
                    <div className="rounded-lg border ktra-border-soft ktra-bg-panel p-3">
                      <div className="text-xs ktra-text-soft">
                        قيمة المخزون — بالعملة الأساسية
                      </div>
                      <div className="mt-1 text-xl font-bold ktra-text-accent">
                        {formatMoney(detail.total_value)}
                      </div>
                    </div>
                  </div>

                  <div className="overflow-x-auto rounded-lg border ktra-border-soft">
                    <table className="w-full min-w-[700px] text-sm">
                      <thead className="ktra-bg-panel ktra-text-soft text-xs">
                        <tr>
                          <th className="px-3 py-2 text-right font-medium">رقم المنتج</th>
                          <th className="px-3 py-2 text-right font-medium">المنتج</th>
                          <th className="px-3 py-2 text-center font-medium">الكمية</th>
                          <th className="px-3 py-2 text-center font-medium">متوسط التكلفة</th>
                          <th className="px-3 py-2 text-center font-medium">القيمة</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.items.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="px-3 py-8 text-center ktra-text-soft">
                              لا توجد منتجات ذات رصيد في هذا المستودع.
                            </td>
                          </tr>
                        ) : detail.items.map((item) => (
                          <tr key={item.product_id} className="border-t ktra-border-soft">
                            <td className="px-3 py-2 font-mono ktra-text-soft">{item.sku}</td>
                            <td className="px-3 py-2 ktra-text-ink dark:text-white">{item.name}</td>
                            <td className="px-3 py-2 text-center">{formatQuantity(item.quantity)}</td>
                            <td className="px-3 py-2 text-center">{formatQuantity(item.avg_cost)}</td>
                            <td className="px-3 py-2 text-center font-medium">
                              {formatMoney(item.stock_value)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WarehousesManager;
