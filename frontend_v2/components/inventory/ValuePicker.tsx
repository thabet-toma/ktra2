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
  /** القيمة قبل الدخول في الإضافة — يعود إليها «إلغاء»، ولا يمحوها حقلٌ فارغ. */
  const [previous, setPrevious] = useState(value);
  /** ما في حقل الإضافة الآن — يُكتب على القيمة الحيّة مع كل حرف. */
  const [draft, setDraft] = useState("");

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
    /**
     * الكتابة حيّة: كلُّ حرفٍ يُكتب على القيمة فوراً، فلا يضيع ما كُتب إن ضغط
     * المستخدم «حفظ»/«تخزين» في النموذج بلا «✓». وحقلٌ فارغٌ يعيد `previous`
     * فلا يمحو قيمةً قائمة.
     */
    const finishAdding = () => {
      setDraft("");
      setAdding(false);
    };
    /** «إلغاء» يردّ `previous` إن تغيّرت القيمة بالكتابة، ثم يخرج. */
    const cancelAdding = () => {
      if (value !== previous) onChange(previous);
      setDraft("");
      setAdding(false);
    };
    return (
      <div style={{ display: "flex", gap: 4, width: "100%" }}>
        <input
          className={className || "ktra-input"}
          style={{ flex: 1 }}
          autoFocus
          value={draft}
          placeholder={addPlaceholder}
          onChange={(e) => {
            const text = e.target.value;
            setDraft(text);
            onChange(text.trim() ? text : previous);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); finishAdding(); }
            if (e.key === "Escape") cancelAdding();
          }}
        />
        <button type="button" className="ktra-toolbtn" title="تم" onClick={finishAdding}>
          <Check className="h-4 w-4" />
        </button>
        <button type="button" className="ktra-toolbtn" title="إلغاء" onClick={cancelAdding}>
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
        onClick={() => { setPrevious(value); setDraft(""); setAdding(true); }}
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
};
