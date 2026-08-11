import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  X, Pencil, Save, Trash2, Loader2, ShieldAlert, ImageOff, Check,
} from "lucide-react";
import {
  DEVICE_STATUSES,
  deleteDevice,
  getDevice,
  listDeviceAudit,
  updateDevice,
  type DeviceAuditRow,
  type DeviceStatus,
  type SensitiveDeviceRow,
} from "../../services/devicesApi";
import { imeiDigits, imeiState, isValidPhone, normalizePhone } from "../../utils/imei";
import { formatDateTimeValue } from "../../utils/formatDate";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { statusPillClass } from "./deviceStatus";

/**
 * THA-45 M2 — «معاينة» سجلٍ واحد: السجل كاملاً، وأثره في التدقيق، والتحرير
 * وتغيير الحالة والحذف من داخل الشاشة نفسها.
 *
 * فتح المعاينة **حدثٌ يُسجَّل** — الخادم يكتب سطر `view` عند كل `GET` للسجل،
 * وهو أحد شروط الوثيقة (يُتتبَّع الاستعلام لا التعديل وحده).
 *
 * الحذف ناعم دائماً: الصف يبقى ويُسترجَع. لكن **الاسترجاع ليس هنا** — الخادم
 * يُخفي المحذوف عن `GET {id}/` (404) فلا تُفتح هذه النافذة على سجلٍ محذوف
 * أصلاً؛ زرّ الاسترجاع يعيش على صفّ الجدول نفسه حيث تعمل نقطة `restore`.
 */

interface Props {
  deviceId: number;
  canEdit: boolean;
  canDelete: boolean;
  canAudit: boolean;
  modelNames: string[];
  onClose: () => void;
  /** يُنادى بعد كل تغيير فعلي كي تُعيد الشاشة تحميل الجدول. */
  onChanged: () => void;
}

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const fieldClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

/** سطر التدقيق بلغة بشرية — التفاصيل JSON خام لا يُعرض كما هو. */
const auditDetailText = (row: DeviceAuditRow): string => {
  const details = row.details || {};
  if (row.action === "update") {
    const changes = (details.changes as { label?: string; old?: unknown; new?: unknown }[]) || [];
    return changes
      .map((c) => `${c.label ?? ""}: ${String(c.old ?? "—")} ← ${String(c.new ?? "—")}`)
      .join(" · ");
  }
  if (row.action === "status") {
    const label = (key: unknown) =>
      DEVICE_STATUSES.find((s) => s.key === key)?.label ?? String(key ?? "—");
    return `${label(details.from)} ← ${label(details.to)}`;
  }
  if (row.action === "search") {
    return `«${String(details.term ?? "")}» — ${String(details.results ?? 0)} نتيجة`;
  }
  if (row.action === "register" || row.action === "delete") {
    return details.imei ? `IMEI ${String(details.imei)}` : "";
  }
  return "";
};

