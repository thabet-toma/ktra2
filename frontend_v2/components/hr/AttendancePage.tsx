import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarCheck, Loader2, RefreshCw, Plus, Ban, MapPin, Image as ImageIcon,
  Pencil, X, Check, Search, Upload,
} from "lucide-react";
import {
  ATTENDANCE_STATUS_LABELS,
  createManualPunch, listAttendanceDays, listCheckEvents, overrideAttendanceDay,
  importAttendanceCsv, recomputeAttendance, voidCheckEvent,
  type AttendanceDayRow, type AttendanceImportResult, type AttendanceStatus,
  type CheckEventRow,
} from "../../services/hrAttendanceApi";
import { listEmployees, type Employee } from "../../services/payrollApi";
import { currentMonth, formatMinutes, monthDays, statusPillClass } from "../../utils/attendance";
import { formatNumber } from "../../utils/formatNumber";
import { formatDateLocalized, formatTimeValue } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";

/**
 * T-HR M3 — «الحضور والانصراف» الإدارية: شبكة الشهر، وسجل البصمات الخام.
 *
 * تحلّ محلّ الشاشة القديمة المبنيّة على جلسات مرآة Firestore
 * (`services/attendanceService.ts`) والتي لم تكن تمسّ `/api/hr/` أصلاً ولا
 * تربط الحضور بالموظف ولا بالرواتب.
 *
 * **صفٌّ لكل يوم لا لكل سجل** في الشبكة: اليوم بلا تسجيل يبقى فراغاً ظاهراً
 * فتُرى الثغرة — نفس قاعدة كشف الدوام في `utils/payroll.ts`.
 */

const cardClass =
  "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4";
const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";
const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";
const btnPrimary =
  "inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3 h-9 text-sm " +
  "font-semibold text-white disabled:opacity-50";
const btnGhost =
  "inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 h-9 " +
  "text-sm text-[var(--color-text)] disabled:opacity-50";

type Tab = "grid" | "events" | "import";

const mapLink = (lat: string | null, lng: string | null) =>
  lat && lng ? `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}` : "";

