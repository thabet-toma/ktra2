/**
 * T-REPORTS — شاشة تشغيل أي تقرير.
 *
 * شاشة واحدة تخدم كل تقارير المنصة: تقرأ مواصفة التقرير من الخادم (فلاتره
 * وأعمدته) وترسمها، فلا تُكتب شاشة لكل تقرير. الفلاتر تُرسَم حسب نوعها:
 * تاريخ، طرف (عميل/مورد)، صنف، مستودع، حساب من الشجرة، قائمة، أو نص.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowRight, Download, Printer, Search } from "lucide-react";

import { reportsApi } from "../../services/reportsApi";
import { accountingApi } from "../../services/accountingApi";
import { apiGetList } from "../../services/restApi";
import { listPickerProducts } from "../../services/inventoryApi";
import { resolveTenantId } from "../../utils/tenantContext";
import {
  formatReportCell,
  initialFilterValues,
  isNumericKind,
  reportFileName,
  reportToCsv,
  type ReportColumnDto,
  type ReportFilterDto,
  type ReportResultDto,
  type ReportRow,
} from "../../utils/reportFormat";
import { isCashAccount, type AccountNodeLike } from "../../utils/accountTree";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import { AseelDocumentShell, AseelReportTable } from "../aseel";
import type { AseelTab, AseelToolbarAction, ReportColumn } from "../aseel";

type PartnerRow = { id: number; name: string; partner_type?: string };
type ProductRow = { id: number; sku?: string; name_ar?: string; name_en?: string; name?: string };
type WarehouseRow = { id: number; name?: string };

const PARTNER_KINDS = new Set(["partner", "customer", "supplier"]);
const ACCOUNT_KINDS = new Set(["account", "cash_account"]);

/** أي بيانات مساعدة يحتاجها هذا التقرير؟ لا نُحمّل ما لا تطلبه فلاتره. */
const lookupsNeeded = (filters: ReportFilterDto[]) => ({
  partners: filters.some((f) => PARTNER_KINDS.has(f.kind)),
  products: filters.some((f) => f.kind === "product"),
  warehouses: filters.some((f) => f.kind === "warehouse"),
  accounts: filters.some((f) => ACCOUNT_KINDS.has(f.kind)),
});

