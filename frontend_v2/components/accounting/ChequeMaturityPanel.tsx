import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ExternalLink, RefreshCw } from "lucide-react";
import { reportsApi } from "../../services/reportsApi";
import {
  formatReportCell,
  isNumericKind,
  type ReportResultDto,
  type ReportRow,
} from "../../utils/reportFormat";
import { AseelReportTable, type ReportColumn } from "../aseel";

/**
 * CHQ-4 — تبويب «الاستحقاق والسيولة».
 *
 * المحفظة تقول كم في اليد، ولا تقول **متى**. هذا التبويب يعرض تقرير
 * `cheques-maturity` كما يبنيه الخادم: أسبوعاً بأسبوع، والمتأخر أولاً، وصافٍ
 * تراكمي يُظهر ما يبقى في اليد لو حُصِّل كل وارد وصُرف كل صادر في موعده.
 *
 * لا حساب هنا ولا إعادة تعريف لعمود: الأعمدة وأنواعها وإجمالياتها من التقرير
 * نفسه، فأي تغيير في الخادم يظهر هنا بلا سطر واجهة. وسطر «بلا تاريخ استحقاق»
 * يصل صافيه التراكمي فارغاً عمداً فيظهر «—»: ورقةٌ بلا تاريخ لا موضع لها على
 * خطّ زمني، وصفرٌ هناك كان سيزعم أنها بلا أثر على السيولة.
 */
export const ChequeMaturityPanel: React.FC<{ refreshKey?: number }> = ({ refreshKey = 0 }) => {
  const navigate = useNavigate();
  const [asOf, setAsOf] = useState("");
  const [result, setResult] = useState<ReportResultDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setResult(await reportsApi.run("cheques-maturity", { as_of: asOf }));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر تحميل جدول الاستحقاق");
    } finally {
      setLoading(false);
    }
  }, [asOf]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const columns: ReportColumn<ReportRow>[] = useMemo(
    () => (result?.columns ?? []).map((col) => ({
      key: col.key,
      header: col.header,
      width: col.width || undefined,
      numeric: isNumericKind(col.kind),
      render: (row: ReportRow) => formatReportCell(row[col.key], col.kind),
    })),
    [result],
  );

  const totals = useMemo(() => {
    if (!result || Object.keys(result.totals || {}).length === 0) return undefined;
    const out: Record<string, string> = {};
    for (const col of result.columns) {
      if (result.totals[col.key] !== undefined) {
        out[col.key] = formatReportCell(result.totals[col.key], col.kind);
      }
    }
    return out;
  }, [result]);

  const filterBar = (
    <div className="flex flex-wrap items-end gap-2">
      <div className="aseel-field">
        <label className="aseel-field-label">اعتباراً من</label>
        <input
          type="date"
          className="aseel-input"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
          title="اليوم الذي يُقاس منه التأخير والأسابيع"
        />
      </div>
      <button type="button" className="aseel-toolbtn" onClick={() => void load()}>
        <RefreshCw className="h-3 w-3" /> تحديث
      </button>
      <button
        type="button"
        className="aseel-toolbtn"
        onClick={() => navigate("/reports/cheques-maturity")}
        title="فتح التقرير كاملاً — للطباعة والتصدير"
      >
        <ExternalLink className="h-3 w-3" /> التقرير الكامل
      </button>
    </div>
  );

  if (err) return <div className="aseel-banner aseel-banner--err m-3">{err}</div>;
  // أول تحميل: الأعمدة نفسها لم تصل بعد، وجدولٌ بلا أعمدة لا يعرض شيئاً.
  if (!result) {
    return <div className="p-4 text-sm text-[var(--aseel-ink-soft)]">جاري تحميل جدول الاستحقاق…</div>;
  }

  return (
    <div className="p-3">
      {result.description && (
        <p className="mb-2 text-xs text-[var(--aseel-ink-soft)]">{result.description}</p>
      )}
      <AseelReportTable<ReportRow>
        filterBar={filterBar}
        columns={columns}
        rows={result.rows}
        totals={totals}
        loading={loading}
        getRowKey={(row, idx) => String(row.period_key ?? idx)}
        emptyHint="لا شيكات مفتوحة لها استحقاق."
      />
    </div>
  );
};
