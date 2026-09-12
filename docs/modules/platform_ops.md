# platform_ops — مركز قيادة كترا وعمليات المنصة

> مبني على قراءة الكود مباشرةً بتاريخ 2026-09-12. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

وحدة داخلية على مستوى المنصة لإدارة موظفي عمليات كترا وخدمة متابعة الزبائن
والإدخال. ليست وحدةً مرخّصةً للشركات، لذلك لا تدخل `core/modules.py` ولا تعتمد
على `X-Tenant-Id`. مسارات الإدارة تحت `/api/platform/ops/` ومحروسة بصلاحيات
المنصة.

## أهم الملفات

| الملف | الغرض |
|---|---|
| `platform_ops/models.py` | هوية موظف المنصة، اشتراك الخدمة مع عميل الفوترة (`billing_customer`)، سجل تدقيق الفوترة الشهرية (`SubscriptionBillingRecord` مع `invoice` اختياري للباقات الصفرية)، الارتباطات (`Engagement` بنوعها `standard`/`onboarding` وتاريخ انتهائها وسابقها `predecessor`)، سجل العضويات (`AgentGrantedMembership`)، وأوامر العمل (`WorkOrder` — بأولوية `priority` منذ 210-C) ومُسلَّماتها (`WorkOrderDeliverable` — بتصنيف رفض `rejection_category` منذ 210-C) وتعليقاتها (`WorkOrderComment`)، ومفاتيح قنوات الاستقبال (`IntegrationKey`)، وملف سياسة الأداء (`PolicyProfile`)، ولقطة الأداء الشهرية (`PerformanceSnapshot`)، وإشعارات المنصة (`PlatformNotification`)، وسجل النشاط العابر (`PlatformActivityLog`)، والتقييم اليومي (`DailyRating`) ورمزه العام (`DailyRatingToken`)، وفحص صحة الدفاتر والتشغيل المعتمد (`CompanyHealthCheck` وبنوده `CompanyHealthCheckItem`)، واكتساب العميل (`CustomerAcquisition`)، وحدث تدقيق عمليات المنصة الموحّد (`PlatformOperationEvent`) — الثلاثة الأخيرة من التذكرة 210-B — وكتالوج وحدات الخدمة بنسخٍ مؤرَّخة (`ServiceUnitCatalog` وبنوده `ServiceUnitCatalogEntry` وحدث تدقيقه `ServiceUnitCatalogEvent`)، وربط المستند بأمر العمل (`WorkOrderDocumentLink`)، ودفتر استخدامٍ غير قابل للمحو (`ServiceUsageEvent`) — الأربعة من التذكرة 210-C |
| `platform_ops/services.py` | بوابة الاشتراك، دورة حياة الارتباط، تعليق الارتباط والمغادرة (`suspend_engagement`)، إدارة دورة حياة أمر العمل، حساب وإيقاف الأجل، اعتماد ورفض المُسلَّمات، مفاتيح القنوات والفوترة، حساب أداء الموظف عبر المحاور الخمسة الرسمية (`ALL_PERFORMANCE_AXES`) بما فيها محور تقييم الزبائن (`AXIS_CUSTOMER_RATING`) ومحور الحضور والانضباط (`AXIS_ATTENDANCE_REGULARITY`)، وقرار تعديل التقييم (`decide_rating_update`)، والتقاط اللقطات الشهرية، وشريط التدخل، والتقييم اليومي وتبويب «من يمسك دفاتري»، ودرجتَي الصحة المنفصلتين مع أسباب التخفيض المفصلة، وحساب وفوترة الاشتراكات الشهرية وإصدار فواتير المبيعات وترحيلها محاسبياً (`bill_subscription_for_period` · `bill_subscriptions_for_period`) مع فحص الصلاحية المسبق الموحد (`billing_preflight`) واستثناءات انتهاء الوظائف والدعوات (`JobGone` · `InvitationGone`)، ودورة حياة فحص صحة الدفاتر والتشغيل (`create_health_check_draft` · `update_health_check` · `refresh_health_check_auto_items` · `update_health_check_item` · `approve_health_check` · `convert_health_check_item_to_work_order` · `compare_health_baseline`)، وبوابة الإسناد والطاقة (`assign_platform_employee` · `transfer_engagement` · `employee_capacity_snapshot` · `list_assignment_candidates`)، واكتساب العميل (`set_customer_acquisition` · `get_customer_acquisition`) — التذكرة 210-B — وكتالوج وحدات الخدمة (`create_service_unit_catalog_draft` · `update_service_unit_catalog_entries` · `activate_service_unit_catalog` · `clone_service_unit_catalog_to_draft` · `get_active_service_unit_catalog`)، وربط مستند وتوليد الطابور (`link_work_order_document` · `change_work_order_priority` · `list_employee_work_order_queue`)، ودفتر الاستخدام (`generate_usage_events_for_deliverable` · `approve_work_order_deliverable_with_usage` · `reverse_usage_event`) — التذكرة 210-C |
| `platform_ops/management/commands/bill_service_subscriptions.py` | أمر إدارة فوترة اشتراكات خدمة المنصة الشهرية وإصدار فواتير المبيعات وتدوير الدورات (`--period` · `--fixed-fee-product-id` · `--overage-product-id` · `--dry-run`)؛ المعاينة والتشغيل يمران بـ`billing_preflight` نفسها، وأي خطأ ⇒ `CommandError` |
| `platform_ops/authentication.py` | مصادقة مفتاح قناة الاستقبال (`IntegrationKeyAuthentication`) وحارس التحقق (`HasValidIntegrationKey`) |
| `platform_ops/throttles.py` | خانق استقبال أوامر العمل المربوط بمفتاح القناة (`IntegrationKeyThrottle`)، وخانق النطاق المربوط بـ`REMOTE_ADDR` لا بترويسة يرسلها العميل (`ClientIpScopedThrottle`) |
| `platform_ops/permissions.py` | حارسا موظف العمليات ومدير العمليات |
| `platform_ops/views.py` | نقاط القراءة الإدارية والتشغيلية، واستقبال أوامر العمل، ومسار استعلام الأداء واللقطات، وصندوق الإشعارات، وسجل النشاط العابر، واللوحة التفاعلية، والتقييم اليومي (`DailyRatingViewSet`)، وتبويب «من يمسك دفاتري» (`TenantAgentBooksViewSet`)، والرابط العام (`PublicDailyRatingView`)، وعرض صحة الشركة الإداري (`CompanyHealthView` — درجتان مشتقّتان حيّاً، لا تخلط مع `CompanyHealthCheckViewSet` أدناه)، وفحص صحة الدفاتر والتشغيل المعتمد (`CompanyHealthCheckViewSet`)، والإسناد والطاقة (`EngagementViewSet`)، واكتساب العميل (`CustomerAcquisitionView`) — الثلاثة الأخيرة 210-B — و`WorkOrderViewSet` بأفعال 210-C الجديدة (`create`/`queue`/`assign`/`change-priority`/`transition`/`comments`/`link-document`/`document-links`/`deliverables`/`deliverables/{id}/review`)، وكتالوج وحدات الخدمة (`ServiceUnitCatalogViewSet`)، ودفتر الاستخدام (`ServiceUsageEventViewSet`) — الثلاثة 210-C |
| `platform_ops/urls.py` · `platform_ops/urls_tenant.py` · `platform_ops/urls_staff.py` | ثلاثة مسارات منفصلة: الأول سطح المنصة تحت `/api/platform/ops/`، والثاني سطح المستأجر تحت `/api/my-agent/`، والثالث قدرات موظفي المنصة تحت `/api/platform-staff/` |
| `frontend_v2/components/platform-hiring/` | شاشة التوظيف المنصي وتبويباتها الثلاث (الوظائف، المتقدمون، مسؤولو التوظيف، ولوحة تفاصيل المتقدم) وصفحتا التقديم العام وقبول الدعوة |
| `frontend_v2/components/platform/BillingRecordsScreen.tsx` | شاشة سياسة اشتراك الـpilot (`SubscriptionPolicyPanel`) ونظرة عامة على الاشتراكات (`SubscriptionsPanel`) للقراءة، مع نافذة سجلات الفوترة للقراءة فقط والبحث المحلي وصف المجموع بالسنتات — التفعيل والانتقالات على بطاقة الشركة |
| `frontend_v2/components/platform/ServiceSubscriptionSection.tsx` | بطاقة خدمة الإدخال داخل `PlatformCompanyPanel.tsx`: الحالة وتبقّي التجربة والأفعال المسموحة لكل حالة وعميل الفوترة وسجل الأحداث |
| `frontend_v2/components/platform/CompanyHealthCheckSection.tsx` | قسم «صحة الدفاتر والتشغيل» داخل `PlatformCompanyPanel.tsx` — دورة حياة الفحص (مسودة/بنودها/اعتماد) ومقارنة الأساس، منفصلٌ بصرياً ونصّياً عن `CompanyHealthPanel.tsx` (210-B) |
| `frontend_v2/components/platform/EngagementAssignmentSection.tsx` | قسم «الإسناد والطاقة» داخل `PlatformCompanyPanel.tsx` — الموظف الحالي وسجل النقل والتعليق والإلغاء، ومربّع اكتساب العميل المستقلّ (210-B) |
| `frontend_v2/utils/platformHealthAssignment.ts` · `.test.ts` | دوال نصية خالصة لفحص الصحة والإسناد: تسميات الحالات، نقص الدليل الإلزامي قبل الاعتماد، تبقّي مهلة onboarding، صياغة الحمل/الطاقة، والأفعال المسموحة لكل حالة ارتباط — بوابة `node --test` (210-B) |
| `frontend_v2/components/platform/WorkOrdersPanel.tsx` (210-C) | تبويب «أوامر العمل» داخل `PlatformOpsDashboard.tsx`: طابور الموظف، تفصيل أمر العمل (نقل الحالة، ربط مستند، تسليم عمل، تعليقات)، ومراجعة المُسلَّمات (اعتماد/ردٌّ بسببٍ وتصنيف) — يُضمَّن بتبويب محلّي في اللوحة بلا لمس `App.tsx` الممنوع |
| `frontend_v2/components/platform/ServiceUnitCatalogPanel.tsx` (210-C) | تبويب «كتالوج وحدات الخدمة»: نسخ الكتالوج، تحرير بنوده لكل نوع مستند، وتفعيله بسبب وتاريخ سريان |
| `frontend_v2/components/platform/ServiceUsageLedgerPanel.tsx` (210-C) | تبويب «دفتر الاستخدام» (القصة ١٩): كل حدثٍ بمصدره (نوع المستند ورقمه) ولقطة بنوده **ومصدر ذلك العدد** (`observed`/`declared`) ونسخة الكتالوج التي حُسب بها — وهي مادّةُ الاعتراض؛ والعكسُ بسببٍ مكتوبٍ **داخل الصفّ** (لا `window.prompt`) يُنشئ حدثاً جديداً ولا يحذف الأصل، ولا يُعرض زرُّه لحدثٍ معكوسٍ سلفاً |
| `frontend_v2/services/platformWorkOrdersApi.ts` (210-C) | عميل API لكل نقاط 210-C الجديدة (الطابور، النقل، الروابط، المُسلَّمات، المراجعة، الكتالوج، دفتر الاستخدام)، ونسخة عميلة من `WORK_ORDER_TRANSITIONS` للعرض فقط — الخادم هو الحكم |
| `frontend_v2/components/platform/SearchPicker.tsx` | هيكل منتقي البحث المشترك (تأجيل 250ms، قائمة نتائج، شريحة المختار)؛ حصر النتائج يبقى خادمياً داخل دالّة `search` التي يمرّرها المستدعي |
| `frontend_v2/components/platform/BillingCustomerPicker.tsx` · `BillingProductPicker.tsx` · `CompanyPicker.tsx` | منتقيات بحث بلا كتابة معرّفات خام فوق `SearchPicker`: عملاء الفوترة (`searchBillingCustomers`)، وأصناف فوترة نسخة السياسة (`searchPolicyBillingProducts`)، وشركات المنصة (`getPlatformDashboard` — لا نداء ثانٍ) |
| `frontend_v2/utils/platformSubscriptionManagement.ts` · `.test.ts` | دوال نصية خالصة: الأفعال المسموحة لكل حالة اشتراك ونص تبقّي التجربة — بوابة `node --test` |
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
| `platform_ops/tests/test_engagement_lifecycle.py` | دورة حياة الارتباط، فرادة الإسناد تحت قفل، حفظ عضوية الزبون، الاستئناف، والمغادرة، وحارس ترتيب الأقفال (يشمل `DECLARED_LOCK_ORDER` بعد 210-B) |
| `platform_ops/tests/test_health_and_capacity.py` | التذكرة 210-B: دورة حياة فحص الصحة (مسودة/تعديل/اعتماد ورفضه الواضح)، بوابة الأساس المعتمد للإسناد العادي واستثناء onboarding، رفض تجاوز الطاقة وقبوله بسبب، النقل يبقي التاريخ ولا يمسّ الاكتساب، اكتساب العميل صفٌّ واحد يُحدَّث لا يتكرر، وعزل كل مسار جديد بـ403 لغير السوبر أدمن |
| `platform_ops/tests/test_health_assignment_frontend_contract.py` | حارس العقد بين واجهات فحص الصحة/الإسناد بالـ frontend وحمولات الخادم الحقيقية، ومطابقة تسميات الحالات لـ`choices` الخادم (210-B) |
| `platform_ops/tests/test_work_orders.py` | آلة حالات أمر العمل، إيقاف الأجل عند انتظار العميل، لقطة السياسة والتسليم، إلزامية مستوى ظهور التعليق، والعزل بالشركة |
| `platform_ops/tests/test_channel_intake.py` | استقبال القنوات، فرادة المرجع الخارجي (idempotency)، احتساب الفوترة تحت قفل، رفض الحقول الممنوعة، التحقق من المرفقات، الخانق، وفحص الحجم بالبايتات |
| `platform_ops/tests/test_performance_metrics.py` | المقاييس الستة، ملفات السياسات، الدرجة المركبة، كفاية العينة، تجميد اللقطة الشهرية، إعادة توزيع الأوزان، وعزل الاستعلام العابر للشركات |
| `platform_ops/tests/test_dashboard_and_notifications.py` | اللوحة التفاعلية، شريط التدخل، التنقيب، الفلترة الخادمية للإشعارات، سجل النشاط العابر، رفض وسائط الشركات الممنوعة بـ 400، واتساع أعمدة الخيارات |
| `platform_ops/tests/test_service_unit_catalog.py` (210-C) | دورة حياة كتالوج وحدات الخدمة: مسودة بلا بنود، تعديل البنود ورفض التكرار وقيم سالبة، رفض تفعيل كتالوج فارغ أو بلا سبب، تفعيل نسخة يُنهي السابقة عند تاريخ سريانها، `effective_state` يعكس النافذة لا الحالة وحدها، الاستنساخ ينسخ البنود، ورفض التعديل بعد التفعيل |
| `platform_ops/tests/test_usage_ledger.py` (210-C) | صيغة الوحدات (أساس + وزن السطر × الكمية)، لا وحدات قبل الاعتماد، كتالوج أو بند غائب يمنعان الاحتساب صراحةً، idempotency برابط المستند (لا حدث مضاعف مهما تكرر الاستدعاء)، إعادة العمل بخطأ الموظف لا تُخصّم ولا تُمنح مرتين، إعادة العمل بمعلومات عميل جديدة تحتسب رابطاً جديداً، مستند القناة لا يمنح إنجازاً إلا بمراجعة، عكس حدث الاستخدام بلا حذف ولا سالب مجهول، اختبار عابر (seam) عبر API حقيقي (فاتورة متعددة البنود ← رد ← اعتماد ← وحدة واحدة بلا مضاعفة)، تسجيل الأنشطة الجديدة (`link_document`/`change_priority`) في `PlatformActivityLog`، وعزل 403 على المسارات الجديدة |

