import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Network, Plus, Pencil, Trash2, Search, Loader2, X, Check, BriefcaseBusiness,
  ChevronDown, ChevronLeft, Users,
} from "lucide-react";
import {
  createDepartment,
  createJobTitle,
  deleteDepartment,
  deleteJobTitle,
  listDepartments,
  listJobTitles,
  updateDepartment,
  updateJobTitle,
  type DepartmentDraft,
  type DepartmentRow,
  type JobTitleDraft,
  type JobTitleRow,
} from "../../services/hrOrgApi";
import { formatNumber } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";

/**
 * T-HR M1 — «الهيكل التنظيمي»: الأقسام شجرةً، والمسميات الوظيفية قائمةً.
 *
 * الشاشة خلف حارس ترخيص `hr_suite` في `App.tsx`، والخادم يرد 404 لكل نقطة
 * لشركةٍ غير مرخّصة — فلا طبقة إخفاءٍ ثالثة هنا، والصلاحية تُستهلك لتعطيل
 * أزرار التحرير لمن لا يملك `hr.org.manage`.
 *
 * القسم لا يُحذف وهو مشغول (الخادم يمنعه) — الزرّ يظهر ورسالةُ الخادم تُقرأ
 * كما هي، فالقاعدة تسكن مكاناً واحداً لا مكانين يتباعدان.
 */

const cardClass =
  "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4";
const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";
const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";
const btnPrimary =
  "inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3 h-9 text-sm " +
  "font-semibold text-white disabled:opacity-50";
const btnGhost =
  "inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 h-9 " +
  "text-sm text-[var(--color-text)] disabled:opacity-50";

type Tab = "departments" | "titles";

interface TreeNode {
  row: DepartmentRow;
  children: TreeNode[];
}

/** شجرة من قائمة مسطّحة. العقدة اليتيمة (أبٌ مفقود) تصعد للجذر فلا تختفي. */
export const buildDepartmentTree = (rows: DepartmentRow[]): TreeNode[] => {
  const nodes = new Map<number, TreeNode>();
  rows.forEach((row) => nodes.set(row.id, { row, children: [] }));
  const roots: TreeNode[] = [];
  rows.forEach((row) => {
    const node = nodes.get(row.id)!;
    const parent = row.parent != null ? nodes.get(row.parent) : undefined;
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  });
  return roots;
};

const messageOf = (cause: unknown, fallback: string) => humanizeThrown(cause, fallback);

