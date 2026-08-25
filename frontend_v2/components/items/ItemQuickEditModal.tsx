/**
 * T-ITEMS M3 — تحرير سريع للصنف من داخل المستند.
 *
 * قبلها كان من يكتشف خطأً في اسم صنفٍ وهو في منتصف فاتورة أمام خيارين: أن
 * يتجاهله، أو أن يضغط «الكرت الكامل» فيغادر الفاتورة إلى `/products/:id`
 * ويعود ليبدأ من جديد. Odoo تحلّ هذا بسهمٍ يفتح سجلّ المنتج من سطر الفاتورة؛
 * هنا نافذةٌ عائمة صغيرة تُبقي الفاتورة مرئيةً خلفها.
 *
 * حقولها **هي** حقول الوضع البسيط (`utils/itemSimpleFields`) لا مجموعةٌ ثالثة:
 * من أراد أكثر منها فزرّ «الكرت الكامل» في الأسفل.
 */
import React, { useEffect, useState } from "react";
import { Loader2, Save, AlertCircle } from "lucide-react";
import { inventoryApi } from "../../services/inventoryApi";
import { KitFloatWindow } from "../kit/KitFloatWindow";
import { CategoryPicker } from "../inventory/CategoryPicker";
import { eventBus } from "../../utils/eventBus";
import { resolveTenantId } from "../../utils/tenantContext";
import {
  blankSimpleFields,
  dirtySimplePayload,
  hasSimpleChanges,
  simpleFieldsFromProduct,
  validateSimpleFields,
  type ItemSimpleFields,
} from "../../utils/itemSimpleFields";

type Props = {
  productId: number | string;
  onClose: () => void;
  /** الصفّ المحدَّث كما ردّه الخادم — يزامن به المستدعي نسخه المحلية. */
  onSaved: (updated: Record<string, unknown>) => void;
  /** فتح الكرت الكامل — يُترك فارغاً حيث لا معنى للمغادرة. */
  onOpenFullCard?: () => void;
};

export const ItemQuickEditModal: React.FC<Props> = ({
  productId, onClose, onSaved, onOpenFullCard,
}) => {
  // لقطة ما قبل التحرير: منها يُشتقّ الفرق، فلا يُرسَل حقلٌ لم يلمسه المستخدم.
  const [before, setBefore] = useState<ItemSimpleFields | null>(null);
  const [form, setForm] = useState<ItemSimpleFields>(blankSimpleFields());
  const [uoms, setUoms] = useState<Array<{ id: number; name_ar: string; name_en: string; code: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [label, setLabel] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      inventoryApi.getProduct(Number(productId)),
      inventoryApi.getUoms().catch(() => []),
    ])
      .then(([product, unitList]) => {
        if (!alive) return;
        const fields = simpleFieldsFromProduct(product as Record<string, unknown>);
        setBefore(fields);
        setForm(fields);
        setUoms(unitList);
        const p = product as Record<string, unknown>;
        setLabel(String(p.display_name ?? p.name_ar ?? p.name_en ?? p.sku ?? ""));
      })
      .catch((e: unknown) => {
        if (alive) setErr(e instanceof Error ? e.message : "فشل تحميل الصنف");
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [productId]);

  const patch = <K extends keyof ItemSimpleFields>(k: K, v: ItemSimpleFields[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const handleSave = async () => {
    const invalid = validateSimpleFields(form);
    if (invalid) { setErr(invalid); return; }
    if (!before || !hasSimpleChanges(before, form)) { onClose(); return; }
    setSaving(true); setErr(null);
    try {
      const updated = await inventoryApi.updateProduct(
        Number(productId), dirtySimplePayload(before, form),
      ) as Record<string, unknown>;
      // `updateProduct` يُبطل كاش منتقي الأصناف بنفسه؛ الحدث يوقظ الشاشات
      // التي تحمل قائمتها الخاصة، و`onSaved` يزامن نسخة المستدعي الحيّة.
      eventBus.publish("products", resolveTenantId());
      onSaved(updated);
      onClose();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const field = (labelText: string, node: React.ReactNode, span = 1) => (
    <label className="flex flex-col gap-1" style={{ gridColumn: `span ${span}` }}>
      <span className="text-xs text-[var(--color-text-muted)]">{labelText}</span>
      {node}
    </label>
  );

  const input = "w-full px-2 py-1.5 border rounded border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm";

  return (
    <KitFloatWindow
      open
      onClose={onClose}
      name="item-quick-edit"
      title={`تعديل سريع — ${label || "صنف"}`}
      defaultWidth={560}
      defaultHeight={430}
      footer={
        <div className="flex items-center justify-between gap-2 w-full">
          {onOpenFullCard ? (
            <button type="button" onClick={onOpenFullCard}
              className="px-3 py-1.5 text-sm rounded border border-[var(--color-border)] hover:bg-[var(--color-surface-3)] text-[var(--color-text-muted)]">
              الكرت الكامل
            </button>
          ) : <span />}
          <div className="flex gap-2">
            <button type="button" onClick={onClose}
              className="px-3 py-1.5 text-sm rounded border border-[var(--color-border)] hover:bg-[var(--color-surface-3)] text-[var(--color-text-muted)]">
              إلغاء
            </button>
            <button type="button" onClick={() => void handleSave()} disabled={saving || loading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              حفظ
            </button>
          </div>
        </div>
      }
    >
      <div dir="rtl" className="p-3">
        {err && (
          <div className="flex items-center gap-2 mb-3 p-2 rounded bg-red-50 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{err}</span>
          </div>
        )}
        {loading ? (
          <div className="flex items-center gap-2 text-[var(--color-text-muted)] text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> جارٍ التحميل…
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {field("اسم الصنف",
              <input className={input} value={form.name_ar} autoFocus
                onChange={(e) => patch("name_ar", e.target.value)} />, 2)}
            {field("الاسم بالإنجليزية",
              <input className={input} value={form.name_en}
                onChange={(e) => patch("name_en", e.target.value)} />, 2)}
            {field("التصنيف",
              <CategoryPicker value={form.category}
                onChange={(id) => patch("category", id)} />, 2)}
            {field("وحدة القياس",
              <select className={input} value={form.uom_id ?? ""}
                onChange={(e) => patch("uom_id", e.target.value ? Number(e.target.value) : null)}>
                <option value="">— بدون وحدة —</option>
                {uoms.map((u) => (
                  <option key={u.id} value={u.id}>{u.name_ar || u.name_en || u.code}</option>
                ))}
              </select>)}
            {field("سعر البيع",
              <input className={input} type="number" min="0" step="0.01"
                placeholder="فارغ = بلا سعر محفوظ" value={form.sale_price}
                onChange={(e) => patch("sale_price", e.target.value)} />)}
            {field("الباركود",
              <input className={input} style={{ direction: "ltr" }} value={form.barcode}
                onChange={(e) => patch("barcode", e.target.value)} />, 2)}
            <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
              <input type="checkbox" checked={form.is_service}
                onChange={(e) => patch("is_service", e.target.checked)} />
              بند خدمة
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
              <input type="checkbox" checked={form.is_serialized} disabled={form.is_service}
                onChange={(e) => patch("is_serialized", e.target.checked)} />
              تتبّع بالرقم التسلسلي
            </label>
          </div>
        )}
      </div>
    </KitFloatWindow>
  );
};

export default ItemQuickEditModal;
