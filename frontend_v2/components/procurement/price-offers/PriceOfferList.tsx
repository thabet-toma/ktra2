// import React from 'react';
// import { PriceOffer } from '../../../types';
// import { 
//   Edit, FileText, DollarSign, Calendar, Building, 
//   CheckCircle2, Clock, XCircle, ArrowRight, Package,
//   MessageSquare // أيقونة جديدة للملاحظات
// } from 'lucide-react';

// interface PriceOfferListProps {
//   offers: PriceOffer[];
//   onEdit: (offer: PriceOffer) => void;
// }

// export const PriceOfferList: React.FC<PriceOfferListProps> = ({ offers, onEdit }) => {

//   // دالة لتحديد لون الحالة
//   const getStatusColor = (status: PriceOffer['status']) => {
//     switch (status) {
//       case 'initial': return 'aseel-bg-panel aseel-text-ink aseel-border-soft';
//       case 'pending_info': return 'aseel-bg-panel aseel-text-ink aseel-border-soft';
//       case 'under_discussion': return 'aseel-bg-accent-bg aseel-text-accent aseel-border-accent';
//       case 'approved_for_shipping': return 'bg-green-50 text-green-700 aseel-border-soft';
//       case 'rejected': return 'aseel-bg-panel aseel-text-state aseel-border-soft';
//       default: return 'aseel-bg-panel aseel-text-ink aseel-border-soft';
//     }
//   };

//   // ترجمة الحالة
//   const getStatusText = (status: PriceOffer['status']) => {
//     const statusMap: Record<string, string> = {
//       'initial': 'مسودة / أولي',
//       'pending_info': 'بانتظار معلومات',
//       'under_discussion': 'قيد المناقشة',
//       'approved_for_shipping': 'معتمد للشحن',
//       'rejected': 'مرفوض'
//     };
//     return statusMap[status] || status;
//   };

//   // أيقونة الحالة
//   const getStatusIcon = (status: PriceOffer['status']) => {
//     if (status === 'approved_for_shipping') return <CheckCircle2 className="w-4 h-4" />;
//     if (status === 'rejected') return <XCircle className="w-4 h-4" />;
//     return <Clock className="w-4 h-4" />;
//   };

//   // دالة لاختصار النص الطويل
//   const truncateText = (text: string, maxLength: number = 100) => {
//     if (!text) return '';
//     if (text.length <= maxLength) return text;
//     return text.substring(0, maxLength) + '...';
//   };

//   return (
//     <div className="space-y-4">
//       {offers.map(offer => (
//         <div 
//           key={offer.id} 
//           className="group aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm hover:shadow-md border aseel-border-soft dark:aseel-border-soft overflow-hidden transition-all duration-300"
//         >
//           {/* Header */}
//           <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center p-4 border-b aseel-border-soft dark:aseel-border-soft aseel-bg-panel/50 dark:aseel-bg-panel/50 gap-3">
//             <div className="flex items-center gap-3">
//               <div className="aseel-bg-field dark:aseel-bg-panel p-2 rounded-lg border aseel-border-soft dark:aseel-border-soft shadow-sm">
//                 <span className="font-mono font-bold text-lg aseel-text-accent dark:aseel-text-soft">
//                   {offer.offerNumber}
//                 </span>
//               </div>
//               <div className="flex flex-col">
//                 <h3 className="font-bold aseel-text-ink dark:text-white flex items-center gap-2">
//                   <Building className="w-4 h-4 aseel-text-soft" />
//                   {offer.factoryName || 'مورد غير محدد'}
//                 </h3>
//                 <span className="text-xs aseel-text-soft flex items-center gap-1">
//                   <Calendar className="w-3 h-3" />
//                   {new Date(offer.createdAt).toLocaleDateString('ar-EG')}
//                 </span>
//               </div>
//             </div>

//             <div className={`px-3 py-1 rounded-full text-sm font-medium border ${getStatusColor(offer.status)} flex items-center gap-2`}>
//               {getStatusIcon(offer.status)}
//               {getStatusText(offer.status)}
//             </div>
//           </div>

//           {/* Body */}
//           <div className="p-5">
//             <div className="flex flex-col lg:flex-row gap-6">
              
