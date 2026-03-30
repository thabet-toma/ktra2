import { SupplierType } from "../types";

export interface SupplierTypeOption {
    value: SupplierType;
    label: string;
    icon?: string;
}

export const SUPPLIER_TYPES: SupplierTypeOption[] = [
    { value: 'factory', label: 'مصنع' },
    { value: 'shipping_agent', label: 'وكيل شحن' },
    { value: 'international_trader', label: 'تاجر عالمي' },
    { value: 'local_company', label: 'شركة محلية' },
    { value: 'service_provider', label: 'مقدم خدمة' },
];

export const getSupplierTypeLabel = (value?: SupplierType): string => {
    if (!value) return 'غير محدد';
    const option = SUPPLIER_TYPES.find(opt => opt.value === value);
    return option ? option.label : value;
};
