import React, { useEffect, useState } from "react";
import {
  Building2, CheckCircle2, CirclePause, ClipboardList, RefreshCw,
  ShieldCheck, Users,
} from "lucide-react";

import { getPlatformDashboard, type PlatformDashboardData } from "../../services/platformAdminApi";
import type { AppView } from "../../types";


interface Props {
  onNavigate: (view: AppView) => void;
}

const statusLabel = (status: string) => ({
  Active: "فعالة",
  Trial: "تجريبية",
  Suspended: "موقوفة",
}[status] || status);

export const SuperAdminDashboard: React.FC<Props> = ({ onNavigate }) => {
  const [data, setData] = useState<PlatformDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getPlatformDashboard()
      .then(setData)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "تعذّر تحميل لوحة المنصة"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading && !data) {
    return <div className="p-8 text-center aseel-text-soft" role="status">جارٍ تحميل لوحة المنصة…</div>;
  }
  if (error && !data) {
    return (
      <div className="p-8 text-center" role="alert">
        <p className="text-red-600">{error}</p>
        <button type="button" onClick={load} className="aseel-btn aseel-btn--primary mt-3">إعادة المحاولة</button>
      </div>
    );
  }
  if (!data) return null;

  const cards = [
    { label: "إجمالي الشركات", value: data.companies.total, icon: Building2, tone: "text-blue-600 bg-blue-50 dark:bg-blue-950/30" },
    { label: "الشركات الفعالة", value: data.companies.active, icon: CheckCircle2, tone: "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30" },
    { label: "الشركات الموقوفة", value: data.companies.suspended, icon: CirclePause, tone: "text-amber-600 bg-amber-50 dark:bg-amber-950/30" },
    { label: "المستخدمون النشطون", value: data.users.active, icon: Users, tone: "text-sky-600 bg-sky-50 dark:bg-sky-950/30" },
  ];

  return (
    <main className="p-4 md:p-6" dir="rtl">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white">
            <ShieldCheck className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-xl font-bold text-[var(--color-text)]">لوحة تحكم السوبر أدمن</h1>
            <p className="text-sm aseel-text-soft">نظرة تشغيلية على المنصة والشركات، منفصلة عن لوحة الشركة</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => onNavigate("development-notes")} className="aseel-btn aseel-btn--primary">
            <ClipboardList className="h-4 w-4" aria-hidden="true" /> ملاحظات التطوير
          </button>
          <button type="button" onClick={load} className="aseel-iconbtn" title="تحديث" aria-label="تحديث لوحة المنصة">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </header>

      {error && <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div>}

      <section aria-label="مؤشرات المنصة" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, tone }) => (
          <article key={label} className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className={`flex h-10 w-10 items-center justify-center rounded-md ${tone}`}><Icon className="h-5 w-5" /></span>
            <div><p className="text-xs aseel-text-soft">{label}</p><p className="text-2xl font-bold text-[var(--color-text)]">{value}</p></div>
          </article>
        ))}
      </section>

      <section className="mt-5 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-3">
          <div><h2 className="font-bold text-[var(--color-text)]">الشركات</h2><p className="text-xs aseel-text-soft">{data.memberships} عضوية عبر المنصة</p></div>
          <span className="text-xs aseel-text-soft">تجريبية: {data.companies.trial} · مستخدمون: {data.users.total}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-[var(--color-surface-2)] aseel-text-soft"><tr>
              <th className="px-3 py-2 text-right">الشركة</th><th className="px-3 py-2 text-right">الخطة</th>
              <th className="px-3 py-2 text-right">الحالة</th><th className="px-3 py-2 text-center">الأعضاء</th>
              <th className="px-3 py-2 text-center">الاستيراد</th><th className="px-3 py-2 text-right">تاريخ الإنشاء</th>
            </tr></thead>
            <tbody>
              {data.company_rows.length === 0 ? (
                <tr><td colSpan={6} className="px-3 py-10 text-center aseel-text-soft">لا توجد شركات بعد</td></tr>
              ) : data.company_rows.map((company) => (
                <tr key={company.id} className="border-t border-[var(--color-border)] hover:bg-[var(--color-surface-2)]">
                  <td className="px-3 py-2 font-semibold text-[var(--color-text)]">{company.name}</td>
                  <td className="px-3 py-2">{company.plan}</td><td className="px-3 py-2">{statusLabel(company.status)}</td>
                  <td className="px-3 py-2 text-center">{company.member_count}</td>
                  <td className="px-3 py-2 text-center">{company.import_enabled ? "مفعّل" : "غير مفعّل"}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{new Date(company.created_at).toLocaleDateString("ar-EG")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
};
