import React, { useEffect, useState } from "react";
import { Building2, Plus, Save, Trash2, X } from "lucide-react";
import {
  apiGetList, apiGetObject, apiPatchObject, apiPostObject,
} from "../../services/restApi";
import { clientLogger } from "../../services/logger";
import { resolveTenantId } from "../../utils/tenantContext";
import { eventBus } from "../../utils/eventBus";
import { KitDateInput } from "../kit/KitDateInput";
import type { PartnerBankAccount } from "../../utils/partnerChequeDefaults";

export type PartnerType =
  | "Customer"
  | "Supplier"
  | "FreightForwarder"
  | "CustomsBroker"
  | "LocalTransporter"
  | "Carrier";

export type PartnerEditorResult = {
  id: number;
  name: string;
  partner_type: PartnerType;
};

/** T-IMPOFFER: نطاق المورد. '' = غير مصنَّف (يظهر في الجانبين). */
export type SupplierScope = "" | "local" | "international";

export const SUPPLIER_SCOPES: Array<{ value: SupplierScope; label: string }> = [
  { value: "", label: "غير مصنَّف (يظهر في الجانبين)" },
  { value: "local", label: "مورد محلي" },
  { value: "international", label: "مورد دولي (استيراد)" },
];

type PartnerDetail = PartnerEditorResult & {
  supplier_scope?: SupplierScope | null;
  legal_name?: string | null;
  tax_number?: string | null;
  phone?: string | null;
  email?: string | null;
  street_address?: string | null;
  city?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  country?: string | null;
  credit_limit?: string | null;
  currency?: number | null;
  default_cost_center?: number | null;
  end_of_dealing_date?: string | null;
  assigned_price_tier?: number | null;
  bank_accounts?: BankForm[];
};

type CurrencyRow = { CurrencyID: number; Code: string; Name?: string | null };
type CostCenterRow = { id: number; name: string };

type BankForm = PartnerBankAccount & {
  iban?: string | null;
  swift_code?: string | null;
  bank_address?: string | null;
};

const TYPES: Array<{ value: PartnerType; label: string }> = [
  { value: "Customer", label: "زبون" },
  { value: "Supplier", label: "مورد" },
  { value: "FreightForwarder", label: "وكيل شحن" },
  { value: "CustomsBroker", label: "مخلّص جمركي" },
  { value: "LocalTransporter", label: "ناقل محلي" },
  { value: "Carrier", label: "ناقل" },
];

const emptyForm = (partnerType: PartnerType) => ({
  name: "",
  legal_name: "",
  partner_type: partnerType,
  supplier_scope: "" as SupplierScope,
  tax_number: "",
  phone: "",
  email: "",
  street_address: "",
  city: "",
  state_or_province: "",
  postal_code: "",
  country: "",
  credit_limit: "",
  currency: "" as number | "",
  default_cost_center: "" as number | "",
  end_of_dealing_date: "",
  assigned_price_tier: "" as number | "",
});

const blankBank = (currency: number | "", isDefault: boolean): BankForm => ({
  id: 0,
  bank_name: "",
  account_number: "",
  branch_name: "",
  beneficiary_name: "",
  iban: "",
  swift_code: "",
  bank_address: "",
  currency: currency || null,
  is_active: true,
  is_default: isDefault,
});

