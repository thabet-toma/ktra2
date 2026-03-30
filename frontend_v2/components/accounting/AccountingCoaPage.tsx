import React, { useEffect, useState, useMemo, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { AccountingAccount } from "../../types/accounting";
import {
  ChevronDown,
  ChevronLeft,
  FolderTree,
  Plus,
  Pencil,
  Trash2,
  X,
  Save,
} from "lucide-react";

const ACCOUNT_TYPES = [
  { v: "Asset", l: "أصول" },
  { v: "Liability", l: "خصوم" },
  { v: "Equity", l: "حقوق ملكية" },
  { v: "Revenue", l: "إيرادات" },
  { v: "Expense", l: "مصروفات" },
];

function buildTree(accounts: AccountingAccount[]) {
  const byParent = new Map<number | null, AccountingAccount[]>();
  for (const a of accounts) {
    const p = a.parent ?? null;
    if (!byParent.has(p)) byParent.set(p, []);
    byParent.get(p)!.push(a);
  }
  for (const [, list] of byParent) {
    list.sort((x, y) => (x.code || "").localeCompare(y.code || ""));
  }
  return byParent;
}

interface RowProps {
  account: AccountingAccount;
  byParent: Map<number | null, AccountingAccount[]>;
  depth: number;
  open: Record<number, boolean>;
  toggle: (id: number) => void;
  onAddChild: (parent: AccountingAccount) => void;
  onEdit: (a: AccountingAccount) => void;
  onDelete: (id: number) => void;
  query: string;
}

const CoaRow: React.FC<RowProps> = ({
  account,
  byParent,
  depth,
  open,
  toggle,
  onAddChild,
  onEdit,
  onDelete,
  query,
}) => {
  const children = byParent.get(account.id) ?? [];
  const hasChildren = children.length > 0;
  const isOpen = open[account.id] === true;

  const q = query.trim().toLowerCase();
  const isMatch =
    !!q &&
    ((account.code ?? "").toLowerCase().includes(q) ||
      (account.name ?? "").toLowerCase().includes(q));

  const indentPx = depth * 16;
  const rightOffset = Math.max(0, (depth - 1) * 16);
  const linkWidth = Math.max(12, (depth - 1) * 16);

  return (
    <div className="select-none group">
      <div
        className={[
          "flex items-center gap-2 py-2 px-3 rounded-lg",
          "hover:bg-gray-100 dark:hover:bg-gray-800/80",
          "border border-transparent hover:border-gray-200 dark:hover:border-gray-700",
          isMatch
            ? "bg-emerald-50/70 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-700"
            : "",
        ].join(" ")}
      >
        {/* Spacer + Tree connector */}
        <div
          className="relative flex-shrink-0"
          style={{ width: indentPx }}
          aria-hidden="true"
        >
          {depth > 0 && (
            <>
              <div
                className="absolute inset-y-0 w-px bg-gray-200 dark:bg-gray-700"
                style={{ right: rightOffset }}
              />
              <div
                className="absolute top-1/2 h-px bg-gray-200 dark:bg-gray-700 -translate-y-1/2"
                style={{ right: rightOffset, width: linkWidth }}
              />
            </>
          )}
        </div>

        {hasChildren ? (
          <button
            type="button"
            onClick={() => toggle(account.id)}
            className="p-1 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
          >
            {isOpen ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        ) : (
          <span className="w-6 h-6" />
        )}
        <span className="font-mono text-sm text-blue-600 dark:text-blue-400 w-20">
          {account.code || "—"}
        </span>
        <span className="flex-1 text-sm font-medium text-gray-900 dark:text-gray-100">
          {account.name}
        </span>
        <span className="text-xs text-gray-500 hidden md:inline">
          {ACCOUNT_TYPES.find((t) => t.v === account.account_type)?.l ||
            account.account_type}
        </span>

        <span
          className={[
            "w-2.5 h-2.5 rounded-full border inline-flex flex-shrink-0",
            account.is_active
              ? "bg-green-500/15 border-green-400 dark:bg-green-900/20 dark:border-green-500"
              : "bg-gray-500/15 border-gray-400 dark:bg-gray-900/20 dark:border-gray-500",
          ].join(" ")}
          title={account.is_active ? "حساب نشط" : "حساب غير نشط"}
          aria-label={account.is_active ? "حساب نشط" : "حساب غير نشط"}
        />

        <button
          type="button"
          onClick={() => onAddChild(account)}
          className="p-1.5 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto focus:pointer-events-auto"
          title="حساب فرعي"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => onEdit(account)}
          className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto focus:pointer-events-auto"
        >
          <Pencil className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => onDelete(account.id)}
          className="p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto focus:pointer-events-auto"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
      {hasChildren && isOpen && (
        <div>
          {children.map((c) => (
            <CoaRow
              key={c.id}
              account={c}
              byParent={byParent}
              depth={depth + 1}
              open={open}
              toggle={toggle}
              onAddChild={onAddChild}
              onEdit={onEdit}
              onDelete={onDelete}
              query={query}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const AccountingCoaPage: React.FC = () => {
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [searchTerm, setSearchTerm] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [dialog, setDialog] = useState<{
    mode: "create" | "edit";
    parentId: number | null;
    account?: AccountingAccount;
  } | null>(null);
  const [form, setForm] = useState({
    name: "",
    code: "",
    account_type: "Asset",
    parent: null as number | null,
    is_active: true,
  });

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = (await accountingApi.getAccounts()) as AccountingAccount[];
      setAccounts(data);
      const tree = buildTree(data);
      const o: Record<number, boolean> = {};
      // Default: open only roots, collapse everything else.
      for (const a of data) {
        const children = tree.get(a.id) ?? [];
        if (children.length > 0) o[a.id] = false;
      }
      const rootList = tree.get(null) ?? [];
      for (const r of rootList) o[r.id] = true;
      setOpen(o);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fullTree = useMemo(() => buildTree(accounts), [accounts]);

  const visibleAccounts = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();

    if (!q && !activeOnly) return accounts;

    // If there is no search, just filter by active flag.
    if (!q) {
      return activeOnly ? accounts.filter((a) => a.is_active) : accounts;
    }

    const parentById = new Map<number, number | null>();
    for (const a of accounts) parentById.set(a.id, a.parent ?? null);

    const visibleIds = new Set<number>();

    for (const a of accounts) {
      const code = (a.code ?? "").toLowerCase();
      const name = (a.name ?? "").toLowerCase();

      if (code.includes(q) || name.includes(q)) {
        visibleIds.add(a.id);
        // add ancestors to keep hierarchy
        let cur = parentById.get(a.id);
        while (cur != null) {
          visibleIds.add(cur);
          cur = parentById.get(cur) ?? null;
        }
      }
    }

    let result = accounts.filter((a) => visibleIds.has(a.id));
    if (activeOnly) result = result.filter((a) => a.is_active);
    return result;
  }, [accounts, searchTerm, activeOnly]);

  const byParent = useMemo(() => buildTree(visibleAccounts), [visibleAccounts]);
  const roots = byParent.get(null) ?? [];

  const toggle = (id: number) =>
    setOpen((p) => ({ ...p, [id]: !(p[id] ?? false) }));

  const expandAll = () => {
    const o: Record<number, boolean> = {};
    for (const a of accounts) {
      const children = fullTree.get(a.id) ?? [];
      if (children.length > 0) o[a.id] = true;
    }
    setOpen(o);
  };

  const collapseAll = () => {
    const o: Record<number, boolean> = {};
    for (const a of accounts) {
      const children = fullTree.get(a.id) ?? [];
      if (children.length > 0) o[a.id] = false;
    }
    setOpen(o);
  };

  const openCreate = (parent: AccountingAccount | null) => {
    setForm({
      name: "",
      code: "",
      account_type: parent?.account_type || "Asset",
      parent: parent?.id ?? null,
      is_active: true,
    });
    setDialog({ mode: "create", parentId: parent?.id ?? null });
  };

  const openEdit = (a: AccountingAccount) => {
    setForm({
      name: a.name || "",
      code: a.code || "",
      account_type: a.account_type || "Asset",
      parent: a.parent,
      is_active: a.is_active,
    });
    setDialog({ mode: "edit", parentId: a.parent, account: a });
  };

  const saveDialog = async () => {
    if (!form.name.trim() || !form.code.trim()) {
      setErr("الاسم والكود مطلوبان");
      return;
    }
    setErr(null);
    try {
      const body = {
        name: form.name.trim(),
        code: form.code.trim(),
        account_type: form.account_type,
        parent: form.parent,
        is_active: form.is_active,
      };
      if (dialog?.mode === "edit" && dialog.account) {
        await accountingApi.updateAccount(dialog.account.id, body);
      } else {
        await accountingApi.createAccount(body);
      }
      setDialog(null);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    }
  };

  const remove = async (id: number) => {
    if (!confirm("حذف هذا الحساب؟")) return;
    try {
      await accountingApi.deleteAccount(id);
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-gradient-to-l from-slate-800 to-slate-900 text-white rounded-xl shadow">
        <div className="flex items-center gap-3">
          <FolderTree className="w-8 h-8 text-emerald-400" />
          <div>
            <h1 className="text-lg font-bold">شجرة الحسابات</h1>
            <p className="text-xs text-slate-400">
              دليل الحسابات المرتبط بقاعدة البيانات المحاسبية
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => openCreate(null)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          حساب رئيسي
        </button>
      </div>

      {/* Toolbar: search / expand / collapse */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="flex-1 min-w-[220px] border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 dark:bg-gray-900"
          placeholder="بحث بالكود أو الاسم..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />

        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200 select-none">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          حسابات نشطة فقط
        </label>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={expandAll}
            className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            توسيع الكل
          </button>
          <button
            type="button"
            onClick={collapseAll}
            className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            طيّ الكل
          </button>
        </div>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-gray-500">جاري التحميل…</div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-2 shadow-sm">
          {roots.length === 0 ? (
            <p className="p-8 text-center text-gray-500">
              لا توجد حسابات. أضف حساباً رئيسياً.
            </p>
          ) : (
            <div className="max-h-[70vh] overflow-auto pr-1">
              {roots.map((r) => (
                <CoaRow
                  key={r.id}
                  account={r}
                  byParent={byParent}
                  depth={0}
                  open={open}
                  toggle={toggle}
                  onAddChild={(p) => openCreate(p)}
                  onEdit={openEdit}
                  onDelete={remove}
                  query={searchTerm}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {dialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-md w-full p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                {dialog.mode === "edit" ? "تعديل حساب" : "حساب جديد"}
              </h3>
              <button
                type="button"
                onClick={() => setDialog(null)}
                className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">الكود</label>
                <input
                  className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                  value={form.code}
                  onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">الاسم</label>
                <input
                  className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">النوع</label>
                <select
                  className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                  value={form.account_type}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, account_type: e.target.value }))
                  }
                >
                  {ACCOUNT_TYPES.map((t) => (
                    <option key={t.v} value={t.v}>
                      {t.l}
                    </option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, is_active: e.target.checked }))
                  }
                />
                نشط
              </label>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                type="button"
                onClick={() => setDialog(null)}
                className="px-4 py-2 rounded-lg border dark:border-gray-600"
              >
                إلغاء
              </button>
              <button
                type="button"
                onClick={saveDialog}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white"
              >
                <Save className="w-4 h-4" />
                حفظ
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
