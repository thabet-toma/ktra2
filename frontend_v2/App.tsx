import React, { useState, useEffect, useRef, useCallback } from "react";
import { SearchForm } from "./components/SearchForm";
import { ResultsPage } from "./components/ResultsPage";
import { LoadingSpinner } from "./components/LoadingSpinner";
import { ErrorDisplay } from "./components/ErrorDisplay";
import {
  Product,
  SearchQuery,
  User,
  Task,
  Theme,
  TaskStatus,
  ActivityLog,
  Submission,
  Category,
  CashBox,
  AppView,
} from "./types";
import { findProducts } from "./services/geminiService";
import { LoginPage } from "./components/LoginPage";
import { SignupPage } from "./components/SignupPage";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { NoSqlMigrationBanner } from "./components/NoSqlMigrationBanner";
import { Dashboard } from "./components/Dashboard";
import { TaskManagement } from "./components/TaskManagement";
import { UserManagement } from "./components/UserManagement";
import { Reports } from "./components/Reports";
import { EmployeeNotes } from "./components/EmployeeNotes";
import { SettingsPage } from "./components/SettingsPage";
import { PointsHistoryPage } from "./components/PointsHistoryPage";
import { EmployeePointsManagement } from "./components/EmployeePointsManagement";
import { PriceOfferManagement } from './components/procurement/PriceOfferManagement';
import { DealManagement } from "./components/procurement/DealManagement";
import { ItemsManagement } from "./components/items/ItemsManagement";
import { SupplierManagement } from "./components/suppliers/SupplierManagement";
import { ShipmentManagement } from "./components/procurement/shipments/ShipmentManagement";
import { TaskList } from "./components/TaskList";
import { RejectReasonModal } from "./components/modals/RejectReasonModal";
import {
  seedUsersIfEmpty,
  subscribeToUsers,
  subscribeToTasks,
  createTaskInDb,
  updateTaskInDb,
  addSubmissionToTaskInDb,
  updateSubmissionInTaskInDb,
  updateUserInDb,
  deleteUserFromDb,
  activityService,
  updateUserTaskStatus,
  pointsHistoryService,
  getCategories,
} from "./services/firestoreService";
import { fetchUserProfile, logoutUser } from "./services/authService";
import { useAuth } from "./contexts/AuthContext";
import { activeTasksService } from "./services/activeTasksService";
import { EmployeeAttendance } from "./components/EmployeeAttendance";
import { AttendanceManagement } from "./components/AttendanceManagement";
import { PurchaseInvoice } from "./components/procurement/PurchaseInvoice";
import { autoDisableScheduler } from "./services/autoDisableScheduler";
import PublicGallery from "./components/PublicGallery";
import { TaskDetailsModal } from "./components/TaskDetailsModal";
import { OldPurchaseInvoice } from "./components/OldPurchaseInvoice";
import { CashBoxList } from "./components/finance/CashBoxList";
import { CashBoxStatement } from "./components/finance/CashBoxStatement";
import { StorePage } from "./components/store/StorePage";
import { AccountingCoaPage } from "./components/accounting/AccountingCoaPage";
import { AccountingJournalListPage } from "./components/accounting/AccountingJournalListPage";
import { AccountingJournalEntryPage } from "./components/accounting/AccountingJournalEntryPage";
import { AccountingChequesPage } from "./components/accounting/AccountingChequesPage";
import { AccountingGeneralLedgerPage } from "./components/accounting/AccountingGeneralLedgerPage";
import { AccountingTrialBalancePage } from "./components/accounting/AccountingTrialBalancePage";
import { SqlProductsPage } from "./components/sql/SqlProductsPage";
import { SqlPartnersPage } from "./components/sql/SqlPartnersPage";
import { SqlDealsPage } from "./components/sql/SqlDealsPage";
import { SqlShipmentsPage } from "./components/sql/SqlShipmentsPage";



type SourcingView = "search" | "loading" | "results";
type AuthView = "login" | "signup";

