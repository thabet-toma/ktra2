// TaskDetailsModal/index.tsx
import React, { useState, useEffect } from "react";
import { TaskDetailsModalProps } from "./TaskDetailsModal.types";
import { useTaskLogic } from "./useTaskLogic";
import { ManagerTaskView } from "./ManagerTaskView";
import { StandardTaskView } from "./StandardTaskView";

type ViewMode = 'dashboard' | 'details';

export const TaskDetailsModal: React.FC<TaskDetailsModalProps> = (props) => {
  const { task, user, users, isOpen } = props;
  const [localTask, setLocalTask] = useState(task);
  const [selectedUserId, setSelectedUserId] = useState<string>(user.id);
  
  // تحديد الوضع الافتراضي: إذا كان مدير أو مشتريات يبدأ بلوحة القيادة، غير ذلك التفاصيل
  const [viewMode, setViewMode] = useState<ViewMode>(
    (user.role === 'manager' || user.role === 'procurement') ? 'dashboard' : 'details'
  );

  useEffect(() => {
    setLocalTask(task);
  }, [task]);

  const logic = useTaskLogic(localTask, users, isOpen);

  if (!isOpen) return null;

  // التعامل مع التنقل
  const handleViewDetails = (userId: string) => {
    setSelectedUserId(userId);
    setViewMode('details');
  };

  const handleBackToDashboard = () => {
    setViewMode('dashboard');
  };

  // عرض لوحة القيادة (Dashboard)
  if (viewMode === 'dashboard' && (user.role === 'manager' || user.role === 'procurement')) {
    return (
      <ManagerTaskView
        {...props}
        task={localTask}
        stats={logic.stats}
        searchTerm={logic.searchTerm}
        setSearchTerm={logic.setSearchTerm}
        statusFilter={logic.statusFilter}
        setStatusFilter={logic.setStatusFilter}
        filteredSubmissionsData={logic.filteredSubmissionsData}
        toggleUserExpansion={logic.toggleUserExpansion}
        expandAllUsers={() => logic.setExpandedUsers(logic.assignedUsers.map(u => u.id))}
        collapseAllUsers={() => logic.setExpandedUsers([])}
        onViewDetails={handleViewDetails} // نمرر دالة الانتقال للتفاصيل
      />
    );
  }

  // عرض تفاصيل المهمة (Standard View)
  return (
    <StandardTaskView
      {...props}
      task={localTask}
      selectedUserId={selectedUserId}
      setSelectedUserId={setSelectedUserId}
      currentTime={logic.currentTime}
      assignedUsers={logic.assignedUsers}
      allSubmissionsData={logic.allSubmissionsData}
      // نمرر خاصية جديدة لزر العودة (سنضيفها في StandardTaskView)
      onBackToDashboard={
        (user.role === 'manager' || user.role === 'procurement') 
          ? handleBackToDashboard 
          : undefined
      }
    />
  );
};