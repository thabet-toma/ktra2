/**
 * T-REPORTS — «قسم التقارير»: فهرس واحد لكل تقارير المنصة.
 *
 * الفهرس مصدره الخادم (`/api/reports/`) فما يظهر هنا هو ما يملك المستخدم
 * صلاحيته فعلاً، ويتوسّع تلقائياً مع كل تقرير جديد بلا لمس الواجهة.
 * تُضاف إليه التقارير التي لها شاشات مخصّصة قائمة (ميزان المراجعة، قائمة
 * الدخل…) كروابط — لا نعيد بناءها في الجدول العام.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BarChart3, ExternalLink, RefreshCw, Search } from "lucide-react";

import { reportsApi } from "../../services/reportsApi";
import type { ReportCategoryDto, ReportSummaryDto } from "../../utils/reportFormat";
import { KitDocumentShell } from "../kit";
import type { KitTab, KitToolbarAction } from "../kit";

/**
 * تقارير لها شاشاتها المخصّصة أصلاً — تُفهرَس هنا ولا تُعاد كتابتها.
 * `permission` يطابق مفاتيح `utils/viewPermissions` الخادمية.
 */
const SCREEN_REPORTS: Record<string, { title: string; description: string; path: string }[]> = {
  accounting: [
    {
      title: "ميزان المراجعة",
      description: "أرصدة كل الحسابات مدينةً ودائنة مع فحص التوازن.",
      path: "/accounting/trial-balance",
    },
    {
      title: "قائمة الدخل",
      description: "الإيرادات والمصروفات وصافي الربح للفترة.",
      path: "/accounting/income-statement",
    },
    {
      title: "الميزانية العمومية",
      description: "الأصول والخصوم وحقوق الملكية في تاريخ محدّد.",
      path: "/accounting/balance-sheet",
    },
    {
      title: "دفتر الأستاذ",
      description: "حركة حساب واحد مفصَّلة برصيد متدرّج.",
      path: "/accounting/general-ledger",
    },
    {
      title: "تقرير ضريبة القيمة المضافة",
      description: "المخرجات والمدخلات وصافي الضريبة المستحقة.",
      path: "/accounting/vat-report",
    },
  ],
  sales: [
    {
      title: "أرباح الفواتير",
      description: "ربح كل فاتورة بيع وهامشها بعد التكلفة.",
      path: "/invoice-profits",
    },
  ],
  inventory: [
    {
      title: "تكلفة المنتجات",
      description: "تفصيل تكلفة المنتج ومصادرها.",
      path: "/product-cost",
    },
  ],
  import: [
    {
      title: "تكلفة الوصول (Landed Cost)",
      description: "توزيع مصاريف الاستيراد على منتجات الشحنة.",
      path: "/accounting/landed-cost",
    },
  ],
  hr: [
    {
      title: "أوقات الفريق",
      description: "الوقت المستغرق لكل موظف وعدد مهامه.",
      path: "/reports-team",
    },
  ],
};

interface CardProps {
  title: string;
  description: string;
  badge?: string;
  onOpen: () => void;
}

const ReportCard: React.FC<CardProps> = ({ title, description, badge, onOpen }) => (
  <button
    type="button"
    onClick={onOpen}
    className="flex flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-start transition-colors hover:border-[var(--color-accent,#2563eb)]"
  >
    <span className="flex items-center gap-2 text-sm font-semibold text-[var(--color-text)]">
      {title}
      {badge && (
        <span className="rounded px-1.5 py-0.5 text-[10px] font-normal text-[var(--color-text-muted)] ring-1 ring-[var(--color-border)]">
          {badge}
        </span>
      )}
    </span>
    <span className="text-xs leading-5 text-[var(--color-text-muted)]">{description}</span>
  </button>
);

export const ReportsHubPage: React.FC = () => {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<ReportCategoryDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCategories(await reportsApi.catalog());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل فهرس التقارير");
      setCategories([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const matches = useCallback(
    (title: string, description: string) => {
      const needle = search.trim().toLowerCase();
      if (!needle) return true;
      return `${title} ${description}`.toLowerCase().includes(needle);
    },
    [search],
  );

  /** الفئات المعروضة = تقارير الخادم + الشاشات المخصّصة، بعد تطبيق البحث. */
  const sections = useMemo(() => {
    const serverKeys = new Set(categories.map((c) => c.key));
    const extraOnly = Object.keys(SCREEN_REPORTS).filter((k) => !serverKeys.has(k));
    const order = [...categories.map((c) => c.key), ...extraOnly];
    const labelOf = (key: string) =>
      categories.find((c) => c.key === key)?.label
      ?? {
        accounting: "المحاسبة", sales: "المبيعات", inventory: "المخزون",
        import: "الاستيراد", hr: "الموارد البشرية",
      }[key]
      ?? key;

    return order.map((key) => {
      const apiReports = (categories.find((c) => c.key === key)?.reports ?? [])
        .filter((r: ReportSummaryDto) => matches(r.title, r.description));
      const screenReports = (SCREEN_REPORTS[key] ?? [])
        .filter((r) => matches(r.title, r.description));
      return { key, label: labelOf(key), apiReports, screenReports };
    }).filter((s) => s.apiReports.length > 0 || s.screenReports.length > 0);
  }, [categories, matches]);

  const totalCount = useMemo(
    () => sections.reduce((n, s) => n + s.apiReports.length + s.screenReports.length, 0),
    [sections],
  );

  const content = (
    <div className="flex flex-col gap-4">
      {error && <div className="ktra-banner ktra-banner--err">{error}</div>}
      <div className="ktra-field" style={{ maxWidth: "320px" }}>
        <label className="ktra-field-label">بحث في التقارير</label>
        <input
          type="text"
          className="ktra-input"
          placeholder="اسم التقرير أو وصفه…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <p className="text-sm text-[var(--color-text-muted)]">جارٍ تحميل الفهرس…</p>
      ) : sections.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          {search.trim() ? "لا تقرير يطابق البحث." : "لا تقارير متاحة لصلاحياتك."}
        </p>
      ) : (
        sections.map((section) => (
          <section key={section.key} className="flex flex-col gap-2">
            <h2 className="text-sm font-bold text-[var(--color-text)]">{section.label}</h2>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
              {section.apiReports.map((report) => (
                <ReportCard
                  key={report.key}
                  title={report.title}
                  description={report.description}
                  onOpen={() => navigate(`/reports/${report.key}`)}
                />
              ))}
              {section.screenReports.map((report) => (
                <ReportCard
                  key={report.path}
                  title={report.title}
                  description={report.description}
                  badge="شاشة مخصّصة"
                  onOpen={() => navigate(report.path)}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );

  const actions: KitToolbarAction[] = [
    { key: "refresh", label: "تحديث", icon: <RefreshCw />, onClick: () => void load() },
  ];

  const tabs: KitTab[] = [
    { key: "catalog", label: "كل التقارير", content },
  ];

  return (
    <div>
      <KitDocumentShell
        title="التقارير"
        actions={actions}
        header={<></>}
        tabs={tabs}
        status={
          <span className="ktra-status-item">
            <BarChart3 className="w-3 h-3" />
            {totalCount} تقرير
          </span>
        }
      >
        <></>
      </KitDocumentShell>
    </div>
  );
};

export default ReportsHubPage;
