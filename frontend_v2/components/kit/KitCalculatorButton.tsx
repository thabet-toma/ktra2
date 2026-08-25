import React, { useState } from "react";
import { Calculator } from "lucide-react";
import { KitCalculatorPopover } from "./KitCalculatorPopover";

/**
 * task16 E15: أيقونة حاسبة في الشريط العلوي — تفتح الحاسبة عند الطلب فقط
 * (بدلاً من الفتح التلقائي عند النقر على الحقول). حاسبة مستقلة لا تملأ خلية.
 */
export const KitCalculatorButton: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const toggle = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (open) {
      setOpen(false);
      return;
    }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    // افتح الحاسبة أسفل الأيقونة، مع مراعاة حدود النافذة
    setPos({ x: Math.max(8, rect.right - 256), y: rect.bottom + 4 });
    setOpen(true);
  };

  return (
    <>
      <button
        type="button"
        onClick={toggle}
        title="حاسبة"
        aria-label="فتح الحاسبة"
        className="p-1.5 rounded text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
      >
        <Calculator className="w-4 h-4" />
      </button>
      {open && (
        <KitCalculatorPopover
          standalone
          initialValue=""
          x={pos.x}
          y={pos.y}
          onConfirm={() => {}}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
};
