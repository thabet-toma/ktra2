// // TaskDetailsModal.tsx
// import React, { useMemo, useState, useEffect } from "react";
// import { Task, User, Submission } from "../../types";
// import { PriorityIndicator } from "../common/PriorityIndicator";
// import { DetailRow } from "../common/DetailRow";
// import { TaskImagesGallery } from "../common/TaskImagesGallery";
// import { SubmissionHistoryList } from "../common/SubmissionHistoryList";
// import { formatMillisecondsToWords } from "../utils/formatters";
// import { getUserTaskStatus } from "./TaskDetailsModal.helpers";
// import SubmissionForm from "./SubmissionForm";
// import { StatusBadge } from "../TaskCard";
// import { 
//   Users, ChevronDown, ChevronUp, Check, X, Eye, 
//   Download, Filter, Search, Mail, Phone, Clock, AlertCircle, 
//   FileText
// } from 'lucide-react';

// interface TaskDetailsModalProps {
//   isOpen: boolean;
//   onClose: () => void;
//   task: Task;
//   user: User;
//   users: User[];
//   onUpdateUserTaskStatus: (taskId: string, userId: string, status: any) => void;
//   onCreateSubmission: (
//     taskId: string,
//     submission: Omit<
//       Submission,
//       "id" | "taskId" | "userId" | "createdAt" | "updatedAt"
//     >
//   ) => void;
//   onEditSubmission: (
//     taskId: string,
//     submissionId: string,
//     data: Partial<Submission>
//   ) => void;
//   onUpdateTask: (task: Task) => void;
//   onOpenSearchPlatform: (task: Task) => void;
//   onUpdateSubmissionStatus: (
//     taskId: string,
//     submissionId: string,
//     status: "approved" | "rejected",
//     reviewerNotes?: string
//   ) => void;
// }

// export const TaskDetailsModal: React.FC<TaskDetailsModalProps> = ({
//   isOpen,
//   onClose,
//   task,
//   user,
//   users,
//   onUpdateUserTaskStatus,
//   onCreateSubmission,
//   onEditSubmission,
//   onUpdateTask,
//   onOpenSearchPlatform,
//   onUpdateSubmissionStatus,
// }) => {
//   const [isCreating, setIsCreating] = useState(false);
//   const [editingSubmissionId, setEditingSubmissionId] = useState<string | null>(null);
//   const [currentTime, setCurrentTime] = useState(Date.now());
//   const [selectedUserId, setSelectedUserId] = useState<string>(user.id);
//   const [expandedUsers, setExpandedUsers] = useState<string[]>([]);
//   const [searchTerm, setSearchTerm] = useState('');
//   const [statusFilter, setStatusFilter] = useState('all');

//   // الحالة المحلية للمهمة لضمان التحديث الفوري
//   const [localTask, setLocalTask] = useState<Task>(task);

//   // تحديث الحالة المحلية عند تغير المهمة من الخارج
//   useEffect(() => {
//     setLocalTask(task);
//   }, [task]);

//   useEffect(() => {
//     if (isOpen) {
//       setCurrentTime(Date.now());
//       const interval = setInterval(() => {
//         setCurrentTime(Date.now());
//       }, 60000);
//       return () => clearInterval(interval);
//     }
//   }, [isOpen]);

//   if (!isOpen) return null;

//   const selectedUserTaskStatus = getUserTaskStatus(localTask, selectedUserId);
//   const selectedUser = users.find((u) => u.id === selectedUserId) || user;

//   const assignedUsers = Array.isArray(localTask.assignedTo)
//     ? localTask.assignedTo
//         .map((userId) => users.find((u) => u.id === userId))
//         .filter(Boolean)
//     : [users.find((u) => u.id === localTask.assignedTo)].filter(Boolean);

//   // تجميع بيانات جميع التسليمات
//   const allSubmissionsData = useMemo(() => {
//     return assignedUsers.map(assignedUser => {
//       const userId = assignedUser.id;
//       const userSubmissions = (localTask.submissions || []).filter(
//         sub => sub.userId === userId
//       );
//       const sortedSubmissions = [...userSubmissions].sort(
//         (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
//       );
//       const latestSubmission = sortedSubmissions.length > 0 ? sortedSubmissions[0] : null;
//       const userStatus = localTask.userStatuses?.[userId] || {};
      
//       return {
//         user: assignedUser,
//         userId,
//         submissions: sortedSubmissions,
//         latestSubmission,
//         userStatus,
//         submissionCount: userSubmissions.length,
//         isExpanded: expandedUsers.includes(userId)
//       };
//     });
//   }, [localTask, assignedUsers, expandedUsers]);

//   // تصفية البيانات حسب البحث
//   const filteredSubmissionsData = useMemo(() => {
//     return allSubmissionsData.filter(data => {
//       const matchesSearch = 
//         data.user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
//         data.user.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
//         (data.latestSubmission?.status && data.latestSubmission.status.toLowerCase().includes(searchTerm.toLowerCase()));
      
