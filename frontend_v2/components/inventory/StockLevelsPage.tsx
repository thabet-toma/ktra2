import React, { useEffect, useState, useCallback } from "react";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { inventoryApi } from "../../services/inventoryApi";
import type { SqlProduct, StockSummaryResponse } from "../../types/inventory";
import { KitDenseTable, type DenseColumn } from "../kit/KitDenseTable";
import { KitDocumentShell, type KitToolbarAction } from "../kit/KitDocumentShell";
import { RefreshCw, Download, Printer, Tags, Pencil, ExternalLink } from "lucide-react";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { productProfilePath } from "../../utils/entityLinks";
import { openInNewTab } from "../../utils/openInNewTab";
import { useSimpleUi } from "../../hooks/useSimpleUi";
import { ItemQuickEditModal } from "../items/ItemQuickEditModal";

// مبالغ مالية — يحذف الأصفار العشرية غير الدالّة (6.00 ⇒ 6، 6.50 ⇒ 6.5) عبر المُنسّق الموحّد.
const fmt = (n: number | string) => formatMoney(n, "0");

export const StockLevelsPage: React.FC = () => {
  const [products, setProducts] = useState<SqlProduct[]>([]);
  const toast = useToast();
  const { show: showAdv, columns: maskColumns } = useSimpleUi();
  const [summary, setSummary] = useState<StockSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // فلاتر
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<"" | "low" | "out" | "over">("");
  const [filterCategory, setFilterCategory] = useState<string>("");
  // task16 E18: اختيار المنتجات للتصدير
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  // T-REORDER: تعيين «الصنف» على المحدَّد — الحقل الذي بلا مدخلٍ جماعي يبقى فارغاً
  // أبداً على كتالوجٍ من ألفٍ ونصف، وبفراغه يسقط تجميع الموديلات كلّه.
  const [groupModal, setGroupModal] = useState(false);
  const [groupValue, setGroupValue] = useState("");
  const [brandValue, setBrandValue] = useState("");
  const [groupBusy, setGroupBusy] = useState(false);
  // T-PRODUCT: التحرير السريع من هذه الشاشة أيضاً — الاسم كان زرّاً أزرق مسطَّراً
  // يقول «رابط» ولا طريقَ منه لتعديل المنتج، كما كان في شاشة المنتجات قبلها.
  const [quickEditProductId, setQuickEditProductId] = useState<number | null>(null);

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
      toast("اكتب صنفاً أو برانداً للتعيين.", "info");
      return;
    }
    setGroupBusy(true);
    try {
      const res = await inventoryApi.bulkSetGroup(ids, fields);
      toast(`عُيِّن على ${res.updated} منتجاً.`, "success");
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
                <th>البضاعة (المنتج)</th>
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
      return <span className="ktra-text-danger">نفذ</span>;
    if (p.stock_status === "low_stock")
      return <span className="ktra-text-warn">منخفض</span>;
    // T-REORDER: «فائض» = فوق الحدّ الأقصى المضبوط على المنتج. كان الفلتر يخمّنه
    // بـ«أكثر من ثلاثة أضعاف الأدنى» — قاعدةٌ لا مصدر لها.
    if (p.stock_status === "overstock")
      return <span className="ktra-text-warn">فائض</span>;
    return <span className="ktra-text-ok">متوفر</span>;
  };

  const allColumns: DenseColumn<SqlProduct>[] = [
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
    /* T-PRODUCT: الاسم نصٌّ لا رابط — كان أزرقَ مسطَّراً يعد بالانتقال ولا يعطي
       طريقاً للتعديل. الوجهتان صارتا أيقونتين صريحتين بجانبه (قلم: تحرير سريع
       في مكانه · سهم: حركة المخزون في تبويب مستقل)، وهو نفس ترتيب شاشة
       المنتجات — لا اصطلاح ثانٍ يتعلّمه المستخدم. */
    { key: "name", header: "المنتج", render: (p) => (
        <span className="group flex min-w-0 items-center gap-1">
          <span className="min-w-0 flex-1 truncate text-start" title={p.name_ar || p.name_en || undefined}>
            {p.name_ar || p.name_en || "—"}
          </span>
          <button
            type="button"
            className="ktra-iconbtn opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
            title="تعديل سريع للمنتج"
            aria-label="تعديل سريع للمنتج"
            onClick={(e) => { e.stopPropagation(); setQuickEditProductId(p.id); }}
          ><Pencil className="h-3 w-3" /></button>
          <button
            type="button"
            className="ktra-iconbtn opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
            title="فتح حركة مخزون المنتج في تبويب مستقل"
            aria-label="فتح حركة مخزون المنتج في تبويب مستقل"
            onClick={(e) => { e.stopPropagation(); openInNewTab(productProfilePath(p.id)); }}
          ><ExternalLink className="h-3 w-3" /></button>
        </span>
      ) },
    { key: "cat", header: "التصنيف", width: "130px", render: (p) => <>{p.category_name || "—"}</> },
    // T-RESERVE: «المتاح» كان يعرض الرصيد نفسه — تسمية مضلِّلة بعد وجود الحجز.
    // الرصيد ثم المحجوز (طلبيات مؤكَّدة سارية) ثم المتاح للبيع = الفرق.
    { key: "qty", header: "الرصيد", width: "90px", align: "center", numeric: true,
      render: (p) => {
        const qty = Number(p.quantity_on_hand);
        const low = p.stock_status === "out_of_stock" || p.stock_status === "low_stock";
        return <span style={low ? { color: "var(--ktra-danger, #c00)", fontWeight: 600 } : {}}>{formatQuantity(qty)}</span>;
      }
    },
    { key: "reserved", header: "محجوز", width: "80px", align: "center", numeric: true,
      render: (p) => {
        const reserved = Number(p.reserved_quantity || 0);
        if (!reserved) return <span className="text-[var(--ktra-ink-soft)]">—</span>;
        return (
          <span title="محجوز بطلبيات زبائن مؤكَّدة سارية"
            className="ktra-text-warn font-semibold">
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
    // T-REORDER: «الصنف» ظاهر كي يُرى فارغاً. حين يكون بلا قيمة يسقط التجميع على
    // اسم المنتج ⇒ كل منتجٍ صنفٌ بذاته ⇒ لا بدائل ولا قرار «مؤجَّل».
    { key: "grp", header: "الصنف", width: "130px",
      render: (p) => p.variant_group
        ? <>{p.variant_group}</>
        : <span className="ktra-text-soft" title="بلا صنف — لن تظهر له بدائل في الفاتورة">—</span> },
    { key: "status", header: "الحالة", width: "80px", align: "center", render: statusCell },
    { key: "avgcost", header: "متوسط التكلفة", width: "110px", align: "center", numeric: true,
      render: (p) => <>{fmt(Number(p.avg_cost))}</> },
    { key: "val", header: "القيمة", width: "110px", align: "center", numeric: true,
      render: (p) => <>{fmt(Number(p.quantity_on_hand) * Number(p.avg_cost))}</> },
  ];

  /* T-SIMPL2: أعمدة الحجز والحدّ الأقصى و«الصنف» تُطوى في الوضع السهل — و«محجوز»
     و«المتاح» يعودان لحظة يوجد حجزٌ فعلاً: رصيدٌ لا يُباع منه لا يُخفى عن بائعه. */
  const anyReserved = filtered.some((p) => Number(p.reserved_quantity || 0) > 0);
  const columns = maskColumns(
    allColumns,
    "stock-levels",
    anyReserved ? ["reserved", "available"] : [],
  );

  // footer: مجاميع
  const totalVal = filtered.reduce(
    (s, p) => s + Number(p.quantity_on_hand) * Number(p.avg_cost), 0
  );

  /* T-WIN M7: كانت الشاشة `div` بأنماط inline خارج الغلاف الموحّد — بلا شريط
     عنوان ولا شريط حالة ولا تلميع الجلد. صارت `KitDocumentShell` كبقية
     الخمسين شاشة: النصوص والأزرار كما هي حرفاً بحرف، والتغيير في الإطار. */
  const actions: KitToolbarAction[] = [
    {
      key: "print",
      label: `طباعة / PDF${selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}`,
      icon: <Printer className="h-4 w-4" />,
      onClick: printPdf,
      disabled: filtered.length === 0,
    },
    /* T-SIMPL2: التعيين الجماعي لـ«الصنف/البراند» إعدادُ كتالوج لا عملٌ يومي —
       يُطوى في الوضع السهل مع عمود «الصنف» الذي يخدمه. */
    ...(showAdv("stock.bulk-group") ? [{
      key: "group",
      label: `تعيين الصنف${selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}`,
      icon: <Tags className="h-4 w-4" />,
      onClick: () => setGroupModal(true),
      disabled: selectedIds.size === 0,
    }] : []),
    {
      key: "reload",
      label: "تحديث",
      icon: <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />,
      onClick: load,
      separatorBefore: true,
    },
  ];

  return (
    <KitDocumentShell
      title="أرصدة المخزون"
      actions={actions}
      status={(
        <>
          {summary && (
            <span className="ktra-status-item">
              إجمالي المنتجات: <b>{summary.total_products_in_stock ?? products.length}</b>
            </span>
          )}
          {summary && (
            <span className="ktra-status-item">
              قيمة المخزون: <b>{fmt(Number(summary.total_inventory_value ?? 0))}</b>
            </span>
          )}
          <span className="ktra-status-item">
            إجمالي القيمة ({filtered.length} منتج): <b>{fmt(totalVal)}</b>
          </span>
        </>
      )}
      header={(
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="ktra-input w-[180px]"
            placeholder="بحث SKU / الاسم…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="ktra-input w-[140px]"
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
          >
            <option value="">كل التصنيفات</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            className="ktra-input w-[140px]"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as "" | "low" | "out" | "over")}
          >
            <option value="">كل الحالات</option>
            <option value="low">منخفض</option>
            <option value="out">نفذ</option>
            <option value="over">فوق الحد الأقصى</option>
          </select>
          <label
            className="ktra-status-item flex cursor-pointer items-center gap-1"
            title="تحديد/إلغاء كل المعروض"
          >
            <input type="checkbox" checked={allFilteredSelected} onChange={toggleAll} />
            تحديد الكل
          </label>
        </div>
      )}
    >

      {err && (
        <div className="ktra-banner ktra-banner--err">{err}</div>
      )}

      {/* T-PRODUCT: نفس نافذة «التعديل السريع» التي يفتحها المستند وبطاقة المنتج
          — لا مسار حفظٍ ثانٍ. وترقيعُ حقول الاسم وحدها بعد الردّ: صفّ هذه
          الشاشة يحمل الرصيد والمحجوز والقيمة، وهي محسوبةٌ لا يعيدها ردّ التعديل. */}
      {quickEditProductId != null && (
        <ItemQuickEditModal
          productId={quickEditProductId}
          onClose={() => setQuickEditProductId(null)}
          onSaved={(updated) => {
            const id = Number(updated.id ?? quickEditProductId);
            setProducts((rows) => rows.map((r) => (r.id === id ? {
              ...r,
              name_ar: (updated.name_ar ?? r.name_ar ?? null) as string | null,
              name_en: (updated.name_en ?? r.name_en ?? null) as string | null,
            } : r)));
          }}
          onOpenFullCard={() => openInNewTab(productProfilePath(quickEditProductId))}
        />
      )}

      {groupModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !groupBusy && setGroupModal(false)}>
          <div dir="rtl" className="w-full max-w-md rounded-xl border ktra-border-soft ktra-bg-field p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-sm font-bold ktra-text-ink">
              تعيين الصنف/البراند لـ{selectedIds.size} منتج
            </h3>
            <p className="mb-3 text-[11px] ktra-text-soft leading-relaxed">
              «الصنف» يجمع الموديلات المتبادلة: منتجاتُ الصنف الواحد تظهر بدائلَ لبعضها في
              بند الفاتورة، ويقرأها تقرير التجديد فلا يطلب موديلاً قديماً وموديلٌ أحدث منه
              على الرفّ. الحقل المتروك فارغاً هنا لا يُمَسّ على المنتجات.
            </p>
            <label className="mb-2 block text-xs ktra-text-soft">
              الصنف / المجموعة
              <input className="ktra-input mt-1 w-full" value={groupValue} autoFocus
                placeholder="مثال: ايفون 14 برو"
                onChange={(e) => setGroupValue(e.target.value)} />
            </label>
            <label className="mb-3 block text-xs ktra-text-soft">
              البراند (اختياري)
              <input className="ktra-input mt-1 w-full" value={brandValue}
                placeholder="مثال: سامسونج"
                onChange={(e) => setBrandValue(e.target.value)} />
            </label>
            <div className="flex justify-start gap-2">
              <button className="ktra-toolbtn" onClick={applyGroup} disabled={groupBusy}>
                {groupBusy ? "جارٍ التعيين…" : "تعيين"}
              </button>
              <button className="ktra-toolbtn" onClick={() => setGroupModal(false)} disabled={groupBusy}>
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}

      <KitDenseTable<SqlProduct>
        columns={columns}
        rows={filtered}
        getRowKey={(p) => p.id}
        loading={loading}
        emptyHint="لا توجد منتجات"
        footer={
          <span className="font-bold ktra-text-ink">
            إجمالي القيمة ({filtered.length} منتج):{" "}
            <span className="ktra-text-accent">{fmt(totalVal)}</span>
          </span>
        }
      />
    </KitDocumentShell>
  );
};
