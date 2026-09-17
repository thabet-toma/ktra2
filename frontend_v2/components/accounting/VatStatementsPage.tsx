import React, { useState, useEffect, useCallback } from "react";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import { useConfirm } from "../../contexts/ConfirmContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import type { VatReportResponse, VatReportLine, VatStatementDto } from "../../types/accounting";
import {
  KitDocumentShell,
  KitDenseTable,
  KitReportTable,
} from "../kit";
import type { KitToolbarAction, KitTab, DenseColumn, ReportColumn } from "../kit";
import { Plus, Search, Lock, Unlock } from "lucide-react";
import OfflineGuard from "../offline/OfflineGuard";
import { formatDateLocalized } from "../../utils/formatDate";

/** نصّ حوار الاعتماد — يشرح القفل قبل أن يقع (A2-1، نمط Tax Lock Date). */
const finalizeMessage = (from: string, to: string) =>
  `اعتماد كشف الضريبة للفترة ${formatDateLocalized(from)} ← ${formatDateLocalized(to)} نهائياً؟\n` +
  "تُحفظ الأرقام من الدفتر لحظة الاعتماد، ثم يُمنع ترحيل أي مستند أو قيد بتاريخٍ داخل الفترة " +
  "ويُمنع التراجع عن ترحيله. إعادة الفتح للمدير وحده وبسببٍ يُسجَّل في سجل التدقيق.";

