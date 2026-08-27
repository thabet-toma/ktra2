import React, { useEffect, useMemo, useState } from "react";
import { Plus, Check, X } from "lucide-react";

/**
 * منتقي قيمة نصية «اختر من الموجود أو أضف جديد» (DRY) — يخدم البراند والمجموعة
 * (المنتج الفرعي). القيمة نصّ على المنتج لا جدول، فـ«الإضافة» = كتابة اسم جديد يصبح
 * متاحاً للمنتجات اللاحقة بعد الحفظ. مرآة لنمط CategoryPicker.
 */
type Props = {
  value: string;
  onChange: (v: string) => void;
  /** يجلب القيم الموجودة (مميّزة) — مثل inventoryApi.getBrands / getGroups. */
  fetchOptions: () => Promise<string[]>;
  emptyLabel: string;
  addPlaceholder: string;
  addTitle: string;
  className?: string;
  disabled?: boolean;
};

export const ValuePicker: React.FC<Props> = ({
  value, onChange, fetchOptions, emptyLabel, addPlaceholder, addTitle, className, disabled,
}) => {
  const [items, setItems] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    fetchOptions().then(setItems).catch(() => setItems([]));
  }, [fetchOptions]);

  // أبقِ القيمة الحالية ضمن الخيارات حتى لو لم تُحفظ بعد (قيمة جديدة مكتوبة).
  const options = useMemo(() => {
    const set = new Set<string>(items);
    if (value) set.add(value);
    return Array.from(set).sort((a, b) => a.localeCompare(b, "ar"));
  }, [items, value]);

  if (adding) {
    return (
      <div style={{ display: "flex", gap: 4, width: "100%" }}>
        <input
          className={className || "ktra-input"}
          style={{ flex: 1 }}
          autoFocus
          value={value}
          placeholder={addPlaceholder}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); setAdding(false); }
            if (e.key === "Escape") setAdding(false);
          }}
        />
        <button type="button" className="ktra-toolbtn" title="تم" onClick={() => setAdding(false)}>
          <Check className="h-4 w-4" />
        </button>
        <button type="button" className="ktra-toolbtn" title="إلغاء" onClick={() => { onChange(""); setAdding(false); }}>
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 4, width: "100%" }}>
      <select
        className={className || "ktra-input"}
        style={{ flex: 1 }}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{emptyLabel}</option>
        {options.map((b) => (
          <option key={b} value={b}>{b}</option>
        ))}
      </select>
      <button
        type="button"
        className="ktra-toolbtn"
        disabled={disabled}
        title={addTitle}
        onClick={() => { onChange(""); setAdding(true); }}
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
};
