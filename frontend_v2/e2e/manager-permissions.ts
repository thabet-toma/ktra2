import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * حمولةُ `/api/permissions/me/` لمديرٍ حقيقيّ — لمُحاكيات Playwright التي تريد
 * أن تُرسَم الشاشةُ كما يراها المدير لا أن تُحجَب.
 *
 * لماذا لا `permissions: []` مع `is_manager: true`: `PermissionsContext.can()`
 * تقرأ المجموعةَ وحدها بعد التحميل ولا تنظر إلى `is_manager`، وحارسُ `App.tsx`
 * (`canView`) يمرّ عليها — فالمجموعةُ الفارغة **تمنع كلَّ شاشةٍ محروسة** بصمت.
 * وردٌّ بـ`[]` لا كائنٍ يُسقط الشيءَ نفسه (`res.permissions.length` يرمي بعد
 * `setLoaded(true)`).
 *
 * المفاتيحُ تُقرأ من كتالوج الخادم نفسه (`core/access.py` — `PERMISSIONS`) لا
 * من قائمةٍ منسوخة: الخادم يمنح المديرَ `"*"` = كلَّ مفاتيح الكتالوج المرئية
 * للشركة (`role_default_permissions`)، ونسخةٌ يدويّةٌ هنا تتأخّر عن أوّل مفتاحٍ
 * جديد فيُحجَب بابُه في الاختبار بلا أن يحمرّ شيء. مفاتيحُ الوحدات المرخّصة
 * (`"module": ...`) مُستثناة كما يستثنيها الخادم لشركةٍ `modules: {}`.
 */
const ACCESS_PY = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "core", "access.py");

function readManagerKeys(): string[] {
  // نهاياتُ الأسطر `CRLF` على Windows بحسب `core.autocrlf` — تُطبَّع قبل البحث
  // عن نهاية القائمة.
  const source = readFileSync(ACCESS_PY, "utf8").replace(/\r\n/g, "\n");
  const start = source.indexOf("PERMISSIONS: list[dict] = [");
  const end = source.indexOf("\n]\n", start);
  if (start < 0 || end < 0) throw new Error(`manager-permissions: كتالوج PERMISSIONS غير موجود في ${ACCESS_PY}`);
  const keys = source
    .slice(start, end)
    .split("\n")
    .filter((line) => line.includes('"key":') && !line.includes('"module":'))
    .map((line) => /"key":\s*"([^"]+)"/.exec(line)?.[1])
    .filter((key): key is string => !!key);
  // حارسُ القراءة نفسها: تغييرُ شكل الكتالوج (مدخلٌ على أسطر) يجب أن يُسقط
  // الاختبارَ هنا لا أن يُنتج مديراً بلا صلاحياتٍ فتُحجب الشاشات بصمت.
  if (keys.length < 50 || !keys.includes("sales.payment.create")) {
    throw new Error(`manager-permissions: قُرئ ${keys.length} مفتاحاً فقط من ${ACCESS_PY}`);
  }
  return keys;
}

export const MANAGER_PERMISSION_KEYS: readonly string[] = readManagerKeys();

/** بشكل `MyPermissions` (`services/permissionsApi.ts`) كما يقرؤه `PermissionsContext`. */
export function managerPermissionsBody() {
  return {
    role: "manager",
    is_manager: true,
    permissions: [...MANAGER_PERMISSION_KEYS],
    modules: {},
    template: "general",
    terms: {},
    shell: null,
    ui_mode: "advanced",
  };
}
