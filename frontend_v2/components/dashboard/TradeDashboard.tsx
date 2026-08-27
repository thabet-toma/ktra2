import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  BookOpen,
  Boxes,
  FileInput,
  FileOutput,
  Handshake,
  Info,
  PackagePlus,
  ReceiptText,
  RefreshCw,
  Ship,
  ShoppingCart,
  TrendingDown,
  TrendingUp,
  WalletCards,
} from "lucide-react";

import { useCompany } from "../../contexts/CompanyContext";
import { fetchDashboard } from "../../services/dashboardApi";
import type {
  DashboardAlert,
  DashboardInvoice,
  DashboardInvoiceSummary,
} from "../../types/dashboard";
import type { AppView } from "../../types/common";
import type { DashboardData } from "../../types/dashboard";
import { formatDateLocalized } from "../../utils/formatDate";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { EmptyState, Spinner } from "../ui";

interface TradeDashboardProps {
  userName: string;
  onNavigate: (view: AppView) => void;
}

const baseMoney = (value: number) => formatMoney(value);

const INVOICE_STATUS: Record<string, string> = {
  draft: "مسودة",
  incomplete: "غير مكتملة",
  posted: "مرحّلة",
  completed: "مكتملة",
  deposit_paid: "دفعة أولى",
  partially_paid: "مدفوعة جزئياً",
  fully_paid: "مدفوعة",
  archived: "مؤرشفة",
};

export const TradeDashboard: React.FC<TradeDashboardProps> = ({
  userName,
  onNavigate,
}) => {
  const { currentCompany, canAccessImport } = useCompany();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchDashboard());
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "تعذّر تحميل لوحة التحكم");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, currentCompany?.TenantID]);

  if (loading) {
    return (
      <div className="flex min-h-[360px] items-center justify-center">
        <Spinner size="md" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <EmptyState
        icon={<AlertTriangle className="h-10 w-10" />}
        title="تعذّر تحميل بيانات الشركة"
        description="تحقق من الاتصال ثم أعد المحاولة. لم يتم عرض أي بيانات مخزنة من شركة أخرى."
        action={
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-[var(--radius-lg)] bg-[var(--color-primary)] px-4 py-2 text-sm font-semibold text-white"
          >
            إعادة المحاولة
          </button>
        }
      />
    );
  }

  const isNewCompany = data.is_new_company;
  const showImport = canAccessImport && !!data.import_operations;

  return (
    <main
      className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 p-4 md:p-6"
      dir="rtl"
      data-testid="business-dashboard"
    >
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="mb-1 text-xs font-semibold text-[var(--color-primary)]">
            {currentCompany?.CompanyName}
          </p>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">
            أهلاً {userName.split(" ")[0]}، هذه صورة أعمالك اليوم
          </h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            المؤشرات المالية والمبيعات والمشتريات من {formatDateLocalized(data.period.from)} إلى {formatDateLocalized(data.period.to)}، مع حالة المخزون الحالية
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center justify-center gap-2 self-start rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-primary)]"
        >
          <RefreshCw className="h-4 w-4" />
          تحديث البيانات
        </button>
      </header>

      {isNewCompany && <GettingStarted onNavigate={onNavigate} />}

      {data.alerts.length > 0 && (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" aria-label="تنبيهات تحتاج انتباهك">
          {data.alerts.map((alert) => (
            <div key={`${alert.title}-${alert.link}`}>
              <AlertCard alert={alert} onNavigate={onNavigate} />
            </div>
          ))}
        </section>
      )}

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6" aria-label="المؤشرات الرئيسية">
        <KpiCard icon={TrendingUp} label="إيرادات الفترة" value={baseMoney(data.financials.revenue)} note="بالعملة الأساسية" tone="success" />
        <KpiCard icon={TrendingDown} label="مصروفات الفترة" value={baseMoney(data.financials.expenses)} note="بالعملة الأساسية" tone="danger" />
        <KpiCard
          icon={WalletCards}
          label="صافي الربح"
          value={baseMoney(data.financials.net_profit)}
          note={data.financials.net_profit < 0 ? "صافي خسارة بالعملة الأساسية" : "بالعملة الأساسية بعد المصروفات"}
          tone={data.financials.net_profit < 0 ? "danger" : "primary"}
          onClick={() => onNavigate("accounting-income-statement")}
        />
        <KpiCard
          icon={ShoppingCart}
          label="فواتير المبيعات"
          value={data.sales_invoices.total}
          note={`${data.sales_invoices.posted} مرحلة · ${data.sales_invoices.draft} مسودة`}
          tone="primary"
          onClick={() => onNavigate("sales-invoices")}
        />
        <KpiCard
          icon={ReceiptText}
          label="فواتير المشتريات"
          value={data.purchase_invoices.total}
          note={`${data.purchase_invoices.posted} مكتملة · ${data.purchase_invoices.draft} مسودة`}
          tone="amber"
          onClick={() => onNavigate("purchase-invoices")}
        />
        <KpiCard
          icon={Boxes}
          label="قيمة المخزون"
          value={baseMoney(data.inventory.inventory_value)}
          note={`${data.inventory.in_stock} منتج · بالعملة الأساسية`}
          tone="violet"
          onClick={() => onNavigate("stock-levels")}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-12">
        <div className="grid gap-4 md:grid-cols-2 xl:col-span-8">
          <InvoicePanel
            title="آخر فواتير المبيعات"
            icon={FileOutput}
            summary={data.sales_invoices}
            emptyTitle="لم تُنشئ فواتير مبيعات بعد"
            emptyDescription="سجّل أول عملية بيع لتبدأ متابعة الإيرادات والذمم تلقائياً."
            actionLabel="إنشاء فاتورة بيع"
            view="sales-invoices"
            onNavigate={onNavigate}
          />
          <InvoicePanel
            title="آخر فواتير المشتريات"
            icon={FileInput}
            summary={data.purchase_invoices}
            emptyTitle="لم تُسجّل فواتير مشتريات بعد"
            emptyDescription="أضف فاتورة المورد لتحديث التكلفة والمخزون والحسابات."
            actionLabel="إضافة فاتورة شراء"
            view="purchase-invoices"
            onNavigate={onNavigate}
          />
        </div>

        <aside className="grid gap-4 md:grid-cols-2 xl:col-span-4 xl:grid-cols-1">
          <InventoryPanel data={data.inventory} onNavigate={onNavigate} />
          <AccountingPanel journals={data.accounting.journals_this_month} onNavigate={onNavigate} />
        </aside>
      </section>

      {showImport && data.import_operations && (
        <ImportOverview data={data.import_operations} onNavigate={onNavigate} />
      )}
    </main>
  );
};

