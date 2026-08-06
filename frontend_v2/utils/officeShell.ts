/**
 * T-EXTACCT — مفتاح القشرة لحساب المحاسب القانوني (سوبر أدمن غالباً).
 *
 * الحساب من نوع `legal_accountant` يفتح قشرة المكتب (`/office`) لا واجهة الشركات
 * التجارية. سوبر أدمن يخرج منها للوحة المنصة بمفتاح جلسة — والرحلة **ذهاب وإياب**:
 *
 * - الخروج للمنصة يعيد الشركة التجارية التي كان يعمل عليها قبل دخول المكتب،
 *   وإلا بقيت واجهةُ الشركات مفتوحةً على **شركة المكتب** (أو على شركة زبون فتحها
 *   من المكتب) — وهي شركة بلا عمل تجاري، فتبدو الواجهة معطوبة.
 * - العودة للمكتب تحفظ الشركة التجارية الحالية من جديد، فتكون الرحلة التالية
 *   مثلها.
 *
 * دوالٌّ في مكان واحد لأن أربعة مواضع تبدّل القشرة: تهيئة `App`، وزر «العودة للوحة
 * المنصة» في المكتب، وزر «العودة لواجهة المكتب» في الشريط الجانبي، وزر فتح واجهة
 * المحاسب في لوحة السوبر أدمن.
 */
const SHELL_KEY = "ktra_shell";
const STASHED_TENANT_KEY = "ktra_shell_tenant";

/** مسارات ليست شاشات عمل شركة: بيت المكتب، وتسجيل المحاسب، ولوحة المنصة. */
const NON_WORKSPACE_PREFIXES = ["/office", "/accountant", "/super-admin"];
/** وجهات تلقائية لا نيّة صريحة فيها — لا تُبدّل قشرة المحاسب. */
const NEUTRAL_PATHS = new Set(["", "/", "/dashboard"]);

const normalizePath = (pathname: string): string => {
  const path = String(pathname || "").split("?")[0].split("#")[0];
  return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
};

/**
 * هل يقصد المسار شاشةَ عملٍ داخل شركة تجارية؟
 *
 * حساب المحاسب القانوني يفتح قشرة المكتب لكل مسار، فكان فتح «فاتورة مبيعات
 * جديدة» بالرابط يعرض لوحة المكتب والرابط يقول شيئاً آخر. الرابط الصريح لشاشة
 * شركة يحسم القشرة — كما أن `/office` يحسمها للمكتب في `platformShellActive`.
 *
 * `viewPaths` تُمرَّر من جدول المسارات في App فلا تتكرر القائمة هنا.
 */
export function companyWorkspaceDeepLink(
  pathname: string,
  viewPaths: readonly string[],
): boolean {
  const path = normalizePath(pathname);
  if (NEUTRAL_PATHS.has(path)) return false;
  const excluded = (p: string) => NON_WORKSPACE_PREFIXES.some(
    (prefix) => p === prefix || p.startsWith(`${prefix}/`),
  );
  if (excluded(path)) return false;
  return viewPaths.some((raw) => {
    const view = normalizePath(raw);
    if (!view || NEUTRAL_PATHS.has(view) || excluded(view)) return false;
    return path === view || path.startsWith(`${view}/`);
  });
}

/**
 * هل نعرض واجهة الشركات التجارية لحساب المحاسب؟
 * **المسار يحسم**: فتح `/office` يلغي التجاوز، فلا يعلق المستخدم في الواجهة
 * التجارية لأنه ضغط «العودة للوحة المنصة» مرة في هذا التبويب.
 */
export function platformShellActive(pathname: string): boolean {
  try {
    if (pathname.startsWith("/office")) {
      sessionStorage.removeItem(SHELL_KEY);
      return false;
    }
    return sessionStorage.getItem(SHELL_KEY) === "platform";
  } catch {
    return false;
  }
}

/** الانتقال لقشرة المكتب: تُحفظ الشركة التجارية الحالية للعودة إليها لاحقاً. */
export function enterOfficeShell(): void {
  try {
    const tenantId = localStorage.getItem("tenantId");
    if (tenantId) sessionStorage.setItem(STASHED_TENANT_KEY, tenantId);
    sessionStorage.removeItem(SHELL_KEY);
  } catch {
    /* ignore */
  }
}

/** الخروج للوحة المنصة: تُستعاد الشركة التجارية المحفوظة إن وُجدت. */
export function enterPlatformShell(): void {
  try {
    sessionStorage.setItem(SHELL_KEY, "platform");
    const stashed = sessionStorage.getItem(STASHED_TENANT_KEY);
    if (stashed) {
      localStorage.setItem("tenantId", stashed);
      // الفرع النشط تابع للشركة — تبديل الشركة يمسحه (task11 M4)
      localStorage.removeItem("branchId");
      sessionStorage.removeItem(STASHED_TENANT_KEY);
    }
  } catch {
    /* ignore */
  }
}
