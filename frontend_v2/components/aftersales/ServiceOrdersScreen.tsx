import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronLeft, ChevronRight, Loader2, Plus, RotateCcw, Search, Wrench,
} from "lucide-react";
import {
  listServiceOrders,
  type ServiceOrderListFilters,
  type ServiceOrderListRow,
  type ServiceOrderStatus,
} from "../../services/afterSalesApi";
import { listPickerProducts } from "../../services/inventoryApi";
import { accountingApi } from "../../services/accountingApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { SERVICE_STATUS_LABELS, serviceStatusPillClass } from "../../utils/serviceOrder";
import { usePermissions } from "../../contexts/PermissionsContext";
import { ServiceOrderDocument } from "./ServiceOrderDocument";
import { ServiceOrderIntakeModal } from "./ServiceOrderIntakeModal";

/**
 * THA-24 م4 — «أوامر الصيانة»: القائمة، والاستقبال، وفتح المستند.
 *
 * القائمة تفلتر **خادمياً** (الحالة والتاريخ والبحث): الفلترة في المتصفح على
 * صفحةٍ واحدة تُظهر «٣ مفتوحة» من أصل مئات، وهي أسوأ من غياب الفلتر.
 *
 * الافتراضي «المفتوحة وحدها» — شاشة الكاونتر تُسأل «ما الذي عندي الآن؟» لا
 * «ماذا أصلحنا منذ سنة».
 */

const PAGE_SIZE = 25;

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const cardClass = "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4";

interface ProductOption {
  id: number;
  display_name?: string;
  name_ar?: string;
  name_en?: string;
  sku?: string;
  sale_price?: string | number | null;
}

interface PartnerOption { id: number; name: string; phone?: string }

interface Props {
  onOpenInvoice?: (invoiceId: number) => void;
}

