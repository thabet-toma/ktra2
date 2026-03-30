import React, { useState, useEffect } from 'react';
import {
  Plus, FileText, Loader2
} from 'lucide-react';
import { Invoice, Item, Supplier, User } from '@/types';
import { invoicesService, itemsService, suppliersService } from '@/services/firestoreService';
import { InvoiceForm } from './invoices/InvoiceForm';
import { dealsService } from '@/services/dealsService';
import { InvoiceList } from './invoices/InvoiceList';
import { ShipmentImportModal } from './invoices/ShipmentImportModal';
import { Truck } from 'lucide-react';
import { InvoicePrintView } from './invoices/InvoicePrintView';

interface PurchaseInvoiceProps {
  // Basic props if any, might receive user from parent
  currentUser?: User; // Depending on how App.tsx passes it, often we use context or pass it down
}

// Mock user if not provided (Safety)
const DEFAULT_USER: User = {
  id: 'unknown_user',
  name: 'User',
  role: 'manager',
  email: 'user@example.com',
  employmentStatus: 'active',
  isApproved: true,
  isEmailVerified: true
};


export const PurchaseInvoice: React.FC<PurchaseInvoiceProps> = ({ currentUser: propUser }) => {
  const currentUser = propUser || DEFAULT_USER; // Should come from AuthContext in real app

  const [viewMode, setViewMode] = useState<'list' | 'form'>('list');
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  const [isReadOnly, setIsReadOnly] = useState(false);


  const [currentInvoice, setCurrentInvoice] = useState<Partial<Invoice> | null>(null);
  const [loading, setLoading] = useState(true);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importing, setImporting] = useState(false);
  const [showPrintView, setShowPrintView] = useState(false);
  const [printInvoice, setPrintInvoice] = useState<Invoice | null>(null);

  // --- Data Subscription ---
  useEffect(() => {
    const unsubInvoices = invoicesService.subscribeToInvoices((data) => {
      setInvoices(data);

      // Auto-open invoice if ID is in URL
      const params = new URLSearchParams(window.location.search);
      const targetId = params.get('id');
      if (targetId && data.length > 0) {
        const targetInvoice = data.find(inv => inv.id === targetId);
        if (targetInvoice) {
          setCurrentInvoice(targetInvoice);
          setViewMode('form');
          // Default to view mode (read only) if just opening via link, or edit? 
          // Usually view is safer.
          setIsReadOnly(true);
        }
      }

      setLoading(false);
    });
    const unsubItems = itemsService.subscribeToItems(setItems);
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);

    return () => {
      unsubInvoices();
      unsubItems();
      unsubSuppliers();
    };
  }, []);

  // --- Handlers ---
  const handleCreateNew = () => {
    setCurrentInvoice(null);
    setIsReadOnly(false); // تعديل متاح
    setViewMode('form');
  };

  const handleEdit = (invoice: Invoice) => {
    setCurrentInvoice(invoice);
    setIsReadOnly(false); // تعديل متاح
    setViewMode('form');
  };

  // 3. 🟢 عرض فاتورة (للقراءة فقط)
  const handleView = (invoice: Invoice) => {
    setCurrentInvoice(invoice);
    setIsReadOnly(true); // قراءة فقط
    setViewMode('form');
  };

  const handlePrint = (invoice: Invoice) => {
    setPrintInvoice(invoice);
    setShowPrintView(true);
  };

  const handleDelete = async (id: string) => {
    // التنبيه (Alert) يظهر في InvoiceList قبل الوصول لهنا
    // هنا نقوم بالتنفيذ الفعلي
    try {
      await invoicesService.deleteInvoiceFromDb(id);
      // لا داعي لإظهار رسالة نجاح لأن القائمة ستتحدث تلقائياً عبر الاشتراك (Subscription)
    } catch (error) {
      console.error("Failed to delete invoice:", error);
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
      // 🟢 تم حذف منطق تجميع الصور والملفات (collectedImages / collectedPdfs)

      // 1. تجهيز بيانات الصفقة
      const dealData: any = {
        // --- البيانات الأساسية ---
        supplierId: invoice.supplierId,
        factoryName: invoice.factoryName || (suppliers.find(s => s.id === invoice.supplierId)?.tradeName || "مورد غير محدد"),

        // معلومات الفاتورة
        originalOfferNumber: invoice.invoiceName || "",
        supplierInvoiceNumber: invoice.supplierInvoiceNumber || "",
        internalNotes: invoice.notes || "",
        alibabaOrderLink: invoice.alibabaOrderLink || invoice.dealInfo?.alibabaOrderLink || "",

        // التاريخ
        dealDate: invoice.invoiceDate || new Date().toISOString().split('T')[0],

        // إلغاء خطة الدفع
        installments: [],
        installmentPlanEnabled: false,

        // 🟢 تم حذف حقول الصور والمرفقات من هنا (quoteImages, quotePdfs...)

        // المنتجات
        items: invoice.items.map(item => ({
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
          notes: `نُقلت من الفاتورة رقم: ${invoice.invoiceNumber}`
        })),

        // المالية
        totalAmount: invoice.grandTotal || 0,
        subtotal: invoice.subtotal || 0,
        discountAmount: invoice.discountAmount || 0,
        taxRate: invoice.taxRate || 0,
        taxAmount: invoice.taxAmount || 0,
        taxType: invoice.taxType || 'percentage',
        shippingCost: invoice.shippingCost || 0,
        shippingIncluded: invoice.shippingIncluded || false,

        // الشحن
        shippingMethod: invoice.dealInfo?.shippingMethod || '',
        totalWeight: invoice.totalWeight || 0,
        totalVolume: invoice.totalVolume || 0,

        // الحالة
        status: 'initial',
        invoiceId: invoice.id,
        hasHistoricalInvoice: true,
      };

      // 2. إنشاء الصفقة
      const dealId = await dealsService.createDeal(
        dealData,
        currentUser.id,
        currentUser.name,
        currentUser.role
      );

      // 🟢 تم حذف إضافة النشاط الخاص بنقل الملفات

      alert("✅ تم تحويل الفاتورة إلى صفقة بنجاح!");

    } catch (e: any) {
      console.error("خطأ في تحويل الفاتورة:", e);
      if (e.message && e.message.includes('exceeds the maximum allowed size')) {
        alert("❌ لا يزال حجم البيانات كبيراً جداً. يبدو أن الفاتورة تحتوي على عدد كبير جداً من المنتجات أو نصوص طويلة جداً.");
      } else {
        alert(`حدث خطأ أثناء عملية التحويل: ${e.message}`);
      }
    }
  };

  const handleImportShipmentInvoices = async (newInvoices: Partial<Invoice>[]) => {
    if (newInvoices.length === 0) return;

    setImporting(true);
    try {
      const now = new Date().toISOString();

      const savePromises = newInvoices.map(inv => {
        const fullInvoice = {
          ...inv,
          id: crypto.randomUUID(),
          createdBy: currentUser.id,
          createdAt: now,
          updatedAt: now,
        } as Invoice;

        return invoicesService.addInvoiceToDb(fullInvoice);
      });

      await Promise.all(savePromises);
      alert(`✅ تم استيراد وتحويل ${newInvoices.length} فواتير بنجاح!`);
    } catch (error) {
      console.error("Error importing shipment invoices:", error);
      alert("حدث خطأ أثناء استيراد الفواتير");
    } finally {
      setImporting(false);
    }
  };

  const handleExitForm = () => {
    setViewMode('list');
    setCurrentInvoice(null);
    setIsReadOnly(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[500px]">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        <span className="mr-3 text-gray-500">جاري تحميل الفواتير...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 pb-10">

      {/* Header - يظهر فقط في وضع القائمة */}
      {viewMode === 'list' && (
        <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 mb-6">
          <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
                <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">فواتير المشتريات</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  إدارة الفواتير الواردة من الموردين ({invoices.length})
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowImportModal(true)}
                disabled={importing}
                className="flex items-center gap-2 bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-800/60 px-5 py-2.5 rounded-xl font-medium transition-all border border-indigo-200 dark:border-indigo-700 disabled:opacity-50"
              >
                {importing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Truck className="w-5 h-5" />}
                <span>استيراد من شحنة</span>
              </button>
              <button
                onClick={handleCreateNew}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl font-medium transition-all shadow-sm hover:shadow-md"
              >
                <Plus className="w-5 h-5" />
                <span>فاتورة جديدة</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className={viewMode === 'list' ? "max-w-7xl mx-auto px-4" : "w-full"}>
        {viewMode === 'list' ? (
          <InvoiceList
            invoices={invoices}
            onEdit={handleEdit}
            onView={handleView}     // 🟢 تمرير دالة العرض
            onPrint={handlePrint}   // 🟢 تمرير دالة الطباعة
            onDelete={handleDelete} // 🔴 تمرير دالة الحذف
            items={items}
            suppliers={suppliers}
            onConvertToDeal={handleConvertToDeal}
          />
        ) : (
          <InvoiceForm
            invoice={currentInvoice}
            currentUser={currentUser}
            onCancel={handleExitForm}
            // تمرير خاصية للقراءة فقط (يجب استقبالها داخل InvoiceForm)
            // ملاحظة: تأكدنا أن المكونات الفرعية داخل InvoiceForm تستقبل readOnly
            // لذا سنحتاج لتعديل بسيط في InvoiceForm لاستقبال هذا الـ Prop وتمريره
            readOnly={isReadOnly}
            onSave={() => {
              // إذا كنا في وضع التعديل، نبقى في الصفحة
              // إذا كنا في وضع العرض، هذا الزر أصلاً لن يظهر أو سيكون معطلاً
            }}
            allDbItems={items}
          />
        )}
      </div>

      {showImportModal && (
        <ShipmentImportModal
          isOpen={showImportModal}
          onClose={() => setShowImportModal(false)}
          onImport={handleImportShipmentInvoices}
          currentUser={currentUser}
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