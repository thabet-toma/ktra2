import React, { useEffect, useState } from "react";
import { Copy, KeyRound, RotateCcw } from "lucide-react";

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
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 space-y-2" dir="rtl">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-amber-800">
          الرمز الخامّ لمفتاح {secret.companyName} — {secret.channelLabel}
        </h3>
        <button type="button" onClick={onDismiss} className="text-[11px] text-amber-700 underline">
          إخفاء
        </button>
      </div>
      <p className="text-[11px] text-amber-700">
        هذا الرمزُ يظهر الآن مرّةً واحدةً ولن يُعرض ثانيةً بعد إخفاء هذه اللافتة أو تحديث الصفحة.
        احفظه في مكانه الآن.
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 min-w-0 truncate rounded-lg bg-white border border-amber-200 px-3 py-2 text-xs font-mono text-slate-800">
          {secret.rawToken}
        </code>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 px-3 py-2 text-xs font-bold text-white bg-amber-600 hover:bg-amber-700 rounded-lg"
        >
          <Copy className="h-3.5 w-3.5" /> {copied ? "تم النسخ" : "نسخ"}
        </button>
      </div>
      {secret.copyFailed && (
        <p className="text-[11px] text-rose-700">
          تعذّر النسخ التلقائي — انسخ النصّ أعلاه يدوياً الآن. لن يُعاد عرضُ هذا الرمز لاحقاً؛ إن
          فاتك نسخُه فأصدِر مفتاحاً بديلاً (تدوير) يُبطل هذا فوراً.
        </p>
      )}
    </div>
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
    <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3" dir="rtl">
      <h3 className="text-xs font-bold text-slate-700">إصدار مفتاح جديد</h3>
      {error && <p className="text-xs text-rose-600">{error}</p>}
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
          className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
        >
          {INTEGRATION_CHANNELS.map((value) => (
            <option key={value} value={value}>
              {INTEGRATION_CHANNEL_FORM_LABELS[value]}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="تسمية اختيارية"
          className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg"
        />
        <button
          type="button"
          onClick={handleIssue}
          disabled={busy || !tenantId}
          className="px-3.5 py-2 text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
        >
          {busy ? "..." : `إصدار${tenantName ? ` لـ${tenantName}` : ""}`}
        </button>
      </div>
    </div>
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
      <div className="py-16 text-center bg-white rounded-xl border border-slate-200" dir="rtl">
        <p className="text-sm font-bold text-slate-700">هذه الشاشة مقصورة على مدير عمليات المنصة.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4" dir="rtl">
      <div className="flex items-center gap-2">
        <KeyRound className="h-4 w-4 text-slate-500" />
        <h2 className="text-sm font-bold text-slate-800">مفاتيح قنوات الإدخال</h2>
      </div>

      {revealed && (
        <CopyOnceBanner
          secret={revealed}
          onDismiss={() => setRevealed(null)}
          onCopyFail={() => setRevealed((prev) => (prev ? { ...prev, copyFailed: true } : prev))}
        />
      )}

      <IssueKeyForm onIssued={setRevealed} onListChanged={load} />

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={load} className="px-3 py-1 bg-rose-100 hover:bg-rose-200 rounded-lg font-bold text-[11px]">
            إعادة المحاولة
          </button>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        {loading ? (
          <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>
        ) : !keys || keys.length === 0 ? (
          <div className="py-10 text-center text-xs text-slate-400">لا مفاتيح مُصدرة بعد</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200">
                  <th className="py-2 pr-2 text-right">الشركة</th>
                  <th className="py-2 px-2 text-right">القناة</th>
                  <th className="py-2 px-2 text-right">التسمية</th>
                  <th className="py-2 px-2 text-right">الحالة</th>
                  <th className="py-2 px-2 text-right">آخر استخدام</th>
                  <th className="py-2 px-2 text-right">آخر تدوير</th>
                  <th className="py-2 px-2 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 align-top">
                    <td className="py-1.5 pr-2 font-medium text-slate-700">{row.company_name}</td>
                    <td className="py-1.5 px-2">{row.channel_display}</td>
                    <td className="py-1.5 px-2">{row.name || "—"}</td>
                    <td className="py-1.5 px-2">
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                          row.status === "active" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                        }`}
                      >
                        {row.status_display}
                      </span>
                      {row.status === "revoked" && row.revocation_reason && (
                        <p className="text-[10px] text-slate-400 mt-0.5">{row.revocation_reason}</p>
                      )}
                    </td>
                    <td className="py-1.5 px-2">{formatDate(row.last_used_at)}</td>
                    <td className="py-1.5 px-2">{formatDate(row.rotated_at)}</td>
                    <td className="py-1.5 px-2 whitespace-nowrap">
                      {row.status === "active" && (
                        <div className="flex flex-col items-end gap-1">
                          <div className="flex gap-1">
                            <button
                              type="button"
                              onClick={() => handleRotate(row)}
                              disabled={busyId === row.id}
                              className="flex items-center gap-1 px-2 py-1 text-[11px] font-bold text-white bg-slate-700 hover:bg-slate-800 rounded-lg disabled:opacity-50"
                            >
                              <RotateCcw className="h-3 w-3" /> تدوير
                            </button>
                            {revokingId === row.id ? (
                              <button
                                type="button"
                                onClick={() => handleRevoke(row)}
                                disabled={busyId === row.id}
                                className="px-2 py-1 text-[11px] font-bold text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
                              >
                                تأكيد الإبطال
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={() => setRevokingId(row.id)}
                                className="px-2 py-1 text-[11px] font-bold text-red-700 bg-red-50 hover:bg-red-100 rounded-lg"
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
                              className="w-40 px-2 py-1 text-[11px] border border-red-200 bg-red-50 rounded-lg"
                            />
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default IntegrationKeysPanel;
