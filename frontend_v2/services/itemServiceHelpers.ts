import { Invoice, Supplier, Item } from '../types';

/**
 * جلب جميع الفواتير التي تحتوي على منتج معين
 */
export const getInvoicesByItem = (allInvoices: Invoice[], itemId: string): Invoice[] => {
  return allInvoices.filter(invoice => 
    invoice.items && invoice.items.some(invItem => invItem.itemId === itemId)
  );
};

/**
 * جلب جميع الموردين الذين تم شراء هذا المنتج منهم
 * يتم ذلك عن طريق البحث في الفواتير أولاً ثم استخراج الموردين
 */
export const getSuppliersByItem = (
  allInvoices: Invoice[], 
  allSuppliers: Supplier[], 
  itemId: string
): { supplier: Supplier, lastPurchaseDate: string, totalQuantity: number }[] => {
  
  // 1. نجد الفواتير التي تحتوي المنتج
  const relevantInvoices = getInvoicesByItem(allInvoices, itemId);

  // 2. نقوم بتجميع البيانات حسب المورد
  const supplierMap = new Map<string, { lastDate: string, quantity: number }>();

  relevantInvoices.forEach(inv => {
    const itemInInvoice = inv.items.find(i => i.itemId === itemId);
    const qty = itemInInvoice ? Number(itemInInvoice.quantity) : 0;
    
    if (inv.supplierId) {
      const existing = supplierMap.get(inv.supplierId) || { lastDate: '', quantity: 0 };
      
      // تحديث آخر تاريخ شراء
      const invDate = inv.createdAt;
      const isNewer = !existing.lastDate || new Date(invDate) > new Date(existing.lastDate);
      
      supplierMap.set(inv.supplierId, {
        lastDate: isNewer ? invDate : existing.lastDate,
        quantity: existing.quantity + qty
      });
    }
  });

  // 3. نربط المعرفات ببيانات الموردين الكاملة
  const result: { supplier: Supplier, lastPurchaseDate: string, totalQuantity: number }[] = [];
  
  supplierMap.forEach((data, supplierId) => {
    const supplierObj = allSuppliers.find(s => s.id === supplierId);
    if (supplierObj) {
      result.push({
        supplier: supplierObj,
        lastPurchaseDate: data.lastDate,
        totalQuantity: data.quantity
      });
    }
  });

  return result;
};