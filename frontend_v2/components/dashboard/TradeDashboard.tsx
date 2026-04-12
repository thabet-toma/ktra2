import React, { useEffect, useState, useCallback } from "react";
import { fetchDashboard } from "../../services/dashboardApi";
import type { DashboardData, DashboardAlert } from "../../types/dashboard";
import type { AppView } from "../../types/common";
import {
  Handshake,
  Ship,
  Banknote,
  FileText,
  Package,
  BookOpen,
  Loader2,
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
      return <AlertCircle className="w-4 h-4 text-red-500" />;
    case "warning":
      return <AlertTriangle className="w-4 h-4 text-amber-500" />;
    default:
      return <Info className="w-4 h-4 text-blue-500" />;
  }
};
const alertBg = (t: DashboardAlert["type"]) => {
  switch (t) {
    case "danger":
      return "bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800";
    case "warning":
      return "bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-800";
    default:
      return "bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-800";
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
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }
  if (err || !data) {
    return (
      <div className="p-8 text-center text-red-600">
        <AlertTriangle className="w-10 h-10 mx-auto mb-3" />
        <p>{err || "فشل تحميل البيانات"}</p>
        <button onClick={load} className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg">
          إعادة المحاولة
        </button>
      </div>
    );
  }

  const { deals, shipments, payments, invoices, inventory, accounting, alerts } = data;

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" dir="rtl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-800 dark:text-white">
            مرحباً، {userName.split(" ")[0]}
          </h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            لوحة التحكم التجارية — نظرة شاملة على العمليات
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"
        >
          <RefreshCw className="w-4 h-4" />
          تحديث
        </button>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {alerts.map((a, i) => (
            <button
              key={i}
              onClick={() => a.link && onNavigate(a.link as AppView)}
              className={`flex items-start gap-3 p-3 rounded-xl border text-right transition-all hover:shadow-sm ${alertBg(a.type)}`}
            >
              <div className="mt-0.5 shrink-0">{alertIcon(a.type)}</div>
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {a.title}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{a.message}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Main KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
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
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: deals status distribution + recent deals + recent shipments */}
        <div className="lg:col-span-2 space-y-6">
          {/* Deal Status Chart (simple bars) */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
            <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-indigo-500" />
              توزيع حالات الصفقات
            </h3>
            <div className="space-y-3">
              {deals.status_distribution.map((s) => {
                const pct = deals.total > 0 ? Math.round((s.count / deals.total) * 100) : 0;
                return (
                  <div key={s.status} className="flex items-center gap-3">
                    <span className="text-xs w-20 text-slate-600 dark:text-slate-300 shrink-0">
                      {DEAL_STATUS_AR[s.status] || s.status}
                    </span>
                    <div className="flex-1 h-5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-l from-indigo-500 to-blue-500 rounded-full transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 w-12 text-left">
                      {s.count} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recent Deals */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200 flex items-center gap-2">
                <Handshake className="w-4 h-4 text-blue-500" />
                آخر الصفقات
              </h3>
              <button
                onClick={() => onNavigate("deals-management")}
                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
              >
                عرض الكل <ArrowLeft className="w-3 h-3" />
              </button>
            </div>
            <div className="space-y-2.5">
              {deals.recent.map((d: any) => (
                <div
                  key={d.id}
                  className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-700 last:border-0"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                      {d.ref_number}
                    </p>
                    <p className="text-xs text-slate-500">{d.partner_name}</p>
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-mono font-semibold text-slate-700 dark:text-slate-200">
                      {fmtMoney(d.total_amount)} $
                    </p>
                    <StatusBadge label={DEAL_STATUS_AR[d.status] || d.status} status={d.status} />
                  </div>
                </div>
              ))}
              {deals.recent.length === 0 && (
                <p className="text-center text-sm text-slate-400 py-4">لا توجد صفقات</p>
              )}
            </div>
          </div>

          {/* Recent Shipments */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200 flex items-center gap-2">
                <Ship className="w-4 h-4 text-indigo-500" />
                آخر الشحنات
              </h3>
              <button
                onClick={() => onNavigate("shipments-management")}
                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
              >
                عرض الكل <ArrowLeft className="w-3 h-3" />
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 dark:text-slate-400 border-b border-slate-100 dark:border-slate-700">
                    <th className="text-right py-2 font-medium">رقم الشحنة</th>
                    <th className="text-center py-2 font-medium">الحالة</th>
                    <th className="text-center py-2 font-medium">المغادرة</th>
                    <th className="text-center py-2 font-medium">الوصول</th>
                    <th className="text-left py-2 font-medium">التكلفة</th>
                  </tr>
                </thead>
                <tbody>
                  {shipments.recent.map((s: any) => (
                    <tr key={s.id} className="border-b border-slate-50 dark:border-slate-700/50 last:border-0">
                      <td className="py-2 font-medium text-slate-800 dark:text-slate-100">
                        {s.shipment_number}
                      </td>
                      <td className="py-2 text-center">
                        <StatusBadge label={SHIP_STATUS_AR[s.status] || s.status} status={s.status} />
                      </td>
                      <td className="py-2 text-center text-xs text-slate-500">{fmtDate(s.departure_date)}</td>
                      <td className="py-2 text-center text-xs text-slate-500">{fmtDate(s.arrival_date)}</td>
                      <td className="py-2 text-left font-mono text-xs">{fmtMoney(s.total_shipping_cost_usd)} $</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {shipments.recent.length === 0 && (
                <p className="text-center text-sm text-slate-400 py-4">لا توجد شحنات</p>
              )}
            </div>
          </div>
        </div>

        {/* Right column: invoices + inventory + quick nav */}
        <div className="space-y-6">
          {/* Recent Invoices */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200 flex items-center gap-2">
                <FileText className="w-4 h-4 text-purple-500" />
                آخر الفواتير
              </h3>
              <button
                onClick={() => onNavigate("purchase-invoices")}
                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
              >
                الكل <ArrowLeft className="w-3 h-3" />
              </button>
            </div>
            <div className="space-y-2.5">
              {invoices.recent.map((inv: any) => (
                <div
                  key={inv.id}
                  className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-700 last:border-0"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                      {inv.invoice_number}
                    </p>
                    <p className="text-xs text-slate-500">{inv.partner_name}</p>
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-mono font-semibold">{fmtMoney(inv.grand_total)}</p>
                    <span className="text-[10px] text-slate-400">
                      {INV_STATUS_AR[inv.status] || inv.status}
                    </span>
                  </div>
                </div>
              ))}
              {invoices.recent.length === 0 && (
                <p className="text-center text-sm text-slate-400 py-4">لا توجد فواتير</p>
              )}
            </div>
          </div>

          {/* Inventory Summary */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
            <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-4 flex items-center gap-2">
              <Boxes className="w-4 h-4 text-amber-500" />
              ملخص المخزون
            </h3>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <MiniStat label="إجمالي الأصناف" value={inventory.total_products} />
              <MiniStat label="بمخزون" value={inventory.in_stock} />
              <MiniStat label="منخفض" value={inventory.low_stock} danger={inventory.low_stock > 0} />
              <MiniStat label="نفذ" value={inventory.out_of_stock} danger={inventory.out_of_stock > 0} />
            </div>
            <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-700">
              <span className="text-xs text-slate-500">قيمة المخزون</span>
              <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                {fmtMoney(inventory.inventory_value)} ₪
              </span>
            </div>
            {inventory.low_stock_items.length > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700">
                <p className="text-xs font-semibold text-amber-600 mb-2">أصناف تحت الحد الأدنى:</p>
                {inventory.low_stock_items.slice(0, 4).map((p) => (
                  <div
                    key={p.id}
                    className="flex justify-between text-xs py-1 text-slate-600 dark:text-slate-300"
                  >
                    <span>{p.name_ar || p.sku}</span>
                    <span className="font-mono text-red-500">
                      {Number(p.quantity_on_hand).toFixed(0)} / {p.min_stock_level}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Navigation */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-5">
            <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-3 flex items-center gap-2">
              <Activity className="w-4 h-4 text-slate-500" />
              وصول سريع
            </h3>
            <div className="grid grid-cols-2 gap-2">
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
                  className="flex items-center gap-2 p-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-700/50 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 hover:text-indigo-600 transition-colors"
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
    blue: "from-blue-500 to-blue-600",
    indigo: "from-indigo-500 to-indigo-600",
    green: "from-emerald-500 to-emerald-600",
    purple: "from-purple-500 to-purple-600",
    amber: "from-amber-500 to-amber-600",
    slate: "from-slate-500 to-slate-600",
  };
  const grad = colorMap[color] || colorMap.slate;

  return (
    <button
      onClick={onClick}
      className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 text-right hover:shadow-md transition-all group"
    >
      <div className={`inline-flex p-2 rounded-xl bg-gradient-to-br ${grad} text-white mb-3`}>
        <Icon className="w-5 h-5" />
      </div>
      <p className="text-xl md:text-2xl font-bold text-slate-800 dark:text-white">{value}</p>
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{label}</p>
      {sub && <p className="text-[10px] text-slate-400 mt-1">{sub}</p>}
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
    <div className="text-center p-2 rounded-lg bg-slate-50 dark:bg-slate-700/40">
      <p
        className={`text-lg font-bold ${
          danger ? "text-red-500" : "text-slate-800 dark:text-white"
        }`}
      >
        {value}
      </p>
      <p className="text-[10px] text-slate-500">{label}</p>
    </div>
  );
}

function StatusBadge({ label, status }: { label: string; status: string }) {
  let cls = "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300";
  if (["Open", "Pending", "draft", "incomplete"].includes(status))
    cls = "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300";
  if (["Shipped", "In-Transit", "deposit_paid", "partially_paid"].includes(status))
    cls = "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300";
  if (["Cleared", "Arrived", "completed", "fully_paid"].includes(status))
    cls = "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300";
  if (["Closed", "Clearing", "archived"].includes(status))
    cls = "bg-slate-200 text-slate-600 dark:bg-slate-600 dark:text-slate-200";
  if (["Cancelled"].includes(status))
    cls = "bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300";

  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${cls}`}>
      {label}
    </span>
  );
}
