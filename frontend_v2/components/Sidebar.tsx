import React, { useState, useEffect } from "react";
import { User, AppView } from "../types";
import { LogoIcon } from "./icons/LogoIcon";
import { DashboardIcon } from "./icons/DashboardIcon";
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
  Calculator, BookMarked, Scale, BookOpen, Banknote
} from 'lucide-react';


interface SidebarProps {
  user: User;
  activeView: AppView;
  setView: (view: AppView) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ user, activeView, setView }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [procurementExpanded, setProcurementExpanded] = useState(false);
  const [accountingExpanded, setAccountingExpanded] = useState(false);
  const [userManagementExpanded, setUserManagementExpanded] = useState(false);

  const accountingLinks: { view: AppView; label: string; icon: React.ReactNode }[] = [
    { view: "accounting-coa", label: "شجرة الحسابات", icon: <BookMarked className="h-4 w-4" /> },
    { view: "accounting-journals", label: "دفتر اليومية (القيود)", icon: <FileText className="h-4 w-4" /> },
    { view: "accounting-cheques", label: "الشيكات", icon: <Banknote className="h-4 w-4" /> },
    { view: "accounting-general-ledger", label: "الأستاذ العام", icon: <BookOpen className="h-4 w-4" /> },
    { view: "accounting-trial-balance", label: "ميزان المراجعة", icon: <Scale className="h-4 w-4" /> },
  ];

  useEffect(() => {
    if (activeView.startsWith("accounting-")) setAccountingExpanded(true);
  }, [activeView]);

  const userManagementLinks = [
    { view: "users" as AppView, label: "قائمة المستخدمين", icon: <UsersIcon className="h-5 w-5" />, roles: ['manager'] },
    { view: "attendance" as AppView, label: "الحضور والغياب", icon: <AttendanceIcon className="h-5 w-5" />, roles: ['manager', 'employee', 'procurement'] },
    { view: "employee-notes" as AppView, label: "ملاحظات الموظفين", icon: <NoteIcon className="h-5 w-5" />, roles: ['manager'] },
    { view: "points-management" as AppView, label: "إدارة النقاط", icon: <PointsIcon className="h-5 w-5" />, roles: ['manager'] },
    { view: "points-history" as AppView, label: "سجل نقاطي", icon: <PointsIcon className="h-5 w-5" />, roles: ['employee', 'procurement', 'manager'] },
  ];

  const procurementLinks = [
    { view: "purchase-invoices" as AppView, label: "فواتير الشراء", icon: <NoteIcon className="h-5 w-5" /> },
    { view: "old-invoices" as AppView, label: "أرشيف الفواتير", icon: <History className="h-5 w-5" /> },
    { view: "price-offers" as AppView, label: "عروض الأسعار", icon: <FileText className="h-5 w-5" /> },
    { view: "deals-management" as AppView, label: "إدارة الصفقات", icon: <Handshake className="h-5 w-5" /> },
    { view: "items-management" as AppView, label: "الأصناف", icon: <DashboardIcon className="h-5 w-5" /> },
    { view: "supplier-management" as AppView, label: "الموردين", icon: <UsersIcon className="h-5 w-5" /> },
    { view: "shipments-management" as AppView, label: "إدارة الشحنات", icon: <Package className="h-5 w-5" /> },
  ];

  const financeLinks = [
    { view: "cash-boxes" as AppView, label: "صناديق الكاش", icon: <FileText className="h-5 w-5" /> },
  ];


  const isViewActive = (view: string) => activeView === view;

  // دالة للتحقق من صلاحيات المستخدم
  const hasAccess = (requiredRole: string) => {
    return user.role === requiredRole;
  };

  const SidebarContent = (isMobile: boolean = false) => {
    const showText = !isCollapsed || isMobile;

    return (
      <div className="flex flex-col h-full bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 transition-all duration-300 relative shadow-lg">
        {/* Header */}
        <div className={`p-4 h-16 border-b border-gray-200 dark:border-gray-700 flex items-center ${isCollapsed && !isMobile ? 'justify-center' : 'justify-between'}`}>
          <div className="flex items-center overflow-hidden">
            <LogoIcon className="h-8 w-8 text-blue-600 flex-shrink-0" />
            {showText && <span className="mr-2 text-xl font-bold dark:text-white truncate">K.T.R.A</span>}
          </div>
          {isMobile && (
            <button onClick={() => setIsMobileMenuOpen(false)} className="p-2 text-gray-500 hover:bg-gray-100 rounded-lg">
              <X className="h-6 w-6" />
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav
          className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-hide"
          style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}
        >
          <style>{`.scrollbar-hide::-webkit-scrollbar { display: none; }`}</style>

          {/* الرئيسية - للمدير فقط */}
          {hasAccess('manager') && (
            <button
              onClick={() => { setView("dashboard"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("dashboard") ? "bg-blue-600 text-white shadow-md" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
              title="الرئيسية"
            >
              <DashboardIcon className="h-6 w-6 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1">الرئيسية</span>}
            </button>
          )}

          <button
            onClick={() => { setView(user.role === 'manager' ? "task-management" : "tasks"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("task-management") || isViewActive("tasks") ? "bg-blue-600 text-white shadow-md" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
            title="المهام"
          >
            <TasksIcon className="h-6 w-6 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">{user.role === 'manager' ? "إدارة المهام" : "مهامي"}</span>}
          </button>

          {/* إدارة الموظفين */}
          <div className="space-y-1">
            <button
              onClick={() => { if (isCollapsed && !isMobile) setIsCollapsed(false); setUserManagementExpanded(!userManagementExpanded); }}
              className={`flex items-center justify-between w-full p-3 rounded-lg ${userManagementExpanded ? "bg-blue-50 dark:bg-blue-900/20 text-blue-600" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
              title="إدارة الموظفين"
            >
              <div className="flex items-center">
                <Users className="h-6 w-6 flex-shrink-0" />
                {showText && <span className="mr-3">إدارة الموظفين</span>}
              </div>
              {showText && (userManagementExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />)}
            </button>
            {userManagementExpanded && showText && (
              <div className="mr-4 pr-4 border-r-2 border-gray-100 dark:border-gray-700 space-y-1 mt-1">
                {userManagementLinks.filter(l => l.roles.includes(user.role)).map(link => (
                  <button
                    key={link.view}
                    onClick={() => { setView(link.view); if (isMobile) setIsMobileMenuOpen(false); }}
                    className={`flex items-center w-full p-2 text-sm rounded-md transition-all ${isViewActive(link.view) ? "text-blue-600 font-bold bg-blue-50 dark:bg-blue-900/20" : "text-gray-500 hover:text-blue-600"}`}
                  >
                    <span className="ml-2">{link.icon}</span>
                    {link.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* المشتريات */}
          {(user.role === 'manager' || user.role === 'procurement') && (
            <div className="space-y-1">
              <button
                onClick={() => { if (isCollapsed && !isMobile) setIsCollapsed(false); setProcurementExpanded(!procurementExpanded); }}
                className={`flex items-center justify-between w-full p-3 rounded-lg ${procurementExpanded ? "bg-blue-50 dark:bg-blue-900/20 text-blue-600" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
                title="المشتريات"
              >
                <div className="flex items-center">
                  <Package className="h-6 w-6 flex-shrink-0" />
                  {showText && <span className="mr-3">المشتريات</span>}
                </div>
                {showText && (procurementExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />)}
              </button>
              {procurementExpanded && showText && (
                <div className="mr-4 pr-4 border-r-2 border-gray-100 dark:border-gray-700 space-y-1 mt-1">
                  {procurementLinks.map(link => (
                    <button
                      key={link.view}
                      onClick={() => { setView(link.view); if (isMobile) setIsMobileMenuOpen(false); }}
                      className={`flex items-center w-full p-2 text-sm rounded-md transition-all ${isViewActive(link.view) ? "text-blue-600 font-bold bg-blue-50 dark:bg-blue-900/20" : "text-gray-500 hover:text-blue-600"}`}
                    >
                      <span className="ml-2">{link.icon}</span>
                      {link.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* المحاسبة — قيود SQL (Django) — للمدير فقط */}
          {hasAccess('manager') && (
            <div className="space-y-1">
              <button
                onClick={() => { if (isCollapsed && !isMobile) setIsCollapsed(false); setAccountingExpanded(!accountingExpanded); }}
                className={`flex items-center justify-between w-full p-3 rounded-lg ${accountingExpanded ? "bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
                title="المحاسبة"
              >
                <div className="flex items-center">
                  <Calculator className="h-6 w-6 flex-shrink-0" />
                  {showText && <span className="mr-3">المحاسبة</span>}
                </div>
                {showText && (accountingExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />)}
              </button>
              {accountingExpanded && showText && (
                <div className="mr-4 pr-4 border-r-2 border-gray-100 dark:border-gray-700 space-y-1 mt-1">
                  {accountingLinks.map((link) => (
                    <button
                      key={link.view}
                      onClick={() => { setView(link.view); if (isMobile) setIsMobileMenuOpen(false); }}
                      className={`flex items-center w-full p-2 text-sm rounded-md transition-all ${isViewActive(link.view) || (link.view === "accounting-journals" && activeView === "accounting-journal-entry") ? "text-indigo-600 font-bold bg-indigo-50 dark:bg-indigo-900/20" : "text-gray-500 hover:text-indigo-600"}`}
                    >
                      <span className="ml-2">{link.icon}</span>
                      {link.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* المالية - للمدير فقط */}
          {hasAccess('manager') && (
            <div className="space-y-1">
              <button
                onClick={() => { setView("cash-boxes"); if (isMobile) setIsMobileMenuOpen(false); }}
                className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("cash-boxes") ? "bg-blue-600 text-white shadow-md" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
                title="المالية"
              >
                <div className="flex items-center">
                  <FileText className="h-6 w-6 flex-shrink-0" />
                  {showText && <span className="mr-3 text-right flex-1">المالية</span>}
                </div>
              </button>
            </div>
          )}

          {/* التقارير - للمدير فقط */}
          {hasAccess('manager') && (
            <button
              onClick={() => { setView("reports"); if (isMobile) setIsMobileMenuOpen(false); }}
              className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("reports") ? "bg-blue-600 text-white shadow-md" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
              title="التقارير"
            >
              <ReportsIcon className="h-6 w-6 flex-shrink-0" />
              {showText && <span className="mr-3 text-right flex-1">التقارير</span>}
            </button>
          )}

          <button
            onClick={() => { setView("gallery"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("gallery") ? "bg-blue-600 text-white shadow-md" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
            title="صالة الصور"
          >
            <GalleryIcon className="h-6 w-6 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">صالة الصور</span>}
          </button>

          <button
            onClick={() => { setView("settings"); if (isMobile) setIsMobileMenuOpen(false); }}
            className={`flex items-center w-full p-3 rounded-lg transition-all ${isViewActive("settings") ? "bg-blue-600 text-white shadow-md" : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"}`}
            title="الإعدادات"
          >
            <SettingsIcon className="h-6 w-6 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">الإعدادات</span>}
          </button>

          <button
            onClick={() => { window.history.pushState({}, '', '/about-us'); window.dispatchEvent(new PopStateEvent('popstate')); if (isMobile) setIsMobileMenuOpen(false); }}
            className="flex items-center w-full p-3 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50"
            title="من نحن"
          >
            <Info className="h-6 w-6 flex-shrink-0" />
            {showText && <span className="mr-3 text-right flex-1">من نحن</span>}
          </button>
        </nav>

        {/* User Profile */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/20">
          <div className={`flex items-center ${isCollapsed && !isMobile ? 'justify-center' : ''} p-2 rounded-xl`}>
            <div className="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold flex-shrink-0 shadow-sm">
              {user.name?.charAt(0)}
            </div>
            {showText && (
              <div className="mr-3 overflow-hidden">
                <p className="text-sm font-bold dark:text-white truncate">{user.name}</p>
                <p className="text-[10px] text-blue-500 font-medium uppercase tracking-wider">{user.role}</p>
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
      <header className="md:hidden fixed top-0 left-0 right-0 h-14 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between px-4 z-40">
        <button onClick={() => setIsMobileMenuOpen(true)} className="p-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 rounded-full transition-colors">
          <Menu className="h-6 w-6" />
        </button>
        <div className="flex items-center">
          <span className="font-bold dark:text-white">K.T.R.A</span>
          <LogoIcon className="h-6 w-6 mr-2 text-blue-600" />
        </div>
        <div className="w-10" />
      </header>

      {/* Mobile Drawer Overlay */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 bg-black/60 z-50 md:hidden backdrop-blur-sm transition-opacity" onClick={() => setIsMobileMenuOpen(false)} />
      )}

      {/* Mobile Sidebar */}
      <aside className={`fixed top-0 right-0 bottom-0 w-72 z-50 transform transition-transform duration-300 md:hidden ${isMobileMenuOpen ? "translate-x-0" : "translate-x-full"}`}>
        {SidebarContent(true)}
      </aside>

      {/* Desktop Sidebar Wrapper */}
      <aside className={`hidden md:flex flex-col sticky top-0 h-screen transition-all duration-300 z-30 ${isCollapsed ? "w-20" : "w-64"}`}>

        {/* المبدل (Toggle Button) - الموضع الجديد المحسن */}
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="absolute -left-4 top-20 w-8 h-8 bg-white dark:bg-gray-700 border-2 border-blue-100 dark:border-gray-600 rounded-full flex items-center justify-center shadow-lg z-50 text-blue-600 dark:text-blue-400 hover:bg-blue-600 hover:text-white dark:hover:bg-blue-500 transition-all duration-200 group"
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

      <div className="h-14 md:hidden" />
    </>
  );
};

export default Sidebar;