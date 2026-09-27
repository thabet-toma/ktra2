import React, { useCallback, useEffect, useState } from "react";
import { Archive, Database, GitBranch, HardDrive, ShieldAlert, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getPlatformHealth, type PlatformHealth } from "../../../services/platformAdminApi";
import { formatBytes } from "../../../utils/formatBytes";
import { formatDateTimeValue } from "../../../utils/formatDate";
import { formatNumber } from "../../../utils/formatNumber";
import {
  ErrorBox, LoadingRow, Panel, PanelHead, SectionHeader, StatCard, companyPath, errorText,
} from "./consoleShared";

const GOOD = "text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30";
const WARN = "text-amber-600 bg-amber-50 dark:bg-amber-950/30";
const BAD = "text-rose-600 bg-rose-50 dark:bg-rose-950/30";
const NEUTRAL = "text-blue-600 bg-blue-50 dark:bg-blue-950/30";

/** حالة النسخ الاحتياطي بجملة يفهمها المالك: مضبوط؟ مقروء؟ حديث؟ */
function backupSummary(backup: PlatformHealth["backup"]): { value: string; hint: string; tone: string } {
  if (!backup.configured) {
    return { value: "غير مضبوط", hint: "لا مجلّد نسخ احتياطي معرَّف على هذا الخادم (KTRA_BACKUP_DIR)", tone: WARN };
  }
  if (!backup.readable) return { value: "تعذّرت القراءة", hint: "المجلّد المضبوط غير موجود أو غير مقروء", tone: BAD };
  if (!backup.latest_file || !backup.latest_at) return { value: "لا نسخ", hint: "المجلّد فارغ", tone: BAD };
  return {
    value: `قبل ${formatNumber(backup.age_hours ?? 0)} ساعة`,
    hint: `${backup.latest_file} · ${formatBytes(backup.latest_bytes ?? 0)} · ${formatDateTimeValue(backup.latest_at)}`,
    tone: backup.stale ? BAD : GOOD,
  };
}

/**
 * SA-9 — صحة النظام الأساسية: القاعدة (استجابة وحجم وأكبر الجداول)، الهجرات المعلّقة،
 * الكاش، آخر نسخة احتياطية، التخزين، أثقل الشركات، ومحاولات الدخول الفاشلة.
 * لقطةٌ عند الطلب لا مراقبة لحظية — CPU/RAM خارج النطاق (مكانه مراقبة الخادم).
 */
export const HealthSection: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<PlatformHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getPlatformHealth());
    } catch (cause) {
      setError(errorText(cause, "تعذّر فحص صحة النظام"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading && !data) return <LoadingRow label="جارٍ فحص النظام…" />;
  if (!data) return <ErrorBox message={error} onRetry={() => void load()} />;

  const backup = backupSummary(data.backup);
  const pending = data.migrations?.pending ?? [];
  const tables = data.database?.largest_tables ?? [];
  const heaviest = data.heaviest_companies ?? [];

  return (
    <div>
      <SectionHeader
        title="صحة النظام"
        subtitle={`آخر فحص ${formatDateTimeValue(data.checked_at)} — لقطة عند الطلب`}
        loading={loading}
        onRefresh={() => void load()}
      />
      <ErrorBox message={error} />

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          label="قاعدة البيانات" icon={Database}
          value={data.database.ok ? `${formatNumber(data.database.ping_ms ?? 0)} ms` : "لا تستجيب"}
          hint={`${data.database.vendor}${data.database.size_bytes != null ? ` · ${formatBytes(data.database.size_bytes)}` : ""}`}
          tone={data.database.ok ? GOOD : BAD}
        />
        <StatCard
          label="الهجرات" icon={GitBranch}
          value={data.migrations.ok ? "مطبّقة كلها" : `${formatNumber(pending.length)} معلّقة`}
          hint={data.migrations.ok ? "مخطط القاعدة يطابق الكود" : "شغّل migrate قبل أن تنكسر شاشة"}
          tone={data.migrations.ok ? GOOD : BAD}
        />
        <StatCard
          label="الكاش" icon={Zap}
          value={data.cache.ok ? "يعمل" : "لا يحفظ"} hint={data.cache.backend}
          tone={data.cache.ok ? GOOD : WARN}
        />
        <StatCard label="آخر نسخة احتياطية" icon={Archive} value={backup.value} hint={backup.hint} tone={backup.tone} />
        <StatCard
          label="تخزين الملفات" icon={HardDrive}
          value={formatBytes(data.storage.ledger_bytes)}
          hint={`منها غير منسوب لشركة: ${formatBytes(data.storage.unattributed_bytes)}`}
          tone={NEUTRAL}
        />
        <StatCard
          label="دخول فاشل آخر 24 ساعة" icon={ShieldAlert}
          value={formatNumber(data.failed_logins_24h)} hint="التفاصيل في سجل التدقيق"
          tone={data.failed_logins_24h > 20 ? WARN : NEUTRAL}
        />
      </div>

      {pending.length > 0 && (
        <div role="alert" className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          هجرات غير مطبّقة: <span dir="ltr">{pending.join(" · ")}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel label="أثقل الشركات استعمالاً">
          <PanelHead title="أثقل الشركات استعمالاً" hint={`الحركات + المستندات — حُسبت ${formatDateTimeValue(data.usage_computed_at)}`} />
          {heaviest.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm ktra-text-soft">لا شركات بعد</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                <tr>
                  <th className="px-3 py-2 text-right">الشركة</th>
                  <th className="px-3 py-2 text-right">حركات</th>
                  <th className="px-3 py-2 text-right">مستندات</th>
                  <th className="px-3 py-2 text-right">تخزين</th>
                </tr>
              </thead>
              <tbody>
                {heaviest.map((row) => (
                  <tr key={row.tenant_id} className="border-t border-[var(--color-border)]">
                    <td className="px-3 py-2">
                      <button type="button" className="hover:underline" onClick={() => navigate(companyPath(row.tenant_id, "usage"))}>{row.name}</button>
                    </td>
                    <td className="px-3 py-2">{formatNumber(row.movements_total)}</td>
                    <td className="px-3 py-2">{formatNumber(row.documents_total)}</td>
                    <td className="px-3 py-2">{formatBytes(row.storage_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel label="أكبر جداول القاعدة">
          <PanelHead title="أكبر جداول القاعدة" hint="حجم البيانات والفهارس — متاح على MySQL" />
          {tables.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm ktra-text-soft">غير متاح على هذه القاعدة ({data.database.vendor})</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                <tr>
                  <th className="px-3 py-2 text-right">الجدول</th>
                  <th className="px-3 py-2 text-right">صفوف (تقريبي)</th>
                  <th className="px-3 py-2 text-right">الحجم</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((row) => (
                  <tr key={row.name} className="border-t border-[var(--color-border)]">
                    <td className="px-3 py-2" dir="ltr">{row.name}</td>
                    <td className="px-3 py-2">{formatNumber(row.rows)}</td>
                    <td className="px-3 py-2">{formatBytes(row.bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <p className="mt-4 text-xs ktra-text-soft">
        Django {data.app.django} · Python {data.app.python} · {data.app.timezone}
        {data.app.debug && <span className="font-bold text-red-600"> · وضع DEBUG مفعّل</span>}
      </p>
    </div>
  );
};
