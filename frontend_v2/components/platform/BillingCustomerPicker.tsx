import React from "react";

import { searchBillingCustomers, type BillingCustomerOption } from "../../services/platformOpsApi";
import { SearchPicker } from "./SearchPicker";

interface Props {
  value: number | null;
  valueLabel: string | null;
  onChange: (customer: BillingCustomerOption | null) => void;
  subscriptionId?: number;
  plan?: string;
  disabled?: boolean;
}

/**
 * منتقي عميل الفوترة — البحث محصور خادمياً (`searchBillingCustomers`): بشركة فوترة
 * الاشتراك الملتقطة حين يُمرَّر `subscriptionId`، وإلا بشركة فوترة نسخة السياسة السارية
 * لنطاق `plan` المطلوب — نفس الشركة التي يتحقّق منها الحفظ. لا معامل شركة يُرسل من هنا إطلاقاً.
 */
export const BillingCustomerPicker: React.FC<Props> = ({ value, valueLabel, onChange, subscriptionId, plan, disabled }) => (
  <SearchPicker<BillingCustomerOption>
    value={value}
    valueLabel={valueLabel}
    onChange={onChange}
    search={(query) => searchBillingCustomers(query, subscriptionId, plan)}
    searchKey={`${subscriptionId ?? ""}:${plan ?? ""}`}
    renderOption={(customer) => `${customer.name} ${customer.phone ? `· ${customer.phone}` : ""}`}
    selectedFallback={`عميل #${value ?? ""}`}
    placeholder="ابحث عن عميل الفوترة بالاسم أو الهاتف..."
    emptyText="لا عملاء مطابقون في شركة الفوترة."
    clearLabel="إزالة عميل الفوترة"
    disabled={disabled}
  />
);
