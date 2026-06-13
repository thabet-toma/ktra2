import React, { useState, useEffect, useRef, useCallback } from "react";
import { SearchForm } from "./components/SearchForm";
import { AppLayout } from "./components/layout/AppLayout";
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
import { useOnlineStatus } from "./hooks/useOnlineStatus";
import OfflineBanner from "./components/offline/OfflineBanner";
import UpdatePrompt from "./components/offline/UpdatePrompt";
import PendingMutationsPanel from "./components/offline/PendingMutationsPanel";
import OfflineCoachmark from "./components/offline/OfflineCoachmark";
import StatusMessage from "./components/offline/StatusMessage";
import { processMutationQueue, registerConflictListener, type ConflictPayload, type ConflictResolution } from "./services/offline/cachedApi";
import StorageQuotaGuard from "./components/offline/StorageQuotaGuard";
import SyncConflictModal from "./components/offline/SyncConflictModal";
import { useBroadcastSync } from "./hooks/useBroadcastSync";
import { cleanOldCache } from "./services/offline/cacheCleaner";
import { Dashboard } from "./components/Dashboard";
import { TradeDashboard } from "./components/dashboard/TradeDashboard";
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
import { AseelKitStory } from "./components/aseel/AseelKitStory";
import { SalesInvoiceAseelStory } from "./components/sales/SalesInvoiceAseelStory";
import { SalesQuotationsPage } from "./components/sales/SalesQuotationsPage";
import { CreditDebitNotesPage } from "./components/sales/CreditDebitNotesPage";
import { SalesReturnEditor } from "./components/sales/SalesReturnEditor";
import { PurchaseReturnEditor } from "./components/sales/PurchaseReturnEditor";
import { SupplierPaymentsPage } from "./components/sales/SupplierPaymentsPage";
import { ImportDocumentScreen } from "./components/import-flow";
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
import { AccountingVatReportPage } from "./components/accounting/AccountingVatReportPage";
import { AccountingLandedCostPage } from "./components/accounting/AccountingLandedCostPage";
import { FiscalPeriodsPage } from "./components/accounting/FiscalPeriodsPage";
import { ExchangeRatesPage } from "./components/accounting/ExchangeRatesPage";
import { BalanceSheetPage } from "./components/accounting/BalanceSheetPage";
import { IncomeStatementPage } from "./components/accounting/IncomeStatementPage";
import { VatStatementsPage } from "./components/accounting/VatStatementsPage";
import { YearEndClosePage } from "./components/accounting/YearEndClosePage";
import { SqlProductsPage } from "./components/sql/SqlProductsPage";
import { SqlPartnersPage } from "./components/sql/SqlPartnersPage";
import { SqlDealsPage } from "./components/sql/SqlDealsPage";
import { SqlShipmentsPage } from "./components/sql/SqlShipmentsPage";
import { SmartAssistantPage } from "./components/SmartAssistantPage";
import { CustomsClearanceManagement } from "./components/procurement/clearance/CustomsClearanceManagement";
import { StockMovementsPage } from "./components/inventory/StockMovementsPage";
import { StockLevelsPage } from "./components/inventory/StockLevelsPage";
import { InventoryValuationPage } from "./components/inventory/InventoryValuationPage";
import { PropertyRentalPage } from "./components/realestate/PropertyRentalPage";
import { SalesInvoicesPage } from "./components/sales/SalesInvoicesPage";
import { SalesCustomersPage } from "./components/sales/SalesCustomersPage";
import SalesCustomerPaymentsPage from "./components/sales/SalesCustomerPaymentsPage";
import SalesSettingsPage from "./components/sales/SalesSettingsPage";
import LocalShippingPage from "./components/logistics/LocalShippingPage";
import { GroupConstantsPage } from './components/settings/GroupConstantsPage';
import { useLocation, useNavigate } from "react-router-dom";

type SourcingView = "search" | "loading" | "results";
type AuthView = "login" | "signup";

