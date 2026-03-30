// TaskDetailsModal/useTaskLogic.ts
import { useState, useMemo, useEffect } from "react";
import { Task, User } from "../../types";

export const useTaskLogic = (
  task: Task,
  users: User[],
  isOpen: boolean
) => {
  const [currentTime, setCurrentTime] = useState(Date.now());
  const [expandedUsers, setExpandedUsers] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  // تحديث الوقت كل دقيقة
  useEffect(() => {
    if (isOpen) {
      setCurrentTime(Date.now());
      const interval = setInterval(() => setCurrentTime(Date.now()), 60000);
      return () => clearInterval(interval);
    }
  }, [isOpen]);

  // FIX: التعامل مع assignedTo سواء كان مصفوفة أو نص مفرد
  const assignedUsers = useMemo(() => {
    // نستخدم (as any) لتجنب خطأ TypeScript إذا كان النوع معرفاً كـ string فقط
    const assignedToRaw = task.assignedTo as unknown;
    
    let userIds: string[] = [];

    if (Array.isArray(assignedToRaw)) {
      userIds = assignedToRaw as string[];
    } else if (typeof assignedToRaw === 'string') {
      userIds = [assignedToRaw];
    }

    return userIds
      .map((userId) => users.find((u) => u.id === userId))
      .filter((u): u is User => Boolean(u)); // (u is User) تضمن لـ TS أن النتيجة مصفوفة مستخدمين صحيحة
  }, [task.assignedTo, users]);

  const allSubmissionsData = useMemo(() => {
    return assignedUsers.map(assignedUser => {
      const userId = assignedUser.id;
      const userSubmissions = (task.submissions || []).filter(sub => sub.userId === userId);
      const sortedSubmissions = [...userSubmissions].sort(
        (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      );
      const latestSubmission = sortedSubmissions.length > 0 ? sortedSubmissions[0] : null;
      const userStatus = task.userStatuses?.[userId] || {};
      
      return {
        user: assignedUser,
        userId,
        submissions: sortedSubmissions,
        latestSubmission,
        userStatus,
        submissionCount: userSubmissions.length,
        isExpanded: expandedUsers.includes(userId)
      };
    });
  }, [task, assignedUsers, expandedUsers, users]);

  const filteredSubmissionsData = useMemo(() => {
    return allSubmissionsData.filter(data => {
      const matchesSearch = 
        data.user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        data.user.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (data.latestSubmission?.status && data.latestSubmission.status.toLowerCase().includes(searchTerm.toLowerCase()));
      
      const matchesStatus = 
        statusFilter === 'all' ||
        (statusFilter === 'submitted' && data.latestSubmission) || // تمت إضافة || هنا (كان مفقوداً)
        (statusFilter === 'pending' && data.latestSubmission?.status === 'pending') ||
        (statusFilter === 'approved' && data.latestSubmission?.status === 'approved') ||
        (statusFilter === 'rejected' && data.latestSubmission?.status === 'rejected') ||
        (statusFilter === 'not_submitted' && !data.latestSubmission) ||
        (statusFilter === 'with_new_items' && data.latestSubmission?.newItemsCount && data.latestSubmission.newItemsCount > 0);
      
      return matchesSearch && matchesStatus;
    });
  }, [allSubmissionsData, searchTerm, statusFilter]);

  const stats = useMemo(() => {
    const total = assignedUsers.length;
    const submitted = allSubmissionsData.filter(d => d.latestSubmission).length;
    const pending = allSubmissionsData.filter(d => d.latestSubmission?.status === 'pending').length;
    const approved = allSubmissionsData.filter(d => d.latestSubmission?.status === 'approved').length;
    const rejected = allSubmissionsData.filter(d => d.latestSubmission?.status === 'rejected').length;
    const withNewItems = allSubmissionsData.filter(d => d.latestSubmission?.newItemsCount && d.latestSubmission.newItemsCount > 0).length;

    return { total, submitted, pending, approved, rejected, withNewItems };
  }, [allSubmissionsData, assignedUsers]);

  const toggleUserExpansion = (userId: string) => {
    setExpandedUsers(prev => prev.includes(userId) ? prev.filter(id => id !== userId) : [...prev, userId]);
  };

  return {
    currentTime,
    assignedUsers,
    allSubmissionsData,
    filteredSubmissionsData,
    stats,
    searchTerm,
    setSearchTerm,
    statusFilter,
    setStatusFilter,
    toggleUserExpansion,
    setExpandedUsers,
    expandedUsers
  };
};