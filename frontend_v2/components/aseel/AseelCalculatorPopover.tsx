import React, { useState, useEffect, useRef } from "react";
import { X, Delete, History as HistoryIcon, Trash2 } from "lucide-react";
import { evaluateArithmeticExpression } from "../../utils/arithmetic";

/** T-C1: ذاكرة العمليات السابقة — تُحفظ محلياً وتبقى بين الجلسات. */
const HISTORY_KEY = "aseel_calc_history";
type CalcEntry = { expr: string; result: string };

interface AseelCalculatorPopoverProps {
  initialValue: string | number;
  x: number;
  y: number;
  onConfirm: (val: number) => void;
  onClose: () => void;
  /** task16 E15: حاسبة مستقلة (من أيقونة الشريط) — «=» تعرض الناتج ولا تملأ خلية */
  standalone?: boolean;
}

export const AseelCalculatorPopover: React.FC<AseelCalculatorPopoverProps> = ({
  initialValue,
  x,
  y,
  onConfirm,
  onClose,
  standalone = false,
}) => {
  const [expression, setExpression] = useState(() => {
    const v = Number(initialValue);
    return isNaN(v) || v === 0 ? "" : String(v);
  });
  const containerRef = useRef<HTMLDivElement | null>(null);

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

  // Focus the container on mount to catch keyboard events
  useEffect(() => {
    containerRef.current?.focus();
  }, []);

  const handleKeyPress = (char: string) => {
    setExpression((prev) => prev + char);
  };

  const handleClear = () => {
    setExpression("");
  };

  const handleBackspace = () => {
    setExpression((prev) => prev.slice(0, -1));
  };

  const handleEvaluate = () => {
    try {
      const result = evaluateArithmeticExpression(expression);
      const rounded = Number(result.toFixed(4));
      // T-C1: سجّل العملية في الذاكرة قبل عرض/تأكيد الناتج.
      if (expression.trim() && expression.trim() !== String(rounded)) {
        pushHistory(expression.trim(), rounded);
      }
      if (standalone) {
        // حاسبة مستقلة: اعرض الناتج وأبقِ النافذة لمواصلة الحساب
        setExpression(String(rounded));
      } else {
        onConfirm(rounded);
      }
    } catch {
      alert("تعبير غير صالح");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
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

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      className="fixed z-[99] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-2xl rounded-2xl p-3 w-64 outline-none select-none"
      style={{
        top: Math.min(y, window.innerHeight - 320),
        left: Math.min(x, window.innerWidth - 280),
      }}
      dir="ltr"
    >
      <div className="flex justify-between items-center mb-2 pb-2 border-b border-gray-100 dark:border-gray-700">
        <span className="text-xs font-bold bg-gradient-to-l from-emerald-500 to-blue-500 bg-clip-text text-transparent">حاسبة الأصيل</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowHistory((s) => !s)}
            title="ذاكرة العمليات السابقة"
            className={`p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 ${showHistory ? "text-emerald-600" : "text-gray-400 hover:text-gray-600 dark:hover:text-white"}`}
          >
            <HistoryIcon className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-white p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* T-C1: لوحة ذاكرة العمليات السابقة — نقرة على عملية تستعيد ناتجها. */}
      {showHistory && (
        <div className="mb-2 border border-gray-100 dark:border-gray-700 rounded-xl overflow-hidden">
          <div className="flex justify-between items-center px-2 py-1 bg-gray-50 dark:bg-gray-900/40">
            <span className="text-[11px] font-semibold text-gray-500 dark:text-gray-400">العمليات السابقة</span>
            {history.length > 0 && (
              <button onClick={clearHistory} title="مسح الذاكرة" className="text-gray-400 hover:text-red-500 p-0.5 rounded">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <div className="max-h-32 overflow-y-auto">
            {history.length === 0 ? (
              <div className="px-2 py-3 text-center text-[11px] text-gray-400">لا عمليات محفوظة</div>
            ) : (
              history.map((h, i) => (
                <button
                  key={i}
                  onClick={() => { setExpression(h.result); setShowHistory(false); }}
                  title="استعادة الناتج"
                  className="w-full flex justify-between items-baseline gap-2 px-2 py-1 text-right hover:bg-emerald-50 dark:hover:bg-emerald-950/20 border-b border-gray-50 dark:border-gray-800 last:border-0"
                >
                  <span className="font-mono text-[11px] text-gray-400 truncate">{h.expr}</span>
                  <span className="font-mono text-xs font-bold text-emerald-600 dark:text-emerald-400">= {h.result}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* Screen */}
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-150 dark:border-gray-700 rounded-xl p-2.5 mb-3 text-right font-mono text-lg font-bold text-gray-800 dark:text-white truncate min-h-[44px]">
        {expression || "0"}
      </div>

      {/* Keyboard Grid */}
      <div className="grid grid-cols-4 gap-1.5 text-sm font-semibold">
        <button onClick={handleClear} className="p-2.5 bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 rounded-lg hover:opacity-80">
          C
        </button>
        <button onClick={handleBackspace} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-lg hover:opacity-80 flex items-center justify-center">
          <Delete className="w-4 h-4" />
        </button>
        <button onClick={() => handleKeyPress("/")} className="p-2.5 bg-blue-50 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 rounded-lg hover:opacity-80">
          /
        </button>
        <button onClick={() => handleKeyPress("*")} className="p-2.5 bg-blue-50 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 rounded-lg hover:opacity-80">
          *
        </button>

        <button onClick={() => handleKeyPress("7")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          7
        </button>
        <button onClick={() => handleKeyPress("8")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          8
        </button>
        <button onClick={() => handleKeyPress("9")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          9
        </button>
        <button onClick={() => handleKeyPress("-")} className="p-2.5 bg-blue-50 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 rounded-lg hover:opacity-80">
          -
        </button>

        <button onClick={() => handleKeyPress("4")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          4
        </button>
        <button onClick={() => handleKeyPress("5")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          5
        </button>
        <button onClick={() => handleKeyPress("6")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          6
        </button>
        <button onClick={() => handleKeyPress("+")} className="p-2.5 bg-blue-50 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 rounded-lg hover:opacity-80">
          +
        </button>

        <button onClick={() => handleKeyPress("1")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          1
        </button>
        <button onClick={() => handleKeyPress("2")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          2
        </button>
        <button onClick={() => handleKeyPress("3")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          3
        </button>
        <button onClick={handleEvaluate} className="row-span-2 p-2.5 bg-emerald-500 text-white rounded-lg hover:opacity-85 flex items-center justify-center font-bold">
          =
        </button>

        <button onClick={() => handleKeyPress("0")} className="col-span-2 p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          0
        </button>
        <button onClick={() => handleKeyPress(".")} className="p-2.5 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:opacity-80">
          .
        </button>
      </div>
    </div>
  );
};
