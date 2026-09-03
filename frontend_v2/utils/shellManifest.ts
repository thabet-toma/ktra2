/**
 * ISSUE #83 — بيان الواجهة: نقطة القراءة الواحدة على جانب الواجهة.
 *
 * الحقيقة تصل من الخادم على حمولة `/api/permissions/me` نفسها (`shell`،
 * `core/shell_manifest.py`) — `null` لـ`general` (والقوالب بلا بيان)، وهو
 * إشارة «استعمل شريط `Sidebar.tsx` اليدوي حرفياً كما هو».
 *
 * **القاعدة الملزِمة (جوهر التذكرة): البيان عرضٌ لا تصريح.** قد يذكر البيان
 * شاشةً يرفضها القناع الحيّ القائم (`TEMPLATE_HIDDEN_VIEWS` في
 * `utils/viewPermissions.ts`) أو يرفضها ترخيص وحدة (`moduleAllowsView`)، أو
 * شاشةً لم تُبنَ بعد (`unbuilt_views`) — الدوال هنا تُقصيها قبل أي رسم. القناع
 * نفسه **لا يُمَسّ ولا يُنسَخ**: الفحص هنا نداءٌ إلى نفس الدالتين الموجودتين،
 * لا نسخة موازية.
 */
import { moduleAllowsView, permForView, templateHidesView } from "./viewPermissions.ts";
import { visibleLinks, type NavAccessLink } from "./navAccess.ts";

export interface ShellFirstAction {
  view: string;
  /** مفتاح معجم (`core.terminology`) — `resolveTerm(terms, label_term)`. */
  label_term?: string;
}

export interface ShellGroup {
  id: string;
  /** مفتاح معجم لعنوان المجموعة. */
  label_term?: string;
  /** مفاتيح شاشات (`AppView`) بترتيبها كما يريدها القالب. */
  views: string[];
}

export interface ShellManifest {
  start_view: string;
  first_action: ShellFirstAction;
  empty_state_term?: string;
  groups: ShellGroup[];
  /** شاشاتٌ يذكرها البيان بلا شاشةٍ فعلية بعد — تُحلّ إلى `dashboard`. */
  unbuilt_views?: string[];
}

const FALLBACK_VIEW = "dashboard";

/** أهذه الشاشة صالحةٌ للعرض فعلاً — لم تُبنَ بعد؟ رفضها القناع؟ ترخيصها مطفأ؟ */
export function manifestViewIsUsable(
  view: string,
  template: string | null | undefined,
  unbuiltViews: readonly string[] = [],
  modules?: Record<string, boolean> | null,
): boolean {
  return (
    !unbuiltViews.includes(view) &&
    !templateHidesView(view, template) &&
    moduleAllowsView(view, modules)
  );
}

/**
 * يحلّ شاشةً مذكورة في البيان إلى شاشةٍ صالحة للتنقّل — يسقط إلى `dashboard`
 * لِما لم يُبنَ بعد أو رفضه القناع أو الترخيص. لا يُستعمل لتصفية قوائم — لذلك
 * {@link filterShellGroups}.
 */
export function resolveManifestView(
  view: string,
  template: string | null | undefined,
  unbuiltViews: readonly string[] = [],
  modules?: Record<string, boolean> | null,
): string {
  return manifestViewIsUsable(view, template, unbuiltViews, modules) ? view : FALLBACK_VIEW;
}

/**
 * إجراء البيان الأول محلولاً لواجهة استهلاكٍ مباشرة (شريط الإجراءات السريعة
 * وقائمة الفأرة اليمنى): شاشته مُحلولة (تسقط إلى `dashboard` عند اللزوم)
 * ولافتته من المعجم. `null` حين لا بيان لهذا القالب — المستهلك يبقي افتراضه
 * القديم (`general`).
 */
export function resolveShellFirstAction(
  shell: ShellManifest | null | undefined,
  template: string | null | undefined,
  term: (key: string) => string,
  modules?: Record<string, boolean> | null,
): { view: string; label: string } | null {
  if (!shell?.first_action) return null;
  const { view, label_term } = shell.first_action;
  return {
    view: resolveManifestView(view, template, shell.unbuilt_views, modules),
    label: label_term ? term(label_term) : view,
  };
}

/**
 * يُقصي من كل مجموعة ما يرفضه القناع أو الترخيص أو لم يُبنَ بعد — القاعدة
 * الملزِمة للتذكرة #83: بيانٌ يذكر شاشةً يرفضها القناع لا يُظهرها. مجموعةٌ
 * تُقصى شاشاتها كلّها تُحذف بلا رأسٍ فارغ.
 */
export function filterShellGroups(
  groups: readonly ShellGroup[],
  template: string | null | undefined,
  unbuiltViews: readonly string[] = [],
  modules?: Record<string, boolean> | null,
): ShellGroup[] {
  return groups
    .map((g) => ({
      ...g,
      views: g.views.filter((v) => manifestViewIsUsable(v, template, unbuiltViews, modules)),
    }))
    .filter((g) => g.views.length > 0);
}

export interface ResolvedShellGroup {
  id: string;
  label_term?: string;
  views: string[];
}

/**
 * يبني أقسام الشريط **الجاهزة للرسم** من البيان — دالّةٌ صرفة بلا React، تُختبر
 * بلا رسمٍ ولا سياق (`Sidebar.tsx` يستهلكها ويُلبس كل مفتاح شاشةٍ أيقونته
 * وتسميته المحليّتين فقط). ثلاث مراحل بالترتيب:
 *
 * 1. القناع الحيّ والترخيص وما لم يُبنَ بعد — {@link filterShellGroups}.
 * 2. الصلاحية — `visibleLinks`/`permForView` **نفس ما يحرس بقية الشريط**، لا
 *    فحصاً موازياً؛ ومفتاحان قديمان («الرئيسية» و«دفاتر عملائي») كانا مقصورين
 *    على المدير بلا مدخل في كتالوج الصلاحيات (`viewPermissions.ts`) — القاعدة
 *    نفسها تُطبَّق هنا عبر `managerOnlyViews` كي لا تنقلب متاحةً للجميع بمجرّد
 *    دخولها البيان.
 * 3. مجموعةٌ فرغت شاشاتها كلّها (بالقناع أو بالصلاحية) **تُحذف كاملةً** — لا
 *    عنوان مجموعةٍ يتيماً بلا رابطٍ تحته.
 *
 * `general` (`shell` غائب) تعيد `[]` فوراً — لا معالجة، ولا هذه الدالة تُستدعى
 * أصلاً من الفرع الذي يرسم شريطه اليدوي كما هو.
 */
export function buildShellSections(
  shell: ShellManifest | null | undefined,
  template: string | null | undefined,
  modules: Record<string, boolean> | null | undefined,
  can: (key: string) => boolean,
  role?: string,
  managerOnlyViews: readonly string[] = [],
  isManager = false,
): ResolvedShellGroup[] {
  if (!shell) return [];
  const masked = filterShellGroups(shell.groups, template, shell.unbuilt_views, modules);
  return masked
    .map((g) => {
      const candidates: NavAccessLink[] = g.views
        .filter((v) => (managerOnlyViews.includes(v) ? isManager : true))
        .map((v) => ({ key: v, perm: permForView(v) }));
      const views = visibleLinks(candidates, can, role).map((l) => l.key);
      return { id: g.id, label_term: g.label_term, views };
    })
    .filter((g) => g.views.length > 0);
}
