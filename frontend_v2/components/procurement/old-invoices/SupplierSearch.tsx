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

    // كخيار أخير نعرض الاسم الأساسي
    return supplier.tradeName || "";
  };

  // ✅ دالة للحصول على الاسم الفرعي
  const getSubName = (supplier: Supplier) => {
    // إذا كان هناك اسم مستعار، نعرض الاسم التجاري كاسم فرعي
    if (supplier.alias && supplier.alias.trim() !== "") {
      return supplier.tradeName || "";
    }

    // إذا لم يكن هناك اسم مستعار، لا نعرض شيئاً كاسم فرعي
    return "";
  };

  // ✅ تصفية الموردين بناءً على البحث + النوع
  const filteredSuppliers = suppliers.filter((s) => {
    // البحث في الاسم البارز (المستعار) والاسم التجاري
    const matchesSearch =
      getDisplayName(s).toLowerCase().includes(supplierSearch.toLowerCase()) ||
      (s.tradeName?.toLowerCase() || "").includes(supplierSearch.toLowerCase())

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
          relative flex items-center w-full border rounded-lg bg-white dark:bg-gray-800 transition-all
          ${isOpen ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-300 dark:border-gray-600'}
        `}
      >
        {selectedSupplier ? (
          // --- حالة تم اختيار مورد (يظهر داخل المربع) ---
          <div className="flex items-center justify-between w-full p-2 pl-3">
            <div className="flex items-center gap-2 overflow-hidden">
              <span className="p-1 bg-blue-100 dark:bg-blue-900/30 rounded text-blue-600 dark:text-blue-400">
                {getTypeIcon(selectedSupplier.type)}
              </span>
              <div className="flex flex-col truncate">
                {/* ✅ عرض الاسم البارز (المستعار أولاً) */}
                <span className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                  {getDisplayName(selectedSupplier)}
                </span>

                {/* ✅ عرض الاسم الفرعي (إذا كان مختلفاً عن البارز) */}
                {getSubName(selectedSupplier) && (
                  <span className="text-[10px] text-gray-500 truncate">
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
                  className="p-1.5 hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 rounded-md transition-colors"
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
                className="p-1.5 hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-400 hover:text-red-500 dark:hover:text-red-400 rounded-md transition-colors"
                title="إزالة المورد"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        ) : (
          // --- حالة البحث (حقل إدخال) ---
          <>
            <Search className="w-4 h-4 text-gray-400 absolute right-3 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              placeholder={type === 'factory' ? "ابحث عن مصنع..." : "ابحث عن مورد..."}
              value={supplierSearch}
              onChange={(e) => {
                onSearchChange(e.target.value);
                setIsOpen(true);
              }}
              onFocus={() => setIsOpen(true)}
              className="w-full h-10 pr-9 pl-3 text-sm bg-transparent border-none outline-none text-gray-900 dark:text-white placeholder:text-gray-400 rounded-lg"
            />
            <ChevronDown className={`w-4 h-4 text-gray-400 absolute left-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </>
        )}
      </div>

      {/* 2. القائمة المنسدلة (Dropdown) */}
      {isOpen && !selectedSupplier && (
        <div className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-60 overflow-y-auto">
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
                    className="px-3 py-2 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer group transition-colors border-b border-gray-100 dark:border-gray-700/50 last:border-0"
                  >
                    <div className="flex items-center gap-2.5 flex-1">
                      <span className="text-gray-400 group-hover:text-blue-500 transition-colors">
                        {getTypeIcon(supplier.type)}
                      </span>
                      <div className="min-w-0 flex-1">
                        {/* ✅ عرض الاسم البارز (المستعار أولاً) */}
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-200 group-hover:text-blue-600 dark:group-hover:text-blue-400 truncate">
                          {displayName}
                        </p>

                        {/* ✅ عرض الاسم الفرعي (إذا كان مختلفاً) */}
                        {subName && (
                          <p className="text-xs text-gray-400 truncate">{subName}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {supplier.country && (
                        <span className="text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-500 px-1.5 py-0.5 rounded flex-shrink-0">
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
                          className="p-1 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-opacity"
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
            <div className="p-3 text-center text-gray-500 dark:text-gray-400 text-sm">
              <p>لا توجد نتائج {type === 'factory' ? ' (مصانع)' : ''}</p>
              {onOpenAddModal && (
                <button
                  onClick={onOpenAddModal}
                  className="mt-2 text-blue-600 hover:underline text-xs flex items-center justify-center gap-1 w-full"
                >
                  <UserPlus className="w-3 h-3" /> إضافة {type === 'factory' ? 'مصنع' : 'مورد'} جديد
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};