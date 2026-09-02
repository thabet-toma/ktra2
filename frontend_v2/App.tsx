import React, { useState, useEffect, useRef, useCallback } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import { LoadingSpinner } from "./components/LoadingSpinner";
import { ErrorDisplay } from "./components/ErrorDisplay";
import {
  Product,
  SearchQuery,
  User,
  Task,
  TaskStatus,
  ActivityLog,
  Submission,
  Category,
  CashBox,
  AppView,
} from "./types";
import { useOnlineStatus } from "./hooks/useOnlineStatus";
import { useDocumentTitle } from "./hooks/useDocumentTitle";
import { useAutoConnectionRecovery } from "./hooks/useAutoConnectionRecovery";
import OfflineBanner from "./components/offline/OfflineBanner";
import UpdatePrompt from "./components/offline/UpdatePrompt";
import PendingMutationsPanel from "./components/offline/PendingMutationsPanel";
import OfflineCoachmark from "./components/offline/OfflineCoachmark";
import DidYouKnow from "./components/ui/DidYouKnow";
import StatusMessage from "./components/offline/StatusMessage";
import { processMutationQueue, registerConflictListener, type ConflictPayload, type ConflictResolution } from "./services/offline/cachedApi";
import StorageQuotaGuard from "./components/offline/StorageQuotaGuard";
import { IdleTimeoutGuard } from "./components/IdleTimeoutGuard";
import SyncConflictModal from "./components/offline/SyncConflictModal";
import { useBroadcastSync } from "./hooks/useBroadcastSync";
import { cleanOldCache } from "./services/offline/cacheCleaner";
// P2-8: `firestoreService` (2,600+ سطر — منطق المشتريات القديم كله) كان
// مستورَداً ثابتاً هنا فيدخل حزمة الإقلاع رغم أن الشل لا يستعمل منه إلا
// المهام والمستخدمين. الاستيراد الديناميكي ينقله إلى chunk مستقل يُحمَّل عند
// أول استعمال، والوعد محفوظ كي لا يتكرّر الطلب.
type LegacyDataModule = typeof import("./services/firestoreService");
let legacyDataPromise: Promise<LegacyDataModule> | null = null;
const legacyData = (): Promise<LegacyDataModule> =>
  (legacyDataPromise ??= import("./services/firestoreService"));
import { fetchUserProfile, logoutUser } from "./services/authService";
import { useAuth } from "./contexts/AuthContext";
import { useCompany } from "./contexts/CompanyContext";
import { usePermissions } from "./contexts/PermissionsContext";
import { moduleAllowsView, permForView, templateHidesView } from "./utils/viewPermissions";
import { companyWorkspaceDeepLink, enterPlatformShell, platformShellActive } from "./utils/officeShell";
import { resolvePublicAuthView } from "./utils/publicAuthRoutes";
import { activeTasksService } from "./services/activeTasksService";
import { autoDisableScheduler } from "./services/autoDisableScheduler";
import { PublicNavbar } from "./components/layout/PublicNavbar";
import { useLocation, useNavigate } from "react-router-dom";
import { apiGetObject } from "./services/restApi";
import { clientLogger } from "./services/logger";
import { useToast } from "./contexts/ToastContext";
import { humanizeThrown } from "./utils/drfError";

// ── تقسيم الحزمة حسب الشاشة (صيانة الأداء 2026-07) ─────────────────────────
// كانت كل الصفحات (~85 مكوّناً) مستورَدة ثابتاً ⇒ حزمة واحدة 3.2MB تحجب أول
// رسم. الآن كل صفحة chunk مستقل يُحمَّل عند فتحها فقط (renderMainContent محاط
// بـ <Suspense>). نمط الـ adapter (.then م → default) لأن الصفحات named exports —
// بلا لمس أي ملف مكوّن. الشل الدائم (الدخول/التخطيط/شريط الاتصال…) يبقى ثابتاً.
const lazyPage = <T extends React.ComponentType<any>>(
  loader: () => Promise<{ default: T }>
) => React.lazy(loader);

