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
| `platform_ops/models.py` | هوية موظف المنصة، اشتراك الخدمة مع عميل الفوترة (`billing_customer`)، سجل تدقيق الفوترة الشهرية (`SubscriptionBillingRecord` مع `invoice` اختياري للباقات الصفرية)، الارتباطات (`Engagement`)، سجل العضويات (`AgentGrantedMembership`)، وأوامر العمل (`WorkOrder`) ومُسلَّماتها (`WorkOrderDeliverable`) وتعليقاتها (`WorkOrderComment`)، ومفاتيح قنوات الاستقبال (`IntegrationKey`)، وملف سياسة الأداء (`PolicyProfile`)، ولقطة الأداء الشهرية (`PerformanceSnapshot`)، وإشعارات المنصة (`PlatformNotification`)، وسجل النشاط العابر (`PlatformActivityLog`)، والتقييم اليومي (`DailyRating`) ورمزه العام (`DailyRatingToken`) |
| `platform_ops/services.py` | بوابة الاشتراك، دورة حياة الارتباط، تعليق الارتباط والمغادرة (`suspend_engagement`)، إدارة دورة حياة أمر العمل، حساب وإيقاف الأجل، اعتماد ورفض المُسلَّمات، مفاتيح القنوات والفوترة، حساب أداء الموظف عبر المحاور الخمسة الرسمية (`ALL_PERFORMANCE_AXES`) بما فيها محور تقييم الزبائن (`AXIS_CUSTOMER_RATING`) ومحور الحضور والانضباط (`AXIS_ATTENDANCE_REGULARITY`)، وقرار تعديل التقييم (`decide_rating_update`)، والتقاط اللقطات الشهرية، وشريط التدخل، والتقييم اليومي وتبويب «من يمسك دفاتري»، ودرجتَي الصحة المنفصلتين مع أسباب التخفيض المفصلة، وحساب وفوترة الاشتراكات الشهرية وإصدار فواتير المبيعات وترحيلها محاسبياً (`bill_subscription_for_period` · `bill_subscriptions_for_period`) مع فحص الصلاحية المسبق الموحد (`billing_preflight`) واستثناءات انتهاء الوظائف والدعوات (`JobGone` · `InvitationGone`) |
| `platform_ops/management/commands/bill_service_subscriptions.py` | أمر إدارة فوترة اشتراكات خدمة المنصة الشهرية وإصدار فواتير المبيعات وتدوير الدورات (`--period` · `--fixed-fee-product-id` · `--overage-product-id` · `--dry-run`)؛ المعاينة والتشغيل يمران بـ`billing_preflight` نفسها، وأي خطأ ⇒ `CommandError` |
| `platform_ops/authentication.py` | مصادقة مفتاح قناة الاستقبال (`IntegrationKeyAuthentication`) وحارس التحقق (`HasValidIntegrationKey`) |
| `platform_ops/throttles.py` | خانق استقبال أوامر العمل المربوط بمفتاح القناة (`IntegrationKeyThrottle`)، وخانق النطاق المربوط بـ`REMOTE_ADDR` لا بترويسة يرسلها العميل (`ClientIpScopedThrottle`) |
| `platform_ops/permissions.py` | حارسا موظف العمليات ومدير العمليات |
| `platform_ops/views.py` | نقاط القراءة الإدارية والتشغيلية، واستقبال أوامر العمل، ومسار استعلام الأداء واللقطات، وصندوق الإشعارات، وسجل النشاط العابر، واللوحة التفاعلية، والتقييم اليومي (`DailyRatingViewSet`)، وتبويب «من يمسك دفاتري» (`TenantAgentBooksViewSet`)، والرابط العام (`PublicDailyRatingView`)، وعرض صحة الشركة الإداري (`CompanyHealthView`) |
| `platform_ops/urls.py` · `platform_ops/urls_tenant.py` · `platform_ops/urls_staff.py` | ثلاثة مسارات منفصلة: الأول سطح المنصة تحت `/api/platform/ops/`، والثاني سطح المستأجر تحت `/api/my-agent/`، والثالث قدرات موظفي المنصة تحت `/api/platform-staff/` |
| `frontend_v2/components/platform-hiring/` | شاشة التوظيف المنصي وتبويباتها الثلاث (الوظائف، المتقدمون، مسؤولو التوظيف، ولوحة تفاصيل المتقدم) وصفحتا التقديم العام وقبول الدعوة |
| `frontend_v2/components/platform/BillingRecordsScreen.tsx` | شاشة سجلات تدقيق الفوترة الشهرية للقراءة فقط بلا زر توليد: بحث محلي باسم الشركة أو رقم الفاتورة، وصف مجموع بالسنتات، والدورة الصفرية تظهر بلا رقم فاتورة |
| `frontend_v2/components/my-agent/QuotaUsageCard.tsx` | بطاقة استهلاك باقة الخدمة والعمليات المشمولة والزائدة لصاحب الشركة داخل التطبيق |
| `frontend_v2/components/my-agent/MyAgentBooksPage.tsx` | شاشة «من يمسك دفاتري» لصاحب الشركة داخل التطبيق: بطاقة الوكيل، التقييم بنقرة واحدة، درجتا الصحة، جدول الصلاحيات، وسجل النشاط المالي |
| `frontend_v2/components/my-agent/PublicRatingPage.tsx` | صفحة التقييم اليومي العامة المهشرة بلا تسجيل دخول بحالاتها الثلاث (التقييم، 410 المنتهي، و404 غير الصالح) |
| `frontend_v2/components/platform/CompanyHealthPanel.tsx` | لوحة درجتي صحة الخدمة وتعاون الزبون في بطاقة الشركة الإدارية تُحسب عند الطلب لمنع N+1 |
| `frontend_v2/services/platformHiringApi.ts` | عميل API للتوظيف المنصي ومسؤولي التوظيف والصفحات العامة |
| `frontend_v2/services/myAgentApi.ts` | عميل API لتبويب «من يمسك دفاتري» والتقييم اليومي وتعليق الوكيل |
| `frontend_v2/hooks/usePlatformStaffCapabilities.ts` | خطاف استعلام قدرات المستخدم الحالي على المنصة (`is_platform_admin`، `is_platform_recruiter`، `is_platform_employee`) |
| `frontend_v2/utils/platformHiring.ts` | أدوات مساعدة وشارات حالات المتقدمين والوظائف واستخراج رسائل أخطاء API وخيارات الحالات وأنواع الدوام |
| `frontend_v2/utils/quotaUsage.ts` · `quotaUsage.test.ts` | دوال نصوص نقية واستخراج نسب استهلاك الحصص وألوان شريط التقدم وإشعارات التجاوز لصاحب الشركة |
| `frontend_v2/utils/billingRecords.ts` · `billingRecords.test.ts` | `sumDecimalAmounts` لجمع المبالغ العشرية النصية بالسنتات بلا فاصلة عائمة، و`filterBillingRecords` للبحث المحلي |
| `frontend_v2/utils/dateTimeLocal.ts` | تحويل طوابع الوقت بين ISO وdatetime-local لمدخلات النماذج |
| `frontend_v2/utils/agentBooks.ts` · `agentBooks.test.ts` | أنواع درجتَي الصحة (مصدر واحد للسطحين) ودوال نصوص نقية للنجوم وإشعارات السقف والعينة — وهي بوابة الواجهة الوحيدة (`node --test`) |
| `frontend_v2/index.tsx` (`/rate/:token`) · `frontend_v2/App.tsx` (`my-agent`) | تركيب الشاشتين: صفحة عامة خارج مزوّد المصادقة، وتبويب داخل التطبيق يظهر لصاحب الشركة وحده في `components/Sidebar.tsx` |
| `platform_ops/tests/test_my_agent_frontend_contract.py` | حارس العقد: كل حقل تعلنه أنواع `myAgentApi.ts` و`agentBooks.ts` موجود في حمولة الخادم الحقيقية — `tsc` هنا لا يفحص شكل ما يصل من الشبكة، فالحقل المخترع يُصيَّر فراغاً بلا شكوى |
| `platform_ops/tests/test_hiring_frontend_contract.py` | حارس العقد بين واجهات التوظيف والفوترة بالـ frontend وحمولات الخادم الحقيقية للـ 13 واجهة، ومطابقة `APPLICANT_STATUS_OPTIONS`/`EMPLOYMENT_TYPE_OPTIONS` لـ`choices` الخادم |
| `platform_ops/public_hiring/` | **كل كود `AllowAny` للتوظيف في حزمة واحدة** ليراجعها الأمن دفعة واحدة: `views.py` (أربع نقاط عامة بخانق `ClientIpScopedThrottle` ومصادقة معلنة صراحة)، و`cv_validation.py` (سقف 5 م.ب وفحص النوع والبنية **بالبايتات**)، و`serializers.py` (بلا `cv_url` بأي حال)، و`urls.py` تحت `/api/careers/` |
| `platform_ops/tests/test_isolation_guard.py` | قائمة الاستيراد البيضاء وحارس الاتجاهين |
| `platform_ops/tests/test_migration_graph.py` | سلامة رسم الهجرات واعتمادها على `tenants` |
| `platform_ops/tests/test_subscription_billing.py` | فوترة الاشتراكات الشهرية: الحساب وفصل السطور وترحيل الفواتير وعدم التكرار والذرية وعزل الشركات وسلامة الحقول، والدورة الصفرية بلا فاتورة، ورفض عميل من شركة الاشتراك، والمعاينة تساوي التشغيل و`CommandError` |
| `platform_ops/tests/test_hiring_portal.py` | بوابة التوظيف والسطح الإداري (`PlatformHiringAdminSurfaceTests`): النماذج بلا `tenant`، فحص السيرة بالبايتات والبنية، التقديم العام، 410 للمغلق، تهشير رمز الدعوة، إنشاء الحساب عند القبول لا قبله، منع تحريك الحالة بكتابة مباشرة، رفض حذف إعلان له متقدمون، تمرير بايتات السيرة بلا تسليم رابط التخزين، عزل دور التوظيف عن كل مسارات المنصة، وجرد السطح العام بخانقه ومصادقته، ورفض المتقدم يبطل الدعوة، و`PATCH is_open` متجاهل، واسم السيرة العربي `filename*=`، وقوة كلمة المرور وسباق اسم المستخدم |
| `platform_ops/tests/test_daily_ratings_and_books.py` | التقييم اليومي وحدّ التعديل الواحد، انتهاء الرمز بـ410، عدم حفظ الرمز الخام، القائمة البيضاء للرد العام، خانق الرابط العام بـ429، تبويب «من يمسك دفاتري»، درجتا الصحة، اختبارات الجزء (ب) (`Stage7PartBTests`)، وعيوب المراجعة الاثنا عشر |
| `platform_ops/tests/test_engagement_lifecycle.py` | دورة حياة الارتباط، فرادة الإسناد تحت قفل، حفظ عضوية الزبون، الاستئناف، والمغادرة، وحارس ترتيب الأقفال |
| `platform_ops/tests/test_work_orders.py` | آلة حالات أمر العمل، إيقاف الأجل عند انتظار العميل، لقطة السياسة والتسليم، إلزامية مستوى ظهور التعليق، والعزل بالشركة |
| `platform_ops/tests/test_channel_intake.py` | استقبال القنوات، فرادة المرجع الخارجي (idempotency)، احتساب الفوترة تحت قفل، رفض الحقول الممنوعة، التحقق من المرفقات، الخانق، وفحص الحجم بالبايتات |
| `platform_ops/tests/test_performance_metrics.py` | المقاييس الستة، ملفات السياسات، الدرجة المركبة، كفاية العينة، تجميد اللقطة الشهرية، إعادة توزيع الأوزان، وعزل الاستعلام العابر للشركات |
| `platform_ops/tests/test_dashboard_and_notifications.py` | اللوحة التفاعلية، شريط التدخل، التنقيب، الفلترة الخادمية للإشعارات، سجل النشاط العابر، رفض وسائط الشركات الممنوعة بـ 400، واتساع أعمدة الخيارات |

