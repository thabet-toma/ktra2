import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ShieldAlert, Camera, Loader2, Check, AlertTriangle, Search, RotateCcw, Eye,
  Trash2, X, ImageOff, ChevronRight, ChevronLeft,
} from "lucide-react";
import {
  DEVICE_STATUSES,
  checkImei,
  createDevice,
  listDeviceModelNames,
  listDevices,
  restoreDevice,
  uploadDevicePhoto,
  type DeviceDuplicateMatch,
  type DeviceListFilters,
  type DeviceStatus,
  type SensitiveDeviceRow,
} from "../../services/devicesApi";
import { IMEI_LENGTH, imeiDigits, imeiState, isValidPhone, normalizePhone } from "../../utils/imei";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useToast } from "../../contexts/ToastContext";
import { DeviceDetailModal } from "./DeviceDetailModal";
import { statusPillClass } from "./deviceStatus";
import { BarcodeScannerModal } from "../shared/BarcodeScannerModal";
import { FileDropZone } from "../ui/FileDropZone";

/**
 * THA-45 M2 — «تسجيل وتتبع الأجهزة الحساسة»: ثلاث مناطق فوق بعضها كما في نموذج
 * المالك — نموذج الاستقبال، ثم شريط البحث والفلترة، ثم سجل التتبع.
 *
 * الشاشة تعيش خلف حارس ترخيص الوحدة في `App.tsx`، والخادم يرد 404 لكل نقطة
 * لشركةٍ غير مرخّصة — فلا تُبنى هنا طبقةُ إخفاءٍ ثالثة، بل تُستهلك الصلاحيات
 * لتعطيل ما لا يملكه المستخدم.
 *
 * الاستقبال يجري عند الكاونتر على جهاز محمول: النموذج عمود واحد على الشاشة
 * الصغيرة، وحقلا SN وIMEI يقبلان الماسح الضوئي (إدخال سريع ينتهي بـEnter)، وفحص
 * الـIMEI يجري لحظة اكتمال الخانة الخامسة عشرة لا عند الحفظ.
 *
 * التكرار **تنبيه لا منع**: الجهاز نفسه قد يعود مرة أخرى، فالسجل يُحفَظ ويُعرض
 * ما سبقه.
 */

const PAGE_SIZE = 25;

const EMPTY_DRAFT = {
  customer_name: "",
  customer_phone: "",
  model_name: "",
  serial_number: "",
  imei: "",
  technical_notes: "",
  photo_url: "",
};

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const cardClass = "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4";

/** سطر «سجل سابق بنفس الـIMEI» — يُقرأ في تنبيه النموذج وفي نتيجة الحفظ معاً. */
const DuplicateList: React.FC<{ matches: DeviceDuplicateMatch[] }> = ({ matches }) => (
  <ul className="mt-1 space-y-0.5">
    {matches.map((m) => (
      <li key={m.id} className="flex flex-wrap items-center gap-x-2 text-xs">
        <span className="font-semibold">{m.customer_name}</span>
        <span>{formatDateTimeValue(m.created_at)}</span>
        <span className={statusPillClass(m.status)}>{m.status_label}</span>
      </li>
    ))}
  </ul>
);

