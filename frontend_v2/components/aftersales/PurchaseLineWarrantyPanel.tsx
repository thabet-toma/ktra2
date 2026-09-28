import React, { useEffect, useMemo, useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import {
  listPurchaseLinePolicies,
  lookupManufacturerWarrantors,
  savePurchaseLineWarranties,
  type ManufacturerWarrantorRow,
  type PurchaseLinePolicyRow,
} from "../../services/afterSalesApi";
import type { InvoiceItem } from "../../types/invoice";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useToast } from "../../contexts/ToastContext";
import { formatNumber } from "../../utils/formatNumber";
import {
  LINE_WARRANTY_MAX_MONTHS,
  purchaseLineWarrantyDiffers,
  purchaseLineWarrantyFromPolicy,
  purchaseLineWarrantyPayload,
  purchaseLineWarrantyProblem,
  type PurchaseLineWarrantyValue,
} from "../../utils/warranty";
import { useProductWarrantyPolicyVisible } from "./ProductWarrantyPolicyLine";

/**
 * #235 — «كفالة المصنع» لكل سطر شراء بمنتجٍ سياسته `serial`: تُملأ من السياسة
 * ويعدّلها المستخدم على السطر. لوحةٌ تحت جدول البنود لا عمودٌ فيه، فتخدم
 * الفاتورة المحلية والدولية بمكوّنٍ واحد.
 *
 * المسودة تُحفظ مع الفاتورة (`extensions` على البند). الفاتورة المرحّلة تُصحَّح
 * عبر نقطتها المستقلة لمن يملك `aftersales.warranty.manage` — البطاقات الصادرة
 * لا تُمسّ، والتصحيح يسري على مبيعاتٍ لاحقة.
 */

interface Props {
  items: InvoiceItem[];
  readOnly: boolean;
  posted: boolean;
  invoiceId?: number;
  /** كفالة المورّد في الصفقة بالسنوات — تملأ `supplier_months` مسبقاً (واجهةٌ فقط). */
  dealWarrantyYears?: unknown;
  onChange: (itemId: string, value: PurchaseLineWarrantyValue) => void;
  /** يضبط القيم دون تعليم الفاتورة معدَّلة (تعبئةٌ ابتدائية أو ما بعد حفظ التصحيح). */
  onPrefill: (values: Record<string, PurchaseLineWarrantyValue>) => void;
}

const fieldClass =
  "h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

