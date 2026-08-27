import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronLeft, ChevronRight, Loader2, Plus, RotateCcw, Search, ShieldCheck,
} from "lucide-react";
import { ShareRowButton } from "../shared/ShareRowButton";
import {
  listWarrantyCards,
  type WarrantyCardRow,
  type WarrantyListFilters,
  type WarrantySource,
  type WarrantyStatus,
} from "../../services/afterSalesApi";
import { listPickerProducts } from "../../services/inventoryApi";
import { accountingApi } from "../../services/accountingApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { warrantyRemainingText, warrantyStatusLabel } from "../../utils/warranty";
import { usePermissions } from "../../contexts/PermissionsContext";
import { WarrantyCardModal } from "./WarrantyCardModal";
import { warrantyPillClass } from "./warrantyStatus";

/**
 * THA-24 م2 — «بطاقات الكفالة»: القائمة والبحث وبطاقة يدوية والتمديد.
 *
 * الشاشة تعيش خلف حارس ترخيص الوحدة في `App.tsx`، والخادم يردّ 404 لكل نقطة
 * لشركةٍ غير مرخّصة — فلا تُبنى هنا طبقةُ إخفاءٍ ثالثة، بل تُستهلك الصلاحيات
 * لتعطيل ما لا يملكه المستخدم.
 *
 * **الحالة مشتقّة لا مخزَّنة**: يحسبها الخادم من تاريخ الانتهاء عند كل قراءة،
 * والفلترة عليه هو أيضاً (`status=active|expired`) — لا نفلتر في المتصفح على
 * صفحةٍ واحدة فنُظهر «١٢ سارية» من أصل مئات.
 *
 * معظم البطاقات تُنشئها فواتير البيع آلياً؛ اليدوية للأجهزة التي لم نبعها أو
 * بِيعت قبل تفعيل الوحدة.
 */

const PAGE_SIZE = 25;

const SOURCES: { key: WarrantySource; label: string }[] = [
  { key: "auto_sale", label: "تلقائية من فاتورة بيع" },
  { key: "manual", label: "يدوية" },
];

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
  warranty_months?: number | null;
  supplier_warranty_months?: number | null;
}

interface PartnerOption {
  id: number;
  name: string;
  phone?: string;
}

