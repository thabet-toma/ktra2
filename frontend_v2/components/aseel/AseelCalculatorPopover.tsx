import React, { useState, useEffect, useRef } from "react";
import { X, Delete, Check } from "lucide-react";

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
      // Safe evaluation of basic math expression
      // Only allow digits, operators +, -, *, /, decimal point, and spaces
      if (!/^[0-9+\-*/. ]*$/.test(expression)) {
        throw new Error("Invalid expression");
      }
      // eslint-disable-next-line no-eval
      const result = eval(expression);
      if (typeof result === "number" && !isNaN(result) && isFinite(result)) {
        const rounded = Number(result.toFixed(4));
        if (standalone) {
          // حاسبة مستقلة: اعرض الناتج وأبقِ النافذة لمواصلة الحساب
          setExpression(String(rounded));
        } else {
          onConfirm(rounded);
        }
      } else {
        alert("تعبير غير صالح");
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
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">حاسبة الأصيل</span>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-white p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

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