## النماذج الحالية

| Model | الحقول والقواعد المهمة |
|---|---|
| `PlatformEmployee` | `user` واحد لواحد، `specialty`، `capacity_target`، وحالة `active/on_leave/offboarded`. بلا `tenant` عمداً لأنه موظف للمنصة لا لشركة. |
| `ServiceSubscription` | صف واحد لكل شركة، الحالة والباقة والرسم الشهري والحد والعداد وسعر العملية الزائدة ودورة الفوترة، مع عميل الفوترة (`billing_customer`) المربوط ببطاقة الطرف في شركة المنصة. `tenant` علاقة OneToOne تفرضها MySQL. |
| `Engagement` | ارتباط موظف بشركة: `active/suspended/revoked`، من أسند ومتى، طوابع التعليق والإلغاء، وحقل `created_membership` للتمييز بين العضوية المنشأة وعضوية الزبون المسبقة. فرادة النشط تحت قفل برمجي لا قيد شرطي. |
| `AgentGrantedMembership` | سجل العضويات الممنوحة أو المعدلة بواسطة وكيل: الشركة، الوكيل الفاعل، الارتباط، `role_before/role_after`، ولقطة هوية ثابتة (`identity_snapshot`) تبقى مقروءة ومفيدة حتى لو حُذفت العضوية لاحقاً. |
| `WorkOrder` | أمر عمل موجه لشركة (`tenant` إلزامي). يتميز بـ `kind` و `source` و `channel` و `external_ref`. مسؤول واحد فقط (`assignee`). آلة حالات صارمة (`received -> screening -> data_entry -> review -> approval -> closed` مع تفريعة `waiting_customer` و `cancelled`). الأجل يُقاس من `received_at` إلى `approved_at`، مع حسم فترات الانتظار المتراكمة (`waiting_seconds_total`). لقطة السياسة (`policy_snapshot`) ثابتة على الصف. فرادة غير مشروطة لكل `(tenant, channel, external_ref)` لضمان idempotency. |
| `WorkOrderDeliverable` | مخرج أمر العمل (`note` / `structured_report` / `attachment`) مع `content_snapshot` ثابتة لا تتأثر بتحرير المصدر، ودورة مراجعة (`pending/approved/rejected`) مع سبب رفض إلزامي. |
| `WorkOrderComment` | خيط تعليقات واستفسارات أمر العمل. حقل `visibility` إلزامي (`internal` أو `client_visible`) مع حجب الداخلي عن أي مسار زبون. |
| `IntegrationKey` | مفتاح قناة استقبال لشركة زبون (`tenant` إلزامي، `channel`، `token_hash` مهشر عبر SHA-256). صف لكل `(tenant, channel)` بفرادة غير مشروطة. قابل للإبطال والتدوير (`active/revoked` وطوابع `revoked_at` و `rotated_at`). الرمز الخام لا يُحفظ في القاعدة أبداً ويظهر مرة واحدة في رد الإصدار أو التدوير. و`revocation_history` تحفظ كل إبطال سابق لأن الصف واحد ويُعاد إصداره. |
| `PolicyProfile` | ملف سياسة أداء لكل تخصص (`specialty` فريد) يحمل أوزان **المحاور الخمسة الرسمية** المحسومة في #203 — `kpi_results` 30٪ · `quality` 25٪ · `customer_rating` 20٪ · `sla_compliance` 15٪ · `attendance_regularity` 10٪ (والإنتاجية جزء من KPI حتى لا يُحسب الحجم مرتين) — ومستهدفاتها وساعات الأجل والحد الأدنى للعينة. المحور غير المنطبق يُسقط ويُعاد توزيع وزنه بالتناسب. لا أوزان لكل موظف على حدة، وتعديلها لاحقاً لا يمس لقطات الأشهر السابقة. |
| `PerformanceSnapshot` | لقطة أداء شهرية لموظف المنصة لكل `(employee, period_year, period_month)` بفرادة غير مشروطة. تحفظ نسخة مجمدة من السياسة والأوزان (`policy_snapshot`) والمقاييس الستة والمحاور، والتقاطها دالة خدمة idempotent لا تكرر الصفوف ولا تضاعف الآثار. |
| `PlatformNotification` | إشعار منصي موجه لمستخدم (`recipient` إلزامي، `tenant` اختياري). مفلتر خادمياً حصراً فلا يرى المستخدم إلا إشعاراته. أنواع مغلقة (`sla_breach`, `low_score`, `quota_exceeded`). يدعم تعليم إشعار أو الكل كمقروء وعدّ غير المقروء. |
| `PlatformActivityLog` | سجل نشاط منصي عابر للشركات مستقل تماماً عن `ActivityLog` المستأجر؛ لأن `ActivityLog` لا يتسع لحدث بلا شركة وفهارسه تبدأ بالشركة. يحمل `employee` إلزامي، و`tenant` اختياري للأنشطة العامة، ومفهرس زمنياً `(employee, -created_at)` و`(-created_at)`. |
| `DailyRating` | تقييم يوم عمل واحد بمفتاح منطقي `(tenant, employee, service_date)` بفرادة **غير مشروطة**. `service_date` حقل `DateField` صريح لا مشتق من وقت. `stars` من 1 إلى 5. `edited_once` يسمح بتعديل واحد لا غير. `source` يميز الرابط العام من داخل التطبيق. |
| `DailyRatingToken` | الرابط اليومي العام: `token_hash` مهشر SHA-256 وفريد، والرمز الخام لا يُحفظ في القاعدة أبداً ويظهر مرة واحدة عند التوليد. صالح 72 ساعة (`expires_at`)، وقابل للإبطال (`revoked_at`). |
| `SubscriptionBillingRecord` | سجل تدقيق الفوترة الشهرية لاشتراك الخدمة: يحفظ لقطة الحساب المالي للدورة (`monthly_fee`, `included_quota`, `consumed_quota`, `overage_units`, `overage_unit_price`, `overage_fee`, `total_amount`)، ورابط الفاتورة المرحلة (`SalesInvoice` ويقبل `NULL` للباقات الصفرية دون إصدار فاتورة مبيعات). قيد فرادة صريح على `(subscription, period_start, period_end)` يمنع التكرار نهائياً. |

