/**
 * InvoiceList — قائمة فواتير الشراء على نمط «الأصيل» (مطابقة لقائمة المبيعات).
 * AseelDocumentShell + AseelDenseTable + شريط فلاتر + شريط أدوات موحّد.
 * أعمدة: رقم / التاريخ / المورد / الحالة / الإجمالي / إجراءات
 * (استُبدل التصميم البطاقي السابق بالكامل بطلب المالك — توحيد UI مع المبيعات.)
 */
import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Invoice, Item, Supplier } from "@/types";
import { openInNewTab } from "@/utils/openInNewTab";
import { clientLogger } from "../../../services/logger";
import { useConfirm } from "../../../contexts/ConfirmContext";
import { PaymentStatusBadge } from "../../shared/PaymentStatusBadge";
import { deriveInvoiceSettlement } from "../../shared/DocumentPaymentPanel";
import {
  Plus,
  RefreshCw,
  Printer,
  Trash2,
  Eye,
  ArrowRightLeft,
  ScrollText,
  Truck,
} from "lucide-react";
import {
  AseelDocumentShell,
  AseelDenseTable,
  AseelDateInput,
  type DenseColumn,
  type AseelToolbarAction,
} from "../../aseel";

/** T-INTENT: تسوية صفّ القائمة من المشتقّة المشتركة — نفس رقم المحرّر. */
const rowSettlement = (r: Invoice) => deriveInvoiceSettlement({
  grandTotal: Number(r.payableTotal ?? r.grandTotal ?? 0),
  paid: Number(r.amountPaid || 0),
  pendingIntent: Number(r.pendingPaymentTotal || 0),
  isPosted: Boolean(r.isPosted),
});

interface InvoiceListProps {
  invoices: Invoice[];
  onEdit: (invoice: Invoice) => void;
  onView: (invoice: Invoice) => void;
  onPrint: (invoice: Invoice) => void;
  onDelete: (id: string) => void;
  onConvertToDeal: (invoice: Invoice) => void;
  items: Item[];
  suppliers: Supplier[];
  /** فتح محرر فاتورة جديدة (من شريط الأدوات). */
  onCreateNew?: () => void;
  /** فتح نافذة الاستيراد من تخليص جمركي. */
  onImport?: () => void;
  /** شاشة الفواتير الدولية — تُسمّى القائمة وبنودها «دولية» بدل «شراء». */
  isInternational?: boolean;
  /** إعادة تحميل القائمة. */
  onRefresh?: () => void;
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  onFiltersChange?: (filters: InvoiceListFilters) => void;
}

export interface InvoiceListFilters {
  search: string;
  status: string;
  paymentStatus: "all" | "paid" | "partially_paid" | "unpaid" | "overdue";
  kind: "all" | "invoice" | "return";
  dateFrom: string;
  dateTo: string;
}

const STATUS_OPTIONS = [
  { v: "all", l: "الكل" },
  { v: "posted", l: "مرحَّلة" },
  { v: "draft", l: "مسودة" },
];

/** شارات حالة استلام البضاعة — مرآة شارات التسليم في قائمة المبيعات. */
const RECEIPT_BADGE: Record<
  NonNullable<Invoice["receiptStatus"]>,
  { label: string; color: string }
> = {
  not_received: { label: "غير مستلمة", color: "var(--aseel-warn, #b06800)" },
  partially_received: { label: "مستلمة جزئياً", color: "var(--aseel-accent, #2563eb)" },
  received: { label: "مستلمة", color: "var(--aseel-ok, #2d7d46)" },
};

import { formatMoney } from "@/utils/formatNumber";
import { formatDateLocalized } from "../../../utils/formatDate";
const fmtNum = (s: string | number | undefined | null) => formatMoney(s, "—");

