/**
 * جدول منتجات شجري بأي عمق (نمط المواقع الاحترافية): يعرض **شجرة التصنيفات** كما بناها
 * المستخدم (أب/ابن/حفيد... بلا حدّ)، والمنتجات أوراق تحت تصنيفاتها. كبسة على أي تصنيف
 * ⇒ الكرت المجمّع لكل ما تحته (بكل الأعماق)؛ كبسة على منتج ⇒ كرته (عبر عمود الاسم).
 * يعيد استخدام نفس أعمدة KitDenseTable وتنسيقها (DRY). الافتراضي **مفتوح**.
 */
import React, { useState } from "react";
import { ChevronDown, ChevronLeft, FolderTree } from "lucide-react";
import type { DenseColumn } from "../kit/KitDenseTable";
import type { SqlProduct } from "../../types/inventory";
import { formatQuantity } from "../../utils/formatNumber";
import { buildCategoryIndex, descendantIds as descendantCategoryIds } from "../../utils/categoryTree";
import { groupProductsByFamily, buildFamilyRow, type ProductGroup } from "../../utils/familyGrouping";

export type TreeCategory = { id: number; name: string; parent: number | null };

type Props = {
  columns: DenseColumn<SqlProduct>[];
  rows: SqlProduct[];
  categories: TreeCategory[];
  getRowKey: (p: SqlProduct) => string | number;
  loading?: boolean;
  emptyHint?: string;
  sortKey?: string;
  sortDir?: "asc" | "desc";
  onSort?: (key: string, dir: "asc" | "desc") => void;
  onRowDoubleClick?: (p: SqlProduct) => void;
  /** الكرت المجمّع لتصنيف: كل معرّفات المنتجات تحته (وكل أحفاده) + اسم التصنيف.
   *  `categoryId` يغني عن تعداد المعرّفات في الطلب (الخادم يشتقّها) — يغيب في
   *  عقدة «بدون تصنيف» وحدها فتبقى معرّفاتها صريحة. */
  onShowGroup: (ids: string[], name: string, categoryId?: number) => void;
};

const UNCAT = -1; // تصنيف افتراضي «بدون تصنيف» للمنتجات بلا تصنيف.

