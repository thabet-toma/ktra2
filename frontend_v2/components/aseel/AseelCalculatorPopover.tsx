import React, { useState, useEffect, useLayoutEffect, useRef } from "react";
import { X, Delete, History as HistoryIcon, Trash2 } from "lucide-react";
import { evaluateArithmeticExpression } from "../../utils/arithmetic";
import { useToast } from "../../contexts/ToastContext";
import { humanizeThrown } from "../../utils/drfError";

/** T-C1: ذاكرة العمليات السابقة — تُحفظ محلياً وتبقى بين الجلسات. */
const HISTORY_KEY = "aseel_calc_history";
type CalcEntry = { expr: string; result: string };

/** مستطيل الحقل الهدف (للإيفكت: الحاسبة تطير نحوه عند الإغلاق). */
type AnchorRect = { x: number; y: number; width: number; height: number };

/** مدة إيفكت الخروج (ms) — بطيء كفايةً كي تُرى الحاسبة وهي تطير نحو الحقل. */
const EXIT_MS = 620;
const ENTER_MS = 200;

interface AseelCalculatorPopoverProps {
  initialValue: string | number;
  x: number;
  y: number;
  onConfirm: (val: number) => void;
  onClose: () => void;
  /** task16 E15: حاسبة مستقلة (من أيقونة الشريط) — «=» تعرض الناتج ولا تملأ خلية */
  standalone?: boolean;
  /** إن مُرّر: عند الإغلاق/التأكيد تطير الحاسبة (تنكمش) نحو هذا الحقل بدل التلاشي مكانها. */
  anchorRect?: AnchorRect | null;
}