export const InvoiceList: React.FC<InvoiceListProps> = ({
  invoices,
  onEdit,
  onView,
  onPrint,
  onDelete,
  onConvertToDeal,
  suppliers,
  onCreateNew,
  onImport,
  isInternational = false,
  onRefresh,
  page = 1,
  pageSize = 50,
  total = invoices.length,
  onPageChange,
  onFiltersChange,
}) => {
  const navigate = useNavigate();
  const confirm = useConfirm();

  // فلاتر
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterPaymentStatus, setFilterPaymentStatus] = useState<
    "all" | "paid" | "partially_paid" | "unpaid"
  >("all");
  // فلتر النوع: الكل / فواتير الشراء / مراجيع الشراء.
  const [filterKind, setFilterKind] = useState<"all" | "invoice" | "return">("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const publishFilters = (patch: Partial<InvoiceListFilters>) => {
    onFiltersChange?.({
      search,
      status: filterStatus,
      paymentStatus: filterPaymentStatus,
      kind: filterKind,
      dateFrom,
      dateTo,
      ...patch,
    });
  };

  const grandOf = (invoice: Invoice): number => {
    if (invoice.payableTotal != null && !Number.isNaN(Number(invoice.payableTotal))) {
      return Number(invoice.payableTotal);
    }
    const itemsTotal = (invoice.items || []).reduce((sum, it) => {
      const qty = parseFloat(it.quantity as any) || 0;
      const price = parseFloat(it.unitPrice as any) || 0;
      return sum + qty * price;
    }, 0);
    const base = itemsTotal > 0 ? itemsTotal : parseFloat(invoice.subtotal as any) || 0;
    if (invoice.grandTotal != null && !Number.isNaN(Number(invoice.grandTotal))) {
      return Number(invoice.grandTotal);
    }
    const discount = parseFloat(invoice.discountAmount as any) || 0;
    const net = Math.max(0, base - discount);
    const taxRate = parseFloat(invoice.taxRate as any) || 0;
    return net + net * (taxRate / 100);
  };

  const supplierName = (invoice: Invoice): string => {
    if (!invoice.supplierId) return "مورد غير محدد";
    const s = suppliers?.find((x) => x.id === invoice.supplierId);
    return s?.alias || s?.tradeName || invoice.supplierSnapshot?.tradeName || invoice.factoryName || "مورد غير محدد";
  };

  const filteredRows = useMemo(() => {
    return invoices
      .filter((inv) => {
        if (inv.isHistorical) return false;
        if (filterKind === "invoice" && inv.isReturn) return false;
        if (filterKind === "return" && !inv.isReturn) return false;
        if (filterStatus === "posted" && !inv.isPosted) return false;
        if (filterStatus === "draft" && inv.isPosted) return false;
        // T-DUE: «متأخرة» بُعدٌ فوق الحالة — تُرشَّح بعلمها لا بمساواة الحالة.
        if (filterPaymentStatus === "overdue") {
          if (!inv.isOverdue) return false;
        } else if (filterPaymentStatus !== "all" && inv.paymentStatus !== filterPaymentStatus) {
          return false;
        }
        const d = inv.invoiceDate || (inv.createdAt ? inv.createdAt.slice(0, 10) : "");
        if (dateFrom && d && d < dateFrom) return false;
        if (dateTo && d && d > dateTo) return false;
        if (search) {
          const t = search.toLowerCase();
          const hay = `${inv.invoiceNumber || ""} ${inv.invoiceName || ""} ${supplierName(inv)} ${inv.dealNumber || ""}`.toLowerCase();
          if (!hay.includes(t)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        const da = new Date(a.invoiceDate || a.createdAt || "").getTime();
        const db = new Date(b.invoiceDate || b.createdAt || "").getTime();
        return db - da;
      });
  }, [invoices, filterStatus, filterPaymentStatus, filterKind, dateFrom, dateTo, search, suppliers]);

  const columns: DenseColumn<Invoice>[] = [
    {
      key: "invoiceNumber",
      header: "رقم",
      width: "120px",
      render: (r) => (
        <button
          type="button"
          className="font-mono text-xs text-blue-700 hover:underline"
          onClick={(e) => { e.stopPropagation(); onEdit(r); }}
          title="فتح الفاتورة"
        >
          {r.invoiceNumber || `#${r.id}`}
        </button>
      ),
    },
    {
      key: "kind",
      header: "النوع",
      width: "90px",
      align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            padding: "1px 6px",
            borderRadius: "4px",
            color: r.isReturn ? "#b04a00" : "var(--aseel-accent, #2563eb)",
            background: r.isReturn ? "rgba(176,74,0,0.12)" : "rgba(37,99,235,0.10)",
          }}
        >
          {r.isReturn ? "مرجع" : r.invoiceType === "international" ? "فاتورة دولية" : "فاتورة"}
        </span>
      ),
    },
    {
      key: "invoiceDate",
      header: "التاريخ",
      width: "110px",
      align: "center",
      render: (r) => <span className="text-xs">{formatDateLocalized(r.invoiceDate || r.createdAt) || "—"}</span>,
    },
    {
      key: "supplier",
      header: "المورد",
      // T-A3: اسم المورد رابط لكشف حساب المورد (بطاقة الشريك) — يفتح في تبويب جديد (G2).
      render: (r) =>
        r.supplierId ? (
          <button
            type="button"
            className="text-xs text-[var(--aseel-accent)] underline hover:no-underline cursor-pointer bg-transparent border-0 p-0 font-inherit text-right"
            title="فتح كشف حساب المورد في تبويب جديد"
            data-ctx-partner-id={r.supplierId}
            data-ctx-partner-name={supplierName(r)}
            data-ctx-partner-kind="supplier"
            onClick={(e) => { e.stopPropagation(); openInNewTab(`/partners/${r.supplierId}`); }}
          >
            {supplierName(r)}
          </button>
        ) : (
          <span className="text-xs">{supplierName(r)}</span>
        ),
    },
    {
      // الفاتورة الدولية تُنشأ من صفقة — اسمها هو ما يعرفه المستخدم، لا رقمها.
      key: "dealTitle",
      header: "الصفقة",
      width: "180px",
      render: (r) => (
        r.dealId ? (
          <button
            type="button"
            className="text-xs text-[var(--aseel-accent)] underline hover:no-underline cursor-pointer bg-transparent border-0 p-0 font-inherit text-right"
            title="فتح الصفقة في تبويب جديد"
            onClick={(e) => { e.stopPropagation(); openInNewTab(`/deals/${r.dealId}`); }}
          >
            {r.dealTitle || r.dealNumber || `#${r.dealId}`}
          </button>
        ) : <span className="text-xs aseel-text-soft">—</span>
      ),
    },
    {
      key: "status",
      header: "الحالة",
      width: "90px",
      align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: r.isPosted ? "var(--aseel-ok, #2d7d46)" : "var(--aseel-warn, #b06800)",
          }}
        >
          {r.isPosted ? "مرحَّلة" : "مسودة"}
        </span>
      ),
    },
    {
      key: "receiptStatus",
      header: "الاستلام",
      width: "100px",
      align: "center",
      render: (r) => {
        const st = r.receiptStatus || "not_received";
        return (
          <span
            style={{ fontSize: "11px", fontWeight: 600, color: RECEIPT_BADGE[st].color }}
            title="حالة استلام البضاعة للمخزن"
          >
            {r.receiptStatusDisplay || RECEIPT_BADGE[st].label}
          </span>
        );
      },
    },
    {
      key: "grandTotal",
      header: "الإجمالي",
      width: "120px",
      align: "left",
      numeric: true,
      render: (r) => <span className="aseel-num font-mono text-xs font-semibold">{fmtNum(grandOf(r))}</span>,
    },
    {
      key: "paymentStatus",
      header: "حالة الدفع",
      width: "125px",
      align: "center",
      render: (r) => {
        const settlement = rowSettlement(r);
        return (
          <PaymentStatusBadge
            status={r.paymentStatus}
            label={r.paymentStatusDisplay}
            isOverdue={r.isOverdue}
            daysOverdue={r.daysOverdue}
            pendingIntent={settlement.pendingIntent}
            intentCoversAll={settlement.intentCoversAll}
          />
        );
      },
    },
    {
      key: "amountPaid",
      header: "المدفوع",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => <span className="aseel-num font-mono text-xs">{fmtNum(r.amountPaid)}</span>,
    },
    {
      key: "remainingBalance",
      // T-RECVIS: «المتبقي» وحدها صارت ملتبسة بعد ظهور باقي الاستلام الكمّي.
      header: "المتبقي للدفع",
      width: "100px",
      align: "left",
      numeric: true,
      // T-INTENT: مسودةٌ سُجِّلت عليها دفعة تُظهر متبقّيها بعدها، موسوماً بأنه
      // لم يدخل الدفاتر — وإلا كذّبت القائمةُ الشاشةَ التي أُدخلت فيها الدفعة.
      render: (r) => {
        const settlement = rowSettlement(r);
        return (
          <span className="inline-flex items-center gap-1">
            <span className="aseel-num font-mono text-xs font-semibold">
              {fmtNum(settlement.remainingAfterIntent)}
            </span>
            {settlement.pendingIntent > 0.009 && (
              <span
                title={`دفعة ${fmtNum(settlement.pendingIntent)} مسجَّلة ولم تُرحَّل بعد`}
                className="inline-flex rounded bg-amber-500 px-1 py-0.5 text-[9px] font-bold text-white"
              >
                غير مرحّلة
              </span>
            )}
          </span>
        );
      },
    },
    {
      key: "partnerBalance",
      header: "رصيد المورد",
      width: "110px",
      align: "left",
      numeric: true,
      render: (r) => <span className="aseel-num font-mono text-xs">{fmtNum(r.partnerBalance)}</span>,
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "200px",
      align: "center",
      render: (r) => (
        <div style={{ display: "flex", gap: "3px", flexWrap: "wrap", justifyContent: "center" }}>
          <button
            type="button"
            className="aseel-toolbtn"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            onClick={(e) => { e.stopPropagation(); onView(r); }}
            title="عرض"
          >
            <Eye className="w-3 h-3" />
          </button>
          <button
            type="button"
            className="aseel-toolbtn"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            onClick={(e) => { e.stopPropagation(); onPrint(r); }}
            title="طباعة"
          >
            <Printer className="w-3 h-3" />
          </button>
          {/* استلام: يفتح محرّر إرسالية بهذه الفاتورة مربوطةً مسبقاً. */}
          {r.isPosted && !r.isReturn && r.invoiceType !== "international"
            && r.receiptStatus !== "received" && (
            <button
              type="button"
              className="aseel-toolbtn"
              style={{ fontSize: "10px", padding: "2px 6px" }}
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/purchase-receipts/new?invoice=${r.id}`);
              }}
              title="استلام البضاعة (إرسالية)"
            >
              <Truck className="w-3 h-3" /> استلام
            </button>
          )}
          <button
            type="button"
            className="aseel-toolbtn"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            onClick={async (e) => {
              e.stopPropagation();
              if (await confirm({ title: "تحويل إلى صفقة", message: `هل تريد إنشاء صفقة شراء جديدة بناءً على الفاتورة (${r.invoiceNumber})؟`, danger: false, confirmText: "تحويل" })) {
                onConvertToDeal(r);
              }
            }}
            title="تحويل إلى صفقة"
          >
            <ArrowRightLeft className="w-3 h-3" />
          </button>
          {!r.isPosted && (
            <button
              type="button"
              className="aseel-toolbtn aseel-toolbtn--danger"
              style={{ fontSize: "10px", padding: "2px 6px" }}
              onClick={async (e) => {
                e.stopPropagation();
                if (await confirm({ title: "حذف الفاتورة", message: `حذف الفاتورة (${r.invoiceNumber}) نهائياً؟ لا يمكن التراجع.` })) {
                  onDelete(String(r.id));
                }
              }}
              title="حذف"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          )}
        </div>
      ),
    },
  ];

  const filterBar = (
    <div className="aseel-print-hidden" style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <label className="aseel-field" style={{ flex: 1, minWidth: "200px" }}>
        <span className="aseel-field-label">بحث (رقم / مورد)</span>
        <input
          className="aseel-input"
          data-aseel-field="search"
          placeholder="بحث... (F6)"
          value={search}
          onChange={(e) => { setSearch(e.target.value); publishFilters({ search: e.target.value }); }}
        />
      </label>
      <label className="aseel-field" style={{ minWidth: "110px" }}>
        <span className="aseel-field-label">النوع</span>
        <select
          className="aseel-input"
          value={filterKind}
          onChange={(e) => {
            const value = e.target.value as "all" | "invoice" | "return";
            setFilterKind(value);
            publishFilters({ kind: value });
          }}
        >
          <option value="all">الكل</option>
          <option value="invoice">{isInternational ? "الفواتير الدولية" : "فواتير الشراء"}</option>
          <option value="return">مراجيع الشراء</option>
        </select>
      </label>
      <label className="aseel-field" style={{ minWidth: "100px" }}>
        <span className="aseel-field-label">الحالة</span>
        <select className="aseel-input" value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); publishFilters({ status: e.target.value }); }}>
          {STATUS_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
      </label>
      <label className="aseel-field" style={{ minWidth: "125px" }}>
        <span className="aseel-field-label">حالة الدفع</span>
        <select
          className="aseel-input"
          value={filterPaymentStatus}
          onChange={(e) => {
            const value = e.target.value as InvoiceListFilters["paymentStatus"];
            clientLogger.info("purchase_invoice.payment_filter_changed", { paymentStatus: value });
            setFilterPaymentStatus(value);
            publishFilters({ paymentStatus: value });
          }}
        >
          <option value="all">الكل</option>
          <option value="unpaid">غير مدفوعة</option>
          <option value="partially_paid">مدفوعة جزئياً</option>
          <option value="paid">مدفوعة بالكامل</option>
          {/* T-DUE: خيارٌ فوق الثلاثة لا رابعٌ بينها — «عليها متبقٍّ واستحقاقها مضى». */}
          <option value="overdue">متأخرة</option>
        </select>
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">من تاريخ</span>
        <AseelDateInput value={dateFrom} onChange={(value) => { clientLogger.info("purchase_invoice.date_filter_changed", { boundary: "from", hasValue: Boolean(value) }); setDateFrom(value); publishFilters({ dateFrom: value }); }} />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">إلى تاريخ</span>
        <AseelDateInput value={dateTo} onChange={(value) => { clientLogger.info("purchase_invoice.date_filter_changed", { boundary: "to", hasValue: Boolean(value) }); setDateTo(value); publishFilters({ dateTo: value }); }} />
      </label>
    </div>
  );

  const toolbarActions: AseelToolbarAction[] = [
    {
      key: "new",
      label: "فاتورة جديدة",
      icon: <Plus />,
      onClick: onCreateNew ?? (() => openInNewTab("/purchase-invoices/new")),
    },
    ...(onImport
      ? [{ key: "import", label: "استيراد من تخليص جمركي", icon: <ScrollText />, onClick: onImport, separatorBefore: true } as AseelToolbarAction]
      : []),
    ...(onRefresh
      ? [{ key: "refresh", label: "تحديث", icon: <RefreshCw />, onClick: onRefresh, separatorBefore: true } as AseelToolbarAction]
      : []),
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => window.print() },
  ];

  const totalSum = filteredRows.reduce((s, r) => s + grandOf(r), 0);
  const postedCount = filteredRows.filter((r) => r.isPosted).length;
  const draftCount = filteredRows.length - postedCount;
  /* T-INTENT: مجاميع المدفوع والمتبقّي في الشريط — كان جانب البيع وحده يجمعها،
     فيغلق المشتري الشاشة وهو لا يعرف كم عليه للموردين في هذه الصفحة. */
  const paidSum = filteredRows.reduce((s, r) => s + (Number(r.amountPaid) || 0), 0);
  const balanceSum = filteredRows.reduce(
    (s, r) => s + rowSettlement(r).remainingAfterIntent, 0,
  );

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title={isInternational ? "الفواتير الدولية" : "فواتير الشراء"}
        state={`${filteredRows.length} في الصفحة من ${total}`}
        actions={toolbarActions}
        header={filterBar}
        status={
          <>
            <span className="aseel-status-item">العدد <b>{filteredRows.length}</b></span>
            <span className="aseel-status-item">الإجمالي <b className="aseel-num">{fmtNum(totalSum)}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-ok, #2d7d46)" }}>مرحَّلة <b>{postedCount}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>مسودة <b>{draftCount}</b></span>
            <span className="aseel-status-item">المدفوع <b className="aseel-num">{fmtNum(paidSum)}</b></span>
            <span className="aseel-status-item">المتبقي للدفع <b className="aseel-num">{fmtNum(balanceSum)}</b></span>
          </>
        }
      >
        <div style={{ padding: "8px" }}>
          <AseelDenseTable<Invoice>
            columns={columns}
            rows={filteredRows}
            getRowKey={(r) => String(r.id)}
            emptyHint="لا توجد فواتير شراء — اضغط «فاتورة جديدة» للإضافة"
            selectable
            selectedKey={selectedKey}
            onSelect={(k) => setSelectedKey(k as string | null)}
            onRowClick={(r) => onEdit(r)}
            onRowDoubleClick={(r) => onEdit(r)}
            pagination={onPageChange ? { page, pageSize, total, onChange: onPageChange } : undefined}
          />
        </div>
      </AseelDocumentShell>
    </div>
  );
};
