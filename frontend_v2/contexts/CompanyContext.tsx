import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { pickActiveMembership, storedTenantId } from "../utils/tenantContext";
import { orderOfficesByPreference } from "../utils/managedBooks";
import { enterManagedBook, leaveManagedBook, managedBookOffice } from "../utils/officeShell";
import { createManagedBook as createManagedBookApi, listManagedBooks } from "../services/managedBooksApi";
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
  /**
   * ISSUE #52/#65: المكتب المالك إن كانت هذه الشركة دفترَ عميلٍ مُدار. `null`
   * أو غياب = شركةٌ عادية. للقراءة فقط: يُضبَط مرة واحدة عند الإنشاء من نقطة
   * `managed-books`.
   */
  managed_by?: number | null;
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
  /**
   * ISSUE #65 — دفاتر عملاء المكتب. **قناةٌ خاصة** لا امتدادٌ لـ`companies`:
   * الدفتر مستثنى من `my-companies` عمداً (#52) كي لا يزحم مبدّل الشركات، وهذه
   * القائمة هي بابه الوحيد.
   */
  managedBooks: Tenant[];
  /** الشركة التي تلعب دور المكتب — `null` فلا دفاتر ولا باب لها. */
  officeTenantId: number | null;
  /** هل الشركة النشطة الآن دفترُ عميلٍ دخلناه من مكتب؟ (طريق العودة ظاهر حينها) */
  insideManagedBook: boolean;
  openManagedBook: (bookId: number) => void;
  createManagedBook: (name: string, template: string) => Promise<Tenant>;
  returnToOffice: () => void;
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
  const [managedBooks, setManagedBooks] = useState<Tenant[]>([]);
  const [officeTenantId, setOfficeTenantId] = useState<number | null>(null);
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
      const explicitTenantId = options?.preferredTenantId ?? storedTenantId();

      // ISSUE #65: قناة دفاتر العملاء. تُقرأ قبل حسم الشركة النشطة لأن الدفتر
      // **ليس** في `my-companies`: بلا هذه القراءة كان الدخول إليه يُقابَل بأن
      // `pickActiveMembership` لا تجده فتُعيد الشركة الافتراضية وتكتب معرّفها
      // فوق معرّفه — أي أن الدخول للدفتر يُلغي نفسه في أول تحميل.
      const offices = orderOfficesByPreference(data, {
        bookOfficeId: managedBookOffice(),
        activeTenantId: explicitTenantId,
      });
      // شركةٌ من شركاته هو ⇒ لا دفتر نبحث عنه، فمكتبٌ واحد يكفي لتعبئة القائمة.
      const explicitIsOwnCompany = explicitTenantId != null
        && data.some((m) => m.tenant.TenantID === explicitTenantId);
      let officeId: number | null = offices.length ? offices[0].tenant.TenantID : null;
      let books: Tenant[] = [];
      let openBook: Tenant | undefined;
      for (let i = 0; i < offices.length; i += 1) {
        const candidate = offices[i].tenant.TenantID;
        const list = await listManagedBooks(candidate).catch(() => [] as Tenant[]);
        if (
          requestVersion !== requestVersionRef.current ||
          activeUserIdRef.current !== requesterUserId
        ) return null;
        if (i === 0) books = list;
        if (explicitTenantId == null || explicitIsOwnCompany) break;
        const found = list.find((book) => book.TenantID === explicitTenantId);
        if (found) {
          // المكتب المالك هو من وُجد عنده الدفتر — لا من رتّبناه أوّلاً. وإلا
          // مضى زرُّ العودة والحصّة إلى مكتبٍ لا يملك ما نحن فيه.
          officeId = candidate;
          books = list;
          openBook = found;
          break;
        }
      }
      setOfficeTenantId(officeId);
      setManagedBooks(books);

      if (openBook) {
        setCurrentCompany(openBook);
        clientLogger.info("onboarding.memberships_loaded", { count: data.length });
        return data;
      }
      if (explicitTenantId != null && !explicitIsOwnCompany) {
        // لم تُحلّ الشركة المطلوبة لا في شركاته ولا في دفاتر مكاتبه ⇒ سنقع على
        // الافتراضية بعد قليل. بلاغٌ صريح كي لا يبقى «فتحتُ دفتراً فوجدتُني في
        // شركةٍ أخرى» بلا أثرٍ في السجل.
        clientLogger.warn("company.explicit_tenant_unresolved", {
          tenantId: explicitTenantId, offices: offices.length,
        });
      }

      const activeMember = pickActiveMembership(data, explicitTenantId);

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
   * ISSUE #65 — فتح دفترٍ جديد لعميل. **من نقطة المكتب حصراً** (`managed-books`)
   * لا من `POST companies/`: تلك تتخطّى حصّة `office.managed_books` ولا تضبط
   * `managed_by`، فينتج دفترٌ يزحم مبدّل الشركات ولا يُحسب على المكتب.
   *
   * رسالة الحصّة تصعد كما هي من الخادم (`plan_limit`) — لا تُبتلع ولا تُستبدل
   * بـ«حدث خطأ»: هي الرسالة الوحيدة التي تقول لصاحب المكتب لماذا تَوقّف.
   */
  const createManagedBook = async (name: string, template: string): Promise<Tenant> => {
    if (officeTenantId === null) {
      throw new Error("لا يوجد مكتب محاسبة على حسابك لفتح دفاتر عملاء تحته.");
    }
    const book = await createManagedBookApi(officeTenantId, {
      CompanyName: name,
      template,
    });
    setManagedBooks((prev) => [...prev, book].sort(
      (a, b) => a.CompanyName.localeCompare(b.CompanyName, "ar"),
    ));
    clientLogger.info("office.book_opened", { tenantId: book.TenantID, template });
    return book;
  };

  /** الدخول إلى دفتر عميل — إعادة تحميل كاملة كما في `switchCompany`. */
  const openManagedBook = (bookId: number) => {
    // وجهةُ العودة: المكتب إن عُرف، وإلا الشركة التي كنّا فيها. الثاني احتياطٌ
    // لمكتبٍ بقالبٍ غير `accounting_firm` — يبقى له طريق عودةٍ لا أن يعلق.
    const origin = officeTenantId ?? currentCompany?.TenantID ?? null;
    if (origin === null) return;
    setLoading(true);
    enterManagedBook(bookId, origin);
    clientLogger.info("office.book_entered", { tenantId: bookId, officeTenantId: origin });
    window.location.assign("/dashboard");
  };

  /**
   * العودة من دفتر العميل إلى المكتب. الوجهة تتبع نوع الحساب: المحاسب القانوني
   * بيته قشرة `/office`، وصاحب شركةٍ بقالب مكتب بيته لوحة شركته نفسها.
   */
  const returnToOffice = () => {
    const office = leaveManagedBook() ?? officeTenantId;
    if (office != null) {
      localStorage.setItem("tenantId", String(office));
      localStorage.removeItem("branchId");
    }
    clientLogger.info("office.book_left", { officeTenantId: office });
    window.location.assign(
      currentUser?.accountType === "legal_accountant" ? "/office" : "/dashboard",
    );
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
  /**
   * ISSUE #65 — «أنا داخل دفتر عميل». شرطان: الشركة النشطة دفترٌ مُدار (حقيقةٌ
   * من الخادم لكل شركة)، ودخلناه من مكتبٍ في هذا التبويب (مفتاح الجلسة). الثاني
   * لازم لأن من فتح الدفتر بالرابط مباشرةً لا مكتبَ له يعود إليه، فزرُّ عودةٍ
   * بلا وجهة أسوأ من غيابه.
   */
  const insideManagedBook =
    currentCompany != null
    && currentCompany.managed_by != null
    && managedBookOffice() != null;
  const canAccessImport =
    !!currentCompany?.import_enabled &&
    (!!currentUser?.isSuperAdmin ||
      activeMembership?.role === "manager" ||
      // داخل دفتر العميل لا عضويةَ في `companies` (الدفتر مستثنى من
      // `my-companies`)، فكان مديرُ المكتب يفقد قائمة الاستيراد في دفترٍ
      // مُرخَّصٍ لها. الدخول لا يتاح إلا لمديري المكتب، والخادم يفرض.
      insideManagedBook ||
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
        managedBooks,
        officeTenantId,
        insideManagedBook,
        openManagedBook,
        createManagedBook,
        returnToOffice,
        setDefaultCompany,
        refreshCompanies: async () => { await fetchCompanies(); },
      }}
    >
      {children}
    </CompanyContext.Provider>
  );
};
