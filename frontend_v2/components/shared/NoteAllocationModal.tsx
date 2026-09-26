/**
 * NoteAllocationModal — توزيع الإشعار المسوّي على مستندات طرفه (كالسند تماماً).
 *
 * المدين على دائن يُطفئ فواتير شرائه ومستحقّاته اللوجستية، والدائن على عميل يُطفئ فواتير
 * بيعه (`sales/services/note_allocation.py`). النافذة نافذةُ السند نفسها
 * (`VoucherAllocationModal`) بمصدرٍ آخر، وفوقها توزيعاتُه القائمة مع «فكّ» لكلٍّ منها.
 * يفتحها كرت الطرف (فائض تحت الحساب) وشاشة الإشعارات.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Unlink } from "lucide-react";
import { formatMoney } from "@/utils/formatNumber";
import { humanizeThrown } from "@/utils/drfError";
import { clientLogger } from "../../services/logger";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import { VoucherAllocationModal } from "./VoucherAllocationModal";
import {
  allocateCreditDebitNote,
  deallocateCreditDebitNote,
  getNoteAllocationTargets,
  type NoteAllocationPayload,
} from "../../services/salesApi";
import { noteAllocationRows, noteTargetDocs } from "../../utils/voucherAllocation";

interface Props {
  noteId: number;
  partnerLabel: string;
  onClose: () => void;
  /** بعد توزيعٍ أو فكٍّ ناجح — ليحدّث المستدعي أرصدته. */
  onSaved: () => void;
}

export const NoteAllocationModal: React.FC<Props> = ({ noteId, partnerLabel, onClose, onSaved }) => {
  const [payload, setPayload] = useState<NoteAllocationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyAllocation, setBusyAllocation] = useState<number | null>(null);
  const [changed, setChanged] = useState(false);

  const load = useCallback(async () => {
    try {
      setPayload(await getNoteAllocationTargets(noteId));
      setError(null);
    } catch (e: unknown) {
      setError(humanizeThrown(e, "تعذّر تحميل مستندات الطرف"));
    }
  }, [noteId]);

  useEffect(() => { void load(); }, [load]);

  const close = () => (changed ? onSaved() : onClose());

  if (!payload) {
    return (
      <PaymentVoucherModal title="توزيع الإشعار" error={error} submitting={false} disabled submitLabel="توزيع" onClose={onClose} onSubmit={() => undefined}>
        {!error && (
          <div className="flex items-center justify-center gap-2 p-6 text-[12px] text-[var(--ktra-ink-soft)]">
            <Loader2 className="h-4 w-4 animate-spin" /> جاري التحميل…
          </div>
        )}
      </PaymentVoucherModal>
    );
  }

  const { note } = payload;
  const creditor = Boolean(note.is_creditor);

  const release = async (allocationKind: "invoice" | "accrual", allocationId: number) => {
    setBusyAllocation(allocationId);
    try {
      setPayload(await deallocateCreditDebitNote(noteId, allocationKind, allocationId));
      setChanged(true);
      setError(null);
      clientLogger.info("credit_debit_note.deallocate", { allocation_kind: allocationKind });
    } catch (e: unknown) {
      setError(humanizeThrown(e, "تعذّر فكّ التوزيع"));
    } finally {
      setBusyAllocation(null);
    }
  };

  const existing = (
    <div className="mb-2">
      {error && <div className="mb-2 text-[11px] text-[var(--ktra-err)]">{error}</div>}
      <div className="mb-1 text-[12px] font-semibold">
        إشعار {note.note_number} — {formatMoney(note.amount)} {note.currency_code || ""}
      </div>
      {payload.allocations.length > 0 && (
        <table className="w-full text-[11px]">
          <thead className="bg-[var(--ktra-surface-2)]">
            <tr>
              <th className="p-1 text-right">موزَّعٌ على</th>
              <th className="p-1 text-right">المبلغ</th>
              <th className="w-[60px] p-1" />
            </tr>
          </thead>
          <tbody>
            {payload.allocations.map((a) => (
              <tr key={`${a.allocation_kind}:${a.allocation_id}`} className="border-t border-[var(--ktra-border)]">
                <td className="p-1">{a.label}</td>
                <td className="ktra-num p-1">{formatMoney(a.amount)}</td>
                <td className="p-1 text-center">
                  <button
                    type="button"
                    className="ktra-toolbtn text-[11px]"
                    title="فكّ التوزيع — يعود المبلغ تحت الحساب"
                    disabled={busyAllocation !== null}
                    onClick={() => void release(a.allocation_kind, a.allocation_id)}
                  >
                    {busyAllocation === a.allocation_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Unlink className="h-3 w-3" />} فكّ
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );

  return (
    <VoucherAllocationModal
      // مفتاحٌ بالمتاح: بعد الفكّ تُعاد الصفوف الجديدة على المتاح الجديد.
      key={payload.unallocated}
      kind={creditor ? "supplier" : "customer"}
      title={`توزيع إشعار ${note.note_number} — ${partnerLabel}`}
      sourceNoun="الإشعار"
      voucher={{
        id: note.id,
        amount: note.amount,
        unallocated: Number(payload.unallocated) || 0,
        is_posted: note.status === "posted",
      }}
      partnerLabel={partnerLabel}
      docs={noteTargetDocs(payload.targets)}
      summary={existing}
      onSubmitRows={async (rows) => {
        await allocateCreditDebitNote(noteId, noteAllocationRows(rows, creditor ? "purchase_invoice" : "sales_invoice"));
        clientLogger.info("credit_debit_note.allocate", { rows: rows.length });
      }}
      onClose={close}
      onSaved={onSaved}
    />
  );
};

export default NoteAllocationModal;
