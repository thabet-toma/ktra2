import React, { useEffect, useState } from "react";
import { useConfirm } from "../../contexts/ConfirmContext";
import { inventoryApi } from "../../services/inventoryApi";
import { Plus, Edit2, Trash2, X, Check, RefreshCw } from "lucide-react";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";

type Category = {
  id: number;
  name: string;
  parent: number | null;
};

export const CategoriesManagement: React.FC = () => {
  const confirm = useConfirm();
  const [list, setList] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editParent, setEditParent] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await inventoryApi.getCategories();
      setList(data);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في جلب التصنيفات");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

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

  // خرائط الشجرة: الاسم بالمعرّف + العمق (لإزاحة الأبناء) + ترتيب DFS (الابن تحت أبيه).
  const nameById = new Map(list.map((c) => [c.id, c.name]));
  const childrenOf = new Map<number | null, Category[]>();
  for (const c of list) {
    const p = c.parent ?? null;
    if (!childrenOf.has(p)) childrenOf.set(p, []);
    childrenOf.get(p)!.push(c);
  }
  const depthOf = (c: Category): number => {
    let d = 0, cur: number | null = c.parent ?? null, guard = 0;
    while (cur != null && guard++ < 50) { d++; cur = nameById.has(cur) ? (list.find((x) => x.id === cur)?.parent ?? null) : null; }
    return d;
  };
  // ترتيب الشجرة (أب ثم أبناؤه ثم أحفاده) عبر DFS من الجذور.
  const orderedTree: Category[] = [];
  const walk = (parent: number | null) => {
    for (const c of (childrenOf.get(parent) || [])) { orderedTree.push(c); walk(c.id); }
  };
  walk(null);
  // التصنيفات اليتيمة (أبٌ غير موجود) لا تظهر تحت أحد — ألحِقها كي لا تختفي.
  for (const c of list) if (!orderedTree.includes(c)) orderedTree.push(c);

  // كل أحفاد تصنيف (لمنع اختياره أباً لنفسه/أحد أبنائه — يكسر الشجرة).
  const descendantsOf = (id: number): Set<number> => {
    const out = new Set<number>();
    const stack = [...(childrenOf.get(id) || [])];
    while (stack.length) { const c = stack.pop()!; out.add(c.id); stack.push(...(childrenOf.get(c.id) || [])); }
    return out;
  };
  const parentOptions = (selfId: number): Category[] => {
    const banned = selfId ? descendantsOf(selfId) : new Set<number>();
    return orderedTree.filter((c) => c.id !== selfId && !banned.has(c.id));
  };

  const displayList = [...orderedTree];
  if (editId === 0) {
    displayList.unshift({ id: 0, name: editName, parent: editParent });
  }

  // محرّر الأب المشترك (للجديد والتعديل) — هذا ما كان ناقصاً فتعذّر إنشاء أب/ابن/حفيد.
  const parentSelect = (selfId: number) => (
    <select
      className="aseel-input w-full"
      value={editParent ?? ""}
      onChange={(e) => setEditParent(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">— تصنيف رئيسي (بدون أب) —</option>
      {parentOptions(selfId).map((c) => (
        <option key={c.id} value={c.id}>{"— ".repeat(depthOf(c))}{c.name}</option>
      ))}
    </select>
  );

  const columns: DenseColumn<Category>[] = [
    {
      key: "id",
      header: "#",
      width: "60px",
      render: (c) => (c.id === 0 ? <span className="text-gray-400">جديد</span> : c.id)
    },
    {
      key: "name",
      header: "اسم التصنيف",
      render: (c) => {
        if (editId === c.id) {
          return (
            <input
              className="aseel-input w-full"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave();
                if (e.key === "Escape") setEditId(null);
              }}
              autoFocus
              placeholder="اسم التصنيف..."
            />
          );
        }
        // إزاحة بصرية حسب العمق لإظهار الشجرة (أب ⇠ ابن ⇠ حفيد).
        return (
          <span style={{ paddingInlineStart: `${depthOf(c) * 18}px` }}>
            {depthOf(c) > 0 && <span style={{ color: "var(--aseel-ink-soft)" }}>└ </span>}
            {c.name}
          </span>
        );
      }
    },
    {
      key: "parent",
      header: "الصنف الأب",
      width: "220px",
      render: (c) => {
        if (editId === c.id) return parentSelect(c.id);
        return c.parent != null
          ? (nameById.get(c.parent) || `#${c.parent}`)
          : <span className="text-gray-400">— رئيسي —</span>;
      }
    },
    {
      key: "actions",
      header: "",
      width: "80px",
      align: "center",
      render: (c) => {
        if (editId === c.id) {
          return (
            <div className="flex gap-1 justify-center">
              <button onClick={handleSave} disabled={loading} className="aseel-iconbtn text-green-600"><Check className="h-4 w-4" /></button>
              <button onClick={() => setEditId(null)} disabled={loading} className="aseel-iconbtn text-gray-500"><X className="h-4 w-4" /></button>
            </div>
          );
        }
        return (
          <div className="flex gap-1 justify-center">
            <button onClick={(e) => { e.stopPropagation(); startEdit(c); }} disabled={loading || editId !== null} className="aseel-iconbtn text-blue-600"><Edit2 className="h-4 w-4" /></button>
            <button onClick={(e) => { e.stopPropagation(); handleDelete(c.id); }} disabled={loading || editId !== null} className="aseel-iconbtn text-red-600"><Trash2 className="h-4 w-4" /></button>
          </div>
        );
      }
    }
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8 }} data-skin="aseel">
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          إدارة التصنيفات
        </strong>
        <span className="aseel-status-item">الإجمالي: <b>{list.length}</b></span>
        
        <div style={{ flex: 1 }} />
        
        <button className="aseel-toolbtn" onClick={load} title="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <button className="aseel-toolbtn" onClick={startNew} disabled={editId !== null} title="إضافة تصنيف">
          <Plus className="h-4 w-4" /> إضافة
        </button>
      </div>

      {err && <div className="aseel-banner aseel-banner--err">{err}</div>}

      <AseelDenseTable<Category>
        columns={columns}
        rows={displayList}
        getRowKey={(c) => c.id}
        loading={loading}
        emptyHint="لا توجد تصنيفات"
        onRowDoubleClick={(c) => { if (editId === null) startEdit(c); }}
      />
    </div>
  );
};
