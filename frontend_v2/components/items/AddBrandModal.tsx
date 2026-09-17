import React, { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import type { AddBrandResult } from "../../services/inventoryApi";

type Props = {
  isOpen: boolean;
  productName: string;
  existingBrands: string[];
  onClose: () => void;
  onAdd: (brand: string) => Promise<AddBrandResult>;
  onAdded?: (result: AddBrandResult) => void;
};

export const AddBrandModal: React.FC<Props> = ({
  isOpen, productName, existingBrands, onClose, onAdd, onAdded,
}) => {
  const [brand, setBrand] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setBrand("");
    setError(null);
  }, [isOpen, productName]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, saving, onClose]);

  if (!isOpen) return null;

  const submit = async () => {
    const clean = brand.trim();
    if (!clean || saving) return;
    setSaving(true);
    setError(null);
    try {
      const result = await onAdd(clean);
      onAdded?.(result);
      onClose();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "تعذّرت إضافة البراند");
    } finally {
      setSaving(false);
    }
  };

  const visibleBrands = existingBrands.map((item) => item.trim()).filter(Boolean);

  return (
    <div
      className="ktra-overlay-mask fixed inset-0 z-[90] flex items-center justify-center p-4"
      dir="rtl"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-brand-title"
        className="w-full max-w-md overflow-hidden rounded-lg border border-[var(--ktra-border)] bg-[var(--ktra-panel)] shadow-xl"
      >
        <div className="flex items-center gap-2 border-b border-[var(--ktra-border-soft)] px-4 py-3">
          <h2 id="add-brand-title" className="min-w-0 flex-1 truncate font-bold text-[var(--ktra-ink)]">
            براند جديد لـ«{productName || "المنتج"}»
          </h2>
          <button
            type="button"
            className="ktra-iconbtn"
            onClick={onClose}
            disabled={saving}
            aria-label="إغلاق نافذة إضافة البراند"
            title="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div>
            <div className="mb-1 text-xs font-bold text-[var(--ktra-ink-soft)]">البراندات الموجودة</div>
            <div className="flex flex-wrap gap-1.5">
              {visibleBrands.length ? visibleBrands.map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-[var(--ktra-accent-bd)] bg-[var(--ktra-accent-bg)] px-2.5 py-1 text-xs font-medium text-[var(--ktra-ink)]"
                >
                  {item}
                </span>
              )) : (
                <span className="rounded-full border border-[var(--ktra-border-soft)] px-2.5 py-1 text-xs text-[var(--ktra-ink-soft)]">
                  بلا براند
                </span>
              )}
            </div>
          </div>

          {error && (
            <div role="alert" className="rounded border border-[var(--ktra-danger-bd)] bg-[var(--ktra-danger-bg)] px-3 py-2 text-sm text-[var(--ktra-danger)]">
              {error}
            </div>
          )}

          <label className="ktra-field">
            <span className="ktra-field-label">اسم البراند الجديد</span>
            <input
              autoFocus
              className="ktra-input"
              value={brand}
              disabled={saving}
              placeholder="مثال: ميشلان"
              onChange={(event) => setBrand(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void submit();
                }
              }}
            />
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t border-[var(--ktra-border-soft)] bg-[var(--ktra-surface-2)] px-4 py-3">
          <button type="button" className="ktra-btn" onClick={onClose} disabled={saving}>
            إلغاء
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            onClick={() => void submit()}
            disabled={saving || !brand.trim()}
          >
            <Plus className="h-4 w-4" /> {saving ? "جارٍ الإضافة…" : "إضافة"}
          </button>
        </div>
      </div>
    </div>
  );
};
