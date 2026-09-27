import React from "react";
import { ShieldCheck } from "lucide-react";
import { useLocation } from "react-router-dom";

import { AccountantsSection } from "./AccountantsSection";
import { AdminsSection } from "./AdminsSection";
import { AuditLogSection } from "./AuditLogSection";
import { CompaniesSection } from "./CompaniesSection";
import { CompanyPage } from "./CompanyPage";
import { HealthSection } from "./HealthSection";
import { OverviewSection } from "./OverviewSection";
import { PlansSection } from "./PlansSection";
import { SupportRequestsSection } from "./SupportRequestsSection";
import { CONSOLE_BASE } from "./consoleShared";

/** أقسام «إدارة المنصة» بمساراتها. للشريط الجانبي مرآةٌ بأيقونات (`Sidebar.tsx` —
 * `PLATFORM_CONSOLE_LINKS`): قسمٌ جديد يُضاف في الموضعين. */
export const CONSOLE_SECTIONS = [
  { key: "", label: "نظرة عامة" },
  { key: "companies", label: "الشركات" },
  { key: "plans", label: "الخطط والأسعار" },
  { key: "support-access", label: "طلبات الدخول للدعم" },
  { key: "accountants", label: "توثيق المحاسبين" },
  { key: "audit-log", label: "سجل التدقيق" },
  { key: "admins", label: "مديرو المنصة" },
  { key: "health", label: "صحة النظام" },
] as const;

export type ConsoleSectionKey = (typeof CONSOLE_SECTIONS)[number]["key"];

/** `/super-admin/companies/12` ← { section: "companies", companyId: 12 } */
export function parseConsolePath(pathname: string): { section: ConsoleSectionKey | null; companyId: number | null } {
  const rest = pathname.replace(/\/+$/, "").slice(CONSOLE_BASE.length).replace(/^\/+/, "");
  const [head = "", id] = rest.split("/");
  const section = CONSOLE_SECTIONS.find((item) => item.key === head)?.key ?? null;
  const companyId = section === "companies" && id && /^\d+$/.test(id) ? Number(id) : null;
  return { section, companyId };
}

/**
 * SA-5 — لوحة المنصة: عرضٌ واحد (`super-admin`) لكل `/super-admin/*`، والقسم من
 * المسار. الأقسام صفحاتٌ مستقلة بروابط تُحفظ وتُشارَك، لا صفحةٌ طويلة واحدة.
 * مسارٌ غير معروف تحت `/super-admin` يسقط على «نظرة عامة» بدل صفحة فارغة.
 */
export const SuperAdminConsole: React.FC = () => {
  const { pathname } = useLocation();
  const { section, companyId } = parseConsolePath(pathname);

  let body: React.ReactNode;
  if (section === "companies" && companyId !== null) body = <CompanyPage key={companyId} companyId={companyId} />;
  else if (section === "companies") body = <CompaniesSection />;
  else if (section === "plans") body = <PlansSection />;
  else if (section === "support-access") body = <SupportRequestsSection />;
  else if (section === "accountants") body = <AccountantsSection />;
  else if (section === "audit-log") body = <AuditLogSection />;
  else if (section === "admins") body = <AdminsSection />;
  else if (section === "health") body = <HealthSection />;
  else body = <OverviewSection />;

  return (
    <main className="p-4 md:p-6" dir="rtl">
      <header className="mb-5 flex items-center gap-3 border-b border-[var(--color-border)] pb-4">
        <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white">
          <ShieldCheck className="h-6 w-6" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text)]">لوحة تحكم السوبر أدمن</h1>
          <p className="text-sm ktra-text-soft">إدارة المنصة والشركات — منفصلة عن لوحة أي شركة</p>
        </div>
      </header>
      {body}
    </main>
  );
};
