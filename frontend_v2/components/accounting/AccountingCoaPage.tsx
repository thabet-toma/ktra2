import React, { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { AccountingAccount } from "../../types/accounting";
import {
  AseelDocumentShell,
  useAseelKeymap,
  useRecordNavigation,
} from "../aseel";
import type { AseelToolbarAction } from "../aseel";
import {
  accountNature,
  accountPath,
  accountStatement,
  ancestorIdsOf,
  buildAccountIndex,
  nextChildCode,
  visibleAccountRows,
} from "../../utils/accountTree";
import {
  ChevronDown,
  ChevronLeft,
  FolderTree,
  Plus,
  Pencil,
  Trash2,
  Save,
  MoreHorizontal,
  BookOpen,
  ExternalLink,
  Factory,
  RefreshCw,
  Search,
  UserRound,
  FilePlus2,
  ReceiptText,
  HandCoins,
  ClipboardList,
  FileText,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  partnerActionGroups,
  partnerKindFromType,
  type PartnerAction,
  type PartnerActionIcon,
} from "../../utils/partnerActions";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { clientLogger } from "../../services/logger";

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

/**
 * THA-111: التصنيف الوظيفي (`Account.sub_type`) — «صندوق» و«ذمم» و«مخزون» كلها
 * `Asset`، والنوع وحده لا يعرف أيّها. يشتقّه الخادم مرة واحدة، وهذا الحقل هو
 * تصحيح صاحب الشركة لحسابٍ صنّفه الاشتقاق خطأً.
 */
const SUB_TYPES = [
  { v: "", l: "—" },
  { v: "cash_box", l: "صندوق نقدية" },
  { v: "bank", l: "حساب بنكي" },
  { v: "receivable", l: "ذمم مدينة (عملاء)" },
  { v: "payable", l: "ذمم دائنة (موردون)" },
  { v: "inventory", l: "مخزون" },
];

/** حقول مشتقّة تُعرض للقراءة فقط — لا تُدخَل يدوياً (نمط الأصيل). */
const NATURE_LABEL = { debit: "مدين", credit: "دائن" } as const;
const STATEMENT_LABEL = { balance: "ميزانية", income: "أرباح وخسائر" } as const;

// T-COAMENU: قائمة يمين مجمَّعة بعناوين — سطور متجاورة بلا عناوين لا تُقرأ.
const MENU_ITEM =
  "flex w-full items-center gap-2 px-3 py-2 text-right text-[var(--font-size-sm)] hover:bg-[var(--color-surface-2)] dark:hover:bg-[var(--color-surface-3)]";
const MENU_GROUP_TITLE =
  "px-3 pt-2 pb-1 text-[10px] font-bold text-[var(--color-text-muted)]";

/** أيقونة الإجراء من مفتاحه — الطبقة المشتركة نقيّة بلا React فتُعيد مفاتيح. */
const PartnerActionIconView: React.FC<{ icon: PartnerActionIcon }> = ({ icon }) => {
  const cls = "h-4 w-4";
  switch (icon) {
    case "card": return <UserRound className={cls} />;
    case "statement": return <FileText className={cls} />;
    case "ledger": return <BookOpen className={cls} />;
    case "invoice": return <FilePlus2 className={cls} />;
    case "quotation": return <FileText className={cls} />;
    case "order": return <ClipboardList className={cls} />;
    case "receipt": return <ReceiptText className={cls} />;
    case "payment": return <HandCoins className={cls} />;
    default: return <ExternalLink className={cls} />;
  }
};

/** الاسم المعروض: الاسم المستعار (عربي) للمورد المرتبط، وإلا اسم الحساب. */
const displayNameOf = (account: AccountingAccount): string => {
  const alias = (account.linked_partner?.trade_name || "").trim();
  if (account.linked_partner) return alias || "—";
  return (account.name || "").trim() || "—";
};

export interface AccountingCoaPageProps {
  onOpenGeneralLedger?: (accountId: number) => void;
  onOpenSupplier?: (partnerId: number) => void;
}

type PaneMode = "view" | "edit" | "create";

/**
 * شجرة الحسابات على نمط الأصيل: الشجرة شريطٌ مضغوط على اليمين، وبطاقة الحساب
 * المحدَّد على اليسار — لا نافذة منبثقة لكل إضافة/تعديل، ولا صفوف طويلة تُخفي
 * نصف الشجرة. منطق الشجرة كله من `utils/accountTree` (مصدر واحد مُختبَر).
 */
export const AccountingCoaPage: React.FC<AccountingCoaPageProps> = ({
  onOpenGeneralLedger,
  onOpenSupplier,
}) => {
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [searchTerm, setSearchTerm] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mode, setMode] = useState<PaneMode>("view");
  const [form, setForm] = useState({
    name: "",
    code: "",
    account_type: "Asset",
    sub_type: "",
    parent: null as number | null,
    is_active: true,
  });

  const [rowMenu, setRowMenu] = useState<{
    account: AccountingAccount;
    anchor: DOMRect;
  } | null>(null);
  const rowMenuRef = useRef<HTMLDivElement | null>(null);
  const treeBodyRef = useRef<HTMLDivElement | null>(null);

  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();

  const visibleAccounts = useMemo(
    () => (activeOnly ? accounts.filter((a) => a.is_active) : accounts),
    [accounts, activeOnly],
  );
  const index = useMemo(() => buildAccountIndex(visibleAccounts), [visibleAccounts]);
  const rows = useMemo(
    () => visibleAccountRows(visibleAccounts, index, { query: searchTerm, expanded }),
    [visibleAccounts, index, searchTerm, expanded],
  );
  const selected = selectedId != null ? index.byId.get(selectedId) ?? null : null;
  const editing = mode !== "view";

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = (await accountingApi.getAccounts()) as AccountingAccount[];
      setAccounts(data);
      // المستويان الأعلى مفتوحان عند الفتح — بقية الفروع بطلب المستخدم.
      const fresh = buildAccountIndex(data);
      const open = new Set<number>();
      for (const root of fresh.childrenOf.get(null) ?? []) {
        open.add(root.id);
        for (const child of fresh.childrenOf.get(root.id) ?? []) open.add(child.id);
      }
      setExpanded(open);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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

  // التنقّل بالأسهم أو بأزرار السجل قد يخرج الصف المحدَّد عن حدود الشريط.
  useEffect(() => {
    if (selectedId == null) return;
    treeBodyRef.current
      ?.querySelector<HTMLElement>(`[data-account-id="${selectedId}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [selectedId, rows]);

  const toggle = useCallback((id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  /** الانتقال إلى حساب آخر يُلغي تحريراً جارياً بعد تأكيد — لا يُسقطه صامتاً. */
  const selectAccount = useCallback(
    async (id: number | null) => {
      if (editing) {
        const ok = await confirm({
          title: "تعديلات غير محفوظة",
          message: "الانتقال إلى حساب آخر يُلغي ما لم يُحفَظ. المتابعة؟",
          confirmText: "متابعة",
          danger: false,
        });
        if (!ok) return;
        setMode("view");
      }
      setSelectedId(id);
      if (id != null) {
        setExpanded((prev) => {
          const next = new Set(prev);
          for (const ancestor of ancestorIdsOf(index, id)) next.add(ancestor);
          return next;
        });
      }
    },
    [confirm, editing, index],
  );

  const nav = useRecordNavigation({
    items: rows,
    getId: useCallback((r: (typeof rows)[number]) => r.account.id, []),
    currentId: mode === "create" ? null : selectedId,
    onSelect: (id) => {
      void selectAccount(id == null ? null : Number(id));
    },
  });

  const startCreate = useCallback(
    (parent: AccountingAccount | null) => {
      setForm({
        name: "",
        code: nextChildCode(index, parent?.id ?? null),
        account_type: parent?.account_type || "Asset",
        // الحساب الجديد تحت صندوق/ذمم يرث تصنيف أبيه — أقرب جواب صحيح.
        sub_type: parent?.sub_type || "",
        parent: parent?.id ?? null,
        is_active: true,
      });
      setErr(null);
      setMode("create");
      if (parent) {
        setExpanded((prev) => new Set(prev).add(parent.id));
      }
    },
    [index],
  );

  const startEdit = useCallback(() => {
    if (!selected) return;
    setForm({
      name: selected.name || "",
      code: selected.code || "",
      account_type: selected.account_type || "Asset",
      sub_type: selected.sub_type || "",
      parent: selected.parent,
      is_active: selected.is_active,
    });
    setErr(null);
    setMode("edit");
  }, [selected]);

  const cancelEdit = useCallback(() => {
    setMode("view");
    setErr(null);
  }, []);

  const save = useCallback(async () => {
    if (!editing) return;
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
        // «—» يعني حساباً عادياً يكفيه نوعه؛ الخادم يقبل NULL لا نصاً فارغاً.
        sub_type: form.sub_type || null,
        parent: form.parent,
        is_active: form.is_active,
      };
      if (mode === "edit" && selected) {
        await accountingApi.updateAccount(selected.id, body);
      } else {
        const created = (await accountingApi.createAccount(body)) as
          | AccountingAccount
          | undefined;
        if (created?.id) setSelectedId(created.id);
      }
      clientLogger.info("app.coa_account_saved");
      setMode("view");
      await load();
      toast(mode === "edit" ? "تم حفظ الحساب" : "تم إنشاء الحساب", "success");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    }
  }, [editing, form, load, mode, selected, toast]);

  const remove = useCallback(async () => {
    if (!selected) return;
    const ok = await confirm({
      title: "حذف حساب",
      message: `حذف «${displayNameOf(selected)}» من شجرة الحسابات؟`,
      confirmText: "حذف",
    });
    if (!ok) return;
    try {
      const parentId = selected.parent;
      await accountingApi.deleteAccount(selected.id);
      clientLogger.info("app.coa_account_deleted");
      setSelectedId(parentId);
      setMode("view");
      await load();
      toast("تم حذف الحساب", "success");
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "فشل الحذف", "error");
    }
  }, [confirm, load, selected, toast]);

  const focusSearch = useCallback(() => {
    document.querySelector<HTMLInputElement>('[data-aseel-field="search"]')?.focus();
  }, []);

  // مفاتيح الأصيل كما في نافذة شجرة الحسابات: جديد F2 · تعديل F3 · حذف F4 ·
  // حفظ F5 · بحث F6 · خروج Esc.
  useAseelKeymap({
    F2: () => startCreate(selected),
    F3: startEdit,
    F4: () => void remove(),
    F5: () => void save(),
    F6: focusSearch,
    Escape: cancelEdit,
    CtrlIns: () => startCreate(null),
  });

  const expandAll = () => setExpanded(new Set(accounts.map((a) => a.id)));
  const collapseAll = () => setExpanded(new Set());

  /**
   * T-COAMENU: إجراءات الطرف المرتبط بالحساب — من نفس مصدر القائمة العامّة.
   * الحساب بلا طرف (أو بنوع غير معروف) يبقى بإجراءات الحساب وحدها.
   */
  const partnerMenuGroups = (account: AccountingAccount) => {
    const lp = account.linked_partner;
    const kind = partnerKindFromType(lp?.partner_type);
    if (!lp || !kind) return [];
    return partnerActionGroups({
      id: String(lp.id),
      name: lp.trade_name || lp.legal_name || "",
      kind,
    });
  };

  const runPartnerAction = (account: AccountingAccount, action: PartnerAction) => {
    const lp = account.linked_partner;
    if (!lp) return;
    clientLogger.info("app.coa_partner_action");
    if (action.bridge) {
      // جسر الجلسة نفسه الذي تستعمله القائمة العامّة (ktra_partner_action).
      try { sessionStorage.setItem("ktra_partner_action", action.bridge); } catch { /* وضع خاص */ }
      navigate(`/partners/${lp.id}`);
      return;
    }
    if (action.href) navigate(action.href);
  };

  const openRowMenu = (account: AccountingAccount, el: HTMLElement | null) => {
    void selectAccount(account.id);
    if (el) setRowMenu({ account, anchor: el.getBoundingClientRect() });
  };

  const onTreeKeyDown = (e: React.KeyboardEvent) => {
    const at = rows.findIndex((r) => r.account.id === selectedId);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = rows[at < 0 ? 0 : Math.min(at + 1, rows.length - 1)];
      if (next) void selectAccount(next.account.id);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = rows[at <= 0 ? 0 : at - 1];
      if (prev) void selectAccount(prev.account.id);
      return;
    }
    // في RTL: السهم الأيسر يفتح الفرع والأيمن يطويه (كما في منتقي الحساب).
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const row = rows[at];
      if (!row?.hasChildren) return;
      e.preventDefault();
      const wantOpen = e.key === "ArrowLeft";
      if (wantOpen !== row.expanded) toggle(row.account.id);
    }
  };

  const tree = (
    <aside className="aseel-tree-panel aseel-tree-panel--coa" aria-label="شجرة الحسابات">
      <div className="aseel-tree-head">
        <FolderTree className="w-4 h-4" />
        <span style={{ fontWeight: 700 }}>شجرة الحسابات</span>
        <span className="aseel-tree-count">{accounts.length}</span>
      </div>
      <div className="aseel-tree-search">
        <Search className="w-3.5 h-3.5" />
        <input
          className="aseel-input"
          data-aseel-field="search"
          placeholder="بحث بالكود أو الاسم… (F6)"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        {searchTerm && (
          <button type="button" className="aseel-tree-act" title="مسح البحث"
            onClick={() => setSearchTerm("")}>
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <div className="aseel-tree-actions">
        <button type="button" className="aseel-toolbtn" onClick={expandAll}>توسيع الكل</button>
        <button type="button" className="aseel-toolbtn" onClick={collapseAll}>طيّ الكل</button>
        <label className="flex items-center gap-1" style={{ fontSize: "var(--aseel-fs-sm)" }}>
          <input type="checkbox" checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)} />
          النشطة فقط
        </label>
      </div>
      <div
        className="aseel-tree-body"
        role="tree"
        tabIndex={0}
        ref={treeBodyRef}
        onKeyDown={onTreeKeyDown}
      >
        {loading ? (
          <div style={{ padding: "16px", textAlign: "center", color: "var(--aseel-ink-soft)" }}>
            جاري التحميل…
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "16px", textAlign: "center", color: "var(--aseel-ink-soft)" }}>
            {accounts.length === 0 ? "لا توجد حسابات. أضف حساباً رئيسياً." : "لا نتائج"}
          </div>
        ) : (
          rows.map((row) => {
            const a = row.account;
            const isSel = a.id === selectedId;
            const letter = row.depth === 0 && a.account_type
              ? TYPE_LETTER[a.account_type] || a.account_type[0]
              : null;
            return (
              <div
                key={a.id}
                data-account-id={a.id}
                role="treeitem"
                aria-level={row.depth + 1}
                aria-expanded={row.hasChildren ? row.expanded : undefined}
                aria-selected={isSel}
                className={row.hasChildren ? "aseel-tree-node" : "aseel-tree-leaf"}
                style={{
                  paddingInlineStart: `${4 + row.depth * 14}px`,
                  fontWeight: row.hasChildren ? 600 : 400,
                  background: isSel ? "var(--aseel-row-sel)" : undefined,
                  opacity: a.is_active ? 1 : 0.55,
                }}
                onClick={() => void selectAccount(a.id)}
                onDoubleClick={() => { if (row.hasChildren) toggle(a.id); }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  openRowMenu(a, e.currentTarget as HTMLElement);
                }}
              >
                {row.hasChildren ? (
                  <button
                    type="button"
                    className="aseel-tree-twisty"
                    aria-label={row.expanded ? "طيّ" : "فتح"}
                    onClick={(e) => { e.stopPropagation(); toggle(a.id); }}
                  >
                    {row.expanded ? <ChevronDown size={13} /> : <ChevronLeft size={13} />}
                  </button>
                ) : (
                  <span style={{ display: "inline-block", width: "16px", flexShrink: 0 }} />
                )}
                {letter ? (
                  <span
                    title="حساب رئيسي"
                    style={{
                      flexShrink: 0, width: "15px", textAlign: "center", fontWeight: 700,
                      color: "var(--aseel-accent)",
                    }}
                  >
                    {letter}
                  </span>
                ) : a.linked_partner ? (
                  <Factory className="w-3 h-3" style={{ flexShrink: 0 }} />
                ) : (
                  <span style={{ display: "inline-block", width: "15px", flexShrink: 0 }} />
                )}
                <span className="font-mono" style={{ flexShrink: 0, minWidth: "62px" }}>
                  {a.code || "—"}
                </span>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {displayNameOf(a)}
                </span>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );

  const readOnly = !editing;
  const natureKey = selected ? accountNature(selected) : null;
  const statementKey = selected ? accountStatement(selected) : null;
  const formNature = accountNature({ id: 0, account_type: form.account_type });
  const formStatement = accountStatement({ id: 0, account_type: form.account_type });
  const parentPath = accountPath(index, editing ? form.parent : selected?.parent ?? null)
    .map((a) => a.name || a.code || "")
    .join(" ← ");

  const pane = (
    <div style={{ padding: "10px 12px", maxWidth: "620px" }}>
      {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}

      {!selected && !editing ? (
        <div style={{ padding: "40px 8px", color: "var(--aseel-ink-soft)", textAlign: "center" }}>
          اختر حساباً من الشجرة لعرض بطاقته، أو «حساب رئيسي» لإضافة جذر جديد.
        </div>
      ) : (
        <>
          <div className="aseel-field">
            <label className="aseel-field-label" style={{ minWidth: "110px" }}>رقم الحساب</label>
            <input
              className="aseel-input font-mono"
              value={editing ? form.code : selected?.code || ""}
              readOnly={readOnly}
              onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
            />
          </div>
          <div className="aseel-field" style={{ marginTop: "6px" }}>
            <label className="aseel-field-label" style={{ minWidth: "110px" }}>وصف الحساب</label>
            <input
              className="aseel-input"
              value={editing ? form.name : selected?.name || ""}
              readOnly={readOnly}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="aseel-field" style={{ marginTop: "6px" }}>
            <label className="aseel-field-label" style={{ minWidth: "110px" }}>نوع الحساب</label>
            <select
              className="aseel-input"
              value={editing ? form.account_type : selected?.account_type || ""}
              disabled={readOnly}
              onChange={(e) => setForm((f) => ({ ...f, account_type: e.target.value }))}
            >
              {ACCOUNT_TYPES.map((t) => (
                <option key={t.v} value={t.v}>{t.l}</option>
              ))}
            </select>
          </div>
          {/* THA-111: الغرض الذي يظهر فيه الحساب داخل منتقيات الحسابات. */}
          <div className="aseel-field" style={{ marginTop: "6px" }}>
            <label className="aseel-field-label" style={{ minWidth: "110px" }}>التصنيف الوظيفي</label>
            <select
              className="aseel-input"
              value={editing ? form.sub_type : selected?.sub_type || ""}
              disabled={readOnly}
              onChange={(e) => setForm((f) => ({ ...f, sub_type: e.target.value }))}
            >
              {SUB_TYPES.map((t) => (
                <option key={t.v} value={t.v}>{t.l}</option>
              ))}
            </select>
          </div>
          <p className="mt-1 text-[11px] text-[var(--aseel-ink-soft)]">
            يحدّد في أي الحقول يُعرض هذا الحساب — حقل الصندوق يعرض الصناديق والبنوك
            وحدها، وهكذا. «—» يعني حساباً عادياً يكفيه نوعه.
          </p>

          {/* حقول مشتقّة — تُعرض ولا تُدخَل (الأصيل يشتقّها من نوع الحساب). */}
          <div className="aseel-field" style={{ marginTop: "6px" }}>
            <label className="aseel-field-label" style={{ minWidth: "110px" }}>نوع الحساب الختامي</label>
            <input
              className="aseel-input aseel-input--hl"
              readOnly
              value={
                (editing ? formStatement : statementKey)
                  ? STATEMENT_LABEL[(editing ? formStatement : statementKey)!]
                  : "—"
              }
            />
          </div>
          <div className="aseel-field" style={{ marginTop: "6px" }}>
            <label className="aseel-field-label" style={{ minWidth: "110px" }}>طبيعة الحساب</label>
            <input
              className="aseel-input aseel-input--hl"
              readOnly
              value={
                (editing ? formNature : natureKey)
                  ? NATURE_LABEL[(editing ? formNature : natureKey)!]
                  : "—"
              }
            />
          </div>
          <div className="aseel-field" style={{ marginTop: "6px" }}>
            <label className="aseel-field-label" style={{ minWidth: "110px" }}>يتبع حساب</label>
            <input className="aseel-input" readOnly value={parentPath || "— حساب رئيسي —"} />
          </div>
          <label className="flex items-center gap-2" style={{ marginTop: "8px", fontSize: "var(--aseel-fs)" }}>
            <input
              type="checkbox"
              checked={editing ? form.is_active : !!selected?.is_active}
              disabled={readOnly}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            حساب نشط
          </label>

          {selected?.linked_partner && !editing && (
            <div style={{ marginTop: "10px", display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span style={{ color: "var(--aseel-ink-soft)", fontSize: "var(--aseel-fs-sm)" }}>
                مرتبط بالطرف:
              </span>
              <span style={{ fontWeight: 600 }}>
                {selected.linked_partner.trade_name || selected.linked_partner.legal_name || "—"}
              </span>
              <button
                type="button"
                className="aseel-toolbtn"
                onClick={() => onOpenSupplier?.(selected.linked_partner!.id)}
              >
                <ExternalLink className="w-3.5 h-3.5" />بطاقة الطرف
              </button>
            </div>
          )}

          {selected && !editing && (
            <div style={{ marginTop: "12px", display: "flex", gap: "6px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="aseel-toolbtn"
                onClick={() => onOpenGeneralLedger?.(selected.id)}
              >
                <BookOpen className="w-4 h-4" />الرصيد الحالي (الأستاذ العام)
              </button>
              <button
                type="button"
                className="aseel-toolbtn"
                onClick={(e) => openRowMenu(selected, e.currentTarget)}
              >
                <MoreHorizontal className="w-4 h-4" />خيارات
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );

  const shellActions: AseelToolbarAction[] = [
    {
      key: "new-child",
      label: selected && !editing ? "جديد F2 (فرعي)" : "جديد F2",
      icon: <Plus className="w-4 h-4" />,
      onClick: () => startCreate(editing ? null : selected),
      disabled: editing,
    },
    { key: "new-root", label: "حساب رئيسي", onClick: () => startCreate(null), disabled: editing },
    {
      key: "edit",
      label: "تعديل F3",
      icon: <Pencil className="w-4 h-4" />,
      onClick: startEdit,
      disabled: editing || !selected,
      separatorBefore: true,
    },
    {
      key: "delete",
      label: "حذف F4",
      icon: <Trash2 className="w-4 h-4" />,
      onClick: () => void remove(),
      disabled: editing || !selected,
      danger: true,
    },
    {
      key: "save",
      label: "حفظ F5",
      icon: <Save className="w-4 h-4" />,
      onClick: () => void save(),
      disabled: !editing,
      separatorBefore: true,
    },
    { key: "cancel", label: "إلغاء Esc", onClick: cancelEdit, disabled: !editing },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className="w-4 h-4" />,
      onClick: load,
      disabled: editing,
      separatorBefore: true,
    },
  ];

  const selectedPath = selected
    ? accountPath(index, selected.id).map((a) => a.name || a.code || "").join(" ← ")
    : "";

  return (
    <div>
      <AseelDocumentShell
        title="شجرة الحسابات"
        state={mode === "create" ? "حساب جديد" : mode === "edit" ? "تعديل" : undefined}
        nav={nav}
        actions={shellActions}
        aside={tree}
        status={
          <>
            <span className="aseel-status-item">
              <FolderTree className="w-3 h-3" />
              الحساب {nav.position} من {nav.total} · {accounts.length} حساب
            </span>
            {selectedPath && <span className="aseel-status-item">{selectedPath}</span>}
          </>
        }
      >
        {pane}
      </AseelDocumentShell>

      {rowMenu && (
        <div
          ref={rowMenuRef}
          className="fixed z-[70] max-h-[70vh] min-w-[230px] overflow-y-auto rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-lg)] dark:border-[var(--color-border)] dark:bg-[var(--color-surface-2)]"
          style={{
            top: Math.min(rowMenu.anchor.bottom + 4, window.innerHeight - 200),
            left: Math.min(rowMenu.anchor.left, window.innerWidth - 250),
          }}
        >
          <div className={MENU_GROUP_TITLE}>الحساب</div>
          <button
            type="button"
            className={MENU_ITEM}
            onClick={() => { startCreate(rowMenu.account); setRowMenu(null); }}
          >
            <Plus className="h-4 w-4" />إنشاء حساب فرعي
          </button>
          <button
            type="button"
            className={MENU_ITEM}
            onClick={() => { startEdit(); setRowMenu(null); }}
          >
            <Pencil className="h-4 w-4" />تعديل الحساب
          </button>
          <button
            type="button"
            className={MENU_ITEM}
            onClick={() => { onOpenGeneralLedger?.(rowMenu.account.id); setRowMenu(null); }}
          >
            <BookOpen className="h-4 w-4" />الأستاذ العام
          </button>
          {/* T-COAMENU: حساب الذمم هو طرفٌ فعلاً — فتُعرض إجراءاته كاملةً من
              نفس مصدر القائمة العامّة (utils/partnerActions)، مجمَّعةً بعناوين. */}
          {partnerMenuGroups(rowMenu.account).map((group) => (
            <div key={group.title}>
              <div className={MENU_GROUP_TITLE}>{group.title}</div>
              {group.actions.map((action) => (
                <button
                  key={action.key}
                  type="button"
                  className={MENU_ITEM}
                  onClick={() => { runPartnerAction(rowMenu.account, action); setRowMenu(null); }}
                >
                  <PartnerActionIconView icon={action.icon} />
                  {action.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
