import React, { useState, useEffect, useMemo } from "react";
import { PriceOffer, Item, Supplier, PriceOfferStatus } from "../../types";
import {
  itemsService,
  suppliersService,
  priceOffersService,
} from "../../services/firestoreService";
import { FileText, Plus, Package } from "lucide-react";
import { LoadingSpinner } from "../LoadingSpinner";

// استيراد المكونات الفرعية
import { PriceOfferForm } from "./price-offers/PriceOfferForm";
import { StatusChangeModal } from "./price-offers/StatusChangeModal";
import { PriceOfferList } from "./price-offers/PriceOfferListUpdated";
import { PriceOfferFilters } from "./price-offers/PriceOfferFilters";
import { StatisticsPanel } from "./price-offers/StatisticsPanel";

export const PriceOfferManagement: React.FC = () => {
  // --- Data States ---
  const [viewMode, setViewMode] = useState<"list" | "form">("list");
  const [offers, setOffers] = useState<PriceOffer[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);

  // --- Filter States ---
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSupplierId, setSelectedSupplierId] = useState("");
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([]);
  const [selectedStatus, setSelectedStatus] = useState<
    PriceOfferStatus | "all"
  >("all");
  const [dateRange, setDateRange] = useState({ start: "", end: "" });

  // --- Form States ---
  const [currentOffer, setCurrentOffer] = useState<Partial<PriceOffer>>({
    status: "initial",
    items: [],
    subtotal: 0,
    discountAmount: 0,
    taxRate: 0,
    taxAmount: 0,
    grandTotal: 0,
    internalNotes: "",
  });

  // UI States
  const [saving, setSaving] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);

  // Status Change Modal State
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [targetStatusOffer, setTargetStatusOffer] = useState<PriceOffer | null>(
    null
  );
  const [newStatusTarget, setNewStatusTarget] =
    useState<PriceOfferStatus | null>(null);

  // --- Effects ---
  useEffect(() => {
    const unsubscribeOffers =
      priceOffersService.subscribeToPriceOffers(setOffers);
    const unsubscribeItems = itemsService.subscribeToItems(setItems);
    const unsubscribeSuppliers =
      suppliersService.subscribeToSuppliers(setSuppliers);
    setLoading(false);

    return () => {
      unsubscribeOffers();
      unsubscribeItems();
      unsubscribeSuppliers();
    };
  }, []);

  // --- Filtering Logic ---
  const filteredOffers = useMemo(() => {
    const lowerSearchTerm = searchTerm.toLowerCase().trim();

    return offers.filter((offer) => {
      // 1. Search filter
      let matchesSearch = true;
      if (lowerSearchTerm) {
        const supplier = suppliers.find((s) => s.id === offer.supplierId);
        const supplierMatch =
          (supplier?.alias || "").toLowerCase().includes(lowerSearchTerm) ||
          (supplier?.tradeName || "").toLowerCase().includes(lowerSearchTerm) ||
          (supplier?.factoryName || "").toLowerCase().includes(lowerSearchTerm);

        const shippingMatch =
          (offer.shippingMethodId || "")
            .toLowerCase()
            .includes(lowerSearchTerm) ||
          (offer.deliveryTime || "").toLowerCase().includes(lowerSearchTerm) ||
          (offer.paymentMethod || "").toLowerCase().includes(lowerSearchTerm) ||
          (offer.shipmentNotes || "").toLowerCase().includes(lowerSearchTerm);

        // البحث في الملاحظات الداخلية أيضاً
        const internalNotesMatch = (offer.internalNotes || "")
          .toLowerCase()
          .includes(lowerSearchTerm);

        matchesSearch =
          (offer.offerNumber || "").toLowerCase().includes(lowerSearchTerm) ||
          internalNotesMatch ||
          supplierMatch ||
          shippingMatch ||
          offer.items?.some(
            (item) =>
              (item.name || "").toLowerCase().includes(lowerSearchTerm) ||
              (item.modelNumber || "")
                .toLowerCase()
                .includes(lowerSearchTerm) ||
              (item.specifications || "")
                .toLowerCase()
                .includes(lowerSearchTerm)
          );
      }

      // 2. Supplier filter
      const matchesSupplier = selectedSupplierId
        ? offer.supplierId === selectedSupplierId
        : true;

      // 3. Items filter
      const matchesItems =
        selectedItemIds.length === 0
          ? true
          : selectedItemIds.some((itemId) =>
            offer.items?.some((offerItem) => offerItem.itemId === itemId)
          );

      // 4. Status filter
      const matchesStatus =
        selectedStatus === "all" ? true : offer.status === selectedStatus;

      // 5. Date range filter
      let matchesDate = true;
      if (dateRange.start) {
        matchesDate = matchesDate && offer.createdAt >= dateRange.start;
      }
      if (dateRange.end) {
        matchesDate = matchesDate && offer.createdAt <= dateRange.end;
      }

      return (
        matchesSearch &&
        matchesSupplier &&
        matchesItems &&
        matchesStatus &&
        matchesDate
      );
    });
  }, [
    offers,
    suppliers,
    searchTerm,
    selectedSupplierId,
    selectedItemIds,
    selectedStatus,
    dateRange,
  ]);

  // الحصول على المنتجات المفلترة لاستخدامها في القوائم المنسدلة
  const filteredItems = useMemo(() => {
    const lowerSearchTerm = searchTerm.toLowerCase().trim();
    return items.filter((item) => {
      if (!lowerSearchTerm) return true;
      return (
        (item.name || "").toLowerCase().includes(lowerSearchTerm) ||
        (item.modelNumber || "").toLowerCase().includes(lowerSearchTerm) ||
        (item.categoryName || "").toLowerCase().includes(lowerSearchTerm)
      );
    });
  }, [items, searchTerm]);

  // اقتراحات البحث الذكي
  const suggestedItems = useMemo(() => {
    if (!searchTerm.trim()) return [];
    const lowerSearchTerm = searchTerm.toLowerCase();
    return items
      .filter(
        (item) =>
          (item.name?.toLowerCase().includes(lowerSearchTerm) ||
            item.modelNumber?.toLowerCase().includes(lowerSearchTerm)) &&
          !selectedItemIds.includes(item.id)
      )
      .slice(0, 5);
  }, [items, searchTerm, selectedItemIds]);

  // --- Handlers ---
  // في PriceOfferManagement - تحديث دالة handleCreateNew
  const handleCreateNew = async () => {
    // لا نستخدم getNextOfferNumber بعد الآن
    setCurrentOffer({
      id: crypto.randomUUID(),
      offerNumber: "", // نص حر - المستخدم يدخله
      status: "initial",
      items: [],
      subtotal: 0,
      discountAmount: 0,
      taxRate: 0,
      taxAmount: 0,
      grandTotal: 0,
      internalNotes: "",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      createdBy: "current-user-id",
    });
    setIsReadOnly(false);
    setViewMode("form");
  };

  const handleEdit = (offer: PriceOffer) => {
    setCurrentOffer(JSON.parse(JSON.stringify(offer)));
    setIsReadOnly(false);
    setViewMode('form');
    // عند التعديل، العرض ليس جديداً لأنه له id
  };

  const handleViewDetails = (offer: PriceOffer) => {
    setCurrentOffer(JSON.parse(JSON.stringify(offer)));
    setIsReadOnly(true);
    setViewMode('form');
    // عند العرض فقط، العرض ليس جديداً
  };

  const handleDelete = async (id: string) => {
    if (confirm("هل أنت متأكد من حذف هذا العرض؟")) {
      await priceOffersService.deletePriceOfferFromDb(id);
    }
  };

  const handleSave = async () => {
    // التحقق من اسم الفاتورة
    if (!currentOffer.offerNumber || currentOffer.offerNumber.trim() === "") {
      alert("يرجى إدخال اسم الفاتورة");
      return;
    }

    if (!currentOffer.supplierId) {
      alert("يرجى اختيار المورد");
      return;
    }

    setSaving(true);
    try {
      const now = new Date().toISOString();
      const finalOffer: PriceOffer = {
        ...(currentOffer as PriceOffer),
        updatedAt: now,
        createdAt: currentOffer.createdAt || now,
        internalNotes: currentOffer.internalNotes || "",
        offerNumber: currentOffer.offerNumber.trim(), // تنظيف النص
      };

      if (currentOffer.id && offers.find((o) => o.id === currentOffer.id)) {
        await priceOffersService.updatePriceOfferInDb(finalOffer);
      } else {
        await priceOffersService.addPriceOfferToDb(finalOffer);
      }

      setViewMode("list");
      alert("تم الحفظ بنجاح");
    } catch (error) {
      console.error("Save error:", error);
      alert("حدث خطأ أثناء الحفظ");
    } finally {
      setSaving(false);
    }
  };

  // --- Status Change Logic ---
  const initiateStatusChange = (
    offerId: string,
    newStatus: PriceOfferStatus
  ) => {
    const offer = offers.find((o) => o.id === offerId);
    if (offer) {
      setTargetStatusOffer(offer);
      setNewStatusTarget(newStatus);
      setStatusModalOpen(true);
    }
  };

  const confirmStatusChange = async (
    status: PriceOfferStatus,
    notes: string
  ) => {
    if (!targetStatusOffer) return;
    setSaving(true);
    try {
      // إنشاء ملاحظة الحالة الجديدة
      const now = new Date();
      const statusNote = `تم تغيير الحالة من ${targetStatusOffer.status
        } إلى ${status} بتاريخ ${now.toLocaleDateString(
          "ar-EG"
        )} الساعة ${now.toLocaleTimeString("ar-EG")}${notes ? ` - ملاحظة: ${notes}` : ""
        }`;

      // دمج الملاحظات القديمة مع الجديدة
      const updatedInternalNotes = targetStatusOffer.internalNotes
        ? `${targetStatusOffer.internalNotes}\n${statusNote}`
        : statusNote;

      const updatedOffer: PriceOffer = {
        ...targetStatusOffer,
        status: status,
        internalNotes: updatedInternalNotes, // استخدام internalNotes بدلاً من statusNotes
        updatedAt: now.toISOString(),
      };

      await priceOffersService.updatePriceOfferInDb(updatedOffer);
      setStatusModalOpen(false);
      setTargetStatusOffer(null);
      setNewStatusTarget(null);
      alert("تم تحديث حالة العرض بنجاح");
    } catch (error) {
      console.error("Error updating status:", error);
      alert("حدث خطأ أثناء تحديث الحالة");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner />;

  // ---------------- RENDER ----------------
  return (
    <div className="p-6 md:p-8 max-w-[1600px] mx-auto space-y-6">
      {/* 1. Header Section */}
      {!isReadOnly && viewMode === "list" && (
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
              <FileText className="w-8 h-8 text-blue-600" />
              إدارة عروض الأسعار
            </h1>
            <p className="text-gray-500 dark:text-gray-400 mt-2">
              إدارة ومراقبة جميع عروض الأسعار وتتبع حالتها
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="font-bold text-blue-600 dark:text-blue-400">
                {filteredOffers.length}
              </span>
              من أصل <span className="font-bold">{offers.length}</span> عرض
            </div>
            <button
              onClick={handleCreateNew}
              className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-bold shadow-lg hover:shadow-blue-500/30"
            >
              <Plus className="w-5 h-5" />
              عرض أسعار جديد
            </button>
          </div>
        </div>
      )}

      {/* View Mode: FORM */}
      {viewMode === "form" ? (
        <PriceOfferForm
          currentOffer={currentOffer}
          setCurrentOffer={setCurrentOffer}
          suppliers={suppliers}
          items={items}
          onSave={handleSave}
          onCancel={() => setViewMode("list")}
          saving={saving}
          readOnly={isReadOnly}
          isNew={!currentOffer.id} // هنا نقول: إذا كان جديداً (ليس له id)
        />
      ) : (
        /* View Mode: LIST DASHBOARD */
        <div className="space-y-6">
          {/* 2. Statistics Panel */}
          <StatisticsPanel offers={offers} suppliers={suppliers} />

          {/* 3. Advanced Filters */}
          <PriceOfferFilters
            searchTerm={searchTerm}
            onSearchChange={setSearchTerm}
            selectedSupplierId={selectedSupplierId}
            onSupplierChange={setSelectedSupplierId}
            selectedItemIds={selectedItemIds}
            onItemsChange={setSelectedItemIds}
            selectedStatus={selectedStatus}
            onStatusChange={setSelectedStatus}
            dateRange={dateRange}
            onDateRangeChange={setDateRange}
            suppliers={suppliers}
            items={filteredItems}
            offersCount={offers.length}
            filteredCount={filteredOffers.length}
          />

          {/* 4. Search Suggestions (Smart Chips) */}
          {searchTerm.trim() && suggestedItems.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-blue-100 dark:border-blue-900/30 p-4 animate-in fade-in slide-in-from-top-2">
              <div className="flex items-center gap-2 mb-3">
                <Package className="w-4 h-4 text-blue-500" />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  هل تبحث عن هذه المنتجات؟
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {suggestedItems.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      if (!selectedItemIds.includes(item.id)) {
                        setSelectedItemIds((prev) => [...prev, item.id]);
                      }
                    }}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-200 transition-all text-sm"
                  >
                    <span>{item.name}</span>
                    <Plus className="w-3 h-3 text-blue-500" />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 5. Main List Table */}
          <PriceOfferList
            offers={filteredOffers}
            suppliers={suppliers}
            activeFilter={selectedStatus}
            searchQuery={searchTerm}
            onFilterChange={setSelectedStatus}
            onSearchChange={setSearchTerm}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onCreateNew={handleCreateNew}
            onClearFilter={() => {
              setSelectedStatus("all");
              setSearchTerm("");
              setSelectedSupplierId("");
              setSelectedItemIds([]);
              setDateRange({ start: "", end: "" });
            }}
            onViewDetails={handleViewDetails}
            onChangeStatus={initiateStatusChange}
            allDbItems={items}
          />
        </div>
      )}

      {/* Global Modals */}
      {targetStatusOffer && newStatusTarget && (
        <StatusChangeModal
          isOpen={statusModalOpen}
          onClose={() => setStatusModalOpen(false)}
          onConfirm={confirmStatusChange}
          currentStatus={targetStatusOffer.status}
          newStatus={newStatusTarget}
          saving={saving}
        />
      )}
    </div>
  );
};
