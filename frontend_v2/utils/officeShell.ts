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
