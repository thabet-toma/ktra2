/**
 * درج سلة المشتريات التفاعلي — استعراض المنتجات وإرسال الطلب عبر الواتساب.
 */
import React, { useState } from "react";
import { MessageCircle, Minus, Plus, ShoppingBag, Trash2, X } from "lucide-react";
import { useStoreCart } from "../../contexts/StoreCartContext";
import { formatMoney } from "../../utils/formatNumber";
import { useToast } from "../../contexts/ToastContext";
import { whatsappLink } from "../../utils/storeLinks";

interface StoreCartDrawerProps {
  storeName: string;
  storePhone?: string | null;
  currency: string | null;
}

export const StoreCartDrawer: React.FC<StoreCartDrawerProps> = ({
  storeName,
  storePhone,
  currency,
}) => {
  const toast = useToast();
  const {
    items,
    updateQuantity,
    removeItem,
    clearCart,
    totalCount,
    subtotal,
    isCartOpen,
    setIsCartOpen,
    buildWhatsAppMessage,
  } = useStoreCart();

  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerAddress, setCustomerAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [sending, setSending] = useState(false);

  if (!isCartOpen) return null;

  const handleCheckoutWhatsApp = () => {
    if (items.length === 0) {
      toast("السلة فارغة", "error");
      return;
    }
    if (!customerName.trim()) {
      toast("يرجى كتابة اسمك لإتمام الطلب", "error");
      return;
    }
    if (!customerPhone.trim()) {
      toast("يرجى كتابة رقم الهاتف للتواصل والتوصيل", "error");
      return;
    }

    setSending(true);
    const message = buildWhatsAppMessage(storeName, currency, {
      name: customerName,
      phone: customerPhone,
      address: customerAddress,
      notes,
    });

    const targetPhone = storePhone || "";
    const link = whatsappLink(targetPhone, message);

    if (!link) {
      toast("تعذّر فتح الواتساب — تأكد من صحة رقم هاتف المتجر", "error");
      setSending(false);
      return;
    }

    window.open(link, "_blank", "noopener,noreferrer");
    setSending(false);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden font-sans" dir="rtl">
      {/* الخلفية المعتمة */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={() => setIsCartOpen(false)}
      />

      <div className="fixed inset-y-0 left-0 flex max-w-full pl-0 sm:pl-10">
        <div className="flex w-screen max-w-md flex-col bg-white shadow-2xl dark:bg-slate-900">
          {/* ترويسة الدرج */}
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                <ShoppingBag className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-white">
                  سلة المشتريات
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {totalCount} {totalCount === 1 ? "منتج" : "منتجات"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {items.length > 0 && (
                <button
                  type="button"
                  onClick={clearCart}
                  className="text-xs text-rose-500 hover:underline"
                >
                  إفراغ السلة
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsCartOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* محتويات السلة */}
          <div className="flex-1 overflow-y-auto p-5">
            {items.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                  <ShoppingBag className="h-8 w-8 text-slate-400" />
                </div>
                <h3 className="mt-4 text-base font-bold text-slate-800 dark:text-slate-200">
                  سلتك فارغة حالياً
                </h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  تصفح المنتجات وأضف ما ترغب به لطلبها مباشرة
                </p>
                <button
                  type="button"
                  onClick={() => setIsCartOpen(false)}
                  className="mt-5 rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white transition hover:bg-blue-700"
                >
                  متابعة التسوق
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {/* قائمة العناصر */}
                <div className="space-y-3">
                  {items.map((item) => (
                    <div
                      key={item.productId}
                      className="flex items-center gap-3 rounded-2xl border border-slate-100 bg-slate-50/70 p-3 dark:border-slate-800/80 dark:bg-slate-800/50"
                    >
                      {item.image ? (
                        <img
                          src={item.image}
                          alt={item.name}
                          className="h-16 w-16 rounded-xl object-cover"
                        />
                      ) : (
                        <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-slate-200 text-xs text-slate-400 dark:bg-slate-700">
                          بلا صورة
                        </div>
                      )}

                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-1">
                          <h4 className="truncate text-xs font-bold text-slate-800 dark:text-slate-100">
                            {item.name}
                          </h4>
                          <button
                            type="button"
                            onClick={() => removeItem(item.productId)}
                            className="text-slate-400 hover:text-rose-500"
                            title="حذف الصنف"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>

                        {item.isPreorder && (
                          <span className="mt-0.5 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/80 dark:text-amber-300">
                            طلب مسبق
                          </span>
                        )}

                        <div className="mt-2 flex items-center justify-between">
                          <span className="text-xs font-black text-blue-600 dark:text-blue-400">
                            {formatMoney(item.price * item.quantity)} {currency || "₪"}
                          </span>

                          <div className="flex items-center rounded-lg border border-slate-200 bg-white px-1 py-0.5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
                            <button
                              type="button"
                              onClick={() => updateQuantity(item.productId, item.quantity - 1)}
                              className="p-1 text-slate-600 hover:text-slate-900 dark:text-slate-300"
                            >
                              <Minus className="h-3 w-3" />
                            </button>
                            <span className="w-6 text-center text-xs font-bold text-slate-800 dark:text-slate-200">
                              {item.quantity}
                            </span>
                            <button
                              type="button"
                              onClick={() => updateQuantity(item.productId, item.quantity + 1)}
                              className="p-1 text-slate-600 hover:text-slate-900 dark:text-slate-300"
                            >
                              <Plus className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* نموذج بيانات العميل */}
                <div className="mt-6 rounded-2xl border border-slate-200/80 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-800/30">
                  <h4 className="mb-3 text-xs font-bold text-slate-700 dark:text-slate-300">
                    بيانات إرسال الطلب والتوصيل
                  </h4>
                  <div className="space-y-2.5">
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-400">
                        الاسم الكريم <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={customerName}
                        onChange={(e) => setCustomerName(e.target.value)}
                        placeholder="مثال: أحمد خليل"
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-400">
                        رقم الهاتف للتواصل <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="tel"
                        value={customerPhone}
                        onChange={(e) => setCustomerPhone(e.target.value)}
                        placeholder="مثال: 0599123456"
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-400">
                        العنوان / المدينة والشارع
                      </label>
                      <input
                        type="text"
                        value={customerAddress}
                        onChange={(e) => setCustomerAddress(e.target.value)}
                        placeholder="مثال: رام الله — شارع الإرسال"
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-400">
                        ملاحظات إضافية (اختياري)
                      </label>
                      <textarea
                        rows={2}
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="أي تفاصيل خاصة بالمقاس أو موعد التوصيل..."
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* التذييل والإجمالي مع زر الواتساب */}
          {items.length > 0 && (
            <div className="border-t border-slate-200 bg-slate-50 p-5 dark:border-slate-800 dark:bg-slate-900/90">
              <div className="mb-4 flex items-center justify-between text-sm">
                <span className="font-medium text-slate-600 dark:text-slate-400">المجموع الإجمالي:</span>
                <span className="text-lg font-black text-slate-900 dark:text-white">
                  {formatMoney(subtotal)} {currency || "₪"}
                </span>
              </div>

              <button
                type="button"
                onClick={handleCheckoutWhatsApp}
                disabled={sending}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-5 py-3.5 text-sm font-bold text-white shadow-lg shadow-emerald-600/30 transition hover:bg-emerald-700 active:scale-[0.99] disabled:opacity-50"
              >
                <MessageCircle className="h-5 w-5 fill-current" />
                <span>إرسال الطلب عبر الواتساب</span>
              </button>
              <p className="mt-2 text-center text-[11px] text-slate-400">
                سيتم فتح محادثة الواتساب مع المتجر مباشرة متضمنة تفاصيل طلبك
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
