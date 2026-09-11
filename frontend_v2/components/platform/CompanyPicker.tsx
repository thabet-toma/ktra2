import React, { useEffect, useMemo, useState } from "react";
import { Loader2, Search } from "lucide-react";

import { getPlatformDashboard, type PlatformDashboardCompanyRow } from "../../services/platformAdminApi";

interface Props {
  value: number | null;
  onChange: (companyId: number, companyName: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * منتقي شركة يعيد استخدام قائمة الشركات الموجودة (`getPlatformDashboard`)
 * بدل نسخ نداء ثانٍ — التذكرة 210-A تطلب صراحةً عدم تكرار سطح المنصة.
 */
export const CompanyPicker: React.FC<Props> = ({ value, onChange, disabled, placeholder }) => {
  const [companies, setCompanies] = useState<PlatformDashboardCompanyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPlatformDashboard()
      .then((data) => { if (!cancelled) setCompanies(data.company_rows); })
      .catch(() => { if (!cancelled) setCompanies([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return companies.slice(0, 20);
    return companies.filter((company) => company.name.toLowerCase().includes(needle)).slice(0, 20);
  }, [companies, query]);

  const selected = companies.find((company) => company.id === value) ?? null;

  return (
    <div className="space-y-1">
      <div className="relative">
        <Search className="absolute right-2 top-2.5 h-3.5 w-3.5 text-slate-400" />
        <input
          className="w-full rounded-lg border border-slate-300 bg-white py-1.5 pl-2 pr-7 text-xs text-slate-900
            focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800
            dark:text-slate-100"
          value={query}
          disabled={disabled || loading}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder ?? (loading ? "جارٍ تحميل الشركات..." : "ابحث باسم الشركة...")}
        />
        {loading && <Loader2 className="absolute left-2 top-2.5 h-3.5 w-3.5 animate-spin text-slate-400" />}
      </div>
      {selected && <p className="text-[11px] text-slate-500">المختارة: {selected.name} (#{selected.id})</p>}
      {query.trim() && (
        <ul className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700">
          {filtered.length === 0 ? (
            <li className="p-2 text-[11px] text-slate-500">لا نتائج مطابقة.</li>
          ) : filtered.map((company) => (
            <li key={company.id}>
              <button
                type="button"
                onClick={() => { onChange(company.id, company.name); setQuery(""); }}
                className="block w-full px-2 py-1.5 text-right text-xs hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                {company.name} (#{company.id})
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
