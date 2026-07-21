import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import type { VatReportResponse, VatReportLine } from "../../types/accounting";
import {
  AseelDocumentShell,
  AseelDenseTable,
  AseelReportTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, DenseColumn, ReportColumn } from "../aseel";
import { Plus, Search, FileText } from "lucide-react";
import OfflineGuard from "../offline/OfflineGuard";

// Placeholder type for future VAT statements (N8-T13 backend not yet done)
interface VatStatement {
  id: number;
  statement_number: string;
  period_from: string;
  period_to: string;
  status: string;
  net_payable: number;
  created_at: string;
}

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
  const [showNewForm, setShowNewForm] = useState(false);

  // Statements list (empty until N8-T13)
  const statements: VatStatement[] = [];

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
      setPreviewErr(e instanceof Error ? e.message : "فشل التحميل");
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewFrom, previewTo]);

  useEffect(() => {
    if (showNewForm) fetchPreview();
  }, [showNewForm, fetchPreview]);

  const fmt = (n: number | undefined | null) => formatMoney(n);

  const stmtColumns: DenseColumn<VatStatement>[] = [
    { key: "statement_number", header: "رقم الكشف" },
    { key: "period_from", header: "من" },
    { key: "period_to", header: "إلى" },
    { key: "status", header: "الحالة" },
    { key: "net_payable", header: "الصافي المستحق", numeric: true, render: (r) => fmt(r.net_payable) },
    { key: "created_at", header: "تاريخ الإنشاء" },
  ];

  type VatLine = VatReportLine & { vat_type: string };
  const allLines: VatLine[] = previewData
    ? [
        ...(previewData.output_lines || []).map((l) => ({ ...l, vat_type: "مخرجات" })),
        ...(previewData.input_lines || []).map((l) => ({ ...l, vat_type: "مدخلات" })),
      ]
    : [];

  const previewColumns: ReportColumn<VatLine>[] = [
    { key: "date", header: "التاريخ", render: (r) => r.date || "—" },
    { key: "vat_type", header: "نوع", render: (r) => r.vat_type },
    { key: "journal_id", header: "رقم", render: (r) => `#${r.journal_id}` },
    { key: "description", header: "البيان", render: (r) => r.description },
    { key: "debit", header: "مدين", numeric: true, render: (r) => fmt(r.debit) },
    { key: "credit", header: "دائن", numeric: true, render: (r) => fmt(r.credit) },
  ];

  const statementsContent = (
    <>
      <div style={{ marginBottom: "8px", fontSize: "0.85rem", color: "var(--aseel-ink-soft)" }}>
        ملاحظة: قائمة الكشوف ستكون متاحة بعد تنفيذ N8-T13 في الخادم.
      </div>
      <AseelDenseTable<VatStatement>
        columns={stmtColumns}
        rows={statements}
        getRowKey={(r) => r.id}
        emptyHint="لا توجد كشوف ضريبية محفوظة بعد"
      />
    </>
  );

  const newStatementContent = (
    <div style={{ padding: "8px 0" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end", marginBottom: "16px" }}>
        <div className="aseel-field">
          <label className="aseel-field-label">من تاريخ</label>
          <input type="date" className="aseel-input" value={previewFrom} onChange={(e) => setPreviewFrom(e.target.value)} />
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">إلى تاريخ</label>
          <input type="date" className="aseel-input" value={previewTo} onChange={(e) => setPreviewTo(e.target.value)} />
        </div>
        <button type="button" className="aseel-toolbtn" onClick={fetchPreview} style={{ marginTop: "18px" }}>
          <Search className="w-4 h-4" />معاينة
        </button>
      </div>

      {previewErr && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{previewErr}</div>}

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

      <AseelReportTable<VatLine>
        columns={previewColumns}
        rows={allLines}
        loading={previewLoading}
        emptyHint="اضغط معاينة لتحميل البيانات"
        exportable={false}
        getRowKey={(r, idx) => `${r.journal_id}-${idx}`}
      />

      {previewData && (
        <div style={{ marginTop: "12px", display: "flex", justifyContent: "flex-end" }}>
          <OfflineGuard
            action="إصدار كشف الضريبة"
            warningMessage="إصدار الكشف يتطلب اتصالاً — يَقفل الفواتير المؤهَّلة على الـserver"
          >
            <button
              type="button"
              className="aseel-toolbtn"
              onClick={() => {
                alert("إنشاء الكشف سيكون متاحاً بعد تنفيذ N8-T13 في الخادم.");
              }}
            >
              <FileText className="w-4 h-4" />إصدار الكشف
            </button>
          </OfflineGuard>
        </div>
      )}
    </div>
  );

  const shellActions: AseelToolbarAction[] = [
    {
      key: "new",
      label: "كشف جديد",
      icon: <Plus className="w-4 h-4" />,
      onClick: () => setShowNewForm(true),
    },
    { key: "refresh", label: "تحديث" },
  ];

  const tabs: AseelTab[] = [
    { key: "statements", label: "الكشوف المحفوظة", content: statementsContent },
    ...(showNewForm ? [{ key: "new", label: "كشف جديد", content: newStatementContent }] : []),
  ];

  return (
    <div>
      <AseelDocumentShell
        title="كشوف الضريبة المضافة"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          <span className="aseel-status-item">
            {statements.length} كشف محفوظ
          </span>
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
