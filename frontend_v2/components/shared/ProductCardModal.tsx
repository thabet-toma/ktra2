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
import { formatQuantity, formatMoney } from "../../utils/formatNumber";
import { productProfilePath } from "../../utils/entityLinks";
import { LedgerTable, DocRefCell, type LedgerColumn } from "./LedgerTable";

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


/** صف حركة المخزون (دفتر الرصيد الجاري) — يُعرض داخل البطاقة لاستغلال المساحة. */
interface LedgerRow {
  id: number;
  date: string | null;
  movement_type_label: string;
  reference_type: string | null;
  reference_id: number | null;
  party: string | null;
  warehouse: string | null;
  qty_in: string;
  qty_out: string;
  running_balance: string;
}

/** نوع الحركة المعروض — مشتقّ من نوع المستند المرجعي (مطابق لـ ProductProfilePage). */
const ledgerTypeLabel = (r: LedgerRow): string => {
  if (r.reference_type === "PURCHASE_INVOICE") return "مشتريات";
  if (r.reference_type === "SALE") return "مبيعات";
  return r.movement_type_label;
};

/** DEF-005 / T-R2: مصدر السعر المقترح للشارة داخل البطاقة. */
export type ProductCardPriceSource = "last_invoice" | "quote" | "default" | null;

interface Props {
  productId: number;
  onClose: () => void;
  /** عند تمريرها يظهر زر «موافق» الذي يُدرج الصنف في الفاتورة (بيع/شراء).
   *  T-R2: في وضع الإضافة يُمرَّر الكمية والسعر المُدخلان. */
  onConfirm?: (opts?: { quantity: number; unitPrice: number }) => void;
  /** نصّ زر التأكيد (افتراضي: «موافق»). */
  confirmLabel?: string;
  /** اسم الصنف الاحتياطي ليظهر فوراً حتى لو تعذّر تحميل بيانات البطاقة. */
  productName?: string;
  /** T-R2: وضع الإضافة للفاتورة — يُظهر حقل الكمية والسعر مع شارة المصدر. */
  addMode?: boolean;
  /** السعر المقترح (من آخر فاتورة/عرض سعر) — مبدئي قابل للتعديل. */
  suggestedPrice?: number | string | null;
  /** مصدر السعر المقترح للشارة. */
  priceSource?: ProductCardPriceSource;
}

const PRICE_SOURCE_LABEL: Record<NonNullable<ProductCardPriceSource>, string> = {
  last_invoice: "من آخر فاتورة",
  quote: "من عرض السعر",
  default: "السعر الافتراضي",
};

