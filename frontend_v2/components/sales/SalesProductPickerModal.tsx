import React, { useMemo, useState, useEffect } from "react";
import { Search, X, Package, Plus } from "lucide-react";
import { ItemQuickCreateModal } from "../items/ItemQuickCreateModal";
import { availableOf, stockBadgeFor } from "../../utils/stockBadge";
import { formatQuantity } from "../../utils/formatNumber";

/** نفس حقول المنتج في فاتورة المبيعات — منفصل لتفادي تبعية دائرية */
export type SalesProductPickerItem = {
  id: number;
  sku: string;
  barcode?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  quantity_on_hand: string;
  online_price?: string | null;
  /** T-REORDER: حالة المخزون كما يحسمها الخادم — لا تُعاد هنا. */
  stock_status?: string | null;
  /** المتاح بعد الحجز (عقد المنتقي يرسله بجانب الرصيد). */
  available_quantity?: string | number | null;
  is_service?: boolean | null;
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  products: SalesProductPickerItem[];
  initialSearch?: string;
  onSelect: (productId: number) => void;
};

/** عنوان مقروء للعرض — الاسم أولاً، وليس الـ SKU الطويل كعنوان رئيسي */
export function formatProductPrimaryName(p: SalesProductPickerItem & { display_name?: string }): string {
  if (p.display_name) return p.display_name;
  const ar = (p.name_ar || "").trim();
  const en = (p.name_en || "").trim();
  const n = ((p as any).name || "").trim();
  if (ar && en) return `${ar} — ${en}`;
  if (ar) return ar;
  if (en) return en;
  if (n) return n;
  return p.sku || `منتج #${p.id}`;
}

function formatProductMeta(p: SalesProductPickerItem): string {
  const parts: string[] = [];
  const sku = (p.sku || "").trim();
  if (sku) parts.push(`SKU: ${sku.length > 40 ? sku.slice(0, 38) + "…" : sku}`);
  if (p.barcode?.trim()) parts.push(`BC: ${p.barcode.trim()}`);
  return parts.join(" · ");
}

