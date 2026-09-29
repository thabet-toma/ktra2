import React, { useState } from "react";
import { PackageX } from "lucide-react";
import { useConfirm } from "../../contexts/ConfirmContext";
import {
  returnedUnitActions,
  returnedUnitLabel,
  returnedUnitNoteValid,
  type ReturnedUnitAction,
  type ReturnedUnitTarget,
} from "../../utils/warranty";

interface Props {
  state: string;
  serial: string;
  canEdit: boolean;
  canPost: boolean;
  busy: boolean;
  onApply: (target: ReturnedUnitTarget, note: string) => Promise<void>;
}

const CONFIRM_TEXT: Partial<Record<ReturnedUnitTarget, string>> = {
  restocked: "يعود الجهاز إلى المخزن بكلفة مُسجَّلة ويُرحَّل قيد استرداد. متابعة؟",
  held: "يُعكس دخول الجهاز للمخزن وقيده، ويعود معطوباً على بيعه الأصلي. متابعة؟",
  disposed: "الإتلاف نهائي ولا يُتراجع عنه. متابعة؟",
};

/** #246 — مصير الجهاز المعطوب على مستند الأمر المُسلَّم باستبدال. */
export const ReturnedUnitBox: React.FC<Props> = ({
  state, serial, canEdit, canPost, busy, onApply,
}) => {
  const confirm = useConfirm();
  const [note, setNote] = useState("");
  const actions = returnedUnitActions(state);
  const allowed = (action: ReturnedUnitAction) => (action.touchesMoney ? canPost : canEdit);

  const apply = async (action: ReturnedUnitAction) => {
    if (!returnedUnitNoteValid(action, note)) return;
    const text = CONFIRM_TEXT[action.target];
    if (text) {
      const ok = await confirm({ title: action.label, message: text });
      if (!ok) return;
    }
    await onApply(action.target, note.trim());
    setNote("");
  };

  return (
    <section
      className="space-y-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4"
      data-testid="returned-unit-box"
    >
      <div className="flex flex-wrap items-center gap-2">
        <PackageX className="h-4 w-4 text-[var(--color-primary)]" />
        <span className="text-sm font-bold text-[var(--color-text)]">مصير الجهاز المعطوب</span>
        {serial && <span className="text-[11px] text-[var(--color-text-muted)]">{serial}</span>}
        <span
          className="rounded-full bg-[var(--color-surface-2)] px-2 py-0.5 text-[11px] font-bold text-[var(--color-text)]"
          data-testid="returned-unit-state"
        >
          {returnedUnitLabel(state)}
        </span>
      </div>

      {actions.length > 0 && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[14rem] flex-1">
            <label className="mb-1 block text-[11px] text-[var(--color-text-muted)]" htmlFor="returned-unit-note">
              ملاحظة (إلزامية عند الإتلاف)
            </label>
            <input
              id="returned-unit-note"
              className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              value={note}
              maxLength={300}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          {actions.map((action) => (
            <button
              key={action.target}
              type="button"
              disabled={busy || !allowed(action) || !returnedUnitNoteValid(action, note)}
              title={allowed(action) ? undefined : "لا تملك صلاحية هذا الإجراء"}
              onClick={() => void apply(action)}
              className={`rounded-lg border px-3 py-2 text-sm font-bold disabled:opacity-40 ${
                action.destructive
                  ? "border-red-300 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
                  : "border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
              }`}
              data-testid={`returned-unit-${action.target}`}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </section>
  );
};

export default ReturnedUnitBox;
