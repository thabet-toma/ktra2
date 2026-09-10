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
| `platform_ops/models.py` | هوية موظف المنصة، اشتراك الخدمة، الارتباطات (`Engagement`)، سجل العضويات (`AgentGrantedMembership`)، وأوامر العمل (`WorkOrder`) ومُسلَّماتها (`WorkOrderDeliverable`) وتعليقاتها (`WorkOrderComment`)، ومفاتيح قنوات الاستقبال (`IntegrationKey`)، وملف سياسة الأداء (`PolicyProfile`)، ولقطة الأداء الشهرية (`PerformanceSnapshot`)، وإشعارات المنصة (`PlatformNotification`)، وسجل النشاط العابر (`PlatformActivityLog`) |
| `platform_ops/services.py` | بوابة الاشتراك، دورة حياة الارتباط، تعليق الاشتراكات والمغادرة، إدارة دورة حياة أمر العمل وآلة حالاته، حساب وإيقاف الأجل (SLA)، اعتماد ورفض المُسلَّمات، وإدارة التعليقات بمستويات الظهور، وتوليد وتدوير وإبطال مفاتيح القنوات واستقبال طلبات القنوات واحتساب الفوترة، وحساب أداء الموظف عبر المقاييس الستة والمحاور الخمسة وإعادة توزيع الأوزان بالتناسب، والتقاط لقطات الأداء الشهرية المجمدة بطريقة idempotent وترتيب الموظفين، وكشف الشذوذات الأربعة لشريط التدخل، وتوليد ملخص اللوحة التفاعلية، وتسجيل النشاط العابر للشركات |
| `platform_ops/authentication.py` | مصادقة مفتاح قناة الاستقبال (`IntegrationKeyAuthentication`) وحارس التحقق (`HasValidIntegrationKey`) |
| `platform_ops/throttles.py` | خانق استقبال أوامر العمل المربوط بمفتاح القناة (`IntegrationKeyThrottle`) |
| `platform_ops/permissions.py` | حارسا موظف العمليات ومدير العمليات |
| `platform_ops/views.py` | نقاط القراءة الإدارية والتشغيلية، ونقطة استقبال أوامر العمل من القنوات الخارجية (`WorkOrderIntakeView`)، ومسار استعلام الأداء وترتيب الموظفين، ومسار سياسات الأداء واللقطات الشهرية، وصندوق الإشعارات المفلتر خادمياً (`PlatformNotificationViewSet`)، وسجل النشاط العابر (`PlatformActivityLogViewSet`)، واللوحة التفاعلية وشريط التدخل (`PlatformDashboardView`) |
| `platform_ops/tests/test_isolation_guard.py` | قائمة الاستيراد البيضاء وحارس الاتجاهين |
| `platform_ops/tests/test_migration_graph.py` | سلامة رسم الهجرات (0001 و0002 و0003 و0004 و0005 و0006) واعتمادها على `tenants` |
| `platform_ops/tests/test_engagement_lifecycle.py` | دورة حياة الارتباط، فرادة الإسناد تحت قفل، حفظ عضوية الزبون، الاستئناف، والمغادرة، وحارس ترتيب الأقفال |
| `platform_ops/tests/test_work_orders.py` | آلة حالات أمر العمل، إيقاف الأجل عند انتظار العميل، لقطة السياسة والتسليم، إلزامية مستوى ظهور التعليق، والعزل بالشركة |
| `platform_ops/tests/test_channel_intake.py` | استقبال القنوات، فرادة المرجع الخارجي (idempotency)، احتساب الفوترة تحت قفل، رفض الحقول الممنوعة، التحقق من المرفقات، الخانق، وفحص الحجم بالبايتات |
| `platform_ops/tests/test_performance_metrics.py` | المقاييس الستة، ملفات السياسات، الدرجة المركبة، كفاية العينة، تجميد اللقطة الشهرية، إعادة توزيع الأوزان، وعزل الاستعلام العابر للشركات |
| `platform_ops/tests/test_dashboard_and_notifications.py` | اللوحة التفاعلية، شريط التدخل، التنقيب، الفلترة الخادمية للإشعارات، سجل النشاط العابر، رفض وسائط الشركات الممنوعة بـ 400، واتساع أعمدة الخيارات |

## النماذج الحالية

