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
  type PriceOfferScope,
} from "../../services/firestoreService";
import type { DenseColumn } from "../aseel/AseelDenseTable";
import { PriceOfferForm } from "./price-offers/PriceOfferForm";
import { StatusChangeModal } from "./price-offers/StatusChangeModal";
import { CommercialDocumentsList } from "../shared/CommercialDocumentsList";
import { FilePreviewModal } from "../shared/FilePreviewModal";
import { Paperclip } from "lucide-react";
import type { PriceOfferAttachment } from "../../types/offer";
import {
  cancelPurchaseOrder,
  confirmPurchaseOrder,
  convertPurchaseOrderToInvoice,
  convertSupplierQuotationToImportDeal,
  convertSupplierQuotationToPurchaseOrder,
} from "../../services/procurementDocumentsApi";
import { useToast } from "../../contexts/ToastContext";
import {
  PROCUREMENT_KIND_LABELS,
  canConvertImportOffer,
  isOfferStruckThrough,
  procurementDocKind,
  procurementStatusLabel,
} from "../../utils/documentBadges";

const STATUS_LABELS: Record<string, string> = {
  initial: "مسودة",
  pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة",
  approved_for_shipping: "معتمد للشحن",
  rejected: "مرفوض",
};

/** T-IMPOFFER: نطاق الاستيراد يقرأ الحالة كقرار ملاءمة (انظر PriceOfferForm). */
const IMPORT_STATUS_LABELS: Record<string, string> = {
  initial: "مسودة",
  pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة",
  approved_for_shipping: "ملائم",
  rejected: "غير ملائم",
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
  return formatDateValue(d);
};

import { formatMoney } from "@/utils/formatNumber";
import { formatDateValue } from "../../utils/formatDate";
const fmtAmt = (n: number | undefined) => formatMoney(n);

interface Props {
  scope?: PriceOfferScope;
}