function GettingStarted({ onNavigate }: { onNavigate: (view: AppView) => void }) {
  const steps = [
    { icon: PackagePlus, title: "أضف المنتجات", description: "عرّف المنتجات والأرصدة الافتتاحية", view: "items-management" as AppView },
    { icon: FileInput, title: "سجّل أول شراء", description: "أدخل فاتورة المورد وتكلفة البضاعة", view: "purchase-invoices" as AppView },
    { icon: FileOutput, title: "أنشئ أول مبيعة", description: "أصدر فاتورة وتابع الإيراد والتحصيل", view: "sales-invoices" as AppView },
  ];
  return (
    <section className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-primary)]/20 bg-[var(--color-primary)]/5 p-4 md:p-5">
      <div className="mb-4">
        <h2 className="text-base font-bold text-[var(--color-text)]">ابدأ تشغيل شركتك بثلاث خطوات</h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">ستتحول هذه اللوحة تلقائياً إلى مؤشرات حية فور تسجيل أول العمليات.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {steps.map((step, index) => (
          <button
            key={step.view}
            type="button"
            onClick={() => onNavigate(step.view)}
            className="flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-right transition-all hover:-translate-y-0.5 hover:border-[var(--color-primary)]/40 hover:shadow-sm"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
              <step.icon className="h-5 w-5" />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold text-[var(--color-primary)]">الخطوة {index + 1}</span>
              <span className="block text-sm font-bold text-[var(--color-text)]">{step.title}</span>
              <span className="block truncate text-xs text-[var(--color-text-muted)]">{step.description}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function KpiCard({ icon: Icon, label, value, note, tone, onClick }: {
  icon: React.FC<{ className?: string }>;
  label: string;
  value: string | number;
  note?: string;
  tone: "success" | "danger" | "primary" | "amber" | "violet";
  onClick?: () => void;
}) {
  const tones = {
    success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    danger: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
    primary: "bg-[var(--color-primary)]/10 text-[var(--color-primary)]",
    amber: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    violet: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  };
  const content = (
    <>
      <span className={`mb-4 inline-flex rounded-[var(--radius-lg)] p-2 ${tones[tone]}`}><Icon className="h-5 w-5" /></span>
      <strong className="block text-xl font-bold tabular-nums text-[var(--color-text)]">{value}</strong>
      <span className="mt-1 block text-xs font-medium text-[var(--color-text-muted)]">{label}</span>
      {note && <span className="mt-1 block text-[11px] text-[var(--color-text-muted)]">{note}</span>}
    </>
  );
  const className = "min-h-36 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-right transition-all hover:border-[var(--color-primary)]/30 hover:shadow-sm";
  return onClick ? <button type="button" onClick={onClick} className={className}>{content}</button> : <div className={className}>{content}</div>;
}