| Model | الحقول والقواعد المهمة |
|---|---|
| `PlatformEmployee` | `user` واحد لواحد، `specialty`، `capacity_target`، وحالة `active/on_leave/offboarded`. بلا `tenant` عمداً لأنه موظف للمنصة لا لشركة. |
| `ServiceSubscription` | صف واحد لكل شركة، الحالة والباقة والرسم الشهري والحد والعداد وسعر العملية الزائدة ودورة الفوترة. `tenant` علاقة OneToOne تفرضها MySQL. |
| `Engagement` | ارتباط موظف بشركة: `active/suspended/revoked`، من أسند ومتى، طوابع التعليق والإلغاء، وحقل `created_membership` للتمييز بين العضوية المنشأة وعضوية الزبون المسبقة. فرادة النشط تحت قفل برمجي لا قيد شرطي. |
| `AgentGrantedMembership` | سجل العضويات الممنوحة أو المعدلة بواسطة وكيل: الشركة، الوكيل الفاعل، الارتباط، `role_before/role_after`، ولقطة هوية ثابتة (`identity_snapshot`) تبقى مقروءة ومفيدة حتى لو حُذفت العضوية لاحقاً. |
| `WorkOrder` | أمر عمل موجه لشركة (`tenant` إلزامي). يتميز بـ `kind` و `source` و `channel` و `external_ref`. مسؤول واحد فقط (`assignee`). آلة حالات صارمة (`received -> screening -> data_entry -> review -> approval -> closed` مع تفريعة `waiting_customer` و `cancelled`). الأجل يُقاس من `received_at` إلى `approved_at`، مع حسم فترات الانتظار المتراكمة (`waiting_seconds_total`). لقطة السياسة (`policy_snapshot`) ثابتة على الصف. فرادة غير مشروطة لكل `(tenant, channel, external_ref)` لضمان idempotency. |
| `WorkOrderDeliverable` | مخرج أمر العمل (`note` / `structured_report` / `attachment`) مع `content_snapshot` ثابتة لا تتأثر بتحرير المصدر، ودورة مراجعة (`pending/approved/rejected`) مع سبب رفض إلزامي. |
| `WorkOrderComment` | خيط تعليقات واستفسارات أمر العمل. حقل `visibility` إلزامي (`internal` أو `client_visible`) مع حجب الداخلي عن أي مسار زبون. |
| `IntegrationKey` | مفتاح قناة استقبال لشركة زبون (`tenant` إلزامي، `channel`، `token_hash` مهشر عبر SHA-256). صف لكل `(tenant, channel)` بفرادة غير مشروطة. قابل للإبطال والتدوير (`active/revoked` وطوابع `revoked_at` و `rotated_at`). الرمز الخام لا يُحفظ في القاعدة أبداً ويظهر مرة واحدة في رد الإصدار أو التدوير. و`revocation_history` تحفظ كل إبطال سابق لأن الصف واحد ويُعاد إصداره. |
| `PolicyProfile` | ملف سياسة أداء لكل تخصص (`specialty` فريد) يحمل أوزان المحاور الخمسة ومستهدفاتها وساعات الأجل والحد الأدنى للعينة. لا أوزان لكل موظف على حدة، وتعديلها لاحقاً لا يمس لقطات الأشهر السابقة. |
| `PerformanceSnapshot` | لقطة أداء شهرية لموظف المنصة لكل `(employee, period_year, period_month)` بفرادة غير مشروطة. تحفظ نسخة مجمدة من السياسة والأوزان (`policy_snapshot`) والمقاييس الستة والمحاور، والتقاطها دالة خدمة idempotent لا تكرر الصفوف ولا تضاعف الآثار. |
| `PlatformNotification` | إشعار منصي موجه لمستخدم (`recipient` إلزامي، `tenant` اختياري). مفلتر خادمياً حصراً فلا يرى المستخدم إلا إشعاراته. أنواع مغلقة (`sla_breach`, `low_score`, `quota_exceeded`). يدعم تعليم إشعار أو الكل كمقروء وعدّ غير المقروء. |
| `PlatformActivityLog` | سجل نشاط منصي عابر للشركات مستقل تماماً عن `ActivityLog` المستأجر؛ لأن `ActivityLog` لا يتسع لحدث بلا شركة وفهارسه تبدأ بالشركة. يحمل `employee` إلزامي، و`tenant` اختياري للأنشطة العامة، ومفهرس زمنياً `(employee, -created_at)` و`(-created_at)`. |

