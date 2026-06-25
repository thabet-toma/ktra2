import React, { useEffect, useState } from "react";
import { useConfirm } from "../../contexts/ConfirmContext";
import { inventoryApi } from "../../services/inventoryApi";
import { Plus, Edit2, Trash2, X, Check, Loader2 } from "lucide-react";

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
        {categories.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
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
          categories={categories}
          onClose={() => {
            setShowManage(false);
            load();
          }}
        />
      )}
    </div>
  );
};

const CategoryManageModal: React.FC<{ categories: Category[]; onClose: () => void }> = ({ categories, onClose }) => {
  const confirm = useConfirm();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [list, setList] = useState<Category[]>(categories);

  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editParent, setEditParent] = useState<number | null>(null);

  const startNew = () => {
    setEditId(0);
    setEditName("");
    setEditParent(null);
    setErr(null);
  };

  const startEdit = (c: Category) => {
    setEditId(c.id);
    setEditName(c.name);
    setEditParent(c.parent);
    setErr(null);
  };

  const handleSave = async () => {
    if (!editName.trim()) {
      setErr("اسم التصنيف مطلوب");
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      const payload = { name: editName, parent: editParent || null };
      if (editId === 0) {
        const created = await inventoryApi.createCategory(payload) as Category;
        setList([...list, created]);
      } else if (editId) {
        const updated = await inventoryApi.updateCategory(editId, payload) as Category;
        setList(list.map((c) => (c.id === editId ? updated : c)));
      }
      setEditId(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!(await confirm({ title: "حذف التصنيف", message: "هل أنت متأكد من حذف هذا التصنيف؟" }))) return;
    setLoading(true);
    setErr(null);
    try {
      await inventoryApi.deleteCategory(id);
      setList(list.filter((c) => c.id !== id));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف. قد يكون مستخدماً.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" dir="rtl">
      <div className="bg-white rounded shadow-xl w-full max-w-md flex flex-col" style={{ maxHeight: "80vh" }}>
        <div className="flex items-center justify-between p-3 border-b bg-gray-50">
          <h3 className="font-bold text-[var(--aseel-ink)]">إدارة التصنيفات</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-4 overflow-y-auto flex-1">
          {err && <div className="aseel-banner aseel-banner--err mb-4">{err}</div>}
          
          <table className="aseel-grid w-full mb-4">
            <thead>
              <tr>
                <th>الاسم</th>
                <th style={{ width: "80px" }}></th>
              </tr>
            </thead>
            <tbody>
              {list.length === 0 && (
                <tr>
                  <td colSpan={2} className="text-center text-gray-500 py-4">لا توجد تصنيفات</td>
                </tr>
              )}
              {list.map((c) => (
                <tr key={c.id}>
                  <td>
                    {editId === c.id ? (
                      <input className="aseel-input" value={editName} onChange={(e) => setEditName(e.target.value)} autoFocus />
                    ) : (
                      c.name
                    )}
                  </td>
                  <td className="text-left whitespace-nowrap">
                    {editId === c.id ? (
                      <div className="flex gap-1 justify-end">
                        <button onClick={handleSave} disabled={loading} className="aseel-iconbtn text-green-600"><Check className="h-4 w-4" /></button>
                        <button onClick={() => setEditId(null)} disabled={loading} className="aseel-iconbtn text-gray-500"><X className="h-4 w-4" /></button>
                      </div>
                    ) : (
                      <div className="flex gap-1 justify-end">
                        <button onClick={() => startEdit(c)} disabled={loading || editId !== null} className="aseel-iconbtn text-blue-600"><Edit2 className="h-4 w-4" /></button>
                        <button onClick={() => handleDelete(c.id)} disabled={loading || editId !== null} className="aseel-iconbtn text-red-600"><Trash2 className="h-4 w-4" /></button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {editId === 0 && (
                <tr>
                  <td>
                    <input className="aseel-input" value={editName} onChange={(e) => setEditName(e.target.value)} autoFocus placeholder="اسم التصنيف..." />
                  </td>
                  <td>
                    <div className="flex gap-1 justify-end">
                      <button onClick={handleSave} disabled={loading} className="aseel-iconbtn text-green-600"><Check className="h-4 w-4" /></button>
                      <button onClick={() => setEditId(null)} disabled={loading} className="aseel-iconbtn text-gray-500"><X className="h-4 w-4" /></button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          {editId === null && (
            <button className="aseel-toolbtn w-full justify-center" onClick={startNew}>
              <Plus className="h-4 w-4" /> إضافة تصنيف جديد
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