const App: React.FC = () => {

  const { currentUser, loading: authLoading, logout, updateUser } = useAuth();
  const [authView, setAuthView] = useState<AuthView>("login");
  const [users, setUsers] = useState<User[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  const [categories, setCategories] = useState<Category[]>([]);

  const [userTaskTime, setUserTaskTime] = useState(0);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [appView, setAppView] = useState<AppView>("dashboard");
  const [sourcingView, setSourcingView] = useState<SourcingView>("search");
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [selectedTaskDetails, setSelectedTaskDetails] = useState<Task | null>(
    null
  );
  const [selectedCashBox, setSelectedCashBox] = useState<CashBox | null>(null);
  /** null = قيد جديد؛ رقم = تعديل — يُستخدم مع appView === accounting-journal-entry */
  const [accountingJournalId, setAccountingJournalId] = useState<number | null>(null);
  const [rejectingTask, setRejectingTask] = useState<Task | null>(null);
  const [theme, setTheme] = useState<Theme>("light");

  const activeTaskRef = useRef<Task | null>(activeTask);

  useEffect(() => {
    // بدء مجدول التعطيل التلقائي عند تحميل التطبيق للمديرين فقط
    if (currentUser && currentUser.role === "manager") {
      autoDisableScheduler.start();
    }

    // تنظيف عند إغلاق التطبيق أو تغيير المستخدم
    return () => {
      if (currentUser && currentUser.role === "manager") {
        autoDisableScheduler.stop();
      }
    };
  }, [currentUser]);

  useEffect(() => {
    activeTaskRef.current = activeTask;
  }, [activeTask]);

  // أو بدلاً من الاشتراك، يمكنك جلب الفئات مرة واحدة
  useEffect(() => {
    const loadCategories = async () => {
      const fetchedCategories = await getCategories();
      setCategories(fetchedCategories);
    };
    loadCategories();
  }, []);

  // الاشتراك في تحديثات الوقت من الخدمة العالمية
  useEffect(() => {
    if (!currentUser) return;

    const unsubscribe = activeTasksService.subscribeToTimeUpdates(
      (taskId, userId, time) => {
        if (userId === currentUser.id) {
          if (activeTask && activeTask.id === taskId) {
            setUserTaskTime(Math.floor(time / 1000)); // تحويل للثواني للعرض فقط
          }
        }
      }
    );

    return unsubscribe;
  }, [currentUser, activeTask]);

  // استعادة المهام النشطة
  useEffect(() => {
    if (!currentUser || tasks.length === 0) return;

    const userActiveTasks = tasks.filter((task) => {
      const userStatus = task.userStatuses?.[currentUser.id];
      return userStatus?.status === "in_progress" && userStatus.workStartTime;
    });

    userActiveTasks.forEach((task) => {
      const userStatus = task.userStatuses![currentUser.id];
      const accumulatedTime =
        (userStatus.totalWorkTime || 0) + (userStatus.currentWorkTime || 0);

      if (!activeTasksService.isTaskActive(task.id, currentUser.id)) {
        activeTasksService.startTask(task.id, currentUser.id, accumulatedTime);
      }

      if (userActiveTasks.length === 1 && !activeTask) {
        setActiveTask(task);
        const currentTime = activeTasksService.getCurrentTime(
          task.id,
          currentUser.id
        );
        setUserTaskTime(currentTime);
      }
    });
  }, [currentUser, tasks, activeTask]);

  // Deep Linking Logic triggered when user loads
  useEffect(() => {
    if (currentUser && currentUser.isApproved) {
      // Check for Query Params for Direct Navigation (Deep Linking)
      const params = new URLSearchParams(window.location.search);
      const viewParam = params.get('view') as AppView;

      let defaultView: AppView = "dashboard";

      if (viewParam) {
        defaultView = viewParam;
      } else {
        // Default logic
        switch (currentUser.role) {
          case "employee":
          case "procurement":
            defaultView = "tasks";
            break;
          case "manager":
            defaultView = "dashboard";
            break;
          default:
            defaultView = "tasks";
        }
      }
      setAppView(defaultView);
    }
  }, [currentUser]);

  // Data Subscription
  useEffect(() => {
    if (!currentUser) return;
    seedUsersIfEmpty();
    const unsubscribeUsers = subscribeToUsers((fetchedUsers) => {
      setUsers(fetchedUsers);
    });
    const unsubscribeTasks = subscribeToTasks((fetchedTasks) => {
      setTasks(fetchedTasks);
    });
    return () => {
      unsubscribeUsers();
      unsubscribeTasks();
    };
  }, [currentUser]);

  // Sync Active Task
  useEffect(() => {
    if (activeTask) {
      const updatedActiveTask = tasks.find((t) => t.id === activeTask.id);
      if (updatedActiveTask) {
        if (JSON.stringify(updatedActiveTask) !== JSON.stringify(activeTask)) {
          setActiveTask(updatedActiveTask);
        }
      }
    }
  }, [tasks, activeTask]);

  // Theme
  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prevTheme) => (prevTheme === "light" ? "dark" : "light"));
  };

  // ... (Task & Submission Handlers - Same as before)
  const handleUpdateUserTaskStatus = async (
    taskId: string,
    userId: string,
    status: any
  ) => {
    try {
      if (
        (status.status === "submitted" || status.status === "completed") &&
        activeTasksService.isTaskActive(taskId, userId)
      ) {
        const totalTime = activeTasksService.getCurrentTime(taskId, userId);
        status = {
          ...status,
          totalWorkTime: totalTime,
          currentWorkTime: 0,
          workStartTime: null,
        };
        activeTasksService.stopTask(taskId, userId);
      }

      if (status.status === "in_progress" && status.workStartTime) {
        const userActiveTasks = activeTasksService.getUserActiveTasks(userId);
        userActiveTasks.forEach((activeTaskId) => {
          activeTasksService.stopTask(activeTaskId, userId);
        });

        const accumulatedTime = status.totalWorkTime || 0;
        activeTasksService.startTask(taskId, userId, accumulatedTime);
      }

      await updateUserTaskStatus(taskId, userId, status);

      setTasks((prevTasks) =>
        prevTasks.map((task) =>
          task.id === taskId
            ? {
              ...task,
              userStatuses: {
                ...task.userStatuses,
                [userId]: status,
              },
              updatedAt: new Date().toISOString(),
            }
            : task
        )
      );

      if (selectedTaskDetails?.id === taskId) {
        setSelectedTaskDetails((prev) =>
          prev
            ? {
              ...prev,
              userStatuses: {
                ...prev.userStatuses,
                [userId]: status,
              },
              updatedAt: new Date().toISOString(),
            }
            : null
        );
      }

      if (activeTask?.id === taskId && userId === currentUser?.id) {
        setActiveTask((prev) =>
          prev
            ? {
              ...prev,
              userStatuses: {
                ...prev.userStatuses,
                [userId]: status,
              },
              updatedAt: new Date().toISOString(),
            }
            : null
        );

        if (status.status === "in_progress" && status.workStartTime) {
          const accumulatedTime = status.totalWorkTime || 0;
          activeTasksService.startTask(taskId, userId, accumulatedTime);
          setUserTaskTime(Math.floor(accumulatedTime / 1000));
        }

        if (status.status === "submitted" || status.status === "completed") {
          setUserTaskTime(Math.floor((status.totalWorkTime || 0) / 1000));
        }
      }
    } catch (error) {
      console.error("Error updating user task status:", error);
      alert("حدث خطأ أثناء تحديث حالة المهمة");
    }
  };

  const handleCreateSubmission = async (
    taskId: string,
    submissionData: Omit<
      Submission,
      "id" | "taskId" | "userId" | "createdAt" | "updatedAt"
    >
  ) => {
    if (!currentUser) return;
    try {
      const now = new Date().toISOString();
      const newSubmission: Submission = {
        id: crypto.randomUUID(),
        taskId,
        userId: currentUser.id,
        items: submissionData.items,
        createdAt: now,
        updatedAt: now,
        status: "pending",
      };

      let totalWorkTime = 0;
      const currentTask = tasks.find((t) => t.id === taskId);
      const currentUserStatus = currentTask?.userStatuses?.[currentUser.id];

      if (activeTasksService.isTaskActive(taskId, currentUser.id)) {
        totalWorkTime = activeTasksService.getCurrentTime(
          taskId,
          currentUser.id
        );
        activeTasksService.stopTask(taskId, currentUser.id);
      } else if (currentUserStatus) {
        totalWorkTime = currentUserStatus.totalWorkTime || 0;
        if (
          currentUserStatus.status === "in_progress" &&
          currentUserStatus.workStartTime
        ) {
          const startTime = new Date(currentUserStatus.workStartTime).getTime();
          const sessionTime = Date.now() - startTime;
          totalWorkTime += sessionTime;
        }
      }

      const log = createLog(currentUser.id, "SUBMISSION_CREATED");
      await addSubmissionToTaskInDb(taskId, newSubmission, log);

      await handleUpdateUserTaskStatus(taskId, currentUser.id, {
        status: "submitted",
        submittedAt: now,
        totalWorkTime: totalWorkTime,
        currentWorkTime: 0,
        workStartTime: null,
      });

      if (activeTask && activeTask.id === taskId) {
        setActiveTask(null);
        setAppView("tasks");
      }
      setSelectedTaskDetails(null);
    } catch (e) {
      console.error("Error creating submission:", e);
      alert("حدث خطأ أثناء حفظ التسليم. الرجاء المحاولة مرة أخرى.");
    }
  };

  const handleEditSubmission = async (
    taskId: string,
    submissionId: string,
    updateData: Partial<Submission>
  ) => {
    if (!currentUser) return;
    try {
      const log = createLog(currentUser.id, "SUBMISSION_EDITED");
      await updateSubmissionInTaskInDb(taskId, submissionId, updateData, log);
      setTasks((prevTasks) =>
        prevTasks.map((t) => {
          if (t.id === taskId) {
            const updatedSubmissions = t.submissions.map((sub) => {
              if (sub.id === submissionId) {
                return { ...sub, ...updateData };
              }
              return sub;
            });
            return { ...t, submissions: updatedSubmissions };
          }
          return t;
        })
      );
      if (selectedTaskDetails?.id === taskId) {
        setSelectedTaskDetails((prev) => {
          if (!prev) return null;
          const updatedSubmissions = prev.submissions.map((sub) =>
            sub.id === submissionId ? { ...sub, ...updateData } : sub
          );
          return { ...prev, submissions: updatedSubmissions };
        });
      }
    } catch (e) {
      console.error("Error editing submission:", e);
      alert("حدث خطأ أثناء تعديل التسليم.");
    }
  };

  const handleUpdateSubmissionStatus = async (
    taskId: string,
    submissionId: string,
    status: "approved" | "rejected",
    reviewerNotes?: string
  ) => {
    if (!currentUser) return;
    try {
      const task = tasks.find((t) => t.id === taskId);
      if (!task) return;

      const submission = task.submissions?.find((s) => s.id === submissionId);
      if (!submission) return;

      const userTaskStatus = task.userStatuses?.[submission.userId];
      const userHasCompletedTask = userTaskStatus?.status === "completed";

      if (status === "approved" && !userHasCompletedTask) {
        const userToReward = users.find((u) => u.id === submission.userId);
        if (userToReward) {
          const today = new Date().toISOString().split("T")[0];
          // Fix: Use totalPoints instead of points, and remove pointsHistory which is not in User type
          const newUserPoints = (userToReward.totalPoints || 0) + 5;

          const updatedUser: User = {
            ...userToReward,
            totalPoints: newUserPoints,
          };

          // Note: pointsHistory is handled by pointsHistoryService below, not in the User object directly

          await updateUserInDb(updatedUser);

          const currentPoints = await pointsHistoryService.getDailyPoints(
            submission.userId,
            today
          );

          const updatedTaskPoints = (currentPoints?.taskPoints || 0) + 5;
          const updatedCompletedTasks = (currentPoints?.completedTasks || 0) + 1;
          const updatedTotalPoints = (currentPoints?.totalPoints || 0) + 5;

          await pointsHistoryService.updatePointsManually(
            submission.userId,
            today,
            {
              taskPoints: updatedTaskPoints,
              completedTasks: updatedCompletedTasks,
              totalPoints: updatedTotalPoints,
              attendancePoints: currentPoints?.attendancePoints || 0,
              activityPoints: currentPoints?.activityPoints || 0,
              workMinutes: currentPoints?.workMinutes || 0,
              checkinClicks: currentPoints?.checkinClicks || 0,
              attended: currentPoints?.attended || false,
            }
          );

          setUsers((prevUsers) =>
            prevUsers.map((u) => (u.id === submission.userId ? updatedUser : u))
          );
        }
      }

      const updatedSubmission: Submission = {
        ...submission,
        status,
        reviewerNotes,
        reviewedAt: new Date().toISOString(),
        reviewedBy: currentUser.id,
      };

      const log = createLog(
        currentUser.id,
        "SUBMISSION_REVIEWED",
        submission.status,
        status
      );

      const updatedTask: Task = {
        ...task,
        submissions:
          task.submissions?.map((s) =>
            s.id === submissionId ? updatedSubmission : s
          ) || [],
        logs: [...task.logs, log],
        updatedAt: new Date().toISOString(),
      };

      const userId = submission.userId;
      const userStatus = task.userStatuses?.[userId];

      if (userStatus) {
        if (status === "approved") {
          updatedTask.userStatuses = {
            ...task.userStatuses,
            [userId]: {
              ...userStatus,
              status: "completed",
              completedAt: new Date().toISOString(),
              totalWorkTime: userStatus.totalWorkTime || 0,
              currentWorkTime: 0,
              workStartTime: null,
            },
          };
          if (activeTask?.id === taskId && userId === currentUser.id) {
            activeTasksService.stopTask(taskId, userId);
          }
        } else if (status === "rejected") {
          updatedTask.userStatuses = {
            ...task.userStatuses,
            [userId]: {
              ...userStatus,
              status: "rejected",
              completedAt: undefined,
              totalWorkTime: userStatus.totalWorkTime || 0,
              currentWorkTime: 0,
              workStartTime: null,
            },
          };
        }
      }

      setTasks((prevTasks) =>
        prevTasks.map((t) => (t.id === taskId ? updatedTask : t))
      );

      if (selectedTaskDetails?.id === taskId) {
        setSelectedTaskDetails(updatedTask);
      }

      await updateTaskInDb(updatedTask);
    } catch (error) {
      console.error("❌ خطأ في handleUpdateSubmissionStatus:", error);
      alert("حدث خطأ أثناء تحديث حالة التسليم");
    }
  };

  // ... (Other Handlers - Same as before)
  const pauseActiveTaskTimer = useCallback(async () => {
    const taskToPause = activeTaskRef.current;
    if (!taskToPause || !currentUser) return;

    const userTaskStatus = taskToPause.userStatuses?.[currentUser.id];
    if (!userTaskStatus || userTaskStatus.status !== "in_progress") {
      return;
    }

    const totalTime = activeTasksService.stopTask(
      taskToPause.id,
      currentUser.id
    );

    const updatedUserStatus = {
      ...userTaskStatus,
      workStartTime: null,
      currentWorkTime: 0,
      totalWorkTime: totalTime,
    };

    await handleUpdateUserTaskStatus(
      taskToPause.id,
      currentUser.id,
      updatedUserStatus
    );
    setUserTaskTime(Math.floor(totalTime / 1000));
  }, [currentUser, handleUpdateUserTaskStatus]);

  const startUserTask = async (taskId: string) => {
    if (!currentUser) return;
    const task = tasks.find((t) => t.id === taskId);
    if (!task) return;

    const userActiveTasks = activeTasksService.getUserActiveTasks(
      currentUser.id
    );
    userActiveTasks.forEach((activeTaskId) => {
      activeTasksService.stopTask(activeTaskId, currentUser.id);
    });

    const userStatus = {
      status: "in_progress" as const,
      startedAt: new Date().toISOString(),
      workStartTime: new Date().toISOString(),
      currentWorkTime: 0,
      totalWorkTime: 0,
    };

    await handleUpdateUserTaskStatus(taskId, currentUser.id, userStatus);
    activeTasksService.startTask(taskId, currentUser.id, 0);
    setActiveTask(task);
    setUserTaskTime(0);
  };

  const handleOpenSearchPlatform = (task: Task) => {
    if (!currentUser) return;
    const userStatus = task.userStatuses?.[currentUser.id];
    if (!userStatus || userStatus.status !== "in_progress") {
      startUserTask(task.id);
    } else if (!activeTasksService.isTaskActive(task.id, currentUser.id)) {
      const accumulatedTime =
        (userStatus.totalWorkTime || 0) + (userStatus.currentWorkTime || 0);
      activeTasksService.startTask(task.id, currentUser.id, accumulatedTime);
    }
    setActiveTask(task);
    setAppView("sourcing");
    setSourcingView("search");
    setSelectedTaskDetails(null);
  };

  const handleLogout = async () => {
    if (currentUser) {
      const userActiveTasks = activeTasksService.getUserActiveTasks(
        currentUser.id
      );
      userActiveTasks.forEach((taskId) =>
        activeTasksService.stopTask(taskId, currentUser.id)
      );
    }
    await logout();
    setActiveTask(null);
    setUserTaskTime(0);
    setSourcingView("search");
    setProducts([]);
    setAppView("dashboard");
  };

  const createLog = (
    userId: string,
    action: string,
    oldValue?: string,
    newValue?: string
  ): ActivityLog => {
    return {
      id: crypto.randomUUID(),
      userId,
      action,
      timestamp: new Date().toISOString(),
      ...(oldValue !== undefined && { oldValue }),
      ...(newValue !== undefined && { newValue }),
    };
  };

  const handleUpdateTask = async (updatedTask: Task) => {
    if (!currentUser) return;
    const log = createLog(currentUser.id, "TASK_EDITED");
    await updateTaskInDb({ ...updatedTask, logs: [...updatedTask.logs, log] });
  };

  const handleUpdateTaskStatus = async (
    taskId: string,
    newStatus: TaskStatus
  ) => {
    if (!currentUser) return;
    const task = tasks.find((t) => t.id === taskId);
    if (!task) return;

    if (newStatus === "REJECTED" && currentUser.role === "manager") {
      setRejectingTask(task);
      return;
    }

    const log = createLog(
      currentUser.id,
      "STATUS_CHANGED",
      task.status,
      newStatus
    );
    const updatedTask: Task = {
      ...task,
      status: newStatus,
      logs: [...task.logs, log],
      updatedAt: new Date().toISOString(),
    };

    if (newStatus === "COMPLETED") {
      updatedTask.completedAt = new Date().toISOString();
      if (currentUser) activeTasksService.stopTask(taskId, currentUser.id);
    }

    if (task.status === "REJECTED" && newStatus === "IN_PROGRESS") {
      updatedTask.rejectReason = "";
    }

    if (newStatus === "IN_PROGRESS") {
      updatedTask.workStartTime = new Date().toISOString();
      setActiveTask(updatedTask);
      setAppView("sourcing");
    } else if (["COMPLETED", "WAITING_FOR_REVIEW"].includes(newStatus)) {
      if (activeTask && activeTask.id === taskId) {
        await pauseActiveTaskTimer();
        setActiveTask(null);
        setAppView("tasks");
      }
    }

    await updateTaskInDb(updatedTask);
    setSelectedTaskDetails(null);
  };

  const handleRejectTaskWithReason = async (taskId: string, reason: string) => {
    if (!currentUser) return;
    const task = tasks.find((t) => t.id === taskId);
    if (!task) return;
    const log = createLog(currentUser.id, "REJECTED", undefined, reason);
    const updatedTask: Task = {
      ...task,
      status: "REJECTED",
      rejectReason: reason,
      logs: [...task.logs, log],
      workStartTime: null,
    };
    if (activeTask && activeTask.id === taskId) {
      activeTasksService.stopTask(taskId, currentUser.id);
      setActiveTask(null);
    }
    await updateTaskInDb(updatedTask);
    setRejectingTask(null);
    setSelectedTaskDetails(null);
  };

  const handleSearch = async (query: SearchQuery) => {
    setSourcingView("loading");
    setError(null);
    try {
      const results = await findProducts(query);
      setProducts(results);
      setSourcingView("results");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "An unknown error occurred."
      );
      setSourcingView("search");
    }
  };

  const handleCreateTask = async (newTaskData: any) => {
    if (!currentUser) return;
    const now = new Date().toISOString();
    const newTask: Task = {
      ...newTaskData,
      id: crypto.randomUUID(),
      assignedTo: newTaskData.assignedTo,
      status: "NEW",
      totalWorkTime: 0,
      workStartTime: null,
      createdAt: now,
      updatedAt: now,
      submissions: [],
      logs: [createLog(currentUser.id, "TASK_CREATED")],
      userStatuses: {},
    };
    await createTaskInDb(newTask);
  };

  const handleResetSourcing = () => {
    setSourcingView("search");
    setProducts([]);
  };

  const handleUpdateUser = async (user: User) => {
    await updateUserInDb(user);
    if (user.id === currentUser?.id) {
      updateUser(user);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    await deleteUserFromDb(userId);
  };

  const handleSaveNotes = async (userId: string, notes: string) => {
    await updateUserInDb({ id: userId, notes });
  };

  const renderMainContent = () => {
    if (appView === "sourcing") {
      if (!activeTask) {
        return (
          <TaskList
            user={currentUser!}
            tasks={tasks}
            onSelectTask={setSelectedTaskDetails}
          />
        );
      }

      switch (sourcingView) {
        case "loading":
          return <LoadingSpinner />;
        case "results":
          return (
            <ResultsPage
              products={products}
              onBack={handleResetSourcing}
              isTaskActive={!!activeTask}
            />
          );
        case "search":
        default:
          return (
            <>
              {error && (
                <ErrorDisplay message={error} onClose={() => setError(null)} />
              )}
              <SearchForm
                onSearch={handleSearch}
                activeTask={activeTask}
                onBackToDashboard={() => setAppView("tasks")}
              />
            </>
          );
      }
    }

    switch (appView) {
      case "dashboard":
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "tasks":
        return (
          <TaskList
            user={currentUser!}
            tasks={tasks}
            categories={categories}
            onSelectTask={setSelectedTaskDetails}
          />
        );

      case "task-management":
        if (
          currentUser!.role === "manager" ||
          currentUser!.role === "procurement"
        ) {
          return (
            <TaskManagement
              allTasks={tasks}
              users={users}
              onCreateTask={handleCreateTask}
              onSelectTask={setSelectedTaskDetails}
            />
          );
        } else {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }

      case "users":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        return (
          <UserManagement
            users={users}
            onUpdateUser={handleUpdateUser}
            onDeleteUser={handleDeleteUser}
          />
        );

      case "reports":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        return <Reports tasks={tasks} users={users} />;

      case "employee-notes":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        return <EmployeeNotes users={users} onSaveNotes={handleSaveNotes} />;

      case "points-history":
        return <PointsHistoryPage user={currentUser} />;

      case "points-management":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        return <EmployeePointsManagement users={users} />;

      case "settings":
        return <SettingsPage user={currentUser!} />;

      case "attendance":
        if (currentUser!.role === "manager") {
          return <AttendanceManagement users={users} currentUser={currentUser!} />;
        }
        return <EmployeeAttendance currentUser={currentUser!} />;

      case "purchase-invoices":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <PurchaseInvoice />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      // ---------- New Case Added Here ----------
      case "old-invoices":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <OldPurchaseInvoice />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "price-offers":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <PriceOfferManagement />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "deals-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <DealManagement currentUser={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
      // -----------------------------------------

      case "items-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <ItemsManagement user={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "supplier-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <SupplierManagement />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "shipments-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <ShipmentManagement currentUser={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "cash-boxes":
        if (currentUser!.role === "manager") {
          return (
            <CashBoxList
              onSelectCashBox={(box) => {
                setSelectedCashBox(box);
                setAppView("cash-box-details");
              }}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "cash-box-details":
        if (currentUser!.role === "manager" && selectedCashBox) {
          return (
            <CashBoxStatement
              cashBox={selectedCashBox}
              onBack={() => setAppView("cash-boxes")}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;

      case "gallery":
        return <PublicGallery />;

      case "accounting-coa":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <AccountingCoaPage />;

      case "accounting-journals":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return (
          <AccountingJournalListPage
            onNew={() => {
              setAccountingJournalId(null);
              setAppView("accounting-journal-entry");
            }}
            onOpen={(id) => {
              setAccountingJournalId(id);
              setAppView("accounting-journal-entry");
            }}
          />
        );

      case "accounting-journal-entry":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return (
          <AccountingJournalEntryPage
            journalId={accountingJournalId}
            onBack={() => setAppView("accounting-journals")}
          />
        );

      case "accounting-cheques":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <AccountingChequesPage />;

      case "accounting-general-ledger":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <AccountingGeneralLedgerPage />;

      case "accounting-trial-balance":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <AccountingTrialBalancePage />;

      case "sql-products":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <SqlProductsPage />;

      case "sql-partners":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <SqlPartnersPage />;

      case "sql-deals":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <SqlDealsPage />;

      case "sql-shipments":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
        }
        return <SqlShipmentsPage />;

      default:
        return <Dashboard tasks={tasks} users={users} onNavigate={setAppView} currentUser={currentUser!} />;
    }
  };

  // 1. Handle Store View (Public & Private)
  // if (appView === 'store') {
  //   return (
  //     <div className={theme}>
  //       <StorePage
  //         currentUser={currentUser}
  //         onLoginSuccess={(user) => {
  //           setCurrentUser(user);
  //           // If user is employee/manager, maybe redirect to dashboard? 
  //           // Or stay in store? Let's stay in store for now, user can click Dashboard.
  //           if (user.role !== 'store_guest') {
  //             // setAppView('dashboard'); // Optional
  //           }
  //         }}
  //         onNavigateToLogin={() => {
  //           setAppView('dashboard'); // Will trigger !currentUser check -> result in Login Page
  //         }}
  //       />
  //     </div>
  //   );
  // }

  // 2. Auth Checks
  if (authLoading) {
    return (
      <div className={theme}>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <LoadingSpinner />
        </div>
      </div>
    );
  }

  if (!currentUser) {
    if (authView === "signup") {
      return (
        <div className={theme}>
          <SignupPage onNavigateToLogin={() => setAuthView("login")} />
        </div>
      );
    }
    return (
      <div className={theme}>
        <LoginPage
          onNavigateToSignup={() => setAuthView("signup")}
          onGoToStore={() => setAppView('store')}
        />
      </div>
    );
  }

  const showReturnButton = !!activeTask && appView !== "sourcing";

  return (
    <div
      dir="rtl"
      className="min-h-screen bg-gray-100 dark:bg-gray-900 font-sans text-gray-800 dark:text-gray-200 flex flex-col md:flex-row"
    >
      <Sidebar user={currentUser} activeView={appView} setView={setAppView} />

      <div className="flex-1 flex flex-col h-screen overflow-hidden mb-16 md:mb-0">
        <Header
          user={currentUser}
          onLogout={handleLogout}
          activeTask={activeTask}
          userTaskTime={userTaskTime}
          theme={theme}
          toggleTheme={toggleTheme}
          showReturnButton={showReturnButton}
          onReturnToTask={() => setAppView("sourcing")}
          onNavigate={(view) => setAppView(view)}
        />

        <NoSqlMigrationBanner isManager={currentUser?.role === "manager"} />

        <main className="flex-1 overflow-y-auto p-3 sm:p-6 lg:p-8 w-full mx-auto max-w-7xl">
          {renderMainContent()}
        </main>
      </div>

      {selectedTaskDetails && (
        <TaskDetailsModal
          isOpen={!!selectedTaskDetails}
          onClose={() => setSelectedTaskDetails(null)}
          task={selectedTaskDetails}
          user={currentUser}
          users={users}
          onUpdateUserTaskStatus={handleUpdateUserTaskStatus}
          onCreateSubmission={handleCreateSubmission}
          onEditSubmission={handleEditSubmission}
          onUpdateTask={handleUpdateTask}
          onOpenSearchPlatform={handleOpenSearchPlatform}
          onUpdateSubmissionStatus={handleUpdateSubmissionStatus}
        />
      )}
      {rejectingTask && (
        <RejectReasonModal
          isOpen={!!rejectingTask}
          onClose={() => setRejectingTask(null)}
          onSubmit={(reason) =>
            handleRejectTaskWithReason(rejectingTask.id, reason)
          }
        />
      )}
    </div>
  );
};

export default App;