//       const matchesStatus = 
//         statusFilter === 'all' ||
//         (statusFilter === 'pending' && data.latestSubmission?.status === 'pending') ||
//         (statusFilter === 'approved' && data.latestSubmission?.status === 'approved') ||
//         (statusFilter === 'rejected' && data.latestSubmission?.status === 'rejected') ||
//         (statusFilter === 'not_submitted' && !data.latestSubmission) ||
//         (statusFilter === 'with_new_items' && data.latestSubmission?.newItemsCount && data.latestSubmission.newItemsCount > 0);
      
//       return matchesSearch && matchesStatus;
//     });
//   }, [allSubmissionsData, searchTerm, statusFilter]);

//   // إحصائيات
//   const stats = useMemo(() => {
//     const total = assignedUsers.length;
//     const submitted = allSubmissionsData.filter(d => d.latestSubmission).length;
//     const pending = allSubmissionsData.filter(d => d.latestSubmission?.status === 'pending').length;
//     const approved = allSubmissionsData.filter(d => d.latestSubmission?.status === 'approved').length;
//     const rejected = allSubmissionsData.filter(d => d.latestSubmission?.status === 'rejected').length;
//     const withNewItems = allSubmissionsData.filter(d => d.latestSubmission?.newItemsCount && d.latestSubmission.newItemsCount > 0).length;

//     return { total, submitted, pending, approved, rejected, withNewItems };
//   }, [allSubmissionsData, assignedUsers]);

//   const usersMap = useMemo(
//     () =>
//       users.reduce(
//         (acc, u) => ({ ...acc, [u.id]: u.name }),
//         {} as Record<string, string>
//       ),
//     [users]
//   );

//   const toggleUserExpansion = (userId: string) => {
//     setExpandedUsers(prev => 
//       prev.includes(userId) 
//         ? prev.filter(id => id !== userId)
//         : [...prev, userId]
//     );
//   };

//   const expandAllUsers = () => {
//     setExpandedUsers(assignedUsers.map(u => u.id));
//   };

//   const collapseAllUsers = () => {
//     setExpandedUsers([]);
//   };

//   const handleSaveSubmission = (data: any) => {
//     let finalTotalTime = selectedUserTaskStatus.totalWorkTime || 0;

//     if (
//       selectedUserTaskStatus.status === "in_progress" &&
//       selectedUserTaskStatus.workStartTime
//     ) {
//       const startTime = new Date(
//         selectedUserTaskStatus.workStartTime
//       ).getTime();
//       const sessionTime = Date.now() - startTime;
//       finalTotalTime += sessionTime;
//     }

//     if (editingSubmissionId) {
//       const existingSubmission = (localTask.submissions || []).find(
//         (s) => s.id === editingSubmissionId
//       );
//       if (existingSubmission) {
//         const updatedSubmission = {
//           ...existingSubmission,
//           items: [...existingSubmission.items, ...data.items],
//           newItemsCount: data.items.length,
//           status: "pending" as const,
//           updatedAt: new Date().toISOString(),
//         };
//         onEditSubmission(task.id, editingSubmissionId, updatedSubmission);
//       }
//       setEditingSubmissionId(null);
//     } else {
//       onCreateSubmission(task.id, {
//         ...data,
//         status: "pending",
//       });
//       setIsCreating(false);
//     }

//     onUpdateUserTaskStatus(task.id, selectedUserId, {
//       ...selectedUserTaskStatus,
//       status: "submitted",
//       submittedAt: new Date().toISOString(),
//       totalWorkTime: finalTotalTime,
//       currentWorkTime: 0,
//       workStartTime: null,
//     });
//   };

//   const handleCancelSubmission = () => {
//     setIsCreating(false);
//     setEditingSubmissionId(null);
//   };

//   const handleEditSubmission = (submission: Submission) => {
//     if (submission.status === "approved") {
//       alert("لا يمكن تعديل التسليم بعد اعتماده نهائياً.");
//       return;
//     }
//     setSelectedUserId(submission.userId);
//     setEditingSubmissionId(submission.id);
//   };

//   const handleAcceptTask = () => {
//     onUpdateUserTaskStatus(task.id, selectedUserId, {
//       status: "in_progress",
//       startedAt: new Date().toISOString(),
//       workStartTime: new Date().toISOString(),
//       currentWorkTime: 0,
//       totalWorkTime: 0,
//     });
//   };

//   const handleRetryTask = () => {
//     onUpdateUserTaskStatus(task.id, selectedUserId, {
//       status: "in_progress",
//       startedAt: new Date().toISOString(),
//       workStartTime: new Date().toISOString(),
//       currentWorkTime: selectedUserTaskStatus.currentWorkTime || 0,
//       totalWorkTime: selectedUserTaskStatus.totalWorkTime || 0,
//     });
//   };