//               {/* Items Summary */}
//               <div className="flex-1">
//                 <div className="text-sm font-medium aseel-text-soft mb-2 flex items-center gap-1">
//                   <Package className="w-4 h-4" />
//                   أبرز المنتجات ({offer.items?.length || 0})
//                 </div>
//                 <div className="flex flex-wrap gap-2 mb-3">
//                   {offer.items && offer.items.length > 0 ? (
//                     offer.items.slice(0, 3).map((item, idx) => (
//                       <span key={idx} className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium aseel-bg-panel dark:aseel-bg-panel aseel-text-ink dark:aseel-text-soft border aseel-border-soft dark:aseel-border-soft">
//                         {item.name}
//                         <span className="mr-1 aseel-text-soft">×{item.quantity}</span>
//                       </span>
//                     ))
//                   ) : (
//                     <span className="text-sm aseel-text-soft italic">لا توجد منتجات</span>
//                   )}
//                   {(offer.items?.length || 0) > 3 && (
//                     <span className="text-xs aseel-text-soft self-center">
//                       +{offer.items.length - 3} المزيد...
//                     </span>
//                   )}
//                 </div>

//                 {/* Internal Notes Preview */}
//                 {offer.internalNotes && (
//                   <div className="mt-3 pt-3 border-t aseel-border-soft dark:aseel-border-soft">
//                     <div className="text-sm font-medium aseel-text-soft mb-1 flex items-center gap-1">
//                       <MessageSquare className="w-4 h-4" />
//                       ملاحظات داخلية
//                     </div>
//                     <p className="text-sm aseel-text-soft dark:aseel-text-soft line-clamp-2">
//                       {truncateText(offer.internalNotes, 120)}
//                     </p>
//                   </div>
//                 )}
//               </div>

//               {/* Financials */}
//               <div className="flex-1 lg:max-w-sm">
//                 <div className="grid grid-cols-2 gap-4">
//                   <div className="flex flex-col">
//                     <span className="text-xs aseel-text-soft dark:aseel-text-soft mb-1">المجموع الفرعي</span>
//                     <span className="font-semibold aseel-text-ink dark:aseel-text-soft">
//                       ${offer.subtotal?.toLocaleString()}
//                     </span>
//                   </div>
//                   <div className="flex flex-col">
//                     <span className="text-xs aseel-text-soft dark:aseel-text-soft mb-1">الإجمالي النهائي</span>
//                     <span className="font-bold text-xl text-green-600 dark:text-green-400 flex items-center gap-1">
//                       <DollarSign className="w-5 h-5" />
//                       {offer.grandTotal?.toLocaleString()}
//                     </span>
//                   </div>
//                   {offer.shipmentNotes && (
//                     <div className="col-span-2 mt-2">
//                       <span className="text-xs aseel-text-soft dark:aseel-text-soft mb-1">ملاحظات الشحن</span>
//                       <p className="text-xs aseel-text-soft dark:aseel-text-soft truncate">
//                         {truncateText(offer.shipmentNotes || '', 60)}
//                       </p>
//                     </div>
//                   )}
//                 </div>
//               </div>
//             </div>

//             {/* Footer Action */}
//             <div className="mt-5 pt-4 border-t aseel-border-soft dark:aseel-border-soft flex justify-end">
//               <button
//                 onClick={() => onEdit(offer)}
//                 className="inline-flex items-center gap-2 px-5 py-2 aseel-bg-accent hover:aseel-bg-accent text-white rounded-lg transition-colors shadow-sm text-sm font-medium"
//               >
//                 <Edit className="w-4 h-4" />
//                 تعديل / عرض التفاصيل
//                 <ArrowRight className="w-4 h-4 opacity-70" />
//               </button>
//             </div>
//           </div>
//         </div>
//       ))}

//       {offers.length === 0 && (
//         <div className="text-center py-16 aseel-bg-field dark:aseel-bg-panel rounded-xl border border-dashed aseel-border-soft dark:aseel-border-soft">
//           <div className="w-20 h-20 aseel-bg-panel dark:aseel-bg-panel rounded-full flex items-center justify-center mx-auto mb-4">
//             <FileText className="w-10 h-10 aseel-text-soft" />
//           </div>
//           <h3 className="text-lg font-bold aseel-text-ink dark:text-white mb-1">لا توجد عروض أسعار</h3>
//           <p className="aseel-text-soft dark:aseel-text-soft">ابدأ بإنشاء عرض سعر جديد الآن</p>
//         </div>
//       )}
//     </div>
//   );
// };