export const ServiceOrdersScreen: React.FC<Props> = ({ onOpenInvoice }) => {
  const { can } = usePermissions();
  const canCreate = can("aftersales.order.create");

  const [searchText, setSearchText] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<ServiceOrderStatus | "">("");
  const [openOnly, setOpenOnly] = useState(true);

  const [rows, setRows] = useState<ServiceOrderListRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [listErr, setListErr] = useState<string | null>(null);

  const [products, setProducts] = useState<ProductOption[]>([]);
  const [customers, setCustomers] = useState<PartnerOption[]>([]);

  const [openId, setOpenId] = useState<number | null>(null);
  const [intakeOpen, setIntakeOpen] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(searchText.trim());
      setPage(1);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchText]);

  const filters: ServiceOrderListFilters = useMemo(() => ({
    q: query,
    status,
    // «المفتوحة» و«حالة بعينها» لا يجتمعان: الأضيق يفوز فلا يُلغي أحدهما الآخر.
    open: status ? false : openOnly,
  }), [query, status, openOnly]);

  const load = useCallback(async () => {
    setLoading(true);
    setListErr(null);
    try {
      const paged = await listServiceOrders(filters, page, PAGE_SIZE);
      setRows(paged.results);
      setTotal(paged.count);
    } catch (e) {
      setListErr(messageOf(e, "تعذّر تحميل أوامر الصيانة"));
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { if (openId === null) void load(); }, [load, openId]);

  // قوائم الاستقبال تُجلب مرة واحدة — لا مع كل بحث.
  useEffect(() => {
    void (async () => {
      try { setProducts(await listPickerProducts<ProductOption>()); } catch { /* الاسم الحر يكفي */ }
      try { setCustomers(await accountingApi.getPartners("customer") as PartnerOption[]); } catch { /* كما أعلاه */ }
    })();
  }, []);

  if (openId !== null) {
    return (
      <ServiceOrderDocument
        orderId={openId}
        products={products}
        onBack={() => setOpenId(null)}
        onChanged={() => { void load(); }}
        onOpenInvoice={onOpenInvoice}
      />
    );
  }

  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div dir="rtl" className="space-y-4 p-3 md:p-4" data-testid="service-orders-screen">
      <div className="flex flex-wrap items-center gap-2">
        <Wrench className="h-5 w-5 text-[var(--color-primary)]" />
        <span className="text-lg font-bold text-[var(--color-text)]">أوامر الصيانة</span>
        <span className="text-[11px] text-[var(--color-text-muted)]">
          ملفٌ لكل جهاز من الشكوى حتى الحل — التشخيص وقطع الغيار والنتيجة، وما يُفوتَر وما تتحمّله الكفالة
        </span>
        <span className="flex-1" />
        {canCreate && (
          <button
            type="button"
            onClick={() => setIntakeOpen(true)}
            className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white"
            data-testid="open-intake"
          >
            <Plus className="h-4 w-4" /> استقبال جهاز
          </button>
        )}
      </div>

      <section className={cardClass}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <label className={labelClass} htmlFor="svc-search">
              بحث برقم الأمر أو التسلسلي أو الزبون أو الشكوى
            </label>
            <div className="relative">
              <input
                id="svc-search"
                className={`${inputClass} pl-9`}
                placeholder="بحث…"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
              <span className="absolute inset-y-0 left-2 flex items-center text-[var(--color-text-muted)]">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </span>
            </div>
          </div>
          <div>
            <label className={labelClass} htmlFor="svc-status-filter">الحالة</label>
            <select
              id="svc-status-filter"
              className={inputClass}
              value={status}
              onChange={(e) => { setStatus(e.target.value as ServiceOrderStatus | ""); setPage(1); }}
            >
              <option value="">الكل</option>
              {Object.entries(SERVICE_STATUS_LABELS).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end gap-2">
            <label className="flex h-10 items-center gap-2 text-sm text-[var(--color-text)]">
              <input
                type="checkbox"
                checked={openOnly}
                disabled={Boolean(status)}
                onChange={(e) => { setOpenOnly(e.target.checked); setPage(1); }}
              />
              المفتوحة فقط
            </label>
            <button
              type="button"
              onClick={() => { setSearchText(""); setQuery(""); setStatus(""); setOpenOnly(true); setPage(1); }}
              className="inline-flex h-10 items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
            >
              <RotateCcw className="h-4 w-4" /> مسح
            </button>
          </div>
        </div>
      </section>

      <section className={cardClass}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-bold text-[var(--color-text)]">سجل أوامر الصيانة</h2>
          <span className="text-xs text-[var(--color-text-muted)]">{formatNumber(total)} أمر</span>
        </div>

        {listErr && (
          <div role="alert" className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
            {listErr}
          </div>
        )}

        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>رقم الأمر</th>
                <th>التاريخ</th>
                <th>الزبون</th>
                <th>الجهاز</th>
                <th className="hidden md:table-cell">الشكوى</th>
                <th>الحالة</th>
                <th className="hidden lg:table-cell">المال</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer"
                  onClick={() => setOpenId(row.id)}
                  title="فتح أمر الصيانة"
                >
                  <td className="whitespace-nowrap font-mono">{row.order_number}</td>
                  <td className="whitespace-nowrap">{formatDateValue(row.order_date)}</td>
                  <td>
                    <div className="text-[var(--color-text)]">{row.partner_name || "—"}</div>
                    {row.customer_phone && (
                      <div className="text-[11px] text-[var(--color-text-muted)]">{row.customer_phone}</div>
                    )}
                  </td>
                  <td>
                    <div className="text-[var(--color-text)]">{row.product_name || "—"}</div>
                    {row.serial && <div className="font-mono text-[11px] text-[var(--color-text-muted)]">{row.serial}</div>}
                  </td>
                  <td className="hidden max-w-[16rem] truncate md:table-cell">{row.complaint || "—"}</td>
                  <td className="whitespace-nowrap">
                    <span className={serviceStatusPillClass(row.status)}>{row.status_label}</span>
                    {row.outcome && (
                      <div className="text-[11px] text-[var(--color-text-muted)]">{row.outcome_label}</div>
                    )}
                  </td>
                  <td className="hidden whitespace-nowrap text-[11px] lg:table-cell">
                    {row.covered_posted_at && (
                      <div className="text-indigo-700 dark:text-indigo-300">صرف كفالة مرحَّل</div>
                    )}
                    {row.sales_invoice && (
                      <div className="text-[var(--color-text-muted)]">فاتورة مرتبطة</div>
                    )}
                    {!row.covered_posted_at && !row.sales_invoice && (
                      <span className="text-[var(--color-text-muted)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && rows.length === 0 && (
          <div className="p-6 text-center text-sm text-[var(--color-text-muted)]">
            لا أوامر مطابقة — ابدأ بـ«استقبال جهاز» عند ورود زبونٍ مشتكٍ.
          </div>
        )}
        {loading && rows.length === 0 && (
          <div className="flex items-center justify-center gap-2 p-6 text-sm text-[var(--color-text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" /> جارٍ التحميل…
          </div>
        )}

        {lastPage > 1 && (
          <div className="mt-3 flex items-center justify-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] disabled:opacity-40"
              title="الصفحة السابقة"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            <span className="text-xs text-[var(--color-text-muted)]">
              صفحة {formatNumber(page)} من {formatNumber(lastPage)}
            </span>
            <button
              type="button"
              disabled={page >= lastPage}
              onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
              className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] disabled:opacity-40"
              title="الصفحة التالية"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        )}
      </section>

      {intakeOpen && (
        <ServiceOrderIntakeModal
          products={products}
          customers={customers}
          onClose={() => setIntakeOpen(false)}
          onCreated={(order) => { setIntakeOpen(false); setOpenId(order.id); }}
        />
      )}
    </div>
  );
};

export default ServiceOrdersScreen;
