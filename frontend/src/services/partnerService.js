import axios from 'axios';

const API_URL = 'http://localhost:8000/api/partners/';

const getPartners = async () => {
    const response = await axios.get(API_URL);
    return Array.isArray(response.data) ? response.data : (response.data.results || []);
};

const createPartner = async (partnerData) => {
    // dealing with image upload and bank accounts requires FormData
    const formData = new FormData();

    // Extract bank_accounts separately
    const bankAccounts = partnerData.bank_accounts || [];
    const internalData = { ...partnerData };
    delete internalData.bank_accounts;

    // Append all partner data
    for (const key in internalData) {
        if (internalData[key] !== null && internalData[key] !== undefined && internalData[key] !== '') {
            formData.append(key, internalData[key]);
        }
    }

    // Append bank accounts as JSON string (always, to allow empty list sync)
    formData.append('bank_accounts', JSON.stringify(bankAccounts));

    const response = await axios.post(API_URL, formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

const updatePartner = async (id, partnerData) => {
    const formData = new FormData();
    const bankAccounts = partnerData.bank_accounts || [];
    const internalData = { ...partnerData };
    delete internalData.bank_accounts;

    for (const key in internalData) {
        if (internalData[key] !== null && internalData[key] !== undefined) {
            let value = internalData[key];

            // Skip image if it's already a URL
            if (key === 'image_path' && typeof value === 'string') continue;

            // Cast numeric fields to numbers (backend expects Decimal)
            if ((key === 'credit_limit' || key === 'opening_balance') && value === '') {
                value = 0;
            } else if (key === 'credit_limit' || key === 'opening_balance') {
                value = Number(value);
            }

            formData.append(key, value);

        }
    }

    // Append bank accounts as JSON string (always)
    formData.append('bank_accounts', JSON.stringify(bankAccounts));

    const response = await axios.patch(`${API_URL}${id}/`, formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

const partnerService = {
    getPartners,
    createPartner,
    updatePartner,
};

export default partnerService;
