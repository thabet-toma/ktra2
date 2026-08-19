/**
 * سياق سلة مشتريات المتجر العام — حفظ المنتجات في المتصفح وتوليد رسالة طلب الواتساب.
 */
import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { StoreProduct, storeProductName } from "../services/storeApi";
import { formatMoney, formatQuantity } from "../utils/formatNumber";

export interface CartItem {
  productId: number;
  name: string;
  price: number;
  formattedPrice: string;
  image: string | null;
  quantity: number;
  uom: string | null;
  isPreorder: boolean;
}

export interface CustomerOrderDetails {
  name: string;
  phone: string;
  address: string;
  notes?: string;
}

interface StoreCartContextType {
  items: CartItem[];
  addItem: (product: StoreProduct, quantity?: number) => void;
  updateQuantity: (productId: number, quantity: number) => void;
  removeItem: (productId: number) => void;
  clearCart: () => void;
  totalCount: number;
  subtotal: number;
  isCartOpen: boolean;
  setIsCartOpen: (open: boolean) => void;
  buildWhatsAppMessage: (
    storeName: string,
    currency: string | null,
    customer: CustomerOrderDetails,
  ) => string;
}

const StoreCartContext = createContext<StoreCartContextType | undefined>(undefined);

interface StoreCartProviderProps {
  slug: string;
  children: React.ReactNode;
}

export const StoreCartProvider: React.FC<StoreCartProviderProps> = ({ slug, children }) => {
  const storageKey = `store_cart_${slug}`;
  const [isCartOpen, setIsCartOpen] = useState(false);

  const readCart = (key: string): CartItem[] => {
    try {
      const saved = localStorage.getItem(key);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch {
      // تجاهل أخطاء التخزين المحلي
    }
    return [];
  };

  const [items, setItems] = useState<CartItem[]>(() => readCart(storageKey));

  // تبديل المتجر يعيد تحميل سلّته: بغير ذلك تُكتب سلّة المتجر السابق فوق
  // سلّة المتجر الجديد، فيرى الزبون أصناف متجرٍ آخر في سلّته.
  const loadedKey = useRef(storageKey);
  useEffect(() => {
    if (loadedKey.current === storageKey) return;
    loadedKey.current = storageKey;
    setIsCartOpen(false);
    setItems(readCart(storageKey));
  }, [storageKey]);

  // مزامنة السلة مع التخزين المحلي
  useEffect(() => {
    if (loadedKey.current !== storageKey) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(items));
    } catch {
      // تجاهل
    }
  }, [items, storageKey]);

  const addItem = (product: StoreProduct, qty: number = 1) => {
    if (qty <= 0) return;
    const priceNum = parseFloat(product.price || "0") || 0;
    const isPreorder = product.availability === "preorder";
    const name = storeProductName(product);
    const img = product.images?.[0] || null;

    setItems((prev) => {
      const existing = prev.find((item) => item.productId === product.id);
      if (existing) {
        return prev.map((item) =>
          item.productId === product.id
            ? { ...item, quantity: item.quantity + qty }
            : item,
        );
      }
      return [
        ...prev,
        {
          productId: product.id,
          name,
          price: priceNum,
          formattedPrice: product.price || "0",
          image: img,
          quantity: qty,
          uom: product.uom_name || null,
          isPreorder,
        },
      ];
    });
    setIsCartOpen(true);
  };

  const updateQuantity = (productId: number, qty: number) => {
    if (qty <= 0) {
      removeItem(productId);
      return;
    }
    setItems((prev) =>
      prev.map((item) =>
        item.productId === productId ? { ...item, quantity: qty } : item,
      ),
    );
  };

  const removeItem = (productId: number) => {
    setItems((prev) => prev.filter((item) => item.productId !== productId));
  };

  const clearCart = () => {
    setItems([]);
  };

  const totalCount = useMemo(
    () => items.reduce((sum, item) => sum + item.quantity, 0),
    [items],
  );

  const subtotal = useMemo(
    () => items.reduce((sum, item) => sum + item.price * item.quantity, 0),
    [items],
  );

  const buildWhatsAppMessage = (
    storeName: string,
    currency: string | null,
    customer: CustomerOrderDetails,
  ): string => {
    const cur = currency || "₪";
    const itemsList = items
      .map((item, idx) => {
        const itemTotal = formatMoney(item.price * item.quantity);
        const tag = item.isPreorder ? " _(طلب مسبق)_" : "";
        const uomText = item.uom ? ` ${item.uom}` : "";
        return `${idx + 1}. *${item.name}*${tag}\n   • الكمية: ${formatQuantity(item.quantity)}${uomText} × ${formatMoney(item.price)} ${cur} = *${itemTotal} ${cur}*`;
      })
      .join("\n\n");

    return [
      `🛍️ *طلب شراء جديد من متجر: ${storeName}*`,
      `━━━━━━━━━━━━━━━━━━━━`,
      `👤 *اسم العميل:* ${customer.name.trim() || "غير محدد"}`,
      `📱 *رقم الهاتف:* ${customer.phone.trim() || "غير محدد"}`,
      `📍 *العنوان والتوصيل:* ${customer.address.trim() || "غير محدد"}`,
      customer.notes?.trim() ? `📝 *ملاحظات:* ${customer.notes.trim()}` : "",
      `━━━━━━━━━━━━━━━━━━━━`,
      `📦 *قائمة المنتجات المطلوبة:*`,
      itemsList,
      `━━━━━━━━━━━━━━━━━━━━`,
      `💰 *المجموع الإجمالي:* *${formatMoney(subtotal)} ${cur}*`,
      `\nتم إرسال هذا الطلب عبر المتجر الإلكتروني.`,
    ]
      .filter(Boolean)
      .join("\n");
  };

  return (
    <StoreCartContext.Provider
      value={{
        items,
        addItem,
        updateQuantity,
        removeItem,
        clearCart,
        totalCount,
        subtotal,
        isCartOpen,
        setIsCartOpen,
        buildWhatsAppMessage,
      }}
    >
      {children}
    </StoreCartContext.Provider>
  );
};

export const useStoreCart = () => {
  const context = useContext(StoreCartContext);
  if (!context) {
    throw new Error("useStoreCart must be used within a StoreCartProvider");
  }
  return context;
};
