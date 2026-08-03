/**
 * G12 — معالِج «أنشئ أول صفقة استيراد».
 * تجربة موجّهة للمستخدم الجديد: 3 خطوات مرقّمة (مورد → منتجات → مراجعة) تخفي
 * عشرات الحقول المتقدّمة وتقود لإنشاء صفقة صالحة بأقل احتكاك. يعيد استخدام
 * `inventoryApi.createProduct` (يربط product_id فعلياً — نفس درس G1) و
 * `dealsService.createDeal`. عند النجاح ينادي onCreated(dealId) لينتقل الأب للصفقة.
 */
import React, { useEffect, useMemo, useState } from "react";
import { X, ArrowLeft, ArrowRight, Check, Building, Package, ClipboardList, Plus, Trash2 } from "lucide-react";
import { Supplier } from "../../../types";
import { dealsService } from "../../../services/dealsService";
import { inventoryApi } from "../../../services/inventoryApi";
import { formatMoney } from "../../../utils/formatNumber";
import { useToast } from "../../../contexts/ToastContext";

interface WizardItem {
  key: string;
  name: string;
  productId: string;       // معرّف صنف موجود إن اختير من القائمة (وإلا يُنشأ)
  quantity: number;
  unitPrice: number;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  suppliers: Supplier[];
  onCreated: (dealId: string) => void;
}

const supplierLabel = (s: Supplier): string =>
  s.tradeName || s.alias || (s as { name?: string }).name || `#${s.id}`;

const emptyItem = (): WizardItem => ({
  key: crypto.randomUUID(), name: "", productId: "", quantity: 1, unitPrice: 0,
});

