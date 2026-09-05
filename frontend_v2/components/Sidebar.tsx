import React, { useState, useEffect } from "react";
import { User, AppView } from "../types";
import { LogoIcon } from "./icons/LogoIcon";
import { TasksIcon } from "./icons/TasksIcon";
import { UsersIcon } from "./icons/UsersIcon";
import { ReportsIcon } from "./icons/ReportsIcon";
import { SettingsIcon } from "./icons/SettingsIcon";
import { NoteIcon } from "./icons/NoteIcon";
import { PointsIcon } from "./icons/PointsIcon";
import { AttendanceIcon } from "./icons/AttendanceIcon";
import { GalleryIcon } from "./icons/GalleryIcon";
import {
  ChevronDown, ChevronUp, Package, FileText, History,
  Handshake, Users, Menu, X, ChevronRight, ChevronLeft, Info,
  Calculator, BookMarked, Scale, BookOpen, BookOpenCheck, Banknote,
  CalendarDays, CalendarX, ArrowLeftRight, Boxes, BarChart3, Building2,
  ShoppingCart, Receipt, Ship, Truck, TrendingUp, ClipboardList,
  ShoppingBag, Landmark, Warehouse, Download, ExternalLink, Home, ShieldCheck,
  Gauge, TableProperties, ShieldAlert, Wrench, Store, Sparkles, LayoutGrid,
  PlayCircle, Network, Fingerprint, CalendarCheck, Inbox, FileSignature,
} from 'lucide-react';
import { openInNewTab } from "../utils/openInNewTab";
import { enterOfficeShell } from "../utils/officeShell";
import { readAccountantMode, writeAccountantMode } from "../utils/accountantMode";
import { clientLogger } from "../services/logger";
import { useCompany } from "../contexts/CompanyContext";
import { usePermissions } from "../contexts/PermissionsContext";
import { devicesNavPlacement, moduleAllowsView, templateHidesView } from "../utils/viewPermissions";
import { groupVisible, visibleLinks } from "../utils/navAccess";
import { buildShellSections } from "../utils/shellManifest";
import { SIMPLE_VIEWS } from "../utils/uiMode";
import { FieldHint } from "./ui/FieldHint";
import type { SimpleHintKey } from "../constants/simpleHints";
import { permForView } from "../utils/viewPermissions";
import { useTenantSettings } from "../hooks/useTenantSettings";
import { listPurchaseRfqs, type PurchaseRFQDto } from "../services/procurementDocumentsApi";

// ISSUE #115 قصّة ٣٠ §٦: شارة «ردٌّ جديد» على بند «العروض والطلبيات» — بلا
// جدول إشعارات جديد على الخادم (المواصفة تنصّ صراحةً «صفر جداول جديدة»).
// العدد مشتقٌّ من بيانات الطلبيات القائمة أصلاً (`recipients[].replied_at`)،
// و«غير مقروء» محليٌّ بنفس نمط `WhatsNewButton.tsx` (`SEEN_KEY` في localStorage)
// لا نمطٌ ثانٍ يُخترع هنا.
type RfqBadgeScope = "local" | "import";
const RFQ_SEEN_STORAGE_KEY: Record<RfqBadgeScope, string> = {
  local: "ktra_rfq_replies_seen_local",
  import: "ktra_rfq_replies_seen_import",
};
const readRfqSeenIds = (scope: RfqBadgeScope): Set<number> => {
  try {
    const raw = localStorage.getItem(RFQ_SEEN_STORAGE_KEY[scope]);
    return new Set(raw ? (JSON.parse(raw) as number[]) : []);
  } catch {
    return new Set();
  }
};
const repliedRecipientIds = (rows: PurchaseRFQDto[]): number[] =>
  rows.flatMap((rfq) => rfq.recipients.filter((r) => r.replied_at).map((r) => r.id));