//   const canSubmit =
//     selectedUser.role === "employee" &&
//     ["in_progress", "rejected"].includes(selectedUserTaskStatus.status) &&
//     selectedUserId === user.id;

//   const getCurrentElapsedTime = (userStatus: any) => {
//     const totalWorkTime = userStatus.totalWorkTime || 0;
//     let totalMs = totalWorkTime;

//     if (userStatus.status === "in_progress" && userStatus.workStartTime) {
//       const startTime = new Date(userStatus.workStartTime).getTime();
//       const elapsedMs = currentTime - startTime;
//       totalMs += elapsedMs;
//     }

//     return totalMs;
//   };

//   const currentElapsedTime = getCurrentElapsedTime(selectedUserTaskStatus);

//   const renderActionButtons = () => {
//     if (
//       (user.role === "manager") &&
//       selectedUserId !== user.id
//     ) {
//       return null;
//     }

//     if (selectedUser.role === "employee") {
//       switch (selectedUserTaskStatus.status) {
//         case "not_started":
//           return (
//             <button
//               onClick={handleAcceptTask}
//               className="bg-blue-600 text-white font-bold py-3 px-4 sm:px-6 rounded-lg hover:bg-blue-700 transition w-full text-sm sm:text-base shadow-md"
//             >
//               قبول المهمة وبدء العمل
//             </button>
//           );
//         case "in_progress":
//           return (
//             <div className="flex flex-col sm:flex-row gap-2 w-full">
//               <button
//                 onClick={() => onOpenSearchPlatform(task)}
//                 className="bg-green-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-green-700 transition flex items-center justify-center gap-2 flex-1 text-sm sm:text-base shadow-md"
//               >
//                 <span>🔍</span>
//                 الانتقال لمنصة البحث
//               </button>
//               <button
//                 onClick={() => setIsCreating(true)}
//                 className="bg-blue-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-blue-700 transition flex-1 text-sm sm:text-base shadow-md"
//               >
//                 تسليم العمل
//               </button>
//             </div>
//           );
//         case "rejected":
//           return (
//             <div className="flex flex-col sm:flex-row gap-2 w-full">
//               <button
//                 onClick={() => onOpenSearchPlatform(task)}
//                 className="bg-green-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-green-700 transition flex items-center justify-center gap-2 flex-1 text-sm sm:text-base shadow-md"
//               >
//                 <span>🔍</span>
//                 الانتقال لمنصة البحث
//               </button>
//               <button
//                 onClick={handleRetryTask}
//                 className="bg-yellow-500 text-white font-bold py-3 px-4 rounded-lg hover:bg-yellow-600 transition flex-1 text-sm sm:text-base shadow-md"
//               >
//                 إعادة المحاولة
//               </button>
//             </div>
//           );
//         case "submitted":
//           return (
//             <div className="flex flex-col sm:flex-row gap-2 w-full">
//               <button
//                 onClick={() => onOpenSearchPlatform(task)}
//                 className="bg-green-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-green-700 transition flex items-center justify-center gap-2 flex-1 text-sm sm:text-base shadow-md"
//               >
//                 <span>🔍</span>
//                 الانتقال لمنصة البحث
//               </button>
//               <button
//                 onClick={() => setIsCreating(true)}
//                 className="bg-blue-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-blue-700 transition flex-1 text-sm sm:text-base shadow-md"
//               >
//                 إضافة بنود
//               </button>
//             </div>
//           );
//         default:
//           return null;
//       }
//     }
//     return null;
//   };

//   // إذا كان المدير أو المشتريات، اعرض جميع التسليمات
//   if ((user.role === "manager" || user.role === "procurement") && selectedUserId === user.id) {
//     return (
//       <div
//         className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-start sm:items-center justify-center p-0 sm:p-4 animate-fade-in overflow-y-auto"
//         onClick={onClose}
//       >
//         <div
//           className="bg-[var(--color-surface)] w-full max-w-6xl transform transition-all flex flex-col mt-4 sm:mt-0 max-h-[calc(100dvh-2rem)] sm:max-h-[90vh] sm:rounded-2xl shadow-xl"
//           onClick={(e) => e.stopPropagation()}
//         >
//           {/* Header */}
//           <header className="flex justify-between items-center p-4 sm:p-5 border-b border-[var(--color-border)] flex-shrink-0 bg-[var(--color-surface)] sm:rounded-t-2xl sticky top-0 z-10">
//             <div className="space-y-1 overflow-hidden flex-1 min-w-0">
//               <h2 className="text-lg sm:text-xl md:text-2xl font-bold text-[var(--color-text)] truncate">
//                 {localTask.title} - جميع التسليمات
//               </h2>
//               <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm">
//                 <PriorityIndicator priority={localTask.priority} />
//                 <span className="text-[var(--color-text-muted)]">
//                   تاريخ التسليم: {localTask.dueDate}
//                 </span>
//               </div>
//             </div>
//             <button
//               onClick={onClose}
//               className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] text-2xl sm:text-3xl px-2 flex-shrink-0"
//             >
//               &times;
//             </button>
//           </header>

