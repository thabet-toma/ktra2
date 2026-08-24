/**
 * DEF-007/008 — بطاقة الصنف (مودال مشترك).
 * مكوّن واحد يُعاد استخدامه في كل مداخل عرض بطاقة الصنف:
 *   1) النقر المفرد على منتج في شجرة المنتجات.
 *   2) أيقونة (i) في قائمة بحث المنتجات (القائمة المنسدلة).
 *   3) أيقونة (i) بجانب منتج مختار على سطر فاتورة.
 * يقرأ نفس نقطة بيانات بطاقة الصنف (`inventory/products/{id}/profile/`) التي
 * يستهلكها الكرت الكامل، ويعرض نفس «النظرة العامة» (`ProductOverview`) — مصدر
 * عرض واحد للصنف، والنسخة المختصرة هنا تُحيل للكرت الكامل للتحرير.
 */
import React, { useEffect, useState } from "react";
import { ExternalLink, Check, Pencil } from "lucide-react";
import { ItemQuickEditModal } from "../items/ItemQuickEditModal";
import { AseelFloatWindow } from "../aseel/AseelFloatWindow";
import { useNavigate } from "react-router-dom";
import { apiGetObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { productProfilePath } from "../../utils/entityLinks";
import { LedgerTable } from "./LedgerTable";
import {
  ProductOverview,
  ledgerColumns,
  type LedgerRow,
  type ProductProfileData,
} from "../items/ProductInsightTabs";

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
  const [profile, setProfile] = useState<ProductProfileData | null>(null);
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

  // T-ITEMS M3: التحرير السريع فوق البطاقة — وبعد الحفظ تُعاد قراءة الملف كي
  // تعرض البطاقة ما صار لا ما كان.
  const [quickEdit, setQuickEdit] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiGetObject<ProductProfileData>(`inventory/products/${productId}/profile/`, {
      tenantId: resolveTenantId(),
    })
      .then((p) => { if (!cancelled) setProfile(p); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [productId, reloadKey]);

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

  // أعمدة حركة المخزون المعروضة داخل البطاقة (مختصرة — بلا طرف/مستودع).
  const ledColumns = ledgerColumns();

  /* T-WIN: البطاقة صارت نافذة عائمة تُسحب وتُحجَّم — كانت لوحاً ثابتاً بعرض
     92vw. الهندسة تُحفظ لكل وضعٍ على حدة: الإضافة نافذة صغيرة والعرض أوسع. */
  return (
    <AseelFloatWindow
      open
      onClose={onClose}
      name={addMode ? "product-card-add" : "product-card"}
      title={title ? `بطاقة الصنف: ${title}` : "بطاقة الصنف"}
      defaultWidth={addMode ? 560 : 860}
      defaultHeight={addMode ? 460 : 620}
      rootProps={{ "data-aseel-modal": "1", "aria-label": "بطاقة الصنف" } as React.HTMLAttributes<HTMLDivElement>}
      footer={(
        <>
          {/* T-ITEMS M3: التعديل في مكانه أولاً — «الكرت الكامل» يغادر المستند
              الجاري، وكان الطريق الوحيد لتغيير اسمٍ خاطئ يُرى من الفاتورة. */}
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={() => setQuickEdit(true)}
            title="تعديل اسم الصنف وبياناته الأساسية دون مغادرة الشاشة"
          >
            <Pencil className="w-4 h-4" /> تعديل سريع
          </button>
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={() => { onClose(); navigate(productProfilePath(productId)); }}
            title="فتح كرت الصنف الكامل (عرض وتعديل)"
          >
            <ExternalLink className="w-4 h-4" /> الكرت الكامل
          </button>
          <div className="ms-auto flex items-center gap-2">
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
        </>
      )}
    >
      <div className="p-2.5">
          {loading ? (
            <div className="p-4 text-center text-[var(--aseel-ink-soft)]">جاري التحميل…</div>
          ) : error ? (
            <div role="alert" className="p-3 text-sm text-[var(--aseel-ink-soft)]">
              تعذّر تحميل تفاصيل البطاقة. يمكنك المتابعة وإضافة الصنف للفاتورة.
            </div>
          ) : profile ? (
            <ProductOverview profile={profile} />
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
      {quickEdit && (
        <ItemQuickEditModal
          productId={productId}
          onClose={() => setQuickEdit(false)}
          onSaved={() => setReloadKey((k) => k + 1)}
        />
      )}
    </AseelFloatWindow>
  );
};

export default ProductCardModal;
