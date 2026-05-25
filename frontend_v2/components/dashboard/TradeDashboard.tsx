import React, { useEffect, useState, useCallback } from "react";
import { fetchDashboard } from "../../services/dashboardApi";
import type { DashboardData, DashboardAlert } from "../../types/dashboard";
import type { AppView } from "../../types/common";
import { StatusBadge, Spinner, EmptyState } from "../../components/ui";
import { AseelDenseTable } from "../aseel";
import {
  Handshake,
  Ship,
  Banknote,
  FileText,
  Package,
  BookOpen,
  AlertTriangle,
  AlertCircle,
  Info,
  RefreshCw,
  TrendingUp,
  Activity,
  ArrowLeft,
  DollarSign,
  Boxes,
  BarChart3,
} from "lucide-react";

interface TradeDashboardProps {
  userName: string;
  onNavigate: (view: AppView) => void;
}

const fmt = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });

const fmtMoney = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtDate = (d: string | null) => {
  if (!d) return "—";
  const [y, m, day] = d.split("-");
  return `${day}/${m}/${y}`;
};

const DEAL_STATUS_AR: Record<string, string> = {
  Open: "مفتوحة",
  Shipped: "مشحونة",
  Cleared: "مخلّصة",
  Closed: "مغلقة",
  Cancelled: "ملغاة",
};

const SHIP_STATUS_AR: Record<string, string> = {
  Pending: "بالانتظار",
  "In-Transit": "في الطريق",
  Arrived: "وصلت",
  Clearing: "تخليص",
  Cleared: "مخلّصة",
};

const INV_STATUS_AR: Record<string, string> = {
  draft: "مسودة",
  incomplete: "غير مكتملة",
  completed: "مكتملة",
  deposit_paid: "دفعة أولى",
  partially_paid: "جزئية",
  fully_paid: "مدفوعة",
  archived: "مؤرشفة",
};

const alertIcon = (t: DashboardAlert["type"]) => {
  switch (t) {
    case "danger":
      return <AlertCircle className="w-4 h-4 text-[var(--color-danger)]" />;
    case "warning":
      return <AlertTriangle className="w-4 h-4 text-[var(--color-warning)]" />;
    default:
      return <Info className="w-4 h-4 text-[var(--color-primary)]" />;
  }
};
const alertBg = (t: DashboardAlert["type"]) => {
  switch (t) {
    case "danger":
      return "bg-[var(--color-danger)]/10 border-[var(--color-danger)]/30";
    case "warning":
      return "bg-[var(--color-warning)]/10 border-[var(--color-warning)]/30";
    default:
      return "bg-[var(--color-primary)]/10 border-[var(--color-primary)]/30";
  }
};

