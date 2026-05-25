import React, { useState } from "react";
import { accountingApi } from "../../services/accountingApi";
import { AseelDocumentShell } from "../aseel";
import { AlertCircle, CheckCircle, Loader2 } from "lucide-react";

export const YearEndClosePage: React.FC = () => {
  const today = new Date();
  const currentYear = today.getFullYear();
  const [year, setYear] = useState(currentYear);
  const [retainedAccountId, setRetainedAccountId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    journal_id?: number;
    profit_or_loss?: string;
    rows_count?: number;
    already_closed?: boolean;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const executeClose = async () => {
    if (!retainedAccountId) {
      setErr("الرجاء اختيار حساب الأرباح المحتجزة");
      return;
    }
    setLoading(true);
    setErr(null);
    setResult(null);
    try {
      const res = await accountingApi.yearEndClose({
        year,
        retained_earnings_account_id: retainedAccountId,
      });
      setResult(res);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الإغلاق السنوي");
    } finally {
      setLoading(false);
    }
  };

  const yearOptions: number[] = [];
  for (let y = 2020; y <= currentYear + 1; y++) yearOptions.push(y);

  return (
    <AseelDocumentShell title="الإغلاق السنوي">
      <div style={{ maxWidth: 500, margin: "0 auto", padding: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>السنة المالية</label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #ccc" }}
          >
            {yearOptions.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
            حساب الأرباح المحتجزة (رقم الحساب)
          </label>
          <input
            type="number"
            placeholder="مثال: 3101"
            value={retainedAccountId ?? ""}
            onChange={(e) => setRetainedAccountId(e.target.value ? Number(e.target.value) : null)}
            style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #ccc" }}
          />
        </div>

        <button
          onClick={executeClose}
          disabled={loading}
          style={{
            width: "100%", padding: "10px 16px", borderRadius: 6, border: "none",
            backgroundColor: "#d97706", color: "#fff", fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? <Loader2 className="animate-spin" size={18} /> : "تنفيذ الإغلاق السنوي"}
        </button>

        {err && (
          <div style={{ marginTop: 16, padding: 12, borderRadius: 6, background: "#fee2e2", display: "flex", alignItems: "center", gap: 8 }}>
            <AlertCircle size={18} color="#dc2626" />
            <span>{err}</span>
          </div>
        )}

        {result && (
          <div style={{ marginTop: 16, padding: 12, borderRadius: 6, background: result.already_closed ? "#fef3c7" : "#dcfce7" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <CheckCircle size={18} color={result.already_closed ? "#d97706" : "#16a34a"} />
              <strong>{result.already_closed ? "مغلق مسبقاً" : "تم الإغلاق بنجاح"}</strong>
            </div>
            <div>رقم القيد: {result.journal_id}</div>
            {result.profit_or_loss !== undefined && (
              <div>صافي الربح/الخسارة: {Number(result.profit_or_loss).toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
            )}
            <div>عدد الأسطر: {result.rows_count}</div>
          </div>
        )}
      </div>
    </AseelDocumentShell>
  );
};
