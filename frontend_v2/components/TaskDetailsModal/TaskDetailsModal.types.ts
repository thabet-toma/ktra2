// TaskDetailsModal/TaskDetailsModal.types.ts
import { Task, User, Submission } from "../../types";

export interface TaskDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  task: Task;
  user: User;
  users: User[];
  onUpdateUserTaskStatus: (taskId: string, userId: string, status: any) => void;
  onCreateSubmission: (
    taskId: string,
    submission: Omit<Submission, "id" | "taskId" | "userId" | "createdAt" | "updatedAt">
  ) => void;
  onEditSubmission: (
    taskId: string,
    submissionId: string,
    data: Partial<Submission>
  ) => void;
  onUpdateTask: (task: Task) => void;
  onOpenSearchPlatform: (task: Task) => void;
  onUpdateSubmissionStatus: (
    taskId: string,
    submissionId: string,
    status: "approved" | "rejected",
    reviewerNotes?: string
  ) => void;
}