//           {/* إحصائيات سريعة */}
//           <div className="px-4 sm:px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
//             <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
//               <div className="bg-[var(--color-surface)] p-3 rounded-lg border border-[var(--color-border)]">
//                 <div className="flex items-center gap-2">
//                   <Users className="w-4 h-4 text-blue-500" />
//                   <div>
//                     <p className="text-xs text-[var(--color-text-muted)]">المعينين</p>
//                     <p className="font-bold text-[var(--color-text)]">{stats.total}</p>
//                   </div>
//                 </div>
//               </div>
//               <div className="bg-[var(--color-surface)] p-3 rounded-lg border border-[var(--color-border)]">
//                 <div className="flex items-center gap-2">
//                   <FileText className="w-4 h-4 text-green-500" />
//                   <div>
//                     <p className="text-xs text-[var(--color-text-muted)]">مسلمة</p>
//                     <p className="font-bold text-[var(--color-text)]">{stats.submitted}</p>
//                   </div>
//                 </div>
//               </div>
//               <div className="bg-[var(--color-surface)] p-3 rounded-lg border border-[var(--color-border)]">
//                 <div className="flex items-center gap-2">
//                   <Clock className="w-4 h-4 text-yellow-500" />
//                   <div>
//                     <p className="text-xs text-[var(--color-text-muted)]">قيد المراجعة</p>
//                     <p className="font-bold text-[var(--color-text)]">{stats.pending}</p>
//                   </div>
//                 </div>
//               </div>
//               <div className="bg-[var(--color-surface)] p-3 rounded-lg border border-[var(--color-border)]">
//                 <div className="flex items-center gap-2">
//                   <Check className="w-4 h-4 text-green-500" />
//                   <div>
//                     <p className="text-xs text-[var(--color-text-muted)]">مقبول</p>
//                     <p className="font-bold text-[var(--color-text)]">{stats.approved}</p>
//                   </div>
//                 </div>
//               </div>
//               <div className="bg-[var(--color-surface)] p-3 rounded-lg border border-[var(--color-border)]">
//                 <div className="flex items-center gap-2">
//                   <X className="w-4 h-4 text-red-500" />
//                   <div>
//                     <p className="text-xs text-[var(--color-text-muted)]">مرفوض</p>
//                     <p className="font-bold text-[var(--color-text)]">{stats.rejected}</p>
//                   </div>
//                 </div>
//               </div>
//               <div className="bg-[var(--color-surface)] p-3 rounded-lg border border-[var(--color-border)]">
//                 <div className="flex items-center gap-2">
//                   <AlertCircle className="w-4 h-4 text-purple-500" />
//                   <div>
//                     <p className="text-xs text-[var(--color-text-muted)]">بنود جديدة</p>
//                     <p className="font-bold text-[var(--color-text)]">{stats.withNewItems}</p>
//                   </div>
//                 </div>
//               </div>
//             </div>
//           </div>

//           {/* الفلاتر */}
//           <div className="px-4 sm:px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
//             <div className="flex flex-col md:flex-row gap-3">
//               <div className="flex-1 relative">
//                 <Search className="absolute right-3 top-1/2 transform -translate-y-1/2 text-[var(--color-text-muted)] w-4 h-4" />
//                 <input
//                   type="text"
//                   value={searchTerm}
//                   onChange={(e) => setSearchTerm(e.target.value)}
//                   placeholder="ابحث عن موظف أو حالة..."
//                   className="w-full pr-10 pl-4 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm"
//                 />
//               </div>
//               <div className="w-full md:w-48">
//                 <div className="flex items-center gap-2">
//                   <Filter className="w-4 h-4 text-[var(--color-text-muted)]" />
//                   <select
//                     value={statusFilter}
//                     onChange={(e) => setStatusFilter(e.target.value)}
//                     className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm"
//                   >
//                     <option value="all">جميع الحالات</option>
//                     <option value="pending">قيد المراجعة</option>
//                     <option value="approved">مقبول</option>
//                     <option value="rejected">مرفوض</option>
//                     <option value="not_submitted">لم يسلم</option>
//                     <option value="with_new_items">بنود جديدة</option>
//                   </select>
//                 </div>
//               </div>
//               <div className="flex gap-2">
//                 <button
//                   onClick={expandAllUsers}
//                   className="px-3 py-2 bg-[var(--color-surface-3)] text-[var(--color-text)] rounded-lg hover:bg-[var(--color-surface-3)] text-sm"
//                 >
//                   <ChevronDown className="w-4 h-4 inline ml-1" />
//                   فتح الكل
//                 </button>
//                 <button
//                   onClick={collapseAllUsers}
//                   className="px-3 py-2 bg-[var(--color-surface-3)] text-[var(--color-text)] rounded-lg hover:bg-[var(--color-surface-3)] text-sm"
//                 >
//                   <ChevronUp className="w-4 h-4 inline ml-1" />
//                   غلق الكل
//                 </button>
//               </div>
//             </div>
//           </div>

