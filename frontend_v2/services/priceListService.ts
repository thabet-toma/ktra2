import { 
  collection, 
  doc, 
  getDocs, 
  orderBy, 
  query, 
  where,
  setDoc,
  limit,
  db
} from "./sqlApiClient";
import { Invoice, SupplierItemPrice } from "../types";

// Price List Service
export const priceListService = {
  // دالة لتسجيل أسعار المنتجات من الفاتورة
  recordPricesFromInvoice: async (invoice: Invoice) => {
    const promises = invoice.items.map(async (item) => {
      const priceRecordId = crypto.randomUUID();
      
      const priceRecord: SupplierItemPrice = {
        id: priceRecordId,
        supplierId: invoice.supplierId,
        supplierName: invoice.factoryName || 'Unknown',
        itemId: item.itemId,
        itemName: item.name,
        price: item.unitPrice,
        currency: 'USD',
        date: invoice.invoiceDate || new Date().toISOString(),
        invoiceId: invoice.id,
        createdAt: new Date().toISOString()
      };

      await setDoc(doc(db, "supplier_prices", priceRecordId), priceRecord);
    });

    await Promise.all(promises);
  },

  // دالة لجلب سجل أسعار منتج معين
  getItemPriceHistory: async (itemId: string) => {
    const q = query(
      collection(db, "supplier_prices"), 
      where("itemId", "==", itemId),
      orderBy("date", "desc")
    );
    const snapshot = await getDocs(q);
    return snapshot.docs.map(doc => doc.data() as SupplierItemPrice);
  },

  // دالة جديدة: جلب آخر سعر من مورد معين لمنتج معين
  getLastSupplierPrice: async (supplierId: string, itemId: string): Promise<number> => {
    if (!supplierId || !itemId) return 0;
    
    try {
      const q = query(
        collection(db, "supplier_prices"),
        where("supplierId", "==", supplierId),
        where("itemId", "==", itemId),
        orderBy("date", "desc"),
        limit(1)
      );
      
      const snapshot = await getDocs(q);
      
      if (!snapshot.empty) {
        const priceRecord = snapshot.docs[0].data() as SupplierItemPrice;
        return priceRecord.price || 0;
      }
      
      return 0;
    } catch (error) {
      // console suppressed
      return 0;
    }
  },

  // دالة إضافية: جلب كل الأسعار من مورد معين لمنتجات متعددة
  getSupplierPricesForItems: async (supplierId: string, itemIds: string[]): Promise<Record<string, number>> => {
    const prices: Record<string, number> = {};
    
    try {
      // إذا كانت هناك مجموعة كبيرة من المنتجات، يمكن تحسين هذا
      const q = query(
        collection(db, "supplier_prices"),
        where("supplierId", "==", supplierId),
        where("itemId", "in", itemIds.length > 0 ? itemIds : ['']), // Firestore requires non-empty array
        orderBy("date", "desc")
      );
      
      const snapshot = await getDocs(q);
      
      // تجميع أحدث سعر لكل منتج
      snapshot.docs.forEach(doc => {
        const priceRecord = doc.data() as SupplierItemPrice;
        if (!prices[priceRecord.itemId]) {
          prices[priceRecord.itemId] = priceRecord.price;
        }
      });
      
    } catch (error) {
      // console suppressed
    }
    
    return prices;
  },

  // دالة إضافية: جلب كل أسعار المورد (لتاريخ معين أو حديثة)
  getSupplierAllPrices: async (supplierId: string, limitCount: number = 100) => {
    try {
      const q = query(
        collection(db, "supplier_prices"),
        where("supplierId", "==", supplierId),
        orderBy("date", "desc"),
        limit(limitCount)
      );
      
      const snapshot = await getDocs(q);
      return snapshot.docs.map(doc => doc.data() as SupplierItemPrice);
    } catch (error) {
      // console suppressed
      return [];
    }
  }
};