const SearchForm = lazyPage(() => import("./components/SearchForm").then((m) => ({ default: m.SearchForm })));
const ResultsPage = lazyPage(() => import("./components/ResultsPage").then((m) => ({ default: m.ResultsPage })));
const LoginPage = lazyPage(() => import("./components/LoginPage").then((m) => ({ default: m.LoginPage })));
const LandingPage = lazyPage(() => import("./components/LandingPage").then((m) => ({ default: m.LandingPage })));
const SignupPage = lazyPage(() => import("./components/SignupPage").then((m) => ({ default: m.SignupPage })));
const TaskList = lazyPage(() => import("./components/TaskList").then((m) => ({ default: m.TaskList })));
const RejectReasonModal = lazyPage(() => import("./components/modals/RejectReasonModal").then((m) => ({ default: m.RejectReasonModal })));
const TaskDetailsModal = lazyPage(() => import("./components/TaskDetailsModal").then((m) => ({ default: m.TaskDetailsModal })));
const GroupConstantsPage = lazyPage(() => import("./components/settings/GroupConstantsPage").then((m) => ({ default: m.GroupConstantsPage })));
const Dashboard = lazyPage(() => import("./components/Dashboard").then((m) => ({ default: m.Dashboard })));
const TradeDashboard = lazyPage(() => import("./components/dashboard/TradeDashboard").then((m) => ({ default: m.TradeDashboard })));
const SuperAdminDashboard = lazyPage(() => import("./components/superadmin/SuperAdminDashboard").then((m) => ({ default: m.SuperAdminDashboard })));
const DevelopmentNotesPage = lazyPage(() => import("./components/superadmin/DevelopmentNotesPage").then((m) => ({ default: m.DevelopmentNotesPage })));
const TaskManagement = lazyPage(() => import("./components/TaskManagement").then((m) => ({ default: m.TaskManagement })));
const UserManagement = lazyPage(() => import("./components/UserManagement").then((m) => ({ default: m.UserManagement })));
const ActivityLogPage = lazyPage(() => import("./components/ActivityLogPage").then((m) => ({ default: m.ActivityLogPage })));
const Reports = lazyPage(() => import("./components/Reports").then((m) => ({ default: m.Reports })));
// T-REPORTS: قسم التقارير — فهرس واحد وشاشة تشغيل عامّة لكل تقارير المنصة.
const ReportsHubPage = lazyPage(() => import("./components/reports/ReportsHubPage").then((m) => ({ default: m.ReportsHubPage })));
const ReportRunnerPage = lazyPage(() => import("./components/reports/ReportRunnerPage").then((m) => ({ default: m.ReportRunnerPage })));
const EmployeeNotes = lazyPage(() => import("./components/EmployeeNotes").then((m) => ({ default: m.EmployeeNotes })));
const SettingsPage = lazyPage(() => import("./components/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const PointsHistoryPage = lazyPage(() => import("./components/PointsHistoryPage").then((m) => ({ default: m.PointsHistoryPage })));
const EmployeePointsManagement = lazyPage(() => import("./components/EmployeePointsManagement").then((m) => ({ default: m.EmployeePointsManagement })));
const PriceOfferManagement = lazyPage(() => import("./components/procurement/PriceOfferManagement").then((m) => ({ default: m.PriceOfferManagement })));
const DealManagement = lazyPage(() => import("./components/procurement/DealManagement").then((m) => ({ default: m.DealManagement })));
const ItemsManagement = lazyPage(() => import("./components/items/ItemsManagement").then((m) => ({ default: m.ItemsManagement })));
const SupplierManagement = lazyPage(() => import("./components/suppliers/SupplierManagement").then((m) => ({ default: m.SupplierManagement })));
const ShipmentManagement = lazyPage(() => import("./components/procurement/shipments/ShipmentManagement").then((m) => ({ default: m.ShipmentManagement })));
const KitStory = lazyPage(() => import("./components/kit/KitStory").then((m) => ({ default: m.KitStory })));
const SalesInvoiceKitStory = lazyPage(() => import("./components/sales/SalesInvoiceKitStory").then((m) => ({ default: m.SalesInvoiceKitStory })));
const SalesDocumentsPage = lazyPage(() => import("./components/sales/SalesQuotationsPage").then((m) => ({ default: m.SalesDocumentsPage })));
const CreditDebitNotesPage = lazyPage(() => import("./components/sales/CreditDebitNotesPage").then((m) => ({ default: m.CreditDebitNotesPage })));
const SalesReturnEditor = lazyPage(() => import("./components/sales/SalesReturnEditor").then((m) => ({ default: m.SalesReturnEditor })));
const PurchaseReturnEditor = lazyPage(() => import("./components/sales/PurchaseReturnEditor").then((m) => ({ default: m.PurchaseReturnEditor })));
const SupplierPaymentsPage = lazyPage(() => import("./components/sales/SupplierPaymentsPage").then((m) => ({ default: m.SupplierPaymentsPage })));
const ImportDocumentScreen = lazyPage(() => import("./components/import-flow").then((m) => ({ default: m.ImportDocumentScreen })));
const EmployeeAttendance = lazyPage(() => import("./components/EmployeeAttendance").then((m) => ({ default: m.EmployeeAttendance })));
const AttendanceManagement = lazyPage(() => import("./components/AttendanceManagement").then((m) => ({ default: m.AttendanceManagement })));
const PurchaseInvoice = lazyPage(() => import("./components/procurement/PurchaseInvoice").then((m) => ({ default: m.PurchaseInvoice })));
const AboutUs = lazyPage(() => import("./components/AboutUs"));
const Contact = lazyPage(() => import("./components/pages/Contact"));
const PublicGallery = lazyPage(() => import("./components/PublicGallery"));
const OldPurchaseInvoice = lazyPage(() => import("./components/OldPurchaseInvoice").then((m) => ({ default: m.OldPurchaseInvoice })));
const CashBoxList = lazyPage(() => import("./components/finance/CashBoxList").then((m) => ({ default: m.CashBoxList })));
const CashBoxStatement = lazyPage(() => import("./components/finance/CashBoxStatement").then((m) => ({ default: m.CashBoxStatement })));
const AccountingCoaPage = lazyPage(() => import("./components/accounting/AccountingCoaPage").then((m) => ({ default: m.AccountingCoaPage })));
const AccountingJournalListPage = lazyPage(() => import("./components/accounting/AccountingJournalListPage").then((m) => ({ default: m.AccountingJournalListPage })));
const AccountingJournalEntryPage = lazyPage(() => import("./components/accounting/AccountingJournalEntryPage").then((m) => ({ default: m.AccountingJournalEntryPage })));
const AccountingChequesPage = lazyPage(() => import("./components/accounting/AccountingChequesPage").then((m) => ({ default: m.AccountingChequesPage })));
const ExpenseVouchersPage = lazyPage(() => import("./components/accounting/ExpenseVouchersPage").then((m) => ({ default: m.ExpenseVouchersPage })));
const ClientBooksPanel = lazyPage(() => import("./components/office/ClientBooksPanel").then((m) => ({ default: m.ClientBooksPanel })));
const BanksPage = lazyPage(() => import("./components/accounting/BanksPage").then((m) => ({ default: m.BanksPage })));
const BankReconciliationPage = lazyPage(() => import("./components/accounting/BankReconciliationPage").then((m) => ({ default: m.BankReconciliationPage })));
const AccountingGeneralLedgerPage = lazyPage(() => import("./components/accounting/AccountingGeneralLedgerPage").then((m) => ({ default: m.AccountingGeneralLedgerPage })));
const AccountingTrialBalancePage = lazyPage(() => import("./components/accounting/AccountingTrialBalancePage").then((m) => ({ default: m.AccountingTrialBalancePage })));
const AccountingVatReportPage = lazyPage(() => import("./components/accounting/AccountingVatReportPage").then((m) => ({ default: m.AccountingVatReportPage })));
const AccountingLandedCostPage = lazyPage(() => import("./components/accounting/AccountingLandedCostPage").then((m) => ({ default: m.AccountingLandedCostPage })));
const FiscalPeriodsPage = lazyPage(() => import("./components/accounting/FiscalPeriodsPage").then((m) => ({ default: m.FiscalPeriodsPage })));
const ExchangeRatesPage = lazyPage(() => import("./components/accounting/ExchangeRatesPage").then((m) => ({ default: m.ExchangeRatesPage })));
const BalanceSheetPage = lazyPage(() => import("./components/accounting/BalanceSheetPage").then((m) => ({ default: m.BalanceSheetPage })));
const IncomeStatementPage = lazyPage(() => import("./components/accounting/IncomeStatementPage").then((m) => ({ default: m.IncomeStatementPage })));
const InvoiceProfitsPage = lazyPage(() => import("./components/accounting/InvoiceProfitsPage").then((m) => ({ default: m.InvoiceProfitsPage })));
const ReservedStockReportPage = lazyPage(() => import("./components/sales/ReservedStockReportPage").then((m) => ({ default: m.ReservedStockReportPage })));
const VatStatementsPage = lazyPage(() => import("./components/accounting/VatStatementsPage").then((m) => ({ default: m.VatStatementsPage })));
const YearEndClosePage = lazyPage(() => import("./components/accounting/YearEndClosePage").then((m) => ({ default: m.YearEndClosePage })));
const OpeningBalancesPage = lazyPage(() => import("./components/accounting/OpeningBalancesPage").then((m) => ({ default: m.OpeningBalancesPage })));
const SqlProductsPage = lazyPage(() => import("./components/sql/SqlProductsPage").then((m) => ({ default: m.SqlProductsPage })));
const SqlPartnersPage = lazyPage(() => import("./components/sql/SqlPartnersPage").then((m) => ({ default: m.SqlPartnersPage })));
const SqlDealsPage = lazyPage(() => import("./components/sql/SqlDealsPage").then((m) => ({ default: m.SqlDealsPage })));
const SqlShipmentsPage = lazyPage(() => import("./components/sql/SqlShipmentsPage").then((m) => ({ default: m.SqlShipmentsPage })));
const SmartAssistantPage = lazyPage(() => import("./components/SmartAssistantPage").then((m) => ({ default: m.SmartAssistantPage })));
const CustomsClearanceManagement = lazyPage(() => import("./components/procurement/clearance/CustomsClearanceManagement").then((m) => ({ default: m.CustomsClearanceManagement })));
const StockMovementsPage = lazyPage(() => import("./components/inventory/StockMovementsPage").then((m) => ({ default: m.StockMovementsPage })));
const WarehousesManager = lazyPage(() => import("./components/inventory/WarehousesManager").then((m) => ({ default: m.WarehousesManager })));
const StockLevelsPage = lazyPage(() => import("./components/inventory/StockLevelsPage").then((m) => ({ default: m.StockLevelsPage })));
const WarehouseTransferPage = lazyPage(() => import("./components/inventory/WarehouseTransferPage").then((m) => ({ default: m.WarehouseTransferPage })));
const StocktakePage = lazyPage(() => import("./components/inventory/StocktakePage").then((m) => ({ default: m.StocktakePage })));
const InventoryValuationPage = lazyPage(() => import("./components/inventory/InventoryValuationPage").then((m) => ({ default: m.InventoryValuationPage })));
const ProductCostPage = lazyPage(() => import("./components/inventory/ProductCostPage").then((m) => ({ default: m.ProductCostPage })));
const PropertyRentalPage = lazyPage(() => import("./components/realestate/PropertyRentalPage").then((m) => ({ default: m.PropertyRentalPage })));
const PartnerProfilePage = lazyPage(() => import("./components/partners/PartnerProfilePage").then((m) => ({ default: m.PartnerProfilePage })));
const ProductProfilePage = lazyPage(() => import("./components/items/ProductProfilePage").then((m) => ({ default: m.ProductProfilePage })));
const GroupProfilePage = lazyPage(() => import("./components/items/GroupProfilePage").then((m) => ({ default: m.GroupProfilePage })));
const SalesInvoicesPage = lazyPage(() => import("./components/sales/SalesInvoicesPage").then((m) => ({ default: m.SalesInvoicesPage })));
const SalesCustomersPage = lazyPage(() => import("./components/sales/SalesCustomersPage").then((m) => ({ default: m.SalesCustomersPage })));
const SalesCustomerPaymentsPage = lazyPage(() => import("./components/sales/SalesCustomerPaymentsPage"));
const SalesSettingsPage = lazyPage(() => import("./components/sales/SalesSettingsPage"));
// T-PERM: شاشة الصلاحيات (مصفوفة دور × صلاحية) — مدير الشركة فقط.
const PermissionsPage = lazyPage(() => import("./components/settings/PermissionsPage"));
// ST-3: «متجري» — فتح المتجر العام واختيار رابطه وتحديد ما يُعرض فيه.
const StoreSettingsPage = lazyPage(() => import("./components/settings/StoreSettingsPage"));
const PurchaseSettingsPage = lazyPage(() => import("./components/procurement/PurchaseSettingsPage"));
const GoodsReceiptsPage = lazyPage(() => import("./components/procurement/receipts/GoodsReceiptsPage"));
const DeliveryNotesPage = lazyPage(() => import("./components/sales/DeliveryNotesPage"));
const LocalShippingPage = lazyPage(() => import("./components/logistics/LocalShippingPage"));
// «حسابي» — صفحة المستخدم نفسه (وفيها دفتر مصاريفه الشخصي)، مفتوحة للجميع:
// العزل خادميّ بالمستخدم لا بالشركة، فلا صلاحية شركة تحرسها ولا تُدرَج في قوائمها.
const MyAccountPage = lazyPage(() => import("./components/personal/MyAccountPage"));
// الرواتب — موظفون وساعات وغيابات وكشوف، مرتبطة بشجرة الحسابات.
const PayrollPage = lazyPage(() => import("./components/hr/PayrollPage"));
const CompanyAccountantEngagementsPage = lazyPage(() => import("./components/accountant/CompanyAccountantEngagementsPage"));
const AccountantOfficeApp = lazyPage(() => import("./components/accountant/office/AccountantOfficeApp"));
// THA-45: سجل الأجهزة الحساسة — وحدة مرخّصة، خلف نفس حارس الترخيص.
const SensitiveDevicesScreen = lazyPage(() => import("./components/devices/SensitiveDevicesScreen"));
// THA-24: بطاقات الكفالة — وحدة «خدمة ما بعد البيع» المرخّصة، بنفس الحارس.
const WarrantyCardsScreen = lazyPage(() => import("./components/aftersales/WarrantyCardsScreen"));
const ServiceOrdersScreen = lazyPage(() => import("./components/aftersales/ServiceOrdersScreen"));
// THA-114: شرح مستندات الاستيراد — وحدة «ملف الاستيراد» المرخّصة، بنفس الحارس.
const ImportFileGuideScreen = lazyPage(() => import("./components/import-file/ImportFileGuideScreen").then((m) => ({ default: m.ImportFileGuideScreen })));
// T-HR: الهيكل التنظيمي — وحدة «الموارد البشرية» المرخّصة، بنفس الحارس.
const OrgStructurePage = lazyPage(() => import("./components/hr/OrgStructurePage").then((m) => ({ default: m.OrgStructurePage })));
const HrAttendancePage = lazyPage(() => import("./components/hr/AttendancePage").then((m) => ({ default: m.AttendancePage })));
const HrCheckInPage = lazyPage(() => import("./components/hr/CheckInPage").then((m) => ({ default: m.CheckInPage })));
const HrRequestsPage = lazyPage(() => import("./components/hr/RequestsPage").then((m) => ({ default: m.RequestsPage })));
const HrContractsPage = lazyPage(() => import("./components/hr/ContractsPage").then((m) => ({ default: m.ContractsPage })));

type SourcingView = "search" | "loading" | "results";
type AuthView = "landing" | "login" | "signup";

/**
 * حارس ترخيص الوحدة — يقرأ عَلَم `/api/permissions/me` (طلب قائم أصلاً، بلا شبكة
 * إضافية) ويفشل **مغلقاً**. يسبق عرض الشاشة الكسولة، فلا يُطلب chunk الوحدة
 * أصلاً للشركة غير المرخّصة.
 *
 * THA-45: صار عاماً لكل الوحدات المرخّصة (كان خاصاً ببوابة المحاسب) — الرسالة
 * وحدها تتغيّر، فحارسٌ باسم وحدةٍ بعينها يلفّ شاشةَ وحدةٍ أخرى نصٌّ يكذب.
 */
const ModuleLicenseGuard: React.FC<{ view: string; message: string; children: React.ReactNode }> = ({ view, message, children }) => {
  const { modules, loading } = usePermissions();

  if (loading) return <div className="flex justify-center py-16"><LoadingSpinner /></div>;
  if (!moduleAllowsView(view, modules)) {
    return <div role="alert" className="mx-auto max-w-xl rounded-2xl border border-amber-300 bg-amber-50 p-8 text-center font-bold text-amber-900">{message}</div>;
  }
  return <>{children}</>;
};

/**
 * task14 M1 (DEF-B1): جدول مسار↔شاشة واحد — مصدر الحقيقة للاتجاهين.
 * كل صفحة أساسية (الشريط الجانبي) لها URL فريد قابل للحفظ والمشاركة؛
 * المسارات ذات المعرّف (deals/:id، accounting/journals/:id، import-flow/:id،
 * purchase-invoices/:id، shipments/:id) تبقى حالات خاصة في setViewAndSyncPath
 * وتأثير التحليل العكسي أدناه.
 */
const VIEW_PATHS: Partial<Record<AppView, string>> = {
  dashboard: "/dashboard",
  "super-admin": "/super-admin",
  "development-notes": "/super-admin/development-notes",
  tasks: "/tasks",
  "task-management": "/task-management",
  "smart-assistant": "/assistant",
  users: "/users",
  attendance: "/attendance",
  "employee-notes": "/employee-notes",
  "points-management": "/points-management",
  "points-history": "/points-history",
  "my-account": "/my-account",
  payroll: "/payroll",
  "company-accountant-engagements": "/accountant/company/engagements",
  "sensitive-devices": "/sensitive-devices",
  "after-sales": "/after-sales",
  "service-orders": "/after-sales/service-orders",
  "hr-org": "/hr/org",
  "hr-attendance": "/hr/attendance",
  "hr-check-in": "/hr/check-in",
  "hr-requests": "/hr/requests",
  "hr-contracts": "/hr/contracts",
  "sales-invoices": "/sales/invoices",
  "sales-quotations": "/sales/quotations",
  "sales-orders": "/sales/orders",
  "credit-debit-notes": "/sales/credit-debit-notes",
  "sales-return": "/sales/returns",
  "purchase-return": "/purchase-returns",
  "sales-customer-payments": "/sales/customer-payments",
  "supplier-payments": "/supplier-payments",
  "invoice-profits": "/sales/profits",
  "reserved-stock": "/sales/reserved-stock",
  "sales-customers": "/sales/customers",
  "sales-settings": "/sales/settings",
  "permissions": "/permissions",
  "purchase-settings": "/purchase-settings",
  "purchase-receipts": "/purchase-receipts",
  "sales-delivery-notes": "/sales/delivery-notes",
  "purchase-invoices": "/purchase-invoices",
  "international-invoices": "/international-invoices",
  "old-invoices": "/old-invoices",
  "price-offers": "/price-offers",
  "import-offers": "/import-offers",
  "deals-management": "/deals",
  "items-management": "/items",
  "items-categories": "/items/categories",
  "supplier-management": "/suppliers",
  "sql-partners": "/partners-directory",
  "import-flow": "/import-flow",
  // THA-114: شرح المستندات — يُفتح في تبويب جديد من لوحة ملف الاستيراد.
  "import-file-guide": "/import-file/guide",
  "shipments-management": "/shipments",
  "customs-clearance": "/clearance",
  "local-shipping": "/local-shipping",
  "stock-levels": "/stock-levels",
  "stock-movements": "/stock-movements",
  "warehouses": "/warehouses",
  "warehouse-transfer": "/warehouse-transfer",
  "stocktake": "/stocktake",
  "product-cost": "/product-cost",
  "product-group": "/product-group",
  "accounting-coa": "/accounting/coa",
  "accounting-journals": "/accounting/journals",
  "accounting-cheques": "/accounting/cheques",
  "accounting-banks": "/accounting/banks",
  "accounting-bank-reconciliation": "/accounting/bank-reconciliation",
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
  "accounting-opening-balances": "/accounting/opening-balances",
  "accounting-expense-vouchers": "/accounting/expense-vouchers",
  "client-books": "/client-books",
  "property-rental": "/property-rental",
  "cash-boxes": "/cash-boxes",
  reports: "/reports",
  "team-time-report": "/reports-team",
  gallery: "/gallery",
  "about-us": "/about-us",
  contact: "/contact",
  settings: "/settings",
  sourcing: "/sourcing",
  // `store` ليست شاشة في هذا التطبيق: `/store` وما تحته يُخدَم من `index.tsx`
  // خارج المصادقة كلياً — إبقاؤه هنا كان سيعيد ربط مسارٍ عام بشاشة لا وجود لها.
  // ST-3: «متجري» عكسها — شاشة مصادَق عليها داخل القشرة، ومسارها لا يبدأ بـ
  // `/store/` كي لا يزاحم مسارات المتجر العام في `index.tsx`.
  "store-settings": "/store-settings",
  "group-constants": "/group-constants",
  "ui-kit": "/ui-kit",
  "sales-classic": "/sales-classic",
};

const PATH_TO_VIEW: Record<string, AppView> = Object.fromEntries(
  (Object.entries(VIEW_PATHS) as [AppView, string][]).map(([view, path]) => [path, view])
);

const IMPORT_VIEWS = new Set<AppView>([
  "import-offers",
  "deals-management",
  "shipments-management",
  "customs-clearance",
  "import-flow",
  "international-invoices",
  "sql-deals",
  "sql-shipments",
  "sql-clearances",
]);

const App: React.FC = () => {
  const toast = useToast();
  const location = useLocation();
  const navigate = useNavigate();

  const { currentUser, loading: authLoading, logout, updateUser } = useAuth();
  const { currentCompany, canAccessImport } = useCompany();
  // T-PERM: صلاحيات الشركة النشطة — تُخفي ما لا يملكه المستخدم (الخادم يفرض).
  const { can: canPerm, isManager, modules: licensedModules, template: companyTemplate } = usePermissions();
  const canManagePermissions = canPerm("admin.permissions.manage");
  // T-PERM: حارس الدخول المباشر بالرابط — نفس خريطة الشريط الجانبي، فلا يظهر
  // رابطٌ يقود إلى لوحة التحكم. الشاشة بلا صلاحية في الخريطة مفتوحة للجميع.
  const canView = (view: AppView): boolean => {
    const perm = permForView(String(view));
    return !perm || canPerm(perm);
  };

  const [authView, setAuthView] = useState<AuthView>("landing");
  // سوبر أدمن يخرج من قشرة المكتب للوحة المنصة دون أن يفقد ملفه المهني.
  const [platformShellOverride] = useState(() => {
    if (typeof window === "undefined") return false;
    const path = window.location.pathname;
    // T-EXTACCT: الرابط الصريح لشاشة شركة يحسم القشرة — كان فتح «فاتورة مبيعات
    // جديدة» يعرض لوحة المكتب لأن نوع الحساب وحده يقرر والمسار لا رأي له.
    if (companyWorkspaceDeepLink(path, Object.values(VIEW_PATHS))) {
      clientLogger.info("accountant.shell_switched", { to: "platform", reason: "deep_link", path });
      return true;
    }
    return platformShellActive(path);
  });
  const [users, setUsers] = useState<User[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  const [categories, setCategories] = useState<Category[]>([]);

  const [userTaskTime, setUserTaskTime] = useState(0);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [appView, setAppView] = useState<AppView>("dashboard");

  useEffect(() => {
    if (currentUser) return;
    const resolved = resolvePublicAuthView(location.pathname || "/");
    if (resolved) setAuthView(resolved);
  }, [currentUser, location.pathname]);

  // SEO: عنوان تبويب/فهرسة مختلف لكل شاشة عامة (غير مصادَق عليها) — index.html
  // يحمل عنواناً افتراضياً واحداً لكل الموقع، وهذا يُخصّصه لكل صفحة يزورها زائر
  // غير مسجَّل قبل تنفيذ React (Google يُفهرس ما بعد تنفيذ JS فيقرأ هذا).
  useDocumentTitle(
    currentUser
      ? "K.T.R.A"
      : appView === "about-us"
      ? "من نحن — نظام K.T.R.A لإدارة الاستيراد والمبيعات والمخزون والمحاسبة"
      : appView === "contact"
      ? "تواصل معنا — نظام K.T.R.A"
      : appView === "gallery"
      ? "معرض الصور — نظام K.T.R.A"
      : authView === "login"
      ? "تسجيل الدخول — نظام K.T.R.A"
      : authView === "signup"
      ? "إنشاء حساب جديد — نظام K.T.R.A"
      : "K.T.R.A — نظام متكامل لإدارة الاستيراد والمبيعات والمخزون والمحاسبة"
  );

  /** مزامنة المسار مع الـ URL لكل شاشة مدعومة */
  const setViewAndSyncPath = useCallback(
    (view: AppView, targetId?: string) => {
      if (IMPORT_VIEWS.has(view) && !canAccessImport) {
        navigate("/dashboard", { replace: true });
        setAppView("dashboard");
        return;
      }
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
      } else if (view === "partner-profile") {
        navigate(targetId ? `/partners/${encodeURIComponent(targetId)}` : "/partners", { replace: false });
      } else if (view === "product-profile") {
        navigate(targetId ? `/products/${encodeURIComponent(targetId)}` : "/products", { replace: false });
      } else if (view === "sales-invoices") {
        // task18 DEF-A2: السماح بفتح فاتورة مبيعات جديدة/محدّدة عبر onNavigate
        // (نفس عقد purchase-invoices). الـ targetId="new" → محرر فاتورة جديد.
        if (targetId && targetId !== "list") {
          navigate(`/sales/invoices/${encodeURIComponent(targetId)}`, { replace: false });
        } else {
          navigate("/sales/invoices", { replace: false });
        }
      } else {
        // task14 M1: بقية الشاشات كلها عبر الجدول — URL فريد لكل صفحة
        navigate(VIEW_PATHS[view] ?? "/", { replace: false });
      }
      setAppView(view);
    },
    [canAccessImport, navigate]
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
  const onlineStatus = useOnlineStatus();
  // إصلاح تلقائي للاتصال العالق (إنترنت موجود لكن نبض الخادم يفشل) — مرة لكل نوبة.
  useAutoConnectionRecovery(onlineStatus);
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
      const fetchedCategories = await (await legacyData()).getCategories();
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

  /* شاشتا معاينة للمطوّر/الفحص (dev/QA) — تُكتشف قبل حارس المصادقة لأن لها
     bypass خاص. M7-T4: `aseel-kit`/`aseel-sales` صارتا `ui-kit`/`sales-classic`،
     و**المساران القديمان يبقيان مقبولين**: إعادة تسمية داخلية لا يجوز أن تكسر
     رابطاً محفوظاً في مفضّلة أحدهم. */
  useEffect(() => {
    const p = (location.pathname || "/").replace(/\/$/, "") || "/";
    if (p === "/ui-kit" || p === "/aseel-kit") setAppView("ui-kit");
    else if (p === "/sales-classic" || p === "/aseel-sales") setAppView("sales-classic");
  }, [location.pathname]);

  // مسارات الصفقات + ?view= القديم؛ لا نفرض شاشة الدور عند كل زيارة لـ /
  useEffect(() => {
    const path = (location.pathname || "/").replace(/\/$/, "") || "/";
    // `/store*` لا يصل إلى هنا إطلاقاً: المتجر العام يُوجَّه في `index.tsx`
    // خارج `AuthProvider` كلياً، فلا شاشة متجر داخل هذا التطبيق ولا حالة له.
    if (path.startsWith("/settings")) {
      setAppView("settings");
    } else if (path.startsWith("/about-us")) {
      setAppView("about-us");
    } else if (path.startsWith("/contact")) {
      setAppView("contact");
    } else if (path.startsWith("/gallery") || path.startsWith("/public-gallery")) {
      setAppView("gallery");
    } else if (path.startsWith("/group-constants")) {
      setAppView("group-constants");
    }

    if (path === "/accountant/company/engagements") {
      setAppView("company-accountant-engagements");
      return;
    }

    if (!currentUser?.isApproved) return;
    // الرابط القديم لدفتر المصاريف الشخصي — صار قسماً داخل «حسابي». يبقى عاملاً
    // كي لا تسقط إشارةٌ محفوظة في متصفّح المستخدم على صفحةٍ لا وجود لها.
    if (path === "/personal-expenses") {
      navigate("/my-account", { replace: true });
      return;
    }
    const params = new URLSearchParams(location.search);
    const idLegacy = params.get("id");
    const viewParam = params.get("view") as AppView | null;
    const isImportPath = /^\/(deals|shipments|import-flow|import-offers|clearance)(\/|$)/.test(path);
    if (!canAccessImport && (isImportPath || (viewParam && IMPORT_VIEWS.has(viewParam)))) {
      navigate("/dashboard", { replace: true });
      setAppView("dashboard");
      return;
    }
    if (viewParam === "deals-management" && idLegacy) {
      navigate(`/deals/${encodeURIComponent(idLegacy)}`, { replace: true });
      return;
    }
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
    // إرساليات الشراء/البيع: المسار `/…/new?invoice=` يفتح محرّراً بفاتورة مربوطة.
    if (path === "/purchase-receipts" || path.startsWith("/purchase-receipts/")) {
      setAppView("purchase-receipts");
      return;
    }
    if (path === "/sales/delivery-notes" || path.startsWith("/sales/delivery-notes/")) {
      setAppView("sales-delivery-notes");
      return;
    }
    // task16 A8: قائمة فواتير المبيعات وتفصيل فاتورة واحدة مساران مستقلان.
    // المحرر يُفتح داخل SalesInvoicesPage حسب الـ id في المسار.
    if (path === "/sales/invoices" || path.startsWith("/sales/invoices/")) {
      setAppView("sales-invoices");
      return;
    }
    if (path === "/partners" || path.startsWith("/partners/")) {
      setAppView("partner-profile");
      return;
    }
    if (path.startsWith("/products/")) {
      setAppView("product-profile");
      return;
    }
    // T-REPORTS: /reports فهرس، و/reports/<key> تشغيل تقرير بمفتاحه.
    if (path.startsWith("/reports/")) {
      setAppView("report-runner");
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
      if (
        (mappedView === "super-admin" || mappedView === "development-notes")
        && !currentUser.isSuperAdmin
      ) {
        setAppView("dashboard");
        navigate("/dashboard", { replace: true });
        return;
      }
      setAppView(mappedView);
      return;
    }
    if (viewParam) {
      setAppView(viewParam);
    }
  }, [canAccessImport, currentUser, location.pathname, location.search, navigate]);

  useEffect(() => {
    if (!currentUser?.isApproved) return;
    const path = (location.pathname || "/").replace(/\/$/, "") || "/";
    if (path !== "/") return;
    const params = new URLSearchParams(location.search);
    if (params.get("view")) return;
    const roleDefault: AppView =
      currentUser.isSuperAdmin ? "super-admin"
        : currentUser.role === "manager" ? "dashboard" : "tasks";
    setAppView(roleDefault);
  }, [currentUser]);

  // Data Subscription
  useEffect(() => {
    if (!currentUser) return;
    let active = true;
    let unsubscribeUsers = () => { };
    let unsubscribeTasks = () => { };
    void legacyData().then((m) => {
      if (!active) return;
      if (currentUser.isSuperAdmin) {
        void m.seedUsersIfEmpty();
        unsubscribeUsers = m.subscribeToUsers(true, (fetchedUsers) => {
          if (active) setUsers(fetchedUsers);
        });
      } else if (currentCompany) {
        void m.loadCompanyMemberUsers(currentCompany.TenantID)
          .then((companyUsers) => { if (active) setUsers(companyUsers); })
          .catch(() => { if (active) setUsers([]); });
      } else {
        setUsers([]);
      }
      unsubscribeTasks = m.subscribeToTasks((fetchedTasks) => {
        setTasks(fetchedTasks);
      });
    });
    return () => {
      active = false;
      unsubscribeUsers();
      unsubscribeTasks();
    };
  }, [currentUser?.id, currentUser?.isSuperAdmin, currentCompany?.TenantID]);

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
      // تذكيرات الملاحظات المستحقة اليوم — للأطراف أو لأي صفحة/سجل في المنصة.
      void import("./services/customerNoteReminders").then((m) =>
        m.runCustomerNoteReminders(currentUser.id)
      );
      // T-DORMANT: عملاء توقّفوا عن الشراء (عتبة إعدادات المبيعات) — إشعار «عميل مختفٍ».
      void import("./services/customerDormancyAlerts").then((m) =>
        m.runCustomerDormancyAlerts(currentUser.id)
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

  // M6: حُذف نظام السمة المكرّر الذي كان هنا (حالة محلية + useEffect يضيف/يزيل
  // كلاس dark + toggleTheme). كان ميتاً وضاراً معاً: toggleTheme لا يُمرَّر لأي
  // مكوّن، و«Header.tsx» الذي يستقبله غير مستورد في أي مكان — بينما الـ useEffect
  // كان يزيل كلاس dark عند كل تركيب فيُلغي ما طبّقه applyThemeOnBoot، وهذا سبب
  // ضياع الوضع الداكن مع كل تحديث للصفحة. المصدر الوحيد الآن: ThemeContext.

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

      await (await legacyData()).updateUserTaskStatus(taskId, userId, status);

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
      toast(humanizeThrown(error, "تعذّر تحديث حالة المهمة"), "error");
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
      await (await legacyData()).addSubmissionToTaskInDb(taskId, newSubmission, log);

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
      toast(humanizeThrown(e, "تعذّر حفظ التسليم"), "error");
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
      await (await legacyData()).updateSubmissionInTaskInDb(taskId, submissionId, updateData, log);
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
      toast(humanizeThrown(e, "تعذّر تعديل التسليم"), "error");
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

          await (await legacyData()).updateUserInDb(updatedUser);

          const currentPoints = await (await legacyData()).pointsHistoryService.getDailyPoints(
            submission.userId,
            today
          );

          const updatedTaskPoints = (currentPoints?.taskPoints || 0) + 5;
          const updatedCompletedTasks = (currentPoints?.completedTasks || 0) + 1;
          const updatedTotalPoints = (currentPoints?.totalPoints || 0) + 5;

          await (await legacyData()).pointsHistoryService.updatePointsManually(
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

      await (await legacyData()).updateTaskInDb(updatedTask);
    } catch (error) {
      // console suppressed
      toast(humanizeThrown(error, "تعذّر تحديث حالة التسليم"), "error");
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
    await (await legacyData()).updateTaskInDb({ ...updatedTask, logs: [...updatedTask.logs, log] });
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

    await (await legacyData()).updateTaskInDb(updatedTask);
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
    await (await legacyData()).updateTaskInDb(updatedTask);
    setRejectingTask(null);
    setSelectedTaskDetails(null);
  };

  const handleSearch = async (query: SearchQuery) => {
    setSourcingView("loading");
    setError(null);
    try {
      const { findProducts } = await import("./services/geminiService");
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
    await (await legacyData()).createTaskInDb(newTask);
  };

  const handleResetSourcing = () => {
    setSourcingView("search");
    setProducts([]);
  };

  const handleUpdateUser = async (user: User) => {
    await (await legacyData()).updateUserInDb(user);
    if (user.id === currentUser?.id) {
      updateUser(user);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    await (await legacyData()).deleteUserFromDb(userId);
  };

  const handleSaveNotes = async (userId: string, notes: string) => {
    await (await legacyData()).updateUserInDb({ id: userId, notes });
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

    // ISSUE #51: القناع الحيّ — يفشل مغلقاً **قبل** الدخول في switch الشاشات، فلا
    // يُنزَّل chunk الشاشة المخفيّة أصلاً (لا case يُطابَق قبل هذا الشرط).
    if (templateHidesView(String(appView), companyTemplate)) {
      return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
    }

    switch (appView) {
      case "company-accountant-engagements":
        if (!canView(appView)) {
          return <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية إدارة ارتباطات المحاسبين (403).</div>;
        }
        return (
          <ModuleLicenseGuard view={appView} message="بوابة المحاسب غير مفعّلة لهذه الشركة أو لا تملك صلاحية الوصول.">
            <CompanyAccountantEngagementsPage />
          </ModuleLicenseGuard>
        );

      case "sensitive-devices":
        // الترخيص أولاً ثم الصلاحية — نفس ترتيب الخادم
        // (`device_registry/views.py::initial`): مفاتيح صلاحيات الوحدة تُحذف من
        // كتالوج الشركة غير المرخّصة، فالفحص المعكوس كان يقول «لا تملك صلاحية»
        // لشركةٍ ينقصها الترخيص لا الصلاحية.
        return (
          <ModuleLicenseGuard view={appView} message="وحدة تسجيل وتتبع الأجهزة الحساسة غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <SensitiveDevicesScreen />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض سجل الأجهزة الحساسة (403).</div>}
          </ModuleLicenseGuard>
        );

      case "after-sales":
        // نفس ترتيب THA-45 والخادم (`after_sales/views.py::initial`): الترخيص
        // أولاً ثم الصلاحية — مفاتيح صلاحيات الوحدة تُحذف أصلاً من كتالوج
        // الشركة غير المرخّصة، فالفحص المعكوس يقول «لا تملك صلاحية» لشركةٍ
        // ينقصها الترخيص لا الصلاحية.
        return (
          <ModuleLicenseGuard view={appView} message="وحدة خدمة ما بعد البيع غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <WarrantyCardsScreen />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض بطاقات الكفالة (403).</div>}
          </ModuleLicenseGuard>
        );

      case "service-orders":
        // نفس ترتيب البوابتين — الوحدة واحدة والصلاحية مستقلة عن الكفالات.
        return (
          <ModuleLicenseGuard view={appView} message="وحدة خدمة ما بعد البيع غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <ServiceOrdersScreen onOpenInvoice={() => setViewAndSyncPath("sales-invoices")} />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض أوامر الصيانة (403).</div>}
          </ModuleLicenseGuard>
        );

      case "hr-org":
        // نفس ترتيب البوابتين — الترخيص أولاً ثم الصلاحية (`hr/suite.py::initial`).
        return (
          <ModuleLicenseGuard view={appView} message="وحدة الموارد البشرية غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <OrgStructurePage />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض الهيكل التنظيمي (403).</div>}
          </ModuleLicenseGuard>
        );

      case "hr-attendance":
        return (
          <ModuleLicenseGuard view={appView} message="وحدة الموارد البشرية غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <HrAttendancePage />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض سجل الحضور (403).</div>}
          </ModuleLicenseGuard>
        );

      case "hr-check-in":
        // شاشة الموظف بنفسه — صلاحيتها `ess.self` التي يملكها كل من يعمل في
        // الشركة، والخادم يحلّ الموظف من الجلسة فلا يرى أحدٌ غير بياناته.
        return (
          <ModuleLicenseGuard view={appView} message="وحدة الموارد البشرية غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <HrCheckInPage />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية الخدمة الذاتية (403).</div>}
          </ModuleLicenseGuard>
        );

      case "hr-requests":
        return (
          <ModuleLicenseGuard view={appView} message="وحدة الموارد البشرية غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <HrRequestsPage />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية الطلبات (403).</div>}
          </ModuleLicenseGuard>
        );

      case "hr-contracts":
        return (
          <ModuleLicenseGuard view={appView} message="وحدة الموارد البشرية غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <HrContractsPage />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض العقود (403).</div>}
          </ModuleLicenseGuard>
        );

      case "import-file-guide":
        // THA-114: نفس ترتيب البوابتين — الترخيص أولاً ثم الصلاحية، ومفاتيح
        // صلاحيات الوحدة محذوفة أصلاً من كتالوج الشركة غير المرخّصة.
        return (
          <ModuleLicenseGuard view={appView} message="وحدة ملف الاستيراد غير مفعّلة لهذه الشركة.">
            {canView(appView)
              ? <ImportFileGuideScreen />
              : <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض ملف الاستيراد (403).</div>}
          </ModuleLicenseGuard>
        );

      case "super-admin":
        if (!currentUser!.isSuperAdmin) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <SuperAdminDashboard onNavigate={setViewAndSyncPath} />;

      case "development-notes":
        if (!currentUser!.isSuperAdmin) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <DevelopmentNotesPage />;

      case "dashboard":
        // T-DASHPERIOD: مؤشرات الشركة المالية للمدير فقط، وإلا اللوحة الشخصية.
        if (isManager) {
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
        if (canPerm("hr.tasks.manage")) {
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
        // ISSUE #62: الصلاحية هي الحقيقة — نفس مفتاح الرابط في الشريط الجانبي.
        if (!canView(appView))
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return (
          <UserManagement
            users={users}
            onUpdateUser={handleUpdateUser}
            onDeleteUser={handleDeleteUser}
          />
        );

      case "activity-log":
        if (!canView(appView))
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return <ActivityLogPage />;

      case "reports":
        return <ReportsHubPage />;

      case "report-runner":
        return <ReportRunnerPage />;

      // تقارير وقت الفريق (مهام وموظفون) — كانت تشغل /reports قبل قسم التقارير.
      case "team-time-report":
        if (!canView(appView))
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return <Reports tasks={tasks} users={users} />;

      case "employee-notes":
        if (!canView(appView))
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return <EmployeeNotes users={users} onSaveNotes={handleSaveNotes} />;

      case "points-history":
        return <PointsHistoryPage user={currentUser} />;

      // «حسابي» — بلا صلاحية في الخريطة: لكل مستخدم صفحته ودفتره وحده.
      case "my-account":
        return <MyAccountPage user={currentUser!} onNavigate={setViewAndSyncPath} />;

      case "payroll":
        if (!canView(appView)) {
          return <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center font-bold text-red-800">لا تملك صلاحية عرض الرواتب (403).</div>;
        }
        return <PayrollPage />;

      case "points-management":
        if (!canView(appView))
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        return <EmployeePointsManagement users={users} />;

      case "settings":
        return <SettingsPage user={currentUser!} />;

      case "attendance":
        // T-HR: شركةٌ مرخّصة لـ`hr_suite` ترى الحضور الحقيقي (بصمةٌ على الموظف
        // تصل الرواتب). الشاشتان القديمتان تعملان على جلسات مرآة Firestore عبر
        // `services/attendanceService.ts` ولا تمسّان `/api/hr/` أصلاً — تبقيان
        // للشركات غير المرخّصة كي لا يفقد أحدٌ ما كان يستعمله، ولا تُحذفان هنا.
        if (moduleAllowsView("hr-attendance", licensedModules)) {
          return canView("hr-attendance")
            ? <HrAttendancePage />
            : <HrCheckInPage />;
        }
        if (currentUser!.role === "manager") {
          return <AttendanceManagement users={users} currentUser={currentUser!} />;
        }
        return <EmployeeAttendance currentUser={currentUser!} />;

      case "sales-invoices":
        if (canView(appView)) {
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
        if (canView(appView)) {
          return <SalesCustomerPaymentsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "permissions":
        // الإنفاذ خادمي؛ هنا إخفاء الشاشة عمّن لا يملك إدارتها.
        if (canManagePermissions) {
          return <PermissionsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "store-settings":
        if (canView(appView)) {
          return <StoreSettingsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sales-settings":
        if (canView(appView)) {
          return <SalesSettingsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "purchase-settings":
        if (canView(appView)) {
          return <PurchaseSettingsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "purchase-receipts":
        if (canView(appView)) {
          return <GoodsReceiptsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sales-delivery-notes":
        if (canView(appView)) {
          return <DeliveryNotesPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sales-customers":
        if (canView(appView)) {
          return <SalesCustomersPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "invoice-profits":
        if (canView(appView)) {
          return <InvoiceProfitsPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "reserved-stock":
        if (canView(appView)) {
          return <ReservedStockReportPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "purchase-invoices":
        if (canView(appView)) {
          return <PurchaseInvoice currentUser={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "international-invoices":
        if (canView(appView)) {
          return (
            <PurchaseInvoice
              currentUser={currentUser!}
              invoiceType="international"
              listPath="/international-invoices"
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      // ---------- New Case Added Here ----------
      case "old-invoices":
        if (canView(appView)) {
          return <OldPurchaseInvoice />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "price-offers":
        if (canView(appView)) {
          return <PriceOfferManagement scope="purchase" />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "import-offers":
        if (canView(appView)) {
          return <PriceOfferManagement scope="import" />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "deals-management":
        if (canView(appView)) {
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
      case "items-categories":
        if (canView(appView)) {
          return <ItemsManagement user={currentUser!} initialTab={appView === "items-categories" ? "categories" : "products"} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "supplier-management":
        if (canView(appView)) {
          return (
            <SupplierManagement
              initialPartnerId={accountingSupplierPartnerId}
              onInitialPartnerConsumed={() => setAccountingSupplierPartnerId(null)}
            />
          );
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "shipments-management":
        if (canView(appView)) {
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
        if (canView(appView)) {
          return <CustomsClearanceManagement currentUser={currentUser!} />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "local-shipping":
        if (canView(appView)) {
          return <LocalShippingPage />;
        }
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "cash-boxes":
        if (canView(appView)) {
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
        if (canPerm("finance.cashbox.manage") && selectedCashBox) {
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

      case "about-us":
        return <AboutUs />;

      case "contact":
        return <Contact currentUser={currentUser} />;

      case "accounting-coa":
        // ISSUE #62: الصلاحية هي الحقيقة — نفس مفتاح الرابط في الشريط الجانبي.
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return (
          <AccountingCoaPage
            onOpenGeneralLedger={(id) => {
              setAccountingGlAccountId(id);
              setAppView("accounting-general-ledger");
            }}
            onOpenSupplier={(partnerId) => {
              setViewAndSyncPath("partner-profile", String(partnerId));
            }}
          />
        );

      case "accounting-journals":
        if (!canView(appView)) {
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
        // ISSUE #62: كان يسمح أيضاً لدور «مشتريات» — لكن المشتريات لا يملك
        // `accounting.journal.create` افتراضياً، فكانت الشاشة تُفتح والحفظ
        // يرتدّ 403 من الخادم. الصلاحية هي الحقيقة على الجانبين معاً الآن.
        if (!canView(appView)) {
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
                : accountingJournalBackView === "accounting-general-ledger"
                  ? "/accounting/general-ledger"
                : "/accounting/journals";
              navigate(backPath);
              setAppView(accountingJournalBackView);
            }}
          />
        );

      case "accounting-cheques":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <AccountingChequesPage />;

      case "accounting-banks":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <BanksPage />;

      case "accounting-bank-reconciliation":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <BankReconciliationPage />;

      case "accounting-general-ledger":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return (
          <AccountingGeneralLedgerPage
            initialAccountId={accountingGlAccountId}
            onInitialAccountConsumed={() => setAccountingGlAccountId(null)}
            onOpenJournal={(journalId, accountId) => {
              // الرجوع من القيد يعيد الكشف على الحساب نفسه لا على شاشة فارغة.
              setAccountingGlAccountId(accountId);
              setAccountingJournalRelatedKind(null);
              setAccountingJournalBackView("accounting-general-ledger");
              setAccountingJournalId(journalId);
              setAccountingJournalDealRef(null);
              setViewAndSyncPath("accounting-journal-entry", String(journalId));
            }}
          />
        );

      case "accounting-trial-balance":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return (
          <AccountingTrialBalancePage
            onOpenAccount={(id) => {
              setAccountingGlAccountId(id);
              setViewAndSyncPath("accounting-general-ledger");
            }}
          />
        );

      case "accounting-vat-report":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <AccountingVatReportPage />;

      case "accounting-landed-cost":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <AccountingLandedCostPage />;

      case "accounting-fiscal-periods":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <FiscalPeriodsPage />;

      case "accounting-exchange-rates":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <ExchangeRatesPage />;

      case "accounting-balance-sheet":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <BalanceSheetPage />;

      case "accounting-income-statement":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <IncomeStatementPage />;

      case "accounting-vat-statements":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <VatStatementsPage />;

      case "accounting-year-end-close":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <YearEndClosePage />;

      case "accounting-opening-balances":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <OpeningBalancesPage />;

      case "accounting-expense-vouchers":
        if (!canView(appView)) {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <ExpenseVouchersPage />;

      // ISSUE #65: باب دفاتر العملاء داخل قشرة الشركة — لمن يدير مكتب محاسبة.
      // اللوحة نفسها تردّ سببَ غيابها حين لا مكتب، فلا حاجة لحارسٍ ثانٍ هنا.
      case "client-books":
        if (currentUser!.role !== "manager") {
          return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
        }
        return <ClientBooksPanel />;

      case "stock-levels":
        return <StockLevelsPage />;

      case "stock-movements":
        return <StockMovementsPage />;

      case "warehouses":
        return <WarehousesManager />;

      case "warehouse-transfer":
        return <WarehouseTransferPage />;

      case "stocktake":
        return <StocktakePage />;

      case "product-cost":
        return <ProductCostPage />;

      case "inventory-valuation":
        return <InventoryValuationPage />;

      case "property-rental":
        if (canView(appView)) {
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

      case "ui-kit":
        return <KitStory />;

      case "sales-classic":
        return <SalesInvoiceKitStory />;

      case "sales-orders":
        if (canView(appView)) return <SalesDocumentsPage initialTab="orders" />;
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;

      case "sales-quotations":
        return <SalesDocumentsPage initialTab="quotations" />;

      case "credit-debit-notes":
        return <CreditDebitNotesPage />;

      case "sales-return":
        return <SalesReturnEditor onBack={() => setAppView("sales-invoices")} />;

      case "purchase-return":
        return <PurchaseReturnEditor onBack={() => setAppView("purchase-invoices")} />;

      case "supplier-payments":
        return <SupplierPaymentsPage />;

      case "partner-profile":
        return <PartnerProfilePage />;

      case "product-profile":
        return <ProductProfilePage />;

      case "product-group":
        return <GroupProfilePage />;

      default:
        return <Dashboard tasks={tasks} users={users} onNavigate={setViewAndSyncPath} currentUser={currentUser!} />;
    }
  };

  // Dev kit — no auth required
  if (appView === "ui-kit") {
    return <KitStory />;
  }
  if (appView === "sales-classic") {
    return <SalesInvoiceKitStory />;
  }

  // 2. Auth Checks
  if (authLoading) {
    return (
      <div>
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <LoadingSpinner />
        </div>
      </div>
    );
  }

  if (!currentUser) {
    if (appView === "about-us") {
      return (
        <div>
          <PublicNavbar />
          <div className="pt-20 min-h-screen bg-gray-50 dark:bg-gray-900">
            <AboutUs />
          </div>
        </div>
      );
    }
    if (appView === "gallery") {
      return (
        <div>
          <PublicNavbar />
          <div className="pt-20 min-h-screen bg-gray-50 dark:bg-gray-900">
            <PublicGallery />
          </div>
        </div>
      );
    }
    if (appView === "contact") {
      return (
        <div>
          <PublicNavbar />
          <div className="pt-20 min-h-screen bg-gray-50 dark:bg-gray-900">
            <Contact currentUser={null} />
          </div>
        </div>
      );
    }

    if (authView === "signup") {
      return (
        <div>
          <SignupPage onNavigateToLogin={() => setAuthView("login")} />
        </div>
      );
    }
    if (authView === "login") {
      return (
        <div>
          <LoginPage
            onNavigateToSignup={() => setAuthView("signup")}
            onGoToStore={() => navigate("/store")}
          />
        </div>
      );
    }
    // صفحة هبوط تعريفية بالمنصة للزوّار غير الأعضاء (الافتراضية قبل تسجيل الدخول).
    return (
      <div>
        <LandingPage
          onLogin={() => setAuthView("login")}
          onSignup={() => setAuthView("signup")}
          onGoToStore={() => navigate("/store")}
        />
      </div>
    );
  }

  // T-EXTACCT: المحاسب القانوني يعمل في **قشرة مستقلة** لا في واجهة الشركات
  // التجارية. سوبر أدمن فتح واجهة تجريبية يخرج منها بمفتاح جلسة واحد.
  // سوبر أدمن له ملف محاسب قانوني: لا يُفتح له مكتب المحاسبة تلقائياً عند
  // الدخول (بيته لوحة المنصة) — المكتب يُفتح فقط بدخول صريح على `/office`
  // (زر «افتح واجهة المحاسب القانوني»)، لا بمجرّد غياب مفتاح القشرة.
  const isOfficePath = typeof window !== "undefined" && window.location.pathname.startsWith("/office");
  if (
    currentUser.accountType === "legal_accountant"
    && !platformShellOverride
    && (!currentUser.isSuperAdmin || isOfficePath)
  ) {
    return (
      <React.Suspense fallback={<div className="flex min-h-screen items-center justify-center"><LoadingSpinner /></div>}>
        <AccountantOfficeApp
          user={currentUser}
          onLogout={logout}
          onExitToPlatform={currentUser.isSuperAdmin ? () => {
            enterPlatformShell();
            clientLogger.info("accountant.shell_switched", { to: "platform" });
            window.location.assign("/super-admin");
          } : undefined}
        />
      </React.Suspense>
    );
  }

  // مسار المكتب لحسابٍ ليس مكتب محاسبة: قل السبب صراحةً بدل عرض لوحة تجارية
  // صامتة يظنها المستخدم «الواجهة لم تتغير».
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/office") && !platformShellOverride) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
        <div className="w-full max-w-lg rounded-3xl bg-white p-8 text-center shadow-xl">
          <h1 className="text-xl font-black text-slate-900">هذا الحساب ليس مكتب محاسبة قانونية</h1>
          <p className="mt-3 text-sm leading-7 text-slate-600">
            واجهة المكتب تفتح للحسابات التي لها ملف محاسب مهني. إن كنت سوبر أدمن فافتحها بزر
            «افتح واجهة المحاسب القانوني» من لوحة المنصة، ثم أعد تحميل الصفحة.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={() => window.location.assign("/super-admin")} className="rounded-xl bg-blue-600 px-5 py-3 font-bold text-white">لوحة المنصة</button>
            <button type="button" onClick={() => window.location.assign("/dashboard")} className="rounded-xl border border-slate-300 px-5 py-3 font-bold">الرئيسية</button>
          </div>
        </div>
      </div>
    );
  }

  const showReturnButton = !!activeTask && appView !== "sourcing";

  return (
    <div dir="rtl">
      <AppLayout user={currentUser} activeView={appView} onNavigate={setViewAndSyncPath} onOpenGroupConstants={() => setGroupConstantsOpen(true)} listPath={VIEW_PATHS[appView]}>
        <div className="fixed top-3 left-3 z-50">
          <PendingMutationsPanel />
        </div>
        <OfflineBanner status={onlineStatus} onRetry={() => window.location.reload()} />
        <main className="p-3 sm:p-4 lg:p-6">
          {/* الصفحات chunks كسولة — سبينر ريثما يصل chunk الشاشة المطلوبة */}
          <React.Suspense fallback={<div className="flex justify-center py-16"><LoadingSpinner /></div>}>
            {renderMainContent()}
          </React.Suspense>
          {/* THA-121: «هل تعلم» — تركيبٌ واحد لكل الشاشات؛ تختار تلميح الشاشة
              الحالية، وتختفي كلياً إن لم يبقَ لها متّسع أسفل المحتوى. */}
          <DidYouKnow view={appView} onNavigate={setViewAndSyncPath} />
        </main>
      </AppLayout>

      <React.Suspense fallback={null}>
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
      </React.Suspense>
      <UpdatePrompt />
      <OfflineCoachmark />
      <StorageQuotaGuard />
      {/* DEF-009: مهلة الخمول — تُنهي الجلسة بعد عدم نشاط طويل */}
      <IdleTimeoutGuard onLogout={logout} />
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