//           {/* Main Content - عرض جميع التسليمات */}
//           <main className="flex-1 p-4 sm:p-5 overflow-y-auto">
//             <div className="space-y-4">
//               {filteredSubmissionsData.map((data, index) => (
//                 <div key={data.userId} className="bg-[var(--color-surface-2)] rounded-lg border border-[var(--color-border)] overflow-hidden">
//                   {/* رأس الموظف */}
//                   <div 
//                     className="flex justify-between items-center p-4 cursor-pointer hover:bg-[var(--color-surface-3)] transition-colors"
//                     onClick={() => toggleUserExpansion(data.userId)}
//                   >
//                     <div className="flex items-center gap-3 flex-1">
//                       <div className="w-10 h-10 bg-[var(--color-surface-3)] rounded-full flex items-center justify-center">
//                         <span className="font-bold text-[var(--color-text)]">
//                           {data.user.name?.charAt(0) || '?'}
//                         </span>
//                       </div>
//                       <div className="flex-1">
//                         <h3 className="font-bold text-[var(--color-text)] text-sm md:text-base">
//                           {data.user.name}
//                         </h3>
//                         <div className="flex items-center gap-3 mt-1">
//                           {data.user.email && (
//                             <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
//                               <Mail className="w-3 h-3" />
//                               {data.user.email}
//                             </span>
//                           )}
//                           {data.user.phone && (
//                             <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
//                               <Phone className="w-3 h-3" />
//                               {data.user.phone}
//                             </span>
//                           )}
//                         </div>
//                       </div>
//                     </div>
                    
//                     <div className="flex items-center gap-4">
//                       {/* حالة التسليم */}
//                       <div>
//                         {data.latestSubmission ? (
//                           <span className={`px-3 py-1 rounded-full text-xs font-medium ${
//                             data.latestSubmission.status === 'approved' 
//                               ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
//                               : data.latestSubmission.status === 'rejected'
//                               ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
//                               : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
//                           }`}>
//                             {data.latestSubmission.status === 'approved' ? 'مقبول' :
//                              data.latestSubmission.status === 'rejected' ? 'مرفوض' : 'قيد المراجعة'}
//                           </span>
//                         ) : (
//                           <span className="px-3 py-1 bg-[var(--color-surface-3)] text-[var(--color-text)] rounded-full text-xs font-medium">
//                             لم يسلم
//                           </span>
//                         )}
//                       </div>
                      
//                       {/* عدد البنود الجديدة */}
//                       {data.latestSubmission?.newItemsCount && data.latestSubmission.newItemsCount > 0 && (
//                         <span className="px-2 py-1 bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded-full text-xs">
//                           {data.latestSubmission.newItemsCount} جديد
//                         </span>
//                       )}
                      
//                       {/* عدد التسليمات */}
//                       <span className="text-sm text-[var(--color-text-muted)]">
//                         {data.submissionCount} تسليم
//                       </span>
                      
//                       {/* زر التوسيع */}
//                       <span className={`transition-transform ${data.isExpanded ? 'rotate-180' : ''}`}>
//                         <ChevronDown className="w-5 h-5 text-[var(--color-text-muted)]" />
//                       </span>
//                     </div>
//                   </div>
                  
