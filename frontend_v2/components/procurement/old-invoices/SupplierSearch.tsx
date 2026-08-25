import React, { useState, useEffect, useRef } from "react";
import { Supplier, SupplierType } from "@/types";
import { Search, X, Check, Building, Factory, Ship, Globe, Store, Wrench, ChevronDown, UserPlus, Eye } from "lucide-react";

interface SupplierSearchProps {
  suppliers: Supplier[];
  selectedSupplierId: string;
  supplierSearch: string;
  onSearchChange: (value: string) => void;
  onSelectSupplier: (id: string) => void;
  onClearSupplier: () => void;
  onOpenAddModal?: () => void;
  type?: SupplierType;
  onViewSupplier?: (id: string) => void;
}

export const SupplierSearch: React.FC<SupplierSearchProps> = ({
  suppliers,
  selectedSupplierId,
  supplierSearch,
  onSearchChange,
  onSelectSupplier,
  onClearSupplier,
  onOpenAddModal,
  onViewSupplier,
  type,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // إغلاق القائمة عند النقر خارجها
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedSupplier = suppliers.find((s) => s.id === selectedSupplierId);

  // ✅ دالة للحصول على الاسم البارز (المستعار أولاً)
  const getDisplayName = (supplier: Supplier) => {
    // عرض الاسم المستعار أولاً إذا كان موجوداً
    if (supplier.alias && supplier.alias.trim() !== "") {
      return supplier.alias;
    }

    // إذا لم يكن هناك اسم مستعار، نعرض الاسم التجاري
    if (supplier.tradeName && supplier.tradeName.trim() !== "") {
      return supplier.tradeName;
    }

    return "";
  };

  // ✅ دالة للحصول على الاسم الفرعي — الاسم الآخر لا نسخة مكرّرة منه
  const getSubName = (supplier: Supplier) => {
    const alias = (supplier.alias || "").trim();
    const trade = (supplier.tradeName || "").trim();

    // إذا كان هناك اسم مستعار (وهو المعروض)، نعرض الاسم الرسمي كاسم فرعي
    if (alias && trade && alias !== trade) return trade;

    // إذا لم يكن هناك اسم مستعار، لا نعرض شيئاً كاسم فرعي
    return "";
  };

  // ✅ تصفية الموردين بناءً على البحث + النوع
  const filteredSuppliers = suppliers.filter((s) => {
    // الاسمان مستقلان (`name` و`legal_name`)، فالبحث يطابقهما معاً — البحث
    // بالاسم العربي يجب أن يجد المورد ولو كان المعروض اسمه الأجنبي.
    const term = supplierSearch.toLowerCase();
    const matchesSearch =
      (s.alias?.toLowerCase() || "").includes(term) ||
      (s.tradeName?.toLowerCase() || "").includes(term)

    // شرط النوع (إذا تم تمرير type)
    const matchesType = type ? s.type === type : true;

    return matchesSearch && matchesType;
  });

  // أيقونة النوع
  const getTypeIcon = (supplierType?: SupplierType) => {
    switch (supplierType) {
      case "factory": return <Factory className="w-3.5 h-3.5" />;
      case "shipping_agent": return <Ship className="w-3.5 h-3.5" />;
      default: return <Building className="w-3.5 h-3.5" />;
    }
  };

  return (
    <div className="relative w-full" ref={containerRef}>
      {/* 1. منطقة الإدخال / العرض */}
      <div
        className={`
          relative flex items-center w-full border rounded-lg ktra-bg-field dark:ktra-bg-panel transition-all
          ${isOpen ? 'ktra-border-soft ring-1 ring-blue-500' : 'ktra-border-soft dark:ktra-border-soft'}
        `}
      >
        {selectedSupplier ? (
          // --- حالة تم اختيار مورد (يظهر داخل المربع) ---
          <div className="flex items-center justify-between w-full p-2 pl-3">
            <div className="flex items-center gap-2 overflow-hidden">
              <span className="p-1 ktra-bg-accent-bg dark:ktra-bg-panel/30 rounded ktra-text-accent dark:ktra-text-soft">
                {getTypeIcon(selectedSupplier.type)}
              </span>
              <div className="flex flex-col truncate">
                {/* ✅ عرض الاسم البارز (المستعار أولاً) */}
                <span className="text-sm font-semibold ktra-text-ink dark:text-white truncate">
                  {getDisplayName(selectedSupplier)}
                </span>

                {/* ✅ عرض الاسم الفرعي (إذا كان مختلفاً عن البارز) */}
                {getSubName(selectedSupplier) && (
                  <span className="text-[10px] ktra-text-soft truncate">
                    {getSubName(selectedSupplier)}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1">
              {/* زر عرض بيانات المورد */}
              {onViewSupplier && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewSupplier(selectedSupplier.id);
                  }}
                  className="p-1.5 hover:ktra-bg-accent-bg dark:hover:ktra-bg-panel/20 ktra-text-accent dark:ktra-text-soft hover:ktra-text-accent dark:hover:ktra-text-soft rounded-md transition-colors"
                  title="عرض بيانات المورد"
                >
                  <Eye className="w-4 h-4" />
                </button>
              )}

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onClearSupplier();
                  if (inputRef.current) inputRef.current.focus();
                }}
                className="p-1.5 hover:ktra-bg-panel dark:hover:ktra-bg-panel/20 ktra-text-soft hover:ktra-text-soft dark:hover:ktra-text-soft rounded-md transition-colors"
                title="إزالة المورد"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        ) : (
          // --- حالة البحث (حقل إدخال) ---
          <>
            <Search className="w-4 h-4 ktra-text-soft absolute right-3 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              placeholder="ابحث عن مورد..."
              value={supplierSearch}
              onChange={(e) => {
                onSearchChange(e.target.value);
                setIsOpen(true);
              }}
              onFocus={() => setIsOpen(true)}
              className="w-full h-10 pr-9 pl-3 text-sm bg-transparent border-none outline-none ktra-text-ink dark:text-white placeholder:ktra-text-soft rounded-lg"
            />
            <ChevronDown className={`w-4 h-4 ktra-text-soft absolute left-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </>
        )}
      </div>

      {/* 2. القائمة المنسدلة (Dropdown) */}
      {isOpen && !selectedSupplier && (
        <div className="absolute z-50 w-full mt-1 ktra-bg-field dark:ktra-bg-panel border ktra-border-soft dark:ktra-border-soft rounded-lg shadow-lg max-h-60 overflow-y-auto">
          {filteredSuppliers.length > 0 ? (
            <ul className="py-1">
              {filteredSuppliers.map((supplier) => {
                const displayName = getDisplayName(supplier);
                const subName = getSubName(supplier);

                return (
                  <li
                    key={supplier.id}
                    onClick={() => {
                      onSelectSupplier(supplier.id);
                      setIsOpen(false);
                    }}
                    className="px-3 py-2 flex items-center justify-between hover:ktra-bg-panel dark:hover:ktra-bg-panel cursor-pointer group transition-colors border-b ktra-border-soft dark:ktra-border-soft/50 last:border-0"
                  >
                    <div className="flex items-center gap-2.5 flex-1">
                      <span className="ktra-text-soft group-hover:ktra-text-soft transition-colors">
                        {getTypeIcon(supplier.type)}
                      </span>
                      <div className="min-w-0 flex-1">
                        {/* ✅ عرض الاسم البارز (المستعار أولاً) */}
                        <p className="text-sm font-medium ktra-text-ink dark:ktra-text-soft group-hover:ktra-text-accent dark:group-hover:ktra-text-soft truncate">
                          {displayName}
                        </p>

                        {/* ✅ عرض الاسم الفرعي (إذا كان مختلفاً) */}
                        {subName && (
                          <p className="text-xs ktra-text-soft truncate">{subName}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {supplier.country && (
                        <span className="text-[10px] ktra-bg-panel dark:ktra-bg-panel ktra-text-soft px-1.5 py-0.5 rounded flex-shrink-0">
                          {supplier.country}
                        </span>
                      )}

                      {/* زر عرض المورد في القائمة */}
                      {onViewSupplier && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onViewSupplier(supplier.id);
                          }}
                          className="p-1 opacity-0 group-hover:opacity-100 ktra-text-soft hover:ktra-text-accent dark:hover:ktra-text-soft transition-opacity"
                          title="عرض بيانات المورد"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="p-3 text-center ktra-text-soft dark:ktra-text-soft text-sm">
              <p>لا توجد نتائج</p>
              {onOpenAddModal && (
                <button
                  onClick={onOpenAddModal}
                  className="mt-2 ktra-text-accent hover:underline text-xs flex items-center justify-center gap-1 w-full"
                >
                  <UserPlus className="w-3 h-3" /> إضافة مورد جديد
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};