## النماذج الحالية

| Model | الحقول والقواعد المهمة |
|---|---|
| `PlatformEmployee` | `user` واحد لواحد، `specialty`، `capacity_target`، وحالة `active/on_leave/offboarded`. بلا `tenant` عمداً لأنه موظف للمنصة لا لشركة. |
| `ServiceSubscription` | صف واحد لكل شركة، الحالة (`trial/active/suspended/cancelled` — `INACTIVE` بلا صفّ أصلاً) والباقة والرسم الشهري والحد والعداد وسعر العملية الزائدة ودورة الفوترة ونافذة التجربة (`trial_started_at`/`trial_ends_at`)، مع عميل الفوترة (`billing_customer`) وشركة الفوترة الملتقطة (`billing_tenant`) ونسخة السياسة الملتقطة (`subscription_policy_version`) وصنفا الفوترة الملتقطان منها (`fixed_fee_product`/`overage_product`)، والحالة قبل التعليق (`pre_suspension_status`) وجدولة الإلغاء (`scheduled_cancellation_date`/`cancellation_reason`). `tenant` علاقة OneToOne تفرضها MySQL. |
| `ServiceSubscriptionPolicy` | نسخة مؤرَّخة من افتراضيات الاشتراك (`draft/active/retired`) بنطاق خطة (`plan` فارغ = عامة، أو اسم خطة تغلب العامة) — الرسم الشهري والحصة وسعر الزائد وأيام التجربة وشركة الفوترة وصنفا الفوترة (`fixed_fee_product`/`overage_product`) وسبب التفعيل الإلزامي وتاريخ السريان. `effective_state` (`draft/scheduled/current/retired`) يُحسب من نافذة السريان لا من الحالة وحدها. النسخة غير المسودة لا تُعدَّل أبداً — تُستنسخ إلى مسودة جديدة. |
| `ServiceSubscriptionEvent` | سجلّ تدقيق غير قابل للمحو (`PROTECT` على الاشتراك) لكل انتقال حالة أو تعديل تجاري: الإجراء، من/إلى حالة، السبب، الفاعل (`SET_NULL`)، معرّف ارتباط (`correlation_id`)، وتفاصيل JSON بلا بيانات شخصية. لا مسار تعديل أو حذف. |
| `ServiceSubscriptionPolicyEvent` | سجلّ تدقيق غير قابل للمحو (`PROTECT` على النسخة) لكل كتابة على سياسة الاشتراك: `created/updated/cloned/activated/retired`، الفاعل (`SET_NULL`)، معرّف الارتباط، وتفاصيل قبل/بعد للتعديل بلا بيانات شخصية. الاستنساخ حدث `cloned` واحد يحمل `source_policy_id` لا `created` معه. |
| `Engagement` | ارتباط موظف بشركة: `active/suspended/revoked`، من أسند ومتى، طوابع التعليق والإلغاء، وحقل `created_membership` للتمييز بين العضوية المنشأة وعضوية الزبون المسبقة. فرادة النشط تحت قفل برمجي لا قيد شرطي. (210-B) يضيف `kind` (`standard`/`onboarding` — الثاني يتخطّى شرط الأساس المعتمد لمدة `MAX_ONBOARDING_DAYS` موسومة بـ`onboarding_expires_at`)، و`ended_at`/`end_reason` (طابع ونهاية عامّان يرافقان الإلغاء أو النقل معاً)، و`predecessor` (self، `SET_NULL`، الارتباط الذي حلّ هذا محلّه عبر `transfer_engagement` — تاريخ النقل يبقى مقروءاً)، و`capacity_override_reason` (يُملأ فقط حين يتجاوز الإسناد/النقل الطاقة المستهدفة). |
| `CompanyHealthCheck` (210-B) | فحصٌ **يُخزَّن ويبقى تاريخه** — لا يُشتق حيّاً كدرجتَي الصحة أعلاه. `tenant` FK (يحمل `tenant` مباشرة لأنه سجلٌّ مستقلٌّ لا مشتقٌّ عبر صفٍّ آخر)، `kind` (`baseline`/`monthly`)، `status` (`draft`/`approved` — لا حذف ولا رجوع)، `period`، `complexity` (`low`/`medium`/`high`، فارغ حتى يُقدَّر، **إلزامي قبل الاعتماد**)، `notes`، `created_by`/`approved_by` (`SET_NULL`)، `approved_at`. فحصٌ جديد صفٌّ جديد دوماً — لا تعديل على صفّ سابق. |
| `CompanyHealthCheckItem` (210-B) | بند من كتالوج ثابت في الكود (`HEALTH_CHECK_ITEM_CATALOG`، سبعة بنود، ليس إدخالاً حرّاً). `health_check` FK (لا `check`: يصطدم اسمها بـ`Model.check()` فيسقط `system check` بخطأ `E020`)، `code`، `status` (`healthy`/`follow_up`/`risk`/`not_applicable`)، `evidence_value`/`evidence_note` (رقم و/أو ملاحظة — الاعتماد يرفض بندًا إلزامياً بلا كليهما معاً)، `source` (`auto` يُملأ من `_compute_auto_health_evidence`، `manual` يبدأ `follow_up` فارغاً)، `mandatory`، `action`، `owner` (`SET_NULL`)، `due_date`، `work_order` (`SET_NULL`، `related_name="health_check_items"` — يربط تحويل البند إلى أمر عمل). قيد فرادة غير مشروط على `(health_check, code)`. |
| `CustomerAcquisition` (210-B) | من جلب الشركة كعميل — **مستقلٌّ تماماً عمّن يخدمها الآن** (`Engagement`)؛ النقل لا يمسّه أبداً. `tenant` OneToOne (صفٌّ واحدٌ لا يتكرر لكل شركة)، `acquired_by` (`PlatformEmployee`، `PROTECT` — لا يُحذف موظفٌ له سجلّ اكتساب)، `acquired_at`، `note`، `created_by` (`SET_NULL`). |
| `PlatformOperationEvent` (210-B) | حدث تدقيق **موحّد** لكل أفعال 210-B (إسناد/نقل/تعليق/استئناف/إلغاء/اعتماد فحص/تحويل بند/تسجيل اكتساب) — نموذجٌ عامّ واحد لا نموذجٌ لكل نطاق، بخلاف `ServiceSubscriptionEvent` المتخصّص. يحمل `tenant` مباشرة (خلافاً لـ`ServiceSubscriptionEvent` الذي يشتقّها عبر `subscription.tenant`؛ هنا القيد نطاقاتٌ متعددة `domain` بلا أب واحد يُشتقّ منه دوماً فحُمل الحقل مباشرة)، `domain` (`engagement`/`health_check`/`acquisition`)، `action`، `subject_id` (معرّف الصفّ المتأثر، لا FK لتعدد النماذج الهدف)، `reason`، `actor` (`SET_NULL`)، `correlation_id`، `details` (JSON بلا بيانات شخصية). لا مسار تعديل أو حذف. |
| `AgentGrantedMembership` | سجل العضويات الممنوحة أو المعدلة بواسطة وكيل: الشركة، الوكيل الفاعل، الارتباط، `role_before/role_after`، ولقطة هوية ثابتة (`identity_snapshot`) تبقى مقروءة ومفيدة حتى لو حُذفت العضوية لاحقاً. |
| `WorkOrder` | أمر عمل موجه لشركة (`tenant` إلزامي). يتميز بـ `kind` و `source` و `channel` و `external_ref`. مسؤول واحد فقط (`assignee`). آلة حالات صارمة (`received -> screening -> data_entry -> review -> approval -> closed` مع تفريعة `waiting_customer` و `cancelled`). الأجل يُقاس من `received_at` إلى `approved_at`، مع حسم فترات الانتظار المتراكمة (`waiting_seconds_total`). لقطة السياسة (`policy_snapshot`) ثابتة على الصف. فرادة غير مشروطة لكل `(tenant, channel, external_ref)` لضمان idempotency. `priority` (210-C — `low/normal/high/urgent`، افتراضياً `normal`) لترتيب طابور الموظف الموحَّد فقط، ولا علاقة له بالأجل المحسوب من السياسة. |
| `WorkOrderDeliverable` | مخرج أمر العمل (`note` / `structured_report` / `attachment`) مع `content_snapshot` ثابتة لا تتأثر بتحرير المصدر، ودورة مراجعة (`pending/approved/rejected`) مع سبب رفض إلزامي. `rejection_category` (210-C — `employee_error`/`customer_new_info`/`other`، إلزامي عند الرفض) يحدد وحده — بالاشتراك مع اصطلاح إعادة استخدام `WorkOrderDocumentLink` نفسه أو إنشاء رابط جديد — هل يُعاد الاحتساب أم لا عند إعادة العمل. |
| `WorkOrderComment` | خيط تعليقات واستفسارات أمر العمل. حقل `visibility` إلزامي (`internal` أو `client_visible`) مع حجب الداخلي عن أي مسار زبون. |
| `WorkOrderDocumentLink` (210-C) | مرجعُ احتسابٍ لا FK حقيقي (`document_type` + `document_id` رقمي بلا علاقة، لتعدد نماذج المستندات الممكنة) — **لا يمسّ مسار المستند الرسمي ولا حقوله**. يحمل `line_count` و`complexity` (فارغ/`low`/`medium`/`high`) و`deliverable` (`SET_NULL`، يُملأ لحظة التسليم). الصفّ **يُعاد استخدامه** لا يُعاد إنشاؤه عند إعادة تسليمٍ بسبب خطأ الموظف — هذا الاصطلاح نفسه هو آلية منع الاحتساب المضاعف (مفتاح idempotency لحدث الاستخدام مشتقٌّ من `pk` هذا الصفّ). ويحمل كذلك `line_count_source` (`observed`/`declared`) و`recount_reason`: **عددُ البنود يُرصد من المستند نفسه حين يكون نوعُه مملوكاً لتطبيقٍ مسموحٍ في حارس العزل** (`sales_invoice` اليوم — تُقرأ الفاتورة فيُتحقَّق وجودُها وانتماؤها للشركة، ويُرفض معرِّفٌ لا وجود له بـ`document_not_found` أو مستندُ شركةٍ أخرى بـ`document_tenant_mismatch`)، وما عداه يبقى `declared` مُصرَّحاً به من الموظف ويُعرَض كذلك للمعتمِد صراحةً. |
| `ServiceUnitCatalog` (210-C) | نسخة مؤرَّخة من صيغة احتساب الوحدات (`draft/active/retired`)، بنفس اصطلاح `ServiceSubscriptionPolicy`: `effective_state()` (`draft/scheduled/current/retired`) يُحسب من نافذة السريان (`effective_from`/`effective_to`) لا من `status` وحدها، والنسخة غير المسودة لا تُعدَّل أبداً — تُستنسخ إلى مسودة جديدة (`clone_service_unit_catalog_to_draft`)، وتفعيل نسخة تالية يُغلق نافذة السابقة عند تاريخ سريان الجديدة (لا تُحذف ولا تُستبدل في مكانها). التفعيل يتطلب `activation_reason` غير فارغ وبنداً واحداً على الأقل (`catalog_empty`). |
| `ServiceUnitCatalogEntry` | صيغة الاحتساب لنوع مستند واحد داخل نسخة كتالوج: `base_units + per_line_weight × line_count + complexity_*_add` (`units_for()`)، مقرَّبة إلى منزلتين عشريتين. فرادة `(catalog, document_type)`. |
| `ServiceUnitCatalogEvent` | سجلّ تدقيق غير قابل للمحو (`PROTECT` على الكتالوج) لكل كتابة (`created/updated/cloned/activated/retired`) — نفس اصطلاح `ServiceSubscriptionPolicyEvent` تماماً، وليس `PlatformOperationEvent` الموحَّد: نطاقاته الثلاثة (`engagement`/`health_check`/`acquisition`) مصمَّمة لحدثٍ واحدٍ بمعرّف صفّ واحد (`subject_id`)، لا لدفعة بنودٍ كاملة كما هنا. |
| `ServiceUsageEvent` (210-C) | **دفتر الاستخدام** — سجلٌّ غير قابل للمحو (`PROTECT` على الاشتراك/أمر العمل/المُسلَّم/الرابط) يُنتَج **حصراً** عند اعتماد مُسلَّمٍ (لا قبله إطلاقاً). لكل حدث: `units` (من صيغة الكتالوج وقت الاحتساب، مثبتة على الحدث)، و`line_count_snapshot` مع `line_count_source` (`observed`/`declared` — منقولان عن الرابط لحظة الاحتساب فيبقى في الدفتر **هل كان العددُ مرصوداً أم مُصرَّحاً به**)، وعلما احتساب مستقلان `chargeable_to_customer`/`creditable_to_employee` (`_classify_usage_flags`) — مستندٌ وصل عبر قناة يستهلك حصة العميل دوماً لكن لا يمنح الموظف إنجازاً إلا إن كان أمر العمل مراجعة. `idempotency_key` فريد ومُشتقٌّ من `pk` رابط المستند (`platform_ops:usage:doclink:{id}`) — استدعاء متكرر لنفس الرابط يعيد نفس الحدث لا حدثاً جديداً. العكس (`event_type=reversal`) حدثٌ جديدٌ يشير لسابقه (`reversed_event`) بمفتاح `platform_ops:usage:reversal:{id}` — **لا حذف ولا رقم سالب مجهول**. |
| `IntegrationKey` | مفتاح قناة استقبال لشركة زبون (`tenant` إلزامي، `channel`، `token_hash` مهشر عبر SHA-256). صف لكل `(tenant, channel)` بفرادة غير مشروطة. قابل للإبطال والتدوير (`active/revoked` وطوابع `revoked_at` و `rotated_at`). الرمز الخام لا يُحفظ في القاعدة أبداً ويظهر مرة واحدة في رد الإصدار أو التدوير. و`revocation_history` تحفظ كل إبطال سابق لأن الصف واحد ويُعاد إصداره. |
| `PolicyProfile` | ملف سياسة أداء لكل تخصص (`specialty` فريد) يحمل أوزان **المحاور الخمسة الرسمية** المحسومة في #203 — `kpi_results` 30٪ · `quality` 25٪ · `customer_rating` 20٪ · `sla_compliance` 15٪ · `attendance_regularity` 10٪ (والإنتاجية جزء من KPI حتى لا يُحسب الحجم مرتين) — ومستهدفاتها وساعات الأجل والحد الأدنى للعينة. المحور غير المنطبق يُسقط ويُعاد توزيع وزنه بالتناسب. لا أوزان لكل موظف على حدة، وتعديلها لاحقاً لا يمس لقطات الأشهر السابقة. |
| `PerformanceSnapshot` | لقطة أداء شهرية لموظف المنصة لكل `(employee, period_year, period_month)` بفرادة غير مشروطة. تحفظ نسخة مجمدة من السياسة والأوزان (`policy_snapshot`) والمقاييس الستة والمحاور، والتقاطها دالة خدمة idempotent لا تكرر الصفوف ولا تضاعف الآثار. |
| `PlatformNotification` | إشعار منصي موجه لمستخدم (`recipient` إلزامي، `tenant` اختياري). مفلتر خادمياً حصراً فلا يرى المستخدم إلا إشعاراته. أنواع مغلقة (`sla_breach`, `low_score`, `quota_exceeded`). يدعم تعليم إشعار أو الكل كمقروء وعدّ غير المقروء. |
| `PlatformActivityLog` | سجل نشاط منصي عابر للشركات مستقل تماماً عن `ActivityLog` المستأجر؛ لأن `ActivityLog` لا يتسع لحدث بلا شركة وفهارسه تبدأ بالشركة. يحمل `employee` إلزامي، و`tenant` اختياري للأنشطة العامة، ومفهرس زمنياً `(employee, -created_at)` و`(-created_at)`. أفعال 210-C الثلاثة الجديدة (`work_order_assigned`/`work_order_priority_changed`/`document_linked`) تُسجَّل بفاعل العملية (المُسنِد/المُغيِّر/الرابط) لا بمُسنَد أمر العمل — نفس اصطلاح `work_order_transition`/`deliverable_submit`/`deliverable_review`/`comment_added` القائم من 210-B، ولا تُسجَّل إن تعذَّر ربط الفاعل بموظف منصة (مدير بلا ملف موظف مثلاً). |
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

