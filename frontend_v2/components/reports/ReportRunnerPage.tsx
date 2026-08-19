/**
 * T-REPORTS — شاشة تشغيل أي تقرير.
 *
 * شاشة واحدة تخدم كل تقارير المنصة: تقرأ مواصفة التقرير من الخادم (فلاتره
 * وأعمدته) وترسمها، فلا تُكتب شاشة لكل تقرير. الفلاتر تُرسَم حسب نوعها:
 * تاريخ، طرف (عميل/مورد)، صنف، مستودع، حساب من الشجرة، قائمة، أو نص.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Download, FileSpreadsheet, Printer, Search } from "lucide-react";

import { reportsApi } from "../../services/reportsApi";
import { accountingApi } from "../../services/accountingApi";
import { apiGetList } from "../../services/restApi";
import { listPickerProducts } from "../../services/inventoryApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { useCompany } from "../../contexts/CompanyContext";
import { useToast } from "../../contexts/ToastContext";
import {
  DATE_PRESETS,
  datePresetRange,
  formatReportCell,
  initialFilterValues,
  isNumericKind,
  reportFileName,
  dateRangeSeed,
  reportToCsv,
  resolveRowLink,
  type DatePresetKey,
  type ReportColumnDto,
  type ReportFilterDto,
  type ReportResultDto,
  type ReportRow,
} from "../../utils/reportFormat";
import { formatDateLocalized } from "../../utils/formatDate";
import { printReport } from "../../utils/printReport";
import type { AccountNodeLike } from "../../utils/accountTree";
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
  // App مركّب على مسار splat (`/*`) بلا `<Route>` فيه `:reportKey` ⇒ كان
  // `useParams()` يُرجع فارغاً فتُطلب `/api/reports//` وتردّ 404 — أي أن كل
  // تقرير في القسم كان يفتح على خطأ. المفتاح يُقرأ من المسار كما في كرت الطرف.
  const location = useLocation();
  const reportKey = useMemo(() => {
    const match = location.pathname.match(/\/reports\/([^/?#]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }, [location.pathname]);
  const navigate = useNavigate();
  const { currentCompany } = useCompany();
  const toast = useToast();

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
    if (!reportKey) return;
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
      // الافتراضي: هذه السنة — تقرير بلا نطاق يجرّ كل تاريخ الشركة؛ إلا أن
      // يعلن التقرير نطاقاً أضيق يفتح عليه (كشف الساعات: هذا الشهر).
      setValues(initialFilterValues(specFilters, dateRangeSeed(specFilters)));
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
    if (!reportKey) {
      setError("لا تقرير في هذا الرابط — افتح تقريراً من فهرس التقارير.");
      setLoading(false);
      return;
    }
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
      // THA-111: فلتر الصندوق يقصّ الشجرة على الصناديق، وبقية فلاتر الحساب
      // تسمح باختيار حساب أب: الفلتر نطاق عرض لا هدف ترحيل.
      return (
        <div style={{ minWidth: "220px" }}>
          <AccountTreeField
            accounts={accounts}
            value={value === "" ? "" : Number(value)}
            onChange={(id) => setValue(filter.key, id == null ? "" : String(id))}
            purpose={filter.kind === "cash_account" ? "cash" : "any"}
            allowParents={filter.kind !== "cash_account"}
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

  /** نطاق جاهز: يملأ الحقلين ويُشغّل فوراً — الضغطة الواحدة هي الفائدة كلها. */
  const applyPreset = useCallback((preset: DatePresetKey) => {
    const range = datePresetRange(preset);
    setValues((prev) => {
      const next = { ...prev, from: range.from, to: range.to };
      void run(next);
      return next;
    });
  }, [run]);

  const hasDateRange = useMemo(
    () => filters.some((f) => f.key === "from") && filters.some((f) => f.key === "to"),
    [filters],
  );

  const activePreset = useMemo(() => {
    if (!hasDateRange) return null;
    return DATE_PRESETS.find((p) => {
      const range = datePresetRange(p.key);
      return range.from === (values.from ?? "") && range.to === (values.to ?? "");
    })?.key ?? null;
  }, [hasDateRange, values.from, values.to]);

  const filterBar = (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {hasDateRange && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          {DATE_PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              onClick={() => applyPreset(preset.key)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                activePreset === preset.key
                  ? "border-[var(--color-accent,#2563eb)] bg-[var(--color-accent,#2563eb)] text-white"
                  : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent,#2563eb)]"
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>
      )}
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
    </div>
  );

  /** التقرير سؤال، وسطره بابٌ إلى مستنده: العمود الأول يصير رابطاً حين يعرف
   *  الخادم مسار المستند. سطر بلا معرّف (رصيد افتتاحي مثلاً) يبقى نصّاً. */
  const columns: ReportColumn<ReportRow>[] = useMemo(
    () => (result?.columns ?? []).map((col: ReportColumnDto, index: number) => ({
      key: col.key,
      header: col.header,
      width: col.width || undefined,
      numeric: isNumericKind(col.kind),
      render: (row: ReportRow) => {
        const text = formatReportCell(row[col.key], col.kind);
        const path = index === 0 ? resolveRowLink(result?.row_link, row) : null;
        if (!path) return text;
        return (
          <button
            type="button"
            className="text-[var(--color-accent,#2563eb)] underline-offset-2 hover:underline"
            onClick={() => navigate(path)}
            title="فتح المستند"
          >
            {text}
          </button>
        );
      },
    })),
    [result, navigate],
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

  const download = (blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportCsv = useCallback(() => {
    if (!result) return;
    download(
      new Blob([reportToCsv(result)], { type: "text/csv;charset=utf-8;" }),
      reportFileName(result),
    );
  }, [result]);

  /** الفترة كما تُقرأ في الترويسة — لا تقرير مطبوع بلا نطاقه. */
  const periodLabel = useMemo(() => {
    const from = values.from ? formatDateLocalized(values.from) : "";
    const to = values.to ? formatDateLocalized(values.to) : "";
    if (from && to) return `الفترة من ${from} إلى ${to}`;
    if (from) return `الفترة من ${from}`;
    if (to) return `الفترة حتى ${to}`;
    return "كل الفترات";
  }, [values.from, values.to]);

  /**
   * تصدير Excel — ملف `.xlsx` بأرقامٍ حقيقية لا CSV منسَّق: المحاسب يفتح
   * الملف ليعيد الحساب فيه، و`SUM` لا تعمل على نصّ. المكتبة تُحمَّل عند أول
   * ضغطة فلا تثقل من لا يصدّر.
   */
  const exportXlsx = useCallback(() => {
    if (!result) return;
    void (async () => {
      try {
        const { reportToXlsxBuffer } = await import("../../utils/reportXlsx");
        const buffer = await reportToXlsxBuffer(result, {
          company: currentCompany?.CompanyName,
          period: periodLabel,
          generatedBy: result.generated_by,
        });
        download(
          new Blob([buffer], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
          reportFileName(result, "xlsx"),
        );
      } catch {
        toast("تعذّر توليد ملف Excel — جرّب تصدير CSV.", "error");
      }
    })();
  }, [result, currentCompany, periodLabel, toast]);

  /**
   * الطباعة بترويسة الشركة والفترة والإجماليات — لا `window.print()` على
   * الصفحة كلها (كانت تطبع القائمة الجانبية والشريط العلوي مع التقرير).
   */
  const print = useCallback(() => {
    if (!result) return;
    const applied = filters
      .filter((f) => f.key !== "from" && f.key !== "to" && (values[f.key] ?? "").trim())
      .map((f) => {
        const raw = values[f.key];
        if (f.kind === "select") {
          return { label: f.label, value: f.options?.find((o) => o.value === raw)?.label ?? raw };
        }
        if (PARTNER_KINDS.has(f.kind)) {
          return { label: f.label, value: partners.find((p) => String(p.id) === raw)?.name ?? raw };
        }
        if (f.kind === "product") {
          const p = products.find((x) => String(x.id) === raw);
          return { label: f.label, value: p ? (p.name_ar || p.name_en || p.name || raw) : raw };
        }
        if (f.kind === "warehouse") {
          return { label: f.label, value: warehouses.find((w) => String(w.id) === raw)?.name ?? raw };
        }
        if (ACCOUNT_KINDS.has(f.kind)) {
          const acc = accounts.find((a) => String(a.id) === raw);
          return { label: f.label, value: acc ? `${acc.code} — ${acc.name}` : raw };
        }
        return { label: f.label, value: raw };
      });

    const opened = printReport<ReportRow>({
      title: result.title,
      subtitle: [currentCompany?.CompanyName, periodLabel].filter(Boolean).join(" · "),
      columns: result.columns.map((col) => ({
        header: col.header,
        numeric: isNumericKind(col.kind),
        value: (row: ReportRow) => formatReportCell(row[col.key], col.kind),
      })),
      rows: result.rows,
      meta: result.generated_by
        ? [...applied, { label: "ولّده", value: result.generated_by }]
        : applied,
      totals: totals
        ? result.columns.map((col, i) => (totals[col.key] ?? (i === 0 ? "الإجمالي" : "")))
        : undefined,
      footer: result.truncated
        ? `عُرض أول ${result.rows.length} سطر من ${result.total_rows} — ضيّق الفترة لطباعة التقرير كاملاً.`
        : undefined,
      emptyHint: "لا توجد بيانات في النطاق المحدد",
    });
    if (!opened) toast("المتصفح منع نافذة الطباعة — اسمح بالنوافذ المنبثقة لهذا الموقع.", "error");
  }, [result, filters, values, partners, products, warehouses, accounts,
      currentCompany, periodLabel, totals, toast]);

  const content = (
    <>
      {error && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{error}</div>}
      {result?.truncated && (
        <div className="aseel-banner aseel-banner--warn" style={{ marginBottom: "8px" }}>
          التقرير أكبر من أن يُعرض كاملاً: ظهر أول {result.rows.length} سطر من{" "}
          {result.total_rows}. الإجماليات أدناه محسوبة على الصفوف كلها — ضيّق الفترة
          لتصفّح الباقي.
        </div>
      )}
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
        getRowKey={(_row, idx) => idx}
      />
    </>
  );

  const actions: AseelToolbarAction[] = [
    { key: "back", label: "كل التقارير", icon: <ArrowRight />, onClick: () => navigate("/reports") },
    { key: "run", label: "تشغيل", icon: <Search />, onClick: () => void run() },
    { key: "export-xlsx", label: "تصدير Excel", icon: <FileSpreadsheet />, onClick: exportXlsx },
    { key: "export", label: "تصدير CSV", icon: <Download />, onClick: exportCsv },
    { key: "print", label: "طباعة / PDF", icon: <Printer />, onClick: print },
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
          <>
            <span className="aseel-status-item">
              {result
                ? (result.truncated
                    ? `${result.rows.length} من ${result.total_rows} سطر`
                    : `${result.rows.length} سطر`)
                : "…"}
            </span>
            <span className="aseel-status-item">{periodLabel}</span>
          </>
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};

export default ReportRunnerPage;