النماذج المنصية المخطط لها في مرحلة التوظيف، `JobPosting` و`JobApplicant`، ستكون
هي أيضاً بلا `tenant` بقرار #207 الموثق؛ هذا استثناء محصور لأن الوظائف
والمتقدمين للمنصة نفسها، لا لشركة زبون.

## أهم نقاط الـAPI

| Method | المسار | الحارس |
|---|---|---|
| GET | `/api/platform/ops/dashboard/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (اللوحة التفاعلية وشريط التدخل) |
| GET | `/api/platform/ops/employees/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` (مفلتر لموظف المنصة على حسابه) |
| GET | `/api/platform/ops/employees/{id}/performance/` | `IsPlatformOperationsManager` أو الموظف نفسه (عزل عابر مشتق من الارتباطات) |
| GET | `/api/platform/ops/employees/{id}/activity/` | `IsPlatformOperationsManager` أو الموظف نفسه |
| GET | `/api/platform/ops/employees/ranking/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/subscriptions/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/work-orders/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (تنقيب مفلتر بدون معاملات شركة) |
| POST | `/api/platform/ops/intake/` | `HasValidIntegrationKey` (بمفتاح القناة لا بجلسة ولا بتوكن مستخدم) |
| GET | `/api/platform/ops/integration-keys/` | `IsPlatformOperationsManager` |
| POST | `/api/platform/ops/integration-keys/issue/` · `{id}/rotate/` · `{id}/revoke/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/policy-profiles/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` |
| GET | `/api/platform/ops/performance-snapshots/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` (مفلتر للموظف على لقطاته) |
| POST | `/api/platform/ops/performance-snapshots/capture/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/notifications/` · `unread-count/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (مفلتر خادمياً) |
| POST | `/api/platform/ops/notifications/{id}/mark-read/` · `mark-all-read/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/activity-logs/` | `IsPlatformOperationsStaff` (لنفسه) أو `IsPlatformOperationsManager` (لكل الشركات) |

## الاعتماديات

**يعتمد على:**

- `core.platform_admin_api` — `IsPlatformAdmin` كأساس لحارس مدير العمليات.
- `core.models` — `TenantAsset` للتحقق من المرفقات المرفوعة عبر خدمة الوسائط القائمة.
- `tenants.models` — `Tenant` لاشتراك الخدمة والارتباطات وأوامر العمل والمفاتيح، و`UserCompanyMembership` لإدارة صلاحية المدير.

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
- نقطة أوامر العمل مفلترة بخلاف أختيها: موظف المنصة يرى شركات ارتباطاته النشطة وحدها، والشركات تُشتق من `Engagement` لا من الطلب. ومدير المنصة وحده يرى الكل.
- كل تغيير حالة لأمر العمل يمر بـ`transition_work_order_status` وفق خريطة `WORK_ORDER_TRANSITIONS` وحدها — لا كتابة مباشرة على `status`.
- مغادرة موظف المنصة (`offboard_platform_employee`) عملية ذرية idempotent لا تفشل ولا تكرر الآثار عند تكرار الاستدعاء.
- قائمة الاستيراد البيضاء تتوسع فقط عند حاجة مرحلة موثقة، ولا تستورد الوحدة `employee_ops`.
- ترتيب الأقفال الصارم: `IntegrationKey -> ServiceSubscription -> PlatformEmployee -> Engagement -> WorkOrder -> WorkOrderDeliverable -> UserCompanyMembership`.
- كل انتقال في حالة أمر العمل يمر حصراً بدالة `transition_work_order_status` في `platform_ops/services.py` وتُفرض الانتقالات عبر بنية `WORK_ORDER_TRANSITIONS` الصريحة.
- الأجل يُقاس من `received_at` إلى `approved_at`؛ و`waiting_customer` يوقف العداد ويُسجل التراكم في `waiting_seconds_total` ويمدد الأجل النهائي.
- لقطة سياسة الأجل (`policy_snapshot`) تُحفظ وقت الإنشاء، ولقطة التسليم (`content_snapshot`) تُحفظ وقت التقديم؛ كلاهما غير قابل للتعديل بتحرير خارجي لاحق.
- حقل `visibility` إلزامي على كل `WorkOrderComment` والتعليق الداخلي لا يظهر في أي استعلام للزبون.
- لا استعمال لـ `__date` على أعمدة الوقت إطلاقاً؛ الفلترة عبر `core/date_ranges.py`.
- كل قيد محاسبي لاحق يمر عبر `accounting.services.post_journal`، وكل تغيير مخزون عبر `inventory.services.record_stock_movement`.
- المفتاح يُخزَّن مهشَّراً فقط (SHA-256)؛ الرمز الخام يظهر مرة واحدة لحظة التوليد ولا يُحفظ في القاعدة إطلاقاً.
- نقطة الاستقبال ليست `AllowAny`؛ وتُصادق بالمفتاح لا بجلسة ولا بتوكن مستخدم.
- الشركة تُستنتج من المفتاح لا من الحمولة.
- الحمولة لا تحمل مُسنَداً ولا حالة ولا سعراً؛ وإلا تُرفض صراحة.
- المرفقات تُرفع عبر خدمة الوسائط القائمة وتُرسل بمعرفات أصول فقط، ويُرفض أي حقل مرفق
  يحمل رابطاً (`url` و`file_url` وأخواتها) **في أي عمق من الحمولة**. أما ذكر رابط في نص
  الزبون فحمولة مشروعة ولا يُردّ — القاعدة عن المرفقات لا عن النص.
- حقول التحكم (`assignee` و`status` و`price` وأخواتها) تُرفض **في المستوى الأعلى** من
  الحمولة: الجدولة والتسعير قرار المنصة. ولا تُفحص البنود المتداخلة لأن المستند المرسَل
  (فاتورة غالباً) يحمل مبالغ وأسعار بنود بطبيعته.
- خانق الاستقبال مربوط بالمفتاح.
- سقف الحجم يُفحص بالبايتات الحقيقية للحمولة لا بالترويسة المعلنة.
- `external_ref` فريد لكل (شركة، قناة)؛ وإعادة الطلب تُرجع نفس أمر العمل ولا تحتسب عملية ثانية.
- احتساب العملية المفوترة يزيد `consumed_quota` فقط عند قبول ما يرسله الزبون تحت قفل في نفس المعاملة الذرية التي تنشئ أمر العمل.
- صف لكل تخصص (`PolicyProfile`) يحمل أوزان المحاور الخمسة وأهدافها؛ لا أوزان لكل موظف على حدة، وتعديلها اللاحق لا يمس الماضي.
- المقاييس الستة قائمة مغلقة ولا سابع، وتُشتق من بيانات أوامر العمل ومُسلَّماتها القائمة.
- العرض والدخول لا يُعدّان عملاً إطلاقاً، والإنشاء لا يدخل الأداء إلا بعد الاعتماد.
- الإلغاء (`cancelled`) لا يعاقب آلياً بل يظهر معدل إعادة عمل منفصلاً كرقم تشخيصي لا يُخصم من الدرجة المركبة.
- الجودة اسمها الصادق «نسبة القبول من أول مراجعة» وتُعرض بمقام معلن وحجم عينة، والرقم المالي «قيمة مبيعات عالجها» كمؤشر عرض لا استحقاق.
- العينة الناقصة (< `min_sample_size`) تُخرج الموظف من الترتيب وتُعيد حالة `insufficient_data` مع `composite_score=None` صراحة في الخدمة.
- المحور غير المنطبق يُسقط ويُعاد توزيع وزنه بالتناسب ليبقى المجموع 100% بالضبط.
- التقاط `PerformanceSnapshot` الشهرية عملية idempotent مجمدة بالأوزان السارية وقتها، وتشغيلها مرتين للشهر نفسه لا يُنتج لقطتين ولا يضاعف أثراً.
- الاستعلام العابر للشركات مشروع ومحصور بخدمة التحليل؛ وتُشتق الشركات من الارتباطات (`Engagement`) حصراً ويُرفض أي وسيط شركة من الطلب بـ 400.
- إشعارات المنصة (`PlatformNotification`) مفلترة على الخادم حصراً، ولا يرى المستخدم إلا إشعاراته، وتحدث كل 60 ثانية في الواجهة ما دام التبويب ظاهراً.
- سجل النشاط المنصي (`PlatformActivityLog`) مستقل تماماً عن `ActivityLog` المستأجر ولا يلمسه؛ لضمان قراءة عابرة للشركات بفهارس زمنية.
  ويُقرأ بسقف صفوف صريح (`PLATFORM_ACTIVITY_PAGE_CAP`) لأن الصفحة غير مصفَّحة افتراضياً.
- للإشعارات **منتِجان حقيقيّان** لا دالة إنشاء بلا مستدعٍ: `notify_quota_exceeded`
  تُطلق مرة واحدة لحظة عبور الحد داخل `receive_channel_work_order`، و`notify_sla_breach`
  تُطلق لحظة الاعتماد وحدها لأن الأجل لا يُحسم قبلها.
- «آخر ظهور» **طابع وقت لا مصباح**: لا نقطة خضراء ولا «نشط الآن»، بل الساعة الحقيقية
  ومدة الغياب. والتاريخ عبر `utils/formatDate` لا `toLocaleString('ar-SA')` (أرقام هندية
  وتقويم هجري حسب ICU الجهاز).
- التنقيب يقبل `company` و`work_order` **تضييقاً داخل النطاق المشتق** من الارتباطات؛
  أما `tenant`/`tenants`/`tenant_id`/`tenant_ids` فمرفوضة بـ 400 كما هي.
- اللوحة مركَّبة على `/super-admin/platform-ops` في `App.tsx` — شاشة بلا مسار شاشة ميتة.
- شريط التدخل يعرض أربعة شذوذات فقط لا غير (`critical_delay`, `absent_with_work`, `overloaded`, `low_score`) مرتبة الأسوأ أولاً.
- عتبة النشاط الأخير للموظف 15 دقيقة صارمة مشتقة من `hr.models.UserDevice.last_active_at`.
- التنقيب في لوحة القيادة يرفض وسائط الشركات الصريحة من الطلب (`tenant`, `tenants`, `tenant_id`, `tenant_ids`) بـ 400 Bad Request، ويعتمد الاشتقاق الخادمي للشركات.
- لا نقاط تحفيزية (gamification) في لوحة عمليات المنصة.

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `platform_ops/tests/test_service_layer.py` | صراحة هوية الموظف، صلاحيات المنصة، بوابة الاشتراك، فرادة صفه، وتسعيره |
| `platform_ops/tests/test_engagement_lifecycle.py` | دورة حياة الارتباط، حفظ عضوية الزبون، الاستئناف، تعليق الاشتراك، المغادرة، حارس ترتيب الأقفال الصارم |
| `platform_ops/tests/test_work_orders.py` | آلة حالات أمر العمل، إيقاف الأجل، استئنافه، لقطات السياسة والتسليم، إسناد المسؤول الواحد، عزل الشركة، وإلزامية مستوى ظهور التعليق |
| `platform_ops/tests/test_channel_intake.py` | استقبال القنوات، فرادة المرجع الخارجي (idempotency)، احتساب الفوترة، رفض الحقول الممنوعة، التحقق من المرفقات، الخانق، سقف الحجم بالبايتات، وعرض أعمدة الخيارات |
| `platform_ops/tests/test_performance_metrics.py` | كفاية العينة، إعادة توزيع الأوزان (سقوط محور ومحورين = 100%)، تجميد اللقطة والسياسة، Idempotency، عدم عد العرض عملاً، الدخول بعد الاعتماد، عدم خصم الإلغاء، رفض وسائط الشركات، وعرض أعمدة الخيارات |
| `platform_ops/tests/test_dashboard_and_notifications.py` | اللوحة التفاعلية، شريط التدخل (الشذوذات الأربعة)، عتبة الـ 15 دقيقة، الفلترة الخادمية للإشعارات، سجل النشاط العابر، ورفض وسائط الشركات بـ 400 |
| `platform_ops/tests/test_isolation_guard.py` | الاستيراد الصريح والديناميكي في الاتجاهين والقائمة البيضاء الصريحة |
| `platform_ops/tests/test_migration_graph.py` | وجود الهجرات (0001، 0002، 0003، 0004، 0005، 0006) وترتيب الاعتماديات |
| `tenants/tests/test_member_activity_log.py` | تسجيل إضافة عضو وتغيير دوره وحذفه في `ActivityLog` |


