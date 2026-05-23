import React, { useMemo, useState, useEffect } from "react";
import { Search, X, Package } from "lucide-react";

/** نفس حقول المنتج في فاتورة المبيعات — منفصل لتفادي تبعية دائرية */
export type SalesProductPickerItem = {
  id: number;
  sku: string;
  barcode?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  quantity_on_hand: string;
  online_price?: string | null;
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  products: SalesProductPickerItem[];
  initialSearch?: string;
  onSelect: (productId: number) => void;
};

/** عنوان مقروء للعرض — الاسم أولاً، وليس الـ SKU الطويل كعنوان رئيسي */
export function formatProductPrimaryName(p: SalesProductPickerItem): string {
  const ar = (p.name_ar || "").trim();
  const en = (p.name_en || "").trim();
  if (ar && en) return `${ar} — ${en}`;
  if (ar) return ar;
  if (en) return en;
  return p.sku || `صنف #${p.id}`;
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

  useEffect(() => {
    if (isOpen) setSearchTerm(initialSearch);
  }, [isOpen, initialSearch]);

  const filtered = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    if (!q) return products.slice(0, 400);
    return products
      .filter((p) => {
        const sku = (p.sku || "").toLowerCase();
        const bar = (p.barcode || "").toLowerCase();
        const n = `${p.name_ar || ""} ${p.name_en || ""}`.toLowerCase();
        return sku.includes(q) || bar.includes(q) || bar === q || n.includes(q);
      })
      .slice(0, 400);
  }, [products, searchTerm]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      dir="rtl"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="aseel-bg-field dark:aseel-bg-panel rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col border aseel-border-soft dark:aseel-border-soft">
        <div className="p-4 border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-start gap-3 aseel-bg-panel/80 dark:aseel-bg-panel/40 rounded-t-2xl">
          <div>
            <h3 className="text-lg font-bold aseel-text-ink dark:text-white flex items-center gap-2">
              <Package className="w-5 h-5 aseel-text-soft" />
              اختيار الصنف
            </h3>
            <p className="text-xs aseel-text-soft dark:aseel-text-soft mt-1">
              ابحث بالاسم أو SKU أو الباركود، ثم اضغط على البطاقة لاختيار الصنف.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:aseel-bg-grid-head/80 dark:hover:aseel-bg-panel rounded-full transition-colors"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5 aseel-text-soft" />
          </button>
        </div>

        <div className="p-3 border-b aseel-border-soft dark:aseel-border-soft">
          <div className="relative">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 aseel-text-soft" />
            <input
              type="text"
              autoFocus
              placeholder="بحث: اسم، SKU، باركود..."
              className="w-full pl-3 pr-10 py-2.5 aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") onClose();
              }}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 aseel-bg-panel/50 dark:bg-black/20 min-h-[200px]">
          {filtered.length === 0 ? (
            <div className="text-center py-12 aseel-text-soft text-sm">لا توجد نتائج. جرّب كلمات أخرى.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {filtered.map((p) => {
                const qty = Number(p.quantity_on_hand);
                const low = qty <= 0;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      onSelect(p.id);
                      onClose();
                    }}
                    className="text-right rounded-xl border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel p-3 hover:aseel-border-soft hover:shadow-md dark:hover:aseel-border-soft transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <div className="font-semibold aseel-text-ink dark:text-white text-sm leading-snug line-clamp-2">
                      {formatProductPrimaryName(p)}
                    </div>
                    {formatProductMeta(p) && (
                      <div className="text-[11px] aseel-text-soft dark:aseel-text-soft mt-1 font-mono line-clamp-1">
                        {formatProductMeta(p)}
                      </div>
                    )}
                    <div className="flex justify-between items-center mt-2 pt-2 border-t aseel-border-soft dark:aseel-border-soft">
                      <span
                        className={`text-xs font-mono px-2 py-0.5 rounded ${
                          low
                            ? "aseel-bg-panel aseel-text-state dark:aseel-bg-panel/30 dark:aseel-text-soft"
                            : "aseel-bg-panel aseel-text-ink dark:aseel-bg-panel/30 dark:aseel-text-soft"
                        }`}
                      >
                        متاح: {qty.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          {products.length > 400 && searchTerm.trim() === "" && (
            <p className="text-center text-xs aseel-text-ink dark:aseel-text-soft py-2">
              يُعرض أول 400 صنف — استخدم البحث لضيق النتائج.
            </p>
          )}
        </div>

        <div className="p-3 border-t aseel-border-soft dark:aseel-border-soft flex justify-end rounded-b-2xl aseel-bg-field dark:aseel-bg-panel">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm aseel-text-soft dark:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg"
          >
            إلغاء
          </button>
        </div>
      </div>
    </div>
  );
};
