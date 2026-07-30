import React, { useState, useRef, useEffect } from "react";
import {
  Printer,
  RefreshCw,
  PlusCircle,
  ChevronDown,
  ChevronUp,
  GripVertical
} from "lucide-react";
import { AppView, User } from "../../types";
import { clientLogger } from "../../services/logger";
import {
  buildQuickActionGroups,
  visibleQuickActionGroups,
  setQuickActionsOrder,
  QuickAction,
} from "./quickActions";

/** يطوي/يفتح شريط الإجراءات السريعة كاملاً — حالة محفوظة محلياً بين الجلسات. */
const COLLAPSE_KEY = "ktra:quickActionsBarCollapsed";

interface Props {
  user: User;
  onNavigate: (view: AppView, targetId?: string) => void;
}

export const GlobalActionBar: React.FC<Props> = ({ user, onNavigate }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; }
  });
  const [orderVersion, setOrderVersion] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const dragKeyRef = useRef<string | null>(null);

  const toggleCollapsed = () => {
    setIsOpen(false);
    setCollapsed((prev) => {
      const next = !prev;
      try { localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0"); } catch { /* تجاهل */ }
      return next;
    });
  };

  const go = (view: AppView, id?: string) => () => {
    onNavigate(view, id);
    setIsOpen(false);
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // orderVersion يُغيَّر بعد كل سحب فقط لإجبار إعادة التصيير — visibleGroups تُقرأ من localStorage بكل مرة أصلاً.
  const visibleGroups = visibleQuickActionGroups(buildQuickActionGroups(user, go));

  if (visibleGroups.length === 0) return null;

  // إعادة ترتيب أيقونات الإجراءات السريعة بالسحب — يُحفظ محلياً فيُطبَّق أيضاً على قائمة زر الفأرة اليمنى.
  const handleDragStart = (key: string) => (e: React.DragEvent) => {
    dragKeyRef.current = key;
    e.dataTransfer.effectAllowed = "move";
  };
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };
  const handleDrop = (groupIndex: number, targetKey: string) => (e: React.DragEvent) => {
    e.preventDefault();
    const draggedKey = dragKeyRef.current;
    dragKeyRef.current = null;
    if (!draggedKey || draggedKey === targetKey) return;
    const reorderedGroups = visibleGroups.map((g: QuickAction[], gi: number) => {
      if (gi !== groupIndex) return g;
      const keys = g.map((a) => a.key);
      const from = keys.indexOf(draggedKey);
      const to = keys.indexOf(targetKey);
      if (from === -1 || to === -1) return g;
      const arr = [...g];
      const [moved] = arr.splice(from, 1);
      arr.splice(to, 0, moved);
      return arr;
    });
    setQuickActionsOrder(reorderedGroups.flat().map((a) => a.key));
    clientLogger.info("app.quick_action_reordered");
    setOrderVersion((v) => v + 1);
  };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={toggleCollapsed}
        className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-primary-emphasis)] hover:bg-[var(--color-surface-2)] rounded-lg transition-colors"
        title="إظهار شريط الإجراءات السريعة"
      >
        <ChevronDown className="w-4 h-4" />
      </button>
    );
  }

  return (
    <div className="relative flex items-center gap-1.5" ref={menuRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-[var(--color-primary)] text-white hover:opacity-90 shadow-sm"
        title="إجراءات سريعة"
      >
        <PlusCircle className="w-4 h-4" />
        <span className="hidden sm:inline">إجراءات سريعة</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Quick single-click icons for Print & Refresh */}
      <button
        type="button"
        onClick={() => {
          clientLogger.info("app.print_requested");
          window.print();
        }}
        className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-primary-emphasis)] hover:bg-[var(--color-surface-2)] rounded-lg transition-colors ml-1"
        title="طباعة"
      >
        <Printer className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-primary-emphasis)] hover:bg-[var(--color-surface-2)] rounded-lg transition-colors"
        title="تحديث"
      >
        <RefreshCw className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={toggleCollapsed}
        className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-primary-emphasis)] hover:bg-[var(--color-surface-2)] rounded-lg transition-colors"
        title="إخفاء شريط الإجراءات السريعة"
      >
        <ChevronUp className="w-4 h-4" />
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-56 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-lg z-50 py-2">
          {visibleGroups.map((group, gi) => (
            <React.Fragment key={gi}>
              {gi > 0 && <div className="h-px bg-[var(--color-border)] my-1.5 mx-3" />}
              <div className="px-1.5">
                {group.map((a) => (
                  <button
                    key={a.key}
                    type="button"
                    draggable
                    onDragStart={handleDragStart(a.key)}
                    onDragOver={handleDragOver}
                    onDrop={handleDrop(gi, a.key)}
                    onClick={a.onClick}
                    title="اسحب لإعادة الترتيب"
                    className="flex items-center gap-2 w-full px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-primary-emphasis)] rounded-md transition-colors cursor-grab active:cursor-grabbing"
                  >
                    <GripVertical className="w-3.5 h-3.5 text-[var(--color-text-muted)]/60 flex-shrink-0" />
                    <span className="text-[var(--color-primary-emphasis)] flex-shrink-0">{a.icon}</span>
                    <span className="truncate">{a.label}</span>
                  </button>
                ))}
              </div>
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
};
