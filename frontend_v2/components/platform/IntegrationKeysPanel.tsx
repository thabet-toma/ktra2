import React, { useEffect, useState } from "react";
import { Copy, RotateCcw } from "lucide-react";

import {
  INTEGRATION_CHANNELS,
  INTEGRATION_CHANNEL_FORM_LABELS,
  IntegrationChannel,
  IntegrationKeyRow,
  issueIntegrationKey,
  listIntegrationKeys,
  revokeIntegrationKey,
  rotateIntegrationKey,
} from "../../services/platformIntegrationKeysApi";
import { CompanyPicker } from "./CompanyPicker";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatDateTimeValue } from "../../utils/formatDate";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcTable,
  CcThead,
  CcTh,
  CcTr,
  CcTd,
} from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "هذه الشاشة لمدير عمليات المنصة فقط.", "تعذّر إتمام العملية.");

const formatDate = (value: string | null): string => formatDateTimeValue(value) || "—";

/** نتيجةُ إصدارٍ أو تدويرٍ لحظيّة — تُعرض مرّةً واحدةً ثم تختفي؛ لا تُسترجَع أبداً. */
interface RevealedSecret {
  keyId: number;
  companyName: string;
  channelLabel: string;
  rawToken: string;
  copyFailed: boolean;
}

const CopyOnceBanner: React.FC<{ secret: RevealedSecret; onDismiss: () => void; onCopyFail: () => void }> = ({
  secret,
  onDismiss,
  onCopyFail,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(secret.rawToken);
      setCopied(true);
    } catch {
      onCopyFail();
    }
  };

  return (
    <CcCard tone="warning" className="p-4 space-y-2" dir="rtl">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-amber-300">
          الرمز الخامّ لمفتاح {secret.companyName} — {secret.channelLabel}
        </h3>
        <button type="button" onClick={onDismiss} className="text-[11px] text-amber-400 underline hover:text-amber-300">
          إخفاء
        </button>
      </div>
      <p className="text-[11px] text-amber-200/80">
        هذا الرمزُ يظهر الآن مرّةً واحدةً ولن يُعرض ثانيةً بعد إخفاء هذه اللافتة أو تحديث الصفحة.
        احفظه في مكانه الآن.
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 min-w-0 truncate rounded-lg bg-cc-surface border border-amber-500/30 px-3 py-2 text-xs font-mono text-amber-200">
          {secret.rawToken}
        </code>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold text-white bg-amber-600 hover:bg-amber-500 rounded-lg transition shrink-0"
        >
          <Copy className="h-3.5 w-3.5" /> {copied ? "تم النسخ" : "نسخ"}
        </button>
      </div>
      {secret.copyFailed && (
        <p className="text-[11px] text-rose-400">
          تعذّر النسخ التلقائي — انسخ النصّ أعلاه يدوياً الآن. لن يُعاد عرضُ هذا الرمز لاحقاً؛ إن
          فاتك نسخُه فأصدِر مفتاحاً بديلاً (تدوير) يُبطل هذا فوراً.
        </p>
      )}
    </CcCard>
  );
};