| `JobPosting` | إعلان وظيفة منصي **بلا `tenant`**. `token` مفتاح الرابط العام (`token_urlsafe`) فريد ومفهرس. `specialty` هو **التخصص المنصي** الذي يُنسخ إلى `PlatformEmployee.specialty` عند قبول الدعوة، وطوله طول العمود الهدف (100) لا طول العنوان (200) — عنوان حر في عمود أقصر يخطئ على MySQL ويُبتر صامتاً على SQLite. |
| `JobApplicant` | متقدم على وظيفة **بلا `tenant`**. مدخل المجهول يُحجر بحالة `new` ولا يمس شيئاً. `cv_url` لا يُطبع في أي مُسلسِل عام ولا يعود للمتقدم. `reference_code` هو ما يراه المتقدم. |
| `JobApplicantInvitation` | دعوة المرشح المقبول: `token_hash` مهشر SHA-256 والرمز الخام لا يُحفظ. `is_consumed` تجمع المقبولة والملغاة **والمنتهية** معاً، فرابط منتهٍ لا يُقبل حتى لو قُصد مسار القبول مباشرة. |
| `PlatformRecruiter` | دور التوظيف المنصي. يفتح مسارَي التوظيف وحدهما ولا يمنح شيئاً من بقية المنصة، وإلغاء تنشيطه يغلقهما فوراً. |

