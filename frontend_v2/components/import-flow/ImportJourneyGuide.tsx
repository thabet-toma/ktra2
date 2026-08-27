import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { Compass, ChevronDown, RefreshCw, Check, ArrowLeft, FolderOpen } from "lucide-react";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useAuth } from "../../contexts/AuthContext";
import { fetchImportJourneySummary } from "../../services/importJourneyApi";
import { clientLogger } from "../../services/logger";
import {
  IMPORT_GUIDE_SLOT_ID,
  readImportGuideOpen,
  writeImportGuideOpen,
} from "../../utils/importGuidePref";
import {
  buildImportJourney,
  matchImportStage,
  type ImportJourneyStep,
  type ImportJourneySummaryFacts,
  type ImportStageKey,
} from "./importJourneyGuidance";

/**
 * مرشد رحلة الاستيراد — لوح متاح في **كل** الشاشات، ومطويّ حتى يُطلَب.
 *
 * السبب: الرحلة تمتدّ على ست شاشات مستقلة (عرض، صفقة، شحنة، تخليص، نقل محلي،
 * فاتورة)، وكل شاشة كانت تعرف خطوتها هي فقط. فمن يقف في شاشة المنتجات أو
 * المحاسبة لا يعرف أن شحنته تنتظر إثبات استحقاق الشحن. اللوح يحمل الجواب معه:
 * أين نحن، ما التالي، وأين يُنفَّذ — بزر واحد يقود إلى مكان الإجراء نفسه.
 *
 * لكنه **مرافق لا مقيم**: لوحٌ ثابت مفتوح فوق كل شاشة يزاحم عمل من لا يستورد
 * اليوم. فمطويّاً لا يبقى منه على الشاشة شيء — يبقى زرّ «مرشد الرحلة» في شريط
 * الرأس (portal إلى مرساه في `AppLayout`)، والتفضيل يُحفظ لكل مستخدم على حدة
 * (`utils/importGuidePref.ts`).
 *
 * القرار ليس هنا: كل منطق المراحل في `importJourneyGuidance.ts` (مُختبَر وحده).
 */

const FOCUS_KEY = "ktra.importGuide.focus";
/** لا نعيد الجلب أكثر من مرة كل دقيقة عند العودة للتبويب. */
const REFRESH_COOLDOWN_MS = 60_000;

const STATE_DOT: Record<ImportJourneyStep["state"], string> = {
  done: "bg-emerald-500",
  current: "bg-blue-600",
  todo: "bg-amber-400",
  optional: "bg-[var(--color-border)]",
};

const readFocus = (): { shipmentId?: number | null; dealId?: number | null } => {
  try {
    const raw = sessionStorage.getItem(FOCUS_KEY);
    return raw ? (JSON.parse(raw) as { shipmentId?: number; dealId?: number }) : {};
  } catch {
    return {};
  }
};

