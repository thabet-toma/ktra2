/**
 * إدارة المستودعات — إنشاء/تعديل/تعطيل المستودعات لكل شركة.
 * المستودع وجهة استلام البضاعة وبُعد على حركات المخزون.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw, Loader2, Star, Warehouse as WhIcon } from "lucide-react";
import { inventoryApi } from "../../services/inventoryApi";

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

  return (
    <div
      dir="rtl"
      className="rounded-xl border aseel-border-soft aseel-bg-field dark:aseel-bg-panel p-4 space-y-4"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-bold aseel-text-ink dark:text-white">
          <WhIcon className="w-5 h-5" />
          المستودعات
        </div>
        <button
          onClick={load}
          className="p-2 aseel-text-soft hover:aseel-bg-panel rounded-lg"
          title="تحديث"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {err && (
        <div className="p-2.5 rounded-lg aseel-bg-panel aseel-text-state text-sm border aseel-border-soft">
          {err}
        </div>
      )}

      {/* نموذج إضافة */}
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px_1fr_auto] gap-2 items-end">
        <input
          className="h-10 px-3 border aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel"
          placeholder="اسم المستودع *"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="h-10 px-3 border aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel"
          placeholder="الرمز"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <input
          className="h-10 px-3 border aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel"
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
      <div className="overflow-x-auto rounded-lg border aseel-border-soft">
        <table className="w-full text-sm min-w-[420px]">
          <thead className="aseel-bg-panel aseel-text-soft text-xs">
            <tr>
              <th className="px-3 py-2 text-right font-medium">المستودع</th>
              <th className="px-3 py-2 text-right font-medium">الرمز</th>
              <th className="px-3 py-2 text-center font-medium">افتراضي</th>
              <th className="px-3 py-2 text-center font-medium">الحالة</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center aseel-text-soft">
                  <Loader2 className="w-4 h-4 animate-spin inline" /> جارٍ التحميل…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center aseel-text-soft">
                  لا مستودعات بعد — أضف الأول من النموذج أعلاه.
                </td>
              </tr>
            ) : (
              items.map((w) => (
                <tr
                  key={w.id}
                  className={`border-t aseel-border-soft ${
                    w.is_active ? "" : "opacity-50"
                  }`}
                >
                  <td className="px-3 py-2 aseel-text-ink dark:aseel-text-soft">
                    {w.name}
                    {w.location && (
                      <span className="block text-[11px] aseel-text-soft">{w.location}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono aseel-text-soft">{w.code || "—"}</td>
                  <td className="px-3 py-2 text-center">
                    {w.is_default ? (
                      <Star className="w-4 h-4 inline text-[var(--color-primary)]" fill="currentColor" />
                    ) : (
                      <button
                        onClick={() => makeDefault(w)}
                        disabled={busy || !w.is_active}
                        className="text-xs aseel-text-soft hover:underline disabled:opacity-40"
                      >
                        تعيين
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <button
                      onClick={() => toggleActive(w)}
                      disabled={busy}
                      className="text-xs hover:underline aseel-text-soft"
                    >
                      {w.is_active ? "تعطيل" : "تفعيل"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default WarehousesManager;
