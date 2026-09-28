import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Archive, Layers, Loader2, Plus, RotateCcw, Settings, ShieldCheck, X,
} from "lucide-react";
import {
  deleteWarrantyPolicy,
  getAfterSalesSettings,
  listManufacturerWarrantors,
  listWarrantyPolicies,
  lookupManufacturerWarrantors,
  updateAfterSalesSettings,
  updateManufacturerWarrantor,
  type AfterSalesSettingsDraft,
  type AfterSalesSettingsRow,
  type ManufacturerWarrantorRow,
  type WarrantyPolicyRow,
} from "../../services/afterSalesApi";
import { listPickerProducts } from "../../services/inventoryApi";
import type { SalesProductPickerItem } from "../sales/SalesProductPickerModal";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { ManufacturerWarrantorModal } from "./ManufacturerWarrantorModal";
import { WarrantyPolicyModal } from "./WarrantyPolicyModal";
import { WarrantyPolicyBulkModal } from "./WarrantyPolicyBulkModal";

/**
 * #230/#231 — إعدادات وحدة خدمة ما بعد البيع: «جهات كفالة المصنع»،
 * «سياسات الكفالة» (صفٌّ لكل براند — لا سياسة = لا بطاقة تلقائية عند البيع)،
 * و«الشروط والإعدادات». تُفتح من زر «الإعدادات» في شاشة بطاقات الكفالة، خلف
 * `aftersales.settings.manage` للكتابة — `GET` وحده يُقرأ بلا صلاحيةٍ خاصة.
 */

interface PolicyProductOption extends SalesProductPickerItem {
  is_service?: boolean;
  family_id?: number | null;
  family_name?: string | null;
  category?: number | null;
  category_name?: string | null;
}

interface Props {
  canManage: boolean;
  onClose: () => void;
  /** #231: رابط «سياسات الكفالة» على كرت المنتج يصل هنا مباشرةً — يُنزل
   *  القسم إلى مرأى المستخدم بدل أن يفتح على أعلى النافذة (جهات المصنع). */
  focusPolicies?: boolean;
}

const TERMS_MAX_LENGTH = 2000;
const TERMS_WARN_LENGTH = 1200;

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const cardClass = "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4";

const fieldClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const textareaClass =
  "w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-sm " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60";

const emptySettingsDraft = (): AfterSalesSettingsDraft => ({
  default_terms: "", extend_for_shop_days: true, repair_warranty_days: 90, repair_terms: "",
});

const TermsCounter: React.FC<{ length: number }> = ({ length }) => (
  <div
    className={`mt-1 text-[11px] ${
      length > TERMS_MAX_LENGTH
        ? "text-red-600 dark:text-red-400"
        : length > TERMS_WARN_LENGTH
          ? "text-amber-600 dark:text-amber-400"
          : "text-[var(--color-text-muted)]"
    }`}
  >
    {length} / {TERMS_MAX_LENGTH} حرفاً
    {length > TERMS_MAX_LENGTH && " — تجاوزت الحد المسموح"}
    {length > TERMS_WARN_LENGTH && length <= TERMS_MAX_LENGTH && " — قد تصير الشهادة صفحتين"}
  </div>
);

