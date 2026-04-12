import React, { useEffect, useState, useRef } from "react";
import { Supplier, Invoice } from "../../types";
import {
  suppliersService,
  invoicesService,
} from "../../services/firestoreService";
import { LoadingSpinner } from "../LoadingSpinner";
import { SupplierRelatedInvoices } from "./SupplierRelatedInvoices";
import { SupplierRelatedItems } from "./SupplierRelatedItems";
import {
  getInvoicesBySupplier,
  getItemsBySupplier,
} from "../../services/supplierServiceHelpers";
import { SupplierModal } from "../common/SupplierModal";
import {
  Plus,
  Search,
  MoreHorizontal,
  Building,
  Edit2,
  Trash2,
  FileText,
  Package,
  Tag,
} from "lucide-react";
import { getSupplierTypeLabel } from "../../constants/supplierConstants";

export interface SupplierManagementProps {
  /** فتح مورد محدد (مثلاً من شجرة الحسابات) */
  initialPartnerId?: number | null;
  onInitialPartnerConsumed?: () => void;
}

export const SupplierManagement: React.FC<SupplierManagementProps> = ({
  initialPartnerId,
  onInitialPartnerConsumed,
}) => {
  // Data State
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);

  // UI State
  const [viewMode, setViewMode] = useState<"list" | "invoices" | "items">("list");
  const [searchTerm, setSearchTerm] = useState("");

  // Selection State
  const [selectedSupplierForView, setSelectedSupplierForView] = useState<Supplier | null>(null);
  const [actionModalSupplier, setActionModalSupplier] = useState<Supplier | null>(null);

  // Modal State
  const [showSupplierModal, setShowSupplierModal] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState<Supplier | null>(null);

  useEffect(() => {
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
    const unsubInvoices = invoicesService.subscribeToInvoices(setInvoices);

    // Simulate loading delay
    setTimeout(() => setLoading(false), 500);

    return () => {
      unsubSuppliers();
      unsubInvoices();
    };
  }, []);

  const consumedPartnerFocus = useRef<number | null>(null);
  useEffect(() => {
    if (initialPartnerId == null) {
      consumedPartnerFocus.current = null;
      return;
    }
    if (!suppliers.length) return;
    if (consumedPartnerFocus.current === initialPartnerId) return;
    const match = suppliers.find((s) => Number(s.id) === Number(initialPartnerId));
    if (match) {
      setSelectedSupplierForView(match);
      setViewMode("list");
      consumedPartnerFocus.current = initialPartnerId;
      onInitialPartnerConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPartnerId, suppliers]);

  // --- Actions ---

  const handleCreateNew = () => {
    setEditingSupplier(null);
    setShowSupplierModal(true);
    setActionModalSupplier(null);
  };

  const handleEdit = (supplier: Supplier) => {
    setEditingSupplier(supplier);
    setShowSupplierModal(true);
    setActionModalSupplier(null);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("هل أنت متأكد من حذف هذا المورد؟")) return;
    try {
      await suppliersService.deleteSupplierFromDb(id);
      setActionModalSupplier(null);
    } catch (error) {
      console.error("Error deleting supplier:", error);
      alert("فشل الحذف");
    }
  };

  const handleViewInvoices = (supplier: Supplier) => {
    setSelectedSupplierForView(supplier);
    setViewMode("invoices");
    setActionModalSupplier(null);
  };

  const handleViewItems = (supplier: Supplier) => {
    setSelectedSupplierForView(supplier);
    setViewMode("items");
    setActionModalSupplier(null);
  };

  const filteredSuppliers = suppliers.filter(
    (s) =>
      s.tradeName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (s.alias || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.supplierId?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.salesRepName?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) return <LoadingSpinner />;

  // --- Sub Views ---

  if (viewMode === "invoices" && selectedSupplierForView) {
    const supplierInvoices = getInvoicesBySupplier(
      invoices,
      selectedSupplierForView.id
    );
    return (
      <SupplierRelatedInvoices
        supplier={selectedSupplierForView}
        invoices={supplierInvoices}
        onBack={() => setViewMode("list")}
      />
    );
  }

  if (viewMode === "items" && selectedSupplierForView) {
    const supplierItems = getItemsBySupplier(invoices, selectedSupplierForView.id);
    return (
      <SupplierRelatedItems
        supplier={selectedSupplierForView}
        data={supplierItems}
        onBack={() => setViewMode("list")}
      />
    );
  }

  // --- List View ---
  return (
    <div className="space-y-6 p-4 md:p-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          إدارة الموردين
        </h1>
        <button
          onClick={handleCreateNew}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" /> إضافة مورد جديد
        </button>
      </div>

      <div className="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="relative">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder="بحث بالاسم التجاري أو رقم المورد أو اسم المندوب..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pr-10 pl-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-900"
          />
        </div>
      </div>

      {filteredSuppliers.length === 0 && suppliers.length > 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <div className="text-gray-500 dark:text-gray-400">
            لا توجد نتائج مطابقة للبحث
          </div>
        </div>
      ) : filteredSuppliers.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <div className="text-gray-500 dark:text-gray-400">
            لا توجد موردين بعد. قم بإضافة مورد جديد.
          </div>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900/50">
                <tr>
                  <th className="px-6 py-4 w-16">#</th>
                  <th className="px-6 py-4">الشعار</th>
                  <th className="px-6 py-4">اسم المورد</th> {/* تغيير هنا */}
                  <th className="px-6 py-4">النوع</th>
                  <th className="px-6 py-4">رقم المورد</th>
                  <th className="px-6 py-4">الجوال</th>
                  <th className="px-6 py-4">البريد الإلكتروني</th>
                  <th className="px-6 py-4">الرصيد</th>
                  <th className="px-6 py-4"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                {filteredSuppliers.map((supplier, index) => (
                  (() => {
                    const legalName = (supplier as any).legalName || (supplier as any).legal_name || "";
                    const primaryName = supplier.alias || legalName || supplier.tradeName;
                    const secondaryName =
                      primaryName !== supplier.tradeName && supplier.tradeName ? supplier.tradeName : "";
                    return (
                  <tr
                    key={supplier.id}
                    className="group hover:bg-gray-50 dark:hover:bg-gray-700/30 cursor-pointer"
                    onClick={() => setActionModalSupplier(supplier)}
                  >
                    <td className="px-6 py-4 text-gray-500">{index + 1}</td>
                    <td className="px-6 py-4">
                      {supplier.logoUrl ? (
                        <img
                          src={supplier.logoUrl}
                          alt=""
                          className="w-10 h-10 rounded-full object-cover border"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
                          <Building className="w-5 h-5 text-gray-400" />
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col">
                        {/* الأولوية: مستعار -> قانوني -> عادي */}
                        <span className="font-medium text-gray-900 dark:text-white">
                          {primaryName}
                        </span>
                        {secondaryName && (
                          <span className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                            {secondaryName}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${supplier.type === 'factory' || !supplier.type ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                        supplier.type === 'shipping_agent' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' :
                          supplier.type === 'international_trader' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' :
                            supplier.type === 'local_company' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                              'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400'
                        }`}>
                        {getSupplierTypeLabel(supplier.type || 'factory')}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-mono text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                        {supplier.supplierId}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-400">
                      {supplier.mobile || "-"}
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-400">
                      {supplier.email || "-"}
                    </td>
                    <td className="px-6 py-4 font-medium text-green-600 dark:text-green-400">
                      {supplier.openingBalance} {supplier.currency || "ILS"}
                    </td>
                    <td className="px-6 py-4 text-left">
                      <MoreHorizontal className="w-5 h-5 text-gray-400 group-hover:text-blue-500 transition-colors" />
                    </td>
                  </tr>
                    );
                  })()
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Action Modal (Dropdown-like) */}
      {actionModalSupplier && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setActionModalSupplier(null)}
        >
          <div
            className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-sm overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex justify-between items-center">
              <h3 className="font-bold text-gray-900 dark:text-white truncate">
                {actionModalSupplier.tradeName}
              </h3>
            </div>
            <div className="p-2">
              <button
                onClick={() => handleEdit(actionModalSupplier)}
                className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-gray-700 dark:text-gray-300 transition-colors"
              >
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg text-blue-600 dark:text-blue-400">
                  <Edit2 className="w-5 h-5" />
                </div>
                <div className="text-right">
                  <div className="font-medium">تعديل البيانات</div>
                  <div className="text-xs text-gray-500">تحديث معلومات المورد</div>
                </div>
              </button>

              <button
                onClick={() => handleViewInvoices(actionModalSupplier)}
                className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-gray-700 dark:text-gray-300 transition-colors"
              >
                <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg text-purple-600 dark:text-purple-400">
                  <FileText className="w-5 h-5" />
                </div>
                <div className="text-right">
                  <div className="font-medium">سجل الفواتير</div>
                  <div className="text-xs text-gray-500">عرض فواتير المورد السابقة</div>
                </div>
              </button>

              <button
                onClick={() => handleViewItems(actionModalSupplier)}
                className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-gray-700 dark:text-gray-300 transition-colors"
              >
                <div className="p-2 bg-orange-100 dark:bg-orange-900/30 rounded-lg text-orange-600 dark:text-orange-400">
                  <Package className="w-5 h-5" />
                </div>
                <div className="text-right">
                  <div className="font-medium">الأصناف الموردة</div>
                  <div className="text-xs text-gray-500">تحليل المشتريات من هذا المورد</div>
                </div>
              </button>

              <div className="h-px bg-gray-200 dark:bg-gray-700 my-2"></div>

              <button
                onClick={() => handleDelete(actionModalSupplier.id)}
                className="w-full flex items-center gap-3 p-3 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg text-red-600 transition-colors"
              >
                <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg text-red-600">
                  <Trash2 className="w-5 h-5" />
                </div>
                <div className="text-right">
                  <div className="font-medium">حذف المورد</div>
                  <div className="text-xs text-red-400">حذف نهائي من السجلات</div>
                </div>
              </button>
            </div>
            <div className="p-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
              <button
                onClick={() => setActionModalSupplier(null)}
                className="w-full py-2 text-center text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-sm font-medium"
              >
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Shared Supplier Modal */}
      <SupplierModal
        isOpen={showSupplierModal}
        onClose={() => {
          setShowSupplierModal(false);
          setEditingSupplier(null);
        }}
        editingSupplier={editingSupplier}
        onSaveSuccess={() => {
          // Subscription auto-updates list
          setShowSupplierModal(false);
          setEditingSupplier(null);
        }}
      />
    </div>
  );
};
