import React from "react";

import { searchPolicyBillingProducts, type BillingProductOption } from "../../services/platformOpsApi";
import { SearchPicker } from "./SearchPicker";

interface Props {
  policyId: number;
  value: number | null;
  valueLabel: string | null;
  onChange: (product: BillingProductOption | null) => void;
  placeholder: string;
  disabled?: boolean;
}

/**
 * منتقي صنف فوترة لمسودة سياسة — البحث محصور خادمياً بالأصناف الخدمية في شركة فوترة
 * هذه النسخة (`searchPolicyBillingProducts`)؛ لا معامل شركة يُرسل من هنا.
 */
export const BillingProductPicker: React.FC<Props> = ({ policyId, value, valueLabel, onChange, placeholder, disabled }) => (
  <SearchPicker<BillingProductOption>
    value={value}
    valueLabel={valueLabel}
    onChange={onChange}
    search={(query) => searchPolicyBillingProducts(policyId, query)}
    searchKey={policyId}
    renderOption={(product) => `${product.name} · ${product.sku}`}
    selectedFallback={`صنف #${value ?? ""}`}
    placeholder={placeholder}
    emptyText="لا أصناف خدمية مطابقة في شركة الفوترة."
    clearLabel="إزالة صنف الفوترة"
    disabled={disabled}
  />
);
