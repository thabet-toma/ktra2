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
  Calculator, BookMarked, Scale, BookOpen, Banknote,
  CalendarDays, CalendarX, ArrowLeftRight, Boxes, BarChart3, Building2,
  ShoppingCart, Receipt, Ship, Truck, TrendingUp, ClipboardList,
  ShoppingBag, Landmark, Warehouse, Download, ExternalLink, Home,
} from 'lucide-react';
import { openInNewTab } from "../utils/openInNewTab";
import { useCompany } from "../contexts/CompanyContext";
import { useTenantSettings } from "../hooks/useTenantSettings";


interface SidebarProps {
  user: User;
  activeView: AppView;
  setView: (view: AppView, targetId?: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ user, activeView, setView }) => {
  // صلاحية الاستيراد للشركة النشطة (تتفاعل مع تبديل الشركة) — لا تعتمد على علم ثابت من تسجيل الدخول.
  const { canAccessImport } = useCompany();
  const { identity } = useTenantSettings();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  // Phase 5 (Section 9): مجموعات تنقّل رئيسية كبيرة، كلٌّ بأيقونته الخاصة.
  const [salesExpanded, setSalesExpanded] = useState(false);
  const [customersExpanded, setCustomersExpanded] = useState(false);
  const [purchasesExpanded, setPurchasesExpanded] = useState(false);
  const [inventoryExpanded, setInventoryExpanded] = useState(false);
  const [importExpanded, setImportExpanded] = useState(false);
  const [financeExpanded, setFinanceExpanded] = useState(false);
  const [reportsExpanded, setReportsExpanded] = useState(false);
  const [accountingExpanded, setAccountingExpanded] = useState(false);
  const [userManagementExpanded, setUserManagementExpanded] = useState(false);

  const accountingLinks: { view: AppView; label: string; icon: React.ReactNode }[] = [
    { view: "accounting-coa", label: "شجرة الحسابات", icon: <BookMarked className="h-4 w-4" /> },
    { view: "accounting-journals", label: "دفتر اليومية (القيود)", icon: <FileText className="h-4 w-4" /> },
    { view: "accounting-cheques", label: "الشيكات", icon: <Banknote className="h-4 w-4" /> },
    { view: "accounting-general-ledger", label: "الأستاذ العام", icon: <BookOpen className="h-4 w-4" /> },
    { view: "accounting-trial-balance", label: "ميزان المراجعة", icon: <Scale className="h-4 w-4" /> },
    { view: "accounting-vat-report", label: "تقرير ضريبة القيمة المضافة", icon: <Receipt className="h-4 w-4" /> },
    { view: "accounting-landed-cost", label: "تقرير التكلفة المستوردة", icon: <Ship className="h-4 w-4" /> },
    { view: "accounting-fiscal-periods", label: "الفترات المالية", icon: <CalendarDays className="h-4 w-4" /> },
    { view: "accounting-exchange-rates", label: "أسعار الصرف", icon: <ArrowLeftRight className="h-4 w-4" /> },
    { view: "accounting-balance-sheet", label: "الميزانية العمومية", icon: <BarChart3 className="h-4 w-4" /> },
    { view: "accounting-income-statement", label: "قائمة الدخل", icon: <TrendingUp className="h-4 w-4" /> },
    { view: "accounting-vat-statements", label: "كشوف ضريبة القيمة المضافة", icon: <ClipboardList className="h-4 w-4" /> },
    { view: "accounting-year-end-close", label: "الإغلاق السنوي", icon: <CalendarX className="h-4 w-4" /> },
    { view: "property-rental", label: "تأجير العقارات والعدادات", icon: <Building2 className="h-4 w-4" /> },
  ];

  const userManagementLinks = [
    { view: "users" as AppView, label: "قائمة المستخدمين", icon: <UsersIcon className="h-5 w-5" />, roles: ['manager'] },
    { view: "activity-log" as AppView, label: "سجل النشاط", icon: <History className="h-5 w-5" />, roles: ['manager'] },
    { view: "attendance" as AppView, label: "الحضور والغياب", icon: <AttendanceIcon className="h-5 w-5" />, roles: ['manager', 'employee', 'procurement'] },
    { view: "employee-notes" as AppView, label: "ملاحظات الموظفين", icon: <NoteIcon className="h-5 w-5" />, roles: ['manager'] },
    { view: "points-management" as AppView, label: "إدارة النقاط", icon: <PointsIcon className="h-5 w-5" />, roles: ['manager'] },
    { view: "points-history" as AppView, label: "سجل نقاطي", icon: <PointsIcon className="h-5 w-5" />, roles: ['employee', 'procurement', 'manager'] },
  ];

  type NavLink = { view: AppView; label: string; icon: React.ReactNode; path?: string; newTab?: boolean; roles?: string[] };

  // 2) المبيعات — إعدادات المبيعات آخراً (Section 9).
  const salesLinks: NavLink[] = [
    { view: "sales-invoices", label: "فواتير المبيعات", icon: <FileText className="h-4 w-4" /> },
    { view: "sales-quotations", label: "العروض", icon: <FileText className="h-4 w-4" /> },
    { view: "credit-debit-notes", label: "الإشعارات المدينة/الدائنة", icon: <FileText className="h-4 w-4" /> },
    { view: "sales-return", label: "مرجع البيع", icon: <FileText className="h-4 w-4" /> },
    { view: "invoice-profits", label: "أرباح الفواتير", icon: <TrendingUp className="h-4 w-4" /> },
    { view: "sales-settings", label: "إعدادات المبيعات", icon: <SettingsIcon className="h-4 w-4" /> },
  ];

  // 3) العملاء
  const customersLinks: NavLink[] = [
    { view: "sales-customers", label: "العملاء", icon: <Users className="h-4 w-4" /> },
    { view: "sales-customer-payments", label: "دفعات العملاء", icon: <Banknote className="h-4 w-4" /> },
  ];

  // 4) المشتريات
  const purchasesLinks: NavLink[] = [
    { view: "purchase-invoices", label: "فواتير الشراء", icon: <NoteIcon className="h-4 w-4" /> },
    { view: "price-offers", label: "عروض الأسعار", icon: <FileText className="h-4 w-4" /> },
    { view: "purchase-return", label: "مرجع الشراء", icon: <FileText className="h-4 w-4" /> },
    { view: "supplier-payments", label: "سندات الصرف للموردين", icon: <Banknote className="h-4 w-4" /> },
    { view: "purchase-settings", label: "إعدادات الشراء", icon: <SettingsIcon className="h-4 w-4" /> },
    { view: "supplier-management", label: "الموردين", icon: <UsersIcon className="h-4 w-4" /> },
  ];

  // 5) الاستيراد
  const importLinks: NavLink[] = [
    { view: "international-invoices", label: "الفواتير الدولية", icon: <FileText className="h-4 w-4" /> },
    { view: "deals-management", label: "الصفقات", icon: <Handshake className="h-4 w-4" /> },
    { view: "shipments-management", label: "الشحنات", icon: <Ship className="h-4 w-4" /> },
    { view: "old-invoices", label: "أرشيف الفواتير", icon: <History className="h-4 w-4" /> },
    { view: "local-shipping", label: "النقل المحلي", icon: <Truck className="h-4 w-4" /> },
    { view: "customs-clearance", label: "التخليص الجمركي", icon: <FileText className="h-4 w-4" /> },
    { view: "import-flow", label: "رحلة الاستيراد", icon: <Package className="h-4 w-4" /> },
  ];

  // 6) المخزون — الأصناف (شجرة، T-N3) + أرصدة + حركات. (إعدادات المخزون غير مبنية — مُدرجة بخارطة الطريق.)
  const inventoryLinks: NavLink[] = [
    { view: "stock-levels", label: "أرصدة المخزون", icon: <BarChart3 className="h-4 w-4" /> },
    { view: "items-management", label: "الأصناف", icon: <Boxes className="h-4 w-4" /> },
    { view: "stock-movements", label: "حركات المخزون", icon: <ArrowLeftRight className="h-4 w-4" /> },
    { view: "product-cost", label: "تكلفة المنتجات", icon: <BarChart3 className="h-4 w-4" /> },
    { view: "warehouses", label: "المستودعات", icon: <Warehouse className="h-4 w-4" /> },
    { view: "warehouse-transfer", label: "تحويل بين المستودعات", icon: <Truck className="h-4 w-4" /> },
    { view: "stocktake", label: "الجرد", icon: <ClipboardList className="h-4 w-4" /> },
  ];

  // 7) المالية — (البنوك غير مبنية كشاشة مستقلة — مُدرجة بخارطة الطريق).
  const financeLinks: NavLink[] = [
    { view: "cash-boxes", label: "صناديق الكاش", icon: <Banknote className="h-4 w-4" /> },
    { view: "accounting-cheques", label: "الشيكات", icon: <Receipt className="h-4 w-4" /> },
  ];

  // 8) التقارير — كل تقرير يفتح في تبويبه الخاص (G2).
  const reportsLinks: NavLink[] = [
    { view: "reports", label: "التقارير العامة", icon: <ReportsIcon className="h-4 w-4" />, path: "/reports", newTab: true },
    { view: "stock-movements", label: "تقرير حركة صنف", icon: <ArrowLeftRight className="h-4 w-4" />, path: "/stock-movements", newTab: true },
    { view: "accounting-trial-balance", label: "ميزان المراجعة", icon: <Scale className="h-4 w-4" />, path: "/accounting/trial-balance", newTab: true },
    { view: "accounting-income-statement", label: "قائمة الدخل", icon: <TrendingUp className="h-4 w-4" />, path: "/accounting/income-statement", newTab: true },
    { view: "accounting-balance-sheet", label: "الميزانية العمومية", icon: <BarChart3 className="h-4 w-4" />, path: "/accounting/balance-sheet", newTab: true },
    { view: "accounting-vat-report", label: "تقرير ض.ق.م", icon: <Receipt className="h-4 w-4" />, path: "/accounting/vat-report", newTab: true },
  ];

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView]);


  const isViewActive = (view: string) => activeView === view;

  // دالة للتحقق من صلاحيات المستخدم
  const hasAccess = (requiredRole: string) => {
    return user.role === requiredRole;
  };

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
            {links.filter((l) => !l.roles || l.roles.includes(user.role)).map((link) => (
              <button
                key={link.view + (link.path || "")}
                onClick={() => {
                  if (link.newTab && link.path) openInNewTab(link.path);
                  else { setView(link.view); if (isMobile) setIsMobileMenuOpen(false); }
                }}
                className={`flex items-center gap-2 w-full p-2 text-sm rounded-md transition-all ${isViewActive(link.view) && !link.newTab ? "text-[var(--color-primary-emphasis)] font-bold bg-[var(--color-surface-3)]" : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}
                title={link.newTab ? `${link.label} (تبويب جديد)` : link.label}
              >
                <span className="flex-shrink-0">{link.icon}</span>
                <span className="flex-1 text-right">{link.label}</span>
                {link.newTab && <ExternalLink className="h-3 w-3 opacity-60 flex-shrink-0" />}
              </button>
            ))}
            {children}
          </div>
        )}
      </div>
    );

    return (
      <div className="flex flex-col h-full bg-[var(--color-surface-2)] border-l border-[var(--color-border)] transition-all duration-300 relative">
        {/* M5-T2: Header بنمط الأصيل */}
        <div className={`p-2 h-12 border-b border-[var(--color-border)] flex items-center ${isCollapsed && !isMobile ? 'justify-center' : 'justify-between'} bg-[var(--color-surface)]`}>
          <div className="flex items-center overflow-hidden">
            <LogoIcon className="h-6 w-6 text-[var(--color-primary)] flex-shrink-0" />
            {showText && <span className="mr-2 text-sm font-bold text-[var(--color-text)] truncate">K.T.R.A</span>}
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

          {/* 1) الرئيسية */}
          {hasAccess('manager') && (
            <button
              onClick={() => { setView("dashboard"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("dashboard") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="الرئيسية"
            >
              <Home className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1 font-semibold">الرئيسية</span>}
            </button>
          )}

          {/* 2) المبيعات */}
          {(user.role === 'manager' || user.role === 'procurement') &&
            renderGroup("المبيعات", <ShoppingCart className="h-5 w-5 flex-shrink-0" />, salesExpanded, () => setSalesExpanded(!salesExpanded), salesLinks)}

          {/* 3) العملاء */}
          {(user.role === 'manager' || user.role === 'procurement') &&
            renderGroup("العملاء", <Users className="h-5 w-5 flex-shrink-0" />, customersExpanded, () => setCustomersExpanded(!customersExpanded), customersLinks)}

          {/* 4) المشتريات */}
          {(user.role === 'manager' || user.role === 'procurement') &&
            renderGroup("المشتريات", <ShoppingBag className="h-5 w-5 flex-shrink-0" />, purchasesExpanded, () => setPurchasesExpanded(!purchasesExpanded), purchasesLinks)}

          {/* 5) الاستيراد — مجموعة مستقلة عن المخزون. */}
          {(user.role === 'manager' || user.role === 'procurement') && canAccessImport &&
            renderGroup("الاستيراد", <Download className="h-5 w-5 flex-shrink-0" />, importExpanded, () => setImportExpanded(!importExpanded), importLinks)}

          {/* 6) المخزون */}
          {(user.role === 'manager' || user.role === 'procurement') &&
            renderGroup("المخزون", <Warehouse className="h-5 w-5 flex-shrink-0" />, inventoryExpanded, () => setInventoryExpanded(!inventoryExpanded), inventoryLinks)}

          {/* 7) المالية */}
          {hasAccess('manager') &&
            renderGroup("المالية", <Landmark className="h-5 w-5 flex-shrink-0" />, financeExpanded, () => setFinanceExpanded(!financeExpanded), financeLinks)}

          {/* المحاسبة — محفوظة للوصول الكامل للعمليات المحاسبية (خارج تبسيط Section 9، لا تُكسر ميزة) */}
          {hasAccess('manager') &&
            renderGroup("المحاسبة", <Calculator className="h-5 w-5 flex-shrink-0" />, accountingExpanded, () => setAccountingExpanded(!accountingExpanded), accountingLinks)}

          {/* 8) التقارير — كل تقرير يفتح في تبويبه الخاص (G2) */}
          {hasAccess('manager') &&
            renderGroup("التقارير", <ReportsIcon className="h-5 w-5 flex-shrink-0" />, reportsExpanded, () => setReportsExpanded(!reportsExpanded), reportsLinks)}

          <button
            onClick={() => { setView("gallery"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("gallery") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
            title="صالة الصور"
          >
            <GalleryIcon className="h-5 w-5 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">صالة الصور</span>}
          </button>

          <button
            onClick={() => { setView("settings"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("settings") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
            title="الإعدادات"
          >
            <SettingsIcon className="h-5 w-5 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">الإعدادات</span>}
          </button>

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
                {userManagementLinks.filter(l => l.roles.includes(user.role)).map(link => (
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
              onClick={() => { setView(user.role === 'manager' ? "task-management" : "tasks"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("task-management") || isViewActive("tasks") ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"}`}
              title="إدارة المهام"
            >
              <TasksIcon className="h-5 w-5 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1 font-semibold">{user.role === 'manager' ? "إدارة المهام" : "مهامي"}</span>}
            </button>
          </div>
        </nav>

        {/* User Profile */}
        <div className="p-4 border-t border-[var(--color-border)] bg-[var(--color-surface-2)]">
          <div className={`flex items-center ${isCollapsed && !isMobile ? 'justify-center' : ''} p-2 rounded-xl`}>
            <div className="w-10 h-10 rounded-full bg-[var(--color-primary)] flex items-center justify-center text-[var(--color-primary-foreground)] font-bold flex-shrink-0 shadow-sm">
              {user.name?.charAt(0)}
            </div>
            {showText && (
              <div className="mr-3 overflow-hidden">
                <p className="text-sm font-bold text-[var(--color-text)] truncate">{user.name}</p>
                <p className="text-[10px] text-[var(--color-primary)] font-medium uppercase tracking-wider">{user.role}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Mobile Top Bar */}
      <header className="aseel-app-chrome md:hidden fixed top-0 left-0 right-0 h-14 bg-[var(--color-surface)] border-b border-[var(--color-border)] flex items-center justify-between px-4 z-40">
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
      <aside className={`aseel-sidebar fixed top-0 right-0 bottom-0 w-72 z-50 transform transition-transform duration-300 md:hidden ${isMobileMenuOpen ? "translate-x-0" : "translate-x-full"}`}>
        {SidebarContent(true)}
      </aside>

      {/* Desktop Sidebar Wrapper */}
      <aside className={`aseel-sidebar hidden md:flex flex-col sticky top-0 h-screen transition-all duration-300 z-30 ${isCollapsed ? "w-20" : "w-64"}`}>

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

      <div className="aseel-sidebar-spacer h-14 md:hidden" />
    </>
  );
};

export default Sidebar;
