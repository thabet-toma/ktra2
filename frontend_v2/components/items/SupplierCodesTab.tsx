/**
 * T-SUPSKU — أرقام الصنف عند مورّديه، داخل كرت الصنف.
 *
 * مطابقة فاتورة المورّد تجري برقم كتالوجه (מק"ט) لا برقمنا. كان الرقم يُحشَر
 * في «الاسم بالإنجليزية» لغياب مكانٍ له — وهذا مكانه.
 *
 * جدول ربط لا حقل على الصنف: نفس الإطار يأتي من أكثر من مورّد، ولكلٍّ ترقيمه.
 * الرقم الواحد عند المورّد الواحد لا يشير إلى صنفين — يحرسه الخادم ويردّ
 * برسالةٍ تسمّي الصنف المالك.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { inventoryApi, type SupplierProductDto } from "@/services/inventoryApi";
import { accountingApi } from "@/services/accountingApi";
import { useConfirm } from "@/contexts/ConfirmContext";

interface SupplierOption {
  id: number;
  name: string;
}

interface Props {
  /** معرّف الصنف. غيابه = صنف لم يُحفظ بعد، فلا رقم يُربط به. */
  productId: number | null;
  readOnly?: boolean;
}

export const SupplierCodesTab: React.FC<Props> = ({ productId, readOnly }) => {
  const confirm = useConfirm();
  const [rows, setRows] = useState<SupplierProductDto[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [supplierId, setSupplierId] = useState("");
  const [code, setCode] = useState("");
  const [supplierItemName, setSupplierItemName] = useState("");

  const load = useCallback(async () => {
    if (!productId) { setRows([]); return; }
    setLoading(true);
    setError(null);
    try {
      setRows(await inventoryApi.listSupplierCodes(productId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل أرقام الموردين");
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    let cancelled = false;
    // موردون فقط — الطرف الذي ليس مورّداً يرفضه الخادم أصلاً، فلا يُعرض.
    accountingApi.getPartners("Supplier")
      .then((list: Array<Record<string, unknown>>) => {
        if (cancelled) return;
        setSuppliers(list.map((p) => ({
          id: Number(p.id), name: String(p.name || p.id),
        })));
      })
      .catch(() => { /* بلا قائمة: يبقى الحقل فارغاً والرسالة من الخادم */ });
    return () => { cancelled = true; };
  }, []);

  const add = async () => {
    if (!productId || !supplierId || !code.trim()) {
      setError("اختر المورّد واكتب رقمه للصنف.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await inventoryApi.createSupplierCode({
        supplier: Number(supplierId),
        product: productId,
        supplier_sku: code.trim(),
        supplier_name: supplierItemName.trim(),
      });
      setCode("");
      setSupplierItemName("");
      await load();
    } catch (e) {
      // رسالة الخادم تسمّي الصنف الذي يحمل الرقم — تُعرض كما هي.
      setError(e instanceof Error ? e.message : "تعذّر الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row: SupplierProductDto) => {
    if (!(await confirm({
      title: "حذف رقم المورّد",
      message: `سيُحذف الرقم «${row.supplier_sku}» عند «${row.supplier_display_name}». `
        + "الصنف نفسه لا يتأثّر، لكن فواتير هذا المورّد لن تُطابَق بهذا الرقم بعدها.",
      confirmText: "حذف",
    }))) return;
    setSaving(true);
    setError(null);
    try {
      await inventoryApi.deleteSupplierCode(row.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر الحذف");
    } finally {
      setSaving(false);
    }
  };

  if (!productId) {
    return (
      <div className="p-4 text-sm ktra-text-soft">
        احفظ الصنف أوّلاً، ثم اربط أرقام مورّديه به.
      </div>
    );
  }

  return (
    <div className="space-y-3 p-2">
      <p className="text-xs ktra-text-soft">
        رقم هذا الصنف في كتالوج كل مورّد — به تُطابَق فاتورته، وبه يجده البحث
        ومنتقي بنود الفاتورة. للصنف الواحد رقمٌ عند كل مورّد، وللمورّد الواحد
        أكثر من رقم إن بدّل ترقيمه.
      </p>

      {error && (
        <div role="alert" className="rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
          {error}
        </div>
      )}

      {!readOnly && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs ktra-text-soft">المورّد</span>
            <select
              className="ktra-input"
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value)}
              data-testid="supplier-code-partner"
            >
              <option value="">— اختر —</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs ktra-text-soft">رقمه للصنف (מק"ט)</span>
            <input
              className="ktra-input"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="3068.82"
              data-testid="supplier-code-sku"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs ktra-text-soft">اسمه عنده (اختياري)</span>
            <input
              className="ktra-input"
              value={supplierItemName}
              onChange={(e) => setSupplierItemName(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="ktra-toolbtn"
            disabled={saving}
            onClick={() => void add()}
            data-testid="supplier-code-add"
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
            {" "}إضافة
          </button>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-right text-sm">
          <thead>
            <tr>
              <th className="p-1 text-start">المورّد</th>
              <th className="p-1 text-start">رقمه للصنف</th>
              <th className="p-1 text-start">اسمه عنده</th>
              {!readOnly && <th className="w-10 p-1" />}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={4} className="p-3 text-center ktra-text-soft">…تحميل</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={4} className="p-3 text-center ktra-text-soft">
                  لا أرقام بعد — أضف رقم المورّد لتُطابَق فاتورته به.
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="p-1">{row.supplier_display_name}</td>
                <td className="p-1 font-mono">{row.supplier_sku}</td>
                <td className="p-1 ktra-text-soft">{row.supplier_name || "—"}</td>
                {!readOnly && (
                  <td className="p-1">
                    <button
                      type="button"
                      className="ktra-iconbtn ktra-iconbtn--danger"
                      disabled={saving}
                      onClick={() => void remove(row)}
                      title="حذف"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SupplierCodesTab;
