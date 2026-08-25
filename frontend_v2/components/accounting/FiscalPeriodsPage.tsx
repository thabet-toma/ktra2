import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import type { FiscalPeriodDto } from "../../types/accounting";
import {
  KitDocumentShell,
  KitDenseTable,
} from "../kit";
import type { KitToolbarAction, KitTab, DenseColumn } from "../kit";
import { Plus, Lock, Unlock } from "lucide-react";

type Granularity = "monthly" | "yearly";

export const FiscalPeriodsPage: React.FC = () => {
  const [periods, setPeriods] = useState<FiscalPeriodDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newYear, setNewYear] = useState(new Date().getFullYear().toString());
  const [granularity, setGranularity] = useState<Granularity>("monthly");
  const [busy, setBusy] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  // إعادة الفتح تحتاج سبباً مكتوباً — لوحة سطرية لأن حوار التأكيد بلا حقل إدخال.
  const [reopenTarget, setReopenTarget] = useState<FiscalPeriodDto | null>(null);
  const [reopenReason, setReopenReason] = useState("");
  const confirm = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await accountingApi.getFiscalPeriods();
      setPeriods(data as FiscalPeriodDto[]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createYear = async () => {
    const y = parseInt(newYear, 10);
    if (!y || y < 2000 || y > 2100) return;
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.createFiscalYear(y, granularity);
      setShowAddForm(false);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const sendClose = async (p: FiscalPeriodDto, force: boolean) => {
    setBusy(true);
    setErr(null);
    try {
      return await accountingApi.closeFiscalPeriod(p.id, force);
    } finally {
      setBusy(false);
    }
  };

  /** الإغلاق يتوقف عند القيود غير المرحّلة (409) ويسأل قبل التجاوز. */
  const closePeriod = async (p: FiscalPeriodDto) => {
    try {
      const res = await sendClose(p, false);
      if ((res as { requires_force?: boolean })?.requires_force) {
        const message = (res as { error?: string }).error
          ?? `توجد قيود غير مرحّلة في الفترة «${p.name}».`;
        const ok = await confirm({
          title: "قيود غير مرحّلة",
          message: `${message}\nالإغلاق رغم ذلك يُسجَّل في سجل التدقيق باسمك.`,
          confirmText: "أغلق رغم ذلك",
        });
        if (!ok) return;
        await sendClose(p, true);
      }
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    }
  };

  const submitReopen = async () => {
    const reason = reopenReason.trim();
    if (!reopenTarget || !reason) return;
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.reopenFiscalPeriod(reopenTarget.id, reason);
      setReopenTarget(null);
      setReopenReason("");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const fmtDate = (d: string) => {
    const [y, m, day] = d.split("-");
    return `${day}/${m}/${y}`;
  };

  const columns: DenseColumn<FiscalPeriodDto>[] = [
    { key: "name", header: "السنة", render: (p) => <strong>{p.name || p.start_date?.split("-")[0]}</strong> },
    { key: "start_date", header: "من تاريخ", render: (p) => fmtDate(p.start_date) },
    { key: "end_date", header: "إلى تاريخ", render: (p) => fmtDate(p.end_date) },
    {
      key: "status", header: "الحالة",
      render: (p) => p.is_closed ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", padding: "2px 8px", borderRadius: "12px", background: "#fee2e215", color: "#dc2626", fontSize: "0.75rem" }}>
          <Lock style={{ width: "12px", height: "12px" }} /> مغلقة
        </span>
      ) : (
        <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", padding: "2px 8px", borderRadius: "12px", background: "#dcfce715", color: "#16a34a", fontSize: "0.75rem" }}>
          <Unlock style={{ width: "12px", height: "12px" }} /> مفتوحة
        </span>
      ),
    },
    {
      key: "actions", header: "إجراءات",
      render: (p) => (
        <button
          type="button"
          className="ktra-toolbtn"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation();
            if (p.is_closed) {
              setReopenReason("");
              setReopenTarget(p);
            } else {
              closePeriod(p);
            }
          }}
        >
          {p.is_closed ? <><Unlock className="w-3 h-3" /> إعادة فتح</> : <><Lock className="w-3 h-3" /> إغلاق</>}
        </button>
      ),
    },
  ];

  const actions: KitToolbarAction[] = [
    { key: "new", label: "إضافة سنة", icon: <Plus className="w-4 h-4" />, onClick: () => setShowAddForm(!showAddForm) },
    { key: "refresh", label: "تحديث", onClick: load },
  ];

  const addYearBand = showAddForm ? (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "12px" }}>
      <div className="ktra-field">
        <label className="ktra-field-label">السنة المالية</label>
        <input
          type="number"
          min={2000}
          max={2100}
          className="ktra-input ktra-num"
          style={{ width: "100px" }}
          value={newYear}
          onChange={(e) => setNewYear(e.target.value)}
        />
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">تقسيم السنة</label>
        <div style={{ display: "flex", gap: "12px", alignItems: "center", height: "30px" }}>
          {([["monthly", "12 شهراً"], ["yearly", "سنة واحدة"]] as [Granularity, string][]).map(
            ([value, label]) => (
              <label key={value} style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "0.8rem" }}>
                <input
                  type="radio"
                  name="fiscal-granularity"
                  value={value}
                  checked={granularity === value}
                  onChange={() => setGranularity(value)}
                />
                {label}
              </label>
            ),
          )}
        </div>
      </div>
      <button type="button" className="ktra-toolbtn" disabled={busy} onClick={createYear}
        style={{ marginTop: "18px" }}>
        <Plus className="w-4 h-4" />
        {granularity === "monthly" ? `إنشاء أشهر ${newYear}` : `إنشاء FY ${newYear}`}
      </button>
      <span style={{ marginTop: "22px", fontSize: "0.75rem", color: "var(--ktra-ink-soft)" }}>
        {granularity === "monthly"
          ? `${newYear}-01 … ${newYear}-12 — يُقفَل كل شهر على حدة`
          : "يناير 1 — ديسمبر 31 — فترة واحدة تُقفَل كاملة"}
      </span>
    </div>
  ) : <></>;

  const reopenBand = reopenTarget ? (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "12px" }}>
      <div className="ktra-field" style={{ flex: "1 1 320px" }}>
        <label className="ktra-field-label">
          سبب إعادة فتح «{reopenTarget.name}» — يُحفظ في سجل التدقيق
        </label>
        <input
          type="text"
          className="ktra-input"
          autoFocus
          placeholder="مثال: تصحيح فاتورة مورّد وردت متأخرة"
          value={reopenReason}
          onChange={(e) => setReopenReason(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submitReopen(); }}
        />
      </div>
      <button type="button" className="ktra-toolbtn" disabled={busy || !reopenReason.trim()}
        onClick={submitReopen} style={{ marginTop: "18px" }}>
        <Unlock className="w-4 h-4" />
        إعادة الفتح
      </button>
      <button type="button" className="ktra-toolbtn" disabled={busy}
        onClick={() => { setReopenTarget(null); setReopenReason(""); }}
        style={{ marginTop: "18px" }}>
        إلغاء
      </button>
    </div>
  ) : <></>;

  const tableContent = (
    <>
      {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <KitDenseTable<FiscalPeriodDto>
        columns={columns}
        rows={periods}
        getRowKey={(p) => p.id}
        loading={loading}
        emptyHint="لا توجد فترات مالية"
      />
    </>
  );

  const tabs: KitTab[] = [
    { key: "periods", label: "الفترات المالية", content: tableContent },
  ];

  return (
    <div>
      <KitDocumentShell
        title="الفترات المالية"
        actions={actions}
        header={<>{addYearBand}{reopenBand}</>}
        tabs={tabs}
        status={
          <span className="ktra-status-item">{periods.length} فترة</span>
        }
      >
        <></>
      </KitDocumentShell>
    </div>
  );
};
