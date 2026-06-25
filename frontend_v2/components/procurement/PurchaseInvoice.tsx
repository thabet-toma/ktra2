import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation, matchPath } from 'react-router-dom';
import {
  Plus, FileText, Loader2, ScrollText
} from 'lucide-react';
import { Invoice, Item, Supplier, User } from '@/types';
import { itemsService, suppliersService } from '@/services/firestoreService';
import { purchaseInvoiceApi } from '@/services/purchaseInvoiceApi';
import type { PurchaseInvoiceDto, PurchaseInvoiceListDto } from '@/types/purchaseInvoice';
import { mapPurchaseInvoiceDtoToInvoice } from '@/utils/mapPurchaseInvoiceDto';
import { roundSqlMoney2, roundSqlMoney4 } from '@/utils/sqlMoneyRound';
import { InvoiceForm } from './invoices/InvoiceForm';
import { dealsService } from '@/services/dealsService';
import { InvoiceList } from './invoices/InvoiceList';
import { ClearanceImportModal, ShipmentImportContext } from './invoices/ClearanceImportModal';
import { shipmentsService, advanceShipmentRouteAtLeast } from '@/services/shipmentsService';
import { InvoicePrintView } from './invoices/InvoicePrintView';
import { openInNewTab } from '@/utils/openInNewTab';

interface PurchaseInvoiceProps {
  currentUser?: User;
  /** نوع الفاتورة المعروضة في القائمة: محلية (افتراضي) أو دولية (الاستيراد). */
  invoiceType?: 'local' | 'international';
  /** مسار القائمة لهذا النوع (محرر الفاتورة يبقى مشتركاً على /purchase-invoices/:id). */
  listPath?: string;
}

const DEFAULT_USER: User = {
  id: 'unknown_user',
  name: 'User',
  role: 'manager',
  email: 'user@example.com',
  employmentStatus: 'active',
  isApproved: true,
  isEmailVerified: true
};

/** Map SQL list DTO → frontend Invoice shape for InvoiceList compatibility */
function sqlListToInvoice(row: PurchaseInvoiceListDto): Invoice {
  return {
    id: String(row.id),
    serialNumber: row.invoice_number.replace('INV-', ''),
    invoiceNumber: row.invoice_number,
    invoiceName: row.invoice_name || '',
    supplierId: String(row.partner),
    items: [],
    status: row.status as Invoice['status'],
    isPosted: Boolean(row.is_posted),
    subtotal: row.subtotal,
    discountAmount: row.discount_amount,
    taxRate: row.tax_rate,
    taxAmount: row.tax_amount,
    grandTotal: row.grand_total,
    currency: row.currency_code === 'USD' ? 'USD' : 'ILS',
    invoiceDate: row.invoice_date || undefined,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    createdBy: '',
    glPurchaseReceiptJournalId: row.journal_id_display || undefined,
    dealId: row.deal ? String(row.deal) : undefined,
    dealNumber: row.deal_ref || undefined,
    supplierSnapshot: { tradeName: row.partner_name },
  };
}

/** Map frontend Invoice → SQL create/update payload */
/** وضع النموذج/القائمة قبل أول رسم لتفادي وميض القائمة عند فتح /purchase-invoices/:id */
function initialPurchaseInvoiceViewMode(): "list" | "form" {
  if (typeof window === "undefined") return "list";
  const path = (window.location.pathname.replace(/\/$/, "") || "/");
  const d = matchPath({ path: "/purchase-invoices/:invoiceId", end: true }, path);
  return (d?.params as Record<string, string>)?.invoiceId ? "form" : "list";
}

function initialInvoiceRouteLoading(): boolean {
  if (typeof window === "undefined") return false;
  const path = (window.location.pathname.replace(/\/$/, "") || "/");
  const d = matchPath({ path: "/purchase-invoices/:invoiceId", end: true }, path);
  const id = (d?.params as Record<string, string>)?.invoiceId;
  return !!id && id !== "new" && Number(id) > 0;
}