/**
 * task14 M1 (DEF-B1): جدول مسار↔شاشة واحد — مصدر الحقيقة للاتجاهين.
 * كل صفحة أساسية (الشريط الجانبي) لها URL فريد قابل للحفظ والمشاركة؛
 * المسارات ذات المعرّف (deals/:id، accounting/journals/:id، import-flow/:id،
 * purchase-invoices/:id، shipments/:id) تبقى حالات خاصة في setViewAndSyncPath
 * وتأثير التحليل العكسي أدناه.
 */
const VIEW_PATHS: Partial<Record<AppView, string>> = {
  dashboard: "/dashboard",
  tasks: "/tasks",
  "task-management": "/task-management",
  "smart-assistant": "/assistant",
  users: "/users",
  attendance: "/attendance",
  "employee-notes": "/employee-notes",
  "points-management": "/points-management",
  "points-history": "/points-history",
  "sales-invoices": "/sales/invoices",
  "sales-quotations": "/sales/quotations",
  "credit-debit-notes": "/sales/credit-debit-notes",
  "sales-return": "/sales/returns",
  "purchase-return": "/purchase-returns",
  "sales-customer-payments": "/sales/customer-payments",
  "supplier-payments": "/supplier-payments",
  "sales-customers": "/sales/customers",
  "sales-settings": "/sales/settings",
  "purchase-invoices": "/purchase-invoices",
  "old-invoices": "/old-invoices",
  "price-offers": "/price-offers",
  "deals-management": "/deals",
  "items-management": "/items",
  "supplier-management": "/suppliers",
  "import-flow": "/import-flow",
  "shipments-management": "/shipments",
  "customs-clearance": "/clearance",
  "local-shipping": "/local-shipping",
  "stock-levels": "/stock-levels",
  "stock-movements": "/stock-movements",
  "accounting-coa": "/accounting/coa",
  "accounting-journals": "/accounting/journals",
  "accounting-cheques": "/accounting/cheques",
  "accounting-general-ledger": "/accounting/general-ledger",
  "accounting-trial-balance": "/accounting/trial-balance",
  "accounting-vat-report": "/accounting/vat-report",
  "accounting-landed-cost": "/accounting/landed-cost",
  "accounting-fiscal-periods": "/accounting/fiscal-periods",
  "accounting-exchange-rates": "/accounting/exchange-rates",
  "accounting-balance-sheet": "/accounting/balance-sheet",
  "accounting-income-statement": "/accounting/income-statement",
  "accounting-vat-statements": "/accounting/vat-statements",
  "accounting-year-end-close": "/accounting/year-end-close",
  "property-rental": "/property-rental",
  "cash-boxes": "/cash-boxes",
  reports: "/reports",
  gallery: "/gallery",
  settings: "/settings",
  sourcing: "/sourcing",
  store: "/store",
  "group-constants": "/group-constants",
  "aseel-kit": "/aseel-kit",
  "aseel-sales": "/aseel-sales",
};

const PATH_TO_VIEW: Record<string, AppView> = Object.fromEntries(
  (Object.entries(VIEW_PATHS) as [AppView, string][]).map(([view, path]) => [path, view])
);

