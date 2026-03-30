import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { CacheProvider } from '@emotion/react';
import createCache from '@emotion/cache';
import stylisRTL from 'stylis-plugin-rtl';
import { prefixer } from 'stylis';

import theme from './theme'; // Using the external premium theme
import './App.css';

// Components
import Layout from './components/Layout/Layout';
import PartnersList from './components/Partners/PartnersList';
import COATree from './components/Accounting/COATree';
import JournalEntry from './components/Accounting/JournalEntry';
import JournalList from './components/Accounting/JournalList';
import ChequeManagement from './components/Accounting/ChequeManagement';
import GeneralLedger from './components/Accounting/GeneralLedger';
import TrialBalance from './components/Accounting/TrialBalance';
import DealsDashboard from './components/Logistics/DealsDashboard';
import DealForm from './components/Logistics/DealForm';
import ShipmentManagement from './components/Logistics/ShipmentManagement';
import ClearanceManagement from './components/Logistics/ClearanceManagement';
import LogisticsExpenses from './components/Logistics/LogisticsExpenses';
import InvoicesPage from './components/Logistics/InvoicesPage';
import UnifiedInventoryDashboard from './components/Inventory/UnifiedInventoryDashboard';

// Create RTL cache
const cacheRtl = createCache({
  key: 'muirtl',
  stylisPlugins: [prefixer, stylisRTL],
});

function App() {
  return (
    <CacheProvider value={cacheRtl}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Router>
          <Layout>
            <Routes>
              <Route path="/" element={<Navigate to="/partners" replace />} />
              <Route path="/partners" element={<PartnersList />} />

              {/* Accounting Routes */}
              <Route path="/accounting/coa" element={<COATree />} />
              <Route path="/accounting/journals" element={<JournalList />} />
              <Route path="/accounting/journals/new" element={<JournalEntry />} />
              <Route path="/accounting/journals/:id" element={<JournalEntry />} />
              <Route path="/accounting/cheques" element={<ChequeManagement />} />
              <Route path="/accounting/general-ledger" element={<GeneralLedger />} />
              <Route path="/accounting/trial-balance" element={<TrialBalance />} />

              {/* Logistics Routes */}
              <Route path="/logistics/deals" element={<DealsDashboard />} />
              <Route path="/logistics/deals/new" element={<DealForm />} />
              <Route path="/logistics/deals/edit/:id" element={<DealForm />} />
              <Route path="/logistics/shipments" element={<ShipmentManagement />} />
              <Route path="/logistics/clearance" element={<ClearanceManagement />} />
              <Route path="/logistics/expenses" element={<LogisticsExpenses />} />
              <Route path="/logistics/invoices" element={<InvoicesPage />} />

              {/* Inventory Routes */}
              <Route path="/inventory" element={<UnifiedInventoryDashboard />} />
              <Route path="/inventory/categories" element={<UnifiedInventoryDashboard />} />
              <Route path="/inventory/products" element={<UnifiedInventoryDashboard />} />
              <Route path="/inventory/add-product" element={<UnifiedInventoryDashboard />} />
            </Routes>
          </Layout>
        </Router>
      </ThemeProvider>
    </CacheProvider>
  );
}

export default App;
