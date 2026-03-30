import axios from 'axios';

/**
 * عميل محاسبة يضيف تلقائياً Token من localStorage إن وُجد
 * (نفس التوكن الذي يستخدمه frontend v2 بعد تسجيل الدخول من K.T.R.A).
 */
const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE || 'http://localhost:8000/api',
});

api.interceptors.request.use((config) => {
  try {
    const t = localStorage.getItem('token');
    if (t) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Token ${t}`;
    }
  } catch {
    /* ignore */
  }
  return config;
});

const accountingService = {
  getAccounts: async () => {
    const response = await api.get('/accounting/accounts/');
    return Array.isArray(response.data) ? response.data : (response.data.results || []);
  },
  createAccount: async (accountData) => {
    const response = await api.post('/accounting/accounts/', accountData);
    return response.data;
  },
  updateAccount: async (id, accountData) => {
    const response = await api.patch(`/accounting/accounts/${id}/`, accountData);
    return response.data;
  },
  deleteAccount: async (id) => {
    const response = await api.delete(`/accounting/accounts/${id}/`);
    return response.data;
  },

  getJournals: async () => {
    const response = await api.get('/accounting/journals/');
    return Array.isArray(response.data) ? response.data : (response.data.results || []);
  },
  getJournal: async (id) => {
    const response = await api.get(`/accounting/journals/${id}/`);
    return response.data;
  },
  createJournal: async (journalData) => {
    const response = await api.post('/accounting/journals/', journalData);
    return response.data;
  },
  updateJournal: async (id, journalData) => {
    const response = await api.patch(`/accounting/journals/${id}/`, journalData);
    return response.data;
  },
  postJournal: async (id) => {
    const response = await api.post(`/accounting/journals/${id}/post/`);
    return response.data;
  },
  deleteJournal: async (id) => {
    const response = await api.delete(`/accounting/journals/${id}/`);
    return response.data;
  },

  getPartners: async () => {
    const response = await api.get('/partners/');
    return Array.isArray(response.data) ? response.data : (response.data.results || []);
  },

  getCostCenters: async () => {
    const response = await api.get('/accounting/cost-centers/');
    return Array.isArray(response.data) ? response.data : (response.data.results || []);
  },
  createCostCenter: async (data) => {
    const response = await api.post('/accounting/cost-centers/', data);
    return response.data;
  },

  getCheques: async () => {
    const response = await api.get('/accounting/cheques/');
    return Array.isArray(response.data) ? response.data : (response.data.results || []);
  },
  createCheque: async (data) => {
    const response = await api.post('/accounting/cheques/', data);
    return response.data;
  },
  updateCheque: async (id, data) => {
    const response = await api.patch(`/accounting/cheques/${id}/`, data);
    return response.data;
  },
  deleteCheque: async (id) => {
    const response = await api.delete(`/accounting/cheques/${id}/`);
    return response.data;
  },

  getGeneralLedger: async (params) => {
    const response = await api.get('/accounting/general-ledger/', { params });
    return response.data;
  },
  getTrialBalance: async (params) => {
    const response = await api.get('/accounting/trial-balance/', { params });
    return response.data;
  },
};

export default accountingService;
