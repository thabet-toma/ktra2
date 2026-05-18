import React, { useEffect, useState, useMemo, useCallback, useRef } from "react";
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
  MoreHorizontal,
  BookOpen,
  ExternalLink,
  Factory,
} from "lucide-react";

const TYPE_LETTER: Record<string, string> = {
  Asset: "أ",
  Liability: "خ",
  Equity: "ح",
  Revenue: "إ",
  Expense: "م",
};

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
  onOpenGeneralLedger?: (accountId: number) => void;
  onOpenSupplier?: (partnerId: number) => void;
  onOpenRowMenu: (account: AccountingAccount, anchor: HTMLElement | null) => void;
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
  onOpenGeneralLedger,
  onOpenSupplier,
  onOpenRowMenu,
}) => {
  const children = byParent.get(account.id) ?? [];
  const hasChildren = children.length > 0;
  const isOpen = open[account.id] === true;
  const lp = account.linked_partner;
  /** الاسم المستعار (عربي) من Partner.name؛ لا نعرض اسم حساب GL الإنجليزي كعنوان رئيسي عند وجود مورد */
  const aliasName = (lp?.trade_name || "").trim();
  const displayName = lp
    ? aliasName || "—"
    : (account.name || "").trim() || "—";
  const subLegal =
    lp?.legal_name?.trim() &&
    lp.legal_name.trim().toLowerCase() !== aliasName.toLowerCase()
      ? lp.legal_name.trim()
      : null;

  const q = query.trim().toLowerCase();
  const isMatch =
    !!q &&
    ((account.code ?? "").toLowerCase().includes(q) ||
      (account.name ?? "").toLowerCase().includes(q) ||
      (lp?.trade_name ?? "").toLowerCase().includes(q) ||
      (lp?.legal_name ?? "").toLowerCase().includes(q));

  const indentPx = depth * 16;
  const rightOffset = Math.max(0, (depth - 1) * 16);
  const linkWidth = Math.max(12, (depth - 1) * 16);

  const typeLetter =
    depth === 0 && account.account_type
      ? TYPE_LETTER[account.account_type] || account.account_type[0]
      : null;

  return (
    <div className="select-none group">
      <div
        onContextMenu={(e) => {
          e.preventDefault();
          onOpenRowMenu(account, e.currentTarget as HTMLElement);
        }}
        className={[
          "flex items-center gap-2 py-2 px-3 rounded-[var(--radius-lg)]",
          "hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]",
          "border border-transparent hover:border-[var(--color-border)]",
          isMatch
            ? "bg-[var(--color-success)]/10 dark:bg-[var(--color-success)]/20 border-[var(--color-success)]/30 dark:border-[var(--color-success)]/50"
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
                className="absolute inset-y-0 w-px bg-[var(--color-border)] dark:bg-[var(--color-text-muted)]"
                style={{ right: rightOffset }}
              />
              <div
                className="absolute top-1/2 h-px bg-[var(--color-border)] dark:bg-[var(--color-text-muted)] -translate-y-1/2"
                style={{ right: rightOffset, width: linkWidth }}
              />
            </>
          )}
        </div>

        {hasChildren ? (
          <button
            type="button"
            onClick={() => toggle(account.id)}
            className="p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)] rounded-[var(--radius-md)]"
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
        {typeLetter && (
          <span
            className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary)]/20 text-[var(--font-size-xs)] font-bold text-[var(--color-primary)] dark:bg-[var(--color-primary)]/30 dark:text-[var(--color-primary-foreground)]"
            title="حساب رئيسي"
          >
            {typeLetter}
          </span>
        )}
        {!typeLetter && lp && (
          <span
            className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-warning)]/20 text-[var(--color-warning)] dark:bg-[var(--color-warning)]/30 dark:text-[var(--color-warning)]"
            title="حساب مرتبط بمورد"
          >
            <Factory className="w-4 h-4" />
          </span>
        )}
        {!typeLetter && !lp && <span className="w-7 flex-shrink-0" />}
        <span className="font-mono text-[var(--font-size-sm)] text-[var(--color-primary)] dark:text-[var(--color-primary)] w-20">
          {account.code || "—"}
        </span>
        <span className="flex-1 min-w-0 text-[var(--font-size-sm)] font-medium text-[var(--color-text)] dark:text-[var(--color-text)]">
          <span className="block truncate" title={displayName}>
            {displayName}
          </span>
          {subLegal && (
            <span className="block truncate text-[var(--font-size-xs)] font-normal uppercase tracking-wide text-[var(--color-text-muted)] dark:text-[var(--color-text-muted)] mt-0.5">
              {subLegal}
            </span>
          )}
          {lp && !aliasName && (
            <span className="block text-[var(--font-size-xs)] text-[var(--color-warning)] dark:text-[var(--color-warning)] mt-0.5">
              أضف اسماً مستعاراً للمورد (الحقل Name) ليظهر هنا
            </span>
          )}
          {lp && (
            <button
              type="button"
              className="mt-0.5 inline-flex items-center gap-1 text-[var(--font-size-xs)] text-[var(--color-primary)] hover:underline dark:text-[var(--color-primary)]"
              onClick={(e) => {
                e.stopPropagation();
                onOpenSupplier?.(lp.id);
              }}
            >
              <ExternalLink className="w-3 h-3" />
              تفاصيل المورد
            </button>
          )}
        </span>
        <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)] hidden md:inline">
          {ACCOUNT_TYPES.find((t) => t.v === account.account_type)?.l ||
            account.account_type}
        </span>

        <span
          className={[
            "w-2.5 h-2.5 rounded-full border inline-flex flex-shrink-0",
            account.is_active
              ? "bg-[var(--color-success)]/20 border-[var(--color-success)] dark:bg-[var(--color-success)]/30 dark:border-[var(--color-success)]"
              : "bg-[var(--color-text-muted)]/20 border-[var(--color-text-muted)] dark:bg-[var(--color-surface-3)] dark:border-[var(--color-text-muted)]",
          ].join(" ")}
          title={account.is_active ? "حساب نشط" : "حساب غير نشط"}
          aria-label={account.is_active ? "حساب نشط" : "حساب غير نشط"}
        />

        <button
          type="button"
          onClick={() => onAddChild(account)}
          className="p-1.5 text-[var(--color-success)] hover:bg-[var(--color-success)]/10 dark:hover:bg-[var(--color-success)]/20 rounded-[var(--radius-md)] opacity-0 group-hover:opacity-100 focus:opacity-100 transition-all pointer-events-none group-hover:pointer-events-auto focus:pointer-events-auto"
          title="حساب فرعي"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => onEdit(account)}
          className="p-1.5 text-[var(--color-primary)] hover:bg-[var(--color-primary)]/10 dark:hover:bg-[var(--color-primary)]/20 rounded-[var(--radius-md)] opacity-0 group-hover:opacity-100 focus:opacity-100 transition-all pointer-events-none group-hover:pointer-events-auto focus:pointer-events-auto"
        >
          <Pencil className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => onDelete(account.id)}
          className="p-1.5 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 dark:hover:bg-[var(--color-danger)]/20 rounded-[var(--radius-md)] opacity-0 group-hover:opacity-100 focus:opacity-100 transition-all pointer-events-none group-hover:pointer-events-auto focus:pointer-events-auto"
        >
          <Trash2 className="w-4 h-4" />
        </button>
        <button
          type="button"
          title="خيارات"
          className="p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)] rounded-[var(--radius-md)]"
          onClick={(e) => {
            e.stopPropagation();
            onOpenRowMenu(account, e.currentTarget);
          }}
        >
          <MoreHorizontal className="w-4 h-4" />
        </button>
        <button
          type="button"
          title="الأستاذ العام"
          className="p-1.5 text-[var(--color-success)] hover:bg-[var(--color-success)]/10 dark:hover:bg-[var(--color-success)]/20 rounded-[var(--radius-md)]"
          onClick={(e) => {
            e.stopPropagation();
            onOpenGeneralLedger?.(account.id);
          }}
        >
          <BookOpen className="w-4 h-4" />
        </button>
      </div>
      {hasChildren && isOpen && (
        <div className="relative me-3 pe-2 border-e-2 border-[var(--color-border)] dark:border-[var(--color-text-muted)] min-h-[2px]">
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
              onOpenGeneralLedger={onOpenGeneralLedger}
              onOpenSupplier={onOpenSupplier}
              onOpenRowMenu={onOpenRowMenu}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export interface AccountingCoaPageProps {
  onOpenGeneralLedger?: (accountId: number) => void;
  onOpenSupplier?: (partnerId: number) => void;
}

export const AccountingCoaPage: React.FC<AccountingCoaPageProps> = ({
  onOpenGeneralLedger,
  onOpenSupplier,
}) => {
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

  const [rowMenu, setRowMenu] = useState<{
    account: AccountingAccount;
    anchor: DOMRect;
  } | null>(null);
  const rowMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!rowMenu) return;
    const close = (e: MouseEvent) => {
      if (rowMenuRef.current?.contains(e.target as Node)) return;
      setRowMenu(null);
    };
    const tid = window.setTimeout(() => document.addEventListener("click", close), 0);
    return () => {
      window.clearTimeout(tid);
      document.removeEventListener("click", close);
    };
  }, [rowMenu]);

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
      const trade = (a.linked_partner?.trade_name ?? "").toLowerCase();
      const legal = (a.linked_partner?.legal_name ?? "").toLowerCase();

      if (code.includes(q) || name.includes(q) || trade.includes(q) || legal.includes(q)) {
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
      <div className="flex flex-wrap items-center justify-between gap-3 p-[var(--spacing-4)] bg-[var(--color-surface-3)] dark:bg-[var(--color-surface-3)] text-[var(--color-text)] dark:text-[var(--color-text-inverted)] rounded-[var(--radius-lg)] shadow-[var(--shadow-md)]">
        <div className="flex items-center gap-3">
          <FolderTree className="w-8 h-8 text-[var(--color-success)]" />
          <div>
            <h1 className="text-[var(--font-size-xl)] font-bold">شجرة الحسابات</h1>
            <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
              دليل الحسابات المرتبط بقاعدة البيانات المحاسبية
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => openCreate(null)}
          className="flex items-center gap-2 px-[var(--spacing-4)] py-2 bg-[var(--color-success)] hover:bg-[var(--color-success-hover)] rounded-[var(--radius-lg)] text-[var(--font-size-sm)] font-medium"
        >
          <Plus className="w-4 h-4" />
          حساب رئيسي
        </button>
      </div>

      {/* Toolbar: search / expand / collapse */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="flex-1 min-w-[220px] border border-[var(--color-border)] dark:border-[var(--color-border)] rounded-[var(--radius-lg)] px-3 py-2 dark:bg-[var(--color-surface-3)]"
          placeholder="بحث بالكود أو الاسم..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />

        <label className="flex items-center gap-2 text-[var(--font-size-sm)] text-[var(--color-text)] dark:text-[var(--color-text)] select-none">
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
            className="px-3 py-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] dark:border-[var(--color-border)] text-[var(--font-size-sm)] bg-[var(--color-surface)] dark:bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]"
          >
            توسيع الكل
          </button>
          <button
            type="button"
            onClick={collapseAll}
            className="px-3 py-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] dark:border-[var(--color-border)] text-[var(--font-size-sm)] bg-[var(--color-surface)] dark:bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]"
          >
            طيّ الكل
          </button>
        </div>
      </div>

      {err && (
        <div className="p-3 rounded-[var(--radius-lg)] bg-[var(--color-danger)]/10 dark:bg-[var(--color-danger)]/20 text-[var(--color-danger)] dark:text-[var(--color-danger)] text-[var(--font-size-sm)]">
          {err}
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-[var(--color-text-muted)]">جاري التحميل…</div>
      ) : (
        <div className="bg-[var(--color-surface)] dark:bg-[var(--color-surface-2)] rounded-[var(--radius-lg)] border border-[var(--color-border)] dark:border-[var(--color-border)] p-2 shadow-[var(--shadow-sm)]">
          {roots.length === 0 ? (
            <p className="p-[var(--spacing-6)] text-center text-[var(--color-text-muted)]">
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
                  onOpenGeneralLedger={onOpenGeneralLedger}
                  onOpenSupplier={onOpenSupplier}
                  onOpenRowMenu={(acc, el) => {
                    if (el) {
                      const r = el.getBoundingClientRect();
                      setRowMenu({ account: acc, anchor: r });
                    }
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {rowMenu && (
        <div
          ref={rowMenuRef}
          className="fixed z-[70] min-w-[200px] rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-lg)] dark:border-[var(--color-border)] dark:bg-[var(--color-surface-2)]"
          style={{
            top: Math.min(rowMenu.anchor.bottom + 4, window.innerHeight - 200),
            left: Math.min(rowMenu.anchor.left, window.innerWidth - 220),
          }}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-2 text-right text-[var(--font-size-sm)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]"
            onClick={() => {
              openCreate(rowMenu.account);
              setRowMenu(null);
            }}
          >
            <Plus className="h-4 w-4" />
            إنشاء حساب فرعي
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-2 text-right text-[var(--font-size-sm)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]"
            onClick={() => {
              openEdit(rowMenu.account);
              setRowMenu(null);
            }}
          >
            <Pencil className="h-4 w-4" />
            تعديل الحساب
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-2 text-right text-[var(--font-size-sm)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]"
            onClick={() => {
              onOpenGeneralLedger?.(rowMenu.account.id);
              setRowMenu(null);
            }}
          >
            <BookOpen className="h-4 w-4" />
            الأستاذ العام
          </button>
          {rowMenu.account.linked_partner && (
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-right text-[var(--font-size-sm)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]"
              onClick={() => {
                onOpenSupplier?.(rowMenu.account.linked_partner!.id);
                setRowMenu(null);
              }}
            >
              <ExternalLink className="h-4 w-4" />
              بطاقة المورد
            </button>
          )}
        </div>
      )}

      {dialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-[var(--spacing-4)] bg-black/50">
          <div className="bg-[var(--color-surface)] dark:bg-[var(--color-surface-2)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] max-w-md w-full p-[var(--spacing-6)] border border-[var(--color-border)] dark:border-[var(--color-border)]">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-[var(--font-size-xl)]">
                {dialog.mode === "edit" ? "تعديل حساب" : "حساب جديد"}
              </h3>
              <button
                type="button"
                onClick={() => setDialog(null)}
                className="p-1 rounded-[var(--radius-md)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">الكود</label>
                <input
                  className="w-full border border-[var(--color-border)] rounded-[var(--radius-lg)] px-3 py-2 dark:bg-[var(--color-surface-3)] dark:border-[var(--color-border)]"
                  value={form.code}
                  onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">الاسم</label>
                <input
                  className="w-full border border-[var(--color-border)] rounded-[var(--radius-lg)] px-3 py-2 dark:bg-[var(--color-surface-3)] dark:border-[var(--color-border)]"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">النوع</label>
                <select
                  className="w-full border border-[var(--color-border)] rounded-[var(--radius-lg)] px-3 py-2 dark:bg-[var(--color-surface-3)] dark:border-[var(--color-border)]"
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
                className="px-[var(--spacing-4)] py-2 rounded-[var(--radius-lg)] border dark:border-[var(--color-border)]"
              >
                إلغاء
              </button>
              <button
                type="button"
                onClick={saveDialog}
                className="flex items-center gap-2 px-[var(--spacing-4)] py-2 rounded-[var(--radius-lg)] bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
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
