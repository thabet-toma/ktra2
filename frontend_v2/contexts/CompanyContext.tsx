import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { pickActiveMembership, storedTenantId } from "../utils/tenantContext";
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
  is_example?: boolean;
  /**
   * ST-3: معرّف المتجر العام — `null` أو غياب = المتجر مقفل، فلا حقل تفعيل
   * ثانٍ. للقراءة فقط هنا: كتابته تمرّ من `set-store-slug` وحدها
   * (`services/storeAdminApi.ts`)، ثم `refreshCompanies()` لتحديث هذه القيمة.
   */
  store_slug?: string | null;
  /**
   * T-TRIAL: آخر يوم كتابة مسموح (YYYY-MM-DD) — `null` أو غياب = اشتراك بلا
   * انتهاء. الحقلان التاليان محسوبان في الخادم من نفس الدالّة التي يسأل عنها
   * حارس الكتابة، فلا يعرض الشريط يوماً ويمنع الخادم في غيره.
   */
  subscription_ends_at?: string | null;
  /** 0 = آخر يوم عمل · سالب = منتهٍ · `null` = بلا انتهاء. */
  subscription_days_left?: number | null;
  subscription_expired?: boolean;
  /** ISSUE #50: مفتاح قالب الشركة — للقراءة فقط، يُضبَط مرة واحدة عند الإنشاء. */
  template?: string;
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
  createCompany: (name: string, template?: string) => Promise<Tenant>;
  /** T-IMPOFFER: الشركة التي تُفتح تلقائياً عند كل تسجيل دخول. */
  setDefaultCompany: (companyId: number) => Promise<void>;
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
  const { currentUser, loading: authLoading } = useAuth();
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

      // Resolve active tenant. `storedTenantId` (not `resolveTenantId`) because
      // the latter fabricates 1 when nothing is stored — that fabricated value
      // was being honoured as an explicit choice, so a fresh login opened tenant
      // 1 instead of the user's default company.
      const activeMember = pickActiveMembership(
        data,
        options?.preferredTenantId ?? storedTenantId(),
      );

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
    if (authLoading) return;
    void fetchCompanies();
  }, [currentUser, authLoading]);

  const switchCompany = async (companyId: number) => {
    setLoading(true);
    try {
      localStorage.setItem("tenantId", String(companyId));
      // task11 M4: الفرع النشط تابع للشركة — تبديل الشركة يمسحه
      localStorage.removeItem("branchId");
      clientLogger.info("company.switch_requested", { tenantId: companyId });
      window.location.reload();
    } catch (e) {
      console.error("Failed to switch company:", e);
      setLoading(false);
    }
  };

  const createCompany = async (name: string, template?: string): Promise<Tenant> => {
    const newCompany = await apiPostObject<Tenant>("tenants/companies/", {
      CompanyName: name,
      ...(template ? { template } : {}),
    });
    // Do not activate the tenant from the POST response alone. The membership
    // read is the source of truth for onboarding completion and owner role.
    const memberships = await fetchCompanies({ commit: false });
    // `is_default` **ليس** شرط نجاح: `create_company` تجعلها افتراضية للشركة
    // الأولى وحدها (`is_first`)، فكل شركةٍ ثانيةٍ فصاعداً كانت تُنشأ بنجاح ثم
    // تُقابَل برسالة فشلٍ حمراء. الشرط الصحيح هو العضوية بدور مدير.
    const confirmedMembership = memberships?.find(
      (membership) =>
        membership.tenant.TenantID === newCompany.TenantID &&
        membership.role === "manager"
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

  /**
   * T-IMPOFFER: تثبيت الشركة الافتراضية. النقطة النهائية كانت موجودة في الخادم
   * (`tenants/companies/set-default/`) وبلا أي مستدعٍ في الواجهة، فلم يكن للمستخدم
   * أي طريق ليقول «هذه شركتي التي تُفتح أول ما أدخل».
   */
  const setDefaultCompany = async (companyId: number) => {
    await apiPostObject("tenants/companies/set-default/", {
      company_id: companyId,
    });
    clientLogger.info("company.default_changed", { tenantId: companyId });
    setCompanies((prev) =>
      prev.map((membership) => ({
        ...membership,
        is_default: membership.tenant.TenantID === companyId,
      })),
    );
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
        setDefaultCompany,
        refreshCompanies: async () => { await fetchCompanies(); },
      }}
    >
      {children}
    </CompanyContext.Provider>
  );
};