export const SensitiveDevicesScreen: React.FC = () => {
  const toast = useToast();
  const { can } = usePermissions();
  const canCreate = can("devices.registry.create");
  const canEdit = can("devices.registry.edit");
  const canDelete = can("devices.registry.delete");
  const canAudit = can("devices.audit.view");

  // ── نموذج الاستقبال ────────────────────────────────────────────────────
  const [draft, setDraft] = useState({ ...EMPTY_DRAFT });
  const [saving, setSaving] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [imeiMatches, setImeiMatches] = useState<DeviceDuplicateMatch[]>([]);
  const [imeiChecking, setImeiChecking] = useState(false);
  const [savedDuplicates, setSavedDuplicates] = useState<DeviceDuplicateMatch[] | null>(null);
  const [modelNames, setModelNames] = useState<string[]>([]);
  // الحقل الذي يستقبل قراءة الكاميرا — يفتح BarcodeScannerModal حتى يُغلق.
  const [scanTarget, setScanTarget] = useState<"serial_number" | "imei" | null>(null);

  // ── البحث والفلترة ─────────────────────────────────────────────────────
  const [searchText, setSearchText] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<DeviceStatus | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(false);

  // ── السجل ──────────────────────────────────────────────────────────────
  const [rows, setRows] = useState<SensitiveDeviceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [listErr, setListErr] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [restoringId, setRestoringId] = useState<number | null>(null);

  const currentImeiState = imeiState(draft.imei);

  // البحث يُسجَّل حدثاً في التدقيق عند كل نداء بنصّ — الإبطاء 500ms هو ما يمنع
  // سطراً لكل حرف.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(searchText.trim());
      setPage(1);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchText]);

  const filters: DeviceListFilters = useMemo(() => ({
    q: query,
    status,
    date_from: dateFrom,
    date_to: dateTo,
    include_deleted: includeDeleted,
  }), [query, status, dateFrom, dateTo, includeDeleted]);

  const load = useCallback(async () => {
    setLoading(true);
    setListErr(null);
    try {
      const paged = await listDevices(filters, page, PAGE_SIZE);
      setRows(paged.results);
      setTotal(paged.count);
    } catch (e) {
      setListErr(messageOf(e, "تعذّر تحميل سجل الأجهزة"));
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { void load(); }, [load]);

  const loadModelNames = useCallback(async () => {
    try {
      setModelNames(await listDeviceModelNames());
    } catch {
      /* الاقتراحات تحسينٌ لا شرط — الإدخال الحر يبقى متاحاً */
    }
  }, []);

  useEffect(() => { void loadModelNames(); }, [loadModelNames]);

  // فحص التكرار لحظة اكتمال الرقم — لا عند الحفظ، فالموظف يريد أن يعرف الآن.
  useEffect(() => {
    if (currentImeiState !== "valid") {
      setImeiMatches([]);
      return;
    }
    const digits = imeiDigits(draft.imei);
    let alive = true;
    setImeiChecking(true);
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const result = await checkImei(digits);
          if (alive) setImeiMatches(result.matches || []);
        } catch {
          if (alive) setImeiMatches([]);
        } finally {
          if (alive) setImeiChecking(false);
        }
      })();
    }, 300);
    return () => { alive = false; clearTimeout(timer); };
  }, [draft.imei, currentImeiState]);

  const pickPhoto = async (file: File | null) => {
    if (!file) return;
    setPhotoBusy(true);
    try {
      const url = await uploadDevicePhoto(file);
      setDraft((d) => ({ ...d, photo_url: url }));
    } catch (e) {
      // فشل الرفع لا يمنع التسجيل — الصورة اختيارية والسجل هو المطلوب.
      toast(`${messageOf(e, "تعذّر رفع الصورة")} — يمكن التسجيل بلا صورة`, "error");
    } finally {
      setPhotoBusy(false);
    }
  };

  const validationProblems = useMemo(() => {
    const problems: string[] = [];
    if (!draft.customer_name.trim()) problems.push("اسم العميل مطلوب");
    if (!isValidPhone(draft.customer_phone)) problems.push("رقم الهاتف غير صالح (7–15 رقماً)");
    if (!draft.model_name.trim()) problems.push("موديل الجهاز مطلوب");
    if (!draft.serial_number.trim()) problems.push("الرقم التسلسلي مطلوب");
    // IMEI اختياري — يُرفض فقط ما أُدخل ناقصاً أو ساقطاً في Luhn، والفراغ يمرّ.
    if (currentImeiState !== "valid" && currentImeiState !== "empty") {
      problems.push(`رقم IMEI يجب أن يكون ${IMEI_LENGTH} خانة تجتاز Luhn — أو اتركه فارغاً`);
    }
    return problems;
  }, [draft, currentImeiState]);

  const clearForm = () => {
    setDraft({ ...EMPTY_DRAFT });
    setFormErr(null);
    setImeiMatches([]);
    setSavedDuplicates(null);
  };

  const submit = async () => {
    if (validationProblems.length > 0) {
      setFormErr(validationProblems.join(" · "));
      return;
    }
    setSaving(true);
    setFormErr(null);
    try {
      const created = await createDevice({
        customer_name: draft.customer_name.trim(),
        customer_phone: normalizePhone(draft.customer_phone),
        model_name: draft.model_name.trim(),
        serial_number: draft.serial_number.trim(),
        imei: imeiDigits(draft.imei),
        technical_notes: draft.technical_notes,
        photo_url: draft.photo_url,
      });
      toast(
        created.imei
          ? `تم تسجيل الجهاز — IMEI ${created.imei}`
          : `تم تسجيل الجهاز — SN ${created.serial_number}`,
        "success",
      );
      setSavedDuplicates(created.duplicate_of?.length ? created.duplicate_of : null);
      setDraft({ ...EMPTY_DRAFT });
      setImeiMatches([]);
      setPage(1);
      await Promise.all([load(), loadModelNames()]);
    } catch (e) {
      setFormErr(messageOf(e, "تعذّر تسجيل الجهاز"));
    } finally {
      setSaving(false);
    }
  };

  const undoDelete = async (row: SensitiveDeviceRow) => {
    setRestoringId(row.id);
    try {
      await restoreDevice(row.id);
      toast(`تم استرجاع سجل ${row.imei || row.serial_number}`, "success");
      await load();
    } catch (e) {
      setListErr(messageOf(e, "تعذّر استرجاع السجل"));
    } finally {
      setRestoringId(null);
    }
  };

  const resetFilters = () => {
    setSearchText("");
    setQuery("");
    setStatus("");
    setDateFrom("");
    setDateTo("");
    setIncludeDeleted(false);
    setPage(1);
  };

  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div dir="rtl" className="space-y-4 p-3 md:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldAlert className="h-5 w-5 text-[var(--color-primary)]" />
        <span className="text-lg font-bold text-[var(--color-text)]">
          تسجيل وتتبع الأجهزة الحساسة
        </span>
        <span className="text-[11px] text-[var(--color-text-muted)]">
          سجل توثيقي وأمني — لا يُنشئ قيداً محاسبياً ولا فاتورة، ولا يُحذف منه سجل نهائياً
        </span>
      </div>

      {/* ── المنطقة 1: نموذج تسجيل جهاز جديد ──────────────────────────── */}
      <section className={cardClass}>
        <h2 className="mb-3 font-bold text-[var(--color-text)]">نموذج تسجيل جهاز جديد</h2>

        {!canCreate && (
          <div className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-[var(--color-text-muted)]">
            لا تملك صلاحية تسجيل جهاز جديد — يمكنك البحث في السجل ومعاينته فقط.
          </div>
        )}

        <div className="flex flex-col gap-4 md:flex-row-reverse">
          {/* الحقول */}
          <div className="min-w-0 flex-1 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className={labelClass} htmlFor="device-customer-name">اسم العميل</label>
              <input
                id="device-customer-name"
                className={inputClass}
                placeholder="اسم العميل"
                disabled={!canCreate}
                value={draft.customer_name}
                onChange={(e) => setDraft({ ...draft, customer_name: e.target.value })}
              />
            </div>

            <div>
              <label className={labelClass} htmlFor="device-customer-phone">رقم هاتف العميل</label>
              <input
                id="device-customer-phone"
                className={inputClass}
                inputMode="tel"
                placeholder="0599123456"
                disabled={!canCreate}
                value={draft.customer_phone}
                onChange={(e) => setDraft({ ...draft, customer_phone: e.target.value })}
              />
              {draft.customer_phone.trim() !== "" && !isValidPhone(draft.customer_phone) && (
                <span className="mt-1 block text-[11px] text-red-600 dark:text-red-400">
                  صيغة غير صالحة — من 7 إلى 15 رقماً، مع مقدمة دولية اختيارية (+)
                </span>
              )}
            </div>

            <div>
              <label className={labelClass} htmlFor="device-model">موديل الجهاز</label>
              <input
                id="device-model"
                className={inputClass}
                list="device-model-suggestions"
                placeholder="موديل الجهاز"
                disabled={!canCreate}
                value={draft.model_name}
                onChange={(e) => setDraft({ ...draft, model_name: e.target.value })}
              />
              <datalist id="device-model-suggestions">
                {modelNames.map((name) => <option key={name} value={name} />)}
              </datalist>
            </div>

            <div>
              <label className={labelClass} htmlFor="device-serial">الرقم التسلسلي (SN)</label>
              <div className="relative">
                <input
                  id="device-serial"
                  className={`${inputClass} pl-9`}
                  placeholder="امسح الباركود أو اكتب الرقم"
                  autoComplete="off"
                  disabled={!canCreate}
                  value={draft.serial_number}
                  onChange={(e) => setDraft({ ...draft, serial_number: e.target.value })}
                  // الماسح الضوئي ينهي القراءة بـEnter — لا يُرسل النموذج قبل اكتماله.
                  onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }}
                />
                <button
                  type="button"
                  disabled={!canCreate}
                  onClick={() => setScanTarget("serial_number")}
                  className="absolute inset-y-0 left-1 my-auto flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-primary)] disabled:opacity-40"
                  title="مسح السيريال بكاميرا الجهاز"
                  aria-label="مسح السيريال بكاميرا الجهاز"
                >
                  <Camera className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div>
              <label className={labelClass} htmlFor="device-imei">رقم الـ IMEI (اختياري)</label>
              <div className="relative">
                <input
                  id="device-imei"
                  className={`${inputClass} pl-16 ${
                    currentImeiState === "invalid"
                      ? "border-red-500"
                      : currentImeiState === "valid" && imeiMatches.length === 0
                        ? "border-emerald-500"
                        : ""
                  }`}
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder={`${IMEI_LENGTH} خانة`}
                  disabled={!canCreate}
                  value={draft.imei}
                  onChange={(e) => setDraft({ ...draft, imei: imeiDigits(e.target.value) })}
                  onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }}
                />
                <span className="absolute inset-y-0 left-9 flex items-center">
                  {imeiChecking && <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-muted)]" />}
                  {!imeiChecking && currentImeiState === "valid" && imeiMatches.length === 0 && (
                    <Check className="h-4 w-4 text-emerald-600" />
                  )}
                  {!imeiChecking && currentImeiState === "invalid" && (
                    <X className="h-4 w-4 text-red-600" />
                  )}
                </span>
                <button
                  type="button"
                  disabled={!canCreate}
                  onClick={() => setScanTarget("imei")}
                  className="absolute inset-y-0 left-1 my-auto flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-primary)] disabled:opacity-40"
                  title="مسح الـ IMEI بكاميرا الجهاز"
                  aria-label="مسح الـ IMEI بكاميرا الجهاز"
                >
                  <Camera className="h-4 w-4" />
                </button>
              </div>
              {currentImeiState === "partial" && (
                <span className="mt-1 block text-[11px] text-[var(--color-text-muted)]">
                  {formatNumber(imeiDigits(draft.imei).length)} من {formatNumber(IMEI_LENGTH)}
                </span>
              )}
              {currentImeiState === "invalid" && (
                <span className="mt-1 block text-[11px] text-red-600 dark:text-red-400">
                  رقم غير صالح — لا يجتاز خانة التحقق (Luhn)
                </span>
              )}
            </div>

            <div className="sm:col-span-2 lg:col-span-3">
              <label className={labelClass} htmlFor="device-notes">ملاحظات فنية</label>
              <input
                id="device-notes"
                className={inputClass}
                placeholder="ملاحظات فنية عن حالة الجهاز"
                disabled={!canCreate}
                value={draft.technical_notes}
                onChange={(e) => setDraft({ ...draft, technical_notes: e.target.value })}
              />
            </div>
          </div>

          {/* صورة الجهاز — التقاط مباشر من كاميرا الجهاز المحمول (`capture="environment"`
              يُمرَّر إلى `input` داخل المنطقة)، أو سحب، أو لصق (Ctrl+V). */}
          <div className="w-full shrink-0 md:w-44">
            <span className={labelClass}>صورة الجهاز</span>
            {draft.photo_url ? (
              <>
                <div className="flex h-36 w-full items-center justify-center overflow-hidden rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-2)]">
                  <img src={draft.photo_url} alt="صورة الجهاز" className="h-full w-full object-cover" />
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <FileDropZone
                    onFiles={(files) => { void pickPhoto(files[0]); }}
                    accept="image"
                    capture="environment"
                    variant="compact"
                    busy={photoBusy}
                    disabled={!canCreate}
                    hint="تغيير الصورة"
                    className="flex-1"
                  />
                  <button
                    type="button"
                    className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                    title="إزالة الصورة"
                    onClick={() => setDraft({ ...draft, photo_url: "" })}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </>
            ) : (
              <FileDropZone
                onFiles={(files) => { void pickPhoto(files[0]); }}
                accept="image"
                capture="environment"
                variant="compact"
                busy={photoBusy}
                disabled={!canCreate}
                hint="صورة الجهاز — اضغط أو التقطها"
                subHint="أو اسحب الصورة إلى هنا، أو الصق (Ctrl+V)"
                className="h-36 w-full"
              />
            )}
          </div>
        </div>

        {imeiMatches.length > 0 && (
          <div className="mt-3 rounded-lg border border-amber-400 bg-amber-50 p-2.5 text-sm text-amber-900 dark:border-amber-600 dark:bg-amber-900/30 dark:text-amber-200">
            <div className="flex items-center gap-1 font-bold">
              <AlertTriangle className="h-4 w-4" />
              هذا الـ IMEI مسجَّل سابقاً لدى شركتك ({formatNumber(imeiMatches.length)})
            </div>
            <DuplicateList matches={imeiMatches} />
            <div className="mt-1 text-[11px]">
              التسجيل غير ممنوع — قد يكون الجهاز نفسه عاد. راجع السجل السابق قبل المتابعة.
            </div>
          </div>
        )}

        {formErr && (
          <div className="mt-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
            {formErr}
          </div>
        )}

        {savedDuplicates && (
          <div className="mt-3 rounded-lg border border-amber-400 bg-amber-50 p-2.5 text-sm text-amber-900 dark:border-amber-600 dark:bg-amber-900/30 dark:text-amber-200">
            <div className="font-bold">تم التسجيل، ولهذا الـ IMEI سجلات سابقة:</div>
            <DuplicateList matches={savedDuplicates} />
          </div>
        )}

        <div className="mt-3 flex flex-col-reverse gap-2 sm:flex-row">
          <button
            type="button"
            onClick={clearForm}
            disabled={saving}
            className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50 sm:w-40"
          >
            مسح الحقول
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canCreate || saving || photoBusy}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            تسجيل
          </button>
        </div>
      </section>

      {/* ── المنطقة 2: شريط البحث المتقدم والفلترة ─────────────────────── */}
      <section className={cardClass}>
        <h2 className="mb-3 font-bold text-[var(--color-text)]">شريط البحث المتقدم والفلترة</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <label className={labelClass} htmlFor="device-search">
              بحث بـ IMEI أو SN أو اسم العميل أو هاتفه
            </label>
            <div className="relative">
              <input
                id="device-search"
                className={`${inputClass} pl-9`}
                placeholder="بحث…"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
              <span className="absolute inset-y-0 left-2 flex items-center text-[var(--color-text-muted)]">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </span>
            </div>
          </div>
          <div>
            <label className={labelClass} htmlFor="device-date-from">من تاريخ</label>
            <input
              id="device-date-from"
              type="date"
              className={inputClass}
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="device-date-to">إلى تاريخ</label>
            <input
              id="device-date-to"
              type="date"
              className={inputClass}
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="device-status-filter">حالة التتبع</label>
            <select
              id="device-status-filter"
              className={inputClass}
              value={status}
              onChange={(e) => { setStatus(e.target.value as DeviceStatus | ""); setPage(1); }}
            >
              <option value="">الكل</option>
              {DEVICE_STATUSES.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          {canDelete && (
            <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
              <input
                type="checkbox"
                checked={includeDeleted}
                onChange={(e) => { setIncludeDeleted(e.target.checked); setPage(1); }}
              />
              إظهار السجلات المحذوفة
            </label>
          )}
          <button
            type="button"
            onClick={resetFilters}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          >
            <RotateCcw className="h-4 w-4" /> مسح الفلاتر
          </button>
        </div>
      </section>

      {/* ── المنطقة 3: سجل التسجيل والتتبع الأمني ──────────────────────── */}
      <section className={cardClass}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-bold text-[var(--color-text)]">سجل التسجيل والتتبع الأمني</h2>
          <span className="text-xs text-[var(--color-text-muted)]">
            {formatNumber(total)} سجل
          </span>
        </div>

        {listErr && (
          <div className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
            {listErr}
          </div>
        )}

        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>صورة</th>
                <th>تاريخ التسجيل</th>
                <th>اسم العميل / الهاتف</th>
                <th className="hidden md:table-cell">الموديل</th>
                <th className="hidden md:table-cell">السيريال (SN)</th>
                <th>IMEI</th>
                <th className="hidden lg:table-cell">المستخدم المسجل</th>
                <th>حالة التتبع</th>
                <th>معاينة</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={row.is_deleted ? "opacity-60" : undefined}
                >
                  <td>
                    <div className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg bg-[var(--color-surface-2)]">
                      {row.photo_url ? (
                        <img src={row.photo_url} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <ImageOff className="h-4 w-4 text-[var(--color-text-muted)]" />
                      )}
                    </div>
                  </td>
                  <td className="whitespace-nowrap">{formatDateTimeValue(row.created_at)}</td>
                  <td>
                    <div className="font-semibold text-[var(--color-text)]">{row.customer_name}</div>
                    <div className="text-[11px] text-[var(--color-text-muted)]">{row.customer_phone}</div>
                  </td>
                  <td className="hidden md:table-cell">{row.model_name}</td>
                  <td className="hidden md:table-cell">{row.serial_number}</td>
                  <td className="whitespace-nowrap font-mono">{row.imei || "—"}</td>
                  <td className="hidden lg:table-cell">{row.created_by_name}</td>
                  <td>
                    <span className={statusPillClass(row.status)}>{row.status_label}</span>
                    {row.is_deleted && (
                      <span className="mr-1 text-[11px] font-bold text-red-600 dark:text-red-400">محذوف</span>
                    )}
                  </td>
                  <td>
                    {/* الخادم يُخفي المحذوف عن `GET {id}/` (404) ويُبقي
                        `restore` عاملاً — فالمعاينة لا تُفتح على سجلٍ محذوف،
                        والاسترجاع هو إجراؤه الوحيد. بدونه يبقى مَن أظهر
                        المحذوفة أمام صفٍّ بلا مخرج. */}
                    {row.is_deleted ? (
                      <button
                        type="button"
                        disabled={restoringId === row.id}
                        onClick={() => void undoDelete(row)}
                        className="inline-flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs text-emerald-700 hover:bg-[var(--color-surface-2)] disabled:opacity-50 dark:text-emerald-400"
                        title="استرجاع السجل المحذوف"
                        aria-label={`استرجاع سجل ${row.imei}`}
                      >
                        <RotateCcw className="h-4 w-4" /> استرجاع
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setOpenId(row.id)}
                        className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-primary)]"
                        title="معاينة السجل وأثره"
                        aria-label={`معاينة سجل ${row.imei}`}
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && rows.length === 0 && (
          <div className="p-6 text-center text-sm text-[var(--color-text-muted)]">
            لا سجلات مطابقة — سجّل جهازاً من النموذج أعلاه، أو وسّع نطاق البحث.
          </div>
        )}
        {loading && rows.length === 0 && (
          <div className="flex items-center justify-center gap-2 p-6 text-sm text-[var(--color-text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" /> جارٍ التحميل…
          </div>
        )}

        {lastPage > 1 && (
          <div className="mt-3 flex items-center justify-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] disabled:opacity-40"
              title="الصفحة السابقة"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            <span className="text-xs text-[var(--color-text-muted)]">
              صفحة {formatNumber(page)} من {formatNumber(lastPage)}
            </span>
            <button
              type="button"
              disabled={page >= lastPage}
              onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
              className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] disabled:opacity-40"
              title="الصفحة التالية"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        )}
      </section>

      {scanTarget && (
        <BarcodeScannerModal
          title={scanTarget === "imei" ? "مسح الـ IMEI بالكاميرا" : "مسح السيريال بالكاميرا"}
          onDetect={(value) => {
            setDraft((d) =>
              scanTarget === "imei"
                ? { ...d, imei: imeiDigits(value) }
                : { ...d, serial_number: value },
            );
          }}
          onClose={() => setScanTarget(null)}
        />
      )}

      {openId != null && (
        <DeviceDetailModal
          deviceId={openId}
          canEdit={canEdit}
          canDelete={canDelete}
          canAudit={canAudit}
          modelNames={modelNames}
          onClose={() => setOpenId(null)}
          onChanged={() => { void load(); void loadModelNames(); }}
        />
      )}
    </div>
  );
};

export default SensitiveDevicesScreen;