export const ProductCardModal: React.FC<Props> = ({ productId, onClose, onConfirm, confirmLabel = "موافق", productName, addMode = false, suggestedPrice, priceSource = null }) => {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<ProductProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // حركة المخزون داخل البطاقة (آخر الحركات) — تُعرض في وضع العرض فقط (لا الإضافة).
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [ledLoading, setLedLoading] = useState(false);
  const [ledError, setLedError] = useState<string | null>(null);
  // T-R2: الكمية والسعر المُدخلان في وضع الإضافة.
  const [qty, setQty] = useState("1");
  const [price, setPrice] = useState<string>(
    suggestedPrice == null || suggestedPrice === "" ? "" : String(suggestedPrice)
  );
  useEffect(() => {
    if (suggestedPrice != null && suggestedPrice !== "") setPrice(String(suggestedPrice));
  }, [suggestedPrice]);

  /** يجمع قيم الإضافة لتمريرها لـ onConfirm. */
  const confirmPayload = () => ({ quantity: Number(qty) || 1, unitPrice: Number(price) || 0 });

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

  // آخر حركات المخزون (حتى 8) — لملء مساحة البطاقة في وضع العرض فقط.
  useEffect(() => {
    if (addMode) return;
    let cancelled = false;
    setLedLoading(true);
    setLedError(null);
    apiGetObject<{ results: LedgerRow[]; count: number }>(
      `inventory/products/${productId}/stock-ledger/?limit=8&offset=0`,
      { tenantId: resolveTenantId() },
    )
      .then((d) => { if (!cancelled) setLedger(Array.isArray(d.results) ? d.results : []); })
      .catch((err) => { if (!cancelled) setLedError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setLedLoading(false); });
    return () => { cancelled = true; };
  }, [productId, addMode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "Enter" && onConfirm) { e.preventDefault(); onConfirm(addMode ? confirmPayload() : undefined); onClose(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onConfirm, addMode, qty, price]);

  const title = profile?.name || productName || null;

  const Kpi: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
    <div className="p-2 border border-[var(--aseel-border)] rounded">
      <div className="text-xs text-[var(--aseel-ink-soft)]">{label}</div>
      <div className="text-base font-bold text-[var(--aseel-ink)]">{value}</div>
    </div>
  );

  // أعمدة حركة المخزون المعروضة داخل البطاقة (مختصرة — نفس دفتر ProductProfilePage).
  const ledColumns: LedgerColumn<LedgerRow>[] = [
    { key: "date", header: "التاريخ", render: (r) => r.date || "—" },
    { key: "type", header: "النوع", render: (r) => ledgerTypeLabel(r) },
    {
      key: "ref", header: "المستند",
      render: (r) => (
        <DocRefCell
          referenceType={r.reference_type}
          referenceId={r.reference_id}
          label={r.reference_id != null ? `${r.reference_type || ""} #${r.reference_id}` : "—"}
        />
      ),
    },
    { key: "qty_in", header: "وارد", align: "center", render: (r) => (Number(r.qty_in) ? formatQuantity(r.qty_in) : "—") },
    { key: "qty_out", header: "صادر", align: "center", render: (r) => (Number(r.qty_out) ? formatQuantity(r.qty_out) : "—") },
    { key: "bal", header: "الرصيد", align: "center", render: (r) => <b>{formatQuantity(r.running_balance)}</b> },
  ];

  return createPortal(
    // البطاقة تُحقن في <body> عبر بورتال، خارج شجرة `.aseel-doc`.
    // أنماط القناع عامة وتتبع الجلد المطبّق على جذر التطبيق، لذلك لا يحتاج
    // المحتوى المنقول عبر البوابة إلى wrapper محلي يفرض جلداً بعينه.
    <div>
    <div
      className="aseel-picker-mask"
      data-aseel-modal="1"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="aseel-picker" role="dialog" aria-modal="true" aria-label="بطاقة الصنف" style={{ maxWidth: addMode ? 560 : 760, width: "92vw" }}>
        <div className="aseel-picker-head">
          <span>{title ? `بطاقة الصنف: ${title}` : "بطاقة الصنف"}</span>
          <button type="button" className="aseel-toolbtn" onClick={onClose} aria-label="إغلاق"><X /></button>
        </div>
        <div className="aseel-picker-body" style={{ padding: "10px", maxHeight: "72vh", overflowY: "auto" }}>
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
              <Kpi label="المخزون الحالي" value={formatQuantity(profile.quantity_on_hand, "—")} />
              <Kpi label="متوسط التكلفة" value={formatMoney(profile.avg_cost, "—")} />
              <Kpi label="تقييم المخزون" value={formatMoney(profile.inventory_valuation, "—")} />
              <Kpi label="إجمالي المشتراة (كمية)" value={formatQuantity(profile.purchased_qty, "—")} />
              <Kpi label="إجمالي المباعة (كمية)" value={formatQuantity(profile.sold_qty, "—")} />
              <Kpi label="إجمالي المباعة (قيمة)" value={formatMoney(profile.sold_value, "—")} />
            </div>
          ) : null}

          {/* حركة المخزون داخل البطاقة — تملأ المساحة في وضع العرض (لا الإضافة). */}
          {!addMode && (
            <div className="mt-3 pt-3 border-t border-[var(--aseel-border)]">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-bold text-[var(--aseel-ink)]">حركة المخزون (آخر الحركات)</span>
                <button
                  type="button"
                  className="text-xs text-[var(--aseel-accent,#2563eb)] underline hover:opacity-80"
                  onClick={() => { onClose(); navigate(productProfilePath(productId)); }}
                  title="عرض كامل حركة المخزون"
                >
                  عرض الكل
                </button>
              </div>
              <LedgerTable<LedgerRow>
                columns={ledColumns}
                rows={ledger}
                loading={ledLoading}
                error={ledError}
                emptyText="لا توجد حركات مخزون لهذا الصنف."
              />
            </div>
          )}

          {/* T-R2: حقل الكمية والسعر مع شارة المصدر — يظهر فقط في وضع الإضافة. */}
          {addMode && onConfirm && (
            <div className="mt-3 pt-3 border-t border-[var(--aseel-border)] grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-xs text-[var(--aseel-ink-soft)]">
                الكمية المراد إضافتها
                <input
                  type="number"
                  min="0"
                  step="any"
                  className="aseel-input"
                  value={qty}
                  autoFocus
                  onChange={(e) => setQty(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--aseel-ink-soft)]">
                <span className="flex items-center justify-between gap-2">
                  السعر
                  {priceSource && (
                    <span className="aseel-price-badge" title="مصدر السعر المقترح">
                      {PRICE_SOURCE_LABEL[priceSource]}
                    </span>
                  )}
                </span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  className="aseel-input"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                />
              </label>
            </div>
          )}
        </div>
        <div className="aseel-picker-foot" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={() => { onClose(); navigate(productProfilePath(productId)); }}
            title="فتح بطاقة الصنف الكاملة (حركة المخزون)"
          >
            <ExternalLink className="w-4 h-4" /> البطاقة الكاملة
          </button>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button type="button" className="aseel-toolbtn" onClick={onClose}>إغلاق</button>
            {onConfirm && (
              <button
                type="button"
                onClick={() => { onConfirm(addMode ? confirmPayload() : undefined); onClose(); }}
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