export const GroupedItemsTable: React.FC<Props> = ({
  columns, rows, categories, getRowKey, loading, emptyHint = "لا توجد منتجات",
  sortKey, sortDir, onSort, onRowDoubleClick, onShowGroup,
}) => {
  // مفتوحة افتراضياً: البدء بالطيّ كان يُخفي كل المنتجات تحت اسم التصنيف فتبدو
  // الشاشة فارغة. `collapsed` تحمل ما طواه المستخدم فقط (الجديد يبقى مفتوحاً).
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const isExpanded = (id: number) => !collapsed.has(id);
  const toggle = (id: number) =>
    setCollapsed((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  // #23: كشف براندات منتجٍ داخل صفّه — بمعرّف الأب (`family_id`)، مطويٌّ افتراضياً
  // (الشجرة تنتهي عند المنتج؛ البراندات تُكشَف حين تُطلَب لا دائماً).
  const [expandedFamilies, setExpandedFamilies] = useState<Set<number>>(new Set());
  const toggleFamily = (familyId: number) =>
    setExpandedFamilies((s) => { const n = new Set(s); n.has(familyId) ? n.delete(familyId) : n.add(familyId); return n; });

  const getAlign = (col: DenseColumn<SqlProduct>) => col.align || (col.numeric ? "right" : "left");
  const handleSort = (col: DenseColumn<SqlProduct>) => {
    if (!col.sortable || !onSort) return;
    onSort(col.key, sortKey === col.key && sortDir === "asc" ? "desc" : "asc");
  };

  // T-ITEMS M2: فهرسة التصنيفات من `utils/categoryTree` — كانت نسخةً رابعة من
  // الخوارزمية نفسها، ونزولُها إلى الأحفاد كان **تعاوداً بلا حارس**: حلقةٌ في
  // البيانات تعني تعاوداً لا نهائياً وشاشةً بيضاء.
  const { byId: catById, childrenOf } = buildCategoryIndex<TreeCategory>(categories);
  const productsOf = new Map<number, SqlProduct[]>();
  for (const p of rows) {
    // منتج بتصنيف غير موجود بالقائمة يُعامل كـ«بدون تصنيف».
    const cid = p.category != null && catById.has(String(p.category)) ? Number(p.category) : UNCAT;
    if (!productsOf.has(cid)) productsOf.set(cid, []);
    productsOf.get(cid)!.push(p);
  }

  // كل معرّفات المنتجات تحت تصنيف (بكل الأعماق) + مجموع الكمية — من مجموعة
  // الأحفاد المحسوبة مرّةً واحدة بلا تعاود.
  const descendantIds = (catId: number): string[] =>
    descendantCategoryIds(categories, catId)
      .flatMap((id) => (productsOf.get(Number(id)) || []).map((p) => String(p.id)));
  const descendantQty = (catId: number): number =>
    descendantCategoryIds(categories, catId).reduce<number>(
      (sum, id) => sum + (productsOf.get(Number(id)) || [])
        .reduce((s, p) => s + Number(p.quantity_on_hand || 0), 0),
      0,
    );

  // سطر منتج (ورقة) — إزاحة الاسم حسب العمق. `reveal` حاضرةٌ فقط لصفّ منتجٍ
  // مجمَّع (أكثر من براند): تضيف عنصر الكشف الصغير داخل عمود الاسم — لا صفٌّ
  // إضافي (#23: «بديش يبين الأب والابن — بدي يبين منتج وبحدّو كلمة صغير أظهر
  // براندات»). اسم الصفّ حينها اسم المنتج المشترك، لا اسم براندٍ بعينه — فتحريره
  // هنا مضلِّل (يكتب فعلياً على براندٍ واحد فقط)، لذا يُعرض نصّاً ثابتاً بلا
  // تحرير مضمَّن، بخلاف صفّ البراند المفرد الذي يحتفظ بسلوكه القائم كاملاً.
  const renderRow = (
    p: SqlProduct,
    depth: number,
    reveal?: { count: number; expanded: boolean; onToggle: () => void; rowKey: string },
  ) => (
    <tr key={reveal ? reveal.rowKey : `p-${getRowKey(p)}`} onDoubleClick={() => onRowDoubleClick?.(p)}>
      {columns.map((col, ci) => {
        const isNameCol = col.key === "name_ar";
        return (
          <td
            key={col.key}
            style={{
              textAlign: getAlign(col) as React.CSSProperties["textAlign"],
              ...(ci === 1 ? { paddingInlineStart: depth * 22 } : {}),
            }}
            className={col.numeric ? "ktra-num" : ""}
          >
            {reveal && isNameCol ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, minWidth: 0, width: "100%" }}>
                <button
                  type="button"
                  className="ktra-iconbtn"
                  title={reveal.expanded ? "طيّ البراندات" : `إظهار البراندات (${reveal.count})`}
                  onClick={(e) => { e.stopPropagation(); reveal.onToggle(); }}
                >
                  {reveal.expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
                </button>
                <span
                  className="truncate"
                  style={{ minWidth: 0, flex: 1, fontWeight: 600 }}
                  title={p.display_name || p.name_ar || ""}
                >
                  {p.display_name || p.name_ar || p.name_en || "—"}
                </span>
                <span style={{ color: "var(--ktra-ink-soft)", fontSize: 11, flexShrink: 0 }}>
                  ({reveal.count})
                </span>
              </span>
            ) : (
              col.render ? col.render(p, 0) : String((p as unknown as Record<string, unknown>)[col.key] ?? "")
            )}
          </td>
        );
      })}
    </tr>
  );

  // #23: عقدة منتجٍ واحدة (فرد) أو مجمَّعة (أكثر من براند) — الأخيرة صفٌّ واحدٌ
  // بمجموع الأرصدة (`buildFamilyRow`، مشتقٌّ لا مخزَّن) مع عنصر كشفٍ، وتوسيعها
  // يُنزل كل براندٍ صفّاً مستقلاً بأرقامه الخاصة تحته — لا يمسّ منتجاً بلا أبٍ
  // (`familyId === null`): يبقى صفّه كما هو اليوم بلا أي عنصر إضافي.
  const renderGroupNodes = (group: ProductGroup, depth: number): React.ReactNode[] => {
    if (group.members.length <= 1) return [renderRow(group.members[0], depth)];
    const familyId = group.familyId as number;
    const expanded = expandedFamilies.has(familyId);
    const nodes: React.ReactNode[] = [
      renderRow(buildFamilyRow(group.members), depth, {
        count: group.members.length,
        expanded,
        onToggle: () => toggleFamily(familyId),
        rowKey: `fam-${familyId}`,
      }),
    ];
    if (expanded) {
      for (const m of group.members) nodes.push(renderRow(m, depth + 1));
    }
    return nodes;
  };

  // صفّ تصنيف: سهم طيّ + مجلّد + اسم (كبسة ⇒ كرت مجمّع) + عدد + مجموع الكمية.
  const renderCatNode = (catId: number, name: string, depth: number) => {
    const open = isExpanded(catId);
    const ids = descendantIds(catId);
    return (
      <tr key={`c-${catId}`} style={{ background: depth === 0 ? "var(--ktra-bg-soft,#e7ecf1)" : "var(--ktra-bg-soft,#f1f3f5)" }}>
        {columns.map((col, ci) => {
          if (ci === 0) {
            return (
              <td key={col.key} style={{ textAlign: "center" }}>
                <button type="button" className="ktra-iconbtn" title={open ? "طيّ" : "فتح"} onClick={() => toggle(catId)}>
                  {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
                </button>
              </td>
            );
          }
          if (col.key === "name_ar") {
            return (
              <td key={col.key}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, paddingInlineStart: depth * 22 }}>
                  <FolderTree className="h-4 w-4" style={{ color: "var(--ktra-primary,#1857a4)", flexShrink: 0 }} />
                  <button type="button" className="hover:underline"
                    style={{ fontWeight: 700, color: "var(--ktra-primary,#1857a4)", background: "none", border: "none", padding: 0, cursor: "pointer" }}
                    onClick={() => (ids.length ? onShowGroup(ids, name, catId === UNCAT ? undefined : catId) : toggle(catId))}
                    title="كرت مجمّع لكل ما تحت التصنيف">
                    {name} <span style={{ color: "var(--ktra-ink-soft)", fontWeight: 400 }}>({ids.length})</span>
                  </button>
                </div>
              </td>
            );
          }
          if (col.key === "qty") {
            return <td key={col.key} style={{ textAlign: "center", fontWeight: 700 }}>{formatQuantity(descendantQty(catId))}</td>;
          }
          return <td key={col.key} />;
        })}
      </tr>
    );
  };

  // بناء الشجرة (recursive) من الجذور، ثم «بدون تصنيف» في الأسفل.
  const body: React.ReactNode[] = [];
  const walk = (cat: TreeCategory, depth: number) => {
    body.push(renderCatNode(cat.id, cat.name, depth));
    if (!isExpanded(cat.id)) return;
    for (const ch of childrenOf.get(String(cat.id)) || []) walk(ch, depth + 1);
    for (const group of groupProductsByFamily(productsOf.get(cat.id) || []))
      body.push(...renderGroupNodes(group, depth + 1));
  };
  for (const root of childrenOf.get(null) || []) walk(root, 0);
  const uncategorized = productsOf.get(UNCAT) || [];
  if (uncategorized.length) {
    body.push(renderCatNode(UNCAT, "بدون تصنيف", 0));
    if (isExpanded(UNCAT)) {
      for (const group of groupProductsByFamily(uncategorized)) body.push(...renderGroupNodes(group, 1));
    }
  }

  return (
    <div className="ktra-dense-table">
      <table className="ktra-grid" data-variant="list">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width, textAlign: getAlign(col) as React.CSSProperties["textAlign"] }}
                className={col.sortable && onSort ? "ktra-sortable" : ""}
                onClick={() => handleSort(col)}
              >
                {col.header}
                {/* المثلّث زخرفة — انظر التعليل في `KitDenseTable.tsx`. */}
                {sortKey === col.key && (
                  <span className="ktra-sort-indicator" aria-hidden="true">{sortDir === "asc" ? "▲" : "▼"}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && rows.length === 0 && (
            <tr className="ktra-row--empty"><td colSpan={columns.length} style={{ textAlign: "center", padding: 16 }}>جاري التحميل…</td></tr>
          )}
          {!loading && rows.length === 0 && (
            <tr className="ktra-row--empty"><td colSpan={columns.length} style={{ textAlign: "center", padding: 16, color: "var(--ktra-ink-soft)" }}>{emptyHint}</td></tr>
          )}
          {body}
        </tbody>
      </table>
    </div>
  );
};
