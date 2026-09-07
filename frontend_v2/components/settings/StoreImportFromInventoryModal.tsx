/**
 * «استيراد من الأصناف» — الجسر الوحيد المسموح بين المخزون والمتجر (مواصفة
 * #166 م٣): نسخٌ مرّةً واحدةً بلا علاقةٍ ولا مزامنة لاحقة. يفتح منتقيَ أصناف
 * متعدّد الاختيار، ويعرض النتيجة نصّاً واضحاً — بلا `alert`/`confirm` المتصفّح.
 */
import React, { useEffect, useMemo, useState } from "react";
import { Loader2, Package, Search, X } from "lucide-react";

import { listPickerProducts } from "../../services/inventoryApi";
import { formatProductPrimaryName } from "../../utils/productDisplayName";
import { humanizeThrown } from "../../utils/drfError";

type PickerRow = {
  id: number;
  sku?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onImport: (productIds: number[]) => void | Promise<void>;
  importing: boolean;
};

export const StoreImportFromInventoryModal: React.FC<Props> = ({
  isOpen, onClose, onImport, importing,
}) => {
  const [products, setProducts] = useState<PickerRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!isOpen) return;
    setSearch("");
    setSelected(new Set());
    setLoadError(null);
    setLoading(true);
    listPickerProducts<PickerRow>()
      .then(setProducts)
      .catch((e) => setLoadError(humanizeThrown(e, "تعذّر جلب أصناف المخزون")))
      .finally(() => setLoading(false));
  }, [isOpen]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return products;
    return products.filter((p) => {
      const name = `${p.name_ar || ""} ${p.name_en || ""}`.toLowerCase();
      const sku = (p.sku || "").toLowerCase();
      return name.includes(q) || sku.includes(q);
    });
  }, [products, search]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[65] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      dir="rtl"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
          <div>
            <h3 className="flex items-center gap-2 text-base font-black text-slate-900 dark:text-white">
              <Package className="h-5 w-5 text-blue-500" />
              استيراد من الأصناف
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              ينسخ الاسم والماركة والوحدة والسعر والوصف مرّةً واحدةً إلى كتالوج المتجر — بلا ربطٍ لاحق ولا مزامنة
            </p>
            <p className="mt-1 text-[11px] font-bold text-amber-700 dark:text-amber-400">
              المستورَد يصل بلا فئة — شجرة فئات المتجر ملكُك أنت، وعليك تصنيفه بنفسك بعد الاستيراد.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="my-3">
          <div className="relative">
            <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="بحث بالاسم أو رقم الصنف…"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2 pl-3 pr-9 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto rounded-2xl border border-slate-100 dark:border-slate-800">
          {loading ? (
            <div className="py-12 text-center text-slate-400">
              <Loader2 className="mx-auto h-6 w-6 animate-spin" />
              <span className="mt-2 block text-xs">جارٍ تحميل الأصناف…</span>
            </div>
          ) : loadError ? (
            <div className="py-12 text-center text-xs text-rose-600">{loadError}</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">لا أصنافٌ مطابقة.</div>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {filtered.slice(0, 400).map((p) => {
                const checked = selected.has(p.id);
                return (
                  <label
                    key={p.id}
                    className="flex cursor-pointer items-center gap-3 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(p.id)}
                      className="h-4 w-4 accent-blue-600"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-bold text-slate-900 dark:text-white">
                        {formatProductPrimaryName(p)}
                      </div>
                      {p.sku && (
                        <div className="truncate font-mono text-[10px] text-slate-400">{p.sku}</div>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
          <span className="text-xs font-bold text-slate-500 dark:text-slate-400">
            {selected.size} صنفٍ محدَّد
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={importing}
              className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
            >
              إلغاء
            </button>
            <button
              type="button"
              onClick={() => onImport(Array.from(selected))}
              disabled={importing || selected.size === 0}
              className="flex items-center gap-2 rounded-xl bg-blue-600 px-6 py-2 text-xs font-bold text-white shadow-md shadow-blue-600/20 hover:bg-blue-700 disabled:opacity-50"
            >
              {importing && <Loader2 className="h-4 w-4 animate-spin" />}
              <span>{importing ? "جارٍ الاستيراد…" : "استيراد المحدَّد"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StoreImportFromInventoryModal;
