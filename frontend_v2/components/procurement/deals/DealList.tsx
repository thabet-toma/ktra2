import React, { useState, useMemo, useEffect } from "react";
import { Deal, Supplier } from "../../../types";
import type { ShippingWorkflowStatus } from "../../../types/deal";
import {
  getShippingWorkflowBadgeClass,
  getShippingWorkflowLabel,
  SHIPPING_WORKFLOW_LABELS,
} from "@/utils/shippingWorkflowLabels";
import { getDealGrandTotalUsd } from "@/utils/dealGrandTotalUsd";
import { SupplierViewModal } from "@/components/common/SupplierViewModal";
// 🟢 1. استيراد مودال التعديل
import { SupplierModal } from "@/components/common/SupplierModal";
import {
  Package,
  DollarSign,
  CheckCircle2,
  AlertCircle,
  Factory,
  FileText,
  ChevronDown,
  User,
  Filter,
  Search,
  SortAsc,
  SortDesc,
  Truck,
  Clock,
  CheckCircle,
  AlertTriangle,
  Printer,
  Calendar,
  X,
  Edit,
  ArrowUpRight,
  Ship,
} from "lucide-react";

interface DealListProps {
  deals: Deal[];
  onEdit: (deal: Deal) => void;
  onPrint: (deal: Deal) => void;
  onDelete: (dealId: string) => void;
  allSuppliers?: Supplier[];
  compactMode?: boolean;
}

