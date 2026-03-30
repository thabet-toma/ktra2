import axios from 'axios';

const API_URL = 'http://localhost:8000/api/inventory/';

const inventoryService = {
    // Categories
    getCategories: async (rootOnly = false) => {
        const response = await axios.get(`${API_URL}categories/`, {
            params: rootOnly ? { root_only: 'true' } : {}
        });
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    },
    createCategory: async (data) => {
        const response = await axios.post(`${API_URL}categories/`, data);
        return response.data;
    },
    updateCategory: async (id, data) => {
        const response = await axios.put(`${API_URL}categories/${id}/`, data);
        return response.data;
    },
    deleteCategory: async (id) => {
        const response = await axios.delete(`${API_URL}categories/${id}/`);
        return response.data;
    },

    // Units of Measure
    getUOMs: async () => {
        const response = await axios.get(`${API_URL}uom/`);
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    },

    // Products
    getProducts: async () => {
        const response = await axios.get(`${API_URL}products/`);
        return Array.isArray(response.data) ? response.data : (response.data.results || []);
    },
    createProduct: async (data) => {
        const response = await axios.post(`${API_URL}products/`, data);
        return response.data;
    },
    updateProduct: async (id, data) => {
        const response = await axios.put(`${API_URL}products/${id}/`, data);
        return response.data;
    },
    deleteProduct: async (id) => {
        const response = await axios.delete(`${API_URL}products/${id}/`);
        return response.data;
    }
};

export default inventoryService;