export const ImportJourneyGuide: React.FC = () => {
  const { can } = usePermissions();
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const userId = currentUser?.id ?? null;
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<ImportJourneySummaryFacts | null>(null);
  const [available, setAvailable] = useState(true);
  const [loading, setLoading] = useState(false);
  const [focus, setFocus] = useState(readFocus);
  // مرسى زرّ الرأس يُركَّب بعد أول رسم (نفس شجرة `AppLayout`)، فيُقرأ في تأثير
  // لا أثناء الرسم — وقراءته أثناء الرسم كانت تعطي null دائماً فيختفي الزر.
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const allowed = can("import.deal.manage");

  // التفضيل يتبع المستخدم لا الجهاز: تبديل الحساب على الجهاز نفسه يعيد القراءة.
  useEffect(() => {
    setOpen(readImportGuideOpen(localStorage, userId));
  }, [userId]);

  useEffect(() => {
    setSlot(document.getElementById(IMPORT_GUIDE_SLOT_ID));
  }, [location.pathname]);

  const load = useCallback(() => {
    setLoading(true);
    fetchImportJourneySummary()
      .then((data) => {
        setSummary(data);
        setAvailable(true);
      })
      .catch((error) => {
        // 403 (بلا صلاحية استيراد) أو وحدة مطفأة ⇒ لا لوح إطلاقاً، بلا ضجيج.
        setAvailable(false);
        clientLogger.info("import_guide.unavailable", { message: String(error?.message || error) });
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
  }, [allowed, load]);

  // بلا استطلاع دوري (نفس سياسة الصفقات): تحديث عند العودة للتبويب فقط.
  useEffect(() => {
    if (!allowed) return;
    let last = Date.now();
    const onFocus = () => {
      if (document.visibilityState === "hidden") return;
      if (Date.now() - last < REFRESH_COOLDOWN_MS) return;
      last = Date.now();
      load();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [allowed, load]);

  const toggle = () => {
    setOpen((value) => {
      const next = !value;
      writeImportGuideOpen(localStorage, userId, next);
      return next;
    });
  };

  const pickFocus = (next: { shipmentId?: number | null; dealId?: number | null }) => {
    setFocus(next);
    try {
      sessionStorage.setItem(FOCUS_KEY, JSON.stringify(next));
    } catch { /* تجاهل */ }
  };

  // اللوح مرافق ثانوي في كل شاشة — خطأ غير متوقع في بناء الرحلة (بيانات حافّة لم
  // تُختبَر بعد) يجب أن يُخفي اللوح فقط، لا أن يُسقط الشاشة كلها بصفحة بيضاء
  // (لا يوجد ErrorBoundary يلتقط استثناء أثناء الرسم).
  const view = useMemo(() => {
    if (!summary) return null;
    try {
      return buildImportJourney(summary, focus);
    } catch (error) {
      clientLogger.error("import_guide.build_failed", { message: String((error as Error)?.message || error) });
      return null;
    }
  }, [summary, focus]);
  const hereStage: ImportStageKey | null = useMemo(
    () => matchImportStage(location.pathname, location.search),
    [location.pathname, location.search],
  );

  if (!allowed || !available || !view) return null;

  const go = (route: string) => {
    clientLogger.info("import_guide.navigate", { route });
    navigate(route);
    // الإجراء يغيّر الوقائع (دفعة، استحقاق، تخليص) — أعِد الجلب بعد استقرار الشاشة.
    window.setTimeout(load, 1500);
  };

  const pending = view.steps.filter((s) => s.state === "todo").length;

  if (!open) {
    // مطويّاً: لا شيء يطفو فوق المحتوى. الزرّ في شريط الرأس حيث تُطلَب الأدوات،
    // ويحمل الخطوة الحالية كي يبقى مفيداً بلا فتح. وإن غاب المرسى (شاشة خارج
    // القشرة) يعود الزرّ عائماً صغيراً — أفضل من مرشدٍ لا طريق إليه.
    const reopen = (
      <button
        type="button"
        onClick={toggle}
        className={
          slot
            ? "flex items-center gap-1.5 rounded-lg border border-blue-200/80 bg-white/75 px-2.5 py-1.5 text-[11px] font-semibold text-blue-900 shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-white hover:shadow-md dark:border-blue-900/60 dark:bg-slate-900/55 dark:text-blue-200 dark:hover:border-blue-700 dark:hover:bg-slate-900"
            : "fixed bottom-3 z-[60] flex items-center gap-1.5 rounded-full border border-blue-300 bg-white/95 px-3 py-2 text-xs font-semibold text-blue-900 shadow-lg backdrop-blur transition-colors hover:bg-blue-50 dark:border-blue-800 dark:bg-slate-900/95 dark:text-blue-200 dark:hover:bg-slate-800"
        }
        style={slot ? undefined : { insetInlineEnd: 12 }}
        title={`مرشد رحلة الاستيراد — ${view.focus.label} · الخطوة ${view.current.order}: ${view.current.label}`}
      >
        <Compass className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-300" />
        <span className="whitespace-nowrap">مرشد الرحلة</span>
        <span className="whitespace-nowrap rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-semibold text-white">
          {view.current.order}. {view.current.label}
        </span>
        {pending > 0 && (
          <span className="whitespace-nowrap rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
            {pending} ناقصة
          </span>
        )}
      </button>
    );
    return slot ? createPortal(reopen, slot) : reopen;
  }

  return (
    <aside
      dir="rtl"
      className="fixed bottom-3 z-[60] flex max-h-[78vh] w-[22rem] flex-col overflow-hidden rounded-xl border border-blue-200 bg-[var(--color-surface)] shadow-2xl dark:border-blue-900"
      style={{ insetInlineEnd: 12 }}
      aria-label="مرشد رحلة الاستيراد"
    >
      <header className="flex items-center gap-2 border-b border-[var(--color-border)] bg-gradient-to-l from-blue-50 to-transparent px-3 py-2 dark:from-blue-950/40">
        <Compass className="h-4 w-4 text-blue-700 dark:text-blue-300" />
        <span className="text-sm font-bold text-[var(--color-text)]">مرشد رحلة الاستيراد</span>
        <button
          type="button"
          onClick={load}
          className="ms-auto rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
          title="تحديث"
          aria-label="تحديث المرشد"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
        <button
          type="button"
          onClick={toggle}
          className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
          title="طيّ المرشد"
          aria-label="طيّ المرشد"
        >
          <ChevronDown className="h-4 w-4" />
        </button>
      </header>

      {view.options.length > 1 && (
        <div className="border-b border-[var(--color-border)] px-3 py-2">
          <label className="block text-[10px] font-semibold text-[var(--color-text-muted)]">الرحلة المتابَعة</label>
          <select
            className="mt-1 w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs"
            value={focus.shipmentId ? `s:${focus.shipmentId}` : focus.dealId ? `d:${focus.dealId}` : ""}
            onChange={(event) => {
              const [kind, id] = event.target.value.split(":");
              if (!kind) return pickFocus({});
              pickFocus(kind === "s" ? { shipmentId: Number(id) } : { dealId: Number(id) });
            }}
          >
            <option value="">— تلقائي (أحدث رحلة) —</option>
            {view.options.map((option) => (
              <option
                key={`${option.kind}-${option.shipmentId ?? option.dealId}`}
                value={option.shipmentId ? `s:${option.shipmentId}` : `d:${option.dealId}`}
                title={option.label}
              >
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="border-b border-[var(--color-border)] bg-blue-50/60 px-3 py-2 dark:bg-blue-950/30">
        {/* اسم الصفقة نصّ حرّ يكتبه المستخدم وقد يطول: يُقصّ إلى سطر واحد مع
            التلميح الكامل، ولا يُزيح «الخطوة س من ص» إلى سطر ثانٍ ولا يدفعها
            خارج اللوح. */}
        <div className="flex items-baseline gap-1.5 text-[10px] font-semibold text-blue-700 dark:text-blue-300">
          <span className="min-w-0 flex-1 truncate" title={view.focus.label}>{view.focus.label}</span>
          <span className="shrink-0">الخطوة {view.current.order} من {view.steps.length}</span>
        </div>
        <div className="mt-0.5 text-sm font-bold text-[var(--color-text)]">{view.current.label}</div>
        <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-muted)]">{view.current.detail}</p>
        <button
          type="button"
          onClick={() => go(view.current.route)}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-xs font-bold text-white shadow-sm transition-colors hover:bg-blue-700"
        >
          {view.current.ctaLabel}
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        {/* الملف لم يُفتح بعد: دعوة صريحة لا شارةٌ غائبة. الغياب الصامت يقول
            «لا أوراق مطلوبة» — عكس الحقيقة، وهو ما وُجدت الوحدة لإزالته. */}
        {view.file.state === "unopened" && view.file.route && (
          <button
            type="button"
            onClick={() => go(view.file.route as string)}
            className="mt-1.5 flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-[11px] font-semibold text-amber-900 transition-colors hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200 dark:hover:bg-amber-900/50"
          >
            <FolderOpen className="h-3.5 w-3.5" />
            لم يُفتح ملف الاستيراد بعد — افتحه لتعرف الأوراق المطلوبة
          </button>
        )}
      </div>

      <ol className="flex-1 overflow-y-auto px-2 py-2">
        {view.steps.map((step) => {
          const here = hereStage === step.key;
          return (
            <li key={step.key}>
              <button
                type="button"
                onClick={() => go(step.route)}
                className={`mb-1 flex w-full items-start gap-2 rounded-lg border px-2 py-2 text-right transition-colors ${
                  step.state === "current"
                    ? "border-blue-400 bg-blue-50/70 dark:border-blue-700 dark:bg-blue-900/20"
                    : here
                      ? "border-[var(--color-border)] bg-[var(--color-surface-2)]"
                      : "border-transparent hover:bg-[var(--color-surface-2)]"
                }`}
                title={step.purpose}
              >
                <span className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] text-white ${STATE_DOT[step.state]}`}>
                  {step.state === "done" ? <Check className="h-3 w-3" /> : step.order}
                </span>
                <span className="flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className={`text-xs font-semibold ${step.state === "optional" ? "text-[var(--color-text-muted)]" : "text-[var(--color-text)]"}`}>
                      {step.label}
                    </span>
                    {step.optional && <span className="text-[9px] text-[var(--color-text-muted)]">اختيارية</span>}
                    {here && <span className="rounded bg-[var(--color-surface-3)] px-1 text-[9px] text-[var(--color-text-muted)]">أنت هنا</span>}
                    {/* أرقام الخادم كما هي — لا حساب هنا (المصدر واحد مع اللوحة). */}
                    {step.fileProgress && (
                      <span
                        className={`rounded px-1 text-[9px] font-semibold ${
                          step.fileProgress.done >= step.fileProgress.total
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
                            : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
                        }`}
                        title="أوراق ملف الاستيراد المطلوبة في هذه المرحلة"
                      >
                        المستندات {step.fileProgress.done} من {step.fileProgress.total}
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-[11px] leading-relaxed text-[var(--color-text-muted)]">{step.detail}</span>
                  <span className="mt-0.5 block text-[10px] font-semibold text-blue-700 dark:text-blue-300">{step.ctaLabel} ←</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <footer className="flex flex-wrap gap-1.5 border-t border-[var(--color-border)] px-3 py-2 text-[10px]">
        <button
          type="button"
          onClick={() => go("/import-offers")}
          className="rounded-full bg-[var(--color-surface-3)] px-2 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          عروض بانتظار قرار: {summary?.offers.awaiting_decision ?? 0}
        </button>
        <button
          type="button"
          onClick={() => go("/deals")}
          className="rounded-full bg-[var(--color-surface-3)] px-2 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          صفقات بلا شحنة: {summary?.deals.without_shipment ?? 0}
        </button>
        <button
          type="button"
          onClick={() => go("/shipments")}
          className="rounded-full bg-[var(--color-surface-3)] px-2 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          شحنات نشطة: {summary?.shipments.length ?? 0}
        </button>
      </footer>
    </aside>
  );
};