export const PurchaseLineWarrantyPanel: React.FC<Props> = ({
  items, readOnly, posted, invoiceId, dealWarrantyYears, onChange, onPrefill,
}) => {
  const visible = useProductWarrantyPolicyVisible();
  const { can } = usePermissions();
  const toast = useToast();

  const [policies, setPolicies] = useState<Record<string, PurchaseLinePolicyRow | null>>({});
  const [warrantors, setWarrantors] = useState<ManufacturerWarrantorRow[]>([]);
  const [edits, setEdits] = useState<Record<string, PurchaseLineWarrantyValue>>({});
  const [busy, setBusy] = useState(false);

  const productIds = useMemo(
    () => Array.from(new Set(items.map((i) => i.itemId).filter(Boolean))),
    [items],
  );

  useEffect(() => {
    if (!visible) return;
    const missing = productIds.filter((id) => !(id in policies));
    if (missing.length === 0) return;
    let cancelled = false;
    // نداءٌ واحد لكل المنتجات الجديدة؛ منتجٌ بلا سياسة يُسجَّل `null` فلا يُطلب ثانيةً.
    const settle = (rows: PurchaseLinePolicyRow[]) => {
      if (cancelled) return;
      const byProduct = new Map(rows.map((row) => [String(row.product), row]));
      setPolicies((p) => {
        const next = { ...p };
        missing.forEach((id) => { next[id] = byProduct.get(String(id)) || null; });
        return next;
      });
    };
    listPurchaseLinePolicies(missing.map(Number)).then(settle).catch(() => settle([]));
    return () => { cancelled = true; };
  }, [visible, productIds, policies]);

  const serialRows = useMemo(
    () => items
      .map((item) => ({ item, policy: policies[item.itemId] }))
      .filter((row): row is { item: InvoiceItem; policy: PurchaseLinePolicyRow } =>
        Boolean(row.policy) && row.policy?.method === "serial"),
    [items, policies],
  );

  const hasSerialRows = serialRows.length > 0;
  useEffect(() => {
    if (!hasSerialRows) return;
    lookupManufacturerWarrantors().then(setWarrantors).catch(() => setWarrantors([]));
  }, [hasSerialRows]);

  const canEditDraft = !posted && !readOnly;
  const canEditPosted = posted && can("aftersales.warranty.manage");
  const editable = canEditDraft || canEditPosted;

  useEffect(() => {
    if (!canEditDraft) return;
    const fresh: Record<string, PurchaseLineWarrantyValue> = {};
    serialRows.forEach(({ item, policy }) => {
      if (item.manufacturerWarranty === undefined) {
        fresh[item.id] = purchaseLineWarrantyFromPolicy(policy, dealWarrantyYears);
      }
    });
    if (Object.keys(fresh).length > 0) onPrefill(fresh);
  }, [canEditDraft, serialRows, dealWarrantyYears, onPrefill]);

  if (!visible || serialRows.length === 0) return null;

  const valueOf = (item: InvoiceItem, policy: PurchaseLinePolicyRow): PurchaseLineWarrantyValue =>
    edits[item.id] ?? item.manufacturerWarranty ?? purchaseLineWarrantyFromPolicy(policy, dealWarrantyYears);

  const update = (item: InvoiceItem, next: PurchaseLineWarrantyValue) => {
    if (canEditPosted) {
      setEdits((e) => ({ ...e, [item.id]: next }));
    } else {
      onChange(item.id, next);
    }
  };

  const warrantorLabel = (id: number | null) => {
    if (id === null) return "لا يوجد";
    return warrantors.find((w) => w.id === id)?.name || `جهة #${id}`;
  };

  const numberOrNull = (raw: string) => (raw === "" ? null : Number(raw));

  const savePosted = async () => {
    if (!invoiceId) return;
    const lines = [] as Array<PurchaseLineWarrantyValue & { item: number }>;
    for (const { item } of serialRows) {
      const edited = edits[item.id];
      if (!edited || !item.serverId) continue;
      const problem = purchaseLineWarrantyProblem(edited);
      if (problem) {
        toast(`${item.name}: ${problem}`, "error");
        return;
      }
      lines.push({ item: item.serverId, ...purchaseLineWarrantyPayload(edited) });
    }
    if (lines.length === 0) return;
    setBusy(true);
    try {
      await savePurchaseLineWarranties(invoiceId, lines);
      const saved: Record<string, PurchaseLineWarrantyValue> = {};
      Object.keys(edits).forEach((key) => { saved[key] = purchaseLineWarrantyPayload(edits[key]); });
      onPrefill(saved);
      setEdits({});
      toast("حُفظت كفالة المصنع على السطور — البطاقات الصادرة سابقاً لم تتغيّر", "success");
    } catch (e) {
      toast(messageOf(e, "تعذّر حفظ كفالة المصنع"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      dir="rtl"
      aria-label="كفالة المصنع على البنود"
      className="mt-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <ShieldCheck className="h-4 w-4 text-[var(--color-text-muted)]" />
        <span className="text-sm font-bold text-[var(--color-text)]">كفالة المصنع</span>
        <span className="text-[11px] text-[var(--color-text-muted)]">
          تُملأ من سياسة المنتج — عدّلها إن اختلفت كفالة هذه الشحنة
        </span>
      </div>

      <div className="space-y-2">
        {serialRows.map(({ item, policy }) => {
          const value = valueOf(item, policy);
          const differs = purchaseLineWarrantyDiffers(value, policy);
          return (
            <div
              key={item.id}
              className="grid grid-cols-1 items-end gap-2 rounded-lg bg-[var(--color-surface-2)] p-2 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1.4fr)_7rem_7rem]"
            >
              <div className="min-w-0">
                <div className="truncate text-sm text-[var(--color-text)]">{item.name}</div>
                {differs && (
                  <span className="mt-0.5 inline-block rounded-full border border-[var(--color-border)] px-2 text-[11px] text-[var(--color-primary)]">
                    يختلف عن السياسة
                  </span>
                )}
              </div>

              <div>
                <label className={labelClass} htmlFor={`plw-warrantor-${item.id}`}>جهة كفالة المصنع</label>
                {editable ? (
                  <select
                    id={`plw-warrantor-${item.id}`}
                    className={fieldClass}
                    value={value.manufacturer_warrantor ?? ""}
                    onChange={(e) => {
                      const id = e.target.value ? Number(e.target.value) : null;
                      update(item, {
                        ...value,
                        manufacturer_warrantor: id,
                        manufacturer_months: id === null ? 0 : value.manufacturer_months,
                      });
                    }}
                  >
                    <option value="">لا يوجد</option>
                    {value.manufacturer_warrantor !== null
                      && !warrantors.some((w) => w.id === value.manufacturer_warrantor) && (
                        <option value={value.manufacturer_warrantor}>
                          {warrantorLabel(value.manufacturer_warrantor)}
                        </option>
                      )}
                    {warrantors.map((w) => (
                      <option key={w.id} value={w.id}>{w.name}</option>
                    ))}
                  </select>
                ) : (
                  <div className="text-sm text-[var(--color-text)]">
                    {warrantorLabel(value.manufacturer_warrantor)}
                  </div>
                )}
              </div>

              <div>
                <label className={labelClass} htmlFor={`plw-months-${item.id}`}>مدة المصنع (أشهر)</label>
                {editable ? (
                  <input
                    id={`plw-months-${item.id}`}
                    type="number" min="0" max={LINE_WARRANTY_MAX_MONTHS} className={fieldClass}
                    disabled={value.manufacturer_warrantor === null}
                    value={value.manufacturer_months}
                    onChange={(e) => update(item, {
                      ...value, manufacturer_months: Number(e.target.value) || 0,
                    })}
                  />
                ) : (
                  <div className="text-sm text-[var(--color-text)]">
                    {formatNumber(value.manufacturer_months)}
                  </div>
                )}
              </div>

              <div>
                <label className={labelClass} htmlFor={`plw-supplier-${item.id}`}>كفالة المورّد (أشهر)</label>
                {editable ? (
                  <input
                    id={`plw-supplier-${item.id}`}
                    type="number" min="0" max={LINE_WARRANTY_MAX_MONTHS} className={fieldClass}
                    value={value.supplier_months ?? ""}
                    onChange={(e) => update(item, {
                      ...value, supplier_months: numberOrNull(e.target.value),
                    })}
                  />
                ) : (
                  <div className="text-sm text-[var(--color-text)]">
                    {value.supplier_months === null ? "—" : formatNumber(value.supplier_months)}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {canEditPosted && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void savePosted()}
            disabled={busy || Object.keys(edits).length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            حفظ كفالة المصنع
          </button>
          <span className="text-[11px] text-[var(--color-text-muted)]">
            التصحيح يسري على مبيعاتٍ لاحقة؛ البطاقات الصادرة لا تتغيّر.
          </span>
        </div>
      )}
    </section>
  );
};

export default PurchaseLineWarrantyPanel;
