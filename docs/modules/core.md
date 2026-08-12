# core — الطبقة المشتركة

## الغرض

ليس دومين أعمال، بل **البنية التي تقف تحت كل الدومينات**: عزل الشركة، الصلاحيات،
الترقيم، الكاش، التقارير، الوحدات المرخّصة، حدود الخطط، الداشبورد، والمساعد الذكي.
وهو أيضاً موطن `settings.py` و`urls.py` الجذر.

**لماذا يهمّك حتى لو كانت مهمتك في app آخر:** كل ViewSet في المشروع يرث حلّ الشركة
والصلاحيات من هنا. أي تسريب بيانات بين الشركات سببه مخالفة قاعدة من هذا الملف.

## أهم الملفات

| الملف | الغرض |
|---|---|
| `core/tenant_utils.py` | حلّ الشركة والفرع من الطلب — **نقطة العزل الوحيدة** |
| `core/mixins.py` | `BaseTenantViewSet` — الفلترة التلقائية بالشركة |
| `core/access.py` | كتالوج الصلاحيات ومصفوفة الأدوار والإنفاذ |
| `core/permissions.py` · `core/permissions_api.py` | صنف الصلاحية لـDRF + نقطة `/api/permissions/me/` |
| `core/modules.py` | أي وحدة مرخّصة مفعّلة لأي شركة |
| `core/plans.py` | حدود الخطط (عدد الفواتير/المستخدمين…) |
| `core/pagination.py` | صنفا الترقيم — الإلزامي والاختياري |
| `core/reports/` | **حزمة** — إطار التقارير + 8 وحدات دومين |
| `core/reports_api.py` | نقطتا الفهرس والتشغيل + كاش التقارير |
| `core/payments.py` | منطق الدفع المشترك بين المبيعات والمشتريات |
| `core/api_defaults.py` | إعدادات المصادقة الموحّدة + `PagePartnerBalanceMixin` |
| `core/cache_backends.py` | خلفية كاش لا تُسقط الطلب عند تعثّر نظام الملفات |
| `core/dashboard_api.py` | تجميع الداشبورد خادمياً (كاش مفتاحه الشركة) |
| `core/activity.py` · `core/activity_views.py` | سجلّ النشاط |
| `core/assistant_*.py` · `core/ollama_assistant.py` | المساعد الذكي وأدواته |
| `core/platform_admin_api.py` | لوحة السوبر أدمن (شركات/أعضاء/إيقاف) |
| `core/settings.py` | الإعدادات — الكاش، الحدود، الأمان، قاعدة البيانات |

## الـModels

`core` بلا نماذج دومين تقريباً. في `core/models.py`: `SystemAttachment` (مرفقات
موحّدة) ودروس المساعد. النماذج المركزية للعزل تسكن في `tenants`.

## دوال الـservices العامة

```python
# core/tenant_utils.py — العزل
get_tenant(request, *, raise_on_missing=False)   # X-Tenant-Id ← user.tenant_id ← شركة وحيدة
get_branch(request)                              # X-Branch-Id، يرفض فرع شركة أخرى

# core/access.py — الصلاحيات
user_has_perm(user, tenant, key) -> bool
require_perm(request, key, tenant=None)          # يرفع 403
@requires_perm(key)                              # مزخرِف على الـaction

# core/reports/_framework.py — التقارير
register(spec: ReportSpec)                       # تسجيل تقرير جديد
run_report(key, tenant_id, params) -> dict       # أعمدة + صفوف + إجماليات
report_catalog() -> list                         # الفهرس مجمَّعاً بالفئات

# core/payments.py — الدفع المشترك
validate_payment(ctx) · post_payment(...) · document_payment_summary(total, paid)
```

## أهم الـAPI endpoints

الفهرس الكامل (692 نقطة) في `docs/API_INDEX.md` — مولَّد.

| المسار | الغرض |
|---|---|
| `/api/reports/` · `/api/reports/<key>/` | فهرس التقارير وتشغيلها |
| `/api/permissions/me/` | أعلام الصلاحيات — **للعرض فقط، لا تحمي endpoint** |
| `/api/dashboard/` | تجميع الداشبورد |
| `/api/platform/…` | لوحة السوبر أدمن |

## الاعتماديات

**يعتمد على:** `tenants` (النماذج المركزية) · `accounting` (قراءات التقارير).
**يعتمد عليه:** كل الـapps — عبر `get_tenant` و`BaseTenantViewSet` و`require_perm`.

## قواعد لا يجوز كسرها

1. **`get_queryset` بلا فلتر شركة = تسريب بيانات.** عند غياب الشركة أعِد `.none()`
   لا queryset غير مفلتر.
2. **أعلام الصلاحيات في الواجهة للعرض فقط** — إخفاء زر ليس حماية؛ الإنفاذ خادمي
   بـ`require_perm`.
3. **الوحدة المرخّصة غير المفعّلة ترد 404 لا 403** (`core/modules.py`) — 403 يكشف
   وجود الوحدة.
4. **الكاش مُسرِّع لا مصدر حقيقة** — تعثّره لا يُسقط طلباً أبداً
   (`core/cache_backends.py`)، وكل مفتاح كاش يحمل الشركة.
5. **تقرير جديد = `ReportSpec` واحد** يُسجَّل في وحدة الدومين المناسبة داخل
   `core/reports/` — لا تلمس `core/reports_api.py`.
6. **سقف صفوف التقرير يُقصّ بعد حساب الإجماليات** — الإجمالي يُحسب على الصفوف
   كاملةً، فالمعروض ينقص والمجموع لا يكذب.
7. **«اليوم» = `timezone.localdate()` دائماً — لا `date.today()`.** الأولى تاريخ
   العمل بحسب `TIME_ZONE` (`Asia/Hebron`)، والثانية تاريخ نظام الخادم. خلطهما
   كان يؤرّخ مستندات ما بعد منتصف الليل بيوم أمس. يحرسه
   `core/tests/test_docs_freshness.py`.

## الاختبارات المهمة

| الملف | يحرس |
|---|---|
| `core/tests/test_docs_freshness.py` | ألا تتعفّن وثائق التنقّل بصمت |
| `core/tests/test_cache_resilience.py` | ألا يُسقط تعثّر الكاش الطلبَ |
| `core/tests/test_global_throttle.py` | حدود المعدّل العامة |
| `core/tests/test_reports.py` | صحة التقارير وثبات عدّ الاستعلامات |
| `core/tests/test_dashboard_isolation.py` | عزل الداشبورد بين الشركات |
