# platform_ops — مركز قيادة كترا وعمليات المنصة

> مبني على قراءة الكود مباشرةً بتاريخ 2026-09-09. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

وحدة داخلية على مستوى المنصة لإدارة موظفي عمليات كترا وخدمة متابعة الزبائن
والإدخال. ليست وحدةً مرخّصةً للشركات، لذلك لا تدخل `core/modules.py` ولا تعتمد
على `X-Tenant-Id`. مسارات الإدارة تحت `/api/platform/ops/` ومحروسة بصلاحيات
المنصة.

## أهم الملفات

| الملف | الغرض |
|---|---|
| `platform_ops/models.py` | هوية موظف المنصة، اشتراك الخدمة، الارتباطات (`Engagement`)، وسجل العضويات الممنوحة (`AgentGrantedMembership`) |
| `platform_ops/services.py` | بوابة الاشتراك، دورة حياة الارتباط (إسناد، تعليق، استئناف، إلغاء)، تعليق الاشتراكات، وسجل العضويات والمغادرة الـidempotent |
| `platform_ops/permissions.py` | حارسا موظف العمليات ومدير العمليات |
| `platform_ops/views.py` | نقاط القراءة الإدارية في المرحلة الأولى |
| `platform_ops/tests/test_isolation_guard.py` | قائمة الاستيراد البيضاء وحارس الاتجاهين |
| `platform_ops/tests/test_migration_graph.py` | سلامة رسم الهجرات (0001 و0002) واعتمادها على `tenants` |
| `platform_ops/tests/test_engagement_lifecycle.py` | دورة حياة الارتباط، فرادة الإسناد تحت قفل، حفظ عضوية الزبون، الاستئناف، والمغادرة |

## النماذج الحالية

| Model | الحقول والقواعد المهمة |
|---|---|
| `PlatformEmployee` | `user` واحد لواحد، `specialty`، `capacity_target`، وحالة `active/on_leave/offboarded`. بلا `tenant` عمداً لأنه موظف للمنصة لا لشركة. |
| `ServiceSubscription` | صف واحد لكل شركة، الحالة والباقة والرسم الشهري والحد والعداد وسعر العملية الزائدة ودورة الفوترة. `tenant` علاقة OneToOne تفرضها MySQL. |
| `Engagement` | ارتباط موظف بشركة: `active/suspended/revoked`، من أسند ومتى، طوابع التعليق والإلغاء، وحقل `created_membership` للتمييز بين العضوية المنشأة وعضوية الزبون المسبقة. فرادة النشط تحت قفل برمجي لا قيد شرطي. |
| `AgentGrantedMembership` | سجل العضويات الممنوحة أو المعدلة بواسطة وكيل: الشركة، الوكيل الفاعل، الارتباط، `role_before/role_after`، ولقطة هوية ثابتة (`identity_snapshot`) تبقى مقروءة ومفيدة حتى لو حُذفت العضوية لاحقاً. |

النماذج المنصية المخطط لها في مرحلة التوظيف، `JobPosting` و`JobApplicant`، ستكون
هي أيضاً بلا `tenant` بقرار #207 الموثق؛ هذا استثناء محصور لأن الوظائف
والمتقدمين للمنصة نفسها، لا لشركة زبون.

## أهم نقاط الـAPI

كلها قراءة فقط في المرحلة الأولى:

| Method | المسار | الحارس |
|---|---|---|
| GET | `/api/platform/ops/employees/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/subscriptions/` | `IsPlatformOperationsManager` |

## الاعتماديات

**يعتمد على:**

- `core.platform_admin_api` — `IsPlatformAdmin` كأساس لحارس مدير العمليات.
- `tenants.models` — `Tenant` لاشتراك الخدمة والارتباطات، و`UserCompanyMembership` لإدارة صلاحية المدير.

**يعتمد عليه:** لا شيء حالياً؛ حارس العزل يمنع الاستيراد الوارد من التطبيقات
الأخرى، والتكامل يتم عبر مسارات وخدمات الوحدة في مراحلها اللاحقة.

## قواعد لا يجوز كسرها

- `PlatformEmployee` هوية صريحة؛ لا تُستنتج من `is_superuser` أو من دور داخل شركة.
- موظف العمليات لا يحصل على `IsPlatformAdmin`، ومدير العمليات وحده يستعمل الحارس الإداري.
- `ServiceSubscription` صف واحد لكل شركة، والاشتراك النشط هو بوابة الإسناد الوحيدة.
- الأسعار تُحفظ على الاشتراك كي تبقى الفوترة قابلة للحساب حتى لو تغيّر تعريف الباقة لاحقاً.
- لا `require_module` ولا `get_tenant` على مسارات المنصة العابرة للشركات.
- أي كيان لاحق يخص شركة يحمل `tenant` ويُفلتر عليه؛ الاستثناءات الوحيدة بلا
  `tenant` هي `PlatformEmployee` و`JobPosting` و`JobApplicant`.
- فرادة الارتباط النشط لنفس (الموظف، الشركة) تُفرض تحت قفل `select_for_update` في الخدمة داخل `transaction.atomic` لأن MySQL تتجاهل القيود الشرطية.
- الإلغاء والتعليق يسحبان فقط العضوية التي أنشأها الارتباط (`created_membership=True`)، ولا يمسّان أي عضوية مسبقة للزبون.
- إيقاف أو تعليق اشتراك الخدمة يُعلّق الارتباطات النشطة ولا يحذفها.
- مغادرة موظف المنصة (`offboard_platform_employee`) عملية ذرية idempotent لا تفشل ولا تكرر الآثار عند تكرار الاستدعاء.
- قائمة الاستيراد البيضاء تتوسع فقط عند حاجة مرحلة موثقة، ولا تستورد الوحدة `employee_ops`.
- كل قيد محاسبي لاحق يمر عبر `accounting.services.post_journal`، وكل تغيير مخزون عبر `inventory.services.record_stock_movement`.

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `platform_ops/tests/test_service_layer.py` | صراحة هوية الموظف، صلاحيات المنصة، بوابة الاشتراك، فرادة صفه، وتسعيره |
| `platform_ops/tests/test_engagement_lifecycle.py` | دورة حياة الارتباط، حفظ عضوية الزبون، الاستئناف، تعليق الاشتراك، المغادرة، ولقطة الهوية |
| `platform_ops/tests/test_isolation_guard.py` | الاستيراد الصريح والديناميكي في الاتجاهين |
| `platform_ops/tests/test_migration_graph.py` | وجود الهجرات وترتيب الاعتماديات |
| `tenants/tests/test_member_activity_log.py` | تسجيل إضافة عضو وتغيير دوره وحذفه في `ActivityLog` |