وبقرار #210-A: `ServiceSubscriptionPolicy` و`ServiceSubscriptionPolicyEvent` بلا
`tenant` لأن السياسة افتراضيات تجارية على مستوى المنصة كلها لا تخص شركة (و`billing_tenant`
فيها شركة المنصة المفوترة لا شركة زبون)، و`ServiceSubscriptionEvent` بلا حقل مباشر
لأن شركته مشتقة عبر `subscription.tenant` كحال `SubscriptionBillingRecord`. كلها تحت
`/api/platform/ops/` لمدير العمليات وحده.

## أهم نقاط الـAPI

| Method | المسار | الحارس |
|---|---|---|
| GET | `/api/platform/ops/dashboard/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (اللوحة التفاعلية وشريط التدخل) |
| GET | `/api/platform/ops/employees/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` (مفلتر لموظف المنصة على حسابه) |
| GET | `/api/platform/ops/employees/{id}/performance/` | `IsPlatformOperationsManager` أو الموظف نفسه (عزل عابر مشتق من الارتباطات) |
| GET | `/api/platform/ops/employees/{id}/activity/` | `IsPlatformOperationsManager` أو الموظف نفسه |
| GET | `/api/platform/ops/employees/ranking/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/subscriptions/` | `IsPlatformOperationsManager` — قائمة الاشتراكات (تصفية `?company=` و`?status=`) |
| POST | `/api/platform/ops/subscriptions/start-trial/` | `IsPlatformOperationsManager` — تجربة واحدة مدى حياة الشركة عبر `start_service_trial`، بخطة اختيارية (`plan`، افتراضياً `standard`) وأيام نسخة السياسة السارية لها |
| POST | `/api/platform/ops/subscriptions/activate-paid/` · `/{id}/activate-paid/` | `IsPlatformOperationsManager` — تفعيل مدفوع من لا شيء أو تجربة أو ملغى عبر `activate_paid_subscription`؛ `billing_customer` إلزامي و`plan` اختياري (`standard`)، ولا يمنح تجربة ثانية أبداً |
| POST | `/api/platform/ops/subscriptions/{id}/suspend/` · `/{id}/resume/` | `IsPlatformOperationsManager` — تعليق بسبب إلزامي يحفظ الحالة السابقة، واستئناف يعيدها |
| POST | `/api/platform/ops/subscriptions/{id}/cancel/` · `/{id}/withdraw-cancellation/` | `IsPlatformOperationsManager` — إلغاء مجدول لنهاية الدورة افتراضياً أو فوري بـ`immediate=true`، وسحب الجدولة قبل تطبيقها |
| POST | `/api/platform/ops/subscriptions/{id}/update-settings/` | `IsPlatformOperationsManager` — تعديل شروط اشتراك بعينه (الباقة والرسم والحصة وعميل الفوترة) بسبب إلزامي (`reason`) متى تغيّر حقل فعلاً؛ الحقول غير المتغيرة لا تُحفظ ولا تُدقَّق، والملغى مرفوض (409). العميل يُتحقق منه cross-tenant فقط حين يرد في الطلب، ولا يُفرَّغ على اشتراك مدفوع. يسري على أول فوترة شهرية تصدر بعد الحفظ |
| GET | `/api/platform/ops/subscriptions/{id}/events/` | `IsPlatformOperationsManager` — سجل `ServiceSubscriptionEvent` الكامل للاشتراك |
| GET | `/api/platform/ops/subscriptions/billing-customers/` | `IsPlatformOperationsManager` — بحث عملاء الفوترة (`?q=`) محصور خادمياً بشركة الفوترة التي سيتحقق منها الحفظ: الملتقطة على الاشتراك مع `?subscription=<id>` (تعديل العميل أو تحويل التجربة)، وإلا شركة فوترة نسخة السياسة السارية لنطاق `?plan=` المطلوب — لا العامّة، وإلا عرَض المنتقي عملاءَ شركةٍ يرفضها الحفظ |
| GET | `/api/platform/ops/subscription-policies/` · `/{id}/` | `IsPlatformOperationsManager` — سجل نسخ السياسة |
| POST | `/api/platform/ops/subscription-policies/draft/` · `/{id}/update-draft/` | `IsPlatformOperationsManager` — مسودة جديدة (`billing_tenant` وحده يكفي؛ الغائب يأخذ افتراضيات النموذج) أو تعديلها؛ النشطة/المنتهية ترفض التعديل |
| POST | `/api/platform/ops/subscription-policies/{id}/clone/` | `IsPlatformOperationsManager` — استنساخ نسخة نشطة/منتهية إلى مسودة جديدة |
| POST | `/api/platform/ops/subscription-policies/{id}/preview/` | `IsPlatformOperationsManager` — أثر المسودة: النسخة النشطة، فروق الحقول، وتصريح بعدم مسّ الاشتراكات القائمة |
| POST | `/api/platform/ops/subscription-policies/{id}/activate/` | `IsPlatformOperationsManager` — تفعيل بسبب إلزامي (`change_reason`) وتاريخ سريان اختياري (`effective_from`، فوري افتراضياً؛ لاحقاً ⇒ مجدولة)؛ يلزمه صنفا الفوترة الصالحان |
| GET | `/api/platform/ops/subscription-policies/{id}/billing-products/` | `IsPlatformOperationsManager` — بحث الأصناف الخدمية (`?q=`) في شركة فوترة هذه النسخة وحدها، لمنتقي صنفَي الفوترة |
| GET | `/api/platform/ops/billing-records/` | `IsPlatformOperationsManager` — نافذة قراءة على ما فُوتر فعلاً (تصفية `?company=` أو `?subscription=`). الفواتير تُصدَر بأمر الإدارة وحده، لا من هنا. |
| GET · POST · PATCH · DELETE | `/api/platform/ops/job-postings/` | `IsPlatformRecruiter` — إدارة إعلانات الوظائف المنصية: الأفعال `close` و`reopen` و`regenerate-link`؛ و`DELETE` مرفوض بـ400 لإعلان له متقدمون. **الاستثناء الوحيد المعلن** يحرسه `PlatformRecruiterRouteScopeTest`. |
| GET | `/api/platform/ops/job-applicants/` | `IsPlatformRecruiter` — متابعة المتقدمين (قراءة وأفعال لا CRUD): الأفعال `transition-status` و`rate` و`invite` و`cv` (يمرر البايتات بلا تسليم رابط التخزين). |
| GET · POST · DELETE | `/api/platform/ops/recruiters/` | `IsPlatformOperationsManager` — الأفعال `GET`، و`POST` بحقل `identifier` (اسم مستخدم أو بريد، بلا حساسية حالة)، و`DELETE` تعطيل لا حذف؛ بلا `PUT`/`PATCH`. |
| GET | `/api/platform-staff/me/` | `IsAuthenticated` — قدرات المستخدم الحالي على المنصة (يجيب عن المستخدم نفسه، **خارج `/api/platform/` عمداً**). |
| GET | `/api/careers/jobs/{token}/` · POST `{token}/apply/` | `AllowAny` + `ClientIpScopedThrottle` — **كل كود `AllowAny` في حزمة `platform_ops/public_hiring/` وحدها** ليراجعه الأمن دفعة واحدة. السيرة ≤ 5 م.ب ونوعها يُفحصان **بالبايتات** لا بترويسة الرافع. |
| GET | `/api/careers/invitations/{token}/` · POST `{token}/accept/` | `AllowAny` + `ClientIpScopedThrottle` — الحساب يُنشأ **عند قبول الدعوة لا قبلها**؛ ورمز مستهلك أو منتهٍ يرد 410 وغير موجود يرد 404. |
| GET | `/api/platform/ops/work-orders/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (تنقيب مفلتر بدون معاملات شركة) |
| POST | `/api/platform/ops/work-orders/create/` | `IsPlatformOperationsManager` — فتح أمر عمل يدوياً (210-C)؛ الشركة تُتحقق من أهليتها للخدمة |
| GET | `/api/platform/ops/work-orders/queue/` | موظف المنصة نفسه — طابوره الموحَّد عبر شركات ارتباطاته النشطة، مرتَّب بالأولوية ثم الأجل (210-C) |
| POST | `/api/platform/ops/work-orders/{id}/assign/` · `/{id}/change-priority/` | `IsPlatformOperationsManager` — إسناد مسؤول أو إعادة للطابور، وتعديل الأولوية (210-C) |
| POST | `/api/platform/ops/work-orders/{id}/transition/` | مسؤول أمر العمل أو `IsPlatformOperationsManager` — نقل حالة ضمن `WORK_ORDER_TRANSITIONS` وحدها؛ `expected_updated_at` اختياري لتعارض متفائل (409 `conflict_stale_version` مع النسخة الحالية) (210-C) |
| GET · POST | `/api/platform/ops/work-orders/{id}/comments/` | القراءة مفتوحة ضمن نطاق الرؤية، والإضافة لمسؤول أمر العمل أو المدير (210-C) |
| POST | `/api/platform/ops/work-orders/{id}/link-document/` | مسؤول أمر العمل أو `IsPlatformOperationsManager` — ربط مستند مُدخَل بأمر العمل تمهيداً لتسليمه، مرجعٌ للاحتساب بلا FK حقيقي (210-C) |
| GET | `/api/platform/ops/work-orders/{id}/document-links/` | نفس نطاق رؤية أمر العمل — قائمة الروابط (210-C) |
| GET · POST | `/api/platform/ops/work-orders/{id}/deliverables/` | القراءة مفتوحة، والتسليم لمسؤول أمر العمل أو المدير — يقبل `document_link_ids` لضمّ روابط غير مُسلَّمة بعد (210-C) |
| POST | `/api/platform/ops/work-orders/{id}/deliverables/{deliverable_id}/review/` | `IsPlatformOperationsManager` — اعتماد (يولّد أحداث دفتر الاستخدام ويعيدها في الرد) أو ردّ بسبب وتصنيف إلزاميَين معاً (210-C) |
| GET | `/api/platform/ops/service-unit-catalogs/` · `/{id}/` · `/active/` | `IsPlatformOperationsManager` — نسخ كتالوج وحدات الخدمة والنسخة السارية حالياً (210-C) |
| POST | `/api/platform/ops/service-unit-catalogs/draft/` · `/{id}/clone/` · `/{id}/update-entries/` · `/{id}/activate/` | `IsPlatformOperationsManager` — مسودة جديدة، استنساخ، استبدال دفعة البنود، وتفعيل بسبب إلزامي وتاريخ سريان اختياري (210-C) |
| GET | `/api/platform/ops/usage-events/` | `IsPlatformOperationsManager` — دفتر الاستخدام (تصفية `?company=` و`?work_order=`) (210-C) |
| POST | `/api/platform/ops/usage-events/{id}/reverse/` | `IsPlatformOperationsManager` — عكس حدث استخدام بسبب إلزامي؛ حدثٌ جديدٌ لا حذف (210-C) |
| POST | `/api/platform/ops/intake/` | `HasValidIntegrationKey` (بمفتاح القناة لا بجلسة ولا بتوكن مستخدم) |
| GET | `/api/platform/ops/integration-keys/` | `IsPlatformOperationsManager` |
| POST | `/api/platform/ops/integration-keys/issue/` · `{id}/rotate/` · `{id}/revoke/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/policy-profiles/` · `/{id}/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` — قراءة فقط؛ محرّر الأوزان المُصدَّر يأتي مع #210-د (والأوزان الرسمية هي الخمسة أعلاه حتى يُحسم غيرها هناك) |
| GET | `/api/platform/ops/performance-snapshots/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` (مفلتر للموظف على لقطاته) |
| POST | `/api/platform/ops/performance-snapshots/capture/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/notifications/` · `unread-count/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (مفلتر خادمياً) |
| POST | `/api/platform/ops/notifications/{id}/mark-read/` · `mark-all-read/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/activity-logs/` | `IsPlatformOperationsStaff` (لنفسه) أو `IsPlatformOperationsManager` (لكل الشركات) |
| GET | `/api/platform/ops/companies/{tenant_id}/health/` | `IsPlatformOperationsStaff` (للشركات المرتبطة) أو `IsPlatformOperationsManager` (لكل الشركات) |
| GET | `/api/platform/ops/health-checks/` · `/{id}/` | `IsPlatformOperationsManager` — فحوص صحة الدفاتر والتشغيل المعتمدة (تصفية `?company=` و`?kind=`)؛ منفصلة تماماً عن `CompanyHealthView` أعلاه (210-B) |
| POST | `/api/platform/ops/health-checks/create-draft/` | `IsPlatformOperationsManager` — مسودة فحص جديدة لشركة مؤهَّلة للخدمة وحدها عبر `create_health_check_draft`؛ ترفض شركة غير مؤهّلة بكود `subscription_not_eligible` |
| POST | `/api/platform/ops/health-checks/{id}/update/` · `/{id}/refresh/` | `IsPlatformOperationsManager` — تعديل تقدير التعقيد/الملاحظات على مسودة، وإعادة حساب البنود الآلية وحدها؛ كلاهما يرفض فحصاً معتمداً بـ409 (`health_check_immutable`) |
| POST | `/api/platform/ops/health-checks/{id}/update-item/` | `IsPlatformOperationsManager` — تعديل بند واحد (`item` في الجسم) على مسودة |
| POST | `/api/platform/ops/health-checks/{id}/approve/` | `IsPlatformOperationsManager` — اعتماد ذرّي؛ يرفض بلا تعقيد مقدَّر (`complexity_required`) أو بند إلزامي بلا دليل رقمي أو ملاحظة (`evidence_missing`) |
| POST | `/api/platform/ops/health-checks/{id}/item-to-work-order/` | `IsPlatformOperationsManager` — تحويل بند `follow_up`/`risk` إلى أمر عمل مرتبط، idempotent (استدعاء ثانٍ يعيد نفس الأمر) |
| GET | `/api/platform/ops/health-checks/compare/` | `IsPlatformOperationsManager` — مقارنة آخر فحصين تأسيسيين معتمدين بنداً بنداً (`?company=` إلزامي)؛ قراءة صرفة **لا تُنسَب لأي موظف** |
| GET | `/api/platform/ops/engagements/` · `/{id}/` | `IsPlatformOperationsManager` — الارتباطات (تصفية `?company=`، `?employee=`، `?status=`) (210-B) |
| POST | `/api/platform/ops/engagements/assign/` | `IsPlatformOperationsManager` — إسناد عبر `assign_platform_employee`؛ يرفض العادي بلا أساس معتمد (`baseline_required`) إلا `kind=onboarding`، ويرفض تجاوز الطاقة (`capacity_exceeded`، 409) إلا بـ`capacity_override_reason` |
| POST | `/api/platform/ops/engagements/{id}/transfer/` | `IsPlatformOperationsManager` — نقل ذرّي واحد إلى موظف آخر (`reason` إلزامي)؛ يبقي `predecessor` والتاريخ، ولا يمسّ `CustomerAcquisition` |
| POST | `/api/platform/ops/engagements/{id}/suspend/` · `/{id}/resume/` · `/{id}/revoke/` | `IsPlatformOperationsManager` — دورة حياة الارتباط الصريحة |
| GET | `/api/platform/ops/engagements/candidates/` | `IsPlatformOperationsManager` — موظفو المنصة النشطون مع حِملهم الحالي وطاقتهم المتبقية وأثر إسناد هذه الشركة عليهم (`?company=` إلزامي) |
| GET · POST | `/api/platform/ops/acquisition/` | `IsPlatformOperationsManager` — من جلب هذه الشركة كعميل (`?company=` للقراءة)؛ صفٌّ واحدٌ لكل شركة، **مستقلٌّ عمّن يخدمها الآن** (210-B) |
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
- `inventory.fifo` — `pending_provisional_layers` لبند فحص الصحة الآلي «طبقات تكلفة مخزون مؤقتة» (210-B)؛ قراءة صرفة بلا أي كتابة.

**يعتمد عليه:** لا شيء حالياً؛ حارس العزل يمنع الاستيراد الوارد من التطبيقات
الأخرى، والتكامل يتم عبر مسارات وخدمات الوحدة في مراحلها اللاحقة.

## قواعد لا يجوز كسرها

- `PlatformEmployee` هوية صريحة؛ لا تُستنتج من `is_superuser` أو من دور داخل شركة.
- موظف العمليات لا يحصل على `IsPlatformAdmin`، ومدير العمليات وحده يستعمل الحارس الإداري.
- `ServiceSubscription` صف واحد لكل شركة، والاشتراك النشط هو بوابة الإسناد الوحيدة.
- **`trial` حالة صريحة منفصلة عن `active`** (`platform_ops/models.py` (`ServiceSubscription.Status`))؛ `INACTIVE` يعني بلا صفّ اشتراك أصلاً لا حالة مخزَّنة. الأهلية محورٌ واحد (`platform_ops/services.py` (`is_service_active` · `is_service_subscription_eligible` · `eligible_service_tenant_ids`)): `active` دائماً مؤهّلة، و`trial` مؤهّلة ما دام `now < trial_ends_at`، و`suspended`/`cancelled` غير مؤهلتين أبداً. بطاقات مركز القيادة وارتباطات الموظف وشريط التدخل وقائمة أوامر العمل (`WorkOrderViewSet`) وصحة الشركة (`CompanyHealthView`) لا تستعلم إلا الشركات المؤهلة في SQL — للمدير والموظف معاً، فالتجربة المنتهية تُبقي ارتباطها نشطاً لكنها تخرج من هذه الأسطح (404 على الصحة). وكل موضع تشغيلي آخر يمر بهذا المحور لا بمقارنة `status == ACTIVE` مباشرة.
- **تجربة واحدة مدى حياة الشركة**: `start_service_trial` يرفض أي شركة لها صفّ اشتراك سابق (`trial_already_used`/`subscription_already_exists`)، و`activate_paid_subscription` (من لا شيء أو تجربة أو ملغى) لا يمنح تجربة ثانية أبداً ولا يعيد ضبط نافذة تجربة محفوظة.
- **الاستئناف يعيد الحالة السابقة لا `active` دائماً**: `suspend_service_subscription` يحفظ `pre_suspension_status` قبل التعليق (من `trial`/`active` فقط)، و`resume_service_subscription` يعيده ولا يُحيي اشتراكاً `cancelled` إطلاقاً.
- **والاستئناف يعيد الارتباطات التي علّقها ذلك التعليق وحدها**: التعليق يسجّل `suspended_engagement_ids` في حدثه، والاستئناف يمرّ عليها بـ`resume_engagement` فقط — ما علّقه مديرٌ يدوياً قبله يبقى معلَّقاً، وفشلُ ارتباطٍ بعينه (موظفٌ خرج من الخدمة) يُسجَّل في `failed_engagements` بحدث الاستئناف ولا يُسقط العملية. بلا هذا كانت الشركة تعود مؤهَّلةً وبلا أي ارتباط بصمت.
- **الإلغاء يُجدول افتراضياً لا يُنفَّذ فوراً**: `schedule_service_subscription_cancellation` يضبط `scheduled_cancellation_date` (آخر يوم خدمة شامل في نهاية الدورة أو التجربة، بلا prorating؛ وفي شهر التفعيل قبل بدء أول دورة مفوترة هو `period_start - 1` كي لا يُفوتر شهر كامل لم يُخدم) ويحفظ السبب؛ `immediate=True` يمر عبر `deactivate_service_subscription` فوراً. `apply_due_subscription_cancellations` idempotent وتعمل بعد تمرير الفوترة في `bill_service_subscriptions`، ولا تعمل في `--dry-run`، فلا تضيع فاتورة الدورة الأخيرة. **الإلغاء المجدول لا يُطبَّق إلا بتشغيل `bill_service_subscriptions` الشهري، وخطأ نطاق في صف واحد يُسجَّل في `failed` ولا يوقف الدفعة، ولا يُطبَّق على اشتراك نشط قبل فوترة الدورة التي تضم آخر يوم خدمة (`period_start <= scheduled_cancellation_date` ⇒ مؤجَّل ويُبلَّغ به) كي لا يُسقط تشغيلٌ محصور أو فاشل فاتورتَها** — تواريخه نهايات دورات فتكفيه جولة شهرية، والتجربة المنتهية غير مؤهلة أصلاً قبل تطبيق إلغائها.
- **كل انتقال اشتراك يكتب `ServiceSubscriptionEvent` واحداً** في نفس المعاملة الذرية، يحمل معرّف ارتباط (`X-Correlation-ID` أو `uuid4` مولَّد) — لا مسار تعديل أو حذف للحدث.
- كل كتابة اشتراك تمر بخدمات `start_service_trial` أو `activate_paid_subscription` أو `suspend_service_subscription` أو `resume_service_subscription` أو `schedule_service_subscription_cancellation` أو `withdraw_scheduled_service_cancellation` أو `update_subscription_commercial_settings`؛ لا CRUD عام، وعميل الفوترة لا يجوز أن يتبع الشركة المشتركة نفسها. **التفعيل المدفوع وتحويل التجربة يلزمهما `billing_customer`** (`billing_customer_required`) — لا اشتراك مدفوع لا يمكن فوترته؛ والتجربة وحدها تبدأ بلا عميل. تعديلات الإعدادات التجارية على اشتراك حي تسري على أول فوترة شهرية تصدر بعد الحفظ (الفوترة تقرأ قيم الصف لحظة التشغيل).
- **سياسة الاشتراك (`ServiceSubscriptionPolicy`) بلا تداخل نوافذ سريان لكل نطاق خطة، تحت قفل صريح على كل صفوفها** لا `UniqueConstraint(condition=…)` — MySQL تتجاهلها بصمت. `get_active_subscription_policy(at, plan)` يعيد نسخة الخطة السارية وإلا العامة. التفعيل يتطلب `change_reason` غير فارغ ومحفوظ وتاريخ سريان غير ماضٍ (فوري افتراضياً): نسخة النطاق السابقة تُغلق نافذتها عند تاريخ الجديدة، وتُرفض الجديدة (`subscription_policy_overlap`، 409) إن سبق تاريخُها نسخةً مجدولة لنفس النطاق؛ ما انقضت نافذته يُعلَّم `retired` عند التفعيل التالي و`effective_state` يعكس الحقيقة بينهما. **التفعيل يلزمه صنف رسم شهري خدمي في شركة فوترة النسخة، وصنف تجاوز متى كان سعر التجاوز أكبر من صفر** — كي لا يُنشأ اشتراك لا يمكن فوترته. النسخة النشطة أو المنتهية لا تُعدَّل أبداً — `clone_subscription_policy_to_draft` ينسخها إلى مسودة جديدة. معرّف شركة فوترة غير صالح يرد 400 عبر `SubscriptionManagementError` لا 500. كل كتابة على السياسة تكتب `ServiceSubscriptionPolicyEvent` في نفس المعاملة بمعرّف الارتباط. رقم نسخة المسودة يُحسب بلا `select_for_update` (قفل مدى فارغ على MySQL = gap lock وتشابك 1213)؛ القيد الفريد على `version` يرد التزامن 409.
- **التسلسل على MySQL بقفل صف موجود**: `start_service_trial` و`activate_paid_subscription` يقفلان صف `Tenant` قبل صف الاشتراك (قفل صف اشتراك غير موجود = gap lock وتشابك)، و`activate_subscription_policy` يقفل كل صفوف السياسة مرتبة بالمفتاح (المسودة نفسها تضمن صفاً واحداً على الأقل). `IntegrityError` يبقى 409.
- **SLA لكل خطة مؤجل صراحةً إلى #210-C** (SLA أوامر العمل) — الخطة في 210-A نطاقُ نسخة سياسة يحدد أسعارها وصنفيها وأيام تجربتها، والفوترة شهرية وحدها. نطاق «موظف» لإعدادات التعويض يأتي مع مجموعته في #210-D.
- **أصناف الفوترة من لقطة الاشتراك لا من سطر الأمر**: بدء التجربة والتفعيل يلتقطان صنفَي نسخة السياسة، و`bill_service_subscriptions` يقرأ لكل اشتراك (`resolve_subscription_billing_products`) التجاوز الصريح `--fixed-fee-product-id`/`--overage-product-id` إن مُرِّر، ثم لقطة الاشتراك، ثم `PLATFORM_OPS_BILLING_*_PRODUCT_ID` للصفوف القديمة؛ ومن ينقصه صنف يُبلَّغ عنه بكود `billing_preflight` لا بخطأ تشغيل عام.
- **شروط اشتراك بعينه تُعدَّل استثناءً بسبب**: `update_subscription_commercial_settings` يرفض بلا `reason` متى تغيّر حقل، ويرفض الملغى، و`subscription_policy_version` يبقى مصدر اللقطة الأصلية والانحراف في حدث `settings_updated`. تحويل التجربة يُبقي خطتها ولقطتها (`plan_fixed_by_trial` عند طلب خطة أخرى)، وإعادة تفعيل الملغى تحفظ الشروط المستبدلة في `previous_terms` بحدث التفعيل. قيم نموذج السياسة الافتراضية (300/300/7) بذرة لمسودة جديدة فقط؛ القيم السارية تأتي دائماً من نسخة مفعّلة.
- الأسعار تُحفظ على الاشتراك كي تبقى الفوترة قابلة للحساب حتى لو تغيّر تعريف الباقة لاحقاً؛ التفعيل المدفوع أو إعادة التفعيل يبدأان أول الشهر الميلادي التالي بلا prorating، لذلك لا تُفوتر بقية شهر التفعيل وتُتخطى الدورة الأسبق بكود `subscription_not_yet_billable`. تحويل التجربة يحفظ لقطة التجربة، وإعادة التفعيل من `cancelled` تلتقط السياسة النشطة الجديدة.
- لا `require_module` ولا `get_tenant` على مسارات المنصة العابرة للشركات.
- أي كيان لاحق يخص شركة يحمل `tenant` ويُفلتر عليه؛ الاستثناءات الوحيدة بلا
  `tenant` هي `PlatformEmployee` و`JobPosting` و`JobApplicant` و`JobApplicantInvitation`
  و`PlatformRecruiter` و`ServiceSubscriptionPolicy` و`ServiceSubscriptionPolicyEvent` (افتراضيات
  منصة لا شركة)، و`SubscriptionBillingRecord` و`ServiceSubscriptionEvent` شركتهما مشتقة عبر
  `subscription.tenant` لا بحقل مباشر.
- فرادة الارتباط النشط لنفس (الموظف، الشركة) تُفرض تحت قفل `select_for_update` في الخدمة داخل `transaction.atomic` لأن MySQL تتجاهل القيود الشرطية.
- الإلغاء والتعليق يسحبان فقط العضوية التي أنشأها الارتباط (`created_membership=True`)، ولا يمسّان أي عضوية مسبقة للزبون.
- إيقاف أو تعليق اشتراك الخدمة يُعلّق الارتباطات النشطة ولا يحذفها.
- نقطة أوامر العمل مفلترة بخلاف أختيها: موظف المنصة يرى شركات ارتباطاته النشطة وحدها، والشركات تُشتق من `Engagement` لا من الطلب. ومدير المنصة وحده يرى كل الشركات — المؤهلة للخدمة منها فقط.
- كل تغيير حالة لأمر العمل يمر بـ`transition_work_order_status` وفق خريطة `WORK_ORDER_TRANSITIONS` وحدها — لا كتابة مباشرة على `status`.
- مغادرة موظف المنصة (`offboard_platform_employee`) عملية ذرية idempotent لا تفشل ولا تكرر الآثار عند تكرار الاستدعاء.
- قائمة الاستيراد البيضاء تتوسع فقط عند حاجة مرحلة موثقة، ولا تستورد الوحدة `employee_ops`؛ اتسعت في م٨ عمّا يسمّيه §١ من المواصفة بـ`sales.models` · `sales.serializers` · `sales.services` · `inventory.models`، لأن §٥ يفرض أن تمر فاتورة الخدمة بمسار المبيعات — قرار مسجّل.
- ترتيب الأقفال الصارم: `Tenant -> ServiceSubscriptionPolicy -> ServiceUnitCatalog -> IntegrationKey -> ServiceSubscription -> CompanyHealthCheck -> CompanyHealthCheckItem -> CustomerAcquisition -> PlatformEmployee -> Engagement -> WorkOrder -> WorkOrderDeliverable -> WorkOrderDocumentLink -> ServiceUsageEvent -> UserCompanyMembership -> DailyRating -> JobPosting -> JobApplicantInvitation -> JobApplicant` (محروسٌ ساكناً بـ`platform_ops/tests/test_engagement_lifecycle.py` (`LockOrderSourceGuardTest`) — `ServiceUnitCatalog` و`ServiceUsageEvent` أُضيفا في 210-C). **تركيب أقفالٍ عابرٌ لدالّتين لا يراه الحارس الساكن** (يفحص كل دالّة على حدة): `approve_work_order_deliverable_with_usage` تقفل `ServiceSubscription` صراحةً **قبل** استدعاء `review_work_order_deliverable` (تقفل `WorkOrderDeliverable`) — عكس الترتيب الظاهر في كل دالّة منفردة كان يُنتج تشابكاً حقيقياً على MySQL لولا هذا القفل المسبق المتعمَّد.
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
- **لا إسناد تشغيلي بلا أساس معتمد (210-B):** `assign_platform_employee` يرفض `kind=standard` بلا `CompanyHealthCheck` تأسيسي `approved` (`baseline_required`)؛ الاستثناء الوحيد `kind=onboarding` الموسوم بتاريخ انتهاء `onboarding_expires_at` (حدّه `MAX_ONBOARDING_DAYS`). لا تُخلط قط مع درجتي «صحة الخدمة»/«تعاون الزبون» المشتقّتين حيّاً في `CompanyHealthView` — الأولى سجلٌّ يُعتمد ويبقى تاريخه، والثانيتان لقطة لحظية.
- **الطاقة قبل الإسناد أو النقل:** حِمل الموظف مجموع وحدات حِمل شركات ارتباطاته النشطة (`employee_capacity_snapshot`)، ووحدة حمل الشركة من تعقيد أحدث أساس معتمد لها (`low=1`/`medium=2`/`high=3`، أو `medium` افتراضاً بلا أساس بعد). تجاوز `capacity_target` يُرفض (`capacity_exceeded`، 409) إلا بـ`capacity_override_reason` صريح يُحفظ على الصفّ. و`capacity_target` صفراً تعني **«لم تُضبط بعد» لا «طاقة صفر»** فلا تُفعِّل الرفض (`_would_exceed_capacity`) — هو افتراض النموذج ولا واجهة كتابة تضبطه بعد (`PlatformEmployeeViewSet` للقراءة فقط)، وهو معنى الصفر نفسه في حجم العيّنة وفي كشف الحمل الزائد؛ القراءة الحرفية كانت ترفض كل إسناد لكل موظف حقيقي.
- **الاعتماد يرفض بوضوح لا بصمت:** `approve_health_check` يرفض بلا `complexity` مقدَّر (`complexity_required`)، وبند إلزامي بلا `evidence_value` **و**`evidence_note` معاً (`evidence_missing` مع رموز البنود الناقصة). بعد الاعتماد: لا تعديل على الفحص ولا بنوده (`health_check_immutable`، 409).
- **النقل معاملة واحدة تُبقي التاريخ:** `transfer_engagement` يُغلق القديم عبر مسار الإلغاء الرسمي نفسه (`_execute_revoke` بقواعد العضوية ذاتها) ويفتح جديداً بـ`predecessor` يشير للقديم؛ `reason` إلزامي، ولا يمسّ `CustomerAcquisition` إطلاقاً — من خدم الشركة يتغيّر، من جلبها كعميل لا. ولا يُنقل إلا **ارتباط نشط**: المعلَّق يُرفض (`not_active`، 409) بدل أن يخرج منه ارتباطٌ نشطٌ بصمت، و`onboarding_expires_at` **يُورَّث كما هو ولا يُستأنف** — النقل تغيير موظف لا استثناء جديد من شرط الأساس المعتمد.
- **لا نسبة آلية لموظف:** `compare_health_baseline` قراءةٌ صرفة تُقارن حالة كل بند بين آخر فحصين تأسيسيين معتمدين بلا أي إشارة لمن أنشأ أو عدّل أو اعتمد في نتيجة المقارنة نفسها.
- **الشركة غير المؤهَّلة مستبعدة من الأصل:** `create_health_check_draft` يرفض تنشئة فحصٍ لشركة خارج `eligible_service_tenant_ids()` (`subscription_not_eligible`) — الأهلية محورٌ واحد كسائر عمليات المنصة، لا فحص منفصل.
- **حدث تدقيق موحّد واحد للتذكرة كلها:** كل فعل 210-B (إسناد/نقل/تعليق/استئناف/إلغاء/اعتماد فحص/تحويل بند لأمر عمل/تسجيل اكتساب) يكتب `PlatformOperationEvent` بفاعل (`SET_NULL`) ومعرّف ارتباط (`X-Correlation-ID` أو `uuid4` مولَّد) — نموذجٌ عامّ واحد بحقل `domain` لا نموذجٌ منفصل لكل نطاق، بخلاف نمط `ServiceSubscriptionEvent` المتخصّص في 210-A؛ قرارٌ مسجَّل لتبسيط التدقيق العابر للنطاقات الثلاثة.
- **والمسارات غير المباشرة تكتب الحدث نفسه:** الارتباط لا يُعلَّق أو يُلغى من واجهته وحدها — `deactivate_service_subscription` تعلّق كل ارتباطات الشركة و`offboard_platform_employee` تلغي كل ارتباطات الموظف، وكلتاهما تكتب حدث الارتباط بـ`details.source` (`subscription_deactivation` / `employee_offboarding`) وبفاعل العملية ومعرّف ارتباطها. بغيرها يبقى السجلّ «موحّداً» بالاسم وفيه ارتباطاتٌ تُعلَّق وتُلغى بلا أثر.
- لا نقاط تحفيزية (gamification) في لوحة عمليات المنصة.
- **لا وحدات قبل اعتماد المُسلَّم (210-C):** `generate_usage_events_for_deliverable` لا تُستدعى إلا من `approve_work_order_deliverable_with_usage`، ولا تُنتج أي `ServiceUsageEvent` إلا لروابط مستندات مُسلَّمٍ حالته `approved` فعلاً؛ ردٌّ أو تعليقٌ لا يحتسبان شيئاً.
- **إعادة استخدام الرابط لا إعادة إنشائه هي آلية منع الاحتساب المضاعف (210-C):** رفضٌ بتصنيف `employee_error` يعيد المُسلَّم لنفس `WorkOrderDocumentLink` (`document_link_ids` عند التسليم التالي)، فمفتاح idempotency (مشتقٌّ من `pk` الرابط) يمنع حدث استخدامٍ ثانياً — لا خصماً ثانياً من العميل ولا إنجازاً ثانياً للموظف. رفضٌ بتصنيف `customer_new_info` يُنشئ رابطاً **جديداً** عمداً فيُحتسب طلباً مستقلاً. الاصطلاح في سير العمل نفسه هو مصدر الحقيقة الوحيد، لا حقل علمٍ إضافي.
- **`consumed_quota` عدّادٌ متراكم لا مسقَط بالكامل من الدفتر (قيدٌ معروفٌ مقبول للـpilot):** المسار القديم من 210-B (`receive_channel_work_order`) ما زال يزيد العداد مباشرة بلا حدث دفتر خلفه — لم يُمَسّ في 210-C تفادياً لكسر `test_channel_intake.py`. فالعدّاد اليوم **مغذًّى من مصدرين** لا مُشتقٌّ حصراً من `SUM(ServiceUsageEvent)` كما قد يُفهم حرفياً من «projection» — إعادة النظر في هذا مؤجلة لمرحلة توحيد لاحقة.
- **الكسورُ لا تضيع: العدّاد يتحرّك بفرق مجموعَي الدفتر لا بتقريب كل حدثٍ منفرداً (210-C):** `units` رقمٌ عشريٌّ (`0.50` لفاتورة سطرٍ واحد بوزن `0.50`) و`consumed_quota` عددٌ صحيح. فلو قُرِّب كلُّ حدثٍ وحدَه لضاعت كلُّ كسورِ الأحداث الصغيرة (حدثان بنصف وحدة = صفر). لذا يحسب `_apply_usage_event_to_quota` مجموعَ الدفتر المحتسَب على العميل **قبل** الحدث و**بعده** (`_ledger_chargeable_total`، حيثُ العكسُ يُطرح والاستخدامُ يُجمع) ثم يزيد العدّادَ بفرق التقريبَين — فحدثان بنصف وحدة يُنتجان وحدةً كاملة، والعكسُ يُطرح من المجموع نفسِه بلا معالجةٍ منفصلة. و**التقريبُ نصفاً لأعلى** (`ROUND_HALF_UP`، اصطلاح الوحدات المعتمَد في 210-C والمُفوتَر عليه في `_calculate_subscription_charge`) يترتّب عليه أثرٌ مقصودٌ يُذكر صراحةً: عكسٌ **جزئيّ** يترك بقيّةً كسريّةً تُقرَأ وحدةً كاملة (0.50 باقيةً ⇒ العدّاد 1)، فالعودةُ إلى الصفر مضمونةٌ عند عكس الدفتر كلِّه لا عند كلّ خطوةٍ منه. تغييرُ هذا إلى `ROUND_FLOOR` قرارُ تسعيرٍ لا تنظيفُ كود — يغيّر المبالغ المفوترة على كلّ وحدةٍ جزئيّة — فيُترك لقرارٍ صريح.
- **علما الاحتساب مستقلان (210-C):** `chargeable_to_customer` و`creditable_to_employee` (`_classify_usage_flags`) — مستندٌ وصل عبر قناة (`source=channel`) يستهلك حصة العميل دوماً، لكنه لا يمنح الموظف إنجازاً إلا إن كان أمر العمل من نوع `review` بوزنٍ مستقل؛ مستندٌ من مصدر `staff`/`admin` يمنح الاثنين معاً.
- **لا تُفعَّل خدمةٌ بلا كتالوج وحداتٍ سارٍ (القصة ١٨ من #210):** `start_service_trial` و`activate_paid_subscription` كلتاهما تمرّان بـ`_require_active_service_unit_catalog` فتُرفضان بـ`service_unit_catalog_required` حين لا نسخةَ كتالوجٍ سارية. سببُه أنّ الاحتساب بلا صيغةٍ منشورةٍ سلفاً احتسابٌ غيرُ محدَّد: الخدمة تبدأ، والمستندات تُعتمد، ثم يُنشر كتالوجٌ لاحقاً فتُحتسب الوحدات بصيغةٍ لم تكن قائمةً وقت العمل.
- **مستندٌ احتُسب سلفاً لا يُعاد احتسابه إلا بطلبٍ صريح (210-C):** ربطُ مستندٍ له حدثُ استخدامٍ قائمٌ لنفس أمر العمل يُرفض بـ`document_already_charged` (409) إلا مع `recount_reason` مكتوب، وهذا السبب متاحٌ لمدير العمليات وحدَه (`manager_only`، 403) ويُحفظ على الرابط. فإعادةُ الاحتساب قرارٌ موثَّقٌ لا نقرةٌ عابرة.
- **كتالوج وحدات الخدمة لا يُعدَّل في مكانه بعد التفعيل (210-C):** كما `ServiceSubscriptionPolicy` تماماً؛ نسخة جديدة تُنشأ وتُستنسخ منها البنود عند الحاجة (`clone_service_unit_catalog_to_draft`)، وتفعيلها يُنهي نافذة السابقة عند تاريخ سريانها لا يحذفها ولا يستبدلها فوراً.
- **تعارضٌ متفائل على انتقال الحالة (210-C):** `expected_updated_at` اختياري في `/work-orders/{id}/transition/`؛ إن أُرسل ولم يطابق `updated_at` الحالي تُردّ 409 (`conflict_stale_version`) مع تمثيل الصفّ الحالي في `current` بدل الكتابة فوق تغييرٍ لم يره طالبه.
- **بوابة الكتابة على أمر العمل (210-C):** أفعال النقل/التعليق/ربط المستند/التسليم تتطلب أن يكون الطالب مسؤول أمر العمل (`assignee`) نفسه أو `IsPlatformOperationsManager`؛ زميلٌ آخر له ارتباطٌ بنفس الشركة لكنه ليس المسؤول يُرفض بـ403 (لا 404 — الفارق أن الصفّ داخل نطاق رؤيته أصلاً بخلاف شركة خارج ارتباطاته).

**قيودٌ معروفةٌ مقبولةٌ للإطلاق التجريبيّ (م٨)** — قرارٌ واعٍ لا سهو، يُعاد النظرُ فيه بعد الـpilot:

- **ربطُ عميل الفوترة محروسٌ من الشاشة:** تكتب شاشة السوبر أدمن `ServiceSubscription.billing_customer` عبر خدمة الإعدادات فقط، وتُرفض قيمة من شركة الاشتراك نفسها قبل الحفظ؛ وتبقى بوابة الفوترة `billing_preflight` الحارس النهائي قبل أي فاتورة.
- **العدّادُ بلا تاريخ:** `consumed_quota` يُحسب على الدورة الجارية لحظةَ القبول، فعمليّةٌ تُقبل بين `period_end` وتشغيل الأمر تُفوتَر على الدورة المنتهية.
  لذلك يُشغَّل `bill_service_subscriptions` صباحَ أوّل يومٍ من الشهر.
- **مسؤولُ التوظيف يرى رابطَ الدعوة الخامّ** لأنّه مَن يسلّمه للمرشّح؛ فيستطيع تقنيّاً قبولَها بنفسه. الحسابُ الناتج يظهر `PlatformEmployee`
  مرتبطاً بالمتقدّم (`hired_employee`) تحت أنظار السوبر أدمن، والدعوةُ تُبطل بالرفض أو بإصدار غيرها.

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `platform_ops/tests/test_service_layer.py` | صراحة هوية الموظف، صلاحيات المنصة، بوابة الاشتراك، فرادة صفه، وتسعيره |
| `platform_ops/tests/test_engagement_lifecycle.py` | دورة حياة الارتباط، حفظ عضوية الزبون، الاستئناف، تعليق الاشتراك، المغادرة، حارس ترتيب الأقفال الصارم |
| `platform_ops/tests/test_health_and_capacity.py` | فحص الصحة (مسودة/بنود آلية ويدوية/اعتماد ورفضه)، idempotency تحويل البند لأمر عمل، مقارنة الأساس بلا نسب لموظف، بوابة الأساس المعتمد للإسناد وطاقة الموظف والتجاوز بسبب، النقل الذرّي وتاريخه، اكتساب العميل المستقلّ، وعزل 403 على كل مسار جديد |
| `platform_ops/tests/test_health_assignment_frontend_contract.py` | عقد واجهة فحص الصحة والإسناد مقابل المسلسلات الحقيقية، وتسميات الحالات مطابقة `choices` الخادم |
| `platform_ops/tests/test_work_orders.py` | آلة حالات أمر العمل، إيقاف الأجل، استئنافه، لقطات السياسة والتسليم، إسناد المسؤول الواحد، عزل الشركة، وإلزامية مستوى ظهور التعليق |
| `platform_ops/tests/test_channel_intake.py` | استقبال القنوات، فرادة المرجع الخارجي (idempotency)، احتساب الفوترة، رفض الحقول الممنوعة، التحقق من المرفقات، الخانق، سقف الحجم بالبايتات، وعرض أعمدة الخيارات |
| `platform_ops/tests/test_performance_metrics.py` | كفاية العينة، إعادة توزيع الأوزان (سقوط محور ومحورين = 100%)، تجميد اللقطة والسياسة، Idempotency، عدم عد العرض عملاً، الدخول بعد الاعتماد، عدم خصم الإلغاء، رفض وسائط الشركات، وعرض أعمدة الخيارات |
| `platform_ops/tests/test_dashboard_and_notifications.py` | اللوحة التفاعلية، شريط التدخل (الشذوذات الأربعة)، عتبة الـ 15 دقيقة، الفلترة الخادمية للإشعارات، سجل النشاط العابر، ورفض وسائط الشركات بـ 400 |
| `platform_ops/tests/test_isolation_guard.py` | الاستيراد الصريح والديناميكي في الاتجاهين والقائمة البيضاء الصريحة |
| `platform_ops/tests/test_migration_graph.py` | وجود الهجرات وترتيب الاعتماديات |
| `platform_ops/tests/test_subscription_billing.py` | فوترة الاشتراكات الشهرية: الحساب وفصل السطور وترحيل الفواتير وعدم التكرار والذرية وعزل الشركات وسلامة الحقول، والدورة الصفرية بلا فاتورة، ورفض عميل من شركة الاشتراك، والمعاينة تساوي التشغيل و`CommandError` |
| `platform_ops/tests/test_subscription_management.py` | جدول انتقالات كامل (تجربة/تفعيل مدفوع/تعليق/استئناف/إلغاء مجدول أو فوري/سحب الجدولة)، تجربة واحدة مدى الحياة، انتهاء التجربة يُسقط الأهلية، رفض فوترة `trial`، تطبيق الإلغاء المجدول مرة واحدة idempotent، تعارض تفعيل متزامن 409، عزل عميل الفوترة وبحثه بشركة فوترة الاشتراك الملتقطة، عميل الفوترة إلزامي للتفعيل المدفوع، الإلغاء في شهر التفعيل قبل أول دورة، حدث واحد بمعرّف ارتباط لكل إجراء اشتراك وسياسة، قاعدة نسخة السياسة النشطة الواحدة ومعاينة الفروق بالمال نصاً، خروج التجربة المنتهية والملغى من أوامر العمل والصحة للدورين، صلاحيات 403 لغير السوبر أدمن (بمن فيهم موظف المنصة) على كل مسار، وعقد API الواجهة |
| `platform_ops/tests/test_daily_ratings_and_books.py` | العمل الفعلي شرطاً، انتهاء الرمز بـ410، التعديل الواحد، عدم حفظ الرمز الخام، القائمة البيضاء للرد العام، الخانق بـ429 مع ترويسة مزوَّرة، استبعاد العرض والدخول، عزل الشركة، اشتقاق الوكيل من `Engagement` حصراً، فصل الدرجتين، ومنع المُقيَّم من تعديل تقييمه أو حذفه |
| `platform_ops/tests/test_hiring_portal.py` | بوابة التوظيف والسطح الإداري (`PlatformHiringAdminSurfaceTests`): النماذج بلا `tenant`، فحص السيرة بالبايتات والبنية، التقديم العام، 410 للمغلق، تهشير رمز الدعوة، إنشاء الحساب عند القبول لا قبله، منع تحريك الحالة بكتابة مباشرة، رفض حذف إعلان له متقدمون، تمرير بايتات السيرة بلا تسليم رابط التخزين، عزل دور التوظيف عن كل مسارات المنصة، وجرد السطح العام بخانقه ومصادقته، ورفض المتقدم يبطل الدعوة، و`PATCH is_open` متجاهل، واسم السيرة العربي `filename*=`، وقوة كلمة المرور وسباق اسم المستخدم |
| `platform_ops/tests/test_hiring_frontend_contract.py` | حارس العقد بين واجهات التوظيف والفوترة بالـ frontend وحمولات الخادم الحقيقية للـ 13 واجهة، ومطابقة `APPLICANT_STATUS_OPTIONS`/`EMPLOYMENT_TYPE_OPTIONS` لـ`choices` الخادم |
| `tenants/tests/test_member_activity_log.py` | تسجيل إضافة عضو وتغيير دوره وحذفه في `ActivityLog` |
