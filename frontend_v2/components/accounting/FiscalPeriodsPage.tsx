import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { FiscalPeriodDto } from "../../types/accounting";
import {
  AseelDocumentShell,
  AseelDenseTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, DenseColumn } from "../aseel";
import { Plus, Lock, Unlock } from "lucide-react";

export const FiscalPeriodsPage: React.FC = () => {
  const [periods, setPeriods] = useState<FiscalPeriodDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newYear, setNewYear] = useState(new Date().getFullYear().toString());
  const [busy, setBusy] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

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
    try {
      await accountingApi.createFiscalYear(y);
      setShowAddForm(false);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ");
    } finally {
      setBusy(false);
    }
  };

  const togglePeriod = async (p: FiscalPeriodDto) => {
    setBusy(true);
    try {
      if (p.is_closed) {
        await accountingApi.reopenFiscalPeriod(p.id);
      } else {
        await accountingApi.closeFiscalPeriod(p.id);
      }
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
          className="aseel-toolbtn"
          disabled={busy}
          onClick={(e) => { e.stopPropagation(); togglePeriod(p); }}
        >
          {p.is_closed ? <><Unlock className="w-3 h-3" /> إعادة فتح</> : <><Lock className="w-3 h-3" /> إغلاق</>}
        </button>
      ),
    },
  ];

  const actions: AseelToolbarAction[] = [
    { key: "new", label: "إضافة سنة", icon: <Plus className="w-4 h-4" />, onClick: () => setShowAddForm(!showAddForm) },
    { key: "refresh", label: "تحديث", onClick: load },
  ];

  const addYearBand = showAddForm ? (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "12px" }}>
      <div className="aseel-field">
        <label className="aseel-field-label">السنة المالية</label>
        <input
          type="number"
          min={2000}
          max={2100}
          className="aseel-input aseel-num"
          style={{ width: "100px" }}
          value={newYear}
          onChange={(e) => setNewYear(e.target.value)}
        />
      </div>
      <button type="button" className="aseel-toolbtn" disabled={busy} onClick={createYear}
        style={{ marginTop: "18px" }}>
        <Plus className="w-4 h-4" />
        إنشاء FY {newYear}
      </button>
      <span style={{ marginTop: "22px", fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
        يناير 1 — ديسمبر 31
      </span>
    </div>
  ) : <></>;

  const tableContent = (
    <>
      {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <AseelDenseTable<FiscalPeriodDto>
        columns={columns}
        rows={periods}
        getRowKey={(p) => p.id}
        loading={loading}
        emptyHint="لا توجد فترات مالية"
      />
    </>
  );

  const tabs: AseelTab[] = [
    { key: "periods", label: "الفترات المالية", content: tableContent },
  ];

  return (
    <div data-skin="aseel">
      <AseelDocumentShell
        title="الفترات المالية"
        actions={actions}
        header={addYearBand}
        tabs={tabs}
        status={
          <span className="aseel-status-item">{periods.length} فترة</span>
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
