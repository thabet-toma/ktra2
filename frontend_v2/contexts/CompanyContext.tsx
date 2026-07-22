import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { resolveTenantId } from "../utils/tenantContext";
import { apiGetObject, apiPostObject } from "../services/restApi";
import { useAuth } from "./AuthContext";
import { clientLogger } from "../services/logger";

export type Tenant = {
  TenantID: number;
  CompanyName: string;
  SubscriptionPlan: string;
  Status: string;
  CreatedAt: string;
  import_enabled?: boolean;
};

export type CompanyMembership = {
  id: number;
  tenant: Tenant;
  role: string;
  is_default: boolean;
  created_at: string;
  can_access_import?: boolean;
};

interface CompanyContextType {
  companies: CompanyMembership[];
  currentCompany: Tenant | null;
  loading: boolean;
  error: string | null;
  /** صلاحية وحدة الاستيراد للشركة النشطة — يشترط تفعيل الشركة للجميع (حتى السوبر أدمن). */
  canAccessImport: boolean;
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
  const [error, setError] = useState<string | null>(null);
  const requestVersionRef = useRef(0);
  const activeUserIdRef = useRef<string | null>(currentUser ? String(currentUser.id) : null);
  activeUserIdRef.current = currentUser ? String(currentUser.id) : null;

  const fetchCompanies = async (options?: {
    preferredTenantId?: number;
    commit?: boolean;
  }): Promise<CompanyMembership[] | null> => {
    const requestVersion = ++requestVersionRef.current;
    const shouldCommit = options?.commit !== false;
    if (shouldCommit) {
      setLoading(true);
      setError(null);
    }
    const token = localStorage.getItem("token");
    if (!token || !currentUser) {
      if (shouldCommit && requestVersion === requestVersionRef.current) {
        setCompanies([]);
        setCurrentCompany(null);
        localStorage.removeItem("tenantId");
        localStorage.removeItem("branchId");
        setLoading(false);
      }
      return [];
    }
    const requesterUserId = String(currentUser.id);

    try {
      const data = await apiGetObject<CompanyMembership[]>(
        "tenants/companies/my-companies/"
      );
      // A response that started for a previous user/session must never restore
      // companies or tenant storage after logout or a user switch.
      if (
        requestVersion !== requestVersionRef.current ||
        activeUserIdRef.current !== requesterUserId
      ) return null;
      if (!shouldCommit) return data;
      setCompanies(data);

      if (data.length === 0) {
        localStorage.removeItem("tenantId");
        localStorage.removeItem("branchId");
        setCurrentCompany(null);
        clientLogger.info("onboarding.memberships_loaded", { count: 0 });
        return data;
      }

      // Resolve active tenant
      const activeTid = options?.preferredTenantId ?? resolveTenantId();
      let activeMember = data.find((m) => m.tenant.TenantID === activeTid);
      if (!activeMember && data.length > 0) {
        const defaultMember = data.find((m) => m.is_default);
        activeMember = defaultMember || data[0];
      }

      localStorage.setItem("tenantId", String(activeMember!.tenant.TenantID));
      setCurrentCompany(activeMember ? activeMember.tenant : null);
      clientLogger.info("onboarding.memberships_loaded", { count: data.length });
      return data;
    } catch {
      if (
        requestVersion !== requestVersionRef.current ||
        activeUserIdRef.current !== requesterUserId
      ) return null;
      if (!shouldCommit) return null;
      const message = "تعذّر تحميل شركاتك. تحقق من الاتصال ثم حاول مرة أخرى.";
      setError(message);
      setCompanies([]);
      setCurrentCompany(null);
      clientLogger.error("onboarding.memberships_load_failed");
      return null;
    } finally {
      if (shouldCommit && requestVersion === requestVersionRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void fetchCompanies();
  }, [currentUser]);

  const switchCompany = async (companyId: number) => {
    setLoading(true);
    try {
      localStorage.setItem("tenantId", String(companyId));
      // task11 M4: الفرع النشط تابع للشركة — تبديل الشركة يمسحه
      localStorage.removeItem("branchId");
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
    // Do not activate the tenant from the POST response alone. The membership
    // read is the source of truth for onboarding completion and owner role.
    const memberships = await fetchCompanies({ commit: false });
    const confirmedMembership = memberships?.find(
      (membership) =>
        membership.tenant.TenantID === newCompany.TenantID &&
        membership.role === "manager" &&
        membership.is_default === true
    );
    if (!confirmedMembership) {
      throw new Error("تم إرسال طلب الإنشاء، لكن تعذّر تأكيد عضوية المدير الافتراضية. أعد تحميل الصفحة للتحقق.");
    }
    setCompanies(memberships!);
    setCurrentCompany(confirmedMembership.tenant);
    localStorage.setItem("tenantId", String(confirmedMembership.tenant.TenantID));
    localStorage.removeItem("branchId");
    return confirmedMembership.tenant;
  };

  // صلاحية الاستيراد للشركة النشطة (تتفاعل مع تبديل الشركة) — تفعيل الشركة شرطٌ للجميع.
  const activeMembership = currentCompany
    ? companies.find((m) => m.tenant.TenantID === currentCompany.TenantID)
    : undefined;
  const canAccessImport =
    !!currentCompany?.import_enabled &&
    (!!currentUser?.isSuperAdmin ||
      activeMembership?.role === "manager" ||
      !!activeMembership?.can_access_import);

  return (
    <CompanyContext.Provider
      value={{
        companies,
        currentCompany,
        canAccessImport,
        // Reflects the actual fetch state only. Deriving loading from
        // `companies.length === 0` would hang the switcher forever for a user
        // with no memberships (e.g. a superuser created after the backfill).
        loading,
        error,
        switchCompany,
        createCompany,
        refreshCompanies: async () => { await fetchCompanies(); },
      }}
    >
      {children}
    </CompanyContext.Provider>
  );
};
