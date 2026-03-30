import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api/logistics';
// Reusing the partner API URL pattern if needed, but usually linked via IDs
const INVENTORY_API_URL = 'http://localhost:8000/api/inventory';

const logisticsService = {
    // --- Deals ---
    getDeals: async () => {
        const response = await axios.get(`${API_BASE_URL}/deals/`);
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    },
    getDeal: async (id) => {
        const response = await axios.get(`${API_BASE_URL}/deals/${id}/`);
        return response.data;
    },
    createDeal: async (data) => {
        const response = await axios.post(`${API_BASE_URL}/deals/`, data);
        return response.data;
    },
    updateDeal: async (id, data) => {
        const response = await axios.patch(`${API_BASE_URL}/deals/${id}/`, data);
        return response.data;
    },
    addItemToDeal: async (dealId, itemData) => {
        const response = await axios.post(`${API_BASE_URL}/deals/${dealId}/add_item/`, itemData);
        return response.data;
    },
    postDealToAccounting: async (id) => {
        const response = await axios.post(`${API_BASE_URL}/deals/${id}/post_to_accounting/`);
        return response.data;
    },
    postPaymentToAccounting: async (dealId, paymentId, bankAccountId) => {
        const data = bankAccountId ? { bank_account_id: bankAccountId } : {};
        const response = await axios.post(`${API_BASE_URL}/deals/${dealId}/post_payment/${paymentId}/`, data);
        return response.data;
    },
    deleteDealItem: async (itemId) => {
        // Assuming a separate endpoint or nested delete might be needed, 
        // but for now let's assume we might need a specific viewset for items or use the main one.
        // Since we didn't explicitly make an ItemViewSet, we might need to add it or handle via updates.
        // Let's add a placeholder or assume the user update the whole deal. 
        // Ideally, we should have an endpoint for items. check views.py... 
        // We only made LogisticsDealViewSet. Let's rely on updating the deal or adding items.
        // Placeholder for delete deal item logic if needed
    },

    // --- Shipments ---
    getShipments: async () => {
        const response = await axios.get(`${API_BASE_URL}/shipments/`);
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    },
    createShipment: async (data) => {
        const response = await axios.post(`${API_BASE_URL}/shipments/`, data);
        return response.data;
    },
    updateShipment: async (id, data) => {
        const response = await axios.patch(`${API_BASE_URL}/shipments/${id}/`, data);
        return response.data;
    },
    addDealToShipment: async (shipmentId, dealId) => {
        const response = await axios.post(`${API_BASE_URL}/shipments/${shipmentId}/add_deal/`, { deal_id: dealId });
        return response.data;
    },

    // --- Clearances ---
    getClearances: async () => {
        const response = await axios.get(`${API_BASE_URL}/clearances/`);
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    },
    createClearance: async (data) => {
        const response = await axios.post(`${API_BASE_URL}/clearances/`, data);
        return response.data;
    },

    // --- Expenses ---
    getExpenses: async () => {
        const response = await axios.get(`${API_BASE_URL}/expenses/`);
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    },
    createExpense: async (data) => {
        const response = await axios.post(`${API_BASE_URL}/expenses/`, data);
        return response.data;
    },
    postExpenseToAccounting: async (id) => {
        const response = await axios.post(`${API_BASE_URL}/expenses/${id}/post_to_accounting/`);
        return response.data;
    },

    // --- Helpers ---
    getProducts: async () => {
        const response = await axios.get(`${INVENTORY_API_URL}/products/`);
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    }
};

export default logisticsService;
