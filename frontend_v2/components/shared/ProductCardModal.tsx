/**
 * DEF-007/008 — بطاقة الصنف (مودال مشترك).
 * مكوّن واحد يُعاد استخدامه في كل مداخل عرض بطاقة الصنف:
 *   1) النقر المفرد على منتج في شجرة المنتجات.
 *   2) أيقونة (i) في قائمة بحث المنتجات (القائمة المنسدلة).
 *   3) أيقونة (i) بجانب منتج مختار على سطر فاتورة.
 * يقرأ نفس نقطة بيانات بطاقة الصنف (`inventory/products/{id}/profile/`) التي
 * تستهلكها صفحة `ProductProfilePage`. عرض الأسعار بمنزلتين عشريتين (DEF-003) —
 * تنسيق عرض فقط، لا يمسّ الدقّة المخزّنة.
 */
import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X, ExternalLink, Check } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { apiGetObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";

interface ProductProfile {
  id: number;
  sku: string;
  name: string;
  category: string | null;
  quantity_on_hand: string;
  avg_cost: string;
  inventory_valuation: string;
  purchased_qty: string;
  purchased_value: string;
  sold_qty: string;
  sold_value: string;
}

/** تنسيق رقم نصّي بمنزلتين عشريتين للعرض فقط (DEF-003). */
const fmt2 = (v: string | number | null | undefined): string => {
  const n = Number(v);
  if (v == null || v === "" || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

interface Props {
  productId: number;
  onClose: () => void;
  /** عند تمريرها يظهر زر «موافق» الذي يُدرج الصنف في الفاتورة (بيع/شراء). */
  onConfirm?: () => void;
  /** نصّ زر التأكيد (افتراضي: «موافق»). */
  confirmLabel?: string;
  /** اسم الصنف الاحتياطي ليظهر فوراً حتى لو تعذّر تحميل بيانات البطاقة. */
  productName?: string;
}

export const ProductCardModal: React.FC<Props> = ({ productId, onClose, onConfirm, confirmLabel = "موافق", productName }) => {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<ProductProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiGetObject<ProductProfile>(`inventory/products/${productId}/profile/`, {
      tenantId: resolveTenantId(),
    })
      .then((p) => { if (!cancelled) setProfile(p); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [productId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "Enter" && onConfirm) { e.preventDefault(); onConfirm(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onConfirm]);

  const title = profile?.name || productName || null;

  const Kpi: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
    <div className="p-2 border border-[var(--aseel-border)] rounded">
      <div className="text-xs text-[var(--aseel-ink-soft)]">{label}</div>
      <div className="text-base font-bold text-[var(--aseel-ink)]">{value}</div>
    </div>
  );

  return createPortal(
    // البطاقة تُحقن في <body> عبر بورتال، خارج شجرة `.aseel-doc`. أنماط
    // `.aseel-picker-mask` مُحدَّدة بـ `[data-skin="aseel"] .aseel-picker-mask`
    // (محدِّد سليل)، فلا تنطبق ما لم يكن للقناع جدّ يحمل data-skin — لذا نلفّه
    // بعنصر `[data-skin="aseel"]` وإلا ظهر القناع بلا تنسيق (غير مرئي).
    <div data-skin="aseel">
    <div
      className="aseel-picker-mask"
      data-aseel-modal="1"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="aseel-picker" role="dialog" aria-modal="true" aria-label="بطاقة الصنف" style={{ maxWidth: 560, width: "92vw" }}>
        <div className="aseel-picker-head">
          <span>{title ? `بطاقة الصنف: ${title}` : "بطاقة الصنف"}</span>
          <button type="button" className="aseel-toolbtn" onClick={onClose} aria-label="إغلاق"><X /></button>
        </div>
        <div className="aseel-picker-body" style={{ padding: "10px" }}>
          {loading ? (
            <div className="p-4 text-center text-[var(--aseel-ink-soft)]">جاري التحميل…</div>
          ) : error ? (
            <div role="alert" className="p-3 text-sm text-[var(--aseel-ink-soft)]">
              تعذّر تحميل تفاصيل البطاقة. يمكنك المتابعة وإضافة الصنف للفاتورة.
            </div>
          ) : profile ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              <Kpi label="SKU" value={profile.sku || "—"} />
              <Kpi label="التصنيف" value={profile.category || "—"} />
              <Kpi label="المخزون الحالي" value={fmt2(profile.quantity_on_hand)} />
              <Kpi label="متوسط التكلفة" value={fmt2(profile.avg_cost)} />
              <Kpi label="تقييم المخزون" value={fmt2(profile.inventory_valuation)} />
              <Kpi label="إجمالي المشتراة (كمية)" value={fmt2(profile.purchased_qty)} />
              <Kpi label="إجمالي المباعة (كمية)" value={fmt2(profile.sold_qty)} />
              <Kpi label="إجمالي المباعة (قيمة)" value={fmt2(profile.sold_value)} />
            </div>
          ) : null}
        </div>
        <div className="aseel-picker-foot" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={() => { onClose(); navigate(`/products/${productId}`); }}
            title="فتح بطاقة الصنف الكاملة"
          >
            <ExternalLink className="w-4 h-4" /> البطاقة الكاملة
          </button>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button type="button" className="aseel-toolbtn" onClick={onClose}>إغلاق</button>
            {onConfirm && (
              <button
                type="button"
                onClick={() => { onConfirm(); onClose(); }}
                title="إضافة الصنف إلى الفاتورة"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 transition-colors"
              >
                <Check className="w-4 h-4" /> {confirmLabel}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
    </div>,
    document.body,
  );
};

export default ProductCardModal;
