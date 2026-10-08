import React, { useEffect, useState } from "react";
import { useMissingProducts } from "../../hooks/useMissingDocumentRecords";
import { Loader2, Package, X } from "lucide-react";
import {
  createWarrantyPolicy,
  getWarrantySerialImpact,
  lookupManufacturerWarrantors,
  updateWarrantyPolicy,
  type ManufacturerWarrantorRow,
  type WarrantyPolicyDraft,
  type WarrantyPolicyMethod,
  type WarrantyPolicyRow,
} from "../../services/afterSalesApi";
import {
  SalesProductPickerModal, type SalesProductPickerItem,
} from "../sales/SalesProductPickerModal";
import { useConfirm } from "../../contexts/ConfirmContext";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { serialImpactConfirmationLines, serialImpactNeedsConfirmation } from "../../utils/warranty";

/**
 * #231 — سياسة كفالة براندٍ واحد: إنشاء أو تعديل. صفٌّ واحد لكل منتج
 * (`OneToOneField`)، فالمنتقي هنا لا يعرض إلا براندات بلا سياسة قائمة عند
 * الإنشاء؛ التعديل مقفلُ المنتج — تغييره يعني سياسةً لبراندٍ آخر، لا تعديل هذه.
 */

interface ProductOption extends SalesProductPickerItem {
  is_serialized?: boolean;
  /** T4: موقوف — يصل من جلب منتج السياسة القائمة لا من المنتقي (نشطٌ فقط). */
  is_active?: boolean;
}

interface Props {
  policy: WarrantyPolicyRow | null;
  products: ProductOption[];
  onClose: () => void;
  onSaved: () => void;
}

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const fieldClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const TERMS_MAX_LENGTH = 2000;

const emptyDraft = (): WarrantyPolicyDraft => ({
  product: 0,
  method: "serial",
  dealer_months: 0,
  manufacturer_warrantor: null,
  manufacturer_months: 0,
  supplier_months: 0,
  terms_override: "",
});

const draftOf = (row: WarrantyPolicyRow): WarrantyPolicyDraft => ({
  product: row.product,
  method: row.method,
  dealer_months: row.dealer_months,
  manufacturer_warrantor: row.manufacturer_warrantor,
  manufacturer_months: row.manufacturer_months,
  supplier_months: row.supplier_months,
  terms_override: row.terms_override,
});

