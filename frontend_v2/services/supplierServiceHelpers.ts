import { Invoice, InvoiceItem, Supplier } from '../types';

/**
 * جلب جميع الفواتير الخاصة بمورد معين
 */
export const getInvoicesBySupplier = (allInvoices: Invoice[], supplierId: string): Invoice[] => {
  return allInvoices.filter(invoice => invoice.supplierId === supplierId);
};

/**
 * جلب جميع المنتجات التي تم شراؤها من مورد معين
 * يتم تجميع البيانات من الفواتير لاستخراج المنتجات الفريدة وحساب الكميات
 */
export const getItemsBySupplier = (
  allInvoices: Invoice[], 
  supplierId: string
): { item: InvoiceItem, lastPurchaseDate: string, totalQuantity: number, totalSpent: number }[] => {
  
  // 1. نجد الفواتير الخاصة بالمورد
  const supplierInvoices = getInvoicesBySupplier(allInvoices, supplierId);

  // 2. تجميع المنتجات
  const itemsMap = new Map<string, { 
    itemData: InvoiceItem, 
    lastDate: string, 
    quantity: number,
    spent: number 
  }>();

  supplierInvoices.forEach(inv => {
    inv.items.forEach(invItem => {
      // نستخدم اسم المنتج كمعرف فريد إذا لم يكن هناك ID ثابت، أو نستخدم ID المنتج إذا توفر
      const key = invItem.itemId || invItem.name; 
      
      const existing = itemsMap.get(key) || { 
        itemData: invItem, 
        lastDate: '', 
        quantity: 0,
        spent: 0
      };

      // تحديث التاريخ للأحدث
      const invDate = inv.createdAt;
      const isNewer = !existing.lastDate || new Date(invDate) > new Date(existing.lastDate);

      itemsMap.set(key, {
        itemData: invItem, // نحتفظ بآخر بيانات للمنتج
        lastDate: isNewer ? invDate : existing.lastDate,
        quantity: existing.quantity + Number(invItem.quantity || 0),
        spent: existing.spent + Number(invItem.totalPrice || 0)
      });
    });
  });

  // 3. تحويل Map إلى مصفوفة
  return Array.from(itemsMap.values()).map(data => ({
    item: data.itemData,
    lastPurchaseDate: data.lastDate,
    totalQuantity: data.quantity,
    totalSpent: data.spent
  }));
};