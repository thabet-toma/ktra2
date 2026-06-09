import React, { createContext, useContext, useEffect, useState } from "react";
import { resolveTenantId } from "../utils/tenantContext";
import { apiGetObject, apiPostObject } from "../services/restApi";
import { useAuth } from "./AuthContext";

export type Tenant = {
  TenantID: number;
  CompanyName: string;
  SubscriptionPlan: string;
  Status: string;
  CreatedAt: string;
};

export type CompanyMembership = {
  id: number;
  tenant: Tenant;
  role: string;
  is_default: boolean;
  created_at: string;
};

interface CompanyContextType {
  companies: CompanyMembership[];
  currentCompany: Tenant | null;
  loading: boolean;
  switchCompany: (companyId: number) => Promise<void>;
  createCompany: (name: string) => Promise<Tenant>;
  refreshCompanies: () => Promise<void>;
}

const CompanyContext = createContext<CompanyContextType | undefined>(undefined);

export const useCompany = () => {
  const context = useContext(CompanyContext);
  if (!context) {
    throw new Error("useCompany must be used within a CompanyProvider");
  }
  return context;
};

export const CompanyProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { currentUser } = useAuth();
  const [companies, setCompanies] = useState<CompanyMembership[]>([]);
  const [currentCompany, setCurrentCompany] = useState<Tenant | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchCompanies = async () => {
    const token = localStorage.getItem("token");
    if (!token || !currentUser) {
      setCompanies([]);
      setCurrentCompany(null);
      setLoading(false);
      return;
    }

    try {
      const data = await apiGetObject<CompanyMembership[]>(
        "tenants/companies/my-companies/"
      );
      setCompanies(data);

      // Resolve active tenant
      const activeTid = resolveTenantId();
      let activeMember = data.find((m) => m.tenant.TenantID === activeTid);
      if (!activeMember && data.length > 0) {
        const defaultMember = data.find((m) => m.is_default);
        activeMember = defaultMember || data[0];
        localStorage.setItem("tenantId", String(activeMember.tenant.TenantID));
      }

      setCurrentCompany(activeMember ? activeMember.tenant : null);
    } catch (e) {
      console.error("Failed to fetch companies:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCompanies();
  }, [currentUser]);

  const switchCompany = async (companyId: number) => {
    setLoading(true);
    try {
      localStorage.setItem("tenantId", String(companyId));
      window.location.reload();
    } catch (e) {
      console.error("Failed to switch company:", e);
      setLoading(false);
    }
  };

  const createCompany = async (name: string): Promise<Tenant> => {
    const newCompany = await apiPostObject<Tenant>("tenants/companies/", {
      CompanyName: name,
    });
    await fetchCompanies();
    return newCompany;
  };

  return (
    <CompanyContext.Provider
      value={{
        companies,
        currentCompany,
        // Reflects the actual fetch state only. Deriving loading from
        // `companies.length === 0` would hang the switcher forever for a user
        // with no memberships (e.g. a superuser created after the backfill).
        loading,
        switchCompany,
        createCompany,
        refreshCompanies: fetchCompanies,
      }}
    >
      {children}
    </CompanyContext.Provider>
  );
};