//                   {/* محتوى التسليمات (يظهر عند التوسيع) */}
//                   {data.isExpanded && (
//                     <div className="border-t border-[var(--color-border)] p-4">
//                       {data.submissions.length > 0 ? (
//                         <div className="space-y-4">
//                           {data.submissions.map((submission, subIndex) => (
//                             <div key={submission.id} className="bg-[var(--color-surface)] p-4 rounded-lg border border-[var(--color-border)]">
//                               <div className="flex justify-between items-start mb-3">
//                                 <div>
//                                   <h4 className="font-bold text-[var(--color-text)] text-sm">
//                                     التسليم #{data.submissions.length - subIndex}
//                                   </h4>
//                                   <p className="text-xs text-[var(--color-text-muted)] mt-1">
//                                     {new Date(submission.createdAt).toLocaleString('ar-EG')}
//                                   </p>
//                                 </div>
//                                 <div className="flex gap-2">
//                                   {submission.status === 'pending' && (
//                                     <>
//                                       <button
//                                         onClick={() => onUpdateSubmissionStatus(
//                                           task.id, 
//                                           submission.id, 
//                                           'approved',
//                                           'تمت الموافقة'
//                                         )}
//                                         className="p-1.5 bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 rounded-lg hover:bg-green-200 dark:hover:bg-green-900/50"
//                                         title="موافقة"
//                                       >
//                                         <Check className="w-4 h-4" />
//                                       </button>
//                                       <button
//                                         onClick={() => {
//                                           const reason = prompt('يرجى كتابة سبب الرفض:');
//                                           if (reason) {
//                                             onUpdateSubmissionStatus(
//                                               task.id, 
//                                               submission.id, 
//                                               'rejected',
//                                               reason
//                                             );
//                                           }
//                                         }}
//                                         className="p-1.5 bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 rounded-lg hover:bg-red-200 dark:hover:bg-red-900/50"
//                                         title="رفض"
//                                       >
//                                         <X className="w-4 h-4" />
//                                       </button>
//                                     </>
//                                   )}
//                                   <button
//                                     onClick={() => {
//                                       // عرض تفاصيل التسليم
//                                       setSelectedUserId(data.userId);
//                                       setEditingSubmissionId(submission.id);
//                                     }}
//                                     className="p-1.5 bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/50"
//                                     title="عرض التفاصيل"
//                                   >
//                                     <Eye className="w-4 h-4" />
//                                   </button>
//                                 </div>
//                               </div>
                              
//                               {/* عرض البنود */}
//                               {submission.items && submission.items.length > 0 && (
//                                 <div className="mt-3">
//                                   <h5 className="text-sm font-medium text-[var(--color-text)] mb-2">
//                                     البنود ({submission.items.length})
//                                   </h5>
//                                   <div className="space-y-2 max-h-40 overflow-y-auto">
//                                     {submission.items.map((item, itemIndex) => (
//                                       <div key={itemIndex} className="bg-[var(--color-surface-2)] p-2 rounded text-xs">
//                                         <p className="font-medium text-[var(--color-text)]">
//                                           {item.productLink || 'بند بدون رابط'}
//                                         </p>
//                                         {item.productPrice && (
//                                           <p className="text-[var(--color-text-muted)] mt-1">
//                                             السعر: {item.productPrice} $
//                                           </p>
//                                         )}
//                                         {item.notes && (
//                                           <p className="text-[var(--color-text-muted)] mt-1 text-xs">
//                                             {item.notes}
//                                           </p>
//                                         )}
//                                       </div>
//                                     ))}
//                                   </div>
//                                 </div>
//                               )}
                              
//                               {submission.reviewerNotes && (
//                                 <div className="mt-3 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded border border-yellow-200 dark:border-yellow-800">
//                                   <p className="text-xs text-yellow-700 dark:text-yellow-400">
//                                     <span className="font-medium">ملاحظات المراجع:</span> {submission.reviewerNotes}
//                                   </p>
//                                 </div>
//                               )}
//                             </div>
//                           ))}
//                         </div>
//                       ) : (
//                         <div className="text-center py-6 text-[var(--color-text-muted)]">
//                           <p className="text-sm">لم يسلم هذا الموظف بعد</p>
//                         </div>
//                       )}
//                     </div>
//                   )}
//                 </div>
//               ))}
              
//               {filteredSubmissionsData.length === 0 && (
//                 <div className="text-center py-12 text-[var(--color-text-muted)]">
//                   <div className="w-16 h-16 mx-auto mb-4 bg-[var(--color-surface-3)] rounded-full flex items-center justify-center">
//                     <Search className="w-8 h-8" />
//                   </div>
//                   <p className="text-lg">لا توجد نتائج مطابقة</p>
//                   <p className="text-sm mt-2">حاول تغيير كلمات البحث أو الفلاتر</p>
//                 </div>
//               )}
//             </div>
//           </main>

//           {/* Footer */}
//           <footer className="p-4 border-t border-[var(--color-border)] bg-[var(--color-surface)]">
//             <div className="flex justify-end">
//               <button
//                 onClick={onClose}
//                 className="px-6 py-2.5 bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500 transition"
//               >
//                 إغلاق
//               </button>
//             </div>
//           </footer>
//         </div>
//       </div>
//     );
//   }