export const SalesProductPickerModal: React.FC<Props> = ({
  isOpen,
  onClose,
  products,
  initialSearch = "",
  onSelect,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showAddModal, setShowAddModal] = useState(false);
  const activeItemRef = React.useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSearchTerm(initialSearch);
      setSelectedIndex(0);
    }
  }, [isOpen, initialSearch]);

  const filtered = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    const result = q
      ? products.filter((p) => {
          const sku = (p.sku || "").toLowerCase();
          const bar = (p.barcode || "").toLowerCase();
          const n = `${p.name_ar || ""} ${p.name_en || ""}`.toLowerCase();
          return sku.includes(q) || bar.includes(q) || bar === q || n.includes(q);
        })
      : products;
    return result.slice(0, 400);
  }, [products, searchTerm]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [filtered]);

  useEffect(() => {
    if (!isOpen) return;
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (filtered.length > 0 ? (prev + 1) % filtered.length : 0));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (filtered.length > 0 ? (prev - 1 + filtered.length) % filtered.length : 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filtered.length > 0 && selectedIndex >= 0 && selectedIndex < filtered.length) {
          onSelect(filtered[selectedIndex].id);
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [isOpen, filtered, selectedIndex, onSelect, onClose]);

  useEffect(() => {
    if (activeItemRef.current) {
      activeItemRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [selectedIndex]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      dir="rtl"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="ktra-bg-field dark:ktra-bg-panel rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col border ktra-border-soft dark:ktra-border-soft">
        <div className="p-4 border-b ktra-border-soft dark:ktra-border-soft flex justify-between items-start gap-3 ktra-bg-panel/80 dark:ktra-bg-panel/40 rounded-t-2xl">
          <div>
            <h3 className="text-lg font-bold ktra-text-ink dark:text-white flex items-center gap-2">
              <Package className="w-5 h-5 ktra-text-soft" />
              اختيار المنتج
            </h3>
            <p className="text-xs ktra-text-soft dark:ktra-text-soft mt-1">
              ابحث بالاسم أو SKU أو الباركود، واستخدم الأسهم والـ Enter أو اضغط على البطاقة.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:ktra-bg-grid-head/80 dark:hover:ktra-bg-panel rounded-full transition-colors"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5 ktra-text-soft" />
          </button>
        </div>

        <div className="p-3 border-b ktra-border-soft dark:ktra-border-soft">
          <div className="relative flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 ktra-text-soft" />
              <input
                type="text"
                autoFocus
                placeholder="بحث: اسم، SKU، باركود..."
                className="w-full pl-3 pr-10 py-2.5 ktra-bg-panel dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <button
              type="button"
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-1 px-3 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-medium transition-colors whitespace-nowrap"
            >
              <Plus className="w-4 h-4" /> إضافة منتج
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 ktra-bg-panel/50 dark:bg-black/20 min-h-[200px]">
          {filtered.length === 0 ? (
            <div className="text-center py-12 ktra-text-soft text-sm">لا توجد نتائج. جرّب كلمات أخرى.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {filtered.map((p, idx) => {
                // T-REORDER: كانت هنا نسخةٌ رابعة من قاعدة «منخفض» (qty <= 0)،
                // وكانت تعرض الرصيد تحت عنوان «متاح» — رقمان مختلفان لاسمٍ واحد.
                // الحالة الآن من الخادم، والرقم هو المتاح فعلاً.
                const qty = availableOf(p);
                const badge = stockBadgeFor(p);
                return (
                  <button
                    key={p.id}
                    ref={idx === selectedIndex ? activeItemRef : undefined}
                    type="button"
                    onClick={() => {
                      onSelect(p.id);
                      onClose();
                    }}
                    className={`text-right rounded-xl border p-3 transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
                      idx === selectedIndex
                        ? "border-emerald-500 ring-2 ring-emerald-500 ktra-bg-panel/40"
                        : "ktra-border-soft dark:ktra-border-soft ktra-bg-field dark:ktra-bg-panel hover:ktra-border-soft hover:shadow-md dark:hover:ktra-border-soft"
                    }`}
                  >
                    <div className="font-semibold ktra-text-ink dark:text-white text-sm leading-snug line-clamp-2">
                      {formatProductPrimaryName(p)}
                    </div>
                    {formatProductMeta(p) && (
                      <div className="text-[11px] ktra-text-soft dark:ktra-text-soft mt-1 font-mono line-clamp-1">
                        {formatProductMeta(p)}
                      </div>
                    )}
                    <div className="flex justify-between items-center mt-2 pt-2 border-t ktra-border-soft dark:ktra-border-soft">
                      <span className="text-xs font-mono px-2 py-0.5 rounded ktra-bg-panel ktra-text-ink dark:ktra-bg-panel/30 dark:ktra-text-soft">
                        متاح: {formatQuantity(qty)}
                      </span>
                      {badge && (
                        <span
                          title={badge.title}
                          className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
                            badge.tone === "danger"
                              ? "bg-[var(--ktra-danger-bg)] border-[var(--ktra-danger-bd)] text-[var(--ktra-danger)]"
                              : "bg-[var(--ktra-warn-bg)] border-[var(--ktra-warn-bd)] text-[var(--ktra-warn-fg)]"
                          }`}
                        >{badge.text}</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          {products.length > 400 && searchTerm.trim() === "" && (
            <p className="text-center text-xs ktra-text-ink dark:ktra-text-soft py-2">
              يُعرض أول 400 منتج — استخدم البحث لضيق النتائج.
            </p>
          )}
        </div>

        <div className="p-3 border-t ktra-border-soft dark:ktra-border-soft flex justify-end rounded-b-2xl ktra-bg-field dark:ktra-bg-panel">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm ktra-text-soft dark:ktra-text-soft hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-lg"
          >
            إلغاء
          </button>
        </div>
      </div>
      {showAddModal && (
        <ItemQuickCreateModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onSaved={(newProduct) => {
            setShowAddModal(false);
            // Ideally we'd add it to the products list locally and select it
            // but since products is passed as prop, we can just trigger onSelect
            // and the parent should refetch products.
            onSelect(newProduct.id);
            onClose();
          }}
        />
      )}
    </div>
  );
};
