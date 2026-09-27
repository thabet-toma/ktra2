import React, { useCallback, useEffect, useState } from "react";
import { RotateCcw, Save } from "lucide-react";

import {
  getPlatformDashboard, listPlanPricing, setPlanPricing,
  type PlanPricingRow, type PlatformDashboardData,
} from "../../../services/platformAdminApi";
import { useToast } from "../../../contexts/ToastContext";
import { formatMoney, formatNumber } from "../../../utils/formatNumber";
import { expectedMrr } from "../../../utils/platformConsole";
import { ErrorBox, LoadingRow, Panel, PanelHead, SectionHeader, errorText } from "./consoleShared";

/**
 * SA-5 — «الخطط والأسعار»: سعر كل خطة (افتراض الكود أو تجاوز المنصة) وعدد
 * شركاتها وما تساهم به في الإيراد المتوقَّع. حدود كل خطة تُرى في صفحة الأسعار
 * العامة وتُعدَّل لكل شركة من صفحتها — لا مصفوفة ثانية هنا.
 */
export const PlansSection: React.FC = () => {
  const toast = useToast();
  const [pricing, setPricing] = useState<PlanPricingRow[] | null>(null);
  const [dashboard, setDashboard] = useState<PlatformDashboardData | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const applyPricing = (rows: PlanPricingRow[]) => {
    setPricing(rows);
    setDraft(Object.fromEntries(rows.map((row) => [row.plan_key, String(Number(row.effective_price))])));
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [priceResult, dashResult] = await Promise.allSettled([listPlanPricing(), getPlatformDashboard()]);
    if (priceResult.status === "fulfilled") applyPricing(priceResult.value.results);
    else setError(errorText(priceResult.reason, "تعذّر تحميل الأسعار"));
    if (dashResult.status === "fulfilled") setDashboard(dashResult.value);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const save = async (row: PlanPricingRow, value: string) => {
    if (value.trim() === "" || Number.isNaN(Number(value)) || Number(value) < 0) {
      toast("السعر رقمٌ صفرٌ أو أكبر.", "error");
      return;
    }
    setBusy(row.plan_key);
    try {
      const result = await setPlanPricing(row.plan_key, value.trim(), note[row.plan_key] ?? "");
      applyPricing(result.results);
      setNote((current) => ({ ...current, [row.plan_key]: "" }));
      toast(`سعر «${row.label}» محفوظ.`, "success");
    } catch (cause) {
      toast(errorText(cause, "تعذّر حفظ السعر."), "error");
    } finally {
      setBusy(null);
    }
  };

  if (loading && !pricing) return <LoadingRow />;
  if (!pricing) return <ErrorBox message={error} onRetry={() => void load()} />;

  const rows = dashboard?.company_rows ?? [];
  const countFor = (plan: string, status?: string) =>
    rows.filter((row) => row.plan === plan && (!status || row.status === status)).length;
  const mrr = expectedMrr(rows, pricing);

  return (
    <div>
      <SectionHeader
        title="الخطط والأسعار"
        subtitle="السعر الشهري لكل خطة — يظهر فوراً في صفحة الأسعار العامة، وكل تغيير في سجل التدقيق"
        loading={loading}
        onRefresh={() => void load()}
      />
      <Panel label="أسعار الخطط">
        <PanelHead
          title="السعر الشهري"
          hint={`الإيراد الشهري المتوقَّع الآن: ${formatMoney(mrr)} ₪ (الشركات الفعّالة × سعر خطتها)`}
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
              <tr>
                <th className="px-3 py-2 text-right">الخطة</th>
                <th className="px-3 py-2 text-center">شركات فعّالة / الكل</th>
                <th className="px-3 py-2 text-center">مساهمتها المتوقَّعة</th>
                <th className="px-3 py-2 text-right">السعر (₪)</th>
                <th className="px-3 py-2 text-right">سبب التغيير</th>
                <th className="px-3 py-2" aria-label="إجراء" />
              </tr>
            </thead>
            <tbody>
              {pricing.map((row) => {
                const active = countFor(row.plan_key, "Active");
                const value = draft[row.plan_key] ?? "";
                const dirty = Number(value) !== Number(row.effective_price);
                return (
                  <tr key={row.plan_key} className="border-t border-[var(--color-border)]">
                    <td className="px-3 py-2">
                      <div className="font-semibold text-[var(--color-text)]">{row.label || row.plan_key}</div>
                      <div className="text-[11px] ktra-text-soft">
                        {row.has_override ? `مخصَّص — الافتراضي ${formatMoney(row.default_price)} ₪` : "السعر الافتراضي"}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-center">{formatNumber(active)} / {formatNumber(countFor(row.plan_key))}</td>
                    <td className="px-3 py-2 text-center">{formatMoney(active * Number(row.effective_price))} ₪</td>
                    <td className="px-3 py-2">
                      <input
                        aria-label={`سعر ${row.label}`}
                        className="ktra-input h-9 w-28"
                        inputMode="decimal"
                        value={value}
                        onChange={(event) => setDraft((current) => ({ ...current, [row.plan_key]: event.target.value }))}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        aria-label={`سبب تغيير سعر ${row.label}`}
                        className="ktra-input h-9 w-full"
                        maxLength={120}
                        value={note[row.plan_key] ?? ""}
                        onChange={(event) => setNote((current) => ({ ...current, [row.plan_key]: event.target.value }))}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        <button type="button" disabled={!dirty || busy === row.plan_key} onClick={() => void save(row, value)} className="ktra-btn ktra-btn-primary">
                          <Save className="h-4 w-4" /> حفظ
                        </button>
                        {row.has_override && (
                          <button type="button" disabled={busy === row.plan_key} onClick={() => void save(row, String(Number(row.default_price)))} className="ktra-iconbtn" title="استعادة السعر الافتراضي" aria-label={`استعادة سعر ${row.label} الافتراضي`}>
                            <RotateCcw className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="border-t border-[var(--color-border)] px-4 py-3 text-xs ktra-text-soft">
          حدود كل خطة (المستخدمون، الفروع، الفواتير، مساحة التخزين…) افتراضاتٌ في الكود تظهر في صفحة الأسعار العامة،
          وتُخصَّص لشركة بعينها من تبويب «الحدود والتخزين» في صفحتها.
        </p>
      </Panel>
    </div>
  );
};