export const TradeDashboard: React.FC<TradeDashboardProps> = ({
  userName,
  onNavigate,
}) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const d = await fetchDashboard();
      setData(d);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[500px]">
        <Spinner size="md" />
      </div>
    );
  }
  if (err || !data) {
    return (
      <EmptyState
        icon={<AlertTriangle className="w-10 h-10" />}
        title={err || "فشل تحميل البيانات"}
        action={
          <button onClick={load} className="px-4 py-2 bg-[var(--color-primary)] text-white rounded-[var(--radius-md)]">
            إعادة المحاولة
          </button>
        }
      />
    );
  }

  const { deals, shipments, payments, invoices, inventory, accounting, alerts } = data;

  return (
    <div className="p-[var(--spacing-4)] md:p-[var(--spacing-6)] max-w-7xl mx-auto gap-[var(--spacing-6)]" dir="rtl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-[var(--spacing-3)]">
        <div>
          <h1 className="text-[var(--font-size-2xl)] md:text-[var(--font-size-2xl)] font-bold text-[var(--color-text)]">
            مرحباً، {userName.split(" ")[0]}
          </h1>
          <p className="text-[var(--color-text-muted)] text-[var(--font-size-sm)] mt-[var(--spacing-1)]">
            لوحة التحكم التجارية — نظرة شاملة على العمليات
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-[var(--font-size-sm)] px-[var(--spacing-3)] py-2 rounded-[var(--radius-lg)] bg-[var(--color-muted)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
        >
          <RefreshCw className="w-4 h-4" />
          تحديث
        </button>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-[var(--spacing-3)]">
          {alerts.map((a, i) => (
            <button
              key={i}
              onClick={() => a.link && onNavigate(a.link as AppView)}
              className={`flex items-start gap-[var(--spacing-3)] p-3 rounded-[var(--radius-lg)] border text-right transition-all hover:shadow-sm ${alertBg(a.type)}`}
            >
              <div className="mt-0.5 shrink-0">{alertIcon(a.type)}</div>
              <div>
                <p className="text-[var(--font-size-sm)] font-semibold text-[var(--color-text)]">
                  {a.title}
                </p>
                <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{a.message}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Main KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-[var(--spacing-3)]">
        <KpiCard
          icon={Handshake}
          label="صفقات مفتوحة"
          value={deals.open}
          sub={`${fmtMoney(deals.open_value)} $`}
          color="blue"
          onClick={() => onNavigate("deals-management")}
        />
        <KpiCard
          icon={Ship}
          label="شحنات في الطريق"
          value={shipments.in_transit}
          sub={`${shipments.clearing} بالتخليص`}
          color="indigo"
          onClick={() => onNavigate("shipments-management")}
        />
        <KpiCard
          icon={Banknote}
          label="مدفوعات الشهر"
          value={fmtMoney(payments.paid_this_month)}
          sub={`${payments.posted} مرحّلة`}
          color="green"
        />
        <KpiCard
          icon={FileText}
          label="فواتير"
          value={invoices.total}
          sub={`${fmtMoney(invoices.total_value)} $`}
          color="purple"
          onClick={() => onNavigate("purchase-invoices")}
        />
        <KpiCard
          icon={Package}
          label="قيمة المخزون"
          value={fmtMoney(inventory.inventory_value)}
          sub={`${inventory.in_stock} صنف`}
          color="amber"
          onClick={() => onNavigate("stock-levels")}
        />
        <KpiCard
          icon={BookOpen}
          label="قيود الشهر"
          value={accounting.journals_this_month}
          sub="قيد محاسبي"
          color="slate"
          onClick={() => onNavigate("accounting-journals")}
        />
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-[var(--spacing-6)]">
        {/* Left: deals status distribution + recent deals + recent shipments */}
        <div className="lg:col-span-2 gap-[var(--spacing-6)]">
          {/* Deal Status Chart (simple bars) */}
          <div className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] p-[var(--spacing-5)]">
            <h3 className="text-[var(--font-size-sm)] font-bold text-[var(--color-text)] mb-[var(--spacing-4)] flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[var(--color-primary)]" />
              توزيع حالات الصفقات
            </h3>
            <div className="gap-[var(--spacing-3)]">
              {deals.status_distribution.map((s) => {
                const pct = deals.total > 0 ? Math.round((s.count / deals.total) * 100) : 0;
                return (
                  <div key={s.status} className="flex items-center gap-[var(--spacing-3)]">
                    <span className="text-[var(--font-size-xs)] w-20 text-[var(--color-text-muted)] shrink-0">
                      {DEAL_STATUS_AR[s.status] || s.status}
                    </span>
                    <div className="flex-1 h-5 bg-[var(--color-muted)] rounded-[var(--radius-full)] overflow-hidden">
                      <div
                        className="h-full bg-[var(--color-primary)] rounded-[var(--radius-full)] transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-[var(--font-size-xs)] font-semibold text-[var(--color-text)] w-12 text-left">
                      {s.count} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recent Deals */}
          <div className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] p-[var(--spacing-5)]">
            <div className="flex items-center justify-between mb-[var(--spacing-4)]">
              <h3 className="text-[var(--font-size-sm)] font-bold text-[var(--color-text)] flex items-center gap-2">
                <Handshake className="w-4 h-4 text-[var(--color-primary)]" />
                آخر الصفقات
              </h3>
              <button
                onClick={() => onNavigate("deals-management")}
                className="text-[var(--font-size-xs)] text-[var(--color-primary)] hover:underline flex items-center gap-1"
              >
                عرض الكل <ArrowLeft className="w-3 h-3" />
              </button>
            </div>
            <div className="gap-[var(--spacing-2)]">
              {deals.recent.map((d: any) => (
                <div
                  key={d.id}
                  className="flex items-center justify-between py-2 border-b border-[var(--color-muted)] last:border-0"
                >
                  <div>
                    <p className="text-[var(--font-size-sm)] font-medium text-[var(--color-text)]">
                      {d.ref_number}
                    </p>
                    <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{d.partner_name}</p>
                  </div>
                  <div className="text-left">
                    <p className="text-[var(--font-size-sm)] font-mono font-semibold text-[var(--color-text)]">
                      {fmtMoney(d.total_amount)} $
                    </p>
                    <StatusBadge status={d.status} />
                  </div>
                </div>
              ))}
              {deals.recent.length === 0 && (
                <EmptyState title="لا توجد صفقات" />
              )}
            </div>
          </div>

          {/* Recent Shipments */}
          <div className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] p-[var(--spacing-5)]">
            <div className="flex items-center justify-between mb-[var(--spacing-4)]">
              <h3 className="text-[var(--font-size-sm)] font-bold text-[var(--color-text)] flex items-center gap-2">
                <Ship className="w-4 h-4 text-[var(--color-primary)]" />
                آخر الشحنات
              </h3>
              <button
                onClick={() => onNavigate("shipments-management")}
                className="text-[var(--font-size-xs)] text-[var(--color-primary)] hover:underline flex items-center gap-1"
              >
                عرض الكل <ArrowLeft className="w-3 h-3" />
              </button>
            </div>
            {shipments.recent.length === 0 ? (
              <EmptyState title="لا توجد شحنات" />
            ) : (
              <AseelDenseTable
                columns={[
                  { key: 'shipment_number', header: 'رقم الشحنة' },
                  { key: 'status', header: 'الحالة', align: 'center', render: (row: any) => <StatusBadge status={row.status} /> },
                  { key: 'departure_date', header: 'المغادرة', align: 'center', render: (row: any) => <span className="text-[var(--font-size-xs)]">{fmtDate(row.departure_date)}</span> },
                  { key: 'arrival_date', header: 'الوصول', align: 'center', render: (row: any) => <span className="text-[var(--font-size-xs)]">{fmtDate(row.arrival_date)}</span> },
                  { key: 'total_shipping_cost_usd', header: 'التكلفة', align: 'end', render: (row: any) => <span className="font-mono text-[var(--font-size-xs)]">{fmtMoney(row.total_shipping_cost_usd)} $</span> },
                ]}
                rows={shipments.recent}
                getRowKey={(row: any) => row.id}
              />
            )}
          </div>
        </div>

        {/* Right column: invoices + inventory + quick nav */}
        <div className="gap-[var(--spacing-6)]">
          {/* Recent Invoices */}
          <div className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] p-[var(--spacing-5)]">
            <div className="flex items-center justify-between mb-[var(--spacing-4)]">
              <h3 className="text-[var(--font-size-sm)] font-bold text-[var(--color-text)] flex items-center gap-2">
                <FileText className="w-4 h-4 text-[var(--color-primary)]" />
                آخر الفواتير
              </h3>
              <button
                onClick={() => onNavigate("purchase-invoices")}
                className="text-[var(--font-size-xs)] text-[var(--color-primary)] hover:underline flex items-center gap-1"
              >
                الكل <ArrowLeft className="w-3 h-3" />
              </button>
            </div>
            <div className="gap-[var(--spacing-2)]">
              {invoices.recent.map((inv: any) => (
                <div
                  key={inv.id}
                  className="flex items-center justify-between py-2 border-b border-[var(--color-muted)] last:border-0"
                >
                  <div>
                    <p className="text-[var(--font-size-sm)] font-medium text-[var(--color-text)]">
                      {inv.invoice_number}
                    </p>
                    <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{inv.partner_name}</p>
                  </div>
                  <div className="text-left">
                    <p className="text-[var(--font-size-sm)] font-mono font-semibold">{fmtMoney(inv.grand_total)}</p>
                    <span className="text-[10px] text-[var(--color-text-muted)]">
                      {INV_STATUS_AR[inv.status] || inv.status}
                    </span>
                  </div>
                </div>
              ))}
              {invoices.recent.length === 0 && (
                <EmptyState title="لا توجد فواتير" />
              )}
            </div>
          </div>

          {/* Inventory Summary */}
          <div className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] p-[var(--spacing-5)]">
            <h3 className="text-[var(--font-size-sm)] font-bold text-[var(--color-text)] mb-[var(--spacing-4)] flex items-center gap-2">
              <Boxes className="w-4 h-4 text-[var(--color-warning)]" />
              ملخص المخزون
            </h3>
            <div className="grid grid-cols-2 gap-[var(--spacing-3)] mb-[var(--spacing-4)]">
              <MiniStat label="إجمالي الأصناف" value={inventory.total_products} />
              <MiniStat label="بمخزون" value={inventory.in_stock} />
              <MiniStat label="منخفض" value={inventory.low_stock} danger={inventory.low_stock > 0} />
              <MiniStat label="نفذ" value={inventory.out_of_stock} danger={inventory.out_of_stock > 0} />
            </div>
            <div className="flex items-center justify-between pt-3 border-t border-[var(--color-muted)]">
              <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">قيمة المخزون</span>
              <span className="text-[var(--font-size-sm)] font-bold text-[var(--color-success)]">
                {fmtMoney(inventory.inventory_value)} ₪
              </span>
            </div>
            {inventory.low_stock_items.length > 0 && (
              <div className="mt-3 pt-3 border-t border-[var(--color-muted)]">
                <p className="text-[var(--font-size-xs)] font-semibold text-[var(--color-warning)] mb-2">أصناف تحت الحد الأدنى:</p>
                {inventory.low_stock_items.slice(0, 4).map((p) => (
                  <div
                    key={p.id}
                    className="flex justify-between text-[var(--font-size-xs)] py-1 text-[var(--color-text-muted)]"
                  >
                    <span>{p.name_ar || p.sku}</span>
                    <span className="font-mono text-[var(--color-danger)]">
                      {Number(p.quantity_on_hand).toFixed(0)} / {p.min_stock_level}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Navigation */}
          <div className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] p-[var(--spacing-5)]">
            <h3 className="text-[var(--font-size-sm)] font-bold text-[var(--color-text)] mb-3 flex items-center gap-2">
              <Activity className="w-4 h-4 text-[var(--color-text-muted)]" />
              وصول سريع
            </h3>
            <div className="grid grid-cols-2 gap-[var(--spacing-2)]">
              {[
                { label: "الصفقات", view: "deals-management" as AppView, icon: Handshake },
                { label: "الشحنات", view: "shipments-management" as AppView, icon: Ship },
                { label: "الفواتير", view: "purchase-invoices" as AppView, icon: FileText },
                { label: "المخزون", view: "stock-levels" as AppView, icon: Package },
                { label: "القيود", view: "accounting-journals" as AppView, icon: BookOpen },
                { label: "حركات المخزون", view: "stock-movements" as AppView, icon: Boxes },
              ].map((item) => (
                <button
                  key={item.view}
                  onClick={() => onNavigate(item.view)}
                  className="flex items-center gap-2 p-2.5 rounded-[var(--radius-lg)] text-[var(--font-size-xs)] font-medium text-[var(--color-text-muted)] bg-[var(--color-muted)] hover:bg-[var(--color-primary)]/10 hover:text-[var(--color-primary)] transition-colors"
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ─── Sub-components ──────────────────────────────────────────────────────── */

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  color,
  onClick,
}: {
  icon: React.FC<{ className?: string }>;
  label: string;
  value: string | number;
  sub?: string;
  color: string;
  onClick?: () => void;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-[var(--color-primary)]",
    indigo: "bg-[var(--color-primary)]",
    green: "bg-[var(--color-success)]",
    purple: "bg-[var(--color-primary)]",
    amber: "bg-[var(--color-warning)]",
    slate: "bg-[var(--color-text-muted)]",
  };
  const bg = colorMap[color] || colorMap.slate;

  return (
    <button
      onClick={onClick}
      className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] p-[var(--spacing-3)] text-right hover:shadow-md transition-all group"
    >
      <div className={`inline-flex p-[var(--spacing-1.5)] rounded-[var(--radius-md)] ${bg} text-white mb-3`}>
        <Icon className="w-5 h-5" />
      </div>
      <p className="text-[var(--font-size-xl)] md:text-[var(--font-size-2xl)] font-bold text-[var(--color-text)]">{value}</p>
      <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)] mt-[var(--spacing-0.5)]">{label}</p>
      {sub && <p className="text-[10px] text-[var(--color-text-muted)] mt-1">{sub}</p>}
    </button>
  );
}

function MiniStat({
  label,
  value,
  danger,
}: {
  label: string;
  value: number;
  danger?: boolean;
}) {
  return (
    <div className="text-center p-2 rounded-[var(--radius-lg)] bg-[var(--color-muted)]">
      <p
        className={`text-lg font-bold ${
          danger ? "text-[var(--color-danger)]" : "text-[var(--color-text)]"
        }`}
      >
        {value}
      </p>
      <p className="text-[10px] text-[var(--color-text-muted)]">{label}</p>
    </div>
  );
}