export const PriceOfferManagement: React.FC<Props> = (props) => {
  const scope: PriceOfferScope = props.scope ?? "purchase";
  const statusLabels = scope === "import" ? IMPORT_STATUS_LABELS : STATUS_LABELS;
  const toast = useToast();
  const [viewMode, setViewMode] = useState<"list" | "form">("list");
  const [offers, setOffers] = useState<PriceOffer[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<PriceOfferStatus | "all">("all");

  const [currentOffer, setCurrentOffer] = useState<Partial<PriceOffer>>({
    status: "initial", items: [], subtotal: 0, discountAmount: 0,
    taxRate: 0, taxAmount: 0, grandTotal: 0, internalNotes: "",
  });
  const [isReadOnly, setIsReadOnly] = useState(false);
  // T-IMPOFFER: معاينة ملف العرض من القائمة نفسها — بلا فتح المستند.
  const [previewFile, setPreviewFile] = useState<PriceOfferAttachment | null>(null);
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [targetStatusOffer, setTargetStatusOffer] = useState<PriceOffer | null>(null);
  const [newStatusTarget, setNewStatusTarget] = useState<PriceOfferStatus | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    let active = true;
    const pending = new Set(["offers", "items", "suppliers"]);
    const settle = (key: string) => {
      pending.delete(key);
      if (active && pending.size === 0) setLoading(false);
    };
    const fail = (key: string, message: string) => (cause: unknown) => {
      if (active) {
        setError(cause instanceof Error ? `${message}: ${cause.message}` : message);
      }
      settle(key);
    };
    const u1 = priceOffersService.subscribeToPriceOffers(
      (rows) => { if (active) setOffers(rows); settle("offers"); },
      scope,
      fail("offers", "تعذّر تحميل العروض"),
    );
    const u2 = itemsService.subscribeToItems(
      (rows) => { if (active) setItems(rows); settle("items"); },
      fail("items", "تعذّر تحميل الأصناف"),
    );
    // T-IMPOFFER: الموردون مفصولون — شاشة الاستيراد تعرض الدوليين (مع غير
    // المصنَّفين) وشاشة الشراء المحليين، فلا يُختار مصنع صيني لطلبية محلية.
    const u3 = suppliersService.subscribeToSuppliers(
      (rows) => { if (active) setSuppliers(rows); settle("suppliers"); },
      fail("suppliers", "تعذّر تحميل الموردين"),
      scope === "import" ? "international" : "local",
    );
    return () => {
      active = false;
      u1();
      u2();
      u3();
    };
  }, [scope, reloadKey]);

  const filtered = useMemo(() => {
    const s = search.toLowerCase();
    return offers.filter((o) => {
      if (filterStatus !== "all" && o.status !== filterStatus) return false;
      if (s) {
        const sup = suppliers.find((x) => x.id === o.supplierId)?.tradeName || "";
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

  const openEdit = async (offer: PriceOffer, readOnly = false) => {
    setLoading(true);
    setError(null);
    try {
      const detail = await priceOffersService.getPriceOfferById(offer.id, scope);
      const resolved = detail || offer;
      setCurrentOffer(resolved);
      setIsReadOnly(
        readOnly
        || resolved.backendStatus === "converted"
        || resolved.backendStatus === "confirmed"
        || resolved.backendStatus === "cancelled"
        || resolved.backendStatus === "invoiced"
        || resolved.backendStatus === "closed"
      );
      setViewMode("form");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر فتح المستند");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (offerData: Partial<PriceOffer>) => {
    setSaving(true);
    try {
      if (offerData.id) {
        const updatedOffer = offerData as PriceOffer;
        const saved = await priceOffersService.updatePriceOfferInDb(updatedOffer, scope);
        setOffers((prev) => prev.map((row) => row.id === updatedOffer.id ? saved : row));
      } else {
        const newOffer: PriceOffer = {
          ...(offerData as PriceOffer),
          id: "",
          offerNumber: offerData.offerNumber || "",
          createdAt: offerData.createdAt || new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        const saved = await priceOffersService.addPriceOfferToDb(newOffer, scope);
        setOffers((prev) => [saved, ...prev]);
      }
      setError(null);
      setViewMode("list");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل حفظ المستند");
      throw e;
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (offerId: string, newStatus: PriceOfferStatus) => {
    const target = offers.find((o) => o.id === offerId);
    if (!target) { setStatusModalOpen(false); return; }
    const saved = await priceOffersService.updatePriceOfferInDb({
      ...target,
      status: newStatus,
      updatedAt: new Date().toISOString(),
    }, scope);
    setOffers((prev) => prev.map((row) => row.id === offerId ? saved : row));
    setStatusModalOpen(false);
  };

  /**
   * إجراءات دورة المستند (تأكيد/تحويل/إلغاء).
   *
   * كان النجاح صامتاً: يُعاد التحميل فقط، والحالة تُعرض بنفس النص قبله وبعده
   * («معتمد للشحن») ⇒ يبدو التحويل كأنه لم يحدث. الآن يُعلن الناتج باسم المستند
   * المُنشأ، ويُسمّى المستند الجديد في الرسالة.
   */
  const runLifecycleAction = async (
    action: () => Promise<unknown>,
    successMessage?: (result: unknown) => string,
  ) => {
    setSaving(true);
    setError(null);
    try {
      const result = await action();
      setReloadKey((key) => key + 1);
      if (successMessage) toast(successMessage(result), "success");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "تعذّر تنفيذ الإجراء";
      setError(message);
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const columns: DenseColumn<PriceOffer>[] = [
    // T-IMPOFFER: «وإذا غير ملائم يكون معلَّم على أنه مشطوب» — الشطب على رقم
    // المستند نفسه فيُقرأ القرار من مسح الصفوف بلا فتح أي عرض.
    { key: "offerNumber", header: "رقم المستند", width: "120px",
      render: (o) => (
        <b style={isOfferStruckThrough(o.backendStatus)
          ? { textDecoration: "line-through", opacity: 0.6 }
          : undefined}>
          {o.offerNumber || o.id.slice(0, 8)}
        </b>
      ) },
    // النوعان كانا في قائمة واحدة بلا ما يميّزهما: «عرض سعر مورد» و«طلبية شراء».
    { key: "kind", header: "النوع", width: "100px", align: "center",
      render: (o) => {
        const kind = procurementDocKind(o.id, scope);
        const isOrder = kind === "order";
        return (
          <span style={{
            fontSize: "10px",
            fontWeight: 700,
            padding: "1px 6px",
            borderRadius: "4px",
            color: isOrder ? "#b04a00" : "var(--aseel-accent, #2563eb)",
            background: isOrder ? "rgba(176,74,0,0.12)" : "rgba(37,99,235,0.10)",
          }}>
            {PROCUREMENT_KIND_LABELS[kind]}
          </span>
        );
      } },
    { key: "supplier", header: "المورد",
      render: (o) => (
        <span style={isOfferStruckThrough(o.backendStatus)
          ? { textDecoration: "line-through", opacity: 0.6 }
          : undefined}>
          {suppliers.find((s) => s.id === o.supplierId)?.tradeName || o.factoryName || "—"}
        </span>
      ) },
    { key: "date", header: "التاريخ", width: "100px",
      render: (o) => <>{fmtDate(o.createdAt)}</> },
    { key: "items", header: "الأصناف", width: "70px", align: "center",
      render: (o) => <>{(o.items || []).length}</> },
    // T-IMPOFFER: ملف العرض ظاهر في القائمة، والنقر عليه يفتح معاينة وسط الشاشة.
    { key: "files", header: "الملف", width: "60px", align: "center",
      render: (o) => {
        const files = o.attachments || [];
        if (files.length === 0) return <span className="aseel-text-soft">—</span>;
        return (
          <button
            type="button"
            className="aseel-text-accent inline-flex items-center gap-0.5"
            title={`عرض «${files[0].name || "الملف"}»`}
            onClick={(e) => { e.stopPropagation(); setPreviewFile(files[0]); }}
          >
            <Paperclip className="h-3.5 w-3.5" />
            {files.length > 1 && <span className="text-[10px]">{files.length}</span>}
          </button>
        );
      } },
    { key: "total", header: "الإجمالي", width: "120px", align: "center", numeric: true,
      render: (o) => <>{fmtAmt(o.grandTotal)}</> },
    // الحالة من حالة الخادم الحقيقية لا من قاموس العرض القديم: «مؤكَّدة» و«محوَّلة
    // إلى فاتورة» كانتا تظهران «معتمد للشحن» كلتاهما، والمستند المرتبط لا يظهر.
    { key: "status", header: scope === "import" ? "قرار الملاءمة" : "الحالة", width: "190px",
      render: (o) => {
        const kind = procurementDocKind(o.id, scope);
        return (
          <div className="flex flex-col leading-tight">
            <span style={{ color: STATUS_COLORS[o.status] || "inherit" }}>
              {procurementStatusLabel(kind, o.backendStatus, statusLabels[o.status])}
            </span>
            {o.linkedDocNumber && (
              <span className="text-[10px] aseel-text-soft">← {o.linkedDocNumber}</span>
            )}
            {/* السبب بجانب القرار: «غير ملائم» بلا سبب لا يعلّم أحداً شيئاً. */}
            {isOfferStruckThrough(o.backendStatus) && o.decisionReason && (
              <span className="text-[10px] aseel-text-soft" title={o.decisionReason}>
                السبب: {o.decisionReason}
              </span>
            )}
          </div>
        );
      }
    },
    { key: "actions", header: "إجراءات", width: "250px", align: "center",
      render: (o) => (
        <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
          <button className="aseel-text-accent hover:underline"
            onClick={(e) => { e.stopPropagation(); void openEdit(o); }}>
            {o.backendStatus === "converted" ? "عرض" : "تعديل"}
          </button>
          {o.id.startsWith("quote-") && canConvertImportOffer(o.backendStatus) && (
            <button className="text-green-600 hover:underline" disabled={saving}
              onClick={(e) => {
                e.stopPropagation();
                const id = Number(o.id.replace("quote-", ""));
                void runLifecycleAction(
                  () => scope === "import"
                    ? convertSupplierQuotationToImportDeal(id)
                    : convertSupplierQuotationToPurchaseOrder(id),
                  (result) => {
                    const payload = result as {
                      deal?: { ref_number?: string };
                      order?: { order_number?: string };
                    };
                    const number = payload?.order?.order_number
                      || payload?.deal?.ref_number || "";
                    return scope === "import"
                      ? `تم تحويل العرض إلى صفقة استيراد ${number}`.trim()
                      : `تم تحويل العرض إلى طلبية شراء ${number}`.trim();
                  },
                );
              }}>
              {scope === "import" ? "تحويل إلى صفقة" : "تحويل إلى طلبية"}
            </button>
          )}
          {/* T-IMPOFFER: العرض غير الملائم لا يُحوَّل — نقول ذلك بدل إخفاء الزر بصمت. */}
          {o.id.startsWith("quote-")
            && scope === "import"
            && o.backendStatus !== "accepted"
            && o.backendStatus !== "converted" && (
            <span className="aseel-text-soft text-[10px]" title="حوّل العرض بعد اعتباره ملائماً">
              {isOfferStruckThrough(o.backendStatus)
                ? "غير ملائم — لا يُحوَّل"
                : "يلزمه قرار «ملائم» للتحويل"}
            </span>
          )}
          {o.id.startsWith("order-") && o.backendStatus === "draft" && (
            <button className="text-green-600 hover:underline" disabled={saving}
              onClick={(e) => {
                e.stopPropagation();
                void runLifecycleAction(
                  () => confirmPurchaseOrder(Number(o.id.replace("order-", ""))),
                  () => `تم تأكيد الطلبية ${o.offerNumber}`,
                );
              }}>
              تأكيد
            </button>
          )}
          {o.id.startsWith("order-") && o.backendStatus === "confirmed" && (
            <>
              <button className="text-blue-600 hover:underline" disabled={saving}
                onClick={(e) => {
                  e.stopPropagation();
                  void runLifecycleAction(
                    () => convertPurchaseOrderToInvoice(
                      Number(o.id.replace("order-", "")),
                    ),
                    (result) => {
                      const payload = result as {
                        invoice?: { invoice_number?: string };
                      };
                      return `تم تحويل الطلبية إلى فاتورة شراء ${
                        payload?.invoice?.invoice_number || ""
                      }`.trim();
                    },
                  );
                }}>
                تحويل لفاتورة
              </button>
              <button className="text-amber-600 hover:underline" disabled={saving}
                onClick={(e) => {
                  e.stopPropagation();
                  void runLifecycleAction(
                    () => cancelPurchaseOrder(Number(o.id.replace("order-", ""))),
                    () => `تم إلغاء الطلبية ${o.offerNumber}`,
                  );
                }}>
                إلغاء
              </button>
            </>
          )}
        </div>
      )
    },
  ];

  if (viewMode === "form") {
    return (
      <PriceOfferForm
        offer={currentOffer}
        items={items}
        suppliers={suppliers}
        scope={scope}
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
    <>
      <CommercialDocumentsList<PriceOffer>
        title={scope === "import" ? "عروض وطلبيات الاستيراد" : "عروض وطلبيات الشراء"}
        state={scope === "import" ? "مستندات الاستيراد" : "مستندات الشراء"}
        rows={filtered}
        columns={columns}
        getRowKey={(offer) => offer.id}
        loading={loading}
        error={error}
        emptyHint="لا توجد عروض أو طلبيات"
        countLabel={`${offers.length} مستند`}
        searchValue={search}
        searchPlaceholder="بحث بالمورد / رقم العرض…"
        onSearchChange={setSearch}
        statusValue={filterStatus}
        statusOptions={[
          { value: "all", label: scope === "import" ? "كل القرارات" : "كل الحالات" },
          ...Object.entries(statusLabels).map(([value, label]) => ({ value, label })),
        ]}
        onStatusChange={(value) => setFilterStatus(value as PriceOfferStatus | "all")}
        onNew={openNew}
        onReload={() => setReloadKey((key) => key + 1)}
        newLabel="عرض / طلبية جديدة"
        onRowDoubleClick={(offer) => void openEdit(offer)}
      />
      <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
      {statusModalOpen && targetStatusOffer && newStatusTarget && (
        <StatusChangeModal
          offer={targetStatusOffer}
          newStatus={newStatusTarget}
          onConfirm={(id, status) => void handleStatusChange(id, status as PriceOfferStatus)}
          onCancel={() => setStatusModalOpen(false)}
        />
      )}
    </>
  );
};