export const OrgStructurePage: React.FC = () => {
  const permissions = usePermissions();
  const toast = useToast();
  const confirm = useConfirm();
  const canManage = permissions.can("hr.org.manage");

  const [tab, setTab] = useState<Tab>("departments");
  const [departments, setDepartments] = useState<DepartmentRow[]>([]);
  const [titles, setTitles] = useState<JobTitleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const [deptDraft, setDeptDraft] = useState<DepartmentDraft | null>(null);
  const [deptEditingId, setDeptEditingId] = useState<number | null>(null);
  const [titleDraft, setTitleDraft] = useState<JobTitleDraft | null>(null);
  const [titleEditingId, setTitleEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [deps, jobs] = await Promise.all([listDepartments(), listJobTitles()]);
      setDepartments(deps);
      setTitles(jobs);
    } catch (cause) {
      toast(messageOf(cause, "تعذّر تحميل الهيكل التنظيمي."), "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const filteredDepartments = useMemo(() => {
    const needle = search.trim();
    if (!needle) return departments;
    return departments.filter((row) => row.name.includes(needle));
  }, [departments, search]);

  const filteredTitles = useMemo(() => {
    const needle = search.trim();
    if (!needle) return titles;
    return titles.filter((row) => row.name.includes(needle));
  }, [titles, search]);

  const tree = useMemo(() => buildDepartmentTree(filteredDepartments), [filteredDepartments]);

  const toggleCollapse = (id: number) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const saveDepartment = async () => {
    if (!deptDraft?.name?.trim()) {
      toast("اسم القسم مطلوب.", "error");
      return;
    }
    setSaving(true);
    try {
      if (deptEditingId != null) await updateDepartment(deptEditingId, deptDraft);
      else await createDepartment(deptDraft);
      toast(deptEditingId != null ? "تم تعديل القسم." : "تم إنشاء القسم.", "success");
      setDeptDraft(null);
      setDeptEditingId(null);
      await reload();
    } catch (cause) {
      toast(messageOf(cause, "تعذّر حفظ القسم."), "error");
    } finally {
      setSaving(false);
    }
  };

  const removeDepartment = async (row: DepartmentRow) => {
    const ok = await confirm({
      title: "حذف القسم",
      message: `سيُحذف القسم «${row.name}». لا يمكن حذف قسم يضمّ موظفين أو أقساماً تابعة.`,
      confirmText: "حذف",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteDepartment(row.id);
      toast("تم حذف القسم.", "success");
      await reload();
    } catch (cause) {
      toast(messageOf(cause, "تعذّر حذف القسم."), "error");
    }
  };

  const saveTitle = async () => {
    if (!titleDraft?.name?.trim()) {
      toast("اسم المسمّى الوظيفي مطلوب.", "error");
      return;
    }
    setSaving(true);
    try {
      if (titleEditingId != null) await updateJobTitle(titleEditingId, titleDraft);
      else await createJobTitle(titleDraft);
      toast(titleEditingId != null ? "تم تعديل المسمّى." : "تم إنشاء المسمّى.", "success");
      setTitleDraft(null);
      setTitleEditingId(null);
      await reload();
    } catch (cause) {
      toast(messageOf(cause, "تعذّر حفظ المسمّى الوظيفي."), "error");
    } finally {
      setSaving(false);
    }
  };

  const removeTitle = async (row: JobTitleRow) => {
    const ok = await confirm({
      title: "حذف المسمّى الوظيفي",
      message: `سيُحذف «${row.name}». لا يمكن حذف مسمّى مستعمل لموظفين.`,
      confirmText: "حذف",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteJobTitle(row.id);
      toast("تم حذف المسمّى.", "success");
      await reload();
    } catch (cause) {
      toast(messageOf(cause, "تعذّر حذف المسمّى الوظيفي."), "error");
    }
  };

  const renderNode = (node: TreeNode, depth: number): React.ReactNode => {
    const isCollapsed = collapsed.has(node.row.id);
    const hasChildren = node.children.length > 0;
    return (
      <React.Fragment key={node.row.id}>
        <div
          className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] py-2"
          style={{ paddingInlineStart: `${depth * 20}px` }}
        >
          <button
            type="button"
            onClick={() => hasChildren && toggleCollapse(node.row.id)}
            className={`grid h-6 w-6 place-items-center rounded ${hasChildren ? "" : "invisible"}`}
            aria-label={isCollapsed ? "توسيع" : "طيّ"}
          >
            {isCollapsed ? <ChevronLeft size={14} /> : <ChevronDown size={14} />}
          </button>
          <span className="font-semibold">{node.row.name}</span>
          {!node.row.is_active && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800">معطَّل</span>
          )}
          <span className="inline-flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <Users size={12} />
            {formatNumber(node.row.employees_count, { maxDecimals: 0 })}
          </span>
          {node.row.branch_name && (
            <span className="text-xs text-[var(--color-text-muted)]">فرع: {node.row.branch_name}</span>
          )}
          {node.row.manager_name && (
            <span className="text-xs text-[var(--color-text-muted)]">مدير: {node.row.manager_name}</span>
          )}
          {canManage && (
            <span className="ms-auto flex items-center gap-1">
              <button
                type="button"
                className={btnGhost}
                onClick={() => {
                  setDeptEditingId(node.row.id);
                  setDeptDraft({
                    name: node.row.name,
                    parent: node.row.parent,
                    branch: node.row.branch,
                    manager: node.row.manager,
                    is_active: node.row.is_active,
                    notes: node.row.notes,
                  });
                }}
              >
                <Pencil size={14} /> تعديل
              </button>
              <button
                type="button"
                className={btnGhost}
                onClick={() => void removeDepartment(node.row)}
              >
                <Trash2 size={14} /> حذف
              </button>
            </span>
          )}
        </div>
        {!isCollapsed && node.children.map((child) => renderNode(child, depth + 1))}
      </React.Fragment>
    );
  };

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        <Network size={20} className="text-[var(--color-primary)]" />
        <h1 className="text-lg font-bold">الهيكل التنظيمي</h1>
        <div className="ms-auto flex items-center gap-2">
          <div className="relative">
            <Search
              size={14}
              className="pointer-events-none absolute inset-y-0 my-auto start-2 text-[var(--color-text-muted)]"
            />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="بحث بالاسم"
              className={`${inputClass} ps-7 w-48`}
            />
          </div>
          {canManage && (
            <button
              type="button"
              className={btnPrimary}
              onClick={() => {
                if (tab === "departments") {
                  setDeptEditingId(null);
                  setDeptDraft({ name: "", is_active: true });
                } else {
                  setTitleEditingId(null);
                  setTitleDraft({ name: "", is_active: true });
                }
              }}
            >
              <Plus size={14} />
              {tab === "departments" ? "قسم جديد" : "مسمّى جديد"}
            </button>
          )}
        </div>
      </header>

      <nav className="flex gap-1 border-b border-[var(--color-border)]">
        {([
          ["departments", "الأقسام", <Network size={14} key="d" />],
          ["titles", "المسميات الوظيفية", <BriefcaseBusiness size={14} key="t" />],
        ] as [Tab, string, React.ReactNode][]).map(([key, label, icon]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm ${
              tab === key
                ? "border-b-2 border-[var(--color-primary)] font-semibold text-[var(--color-primary)]"
                : "text-[var(--color-text-muted)]"
            }`}
          >
            {icon}
            {label}
          </button>
        ))}
      </nav>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="animate-spin" />
        </div>
      ) : tab === "departments" ? (
        <div className={cardClass}>
          {tree.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--color-text-muted)]">
              لا أقسام بعد — ابدأ بقسمٍ واحد ثم ضع تحته ما يتبعه.
            </p>
          ) : (
            tree.map((node) => renderNode(node, 0))
          )}
        </div>
      ) : (
        <div className={`${cardClass} overflow-x-auto`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-start text-[var(--color-text-muted)]">
                <th className="p-2 text-start">المسمّى</th>
                <th className="p-2 text-start">القسم</th>
                <th className="p-2 text-start">الموظفون</th>
                <th className="p-2 text-start">الحالة</th>
                {canManage && <th className="p-2" />}
              </tr>
            </thead>
            <tbody>
              {filteredTitles.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-[var(--color-text-muted)]">
                    لا مسميات وظيفية بعد.
                  </td>
                </tr>
              ) : (
                filteredTitles.map((row) => (
                  <tr key={row.id} className="border-t border-[var(--color-border)]">
                    <td className="p-2 font-semibold">{row.name}</td>
                    <td className="p-2">{row.department_name || "—"}</td>
                    <td className="p-2">{formatNumber(row.employees_count, { maxDecimals: 0 })}</td>
                    <td className="p-2">{row.is_active ? "نشط" : "معطَّل"}</td>
                    {canManage && (
                      <td className="p-2">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            className={btnGhost}
                            onClick={() => {
                              setTitleEditingId(row.id);
                              setTitleDraft({
                                name: row.name,
                                department: row.department,
                                is_active: row.is_active,
                              });
                            }}
                          >
                            <Pencil size={14} /> تعديل
                          </button>
                          <button
                            type="button"
                            className={btnGhost}
                            onClick={() => void removeTitle(row)}
                          >
                            <Trash2 size={14} /> حذف
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {deptDraft && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-3">
          <div className={`${cardClass} w-full max-w-md`}>
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-bold">{deptEditingId != null ? "تعديل قسم" : "قسم جديد"}</h2>
              <button
                type="button"
                className="ms-auto"
                onClick={() => {
                  setDeptDraft(null);
                  setDeptEditingId(null);
                }}
                aria-label="إغلاق"
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className={labelClass} htmlFor="dept-name">اسم القسم</label>
                <input
                  id="dept-name"
                  className={inputClass}
                  value={deptDraft.name}
                  onChange={(event) => setDeptDraft({ ...deptDraft, name: event.target.value })}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="dept-parent">القسم الأعلى</label>
                <select
                  id="dept-parent"
                  className={inputClass}
                  value={deptDraft.parent ?? ""}
                  onChange={(event) =>
                    setDeptDraft({
                      ...deptDraft,
                      parent: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                >
                  <option value="">— بلا قسم أعلى —</option>
                  {departments
                    .filter((row) => row.id !== deptEditingId)
                    .map((row) => (
                      <option key={row.id} value={row.id}>{row.name}</option>
                    ))}
                </select>
              </div>
              <div>
                <label className={labelClass} htmlFor="dept-notes">ملاحظات</label>
                <textarea
                  id="dept-notes"
                  className={`${inputClass} h-20 py-2`}
                  value={deptDraft.notes ?? ""}
                  onChange={(event) => setDeptDraft({ ...deptDraft, notes: event.target.value })}
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={deptDraft.is_active !== false}
                  onChange={(event) => setDeptDraft({ ...deptDraft, is_active: event.target.checked })}
                />
                نشط
              </label>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                className={btnGhost}
                onClick={() => {
                  setDeptDraft(null);
                  setDeptEditingId(null);
                }}
              >
                إلغاء
              </button>
              <button type="button" className={btnPrimary} disabled={saving} onClick={() => void saveDepartment()}>
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} حفظ
              </button>
            </div>
          </div>
        </div>
      )}

      {titleDraft && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-3">
          <div className={`${cardClass} w-full max-w-md`}>
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-bold">
                {titleEditingId != null ? "تعديل مسمّى وظيفي" : "مسمّى وظيفي جديد"}
              </h2>
              <button
                type="button"
                className="ms-auto"
                onClick={() => {
                  setTitleDraft(null);
                  setTitleEditingId(null);
                }}
                aria-label="إغلاق"
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className={labelClass} htmlFor="title-name">المسمّى</label>
                <input
                  id="title-name"
                  className={inputClass}
                  value={titleDraft.name}
                  onChange={(event) => setTitleDraft({ ...titleDraft, name: event.target.value })}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="title-dept">القسم</label>
                <select
                  id="title-dept"
                  className={inputClass}
                  value={titleDraft.department ?? ""}
                  onChange={(event) =>
                    setTitleDraft({
                      ...titleDraft,
                      department: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                >
                  <option value="">— بلا قسم —</option>
                  {departments.map((row) => (
                    <option key={row.id} value={row.id}>{row.name}</option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={titleDraft.is_active !== false}
                  onChange={(event) => setTitleDraft({ ...titleDraft, is_active: event.target.checked })}
                />
                نشط
              </label>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                className={btnGhost}
                onClick={() => {
                  setTitleDraft(null);
                  setTitleEditingId(null);
                }}
              >
                إلغاء
              </button>
              <button type="button" className={btnPrimary} disabled={saving} onClick={() => void saveTitle()}>
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} حفظ
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OrgStructurePage;