//   // إذا كان الموظف العادي، استمر بالعرض العادي
//   return (
//     <div
//       className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-start sm:items-center justify-center p-0 sm:p-4 animate-fade-in overflow-y-auto"
//       onClick={onClose}
//     >
//       <div
//         className="bg-[var(--color-surface)] w-full max-w-4xl transform transition-all flex flex-col mt-4 sm:mt-0 max-h-[calc(100dvh-2rem)] sm:max-h-[90vh] sm:rounded-2xl shadow-xl"
//         onClick={(e) => e.stopPropagation()}
//       >
//         {/* Header */}
//         <header className="flex justify-between items-center p-4 sm:p-5 border-b border-[var(--color-border)] flex-shrink-0 bg-[var(--color-surface)] sm:rounded-t-2xl sticky top-0 z-10">
//           <div className="space-y-1 overflow-hidden flex-1 min-w-0">
//             <h2 className="text-lg sm:text-xl md:text-2xl font-bold text-[var(--color-text)] truncate">
//               {localTask.title}
//             </h2>
//             <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm">
//               <StatusBadge status={selectedUserTaskStatus.status} />
//               <PriorityIndicator priority={localTask.priority} />
//             </div>
//           </div>
//           <button
//             onClick={onClose}
//             className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] text-2xl sm:text-3xl px-2 flex-shrink-0"
//           >
//             &times;
//           </button>
//         </header>

//         {(user.role === "manager" || user.role === "procurement") &&
//           assignedUsers.length > 0 && (
//             <div className="px-4 sm:px-5 pt-3 border-b border-[var(--color-border)] pb-3 bg-[var(--color-surface-2)] sticky top-[73px] z-10">
//               <label className="text-sm font-semibold text-[var(--color-text)] mb-2 block">
//                 اختر الموظف لعرض حالته:
//               </label>
//               <div className="flex flex-wrap gap-2">
//                 {assignedUsers.map((assignedUser) => (
//                   <button
//                     key={assignedUser.id}
//                     onClick={() => setSelectedUserId(assignedUser.id)}
//                     className={`px-3 py-1 rounded-full text-xs sm:text-sm transition ${
//                       selectedUserId === assignedUser.id
//                         ? "bg-blue-600 text-white"
//                         : "bg-[var(--color-surface-3)] text-[var(--color-text)] hover:bg-gray-300"
//                     }`}
//                   >
//                     {assignedUser.name}
//                     {assignedUser.id === user.id && " (أنت)"}
//                   </button>
//                 ))}
//               </div>
//             </div>
//           )}

//         {/* Main Content */}
//         <main className="flex-1 p-4 sm:p-5 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6 md:gap-8">
//           <div className="space-y-4 sm:space-y-6">
//             <div>
//               <h3 className="text-base sm:text-lg font-bold mb-2 text-[var(--color-text)] border-b pb-1 dark:border-gray-700">
//                 تفاصيل المهمة
//               </h3>
//               <div className="divide-y divide-[var(--color-border)] text-xs sm:text-sm">
//                 <DetailRow
//                   label="الموظفين المعينين"
//                   value={
//                     <div className="flex flex-wrap gap-1">
//                       {assignedUsers.map((u) => (
//                         <span
//                           key={u.id}
//                           className={`px-2 py-1 rounded text-xs ${
//                             u.id === selectedUserId
//                               ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
//                               : "bg-[var(--color-surface-3)] text-[var(--color-text)]"
//                           }`}
//                         >
//                           {u.name} {u.id === user.id && "(أنت)"}
//                         </span>
//                       ))}
//                     </div>
//                   }
//                 />
//                 <DetailRow
//                   label={`حالة ${
//                     selectedUser.id === user.id ? "لديك" : selectedUser.name
//                   } في المهمة`}
//                   value={<StatusBadge status={selectedUserTaskStatus.status} />}
//                 />
//                 {selectedUserTaskStatus.startedAt && (
//                   <DetailRow
//                     label="بدأت في"
//                     value={new Date(
//                       selectedUserTaskStatus.startedAt
//                     ).toLocaleString()}
//                   />
//                 )}
//                 {selectedUserTaskStatus.workStartTime && (
//                   <DetailRow
//                     label="آخر بدء"
//                     value={new Date(
//                       selectedUserTaskStatus.workStartTime
//                     ).toLocaleString()}
//                   />
//                 )}
//                 <DetailRow label="تاريخ التسليم" value={localTask.dueDate} />
//                 <DetailRow
//                   label="تاريخ الإنشاء"
//                   value={new Date(localTask.createdAt).toLocaleDateString()}
//                 />
//                 <DetailRow
//                   label="الوقت المنقضي"
//                   value={
//                     <div className="flex items-center gap-2">
//                       <span className="text-xs sm:text-sm">
//                         {formatMillisecondsToWords(currentElapsedTime)}
//                       </span>
//                       {selectedUserTaskStatus.status === "in_progress" && (
//                         <span
//                           className="text-xs text-green-600 animate-pulse"
//                           title="جاري العمل"
//                         >
//                           🟢
//                         </span>
//                       )}
//                     </div>
//                   }
//                 />
//               </div>

//               {/* عرض وصف المهمة */}
//               <div className="mt-3">
//                 <p className="p-3 bg-[var(--color-surface-2)] rounded-lg border dark:border-gray-600 text-xs sm:text-sm whitespace-pre-wrap">
//                   {localTask.description}
//                 </p>
//               </div>

