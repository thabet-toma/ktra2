import React, { useEffect, useState } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import { Plus, X, FolderTree } from "lucide-react";
import { InvoiceCategoryTree } from "../procurement/invoices/InvoiceCategoryTree";
import { categoryPathLabel, sortCategoryRows } from "../../utils/categoryTree";

type Category = {
  id: number;
  name: string;
  parent: number | null;
  // backend also returns other fields if any
};

type Props = {
  value: number | null;
  onChange: (id: number | null, name?: string) => void;
  className?: string;
  disabled?: boolean;
};

export const CategoryPicker: React.FC<Props> = ({ value, onChange, className, disabled }) => {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [showManage, setShowManage] = useState(false);
  // T-ITEMS M2: إنشاء تصنيفٍ فرعي في مكانه — كان لا بدّ من فتح نافذة الإدارة
  // والعودة، وهو ما يقطع الإدخال. يُنشأ تحت المختار مباشرةً، أو جذراً إن لم يُختر.
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [addErr, setAddErr] = useState<string | null>(null);
  const [addBusy, setAddBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await inventoryApi.getCategories();
      setCategories(data);
    } catch (e) {
      console.error("Failed to load categories", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleAdd = async () => {
    const name = newName.trim();
    if (!name) { setAddErr("اسم التصنيف مطلوب."); return; }
    setAddBusy(true); setAddErr(null);
    try {
      const created = await inventoryApi.createCategory({
        name, parent: value ?? null,
      }) as Category;
      await load();
      onChange(created.id, created.name);
      setNewName("");
      setAdding(false);
    } catch (e: unknown) {
      // خطأ الخادم يُعرَض لا يُبتلع — وإلا بدا الزرّ معطّلاً بلا سبب.
      setAddErr(e instanceof Error ? e.message : "تعذّر إنشاء التصنيف");
    } finally {
      setAddBusy(false);
    }
  };

  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", gap: "4px", width: "100%" }}>
        <select
          className={className || "aseel-input"}
          value={value ?? ""}
          onChange={(e) => {
            const val = e.target.value;
            if (!val) {
              onChange(null);
              return;
            }
            const id = Number(val);
            const cat = categories.find((c) => c.id === id);
            onChange(id, cat?.name);
          }}
          disabled={disabled || loading}
          style={{ flex: 1 }}
        >
          <option value="">-- بدون تصنيف --</option>
          {/* الإزاحة بمسافات NBSP لا عادية: المتصفح يطوي المسافات العادية داخل
              الخيار فيستوي العمق ويضيع شكل الشجرة. */}
          {sortCategoryRows(categories).map(({ category, depth }) => (
            <option key={category.id} value={category.id}>
              {" ".repeat(depth * 4)}{depth > 0 ? "└─ " : ""}{category.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="aseel-toolbtn"
          onClick={() => { setAdding((v) => !v); setAddErr(null); }}
          disabled={disabled}
          title={value ? "تصنيف فرعي تحت المختار" : "تصنيف جذري جديد"}
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="aseel-toolbtn"
          onClick={() => setShowManage(true)}
          disabled={disabled}
          title="إدارة التصنيفات (شجرة)"
        >
          <FolderTree className="h-4 w-4" />
        </button>
      </div>

      {/* المسار الكامل للمختار — «أين يقع هذا التصنيف» يُقرأ بلا فتح الشجرة. */}
      {value != null && (
        <div style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)", marginTop: 2 }}>
          {categoryPathLabel(categories, value)}
        </div>
      )}

      {adding && (
        <div style={{ display: "flex", gap: 4, marginTop: 4, alignItems: "center" }}>
          <input
            className="aseel-input"
            style={{ flex: 1 }}
            autoFocus
            value={newName}
            placeholder={value ? "اسم التصنيف الفرعي" : "اسم التصنيف الجذري"}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); void handleAdd(); }
              if (e.key === "Escape") { e.preventDefault(); setAdding(false); setNewName(""); }
            }}
          />
          <button type="button" className="aseel-toolbtn" disabled={addBusy}
            onClick={() => void handleAdd()}>إضافة</button>
          <button type="button" className="aseel-toolbtn"
            onClick={() => { setAdding(false); setNewName(""); setAddErr(null); }}>
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {addErr && (
        <div style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-danger, #c0392b)", marginTop: 2 }}>
          {addErr}
        </div>
      )}

      {showManage && (
        <CategoryManageModal
          onClose={() => {
            setShowManage(false);
            load();
          }}
        />
      )}
    </div>
  );
};

const CategoryManageModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" dir="rtl">
      <div className="bg-[var(--color-surface)] rounded shadow-xl w-full max-w-md flex flex-col" style={{ maxHeight: "80vh", height: "600px" }}>
        <div className="flex items-center justify-between p-3 border-b bg-[var(--color-surface-2)]">
          <h3 className="font-bold text-[var(--aseel-ink)]">إدارة التصنيفات (شجرة)</h3>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)]"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-0 overflow-hidden flex-1 flex flex-col">
          <InvoiceCategoryTree items={[]} onPickItem={()=>{}} disabled={false} manageMode />
        </div>
      </div>
    </div>
  );
};