export const DeviceDetailModal: React.FC<Props> = ({
  deviceId, canEdit, canDelete, canAudit, modelNames, onClose, onChanged,
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [device, setDevice] = useState<SensitiveDeviceRow | null>(null);
  const [audit, setAudit] = useState<DeviceAuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SensitiveDeviceRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      // `GET` واحد للسجل — وهو نفسه ما يكتب سطر «عرض» في التدقيق.
      const row = await getDevice(deviceId);
      setDevice(row);
      setDraft(row);
      if (canAudit) setAudit(await listDeviceAudit(deviceId));
    } catch (e) {
      setErr(messageOf(e, "تعذّر فتح السجل"));
    } finally {
      setLoading(false);
    }
  }, [deviceId, canAudit]);

  useEffect(() => { void load(); }, [load]);

  const draftErrors = useMemo(() => {
    if (!draft) return [];
    const problems: string[] = [];
    if (!draft.customer_name.trim()) problems.push("اسم العميل مطلوب");
    if (!isValidPhone(draft.customer_phone)) problems.push("رقم الهاتف غير صالح");
    if (!draft.model_name.trim()) problems.push("موديل الجهاز مطلوب");
    if (!draft.serial_number.trim()) problems.push("الرقم التسلسلي مطلوب");
    if (imeiState(draft.imei) !== "valid") problems.push("رقم IMEI غير صالح (15 خانة تجتاز Luhn)");
    return problems;
  }, [draft]);

  const saveEdits = async () => {
    if (!draft || draftErrors.length > 0) return;
    setBusy(true);
    setErr(null);
    try {
      const saved = await updateDevice(draft.id, {
        customer_name: draft.customer_name.trim(),
        customer_phone: normalizePhone(draft.customer_phone),
        model_name: draft.model_name.trim(),
        serial_number: draft.serial_number.trim(),
        imei: imeiDigits(draft.imei),
        technical_notes: draft.technical_notes,
        status: draft.status,
      });
      setDevice(saved);
      setDraft(saved);
      setEditing(false);
      if (canAudit) setAudit(await listDeviceAudit(saved.id));
      toast("تم حفظ التعديل", "success");
      onChanged();
    } catch (e) {
      setErr(messageOf(e, "تعذّر حفظ التعديل"));
    } finally {
      setBusy(false);
    }
  };

  const changeStatus = async (status: DeviceStatus) => {
    if (!device || status === device.status) return;
    setBusy(true);
    setErr(null);
    try {
      const saved = await updateDevice(device.id, { status });
      setDevice(saved);
      setDraft(saved);
      if (canAudit) setAudit(await listDeviceAudit(saved.id));
      toast(`الحالة الآن: ${saved.status_label}`, "success");
      onChanged();
    } catch (e) {
      setErr(messageOf(e, "تعذّر تغيير الحالة"));
    } finally {
      setBusy(false);
    }
  };

  const removeDevice = async () => {
    if (!device) return;
    const ok = await confirm({
      title: "حذف سجل الجهاز",
      message: `سيُخفى سجل «${device.model_name}» (IMEI ${device.imei}) من القائمة، ويبقى محفوظاً في قاعدة البيانات مع أثره الكامل ويمكن استرجاعه. الحذف النهائي غير متاح في هذه الوحدة.`,
      confirmText: "حذف السجل",
      cancelText: "تراجع",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await deleteDevice(device.id);
      toast("تم حذف السجل — يمكن استرجاعه من «إظهار المحذوفة»", "success");
      onChanged();
      onClose();
    } catch (e) {
      setErr(messageOf(e, "تعذّر حذف السجل"));
      setBusy(false);
    }
  };

  const readOnlyRow = (label: string, value: React.ReactNode) => (
    <div className="min-w-0">
      <div className="text-[11px] text-[var(--color-text-muted)]">{label}</div>
      <div className="truncate font-semibold text-[var(--color-text)]">{value || "—"}</div>
    </div>
  );

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label="معاينة سجل الجهاز"
      className="fixed inset-0 z-[70] flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
    >
      <div className="w-full max-w-3xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
          <div className="flex min-w-0 items-center gap-2">
            <ShieldAlert className="h-5 w-5 shrink-0 text-[var(--color-primary)]" />
            <span className="truncate font-bold text-[var(--color-text)]">
              {device ? `${device.model_name} — ${device.imei}` : "معاينة السجل"}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-3 md:p-4">
          {err && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-2 py-10 text-[var(--color-text-muted)]">
              <Loader2 className="h-5 w-5 animate-spin" /> جارٍ التحميل…
            </div>
          )}

          {!loading && device && draft && (
            <>
              <div className="flex flex-col gap-4 md:flex-row">
                <div className="flex h-40 w-full shrink-0 items-center justify-center overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] md:w-40">
                  {device.photo_url ? (
                    <img src={device.photo_url} alt="صورة الجهاز" className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex flex-col items-center gap-1 text-[var(--color-text-muted)]">
                      <ImageOff className="h-6 w-6" />
                      <span className="text-[11px]">بلا صورة</span>
                    </div>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  {editing ? (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <label className="block">
                        <span className="text-[11px] text-[var(--color-text-muted)]">اسم العميل</span>
                        <input
                          className={fieldClass}
                          value={draft.customer_name}
                          onChange={(e) => setDraft({ ...draft, customer_name: e.target.value })}
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-[var(--color-text-muted)]">رقم هاتف العميل</span>
                        <input
                          className={fieldClass}
                          inputMode="tel"
                          value={draft.customer_phone}
                          onChange={(e) => setDraft({ ...draft, customer_phone: e.target.value })}
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-[var(--color-text-muted)]">موديل الجهاز</span>
                        <input
                          className={fieldClass}
                          list="device-model-suggestions-detail"
                          value={draft.model_name}
                          onChange={(e) => setDraft({ ...draft, model_name: e.target.value })}
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-[var(--color-text-muted)]">الرقم التسلسلي (SN)</span>
                        <input
                          className={fieldClass}
                          value={draft.serial_number}
                          onChange={(e) => setDraft({ ...draft, serial_number: e.target.value })}
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-[var(--color-text-muted)]">رقم الـ IMEI</span>
                        <input
                          className={fieldClass}
                          inputMode="numeric"
                          value={draft.imei}
                          onChange={(e) => setDraft({ ...draft, imei: imeiDigits(e.target.value) })}
                        />
                      </label>
                      <label className="block">
                        <span className="text-[11px] text-[var(--color-text-muted)]">حالة التتبع</span>
                        <select
                          className={fieldClass}
                          value={draft.status}
                          onChange={(e) => setDraft({ ...draft, status: e.target.value as DeviceStatus })}
                        >
                          {DEVICE_STATUSES.map((s) => (
                            <option key={s.key} value={s.key}>{s.label}</option>
                          ))}
                        </select>
                      </label>
                      <label className="block sm:col-span-2">
                        <span className="text-[11px] text-[var(--color-text-muted)]">ملاحظات فنية</span>
                        <textarea
                          rows={2}
                          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                          value={draft.technical_notes}
                          onChange={(e) => setDraft({ ...draft, technical_notes: e.target.value })}
                        />
                      </label>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {readOnlyRow("اسم العميل", device.customer_name)}
                      {readOnlyRow("رقم هاتف العميل", device.customer_phone)}
                      {readOnlyRow("موديل الجهاز", device.model_name)}
                      {readOnlyRow("الرقم التسلسلي (SN)", device.serial_number)}
                      {readOnlyRow("رقم الـ IMEI", device.imei)}
                      {readOnlyRow("حالة التتبع", (
                        <span className={statusPillClass(device.status)}>{device.status_label}</span>
                      ))}
                      {readOnlyRow("تاريخ ووقت التسجيل", formatDateTimeValue(device.created_at))}
                      {readOnlyRow("المستخدم المسجل", device.created_by_name)}
                      <div className="sm:col-span-2">
                        {readOnlyRow("ملاحظات فنية", device.technical_notes)}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {editing && draftErrors.length > 0 && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
                  {draftErrors.join(" · ")}
                </div>
              )}

              {/* الإجراءات — تغيير الحالة أكثرها استعمالاً فيبقى بنقرة واحدة */}
              <div className="flex flex-wrap items-center gap-2 border-t border-[var(--color-border)] pt-3">
                {canEdit && !editing && DEVICE_STATUSES.map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    disabled={busy || s.key === device.status}
                    onClick={() => void changeStatus(s.key)}
                    className={`rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50 ${
                      s.key === device.status ? "bg-[var(--color-surface-2)]" : ""
                    }`}
                    title={`نقل الحالة إلى «${s.label}»`}
                  >
                    {s.key === device.status && <Check className="ml-1 inline h-3 w-3" />}
                    {s.label}
                  </button>
                ))}

                <div className="flex-1" />

                {canEdit && (
                  editing ? (
                    <>
                      <button
                        type="button"
                        disabled={busy || draftErrors.length > 0}
                        onClick={() => void saveEdits()}
                        className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
                      >
                        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        حفظ
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => { setDraft(device); setEditing(false); }}
                        className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                      >
                        إلغاء
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setEditing(true)}
                      className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                    >
                      <Pencil className="h-4 w-4" /> تعديل
                    </button>
                  )
                )}

                {canDelete && (
                  <button
                    type="button"
                    disabled={busy || editing}
                    onClick={() => void removeDevice()}
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-red-600 hover:bg-[var(--color-surface-2)] disabled:opacity-50 dark:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" /> حذف
                  </button>
                )}
              </div>

              {canAudit && (
                <div>
                  <div className="mb-2 text-sm font-bold text-[var(--color-text)]">
                    أثر التدقيق ({audit.length})
                  </div>
                  <div className="max-h-64 overflow-y-auto rounded-xl border border-[var(--color-border)]">
                    {audit.length === 0 ? (
                      <div className="p-3 text-sm text-[var(--color-text-muted)]">لا أحداث بعد.</div>
                    ) : (
                      <ul className="divide-y divide-[var(--color-border)]">
                        {audit.map((row) => (
                          <li key={row.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 p-2 text-xs">
                            <span className="font-bold text-[var(--color-text)]">{row.action_label}</span>
                            <span className="text-[var(--color-text-muted)]">{row.actor_name}</span>
                            <span className="text-[var(--color-text-muted)]">
                              {formatDateTimeValue(row.created_at)}
                            </span>
                            <span className="w-full text-[var(--color-text-muted)] sm:w-auto">
                              {auditDetailText(row)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}

              <datalist id="device-model-suggestions-detail">
                {modelNames.map((name) => <option key={name} value={name} />)}
              </datalist>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default DeviceDetailModal;
