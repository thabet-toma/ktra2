import React, { useCallback, useEffect, useState } from "react";
import { LogIn, XCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  endSupportAccess, listPlatformSupportAccess, type SupportAccessGrant,
} from "../../../services/platformAdminApi";
import { useAuth } from "../../../contexts/AuthContext";
import { useToast } from "../../../contexts/ToastContext";
import { formatDateTimeValue } from "../../../utils/formatDate";
import { formatNumber } from "../../../utils/formatNumber";
import { SUPPORT_SCOPE_LABELS, supportDurationLabel } from "../../../utils/supportAccessLabels";
import {
  ErrorBox, LoadingRow, Panel, PanelHead, Pill, SectionHeader, companyPath, enterSupportSession, errorText,
} from "./consoleShared";

const GrantTable: React.FC<{
  grants: SupportAccessGrant[];
  empty: string;
  kind: "pending" | "active";
  onEnd: (grant: SupportAccessGrant) => void;
}> = ({ grants, empty, kind, onEnd }) => {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  if (grants.length === 0) return <p className="px-4 py-6 text-center text-sm ktra-text-soft">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-sm">
        <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
          <tr>
            <th className="px-3 py-2 text-right">الشركة</th>
            <th className="px-3 py-2 text-right">الطالب</th>
            <th className="px-3 py-2 text-right">السبب</th>
            <th className="px-3 py-2 text-right">{kind === "pending" ? "المطلوب" : "النطاق"}</th>
            <th className="px-3 py-2 text-right">{kind === "pending" ? "أُرسل" : "ينتهي"}</th>
            <th className="px-3 py-2" aria-label="إجراء" />
          </tr>
        </thead>
        <tbody>
          {grants.map((grant) => {
            const mine = grant.requested_by_id === Number(currentUser?.id);
            return (
              <tr key={grant.id} className="border-t border-[var(--color-border)]">
                <td className="px-3 py-2">
                  <button type="button" onClick={() => navigate(companyPath(grant.tenant_id, "support"))} className="font-semibold text-[var(--color-text)] hover:underline">
                    {grant.tenant_name}
                  </button>
                </td>
                <td className="px-3 py-2">
                  {grant.requested_by}
                  {grant.is_emergency && <Pill tone="border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">طارئ</Pill>}
                </td>
                <td className="px-3 py-2">{grant.reason}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {kind === "pending"
                    ? `${SUPPORT_SCOPE_LABELS[grant.requested_scope]} · ${supportDurationLabel(grant.requested_hours)}`
                    : SUPPORT_SCOPE_LABELS[grant.scope] || grant.scope}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {formatDateTimeValue(kind === "pending" ? grant.created_at : grant.expires_at)}
                </td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1">
                    {kind === "active" && mine && (
                      <button type="button" onClick={() => enterSupportSession(grant)} className="ktra-btn ktra-btn-primary">
                        <LogIn className="h-4 w-4" /> دخول
                      </button>
                    )}
                    {mine && (
                      <button type="button" onClick={() => onEnd(grant)} className="ktra-iconbtn text-red-600" title={kind === "pending" ? "سحب الطلب" : "إنهاء الإذن"} aria-label={kind === "pending" ? "سحب الطلب" : "إنهاء الإذن"}>
                        <XCircle className="h-4 w-4" />
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
  );
};

/**
 * SA-5 — «طلبات الدخول للدعم» على مستوى المنصة: ما ينتظر الشركات، وما هو ساري الآن.
 * طلب دخول جديد يبدأ من صفحة الشركة (تبويب «الدخول والدعم») — هناك سياقها.
 */
export const SupportRequestsSection: React.FC = () => {
  const toast = useToast();
  const [pending, setPending] = useState<SupportAccessGrant[] | null>(null);
  const [active, setActive] = useState<SupportAccessGrant[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingRows, activeRows] = await Promise.all([
        listPlatformSupportAccess("pending"), listPlatformSupportAccess("active"),
      ]);
      setPending(pendingRows.results);
      setActive(activeRows.results);
    } catch (cause) {
      setError(errorText(cause, "تعذّر تحميل الطلبات"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const end = async (grant: SupportAccessGrant) => {
    try {
      await endSupportAccess(grant.id);
      toast(grant.status === "pending" ? "سُحب الطلب." : "أُنهي الإذن.", "success");
      void load();
    } catch (cause) {
      toast(errorText(cause, "تعذّر الإنهاء."), "error");
    }
  };

  if (loading && !pending) return <LoadingRow />;

  return (
    <div>
      <SectionHeader
        title="طلبات الدخول للدعم"
        subtitle="الدخول إلى بيانات شركة بإذنها فقط — الطلب الجديد من صفحة الشركة، تبويب «الدخول والدعم»"
        loading={loading}
        onRefresh={() => void load()}
      />
      <ErrorBox message={error} onRetry={() => void load()} />
      <Panel label="بانتظار الشركات" className="mb-4">
        <PanelHead title={`بانتظار موافقة الشركات (${formatNumber(pending?.length ?? 0)})`} hint="الطلب المعلّق يسقط وحده بعد 72 ساعة بلا قرار" />
        <GrantTable grants={pending ?? []} kind="pending" empty="لا طلبات معلّقة." onEnd={(grant) => void end(grant)} />
      </Panel>
      <Panel label="أذونات سارية">
        <PanelHead title={`سارية الآن (${formatNumber(active?.length ?? 0)})`} hint="الإذن شخصي — يدخل به من طلبه وحده" />
        <GrantTable grants={active ?? []} kind="active" empty="لا أذونات سارية." onEnd={(grant) => void end(grant)} />
      </Panel>
    </div>
  );
};
