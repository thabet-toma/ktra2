
// import React, { useState } from 'react';
// import { DollarSign, Upload, X, Loader2, CheckCircle } from 'lucide-react';
// import { cloudinaryService } from '@/services/cloudinaryService';

// interface PaymentProps {
//   title: string;
//   paymentData: any; // First or Second payment object from deal
//   onConfirm: (data: any) => void;
//   isPaid: boolean;
//   required?: boolean;
// }

// export const PaymentRegistration: React.FC<PaymentProps> = ({ title, paymentData, onConfirm, isPaid }) => {
//   // Local state for the form inputs
//   const [input, setInput] = useState({
//     amount: 0, usdToIls: 0, transferCost: 0, notes: '',
//     alibabaImageUrl: '', swiftImageUrl: '',
//     isUploadingAlibaba: false, isUploadingSwift: false
//   });

//   const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>, type: 'alibaba' | 'swift') => {
//     if (!e.target.files?.[0]) return;
//     const file = e.target.files[0];
//     const loadingKey = type === 'alibaba' ? 'isUploadingAlibaba' : 'isUploadingSwift';
//     const urlKey = type === 'alibaba' ? 'alibabaImageUrl' : 'swiftImageUrl';

//     setInput(prev => ({ ...prev, [loadingKey]: true }));
//     try {
//         const url = await cloudinaryService.uploadImage(file);
//         setInput(prev => ({ ...prev, [urlKey]: url }));
//     } catch (err) { alert('Upload failed'); }
//     finally { setInput(prev => ({ ...prev, [loadingKey]: false })); }
//   };

//   if (isPaid) {
//       return (
//           <div className="bg-green-50 dark:bg-green-900/20 p-4 rounded-lg border border-green-200 dark:border-green-800 flex items-center gap-3">
//               <CheckCircle className="text-green-600 w-6 h-6" />
//               <div>
//                   <h4 className="font-bold text-green-800 dark:text-green-300">{title} مدفوعة</h4>
//                   <p className="text-sm text-green-700 dark:text-green-400">المبلغ: ${paymentData?.amount} - التاريخ: {new Date(paymentData?.date).toLocaleDateString()}</p>
//               </div>
//           </div>
//       );
//   }

//   return (
//     <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
//         <h3 className="font-bold text-lg mb-4 dark:text-white">{title}</h3>
//         <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
//              <input type="number" placeholder="المبلغ ($)" value={input.amount || ''} onChange={e => setInput({...input, amount: parseFloat(e.target.value)})} className="p-3 border rounded dark:bg-gray-700 dark:text-white"/>
//              <input type="number" placeholder="سعر الدولار" value={input.usdToIls || ''} onChange={e => setInput({...input, usdToIls: parseFloat(e.target.value)})} className="p-3 border rounded dark:bg-gray-700 dark:text-white"/>
//              <input type="number" placeholder="تكلفة الحوالة" value={input.transferCost || ''} onChange={e => setInput({...input, transferCost: parseFloat(e.target.value)})} className="p-3 border rounded dark:bg-gray-700 dark:text-white"/>
//         </div>
        
//         <div className="grid grid-cols-2 gap-4 mb-4">
//             {/* Upload Buttons Logic (Simplified for brevity) */}
//             {['alibaba', 'swift'].map(type => (
//                 <div key={type} className="border border-dashed p-4 rounded text-center">
//                     <p className="mb-2 text-sm dark:text-gray-300">{type === 'alibaba' ? 'صورة علي بابا' : 'صورة Swift'} *</p>
//                     {input[type === 'alibaba' ? 'alibabaImageUrl' : 'swiftImageUrl'] ? (
//                         <div className="relative inline-block">
//                              <img src={input[type === 'alibaba' ? 'alibabaImageUrl' : 'swiftImageUrl']} className="h-20 rounded" />
//                              {/* Remove button logic here */}
//                         </div>
//                     ) : (
//                         <label className="cursor-pointer block">
//                             {input[type === 'alibaba' ? 'isUploadingAlibaba' : 'isUploadingSwift'] ? <Loader2 className="animate-spin mx-auto"/> : <Upload className="mx-auto text-gray-400"/>}
//                             <input type="file" className="hidden" onChange={(e) => handleUpload(e, type as any)} />
//                         </label>
//                     )}
//                 </div>
//             ))}
//         </div>

//         <button onClick={() => onConfirm(input)} className="w-full py-2 bg-blue-600 text-white rounded hover:bg-blue-700">تأكيد الدفع</button>
//     </div>
//   );
// };