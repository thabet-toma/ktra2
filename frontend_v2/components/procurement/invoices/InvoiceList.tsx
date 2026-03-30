import React, { useState, useMemo, useEffect } from "react";
import { Invoice, Item, Supplier } from "@/types";
import {
  Plus,
  Search,
  Filter,
  SortAsc,
  SortDesc,
  FileText,
  Calendar,
  DollarSign,
  ChevronDown,
  ChevronUp,
  Edit,
  Trash2,
  Building,
  User,
  Package,
  Truck,
  Clock,
  CheckCircle2,
  AlertCircle,
  Factory,
  Percent,
  TrendingUp,
  History,
  Activity,
  Box,
  Layers,
  Wallet,
  Eye,
  ArrowRightLeft,
  Coins,
  Printer,
  ArrowUpRight,
} from "lucide-react";

interface InvoiceListProps {
  invoices: Invoice[];
  onEdit: (invoice: Invoice) => void;
  onView: (invoice: Invoice) => void;
  onPrint: (invoice: Invoice) => void; // 🟢 إضافة خاصية الطباعة
  onDelete: (id: string) => void;
  onConvertToDeal: (invoice: Invoice) => void; // ⭐ 2. إضافة خاصية دالة التحويل
  items: Item[];
  suppliers: Supplier[];
}

