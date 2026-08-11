// TaskDetailsModal/StandardTaskView.tsx
import React, { useState } from "react";
import { User, Submission } from "../../types";
import { PriorityIndicator } from "../common/PriorityIndicator";
import { DetailRow } from "../common/DetailRow";
import { TaskImagesGallery } from "../common/TaskImagesGallery";
import { SubmissionHistoryList } from "../common/SubmissionHistoryList";
import { formatMillisecondsToWords } from "../utils/formatters";
import { StatusBadge } from "../TaskCard";
import { formatDateTimeValue } from "../../utils/formatDate";
import { TaskDetailsModalProps } from "./TaskDetailsModal.types";
import SubmissionForm from "../modals/SubmissionForm";
import { getUserTaskStatus } from "../modals/TaskDetailsModal.helpers";
import { ArrowRight, LayoutDashboard } from "lucide-react"; // أيقونات جديدة

interface StandardViewProps extends TaskDetailsModalProps {
  selectedUserId: string;
  setSelectedUserId: (id: string) => void;
  currentTime: number;
  assignedUsers: User[];
  allSubmissionsData: any[];
  onBackToDashboard?: () => void; // دالة اختيارية للعودة
}

export const StandardTaskView: React.FC<StandardViewProps> = ({
  isOpen, onClose, task, user, users, onUpdateUserTaskStatus, onCreateSubmission,
  onEditSubmission, onOpenSearchPlatform, onUpdateSubmissionStatus,
  selectedUserId, setSelectedUserId, currentTime, assignedUsers, allSubmissionsData,
  onBackToDashboard // استقبال الدالة
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [editingSubmissionId, setEditingSubmissionId] = useState<string | null>(null);

  const selectedUserTaskStatus = getUserTaskStatus(task, selectedUserId);
  const selectedUser = users.find((u) => u.id === selectedUserId) || user;
  const usersMap = users.reduce((acc, u) => ({ ...acc, [u.id]: u.name }), {} as Record<string, string>);

  // 1. صلاحية العمل: للموظف أو المشتريات (فقط عندما يشاهد ملفه الخاص)
  const canWorkOnTask = (user.role === "employee" || user.role === "procurement") && selectedUserId === user.id;

  // 2. صلاحية التقييم: للمدير أو المشتريات (عندما يشاهدون ملفات الآخرين، أو حتى ملفاتهم في سياق المراجعة)
  // ملاحظة: SubmissionHistoryList عادة ما تتعامل مع زر القبول/الرفض بناءً على role
  const isReviewer = user.role === "manager" || user.role === "procurement";

  // حساب الوقت المنقضي
  const getCurrentElapsedTime = () => {
    let totalMs = selectedUserTaskStatus.totalWorkTime || 0;
    if (selectedUserTaskStatus.status === "in_progress" && selectedUserTaskStatus.workStartTime) {
      totalMs += currentTime - new Date(selectedUserTaskStatus.workStartTime).getTime();
    }
    return totalMs;
  };

  const handleSaveSubmission = (data: any) => {
    let finalTotalTime = selectedUserTaskStatus.totalWorkTime || 0;
    if (selectedUserTaskStatus.status === "in_progress" && selectedUserTaskStatus.workStartTime) {
        finalTotalTime += Date.now() - new Date(selectedUserTaskStatus.workStartTime).getTime();
    }

    if (editingSubmissionId) {
      const existing = task.submissions?.find(s => s.id === editingSubmissionId);
      if (existing) {
        onEditSubmission(task.id, editingSubmissionId, { ...existing, items: [...existing.items, ...data.items], newItemsCount: data.items.length, status: "pending", updatedAt: new Date().toISOString() });
      }
      setEditingSubmissionId(null);
    } else {
      onCreateSubmission(task.id, { ...data, status: "pending" });
      setIsCreating(false);
    }

    onUpdateUserTaskStatus(task.id, selectedUserId, {
      ...selectedUserTaskStatus, status: "submitted", submittedAt: new Date().toISOString(),
      totalWorkTime: finalTotalTime, currentWorkTime: 0, workStartTime: null
    });
  };

  const renderActionButtons = () => {
    // إذا كنت مدير ولا تشاهد ملفك (أو لست معيناً)، لا تعرض أزرار "بدء العمل"
    if (user.role === "manager" && selectedUserId !== user.id) return null;
    
    // إذا كنت مشتريات وتشاهد ملف موظف آخر، لا تعرض أزرار "بدء العمل" (دورك هنا مراجع فقط)
    if (user.role === "procurement" && selectedUserId !== user.id) return null;

    // إذا لم تكن معيناً للمهمة أصلاً
    if (!assignedUsers.find(u => u.id === user.id)) return null;

    const commonBtnClass = "bg-green-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-green-700 transition flex items-center justify-center gap-2 flex-1 text-sm sm:text-base shadow-md";
    const actionBtnClass = "text-white font-bold py-3 px-4 rounded-lg transition flex-1 text-sm sm:text-base shadow-md";

    if (selectedUserTaskStatus.status === "not_started") {
      return (
        <button onClick={() => onUpdateUserTaskStatus(task.id, selectedUserId, { status: "in_progress", startedAt: new Date().toISOString(), workStartTime: new Date().toISOString(), currentWorkTime: 0, totalWorkTime: 0 })}
          className={`${actionBtnClass} bg-blue-600 hover:bg-blue-700 w-full`}>
          قبول المهمة وبدء العمل
        </button>
      );
    }

    return (
      <div className="flex flex-col sm:flex-row gap-2 w-full">
        <button onClick={() => onOpenSearchPlatform(task)} className={commonBtnClass}><span>🔍</span>الانتقال لمنصة البحث</button>
        {selectedUserTaskStatus.status === "in_progress" && (
          <button onClick={() => setIsCreating(true)} className={`${actionBtnClass} bg-blue-600 hover:bg-blue-700`}>تسليم العمل</button>
        )}
        {selectedUserTaskStatus.status === "rejected" && (
            <button onClick={() => onUpdateUserTaskStatus(task.id, selectedUserId, { status: "in_progress", startedAt: new Date().toISOString(), workStartTime: new Date().toISOString(), currentWorkTime: selectedUserTaskStatus.currentWorkTime || 0, totalWorkTime: selectedUserTaskStatus.totalWorkTime || 0 })}
                className={`${actionBtnClass} bg-yellow-500 hover:bg-yellow-600`}>إعادة المحاولة</button>
        )}
        {selectedUserTaskStatus.status === "submitted" && (
             <button onClick={() => setIsCreating(true)} className={`${actionBtnClass} bg-blue-600 hover:bg-blue-700`}>إضافة بنود</button>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-start sm:items-center justify-center p-0 sm:p-4 animate-fade-in overflow-y-auto" onClick={onClose}>
      <div className="bg-[var(--color-surface)] w-full max-w-4xl transform transition-all flex flex-col mt-4 sm:mt-0 max-h-[calc(100dvh-2rem)] sm:max-h-[90vh] sm:rounded-2xl shadow-xl" onClick={(e) => e.stopPropagation()}>
        
        {/* Header */}
        <header className="flex justify-between items-center p-4 sm:p-5 border-b border-[var(--color-border)] flex-shrink-0 bg-[var(--color-surface)] sm:rounded-t-2xl sticky top-0 z-10">
           <div className="flex items-center gap-3 overflow-hidden flex-1 min-w-0">
             {/* زر العودة للوحة القيادة */}
             {onBackToDashboard && (
               <button 
                 onClick={onBackToDashboard}
                 className="p-2 bg-[var(--color-surface-3)] rounded-full hover:bg-[var(--color-surface-3)] transition text-[var(--color-text)]"
                 title="العودة لجميع التسليمات"
               >
                 <LayoutDashboard className="w-5 h-5" />
               </button>
             )}
             
             <div className="space-y-1 overflow-hidden">
               <h2 className="text-lg sm:text-xl md:text-2xl font-bold text-[var(--color-text)] truncate flex items-center gap-2">
                 {task.title}
                 {selectedUser.id !== user.id && <span className="text-sm font-normal text-[var(--color-text-muted)]">({selectedUser.name})</span>}
               </h2>
               <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm">
                 <StatusBadge status={selectedUserTaskStatus.status} />
                 <PriorityIndicator priority={task.priority} />
               </div>
             </div>
           </div>
           <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] text-2xl px-2">&times;</button>
        </header>

        {/* User Selector for Admins */}
        {isReviewer && assignedUsers.length > 0 && (
          <div className="px-4 py-3 bg-[var(--color-surface-2)] border-b border-[var(--color-border)] sticky top-[73px] z-10">
             <div className="flex flex-wrap gap-2">
               {assignedUsers.map(u => (
                 <button key={u.id} onClick={() => setSelectedUserId(u.id)} className={`px-3 py-1 rounded-full text-xs transition ${selectedUserId === u.id ? "bg-blue-600 text-white" : "bg-[var(--color-surface-3)] text-[var(--color-text)]"}`}>
                    {u.name} {u.id === user.id && " (أنت)"}
                 </button>
               ))}
             </div>
          </div>
        )}

        {/* Main Content */}
        <main className="flex-1 p-4 sm:p-5 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-6">
           {/* Task Info Column */}
           <div className="space-y-6">
              <div>
                 <h3 className="text-lg font-bold mb-2 text-[var(--color-text)] border-b pb-1">تفاصيل المهمة</h3>
                 <div className="divide-y divide-[var(--color-border)] text-sm">
                    <DetailRow label="الوقت المنقضي" value={
                        <div className="flex items-center gap-2">
                            <span>{formatMillisecondsToWords(getCurrentElapsedTime())}</span>
                            {selectedUserTaskStatus.status === "in_progress" && <span className="animate-pulse">🟢</span>}
                        </div>
                    } />
                    <DetailRow label="تاريخ التسليم" value={task.dueDate} />
                 </div>
                 <p className="mt-3 p-3 bg-[var(--color-surface-2)] rounded-lg text-sm whitespace-pre-wrap">{task.description}</p>
                 <TaskImagesGallery images={task.images || []} />
                 {selectedUserTaskStatus.status === "rejected" && task.rejectReason && (
                    <div className="mt-3 p-3 bg-red-50 text-red-800 rounded-lg border border-red-300">
                        <p className="font-bold text-sm">سبب الرفض:</p>
                        <p className="text-sm">{task.rejectReason}</p>
                    </div>
                 )}
              </div>
              
              {/* Submission Area */}
              <div>
                <div className="flex justify-between items-center mb-2 border-b pb-1">
                   <h3 className="text-lg font-bold">تسليم العمل</h3>
                   {/* زر إضافة تسليم يظهر فقط إذا كنت تعمل على ملفك الخاص والحالة تسمح */}
                   {canWorkOnTask && !isCreating && !editingSubmissionId && ["in_progress", "submitted", "rejected"].includes(selectedUserTaskStatus.status) && (
                      <button onClick={() => setIsCreating(true)} className="text-sm bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">+ تسليم جديد</button>
                   )}
                </div>
                {isCreating || editingSubmissionId ? (
                   <SubmissionForm
                     initialData={editingSubmissionId ? (task.submissions || []).find(s => s.id === editingSubmissionId) : undefined}
                     onSubmit={handleSaveSubmission} onCancel={() => {setIsCreating(false); setEditingSubmissionId(null);}}
                     isEditMode={!!editingSubmissionId} userRole={user.role} taskId={task.id} userId={selectedUserId}
                   />
                ) : (
                   <SubmissionHistoryList
                     submissions={allSubmissionsData.find(d => d.userId === selectedUserId)?.submissions || []}
                     onEdit={(s) => { 
                       // السماح بالتعديل فقط إذا كان المستخدم يملك التسليم ولم تتم الموافقة عليه
                       if(s.userId === user.id && s.status !== 'approved') setEditingSubmissionId(s.id); 
                     }}
                     // نمرر الدور: إذا كان المستخدم يراجع موظف آخر، نمرر دوره (مدير/مشتريات). إذا كان يشاهد نفسه، نمرر 'employee' ليختفي زر القبول/الرفض
                     userRole={selectedUserId === user.id ? 'employee' : user.role} 
                     currentUserId={selectedUserId}
                     onUpdateSubmissionStatus={onUpdateSubmissionStatus} 
                     selectedUserName={selectedUser.name}
                   />
                )}
              </div>
           </div>

           {/* Activity Log Column */}
           <div className="border-t md:border-t-0 md:border-r md:pr-4 pt-4 md:pt-0">
              <h3 className="text-lg font-bold mb-3 text-[var(--color-text)]">سجل النشاط</h3>
              <ul className="space-y-4 text-sm max-h-[300px] md:max-h-full overflow-y-auto">
                 {(task.logs || []).slice().reverse().map(log => (
                    <li key={log.id} className="relative pr-4 border-r-2 border-[var(--color-border)]">
                       <div className="absolute -right-[5px] top-1 w-2 h-2 bg-blue-500 rounded-full"></div>
                       <p className="font-bold">{usersMap[log.userId] || "System"}</p>
                       <span className="text-xs text-[var(--color-text-muted)] block mb-1">{formatDateTimeValue(log.timestamp)}</span>
                       <p className="text-[var(--color-text-muted)]">{log.action} {log.newValue && `: ${log.newValue}`}</p>
                    </li>
                 ))}
              </ul>
           </div>
        </main>

        <footer className="p-4 bg-[var(--color-surface-2)] border-t flex flex-col sm:flex-row gap-3">
           <div className="w-full sm:flex-1">{renderActionButtons()}</div>
           <button onClick={onClose} className="bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold py-3 px-6 rounded-lg hover:bg-gray-300">إغلاق</button>
        </footer>
      </div>
    </div>
  );
};