/** يُظهر × و÷ و− للعرض فقط (التقييم يبقى على * و/ و-). */
const prettyExpr = (s: string) =>
  s.replace(/\*/g, "×").replace(/\//g, "÷").replace(/-/g, "−");

/** زر عصري بلمعان 3D وتوهّج وضغطة حيّة. */
const CalcButton: React.FC<{
  children: React.ReactNode;
  colorClass?: string;
  className?: string;
  onClick?: () => void;
}> = ({ children, colorClass = "bg-white/5 text-slate-100 hover:bg-white/10 border border-white/10", className = "", onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`relative overflow-hidden flex items-center justify-center text-xl font-semibold rounded-2xl transition-all duration-200 active:scale-90 shadow-lg ${colorClass} ${className}`}
  >
    {/* لمعان خفيف أعلى الزر لإعطاء بروز 3D */}
    <div className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-white/15 to-transparent pointer-events-none" />
    <span className="relative z-10">{children}</span>
  </button>
);

export const AseelCalculatorPopover: React.FC<AseelCalculatorPopoverProps> = ({
  initialValue,
  x,
  y,
  onConfirm,
  onClose,
  standalone = false,
  anchorRect = null,
}) => {
  const toast = useToast();
  const [expression, setExpression] = useState(() => {
    const v = Number(initialValue);
    return isNaN(v) || v === 0 ? "" : String(v);
  });
  const containerRef = useRef<HTMLDivElement | null>(null);

  // تموضع مثبَّت داخل الشاشة — يُصحَّح بعد القياس كي لا يُقطع أسفل/يمين الحاسبة
  // (يراعي الارتفاع الحقيقي مع/بلا لوحة الذاكرة). التصحيح في useLayoutEffect أدناه.
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: y, left: x });

  // إيفكت الدخول/الخروج: enter (منكمش شفّاف) ← shown ← leave (يطير نحو الحقل).
  const [anim, setAnim] = useState<"enter" | "shown" | "leave">("enter");
  const leaveDelta = useRef<{ tx: number; ty: number }>({ tx: 0, ty: 0 });

  // T-C1: ذاكرة العمليات السابقة (محفوظة محلياً).
  const [history, setHistory] = useState<CalcEntry[]>(() => {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      return raw ? (JSON.parse(raw) as CalcEntry[]) : [];
    } catch {
      return [];
    }
  });
  const [showHistory, setShowHistory] = useState(false);

  // صحّح التموضع بعد القياس (وعند فتح/إغلاق لوحة الذاكرة التي تغيّر الارتفاع).
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const h = el.offsetHeight;
    const w = el.offsetWidth;
    setPos({
      top: Math.max(8, Math.min(y, window.innerHeight - h - 8)),
      left: Math.max(8, Math.min(x, window.innerWidth - w - 8)),
    });
  }, [x, y, showHistory]);

  const pushHistory = (expr: string, result: number) => {
    setHistory((prev) => {
      const next = [{ expr, result: String(result) }, ...prev].slice(0, 25);
      try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
      } catch {
        /* localStorage غير متاح (وضع خاص) — تجاهل */
      }
      return next;
    });
  };

  const clearHistory = () => {
    setHistory([]);
    try {
      localStorage.removeItem(HISTORY_KEY);
    } catch {
      /* تجاهل */
    }
  };

  // Focus the container on mount + شغّل إيفكت الدخول في الإطار التالي.
  useEffect(() => {
    containerRef.current?.focus();
    const raf = requestAnimationFrame(() => setAnim("shown"));
    return () => cancelAnimationFrame(raf);
  }, []);

  /** يشغّل إيفكت الخروج (طيران بطيء نحو الحقل إن وُجد) ثم ينفّذ الإجراء. */
  const animateOut = (done: () => void) => {
    const el = containerRef.current;
    if (el && anchorRect) {
      const rect = el.getBoundingClientRect();
      leaveDelta.current = {
        tx: anchorRect.x + anchorRect.width / 2 - (rect.left + rect.width / 2),
        ty: anchorRect.y + anchorRect.height / 2 - (rect.top + rect.height / 2),
      };
    } else {
      leaveDelta.current = { tx: 0, ty: 0 };
    }
    setAnim("leave");
    window.setTimeout(done, EXIT_MS);
  };

  const requestClose = () => animateOut(onClose);

  const handleKeyPress = (char: string) => {
    setExpression((prev) => prev + char);
  };

  const handleClear = () => {
    setExpression("");
  };

  const handleBackspace = () => {
    setExpression((prev) => prev.slice(0, -1));
  };

  /** يحسب التعبير الحالي ويسجّله في الذاكرة — بلا إغلاق ولا تعبئة حقل. */
  const evaluateCurrent = (): number | null => {
    try {
      const result = evaluateArithmeticExpression(expression);
      const rounded = Number(result.toFixed(4));
      // T-C1: سجّل العملية في الذاكرة قبل عرض/تأكيد الناتج.
      if (expression.trim() && expression.trim() !== String(rounded)) {
        pushHistory(expression.trim(), rounded);
      }
      return rounded;
    } catch (e) {
      toast(humanizeThrown(e), 'error');
      return null;
    }
  };

  // «=» تحسب وتعرض الناتج فقط — الحاسبة تبقى مفتوحة لمواصلة الحساب.
  const handleEvaluate = () => {
    const rounded = evaluateCurrent();
    if (rounded !== null) setExpression(String(rounded));
  };

  // «تسجيل» — الإجراء الوحيد الذي يعبّئ الحقل ويُغلق الحاسبة (يطير نحو الحقل إن وُجد).
  const handleRecord = () => {
    const rounded = evaluateCurrent();
    if (rounded !== null) animateOut(() => onConfirm(rounded));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      requestClose();
    } else if (e.key === "Enter") {
      e.preventDefault();
      handleEvaluate();
    } else if (e.key === "Backspace") {
      e.preventDefault();
      handleBackspace();
    } else if (["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "+", "-", "*", "/", "."].includes(e.key)) {
      e.preventDefault();
      handleKeyPress(e.key);
    }
  };

  // نمط الإيفكت: انكماش/ظهور عند الدخول، وطيران/انكماش نحو الحقل عند الخروج.
  const transform =
    anim === "enter"
      ? "scale(.9)"
      : anim === "leave"
        ? `translate(${leaveDelta.current.tx}px, ${leaveDelta.current.ty}px) scale(.05)`
        : "scale(1)";
  const transition =
    anim === "leave"
      ? `transform ${EXIT_MS}ms cubic-bezier(.5,0,.2,1), opacity ${EXIT_MS}ms cubic-bezier(.7,0,.9,1)`
      : `transform ${ENTER_MS}ms cubic-bezier(.2,.8,.25,1), opacity ${ENTER_MS}ms ease`;

  const opBtn = "bg-indigo-500/80 text-white border border-indigo-400/30 hover:bg-indigo-500 shadow-[0_0_14px_rgba(99,102,241,.35)]";

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      className="fixed z-[99] w-72 outline-none select-none rounded-[2rem] p-4 bg-slate-800/40 backdrop-blur-2xl border border-slate-700/50 shadow-[0_20px_50px_rgba(0,0,0,.55)] overflow-hidden"
      style={{
        top: pos.top,
        left: pos.left,
        transform,
        opacity: anim === "shown" ? 1 : 0,
        transformOrigin: "center",
        transition,
        willChange: "transform, opacity",
      }}
      dir="ltr"
    >
      {/* توهّج خلفي زخرفي */}
      <div className="absolute -top-16 -right-16 w-40 h-40 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-16 -left-16 w-40 h-40 bg-emerald-500/15 rounded-full blur-3xl pointer-events-none" />

      {/* أدوات علوية: عنوان + ذاكرة + إغلاق */}
      <div className="relative flex justify-between items-center mb-3">
        <span className="text-xs font-extrabold bg-gradient-to-l from-emerald-400 to-indigo-400 bg-clip-text text-transparent tracking-wider">حاسبة الأصيل</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setShowHistory((s) => !s)}
            title="ذاكرة العمليات السابقة"
            className={`p-1.5 rounded-full bg-black/25 hover:bg-black/40 ${showHistory ? "text-emerald-400" : "text-slate-200"}`}
          >
            <HistoryIcon className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={requestClose}
            title="إغلاق"
            className="p-1.5 rounded-full bg-black/25 text-slate-200 hover:bg-rose-500 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* T-C1: لوحة ذاكرة العمليات السابقة — نقرة على عملية تستعيد ناتجها. */}
      {showHistory && (
        <div className="relative mb-3 border border-slate-700/60 rounded-2xl overflow-hidden bg-slate-950/50">
          <div className="flex justify-between items-center px-2 py-1 bg-white/5">
            <span className="text-[11px] font-semibold text-slate-400">العمليات السابقة</span>
            {history.length > 0 && (
              <button type="button" onClick={clearHistory} title="مسح الذاكرة" className="text-slate-400 hover:text-rose-400 p-0.5 rounded">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <div className="max-h-32 overflow-y-auto">
            {history.length === 0 ? (
              <div className="px-2 py-3 text-center text-[11px] text-slate-500">لا عمليات محفوظة</div>
            ) : (
              history.map((h, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => { setExpression(h.result); setShowHistory(false); }}
                  title="استعادة الناتج"
                  className="w-full flex justify-between items-baseline gap-2 px-2 py-1 text-right hover:bg-white/5 border-b border-white/5 last:border-0"
                >
                  <span className="font-mono text-[11px] text-slate-500 truncate">{prettyExpr(h.expr)}</span>
                  <span className="font-mono text-xs font-bold text-emerald-400">= {h.result}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* الشاشة — داكنة أنيقة بلمعان علوي وثلاث نقاط حالة */}
      <div className="relative bg-slate-950/80 rounded-3xl px-4 py-3 mb-4 border border-slate-800/80 shadow-inner min-h-[80px] flex flex-col justify-between overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-white/5 to-transparent pointer-events-none" />
        <div className="relative flex justify-between items-center">
          <span className="text-slate-500 text-[10px] tracking-[.2em] font-semibold uppercase">Aseel Calc</span>
          <div className="flex gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          </div>
        </div>
        <span className="relative text-white text-4xl font-light tracking-wider truncate w-full text-right drop-shadow-[0_0_15px_rgba(255,255,255,.2)]">
          {prettyExpr(expression) || "0"}
        </span>
      </div>

      {/* شبكة الأزرار */}
      <div className="relative grid grid-cols-4 gap-2.5 h-64">
        <CalcButton colorClass="bg-rose-500/80 text-white border border-rose-400/30 hover:bg-rose-500 shadow-[0_0_14px_rgba(244,63,94,.35)] text-lg font-bold" onClick={handleClear}>C</CalcButton>
        <CalcButton colorClass="bg-amber-400/80 text-white border border-amber-300/30 hover:bg-amber-400 shadow-[0_0_14px_rgba(251,191,36,.3)]" onClick={handleBackspace}><Delete className="w-5 h-5" /></CalcButton>
        <CalcButton colorClass={opBtn} onClick={() => handleKeyPress("/")}>÷</CalcButton>
        <CalcButton colorClass={opBtn} onClick={() => handleKeyPress("*")}>×</CalcButton>

        <CalcButton onClick={() => handleKeyPress("7")}>7</CalcButton>
        <CalcButton onClick={() => handleKeyPress("8")}>8</CalcButton>
        <CalcButton onClick={() => handleKeyPress("9")}>9</CalcButton>
        <CalcButton colorClass={opBtn} onClick={() => handleKeyPress("-")}>−</CalcButton>

        <CalcButton onClick={() => handleKeyPress("4")}>4</CalcButton>
        <CalcButton onClick={() => handleKeyPress("5")}>5</CalcButton>
        <CalcButton onClick={() => handleKeyPress("6")}>6</CalcButton>
        <CalcButton colorClass={opBtn} onClick={() => handleKeyPress("+")}>+</CalcButton>

        <CalcButton onClick={() => handleKeyPress("1")}>1</CalcButton>
        <CalcButton onClick={() => handleKeyPress("2")}>2</CalcButton>
        <CalcButton onClick={() => handleKeyPress("3")}>3</CalcButton>
        <CalcButton className="text-2xl font-extrabold" colorClass={opBtn} onClick={handleEvaluate}>=</CalcButton>

        <CalcButton className="col-span-2" onClick={() => handleKeyPress("0")}>0</CalcButton>
        <CalcButton onClick={() => handleKeyPress(".")}>.</CalcButton>
        {!standalone && (
          <CalcButton
            className="text-xs font-extrabold"
            colorClass="bg-emerald-500/90 text-white border border-emerald-400/30 hover:bg-emerald-500 shadow-[0_0_18px_rgba(16,185,129,.45)]"
            onClick={handleRecord}
          >
            تسجيل
          </CalcButton>
        )}
      </div>
    </div>
  );
};