export const DealList: React.FC<DealListProps> = ({
  deals,
  onEdit,
  onPrint,
  onDelete,
  allSuppliers,
  compactMode = true,
}) => {
  const [expandedDeals, setExpandedDeals] = useState<Set<string>>(new Set());
  const [hoveredImage, setHoveredImage] = useState<{ dealId: string, index: number } | null>(null);

  // States للعرض
  const [viewSupplierId, setViewSupplierId] = useState<string | null>(null);

  // 🟢 2. States جديدة للتعديل
  const [showSupplierEditModal, setShowSupplierEditModal] = useState(false);
  const [supplierToEdit, setSupplierToEdit] = useState<Supplier | null>(null);

  // States for Filters & Sorting
  const [selectedShippingWorkflow, setSelectedShippingWorkflow] = useState<string>("all");
  const [selectedPaymentStatus, setSelectedPaymentStatus] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [sortField, setSortField] = useState<"date" | "amount" | "status">("date");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  const [showDateFilter, setShowDateFilter] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 20;

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '-';
    return date.toLocaleDateString('en-GB');
  };

  // --- Helper Functions ---
  const calculateDealFinancials = (deal: Deal) => {
    const grandTotal = getDealGrandTotalUsd(deal);
    const paidAmount = deal.payments?.reduce((sum, p) => sum + (parseFloat(p.amount as any) || 0), 0) || 0;
    const remainingAmount = grandTotal - paidAmount;

    return { grandTotal, paidAmount, remainingAmount };
  };

  // ... (باقي دوال الحالة والفلترة كما هي للحفاظ على نظافة الكود) ...
  // (getOperationalStatus, getPaymentStatusFromPayments, getSupplierDisplayName, etc.)

  type PaymentStatus = "not_paid" | "claim_raised" | "payment_pending_confirmation" | "partially_paid" | "paid";

  const getPaymentStatusFromPayments = (deal: Deal): PaymentStatus => {
    const { grandTotal, paidAmount } = calculateDealFinancials(deal);
    if (grandTotal === 0 && paidAmount === 0) return "not_paid";
    if (grandTotal === 0 && paidAmount > 0) return "paid";
    const percentage = (paidAmount / grandTotal) * 100;
    if (percentage >= 99) return "paid";
    if (percentage > 0) return "partially_paid";
    return "not_paid";
  };

  const getPayStyles = (status: PaymentStatus) => { const styles: any = { not_paid: "aseel-bg-panel aseel-text-state aseel-border-soft dark:aseel-bg-panel/20 dark:aseel-text-soft", claim_raised: "aseel-bg-panel aseel-text-ink aseel-border-soft dark:aseel-bg-panel/20 dark:aseel-text-soft", payment_pending_confirmation: "aseel-bg-accent-bg aseel-text-accent aseel-border-accent dark:aseel-bg-panel/20 dark:aseel-text-soft", partially_paid: "aseel-bg-panel aseel-text-ink aseel-border-soft dark:aseel-bg-panel/20 dark:aseel-text-soft", paid: "bg-green-50 text-green-700 aseel-border-soft dark:bg-green-900/20 dark:text-green-300", }; return styles[status] || styles["not_paid"]; };
  const getPayText = (status: PaymentStatus) => { const map: any = { not_paid: "غير مدفوعة", claim_raised: "رفع مطالبة", payment_pending_confirmation: "بانتظار تأكيد", partially_paid: "مدفوعة جزئياً", paid: "مدفوعة كلياً" }; return map[status] || status; };
  const getPayIcon = (status: PaymentStatus) => { const icons: any = { not_paid: <AlertCircle className="w-3 h-3" />, claim_raised: <AlertTriangle className="w-3 h-3" />, payment_pending_confirmation: <Clock className="w-3 h-3" />, partially_paid: <DollarSign className="w-3 h-3" />, paid: <CheckCircle className="w-3 h-3" />, }; return icons[status]; };

  const getShippingWorkflowIcon = (code: ShippingWorkflowStatus | null | undefined) => {
    if (!code) return <Package className="w-3 h-3" />;
    const icons: Record<ShippingWorkflowStatus, React.ReactNode> = {
      sw_mfg_start: <Factory className="w-3 h-3" />,
      sw_wait_agent_ship: <Package className="w-3 h-3" />,
      sw_wait_intl_ship: <Truck className="w-3 h-3" />,
      sw_wait_arrival: <Ship className="w-3 h-3" />,
      sw_wait_clearance: <FileText className="w-3 h-3" />,
      sw_released: <CheckCircle2 className="w-3 h-3" />,
    };
    return icons[code] ?? <Package className="w-3 h-3" />;
  };

  const getSupplierDisplayName = (deal: Deal): string => {
    if (!allSuppliers || !deal.supplierId) return deal.factoryName || "مورد غير محدد";
    const supplier = allSuppliers.find((s) => s.id === deal.supplierId);
    if (supplier) {
      if (supplier.alias && supplier.alias.trim() !== '') {
        return `${supplier.tradeName} (${supplier.alias})`;
      }
      return supplier.tradeName;
    }
    return deal.factoryName || "مورد غير محدد";
  };

  const getDealImages = (deal: Deal) => {
    const images: string[] = [];
    deal.items?.forEach(item => {
      if (item.imageUrls?.length) images.push(...item.imageUrls.slice(0, 3));
      if (images.length >= 3) return;
    });
    return images.slice(0, 3);
  };

  const resetAllFilters = () => {
    setSelectedShippingWorkflow("all");
    setSelectedPaymentStatus("all");
    setSearchTerm("");
    setDateFrom("");
    setDateTo("");
    setShowDateFilter(false);
    setCurrentPage(1);
  };

  const filteredDeals = useMemo(() => {
    return deals.filter((deal) => {
      const wf = deal.shippingWorkflowStatus ?? null;
      if (selectedShippingWorkflow !== "all") {
        if (selectedShippingWorkflow === "unset") {
          if (wf) return false;
        } else if (wf !== selectedShippingWorkflow) return false;
      }
      const paymentStatus = getPaymentStatusFromPayments(deal);
      if (selectedPaymentStatus !== "all" && paymentStatus !== selectedPaymentStatus) return false;
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        const matchesNumbers = deal.dealNumber?.toLowerCase().includes(term) || deal.originalOfferNumber?.toLowerCase().includes(term) || (deal as any).supplierInvoiceNumber?.toLowerCase().includes(term);
        const matchesSupplier = deal.factoryName?.toLowerCase().includes(term) || allSuppliers?.find(s => s.id === deal.supplierId)?.tradeName?.toLowerCase().includes(term) || allSuppliers?.find(s => s.id === deal.supplierId)?.alias?.toLowerCase().includes(term);
        const matchesItems = deal.items?.some(item => item.name?.toLowerCase().includes(term));
        if (!matchesNumbers && !matchesSupplier && !matchesItems) return false;
      }
      if (dateFrom || dateTo) {
        const dealDateStr = deal.dealDate || deal.createdAt;
        if (!dealDateStr) return false;
        const dealDate = new Date(dealDateStr);
        dealDate.setHours(0, 0, 0, 0);
        if (dateFrom) { const from = new Date(dateFrom); from.setHours(0, 0, 0, 0); if (dealDate < from) return false; }
        if (dateTo) { const to = new Date(dateTo); to.setHours(23, 59, 59, 999); if (dealDate > to) return false; }
      }
      return true;
    });
  }, [deals, selectedShippingWorkflow, selectedPaymentStatus, searchTerm, allSuppliers, dateFrom, dateTo]);

  const sortedDeals = useMemo(() => {
    return [...filteredDeals].sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case "date": const dateA = new Date(a.dealDate || 0).getTime(); const dateB = new Date(b.dealDate || 0).getTime(); comparison = dateB - dateA; break;
        case "amount": comparison = calculateDealFinancials(b).grandTotal - calculateDealFinancials(a).grandTotal; break;
        case "status": comparison = (a.status || "").localeCompare(b.status || ""); break;
      }
      return sortDirection === "asc" ? -comparison : comparison;
    });
  }, [filteredDeals, sortField, sortDirection]);

  const totalPages = Math.ceil(sortedDeals.length / itemsPerPage);
  const paginatedDeals = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return sortedDeals.slice(startIndex, startIndex + itemsPerPage);
  }, [sortedDeals, currentPage]);

  useEffect(() => setCurrentPage(1), [selectedShippingWorkflow, selectedPaymentStatus, searchTerm, dateFrom, dateTo]);
  const goToPage = (page: number) => { if (page >= 1 && page <= totalPages) { setCurrentPage(page); window.scrollTo({ top: 0, behavior: 'smooth' }); } };
  const toggleDealExpand = (dealId: string) => { setExpandedDeals((prev) => { const newSet = new Set(prev); if (newSet.has(dealId)) newSet.delete(dealId); else newSet.add(dealId); return newSet; }); };

  return (
    <div className="space-y-3">
      {/* --- Filter Bar --- */}
      <div className="aseel-bg-field dark:aseel-bg-panel p-2 rounded-lg border aseel-border-soft dark:aseel-border-soft shadow-sm">
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-2 mb-2">
          {/* ... (نفس كود الفلاتر العلوية) ... */}
          <div className="flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 aseel-text-soft" />
            <span className="font-medium aseel-text-ink dark:aseel-text-soft text-xs">فلاتر البحث</span>
            <span className="text-xs aseel-bg-accent-bg aseel-text-accent dark:aseel-bg-panel/30 dark:aseel-text-soft px-1.5 py-0.5 rounded-full">
              {filteredDeals.length} صفقة
            </span>
          </div>
          <div className="flex gap-1.5">
            <button
              onClick={() => setShowDateFilter(!showDateFilter)}
              className={`px-2 py-1 rounded-lg flex items-center gap-1 text-xs transition-colors ${showDateFilter
                ? "aseel-bg-accent-bg aseel-text-accent dark:aseel-bg-panel/30 dark:aseel-text-soft"
                : "aseel-bg-panel aseel-text-ink dark:aseel-bg-panel dark:aseel-text-soft"
                }`}
              title="فلترة بالتاريخ"
            >
              <Calendar className="w-3 h-3" />
              <span>التاريخ</span>
              {(dateFrom || dateTo) && <span className="w-1.5 h-1.5 aseel-bg-accent-bg rounded-full" />}
            </button>

            <button onClick={() => setSortField("date")} className={`px-2 py-1 rounded-lg flex items-center gap-0.5 text-xs ${sortField === "date" ? "aseel-bg-accent-bg aseel-text-accent dark:aseel-bg-panel/30 dark:aseel-text-soft" : "aseel-bg-panel aseel-text-ink dark:aseel-bg-panel dark:aseel-text-soft"}`}>
              {sortField === "date" && sortDirection === "desc" ? <SortDesc className="w-3 h-3" /> : <SortAsc className="w-3 h-3" />} التاريخ
            </button>
            <button onClick={() => setSortField("amount")} className={`px-2 py-1 rounded-lg text-xs ${sortField === "amount" ? "aseel-bg-accent-bg aseel-text-accent dark:aseel-bg-panel/30 dark:aseel-text-soft" : "aseel-bg-panel aseel-text-ink dark:aseel-bg-panel dark:aseel-text-soft"}`}>
              المبلغ
            </button>
            <button onClick={() => setSortDirection(prev => prev === "asc" ? "desc" : "asc")} className="px-2 py-1 aseel-bg-panel dark:aseel-bg-panel aseel-text-ink dark:aseel-text-soft rounded-lg text-xs">
              {sortDirection === "desc" ? "تنازلي" : "تصاعدي"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-1.5">
          {/* ... (نفس كود حقول البحث) ... */}
          <div className="relative">
            <Search className="absolute right-2 top-1/2 transform -translate-y-1/2 w-3 h-3 aseel-text-soft" />
            <input type="text" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="ابحث (رقم الصفقة، الفاتورة، المورد)..." className="w-full p-1.5 pr-7 text-xs border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg aseel-text-ink dark:text-white placeholder-gray-400" />
          </div>
          <select value={selectedShippingWorkflow} onChange={(e) => setSelectedShippingWorkflow(e.target.value)} className="p-1.5 text-xs border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg aseel-text-ink dark:text-white">
            <option value="all">كل أوضاع الشحنة</option>
            <option value="unset">لم يُحدد وضع الشحنة</option>
            {(Object.keys(SHIPPING_WORKFLOW_LABELS) as ShippingWorkflowStatus[]).map((code) => (
              <option key={code} value={code}>
                {SHIPPING_WORKFLOW_LABELS[code]}
              </option>
            ))}
          </select>
          <select value={selectedPaymentStatus} onChange={(e) => setSelectedPaymentStatus(e.target.value)} className="p-1.5 text-xs border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded-lg aseel-text-ink dark:text-white">
            <option value="all">كل الدفعات</option>
            <option value="not_paid">غير مدفوعة</option>
            <option value="claim_raised">رفع مطالبة</option>
            <option value="payment_pending_confirmation">بانتظار تأكيد</option>
            <option value="partially_paid">مدفوعة جزئياً</option>
            <option value="paid">مدفوعة كلياً</option>
          </select>
          <button onClick={resetAllFilters} className="p-1.5 text-xs aseel-bg-panel hover:aseel-bg-panel dark:aseel-bg-panel/20 dark:hover:aseel-bg-panel/30 aseel-text-state dark:aseel-text-soft rounded-lg transition-colors">
            إعادة تعيين
          </button>
        </div>

        {showDateFilter && (
          <div className="flex items-center gap-2 mt-2 pt-2 border-t aseel-border-soft dark:aseel-border-soft animate-in fade-in slide-in-from-top-1">
            {/* ... (نفس كود فلاتر التاريخ) ... */}
            <div className="flex items-center gap-1.5 aseel-bg-panel dark:aseel-bg-panel/50 p-1.5 rounded-lg border aseel-border-soft dark:aseel-border-soft">
              <span className="text-xs aseel-text-soft font-medium">من:</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="p-1 text-xs border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded aseel-text-ink dark:aseel-text-soft outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-center gap-1.5 aseel-bg-panel dark:aseel-bg-panel/50 p-1.5 rounded-lg border aseel-border-soft dark:aseel-border-soft">
              <span className="text-xs aseel-text-soft font-medium">إلى:</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="p-1 text-xs border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel rounded aseel-text-ink dark:aseel-text-soft outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            {(dateFrom || dateTo) && (
              <button
                onClick={() => { setDateFrom(""); setDateTo(""); }}
                className="p-1.5 aseel-text-soft hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg transition-colors"
                title="مسح التاريخ"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* --- Deal List --- */}
      <div className="space-y-2">
        {paginatedDeals.map((deal) => {
          // ... (حسابات الصفقة) ...
          const { grandTotal, paidAmount, remainingAmount } = calculateDealFinancials(deal);
          const shippingWf = deal.shippingWorkflowStatus ?? null;
          const paymentStatus = getPaymentStatusFromPayments(deal);
          const supplierDisplayName = getSupplierDisplayName(deal);
          const images = getDealImages(deal);
          const isExpanded = expandedDeals.has(deal.id);

          return (
            <div key={deal.id} className="relative group rounded-lg border transition-all duration-200 aseel-bg-field dark:aseel-bg-panel aseel-border-soft dark:aseel-border-soft hover:shadow-md hover:z-20 hover:aseel-border-soft dark:hover:aseel-border-soft hover:aseel-bg-accent-bg/50 dark:hover:aseel-bg-panel/50">
              {/* Main Compact Row */}
              <div className="flex items-center justify-between p-3 cursor-pointer" onClick={() => toggleDealExpand(deal.id)}>
                {/* Left Side: Images & Info */}
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {/* ... (صور الصفقة) ... */}
                  {images.length > 0 && (
                    <div className="relative flex-shrink-0 z-10" onClick={(e) => e.stopPropagation()}>
                      <div className="flex -space-x-2">
                        {images.slice(0, 2).map((img, idx) => {
                          const item = deal.items?.find(i => i.imageUrls?.includes(img) || i.factoryImageUrl === img);
                          const itemName = item?.name || "منتج";
                          return (
                            <div key={idx} className="relative group/image" onMouseEnter={() => setHoveredImage({ dealId: deal.id, index: idx })} onMouseLeave={() => setHoveredImage(null)}>
                              <div className="w-9 h-9 rounded-md border-2 border-white dark:aseel-border-soft shadow-sm overflow-hidden hover:scale-110 transition-transform duration-200">
                                <img src={img} alt="" className="w-full h-full object-cover" />
                              </div>
                              {hoveredImage?.dealId === deal.id && hoveredImage?.index === idx && (
                                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50">
                                  <div className="aseel-bg-panel text-white text-xs px-2 py-1 rounded shadow-lg whitespace-nowrap">
                                    {itemName}
                                    <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></div>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                        {images.length > 2 && (
                          <div className="w-9 h-9 rounded-md border-2 border-white dark:aseel-border-soft aseel-bg-panel dark:aseel-bg-panel flex items-center justify-center text-[10px] font-bold aseel-text-soft dark:aseel-text-soft z-0">
                            +{images.length - 2}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold aseel-text-ink dark:text-white text-sm truncate">{deal.dealNumber}</span>
                      {deal.originalOfferNumber && (
                        <span
                          title={deal.originalOfferNumber}
                          className="font-bold aseel-text-ink dark:text-white text-sm truncate max-w-[240px] aseel-bg-accent-bg dark:aseel-bg-panel/40 px-1.5 py-0.5 rounded border aseel-border-soft dark:aseel-border-soft flex-shrink-0"
                        >
                          {deal.originalOfferNumber}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs aseel-text-soft dark:aseel-text-soft">
                      {/* 🟢 زر فتح المورد (عرض) */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (deal.supplierId) setViewSupplierId(deal.supplierId);
                        }}
                        className="font-medium aseel-text-accent hover:aseel-text-ink dark:aseel-text-soft dark:hover:aseel-text-soft hover:underline transition-colors text-left"
                      >
                        {supplierDisplayName}
                      </button>
                      <span className="w-1 h-1 aseel-bg-grid-head rounded-full"></span>
                      <span className="flex-shrink-0">{deal.items?.length || 0} منتج</span>
                    </div>
                  </div>
                </div>

                {/* Middle & Right ... (نفس الكود) */}
                <div className="hidden sm:flex items-center gap-2 mx-4">
                  <div
                    className={`px-2 py-1 rounded-md text-xs border flex items-center gap-1.5 font-medium ${getShippingWorkflowBadgeClass(shippingWf)}`}
                    title="وضع الشحنة"
                  >
                    {getShippingWorkflowIcon(shippingWf)}
                    <span className="hidden lg:inline">{getShippingWorkflowLabel(shippingWf)}</span>
                  </div>
                  <div className={`px-2 py-1 rounded-md text-xs border flex items-center gap-1.5 font-medium ${getPayStyles(paymentStatus)}`}>
                    {getPayIcon(paymentStatus)}
                    <span className="hidden lg:inline">{getPayText(paymentStatus)}</span>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="font-bold aseel-text-ink dark:text-white text-sm">${grandTotal.toLocaleString()}</div>
                    <div className="text-[10px] aseel-text-soft">{formatDate(deal.dealDate)}</div>
                  </div>
                  <div className="flex items-center gap-1 pl-1">
                    {/* New Tab Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        window.open(`${window.location.origin}/deals/${encodeURIComponent(deal.id)}`, '_blank', 'noopener,noreferrer');
                      }}
                      className="p-1.5 hover:aseel-bg-field dark:hover:aseel-bg-panel rounded-full aseel-text-soft hover:aseel-text-accent transition-colors"
                      title="فتح في نافذة جديدة"
                    >
                      <ArrowUpRight className="w-4 h-4" />
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); onPrint(deal); }} className="p-1.5 hover:aseel-bg-field dark:hover:aseel-bg-panel rounded-full aseel-text-soft hover:aseel-text-accent transition-colors" title="طباعة"><Printer className="w-4 h-4" /></button>
                    <button onClick={(e) => { e.stopPropagation(); onEdit(deal); }} className="p-1.5 hover:aseel-bg-field dark:hover:aseel-bg-panel rounded-full aseel-text-soft hover:aseel-text-accent transition-colors" title="تعديل"><Edit className="w-4 h-4" /></button>
                    <div className={`p-1 rounded-full transition-transform duration-200 ${isExpanded ? 'rotate-180 aseel-bg-panel dark:aseel-bg-panel' : ''}`}><ChevronDown className="w-4 h-4 aseel-text-soft" /></div>
                  </div>
                </div>
              </div>

              {/* Expanded Details Section */}
              {isExpanded && (
                <div className="border-t aseel-border-soft dark:aseel-border-soft aseel-bg-panel/50 dark:bg-black/20 p-3 rounded-b-lg">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-xs">
                        <User className="w-3.5 h-3.5 aseel-text-soft" />
                        <span className="aseel-text-soft">المورد:</span>
                        {/* 🟢 زر فتح المورد (عرض) أيضاً في القسم الموسع */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (deal.supplierId) setViewSupplierId(deal.supplierId);
                          }}
                          className="font-medium aseel-text-accent hover:aseel-text-ink dark:aseel-text-soft dark:hover:aseel-text-soft hover:underline transition-colors text-left"
                        >
                          {supplierDisplayName}
                        </button>
                      </div>
                      {/* ... باقي التفاصيل ... */}
                      <div className="sm:hidden flex flex-wrap gap-2 mt-2">
                        <span className={`px-2 py-1 rounded text-xs border ${getShippingWorkflowBadgeClass(shippingWf)}`}>
                          {getShippingWorkflowLabel(shippingWf)}
                        </span>
                        <span className={`px-2 py-1 rounded text-xs ${getPayStyles(paymentStatus)}`}>{getPayText(paymentStatus)}</span>
                      </div>
                    </div>
                    {/* ... باقي الأعمدة (Financials, Products, Footer Actions) ... */}
                    <div className="grid grid-cols-3 gap-2">
                      <div className="aseel-bg-field dark:aseel-bg-panel p-2 rounded border aseel-border-soft dark:aseel-border-soft text-center">
                        <div className="text-[10px] aseel-text-soft mb-0.5">المدفوع</div>
                        <div className="text-sm font-bold aseel-text-soft">${paidAmount.toLocaleString()}</div>
                      </div>
                      <div className="aseel-bg-field dark:aseel-bg-panel p-2 rounded border aseel-border-soft dark:aseel-border-soft text-center">
                        <div className="text-[10px] aseel-text-soft mb-0.5">المتبقي</div>
                        <div className="text-sm font-bold aseel-text-soft">${remainingAmount.toLocaleString()}</div>
                      </div>
                      <div className="aseel-bg-field dark:aseel-bg-panel p-2 rounded border aseel-border-soft dark:aseel-border-soft text-center">
                        <div className="text-[10px] aseel-text-soft mb-0.5">الإجمالي</div>
                        <div className="text-sm font-bold aseel-text-accent">${grandTotal.toLocaleString()}</div>
                      </div>
                    </div>
                    <div className="lg:col-span-1">
                      <div className="text-xs font-medium aseel-text-soft mb-1.5">أبرز المنتجات</div>
                      <div className="flex flex-wrap gap-1">
                        {deal.items?.slice(0, 3).map((item, i) => (
                          <span key={i} className="px-2 py-1 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded text-[10px] aseel-text-ink dark:aseel-text-soft">
                            {item.name} <span className="aseel-text-soft mx-1">x{item.quantity}</span>
                          </span>
                        ))}
                        {(deal.items?.length || 0) > 3 && (
                          <span className="px-2 py-1 aseel-bg-panel dark:aseel-bg-panel rounded text-[10px] aseel-text-soft">
                            +{(deal.items?.length || 0) - 3}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="md:col-span-2 lg:col-span-3 flex justify-end gap-2 pt-2 mt-2 border-t aseel-border-soft dark:aseel-border-soft">
                      <button onClick={() => onEdit(deal)} className="px-3 py-1.5 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft aseel-text-ink dark:aseel-text-soft rounded text-xs hover:aseel-bg-panel transition-colors">سجل النشاطات</button>
                      <button onClick={() => { if (confirm('حذف؟')) onDelete(deal.id) }} className="px-3 py-1.5 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft/50 aseel-text-state dark:aseel-text-soft rounded text-xs hover:aseel-bg-panel dark:hover:aseel-bg-panel/20 transition-colors">حذف</button>
                      <button onClick={() => onEdit(deal)} className="px-4 py-1.5 aseel-bg-accent hover:aseel-bg-accent text-white rounded text-xs font-medium shadow-sm transition-colors">إدارة الصفقة الكاملة</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <button onClick={() => goToPage(currentPage - 1)} disabled={currentPage === 1} className="px-3 py-1.5 text-xs aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded hover:aseel-bg-panel disabled:opacity-50 transition-colors dark:text-white">السابقة</button>
          <span className="px-3 py-1.5 text-xs aseel-text-soft dark:aseel-text-soft flex items-center">{currentPage} / {totalPages}</span>
          <button onClick={() => goToPage(currentPage + 1)} disabled={currentPage === totalPages} className="px-3 py-1.5 text-xs aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded hover:aseel-bg-panel disabled:opacity-50 transition-colors dark:text-white">التالية</button>
        </div>
      )}

      {/* 4. عرض مودال المورد في أسفل الصفحة */}
      <SupplierViewModal
        isOpen={!!viewSupplierId}
        supplierId={viewSupplierId}
        onClose={() => setViewSupplierId(null)}
        // 🟢 5. دالة التعديل (تفتح مودال التعديل)
        onEdit={(supplier) => {
          setViewSupplierId(null); // إغلاق مودال العرض
          setSupplierToEdit(supplier); // تعيين المورد المراد تعديله
          setShowSupplierEditModal(true); // فتح مودال التعديل
        }}
      />

      {/* 🟢 6. مودال التعديل */}
      <SupplierModal
        isOpen={showSupplierEditModal}
        onClose={() => {
          setShowSupplierEditModal(false);
          setSupplierToEdit(null);
        }}
        onSaveSuccess={() => {
          // التحديث يتم تلقائياً لأن البيانات تأتي من الأب (Firestore Subscription)
        }}
        editingSupplier={supplierToEdit}
      />
    </div>
  );
};