function invoiceToSqlPayload(inv: Partial<Invoice>): Partial<PurchaseInvoiceDto> {
  const partnerId = Number(String(inv.supplierId || '').trim());
  return {
    invoice_number: inv.invoiceNumber || undefined,
    invoice_name: inv.invoiceName || null,
    invoice_date: inv.invoiceDate || null,
    partner: Number.isFinite(partnerId) && partnerId > 0 ? partnerId : undefined as any,
    deal: inv.dealId ? Number(inv.dealId) : null,
    shipment: inv.shipment ? Number(inv.shipment) : null,
    clearance: inv.clearanceId ? Number(inv.clearanceId) : null,
    subtotal: roundSqlMoney2(inv.subtotal ?? 0),
    discount_amount: roundSqlMoney2(inv.discountAmount ?? 0),
    tax_rate: roundSqlMoney4(inv.taxRate ?? 0),
    tax_amount: roundSqlMoney2(inv.taxAmount ?? 0),
    tax_type: inv.taxType || 'percentage',
    shipping_cost: roundSqlMoney2(inv.shippingCost ?? 0),
    shipping_included: inv.shippingIncluded || false,
    grand_total: roundSqlMoney2(inv.grandTotal ?? 0),
    local_payments_json: inv.localPayments as any || null,
    conversion_metadata_json: inv.conversionMetadata as any || null,
    status: inv.status || 'draft',
    notes: inv.notes || null,
    supplier_invoice_number: inv.supplierInvoiceNumber || null,
    factory_name: inv.factoryName || null,
    items: (inv.items || []).map(item => ({
      product: item.itemId ? Number(item.itemId) || null : null,
      name: item.name,
      quantity: roundSqlMoney4(item.quantity ?? 0),
      unit_price: roundSqlMoney4(item.unitPrice ?? 0),
      total_price: roundSqlMoney2(item.totalPrice ?? 0),
      notes: item.notes || null,
      hs_code: item.hsCodePrimary || null,
      landed_unit_price_ils:
        item.landedUnitPriceIls != null
          ? roundSqlMoney4(item.landedUnitPriceIls)
          : null,
      landed_line_total_ils:
        item.landedLineTotalIls != null
          ? roundSqlMoney2(item.landedLineTotalIls)
          : null,
    })),
  };
}


