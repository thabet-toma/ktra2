// TaskDetailsModal/ManagerTaskView.tsx
import React, { useState } from "react";
import { Task, Submission } from "../../types";
import { PriorityIndicator } from "../common/PriorityIndicator";
import { Users, ChevronDown, ChevronUp, Check, X, Eye, Filter, Search, Mail, Phone, Clock, AlertCircle, FileText, ImageIcon } from 'lucide-react';
import { TaskDetailsModalProps } from "./TaskDetailsModal.types";

interface ManagerViewProps extends TaskDetailsModalProps {
  stats: any;
  searchTerm: string;
  setSearchTerm: (s: string) => void;
  statusFilter: string;
  setStatusFilter: (s: string) => void;
  filteredSubmissionsData: any[];
  toggleUserExpansion: (id: string) => void;
  expandAllUsers: () => void;
  collapseAllUsers: () => void;
  onViewDetails: (userId: string, submissionId?: string) => void;
}

export const ManagerTaskView: React.FC<ManagerViewProps> = ({
  onClose, task, user,
  stats, searchTerm, setSearchTerm, statusFilter, setStatusFilter,
  filteredSubmissionsData, toggleUserExpansion, expandAllUsers, collapseAllUsers,
  onUpdateSubmissionStatus, onViewDetails
}) => {
  // حالة لتخزين رابط الصورة المراد تكبيرها (Lightbox)
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  
  const isAssignedToMe = Array.isArray(task.assignedTo) 
    ? task.assignedTo.includes(user.id) 
    : task.assignedTo === user.id;

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-start sm:items-center justify-center p-0 sm:p-4 animate-fade-in overflow-y-auto" onClick={onClose}>
        <div className="bg-white dark:bg-gray-800 w-full max-w-6xl transform transition-all flex flex-col mt-4 sm:mt-0 max-h-[calc(100dvh-2rem)] sm:max-h-[90vh] sm:rounded-2xl shadow-xl" onClick={(e) => e.stopPropagation()}>
          {/* Header */}
          <header className="flex justify-between items-center p-4 sm:p-5 border-b border-gray-200 dark:border-gray-700 flex-shrink-0 bg-white dark:bg-gray-800 sm:rounded-t-2xl sticky top-0 z-10">
            <div className="space-y-1 overflow-hidden flex-1 min-w-0">
              <h2 className="text-lg sm:text-xl md:text-2xl font-bold text-gray-800 dark:text-gray-100 truncate">
                {task.title} - لوحة المتابعة
              </h2>
              <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm">
                <PriorityIndicator priority={task.priority} />
                <span className="text-gray-500 dark:text-gray-400">تاريخ التسليم: {task.dueDate}</span>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              {isAssignedToMe && (
                <button 
                  onClick={() => onViewDetails(user.id)}
                  className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-blue-700 transition hidden sm:block"
                >
                  العمل على المهمة
                </button>
              )}
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-2xl sm:text-3xl px-2 flex-shrink-0">&times;</button>
            </div>
          </header>

          {/* Stats Grid - Clickable Filters */}
          <div className="px-4 sm:px-5 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
               <StatCard 
                 icon={<Users className="text-blue-500" />} 
                 label="الكل (المعينين)" 
                 value={stats.total} 
                 isActive={statusFilter === 'all'}
                 onClick={() => setStatusFilter('all')}
                 activeColor="border-blue-500 bg-blue-50 dark:bg-blue-900/20"
               />
               <StatCard 
                 icon={<FileText className="text-indigo-500" />} 
                 label="مسلمة (الكل)" 
                 value={stats.submitted} 
                 isActive={statusFilter === 'submitted'}
                 onClick={() => setStatusFilter('submitted')}
                 activeColor="border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20"
               />
               <StatCard 
                 icon={<Clock className="text-yellow-500" />} 
                 label="قيد المراجعة" 
                 value={stats.pending} 
                 isActive={statusFilter === 'pending'}
                 onClick={() => setStatusFilter('pending')}
                 activeColor="border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20"
               />
               <StatCard 
                 icon={<Check className="text-green-500" />} 
                 label="مقبول" 
                 value={stats.approved} 
                 isActive={statusFilter === 'approved'}
                 onClick={() => setStatusFilter('approved')}
                 activeColor="border-green-500 bg-green-50 dark:bg-green-900/20"
               />
               <StatCard 
                 icon={<X className="text-red-500" />} 
                 label="مرفوض" 
                 value={stats.rejected} 
                 isActive={statusFilter === 'rejected'}
                 onClick={() => setStatusFilter('rejected')}
                 activeColor="border-red-500 bg-red-50 dark:bg-red-900/20"
               />
               <StatCard 
                 icon={<AlertCircle className="text-purple-500" />} 
                 label="بنود جديدة" 
                 value={stats.withNewItems} 
                 isActive={statusFilter === 'with_new_items'}
                 onClick={() => setStatusFilter('with_new_items')}
                 activeColor="border-purple-500 bg-purple-50 dark:bg-purple-900/20"
               />
            </div>
          </div>

          {/* Filters */}
          <div className="px-4 sm:px-5 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            <div className="flex flex-col md:flex-row gap-3">
              <div className="flex-1 relative">
                <Search className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                <input type="text" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="ابحث عن موظف أو حالة..." className="w-full pr-10 pl-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              </div>
              <div className="w-full md:w-48">
                <div className="flex items-center gap-2">
                  <Filter className="w-4 h-4 text-gray-400" />
                  <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm">
                    <option value="all">جميع الحالات</option>
                    <option value="submitted">مسلمة (الكل)</option>
                    <option value="pending">قيد المراجعة</option>
                    <option value="approved">مقبول</option>
                    <option value="rejected">مرفوض</option>
                    <option value="not_submitted">لم يسلم</option>
                    <option value="with_new_items">بنود جديدة</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={expandAllUsers} className="px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm"><ChevronDown className="w-4 h-4 inline ml-1" />فتح الكل</button>
                <button onClick={collapseAllUsers} className="px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm"><ChevronUp className="w-4 h-4 inline ml-1" />غلق الكل</button>
              </div>
            </div>
          </div>

          {/* List Content */}
          <main className="flex-1 p-4 sm:p-5 overflow-y-auto space-y-4">
            {filteredSubmissionsData.map((data) => (
              <div key={data.userId} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                 {/* User Header Row */}
                 <div className="flex justify-between items-center p-4 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors" onClick={() => toggleUserExpansion(data.userId)}>
                    <div className="flex items-center gap-3 flex-1">
                      <div className="w-10 h-10 bg-gray-200 dark:bg-gray-700 rounded-full flex items-center justify-center">
                        <span className="font-bold text-gray-700 dark:text-gray-300">{data.user.name?.charAt(0) || '?'}</span>
                      </div>
                      <div>
                        <h3 className="font-bold text-gray-900 dark:text-white text-sm md:text-base">{data.user.name}</h3>
                        <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {data.user.email && <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{data.user.email}</span>}
                          {data.user.phone && <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{data.user.phone}</span>}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <StatusBadge submission={data.latestSubmission} />
                      {data.latestSubmission?.newItemsCount && data.latestSubmission.newItemsCount > 0 && (
                        <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs">{data.latestSubmission.newItemsCount} جديد</span>
                      )}
                      <span className="text-sm text-gray-600 dark:text-gray-400">{data.submissionCount} تسليم</span>
                      <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${data.isExpanded ? 'rotate-180' : ''}`} />
                    </div>
                 </div>

                 {/* Expanded Details */}
                 {data.isExpanded && (
                   <div className="border-t border-gray-200 dark:border-gray-700 p-4 space-y-4">
                      {data.submissions.length > 0 ? data.submissions.map((submission: Submission, subIndex: number) => {
                        
                        const allSubmissionImages = submission.items
                          ? submission.items.flatMap(item => item.images || [])
                          : [];

                        return (
                          <div key={submission.id} className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                             <div className="flex justify-between items-start mb-3">
                               <div>
                                 <h4 className="font-bold text-gray-900 dark:text-white text-sm">التسليم #{data.submissions.length - subIndex}</h4>
                                 <p className="text-xs text-gray-500 mt-1">{new Date(submission.createdAt).toLocaleString('ar-EG')}</p>
                               </div>
                               <div className="flex gap-2">
                                 {submission.status === 'pending' && (
                                   <>
                                     <button onClick={() => onUpdateSubmissionStatus(task.id, submission.id, 'approved', 'تمت الموافقة')} className="p-1.5 bg-green-100 text-green-700 rounded-lg hover:bg-green-200" title="موافقة"><Check className="w-4 h-4" /></button>
                                     <button onClick={() => { const r = prompt('سبب الرفض:'); if(r) onUpdateSubmissionStatus(task.id, submission.id, 'rejected', r); }} className="p-1.5 bg-red-100 text-red-700 rounded-lg hover:bg-red-200" title="رفض"><X className="w-4 h-4" /></button>
                                   </>
                                 )}
                                 <button onClick={() => onViewDetails(data.userId, submission.id)} className="p-1.5 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200" title="عرض التفاصيل"><Eye className="w-4 h-4" /></button>
                               </div>
                             </div>
                             
                             {allSubmissionImages.length > 0 && (
                               <div className="mt-3">
                                 <h5 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1">
                                   <ImageIcon className="w-3 h-3" /> صور التسليم ({allSubmissionImages.length})
                                 </h5>
                                 <div className="flex flex-wrap gap-2">
                                   {allSubmissionImages.map((imgUrl, idx) => (
                                     <div 
                                       key={idx} 
                                       className="group relative w-16 h-16 sm:w-20 sm:h-20 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-600 cursor-zoom-in"
                                       onClick={() => setPreviewImage(imgUrl)}
                                     >
                                       <img 
                                         src={imgUrl} 
                                         alt={`Item Image ${idx + 1}`} 
                                         className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110" 
                                       />
                                       <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
                                     </div>
                                   ))}
                                 </div>
                               </div>
                             )}

                             {submission.items && submission.items.length > 0 && (
                               <div className="mt-3 max-h-40 overflow-y-auto space-y-2">
                                 {submission.items.map((item, i) => (
                                   <div key={i} className="bg-gray-50 dark:bg-gray-700/50 p-2 rounded text-xs">
                                     <div className="flex justify-between items-start">
                                        <p className="font-medium text-gray-800 dark:text-gray-200">{item.productLink || 'بند بدون رابط'}</p>
                                        {item.images && item.images.length > 0 && <ImageIcon className="w-3 h-3 text-blue-500" />}
                                     </div>
                                     {item.productPrice && <p className="text-gray-600 mt-1">السعر: {item.productPrice} $</p>}
                                   </div>
                                 ))}
                               </div>
                             )}
                          </div>
                        );
                      }) : <p className="text-center py-6 text-gray-500 text-sm">لم يسلم هذا الموظف بعد</p>}
                   </div>
                 )}
              </div>
            ))}
            {filteredSubmissionsData.length === 0 && <div className="text-center py-12 text-gray-500"><p>لا توجد نتائج مطابقة</p></div>}
          </main>
          
          <footer className="p-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex justify-end">
            <button onClick={onClose} className="px-6 py-2.5 bg-gray-200 text-gray-800 font-bold rounded-lg hover:bg-gray-300">إغلاق</button>
          </footer>
        </div>
      </div>

      {previewImage && (
        <div 
          className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center p-4 animate-fade-in backdrop-blur-sm"
          onClick={() => setPreviewImage(null)}
        >
          <button 
            className="absolute top-4 right-4 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition"
            onClick={() => setPreviewImage(null)}
          >
            <X className="w-8 h-8" />
          </button>
          <img 
            src={previewImage} 
            alt="Preview" 
            className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
};

// مكون StatCard المحدث ليدعم النقر والحالة النشطة
const StatCard = ({ icon, label, value, isActive, onClick, activeColor }: any) => (
  <div
    onClick={onClick}
    className={`
      p-3 rounded-lg border transition-all cursor-pointer select-none
      flex items-center gap-2
      ${isActive 
        ? `${activeColor} ring-1 ring-offset-0 shadow-md transform scale-105` 
        : "bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500 hover:shadow-sm"
      }
    `}
  >
    <div className="w-4 h-4">{icon}</div>
    <div>
      <p className={`text-xs ${isActive ? 'text-gray-800 dark:text-gray-100 font-semibold' : 'text-gray-500 dark:text-gray-400'}`}>{label}</p>
      <p className="font-bold text-gray-900 dark:text-white">{value}</p>
    </div>
  </div>
);

const StatusBadge = ({ submission }: { submission: Submission | null }) => {
  if (!submission) return <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-xs font-medium">لم يسلم</span>;
  const colors = {
    approved: 'bg-green-100 text-green-700',
    rejected: 'bg-red-100 text-red-700',
    pending: 'bg-yellow-100 text-yellow-700'
  };
  return <span className={`px-3 py-1 rounded-full text-xs font-medium ${colors[submission.status] || ''}`}>
    {submission.status === 'approved' ? 'مقبول' : submission.status === 'rejected' ? 'مرفوض' : 'قيد المراجعة'}
  </span>;
};