export const InvoiceList: React.FC<InvoiceListProps> = ({
  invoices,
  onEdit,
  onView,
  onPrint, // ⭐ استقبال الدالة
  onDelete,
  onConvertToDeal, // ⭐ استقبال الدالة
  items,
  suppliers,
}) => {
  const [selectedInvoiceForDetails, setSelectedInvoiceForDetails] = useState<string | null>(null);
  const [expandedInvoices, setExpandedInvoices] = useState<Set<string>>(new Set());

  // فلاتر
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState<string>("");

  // ترتيب
  const [sortField, setSortField] = useState<"date" | "amount" | "number">("date");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  // ✅ Pagination states
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [itemsPerPage, setItemsPerPage] = useState<number>(20);

  // ── دالة معالجة الحذف مع التأكيد ──
  const handleDeleteClick = (id: string, invoiceNumber: string) => {
    const isConfirmed = window.confirm(
      `هل أنت متأكد من حذف الفاتورة رقم (${invoiceNumber}) نهائياً؟\n\nلا يمكن التراجع عن هذا الإجراء وسيتم فقدان جميع البيانات المرتبطة بها.`
    );

    if (isConfirmed) {
      onDelete(id);
    }
  };

  // ── دالة معالجة التحويل مع التأكيد ──
  const handleConvertClick = (invoice: Invoice) => {
    const isConfirmed = window.confirm(
      `هل تريد إنشاء صفقة شراء جديدة بناءً على بيانات الفاتورة رقم (${invoice.invoiceNumber})؟\n\nسيتم نسخ المنتجات والمورد والبيانات المالية إلى صفقة جديدة.`
    );

    if (isConfirmed) {
      onConvertToDeal(invoice);
    }
  };

  // ✅ دالة Pagination: تغيير الصفحة
  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const calculateInvoiceFinancials = (invoice: Invoice) => {
    const invoiceItems = invoice.items || [];
    let calculatedSubtotal = 0;

    if (invoiceItems.length > 0) {
      calculatedSubtotal = invoiceItems.reduce((sum, item) => {
        const qty = parseFloat(item.quantity as any) || 0;
        const price = parseFloat(item.unitPrice as any) || 0;
        return sum + qty * price;
      }, 0);
    } else {
      calculatedSubtotal = parseFloat(invoice.subtotal as any) || 0;
    }

    const discountAmount = parseFloat(invoice.discountAmount as any) || 0;
    const netAfterDiscount = Math.max(0, calculatedSubtotal - discountAmount);
    const taxRate = parseFloat(invoice.taxRate as any) || 0;
    const taxAmount = netAfterDiscount * (taxRate / 100);
    const shippingCost = invoice.shippingIncluded
      ? 0
      : parseFloat(invoice.shippingCost as any) || 0;

    const localPayments = invoice.localPayments || {};
    let totalLocalPayments = 0;

    if (localPayments.includedInPrice !== true) {
      if (localPayments.calculationMethod === 'lump_sum') {
        totalLocalPayments = parseFloat(localPayments.lumpSumAmount as any) || 0;
      } else if (localPayments.calculationMethod === 'detailed') {
        totalLocalPayments =
          (parseFloat(localPayments.customsClearanceFees as any) || 0) +
          (parseFloat(localPayments.customsDuties as any) || 0) +
          (parseFloat(localPayments.portFees as any) || 0) +
          (parseFloat(localPayments.internalShippingFees as any) || 0);
      }
    }

    const grandTotal = netAfterDiscount + taxAmount + shippingCost + totalLocalPayments;

    return {
      subtotal: calculatedSubtotal,
      taxAmount,
      grandTotal,
      discountAmount,
      taxRate,
      shippingCost,
      localPayments: totalLocalPayments,
      localPaymentsIncluded: localPayments.includedInPrice || false,
    };
  };

  const getInvoiceStatus = (invoice: Invoice): string => {
    if (!invoice.isHistorical) {
      if (invoice.status === "incomplete") return "incomplete";
      if (invoice.status === "completed") return "completed";
      if (invoice.status === "deposit_paid" ||
        invoice.status === "partially_paid" ||
        invoice.status === "fully_paid"
      ) {
        return "completed";
      }
    }
    return "incomplete";
  };

  const getStatusText = (status: string): string => {
    const statusMap: Record<string, string> = {
      incomplete: "غير مكتملة",
      completed: "مكتملة",
    };
    return statusMap[status] || status;
  };

  const getStatusStyles = (status: string): string => {
    const styles: Record<string, string> = {
      incomplete:
        "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800/50",
      completed:
        "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800/50",
    };
    return styles[status] || styles["incomplete"];
  };

  const getStatusIcon = (status: string): React.ReactNode => {
    const icons: Record<string, React.ReactNode> = {
      incomplete: <AlertCircle className="w-4 h-4 text-yellow-500" />,
      completed: <CheckCircle2 className="w-4 h-4 text-green-500" />,
    };
    return icons[status] || <AlertCircle className="w-4 h-4 text-yellow-500" />;
  };

  const filteredInvoices = useMemo(() => {
    return invoices.filter((invoice) => {
      if (invoice.isHistorical) return false;

      const invoiceDate = new Date(invoice.createdAt || "");
      if (dateFrom && invoiceDate < new Date(dateFrom)) return false;
      if (dateTo && invoiceDate > new Date(dateTo)) return false;

      const status = getInvoiceStatus(invoice);
      if (selectedStatus !== "all" && status !== selectedStatus) {
        return false;
      }

      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        const matchesNumber = invoice.invoiceNumber?.toLowerCase().includes(term);
        const matchesSupplier =
          invoice.supplierId?.toLowerCase().includes(term) ||
          suppliers?.find((s) => s.id === invoice.supplierId)?.tradeName?.toLowerCase().includes(term) ||
          suppliers?.find((s) => s.id === invoice.supplierId)?.alias?.toLowerCase().includes(term);
        const matchesName = invoice.invoiceName?.toLowerCase().includes(term);
        const matchesItems = invoice.items?.some((item) =>
          item.name?.toLowerCase().includes(term)
        );

        if (!matchesNumber && !matchesSupplier && !matchesName && !matchesItems) {
          return false;
        }
      }

      return true;
    });
  }, [invoices, dateFrom, dateTo, selectedStatus, searchTerm, suppliers]);

  const sortedInvoices = useMemo(() => {
    return [...filteredInvoices].sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case "date":
          // 🟢 التعديل هنا: استخدام invoiceDate كأولوية، وفي حال عدم وجوده نستخدم createdAt كاحتياط
          const dateA = new Date(a.invoiceDate || a.createdAt || "").getTime();
          const dateB = new Date(b.invoiceDate || b.createdAt || "").getTime();
          comparison = dateB - dateA;
          break;
        case "amount":
          const { grandTotal: amountA } = calculateInvoiceFinancials(a);
          const { grandTotal: amountB } = calculateInvoiceFinancials(b);
          comparison = amountB - amountA;
          break;
        case "number":
          const numA = a.invoiceNumber || "";
          const numB = b.invoiceNumber || "";
          comparison = numB.localeCompare(numA);
          break;
      }
      return sortDirection === "asc" ? -comparison : comparison;
    });
  }, [filteredInvoices, sortField, sortDirection]);

  const totalPages = Math.ceil(sortedInvoices.length / itemsPerPage);

  const paginatedInvoices = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    return sortedInvoices.slice(startIndex, endIndex);
  }, [sortedInvoices, currentPage, itemsPerPage]);

  useEffect(() => {
    setCurrentPage(1);
  }, [dateFrom, dateTo, selectedStatus, searchTerm, sortField, sortDirection]);

  const toggleInvoiceExpand = (invoiceId: string) => {
    setExpandedInvoices((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(invoiceId)) {
        newSet.delete(invoiceId);
      } else {
        newSet.add(invoiceId);
      }
      return newSet;
    });
  };

  const getSupplierDisplayName = (invoice: Invoice): string => {
    if (!suppliers || !invoice.supplierId) return "مورد غير محدد";
    const supplier = suppliers.find((s) => s.id === invoice.supplierId);
    if (!supplier) return "مورد غير محدد";
    return supplier.alias || supplier.tradeName || "مورد غير محدد";
  };

  const stats = useMemo(() => {
    return sortedInvoices.reduce(
      (acc, invoice) => {
        const { grandTotal } = calculateInvoiceFinancials(invoice);
        const status = getInvoiceStatus(invoice);

        return {
          totalAmount: acc.totalAmount + grandTotal,
          incompleteCount: acc.incompleteCount + (status === "incomplete" ? 1 : 0),
          completedCount: acc.completedCount + (status === "completed" ? 1 : 0),
        };
      },
      {
        totalAmount: 0,
        incompleteCount: 0,
        completedCount: 0,
      }
    );
  }, [sortedInvoices]);

  const resetAllFilters = () => {
    setDateFrom("");
    setDateTo("");
    setSelectedStatus("all");
    setSearchTerm("");
  };

  return (
    <div className="space-y-6">
      {/* لوحة الفلاتر */}
      <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 mb-4">
          <div className="flex items-center gap-2">
            <Filter className="w-5 h-5 text-slate-500" />
            <span className="font-medium text-slate-700 dark:text-slate-300">
              فلاتر البحث:
            </span>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setSortField("date")}
              className={`px-3 py-1.5 rounded-lg flex items-center gap-2 text-sm ${sortField === "date"
                ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                }`}
            >
              {sortField === "date" && sortDirection === "desc" ? (
                <SortDesc className="w-4 h-4" />
              ) : (
                <SortAsc className="w-4 h-4" />
              )}
              حسب التاريخ
            </button>
            <button
              onClick={() => setSortField("amount")}
              className={`px-3 py-1.5 rounded-lg flex items-center gap-2 text-sm ${sortField === "amount"
                ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                }`}
            >
              حسب المبلغ
            </button>
            <button
              onClick={() =>
                setSortDirection(sortDirection === "asc" ? "desc" : "asc")
              }
              className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg"
              title={sortDirection === "desc" ? "تنازلي" : "تصاعدي"}
            >
              {sortDirection === "desc" ? (
                <SortDesc className="w-4 h-4" />
              ) : (
                <SortAsc className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {/* فلاتر الجزء الأول */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              بحث سريع
            </label>
            <div className="relative">
              <Search className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="ابحث برقم الفاتورة، الاسم، المورد..."
                className="w-full p-2 pr-10 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              من تاريخ
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full p-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              إلى تاريخ
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full p-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex items-end">
            <button
              onClick={resetAllFilters}
              className="w-full py-2 bg-red-50 hover:bg-red-100 dark:bg-red-900/20 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400 rounded-lg font-medium"
            >
              إعادة تعيين جميع الفلاتر
            </button>
          </div>
        </div>

        {/* فلاتر الجزء الثاني */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              حالة الفاتورة
            </label>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full p-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              <option value="all">جميع الحالات</option>
              <option value="incomplete">غير مكتملة</option>
              <option value="completed">مكتملة</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
              المورد
            </label>
            <select
              className="w-full p-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              disabled
            >
              <option value="all">جميع الموردين</option>
            </select>
          </div>
        </div>

        {/* إحصائيات */}
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-blue-50 dark:bg-blue-900/10 p-3 rounded-lg border border-blue-100 dark:border-blue-800">
            <p className="text-xs text-blue-700 dark:text-blue-300 font-medium">
              عدد الفواتير
            </p>
            <p className="text-xl font-bold text-blue-900 dark:text-blue-100">
              {sortedInvoices.length}
            </p>
          </div>
          <div className="bg-yellow-50 dark:bg-yellow-900/10 p-3 rounded-lg border border-yellow-100 dark:border-yellow-800">
            <p className="text-xs text-yellow-700 dark:text-yellow-300 font-medium">
              غير مكتملة
            </p>
            <p className="text-xl font-bold text-yellow-900 dark:text-yellow-100">
              {stats.incompleteCount}
            </p>
          </div>
          <div className="bg-green-50 dark:bg-green-900/10 p-3 rounded-lg border border-green-100 dark:border-green-800">
            <p className="text-xs text-green-700 dark:text-green-300 font-medium">
              مكتملة
            </p>
            <p className="text-xl font-bold text-green-900 dark:text-green-100">
              {stats.completedCount}
            </p>
          </div>
        </div>
      </div>

      {/* معلومات العرض */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div className="text-sm text-slate-500 dark:text-slate-400">
          عرض {paginatedInvoices.length} فاتورة من أصل {sortedInvoices.length}
          {(dateFrom || dateTo || selectedStatus !== "all" || searchTerm) && (
            <span className="text-blue-600 dark:text-blue-400 font-medium">
              {" "}
              (مع فلاتر مطبقة)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <span>مرتبة حسب:</span>
          <span className="font-medium">
            {sortField === "date"
              ? "تاريخ الفاتورة"
              : sortField === "amount"
                ? "المبلغ الإجمالي"
                : "رقم الفاتورة"}
          </span>
          <span className="font-medium">
            ({sortDirection === "asc" ? "تصاعدي" : "تنازلي"})
          </span>
        </div>
      </div>

      {/* القائمة */}
      {paginatedInvoices.length > 0 ? (
        paginatedInvoices.map((invoice) => {
          const { grandTotal, subtotal, taxAmount, discountAmount } = calculateInvoiceFinancials(invoice);
          const status = getInvoiceStatus(invoice);
          const mainImage = invoice.items?.[0]?.imageUrls?.[0];
          const isExpanded = expandedInvoices.has(invoice.id);
          const supplierDisplayName = getSupplierDisplayName(invoice);

          return (
            <div
              key={invoice.id}
              className="group relative bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700/60 hover:border-blue-300 dark:hover:border-blue-700 transition-all duration-300 overflow-hidden"
            >
              {/* Header */}
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center p-3 gap-3 border-b border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="flex items-center justify-between w-full">

                  <div className="flex flex-col">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-sm font-bold text-slate-700 dark:text-slate-300">
                        رقم الفاتورة:
                      </span>
                      <span className="text-xs px-2 py-1 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800/50">
                        {invoice.invoiceNumber || "غير معروف"}
                      </span>
                      {invoice.invoiceName && (
                        <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                          {invoice.invoiceName}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <div className="flex items-center gap-2">
                        <div className={`px-3 py-1.5 rounded-lg text-sm font-semibold border flex items-center gap-2 shadow-sm ${getStatusStyles(status)}`}>
                          {getStatusIcon(status)}
                          <span>{getStatusText(status)}</span>
                        </div>
                      </div>
                      <span className="text-sm text-slate-500 dark:text-slate-400 flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {new Date(invoice.invoiceDate || "").toLocaleDateString("ar-EG")}
                      </span>
                      <span className="text-sm text-slate-500 dark:text-slate-400 flex items-center gap-1">
                        <Coins className="w-3 h-3" />
                        {invoice.currency === 'ILS' ? '₪' : '$'}
                        {grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </span>
                      {invoice.currency === 'ILS' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-600 border border-green-200 dark:bg-green-900/20 dark:border-green-800 flex items-center gap-1 font-bold">
                          <ArrowRightLeft className="w-2.5 h-2.5" />
                          محول للشيقل
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 🟢⭐ الأزرار (Buttons) */}
                  <div className="flex items-center gap-2">

                    {/* New Tab Button */}
                    <button
                      onClick={() => window.open(`${window.location.origin}?view=purchase-invoices&id=${invoice.id}`, '_blank')}
                      className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 dark:text-slate-400 dark:hover:text-blue-400 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                      title="فتح في نافذة جديدة"
                    >
                      <ArrowRightLeft className="w-5 h-5 rotate-45" />
                      {/* Using ArrowRightLeft rotated as we don't need to import new icon if not available, OR prefer adding ArrowUpRight to imports */}
                    </button>

                    {/* ⭐ زر التحويل إلى صفقة */}
                    <button
                      onClick={() => handleConvertClick(invoice)}
                      className="p-2 text-slate-500 hover:text-orange-600 hover:bg-orange-50 dark:text-slate-400 dark:hover:text-orange-400 dark:hover:bg-orange-900/30 rounded-lg transition-colors"
                      title="تحويل إلى صفقة شراء"
                    >
                      <ArrowRightLeft className="w-5 h-5" />
                    </button>

                    <button
                      onClick={() => onView(invoice)}
                      className="p-2 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 dark:text-slate-400 dark:hover:text-indigo-400 dark:hover:bg-indigo-900/30 rounded-lg transition-colors"
                      title="عرض التفاصيل"
                    >
                      <Eye className="w-5 h-5" />
                    </button>

                    <button
                      onClick={() => onPrint(invoice)}
                      className="p-2 text-slate-500 hover:text-blue-900 hover:bg-blue-50 dark:text-slate-400 dark:hover:text-blue-300 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                      title="طباعة الفاتورة"
                    >
                      <Printer className="w-5 h-5" />
                    </button>

                    <button
                      onClick={() => onEdit(invoice)}
                      className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 dark:text-slate-400 dark:hover:text-blue-400 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                      title="تعديل الفاتورة"
                    >
                      <Edit className="w-5 h-5" />
                    </button>

                    <button
                      onClick={() => handleDeleteClick(invoice.id, invoice.invoiceNumber)}
                      className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 dark:text-slate-400 dark:hover:text-red-400 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                      title="حذف نهائي"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>

                    <button
                      onClick={() => toggleInvoiceExpand(invoice.id)}
                      className="p-2 text-slate-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-gray-200 rounded-lg transition-colors border-r border-gray-200 dark:border-gray-700 pr-2 mr-1"
                    >
                      {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* المحتوى الموسع */}
              {isExpanded && (
                <div className="p-3 border-t border-slate-100 dark:border-slate-800/80">
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                    {/* معلومات المورد والصور */}
                    <div className="lg:col-span-7">
                      <div className="relative w-full sm:w-24 sm:h-24 h-40 bg-slate-100 dark:bg-slate-800 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700 flex-shrink-0">
                        {mainImage ? (
                          <img
                            src={mainImage}
                            alt="Invoice Item"
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center text-slate-400 dark:text-slate-500">
                            <Box className="w-6 h-6 mb-2 opacity-50" />
                            <span className="text-xs">لا توجد صورة</span>
                          </div>
                        )}
                      </div>

                      <div className="flex-1 space-y-2 mt-2">
                        <div>
                          <h4 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                            <User className="w-3 h-3 text-slate-400" />
                            {supplierDisplayName}
                          </h4>
                        </div>
                        {/* باقي التفاصيل... */}
                      </div>
                    </div>

                    {/* الإحصائيات المالية */}
                    <div className="lg:col-span-5">
                      <div className="grid grid-cols-3 gap-2">
                        <div className="p-3 rounded-xl border bg-slate-50 dark:bg-slate-800/50 border-slate-100 dark:border-slate-700 text-slate-900 dark:text-slate-100 flex flex-col items-center justify-center text-center h-full">
                          <span className="text-xs opacity-80 mb-1 flex items-center gap-1.5 font-medium">
                            <FileText className="w-3 h-3" /> الإجمالي
                          </span>
                          <span className="text-sm sm:text-base font-bold tracking-tight">
                            {invoice.currency === 'ILS' ? '₪' : '$'}
                            {grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </span>
                        </div>
                        <div className="p-3 rounded-xl border bg-blue-50 dark:bg-blue-900/10 border-blue-100 dark:border-blue-800/30 text-blue-700 dark:text-blue-400 flex flex-col items-center justify-center text-center h-full">
                          <span className="text-xs opacity-80 mb-1 flex items-center gap-1.5 font-medium">
                            <Package className="w-3 h-3" /> المنتجات
                          </span>
                          <span className="text-sm sm:text-base font-bold tracking-tight">
                            {invoice.currency === 'ILS' ? '₪' : '$'}
                            {subtotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </span>
                        </div>
                        <div className="p-3 rounded-xl border bg-amber-50 dark:bg-amber-900/10 border-amber-100 dark:border-amber-800/30 text-amber-700 dark:text-amber-400 flex flex-col items-center justify-center text-center h-full">
                          <span className="text-xs opacity-80 mb-1 flex items-center gap-1.5 font-medium">
                            <Percent className="w-3 h-3" /> الضريبة
                          </span>
                          <span className="text-sm sm:text-base font-bold tracking-tight">
                            {invoice.currency === 'ILS' ? '₪' : '$'}
                            {taxAmount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })
      ) : (
        <div className="flex flex-col items-center justify-center py-16 px-4 text-center bg-white dark:bg-slate-800 rounded-xl border border-dashed border-slate-300 dark:border-slate-700">
          {/* Empty State */}
          <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">
            لا توجد فواتير مطابقة
          </h3>
        </div>
      )}

      {/* Pagination Controls ... (نفس الكود السابق) */}
      {sortedInvoices.length > 0 && (
        <div className="flex justify-center mt-6 gap-2">
          <button onClick={() => goToPage(Math.max(1, currentPage - 1))} disabled={currentPage === 1} className="px-3 py-1 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700 border rounded">السابقة</button>
          <span className="px-3 py-1">صفحة {currentPage} من {totalPages}</span>
          <button onClick={() => goToPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage === totalPages} className="px-3 py-1 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700 border rounded">التالية</button>
        </div>
      )}
    </div>
  );
};