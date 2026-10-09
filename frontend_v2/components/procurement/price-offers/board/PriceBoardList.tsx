/**
 * تبويب «جداول الأسعار» في شاشة العروض الدولية (PB-2): قائمة الجولات (جدول لكل
 * جولة تسعير) مع فلتر الأرشيف و«جدول جديد» وأرشفة/استرجاع، ثم فتح جدولٍ إلى
 * `PriceBoardSheet`.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { CommercialDocumentsList } from "../../../shared/CommercialDocumentsList";
import type { DenseColumn } from "../../../kit/KitDenseTable";
import { useToast } from "../../../../contexts/ToastContext";
import {
  createPriceBoard,
  listPriceBoards,
  updatePriceBoard,
  type PriceBoardSummaryDto,
} from "../../../../services/priceBoardApi";
import type { Item } from "../../../../types/product";
import type { Supplier } from "../../../../types/supplier";
import { formatNumber } from "../../../../utils/formatNumber";
import { formatDateValue } from "../../../../utils/formatDate";
import { BoardDialog, PriceBoardSheet } from "./PriceBoardSheet";

interface Props {
  products: Item[];
  suppliers: Supplier[];
}

export const PriceBoardList: React.FC<Props> = ({ products, suppliers }) => {
  const toast = useToast();
  const [boards, setBoards] = useState<PriceBoardSummaryDto[]>([]);
  const [archived, setArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    if (openId !== null) return;
    let active = true;
    setLoading(true);
    setError(null);
    listPriceBoards(archived)
      .then((rows) => { if (active) setBoards(rows); })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : "تعذّر تحميل جداول الأسعار");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
    // العودة من جدول مفتوح (openId → null) تعيد التحميل فتتحدّث العدّادات.
  }, [archived, reloadKey, openId]);

  const toggleArchive = useCallback(async (row: PriceBoardSummaryDto) => {
    setBusyId(row.id);
    try {
      await updatePriceBoard(row.id, { is_archived: !row.is_archived });
      setBoards((prev) => prev.filter((b) => b.id !== row.id));
      toast(row.is_archived ? "أُعيد الجدول من الأرشيف" : "نُقل الجدول إلى الأرشيف", "success");
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّر تغيير حالة الأرشيف", "error");
    } finally {
      setBusyId(null);
    }
  }, [toast]);

  const columns = useMemo<DenseColumn<PriceBoardSummaryDto>[]>(() => [
    { key: "title", header: "الجدول",
      render: (b) => (
        <div className="min-w-0 leading-tight">
          <div className="truncate font-semibold" title={b.title}>{b.title}</div>
          {b.notes && <div className="line-clamp-2 text-[10px] ktra-text-soft" title={b.notes}>{b.notes}</div>}
        </div>
      ) },
    { key: "created", header: "التاريخ", width: "100px", render: (b) => <>{formatDateValue(b.created_at)}</> },
    { key: "items", header: "الأصناف", width: "80px", align: "center", render: (b) => <>{formatNumber(b.items_count)}</> },
    { key: "suppliers", header: "الموردون", width: "80px", align: "center", render: (b) => <>{formatNumber(b.suppliers_count)}</> },
    { key: "prices", header: "الأسعار", width: "80px", align: "center", render: (b) => <>{formatNumber(b.prices_count)}</> },
    { key: "actions", header: "إجراءات", width: "170px", align: "center",
      render: (b) => (
        <div className="flex items-center justify-center gap-3 text-xs">
          <button type="button" className="ktra-text-accent hover:underline"
            onClick={(e) => { e.stopPropagation(); setOpenId(b.id); }}>
            فتح
          </button>
          <button type="button" className="ktra-text-accent hover:underline disabled:opacity-50" disabled={busyId === b.id}
            onClick={(e) => { e.stopPropagation(); void toggleArchive(b); }}>
            {b.is_archived ? "استرجاع" : "أرشفة"}
          </button>
        </div>
      ) },
  ], [busyId, toggleArchive]);

  const submitCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setCreateError("اكتب عنواناً للجدول");
      return;
    }
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createPriceBoard({ title: title.trim(), notes: notes.trim() });
      setCreating(false);
      setTitle("");
      setNotes("");
      setOpenId(created.id);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : "تعذّر إنشاء الجدول");
    } finally {
      setCreateBusy(false);
    }
  };

  if (openId !== null) {
    return (
      <PriceBoardSheet
        key={openId}
        boardId={openId}
        products={products}
        suppliers={suppliers}
        onBack={() => setOpenId(null)}
      />
    );
  }

  return (
    <>
      <CommercialDocumentsList<PriceBoardSummaryDto>
        title="جداول أسعار الاستيراد"
        state="أصناف × موردون — قارن الأسعار في جولة واحدة"
        rows={boards}
        columns={columns}
        getRowKey={(b) => b.id}
        loading={loading}
        error={error}
        emptyHint={archived ? "لا توجد جداول مؤرشفة" : "لا توجد جداول بعد — ابدأ بجدول جديد"}
        countLabel={`${formatNumber(boards.length)} جدول`}
        statusValue={archived ? "archived" : "active"}
        statusOptions={[
          { value: "active", label: "الجداول الجارية" },
          { value: "archived", label: "المؤرشفة" },
        ]}
        onStatusChange={(value) => setArchived(value === "archived")}
        onNew={() => { setCreateError(null); setCreating(true); }}
        onReload={() => setReloadKey((key) => key + 1)}
        newLabel="جدول جديد"
        onRowDoubleClick={(b) => setOpenId(b.id)}
      />
      {creating && (
        <BoardDialog title="جدول أسعار جديد" onClose={() => { if (!createBusy) setCreating(false); }}>
          <form className="flex flex-col gap-3" onSubmit={(e) => { void submitCreate(e); }}>
            <label className="flex flex-col gap-1">
              <span className="text-xs ktra-text-soft">عنوان الجولة</span>
              <input
                autoFocus
                className="ktra-input"
                placeholder="مثال: بلاط وصحيات — خريف 2026"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs ktra-text-soft">ملاحظات (اختياري)</span>
              <textarea className="ktra-input min-h-20" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
            {createError && <p className="text-xs text-[var(--ktra-danger)]" role="alert">{createError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" className="ktra-btn" disabled={createBusy} onClick={() => setCreating(false)}>إلغاء</button>
              <button type="submit" className="ktra-btn-primary px-4 py-1.5 text-sm font-semibold disabled:opacity-50" disabled={createBusy}>
                {createBusy ? <Loader2 className="inline h-4 w-4 animate-spin" /> : "إنشاء وفتح"}
              </button>
            </div>
          </form>
        </BoardDialog>
      )}
    </>
  );
};