//               {/* عرض صور المهمة */}
//               <TaskImagesGallery images={localTask.images || []} />
//             </div>

//             {selectedUserTaskStatus.status === "rejected" &&
//               localTask.rejectReason && (
//                 <div className="p-3 sm:p-4 bg-red-50 dark:bg-red-900/50 rounded-lg border border-red-300 dark:border-red-700">
//                   <h4 className="font-bold text-red-800 dark:text-red-200 text-sm sm:text-base">
//                     سبب الرفض:
//                   </h4>
//                   <p className="mt-1 text-red-700 dark:text-red-300 text-xs sm:text-sm">
//                     {localTask.rejectReason}
//                   </p>
//                 </div>
//               )}

//             <div>
//               <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-2 border-b pb-1 dark:border-gray-700">
//                 <h3 className="text-base sm:text-lg font-bold text-[var(--color-text)]">
//                   تسليم العمل{" "}
//                   {selectedUser.id !== user.id && `- ${selectedUser.name}`}
//                 </h3>
//                 {canSubmit &&
//                   !isCreating &&
//                   !editingSubmissionId &&
//                   selectedUserTaskStatus.status == "in_progress" && (
//                     <button
//                       onClick={() => setIsCreating(true)}
//                       className="text-xs sm:text-sm bg-blue-600 text-white px-3 py-2 sm:px-4 sm:py-2 rounded-lg hover:bg-blue-700 transition flex items-center justify-center gap-2 w-full sm:w-auto"
//                     >
//                       <span>+</span>
//                       تسليم جديد
//                     </button>
//                   )}
//               </div>

//               {isCreating || editingSubmissionId ? (
//                 <SubmissionForm
//                   initialData={
//                     editingSubmissionId
//                       ? (localTask.submissions || []).find(
//                           (s) => s.id === editingSubmissionId && s.userId === selectedUserId
//                         )
//                       : undefined
//                   }
//                   onSubmit={handleSaveSubmission}
//                   onCancel={handleCancelSubmission}
//                   isEditMode={!!editingSubmissionId}
//                   userRole={user.role}
//                   taskId={task.id}
//                   userId={selectedUserId}
//                 />
//               ) : (
//                 <SubmissionHistoryList
//                   submissions={allSubmissionsData.find(d => d.userId === selectedUserId)?.submissions || []}
//                   onEdit={handleEditSubmission}
//                   userRole={user.role}
//                   currentUserId={selectedUserId}
//                   onUpdateSubmissionStatus={(
//                     submissionId,
//                     status,
//                     reviewerNotes
//                   ) => {
//                     onUpdateSubmissionStatus(
//                       task.id,
//                       submissionId,
//                       status,
//                       reviewerNotes
//                     );
//                   }}
//                   selectedUserName={selectedUser.name}
//                 />
//               )}
//             </div>
//           </div>

//           <div className="border-t md:border-t-0 md:border-r md:pr-4 border-[var(--color-border)] pt-4 sm:pt-6 md:pt-0">
//             <h3 className="text-base sm:text-lg font-bold mb-3 sm:mb-4 text-[var(--color-text)]">
//               سجل النشاط
//             </h3>
//             <ul className="space-y-3 sm:space-y-4 text-xs sm:text-sm max-h-[300px] md:max-h-full overflow-y-auto">
//               {(localTask.logs || [])
//                 .slice()
//                 .reverse()
//                 .map((log) => (
//                   <li
//                     key={log.id}
//                     className="relative pr-4 border-r-2 border-[var(--color-border)]"
//                   >
//                     <div className="absolute -right-[5px] top-1 w-2 h-2 bg-blue-500 rounded-full"></div>
//                     <p className="font-bold text-[var(--color-text)] text-xs sm:text-sm">
//                       {usersMap[log.userId] || "System"}
//                     </p>
//                     <span className="text-xs text-[var(--color-text-muted)] block mb-1">
//                       {new Date(log.timestamp).toLocaleString()}
//                     </span>
//                     <p className="text-[var(--color-text-muted)] text-xs sm:text-sm">
//                       {log.action} {log.newValue && `: ${log.newValue}`}
//                     </p>
//                   </li>
//                 ))}
//             </ul>
//           </div>
//         </main>

//         {/* Footer */}
//         <footer className="p-3 sm:p-4 bg-[var(--color-surface-2)] border-t border-[var(--color-border)] flex flex-col sm:flex-row gap-2 sm:gap-3 flex-shrink-0 sm:rounded-b-2xl sticky bottom-0 z-10">
//           <div className="w-full sm:flex-1">{renderActionButtons()}</div>
//           <button
//             onClick={onClose}
//             className="bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold py-3 px-4 sm:px-6 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500 transition w-full sm:w-auto text-sm sm:text-base flex-shrink-0"
//           >
//             إغلاق
//           </button>
//         </footer>
//       </div>
//     </div>
//   );
// };