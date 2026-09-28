import React, { useState } from "react";
import { Loader2, X } from "lucide-react";
import {
  createManufacturerWarrantor,
  updateManufacturerWarrantor,
  type ManufacturerWarrantorDraft,
  type ManufacturerWarrantorRow,
} from "../../services/afterSalesApi";

/**
 * #230 — جهة كفالة مصنع واحدة: إنشاء أو تعديل. لا حذف من هنا — الحذف يُرفض
 * خادمياً لجهةٍ مرتبطة، والأرشفة (`is_active=False`) هي أداة إيقاف التعامل.
 */

interface Props {
  warrantor: ManufacturerWarrantorRow | null;
  onClose: () => void;
  onSaved: () => void;
}

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const fieldClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const emptyDraft = (): ManufacturerWarrantorDraft => ({
  name: "", service_center_address: "", phone: "", notes: "", is_active: true,
});

const draftOf = (row: ManufacturerWarrantorRow): ManufacturerWarrantorDraft => ({
  name: row.name,
  service_center_address: row.service_center_address,
  phone: row.phone,
  notes: row.notes,
  is_active: row.is_active,
});

export const ManufacturerWarrantorModal: React.FC<Props> = ({ warrantor, onClose, onSaved }) => {
  const [draft, setDraft] = useState<ManufacturerWarrantorDraft>(() =>
    warrantor ? draftOf(warrantor) : emptyDraft());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const patch = <K extends keyof ManufacturerWarrantorDraft>(
    key: K, value: ManufacturerWarrantorDraft[K],
  ) => setDraft((d) => ({ ...d, [key]: value }));

  const save = async () => {
    if (!draft.name.trim()) {
      setErr("اسم جهة الكفالة مطلوب");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const payload: ManufacturerWarrantorDraft = {
        ...draft,
        name: draft.name.trim(),
        service_center_address: draft.service_center_address.trim(),
        phone: draft.phone.trim(),
      };
      if (warrantor) {
        await updateManufacturerWarrantor(warrantor.id, payload);
      } else {
        await createManufacturerWarrantor(payload);
      }
      onSaved();
      onClose();
    } catch (e) {
      setErr(messageOf(e, "تعذّر حفظ جهة الكفالة"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label={warrantor ? "تعديل جهة كفالة المصنع" : "جهة كفالة مصنع جديدة"}
      className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
    >
      <div className="w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
          <span className="truncate font-bold text-[var(--color-text)]">
            {warrantor ? `تعديل — ${warrantor.name}` : "جهة كفالة مصنع جديدة"}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="إغلاق"
            aria-label="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 p-3 md:p-4">
          {err && (
            <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          )}

          <div>
            <label className={labelClass} htmlFor="warrantor-name">اسم الجهة</label>
            <input
              id="warrantor-name"
              className={fieldClass}
              value={draft.name}
              onChange={(e) => patch("name", e.target.value)}
              placeholder="مثال: الوكيل الرسمي"
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="warrantor-address">عنوان مركز الخدمة</label>
            <input
              id="warrantor-address"
              className={fieldClass}
              value={draft.service_center_address}
              onChange={(e) => patch("service_center_address", e.target.value)}
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="warrantor-phone">الهاتف</label>
            <input
              id="warrantor-phone"
              className={fieldClass}
              inputMode="tel"
              value={draft.phone}
              onChange={(e) => patch("phone", e.target.value)}
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="warrantor-notes">ملاحظات</label>
            <textarea
              id="warrantor-notes"
              rows={2}
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-sm text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              value={draft.notes}
              onChange={(e) => patch("notes", e.target.value)}
            />
          </div>

          {warrantor && (
            <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(e) => patch("is_active", e.target.checked)}
              />
              مفعَّلة — نتعامل معها حالياً
              <span className="text-[11px] text-[var(--color-text-muted)]">
                (أرشفة بدل حذف: تعطيل الخانة لا يحذف الجهة ولا يمسّ ما ارتبط بها)
              </span>
            </label>
          )}
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-[var(--color-border)] p-3 sm:flex-row sm:items-center">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50 sm:w-32"
          >
            إغلاق
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={busy}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            حفظ
          </button>
        </div>
      </div>
    </div>
  );
};

export default ManufacturerWarrantorModal;
