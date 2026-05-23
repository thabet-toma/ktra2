/**
 * N5-T6 — PriceOfferManagement (L3) — AseelDenseTable لعروض الأسعار
 * المرجع: العروض والطلبيات.txt:4-9
 */
import React, { useState, useEffect, useMemo } from "react";
import { PriceOffer, Item, Supplier, PriceOfferStatus } from "../../types";
import {
  itemsService,
  suppliersService,
  priceOffersService,
} from "../../services/firestoreService";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { PriceOfferForm } from "./price-offers/PriceOfferForm";
import { StatusChangeModal } from "./price-offers/StatusChangeModal";
import { Plus, RefreshCw } from "lucide-react";

const STATUS_LABELS: Record<string, string> = {
  initial: "مسودة",
  pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة",
  approved_for_shipping: "معتمد للشحن",
  rejected: "مرفوض",
};

const STATUS_COLORS: Record<string, string> = {
  initial: "var(--aseel-ink-soft)",
  pending_info: "var(--aseel-warn, #b8800a)",
  under_discussion: "var(--aseel-accent, #1857a4)",
  approved_for_shipping: "var(--aseel-ok, #267346)",
  rejected: "var(--aseel-danger, #c00)",
};

const fmtDate = (d: string | undefined) => {
  if (!d) return "—";
  try { return new Date(d).toLocaleDateString("ar"); } catch { return d; }
};

const fmtAmt = (n: number | undefined) =>
  (n ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const PriceOfferManagement: React.FC = () => {
  const [viewMode, setViewMode] = useState<"list" | "form">("list");
  const [offers, setOffers] = useState<PriceOffer[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<PriceOfferStatus | "all">("all");

  const [currentOffer, setCurrentOffer] = useState<Partial<PriceOffer>>({
    status: "initial", items: [], subtotal: 0, discountAmount: 0,
    taxRate: 0, taxAmount: 0, grandTotal: 0, internalNotes: "",
  });
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [targetStatusOffer, setTargetStatusOffer] = useState<PriceOffer | null>(null);
  const [newStatusTarget, setNewStatusTarget] = useState<PriceOfferStatus | null>(null);

  useEffect(() => {
    const u1 = priceOffersService.subscribeToPriceOffers(setOffers);
    const u2 = itemsService.subscribeToItems(setItems);
    const u3 = suppliersService.subscribeToSuppliers(setSuppliers);
    setLoading(false);
    return () => { u1(); u2(); u3(); };
  }, []);

  const filtered = useMemo(() => {
    const s = search.toLowerCase();
    return offers.filter((o) => {
      if (filterStatus !== "all" && o.status !== filterStatus) return false;
      if (s) {
        const sup = suppliers.find((x) => x.id === o.supplierId)?.name || "";
        return (
          sup.toLowerCase().includes(s) ||
          (o.offerNumber || "").toLowerCase().includes(s)
        );
      }
      return true;
    });
  }, [offers, suppliers, search, filterStatus]);

  const openNew = () => {
    setCurrentOffer({
      status: "initial", items: [], subtotal: 0, discountAmount: 0,
      taxRate: 0, taxAmount: 0, grandTotal: 0, internalNotes: "",
    });
    setIsReadOnly(false);
    setViewMode("form");
  };

  const openEdit = (offer: PriceOffer, readOnly = false) => {
    setCurrentOffer(offer);
    setIsReadOnly(readOnly);
    setViewMode("form");
  };

  const handleSave = async (offerData: Partial<PriceOffer>) => {
    setSaving(true);
    try {
      if (offerData.id) {
        await priceOffersService.updatePriceOfferInDb(offerData as PriceOffer);
      } else {
        const newOffer: PriceOffer = {
          ...(offerData as PriceOffer),
          id: `offer-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          offerNumber: offerData.offerNumber || await priceOffersService.getNextOfferNumber(),
          createdAt: offerData.createdAt || new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        await priceOffersService.addPriceOfferToDb(newOffer);
      }
      setViewMode("list");
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (offerId: string, newStatus: PriceOfferStatus) => {
    const target = offers.find((o) => o.id === offerId);
    if (!target) { setStatusModalOpen(false); return; }
    await priceOffersService.updatePriceOfferInDb({
      ...target,
      status: newStatus,
      updatedAt: new Date().toISOString(),
    });
    setStatusModalOpen(false);
  };

  const columns: DenseColumn<PriceOffer>[] = [
    { key: "offerNumber", header: "رقم العرض", width: "120px",
      render: (o) => <b>{o.offerNumber || o.id.slice(0, 8)}</b> },
    { key: "supplier", header: "المورد",
      render: (o) => <>{suppliers.find((s) => s.id === o.supplierId)?.name || "—"}</> },
    { key: "date", header: "التاريخ", width: "100px",
      render: (o) => <>{fmtDate(o.createdAt)}</> },
    { key: "items", header: "الأصناف", width: "70px", align: "center",
      render: (o) => <>{(o.items || []).length}</> },
    { key: "total", header: "الإجمالي", width: "120px", align: "center", numeric: true,
      render: (o) => <>{fmtAmt(o.grandTotal)}</> },
    { key: "status", header: "الحالة", width: "150px",
      render: (o) => (
        <span style={{ color: STATUS_COLORS[o.status] || "inherit" }}>
          {STATUS_LABELS[o.status] || o.status}
        </span>
      )
    },
    { key: "actions", header: "", width: "60px", align: "center",
      render: (o) => (
        <button className="aseel-toolbtn" style={{ fontSize: "var(--aseel-fs-sm)", padding: "2px 6px" }}
          onClick={(e) => { e.stopPropagation(); openEdit(o); }}>
          تعديل
        </button>
      )
    },
  ];

  if (viewMode === "form") {
    return (
      <PriceOfferForm
        offer={currentOffer}
        items={items}
        suppliers={suppliers}
        isReadOnly={isReadOnly}
        saving={saving}
        onSave={handleSave}
        onCancel={() => setViewMode("list")}
        onStatusChangeRequest={(offer, newStatus) => {
          setTargetStatusOffer(offer as PriceOffer);
          setNewStatusTarget(newStatus as PriceOfferStatus);
          setStatusModalOpen(true);
        }}
      />
    );
  }

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }} data-skin="aseel">
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          عروض الأسعار
        </strong>
        <span className="aseel-status-item">الإجمالي: <b>{offers.length}</b></span>
        <div style={{ flex: 1 }} />
        <input className="aseel-input" style={{ width: 180 }}
          placeholder="بحث بالمورد / رقم العرض…"
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="aseel-input" style={{ width: 160 }}
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value as PriceOfferStatus | "all")}>
          <option value="all">كل الحالات</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <button className="aseel-toolbtn" title="تحديث">
          <RefreshCw className="h-4 w-4" />
        </button>
        <button className="aseel-toolbtn" onClick={openNew} title="عرض جديد (Ctrl+Ins)">
          <Plus className="h-4 w-4" /> عرض جديد
        </button>
      </div>

      <AseelDenseTable<PriceOffer>
        columns={columns}
        rows={filtered}
        getRowKey={(o) => o.id}
        loading={loading}
        emptyHint="لا توجد عروض أسعار"
        onRowDoubleClick={(o) => openEdit(o)}
      />

      {statusModalOpen && targetStatusOffer && newStatusTarget && (
        <StatusChangeModal
          offer={targetStatusOffer}
          newStatus={newStatusTarget}
          onConfirm={(id, status) => void handleStatusChange(id, status as PriceOfferStatus)}
          onCancel={() => setStatusModalOpen(false)}
        />
      )}
    </div>
  );
};
