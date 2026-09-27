import React, { useEffect, useState } from "react";
import { LogOut, ShieldAlert } from "lucide-react";

import { endSupportAccess } from "../../services/platformAdminApi";
import { clientLogger } from "../../services/logger";
import { useCompany } from "../../contexts/CompanyContext";
import {
  SUPPORT_ACCESS_DENIED_EVENT, type SupportAccessDeniedDetail,
} from "../../utils/sessionEvents";
import {
  clearSupportSession, readSupportSession, splitMinutes, supportMinutesLeft,
  supportSessionExpired, type SupportSession,
} from "../../utils/supportSession";
import { SUPPORT_SCOPE_LABELS } from "../../utils/supportAccessLabels";
import { formatTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";

const TICK_MS = 30_000;

/**
 * SA-7 — شريط أحمر ثابت ما دام سوبر أدمن داخل شركةٍ بإذن دعم: أيّ شركة، أيّ
 * نطاق، حتى متى، وزرّ خروج. انتهاء الإذن (بالوقت أو بسحب الشركة — رمز
 * `support_access_required`) يحوّله إلى «انتهى الإذن» ولا يبقى إلا الخروج.
 */
export const SupportSessionBanner: React.FC = () => {
  const { currentCompany } = useCompany();
  const [session, setSession] = useState<SupportSession | null>(() => readSupportSession());
  const [now, setNow] = useState(() => Date.now());
  const [revoked, setRevoked] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (!session) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(timer);
  }, [session]);

  useEffect(() => {
    const onDenied = (event: Event) => {
      const detail = (event as CustomEvent<SupportAccessDeniedDetail>).detail;
      if (!detail) return;
      if (detail.code === "support_access_required") setRevoked(true);
      else setNotice(detail.message);
    };
    window.addEventListener(SUPPORT_ACCESS_DENIED_EVENT, onDenied);
    return () => window.removeEventListener(SUPPORT_ACCESS_DENIED_EVENT, onDenied);
  }, []);

  if (!session || currentCompany?.TenantID !== session.tenantId) return null;

  const ended = revoked || supportSessionExpired(session, now);
  const { hours, minutes } = splitMinutes(supportMinutesLeft(session, now));

  const leave = async () => {
    setLeaving(true);
    // الإنهاء في الخادم أفضل جهد: إذنٌ انتهى أو سُحب يرفض الإنهاء، والخروج محلياً يتمّ في كل حال.
    if (!ended) {
      await endSupportAccess(session.grantId).catch((cause) => {
        clientLogger.warn("support_access.end_failed", {
          grantId: session.grantId, error: cause instanceof Error ? cause.message : String(cause),
        });
      });
    }
    clientLogger.info("support_access.session_left", { grantId: session.grantId });
    clearSupportSession();
    setSession(null);
    if (session.returnTenantId) localStorage.setItem("tenantId", String(session.returnTenantId));
    else localStorage.removeItem("tenantId");
    localStorage.removeItem("branchId");
    window.location.assign(`/super-admin/companies/${session.tenantId}`);
  };

  return (
    <div
      role="alert"
      data-testid="support-session-banner"
      className={`flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-sm font-semibold text-white ${ended ? "border-slate-700 bg-slate-700" : "border-red-800 bg-red-700"}`}
    >
      <span className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        {ended ? (
          <>انتهى إذن الدخول إلى «{session.tenantName || currentCompany?.CompanyName}» — لا يُقبل منك طلبٌ آخر فيها. اخرج للعودة إلى لوحة المنصة.</>
        ) : (
          <>
            أنت داخل «{session.tenantName || currentCompany?.CompanyName}» كفريق دعم كترا
            {session.isEmergency ? " (دخول طارئ)" : ""} — {SUPPORT_SCOPE_LABELS[session.scope]} — حتى{" "}
            {formatTimeValue(session.expiresAt)}
            {" "}(باقٍ {hours > 0 ? `${formatNumber(hours)} س ` : ""}{formatNumber(minutes)} د). كل ما تفعله يُسجَّل في سجل الشركة.
          </>
        )}
        {notice && !ended && <span className="rounded bg-white/15 px-2 py-0.5 text-xs">{notice}</span>}
      </span>
      <button
        type="button"
        onClick={() => void leave()}
        disabled={leaving}
        className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-1.5 text-xs font-bold text-red-800 disabled:opacity-60"
      >
        <LogOut className="h-3.5 w-3.5" aria-hidden="true" /> خروج من الشركة
      </button>
    </div>
  );
};
