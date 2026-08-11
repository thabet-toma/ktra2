import React from "react";
import { Plus, Minus, PencilLine } from "lucide-react";
import type { ActivityChange, ActivityFieldChange } from "@/types/activity";

/** «من ← إلى» بشكل موحّد: القديم مشطوب باهت، والجديد بارز. */
const ValuePair: React.FC<{ change: ActivityFieldChange }> = ({ change }) => (
  <span className="inline-flex items-center gap-1 whitespace-nowrap">
    <span className="aseel-text-soft line-through">{change.old || "—"}</span>
    <span className="aseel-text-soft">←</span>
    <span className="font-semibold text-[var(--color-text)]">{change.new || "—"}</span>
  </span>
);

const rowCls = "flex items-start gap-1.5 text-xs leading-5";

/** تفصيل حركة المستند في سجل النشاط: أي بند أُضيف/حُذف وأي قيمة تغيّرت. */
export const ActivityChanges: React.FC<{ changes: ActivityChange[] }> = ({ changes }) => (
  <ul className="space-y-1">
    {changes.map((change, index) => {
      const kind = change.kind || "field";
      if (kind === "line_added" || kind === "line_removed") {
        const added = kind === "line_added";
        const { label, values } = change as Extract<ActivityChange, { values: unknown }>;
        return (
          <li key={index} className={rowCls}>
            {added ? (
              <Plus className="w-3.5 h-3.5 mt-0.5 shrink-0 text-green-600" />
            ) : (
              <Minus className="w-3.5 h-3.5 mt-0.5 shrink-0 text-red-600" />
            )}
            <span>
              <span className={added ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}>
                {added ? "أضاف" : "حذف"}
              </span>{" "}
              <span className="font-semibold text-[var(--color-text)]">{label}</span>
              {values.length > 0 && (
                <span className="aseel-text-soft">
                  {" "}({values.map((v) => `${v.label} ${v.value}`).join(" · ")})
                </span>
              )}
            </span>
          </li>
        );
      }
      if (kind === "line_changed") {
        const { label, changes: fields } = change as Extract<ActivityChange, { kind: "line_changed" }>;
        return (
          <li key={index} className={rowCls}>
            <PencilLine className="w-3.5 h-3.5 mt-0.5 shrink-0 text-blue-600" />
            <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="font-semibold text-[var(--color-text)]">{label}</span>
              {fields.map((field) => (
                <span key={field.field} className="inline-flex items-center gap-1">
                  <span className="aseel-text-soft">{field.label}:</span>
                  <ValuePair change={field} />
                </span>
              ))}
            </span>
          </li>
        );
      }
      const field = change as ActivityFieldChange;
      return (
        <li key={index} className={rowCls}>
          <PencilLine className="w-3.5 h-3.5 mt-0.5 shrink-0 aseel-text-soft" />
          <span className="inline-flex items-center gap-1 flex-wrap">
            <span className="aseel-text-soft">{field.label}:</span>
            <ValuePair change={field} />
          </span>
        </li>
      );
    })}
  </ul>
);