export const PartnerEditorModal: React.FC<{
  open: boolean;
  partnerId?: number | null;
  fixedType?: PartnerType;
  initialType?: PartnerType;
  embedded?: boolean;
  onClose: () => void;
  onSaved: (partner: PartnerEditorResult) => void;
}> = ({
  open,
  partnerId,
  fixedType,
  initialType = "Customer",
  embedded = false,
  onClose,
  onSaved,
}) => {
  const tenantId = resolveTenantId();
  const [form, setForm] = useState(() => emptyForm(fixedType || initialType));
  const [banks, setBanks] = useState<BankForm[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyRow[]>([]);
  const [costCenters, setCostCenters] = useState<CostCenterRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const currencyRequest = apiGetList<CurrencyRow>("accounting/currencies/", { tenantId });
    const costCenterRequest = apiGetList<CostCenterRow>("accounting/cost-centers/", { tenantId });
    const partnerRequest = partnerId
      ? apiGetObject<PartnerDetail>(`partners/${partnerId}/`, { tenantId })
      : Promise.resolve(null);
    Promise.all([currencyRequest, costCenterRequest, partnerRequest])
      .then(([currencyRows, costCenterRows, partner]) => {
        if (cancelled) return;
        setCurrencies(currencyRows);
        setCostCenters(costCenterRows);
        if (partner) {
          setForm({
            name: partner.name || "",
            legal_name: partner.legal_name || "",
            partner_type: fixedType || partner.partner_type,
            supplier_scope: (partner.supplier_scope || "") as SupplierScope,
            tax_number: partner.tax_number || "",
            phone: partner.phone || "",
            email: partner.email || "",
            street_address: partner.street_address || "",
            city: partner.city || "",
            state_or_province: partner.state_or_province || "",
            postal_code: partner.postal_code || "",
            country: partner.country || "",
            credit_limit: partner.credit_limit || "",
            currency: partner.currency || "",
            default_cost_center: partner.default_cost_center || "",
            end_of_dealing_date: partner.end_of_dealing_date || "",
            assigned_price_tier: partner.assigned_price_tier || "",
          });
          setBanks(partner.bank_accounts || []);
        } else {
          setForm(emptyForm(fixedType || initialType));
          setBanks([]);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "تعذّر تحميل بطاقة الطرف.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fixedType, initialType, open, partnerId, tenantId]);

  if (!open) return null;

  const patchBank = (index: number, patch: Partial<BankForm>) => {
    setBanks((rows) => rows.map((row, i) => (
      i === index ? { ...row, ...patch } : row
    )));
  };

  const chooseDefault = (index: number) => {
    setBanks((rows) => rows.map((row, i) => ({
      ...row,
      is_default: i === index,
      is_active: i === index ? true : row.is_active,
    })));
  };

  const save = async () => {
    if (!form.name.trim()) {
      setError("اسم الطرف مطلوب.");
      return;
    }
    const effectiveBanks = banks.filter((bank) => (
      bank.bank_name.trim() || bank.account_number.trim()
    ));
    if (effectiveBanks.some((bank) => !bank.bank_name.trim() || !bank.account_number.trim())) {
      setError("اسم البنك ورقم الحساب مطلوبان لكل حساب بنكي.");
      return;
    }
    if (effectiveBanks.some((bank) => !bank.currency)) {
      setError("اختر عملة لكل حساب بنكي.");
      return;
    }
    if (effectiveBanks.filter((bank) => bank.is_default).length > 1) {
      setError("اختر حساباً بنكياً افتراضياً واحداً فقط.");
      return;
    }
    if (effectiveBanks.length && !effectiveBanks.some((bank) => bank.is_default)) {
      effectiveBanks[0] = { ...effectiveBanks[0], is_default: true, is_active: true };
    }

    setSaving(true);
    setError(null);
    const payload = {
      ...form,
      name: form.name.trim(),
      legal_name: form.legal_name.trim() || null,
      tax_number: form.tax_number.trim() || null,
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      street_address: form.street_address.trim() || null,
      city: form.city.trim() || null,
      state_or_province: form.state_or_province.trim() || null,
      postal_code: form.postal_code.trim() || null,
      country: form.country.trim() || null,
      credit_limit: form.credit_limit === "" ? null : form.credit_limit,
      currency: form.currency || null,
      default_cost_center: form.default_cost_center || null,
      end_of_dealing_date: form.end_of_dealing_date || null,
      assigned_price_tier: form.assigned_price_tier || null,
      partner_type: fixedType || form.partner_type,
      // T-IMPOFFER: النطاق يخص المورد وحده — لا يُكتب لزبون أو ناقل.
      supplier_scope:
        (fixedType || form.partner_type) === "Supplier" ? form.supplier_scope : "",
      bank_accounts: effectiveBanks.map((bank) => ({
        ...(bank.id ? { id: bank.id } : {}),
        bank_name: bank.bank_name.trim(),
        account_number: bank.account_number.trim(),
        branch_name: bank.branch_name?.trim() || "",
        beneficiary_name: bank.beneficiary_name?.trim() || "",
        iban: bank.iban?.trim() || "",
        swift_code: bank.swift_code?.trim() || "",
        bank_address: bank.bank_address?.trim() || "",
        currency: bank.currency,
        is_active: bank.is_active,
        is_default: bank.is_default,
      })),
    };

    try {
      const saved = partnerId
        ? await apiPatchObject<PartnerEditorResult>(
            `partners/${partnerId}/`, payload, { tenantId },
          )
        : await apiPostObject<PartnerEditorResult>("partners/", payload, { tenantId });
      clientLogger.info("partner.card_saved", {
        partner_id: saved.id,
        partner_type: saved.partner_type,
        bank_accounts: effectiveBanks.length,
      });
      eventBus.publish("partners", tenantId);
      onSaved(saved);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل حفظ بطاقة الطرف.");
    } finally {
      setSaving(false);
    }
  };

  const field = (
    label: string,
    value: string,
    key: keyof typeof form,
    type = "text",
  ) => (
    <label className="ktra-field">
      <span className="ktra-field-label">{label}</span>
      <input
        className="ktra-input"
        type={type}
        value={value}
        onChange={(e) => setForm((current) => ({ ...current, [key]: e.target.value }))}
      />
    </label>
  );

  return (
    <div
      className={embedded ? "w-full" : "fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"}
      dir="rtl"
      onMouseDown={(e) => { if (!embedded && e.target === e.currentTarget) onClose(); }}
    >
      <div className={embedded ? "w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]" : "max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl"}>
        <div className={`${embedded ? "" : "sticky top-0 z-10 "}flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] p-4`}>
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-blue-600" />
            <div>
              <h2 className="font-bold">{partnerId ? "تعديل بطاقة الطرف" : "إضافة طرف جديد"}</h2>
              <p className="text-xs text-[var(--color-text-muted)]">بيانات موحّدة تُستخدم في الفواتير والسندات والشيكات</p>
            </div>
          </div>
          {!embedded && <button type="button" className="ktra-toolbtn" onClick={onClose}><X className="h-4 w-4" /></button>}
        </div>

        <div className="space-y-5 p-4">
          {error && <div className="ktra-banner ktra-banner--err">{error}</div>}
          {loading ? (
            <div className="p-8 text-center text-sm text-[var(--color-text-muted)]">جاري تحميل البطاقة…</div>
          ) : (
            <>
              <section className="rounded-lg border border-[var(--color-border)] p-4">
                <h3 className="mb-3 text-sm font-bold">البيانات الأساسية</h3>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                  {!fixedType && (
                    <label className="ktra-field">
                      <span className="ktra-field-label">نوع الطرف *</span>
                      <select
                        className="ktra-input"
                        value={form.partner_type}
                        onChange={(e) => setForm((current) => ({
                          ...current, partner_type: e.target.value as PartnerType,
                        }))}
                      >
                        {TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                      </select>
                    </label>
                  )}
                  {(fixedType || form.partner_type) === "Supplier" && (
                    <label className="ktra-field">
                      <span className="ktra-field-label">نطاق المورد</span>
                      <select
                        className="ktra-input"
                        value={form.supplier_scope}
                        onChange={(e) => setForm((current) => ({
                          ...current, supplier_scope: e.target.value as SupplierScope,
                        }))}
                      >
                        {SUPPLIER_SCOPES.map((scope) => (
                          <option key={scope.value} value={scope.value}>{scope.label}</option>
                        ))}
                      </select>
                    </label>
                  )}
                  {field("الاسم *", form.name, "name")}
                  {field("الاسم القانوني", form.legal_name, "legal_name")}
                  {field("الرقم الضريبي", form.tax_number, "tax_number")}
                  {field("الهاتف", form.phone, "phone", "tel")}
                  {field("البريد الإلكتروني", form.email, "email", "email")}
                  {field("حد الائتمان", form.credit_limit, "credit_limit", "number")}
                  <label className="ktra-field">
                    <span className="ktra-field-label">العملة الافتراضية</span>
                    <select
                      className="ktra-input"
                      value={form.currency}
                      onChange={(e) => setForm((current) => ({
                        ...current,
                        currency: e.target.value ? Number(e.target.value) : "",
                      }))}
                    >
                      <option value="">—</option>
                      {currencies.map((currency) => (
                        <option key={currency.CurrencyID} value={currency.CurrencyID}>{currency.Code}</option>
                      ))}
                    </select>
                  </label>
                  <label className="ktra-field">
                    <span className="ktra-field-label">مركز التكلفة الافتراضي</span>
                    <select
                      className="ktra-input"
                      value={form.default_cost_center}
                      onChange={(e) => setForm((current) => ({
                        ...current,
                        default_cost_center: e.target.value ? Number(e.target.value) : "",
                      }))}
                    >
                      <option value="">—</option>
                      {costCenters.map((center) => <option key={center.id} value={center.id}>{center.name}</option>)}
                    </select>
                  </label>
                  <label className="ktra-field">
                    <span className="ktra-field-label">نهاية التعامل</span>
                    <KitDateInput
                      className="ktra-input"
                      value={form.end_of_dealing_date}
                      onChange={(value) => setForm((current) => ({
                        ...current, end_of_dealing_date: value,
                      }))}
                    />
                  </label>
                  <label className="ktra-field">
                    <span className="ktra-field-label">فئة السعر</span>
                    <select
                      className="ktra-input"
                      value={form.assigned_price_tier}
                      onChange={(e) => setForm((current) => ({
                        ...current,
                        assigned_price_tier: e.target.value ? Number(e.target.value) : "",
                      }))}
                    >
                      <option value="">—</option>
                      <option value="1">تجزئة</option>
                      <option value="2">جملة</option>
                      <option value="3">موزّع</option>
                      <option value="4">VIP</option>
                    </select>
                  </label>
                </div>
              </section>

              <section className="rounded-lg border border-[var(--color-border)] p-4">
                <h3 className="mb-3 text-sm font-bold">العنوان</h3>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div className="md:col-span-2 lg:col-span-3">
                    {field("العنوان", form.street_address, "street_address")}
                  </div>
                  {field("المدينة", form.city, "city")}
                  {field("المحافظة", form.state_or_province, "state_or_province")}
                  {field("الرمز البريدي", form.postal_code, "postal_code")}
                  {field("الدولة", form.country, "country")}
                </div>
              </section>

              <section className="rounded-lg border border-[var(--color-border)] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold">الحسابات البنكية</h3>
                    <p className="text-xs text-[var(--color-text-muted)]">الحساب الافتراضي يُستخدم لتعبئة الشيك الوارد تلقائياً.</p>
                  </div>
                  <button
                    type="button"
                    className="ktra-toolbtn"
                    onClick={() => setBanks((rows) => [
                      ...rows,
                      blankBank(form.currency || currencies[0]?.CurrencyID || "", rows.length === 0),
                    ])}
                  >
                    <Plus className="h-3 w-3" /> حساب بنكي
                  </button>
                </div>
                {banks.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-[var(--color-border)] p-5 text-center text-xs text-[var(--color-text-muted)]">
                    لا توجد حسابات بنكية محفوظة.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {banks.map((bank, index) => (
                      <div key={bank.id || `new-${index}`} className="rounded-lg bg-[var(--color-surface-2)] p-3">
                        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-4">
                          <label className="ktra-field">
                            <span className="ktra-field-label">اسم البنك *</span>
                            <input className="ktra-input" value={bank.bank_name} onChange={(e) => patchBank(index, { bank_name: e.target.value })} />
                          </label>
                          <label className="ktra-field">
                            <span className="ktra-field-label">رقم الحساب *</span>
                            <input className="ktra-input font-mono" dir="ltr" value={bank.account_number} onChange={(e) => patchBank(index, { account_number: e.target.value })} />
                          </label>
                          <label className="ktra-field">
                            <span className="ktra-field-label">الفرع</span>
                            <input className="ktra-input" value={bank.branch_name || ""} onChange={(e) => patchBank(index, { branch_name: e.target.value })} />
                          </label>
                          <label className="ktra-field">
                            <span className="ktra-field-label">اسم صاحب الحساب</span>
                            <input className="ktra-input" value={bank.beneficiary_name || ""} onChange={(e) => patchBank(index, { beneficiary_name: e.target.value })} />
                          </label>
                          <label className="ktra-field">
                            <span className="ktra-field-label">IBAN</span>
                            <input className="ktra-input font-mono" dir="ltr" value={bank.iban || ""} onChange={(e) => patchBank(index, { iban: e.target.value })} />
                          </label>
                          <label className="ktra-field">
                            <span className="ktra-field-label">SWIFT</span>
                            <input className="ktra-input font-mono" dir="ltr" value={bank.swift_code || ""} onChange={(e) => patchBank(index, { swift_code: e.target.value })} />
                          </label>
                          <label className="ktra-field">
                            <span className="ktra-field-label">العملة *</span>
                            <select className="ktra-input" value={bank.currency || ""} onChange={(e) => patchBank(index, { currency: e.target.value ? Number(e.target.value) : null })}>
                              <option value="">—</option>
                              {currencies.map((currency) => <option key={currency.CurrencyID} value={currency.CurrencyID}>{currency.Code}</option>)}
                            </select>
                          </label>
                          <div className="flex items-end gap-4 pb-1">
                            <label className="flex items-center gap-1 text-xs">
                              <input type="radio" name="default-bank" checked={bank.is_default} onChange={() => chooseDefault(index)} />
                              افتراضي
                            </label>
                            <label className="flex items-center gap-1 text-xs">
                              <input type="checkbox" checked={bank.is_active} onChange={(e) => patchBank(index, { is_active: e.target.checked, is_default: e.target.checked ? bank.is_default : false })} />
                              فعّال
                            </label>
                            <button type="button" className="text-red-600" onClick={() => setBanks((rows) => rows.filter((_, i) => i !== index))} title="حذف الحساب">
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </div>

        <div className={`${embedded ? "" : "sticky bottom-0 "}flex justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface)] p-4`}>
          <button type="button" className="ktra-toolbtn" onClick={onClose}>{embedded ? "العودة للتفاصيل" : "إلغاء"}</button>
          <button type="button" className="ktra-toolbtn bg-blue-600 text-white" disabled={loading || saving} onClick={() => void save()}>
            <Save className="h-4 w-4" /> {saving ? "جاري الحفظ…" : "حفظ البطاقة"}
          </button>
        </div>
      </div>
    </div>
  );
};