function InvoicePanel({ title, icon: Icon, summary, emptyTitle, emptyDescription, actionLabel, view, onNavigate }: {
  title: string;
  icon: React.FC<{ className?: string }>;
  summary: DashboardInvoiceSummary;
  emptyTitle: string;
  emptyDescription: string;
  actionLabel: string;
  view: AppView;
  onNavigate: (view: AppView) => void;
}) {
  return (
    <article className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold text-[var(--color-text)]"><Icon className="h-4 w-4 text-[var(--color-primary)]" />{title}</h2>
        <button type="button" onClick={() => onNavigate(view)} className="flex items-center gap-1 text-xs font-semibold text-[var(--color-primary)]">عرض الكل <ArrowLeft className="h-3 w-3" /></button>
      </div>
      {summary.recent.length ? (
        <div className="divide-y divide-[var(--color-border)]">
          {summary.recent.map((invoice) => (
            <div key={invoice.id}>
              <InvoiceRow invoice={invoice} />
            </div>
          ))}
        </div>
      ) : (
        <div className="flex min-h-48 flex-col items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-muted)]/55 px-5 py-6 text-center">
          <Icon className="mb-2 h-7 w-7 text-[var(--color-text-muted)]" />
          <p className="text-sm font-bold text-[var(--color-text)]">{emptyTitle}</p>
          <p className="mt-1 max-w-xs text-xs leading-5 text-[var(--color-text-muted)]">{emptyDescription}</p>
          <button type="button" onClick={() => onNavigate(view)} className="mt-3 rounded-[var(--radius-lg)] bg-[var(--color-primary)] px-3 py-2 text-xs font-semibold text-white">{actionLabel}</button>
        </div>
      )}
    </article>
  );
}

function InvoiceRow({ invoice }: { invoice: DashboardInvoice }) {
  return (
    <div className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-[var(--color-text)]">{invoice.invoice_number}</p>
        <p className="truncate text-xs text-[var(--color-text-muted)]">{invoice.partner_name || "بدون اسم"}</p>
      </div>
      <div className="shrink-0 text-left">
        <p className="text-sm font-bold tabular-nums text-[var(--color-text)]">{formatMoney(invoice.grand_total)} {invoice.currency_code}</p>
        <p className="text-[11px] text-[var(--color-text-muted)]">{INVOICE_STATUS[invoice.status] || invoice.status}</p>
      </div>
    </div>
  );
}

function InventoryPanel({ data, onNavigate }: { data: DashboardData["inventory"]; onNavigate: (view: AppView) => void }) {
  return (
    <article className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold text-[var(--color-text)]"><Boxes className="h-4 w-4 text-violet-500" />حالة المخزون</h2>
        <button type="button" onClick={() => onNavigate("stock-levels")} className="text-xs font-semibold text-[var(--color-primary)]">التفاصيل</button>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <MiniStat label="المنتجات" value={data.total_products} />
        <MiniStat label="منخفض" value={data.low_stock} warning={data.low_stock > 0} />
        <MiniStat label="نافد" value={data.out_of_stock} warning={data.out_of_stock > 0} />
      </div>
      {data.total_products === 0 ? (
        <button type="button" onClick={() => onNavigate("items-management")} className="mt-3 w-full rounded-[var(--radius-lg)] border border-dashed border-[var(--color-primary)]/40 bg-[var(--color-primary)]/5 px-3 py-3 text-xs font-semibold text-[var(--color-primary)]">إضافة أول منتج للمخزون</button>
      ) : data.low_stock_items.length > 0 ? (
        <div className="mt-3 space-y-2 border-t border-[var(--color-border)] pt-3">
          {data.low_stock_items.slice(0, 3).map((item) => (
            <div key={item.id} className="flex justify-between text-xs"><span className="truncate text-[var(--color-text-muted)]">{item.name_ar || item.sku}</span><span className="font-semibold text-rose-500">{formatQuantity(item.quantity_on_hand)} متبقٍ</span></div>
          ))}
        </div>
      ) : <p className="mt-3 text-xs text-emerald-600 dark:text-emerald-400">مستويات المخزون ضمن الحدود المحددة.</p>}
    </article>
  );
}