export const VatStatementsPage: React.FC = () => {
  const today = new Date();
  // VAT preview section
  const [previewFrom, setPreviewFrom] = useState(() => {
    const d = new Date(today.getFullYear(), today.getMonth(), 1);
    return d.toISOString().split("T")[0];
  });
  const [previewTo, setPreviewTo] = useState(today.toISOString().split("T")[0]);
  const [previewData, setPreviewData] = useState<VatReportResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();
  const { can, isManager } = usePermissions();
  const canFinalize = can("accounting.period.manage");
  const [showNewForm, setShowNewForm] = useState(false);

  // A2-1: الكشوف المحفوظة من الخادم.
  const [statements, setStatements] = useState<VatStatementDto[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listErr, setListErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reopenTarget, setReopenTarget] = useState<VatStatementDto | null>(null);
  const [reopenReason, setReopenReason] = useState("");

  const loadStatements = useCallback(async () => {
    setListLoading(true);
    setListErr(null);
    try {
      setStatements(await accountingApi.getVatStatements());
    } catch (e: unknown) {
      setListErr(humanizeThrown(e, "فشل تحميل الكشوف"));
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => { void loadStatements(); }, [loadStatements]);

  const runAction = async (fn: () => Promise<unknown>, okMessage: string) => {
    setBusy(true);
    try {
      await fn();
      toast(okMessage, "success");
      await loadStatements();
      return true;
    } catch (e: unknown) {
      toast(humanizeThrown(e, "تعذّر تنفيذ العملية"), "error");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const finalizeRow = async (row: VatStatementDto) => {
    if (!(await confirm({
      title: "اعتماد نهائي",
      message: finalizeMessage(row.period_from, row.period_to),
      confirmText: "اعتماد نهائي",
    }))) return;
    await runAction(() => accountingApi.finalizeVatStatement(row.id), `اعتُمد الكشف ${row.statement_number} نهائياً`);
  };

  const finalizePreviewPeriod = async () => {
    if (!(await confirm({
      title: "اعتماد نهائي",
      message: finalizeMessage(previewFrom, previewTo),
      confirmText: "اعتماد نهائي",
    }))) return;
    const ok = await runAction(
      () => accountingApi.finalizeVatStatementPeriod(previewFrom, previewTo),
      "اعتُمد كشف الفترة نهائياً",
    );
    if (ok) setShowNewForm(false);
  };

  const submitReopen = async () => {
    const reason = reopenReason.trim();
    if (!reopenTarget || !reason) return;
    const ok = await runAction(
      () => accountingApi.reopenVatStatement(reopenTarget.id, reason),
      `أُعيد فتح الكشف ${reopenTarget.statement_number}`,
    );
    if (ok) { setReopenTarget(null); setReopenReason(""); }
  };

  const fetchPreview = useCallback(async () => {
    setPreviewLoading(true);
    setPreviewErr(null);
    try {
      const resp = await accountingApi.getVatReport({
        start_date: previewFrom,
        end_date: previewTo,
      });
      setPreviewData(resp as VatReportResponse);
    } catch (e: unknown) {
      setPreviewErr(humanizeThrown(e, "فشل التحميل"));
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewFrom, previewTo]);

  useEffect(() => {
    if (showNewForm) fetchPreview();
  }, [showNewForm, fetchPreview]);

  const fmt = (n: number | undefined | null) => formatMoney(n);

  const stmtColumns: DenseColumn<VatStatementDto>[] = [
    { key: "statement_number", header: "رقم الكشف" },
    { key: "period_from", header: "من", render: (r) => formatDateLocalized(r.period_from) },
    { key: "period_to", header: "إلى", render: (r) => formatDateLocalized(r.period_to) },
    {
      key: "status", header: "الحالة",
      render: (r) => r.status === "final" ? (
        <span className="inline-flex items-center gap-1 text-red-600">
          <Lock className="w-3 h-3" /> نهائي — الفترة مقفلة
        </span>
      ) : "مسودة",
    },
    { key: "total_sales_vat", header: "ضريبة مخرجات", numeric: true, render: (r) => fmt(Number(r.total_sales_vat)) },
    { key: "total_purchase_vat", header: "ضريبة مدخلات", numeric: true, render: (r) => fmt(Number(r.total_purchase_vat)) },
    { key: "net_vat", header: "الصافي المستحق", numeric: true, render: (r) => fmt(Number(r.net_vat)) },
    {
      key: "actions", header: "",
      render: (r) => r.status === "final" ? (
        isManager ? (
          <button type="button" className="ktra-toolbtn" disabled={busy}
            onClick={() => { setReopenReason(""); setReopenTarget(r); }}>
            <Unlock className="w-3 h-3" /> إعادة فتح
          </button>
        ) : null
      ) : (
        canFinalize ? (
          <button type="button" className="ktra-toolbtn" disabled={busy}
            onClick={() => void finalizeRow(r)}>
            <Lock className="w-3 h-3" /> اعتماد نهائي
          </button>
        ) : null
      ),
    },
  ];

  type VatLine = VatReportLine & { vat_type: string };
  const allLines: VatLine[] = previewData
    ? [
        ...(previewData.output_lines || []).map((l) => ({ ...l, vat_type: "مخرجات" })),
        ...(previewData.input_lines || []).map((l) => ({ ...l, vat_type: "مدخلات" })),
      ]
    : [];

  const previewColumns: ReportColumn<VatLine>[] = [
    { key: "date", header: "التاريخ", render: (r) => formatDateLocalized(r.date) || "—" },
    { key: "vat_type", header: "نوع", render: (r) => r.vat_type },
    { key: "journal_id", header: "رقم", render: (r) => `#${r.journal_id}` },
    { key: "description", header: "البيان", render: (r) => r.description },
    { key: "debit", header: "مدين", numeric: true, render: (r) => fmt(r.debit) },
    { key: "credit", header: "دائن", numeric: true, render: (r) => fmt(r.credit) },
  ];

  const statementsContent = (
    <>
      {listErr && <div className="ktra-banner ktra-banner--err mb-2">{listErr}</div>}
      {reopenTarget && (
        <div className="flex flex-wrap items-end gap-2 mb-2">
          <div className="ktra-field flex-1 min-w-[260px]">
            <label className="ktra-field-label">
              سبب إعادة فتح الكشف {reopenTarget.statement_number} (يُحفظ في سجل التدقيق)
            </label>
            <input
              className="ktra-input"
              autoFocus
              placeholder="مثال: إقرار معدَّل لفاتورة مورّد وردت متأخرة"
              value={reopenReason}
              onChange={(e) => setReopenReason(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void submitReopen(); }}
            />
          </div>
          <button type="button" className="ktra-toolbtn" disabled={busy || !reopenReason.trim()}
            onClick={() => void submitReopen()}>
            <Unlock className="w-4 h-4" /> إعادة الفتح
          </button>
          <button type="button" className="ktra-toolbtn" disabled={busy}
            onClick={() => { setReopenTarget(null); setReopenReason(""); }}>
            إلغاء
          </button>
        </div>
      )}
      <KitDenseTable<VatStatementDto>
        columns={stmtColumns}
        rows={statements}
        getRowKey={(r) => r.id}
        loading={listLoading}
        emptyHint="لا توجد كشوف ضريبية محفوظة بعد"
      />
    </>
  );

  const newStatementContent = (
    <div style={{ padding: "8px 0" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end", marginBottom: "16px" }}>
        <div className="ktra-field">
          <label className="ktra-field-label">من تاريخ</label>
          <input type="date" className="ktra-input" value={previewFrom} onChange={(e) => setPreviewFrom(e.target.value)} />
        </div>
        <div className="ktra-field">
          <label className="ktra-field-label">إلى تاريخ</label>
          <input type="date" className="ktra-input" value={previewTo} onChange={(e) => setPreviewTo(e.target.value)} />
        </div>
        <button type="button" className="ktra-toolbtn" onClick={fetchPreview} style={{ marginTop: "18px" }}>
          <Search className="w-4 h-4" />معاينة
        </button>
      </div>

      {previewErr && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{previewErr}</div>}

      {previewData && (
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "12px" }}>
          <div style={{ flex: "1", minWidth: "140px", padding: "10px", borderRadius: "8px", border: "1px solid #dbeafe", background: "#dbeafe15" }}>
            <div style={{ fontSize: "0.75rem", color: "#2563eb", marginBottom: "4px" }}>ضريبة مدخلات</div>
            <div style={{ fontWeight: "bold" }}>{fmt(previewData.input.balance)}</div>
          </div>
          <div style={{ flex: "1", minWidth: "140px", padding: "10px", borderRadius: "8px", border: "1px solid #fee2e2", background: "#fee2e215" }}>
            <div style={{ fontSize: "0.75rem", color: "#dc2626", marginBottom: "4px" }}>ضريبة مخرجات</div>
            <div style={{ fontWeight: "bold" }}>{fmt(previewData.output.balance_payable)}</div>
          </div>
          <div style={{ flex: "1", minWidth: "140px", padding: "10px", borderRadius: "8px", border: "1px solid #fef9c3", background: "#fef9c315" }}>
            <div style={{ fontSize: "0.75rem", color: "#ca8a04", marginBottom: "4px" }}>صافي مستحق</div>
            <div style={{ fontWeight: "bold" }}>{fmt(previewData.net_payable)}</div>
          </div>
        </div>
      )}

      <KitReportTable<VatLine>
        columns={previewColumns}
        rows={allLines}
        loading={previewLoading}
        emptyHint="اضغط معاينة لتحميل البيانات"
        exportable={false}
        getRowKey={(r, idx) => `${r.journal_id}-${idx}`}
      />

      {previewData && canFinalize && (
        <div className="mt-3 flex justify-end">
          <OfflineGuard
            action="اعتماد كشف الضريبة"
            warningMessage="الاعتماد النهائي يتطلب اتصالاً — يَقفل الترحيل داخل الفترة على الخادم"
          >
            <button
              type="button"
              className="ktra-toolbtn"
              disabled={busy}
              onClick={() => void finalizePreviewPeriod()}
            >
              <Lock className="w-4 h-4" />اعتماد نهائي
            </button>
          </OfflineGuard>
        </div>
      )}
    </div>
  );

  const shellActions: KitToolbarAction[] = [
    {
      key: "new",
      label: "كشف جديد",
      icon: <Plus className="w-4 h-4" />,
      onClick: () => setShowNewForm(true),
    },
    { key: "refresh", label: "تحديث", onClick: () => void loadStatements() },
  ];

  const tabs: KitTab[] = [
    { key: "statements", label: "الكشوف المحفوظة", content: statementsContent },
    ...(showNewForm ? [{ key: "new", label: "كشف جديد", content: newStatementContent }] : []),
  ];

  return (
    <div>
      <KitDocumentShell
        title="كشوف الضريبة المضافة"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          <span className="ktra-status-item">
            {statements.length} كشف محفوظ
          </span>
        }
      >
        <></>
      </KitDocumentShell>
    </div>
  );
};
