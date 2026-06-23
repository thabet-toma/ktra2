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
import {
  Plus,
  RefreshCw,
  Printer,
  Edit,
  Trash2,
  Eye,
  ArrowRightLeft,
  ScrollText,
} from "lucide-react";
import {
  AseelDocumentShell,
  AseelDenseTable,
  type DenseColumn,
  type AseelToolbarAction,
} from "../../aseel";

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
  /** إعادة تحميل القائمة. */
  onRefresh?: () => void;
}

const STATUS_OPTIONS = [
  { v: "all", l: "الكل" },
  { v: "posted", l: "مرحَّلة" },
  { v: "draft", l: "مسودة" },
];

const fmtNum = (s: string | number | undefined | null) => {
  const n = Number(s);
  if (!isFinite(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

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
  onRefresh,
}) => {
  const navigate = useNavigate();

  // فلاتر
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const grandOf = (invoice: Invoice): number => {
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
    if (!suppliers || !invoice.supplierId) return "مورد غير محدد";
    const s = suppliers.find((x) => x.id === invoice.supplierId);
    return s?.alias || s?.tradeName || invoice.factoryName || "مورد غير محدد";
  };

  const filteredRows = useMemo(() => {
    return invoices
      .filter((inv) => {
        if (inv.isHistorical) return false;
        if (filterStatus === "posted" && !inv.isPosted) return false;
        if (filterStatus === "draft" && inv.isPosted) return false;
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
  }, [invoices, filterStatus, dateFrom, dateTo, search, suppliers]);

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
      key: "invoiceDate",
      header: "التاريخ",
      width: "110px",
      align: "center",
      render: (r) => <span className="text-xs">{r.invoiceDate || (r.createdAt ? r.createdAt.slice(0, 10) : "—")}</span>,
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
            onClick={(e) => { e.stopPropagation(); openInNewTab(`/partners/${r.supplierId}`); }}
          >
            {supplierName(r)}
          </button>
        ) : (
          <span className="text-xs">{supplierName(r)}</span>
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
      key: "grandTotal",
      header: "الإجمالي",
      width: "120px",
      align: "left",
      numeric: true,
      render: (r) => <span className="aseel-num font-mono text-xs font-semibold">{fmtNum(grandOf(r))}</span>,
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
            onClick={(e) => { e.stopPropagation(); onEdit(r); }}
            title="تعديل"
          >
            <Edit className="w-3 h-3" />
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
          <button
            type="button"
            className="aseel-toolbtn"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            onClick={(e) => {
              e.stopPropagation();
              if (window.confirm(`هل تريد إنشاء صفقة شراء جديدة بناءً على الفاتورة (${r.invoiceNumber})؟`)) {
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
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm(`حذف الفاتورة (${r.invoiceNumber}) نهائياً؟ لا يمكن التراجع.`)) {
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
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <label className="aseel-field" style={{ flex: 1, minWidth: "200px" }}>
        <span className="aseel-field-label">بحث (رقم / مورد)</span>
        <input
          className="aseel-input"
          data-aseel-field="search"
          placeholder="بحث... (F6)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <label className="aseel-field" style={{ minWidth: "100px" }}>
        <span className="aseel-field-label">الحالة</span>
        <select className="aseel-input" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          {STATUS_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">من تاريخ</span>
        <input type="date" className="aseel-input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">إلى تاريخ</span>
        <input type="date" className="aseel-input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
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

  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="فواتير الشراء"
        state={`${filteredRows.length} من ${invoices.filter((i) => !i.isHistorical).length}`}
        actions={toolbarActions}
        header={filterBar}
        status={
          <>
            <span className="aseel-status-item">العدد <b>{filteredRows.length}</b></span>
            <span className="aseel-status-item">الإجمالي <b className="aseel-num">{fmtNum(totalSum)}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-ok, #2d7d46)" }}>مرحَّلة <b>{postedCount}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>مسودة <b>{draftCount}</b></span>
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
            onRowDoubleClick={(r) => onEdit(r)}
          />
        </div>
      </AseelDocumentShell>
    </div>
  );
};
