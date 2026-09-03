/**
 * ISSUE #87 — شاشتا البداية للقالبين.
 *
 * #77 القسم ٦: كل قالبٍ له «شاشة بداية». `core/shell_manifest.py` يذكر
 * `start_view: "dashboard"` لكلا القالبين — نفس مفتاح الشاشة الذي يفتح عليه
 * أي مستخدم أصلاً (`App.tsx` — `useState<AppView>("dashboard")`)، فالبيان لا
 * يحتاج مفتاحاً جديداً. ما يتغيّر هو **محتوى** هذه الشاشة حسب قالب الشركة —
 * دالّةٌ صرفة هنا كي يبقى قرار «أيّ شاشة تُرسَم» قابلاً للاختبار بلا React.
 */

export type HomeScreenKind = "office-dashboard" | "financial-position" | "default";

export function resolveHomeScreen(template: string | null | undefined): HomeScreenKind {
  if (template === "accounting_firm") return "office-dashboard";
  if (template === "client_book") return "financial-position";
  return "default";
}

/**
 * ISSUE #87 (مراجعة) — بوابة ترخيص `accountant_portal` أمام شاشة «الوضع
 * المالي». `client_book` صار يُرخَّص تلقائياً عند الزرع (`tenants/services.py`
 * — `create_company`)، لكن دفاتر **قائمة** أُنشئت قبل هذا الإصلاح تبقى بلا
 * ترخيص، ونقاط `ClientSummaryView`/`ClientTrendView` تردّ 404 بلا `X-Tenant-Id`
 * مرخَّص (`guard_module_surface`). تفشل الشاشة إغلاقاً بصريح لا صمتاً: `false`
 * أو غياب المفتاح = غير مرخَّصة (نفس منطق `moduleAllowsView` في
 * `utils/viewPermissions.ts`) — لا افتراض نجاح.
 */
export type ModuleGateStatus = "loading" | "unlicensed" | "ready";

export function resolveModuleGate(
  loading: boolean,
  moduleEnabled: boolean | undefined,
): ModuleGateStatus {
  if (loading) return "loading";
  if (moduleEnabled !== true) return "unlicensed";
  return "ready";
}
