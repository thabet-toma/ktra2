// TaskDetailsModal.helpers.ts
import { Task } from "../../types";

// الحصول على حالة المستخدم الحالي في المهمة
export const getUserTaskStatus = (task: Task, userId: string) => {
  return (
    task.userStatuses?.[userId] || {
      status: "not_started" as const,
      startedAt: undefined,
      completedAt: undefined,
      currentWorkTime: 0,
      totalWorkTime: 0,
      workStartTime: undefined,
    }
  );
};