interface SidebarProps {
  user: User;
  activeView: AppView;
  setView: (view: AppView, targetId?: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ user, activeView, setView }) => {
  // صلاحية الاستيراد للشركة النشطة (تتفاعل مع تبديل الشركة) — لا تعتمد على علم ثابت من تسجيل الدخول.
  const { canAccessImport } = useCompany();
  // T-PERM: القائمة مشتقّة من الصلاحيات؛ ملخص الأعمال استثناء للمدير فقط.
  // THA-110: `uiMode` تفضيل عرضٍ لا صلاحية — يُقلّم ما يُعرَض أولاً ولا يحجب مساراً.
  const { can, isManager, permissions, modules, template, uiMode, setUiMode, term, shell } = usePermissions();
  // ISSUE #51: القناع الحيّ — نفس النقطة التي يحرس بها App.tsx الدخول المباشر.
  const hiddenByTemplate = (view: AppView) => templateHidesView(String(view), template);
  const isSimpleMode = uiMode === 'simple';
  const { identity } = useTenantSettings();

  // ISSUE #115 قصّة ٣٠ §٦: عدّاد ردود الطلبية غير المطّلَع عليها — لكلا بندي
  // «العروض والطلبيات» (الشراء المحلي والاستيراد، لكلٍّ نطاقه الخاص في
  // `PurchaseRFQ`). يُجلب مرّة عند إتاحة البند فقط — لا استطلاعٌ متكرر.
  const [rfqRepliedIds, setRfqRepliedIds] = useState<Record<RfqBadgeScope, number[]>>({ local: [], import: [] });
  const [rfqUnseenCount, setRfqUnseenCount] = useState<Record<RfqBadgeScope, number>>({ local: 0, import: 0 });
  const localRfqPerm = permForView("price-offers");
  const importRfqPerm = permForView("import-offers");
  const canSeeLocalRfq = !localRfqPerm || can(localRfqPerm);
  const canSeeImportRfq = canAccessImport && (!importRfqPerm || can(importRfqPerm));
  useEffect(() => {
    const wantLocal = canSeeLocalRfq && !templateHidesView("price-offers", template);
    const wantImport = canSeeImportRfq && !templateHidesView("import-offers", template);
    if (!wantLocal && !wantImport) return;
    let cancelled = false;
    (async () => {
      try {
        const [localRows, importRows] = await Promise.all([
          // «مُرسَلة» وحدها — الطلبيةُ المُرساة أو الملغاة لا يصلها ردٌّ جديد،
          // وجلبُ القائمة كاملةً عند كل إقلاعٍ ثمنٌ لا تستحقّه شارة.
          wantLocal ? listPurchaseRfqs("local", "sent") : Promise.resolve([]),
          wantImport ? listPurchaseRfqs("import", "sent") : Promise.resolve([]),
        ]);
        if (cancelled) return;
        const localIds = repliedRecipientIds(localRows);
        const importIds = repliedRecipientIds(importRows);
        setRfqRepliedIds({ local: localIds, import: importIds });
        setRfqUnseenCount({
          local: localIds.filter((id) => !readRfqSeenIds("local").has(id)).length,
          import: importIds.filter((id) => !readRfqSeenIds("import").has(id)).length,
        });
      } catch {
        // الشارة تفصيلٌ تجميلي — فشل جلبها لا يجوز أن يُسقط الشريط الجانبي.
      }
    })();
    return () => { cancelled = true; };
  }, [canSeeLocalRfq, canSeeImportRfq, template]);

  // فتح البند = «اطّلع» — يُسجَّل ما عُرف من ردود حتى الآن فتختفي الشارة.
  const markRfqRepliesSeen = (scope: RfqBadgeScope) => {
    try {
      localStorage.setItem(RFQ_SEEN_STORAGE_KEY[scope], JSON.stringify(rfqRepliedIds[scope]));
    } catch {
      // لا صلاحية تخزين محلي — الشارة تعود في الزيارة القادمة، لا كسر يحدث.
    }
    setRfqUnseenCount((prev) => ({ ...prev, [scope]: 0 }));
  };

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  // A5: «وضع المحاسب» — ترتيبُ عرضٍ محفوظ لصاحب هذا المتصفح، يضع المحاسبة أولاً.
  const [accountantMode, setAccountantMode] = useState<boolean>(readAccountantMode);
  // Phase 5 (Section 9): مجموعات تنقّل رئيسية كبيرة، كلٌّ بأيقونته الخاصة.
  const [salesExpanded, setSalesExpanded] = useState(false);
  const [customersExpanded, setCustomersExpanded] = useState(false);
  const [purchasesExpanded, setPurchasesExpanded] = useState(false);
  const [inventoryExpanded, setInventoryExpanded] = useState(false);
  const [importExpanded, setImportExpanded] = useState(false);
  const [financeExpanded, setFinanceExpanded] = useState(false);
  const [reportsExpanded, setReportsExpanded] = useState(false);
  // A5: في «وضع المحاسب» تبدأ المحاسبة مفتوحة — وهي أول ما جاء المستخدم لأجله.
  const [accountingExpanded, setAccountingExpanded] = useState(accountantMode);
  const [userManagementExpanded, setUserManagementExpanded] = useState(false);
  const [afterSalesExpanded, setAfterSalesExpanded] = useState(false);
  const [platformExpanded, setPlatformExpanded] = useState(true);
  // ISSUE #83: مجموعات بيان الشريط تُوسَّع بمفتاحها (id) لا بفهرسها — إدراج
  // مجموعةٍ في البيان لا يزيح توسيع مجموعةٍ أخرى.
  const [manifestExpanded, setManifestExpanded] = useState<Record<string, boolean>>({});

  const accountingLinks: { view: AppView; label: string; icon: React.ReactNode; perm?: string }[] = [
    { view: "accounting-coa", label: "شجرة الحسابات", icon: <BookMarked className="h-4 w-4" /> },
    { view: "accounting-journals", label: "دفتر اليومية (القيود)", icon: <FileText className="h-4 w-4" /> },
    { view: "accounting-cheques", label: "الشيكات", icon: <Banknote className="h-4 w-4" /> },
    { view: "accounting-banks", label: "البنوك وفروعها", icon: <Landmark className="h-4 w-4" /> },
    { view: "accounting-bank-reconciliation", label: "المطابقة البنكية", icon: <Scale className="h-4 w-4" /> },
    { view: "accounting-general-ledger", label: "الأستاذ العام", icon: <BookOpen className="h-4 w-4" /> },
    { view: "accounting-trial-balance", label: "ميزان المراجعة", icon: <Scale className="h-4 w-4" /> },
    { view: "accounting-vat-report", label: "تقرير ضريبة القيمة المضافة", icon: <Receipt className="h-4 w-4" /> },
    { view: "accounting-landed-cost", label: "تقرير التكلفة المستوردة", icon: <Ship className="h-4 w-4" /> },
    { view: "accounting-fiscal-periods", label: "الفترات المالية", icon: <CalendarDays className="h-4 w-4" /> },
    { view: "accounting-opening-balances", label: "الأرصدة الافتتاحية", icon: <PlayCircle className="h-4 w-4" /> },
    { view: "accounting-exchange-rates", label: "أسعار الصرف", icon: <ArrowLeftRight className="h-4 w-4" /> },
    { view: "accounting-balance-sheet", label: "الميزانية العمومية", icon: <BarChart3 className="h-4 w-4" /> },
    { view: "accounting-income-statement", label: "قائمة الدخل", icon: <TrendingUp className="h-4 w-4" /> },
    { view: "accounting-vat-statements", label: "كشوف ضريبة القيمة المضافة", icon: <ClipboardList className="h-4 w-4" /> },
    { view: "accounting-year-end-close", label: "الإغلاق السنوي", icon: <CalendarX className="h-4 w-4" /> },
    { view: "property-rental", label: "تأجير العقارات والعدادات", icon: <Building2 className="h-4 w-4" /> },
  ];

  const userManagementLinks = [
    { view: "users" as AppView, label: "قائمة المستخدمين", icon: <UsersIcon className="h-5 w-5" /> },
    { view: "activity-log" as AppView, label: "سجل النشاط", icon: <History className="h-5 w-5" /> },
    // T-PERM: مصفوفة (دور × صلاحية) — مدير الشركة فقط.
    { view: "permissions" as AppView, label: "الصلاحيات والأدوار", icon: <ShieldCheck className="h-5 w-5" /> },
    { view: "attendance" as AppView, label: "الحضور والغياب", icon: <AttendanceIcon className="h-5 w-5" /> },
    // الرواتب — بندها في شجرة الحسابات وتحته حساب كل موظف.
    { view: "payroll" as AppView, label: "الرواتب", icon: <Banknote className="h-5 w-5" /> },
    // T-HR: بنود وحدة `hr_suite` المرخّصة — تُحقن هنا لا في مجموعة مستقلة، لأن
    // مكانها الطبيعي مع بقية شؤون الموظفين. الشرط بالوحدة لا بالصلاحية:
    // `withPerms` يقرأ الصلاحية وحدها من الخريطة ولا يعرف الترخيص.
    ...(moduleAllowsView("hr-org", modules)
      ? [
        { view: "hr-check-in" as AppView, label: "تسجيل حضوري", icon: <Fingerprint className="h-5 w-5" /> },
        { view: "hr-attendance" as AppView, label: "سجل الحضور والانصراف", icon: <CalendarCheck className="h-5 w-5" /> },
        { view: "hr-requests" as AppView, label: "الطلبات والسلف", icon: <Inbox className="h-5 w-5" /> },
        { view: "hr-contracts" as AppView, label: "العقود ومسير الرواتب", icon: <FileSignature className="h-5 w-5" /> },
        { view: "hr-org" as AppView, label: "الهيكل التنظيمي", icon: <Network className="h-5 w-5" /> },
      ]
      : []),
    { view: "employee-notes" as AppView, label: "ملاحظات الموظفين", icon: <NoteIcon className="h-5 w-5" /> },
    { view: "points-management" as AppView, label: "إدارة النقاط", icon: <PointsIcon className="h-5 w-5" /> },
    { view: "points-history" as AppView, label: "سجل نقاطي", icon: <PointsIcon className="h-5 w-5" />, roles: ['employee', 'procurement', 'manager'] },
  ];

  type NavLink = { view: AppView; label: string; icon: React.ReactNode; path?: string; newTab?: boolean; roles?: string[]; perm?: string; badge?: number };

  // 2) المبيعات — إعدادات المبيعات آخراً (Section 9).
  const salesLinksAll: NavLink[] = [
    { view: "sales-invoices", label: "فواتير المبيعات", icon: <FileText className="h-4 w-4" /> },
    { view: "sales-quotations", label: "العروض والطلبيات", icon: <ClipboardList className="h-4 w-4" /> },
    { view: "credit-debit-notes", label: "الإشعارات المدينة/الدائنة", icon: <FileText className="h-4 w-4" /> },
    { view: "sales-delivery-notes", label: "إرساليات البيع", icon: <Truck className="h-4 w-4" /> },
    { view: "sales-return", label: "مرتجع البيع", icon: <FileText className="h-4 w-4" /> },
    { view: "invoice-profits", label: "أرباح الفواتير", icon: <TrendingUp className="h-4 w-4" /> },
    { view: "reserved-stock", label: "تقرير المحجوزات", icon: <ClipboardList className="h-4 w-4" /> },
    { view: "sales-settings", label: "إعدادات المبيعات", icon: <SettingsIcon className="h-4 w-4" /> },
  ];
  const salesLinks = salesLinksAll.filter((l) => !hiddenByTemplate(l.view));

  // 3) العملاء
  const customersLinks: NavLink[] = [
    { view: "sales-customers", label: "العملاء", icon: <Users className="h-4 w-4" /> },
    { view: "sql-partners", label: "دليل الأطراف", icon: <UsersIcon className="h-4 w-4" />, roles: ["manager", "procurement"] },
    { view: "sales-customer-payments", label: "دفعات العملاء", icon: <Banknote className="h-4 w-4" /> },
  ];

  // 4) المشتريات
  const purchasesLinksAll: NavLink[] = [
    { view: "purchase-invoices", label: "فواتير الشراء", icon: <NoteIcon className="h-4 w-4" /> },
    { view: "price-offers", label: "العروض والطلبيات", icon: <FileText className="h-4 w-4" />, badge: rfqUnseenCount.local || undefined },
    { view: "purchase-receipts", label: "إرساليات الشراء", icon: <Truck className="h-4 w-4" /> },
    { view: "purchase-return", label: "مرتجع الشراء", icon: <FileText className="h-4 w-4" /> },
    { view: "supplier-payments", label: "سندات الصرف للموردين", icon: <Banknote className="h-4 w-4" /> },
    { view: "purchase-settings", label: "إعدادات الشراء", icon: <SettingsIcon className="h-4 w-4" /> },
    { view: "supplier-management", label: "الموردين", icon: <UsersIcon className="h-4 w-4" /> },
  ];
  // سند الصرف والموردون يبقيان — المكتب يدفع ويسدّد ذمّة 2101؛ ما يسقط هو
  // فواتير البضاعة وإرسالياتها ومرجعها وإعداداتها.
  const purchasesLinks = purchasesLinksAll.filter((l) => !hiddenByTemplate(l.view));

  // 5) الاستيراد
  const importLinksAll: NavLink[] = [
    { view: "import-offers", label: "عروض وطلبيات دولية", icon: <ClipboardList className="h-4 w-4" />, badge: rfqUnseenCount.import || undefined },
    { view: "international-invoices", label: "الفواتير الدولية", icon: <FileText className="h-4 w-4" /> },
    { view: "deals-management", label: "الصفقات", icon: <Handshake className="h-4 w-4" /> },
    { view: "shipments-management", label: "الشحنات", icon: <Ship className="h-4 w-4" /> },
    { view: "old-invoices", label: "أرشيف الفواتير", icon: <History className="h-4 w-4" /> },
    { view: "local-shipping", label: "النقل المحلي", icon: <Truck className="h-4 w-4" /> },
    { view: "customs-clearance", label: "التخليص الجمركي", icon: <FileText className="h-4 w-4" /> },
    { view: "import-flow", label: "رحلة الاستيراد", icon: <Package className="h-4 w-4" /> },
  ];
  const importLinks = importLinksAll.filter((l) => !hiddenByTemplate(l.view));

  // 6) المخزون — المنتجات (شجرة، T-N3) + أرصدة + حركات. (إعدادات المخزون غير مبنية — مُدرجة بخارطة الطريق.)
  const inventoryLinksAll: NavLink[] = [
    { view: "items-management", label: "المنتجات", icon: <Boxes className="h-4 w-4" /> },
    { view: "stock-levels", label: "أرصدة المخزون", icon: <BarChart3 className="h-4 w-4" /> },
    { view: "stock-movements", label: "حركات المخزون", icon: <ArrowLeftRight className="h-4 w-4" /> },
    { view: "product-cost", label: "تكلفة المنتجات", icon: <BarChart3 className="h-4 w-4" /> },
    { view: "warehouses", label: "المستودعات", icon: <Warehouse className="h-4 w-4" /> },
    { view: "warehouse-transfer", label: "تحويل بين المستودعات", icon: <Truck className="h-4 w-4" /> },
    { view: "stocktake", label: "الجرد", icon: <ClipboardList className="h-4 w-4" /> },
  ];
  const inventoryLinks = inventoryLinksAll.filter((l) => !hiddenByTemplate(l.view));

  // 7) المالية — الصناديق والبنوك والشيكات ومطابقة كشف البنك.
  const financeLinks: NavLink[] = [
    { view: "cash-boxes", label: "صناديق الكاش", icon: <Banknote className="h-4 w-4" /> },
    { view: "accounting-banks", label: "البنوك وفروعها", icon: <Landmark className="h-4 w-4" /> },
    { view: "accounting-bank-reconciliation", label: "المطابقة البنكية", icon: <Scale className="h-4 w-4" /> },
    { view: "accounting-cheques", label: "الشيكات", icon: <Receipt className="h-4 w-4" /> },
    // issue #56 — سند مصروف: مستندٌ عامٌّ لكل شركة بلا مورّدٍ إلزامي.
    { view: "accounting-expense-vouchers", label: "سندات المصروف", icon: <FileSignature className="h-4 w-4" /> },
    { view: "accounting-revenue-vouchers", label: "سندات الإيراد", icon: <FileSignature className="h-4 w-4" /> },
  ];

  // 8) التقارير — كل تقرير يفتح في تبويبه الخاص (G2).
  const reportsLinksAll: NavLink[] = [
    // T-REPORTS: «كل التقارير» هو فهرس القسم — يقود لكل تقارير المنصة. البقية
    // اختصارات للأكثر استعمالاً كي لا يمرّ المستخدم بالفهرس في كل مرة.
    { view: "reports", label: "كل التقارير", icon: <ReportsIcon className="h-4 w-4" />, path: "/reports", newTab: true },
    { view: "stock-movements", label: "تقرير حركة منتج", icon: <ArrowLeftRight className="h-4 w-4" />, path: "/stock-movements", newTab: true },
    { view: "accounting-trial-balance", label: "ميزان المراجعة", icon: <Scale className="h-4 w-4" />, path: "/accounting/trial-balance", newTab: true },
    { view: "accounting-income-statement", label: "قائمة الدخل", icon: <TrendingUp className="h-4 w-4" />, path: "/accounting/income-statement", newTab: true },
    { view: "accounting-balance-sheet", label: "الميزانية العمومية", icon: <BarChart3 className="h-4 w-4" />, path: "/accounting/balance-sheet", newTab: true },
    { view: "accounting-vat-report", label: "تقرير ض.ق.م", icon: <Receipt className="h-4 w-4" />, path: "/accounting/vat-report", newTab: true },
  ];
  const reportsLinks = reportsLinksAll.filter((l) => !hiddenByTemplate(l.view));

  // THA-24: خدمة ما بعد البيع — وحدة مرخّصة، مُلحَقة **آخر** قسم الوحدات كما
  // أُلحقت الأجهزة الحساسة قبلها: القسم الجديد في الوسط يزحزح ما تعوّده المستخدم.
  // بند «الأجهزة الحساسة» ينتقل إلى هنا حين تُرخَّص الوحدتان معاً (قرار المالك:
  // السجل إجراء ضمن هذا النظام)، ويبقى مستقلاً حين تُرخَّص وحدته وحدها.
  const devicesPlacement = devicesNavPlacement(modules);
  const afterSalesLinksAll: NavLink[] = [
    { view: "after-sales", label: "بطاقات الكفالة", icon: <ShieldCheck className="h-4 w-4" /> },
    { view: "service-orders", label: "أوامر الصيانة", icon: <Wrench className="h-4 w-4" /> },
    ...(devicesPlacement === "after-sales"
      ? [{ view: "sensitive-devices" as AppView, label: "الأجهزة الحساسة", icon: <ShieldAlert className="h-4 w-4" /> }]
      : []),
  ];
  const afterSalesLinks = afterSalesLinksAll.filter((l) => !hiddenByTemplate(l.view));

  // THA-110: بنود «الوضع السهل» — لا شاشة جديدة، بل نفس الشاشات القائمة بعنوانها
  // وأيقونتها المعتادتين. الخريطة `Record` فوق `SIMPLE_VIEWS`: أي بندٍ يُضاف أو
  // يُحذف في `utils/uiMode.ts` يكسر البناء هنا بدل أن يمرّ صامتاً، والترتيب من
  // هناك أيضاً — مصدرٌ واحد لا نسخة ثانية تفترق لاحقاً.
  const simpleViewMeta: Record<(typeof SIMPLE_VIEWS)[number], { label: string; icon: React.ReactNode }> = {
    "dashboard": { label: "الرئيسية", icon: <Home className="h-5 w-5 flex-shrink-0" /> },
    "sales-invoices": { label: "فواتير المبيعات", icon: <FileText className="h-5 w-5 flex-shrink-0" /> },
    "purchase-invoices": { label: "فواتير الشراء", icon: <NoteIcon className="h-5 w-5 flex-shrink-0" /> },
    "stock-levels": { label: "أرصدة المخزون", icon: <BarChart3 className="h-5 w-5 flex-shrink-0" /> },
    "items-management": { label: "المنتجات", icon: <Boxes className="h-5 w-5 flex-shrink-0" /> },
    "supplier-management": { label: "الموردين", icon: <UsersIcon className="h-5 w-5 flex-shrink-0" /> },
    "sales-customers": { label: "العملاء", icon: <Users className="h-5 w-5 flex-shrink-0" /> },
    "settings": { label: "الإعدادات", icon: <SettingsIcon className="h-5 w-5 flex-shrink-0" /> },
  };
  // «الرئيسية» تبقى للمدير وحده كما هي في الوضع المتقدم — الوضع يُرتّب ولا يمنح.
  // T5: مفتاح التلميح مشتقّ من اسم الشاشة نفسه، فلا قائمة مفاتيح ثانية تفترق.
  const simpleLinks: (NavLink & { hint: SimpleHintKey })[] = SIMPLE_VIEWS
    .filter((view) => view !== "dashboard" || isManager)
    .filter((view) => !hiddenByTemplate(view as AppView))
    .map((view) => ({ view: view as AppView, hint: `nav.${view}` as const, ...simpleViewMeta[view] }));

  // ISSUE #83: بيان الشريط — `buildShellSections` (`utils/shellManifest.ts`)
  // يحسم أيّ شاشةٍ تظهر وفي أيّ مجموعة (القناع ثم الصلاحية، نفس الدالتين
  // القائمتين لا فحصاً موازياً)؛ هنا فقط نُلبس كل مفتاح شاشةٍ أيقونته وتسميته
  // المحليّتين — دمجٌ لِما عُرِّف أعلاه بالفعل، لا تعريفٌ مزدوج. `[]` حين لا
  // بيان لهذا القالب (`general`)، فلا يستهلكها أحد.
  const manifestLinkMeta: Record<string, { label: string; icon: React.ReactNode }> = {
    dashboard: { label: "الرئيسية", icon: <Home className="h-4 w-4" /> },
    "client-books": { label: "دفاتر عملائي", icon: <BookOpenCheck className="h-4 w-4" /> },
    "accounting-journal-entry": { label: "قيد اليومية", icon: <ArrowLeftRight className="h-4 w-4" /> },
    settings: { label: "الإعدادات", icon: <SettingsIcon className="h-4 w-4" /> },
  };
  ([
    ...accountingLinks, ...salesLinksAll, ...customersLinks, ...purchasesLinksAll,
    ...importLinksAll, ...inventoryLinksAll, ...financeLinks, ...reportsLinksAll,
    ...userManagementLinks, ...afterSalesLinksAll,
  ] as { view: AppView; label: string; icon: React.ReactNode }[]).forEach((l) => {
    if (!manifestLinkMeta[String(l.view)]) manifestLinkMeta[String(l.view)] = { label: l.label, icon: l.icon };
  });
  // «الرئيسية» و«دفاتر عملائي» كانتا مقصورتين على المدير بلا مدخل في كتالوج
  // الصلاحيات — القاعدة نفسها هنا كي لا تنقلب متاحةً للجميع بمجرّد دخولها البيان.
  const shellSections = buildShellSections(shell, template, modules, can, user.role, ["dashboard", "client-books"], isManager);
  // الإعدادات تظهر مرّةً: إن كانت مجموعةً في البيان (دفتر عميل) لا تتكرّر كزرٍّ
  // عامٍّ أسفل القائمة.
  const manifestCoversSettings = shellSections.some((g) => g.views.includes("settings"));

  // فتح المجموعة التي تحتوي الشاشة النشطة تلقائياً.
  useEffect(() => {
    const inAny = (links: NavLink[]) => links.some((l) => l.view === activeView);
    if (inAny(salesLinks)) setSalesExpanded(true);
    if (inAny(customersLinks)) setCustomersExpanded(true);
    if (inAny(purchasesLinks)) setPurchasesExpanded(true);
    if (inAny(inventoryLinks)) setInventoryExpanded(true);
    if (inAny(importLinks)) setImportExpanded(true);
    if (inAny(financeLinks)) setFinanceExpanded(true);
    if (activeView.startsWith("accounting-") || activeView === "property-rental") setAccountingExpanded(true);
    if (inAny(afterSalesLinks)) setAfterSalesExpanded(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView]);

  // ISSUE #83: يفتح مجموعة البيان التي تحوي الشاشة النشطة — بمفتاحها (id) لا
  // بفهرسها، فترتيب البيان لا يقفز بالمستخدم عند تبديل الشاشة.
  useEffect(() => {
    if (!shell) return;
    const owner = shellSections.find((g) => g.views.includes(activeView));
    if (owner) setManifestExpanded((prev) => (prev[owner.id] ? prev : { ...prev, [owner.id]: true }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, shell]);


  // A5: تبديل «وضع المحاسب». الأثر فوري ومرئي — المحاسبة تُفتح، والمبيعات
  // والاستيراد يُطويان — كي يرى المستخدم ما فعله زرّه لا أن يثق به.
  // عرضٌ فقط: لا صلاحية تتغيّر، ولا مسار، ولا بند يظهر أو يختفي.
  const toggleAccountantMode = () => {
    const next = !accountantMode;
    setAccountantMode(next);
    writeAccountantMode(next);
    if (next) {
      setAccountingExpanded(true);
      setSalesExpanded(false);
      setImportExpanded(false);
    }
    clientLogger.info("sidebar.accountant_mode", { enabled: next });
  };

  const isViewActive = (view: string) => activeView === view;

  // T-PERM: صلاحية كل رابط من الخريطة الموحّدة (نفسها التي يحرس بها App.tsx
  // الدخول المباشر بالرابط) — لا نسخة ثانية داخل القائمة.
  const withPerms = <T extends { view: AppView; roles?: string[] }>(ls: T[]) =>
    ls.map((l) => ({ ...l, key: String(l.view), perm: permForView(String(l.view)) }));

  const SidebarContent = (isMobile: boolean = false) => {
    const showText = !isCollapsed || isMobile;

    // عارض مجموعة تنقّل رئيسية قابلة للطيّ (Section 9): تبويب كبير بأيقونته الخاصة
    // + أبناء. روابط newTab تفتح في تبويب جديد (G2). توحيد DRY لكل المجموعات.
    const renderGroup = (
      label: string,
      icon: React.ReactNode,
      expanded: boolean,
      toggle: () => void,
      links: NavLink[],
      children?: React.ReactNode,
    ) => (
      <div className="space-y-1">
        <button
          onClick={() => { if (isCollapsed && !isMobile) setIsCollapsed(false); toggle(); }}
          className={`flex items-center justify-between w-full p-3 rounded-lg transition-all ${expanded ? "bg-[var(--color-surface-3)] text-[var(--color-primary-emphasis)]" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
          title={label}
        >
          <div className="flex items-center">
            <span className="flex-shrink-0">{icon}</span>
            {showText && <span className="mr-3 font-semibold">{label}</span>}
          </div>
          {showText && (expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />)}
        </button>
        {expanded && showText && (
          <div className="mr-4 pr-4 border-r-2 border-[var(--color-border)] space-y-1 mt-1">
            {visibleLinks(withPerms(links), can, user.role).map((link) => (
              <button
                key={link.view + (link.path || "")}
                onClick={() => {
                  if (link.newTab && link.path) openInNewTab(link.path);
                  else {
                    setView(link.view);
                    // ISSUE #115 قصّة ٣٠ §٦: فتح الشاشة = اطّلاعٌ على ردودها المعروفة الآن.
                    if (link.view === "price-offers") markRfqRepliesSeen("local");
                    else if (link.view === "import-offers") markRfqRepliesSeen("import");
                    if (isMobile) setIsMobileMenuOpen(false);
                  }
                }}
                className={`flex items-center gap-2 w-full p-2 text-sm rounded-md transition-all ${isViewActive(link.view) && !link.newTab ? "text-[var(--color-primary-emphasis)] font-bold bg-[var(--color-surface-3)]" : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}
                title={link.newTab ? `${link.label} (تبويب جديد)` : link.label}
              >
                <span className="flex-shrink-0">{link.icon}</span>
                <span className="flex-1 text-right">{link.label}</span>
                {!!link.badge && (
                  <span
                    className="mr-1 inline-flex h-4 min-w-4 flex-shrink-0 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold leading-none text-white"
                    title={`${link.badge} ردّاً جديداً`}
                  >
                    {link.badge}
                  </span>
                )}
                {link.newTab && <ExternalLink className="h-3 w-3 opacity-60 flex-shrink-0" />}
              </button>
            ))}
            {children}
          </div>
        )}
      </div>
    );

    // A5: المحاسبة مجموعةٌ واحدة تُبنى مرة وتُوضع في أحد موضعين — أول القائمة في
    // «وضع المحاسب»، وموضعها المعتاد خلافه. نسخة واحدة لا اثنتان تفترقان لاحقاً.
    const accountingGroup = groupVisible(withPerms(accountingLinks), can, user.role)
      ? renderGroup("المحاسبة", <Calculator className="h-5 w-5 flex-shrink-0" />, accountingExpanded, () => setAccountingExpanded(!accountingExpanded), accountingLinks)
      : null;

    // ISSUE #83: بيان الشريط — يُرسَم بدلاً من مجموعات القالب اليدوية أدناه حين
    // يوجد بيانٌ لهذا القالب (`general` بلا بيان: `shellSections` أصلاً `[]`،
    // ولا يُستهلَك هذا المتغيّر من الفرع الذي يرسم الشريط اليدوي كما هو). نفس
    // `renderGroup` — لا رسمَ ثانياً، ولا نمطاً مكرّراً.
    const manifestGroupIcons: Record<string, React.ReactNode> = {
      home: <Home className="h-5 w-5 flex-shrink-0" />,
      clients: <BookOpenCheck className="h-5 w-5 flex-shrink-0" />,
      fees: <Receipt className="h-5 w-5 flex-shrink-0" />,
      treasury: <Landmark className="h-5 w-5 flex-shrink-0" />,
      "office-accounting": <Calculator className="h-5 w-5 flex-shrink-0" />,
      reports: <ReportsIcon className="h-5 w-5 flex-shrink-0" />,
      office: <Building2 className="h-5 w-5 flex-shrink-0" />,
      entry: <FileSignature className="h-5 w-5 flex-shrink-0" />,
      "receipt-payment": <Banknote className="h-5 w-5 flex-shrink-0" />,
      parties: <Users className="h-5 w-5 flex-shrink-0" />,
      accounts: <BookMarked className="h-5 w-5 flex-shrink-0" />,
      declarations: <ClipboardList className="h-5 w-5 flex-shrink-0" />,
      settings: <SettingsIcon className="h-5 w-5 flex-shrink-0" />,
    };
    const manifestSections = shellSections.map((g) => {
      const links: NavLink[] = g.views.map((v) => {
        const meta = manifestLinkMeta[v];
        return { view: v as AppView, label: meta?.label ?? v, icon: meta?.icon ?? <FileText className="h-4 w-4" /> };
      });
      return (
        <React.Fragment key={g.id}>
          {renderGroup(
            term(g.label_term ?? g.id),
            manifestGroupIcons[g.id] ?? <FileText className="h-5 w-5 flex-shrink-0" />,
            !!manifestExpanded[g.id],
            () => setManifestExpanded((prev) => ({ ...prev, [g.id]: !prev[g.id] })),
            links,
          )}
        </React.Fragment>
      );
    });

    return (
      <div className="flex flex-col h-full bg-[var(--color-surface-2)] border-l border-[var(--color-border)] transition-all duration-300 relative">
        {/* M5-T2: Header بنمط الأصيل */}
        <div className={`p-2 h-12 border-b border-[var(--color-border)] flex items-center ${isCollapsed && !isMobile ? 'justify-center' : 'justify-between'} bg-[var(--color-surface)]`}>
          <div className="flex items-center overflow-hidden">
            <LogoIcon className="h-6 w-6 text-[var(--color-primary)] flex-shrink-0" />
            {showText && <span className="mr-2 text-sm font-bold text-[var(--color-text)] truncate">K.T.R.A</span>}
            {/* THA-110: شارة الوضع السهل — لونٌ هادئ يقول «أنت هنا» بلا إعادة
                تلوين الواجهة (إعادة التلوين خارج نطاق المهمة بنصّ المالك). */}
            {isSimpleMode && showText && (
              <span className="mr-2 flex-shrink-0 whitespace-nowrap rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
                الوضع السهل
              </span>
            )}
          </div>
          {isMobile && (
            <button onClick={() => setIsMobileMenuOpen(false)} className="p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] rounded" title="إغلاق القائمة" aria-label="إغلاق القائمة">
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Navigation بنمط الأصيل */}
        <nav
          className="flex-1 overflow-y-auto p-1 space-y-0.5"
          style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}
        >
          <style>{`.scrollbar-hide::-webkit-scrollbar { display: none; }`}</style>

          {/* THA-110: الوضع السهل — قائمة مسطّحة بلا مجموعات، مرشّحة بنفس دالة
              الصلاحيات (`visibleLinks`) فلا يظهر بندٌ لا يملكه المستخدم. شرطٌ
              واحد يفصلها عن القائمة المتقدمة أدناه، وتلك تبقى كما كانت حرفياً. */}
          {isSimpleMode ? (
            visibleLinks(withPerms(simpleLinks), can, user.role, uiMode).map((link) => (
              // T5: «؟» شقيقةُ الزرّ لا ابنته — زرٌّ داخل زرٍّ لا يصحّ، وكانت
              // ضغطة الشرح ستفتح الشاشة بدل أن تشرحها. وتختفي مع النصّ حين
              // تنكمش القائمة إلى أيقوناتها.
              <div key={link.view} data-simple-nav className="flex items-center gap-1">
                <button
                  onClick={() => { setView(link.view); if (isMobile) setIsMobileMenuOpen(false); }}
                  className={`flex items-center flex-1 min-w-0 p-3 rounded-lg transition-all ${isViewActive(link.view) ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
                  title={link.label}
                >
                  {link.icon}
                  {showText && <span className="mr-3 text-right flex-1 font-semibold">{link.label}</span>}
                </button>
                {showText && <FieldHint hint={link.hint} align="end" />}
              </div>
            ))
          ) : (<>

          {user.isSuperAdmin && (
            <div className="mb-2 rounded-lg border border-blue-200 bg-blue-50/70 p-1 dark:border-blue-900 dark:bg-blue-950/20">
              <button type="button"
                onClick={() => { if (isCollapsed && !isMobile) setIsCollapsed(false); setPlatformExpanded(!platformExpanded); }}
                className="flex w-full items-center justify-between rounded-md p-2 text-blue-800 hover:bg-blue-100 dark:text-blue-300 dark:hover:bg-blue-900/30"
                aria-expanded={platformExpanded}>
                <span className="flex items-center gap-2"><ShieldCheck className="h-5 w-5" />{showText && <span className="font-bold">إدارة المنصة</span>}</span>
                {showText && (platformExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />)}
              </button>
              {platformExpanded && showText && (
                <div className="mt-1 space-y-1 border-r border-blue-200 pr-3 dark:border-blue-900">
                  <button type="button" onClick={() => { setView("super-admin"); if (isMobile) setIsMobileMenuOpen(false); }}
                    className={`flex w-full items-center gap-2 rounded-md p-2 text-sm ${isViewActive("super-admin") ? "bg-blue-600 text-white" : "text-blue-800 hover:bg-blue-100 dark:text-blue-300 dark:hover:bg-blue-900/30"}`}>
                    <Gauge className="h-4 w-4" /> لوحة السوبر أدمن
                  </button>
                  <button type="button" onClick={() => { setView("development-notes"); if (isMobile) setIsMobileMenuOpen(false); }}
                    className={`flex w-full items-center gap-2 rounded-md p-2 text-sm ${isViewActive("development-notes") ? "bg-blue-600 text-white" : "text-blue-800 hover:bg-blue-100 dark:text-blue-300 dark:hover:bg-blue-900/30"}`}>
                    <TableProperties className="h-4 w-4" /> ملاحظات التطوير
                  </button>
                  {/* T-EXTACCT: طريق العودة لقشرة المكتب — «العودة للوحة المنصة»
                      رحلة ذهاب وإياب، فمن خرج منها يجدها هنا حيث خرج. */}
                  {user.accountType === "legal_accountant" && (
                    <button type="button"
                      onClick={() => {
                        enterOfficeShell();
                        clientLogger.info("accountant.shell_switched", { to: "office" });
                        window.location.assign("/office");
                      }}
                      className="flex w-full items-center gap-2 rounded-md p-2 text-sm text-blue-800 hover:bg-blue-100 dark:text-blue-300 dark:hover:bg-blue-900/30">
                      <Scale className="h-4 w-4" /> العودة لواجهة المكتب
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ISSUE #83: بيان الشريط — حين يوجد بيانٌ لهذا القالب يُرسَم الشريط
              **منه** بدلاً من مجموعات القالب اليدوية أدناه (المصدر الجذري الذي
              فتحته التذكرة: مجموعاتٌ مكتوبةٌ لتاجر، والقالب يحذف منها فيبقى
              هيكلٌ مثقوب). `general` بلا بيان (`shell` هنا `null` — القيمة
              نفسها التي بناها `usePermissions()`): الفرع القائم أدناه **حرفاً
              بحرف بلا لمسة واحدة**. */}
          {shell ? (
            manifestSections
          ) : (<>
          {/* 1) الرئيسية — ملخص مؤشرات الشركة للمدير فقط (T-DASHPERIOD) */}
          {isManager && (
            <button
              onClick={() => { setView("dashboard"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("dashboard") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="الرئيسية"
            >
              <Home className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1 font-semibold">الرئيسية</span>}
            </button>
          )}

          {/* ISSUE #65: «دفاتر عملائي» — بابُ مكتب المحاسبة إلى دفاتر زبائنه.
              فوق كل شيء لأنه أول ما يقصده صاحب المكتب، ومشروطٌ بقالب المكتب
              وحده: فتح دفاترٍ لعملاء عملٌ مكتبيّ لا معنى له في شركةٍ تجارية. */}
          {isManager && template === "accounting_firm" && (
            <button
              onClick={() => { setView("client-books"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("client-books") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="دفاتر عملائي"
            >
              <BookOpenCheck className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1 font-semibold">دفاتر عملائي</span>}
            </button>
          )}

          {/* A5: «وضع المحاسب» — المحاسبة أول القائمة بعد الرئيسية. */}
          {accountantMode && accountingGroup}

          {/* 2) المبيعات */}
          {groupVisible(withPerms(salesLinks), can, user.role) &&
            renderGroup("المبيعات", <ShoppingCart className="h-5 w-5 flex-shrink-0" />, salesExpanded, () => setSalesExpanded(!salesExpanded), salesLinks)}

          {/* 3) العملاء */}
          {groupVisible(withPerms(customersLinks), can, user.role) &&
            renderGroup("العملاء", <Users className="h-5 w-5 flex-shrink-0" />, customersExpanded, () => setCustomersExpanded(!customersExpanded), customersLinks)}

          {/* 4) المشتريات */}
          {groupVisible(withPerms(purchasesLinks), can, user.role) &&
            renderGroup("المشتريات", <ShoppingBag className="h-5 w-5 flex-shrink-0" />, purchasesExpanded, () => setPurchasesExpanded(!purchasesExpanded), purchasesLinks)}

          {/* 5) الاستيراد — مجموعة مستقلة عن المخزون. */}
          {canAccessImport && groupVisible(withPerms(importLinks), can, user.role) &&
            renderGroup("الاستيراد", <Download className="h-5 w-5 flex-shrink-0" />, importExpanded, () => setImportExpanded(!importExpanded), importLinks)}

          {/* 6) المخزون */}
          {groupVisible(withPerms(inventoryLinks), can, user.role) &&
            renderGroup("المخزون", <Warehouse className="h-5 w-5 flex-shrink-0" />, inventoryExpanded, () => setInventoryExpanded(!inventoryExpanded), inventoryLinks)}

          {/* 7) المالية */}
          {groupVisible(withPerms(financeLinks), can, user.role) &&
            renderGroup("المالية", <Landmark className="h-5 w-5 flex-shrink-0" />, financeExpanded, () => setFinanceExpanded(!financeExpanded), financeLinks)}

          {/* المحاسبة — محفوظة للوصول الكامل للعمليات المحاسبية (خارج تبسيط Section 9، لا تُكسر ميزة).
              A5: موضعها المعتاد — تنتقل لأول القائمة في «وضع المحاسب» وحده. */}
          {!accountantMode && accountingGroup}

          {/* 8) التقارير — كل تقرير يفتح في تبويبه الخاص (G2) */}
          {groupVisible(withPerms(reportsLinks), can, user.role) &&
            renderGroup("التقارير", <ReportsIcon className="h-5 w-5 flex-shrink-0" />, reportsExpanded, () => setReportsExpanded(!reportsExpanded), reportsLinks)}
          </>)}

          <button
            onClick={() => { setView("gallery"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("gallery") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
            title="صالة الصور"
          >
            <GalleryIcon className="h-5 w-5 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">صالة الصور</span>}
          </button>

          {/* THA-108: «مصاريفي الشخصية» لم تعد بنداً هنا — دفتر الجيب ليس شاشة
              شركة، وموضعه بين «صناديق الكاش» و«فواتير الشراء» كان يوحي بأنه
              مصروف شركة. صار داخل «حسابي» (بطاقة المستخدم أسفل القائمة). */}

          {/* T-EXTACCT: الشركة التجارية لها تبويب واحد لا أكثر — مَن المحاسب
              الماسك ملفنا، وماذا طلب، وما الصلاحيات التي منحناه. لا تصير الشركة
              التجارية محاسباً قانونياً، وشاشات المكتب ليست من شأنها. */}
          {permissions.has("admin.members.manage") && moduleAllowsView("company-accountant-engagements", modules) && (
            <button
              onClick={() => { setView("company-accountant-engagements"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("company-accountant-engagements") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="واجهة المحاسب القانوني"
            >
              <ShieldCheck className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1">واجهة المحاسب القانوني</span>}
            </button>
          )}

          {/* THA-45: سجل الأجهزة الحساسة — وحدة مرخّصة. مُلحَق في آخر قسم
              الوحدات المرخّصة: بلا ترخيص لا يظهر البند أصلاً، وبلا صلاحية
              العرض لا يظهر ولو كانت الوحدة مرخّصة.
              THA-24: حين تُرخَّص «خدمة ما بعد البيع» أيضاً ينتقل البند إلى
              قسمها أدناه — بندٌ واحد لا اثنان. */}
          {permissions.has("devices.registry.view") && devicesPlacement === "standalone" &&
            !hiddenByTemplate("sensitive-devices") && (
            <button
              onClick={() => { setView("sensitive-devices"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("sensitive-devices") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="تسجيل وتتبع الأجهزة الحساسة"
            >
              <ShieldAlert className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1">الأجهزة الحساسة</span>}
            </button>
          )}

          {/* THA-24: خدمة ما بعد البيع — قسم وحدةٍ مرخّصة، مُلحَق آخر أقسام
              الوحدات. الترخيص يُفحَص هنا مرة واحدة، والصلاحية داخل كل بند. */}
          {moduleAllowsView("after-sales", modules) &&
            groupVisible(withPerms(afterSalesLinks), can, user.role) &&
            renderGroup("خدمة ما بعد البيع", <Wrench className="h-5 w-5 flex-shrink-0" />, afterSalesExpanded, () => setAfterSalesExpanded(!afterSalesExpanded), afterSalesLinks)}

          {/* ST-3: «متجري» — واجهة الشركة العامة. بندٌ مستقل لا داخل «الإعدادات»
              لأنه ليس ضبطاً بل قناة بيع يفتحها صاحبها ويشارك رابطها؛ ولأن
              `store.manage` مفتاح مستقل يُمنح لمن يدير المتجر وحده. وبلا هذه
              الصلاحية لا يظهر: المتجر واجهة الشركة للعالم لا إعدادٌ يعبث به كل
              عضو. **بندٌ واحد** — كان مكرّراً حرفياً حتى فحص ST-4. */}
          {permissions.has("store.manage") && !hiddenByTemplate("store-settings") && (
            <button
              onClick={() => { setView("store-settings"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("store-settings") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="متجري — الواجهة العامة لمنتجاتك"
            >
              <Store className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1">متجري</span>}
            </button>
          )}

          {/* ISSUE #83: حين تحمل مجموعات البيان «الإعدادات» (دفتر عميل) لا يتكرّر
              الزرّ العام أسفل القائمة — رابطٌ واحد للشاشة لا اثنان. */}
          {!manifestCoversSettings && (
          <button
            onClick={() => { setView("settings"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("settings") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
            title="الإعدادات"
          >
            <SettingsIcon className="h-5 w-5 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">الإعدادات</span>}
          </button>
          )}

          {/* task16 E19: إدارة الموظفين */}
          <div className="space-y-0.5">
            <button
              onClick={() => { if (isCollapsed && !isMobile) setIsCollapsed(false); setUserManagementExpanded(!userManagementExpanded); }}
              className={`flex items-center justify-between w-full p-2 text-sm rounded ${userManagementExpanded ? "bg-[var(--color-surface-2)] text-[var(--color-primary-emphasis)]" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="إدارة الموظفين"
            >
              <div className="flex items-center">
                <Users className="h-4 w-4 flex-shrink-0" />
                {showText && <span className="mr-2">إدارة الموظفين</span>}
              </div>
              {showText && (userManagementExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
            </button>
            {userManagementExpanded && showText && (
              <div className="mr-3 pr-2 border-r border-[var(--color-border)] space-y-0.5 mt-0.5">
                {visibleLinks(withPerms(userManagementLinks), can, user.role).map(link => (
                  <button
                    key={link.view}
                    onClick={() => { setView(link.view); if (isMobile) setIsMobileMenuOpen(false); }}
                    className={`flex items-center w-full p-2 text-sm rounded-md transition-all ${isViewActive(link.view) ? "text-[var(--color-primary-emphasis)] font-bold bg-[var(--color-surface-3)]" : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}
                  >
                    <span className="ml-2">{link.icon}</span>
                    {link.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => { setView("about-us"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("about-us") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
            title="من نحن"
          >
            <Info className="h-5 w-5 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">من نحن</span>}
          </button>

          <button
            onClick={() => { setView("contact"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("contact") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
            title="تواصل معنا"
          >
            <Users className="h-5 w-5 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">تواصل معنا</span>}
          </button>

          {/* 8) إدارة المهام — في الأسفل تماماً (Section 9) */}
          <div className="mt-2 pt-2 border-t border-[var(--color-border)]">
            <button
              onClick={() => { setView(can("hr.tasks.manage") ? "task-management" : "tasks"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("task-management") || isViewActive("tasks") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="إدارة المهام"
            >
              <TasksIcon className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1 font-semibold">{can("hr.tasks.manage") ? "إدارة المهام" : "مهامي"}</span>}
            </button>
          </div>
          </>)}
        </nav>

        {/* User Profile */}
        <div className="p-4 border-t border-[var(--color-border)] bg-[var(--color-surface-2)]">
          {/* THA-110: مبدّل الواجهة — **ظاهر دائماً وفي الوضعين**، لأن طريق
              العودة يجب ألا يمرّ بشاشةٍ يخفيها القناع نفسه: ضغطةٌ واحدة تكفي
              للرجوع من حيث ما كان المستخدم. */}
          <button
            type="button"
            onClick={() => setUiMode(isSimpleMode ? 'advanced' : 'simple')}
            aria-pressed={isSimpleMode}
            className={`flex items-center w-full p-2 mb-2 rounded-lg border transition-all ${isCollapsed && !isMobile ? "justify-center" : ""} ${isSimpleMode ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300" : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"}`}
            title={isSimpleMode ? "العودة للواجهة المتقدمة — كل الشاشات" : "الواجهة السهلة — الأساسيات فقط"}
          >
            {isSimpleMode
              ? <LayoutGrid className="h-4 w-4 flex-shrink-0" />
              : <Sparkles className="h-4 w-4 flex-shrink-0" />}
            {showText && (
              <span className="mr-2 flex-1 text-right text-xs font-semibold">
                {isSimpleMode ? "الواجهة المتقدمة" : "الواجهة السهلة"}
              </span>
            )}
          </button>

          {/* A5: «وضع المحاسب» — مبدّل ترتيبٍ لصاحب هذا المتصفح وحده، في ذيل
              القائمة حيث تعيش تفضيلات العرض لا بنود التنقّل.
              THA-110: يختفي في الوضع السهل — ترتيبُ قائمةٍ لا وجود لها.
              ISSUE #83: ويختفي حين يُرسَم الشريط من بيان القالب — لا مجموعة
              محاسبةٍ يدوية يعيد ترتيبها، فيصير الزرّ تحكّماً بلا أثر. */}
          {!isSimpleMode && !shell && (
          <button
            type="button"
            onClick={toggleAccountantMode}
            aria-pressed={accountantMode}
            className={`flex items-center w-full p-2 mb-2 rounded-lg transition-all ${isCollapsed && !isMobile ? "justify-center" : ""} ${accountantMode ? "bg-[var(--color-surface-3)] text-[var(--color-primary-emphasis)]" : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"}`}
            title="وضع المحاسب — يضع المحاسبة أول القائمة"
          >
            <Calculator className="h-4 w-4 flex-shrink-0" />
            {showText && <span className="mr-2 flex-1 text-right text-xs font-semibold">وضع المحاسب</span>}
            {showText && (
              <span className={`flex items-center w-8 h-4 p-0.5 rounded-full flex-shrink-0 transition-colors ${accountantMode ? "bg-[var(--color-primary)] justify-end" : "bg-[var(--color-border)] justify-start"}`}>
                <span className="w-3 h-3 rounded-full bg-white shadow-sm" />
              </span>
            )}
          </button>
          )}
          {/* THA-108: بطاقة المستخدم هي مدخل «حسابي» — ما يخصّ الشخص يُدخَل من
              اسمه لا من قائمة الشركة، وهو موضعه في المنتجات المحترفة (Odoo:
              My Profile خلف صورة المستخدم · Zoho Books: حساب المستخدم منفصل عن
              إعدادات المنظّمة). **خارج شرط الوضع السهل** فيبقى دفتر المستخدم
              الشخصي في متناوله في الوضعين. */}
          <button
            type="button"
            onClick={() => { setView("my-account"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full ${isCollapsed && !isMobile ? 'justify-center' : ''} p-2 rounded-xl transition-all ${isViewActive("my-account") ? "bg-[var(--color-surface-3)] ring-1 ring-[var(--color-primary)]" : "hover:bg-[var(--color-surface-3)]"}`}
            title="حسابي — صفحتك الشخصية ومصاريفك الخاصة"
            aria-current={isViewActive("my-account") ? "page" : undefined}
          >
            <div className="w-10 h-10 rounded-full bg-[var(--color-primary)] flex items-center justify-center text-[var(--color-primary-foreground)] font-bold flex-shrink-0 shadow-sm">
              {user.name?.charAt(0)}
            </div>
            {showText && (
              <div className="mr-3 overflow-hidden text-right">
                <p className="text-sm font-bold text-[var(--color-text)] truncate">{user.name}</p>
                <p className="text-[10px] text-[var(--color-primary)] font-medium tracking-wider">
                  {user.isSuperAdmin ? "سوبر أدمن المنصة" : user.role}
                </p>
                <p className="text-[10px] text-[var(--color-text-muted)]">حسابي ومصاريفي الشخصية</p>
              </div>
            )}
          </button>
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Mobile Top Bar */}
      <header className="ktra-app-chrome md:hidden fixed top-0 left-0 right-0 h-14 bg-[var(--color-surface)] border-b border-[var(--color-border)] flex items-center justify-between px-4 z-40">
        <button onClick={() => setIsMobileMenuOpen(true)} className="p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)] rounded-full transition-colors">
          <Menu className="h-6 w-6" />
        </button>
        <div className="flex items-center">
          <span className="font-bold text-[var(--color-text)]">K.T.R.A</span>
          <LogoIcon className="h-6 w-6 mr-2 text-[var(--color-primary)]" />
        </div>
        <div className="w-10" />
      </header>

      {/* Mobile Drawer Overlay */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 bg-black/60 z-50 md:hidden backdrop-blur-sm transition-opacity" onClick={() => setIsMobileMenuOpen(false)} />
      )}

      {/* Mobile Sidebar */}
      <aside className={`ktra-sidebar fixed top-0 right-0 bottom-0 w-72 z-50 transform transition-transform duration-300 md:hidden ${isMobileMenuOpen ? "translate-x-0" : "translate-x-full"}`}>
        {SidebarContent(true)}
      </aside>

      {/* Desktop Sidebar Wrapper */}
      <aside className={`ktra-sidebar hidden md:flex flex-col sticky top-0 h-screen transition-all duration-300 z-30 ${isCollapsed ? "w-20" : "w-64"}`}>

        {/* المبدل (Toggle Button) - الموضع الجديد المحسن */}
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="absolute -left-4 top-20 w-8 h-8 bg-[var(--color-surface)] border-2 border-[var(--color-border)] rounded-full flex items-center justify-center shadow-lg z-50 text-[var(--color-primary)] hover:bg-[var(--color-primary)] hover:text-[var(--color-primary-foreground)] hover:border-[var(--color-primary)] transition-all duration-200 group"
          title={isCollapsed ? "فتح القائمة" : "إغلاق القائمة"}
        >
          {isCollapsed ? (
            <ChevronLeft className="h-5 w-5 group-hover:-translate-x-0.5 transition-transform" />
          ) : (
            <ChevronRight className="h-5 w-5 group-hover:translate-x-0.5 transition-transform" />
          )}
        </button>

        {SidebarContent(false)}
      </aside>

      <div className="ktra-sidebar-spacer h-14 md:hidden" />
    </>
  );
};

export default Sidebar;