`JobPosting` و`JobApplicant` و`JobApplicantInvitation` و`PlatformRecruiter` بلا
`tenant` بقرار #207 الموثق — استثناء محصور لأن الوظائف والمتقدمين للمنصة نفسها لا
لشركة زبون، ويحرسه `platform_ops/tests/test_isolation_guard.py`.

## أهم نقاط الـAPI

| Method | المسار | الحارس |
|---|---|---|
| GET | `/api/platform/ops/dashboard/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (اللوحة التفاعلية وشريط التدخل) |
| GET | `/api/platform/ops/employees/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` (مفلتر لموظف المنصة على حسابه) |
| GET | `/api/platform/ops/employees/{id}/performance/` | `IsPlatformOperationsManager` أو الموظف نفسه (عزل عابر مشتق من الارتباطات) |
| GET | `/api/platform/ops/employees/{id}/activity/` | `IsPlatformOperationsManager` أو الموظف نفسه |
| GET | `/api/platform/ops/employees/ranking/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/subscriptions/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/billing-records/` | `IsPlatformOperationsManager` — نافذة قراءة على ما فُوتر فعلاً (تصفية `?company=` أو `?subscription=`). الفواتير تُصدَر بأمر الإدارة وحده، لا من هنا. |
| GET · POST · PATCH · DELETE | `/api/platform/ops/job-postings/` | `IsPlatformRecruiter` — إدارة إعلانات الوظائف المنصية: الأفعال `close` و`reopen` و`regenerate-link`؛ و`DELETE` مرفوض بـ400 لإعلان له متقدمون. **الاستثناء الوحيد المعلن** يحرسه `PlatformRecruiterRouteScopeTest`. |
| GET | `/api/platform/ops/job-applicants/` | `IsPlatformRecruiter` — متابعة المتقدمين (قراءة وأفعال لا CRUD): الأفعال `transition-status` و`rate` و`invite` و`cv` (يمرر البايتات بلا تسليم رابط التخزين). |
| GET · POST · DELETE | `/api/platform/ops/recruiters/` | `IsPlatformOperationsManager` — الأفعال `GET`، و`POST` بحقل `identifier` (اسم مستخدم أو بريد، بلا حساسية حالة)، و`DELETE` تعطيل لا حذف؛ بلا `PUT`/`PATCH`. |
| GET | `/api/platform-staff/me/` | `IsAuthenticated` — قدرات المستخدم الحالي على المنصة (يجيب عن المستخدم نفسه، **خارج `/api/platform/` عمداً**). |
| GET | `/api/careers/jobs/{token}/` · POST `{token}/apply/` | `AllowAny` + `ClientIpScopedThrottle` — **كل كود `AllowAny` في حزمة `platform_ops/public_hiring/` وحدها** ليراجعه الأمن دفعة واحدة. السيرة ≤ 5 م.ب ونوعها يُفحصان **بالبايتات** لا بترويسة الرافع. |
| GET | `/api/careers/invitations/{token}/` · POST `{token}/accept/` | `AllowAny` + `ClientIpScopedThrottle` — الحساب يُنشأ **عند قبول الدعوة لا قبلها**؛ ورمز مستهلك أو منتهٍ يرد 410 وغير موجود يرد 404. |
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
| GET | `/api/platform/ops/companies/{tenant_id}/health/` | `IsPlatformOperationsStaff` (للشركات المرتبطة) أو `IsPlatformOperationsManager` (لكل الشركات) |
| GET | `/api/my-agent/` | صاحب الشركة (`role="manager"`) وحده — التبويب يعرض نشاط الوكيل المالي ودرجتَي الصحة |
| POST | `/api/my-agent/suspend/` | صاحب الشركة (`role="manager"`) وحده — لا أي عضو |
| GET | `/api/my-agent/daily-ratings/summary/` | ملخّص تقييمات موظف؛ مفلتر بالشركة لغير مدير المنصة |
| GET · POST | `/api/my-agent/daily-ratings/` | قراءة بعضوية الشركة؛ والإنشاء لصاحبها وحده. `DELETE` مرفوض دائماً بـ405 |
| PATCH | `/api/my-agent/daily-ratings/{id}/` | صاحب الشركة وحده؛ ومحظور على موظف المنصة المُقيَّم نفسه |
| POST | `/api/my-agent/daily-ratings/generate-link/` | صاحب الشركة وحده |
| GET | `/api/my-agent/quota/` | صاحب الشركة (`role="manager"`) وحده — استهلاك باقة الخدمة والعمليات المشمولة والزائدة (أرقام دالة الفوترة نفسها) |
| GET · POST | `/api/my-agent/ratings/public/{token}/` | **بلا مصادقة** — الرمز وحده، مع `ClientIpScopedThrottle` |

## الاعتماديات

**يعتمد على:**

- `core.platform_admin_api` — `IsPlatformAdmin` كأساس لحارس مدير العمليات.
- `core.models` — `TenantAsset` للتحقق من المرفقات المرفوعة عبر خدمة الوسائط القائمة.
- `core.tenant_utils` — `get_tenant` المصدر الواحد لحل شركة المستخدم على نقاط سطح المستأجر.
- `core.terminology` — `term(tenant, key)` لاسم نوع المستند بمعجم الشركة لا حرفياً.
- `tenants.models` — `Tenant` لاشتراك الخدمة والارتباطات وأوامر العمل والمفاتيح، و`UserCompanyMembership` لإدارة صلاحية المدير.
- `partners.models` — `Partner` لعميل الفوترة (`billing_customer`) المربوط باشتراك الخدمة.
- `inventory.models` — `Product` لأصناف الخدمات في سطور الفاتورة (الرسم الثابت والعمليات الزائدة).
- `sales.models` · `sales.serializers` · `sales.services` — `SalesInvoice` و`SalesInvoiceSerializer` و`post_sales_invoice` لإصدار فاتورة المبيعات في شركة المنصة وترحيلها محاسبياً.

**يعتمد عليه:** لا شيء حالياً؛ حارس العزل يمنع الاستيراد الوارد من التطبيقات
الأخرى، والتكامل يتم عبر مسارات وخدمات الوحدة في مراحلها اللاحقة.

## قواعد لا يجوز كسرها

- `PlatformEmployee` هوية صريحة؛ لا تُستنتج من `is_superuser` أو من دور داخل شركة.
- موظف العمليات لا يحصل على `IsPlatformAdmin`، ومدير العمليات وحده يستعمل الحارس الإداري.
- `ServiceSubscription` صف واحد لكل شركة، والاشتراك النشط هو بوابة الإسناد الوحيدة.
- الأسعار تُحفظ على الاشتراك كي تبقى الفوترة قابلة للحساب حتى لو تغيّر تعريف الباقة لاحقاً.
- لا `require_module` ولا `get_tenant` على مسارات المنصة العابرة للشركات.
- أي كيان لاحق يخص شركة يحمل `tenant` ويُفلتر عليه؛ الاستثناءات الوحيدة بلا
  `tenant` هي `PlatformEmployee` و`JobPosting` و`JobApplicant` و`JobApplicantInvitation`
  و`PlatformRecruiter`، و`SubscriptionBillingRecord` شركته مشتقة عبر `subscription.tenant`
  لا بحقل مباشر.
- فرادة الارتباط النشط لنفس (الموظف، الشركة) تُفرض تحت قفل `select_for_update` في الخدمة داخل `transaction.atomic` لأن MySQL تتجاهل القيود الشرطية.
- الإلغاء والتعليق يسحبان فقط العضوية التي أنشأها الارتباط (`created_membership=True`)، ولا يمسّان أي عضوية مسبقة للزبون.
- إيقاف أو تعليق اشتراك الخدمة يُعلّق الارتباطات النشطة ولا يحذفها.
- نقطة أوامر العمل مفلترة بخلاف أختيها: موظف المنصة يرى شركات ارتباطاته النشطة وحدها، والشركات تُشتق من `Engagement` لا من الطلب. ومدير المنصة وحده يرى الكل.
- كل تغيير حالة لأمر العمل يمر بـ`transition_work_order_status` وفق خريطة `WORK_ORDER_TRANSITIONS` وحدها — لا كتابة مباشرة على `status`.
- مغادرة موظف المنصة (`offboard_platform_employee`) عملية ذرية idempotent لا تفشل ولا تكرر الآثار عند تكرار الاستدعاء.
- قائمة الاستيراد البيضاء تتوسع فقط عند حاجة مرحلة موثقة، ولا تستورد الوحدة `employee_ops`؛ اتسعت في م٨ عمّا يسمّيه §١ من المواصفة بـ`sales.models` · `sales.serializers` · `sales.services` · `inventory.models`، لأن §٥ يفرض أن تمر فاتورة الخدمة بمسار المبيعات — قرار مسجّل.
- ترتيب الأقفال الصارم: `IntegrationKey -> ServiceSubscription -> PlatformEmployee -> Engagement -> WorkOrder -> WorkOrderDeliverable -> UserCompanyMembership -> DailyRating -> JobPosting -> JobApplicantInvitation -> JobApplicant`.
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
- صف لكل تخصص (`PolicyProfile`) يحمل أوزان محاور التقييم وأهدافها؛ لا أوزان لكل موظف على حدة، وتعديلها اللاحق لا يمس الماضي.
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
- **سطح المستأجر خارج `/api/platform/` قطعاً.** عقد ذلك الجذر — المكتوب في
  `core/urls.py` والمحروس بـ`core/tests/test_platform_admin.py::PlatformRouteGuardTest` —
  أن لا نقطة تحته تُقرأ بغير سوبر أدمن. فنقاط م٧ الموجهة للزبون (ومنها رابط
  يُفتح بلا تسجيل دخول أصلاً) مكانها `/api/my-agent/` عبر `urls_tenant.py`،
  تماماً كما فصلت `docshare` مساراتها العامة عن المحروسة.
- **التقييم شهادة الزبون لا سجل داخلي.** موظف المنصة يقرأ تقييماته ولا يكتبها،
  ولا يحذفها أحد إطلاقاً (`DELETE` يرد 405) — مقياس يملك المُقاس محوه ليس مقياساً.
- **لا تقييم ليوم لم يُعمل فيه.** `has_employee_worked_on_date` شرط سابق لتوليد
  الرابط ولإرسال التقييم معاً؛ ووجود الارتباط وحده لا يكفي.
- **التعديل مرة واحدة.** `edited_once` يحسم، والثانية ترد بـ400 ورمز `already_edited`.
  والرابط العام يقرأ **تقييم اليوم الحقيقي** بمفتاح `(tenant, employee, service_date)`
  لا `token.rating` (يُولَّد فارغاً)، وإلا بدا التقييم المُسجَّل داخل التطبيق «غير موجود»
  لفاتح الرابط فمحاه وأحرق حق التعديل الوحيد.
- **رابط واحد حيّ لليوم الواحد.** توليد رابط جديد يُبطل سابقه (`revoked_at`) — وهو
  الكاتب الوحيد لذلك الحقل، فرابطان حيّان نافذتا كتابة على شهادة واحدة.
- **«عمل فعلي» لا يشمل ما يختمه الزبون.** `received_at` (تُختم لحظة إرسال الزبون عبر
  القناة) و`cancelled_at` ليسا دليل عمل؛ الأدلة `approved_at` و`closed_at`
  و`waiting_entered_at` وحركات المُسلَّمات وسجل النشاط المنصي.
- **الإلغاء لا يخصم من صحة الخدمة** — رقم تشخيصي في `rework_diagnostic` وحده،
  التزاماً بالقرار نفسه في §٨ («سبب الإلغاء قد لا يكون من الموظف»).
- **تقييم منفرد لا يعاقب**: التقييمات المنخفضة لا تخصم إلا بعد
  `RATING_HEALTH_MIN_SAMPLE`، وحالة العيّنة معلنة في `ratings_sample`.
- **اصطدام إنشاءين متزامنين تعارض لا 500**: القفل على صف غير موجود لا يقفل شيئاً،
  فالقيد في القاعدة هو الحارس والخدمة تترجم اصطدامه (`already_rated` / 409).
- **الرمز الخام لا يُحفظ أبداً**، والمنتهي يرد 410 صريحة لا 404 (سابقة `docshare`).
- **حل الشركة عبر `core.tenant_utils.get_tenant` وحده** — لا `UserCompanyMembership.first()`
  مكتوبة باليد: ترويسة أُرسلت ولم تُحَل تُرَد ولا تسقط على شركة أخرى، وشركة موقوفة
  لا تُفتح، وأكثر من عضوية تلزمها `X-Tenant-Id` صراحة.
- **الدرجتان لا تُخلطان ولا يُؤخذ متوسطهما**، ولا يدخل استهلاك الباقة أو حالة
  الاشتراك في أي منهما إطلاقاً.
- **أسماء أنواع المستندات من `term(tenant, key)`** لا حرفياً — قوالب الشركات
  تسمّي المستند أسماء مختلفة، ويحرس ذلك `core/tests/test_terminology_guard.py`.
- **«من ماذا إلى ماذا» عبر `core.activity.describe_activity_changes`** لا بواصف ثانٍ:
  المنتِجون الحقيقيون يكتبون بنود أسطر (`line_changed` / `line_added`) وفيها يسكن
  المال، وقراءة `old`/`new` من المستوى الأعلى وحده كانت تُسقطها كلها بصمت.
- **`company` تضييق مشروع لا وسيط شركة.** `CROSS_TENANT_FROM_REQUEST_KEYS` تبقى
  `tenant*` وحدها لأن `WorkOrderViewSet` يقرأ `company` تضييقاً داخل النطاق المشتق
  (عقد م٦: «كل رقم يصل إلى صفوفه»). ونقاط سطح المستأجر تستعمل
  `TENANT_SURFACE_FORBIDDEN_KEYS` التي تضيف `company`/`companies` — شركتها من الجلسة.
- **تعليق الوكيل محدد بارتباطه:** `platform_ops/views.py` (`TenantAgentBooksViewSet`) يستدعي `platform_ops/services.py` (`suspend_engagement`) بتحديد `engagement_id`، مع توافق تراجعي لوكيل واحد تلقائياً، ورفض بـ 400 إن وُجد أكثر من وكيل نشط دون تحديد، وعزل الشركات برفض معرف شركة أخرى بـ 404.
- **قاعدة قرار التعديل الواحد للتقييم:** `platform_ops/services.py` (`decide_rating_update`): إضافة ملاحظة لملاحظة فارغة مع بقاء النجوم لا تحرق فرصة التعديل؛ بينما تغيير النجوم أو تعديل ملاحظة كانت غير فارغة يستهلك التعديل؛ وإرسال قيم مطابقة يعيد 200 دون استهلاك.
- **محور تقييم الزبائن ومحور الحضور والانضباط:** `platform_ops/services.py` (`calculate_employee_performance`): يعتمد 5 محاور رسمية (`ALL_PERFORMANCE_AXES`). محور تقييم الزبائن (`AXIS_CUSTOMER_RATING` بوزن 20.00) ينطبق فقط إن كانت عينة التقييمات في الفترة ≥ `min_sample_size` المستمدة من `PolicyProfile`، ومحور الحضور والانضباط (`AXIS_ATTENDANCE_REGULARITY` بوزن 10.00) يُحسب من صفوف `AttendanceDay` الحقيقية المجدولة (`present / (present+late+absent) * 100`) داخل شركات الموظف المرتبطة وفي النطاق الزمني؛ وعند غياب بيانات مجدولة يُسقط المحور ويُعاد توزيع وزنه بالتناسب ليبقى مجموع الأوزان 100%.
- **رابط التقييم المُسلَّم صفحةٌ لا نقطة API:** `platform_ops/services.py` (`rating_public_url`) يبنيه من `PLATFORM_RATING_PUBLIC_BASE_URL` و`PLATFORM_RATING_PUBLIC_PATH` (نمط `docshare/services.py` (`public_url`)) — من إعدادٍ صريح لا من ترويسة `Host`. والرد يحمل `api_path` أيضاً لمن يريد النقطة نفسها.
- **التبويب يعرض كل وكيل نشط لا أولَه:** `platform_ops/services.py` (`get_my_books_tab_data`) يعيد `agents` قائمةً — فرادة `Engagement` على (موظف، شركة) لا على الشركة، وشركةٌ بوكيلين كانت ترى اسماً واحداً بينما اثنان يملكان صلاحية مدير (قصة 49). ولكل وكيل في القائمة `today_rating` و`worked_today`.
- **تقييم اليوم و«هل عمل اليوم» يصلان مع التبويب:** بدون `today_rating` تفتح الشاشة بنجوم فارغة لصاحب شركة قيّم من الرابط، فتُقرأ نقرته التالية تعديلاً يحرق حقه الوحيد. وبدون `worked_today` تُعرض النجوم ليوم بلا عمل ثم يردّ الخادم 400 — والقصة 60 تطلب ألّا يُسأل أصلاً.
- **معادلة الفوترة الشهرية لاشتراك الخدمة:** `monthly_fee + max(consumed_quota - included_quota, 0) * overage_unit_price`. الرسم الثابت يُفوتر دائماً بسطر منفصل، وسطر العمليات الزائدة يُحذف تماماً من الفاتورة عند استهلاك ضمن الباقة أو مساوٍ لها لمنع ظهور سطور بقيمة صفر.
- **حظر القيود المحاسبية المباشرة في `platform_ops`:** لا تستورد الوحدة `JournalHeader` أو `JournalLine` أو `post_journal` إطلاقاً. كل أثر مالي يمر عبر مسار المبيعات الرسمي بإنشاء `SalesInvoice` عبر `SalesInvoiceSerializer` ثم ترحيلها عبر `sales.services.post_sales_invoice` في شركة المنصة.
- **ذرية وعدم تكرار الفوترة (Idempotency & Atomicity):** كل دورة فوترة مقفولة بسجل تدقيق `SubscriptionBillingRecord` بقيد فرادة صريح على `(subscription, period_start, period_end)`. تكرار استدعاء الخدمة أو تشغيل أمر الإدارة لنفس الدورة يعيد نفس السجل فوراً دون إنشاء فواتير جديدة ودون تدوير مضاعف للعداد.
- **التدوير الآمن لدورة الاشتراك:** تصفير العداد (`consumed_quota = 0`) وتقديم دورة الاشتراك (`period_start`, `period_end`) للشهر التالي يتمان حصراً داخل نفس المعاملة الذرية الناجحة وتحت قفل `select_for_update` على الاشتراك؛ وأي خطأ أثناء إنشاء أو ترحيل الفاتورة يُرجع المعاملة بالكامل ويحفظ العداد والدورة دون أي تعديل.
- **التحقق الصارم من صحة الأصناف والشركات (cross-tenant):** عميل الفوترة (`billing_customer`) وأصناف الفوترة (الرسم الثابت والعمليات الزائدة) يجب أن تتبع شركة المنصة المفوترة (لا شركة الزبون المشترك ولا شركة أخرى)، ويجب أن تكون الأصناف خدمية (`is_service=True`).
- **الدعوة لحالة `offered` وحدها ولا لمن له `hired_employee`:** إصدار الدعوة محصور بالمترشحين في حالة عرض العمل والذين لم يُعيَّنوا بعد؛ وإصدارُ دعوةٍ يُبطل كلَّ دعوةٍ سابقةٍ حيّةٍ للمتقدّم (`revoked_at`)، والصلاحيّةُ 1..168 ساعة وإلا 400.
- **حذفُ إعلانٍ له متقدّمون مرفوضٌ:** لأنّ `JobApplicant.job` هو `CASCADE`، فحذف الإعلان يسقط المتقدمين وسجلاتهم وسيرهم الذاتية؛ ورفضه بـ400 يحمي البيانات.
- **إبطال الدعوة عند مغادرة العرض:** `platform_ops/services.py` (`transition_applicant_status`) يبطل تحت القفل كل دعوة حية للمتقدم (`revoked_at`) عند مغادرة حالة `offered`؛ و`platform_ops/services.py` (`accept_applicant_invitation`) لا يقبل إلا متقدماً حالتُه `offered` تماماً وإلا 410 ولا ينشأ مستخدم، فلا يُوظَّف المرفوض برابط قديم. تمر كلمة المرور بـ`validate_password`، وسباق اسم المستخدم ⇒ 400 لا 500.
- **الدورة ذات الإجمالي الصفري:** `platform_ops/services.py` (`bill_subscription_for_period`) تنشئ `SubscriptionBillingRecord` بلا فاتورة، وتقدّم الدورة وتصفّر العداد في المعاملة نفسها؛ وإلا علق الاشتراك وتراكم العداد أشهراً.
- **بوابة الفوترة الواحدة:** `platform_ops/services.py` (`billing_preflight`) هي بوابة التشغيل والمعاينة؛ ومنها أن عميل الفوترة لا يكون من شركة الاشتراك نفسها (`billing_customer_same_tenant`) وإلا رُحّلت فاتورة الخدمة في دفاتر الزبون.
- **فتح وإغلاق الإعلان:** `platform_ops/serializers.py` (`JobPostingSerializer`) يجعل `is_open` للقراءة فقط؛ الإغلاق وإعادة الفتح بفعلَي `close`/`reopen` وحدهما.
- لا نقاط تحفيزية (gamification) في لوحة عمليات المنصة.

**قيودٌ معروفةٌ مقبولةٌ للإطلاق التجريبيّ (م٨)** — قرارٌ واعٍ لا سهو، يُعاد النظرُ فيه بعد الـpilot:

- **ربطُ عميل الفوترة يدويّ:** لا نقطةَ ولا شاشةَ تكتب `ServiceSubscription.billing_customer`؛ يُضبط من `manage.py shell` لشركة الـpilot الواحدة.
  ولا حارسَ عند الكتابة نفسِها؛ الحارسُ عند الفوترة في `platform_ops/services.py` (`billing_preflight`) — عميلٌ من شركة الاشتراك يُرفض قبل أيّ فاتورة.
- **العدّادُ بلا تاريخ:** `consumed_quota` يُحسب على الدورة الجارية لحظةَ القبول، فعمليّةٌ تُقبل بين `period_end` وتشغيل الأمر تُفوتَر على الدورة المنتهية.
  لذلك يُشغَّل `bill_service_subscriptions` صباحَ أوّل يومٍ من الشهر.
- **مسؤولُ التوظيف يرى رابطَ الدعوة الخامّ** لأنّه مَن يسلّمه للمرشّح؛ فيستطيع تقنيّاً قبولَها بنفسه. الحسابُ الناتج يظهر `PlatformEmployee`
  مرتبطاً بالمتقدّم (`hired_employee`) تحت أنظار السوبر أدمن، والدعوةُ تُبطل بالرفض أو بإصدار غيرها.

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
| `platform_ops/tests/test_migration_graph.py` | وجود الهجرات وترتيب الاعتماديات |
| `platform_ops/tests/test_subscription_billing.py` | فوترة الاشتراكات الشهرية: الحساب وفصل السطور وترحيل الفواتير وعدم التكرار والذرية وعزل الشركات وسلامة الحقول، والدورة الصفرية بلا فاتورة، ورفض عميل من شركة الاشتراك، والمعاينة تساوي التشغيل و`CommandError` |
| `platform_ops/tests/test_daily_ratings_and_books.py` | العمل الفعلي شرطاً، انتهاء الرمز بـ410، التعديل الواحد، عدم حفظ الرمز الخام، القائمة البيضاء للرد العام، الخانق بـ429 مع ترويسة مزوَّرة، استبعاد العرض والدخول، عزل الشركة، اشتقاق الوكيل من `Engagement` حصراً، فصل الدرجتين، ومنع المُقيَّم من تعديل تقييمه أو حذفه |
| `platform_ops/tests/test_hiring_portal.py` | بوابة التوظيف والسطح الإداري (`PlatformHiringAdminSurfaceTests`): النماذج بلا `tenant`، فحص السيرة بالبايتات والبنية، التقديم العام، 410 للمغلق، تهشير رمز الدعوة، إنشاء الحساب عند القبول لا قبله، منع تحريك الحالة بكتابة مباشرة، رفض حذف إعلان له متقدمون، تمرير بايتات السيرة بلا تسليم رابط التخزين، عزل دور التوظيف عن كل مسارات المنصة، وجرد السطح العام بخانقه ومصادقته، ورفض المتقدم يبطل الدعوة، و`PATCH is_open` متجاهل، واسم السيرة العربي `filename*=`، وقوة كلمة المرور وسباق اسم المستخدم |
| `platform_ops/tests/test_hiring_frontend_contract.py` | حارس العقد بين واجهات التوظيف والفوترة بالـ frontend وحمولات الخادم الحقيقية للـ 13 واجهة، ومطابقة `APPLICANT_STATUS_OPTIONS`/`EMPLOYMENT_TYPE_OPTIONS` لـ`choices` الخادم |
| `tenants/tests/test_member_activity_log.py` | تسجيل إضافة عضو وتغيير دوره وحذفه في `ActivityLog` |