export const WarrantySettingsScreen: React.FC<Props> = ({ canManage, onClose, focusPolicies }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const policiesSectionRef = useRef<HTMLElement | null>(null);

  const [warrantors, setWarrantors] = useState<ManufacturerWarrantorRow[]>([]);
  const [warrantorsErr, setWarrantorsErr] = useState<string | null>(null);
  const [loadingWarrantors, setLoadingWarrantors] = useState(false);
  const [openWarrantor, setOpenWarrantor] = useState<ManufacturerWarrantorRow | "new" | null>(null);

  const [policies, setPolicies] = useState<WarrantyPolicyRow[]>([]);
  const [policiesErr, setPoliciesErr] = useState<string | null>(null);
  const [loadingPolicies, setLoadingPolicies] = useState(false);
  const [policyProducts, setPolicyProducts] = useState<PolicyProductOption[]>([]);
  const [openPolicy, setOpenPolicy] = useState<WarrantyPolicyRow | "new" | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);

  const [settings, setSettings] = useState<AfterSalesSettingsRow | null>(null);
  const [draft, setDraft] = useState<AfterSalesSettingsDraft>(emptySettingsDraft());
  const [settingsErr, setSettingsErr] = useState<string | null>(null);
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);

  const loadWarrantors = useCallback(async () => {
    setLoadingWarrantors(true);
    setWarrantorsErr(null);
    try {
      // `manufacturer-warrantors/` الكاملة (وفيها المؤرشفة) خلف
      // `aftersales.settings.manage` وحدها — من دونها نقرأ `lookup/` الأوسع
      // (المفعَّلة فقط)، وإلا ارتدّ كل غير مديرٍ يفتح الشاشة 403.
      setWarrantors(
        canManage ? await listManufacturerWarrantors() : await lookupManufacturerWarrantors(),
      );
    } catch (e) {
      setWarrantorsErr(messageOf(e, "تعذّر تحميل جهات كفالة المصنع"));
    } finally {
      setLoadingWarrantors(false);
    }
  }, [canManage]);

  const loadPolicies = useCallback(async () => {
    setLoadingPolicies(true);
    setPoliciesErr(null);
    try {
      const [rows, products] = await Promise.all([
        listWarrantyPolicies(),
        listPickerProducts<PolicyProductOption>(),
      ]);
      setPolicies(rows);
      setPolicyProducts(products);
    } catch (e) {
      setPoliciesErr(messageOf(e, "تعذّر تحميل سياسات الكفالة"));
    } finally {
      setLoadingPolicies(false);
    }
  }, []);

  const loadSettings = useCallback(async () => {
    setLoadingSettings(true);
    setSettingsErr(null);
    try {
      const row = await getAfterSalesSettings();
      setSettings(row);
      setDraft({
        default_terms: row.default_terms,
        extend_for_shop_days: row.extend_for_shop_days,
        repair_warranty_days: row.repair_warranty_days,
        repair_terms: row.repair_terms,
      });
    } catch (e) {
      setSettingsErr(messageOf(e, "تعذّر تحميل إعدادات الوحدة"));
    } finally {
      setLoadingSettings(false);
    }
  }, []);

  useEffect(() => {
    void loadWarrantors();
    void loadPolicies();
    void loadSettings();
  }, [loadWarrantors, loadPolicies, loadSettings]);

  useEffect(() => {
    if (focusPolicies) policiesSectionRef.current?.scrollIntoView({ block: "start" });
  }, [focusPolicies]);

  // المنتقي عند إنشاء سياسة جديدة يعرض براندات بلا سياسة قائمة فقط — صفٌّ واحد
  // لكل براند (`OneToOneField`)، فاختيار براند له سياسة يرتدّ 400 من الخادم.
  const productsWithoutPolicy = useMemo(() => {
    const taken = new Set(policies.map((p) => p.product));
    return policyProducts.filter((p) => !taken.has(p.id));
  }, [policyProducts, policies]);

  const deletePolicy = async (row: WarrantyPolicyRow) => {
    const ok = await confirm({
      title: "حذف سياسة الكفالة",
      message: `ستُحذف سياسة «${row.product_name}» — البطاقات الصادرة لا تتأثر، لكن مبيعات هذا البراند لن تصدر بطاقةً بعد الآن حتى تُضاف سياسةٌ جديدة.`,
      confirmText: "حذف السياسة",
      cancelText: "تراجع",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteWarrantyPolicy(row.id);
      toast("حُذفت السياسة", "success");
      void loadPolicies();
    } catch (e) {
      toast(messageOf(e, "تعذّر حذف السياسة"), "error");
    }
  };

  const toggleActive = async (row: ManufacturerWarrantorRow) => {
    try {
      await updateManufacturerWarrantor(row.id, { is_active: !row.is_active });
      toast(row.is_active ? "أُرشفت الجهة" : "أُعيد تفعيل الجهة", "success");
      void loadWarrantors();
    } catch (e) {
      toast(messageOf(e, "تعذّر تحديث حالة الجهة"), "error");
    }
  };

  const saveSettings = async () => {
    setSavingSettings(true);
    setSettingsErr(null);
    try {
      const saved = await updateAfterSalesSettings(draft);
      setSettings(saved);
      toast("تم حفظ الشروط والإعدادات", "success");
    } catch (e) {
      setSettingsErr(messageOf(e, "تعذّر حفظ الإعدادات"));
    } finally {
      setSavingSettings(false);
    }
  };

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label="إعدادات خدمة ما بعد البيع"
      data-testid="after-sales-settings-screen"
      className="fixed inset-0 z-[70] flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
    >
      <div className="w-full max-w-4xl space-y-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-xl md:p-4">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] pb-3">
          <div className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-[var(--color-primary)]" />
            <span className="font-bold text-[var(--color-text)]">إعدادات خدمة ما بعد البيع</span>
          </div>
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

        {!canManage && (
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-[var(--color-text-muted)]">
            تُعرض هنا للاطّلاع فقط — تعديل الجهات والشروط والإعدادات يحتاج صلاحية إدارة إعدادات
            خدمة ما بعد البيع.
          </div>
        )}

        {/* ── جهات كفالة المصنع ─────────────────────────────────────────── */}
        <section className={cardClass}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-[var(--color-primary)]" />
              <h2 className="font-bold text-[var(--color-text)]">جهات كفالة المصنع</h2>
            </div>
            {canManage && (
              <button
                type="button"
                onClick={() => setOpenWarrantor("new")}
                className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-1.5 text-sm font-bold text-white"
              >
                <Plus className="h-4 w-4" /> جهة جديدة
              </button>
            )}
          </div>

          {warrantorsErr && (
            <div role="alert" className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {warrantorsErr}
            </div>
          )}

          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>الاسم</th>
                  <th className="hidden md:table-cell">عنوان مركز الخدمة</th>
                  <th>الهاتف</th>
                  <th>الحالة</th>
                  {canManage && <th>إجراءات</th>}
                </tr>
              </thead>
              <tbody>
                {warrantors.map((row) => (
                  <tr key={row.id}>
                    <td
                      className={canManage ? "cursor-pointer font-semibold text-[var(--color-text)]" : "font-semibold text-[var(--color-text)]"}
                      onClick={() => canManage && setOpenWarrantor(row)}
                    >
                      {row.name}
                    </td>
                    <td className="hidden md:table-cell">{row.service_center_address || "—"}</td>
                    <td>{row.phone || "—"}</td>
                    <td>
                      <span
                        className={
                          row.is_active
                            ? "rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                            : "rounded-full bg-[var(--color-surface-2)] px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]"
                        }
                      >
                        {row.is_active ? "مفعَّلة" : "مؤرشفة"}
                      </span>
                    </td>
                    {canManage && (
                      <td>
                        <button
                          type="button"
                          onClick={() => void toggleActive(row)}
                          className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                          title={row.is_active ? "أرشفة الجهة" : "إعادة تفعيل الجهة"}
                        >
                          {row.is_active
                            ? <Archive className="h-3.5 w-3.5" />
                            : <RotateCcw className="h-3.5 w-3.5" />}
                          {row.is_active ? "أرشفة" : "تفعيل"}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!loadingWarrantors && warrantors.length === 0 && (
            <div className="p-6 text-center text-sm text-[var(--color-text-muted)]">
              لا جهات كفالة مصنع بعد — أضف جهةً كي تظهر على الشهادة وورقة الإحالة.
            </div>
          )}
          {loadingWarrantors && warrantors.length === 0 && (
            <div className="flex items-center justify-center gap-2 p-6 text-sm text-[var(--color-text-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" /> جارٍ التحميل…
            </div>
          )}
        </section>

        {/* ── سياسات الكفالة (#231) ──────────────────────────────────────── */}
        <section ref={policiesSectionRef} className={cardClass}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-[var(--color-primary)]" />
              <h2 className="font-bold text-[var(--color-text)]">سياسات الكفالة</h2>
            </div>
            {canManage && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setBulkOpen(true)}
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                >
                  تطبيق جماعي
                </button>
                <button
                  type="button"
                  onClick={() => setOpenPolicy("new")}
                  className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-1.5 text-sm font-bold text-white"
                >
                  <Plus className="h-4 w-4" /> سياسة جديدة
                </button>
              </div>
            )}
          </div>

          <p className="mb-3 text-[11px] text-[var(--color-text-muted)]">
            لا سياسة لبراندٍ = لا بطاقة كفالة تُصدَر تلقائياً عند بيعه.
          </p>

          {policiesErr && (
            <div role="alert" className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {policiesErr}
            </div>
          )}

          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>البراند</th>
                  <th>الطريقة</th>
                  <th>تاجر</th>
                  <th>مصنع</th>
                  <th>مورّد</th>
                  {canManage && <th>إجراءات</th>}
                </tr>
              </thead>
              <tbody>
                {policies.map((row) => (
                  <tr key={row.id}>
                    <td
                      className={canManage ? "cursor-pointer font-semibold text-[var(--color-text)]" : "font-semibold text-[var(--color-text)]"}
                      onClick={() => canManage && setOpenPolicy(row)}
                    >
                      {row.product_name}
                    </td>
                    <td>{row.method_label}</td>
                    <td>{row.dealer_months ? `${row.dealer_months} شهراً` : "—"}</td>
                    <td>
                      {row.manufacturer_months
                        ? `${row.manufacturer_months} شهراً${row.manufacturer_warrantor_name ? ` — ${row.manufacturer_warrantor_name}` : ""}`
                        : "—"}
                    </td>
                    <td>{row.supplier_months ? `${row.supplier_months} شهراً` : "—"}</td>
                    {canManage && (
                      <td>
                        <button
                          type="button"
                          onClick={() => void deletePolicy(row)}
                          className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                          title="حذف السياسة"
                        >
                          حذف
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!loadingPolicies && policies.length === 0 && (
            <div className="p-6 text-center text-sm text-[var(--color-text-muted)]">
              لا سياسات كفالة بعد — أضف سياسةً لبراند كي تُصدر بطاقاتٍ تلقائية عند بيعه.
            </div>
          )}
          {loadingPolicies && policies.length === 0 && (
            <div className="flex items-center justify-center gap-2 p-6 text-sm text-[var(--color-text-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" /> جارٍ التحميل…
            </div>
          )}
        </section>

        {/* ── الشروط والإعدادات ──────────────────────────────────────────── */}
        <section className={cardClass}>
          <h2 className="mb-3 font-bold text-[var(--color-text)]">الشروط والإعدادات</h2>

          {settingsErr && (
            <div role="alert" className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {settingsErr}
            </div>
          )}

          {loadingSettings && !settings ? (
            <div className="flex items-center justify-center gap-2 p-6 text-sm text-[var(--color-text-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" /> جارٍ التحميل…
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className={labelClass} htmlFor="settings-default-terms">شروط كفالة الشركة</label>
                <textarea
                  id="settings-default-terms"
                  rows={5}
                  disabled={!canManage}
                  className={textareaClass}
                  value={draft.default_terms}
                  onChange={(e) => setDraft((d) => ({ ...d, default_terms: e.target.value }))}
                  placeholder="تُنسخ إلى كل بطاقة كفالة عند إنشائها"
                />
                <TermsCounter length={draft.default_terms.length} />
              </div>

              <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
                <input
                  type="checkbox"
                  disabled={!canManage}
                  checked={draft.extend_for_shop_days}
                  onChange={(e) => setDraft((d) => ({ ...d, extend_for_shop_days: e.target.checked }))}
                />
                تمديد كفالة التاجر تلقائياً بعدد أيام بقاء الجهاز المغطّى عندنا للصيانة
              </label>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className={labelClass} htmlFor="settings-repair-days">
                    مدة كفالة الإصلاح (أيام) — صفر يُطفئها
                  </label>
                  <input
                    id="settings-repair-days"
                    type="number"
                    min="0"
                    max="730"
                    disabled={!canManage}
                    className={fieldClass}
                    value={draft.repair_warranty_days}
                    onChange={(e) => setDraft((d) => ({
                      ...d, repair_warranty_days: e.target.value ? Number(e.target.value) : 0,
                    }))}
                  />
                </div>
              </div>

              <div>
                <label className={labelClass} htmlFor="settings-repair-terms">شروط كفالة الإصلاح</label>
                <textarea
                  id="settings-repair-terms"
                  rows={4}
                  disabled={!canManage}
                  className={textareaClass}
                  value={draft.repair_terms}
                  onChange={(e) => setDraft((d) => ({ ...d, repair_terms: e.target.value }))}
                  placeholder="تُطبع على شهادة كفالة الإصلاح"
                />
                <TermsCounter length={draft.repair_terms.length} />
              </div>

              {canManage && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => void saveSettings()}
                    disabled={savingSettings}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                  >
                    {savingSettings && <Loader2 className="h-4 w-4 animate-spin" />}
                    حفظ الشروط والإعدادات
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {openWarrantor !== null && (
        <ManufacturerWarrantorModal
          warrantor={openWarrantor === "new" ? null : openWarrantor}
          onClose={() => setOpenWarrantor(null)}
          onSaved={() => { void loadWarrantors(); }}
        />
      )}

      {openPolicy !== null && (
        <WarrantyPolicyModal
          policy={openPolicy === "new" ? null : openPolicy}
          products={openPolicy === "new" ? productsWithoutPolicy : policyProducts}
          onClose={() => setOpenPolicy(null)}
          onSaved={() => { void loadPolicies(); }}
        />
      )}

      {bulkOpen && (
        <WarrantyPolicyBulkModal
          products={policyProducts}
          onClose={() => setBulkOpen(false)}
          onApplied={(count) => {
            toast(`طُبّقت السياسة على ${count} براند`, "success");
            void loadPolicies();
          }}
        />
      )}
    </div>
  );
};

export default WarrantySettingsScreen;