function AccountingPanel({ journals, onNavigate }: { journals: number; onNavigate: (view: AppView) => void }) {
  return (
    <article className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-center gap-3">
        <span className="rounded-[var(--radius-lg)] bg-[var(--color-primary)]/10 p-2 text-[var(--color-primary)]"><BookOpen className="h-5 w-5" /></span>
        <div><p className="text-xs text-[var(--color-text-muted)]">القيود المرحلة خلال الفترة</p><p className="text-xl font-bold text-[var(--color-text)]">{journals}</p></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button type="button" onClick={() => onNavigate("accounting-journals")} className="rounded-[var(--radius-lg)] bg-[var(--color-muted)] px-3 py-2 text-xs font-medium text-[var(--color-text)]">دفتر اليومية</button>
        <button type="button" onClick={() => onNavigate("accounting-trial-balance")} className="rounded-[var(--radius-lg)] bg-[var(--color-muted)] px-3 py-2 text-xs font-medium text-[var(--color-text)]">ميزان المراجعة</button>
      </div>
    </article>
  );
}

function ImportOverview({ data, onNavigate }: { data: NonNullable<DashboardData["import_operations"]>; onNavigate: (view: AppView) => void }) {
  return (
    <section data-testid="import-overview" className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between"><div><p className="text-xs font-semibold text-[var(--color-primary)]">وحدة الاستيراد</p><h2 className="text-sm font-bold text-[var(--color-text)]">ملخص العمليات الدولية</h2></div><BarChart3 className="h-5 w-5 text-[var(--color-text-muted)]" /></div>
      <div className="grid gap-3 sm:grid-cols-3">
        <button type="button" onClick={() => onNavigate("deals-management")} className="flex items-center gap-3 rounded-[var(--radius-lg)] bg-[var(--color-muted)] p-3 text-right"><Handshake className="h-5 w-5 text-[var(--color-primary)]" /><span><strong className="block text-lg text-[var(--color-text)]">{data.deals.open}</strong><span className="text-xs text-[var(--color-text-muted)]">صفقات مفتوحة</span></span></button>
        <button type="button" onClick={() => onNavigate("shipments-management")} className="flex items-center gap-3 rounded-[var(--radius-lg)] bg-[var(--color-muted)] p-3 text-right"><Ship className="h-5 w-5 text-[var(--color-primary)]" /><span><strong className="block text-lg text-[var(--color-text)]">{data.shipments.in_transit}</strong><span className="text-xs text-[var(--color-text-muted)]">شحنات في الطريق</span></span></button>
        <button type="button" onClick={() => onNavigate("shipments-management")} className="flex items-center gap-3 rounded-[var(--radius-lg)] bg-[var(--color-muted)] p-3 text-right"><ReceiptText className="h-5 w-5 text-[var(--color-primary)]" /><span><strong className="block text-lg text-[var(--color-text)]">{data.shipments.clearing}</strong><span className="text-xs text-[var(--color-text-muted)]">شحنات قيد التخليص</span></span></button>
      </div>
    </section>
  );
}

function MiniStat({ label, value, warning = false }: { label: string; value: number; warning?: boolean }) {
  return <div className="rounded-[var(--radius-lg)] bg-[var(--color-muted)] p-2 text-center"><strong className={`block text-lg ${warning ? "text-rose-500" : "text-[var(--color-text)]"}`}>{value}</strong><span className="text-[11px] text-[var(--color-text-muted)]">{label}</span></div>;
}

function AlertCard({ alert, onNavigate }: { alert: DashboardAlert; onNavigate: (view: AppView) => void }) {
  const icons = { danger: AlertCircle, warning: AlertTriangle, info: Info };
  const Icon = icons[alert.type];
  return (
    <button type="button" onClick={() => alert.link && onNavigate(alert.link as AppView)} className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-right">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${alert.type === "danger" ? "text-rose-500" : alert.type === "warning" ? "text-amber-500" : "text-[var(--color-primary)]"}`} />
      <span><strong className="block text-xs text-[var(--color-text)]">{alert.title}</strong><span className="text-[11px] text-[var(--color-text-muted)]">{alert.message}</span></span>
    </button>
  );
}