const IssueKeyForm: React.FC<{ onIssued: (row: RevealedSecret) => void; onListChanged: () => void }> = ({
  onIssued,
  onListChanged,
}) => {
  const [tenantId, setTenantId] = useState<number | null>(null);
  const [tenantName, setTenantName] = useState("");
  const [channel, setChannel] = useState<IntegrationChannel>("whatsapp");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleIssue = async () => {
    if (!tenantId) {
      setError("اختر شركةً أوّلاً.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const issued = await issueIntegrationKey({ tenant: tenantId, channel, name: name.trim() });
      onIssued({
        keyId: issued.id,
        companyName: issued.company_name,
        channelLabel: issued.channel_display,
        rawToken: issued.raw_token,
        copyFailed: false,
      });
      setName("");
      onListChanged();
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <CcCard className="p-4 sm:p-5 space-y-3" dir="rtl">
      <h3 className="text-xs font-bold text-cc-text">إصدار مفتاح جديد</h3>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-start">
        <CompanyPicker
          value={tenantId}
          onChange={(id, companyName) => {
            setTenantId(id);
            setTenantName(companyName);
          }}
        />
        <select
          value={channel}
          onChange={(event) => setChannel(event.target.value as IntegrationChannel)}
          className="rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          {INTEGRATION_CHANNELS.map((value) => (
            <option key={value} value={value} className="bg-cc-surface-2 text-cc-text">
              {INTEGRATION_CHANNEL_FORM_LABELS[value]}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="تسمية اختيارية"
          className="rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
        <button
          type="button"
          onClick={handleIssue}
          disabled={busy || !tenantId}
          className="rounded-lg bg-sky-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-sky-500 disabled:opacity-50 transition"
        >
          {busy ? "..." : `إصدار${tenantName ? ` لـ${tenantName}` : ""}`}
        </button>
      </div>
    </CcCard>
  );
};

export const IntegrationKeysPanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [keys, setKeys] = useState<IntegrationKeyRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [revealed, setRevealed] = useState<RevealedSecret | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [revokeReasons, setRevokeReasons] = useState<Record<number, string>>({});
  const [revokingId, setRevokingId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listIntegrationKeys();
      setKeys(rows);
      setForbidden(false);
    } catch (cause) {
      if ((cause as { status?: number } | null)?.status === 403) {
        setForbidden(true);
        setKeys(null);
      } else {
        setError(displayError(cause));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleRotate = async (row: IntegrationKeyRow) => {
    const proceed = await confirm({
      title: "تدوير المفتاح",
      message: `سيُصدَر رمزٌ جديدٌ لمفتاح ${row.company_name} — ${row.channel_display}، ويسقط الرمزُ الحاليّ فوراً. متابعة؟`,
      confirmText: "تدوير",
      danger: false,
    });
    if (!proceed) return;
    setBusyId(row.id);
    setError(null);
    try {
      const rotated = await rotateIntegrationKey(row.id);
      setRevealed({
        keyId: rotated.id,
        companyName: rotated.company_name,
        channelLabel: rotated.channel_display,
        rawToken: rotated.raw_token,
        copyFailed: false,
      });
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusyId(null);
    }
  };

  const handleRevoke = async (row: IntegrationKeyRow) => {
    const reason = (revokeReasons[row.id] ?? "").trim();
    if (!reason) {
      toast("سبب الإبطال إلزامي.", "error");
      return;
    }
    const proceed = await confirm({
      title: "إبطال المفتاح",
      message: `سيتوقف مفتاح ${row.company_name} — ${row.channel_display} عن العمل نهائياً. متابعة؟`,
      confirmText: "إبطال",
      danger: true,
    });
    if (!proceed) return;
    setBusyId(row.id);
    try {
      await revokeIntegrationKey(row.id, reason);
      toast("أُبطل المفتاح.", "success");
      setRevokingId(null);
      setRevokeReasons((prev) => ({ ...prev, [row.id]: "" }));
      await load();
    } catch (cause) {
      toast(displayError(cause), "error");
    } finally {
      setBusyId(null);
    }
  };

  if (forbidden) {
    return (
      <CcCard className="py-16 text-center" dir="rtl">
        <p className="text-sm font-bold text-cc-text">هذه الشاشة مقصورة على مدير عمليات المنصة.</p>
      </CcCard>
    );
  }

  return (
    <div className="space-y-6" dir="rtl">
      <CcSectionTitle
        title="مفاتيح قنوات الإدخال"
        badge={keys ? keys.length : undefined}
      />

      {revealed && (
        <CopyOnceBanner
          secret={revealed}
          onDismiss={() => setRevealed(null)}
          onCopyFail={() => setRevealed((prev) => (prev ? { ...prev, copyFailed: true } : prev))}
        />
      )}

      <IssueKeyForm onIssued={setRevealed} onListChanged={load} />

      {error && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={load}
            className="px-3 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 rounded-lg font-bold text-[11px] transition"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      <CcCard className="p-4 sm:p-6">
        {loading ? (
          <div className="py-10 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
        ) : !keys || keys.length === 0 ? (
          <CcEmpty title="لا مفاتيح مُصدرة بعد" />
        ) : (
          <CcTable>
            <CcThead>
              <tr>
                <CcTh>الشركة</CcTh>
                <CcTh>القناة</CcTh>
                <CcTh>التسمية</CcTh>
                <CcTh>الحالة</CcTh>
                <CcTh>آخر استخدام</CcTh>
                <CcTh>آخر تدوير</CcTh>
                <CcTh />
              </tr>
            </CcThead>
            <tbody>
              {keys.map((row) => (
                <CcTr key={row.id}>
                  <CcTd className="font-medium text-cc-text">{row.company_name}</CcTd>
                  <CcTd className="text-cc-text-muted">{row.channel_display}</CcTd>
                  <CcTd className="text-cc-text">{row.name || "—"}</CcTd>
                  <CcTd>
                    <CcPill tone={row.status === "active" ? "success" : "danger"}>
                      {row.status_display}
                    </CcPill>
                    {row.status === "revoked" && row.revocation_reason && (
                      <p className="text-[10px] text-cc-text-muted mt-0.5">{row.revocation_reason}</p>
                    )}
                  </CcTd>
                  <CcTd className="text-cc-text-muted">{formatDate(row.last_used_at)}</CcTd>
                  <CcTd className="text-cc-text-muted">{formatDate(row.rotated_at)}</CcTd>
                  <CcTd className="whitespace-nowrap">
                    {row.status === "active" && (
                      <div className="flex flex-col items-end gap-1">
                        <div className="flex gap-1">
                          <button
                            type="button"
                            onClick={() => handleRotate(row)}
                            disabled={busyId === row.id}
                            className="flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold text-cc-text bg-cc-surface-2 border border-cc-border hover:bg-cc-surface rounded-lg transition disabled:opacity-50"
                          >
                            <RotateCcw className="h-3 w-3" /> تدوير
                          </button>
                          {revokingId === row.id ? (
                            <button
                              type="button"
                              onClick={() => handleRevoke(row)}
                              disabled={busyId === row.id}
                              className="px-2.5 py-1 text-[11px] font-bold text-white bg-rose-600 hover:bg-rose-500 rounded-lg transition disabled:opacity-50"
                            >
                              تأكيد الإبطال
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setRevokingId(row.id)}
                              className="px-2.5 py-1 text-[11px] font-bold text-rose-400 border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 rounded-lg transition"
                            >
                              إبطال
                            </button>
                          )}
                        </div>
                        {revokingId === row.id && (
                          <input
                            type="text"
                            value={revokeReasons[row.id] ?? ""}
                            onChange={(event) =>
                              setRevokeReasons((prev) => ({ ...prev, [row.id]: event.target.value }))
                            }
                            placeholder="سبب الإبطال"
                            className="w-40 rounded-lg border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-cc-text placeholder:text-rose-400/60 focus:outline-none focus:ring-1 focus:ring-rose-500"
                          />
                        )}
                      </div>
                    )}
                  </CcTd>
                </CcTr>
              ))}
            </tbody>
          </CcTable>
        )}
      </CcCard>
    </div>
  );
};

export default IntegrationKeysPanel;