export const AttendancePage: React.FC = () => {
  const permissions = usePermissions();
  const toast = useToast();
  const confirm = useConfirm();
  const canManage = permissions.can("hr.attendance.manage");

  const [tab, setTab] = useState<Tab>("grid");
  const [month, setMonth] = useState(() => currentMonth());
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [days, setDays] = useState<AttendanceDayRow[]>([]);
  const [events, setEvents] = useState<CheckEventRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [onlyRejected, setOnlyRejected] = useState(false);
  const [punchDraft, setPunchDraft] = useState<
    { employee: number | ""; kind: "in" | "out"; ts: string; notes: string } | null>(null);
  const [editing, setEditing] = useState<AttendanceDayRow | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [staff, dayRows, eventRows] = await Promise.all([
        listEmployees(),
        listAttendanceDays({ month }),
        listCheckEvents({ month, accepted: onlyRejected ? false : undefined }),
      ]);
      setEmployees(staff);
      setDays(dayRows);
      setEvents(eventRows);
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر تحميل بيانات الحضور."), "error");
    } finally {
      setLoading(false);
    }
  }, [month, onlyRejected, toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const visibleEmployees = useMemo(() => {
    const needle = search.trim();
    const active = employees.filter((e) => e.is_active !== false);
    return needle ? active.filter((e) => (e.name || "").includes(needle)) : active;
  }, [employees, search]);

  /** خريطة (موظف، يوم) — الشبكة تُبنى من الأيام كلها لا من الصفوف الموجودة. */
  const dayMap = useMemo(() => {
    const map = new Map<string, AttendanceDayRow>();
    days.forEach((row) => map.set(`${row.employee}:${row.date}`, row));
    return map;
  }, [days]);

  const calendar = useMemo(() => monthDays(month), [month]);

  const runRecompute = async () => {
    const dates = monthDays(month);
    if (dates.length === 0) return;
    setBusy(true);
    try {
      const result = await recomputeAttendance({
        from: dates[0], to: dates[dates.length - 1],
      });
      toast(`أُعيد حساب ${formatNumber(result.recomputed, { maxDecimals: 0 })} يوماً.`, "success");
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّرت إعادة الحساب."), "error");
    } finally {
      setBusy(false);
    }
  };

  const savePunch = async () => {
    if (!punchDraft || !punchDraft.employee || !punchDraft.ts) {
      toast("اختر الموظف ووقت البصمة.", "error");
      return;
    }
    setBusy(true);
    try {
      await createManualPunch({
        employee: Number(punchDraft.employee),
        kind: punchDraft.kind,
        ts: new Date(punchDraft.ts).toISOString(),
        notes: punchDraft.notes,
      });
      toast("تمت إضافة البصمة.", "success");
      setPunchDraft(null);
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر حفظ البصمة."), "error");
    } finally {
      setBusy(false);
    }
  };

  const voidEvent = async (row: CheckEventRow) => {
    const ok = await confirm({
      title: "إبطال البصمة",
      message: `ستُبطل بصمة «${row.employee_name}» في ${formatDateLocalized(row.attendance_date)}. تبقى في السجل ولا تدخل الحساب.`,
      confirmText: "إبطال",
      danger: true,
    });
    if (!ok) return;
    try {
      await voidCheckEvent(row.id);
      toast("أُبطلت البصمة وأُعيد حساب يومها.", "success");
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر إبطال البصمة."), "error");
    }
  };

  const saveOverride = async (payload: Record<string, unknown>) => {
    if (!editing) return;
    setBusy(true);
    try {
      await overrideAttendanceDay(editing.id, payload);
      toast("تم تصحيح اليوم.", "success");
      setEditing(null);
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر تصحيح اليوم."), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        <CalendarCheck size={20} className="text-[var(--color-primary)]" />
        <h1 className="text-lg font-bold">الحضور والانصراف</h1>
        <div className="ms-auto flex flex-wrap items-center gap-2">
          <input
            type="month"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            className={`${inputClass} w-40`}
            aria-label="الشهر"
          />
          <button type="button" className={btnGhost} disabled={busy} onClick={() => void runRecompute()}>
            <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> إعادة حساب الشهر
          </button>
          {canManage && (
            <button
              type="button"
              className={btnPrimary}
              onClick={() => setPunchDraft({
                employee: "", kind: "in",
                ts: new Date().toISOString().slice(0, 16), notes: "",
              })}
            >
              <Plus size={14} /> تسجيل الحضور
            </button>
          )}
        </div>
      </header>

      <nav className="flex gap-1 border-b border-[var(--color-border)]">
        {([
          ["grid", "السجل اليومي"],
          ["events", "سجل البصمات"],
          ...(canManage ? [["import", "استيراد"] as [Tab, string]] : []),
        ] as [Tab, string][]).map(
          ([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`px-3 py-2 text-sm ${
                tab === key
                  ? "border-b-2 border-[var(--color-primary)] font-semibold text-[var(--color-primary)]"
                  : "text-[var(--color-text-muted)]"
              }`}
            >
              {label}
            </button>
          ))}
        <div className="ms-auto flex items-center gap-2 pb-1">
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute inset-y-0 my-auto start-2 text-[var(--color-text-muted)]"
            />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="بحث باسم الموظف"
              className={`${inputClass} ps-7 w-44`}
            />
          </div>
          {tab === "events" && (
            <label className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={onlyRejected}
                onChange={(event) => setOnlyRejected(event.target.checked)}
              />
              المرفوضة فقط
            </label>
          )}
        </div>
      </nav>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin" /></div>
      ) : tab === "grid" ? (
        <div className={`${cardClass} overflow-x-auto`}>
          <table className="w-full min-w-[900px] text-sm">
            <thead>
              <tr className="text-[var(--color-text-muted)]">
                <th className="sticky start-0 bg-[var(--color-surface)] p-2 text-start">الموظف</th>
                {calendar.map((iso) => (
                  <th key={iso} className="p-1 text-center text-[11px]">
                    {iso.slice(8)}
                  </th>
                ))}
                <th className="p-2 text-center text-[11px]">الساعات</th>
              </tr>
            </thead>
            <tbody>
              {visibleEmployees.length === 0 ? (
                <tr>
                  <td colSpan={calendar.length + 2} className="py-8 text-center text-[var(--color-text-muted)]">
                    لا موظفون لعرضهم.
                  </td>
                </tr>
              ) : (
                visibleEmployees.map((employee) => {
                  const rows = calendar.map((iso) => dayMap.get(`${employee.id}:${iso}`));
                  const total = rows.reduce((sum, row) => sum + (row?.worked_minutes || 0), 0);
                  return (
                    <tr key={employee.id} className="border-t border-[var(--color-border)]">
                      <td className="sticky start-0 bg-[var(--color-surface)] p-2 font-semibold">
                        {employee.name}
                      </td>
                      {rows.map((row, index) => (
                        <td key={calendar[index]} className="p-1 text-center">
                          {row ? (
                            <button
                              type="button"
                              disabled={!canManage}
                              onClick={() => setEditing(row)}
                              title={`${row.status_label}${row.late_minutes ? ` — تأخير ${formatMinutes(row.late_minutes)}` : ""}`}
                              className={`${statusPillClass(row.status)} ${canManage ? "cursor-pointer" : "cursor-default"}`}
                            >
                              {row.status === "present" ? "✓"
                                : row.status === "late" ? "ت"
                                  : row.status === "absent" ? "غ"
                                    : row.status === "leave" ? "إ"
                                      : row.status === "holiday" ? "ع"
                                        : row.status === "off" ? "—" : "·"}
                            </button>
                          ) : (
                            // اليوم بلا صفّ يبقى فراغاً ظاهراً فتُرى الثغرة.
                            <span className="text-[var(--color-text-muted)]">·</span>
                          )}
                        </td>
                      ))}
                      <td className="p-2 text-center font-semibold">{formatMinutes(total)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
            ✓ حاضر · ت متأخّر · غ غائب · إ إجازة · ع عطلة رسمية · — عطلة أسبوعية · · بلا تسجيل
          </p>
        </div>
      ) : tab === "import" ? (
        <ImportPanel onDone={() => void reload()} />
      ) : (
        <div className={`${cardClass} overflow-x-auto`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-muted)]">
                <th className="p-2 text-start">الموظف</th>
                <th className="p-2 text-start">تاريخ ووقت التسجيل</th>
                <th className="p-2 text-start">دخول/خروج</th>
                <th className="p-2 text-start">المصدر</th>
                <th className="p-2 text-start">الحالة</th>
                <th className="p-2 text-start">الموقع</th>
                {canManage && <th className="p-2" />}
              </tr>
            </thead>
            <tbody>
              {events.filter((row) => !search.trim() || row.employee_name.includes(search.trim()))
                .length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-[var(--color-text-muted)]">
                    لا بصمات في هذا الشهر.
                  </td>
                </tr>
              ) : (
                events
                  .filter((row) => !search.trim() || row.employee_name.includes(search.trim()))
                  .map((row) => (
                    <tr
                      key={row.id}
                      className={`border-t border-[var(--color-border)] ${row.is_voided ? "opacity-50" : ""}`}
                    >
                      <td className="p-2">
                        <div className="font-semibold">{row.employee_name}</div>
                        <div className="text-[11px] text-[var(--color-text-muted)]">
                          #{row.employee_code}
                        </div>
                      </td>
                      <td className="p-2">
                        {formatDateLocalized(row.attendance_date)} — {formatTimeValue(row.ts)}
                      </td>
                      <td className="p-2">{row.kind_label}</td>
                      <td className="p-2">{row.source_label}</td>
                      <td className="p-2">
                        {row.is_voided ? (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700">
                            مُبطَلة
                          </span>
                        ) : row.accepted ? (
                          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] text-emerald-800">
                            مسجَّل
                          </span>
                        ) : (
                          <span
                            className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] text-red-800"
                            title={row.reject_label}
                          >
                            {row.reject_label || "مرفوضة"}
                          </span>
                        )}
                      </td>
                      <td className="p-2">
                        <div className="flex items-center gap-2">
                          {mapLink(row.latitude, row.longitude) && (
                            <a
                              href={mapLink(row.latitude, row.longitude)}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="inline-flex items-center gap-1 text-xs underline"
                            >
                              <MapPin size={12} /> خريطة
                            </a>
                          )}
                          {row.photo_url && (
                            <a
                              href={row.photo_url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="inline-flex items-center gap-1 text-xs underline"
                            >
                              <ImageIcon size={12} /> صورة
                            </a>
                          )}
                          {row.distance_m != null && (
                            <span className="text-[11px] text-[var(--color-text-muted)]">
                              {formatNumber(row.distance_m, { maxDecimals: 0 })} م
                            </span>
                          )}
                        </div>
                      </td>
                      {canManage && (
                        <td className="p-2 text-end">
                          {!row.is_voided && row.accepted && (
                            <button
                              type="button"
                              className={btnGhost}
                              onClick={() => void voidEvent(row)}
                            >
                              <Ban size={14} /> إبطال
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {punchDraft && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-3">
          <div className={`${cardClass} w-full max-w-md`}>
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-bold">تسجيل بصمة يدوية</h2>
              <button type="button" className="ms-auto" onClick={() => setPunchDraft(null)} aria-label="إغلاق">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className={labelClass} htmlFor="punch-employee">الموظف</label>
                <select
                  id="punch-employee"
                  className={inputClass}
                  value={punchDraft.employee}
                  onChange={(event) => setPunchDraft({
                    ...punchDraft,
                    employee: event.target.value ? Number(event.target.value) : "",
                  })}
                >
                  <option value="">— اختر —</option>
                  {employees.map((employee) => (
                    <option key={employee.id} value={employee.id}>{employee.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelClass} htmlFor="punch-kind">النوع</label>
                <select
                  id="punch-kind"
                  className={inputClass}
                  value={punchDraft.kind}
                  onChange={(event) => setPunchDraft({
                    ...punchDraft, kind: event.target.value as "in" | "out",
                  })}
                >
                  <option value="in">دخول</option>
                  <option value="out">خروج</option>
                </select>
              </div>
              <div>
                <label className={labelClass} htmlFor="punch-ts">تاريخ ووقت التسجيل</label>
                <input
                  id="punch-ts"
                  type="datetime-local"
                  className={inputClass}
                  value={punchDraft.ts}
                  onChange={(event) => setPunchDraft({ ...punchDraft, ts: event.target.value })}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="punch-notes">ملاحظات</label>
                <input
                  id="punch-notes"
                  className={inputClass}
                  value={punchDraft.notes}
                  onChange={(event) => setPunchDraft({ ...punchDraft, notes: event.target.value })}
                />
              </div>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={() => setPunchDraft(null)}>إلغاء</button>
              <button type="button" className={btnPrimary} disabled={busy} onClick={() => void savePunch()}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} حفظ
              </button>
            </div>
          </div>
        </div>
      )}

      {editing && (
        <DayOverrideDialog
          day={editing}
          busy={busy}
          onClose={() => setEditing(null)}
          onSave={saveOverride}
        />
      )}
    </div>
  );
};

/**
 * استيراد سجل الحضور من CSV — مخرَج أجهزة البصمة وجداول Excel.
 *
 * **الفحص قبل الكتابة إلزاميّ في التدفّق**: الزرّ الأول «فحص» والثاني لا يظهر
 * إلا بعده، لأن الاستيراد الأعمى في سجلٍّ لا يُحذف منه شيء خطأٌ لا يُتراجَع
 * عنه بسهولة. والتصدير يمرّ بمركز التقارير (`سجل البصمات`) بلا زرٍّ هنا.
 */
const ImportPanel: React.FC<{ onDone: () => void }> = ({ onDone }) => {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [checked, setChecked] = useState<AttendanceImportResult | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (dryRun: boolean) => {
    if (!file) {
      toast("اختر ملف CSV أولاً.", "error");
      return;
    }
    setBusy(true);
    try {
      const result = await importAttendanceCsv(file, dryRun);
      setChecked(result);
      if (!dryRun) {
        toast(
          `استُوردت ${formatNumber(result.created, { maxDecimals: 0 })} بصمة على ${formatNumber(result.days, { maxDecimals: 0 })} يوماً.`,
          "success");
        setFile(null);
        setChecked(null);
        onDone();
      }
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر استيراد الملف."), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`${cardClass} space-y-3`}>
      <div>
        <h2 className="flex items-center gap-1.5 font-bold">
          <Upload size={15} /> استيراد سجل الحضور
        </h2>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          ملف CSV بأربعة أعمدة: رقم الموظف · التاريخ (YYYY-MM-DD) · وقت الدخول · وقت الخروج.
          الترويسة اختيارية وتُقبل بالعربية أو الإنجليزية. الخروج الأبكر من الدخول
          يُفهم وردية ليلية عبرت منتصف الليل.
        </p>
      </div>

      <input
        type="file"
        accept=".csv,text/csv"
        onChange={(event) => {
          setFile(event.target.files?.[0] || null);
          setChecked(null);
        }}
        className="block w-full text-sm"
      />

      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnGhost} disabled={busy || !file} onClick={() => void run(true)}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} فحص الملف
        </button>
        <button
          type="button"
          className={btnPrimary}
          disabled={busy || !checked || checked.created === 0}
          onClick={() => void run(false)}
        >
          <Check size={14} /> استيراد فعلي
        </button>
      </div>

      {checked && (
        <div className="rounded-xl border border-[var(--color-border)] p-3 text-sm">
          <p>
            صفوف صالحة تُنتج <b>{formatNumber(checked.created, { maxDecimals: 0 })}</b> بصمة
            على <b>{formatNumber(checked.days, { maxDecimals: 0 })}</b> يوماً.
            {checked.error_count > 0 && (
              <> ومعها <b>{formatNumber(checked.error_count, { maxDecimals: 0 })}</b> سطراً لن يُستورد.</>
            )}
          </p>
          {checked.errors.length > 0 && (
            <ul className="mt-2 max-h-40 space-y-0.5 overflow-y-auto text-xs text-amber-900">
              {checked.errors.map((row) => (
                <li key={row.row}>سطر {row.row}: {row.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

/** تصحيح يومٍ بيد مشرف — يُعلن نفسه، ورفعُه يعيد اليوم إلى حكم بصماته. */
const DayOverrideDialog: React.FC<{
  day: AttendanceDayRow;
  busy: boolean;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => void | Promise<void>;
}> = ({ day, busy, onClose, onSave }) => {
  const [status, setStatus] = useState<AttendanceStatus>(day.status);
  const [late, setLate] = useState(String(day.late_minutes));
  const [worked, setWorked] = useState(String(day.worked_minutes));
  const [notes, setNotes] = useState(day.notes || "");

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-3">
      <div className={`${cardClass} w-full max-w-md`}>
        <div className="mb-3 flex items-center gap-2">
          <Pencil size={15} />
          <h2 className="font-bold">
            {day.employee_name} — {formatDateLocalized(day.date)}
          </h2>
          <button type="button" className="ms-auto" onClick={onClose} aria-label="إغلاق">
            <X size={16} />
          </button>
        </div>
        <div className="space-y-2">
          <div>
            <label className={labelClass} htmlFor="day-status">الحالة</label>
            <select
              id="day-status"
              className={inputClass}
              value={status}
              onChange={(event) => setStatus(event.target.value as AttendanceStatus)}
            >
              {(Object.keys(ATTENDANCE_STATUS_LABELS) as AttendanceStatus[]).map((key) => (
                <option key={key} value={key}>{ATTENDANCE_STATUS_LABELS[key]}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelClass} htmlFor="day-worked">دقائق العمل</label>
              <input
                id="day-worked"
                type="number"
                min={0}
                className={inputClass}
                value={worked}
                onChange={(event) => setWorked(event.target.value)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="day-late">دقائق التأخير</label>
              <input
                id="day-late"
                type="number"
                min={0}
                className={inputClass}
                value={late}
                onChange={(event) => setLate(event.target.value)}
              />
            </div>
          </div>
          <div>
            <label className={labelClass} htmlFor="day-notes">سبب التصحيح</label>
            <input
              id="day-notes"
              className={inputClass}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
          {day.is_manual_override && (
            <p className="text-[11px] text-amber-800">
              هذا اليوم مُصحَّح يدوياً — إعادة الحساب لا تكتسحه حتى تُرفع علامة التصحيح.
            </p>
          )}
        </div>
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          {day.is_manual_override && (
            <button
              type="button"
              className={btnGhost}
              disabled={busy}
              onClick={() => void onSave({ is_manual_override: false })}
            >
              رفع التصحيح وإعادة الحساب
            </button>
          )}
          <button type="button" className={btnGhost} onClick={onClose}>إلغاء</button>
          <button
            type="button"
            className={btnPrimary}
            disabled={busy}
            onClick={() => void onSave({
              status,
              worked_minutes: Number(worked) || 0,
              late_minutes: Number(late) || 0,
              notes,
              is_manual_override: true,
            })}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} حفظ التصحيح
          </button>
        </div>
      </div>
    </div>
  );
};

export default AttendancePage;
