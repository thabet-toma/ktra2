// import React, { useState } from 'react';
// import { Truck, Upload, Loader2 } from 'lucide-react';
// import { cloudinaryService } from '@/services/cloudinaryService';
// import { PaymentRegistration } from './PaymentRegistration';

// interface ShippingProps {
//     data: any;
//     setData: (data: any) => void;
//     onSecondPaymentConfirm: (data: any) => void;
//     onPrepareShipping: () => void;
//     paymentType: string;
//     onSaveClaim: (data: any) => void;
//     onSavePayment: (data: any) => void;
//     onConfirmSupplier: (data: any) => void;
//     currentUser: any;
// }

// export const ShippingPrepSection: React.FC<ShippingProps> = ({ data, setData, onSecondPaymentConfirm, onPrepareShipping, paymentType, onSaveClaim, onSavePayment, onConfirmSupplier, currentUser }) => {
//     const [uploading, setUploading] = useState(false);

//     const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
//         if (!e.target.files?.[0]) return;
//         setUploading(true);
//         try {
//             const url = await cloudinaryService.uploadImage(e.target.files[0]);
//             setData((prev: any) => ({ ...prev, shippingDetails: { ...prev.shippingDetails, shipmentImageUrl: url } }));
//         } catch (err) { alert('فشل الرفع'); }
//         finally { setUploading(false); }
//     };

//     return (
//         <div className="bg-orange-50 dark:bg-orange-900/20 p-6 rounded-xl border border-orange-200 dark:border-orange-800 space-y-6">
//             <h3 className="text-lg font-bold text-[var(--color-text)] flex items-center gap-2">
//                 <Truck className="w-5 h-5 text-orange-500" /> تجهيز الشحنة والدفعة الثانية
//             </h3>

//             {/* 1. Shipping Details */}
//             <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
//                 <div>
//                     <label className="block text-sm font-medium mb-1 dark:text-gray-300">عنوان الشحن الكامل</label>
//                     <textarea
//                         value={data.shippingDetails?.address || ''}
//                         onChange={e => setData((p: any) => ({ ...p, shippingDetails: { ...p.shippingDetails, address: e.target.value } }))}
//                         className="w-full p-3 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white h-32"
//                         placeholder="العنوان، المستلم، رقم الهاتف..."
//                     />
//                 </div>
//                 <div>
//                     <label className="block text-sm font-medium mb-1 dark:text-gray-300">صورة الشحنة (الكراتين)</label>
//                     <div className="border-2 border-dashed border-[var(--color-border)] rounded-lg h-32 flex items-center justify-center relative bg-[var(--color-surface)]">
//                         {data.shippingDetails?.shipmentImageUrl ? (
//                             <img src={data.shippingDetails.shipmentImageUrl} className="h-full w-full object-contain rounded-lg" alt="shipment" />
//                         ) : (
//                             <label className="cursor-pointer flex flex-col items-center">
//                                 {uploading ? <Loader2 className="animate-spin text-orange-500" /> : <Upload className="text-[var(--color-text-muted)]" />}
//                                 <span className="text-xs text-[var(--color-text-muted)] mt-1">اضغط لرفع صورة الشحنة</span>
//                                 <input type="file" className="hidden" accept="image/*" onChange={handleImageUpload} />
//                             </label>
//                         )}
//                     </div>
//                 </div>
//             </div>

//             {/* 2. Second Payment */}
//             <div className="border-t border-orange-200 dark:border-orange-800 pt-6">
//                 <PaymentRegistration
//                     title="الدفعة الثانية (الأخيرة)"
//                     paymentData={data.secondPayment}
//                     paymentType={paymentType}
//                     onSaveClaim={onSaveClaim}
//                     onSavePayment={onSavePayment}
//                     onConfirmSupplier={onConfirmSupplier}
//                     currentUser={currentUser}
//                 />
//             </div>

//             {/* 3. Final Action */}
//             <button
//                 onClick={onPrepareShipping}
//                 disabled={!data.secondPayment || !data.shippingDetails?.address}
//                 className="w-full py-3 bg-green-600 hover:bg-green-700 text-white font-bold rounded-xl shadow-lg disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all"
//             >
//                 <Truck className="w-5 h-5" />
//                 جاهزة للشحن
//             </button>
//         </div>
//     );
// };