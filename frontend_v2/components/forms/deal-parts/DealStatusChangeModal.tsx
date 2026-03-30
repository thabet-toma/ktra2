// import React, { useState } from 'react';
// import { DealStatus } from '../../../types';
// import { 
//   X, 
//   Save, 
//   AlertCircle, 
//   CheckCircle, 
//   Clock, 
//   DollarSign, 
//   Factory, 
//   Package, 
//   Truck,
//   CheckSquare,
//   Ban,
//   MessageSquare
// } from 'lucide-react';

// interface DealStatusChangeModalProps {
//     isOpen: boolean;
//     onClose: () => void;
//     onConfirm: (status: DealStatus) => void; // تم إزالة notes من هنا
//     currentStatus: DealStatus;
//     newStatus: DealStatus;
// }

// export const DealStatusChangeModal: React.FC<DealStatusChangeModalProps> = ({
//     isOpen,
//     onClose,
//     onConfirm,
//     currentStatus,
//     newStatus
// }) => {
//     if (!isOpen) return null;

//     // ترجمة حالات الصفقة مع الأيقونات
//     const statusConfig: Record<DealStatus, { label: string; icon: React.ElementType; color: string }> = {
//         'initial': { label: 'مسودة / أولي', icon: FileText, color: 'text-gray-500 bg-gray-100' },
//         'first_payment_pending': { label: 'بانتظار الدفعة الأولى', icon: Clock, color: 'text-yellow-500 bg-yellow-100' },
//         'first_payment_completed': { label: 'تم دفع العربون', icon: DollarSign, color: 'text-green-500 bg-green-100' },
//         'in_production': { label: 'قيد التصنيع', icon: Factory, color: 'text-blue-500 bg-blue-100' },
//         'ready_stock': { label: 'مخزون جاهز', icon: Package, color: 'text-purple-500 bg-purple-100' },
//         'production_completed': { label: 'انتهى التصنيع', icon: CheckCircle, color: 'text-indigo-500 bg-indigo-100' },
//         'shipping_preparation': { label: 'تجهيز الشحن', icon: Package, color: 'text-orange-500 bg-orange-100' },
//         'ready_for_shipping': { label: 'جاهز للشحن', icon: Truck, color: 'text-teal-500 bg-teal-100' },
//         'shipped': { label: 'تم الشحن', icon: Truck, color: 'text-cyan-500 bg-cyan-100' },
//         'completed': { label: 'مكتملة', icon: CheckSquare, color: 'text-emerald-500 bg-emerald-100' },
//         'cancelled': { label: 'ملغاة', icon: Ban, color: 'text-red-500 bg-red-100' }
//     };

//     const currentConfig = statusConfig[currentStatus] || { label: currentStatus, icon: AlertCircle, color: 'text-gray-500 bg-gray-100' };
//     const newConfig = statusConfig[newStatus] || { label: newStatus, icon: AlertCircle, color: 'text-blue-500 bg-blue-100' };
    
//     const CurrentIcon = currentConfig.icon;
//     const NewIcon = newConfig.icon;

//     return (
//         <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
//             <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md overflow-hidden border border-gray-200 dark:border-gray-700">
//                 <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-900/50">
//                     <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
//                         <AlertCircle className="w-5 h-5 text-blue-500" />
//                         تأكيد تغيير الحالة
//                     </h3>
//                     <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors">
//                         <X className="w-5 h-5" />
//                     </button>
//                 </div>

//                 <div className="p-6 space-y-6">
//                     {/* Status Transition Visualization */}
//                     <div className="flex items-center justify-between">
//                         <div className="text-center">
//                             <div className={`flex items-center justify-center w-16 h-16 rounded-full ${currentConfig.color} border-2 border-white dark:border-gray-800 mb-2 shadow-sm`}>
//                                 <CurrentIcon className="w-7 h-7" />
//                             </div>
//                             <div className="text-sm font-medium text-gray-900 dark:text-white">
//                                 {currentConfig.label}
//                             </div>
//                             <div className="text-xs text-gray-500 dark:text-gray-400">الحالية</div>
//                         </div>

//                         <div className="flex-1 flex items-center justify-center px-4">
//                             <div className="relative">
//                                 <div className="w-24 h-1 bg-gray-300 dark:bg-gray-600"></div>
//                                 <div className="absolute left-1/2 top-1/2 transform -translate-x-1/2 -translate-y-1/2">
//                                     <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-full shadow-md">
//                                         <AlertCircle className="w-6 h-6 text-blue-500" />
//                                     </div>
//                                 </div>
//                             </div>
//                         </div>

//                         <div className="text-center">
//                             <div className={`flex items-center justify-center w-16 h-16 rounded-full ${newConfig.color} border-2 border-white dark:border-gray-800 mb-2 shadow-sm`}>
//                                 <NewIcon className="w-7 h-7" />
//                             </div>
//                             <div className="text-sm font-bold text-blue-600 dark:text-blue-400">
//                                 {newConfig.label}
//                             </div>
//                             <div className="text-xs text-gray-500 dark:text-gray-400">الجديدة</div>
//                         </div>
//                     </div>

//                     {/* Informational Message */}
//                     <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border border-blue-100 dark:border-blue-800">
//                         <div className="flex items-start gap-3">
//                             <MessageSquare className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
//                             <div>
//                                 <p className="text-sm text-gray-700 dark:text-gray-300">
//                                     أنت على وشك تغيير حالة هذه الصفقة من <span className="font-bold">{currentConfig.label}</span> إلى <span className="font-bold text-blue-600 dark:text-blue-400">{newConfig.label}</span>.
//                                 </p>
//                                 <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
//                                     سيتم تسجيل هذا التغيير في سجل الحالات تلقائياً.
//                                 </p>
//                             </div>
//                         </div>
//                     </div>

//                     {/* Simple Confirmation Check */}
//                     <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
//                         <div className="w-6 h-6 flex items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 flex-shrink-0">
//                             <CheckCircle className="w-4 h-4" />
//                         </div>
//                         <p className="text-sm text-gray-600 dark:text-gray-300">
//                             هل أنت متأكد من تغيير الحالة؟
//                         </p>
//                     </div>
//                 </div>

//                 <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex gap-3 justify-end">
//                     <button 
//                         onClick={onClose}
//                         className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
//                     >
//                         إلغاء
//                     </button>
//                     <button
//                         onClick={() => onConfirm(newStatus)} // فقط تأكيد التغيير بدون notes
//                         className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white rounded-lg flex items-center gap-2 font-medium transition-colors shadow-sm hover:shadow-md"
//                     >
//                         <CheckCircle className="w-4 h-4" />
//                         تأكيد التغيير
//                     </button>
//                 </div>
//             </div>
//         </div>
//     );
// };

// // استيراد أيقونة FileText التي استخدمناها
// import { FileText } from 'lucide-react';