export const FirstDealWizard: React.FC<Props> = ({ isOpen, onClose, suppliers, onCreated }) => {
  const toast = useToast();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [supplierId, setSupplierId] = useState("");
  const [supplierQuery, setSupplierQuery] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState<WizardItem[]>([emptyItem()]);
  const [products, setProducts] = useState<Array<{ id: string; name: string }>>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setStep(1); setSupplierId(""); setSupplierQuery(""); setDescription("");
    setItems([emptyItem()]); setError(null);
    inventoryApi.getAllProducts()
      .then((rows) => setProducts(
        (rows as Array<Record<string, unknown>>).map((p) => ({
          id: String(p.id),
          name: String(p.display_name || p.name_ar || p.name_en || p.sku || `صنف ${p.id ?? ""}`),
        }))
      ))
      .catch(() => setProducts([]));
  }, [isOpen]);

  const selectedSupplier = suppliers.find((s) => String(s.id) === supplierId) || null;

  const filteredSuppliers = useMemo(() => {
    const q = supplierQuery.trim().toLowerCase();
    const list = q
      ? suppliers.filter((s) => supplierLabel(s).toLowerCase().includes(q) || String(s.id).includes(q))
      : suppliers;
    return list.slice(0, 30);
  }, [suppliers, supplierQuery]);

  const validItems = items.filter((i) => i.name.trim() && i.quantity > 0);
  const total = validItems.reduce((s, i) => s + i.quantity * i.unitPrice, 0);

  const setItem = (key: string, patch: Partial<WizardItem>) =>
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, ...patch } : i)));

  const onItemName = (key: string, name: string) => {
    const match = products.find((p) => p.name === name);
    setItem(key, { name, productId: match ? match.id : "" });
  };

  const canNext = step === 1 ? Boolean(supplierId) : step === 2 ? validItems.length > 0 : true;

  const handleCreate = async () => {
    if (!supplierId || validItems.length === 0) return;
    setSaving(true); setError(null);
    try {
      // اربط كل بند بصنف حقيقي: الموجود بمعرّفه، والجديد يُنشأ Product أولاً.
      const resolved = [];
      for (const it of validItems) {
        let productId = it.productId;
        if (!/^\d+$/.test(productId)) {
          const created = await inventoryApi.createProduct({ name_ar: it.name.trim(), uom_primary: "عدد" }) as { id: number | string };
          productId = String(created.id);
        }
        resolved.push({
          id: crypto.randomUUID(), itemId: productId, name: it.name.trim(),
          quantity: it.quantity, unitPrice: it.unitPrice, totalPrice: it.quantity * it.unitPrice,
          categoryId: "", categoryName: "", specifications: "", imageUrls: [],
        });
      }
      const subtotal = resolved.reduce((s, i) => s + i.totalPrice, 0);
      const dealId = await dealsService.createDeal({
        supplierId,
        dealDescription: description.trim(),
        items: resolved,
        subtotal, totalAmount: subtotal, remaining_amount: subtotal,
        status: "initial",
        dealDate: new Date().toISOString().slice(0, 10),
      });
      toast("تم إنشاء أول صفقة بنجاح 🎉", "success");
      onCreated(dealId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  const steps = [
    { n: 1, label: "المورد", icon: Building },
    { n: 2, label: "المنتجات", icon: Package },
    { n: 3, label: "مراجعة", icon: ClipboardList },
  ];

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" dir="rtl">
      <div className="bg-[var(--color-surface)] rounded-xl shadow-xl w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden">
        {/* الرأس + مؤشّر الخطوات */}
        <div className="px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-bold text-[var(--color-text)]">إنشاء أول صفقة استيراد</h3>
            <button onClick={onClose} className="p-1 hover:bg-[var(--color-surface-3)] rounded-full" aria-label="إغلاق">
              <X className="w-5 h-5 text-[var(--color-text-muted)]" />
            </button>
          </div>
          <div className="flex items-center gap-2">
            {steps.map((s, idx) => {
              const Icon = s.icon;
              const active = step === s.n;
              const done = step > s.n;
              return (
                <React.Fragment key={s.n}>
                  <div className={`flex items-center gap-1.5 text-xs font-medium ${active ? "text-blue-600" : done ? "text-emerald-600" : "text-[var(--color-text-muted)]"}`}>
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center border ${active ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30" : done ? "border-emerald-400 bg-emerald-50 dark:bg-emerald-900/20" : "border-[var(--color-border)]"}`}>
                      {done ? <Check className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
                    </span>
                    <span className="hidden sm:inline">{s.n}. {s.label}</span>
                  </div>
                  {idx < steps.length - 1 && <div className={`flex-1 h-px ${done ? "bg-emerald-300" : "bg-[var(--color-surface-3)]"}`} />}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* المحتوى */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {error && <div className="text-red-600 bg-red-50 dark:bg-red-900/20 p-2 rounded text-sm">{error}</div>}

          {step === 1 && (
            <div className="space-y-3">
              <label className="block text-sm font-medium text-[var(--color-text)]">اختر المورد <span className="text-red-500">*</span></label>
              <input
                type="text" autoFocus value={supplierQuery}
                onChange={(e) => setSupplierQuery(e.target.value)}
                placeholder="ابحث عن مورد بالاسم…"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] text-sm"
              />
              <div className="border border-[var(--color-border)] rounded-lg max-h-64 overflow-y-auto divide-y divide-[var(--color-border)]">
                {filteredSuppliers.length === 0 ? (
                  <p className="p-3 text-sm text-[var(--color-text-muted)] text-center">لا موردين مطابقين — أنشئ مورداً من شاشة الموردين أولاً.</p>
                ) : filteredSuppliers.map((s) => (
                  <button
                    key={s.id} type="button"
                    onClick={() => setSupplierId(String(s.id))}
                    className={`w-full text-right px-3 py-2 text-sm hover:bg-blue-50 dark:hover:bg-blue-900/20 flex justify-between items-center ${supplierId === String(s.id) ? "bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-semibold" : ""}`}
                  >
                    <span>{supplierLabel(s)}</span>
                    {supplierId === String(s.id) && <Check className="w-4 h-4" />}
                  </button>
                ))}
              </div>
              <label className="block text-sm font-medium text-[var(--color-text)] pt-1">وصف الصفقة (اختياري)</label>
              <input
                type="text" value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="مثال: طلبية ألواح شمسية"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] text-sm"
              />
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <datalist id="wizard-products">
                {products.map((p) => <option key={p.id} value={p.name} />)}
              </datalist>
              <div className="grid grid-cols-[1fr_70px_90px_32px] gap-2 text-xs text-[var(--color-text-muted)] font-medium px-1">
                <span>اسم الصنف</span><span>الكمية</span><span>السعر</span><span />
              </div>
              {items.map((it) => (
                <div key={it.key} className="grid grid-cols-[1fr_70px_90px_32px] gap-2 items-center">
                  <input
                    list="wizard-products" value={it.name}
                    onChange={(e) => onItemName(it.key, e.target.value)}
                    placeholder="اكتب أو اختر صنفاً"
                    className="px-2 py-1.5 border rounded dark:bg-gray-700 border-[var(--color-border)] text-sm"
                  />
                  <input
                    type="number" min={0} value={it.quantity}
                    onChange={(e) => setItem(it.key, { quantity: Number(e.target.value) || 0 })}
                    className="px-2 py-1.5 border rounded dark:bg-gray-700 border-[var(--color-border)] text-sm text-center"
                  />
                  <input
                    type="number" min={0} value={it.unitPrice}
                    onChange={(e) => setItem(it.key, { unitPrice: Number(e.target.value) || 0 })}
                    className="px-2 py-1.5 border rounded dark:bg-gray-700 border-[var(--color-border)] text-sm text-center"
                  />
                  <button
                    type="button" onClick={() => setItems((prev) => prev.length > 1 ? prev.filter((x) => x.key !== it.key) : prev)}
                    className="text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded p-1" aria-label="حذف السطر"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button
                type="button" onClick={() => setItems((prev) => [...prev, emptyItem()])}
                className="flex items-center gap-1 text-sm text-blue-600 hover:underline"
              >
                <Plus className="w-4 h-4" /> إضافة سطر
              </button>
              <p className="text-xs text-[var(--color-text-muted)]">الأصناف الجديدة (غير الموجودة) تُنشأ تلقائياً كمنتجات عند الإنشاء.</p>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <div className="rounded-lg border border-[var(--color-border)] p-3 text-sm space-y-1">
                <div className="flex justify-between"><span className="text-[var(--color-text-muted)]">المورد</span><b>{selectedSupplier ? supplierLabel(selectedSupplier) : "—"}</b></div>
                {description && <div className="flex justify-between"><span className="text-[var(--color-text-muted)]">الوصف</span><span>{description}</span></div>}
                <div className="flex justify-between"><span className="text-[var(--color-text-muted)]">عدد البنود</span><b>{validItems.length}</b></div>
              </div>
              <table className="w-full text-sm">
                <thead><tr className="text-[var(--color-text-muted)] text-xs text-right"><th className="py-1">الصنف</th><th>الكمية</th><th>السعر</th><th className="text-left">الإجمالي</th></tr></thead>
                <tbody>
                  {validItems.map((i) => (
                    <tr key={i.key} className="border-t border-[var(--color-border)]">
                      <td className="py-1.5">{i.name}</td>
                      <td>{formatMoney(i.quantity)}</td>
                      <td>{formatMoney(i.unitPrice)}</td>
                      <td className="text-left font-mono">{formatMoney(i.quantity * i.unitPrice)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex justify-between items-center border-t border-[var(--color-border)] pt-2 font-bold">
                <span>الإجمالي</span><span className="text-emerald-600">${formatMoney(total)}</span>
              </div>
            </div>
          )}
        </div>

        {/* التذييل — تنقّل */}
        <div className="px-5 py-4 border-t border-[var(--color-border)] bg-[var(--color-surface-2)] flex justify-between items-center">
          <button
            type="button"
            onClick={() => (step === 1 ? onClose() : setStep((s) => (s - 1) as 1 | 2 | 3))}
            className="px-4 py-2 border rounded-lg text-sm font-medium hover:bg-[var(--color-surface-3)] text-[var(--color-text-muted)] flex items-center gap-1"
          >
            <ArrowRight className="w-4 h-4" /> {step === 1 ? "إلغاء" : "السابق"}
          </button>
          {step < 3 ? (
            <button
              type="button" disabled={!canNext}
              onClick={() => setStep((s) => (s + 1) as 1 | 2 | 3)}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
            >
              التالي <ArrowLeft className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="button" disabled={saving || validItems.length === 0}
              onClick={() => void handleCreate()}
              className="px-5 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1"
            >
              {saving ? "جارٍ الإنشاء…" : <><Check className="w-4 h-4" /> إنشاء الصفقة</>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
