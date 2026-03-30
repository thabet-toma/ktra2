export const SHIPPING_TERMS = [
    { code: 'EXW', name: 'Ex Works' },
    { code: 'FCA', name: 'Free Carrier' },
    { code: 'FAS', name: 'Free Alongside Ship' },
    { code: 'FOB', name: 'Free on Board' },
    { code: 'CFR', name: 'Cost and Freight' },
    { code: 'CIF', name: 'Cost, Insurance and Freight' },
    { code: 'CPT', name: 'Carriage Paid To' },
    { code: 'CIP', name: 'Carriage and Insurance Paid To' },
    { code: 'DAT', name: 'Delivered at Terminal' },
    { code: 'DAP', name: 'Delivered at Place' },
    { code: 'DDP', name: 'Delivered Duty Paid' }
] as const;

export type ShippingTermCode = typeof SHIPPING_TERMS[number]['code'];

export const getShippingTermIndex = (code: string) => {
    return SHIPPING_TERMS.findIndex(t => t.code === code);
};

export const getLatestShippingTerm = (codes: string[]): ShippingTermCode => {
    if (!codes || codes.length === 0) return 'EXW';

    let maxIndex = -1;
    let latestTerm: ShippingTermCode = 'EXW';

    codes.forEach(code => {
        const index = getShippingTermIndex(code);
        if (index > maxIndex) {
            maxIndex = index;
            latestTerm = code as ShippingTermCode;
        }
    });

    return latestTerm;
};

export const getShippingPath = (from: string, to: string): typeof SHIPPING_TERMS[number][] => {
    const fromIndex = getShippingTermIndex(from);
    const toIndex = getShippingTermIndex(to);

    if (fromIndex === -1 || toIndex === -1) return [];

    if (fromIndex <= toIndex) {
        return SHIPPING_TERMS.slice(fromIndex, toIndex + 1) as unknown as typeof SHIPPING_TERMS[number][];
    } else {
        // In case 'to' is earlier than 'from' (odd but handle it)
        return SHIPPING_TERMS.slice(toIndex, fromIndex + 1).reverse() as unknown as typeof SHIPPING_TERMS[number][];
    }
};