export const PurchaseInvoice: React.FC<PurchaseInvoiceProps> = ({
  currentUser: propUser,
  invoiceType = 'local',
  listPath = '/purchase-invoices',
}) => {
  const currentUser = propUser || DEFAULT_USER;
  const isInternational = invoiceType === 'international';
  const navigate = useNavigate();
  const location = useLocation();

  const [viewMode, setViewMode] = useState<"list" | "form">(initialPurchaseInvoiceViewMode);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  const [isReadOnly, setIsReadOnly] = useState(false);

  const [currentInvoice, setCurrentInvoice] = useState<Partial<Invoice> | null>(null);
  const [loading, setLoading] = useState(true);
  /** جاري جلب فاتورة من المسار (رقم) */
  const [invoiceRouteLoading, setInvoiceRouteLoading] = useState(initialInvoiceRouteLoading);
  const [showImportModal, setShowImportModal] = useState(false);
  /** فتح مودال الاستيراد مسبق الاختيار — يصل من شاشة الاستيراد: /purchase-invoices?import_shipment=N (T12-A4) */
  const [importShipmentId, setImportShipmentId] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [showPrintView, setShowPrintView] = useState(false);
  const [printInvoice, setPrintInvoice] = useState<Invoice | null>(null);

  const loadInvoices = useCallback(async () => {
    try {
      const rows = await purchaseInvoiceApi.list({ invoice_type: invoiceType });
      const mapped = rows.map(sqlListToInvoice);
      setInvoices(mapped);
    } catch (e) {
      // console suppressed
    } finally {
      setLoading(false);
    }
  }, [invoiceType]);

  /** مزامنة قائمة/نموذج الفاتورة مع المسار: /purchase-invoices و /purchase-invoices/:id */
  const applyLocationToView = useCallback(async () => {
    const path = location.pathname.replace(/\/$/, "") || "/";
    const listOnly = matchPath({ path: listPath, end: true }, path);
    const detail = matchPath({ path: "/purchase-invoices/:invoiceId", end: true }, path);

    if (listOnly) {
      setInvoiceRouteLoading(false);
      setViewMode("list");
      setCurrentInvoice(null);
      setIsReadOnly(false);
      return;
    }

    const pathId = (detail?.params as Record<string, string>)?.invoiceId;
    if (pathId) {
      if (pathId === "new") {
        setInvoiceRouteLoading(false);
        setCurrentInvoice(null);
        setIsReadOnly(false);
        setViewMode("form");
        return;
      }
      const numId = Number(pathId);
      if (!Number.isFinite(numId) || numId <= 0) {
        setInvoiceRouteLoading(false);
        navigate(listPath, { replace: true });
        return;
      }
      const sp = new URLSearchParams(location.search);
      const readOnly = sp.get("mode") === "view";
      if (String(numId) === String(currentInvoice?.id)) {
        setIsReadOnly(readOnly);
        setViewMode("form");
        setInvoiceRouteLoading(false);
        return;
      }
      setInvoiceRouteLoading(true);
      try {
        const full = await purchaseInvoiceApi.get(numId);
        setCurrentInvoice(mapPurchaseInvoiceDtoToInvoice(full));
        setIsReadOnly(readOnly);
        setViewMode("form");
      } catch (e) {
        // console suppressed
        navigate(listPath, { replace: true });
      } finally {
        setInvoiceRouteLoading(false);
      }
    }
  }, [location.pathname, location.search, navigate, currentInvoice?.id, listPath]);

  useEffect(() => {
    void loadInvoices();
    const unsubItems = itemsService.subscribeToItems(setItems);
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
    return () => {
      unsubItems();
      unsubSuppliers();
    };
  }, [loadInvoices]);

  useEffect(() => {
    void applyLocationToView();
  }, [applyLocationToView]);

  useEffect(() => {
    const sp = new URLSearchParams(location.search);
    const sid = Number(sp.get("import_shipment"));
    if (Number.isFinite(sid) && sid > 0) {
      setImportShipmentId(sid);
      setShowImportModal(true);
      // إزالة البارامتر حتى لا يُعاد فتح المودال عند كل تنقّل
      sp.delete("import_shipment");
      navigate({ pathname: location.pathname, search: sp.toString() }, { replace: true });
    }
  }, [location.search, location.pathname, navigate]);

  // --- Handlers ---
  const handleCreateNew = () => {
    openInNewTab("/purchase-invoices/new");
  };

  /** قائمة الفواتير لا تتضمن البنود — نجلب التفاصيل من الـ API عند الفتح */
  const handleEdit = (invoice: Invoice) => {
    openInNewTab(`/purchase-invoices/${invoice.id}`);
  };

  const handleView = (invoice: Invoice) => {
    openInNewTab(`/purchase-invoices/${invoice.id}?mode=view`);
  };

  const handlePrint = async (invoice: Invoice) => {
    try {
      const full = await purchaseInvoiceApi.get(Number(invoice.id));
      setPrintInvoice(mapPurchaseInvoiceDtoToInvoice(full));
      setShowPrintView(true);
    } catch (e) {
      // console suppressed
      alert('تعذّر تحميل الفاتورة للطباعة.');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await purchaseInvoiceApi.delete(Number(id));
      await loadInvoices();
    } catch (error) {
      // console suppressed
      alert("حدث خطأ أثناء محاولة حذف الفاتورة.");
    }
  };

  // في ملف PurchaseInvoice.tsx

  // داخل ملف PurchaseInvoice.tsx

  // داخل ملف PurchaseInvoice.tsx

  const handleConvertToDeal = async (invoice: Invoice) => {
    const isConfirmed = window.confirm(
      `هل تريد تحويل الفاتورة رقم (${invoice.invoiceNumber}) إلى صفقة شراء؟\n\nسيتم نقل بيانات المنتجات والمورد فقط (لن يتم نقل الصور أو المرفقات).`
    );
    if (!isConfirmed) return;

    try {
      let inv = invoice;
      if (!inv.items?.length) {
        inv = mapPurchaseInvoiceDtoToInvoice(await purchaseInvoiceApi.get(Number(invoice.id)));
      }

      // 🟢 تم حذف منطق تجميع الصور والملفات (collectedImages / collectedPdfs)

      // 1. تجهيز بيانات الصفقة
      const dealData: any = {
        // --- البيانات الأساسية ---
        supplierId: inv.supplierId,
        factoryName: inv.factoryName || (suppliers.find(s => s.id === inv.supplierId)?.tradeName || "مورد غير محدد"),

        // معلومات الفاتورة
        originalOfferNumber: inv.invoiceName || "",
        supplierInvoiceNumber: inv.supplierInvoiceNumber || "",
        internalNotes: inv.notes || "",
        alibabaOrderLink: inv.alibabaOrderLink || inv.dealInfo?.alibabaOrderLink || "",

        // التاريخ
        dealDate: inv.invoiceDate || new Date().toISOString().split('T')[0],

        // إلغاء خطة الدفع
        installments: [],
        installmentPlanEnabled: false,

        // 🟢 تم حذف حقول الصور والمرفقات من هنا (quoteImages, quotePdfs...)

        // المنتجات
        items: inv.items.map(item => ({
          id: crypto.randomUUID(),
          itemId: item.itemId,
          name: item.name,
          categoryId: item.categoryId,
          categoryName: item.categoryName,
          // قص النصوص الطويلة جداً احتياطياً لتجنب تجاوز الحجم
          specifications: (item.specifications || "").substring(0, 500),
          hsCodePrimary: item.hsCodePrimary,

          // 🟢 تقليل بيانات الصور داخل المنتجات: نأخذ فقط أول صورة كرابط نصي، ونتجاهل المصفوفة الكاملة إذا كانت ضخمة
          imageUrls: item.imageUrls && item.imageUrls.length > 0 ? [item.imageUrls[0]] : [],

          quantity: item.quantity,
          unitPrice: item.unitPrice,
          totalPrice: item.totalPrice,
          factoryImageUrl: item.imageUrls?.[0],
          notes: `نُقلت من الفاتورة رقم: ${inv.invoiceNumber}`
        })),

        // المالية
        totalAmount: inv.grandTotal || 0,
        subtotal: inv.subtotal || 0,
        discountAmount: inv.discountAmount || 0,
        taxRate: inv.taxRate || 0,
        taxAmount: inv.taxAmount || 0,
        taxType: inv.taxType || 'percentage',
        shippingCost: inv.shippingCost || 0,
        shippingIncluded: inv.shippingIncluded || false,

        // الشحن
        shippingMethod: inv.dealInfo?.shippingMethod || '',
        totalWeight: inv.totalWeight || 0,
        totalVolume: inv.totalVolume || 0,

        // الحالة
        status: 'initial',
        invoiceId: inv.id,
        hasHistoricalInvoice: true,
      };

      // 2. إنشاء الصفقة
      const dealId = await dealsService.createDeal(dealData);

      // 🟢 تم حذف إضافة النشاط الخاص بنقل الملفات

      alert("✅ تم تحويل الفاتورة إلى صفقة بنجاح!");

    } catch (e: any) {
      // console suppressed
      if (e.message && e.message.includes('exceeds the maximum allowed size')) {
        alert("❌ لا يزال حجم البيانات كبيراً جداً. يبدو أن الفاتورة تحتوي على عدد كبير جداً من المنتجات أو نصوص طويلة جداً.");
      } else {
        alert(`حدث خطأ أثناء عملية التحويل: ${e.message}`);
      }
    }
  };

  const handleImportFromClearance = async (
    ctx: ShipmentImportContext,
    meta?: { createdCount: number }
  ) => {
    setImporting(true);
    try {
      const minRoute =
        ctx.shippingType === "air" ? "arrived_airport" : "arrived_port";
      const nextRoute = advanceShipmentRouteAtLeast(
        ctx.currentRouteStatus,
        minRoute,
        ctx.shippingType
      );
      try {
        await shipmentsService.patchShipmentRoute(
          ctx.shipmentId,
          nextRoute,
          ctx.shippingType
        );
      } catch (e) {
        console.warn("تعذّر تحديث مسار الشحنة في SQL:", e);
      }

      await Promise.all(
        ctx.dealIds.map(async (did) => {
          try {
            const d = await dealsService.getDeal(did);
            if (d.shippingWorkflowStatus === "sw_released") return;
            await dealsService.patchShippingWorkflow(did, "sw_wait_clearance");
          } catch (e) {
            console.warn("تعذّر تحديث مرحلة الشحن للصفقة", did, e);
          }
        })
      );

      await loadInvoices();
      const n = meta?.createdCount ?? 0;
      alert(
        n > 0
          ? `✅ تم استيراد وتحويل ${n} فاتورة بنجاح!`
          : "✅ تم تحديث المسارات بعد الاستيراد."
      );
    } catch (error) {
      // console suppressed
      alert("حدث خطأ أثناء استيراد الفواتير");
    } finally {
      setImporting(false);
    }
  };

  const handleExitForm = () => {
    navigate("/purchase-invoices");
  };

  if (loading || invoiceRouteLoading) {
    return (
      <div className="flex items-center justify-center min-h-[500px]">
        <Loader2 className="w-8 h-8 text-[var(--color-primary)] animate-spin" />
        <span className="mr-3 text-[var(--color-text-muted)]">
          {invoiceRouteLoading ? "جاري تحميل الفاتورة..." : "جاري تحميل الفواتير..."}
        </span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-surface-2)] pb-10">

      {/* Content */}
      <div className="w-full">
        {viewMode === 'list' ? (
          <InvoiceList
            invoices={invoices}
            onEdit={handleEdit}
            onView={handleView}
            onPrint={handlePrint}
            onDelete={handleDelete}
            items={items}
            suppliers={suppliers}
            onConvertToDeal={handleConvertToDeal}
            onCreateNew={handleCreateNew}
            onImport={isInternational ? () => setShowImportModal(true) : undefined}
            onRefresh={() => void loadInvoices()}
          />
        ) : (
          <>
            <InvoiceForm
              invoice={currentInvoice}
              currentUser={currentUser}
              onCancel={handleExitForm}
              readOnly={isReadOnly}
              onSave={({ id }) => {
                void loadInvoices();
                if (location.pathname.endsWith("/new")) {
                  navigate(`/purchase-invoices/${id}`, { replace: true });
                }
              }}
              allDbItems={items}
            />
            {/* M2: لوحة المحاسبة والحركات المالية أصبحت تبويبات داخل المحرر
                (single editor + inline accounting) — توحيداً مع شاشة المبيعات. */}
          </>
        )}
      </div>

      {showImportModal && (
        <ClearanceImportModal
          isOpen={showImportModal}
          onClose={() => { setShowImportModal(false); setImportShipmentId(null); }}
          onImport={handleImportFromClearance}
          currentUser={currentUser}
          initialShipmentId={importShipmentId}
        />
      )}

      {showPrintView && printInvoice && (
        <InvoicePrintView
          invoice={printInvoice}
          currentUser={currentUser}
          supplier={suppliers.find(s => s.id === printInvoice.supplierId)}
          onClose={() => {
            setShowPrintView(false);
            setPrintInvoice(null);
          }}
          onEdit={() => {
            setShowPrintView(false);
            handleEdit(printInvoice);
          }}
        />
      )}
    </div>
  );
};