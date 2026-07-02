import React, { useEffect, useState } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import { Plus, X } from "lucide-react";
import { InvoiceCategoryTree } from "../procurement/invoices/InvoiceCategoryTree";

type Category = {
  id: number;
  name: string;
  parent: number | null;
  // backend also returns other fields if any
};

const sortCategories = (cats: Category[]) => {
  const map = new Map<number, Category[]>();
  const roots: Category[] = [];
  cats.forEach((c) => {
    if (c.parent) {
      if (!map.has(c.parent)) map.set(c.parent, []);
      map.get(c.parent)!.push(c);
    } else {
      roots.push(c);
    }
  });

  const result: (Category & { depth: number })[] = [];
  const traverse = (list: Category[], depth: number) => {
    const sorted = [...list].sort((a, b) => a.name.localeCompare(b.name));
    for (const c of sorted) {
      result.push({ ...c, depth });
      if (map.has(c.id)) {
        traverse(map.get(c.id)!, depth + 1);
      }
    }
  };
  traverse(roots, 0);
  return result;
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

  return (
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
        {sortCategories(categories).map((c) => (
          <option key={c.id} value={c.id}>
            {"\u00A0".repeat(c.depth * 4)}{c.depth > 0 ? "└─ " : ""}{c.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="aseel-toolbtn"
        onClick={() => setShowManage(true)}
        disabled={disabled}
        title="إدارة التصنيفات"
      >
        <Plus className="h-4 w-4" />
      </button>

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
      <div className="bg-white rounded shadow-xl w-full max-w-md flex flex-col" style={{ maxHeight: "80vh", height: "600px" }}>
        <div className="flex items-center justify-between p-3 border-b bg-gray-50">
          <h3 className="font-bold text-[var(--aseel-ink)]">إدارة التصنيفات (شجرة)</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-0 overflow-hidden flex-1 flex flex-col">
          <InvoiceCategoryTree items={[]} onPickItem={()=>{}} disabled={false} manageMode />
        </div>
      </div>
    </div>
  );
};
