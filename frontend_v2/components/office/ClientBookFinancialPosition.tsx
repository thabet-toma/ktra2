import React, { useCallback, useEffect, useState } from 'react';

import { useCompany } from '../../contexts/CompanyContext';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import { getClientSummary, getClientTrend, type ClientSummary, type TrendPoint } from '../../services/accountantApi';
import { resolveModuleGate } from '../../utils/homeScreen';
import { formatNumber } from '../../utils/formatNumber';
import { TrendBars } from '../accountant/office/OfficeStatements';
import { OfficeCard, OfficeError, OfficeSkeleton, OfficeStat } from '../accountant/office/OfficeUi';

/**
 * ISSUE #87 (مراجعة) — دفترٌ قائمٌ أُنشئ قبل ترخيص `accountant_portal`
 * التلقائي مع قالب `client_book` (`tenants/services.py` — `create_company`)
 * يبقى بلا الوحدة. رسالةٌ عربية صريحة تقول الناقص لا 404 خام ولا شاشة بيضاء.
 */
const ModuleNotLicensedNotice: React.FC = () => (
  <div role="alert" className="mx-auto max-w-xl rounded-2xl border border-amber-300 bg-amber-50 p-8 text-center font-bold text-amber-900">
    وحدة بوابة المحاسب القانوني الخارجي غير مفعّلة لهذه الشركة — الوضع المالي
    يحتاجها. فعّلها مدير المكتب من لوحة المنصة لعرض هذه الشاشة.
  </div>
);

const monthStart = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
};

const monthEnd = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
};

/**
 * ISSUE #87 — شاشة بداية قالب «دفتر عميل»: إيراد · مصروف · ربح · ضريبة صافية
 * للفترة (الشهر الحالي)، مع اتجاه آخر ستة أشهر — سببُ فتح المحاسب لهذا الدفتر
 * أصلاً (#77 القصة ٢٠). تستهلك `ClientSummaryView` و`ClientTrendView` القائمتين
 * في `accountant_portal` كما هما — لا نقطة ثالثة. الضريبة الصافية (`vat_due`)
 * تصل من `client_financial_summary` التي تقرأها من `vat_period_totals` وحدها
 * (issue #79) — نفس المصدر الذي يقرأ منه تقرير ض.ق.م وكشفه، فلا حسبة ثانية هنا.
 */
export const ClientBookFinancialPosition: React.FC = () => {
  const { currentCompany } = useCompany();
  const { modules, loading: permsLoading } = usePermissions();
  const toast = useToast();
  const [range] = useState({ from: monthStart(), to: monthEnd() });
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const tenantId = currentCompany?.TenantID;
  const moduleGate = resolveModuleGate(permsLoading, modules?.accountant_portal);

  const load = useCallback(() => {
    if (!tenantId || moduleGate !== 'ready') return;
    setLoading(true);
    setError('');
    Promise.all([
      getClientSummary(tenantId, range.from, range.to),
      getClientTrend(tenantId, 6),
    ])
      .then(([summaryRes, trendRes]) => {
        setSummary(summaryRes.summary);
        setTrend(trendRes.series);
      })
      .catch(() => {
        setError('تعذّر تحميل الوضع المالي.');
        toast('تعذّر تحميل الوضع المالي.', 'error');
      })
      .finally(() => setLoading(false));
  }, [tenantId, moduleGate, range.from, range.to, toast]);

  useEffect(load, [load]);

  if (moduleGate === 'loading') return <OfficeSkeleton rows={5} />;
  if (moduleGate === 'unlicensed') return <ModuleNotLicensedNotice />;
  if (loading) return <OfficeSkeleton rows={5} />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!summary) return null;

  return (
    <div dir="rtl" className="space-y-6 p-4 sm:p-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <OfficeStat label="الإيرادات" value={formatNumber(summary.revenue)} hint={`${range.from} → ${range.to}`} />
        <OfficeStat label="المصاريف" value={formatNumber(summary.expenses)} hint="كل حسابات المصاريف" />
        <OfficeStat
          label="الربح"
          value={formatNumber(summary.profit)}
          hint="الإيرادات − المصاريف"
          tone={Number(summary.profit) >= 0 ? 'positive' : 'negative'}
        />
        <OfficeStat
          label={Number(summary.vat_due) >= 0 ? 'الضريبة الصافية المستحقة' : 'رصيد ضريبة لصالحك'}
          value={formatNumber(summary.vat_due)}
          hint="مخرجات − مدخلات"
          tone="accent"
        />
      </div>

      <OfficeCard title="اتجاه آخر ستة أشهر" actions={<span className="text-xs text-slate-500">أخضر: إيرادات · وردي: مصاريف</span>}>
        <TrendBars series={trend} />
      </OfficeCard>
    </div>
  );
};

export default ClientBookFinancialPosition;
