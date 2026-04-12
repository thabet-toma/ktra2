import { SupplierType } from "../types";

export interface SupplierTypeOption {
    value: SupplierType;
    label: string;
    icon?: string;
}

export const SUPPLIER_TYPES: SupplierTypeOption[] = [
    { value: 'factory', label: 'مورد (Supplier)' },
    { value: 'shipping_agent', label: 'وكيل شحن (FreightForwarder)' },
    { value: 'service_provider', label: 'مخلّص جمركي (CustomsBroker)' },
    { value: 'local_company', label: 'ناقل محلي (LocalTransporter)' },
    { value: 'international_trader', label: 'مورد دولي (Supplier)' },
];

export const getSupplierTypeLabel = (value?: SupplierType): string => {
    if (!value) return 'غير محدد';
    const option = SUPPLIER_TYPES.find(opt => opt.value === value);
    return option ? option.label : value;
};