export const WarrantyCardsScreen: React.FC = () => {
  const { can } = usePermissions();
  const canManage = can("aftersales.warranty.manage");

  const [searchText, setSearchText] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<WarrantyStatus | "">("");
  const [source, setSource] = useState<WarrantySource | "">("");
  const [expiringOnly, setExpiringOnly] = useState(false);

  const [rows, setRows] = useState<WarrantyCardRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [listErr, setListErr] = useState<string | null>(null);

  const [products, setProducts] = useState<ProductOption[]>([]);
  const [customers, setCustomers] = useState<PartnerOption[]>([]);
  const [suppliers, setSuppliers] = useState<PartnerOption[]>([]);

  /** `null` = مغلقة · `"new"` = بطاقة يدوية جديدة · صف = بطاقة قائمة. */
  const [openCard, setOpenCard] = useState<WarrantyCardRow | "new" | null>(null);

  // البحث يضرب الخادم — الإبطاء 500ms هو ما يمنع طلباً لكل حرف.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(searchText.trim());
      setPage(1);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchText]);

  const filters: WarrantyListFilters = useMemo(() => ({
    q: query,
    status,
    source,
    // «توشك على الانتهاء» فلتر خادمي على النافذة نفسها التي تلوّن الشارة.
    expiring_within_days: expiringOnly ? 30 : "",
  }), [query, status, source, expiringOnly]);

  const load = useCallback(async () => {
    setLoading(true);
    setListErr(null);
    try {
      const paged = await listWarrantyCards(filters, page, PAGE_SIZE);
      setRows(paged.results);
      setTotal(paged.count);
    } catch (e) {
      setListErr(messageOf(e, "تعذّر تحميل بطاقات الكفالة"));
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { void load(); }, [load]);

  // قوائم النافذة تُجلب مرة واحدة — البطاقة اليدوية نادرة، فلا تُحمَّل مع كل بحث.
  useEffect(() => {
    if (!canManage) return;
    void (async () => {
      try {
        setProducts(await listPickerProducts<ProductOption>());
      } catch { /* الاختيار من المخزون تحسينٌ لا شرط — الاسم الحر يكفي */ }
      try {
        setCustomers(await accountingApi.getPartners("customer") as PartnerOption[]);
      } catch { /* كما أعلاه */ }
      try {
        setSuppliers(await accountingApi.getPartners("supplier") as PartnerOption[]);
      } catch { /* كما أعلاه */ }
    })();
  }, [canManage]);

  const resetFilters = () => {
    setSearchText("");
    setQuery("");
    setStatus("");
    setSource("");
    setExpiringOnly(false);
    setPage(1);
  };

  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div dir="rtl" className="space-y-4 p-3 md:p-4" data-testid="warranty-cards-screen">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-[var(--color-primary)]" />
        <span className="text-lg font-bold text-[var(--color-text)]">بطاقات الكفالة</span>
        <span className="text-[11px] text-[var(--color-text-muted)]">
          تُنشأ آلياً عند ترحيل فاتورة البيع لكل وحدة مُرقَّمة لمنتجٍ له كفالة — والحالة
          محسوبة من تاريخ الانتهاء، لا مُدخَلة
        </span>
        <span className="flex-1" />
        {canManage && (
          <button
            type="button"
            onClick={() => setOpenCard("new")}
            className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white"
          >
            <Plus className="h-4 w-4" /> بطاقة يدوية
          </button>
        )}
      </div>

      {/* ── البحث والفلترة ─────────────────────────────────────────────── */}
      <section className={cardClass}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <label className={labelClass} htmlFor="warranty-search">
              بحث بالرقم التسلسلي أو الزبون أو المنتج
            </label>
            <div className="relative">
              <input
                id="warranty-search"
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
            <label className={labelClass} htmlFor="warranty-status-filter">حالة الكفالة</label>
            <select
              id="warranty-status-filter"
              className={inputClass}
              value={status}
              onChange={(e) => { setStatus(e.target.value as WarrantyStatus | ""); setPage(1); }}
            >
              <option value="">الكل</option>
              <option value="active">سارية</option>
              <option value="expired">منتهية</option>
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="warranty-source-filter">مصدر البطاقة</label>
            <select
              id="warranty-source-filter"
              className={inputClass}
              value={source}
              onChange={(e) => { setSource(e.target.value as WarrantySource | ""); setPage(1); }}
            >
              <option value="">الكل</option>
              {SOURCES.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
            <input
              type="checkbox"
              checked={expiringOnly}
              onChange={(e) => { setExpiringOnly(e.target.checked); setPage(1); }}
            />
            توشك على الانتهاء (خلال {formatNumber(30)} يوماً)
          </label>
          <button
            type="button"
            onClick={resetFilters}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          >
            <RotateCcw className="h-4 w-4" /> مسح الفلاتر
          </button>
        </div>
      </section>

      {/* ── القائمة ───────────────────────────────────────────────────── */}
      <section className={cardClass}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-bold text-[var(--color-text)]">سجل بطاقات الكفالة</h2>
          <span className="text-xs text-[var(--color-text-muted)]">
            {formatNumber(total)} بطاقة
          </span>
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
                <th>الرقم التسلسلي</th>
                <th>المنتج / الجهاز</th>
                <th>الزبون</th>
                <th className="hidden md:table-cell">البداية</th>
                <th>الانتهاء</th>
                <th>الحالة</th>
                <th className="hidden lg:table-cell">المصدر</th>
                <th className="hidden lg:table-cell">كفالة المورد</th>
                <th>مشاركة</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer"
                  onClick={() => setOpenCard(row)}
                  title="فتح البطاقة"
                >
                  <td className="whitespace-nowrap font-mono">{row.serial || "—"}</td>
                  <td>
                    <div className="font-semibold text-[var(--color-text)]">
                      {row.product_name || row.device_name || "—"}
                    </div>
                    {row.sales_invoice_number && (
                      <div className="text-[11px] text-[var(--color-text-muted)]">
                        فاتورة {row.sales_invoice_number}
                      </div>
                    )}
                  </td>
                  <td>
                    <div className="text-[var(--color-text)]">{row.partner_name || "—"}</div>
                    {row.customer_phone && (
                      <div className="text-[11px] text-[var(--color-text-muted)]">{row.customer_phone}</div>
                    )}
                  </td>
                  <td className="hidden whitespace-nowrap md:table-cell">
                    {formatDateValue(row.start_date)}
                  </td>
                  <td className="whitespace-nowrap">{formatDateValue(row.end_date)}</td>
                  <td className="whitespace-nowrap">
                    <span className={warrantyPillClass(row.status, row.days_remaining)}>
                      {warrantyStatusLabel(row.status)}
                    </span>
                    <div className="text-[11px] text-[var(--color-text-muted)]">
                      {warrantyRemainingText(row.status, row.days_remaining)}
                    </div>
                  </td>
                  <td className="hidden lg:table-cell">{row.source_label}</td>
                  <td className="hidden lg:table-cell">
                    {row.supplier_warranty_end_date ? (
                      <span className={row.supplier_warranty_active
                        ? "text-emerald-700 dark:text-emerald-400"
                        : "text-[var(--color-text-muted)]"}>
                        {formatDateValue(row.supplier_warranty_end_date)}
                      </span>
                    ) : "—"}
                  </td>
                  {/* DOC-SHARE: البطاقة تُسلَّم للزبون — و`supplier` و
                      `supplier_warranty_end_date` لا يخرجان إليه (العمود
                      المجاور داخليّ، والصفحة العامة لا تحمله). */}
                  <td onClick={(e) => e.stopPropagation()}>
                    <ShareRowButton
                      docType="warranty_card"
                      docId={row.id}
                      docLabel={`بطاقة كفالة #${row.id}`}
                      partyName={row.customer_name || undefined}
                      className="text-blue-600 hover:underline text-xs"
                      label=""
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && rows.length === 0 && (
          <div className="p-6 text-center text-sm text-[var(--color-text-muted)]">
            لا بطاقات مطابقة — تُنشأ البطاقات مع ترحيل فواتير البيع للمنتجات ذات الكفالة،
            أو أضف بطاقة يدوية لجهازٍ بِيع قبل تفعيل الوحدة.
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

      {openCard !== null && (
        <WarrantyCardModal
          card={openCard === "new" ? null : openCard}
          canManage={canManage}
          products={products}
          customers={customers}
          suppliers={suppliers}
          onClose={() => setOpenCard(null)}
          onChanged={() => { void load(); }}
        />
      )}
    </div>
  );
};

export default WarrantyCardsScreen;
