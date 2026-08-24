import React, { useEffect, useState, useCallback } from "react";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct, StockSummaryResponse } from "../../types/inventory";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { AseelDocumentShell, type AseelToolbarAction } from "../aseel/AseelDocumentShell";
import { RefreshCw, Download, Printer, Tags } from "lucide-react";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { productProfilePath } from "../../utils/entityLinks";
import { openInNewTab } from "../../utils/openInNewTab";

// مبالغ مالية — يحذف الأصفار العشرية غير الدالّة (6.00 ⇒ 6، 6.50 ⇒ 6.5) عبر المُنسّق الموحّد.
const fmt = (n: number | string) => formatMoney(n, "0");

export const StockLevelsPage: React.FC = () => {
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const toast = useToast();
  const [summary, setSummary] = useState<StockSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // فلاتر
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<"" | "low" | "out" | "over">("");
  const [filterCategory, setFilterCategory] = useState<string>("");
  // task16 E18: اختيار الأصناف للتصدير
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  // T-REORDER: تعيين «النوع» على المحدَّد — الحقل الذي بلا مدخلٍ جماعي يبقى فارغاً
  // أبداً على كتالوجٍ من ألفٍ ونصف، وبفراغه يسقط تجميع الموديلات كلّه.
  const [groupModal, setGroupModal] = useState(false);
  const [groupValue, setGroupValue] = useState("");
  const [brandValue, setBrandValue] = useState("");
  const [groupBusy, setGroupBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [prods, sum] = await Promise.all([
        inventoryApi.getProducts(),
        inventoryApi.getStockSummary(),
      ]);
      setProducts(prods as SqlProduct[]);
      setSummary(sum as StockSummaryResponse);
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "خطأ في التحميل"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const applyGroup = async () => {
    const ids: number[] = Array.from(selectedIds);
    if (ids.length === 0) return;
    const fields: { variant_group?: string; brand?: string } = {};
    if (groupValue.trim()) fields.variant_group = groupValue.trim();
    if (brandValue.trim()) fields.brand = brandValue.trim();
    if (Object.keys(fields).length === 0) {
      toast("اكتب نوعاً أو برانداً للتعيين.", "info");
      return;
    }
    setGroupBusy(true);
    try {
      const res = await inventoryApi.bulkSetGroup(ids, fields);
      toast(`عُيِّن على ${res.updated} صنفاً.`, "success");
      setGroupModal(false);
      setGroupValue("");
      setBrandValue("");
      await load();
    } catch (e: unknown) {
      toast(humanizeThrown(e, "تعذّر التعيين"), "error");
    } finally {
      setGroupBusy(false);
    }
  };

  const categories = Array.from(
    new Set(products.map((p) => p.category_name || "").filter(Boolean))
  ).sort();

  const filtered = products.filter((p) => {
    if (search) {
      const s = search.toLowerCase();
      if (
        !p.sku.toLowerCase().includes(s) &&
        !(p.name_ar || "").toLowerCase().includes(s) &&
        !(p.name_en || "").toLowerCase().includes(s)
      ) return false;
    }
    if (filterCategory && p.category_name !== filterCategory) return false;
    // T-REORDER: الحالة يحسمها الخادم (`inventory/stock_status.py`) — كانت
    // تُحسب هنا بقاعدةٍ ثانية تصبغ كلّ رصيدٍ صفر «منخفضاً» بينما الخادم يسمّيه
    // «نفذ»، فرقمان مختلفان لسؤالٍ واحد على شاشتين.
    if (filterStatus === "out") return p.stock_status === "out_of_stock";
    if (filterStatus === "low") return p.stock_status === "low_stock";
    if (filterStatus === "over") return p.stock_status === "overstock";
    return true;
  });

  // task16 E18: تصدير رصيد المخزون إلى CSV — المختار، وإلا كل المعروض
  const STATUS_AR: Record<string, string> = {
    // T-REORDER: «فائض» كانت ناقصة — الحالة الرابعة كانت تُصدَّر فارغة.
    out_of_stock: "نفذ", low_stock: "منخفض", overstock: "فائض", in_stock: "متوفر",
  };
  const toggleOne = (id: number) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const allFilteredSelected = filtered.length > 0 && filtered.every((p) => selectedIds.has(p.id));
  const toggleAll = () =>
    setSelectedIds((prev) => {
      if (filtered.every((p) => prev.has(p.id))) {
        const next = new Set(prev);
        filtered.forEach((p) => next.delete(p.id));
        return next;
      }
      const next = new Set(prev);
      filtered.forEach((p) => next.add(p.id));
      return next;
    });

  const printPdf = () => {
    const rowsToExport = selectedIds.size > 0
      ? filtered.filter((p) => selectedIds.has(p.id))
      : filtered;
    if (rowsToExport.length === 0) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      toast("الرجاء السماح بالنوافذ المنبثقة (Pop-ups) للطباعة", "error");
      return;
    }

    const today = new Date().toISOString().slice(0, 10);
    
    let html = `
      <html dir="rtl" lang="ar">
        <head>
          <title>أرصدة المخزون - ${today}</title>
          <style>
            body { font-family: system-ui, -apple-system, sans-serif; padding: 20px; color: #111827; }
            h2 { text-align: center; color: #1857a4; margin-bottom: 5px; }
            .subtitle { text-align: center; color: #6b7280; margin-bottom: 20px; font-size: 14px; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
            th, td { border: 1px solid #e5e7eb; padding: 10px 12px; text-align: right; }
            th { background-color: #f9fafb; color: #374151; font-weight: 600; }
            tr:nth-child(even) { background-color: #fcfcfd; }
            .num { text-align: left; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
            .danger { color: #dc2626; font-weight: bold; }
            @media print {
              body { padding: 0; }
              @page { margin: 1.5cm; }
            }
          </style>
        </head>
        <body>
          <h2>تقرير أرصدة المخزون</h2>
          <div class="subtitle">التاريخ: ${today}</div>
          <table>
            <thead>
              <tr>
                <th>البضاعة (الصنف)</th>
                <th>الكمية المتبقية</th>
                <th>متوسط التكلفة</th>
                <th>الحد الأدنى</th>
              </tr>
            </thead>
            <tbody>
    `;

    rowsToExport.forEach(p => {
      const name = p.name_ar || p.name_en || p.sku || '—';
      const qty = Number(p.quantity_on_hand);
      const avgCost = formatMoney(p.avg_cost);
      const minStock = p.min_stock_level ?? '—';
      const isLow = p.stock_status === 'out_of_stock' || p.stock_status === 'low_stock';
      
      html += `
        <tr>
          <td>${name} <br><span style="color:#6b7280; font-size:12px">${p.sku}</span></td>
          <td class="num ${isLow ? 'danger' : ''}" style="direction: ltr">${formatQuantity(qty)}</td>
          <td class="num" style="direction: ltr">${avgCost}</td>
          <td class="num" style="direction: ltr">${minStock}</td>
        </tr>
      `;
    });

    html += `
            </tbody>
          </table>
          <script>
            window.onload = () => {
              window.print();
            };
          </script>
        </body>
      </html>
    `;

    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
  };

  const statusCell = (p: SqlProduct) => {
    if (p.stock_status === "out_of_stock")
      return <span className="aseel-text-danger">نفذ</span>;
    if (p.stock_status === "low_stock")
      return <span className="aseel-text-warn">منخفض</span>;
    // T-REORDER: «فائض» = فوق الحدّ الأقصى المضبوط على الصنف. كان الفلتر يخمّنه
    // بـ«أكثر من ثلاثة أضعاف الأدنى» — قاعدةٌ لا مصدر لها.
    if (p.stock_status === "overstock")
      return <span className="aseel-text-warn">فائض</span>;
    return <span className="aseel-text-ok">متوفر</span>;
  };

  const columns: DenseColumn<SqlProduct>[] = [
    {
      key: "sel",
      header: "✓",
      width: "36px",
      align: "center",
      render: (p) => (
        <input
          type="checkbox"
          checked={selectedIds.has(p.id)}
          onChange={() => toggleOne(p.id)}
          onClick={(e) => e.stopPropagation()}
        />
      ),
    },
    { key: "sku", header: "SKU", width: "110px" },
    { key: "name", header: "الصنف", render: (p) => (
        // اسم الصنف قابل للنقر — يفتح حركة مخزون الصنف.
        <button
          type="button"
          className="text-blue-700 hover:underline text-right"
          onClick={(e) => { e.stopPropagation(); openInNewTab(productProfilePath(p.id)); }}
          title="فتح حركة مخزون الصنف"
        >
          {p.name_ar || p.name_en || "—"}
        </button>
      ) },
    { key: "cat", header: "التصنيف", width: "130px", render: (p) => <>{p.category_name || "—"}</> },
    // T-RESERVE: «المتاح» كان يعرض الرصيد نفسه — تسمية مضلِّلة بعد وجود الحجز.
    // الرصيد ثم المحجوز (طلبيات مؤكَّدة سارية) ثم المتاح للبيع = الفرق.
    { key: "qty", header: "الرصيد", width: "90px", align: "center", numeric: true,
      render: (p) => {
        const qty = Number(p.quantity_on_hand);
        const low = p.stock_status === "out_of_stock" || p.stock_status === "low_stock";
        return <span style={low ? { color: "var(--aseel-danger, #c00)", fontWeight: 600 } : {}}>{formatQuantity(qty)}</span>;
      }
    },
    { key: "reserved", header: "محجوز", width: "80px", align: "center", numeric: true,
      render: (p) => {
        const reserved = Number(p.reserved_quantity || 0);
        if (!reserved) return <span className="text-[var(--aseel-ink-soft)]">—</span>;
        return (
          <span title="محجوز بطلبيات زبائن مؤكَّدة سارية"
            className="aseel-text-warn font-semibold">
            {formatQuantity(reserved)}
          </span>
        );
      }
    },
    { key: "available", header: "المتاح", width: "90px", align: "center", numeric: true,
      render: (p) => (
        <span title="المتاح للبيع = الرصيد − المحجوز">
          {formatQuantity(p.available_quantity ?? p.quantity_on_hand)}
        </span>
      )
    },
    { key: "min", header: "الحد الأدنى", width: "90px", align: "center", numeric: true,
      render: (p) => <>{p.min_stock_level ?? "—"}</> },
    { key: "max", header: "الحد الأقصى", width: "90px", align: "center", numeric: true,
      render: (p) => <>{p.max_stock_level ?? "—"}</> },
    // T-REORDER: «النوع» ظاهر كي يُرى فارغاً. حين يكون بلا قيمة يسقط التجميع على
    // اسم الصنف ⇒ كل صنفٍ نوعٌ بذاته ⇒ لا بدائل ولا قرار «مؤجَّل».
    { key: "grp", header: "النوع", width: "130px",
      render: (p) => p.variant_group
        ? <>{p.variant_group}</>
        : <span className="aseel-text-soft" title="بلا نوع — لن تظهر له بدائل في الفاتورة">—</span> },
    { key: "status", header: "الحالة", width: "80px", align: "center", render: statusCell },
    { key: "avgcost", header: "متوسط التكلفة", width: "110px", align: "center", numeric: true,
      render: (p) => <>{fmt(Number(p.avg_cost))}</> },
    { key: "val", header: "القيمة", width: "110px", align: "center", numeric: true,
      render: (p) => <>{fmt(Number(p.quantity_on_hand) * Number(p.avg_cost))}</> },
  ];

  // footer: مجاميع
  const totalVal = filtered.reduce(
    (s, p) => s + Number(p.quantity_on_hand) * Number(p.avg_cost), 0
  );

  /* T-WIN M7: كانت الشاشة `div` بأنماط inline خارج الغلاف الموحّد — بلا شريط
     عنوان ولا شريط حالة ولا تلميع الجلد. صارت `AseelDocumentShell` كبقية
     الخمسين شاشة: النصوص والأزرار كما هي حرفاً بحرف، والتغيير في الإطار. */
  const actions: AseelToolbarAction[] = [
    {
      key: "print",
      label: `طباعة / PDF${selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}`,
      icon: <Printer className="h-4 w-4" />,
      onClick: printPdf,
      disabled: filtered.length === 0,
    },
    {
      key: "group",
      label: `تعيين النوع${selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}`,
      icon: <Tags className="h-4 w-4" />,
      onClick: () => setGroupModal(true),
      disabled: selectedIds.size === 0,
    },
    {
      key: "reload",
      label: "تحديث",
      icon: <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />,
      onClick: load,
      separatorBefore: true,
    },
  ];

  return (
    <AseelDocumentShell
      title="أرصدة المخزون"
      actions={actions}
      status={(
        <>
          {summary && (
            <span className="aseel-status-item">
              إجمالي الأصناف: <b>{summary.total_products_in_stock ?? products.length}</b>
            </span>
          )}
          {summary && (
            <span className="aseel-status-item">
              قيمة المخزون: <b>{fmt(Number(summary.total_inventory_value ?? 0))}</b>
            </span>
          )}
          <span className="aseel-status-item">
            إجمالي القيمة ({filtered.length} صنف): <b>{fmt(totalVal)}</b>
          </span>
        </>
      )}
      header={(
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="aseel-input w-[180px]"
            placeholder="بحث SKU / الاسم…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="aseel-input w-[140px]"
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
          >
            <option value="">كل التصنيفات</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            className="aseel-input w-[140px]"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as "" | "low" | "out" | "over")}
          >
            <option value="">كل الحالات</option>
            <option value="low">منخفض</option>
            <option value="out">نفذ</option>
            <option value="over">فوق الحد الأقصى</option>
          </select>
          <label
            className="aseel-status-item flex cursor-pointer items-center gap-1"
            title="تحديد/إلغاء كل المعروض"
          >
            <input type="checkbox" checked={allFilteredSelected} onChange={toggleAll} />
            تحديد الكل
          </label>
        </div>
      )}
    >

      {err && (
        <div className="aseel-banner aseel-banner--err">{err}</div>
      )}

      {groupModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !groupBusy && setGroupModal(false)}>
          <div dir="rtl" className="w-full max-w-md rounded-xl border aseel-border-soft aseel-bg-field p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-sm font-bold aseel-text-ink">
              تعيين النوع/البراند لـ{selectedIds.size} صنف
            </h3>
            <p className="mb-3 text-[11px] aseel-text-soft leading-relaxed">
              «النوع» يجمع الموديلات المتبادلة: أصنافُ النوع الواحد تظهر بدائلَ لبعضها في
              بند الفاتورة، ويقرأها تقرير التجديد فلا يطلب موديلاً قديماً وموديلٌ أحدث منه
              على الرفّ. الحقل المتروك فارغاً هنا لا يُمَسّ على الأصناف.
            </p>
            <label className="mb-2 block text-xs aseel-text-soft">
              النوع / المجموعة
              <input className="aseel-input mt-1 w-full" value={groupValue} autoFocus
                placeholder="مثال: ايفون 14 برو"
                onChange={(e) => setGroupValue(e.target.value)} />
            </label>
            <label className="mb-3 block text-xs aseel-text-soft">
              البراند (اختياري)
              <input className="aseel-input mt-1 w-full" value={brandValue}
                placeholder="مثال: سامسونج"
                onChange={(e) => setBrandValue(e.target.value)} />
            </label>
            <div className="flex justify-start gap-2">
              <button className="aseel-toolbtn" onClick={applyGroup} disabled={groupBusy}>
                {groupBusy ? "جارٍ التعيين…" : "تعيين"}
              </button>
              <button className="aseel-toolbtn" onClick={() => setGroupModal(false)} disabled={groupBusy}>
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}

      <AseelDenseTable<SqlProduct>
        columns={columns}
        rows={filtered}
        getRowKey={(p) => p.id}
        loading={loading}
        emptyHint="لا توجد أصناف"
        footer={
          <span className="font-bold aseel-text-ink">
            إجمالي القيمة ({filtered.length} صنف):{" "}
            <span className="aseel-text-accent">{fmt(totalVal)}</span>
          </span>
        }
      />
    </AseelDocumentShell>
  );
};