export const ReportRunnerPage: React.FC = () => {
  const { reportKey = "" } = useParams();
  const navigate = useNavigate();

  const [result, setResult] = useState<ReportResultDto | null>(null);
  const [filters, setFilters] = useState<ReportFilterDto[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  /** وصلت مواصفة التقرير؟ التشغيل الأول ينتظرها وإلا ضاع نطاق التاريخ الافتراضي. */
  const [specLoaded, setSpecLoaded] = useState(false);
  const [ranOnce, setRanOnce] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [partners, setPartners] = useState<PartnerRow[]>([]);
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([]);
  const [accounts, setAccounts] = useState<AccountNodeLike[]>([]);

  /** المواصفة من الفهرس — نحتاج الفلاتر قبل أول تشغيل. */
  useEffect(() => {
    let alive = true;
    setSpecLoaded(false);
    setRanOnce(false);
    void (async () => {
      let specFilters: ReportFilterDto[] = [];
      try {
        const categories = await reportsApi.catalog();
        specFilters = categories
          .flatMap((c) => c.reports)
          .find((r) => r.key === reportKey)?.filters ?? [];
      } catch {
        specFilters = [];
      }
      if (!alive) return;
      setFilters(specFilters);
      // الافتراضي: هذه السنة — تقرير بلا نطاق يجرّ كل تاريخ الشركة.
      const year = new Date().getFullYear();
      setValues(initialFilterValues(specFilters, {
        from: specFilters.some((f) => f.key === "from") ? `${year}-01-01` : "",
        to: specFilters.some((f) => f.key === "to")
          ? new Date().toISOString().slice(0, 10) : "",
      }));
      setSpecLoaded(true);
    })();
    return () => { alive = false; };
  }, [reportKey]);

  /** قوائم الفلاتر المساعدة. */
  useEffect(() => {
    if (filters.length === 0) return;
    const needed = lookupsNeeded(filters);
    let alive = true;
    void (async () => {
      const tenantId = resolveTenantId();
      const [p, pr, wh, acc] = await Promise.allSettled([
        needed.partners ? (accountingApi.getPartners() as Promise<PartnerRow[]>) : Promise.resolve([]),
        needed.products ? listPickerProducts<ProductRow>(tenantId) : Promise.resolve([]),
        needed.warehouses ? apiGetList<WarehouseRow>("inventory/warehouses/", { tenantId }) : Promise.resolve([]),
        needed.accounts ? (accountingApi.getAccounts() as Promise<AccountNodeLike[]>) : Promise.resolve([]),
      ]);
      if (!alive) return;
      if (p.status === "fulfilled") setPartners(p.value || []);
      if (pr.status === "fulfilled") setProducts(pr.value || []);
      if (wh.status === "fulfilled") setWarehouses(wh.value || []);
      if (acc.status === "fulfilled") setAccounts(acc.value || []);
    })();
    return () => { alive = false; };
  }, [filters]);

  const run = useCallback(async (overrides?: Record<string, string>) => {
    setLoading(true);
    setError(null);
    try {
      setResult(await reportsApi.run(reportKey, overrides ?? values));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "تعذّر توليد التقرير");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [reportKey, values]);

  // أول تشغيل بعد وصول المواصفة وحدها — لا قبلها، وإلا شُغِّل التقرير بلا نطاق.
  useEffect(() => {
    if (!specLoaded || ranOnce) return;
    setRanOnce(true);
    void run(values);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specLoaded, ranOnce]);

  const setValue = (key: string, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const partnersFor = useCallback((kind: string) => {
    if (kind === "customer") {
      return partners.filter((p) => String(p.partner_type || "").toLowerCase() === "customer");
    }
    if (kind === "supplier") {
      return partners.filter((p) => String(p.partner_type || "").toLowerCase() !== "customer");
    }
    return partners;
  }, [partners]);

  const renderFilter = (filter: ReportFilterDto) => {
    const value = values[filter.key] ?? "";
    if (filter.kind === "date") {
      return (
        <input type="date" className="aseel-input" value={value}
          onChange={(e) => setValue(filter.key, e.target.value)} />
      );
    }
    if (PARTNER_KINDS.has(filter.kind)) {
      return (
        <select className="aseel-input" style={{ minWidth: "170px" }} value={value}
          onChange={(e) => setValue(filter.key, e.target.value)}>
          <option value="">الكل</option>
          {partnersFor(filter.kind).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      );
    }
    if (filter.kind === "product") {
      return (
        <select className="aseel-input" style={{ minWidth: "200px" }} value={value}
          onChange={(e) => setValue(filter.key, e.target.value)}>
          <option value="">الكل</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {[p.sku, p.name_ar || p.name_en || p.name].filter(Boolean).join(" — ")}
            </option>
          ))}
        </select>
      );
    }
    if (filter.kind === "warehouse") {
      return (
        <select className="aseel-input" style={{ minWidth: "150px" }} value={value}
          onChange={(e) => setValue(filter.key, e.target.value)}>
          <option value="">الكل</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
      );
    }
    if (ACCOUNT_KINDS.has(filter.kind)) {
      // T-DEFACC: اختيار الحساب من الشجرة هنا أيضاً — لا قائمة مسطّحة.
      return (
        <div style={{ minWidth: "220px" }}>
          <AccountTreeField
            accounts={accounts}
            value={value === "" ? "" : Number(value)}
            onChange={(id) => setValue(filter.key, id == null ? "" : String(id))}
            isSelectable={filter.kind === "cash_account" ? isCashAccount : undefined}
            placeholder="الكل"
            title={filter.label}
          />
        </div>
      );
    }
    if (filter.kind === "select") {
      return (
        <select className="aseel-input" style={{ minWidth: "150px" }} value={value}
          onChange={(e) => setValue(filter.key, e.target.value)}>
          {(filter.options ?? []).map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      );
    }
    return (
      <input type="text" className="aseel-input" value={value}
        onChange={(e) => setValue(filter.key, e.target.value)} />
    );
  };

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      {filters.map((filter) => (
        <div className="aseel-field" key={filter.key}>
          <label className="aseel-field-label">{filter.label}</label>
          {renderFilter(filter)}
        </div>
      ))}
      <button type="button" className="aseel-toolbtn" style={{ marginTop: "18px" }}
        onClick={() => void run()}>
        <Search className="w-4 h-4" /> تشغيل
      </button>
    </div>
  );

  const columns: ReportColumn<ReportRow>[] = useMemo(
    () => (result?.columns ?? []).map((col: ReportColumnDto) => ({
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

  const exportCsv = useCallback(() => {
    if (!result) return;
    const blob = new Blob([reportToCsv(result)], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = reportFileName(result);
    link.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const content = (
    <>
      {error && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{error}</div>}
      {result?.description && (
        <p className="mb-2 text-xs text-[var(--color-text-muted)]">{result.description}</p>
      )}
      <AseelReportTable<ReportRow>
        filterBar={filterBar}
        columns={columns}
        rows={result?.rows ?? []}
        totals={totals}
        exportable
        onExport={exportCsv}
        loading={loading}
        getRowKey={(row, idx) => String(row.id ?? idx)}
      />
    </>
  );

  const actions: AseelToolbarAction[] = [
    { key: "back", label: "كل التقارير", icon: <ArrowRight />, onClick: () => navigate("/reports") },
    { key: "run", label: "تشغيل", icon: <Search />, onClick: () => void run() },
    { key: "export", label: "تصدير CSV", icon: <Download />, onClick: exportCsv },
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => window.print() },
  ];

  const tabs: AseelTab[] = [
    { key: "result", label: result?.title || "التقرير", content },
  ];

  return (
    <div>
      <AseelDocumentShell
        title={result?.title || "تقرير"}
        actions={actions}
        header={<></>}
        tabs={tabs}
        status={
          <span className="aseel-status-item">
            {result ? `${result.rows.length} سطر` : "…"}
          </span>
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};

export default ReportRunnerPage;
