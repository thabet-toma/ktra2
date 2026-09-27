import React, { useCallback, useEffect, useState } from "react";
import { Check, Loader2, LifeBuoy, RefreshCw, ShieldOff, X } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  approveSupportAccess, listSupportAccess, rejectSupportAccess, revokeSupportAccess,
  type CompanySupportAccessList, type SupportAccessGrant, type SupportScope,
} from "../../services/supportAccessApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useCompany } from "../../contexts/CompanyContext";
import { readSupportSession } from "../../utils/supportSession";
import {
  SUPPORT_DURATIONS, SUPPORT_SCOPE_LABELS, SUPPORT_STATUS_LABELS, supportDurationLabel,
  supportStatusTone,
} from "../../utils/supportAccessLabels";
import { formatDateTimeValue } from "../../utils/formatDate";

export const SUPPORT_ACCESS_PATH = "/settings/support-access";
const MANAGE_PERM = "admin.members.manage";

const StatusBadge: React.FC<{ status: string }> = ({ status }) => (
  <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-bold ${supportStatusTone(status)}`}>
    {SUPPORT_STATUS_LABELS[status] || status}
  </span>
);

/** طلبٌ معلّق: الشركة تختار المدة والنطاق — لها أن تقصّر وتخفّض، لا أن ترفع. */
const PendingCard: React.FC<{ grant: SupportAccessGrant; onDone: () => void }> = ({ grant, onDone }) => {
  const toast = useToast();
  const [hours, setHours] = useState(grant.requested_hours);
  const [scope, setScope] = useState<SupportScope>(grant.requested_scope);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const decide = async (approve: boolean) => {
    setBusy(true);
    try {
      if (approve) await approveSupportAccess(grant.id, { hours, scope, note });
      else await rejectSupportAccess(grant.id, note);
      toast(approve ? "وافقتَ على دخول فريق كترا." : "رُفض الطلب.", "success");
      onDone();
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّر تسجيل القرار.", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="rounded-lg border border-amber-300 bg-amber-50/60 p-4 dark:border-amber-800 dark:bg-amber-950/20">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-bold text-[var(--color-text)]">{grant.requested_by} من فريق كترا يطلب الدخول</p>
          <p className="mt-1 text-sm text-[var(--color-text)]">السبب: {grant.reason}</p>
          <p className="mt-1 text-xs ktra-text-soft">
            طلب {SUPPORT_SCOPE_LABELS[grant.requested_scope]} لمدة {supportDurationLabel(grant.requested_hours)} · {formatDateTimeValue(grant.created_at)}
          </p>
        </div>
        <StatusBadge status={grant.status} />
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor={`support-hours-${grant.id}`} className="mb-1 block text-xs font-bold ktra-text-soft">المدة</label>
          <select
            id={`support-hours-${grant.id}`}
            className="ktra-input h-9 w-full"
            value={hours}
            onChange={(event) => setHours(Number(event.target.value))}
          >
            {SUPPORT_DURATIONS.filter((row) => row.hours <= grant.requested_hours).map((row) => (
              <option key={row.hours} value={row.hours}>{row.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`support-scope-${grant.id}`} className="mb-1 block text-xs font-bold ktra-text-soft">النطاق</label>
          <select
            id={`support-scope-${grant.id}`}
            className="ktra-input h-9 w-full"
            value={scope}
            onChange={(event) => setScope(event.target.value as SupportScope)}
          >
            <option value="read_only">{SUPPORT_SCOPE_LABELS.read_only}</option>
            {grant.requested_scope === "full" && <option value="full">{SUPPORT_SCOPE_LABELS.full}</option>}
          </select>
        </div>
        <div>
          <label htmlFor={`support-note-${grant.id}`} className="mb-1 block text-xs font-bold ktra-text-soft">ملاحظة (اختيارية)</label>
          <input
            id={`support-note-${grant.id}`}
            className="ktra-input h-9 w-full"
            value={note}
            maxLength={255}
            onChange={(event) => setNote(event.target.value)}
          />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => void decide(true)} className="ktra-btn ktra-btn-primary">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} موافقة
        </button>
        <button type="button" disabled={busy} onClick={() => void decide(false)} className="ktra-btn text-red-600">
          <X className="h-4 w-4" /> رفض
        </button>
      </div>
    </li>
  );
};

/**
 * SA-8 — «دخول فريق كترا» في إعدادات الشركة: المعلّق للقرار، والساري للسحب في أيّ
 * لحظة، والسجلّ. لا يدخل فريق كترا شركةً بلا إذنٍ منها إلا دخولاً طارئاً يظهر هنا.
 */
export const SupportAccessPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can, loading: permsLoading } = usePermissions();
  const [data, setData] = useState<CompanySupportAccessList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await listSupportAccess());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر تحميل أذونات الدخول.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (!permsLoading && !can(MANAGE_PERM)) {
    return (
      <div role="alert" className="m-6 rounded-lg border border-red-200 bg-red-50 p-6 text-center font-bold text-red-800">
        إذن دخول فريق كترا يقرّره مالك الشركة أو مديرها.
      </div>
    );
  }

  const revoke = async (grant: SupportAccessGrant) => {
    const ok = await confirm({
      title: "سحب إذن الدخول",
      message: "يُمنع فريق كترا من شركتك فوراً، مع أول طلبٍ تالٍ له.",
      confirmText: "سحب",
      danger: true,
    });
    if (!ok) return;
    try {
      await revokeSupportAccess(grant.id);
      toast("سُحب الإذن.", "success");
      void load();
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّر سحب الإذن.", "error");
    }
  };

  return (
    <main className="mx-auto max-w-4xl p-4 md:p-6" dir="rtl">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white">
            <LifeBuoy className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-xl font-bold text-[var(--color-text)]">دخول فريق كترا للدعم</h1>
            <p className="text-sm ktra-text-soft">
              فريق كترا لا يرى بيانات شركتك إلا بإذنٍ منك، لمدةٍ محددة، وكل ما يفعله يظهر في سجل النشاط.
            </p>
          </div>
        </div>
        <button type="button" onClick={() => void load()} className="ktra-iconbtn" aria-label="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </header>

      {error && <div role="alert" className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      {loading && !data && <p role="status" className="py-8 text-center ktra-text-soft">جارٍ التحميل…</p>}

      {data && (
        <>
          <section aria-label="طلبات بانتظار قرارك">
            <h2 className="mb-2 font-bold text-[var(--color-text)]">بانتظار قرارك</h2>
            {data.pending.length === 0 ? (
              <p className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-5 text-center text-sm ktra-text-soft">لا طلبات معلّقة.</p>
            ) : (
              <ul className="space-y-3">
                {data.pending.map((grant) => <PendingCard key={grant.id} grant={grant} onDone={() => void load()} />)}
              </ul>
            )}
          </section>

          <section aria-label="أذونات سارية" className="mt-6">
            <h2 className="mb-2 font-bold text-[var(--color-text)]">سارية الآن</h2>
            {data.active.length === 0 ? (
              <p className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-5 text-center text-sm ktra-text-soft">لا أحد من فريق كترا يملك دخولاً إلى شركتك الآن.</p>
            ) : (
              <ul className="space-y-2">
                {data.active.map((grant) => (
                  <li key={grant.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-300 bg-emerald-50/60 p-4 dark:border-emerald-800 dark:bg-emerald-950/20">
                    <div>
                      <p className="font-bold text-[var(--color-text)]">
                        {grant.requested_by}{grant.is_emergency ? " — دخول طارئ" : ""}
                      </p>
                      <p className="text-sm text-[var(--color-text)]">السبب: {grant.reason}</p>
                      <p className="text-xs ktra-text-soft">
                        {SUPPORT_SCOPE_LABELS[grant.scope] || grant.scope} حتى {formatDateTimeValue(grant.expires_at)}
                        {grant.last_used_at ? ` · آخر استعمال ${formatDateTimeValue(grant.last_used_at)}` : " · لم يُستعمل بعد"}
                      </p>
                    </div>
                    <button type="button" onClick={() => void revoke(grant)} className="ktra-btn text-red-600">
                      <ShieldOff className="h-4 w-4" /> سحب الآن
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="السجل" className="mt-6">
            <h2 className="mb-2 font-bold text-[var(--color-text)]">السجل</h2>
            {data.history.length === 0 ? (
              <p className="text-sm ktra-text-soft">لا سجل بعد.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                    <tr>
                      <th className="px-3 py-2 text-right">الطالب</th>
                      <th className="px-3 py-2 text-right">السبب</th>
                      <th className="px-3 py-2 text-right">الحالة</th>
                      <th className="px-3 py-2 text-right">التاريخ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.map((grant) => (
                      <tr key={grant.id} className="border-t border-[var(--color-border)]">
                        <td className="px-3 py-2">{grant.requested_by}{grant.is_emergency ? " (طارئ)" : ""}</td>
                        <td className="px-3 py-2">{grant.reason}</td>
                        <td className="px-3 py-2"><StatusBadge status={grant.status} /></td>
                        <td className="px-3 py-2 whitespace-nowrap">{formatDateTimeValue(grant.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
};

/**
 * تنبيهٌ أعلى التطبيق لمن يملك القرار: طلبٌ معلّق أو إذنٌ ساري الآن. يُقرأ عند
 * تحميل الشركة وعند مغادرة صفحة الأذونات — والبريد يصل مع الطلب أصلاً (`_notify_tenant`).
 */
export const SupportAccessNotice: React.FC = () => {
  const { can, loading: permsLoading } = usePermissions();
  const { currentCompany } = useCompany();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [counts, setCounts] = useState<{ pending: number; active: number } | null>(null);
  const onPage = pathname === SUPPORT_ACCESS_PATH;
  const allowed = !permsLoading && can(MANAGE_PERM) && !readSupportSession();
  const tenantId = currentCompany?.TenantID;

  useEffect(() => {
    if (!allowed || !tenantId || onPage) return undefined;
    let cancelled = false;
    listSupportAccess()
      .then((data) => { if (!cancelled) setCounts({ pending: data.pending.length, active: data.active.length }); })
      .catch(() => { if (!cancelled) setCounts(null); });
    return () => { cancelled = true; };
  }, [allowed, tenantId, onPage]);

  if (!allowed || onPage || !counts || (counts.pending === 0 && counts.active === 0)) return null;
  return (
    <div role="status" className="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-200">
      <span className="flex items-center gap-2">
        <LifeBuoy className="h-4 w-4" aria-hidden="true" />
        {counts.pending > 0
          ? "فريق كترا يطلب إذناً بالدخول إلى شركتك للدعم — القرار لك."
          : "لفريق كترا إذن دخول ساري إلى شركتك الآن — تستطيع سحبه في أيّ لحظة."}
      </span>
      <button type="button" onClick={() => navigate(SUPPORT_ACCESS_PATH)} className="rounded-lg bg-amber-700 px-3 py-1.5 text-xs font-bold text-white">
        {counts.pending > 0 ? "راجع الطلب" : "عرض الإذن"}
      </button>
    </div>
  );
};
