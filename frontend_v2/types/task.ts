
import { Product } from './product';

export type TaskCategory = 'electronics' | 'electrical' | 'clothing';

export type TaskStatus = 'NEW' | 'ACCEPTED' | 'IN_PROGRESS' | 'WAITING_FOR_REVIEW' | 'COMPLETED' | 'REJECTED';

export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

export interface ActivityLog {
    id: string;
    userId: string;
    action: string;
    oldValue?: string;
    newValue?: string;
    timestamp: string;
}

export interface SubmissionItem {
    id: string;
    productLink: string;
    productPrice?: number;
    notes?: string;
    attachmentName?: string;
    attachmentUrl?: string;
    images?: string[];
    imageFiles?: File[];
    attachmentType?: 'file' | 'images';
    createdAt?: string;
    isNew?: boolean;
}

export interface Submission {
    id: string;
    taskId: string;
    userId: string;
    items: SubmissionItem[];
    createdAt: string;
    updatedAt: string;
    status: 'pending' | 'approved' | 'rejected';
    reviewerNotes?: string;
    reviewedAt?: string;
    reviewedBy?: string;
    newItemsCount?: number;
}

export interface Task {
    id: string;
    title: string;
    description: string;
    targetPrice?: number;
    imageUrl?: string;
    images?: string[];
    assignedTo: string[];
    status: TaskStatus;
    priority: TaskPriority;
    tags?: string[];
    createdAt: string;
    updatedAt: string;
    completedAt?: string;
    logs: ActivityLog[];
    submissions: Submission[];
    rejectReason?: string;
    totalWorkTime: number;
    workStartTime?: string | null;
    category: TaskCategory;
    allowedSites: string[];
    dueDate: string;
    userStatuses?: {
        [userId: string]: {
            status: 'not_started' | 'in_progress' | 'submitted' | 'completed' | 'rejected';
            startedAt?: string;
            completedAt?: string;
            currentWorkTime?: number;
            totalWorkTime?: number;
            workStartTime?: string | null;
        };
    };
}

export const isTaskAssignedToUser = (task: Task, userId: string): boolean => {
    if (Array.isArray(task.assignedTo)) {
        return task.assignedTo.includes(userId);
    }
    return task.assignedTo === userId;
};

export const getUserSubmissions = (task: Task, userId: string): Submission[] => {
    return task.submissions?.filter(sub => sub.userId === userId) || [];
};

export const getUserTaskStatus = (task: Task, userId: string) => {
    const userSubmissions = getUserSubmissions(task, userId);

    if (userSubmissions.length > 0) {
        const latestSubmission = userSubmissions[userSubmissions.length - 1];
        return {
            hasSubmission: true,
            status: latestSubmission.status || 'pending',
            submissionCount: userSubmissions.length,
            latestSubmission: latestSubmission
        };
    }

    return {
        hasSubmission: false,
        status: 'not_started',
        submissionCount: 0,
        latestSubmission: null
    };
};