const App: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const { currentUser, loading: authLoading, logout, updateUser } = useAuth();

  const [authView, setAuthView] = useState<AuthView>("login");
  const [users, setUsers] = useState<User[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  const [categories, setCategories] = useState<Category[]>([]);

  const [userTaskTime, setUserTaskTime] = useState(0);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [appView, setAppView] = useState<AppView>("dashboard");
  /** مزامنة المسار مع الـ URL لكل شاشة مدعومة */
  const setViewAndSyncPath = useCallback(
    (view: AppView, targetId?: string) => {
      if (view === "deals-management") {
        navigate(targetId ? `/deals/${encodeURIComponent(targetId)}` : "/deals", { replace: false });
      } else if (view === "shipments-management") {
        navigate(
          targetId ? `/shipments/${encodeURIComponent(targetId)}` : "/shipments",
          { replace: false }
        );
      } else if (view === "accounting-journals") {
        navigate("/accounting/journals", { replace: false });
      } else if (view === "accounting-journal-entry") {
        if (targetId && targetId !== "new") {
          navigate(`/accounting/journals/${targetId}`, { replace: false });
        } else {
          navigate("/accounting/journals/new", { replace: false });
        }
      } else if (view === "smart-assistant") {
        navigate("/assistant", { replace: false });
      } else if (view === "import-flow") {
        navigate(targetId ? `/import-flow/${encodeURIComponent(targetId)}` : "/import-flow", { replace: false });
      } else if (view === "purchase-invoices") {
        if (targetId && targetId !== "list") {
          navigate(`/purchase-invoices/${encodeURIComponent(targetId)}`, { replace: false });
        } else {
          navigate("/purchase-invoices", { replace: false });
        }
      } else {
        // task14 M1: بقية الشاشات كلها عبر الجدول — URL فريد لكل صفحة
        navigate(VIEW_PATHS[view] ?? "/", { replace: false });
      }
      setAppView(view);
    },
    [navigate]
  );
  const [sourcingView, setSourcingView] = useState<SourcingView>("search");
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [selectedTaskDetails, setSelectedTaskDetails] = useState<Task | null>(
    null
  );
  const [selectedCashBox, setSelectedCashBox] = useState<CashBox | null>(null);
  /** null = قيد جديد؛ رقم = تعديل — يُستخدم مع appView === accounting-journal-entry */
  const [accountingJournalId, setAccountingJournalId] = useState<number | null>(null);
  /** معلومات الصفقة المرتبطة بالقيد المفتوح (لعرض رابط الصفقة داخل القيد) */
  const [accountingJournalDealRef, setAccountingJournalDealRef] = useState<{
    dealId: string;
    dealNumber: string;
    displayName: string;
  } | null>(null);
  /** شاشة الرجوع من قيد اليومية (صفقات أو قائمة القيود) */
  const [accountingJournalBackView, setAccountingJournalBackView] =
    useState<AppView>("accounting-journals");
  /** الصفقة مقابل الشحنة — لعرض الرابط الصحيح من شاشة القيد */
  const [accountingJournalRelatedKind, setAccountingJournalRelatedKind] = useState<
    "deal" | "shipment" | null
  >(null);
  /** تنقّل من شجرة الحسابات: أستاذ عام / مورد */
  const [accountingGlAccountId, setAccountingGlAccountId] = useState<number | null>(null);
  const [accountingSupplierPartnerId, setAccountingSupplierPartnerId] = useState<number | null>(null);
  const [rejectingTask, setRejectingTask] = useState<Task | null>(null);
  const [theme, setTheme] = useState<Theme>("light");
  const onlineStatus = useOnlineStatus();
  const [statusMsg, setStatusMsg] = useState<{ message: string; type: 'info' | 'warn' | 'error' } | null>(null);
  // P3-4 wiring: keep one conflict modal at app root and route 409s from
  // processMutationQueue through it.
  const [syncConflict, setSyncConflict] = useState<{
    payload: ConflictPayload;
    resolve: (r: ConflictResolution) => void;
  } | null>(null);

  useEffect(() => {
    registerConflictListener((payload) => {
      return new Promise<ConflictResolution>((resolve) => {
        setSyncConflict({ payload, resolve });
      });
    });
    return () => registerConflictListener(null);
  }, []);

  useBroadcastSync(useCallback((msg) => {
    if (msg.type === 'ONLINE_CHANGED' && msg.online) {
      processMutationQueue().catch(() => {});
    }
    if (msg.type === 'TENANT_SWITCHED') {
      cleanOldCache(0).catch(() => {});
    }
    if (msg.type === 'MUTATION_UPDATED') {
      setStatusMsg({ message: 'تحديث من تبويب آخر', type: 'info' });
      setTimeout(() => setStatusMsg(null), 3000);
    }
  }, []));
  /** N0-T5: F11 modal portal لثوابت المجموعة */
  const [groupConstantsOpen, setGroupConstantsOpen] = useState(false);

  const activeTaskRef = useRef<Task | null>(activeTask);

  useEffect(() => {
    // بدء مجدول التعطيل التلقائي عند تحميل التطبيق للمديرين فقط
    if (currentUser && currentUser.role === "manager") {
      autoDisableScheduler.start();
    }
    // Surface a console warning if localStorage.tenantId doesn't match the
    // env-configured tenant — helps diagnose the "0 شحنة / 0 بيان but deals
    // work" symptom by pointing at the actual mismatch. Then run the
    // boot-time auto-recovery: if the backend rejects the stored tenantId,
    // clear it and reload (no manual DevTools step needed).
    import("./utils/tenantContext").then((m) => {
      m.warnIfTenantMismatch?.();
      void m.autoRecoverInvalidTenant?.();
    });

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

  // مسارات معاينة الأصيل (dev/QA) — تُكتشف قبل حارس المصادقة لأن لها bypass خاص
  useEffect(() => {
    const p = (location.pathname || "/").replace(/\/$/, "") || "/";
    if (p === "/aseel-kit") setAppView("aseel-kit");
    else if (p === "/aseel-sales") setAppView("aseel-sales");
  }, [location.pathname]);

  // مسارات الصفقات + ?view= القديم؛ لا نفرض شاشة الدور عند كل زيارة لـ /
  useEffect(() => {
    if (!currentUser?.isApproved) return;
    const params = new URLSearchParams(location.search);
    const idLegacy = params.get("id");
    const viewParam = params.get("view") as AppView | null;
    if (viewParam === "deals-management" && idLegacy) {
      navigate(`/deals/${encodeURIComponent(idLegacy)}`, { replace: true });
      return;
    }
    const path = (location.pathname || "/").replace(/\/$/, "") || "/";
    /** روابط قديمة على الرئيسية: ?view=purchase-invoices&id= → مسار مخصص */
    if (path === "/" && viewParam === "purchase-invoices") {
      if (idLegacy) {
        navigate(`/purchase-invoices/${encodeURIComponent(idLegacy)}`, { replace: true });
      } else {
        navigate("/purchase-invoices", { replace: true });
      }
      return;
    }
    if (path === "/deals" || path.startsWith("/deals/")) {
      setAppView("deals-management");
      return;
    }
    if (path === "/shipments" || path.startsWith("/shipments/")) {
      // task6.1 G-5: legacy /shipments/<id> bookmarks → import-flow editor.
      // List page (/shipments) keeps showing ShipmentManagement.
      const m = path.match(/^\/shipments\/(.+)$/);
      const seg = m ? decodeURIComponent(m[1]) : "";
      if (seg) {
        navigate(`/import-flow/${encodeURIComponent(seg)}`, { replace: true });
        return;
      }
      setAppView("shipments-management");
      return;
    }
    if (path.startsWith("/import-flow/")) {
      setAppView("import-flow");
      return;
    }
    if (path === "/purchase-invoices" || path.startsWith("/purchase-invoices/")) {
      setAppView("purchase-invoices");
      return;
    }
    // task16 A8: قائمة فواتير المبيعات وتفصيل فاتورة واحدة مساران مستقلان.
    // المحرر يُفتح داخل SalesInvoicesPage حسب الـ id في المسار.
    if (path === "/sales/invoices" || path.startsWith("/sales/invoices/")) {
      setAppView("sales-invoices");
      return;
    }
    const journalMatch = path.match(/^\/accounting\/journals\/(.+)$/);
    if (journalMatch) {
      const seg = journalMatch[1];
      if (seg === "new") {
        setAccountingJournalId(null);
        setAccountingJournalDealRef(null);
      } else {
        const jid = parseInt(seg, 10);
        if (!isNaN(jid)) setAccountingJournalId(jid);
      }
      setAppView("accounting-journal-entry");
      return;
    }
    // task14 M1: بقية الصفحات — مطابقة مباشرة من جدول المسارات
    const mappedView = PATH_TO_VIEW[path];
    if (mappedView) {
      setAppView(mappedView);
      return;
    }
    if (viewParam) {
      setAppView(viewParam);
    }
  }, [currentUser, location.pathname, location.search, navigate]);

  useEffect(() => {
    if (!currentUser?.isApproved) return;
    const path = (location.pathname || "/").replace(/\/$/, "") || "/";
    if (path !== "/") return;
    const params = new URLSearchParams(location.search);
    if (params.get("view")) return;
    const roleDefault: AppView =
      currentUser.role === "manager" ? "dashboard" : "tasks";
    setAppView(roleDefault);
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

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'PROCESS_MUTATIONS') {
        processMutationQueue().catch(() => {});
      }
    };
    navigator.serviceWorker?.addEventListener('message', handler);
    return () => navigator.serviceWorker?.removeEventListener('message', handler);
  }, []);

  useEffect(() => {
    setStatusMsg({
      message: onlineStatus.online ? 'عودة الاتصال — جارٍ مزامنة العمليات المعلقة' : 'أنت الآن بدون اتصال — الأعمال ستُحفظ محلياً',
      type: onlineStatus.online ? 'info' : 'warn',
    });
    if (onlineStatus.online) {
      processMutationQueue().catch(() => {});
    }
    const t = setTimeout(() => setStatusMsg(null), 5000);
    return () => clearTimeout(t);
  }, [onlineStatus.online]);

  /** تذكيرات وصول الشحنات (≤ 3 أيام) — إشعار Firestore، تكرار محكوم بـ localStorage */
  useEffect(() => {
    if (!currentUser?.isApproved) return;
    if (currentUser.role !== "manager" && currentUser.role !== "procurement") return;
    const run = () => {
      void import("./services/shipmentArrivalReminders").then((m) =>
        m.runShipmentArrivalReminders(currentUser.id)
      );
    };
    run();
    const t = window.setInterval(run, 6 * 60 * 60 * 1000);
    return () => window.clearInterval(t);
  }, [currentUser?.id, currentUser?.isApproved, currentUser?.role]);

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
      // console suppressed
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
      // console suppressed
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
      // console suppressed
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
      // console suppressed
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
        if (currentUser!.role === "manager" || currentUser!.role === "procurement") {
          return <TradeDashboard userName={currentUser!.name} onNavigate={setViewAndSyncPath} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

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
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }

      case "users":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return (
          <UserManagement
            users={users}
            onUpdateUser={handleUpdateUser}
            onDeleteUser={handleDeleteUser}
          />
        );

      case "reports":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return <Reports tasks={tasks} users={users} />;

      case "employee-notes":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return <EmployeeNotes users={users} onSaveNotes={handleSaveNotes} />;

      case "points-history":
        return <PointsHistoryPage user={currentUser} />;

      case "points-management":
        if (currentUser!.role !== "manager")
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return <EmployeePointsManagement users={users} />;

      case "settings":
        return <SettingsPage user={currentUser!} />;

      case "attendance":
        if (currentUser!.role === "manager") {
          return <AttendanceManagement users={users} currentUser={currentUser!} />;
        }
        return <EmployeeAttendance currentUser={currentUser!} />;

      case "sales-invoices":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return (
            <SalesInvoicesPage
              onOpenGeneralLedger={(id) => {
                setAccountingGlAccountId(id);
                setAppView("accounting-general-ledger");
              }}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sales-customer-payments":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <SalesCustomerPaymentsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sales-settings":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <SalesSettingsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sales-customers":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <SalesCustomersPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "purchase-invoices":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <PurchaseInvoice currentUser={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      // ---------- New Case Added Here ----------
      case "old-invoices":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <OldPurchaseInvoice />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "price-offers":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <PriceOfferManagement />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "deals-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return (
            <DealManagement
              currentUser={currentUser!}
              onOpenAccountingJournal={(journalId, dealRef) => {
                setAccountingJournalRelatedKind("deal");
                setAccountingJournalId(journalId);
                setAccountingJournalDealRef(dealRef ?? null);
                setAccountingJournalBackView("deals-management");
                if (journalId != null) {
                  setViewAndSyncPath("accounting-journal-entry", String(journalId));
                } else {
                  setViewAndSyncPath("accounting-journal-entry");
                }
              }}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
      // -----------------------------------------

      case "items-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <ItemsManagement user={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "supplier-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return (
            <SupplierManagement
              initialPartnerId={accountingSupplierPartnerId}
              onInitialPartnerConsumed={() => setAccountingSupplierPartnerId(null)}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "shipments-management":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return (
            <ShipmentManagement
              currentUser={currentUser!}
              onOpenAccountingJournal={(journalId, dealRef) => {
                setAccountingJournalRelatedKind("shipment");
                setAccountingJournalId(journalId);
                setAccountingJournalDealRef(dealRef ?? null);
                setAccountingJournalBackView("shipments-management");
                if (journalId != null) {
                  setViewAndSyncPath("accounting-journal-entry", String(journalId));
                } else {
                  setViewAndSyncPath("accounting-journal-entry");
                }
              }}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "import-flow": {
        const m = location.pathname.match(/^\/import-flow\/(.+)$/);
        const shipmentId = m ? m[1] : null;
        return (
          <ImportDocumentScreen
            shipmentId={shipmentId}
            onClose={() => setViewAndSyncPath("shipments-management")}
          />
        );
      }

      case "customs-clearance":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <CustomsClearanceManagement currentUser={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "local-shipping":
        if (
          currentUser!.role === "procurement" ||
          currentUser!.role === "manager"
        ) {
          return <LocalShippingPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

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
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "cash-box-details":
        if (currentUser!.role === "manager" && selectedCashBox) {
          return (
            <CashBoxStatement
              cashBox={selectedCashBox}
              onBack={() => setAppView("cash-boxes")}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "gallery":
        return <PublicGallery />;

      case "accounting-coa":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return (
          <AccountingCoaPage
            onOpenGeneralLedger={(id) => {
              setAccountingGlAccountId(id);
              setAppView("accounting-general-ledger");
            }}
            onOpenSupplier={(partnerId) => {
              setAccountingSupplierPartnerId(partnerId);
              setAppView("supplier-management");
            }}
          />
        );

      case "accounting-journals":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return (
          <AccountingJournalListPage
            onNew={() => {
              setAccountingJournalRelatedKind(null);
              setAccountingJournalBackView("accounting-journals");
              setAccountingJournalId(null);
              setAccountingJournalDealRef(null);
              setViewAndSyncPath("accounting-journal-entry");
            }}
            onOpen={(id, dealRefNumber, referenceSummary) => {
              setAccountingJournalRelatedKind(null);
              setAccountingJournalBackView("accounting-journals");
              setAccountingJournalId(id);
              if (dealRefNumber) {
                setAccountingJournalDealRef({
                  dealId: "",
                  dealNumber: dealRefNumber,
                  displayName: referenceSummary || dealRefNumber,
                });
              } else {
                setAccountingJournalDealRef(null);
              }
              setViewAndSyncPath("accounting-journal-entry", String(id));
            }}
            onNavigateToDeal={(dealRefNumber) => {
              navigate(`/deals?ref=${encodeURIComponent(dealRefNumber)}`);
              setAppView("deals-management");
            }}
          />
        );

      case "accounting-journal-entry":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return (
          <AccountingJournalEntryPage
            journalId={accountingJournalId}
            dealRef={accountingJournalDealRef}
            relatedKind={accountingJournalRelatedKind}
            onNavigateToShipment={(shipmentId) => {
              setAccountingJournalDealRef(null);
              setAccountingJournalRelatedKind(null);
              setAccountingJournalId(null);
              navigate(`/shipments/${encodeURIComponent(shipmentId)}`);
              setAppView("shipments-management");
            }}
            onNavigateToDeal={(dealIdOrRef) => {
              setAccountingJournalDealRef(null);
              setAccountingJournalRelatedKind(null);
              setAccountingJournalId(null);
              if (dealIdOrRef && dealIdOrRef.startsWith("D-")) {
                navigate(`/deals?ref=${encodeURIComponent(dealIdOrRef)}`);
                setAppView("deals-management");
              } else {
                setViewAndSyncPath("deals-management", dealIdOrRef);
              }
            }}
            onBack={() => {
              setAccountingJournalDealRef(null);
              setAccountingJournalRelatedKind(null);
              const backPath = accountingJournalBackView === "deals-management"
                ? "/deals"
                : accountingJournalBackView === "shipments-management"
                  ? "/shipments"
                : "/accounting/journals";
              navigate(backPath);
              setAppView(accountingJournalBackView);
            }}
          />
        );

      case "accounting-cheques":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <AccountingChequesPage />;

      case "accounting-general-ledger":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return (
          <AccountingGeneralLedgerPage
            initialAccountId={accountingGlAccountId}
            onInitialAccountConsumed={() => setAccountingGlAccountId(null)}
          />
        );

      case "accounting-trial-balance":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <AccountingTrialBalancePage />;

      case "accounting-vat-report":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <AccountingVatReportPage />;

      case "accounting-landed-cost":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <AccountingLandedCostPage />;

      case "accounting-fiscal-periods":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <FiscalPeriodsPage />;

      case "accounting-exchange-rates":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <ExchangeRatesPage />;

      case "accounting-balance-sheet":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <BalanceSheetPage />;

      case "accounting-income-statement":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <IncomeStatementPage />;

      case "accounting-vat-statements":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <VatStatementsPage />;

      case "accounting-year-end-close":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <YearEndClosePage />;

      case "stock-levels":
        return <StockLevelsPage />;

      case "stock-movements":
        return <StockMovementsPage />;

      case "inventory-valuation":
        return <InventoryValuationPage />;

      case "property-rental":
        if (currentUser!.role === "manager" || currentUser!.role === "procurement") {
          return <PropertyRentalPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sql-products":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <SqlProductsPage />;

      case "sql-partners":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <SqlPartnersPage />;

      case "sql-deals":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <SqlDealsPage />;

      case "sql-shipments":
        if (currentUser!.role !== "manager" && currentUser!.role !== "procurement") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <SqlShipmentsPage />;

      case "smart-assistant":
        return <SmartAssistantPage />;

      case "aseel-kit":
        return <AseelKitStory />;

      case "aseel-sales":
        return <SalesInvoiceAseelStory />;

      case "sales-quotations":
        return <SalesQuotationsPage />;

      case "credit-debit-notes":
        return <CreditDebitNotesPage />;

      case "sales-return":
        return <SalesReturnEditor onBack={() => setAppView("sales-invoices")} />;

      case "purchase-return":
        return <PurchaseReturnEditor onBack={() => setAppView("purchase-invoices")} />;

      case "supplier-payments":
        return <SupplierPaymentsPage />;

      default:
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
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

  // Dev kit — no auth required
  if (appView === "aseel-kit") {
    return <AseelKitStory />;
  }
  if (appView === "aseel-sales") {
    return <SalesInvoiceAseelStory />;
  }

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
    <div dir="rtl">
      <AppLayout user={currentUser} activeView={appView} onNavigate={setViewAndSyncPath} onOpenGroupConstants={() => setGroupConstantsOpen(true)}>
        <div className="fixed top-3 left-3 z-50">
          <PendingMutationsPanel />
        </div>
        <OfflineBanner status={onlineStatus} onRetry={() => window.location.reload()} />
        <NoSqlMigrationBanner isManager={currentUser?.role === "manager"} />
        <main className="p-3 sm:p-4 lg:p-6">
          {renderMainContent()}
        </main>
      </AppLayout>

      {/* N0-T5: F11 modal portal لثوابت المجموعة */}
      {groupConstantsOpen && (
        <div className="fixed inset-0 z-[9999] bg-black/50 flex items-center justify-center p-4" onClick={() => setGroupConstantsOpen(false)}>
          <div className="w-full max-w-6xl h-[90vh] bg-white rounded-lg shadow-xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <GroupConstantsPage
              currentUserName={currentUser?.name}
              onClose={() => setGroupConstantsOpen(false)}
            />
          </div>
        </div>
      )}

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
      <UpdatePrompt />
      <OfflineCoachmark />
      <StorageQuotaGuard />
      {statusMsg && <StatusMessage message={statusMsg.message} type={statusMsg.type} />}
      {syncConflict && (
        <SyncConflictModal
          modelName={syncConflict.payload.endpoint}
          localData={syncConflict.payload.localBody}
          serverData={syncConflict.payload.serverBody}
          onResolve={(r) => { syncConflict.resolve(r); setSyncConflict(null); }}
        />
      )}
    </div>
  );
};

export default App;