export const WarrantyPolicyModal: React.FC<Props> = ({ policy, products, onClose, onSaved }) => {
  const confirm = useConfirm();
  const [draft, setDraft] = useState<WarrantyPolicyDraft>(() =>
    policy ? draftOf(policy) : emptyDraft());
  const [pickedProduct, setPickedProduct] = useState<ProductOption | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [warrantors, setWarrantors] = useState<ManufacturerWarrantorRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    lookupManufacturerWarrantors().then(setWarrantors).catch(() => setWarrantors([]));
  }, []);

  /* T4: سياسة كفالة قائمة لبراندٍ أُوقف بعد وضعها غاب عن المنتقي (نشطٌ فقط) — فكان
     `pickedProduct` فارغاً: يضيع اسمه في معاينة أثر الرقم التسلسلي ويضيع `is_service` فتُتاح
     له طريقة «برقم تسلسلي» وهو خدمة. يُجلب فرداً للقراءة وحدها؛ منتقي البراند الجديد على `products`. */
  const heldProducts = useMissingProducts<ProductOption>([policy?.product], products);
  useEffect(() => {
    if (!policy) return;
    setPickedProduct(
      products.find((p) => p.id === policy.product)
        || heldProducts.find((p) => p.id === policy.product)
        || null,
    );
  }, [policy, products, heldProducts]);

  const patch = <K extends keyof WarrantyPolicyDraft>(key: K, value: WarrantyPolicyDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const isService = pickedProduct?.is_service ?? false;
  const lastPurchase = policy?.last_purchase ?? null;

  const save = async () => {
    if (!draft.product) {
      setErr("اختر براند المنتج أولاً");
      return;
    }
    if (draft.dealer_months <= 0 && draft.manufacturer_months <= 0) {
      setErr("حدّد مدة كفالة التاجر أو المصنع أكبر من صفر — كفالة المورّد وحدها داخلية لا تُصدر للزبون بطاقة");
      return;
    }
    // #233: قبل حفظ سياسة `serial` — معاينة الإخوة الذين سيُتتبَّعون معها
    // والوحدات غير المرقَّمة القائمة، وتأكيدٌ من المستخدم إن وُجد أيٌّ منهما.
    if (draft.method === "serial") {
      try {
        const impact = await getWarrantySerialImpact({ product: draft.product });
        const productName =
          pickedProduct?.display_name || pickedProduct?.name_ar || pickedProduct?.sku || "";
        const unitsRows = [{
          productName,
          count: impact.unnumbered_units[draft.product] || 0,
        }];
        const siblingNames = impact.sibling_brands.map((s) => s.name);
        if (serialImpactNeedsConfirmation({ siblingCount: siblingNames.length, unitsRows })) {
          const proceed = await confirm({
            title: "تفعيل تتبّع الرقم التسلسلي",
            message: serialImpactConfirmationLines({ siblingNames, unitsRows }).join("\n"),
            confirmText: "متابعة الحفظ",
            cancelText: "رجوع",
            danger: false,
          });
          if (!proceed) return;
        }
      } catch {
        // معاينةٌ لا حارس — تعذّرها لا يمنع الحفظ، والخادم يفرض قيوده الحقيقية عنده.
      }
    }
    setBusy(true);
    setErr(null);
    try {
      const payload: WarrantyPolicyDraft = {
        ...draft,
        terms_override: draft.terms_override.trim(),
        manufacturer_warrantor: draft.manufacturer_warrantor || null,
      };
      if (policy) {
        await updateWarrantyPolicy(policy.id, payload);
      } else {
        await createWarrantyPolicy(payload);
      }
      onSaved();
      onClose();
    } catch (e) {
      setErr(messageOf(e, "تعذّر حفظ سياسة الكفالة"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label={policy ? "تعديل سياسة الكفالة" : "سياسة كفالة جديدة"}
      className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
    >
      <div className="w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
          <span className="truncate font-bold text-[var(--color-text)]">
            {policy ? `تعديل — ${policy.product_name}` : "سياسة كفالة جديدة"}
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

          {!policy && (
            <div>
              <label className={labelClass}>البراند</label>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="flex h-10 w-full items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
              >
                <Package className="h-4 w-4 text-[var(--color-text-muted)]" />
                {pickedProduct
                  ? (pickedProduct.display_name || pickedProduct.name_ar || pickedProduct.sku)
                  : "اختر برانداً…"}
              </button>
            </div>
          )}

          {lastPurchase && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <div className="text-[11px] text-[var(--color-text-muted)]">
                  آخر شراء — فاتورة {lastPurchase.invoice_number}
                  {lastPurchase.invoice_date ? ` (${formatDateValue(lastPurchase.invoice_date)})` : ""}
                </div>
                <div className="text-[var(--color-text)]">
                  {lastPurchase.manufacturer_warrantor_name || "لا يوجد جهة"}
                  {" · "}المصنع {formatNumber(lastPurchase.manufacturer_months)} شهراً
                  {lastPurchase.supplier_months !== null && (
                    <>{" · "}المورّد {formatNumber(lastPurchase.supplier_months)} شهراً</>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  patch("manufacturer_warrantor", lastPurchase.manufacturer_warrantor);
                  patch("manufacturer_months", lastPurchase.manufacturer_months);
                  patch("supplier_months", lastPurchase.supplier_months ?? 0);
                }}
                className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-primary)] hover:bg-[var(--color-surface)]"
              >
                اعتمدها
              </button>
            </div>
          )}

          <div>
            <label className={labelClass} htmlFor="policy-method">طريقة الإثبات</label>
            <select
              id="policy-method"
              className={fieldClass}
              disabled={isService && draft.method === "invoice"}
              value={draft.method}
              onChange={(e) => patch("method", e.target.value as WarrantyPolicyMethod)}
            >
              <option value="serial" disabled={isService}>برقم تسلسلي</option>
              <option value="invoice">على الفاتورة</option>
            </select>
            {isService && (
              <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                منتج خدمة — لا رقم تسلسلي له، فالإثبات على الفاتورة وحده.
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className={labelClass} htmlFor="policy-dealer">كفالة التاجر (أشهر)</label>
              <input
                id="policy-dealer" type="number" min="0" max="600" className={fieldClass}
                value={draft.dealer_months}
                onChange={(e) => patch("dealer_months", Number(e.target.value) || 0)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="policy-manufacturer">كفالة المصنع (أشهر)</label>
              <input
                id="policy-manufacturer" type="number" min="0" max="600" className={fieldClass}
                value={draft.manufacturer_months}
                onChange={(e) => patch("manufacturer_months", Number(e.target.value) || 0)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="policy-supplier">كفالة المورّد (أشهر)</label>
              <input
                id="policy-supplier" type="number" min="0" max="600" className={fieldClass}
                value={draft.supplier_months}
                onChange={(e) => patch("supplier_months", Number(e.target.value) || 0)}
              />
            </div>
          </div>

          <div>
            <label className={labelClass} htmlFor="policy-warrantor">جهة كفالة المصنع</label>
            <select
              id="policy-warrantor"
              className={fieldClass}
              value={draft.manufacturer_warrantor ?? ""}
              onChange={(e) => patch(
                "manufacturer_warrantor", e.target.value ? Number(e.target.value) : null,
              )}
            >
              <option value="">لا يوجد</option>
              {warrantors.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelClass} htmlFor="policy-terms">شروطٌ خاصة بهذا البراند</label>
            <textarea
              id="policy-terms"
              rows={4}
              maxLength={TERMS_MAX_LENGTH}
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-sm text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              value={draft.terms_override}
              onChange={(e) => patch("terms_override", e.target.value)}
              placeholder="فارغة = تُستخدم شروط الشركة العامة"
            />
            <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
              {draft.terms_override.length} / {TERMS_MAX_LENGTH} حرفاً
            </p>
          </div>
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

      <SalesProductPickerModal
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        products={products}
        onSelect={(productId) => {
          const product = products.find((p) => p.id === productId) || null;
          setPickedProduct(product);
          patch("product", productId);
          if (product?.is_service) patch("method", "invoice");
          setPickerOpen(false);
        }}
      />
    </div>
  );
};

export default WarrantyPolicyModal;
