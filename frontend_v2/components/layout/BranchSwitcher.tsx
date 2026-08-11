/**
 * task11 M4 — مبدّل الفرع النشط.
 *
 * يعرض فروع الشركة النشطة + خيار «كل الفروع». الاختيار يُخزن في
 * localStorage.branchId ويُعاد تحميل الصفحة ليُرسل X-Branch-Id مع كل طلب
 * (فواتير/مخزون/تقارير مستقلة لكل فرع — شجرة الحسابات والأصناف مشتركة).
 * إنشاء فرع جديد = صلاحية مدير.
 */
import React, { useEffect, useRef, useState } from "react";
import { GitBranch, Plus, ChevronDown, Check, Loader2 } from "lucide-react";
import { apiGetList, apiPostObject } from "../../services/restApi";
import { resolveBranchId, resolveTenantId } from "../../utils/tenantContext";

type BranchRow = {
  id: number;
  name: string;
  code: string;
  is_main: boolean;
  is_active: boolean;
};

export const BranchSwitcher: React.FC = () => {
  const [branches, setBranches] = useState<BranchRow[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const activeBranchId = resolveBranchId();
  const activeBranch = branches.find((b) => b.id === activeBranchId) || null;

  useEffect(() => {
    apiGetList<BranchRow>("tenants/branches/", { tenantId: resolveTenantId() })
      .then((rows) => setBranches(rows.filter((b) => b.is_active)))
      .catch(() => setBranches([]));
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectBranch = (branchId: number | null) => {
    if (branchId === activeBranchId) {
      setIsOpen(false);
      return;
    }
    if (branchId == null) localStorage.removeItem("branchId");
    else localStorage.setItem("branchId", String(branchId));
    window.location.reload();
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !newCode.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await apiPostObject<BranchRow>(
        "tenants/branches/",
        { name: newName.trim(), code: newCode.trim().toUpperCase() },
        { tenantId: resolveTenantId() }
      );
      setShowModal(false);
      setNewName("");
      setNewCode("");
      selectBranch(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل إنشاء الفرع");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative inline-block text-right" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[var(--aseel-panel)] border border-[var(--aseel-border-soft)] hover:bg-[var(--aseel-panel-hover)] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[var(--aseel-accent)]"
        style={{ color: "var(--aseel-ink)" }}
        title="الفرع النشط"
      >
        <GitBranch className="w-3.5 h-3.5 opacity-70" />
        <span>{activeBranch ? activeBranch.name : "كل الفروع"}</span>
        <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-1.5 w-56 rounded-xl shadow-xl bg-[var(--aseel-bg)] border border-[var(--aseel-border)] z-50 overflow-hidden">
          <div className="px-4 py-2 bg-[var(--aseel-panel)] border-b border-[var(--aseel-border-soft)]">
            <span className="text-[11px] font-bold tracking-wider uppercase opacity-60">فروع الشركة</span>
          </div>

          <div className="max-h-56 overflow-y-auto py-1">
            <button
              type="button"
              onClick={() => selectBranch(null)}
              className={`w-full flex items-center justify-between px-4 py-2 text-xs text-right hover:bg-[var(--aseel-panel-hover)] ${activeBranchId == null ? "font-bold" : ""}`}
            >
              <span style={{ color: activeBranchId == null ? "var(--aseel-accent)" : "var(--aseel-ink)" }}>
                كل الفروع (مستوى الشركة)
              </span>
              {activeBranchId == null && <Check className="w-3.5 h-3.5 text-[var(--aseel-accent)]" />}
            </button>
            {branches.map((b) => {
              const isActive = b.id === activeBranchId;
              return (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => selectBranch(b.id)}
                  className={`w-full flex items-center justify-between px-4 py-2 text-xs text-right hover:bg-[var(--aseel-panel-hover)] ${isActive ? "font-bold" : ""}`}
                >
                  <span style={{ color: isActive ? "var(--aseel-accent)" : "var(--aseel-ink)" }}>
                    {b.name}
                    <span className="opacity-50 mr-1">[{b.code}]</span>
                    {b.is_main && <span className="opacity-50 mr-1">— رئيسي</span>}
                  </span>
                  {isActive && <Check className="w-3.5 h-3.5 text-[var(--aseel-accent)]" />}
                </button>
              );
            })}
          </div>

          <div className="border-t border-[var(--aseel-border-soft)] p-1.5 bg-[var(--aseel-panel)]">
            <button
              type="button"
              onClick={() => {
                setShowModal(true);
                setIsOpen(false);
              }}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-[11px] font-bold text-white rounded-lg bg-[var(--aseel-accent)] hover:opacity-90 transition-opacity"
            >
              <Plus className="w-3 h-3" />
              <span>إضافة فرع</span>
            </button>
          </div>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4">
          <div
            className="w-full max-w-sm rounded-2xl bg-[var(--aseel-bg)] border border-[var(--aseel-border)] shadow-2xl p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-base font-bold" style={{ color: "var(--aseel-ink)" }}>إضافة فرع جديد</h3>
              <button
                type="button"
                onClick={() => { setShowModal(false); setError(null); }}
                className="p-1 rounded-lg hover:bg-[var(--aseel-panel-hover)] opacity-70 hover:opacity-100"
              >
                <Plus className="w-4 h-4 rotate-45" />
              </button>
            </div>

            <p className="text-[11px] mb-4 opacity-70" style={{ color: "var(--aseel-ink)" }}>
              الفرع يشارك الشركة شجرة الحسابات والأصناف والعملاء، وله فواتير
              ومخزون وتقارير مالية مستقلة.
            </p>

            <form onSubmit={handleCreate} className="space-y-3">
              {error && (
                <div className="p-2.5 text-xs bg-[color-mix(in_srgb,var(--color-danger)_10%,transparent)] text-[var(--color-danger)] rounded-lg border border-[color-mix(in_srgb,var(--color-danger)_35%,transparent)] font-semibold">
                  {error}
                </div>
              )}
              <div className="space-y-1">
                <label className="text-xs font-bold opacity-80" htmlFor="branch-name">اسم الفرع</label>
                <input
                  id="branch-name"
                  type="text"
                  required
                  placeholder="مثال: فرع نابلس"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--aseel-border)] bg-[var(--aseel-panel)] focus:outline-none focus:ring-2 focus:ring-[var(--aseel-accent)]"
                  disabled={submitting}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold opacity-80" htmlFor="branch-code">رمز الفرع (يدخل في ترقيم الفواتير)</label>
                <input
                  id="branch-code"
                  type="text"
                  required
                  maxLength={20}
                  placeholder="مثال: NAB"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value.toUpperCase())}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--aseel-border)] bg-[var(--aseel-panel)] focus:outline-none focus:ring-2 focus:ring-[var(--aseel-accent)] font-mono"
                  disabled={submitting}
                />
              </div>
              <div className="flex gap-2 justify-end pt-1">
                <button
                  type="button"
                  onClick={() => { setShowModal(false); setError(null); }}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg hover:bg-[var(--aseel-panel-hover)]"
                  disabled={submitting}
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold text-white rounded-lg bg-[var(--aseel-accent)] hover:opacity-90"
                  disabled={submitting}
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>جاري الإنشاء...</span>
                    </>
                  ) : (
                    <span>إنشاء وتفعيل</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
