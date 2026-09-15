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
| `platform_ops/models.py` (210-D) | سياسة تقييم الـpilot بنسخٍ مؤرَّخة (`PerformanceEvaluationPolicy` وحدث تدقيقها `PerformanceEvaluationPolicyEvent`) بالمحاور الأربعة الجديدة (`task_completion`/`quality_accuracy`/`sla_adherence`/`customer_satisfaction`، 40/30/20/10)، سياسة تعويض الموظف بنسخٍ مؤرَّخة (`EmployeeCompensationPolicy` وحدث تدقيقها `EmployeeCompensationPolicyEvent`)، حالات سطر المحفظة المشتركة (`WalletLineStatus`)، إغلاق مستحقّات الشهر (`MonthlyCompensationClose`)، وسطرا المحفظة المنفصلان (`EmployeeSalaryLine` و`AcquisitionCommissionLine`) — كلاهما `PENDING → ELIGIBLE → APPROVED → PAYABLE → PAID` أو `REVERSED`، بلا مسار حذف. `PerformanceSnapshot` يضيف `evaluation_policy` (`SET_NULL`، فارغ للقطات #207 القديمة) بجانب `policy_profile` القديم بلا تعديل عليه |
| `platform_ops/services.py` (210-D) | يوسّع محرّك #207 القائم — `redistribute_axis_weights` معمَّمة بـ`all_axes`/`default_weights` اختياريَّين بلا كسر التوقيع القديم — بدل بناء محرّك ثانٍ: دورة حياة سياسة التقييم (`create_performance_evaluation_policy_draft` · `clone_performance_evaluation_policy_to_draft` · `update_performance_evaluation_policy_draft` · `preview_performance_evaluation_policy` · `activate_performance_evaluation_policy` · `get_active_performance_evaluation_policy`)، دورة حياة سياسة التعويض بنفس الاصطلاح (`*_employee_compensation_policy_*`)، حساب أداء الـpilot الأربعة المحاور (`calculate_employee_pilot_performance`) والتقاط لقطتها (`capture_pilot_performance_snapshot`)، إغلاق مستحقّات الشهر idempotent (`close_compensation_month` · `preview_compensation_month_close`)، وأفعال سطر المحفظة (`transition_wallet_line` · `reverse_wallet_line` · `adjust_wallet_line` · `get_employee_wallet_summary`) |
| `frontend_v2/services/platformPilotApi.ts` (210-D) | عميل API لسياستَي الأداء والتعويض (مسودة/استنساخ/تعديل/معاينة/تفعيل)، إغلاق الشهر (معاينة وإغلاق)، سطور المحفظة (نقل/عكس/تسوية)، وأداء الموظف/محفظته |
| `frontend_v2/components/platform/PilotSettingsPanel.tsx` (210-D) | تبويب «سياسات الأداء والتعويض»: محرّر أوزان المحاور الأربعة (يمنع الحفظ أو التفعيل عند مجموعٍ لا يساوي 100%) وسياسة التعويض (راتب/دوام/عمولة اكتساب)، كلٌّ بمسودة ومعاينة أثر وتفعيل بسبب وتاريخ سريان |
| `frontend_v2/components/platform/CompensationMonthClosePanel.tsx` (210-D) | تبويب «إغلاق الشهر»: معاينةٌ بلا كتابة تُظهر التسليمات المعلَّقة المانعة (`blockers`) ومهلة المراجعة، ثم إغلاقٌ idempotent — تكراره لا يكرّر سطراً |
| `frontend_v2/components/platform/EmployeeWalletPanel.tsx` (210-D) | تبويب «محفظة الموظف»: المؤكَّد/المعلَّق وسبب التعليق لكل سطر، سطور الراتب والعمولة منفصلة، أفعال نقل/عكس/تسوية، وتفصيل محاور تقييم الموظف (البسط/المقام/الوزن/النتيجة/المساهمة/الاستبعادات) |
| `frontend_v2/components/platform-hiring/` | شاشة التوظيف المنصي وتبويباتها (الوظائف، المتقدمون، مسؤولو التوظيف، **واجتماعات المتقدّمين** بعرضَيها: قائمةٌ و**شبكةُ حضور** — ولوحة تفاصيل المتقدم) وصفحتا التقديم العام وقبول الدعوة |
| `frontend_v2/components/platform-hiring/ApplicantAttendanceMatrix.tsx` (#213-ج) | شبكةُ الحضور: صفٌّ لكلّ شخصٍ بحالته، وعمودٌ لكلّ اجتماع، وأيقونةُ الحالة بخريطةٍ **شاملةٍ على النوع** (`Record<ApplicantAttendanceStatus, …>`) لا سلسلةِ `if` بنصوصٍ حرّة؛ بحثٌ محلّيٌّ بـ`filterPlatformApplicants` المشتركة، ومدىً من/إلى يُطبَّق بزرّ «تحديث»، وتصديرٌ CSV معطَّلٌ **بتفسيرٍ مكتوب** حتى يُطبَّق المدى |
| `frontend_v2/components/platform/StaffLoginPage.tsx` · `components/platform/staff/` | بابُ دخول فريق المنصّة على `/staff` وقشرتُه المستقلّة على `/staff/*` (212-A): لا تمرّ بقشرة الشركة، وتعرض فقط لوحة الموظف وأوامره وشركاته واجتماعاته وأدائه وملفه الشخصي بعد حسم صلاحية موظف المنصّة أو مديرها. وقرارُ البوّابة دالّتان خالصتان في `frontend_v2/utils/staffAccess.ts` (`capabilitiesPending` · `staffGate`) لا شرطٌ داخلَ المكوّن: **الجوابُ الفارغُ قبل السؤال ليس رفضاً** (212-L0). |
| `frontend_v2/components/platform/BillingRecordsScreen.tsx` | شاشة سياسة اشتراك الـpilot (`SubscriptionPolicyPanel`) ونظرة عامة على الاشتراكات (`SubscriptionsPanel`) للقراءة، مع نافذة سجلات الفوترة للقراءة فقط والبحث المحلي وصف المجموع بالسنتات — التفعيل والانتقالات على بطاقة الشركة |
| `frontend_v2/components/platform/ServiceSubscriptionSection.tsx` | بطاقة خدمة الإدخال داخل `PlatformCompanyPanel.tsx`: الحالة وتبقّي التجربة والأفعال المسموحة لكل حالة وعميل الفوترة وسجل الأحداث |
| `frontend_v2/components/platform/CompanyHealthCheckSection.tsx` | قسم «صحة الدفاتر والتشغيل» داخل `PlatformCompanyPanel.tsx` — دورة حياة الفحص (مسودة/بنودها/اعتماد) ومقارنة الأساس، منفصلٌ بصرياً ونصّياً عن `CompanyHealthPanel.tsx` (210-B) |
| `frontend_v2/components/platform/EngagementAssignmentSection.tsx` | قسم «الإسناد والطاقة» داخل `PlatformCompanyPanel.tsx` — الموظف الحالي وسجل النقل والتعليق والإلغاء، ومربّع اكتساب العميل المستقلّ (210-B) |
| `frontend_v2/utils/platformHealthAssignment.ts` · `.test.ts` | دوال نصية خالصة لفحص الصحة والإسناد: تسميات الحالات، نقص الدليل الإلزامي قبل الاعتماد، تبقّي مهلة onboarding، صياغة الحمل/الطاقة، والأفعال المسموحة لكل حالة ارتباط — بوابة `node --test` (210-B) |
| `frontend_v2/components/platform/WorkOrdersPanel.tsx` (210-C، ووصلُ الإسناد/الأولوية 210-E) | تبويب «أوامر العمل» داخل `PlatformOpsDashboard.tsx` وداخل `PlatformEmployeeWorkspace.tsx` (210-E): طابور الموظف، تفصيل أمر العمل (نقل الحالة، ربط مستند، تسليم عمل، تعليقات)، ومراجعة المُسلَّمات (اعتماد/ردٌّ بسببٍ وتصنيف) **لمدير العمليات وحدَه** (212-Q2 — الخادمُ يردّ `manager_only`، واللوحةُ نفسُها تُركَّب في قشرة الموظّف: فبلا الشرط كان صاحبُ المُسلَّم يرى الحكمَ على عملِه؛ وحالةُ تسليمه تبقى مقروءةً له في الشارة) — يُضمَّن بتبويب محلّي بلا لمس `App.tsx` الممنوع. منذ 210-E: ضابطُ «الإسناد والأولوية» (`assignWorkOrder`/`changeWorkOrderPriority`) يظهر لمدير العمليات وحده (`usePlatformStaffCapabilities().is_platform_admin`) — كانا عميلَي API بلا مستدعٍ |
| `frontend_v2/components/platform/ServiceUnitCatalogPanel.tsx` (210-C، وتصحيحُ الاختيار الافتراضي 210-E) | تبويب «كتالوج وحدات الخدمة»: نسخ الكتالوج، تحرير بنوده لكل نوع مستند، وتفعيله بسبب وتاريخ سريان. منذ 210-E: التحميلُ الأوّل يفتح على النسخة **السارية فعلاً** (`getActiveServiceUnitCatalog()`، كانت بلا مستدعٍ) لا أحدثَ رقم إصدارٍ فحسب — قبلها كانت مسودةٌ أجدد تُعرض افتراضياً بدل النسخة التي تُحاسِب عليها الفواتير الآن |
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
| `platform_ops/tests/test_applicant_meetings.py` | اجتماعاتُ المتقدّمين (212-S1): نافذةُ الاجتماع على القاعدة وفي الخدمة معاً، وهويّةُ الحاضر الواحدة (لا الاثنان ولا لا شيء)، ومنعُ تكراره، ومنعُ إضافة من وُظِّف **لحظةَ الإضافة وحدَها** (فالفحصُ الرجعيُّ يمحو تاريخاً)، واستقلالُ الملاحظة عن الحضور، و«مدعوّ» افتراضاً لا «غائب»، ومنعُ الكتابة على حاضرِ اجتماعٍ آخر بمعرّفٍ مخمَّن، وعدمُ تسريب `cv_url` من الباب الجديد. وحرّاسٌ ساكنةٌ على ما لا يقرؤه `tsc`: نافذةُ الاجتماع تُحوَّل قبل أن تُقارَن (طرفٌ نصٌّ من الشبكة وطرفٌ `datetime` من الصفّ ⇒ خمسمئة)، ومنتقي المتقدّمين يخفي **الحالةَ نفسَها** التي ترفضها `add_meeting_attendee` |
| `platform_ops/tests/test_hiring_frontend_contract.py` | حارس العقد بين واجهات التوظيف والفوترة بالـ frontend وحمولات الخادم الحقيقية للـ 15 واجهة، ومطابقة `APPLICANT_STATUS_OPTIONS`/`EMPLOYMENT_TYPE_OPTIONS` لـ`choices` الخادم |
| `platform_ops/tests/test_task_file.py` (#213-ب) | ملفُّ المهمّة: الإجباريّةُ تُولَد مقبولةً · دورُ المرفق يُحرَس في القاعدة لا في بايثون وحدَها · التنزيلُ مقصورٌ على مُسنَدٍ أو مدير · التسليمُ يحمل ملفّاتِ صاحبِه هو · الخيطُ يُرشَّح لكلّ قارئٍ على حدة · لوحُ المدير ثلاثةُ استعلاماتٍ لا استعلامٌ لكلّ موظّف |
| `platform_ops/tests/test_attendance_matrix.py` (#213-ج) | شبكةُ حضور المتقدّمين: شكلُ المصفوفة · النافذةُ وحدُّها الأقصى وتاريخٌ خبيثٌ يُردّ ٤٠٠ لا ٥٠٠ · ميزانيّةُ الاستعلامات · التصديرُ CSV · البابُ ومن يملكه · **وأنّ الشبكةَ تُبنى في الخدمة وحدَها** فلا نسخةَ ثانيةٌ في الـview تتباعد عنها |
| `platform_ops/public_hiring/` | **كل كود `AllowAny` للتوظيف في حزمة واحدة** ليراجعها الأمن دفعة واحدة: `views.py` (خمس نقاط عامة بخانق `ClientIpScopedThrottle` ومصادقة معلنة صراحة)، و`cv_validation.py` (سقف 5 م.ب وفحص النوع والبنية **بالبايتات**)، و`serializers.py` (بلا `cv_url` بأي حال)، و`urls.py` تحت `/api/careers/`، و`urls_page.py` (#214-أ) لصفحة الإعلان المُصيَّرة من الخادم — مركَّبةٌ **مرّتين** في `core/urls.py` |
| `platform_ops/templates/platform_ops/careers/` (#214-أ) | قوالبُ صفحة الإعلان العامّة: `base.html` (غلافٌ بلا Tailwind وبلا حزمة Vite — **ثاني استثناءٍ موثَّقٍ من «Tailwind فقط» بعد `docshare`**، ونطاقُ تلك القاعدة `frontend_v2/`)، و`job.html` (وسومُ المعاينة + `JobPosting` JSON-LD)، و`notice.html` (410/404 **بلا وسومِ معاينة**: رابطٌ ميّتٌ لا يحمل بطاقةَ وظيفةٍ لا وجودَ لها) |
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
| `frontend_v2/components/platform/PlatformEmployeeWorkspace.tsx` (210-E) | مساحةُ موظّف عمليات المنصة — أكبرُ بابٍ ميّتٍ في المواصفة: طبقةُ الصلاحيّات (`IsPlatformOperationsStaff`/`is_platform_employee`) جاهزةٌ منذ #207 ولا شاشة لها. تُفرّق `loading` (لم يُحسم بعد) عن `forbidden` (الجوابُ لا) عبر `usePlatformStaffCapabilitiesState` تفادياً لوميض «ممنوع» على موظّفٍ حقيقيّ في أوّل رسم. تبويبان: طابوري (`WorkOrdersPanel` نفسُها) ومحفظتي وتقييمي (`EmployeeSelfWalletCard`)، وجرسُ الإشعارات مُركَّبٌ هنا (القصة ٤٨) لا في لوحة السوبر أدمن وحدها. مسجَّلةٌ كاملةً: `Sidebar.tsx` (المدخل) و`types/common.ts` (`AppView`) و`layout/Breadcrumb.tsx` (التسمية)، وفي `App.tsx` سطرُ `lazyPage` ومدخلُ `VIEW_PATHS` و`case` المبدّل — **بلا حارس `isSuperAdmin` عمداً**، فجمهورُها موظّفٌ ليس سوبر أدمن والمكوّنُ نفسُه يحسم الصلاحيّة |
| `frontend_v2/components/platform/EmployeeCompaniesPanel.tsx` (210-E) | تبويب «شركاتي» في مساحة الموظف (القصّتان ٣٩، ٤٠): لكلّ شركةِ ارتباطٍ نشطةٍ حصّتُها (مشمول/مستهلَك/متبقٍّ أو تجاوز) وبنودُ صحّتها **المُسنَدةُ إليه** من أحدث فحصٍ معتمد. المتبقّي لا يكون سالباً؛ التجاوزُ رقمٌ مستقلٌّ بتحذيرٍ صريح: «لا تَعِد العميلَ بعملٍ إضافيّ» — وهو نصُّ القصة ٤٠ |
| `frontend_v2/components/platform/PilotAxesTable.tsx` (210-E) | جدولُ محاور الـpilot — **مصدرٌ واحد** لبطاقة الموظف الذاتيّة ولوحة المدير معاً (كان نسختين متطابقتين فأيُّ تعديلِ عمودٍ يُنتج جدولين متناقضين). يعرض `weight_original_pct` بصيغة «الأصلي ← الفعلي»، و`raw_percent` فائضاً فوق الطاقة تحت الدرجة المقصوصة، و`uncatalogued_document_links` تحذيراً |
| `frontend_v2/services/platformEmployeeSpaceApi.ts` (210-E) | `getMyPlatformEmployeeProfile(currentUserId)` — الصفُّ **المطابقُ لهويّة المستخدم الحاليّ** من `GET /employees/`. ولا يُؤخذ أوّلُ صفٍّ: `PlatformEmployeeViewSet.get_queryset` يضيّق على `user=request.user` لغيرِ المدير وحدَه، أمّا مديرُ العمليات فيعود له كلُّ الموظفين — فأخذُ الأوّل يعني قراءةَ محفظةِ زميلٍ عشوائيٍّ تحت عنوان «محفظتي». النقطةُ كانت بلا مستدعٍ إطلاقاً قبل 210-E. منذ 210-F: `listPerformanceReviewRequestsForManager`/`resolvePerformanceReviewRequest` — الخادمُ نفسُه (`PerformanceReviewRequestViewSet`) يفرّق الجمهورَ بـ`get_queryset`، وكانت نقطةُ `{pk}/resolve/` بلا مستدعٍ إطلاقاً فلا شاشةَ لمدير العمليات يردّ منها على اعتراض موظّف |
| `frontend_v2/components/platform/PerformanceReviewRequestsPanel.tsx` (210-F) | تبويبُ «اعتراضات الأداء» داخل `PlatformOpsDashboard.tsx`: يسرد اعتراضات الموظّفين (القصة ٤٤) ويردّ عليها مديرُ العمليات قبولاً أو رفضاً بردٍّ مكتوبٍ إلزاميّ في الحالتين (`accepted: boolean` مطابقةً حرفيّاً لـ`ResolvePerformanceReviewSerializer` الخادميّ — لا حقل `status`) |
| `frontend_v2/components/platform/EmployeeSelfWalletCard.tsx` (210-E) | قراءةٌ ذاتيّةٌ للموظّف لمحفظته (`getEmployeeWallet`) وتفصيل محاور تقييمه (`getEmployeePilotPerformance`) — **بلا أفعالٍ إداريّة**: لا نقل حالة ولا عكس ولا تسوية، خلافاً لـ`EmployeeWalletPanel.tsx` الإداريّة التي تبقى لمدير العمليات وحده |
| `frontend_v2/components/platform/PlatformTasksAdminPanel.tsx` (212-E2) | تبويبُ «مهام الموظفين» في مركز القيادة: إنشاءُ مهمّةٍ بالجماهير الأربعة (**والحقولُ غيرُ المعنيّةِ لا تُعرَض**: منتقي موظّفٍ للفرديّ، ومتعدِّدٌ للمحدَّدين، وحدُّ مطالبين للمجمَع وحده) · جدولُ المهامّ بتقدّم إسناداتها · صندوقُ المراجعة بقراراتٍ ثلاثةٍ وحقلِ ملاحظاتٍ **إلزاميٍّ على اثنين منها قبل الضغط لا بعده** · وملاحظةٌ على موظّفٍ برؤيةٍ صريحة. **ويقرأ ما يكتب**: قائمةُ ملاحظات المدير (وفيها `MANAGER_ONLY` التي لا يراها غيرُه) وملاحظاتُ الموظّفين في مساحة عملهم — لوحةٌ تكتب ولا تقرأ تُخفي الملاحظةَ عن الجهة الوحيدة التي كُتبت لها. **و«جدولُ المهامّ» يُفتَح** (212-M1): صفٌّ يُنقَر ⇒ درجُ تفصيلٍ فيه المُسنَد إليهم **بأسمائهم** وحالةُ كلٍّ وتواريخُه، وتسليماتُه، وخيطُ ملاحظاتٍ يجمع كلامَ الإدارة وكلامَ الموظّف مرتَّبَين بالوقت، ونموذجُ كتابةِ ملاحظةٍ على المهمّة. وعمودُ «المُسنَد إليهم» يعرض **الأسماء** لا عدداً، ورأسُ «نطاق الإسناد» لا «الجمهور» (212-M2: كان العددُ بجانب «موظّفٌ واحد» يُقرأ اسمَ موظّف وليس اسماً) |
| `frontend_v2/components/platform/staff/tasks/StaffTasksPanel.tsx` (212-E2) | لوحةُ مهامِّ الموظّف داخل تبويب `tasks` في القشرة الداكنة (فوق `WorkOrdersPanel` لا بدلاً منه): قبولُ الإسناد، وتسليمُه بملاحظاتٍ **اختياريّةٍ كما في الخادم**، ومهامُّ المجمَع بعدِّ مطالبيها **من الحمولة** وزرٍّ يُقفَل عند بلوغ الحدّ، وملاحظاتُ مساحة العمل (عمومية أو على مهمّةٍ من إسناداته هو)، وملاحظاتُ المدير الظاهرةُ له. و**سجلُّ التسليمات مستقلٌّ عن الإسناد** لأنّ رفضَ مهمّةِ مجمَعٍ يحذف الإسناد: قرارٌ معروضٌ عليه وحدَه يختفي معه |
| `frontend_v2/services/platformTasksApi.ts` (212-E2) | عميلُ نقاط 212-E الثلاثَ عشرة عبر `restApi` |
| `frontend_v2/components/platform/IntegrationKeysPanel.tsx` (210-E) | شاشةُ القصة ٣١: إصدار/تدوير/إبطال مفاتيح القنوات — الظهرُ الخلفيُّ (`IntegrationKeyViewSet`) كان جاهزاً كاملاً بلا شاشة. السرُّ الخامّ يظهر في لافتةٍ مرّةً واحدةً مع نسخٍ للحافظة؛ فشلُ النسخ **لا** يُعيد كشفه، بل يعرض تنبيهاً بأنّ البديل الوحيد إصدارُ مفتاحٍ آخر (تدوير) يُبطل الحاليّ فوراً. مُركَّبةٌ كتبويبٍ جديدٍ داخل `PlatformOpsDashboard.tsx` |
| `frontend_v2/services/platformIntegrationKeysApi.ts` (210-E) | عميلُ `issue`/`rotate`/`revoke`/`list` لمفاتيح القنوات؛ `channel_display`/`status_display` أُضيفا إلى `IntegrationKeySerializer` (كانا غائبين لأن لا أحد استهلك الحمولة) |
| `frontend_v2/hooks/usePlatformStaffCapabilities.ts` | (210-E) يضيف `usePlatformStaffCapabilitiesState` بجانب الأصلية بلا تغيير توقيعها (السايدبار يستدعيها كما هي) — يعيد `{capabilities, loading}` صريحين لمن يحتاج التفريق بين «لم يُحسم» و«حُسم بالرفض» (شاشةٌ كاملة، لا زرٌّ يتحمّل الوميض) |

| `frontend_v2/components/platform/WorkspaceRoom.tsx` (211-I) | غرفةُ «مساحة العمل»: حلقةُ عشرة مقاعدَ حول طاولةٍ مركزيّةٍ بشاشةٍ، وثلاثةُ أضواءٍ (أخضرُ متّصل · أصفرُ في اجتماع · أحمرُ غير متّصل) **مع نصٍّ صريحٍ تحت كلّ ضوء** — اللونُ وحدَه لا يكفي لمن لا يميّز الأحمرَ من الأخضر. و**المقعدُ الفارغُ يبقى فارغاً**: نموذجُ المالك البصريُّ يُجلِس الغائبَ على كرسيّه بضوءٍ أحمر، وذلك يقرأ حضوراً لا وجودَ له. ومن زاد على عشرةٍ يُعرَض في شريطٍ تحت الطاولة لا يُخفى. والعمقُ بالتحجيم لا بدورانٍ ثلاثيّ الأبعاد: الدورانُ يُميل وجوهَ البطاقات فتصير الأسماءُ مائلةً لا تُقرأ، والغرضُ أن تُقرأ بلمحة. **وفوق كلّ وجهٍ رقاقةُ مجموعِ يومه** (212-N2، `PresenceClockChip`): الضوءُ يقول «الآن» ولا يقول «كم قعد اليوم» — وهو السؤالُ الذي وُضع العدّادُ له ويدخل جوابُه في التقييم |
| `frontend_v2/utils/roomPresence.ts` (211-I) | اشتقاقُ الحضور: **الاتّصالُ من `is_recently_active` الذي يحسبه الخادم** بعتبة ١٥ دقيقة — لا يُعاد اشتقاقُه من ساعة المتصفّح (ساعةُ جهازٍ مغلوطةٌ تُخرج نصفَ الفريق من الغرفة)؛ و**الاجتماعُ يغلب الاتّصال** حين يجتمعان وإلاّ اختفى الضوءُ الأصفرُ في الحالة التي وُجد لها. و`sortByPresence` ترتيبٌ ثابتٌ بين تحديثين فلا «تقفز» الوجوهُ حول الطاولة عند كلّ استقصاء، و`countPresent` تعدّ المجتمعَ حاضراً — هو في العمل لا خارجه |
| `frontend_v2/styles/index.css` (`.pf-room*`/`.pf-seat*`، 211-I) | هندسةُ الغرفة: مواضعُ المقاعد وعمقُها **أصنافٌ ثابتةٌ مولَّدة** لا `style` سطريّ (قاعدةُ المستودع Tailwind وحدَها)، وحدّا ارتفاعٍ (34rem/40rem) يمنعان تراكبَ البطاقات في اللوح الضيّق وابتلاعَ الشاشة العريضة. ودون 33.8rem من **عرض الحاوية** (`@container` لا `@media`: شريطٌ جانبيٌّ مفتوحٌ يقضم مئتي بكسل) تُستبدَل الحلقةُ بشبكةِ بطاقاتٍ تُظهر الجميع — الطاولةُ زينةٌ والأسماءُ وظيفة |

| `frontend_v2/services/platformMeetingsApi.ts` (211-G) | عميلُ النقاط العشر تحت `/api/platform/ops/meetings/`، وتسمياتُ حالتَي الاجتماع والحضور **مصدراً واحداً** لكلتا الشاشتين. والقراءةُ مضيَّقةٌ خادمياً حسب الجمهور فلا تُفلتر ثانيةً هنا. و`listActivePlatformEmployeesForInvite` تعيد استعمالَ `platform/ops/employees/` القائمة بلا نقطةٍ جديدة |
| `frontend_v2/components/platform/MeetingsPanel.tsx` (211-G) | شاشةُ المدير: إنشاءٌ (بتحقّقٍ فوريٍّ أنّ النهاية بعد البداية) وتعديلٌ وإلغاءٌ بتأكيدٍ ودعوةٌ ودفترُ حضورٍ يبتُّ في الأعذار **المعلَّقة وحدَها**. ومنتقي المدعوّين يقرأ دفترَ الحضور معه فيُعلّم المدعوَّ سلفاً ويعطّل مربّعَه — الخدمةُ idempotent فالدعوةُ المكرّرة لا تضرّ، لكنّ اختياراً على غير علمٍ يترك أحداً ظنّاً أنّه مدعوّ. ونموذجُ الإنشاء يُعاد فارغاً بعد كلّ نجاحٍ (مفتاحُ تركيب) فلا تُنشئ نقرةٌ ثانيةٌ اجتماعاً مكرَّراً |
| `frontend_v2/components/platform/MyMeetingsPanel.tsx` (211-G) | شاشةُ الموظّف: «تسجيل الدخول» يستدعي `check-in/` ثمّ يفتح `meeting_link` **من ردّ الخادم** لا من صفّ القائمة المحلّيّ، و«اعتذار» بسببٍ إلزاميّ. ونافذةُ الدخول **تلميحٌ لا قفل** |
| `frontend_v2/utils/meetingAttendanceTally.ts` (211-G) | عدُّ الدفتر بحالاته الخمس دالّةً خالصةً يفحصها `npm test` — منطقٌ يسكن `useMemo` داخل مكوّنٍ لا يراه اختبارٌ هنا إطلاقاً |
| `frontend_v2/services/platformEmployeeProfileApi.ts` (211-Q · 211-J) | بطاقةُ الموظّف (قراءةً وكتابةً ورفعَ صورة) وأداءُ المحاور الخمسة الرسميّة (#207) — **النقطتان الوحيدتان اللتان كانتا بلا عميلٍ إطلاقاً**؛ بقيّةُ تبويبات الدرج تستورد عملاءَها القائمين ولا تُكرَّر هنا |
| `frontend_v2/components/platform/EmployeeProfileDrawer.tsx` (211-J) | ملفُّ الموظّف الـ360: رأسُه بطاقتُه الشخصيّة، وتبويباتُه الأربعة (عام · الأداء · المحفظة · النشاط) **كلٌّ يحمّل بياناته عند فتحه لا قبله** — نداءٌ واحدٌ لتبويبٍ يُفتح لا خمسةٌ عند أوّل نقرة. ولا رقمَ يُشتقّ فيه: ما لا تُرجعه نقطةٌ لا يُعرَض. ويُفتح من نقرةٍ على وجه الموظّف في البطاقة أو على مقعده في الغرفة |
| `frontend_v2/components/platform/MyProfileCard.tsx` (211-Q) | بطاقةُ الموظّف في مساحته هو: **صورتُه ورقمُه يضبطهما بنفسه**، والمسمّى للعرض لا للتعديل. ولولاها لبقي إذنُ الخادم لصاحب الصفّ **باباً بلا طارق** — الدرجُ يُفتح من لوحة المدير وحدَها، فكانت صورةُ الموظّف لا يرفعها إلاّ مديرُه |
| `frontend_v2/components/platform/DashboardHeroStrip.tsx` (211-S) | شريطُ الأرقام العلويّ: مجموعُ أوامر العمل النشطة رقماً كبيراً، والمتأخّرةُ بطاقةَ تنبيهٍ **تُصبَغ حين تتجاوز الصفرَ وحدَه**، ودوناتُ «المتّصلون الآن N/M» بـSVG لا بمكتبة. و**لا رقمَ مالٍ فيه**: نموذجُ المالك يعرض «مبيعات اليوم» لأنّه رسمُ شركةِ زبون، وحمولةُ لوحة العمليّات لا تحمل مبيعاتٍ إطلاقاً |
| `frontend_v2/components/platform/TeamTargetBars.tsx` (211-S) | أشرطةُ استهلاك طاقة الإسناد (`active_work_orders_count / capacity_target`) — النسبةُ الوحيدةُ في الحمولة ببسطٍ ومقامٍ متجانسَين. و`capacity_target == 0` تعني «لم تُضبط» لا «طاقةَ صفر» فلا شريطَ ولا قسمة؛ وفوق المئة يُقصّ **عرضُ الشريط** ويبقى **الرقمُ** يعرض الفائض بلونٍ تحذيريّ — موظّفٌ فوق طاقته هو الخبرُ نفسُه |

### بابُ الموظّف الواحد (212-I)

مدخلُ «مساحتي — عمليات المنصة» في `Sidebar.tsx` يحمّل `/staff/home` بجلسة الموظف
المستعادة؛ فـ`/staff` هو بابُ الموظف الوحيد إلى القشرة الداكنة الكاملة.

ومنذ 212-Q3 **البابُ نفسُه يُفتَح للمالك معايناً**: القشرةُ كانت تقبله أصلاً
(`staffGate` يمرّر `is_platform_admin`) والناقصُ الرابطُ وحدَه، فكان مالكُ النظام
لا يرى ما يراه موظّفوه إلّا بكتابة العنوان بيده. ومَن يُفتَح له وبأيّ اسمٍ قرارُ
`frontend_v2/utils/staffDoor.ts` (`staffDoorFor`) لا شرطٌ في الشريط: «مساحتي —
عمليات المنصة» لموظّف المنصّة، و«معاينة مساحة الموظّف» للمالك. والاسمان يفترقان
عمداً — حسابٌ بلا صفِّ `PlatformEmployee` تظهر لوحاتُه الشخصيّة فارغةً بحقّ،
فيقرؤها صاحبُها عطباً إن قيل له «مساحتي». ولذلك تعلن القشرةُ المعاينةَ لافتةً
(`isStaffPreview`) تقول إنّ الفراغَ ليس عطباً. والقاعدتان خالصتان يختبرهما
`npm test`، ويحرس التركيبَ `platform_ops/tests/test_employee_door.py`. يبقى
`PlatformEmployeeWorkspace.tsx` ومساره العميق للتوافق لأن `App.tsx` ما زال يستورده،
لا كمسار استعمالٍ من الشريط الجانبي.

والانتقالُ كاملٌ (`window.location.assign`) لأنّ الوجهةَ خارجُ موجّهِ التطبيق؛
والجلسةُ تنجو لأنّ `AuthContext` يقرأ `token` و`userId` من `localStorage` عند
الإقلاع ثمّ ينادي `applyUserSession` — فمُوفِّرُ `/staff` المستقلُّ يعيد بناءَ
المستخدم بلا دخولٍ ثانٍ.

**ولأنّ البابَ كاملُ الانتقال، لزم مخرجٌ صريح:** القشرةُ لا تحمل شريطَ التطبيق
بقرارٍ يحرسه `test_the_staff_shell_never_imports_the_company_sidebar`، فبلا زرٍّ
يعود كانت ضغطةٌ واحدةٌ تُخرج الموظّفَ من نظام شركته بلا رجعةٍ إلّا بكتابة
العنوان. زرُّ «نظام الشركة» في ذيل `StaffSidebar.tsx` هو ذلك المخرج، ويحرسه
`test_the_staff_shell_offers_a_way_back_to_the_company_system` **على القشرة
كلِّها** لا على ملفٍّ بعينه: نقلُه إلى الترويسة إصلاحٌ مقبول، وحذفُه ليس كذلك.

## النماذج الحالية

| Model | الحقول والقواعد المهمة |
|---|---|
| `PlatformEmployee` | `user` واحد لواحد، `specialty`، `capacity_target`، و(210-ز) `monthly_units_target`، وحالة `active/on_leave/offboarded`. بلا `tenant` عمداً لأنه موظف للمنصة لا لشركة. **والحقلان مستهدفان على سُلَّمين مختلفين لا رقم واحد** — انظر القاعدة أدناه. و(211-Q) `photo_url` و`phone` و`job_title` — بطاقةٌ شخصيّةٌ للعرض؛ و`job_title` **منفصلٌ عن `specialty` عمداً** لأنّ الثاني مفتاحُ سياسةِ تقييم. |
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
| `PerformanceReviewRequest` (210-E) | اعتراضُ موظّفٍ على نتيجةِ شهرٍ بسببٍ مكتوب (القصة ٤٤). محورٌ بعينه أو فارغٌ للنتيجة المركّبة. **ولا يمسّ الدرجةَ**: صفُّ اعتراضٍ يفتح مساراً بشريّاً يصحّح فيه المديرُ بيانةً أو تصنيفاً عند المصدر ثمّ تُعاد اللقطة — ولو رفع الدرجةَ لصار باباً خلفيّاً يلتفّ على الحساب من الأعمال. حالات: `open → accepted\|rejected`، ولا حذفَ لصفّ. طلبٌ مفتوحٌ واحدٌ لكلّ (موظّف، فترة، محور) بحارسٍ في الخدمة لا بقيدٍ شرطيٍّ تتجاهله MySQL |
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
| `PerformanceSnapshot` | لقطة أداء شهرية لموظف المنصة لكل `(employee, period_year, period_month)` بفرادة غير مشروطة. تحفظ نسخة مجمدة من السياسة والأوزان (`policy_snapshot`) والمقاييس الستة والمحاور، والتقاطها دالة خدمة idempotent لا تكرر الصفوف ولا تضاعف الآثار. (210-D) تضيف `evaluation_policy` (`SET_NULL`، فارغة للقطات #207 القديمة، مملوءة للقطات الـpilot الأربعة المحاور) بجانب `policy_profile` القديم دون أي تعديل عليه — التوسيع بحقلٍ جديد لا بمحرّكٍ ثانٍ. |
| `PerformanceEvaluationPolicy` (210-D) | نسخة مؤرَّخة (`draft/active/retired`، نفس اصطلاح `ServiceSubscriptionPolicy`) من سياسة تقييم الـpilot **الثانية والمستقلّة** عن `PolicyProfile`: محاور جديدة `weights` (`task_completion` 40 · `quality_accuracy` 30 · `sla_adherence` 20 · `customer_satisfaction` 10)، `specialty` (فارغ = عامة)، `min_sample_size`، `review_grace_period_hours` (مهلة مراجعةٍ إعلامية قابلة للضبط لا مطمورة في الكود)، `activation_reason` إلزامي، ونافذة سريان. `effective_state()` من النافذة لا من `status` وحده. |
| `PerformanceEvaluationPolicyEvent` (210-D) | سجلّ تدقيق غير قابل للمحو (`PROTECT`) لكل كتابة على نسخ سياسة التقييم — نفس اصطلاح `ServiceSubscriptionPolicyEvent`. |
| `EmployeeCompensationPolicy` (210-D) | نسخة مؤرَّخة من إعدادات تعويض الموظف: `employee` اختياري (فارغ = عامة لكل الموظفين، محدَّد يغلب العامة)، `base_salary`، `daily_hours`، `weekly_days`، `acquisition_commission_amount`/`acquisition_commission_months` (100₪×3 شهور افتراضياً — **قابلة للتغيير من الواجهة بإصدارٍ وتاريخ سريان لا مطمورة في الكود**)، `accrual_day_of_month`. لا payroll قانوني — إعداداتٌ تشغيلية تغذّي المحفظة وحدها. |
| `EmployeeCompensationPolicyEvent` (210-D) | سجلّ تدقيق غير قابل للمحو لكل كتابة على نسخ سياسة التعويض — نفس الاصطلاح. |
| `WalletLineStatus` (210-D) | حالات سطر المحفظة المشتركة: `PENDING → ELIGIBLE → APPROVED → PAYABLE → PAID`، أو `REVERSED` — بلا مسار حذف لأي سطر مالي إطلاقاً. |
| `MonthlyCompensationClose` (210-D) | إغلاقُ مستحقّات شهرٍ واحدٍ لكلّ الموظفين دفعةً واحدة. فرادةٌ **غير مشروطة** على `(period_year, period_month)` — هي حارس الـidempotency الأول: محاولة إغلاقٍ ثانية تصطدم بالقيد فتعيد الصفّ القائم بلا إعادة تنفيذ حلقة الإغلاق. تحمل `performance_policy` الملتقطة وعدّادات (`employees_processed`/`snapshots_captured`/`salary_lines_created`/`commission_lines_created`). |
| `EmployeeSalaryLine` (210-D) | سطر راتبٍ شهريٍّ واحد لموظف — **منفصلٌ عمداً** عن سطور عمولة الاكتساب (نموذجان لا نموذجٌ واحدٌ بعمودٍ مميِّزٍ قابلٍ لأن يكون NULL، لأن قيد فرادةٍ مركّبٍ يضمّ عموداً NULL لا يمنع التكرار بدلالة SQL القياسية). فرادةٌ غير مشروطة على `(employee, period_year, period_month, sequence)`: `sequence=0` السطر الأصلي، وأي تصحيحٍ لاحق سطرُ تسويةٍ ظاهر بتسلسلٍ أعلى يشير إلى الأصل عبر `adjustment_of` — **لا حذف ولا تعديل على السطر الأصلي بعد إنشائه**. `pending_reason` يحمل سبب التعليق الصريح (مثل «الدفع غير مسجَّل»)، لا مبلغاً مؤكَّداً يظهر معلَّقاً بصمت. |
| `AcquisitionCommissionLine` (210-D) | سطر عمولة اكتسابٍ شهريّة لعميلٍ واحد — **مستقلٌّ عن موظّف الخدمة الحالي**، يُنسب دوماً إلى `acquisition.acquired_by` وقت الإنشاء (لا يتغيّر بنقل الخدمة لاحقاً؛ النقل لا يغيّره أبداً). فرادةٌ غير مشروطة على `(acquisition, period_year, period_month, sequence)` — العميل نفسه لا يُنتج سطرين لنفس الشهر مهما تكرّر تشغيل الإغلاق. `commission_month_index` (1..`acquisition_commission_months`)؛ بعد بلوغ الحدّ **لا يُنشأ سطرٌ جديد إطلاقاً** — لا حتى بمبلغ صفر — فالاستحقاق ينتهي نهائياً ولا يتجدد بتغيير موظف الخدمة. |
| `PlatformNotification` | إشعار منصي موجه لمستخدم (`recipient` إلزامي، `tenant` اختياري). مفلتر خادمياً حصراً فلا يرى المستخدم إلا إشعاراته. أنواع مغلقة (`sla_breach`, `low_score`, `quota_exceeded`). يدعم تعليم إشعار أو الكل كمقروء وعدّ غير المقروء. |
| `PlatformActivityLog` | سجل نشاط منصي عابر للشركات مستقل تماماً عن `ActivityLog` المستأجر؛ لأن `ActivityLog` لا يتسع لحدث بلا شركة وفهارسه تبدأ بالشركة. يحمل `employee` إلزامي، و`tenant` اختياري للأنشطة العامة، ومفهرس زمنياً `(employee, -created_at)` و`(-created_at)`. أفعال 210-C الثلاثة الجديدة (`work_order_assigned`/`work_order_priority_changed`/`document_linked`) تُسجَّل بفاعل العملية (المُسنِد/المُغيِّر/الرابط) لا بمُسنَد أمر العمل — نفس اصطلاح `work_order_transition`/`deliverable_submit`/`deliverable_review`/`comment_added` القائم من 210-B، ولا تُسجَّل إن تعذَّر ربط الفاعل بموظف منصة (مدير بلا ملف موظف مثلاً). |
| `DailyRating` | تقييم يوم عمل واحد بمفتاح منطقي `(tenant, employee, service_date)` بفرادة **غير مشروطة**. `service_date` حقل `DateField` صريح لا مشتق من وقت. `stars` من 1 إلى 5. `edited_once` يسمح بتعديل واحد لا غير. `source` يميز الرابط العام من داخل التطبيق. |
| `DailyRatingToken` | الرابط اليومي العام: `token_hash` مهشر SHA-256 وفريد، والرمز الخام لا يُحفظ في القاعدة أبداً ويظهر مرة واحدة عند التوليد. صالح 72 ساعة (`expires_at`)، وقابل للإبطال (`revoked_at`). |
| `SubscriptionBillingRecord` | سجل تدقيق الفوترة الشهرية لاشتراك الخدمة: يحفظ لقطة الحساب المالي للدورة (`monthly_fee`, `included_quota`, `consumed_quota`, `overage_units`, `overage_unit_price`, `overage_fee`, `total_amount`)، ورابط الفاتورة المرحلة (`SalesInvoice` ويقبل `NULL` للباقات الصفرية دون إصدار فاتورة مبيعات). قيد فرادة صريح على `(subscription, period_start, period_end)` يمنع التكرار نهائياً. |

| `JobPosting` | إعلان وظيفة منصي **بلا `tenant`**. `token` مفتاح الرابط العام (`token_urlsafe`) فريد ومفهرس. `specialty` هو **التخصص المنصي** الذي يُنسخ إلى `PlatformEmployee.specialty` عند قبول الدعوة، وطوله طول العمود الهدف (100) لا طول العنوان (200) — عنوان حر في عمود أقصر يخطئ على MySQL ويُبتر صامتاً على SQLite. |
| `JobApplicant` | متقدم على وظيفة **بلا `tenant`**. مدخل المجهول يُحجر بحالة `new` ولا يمس شيئاً. `cv_url` لا يُطبع في أي مُسلسِل عام ولا يعود للمتقدم. `reference_code` هو ما يراه المتقدم. |
| `JobApplicantInvitation` | دعوة المرشح المقبول: `token_hash` مهشر SHA-256 والرمز الخام لا يُحفظ. `is_consumed` تجمع المقبولة والملغاة **والمنتهية** معاً، فرابط منتهٍ لا يُقبل حتى لو قُصد مسار القبول مباشرة. |
| `ApplicantMeeting` | اجتماعُ مقابلةٍ مع متقدّمين **قبل التوظيف**، بلا `tenant`. **ليس `PlatformMeeting`**: ذاك اجتماعُ فريق المنصّة وصفُّ حضوره مفتاحُه `PlatformEmployee` وفيه دورةُ أعذارٍ تُغذّي محورَ «الانتظام» — وللمتقدّم لا حسابَ أصلاً ولا عقوبةَ تُعلَّق عليه، وذاك الصفُّ **بلا حقل ملاحظة** وهو الغرضُ كلُّه هنا. و`location` نصٌّ حرٌّ لا `URLField`: المقابلةُ الأولى تكون في مكتبٍ كما تكون على رابط. |
| `ApplicantMeetingAttendee` | حاضرٌ في اجتماعٍ يحمل **ملاحظتَه هو**. هويّةٌ من بابين وواحدٍ منهما لا غير: `applicant` (من رابط الوظيفة) **أو** `guest_name` نصّاً حرّاً — قيدُ قاعدةٍ يمنع الاثنين معاً ويمنع غيابَهما. والحضورُ **ثلاثُ حالاتٍ لا بوليان**: «مدعوّ» الافتراضُ، لأنّ بوليانَ `false` يقول «لم يحضر» عن اجتماعٍ لم يبدأ. وصفٌّ واحدٌ لكلّ شخصٍ في الاجتماع: قيدٌ **غيرُ مشروطٍ** على `(meeting, identity_key)` — و`identity_key` عمودٌ مُولَّدٌ مخزَّنٌ يحمل `a:<رقم المتقدّم>` أو `g:<اسم الضيف>`. كان القيدان شرطيّين وMySQL تتجاهل الفرادةَ المشروطة بصمت، فكانت الحراسةُ في بايثون وحدَها وهي تفحص ثمّ تكتب فتسابق نفسَها. والرسالةُ العربيّةُ باقيةٌ في `add_meeting_attendee`، و`IntegrityError` يُترجَم إليها فلا يرى خاسرُ السباق خمسمئة. |
| `PlatformRecruiter` | دور التوظيف المنصي. يفتح مسارَي التوظيف وحدهما ولا يمنح شيئاً من بقية المنصة، وإلغاء تنشيطه يغلقهما فوراً. |

`JobPosting` و`JobApplicant` و`JobApplicantInvitation` و`PlatformRecruiter` و`ApplicantMeeting` و`ApplicantMeetingAttendee` بلا
`tenant` بقرار #207 الموثق — استثناء محصور لأن الوظائف والمتقدمين للمنصة نفسها لا
لشركة زبون، ويحرسه `platform_ops/tests/test_isolation_guard.py`.

وبقرار #210-D: `PerformanceEvaluationPolicy` و`PerformanceEvaluationPolicyEvent`
و`EmployeeCompensationPolicy` و`EmployeeCompensationPolicyEvent` و`MonthlyCompensationClose`
بلا `tenant` لأنّها سياساتُ المنصّة تجاه موظّفيها وإغلاقُ مستحقّاتهم — لا تخصّ شركةَ
زبونٍ بحال؛ و`EmployeeSalaryLine` كذلك (راتبُ موظّف المنصّة لا شركة له)، أمّا
`AcquisitionCommissionLine` فشركتُه مشتقّةٌ عبر `acquisition.tenant` كحال
`ServiceSubscriptionEvent`. كلّها تحت `/api/platform/ops/` لمدير العمليات وحده،
ويحرسها `platform_ops/tests/test_isolation_guard.py`.

وبقرار #210-A: `ServiceSubscriptionPolicy` و`ServiceSubscriptionPolicyEvent` بلا
`tenant` لأن السياسة افتراضيات تجارية على مستوى المنصة كلها لا تخص شركة (و`billing_tenant`
فيها شركة المنصة المفوترة لا شركة زبون)، و`ServiceSubscriptionEvent` بلا حقل مباشر
لأن شركته مشتقة عبر `subscription.tenant` كحال `SubscriptionBillingRecord`. كلها تحت
`/api/platform/ops/` لمدير العمليات وحده.

و#211 م٢ أضافت `PlatformMeeting` و`PlatformMeetingAttendance` — بلا `tenant` للسبب نفسِه: الاجتماعُ ملكُ المنصّة وجمهورُه موظّفوها حصراً. و**دفترُ حضور الاجتماعات مستقلٌّ تماماً عن دفتر الدوام** في `hr/attendance.py` بقرار المالك («الاثنين وكلّ واحد لحال»)، فلا يقرأ أحدُهما الآخر.

## أهم نقاط الـAPI

| Method | المسار | الحارس |
|---|---|---|
| GET | `/api/platform/ops/dashboard/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (اللوحة التفاعلية وشريط التدخل) |
| GET | `/api/platform/ops/employees/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` (مفلتر لموظف المنصة على حسابه) — موصولةٌ منذ 210-E عبر `getMyPlatformEmployeeProfile()` كبوّابةِ تعريفِ الموظفِ بنفسه، لا بابَ مديرٍ ميّت |
| POST | `/api/platform/ops/employees/promote/` | `IsPlatformOperationsManager` بحارسٍ **داخل الفعل** (الـviewset نفسُه مفتوحٌ لموظّف المنصّة على صفّه) — «اجعله موظّفَ منصّة» (212-Q4): ترفع الدورَ على مستخدمٍ مسجَّلٍ بـ`identifier` (اسمٌ أو بريدٌ بلا حساسية حالة) **ولا تُنشئ حساباً**؛ بابُ إنشاء الحسابات هو `accept_job_invitation` وحدَه. والعائدُ من مغادرةٍ يعود إلى **صفّه نفسِه** (`OneToOne`) بتاريخه كلِّه فتردّ `200` و`created=false` بدل `201`، وتخصّصٌ فارغٌ في الطلب لا يمحو تخصّصَه القديم ومعه سياسةُ تقييمه. والنشطُ يُرفض بـ`409 already_platform_employee`، والحسابُ المعطَّل بـ400 |
| PATCH | `/api/platform/ops/employees/{id}/profile-card/` | `IsPlatformOperationsManager` للثلاثة، والموظّفُ نفسُه لصورته وهاتفه وحدَهما — و`job_title` يُردّ **403** `job_title_is_manager_only` حتى على صفّه هو |
| POST | `/api/platform/ops/employees/{id}/photo/` | نفسُ صلاحيّة `profile-card/`؛ رفعٌ عبر `core.media_views.upload_media_file` بـ`tenant=None` ثمّ حفظُ الرابط في الصفّ في العمليّة نفسِها |
| GET | `/api/platform/ops/employees/{id}/performance/` | `IsPlatformOperationsManager` أو الموظف نفسه (عزل عابر مشتق من الارتباطات) |
| GET | `/api/platform/ops/employees/{id}/activity/` | `IsPlatformOperationsManager` أو الموظف نفسه |
| GET | `/api/platform/ops/employees/my-companies/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` — **قراءةٌ ذاتيّة**: النطاقُ هو المستدعي نفسُه والشركاتُ تُشتقّ من ارتباطاته؛ لا تقبل معرّفَ موظّفٍ ولا معرّفَ شركة، ومحاولةُ تمرير شركةٍ تُرفض بـ400 (210-E، القصّتان ٣٩ و٤٠) |
| GET | `/api/platform/ops/performance-review-requests/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` — المديرُ يرى الكلَّ (وله `?employee=`)، والموظّفُ اعتراضاتِه وحدَه (210-E، القصة ٤٤) |
| POST | `/api/platform/ops/performance-review-requests/open/` | الموظّفُ على نتيجته هو — يُشتقّ من الجلسة لا من الحمولة؛ السببُ إلزاميّ، وطلبٌ مفتوحٌ واحدٌ لكلّ فترةٍ ومحور (210-E) |
| POST | `/api/platform/ops/performance-review-requests/{id}/resolve/` | `IsPlatformOperationsManager` وحدَه — قبولٌ أو رفضٌ بردٍّ مكتوبٍ في الحالتين؛ **ولا يغيّر الدرجةَ** (210-E) |
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
| GET | `/api/platform/ops/job-applicants/` | `IsPlatformRecruiter` — متابعة المتقدمين (قراءة وأفعال لا CRUD): الأفعال `transition-status` و`rate` و`invite` و`cv` (يمرر البايتات بلا تسليم رابط التخزين — عبر `core/media_views.py` (`stream_stored_asset`) المشتركة مع `employee_ops`، ففشلُ التخزين مصنَّفٌ ومسجَّل: 502 لرفضِ المزوّد · 404 لملفٍّ كُنس · 504 للمهلة). |
| GET | `/api/platform/ops/applicant-meetings/` | `IsPlatformRecruiter` — اجتماعاتُ المتقدّمين (212-S1): **قراءةٌ وأفعالٌ لا CRUD** كنظيرِها `job-applicants`، فالقواعدُ في الخدمات لا في مُسلسِلٍ قابلٍ للكتابة. الأفعال: `create` · `update` · `attendees` (إضافةُ حاضر) · `record` (الحضورُ والملاحظة) · `remove-attendee`. وكلُّ فعلٍ على الحاضرين يعيد **الاجتماعَ كاملاً** فتُحدَّث الشاشةُ بنداءٍ واحد. والحاضرُ يُبحَث داخلَ اجتماعه لا في الجدول كلِّه — معرّفٌ من اجتماعٍ آخر يردّ ٤٠٤. و`cv_url` لا يُطبَع هنا كما لا يُطبَع في أيّ مُسلسِل. **بادئتُه الثالثةُ مُعلَنةٌ في `PlatformRecruiterRouteScopeTest.HIRING_PREFIXES`** — وقد سقط الجردُ على مساراتها السبعة قبل إعلانها. |
| GET · POST · DELETE | `/api/platform/ops/recruiters/` | `IsPlatformOperationsManager` — الأفعال `GET`، و`POST` بحقل `identifier` (اسم مستخدم أو بريد، بلا حساسية حالة)، و`DELETE` تعطيل لا حذف؛ بلا `PUT`/`PATCH`. |
| GET | `/api/platform-staff/me/` | `IsAuthenticated` — قدرات المستخدم الحالي على المنصة (يجيب عن المستخدم نفسه، **خارج `/api/platform/` عمداً**). |
| GET | `/api/careers/jobs/{token}/` · POST `{token}/apply/` | `AllowAny` + `ClientIpScopedThrottle` — **كل كود `AllowAny` في حزمة `platform_ops/public_hiring/` وحدها** ليراجعه الأمن دفعة واحدة. السيرة ≤ 5 م.ب ونوعها يُفحصان **بالبايتات** لا بترويسة الرافع. |
| GET | `/api/careers/j/{token}/` · `/j/{token}` (#214-أ) | `AllowAny` + `ClientIpScopedThrottle` — **صفحةُ HTML لا JSON**، وهي **الرابطُ المنسوخ** (`JobPostingSerializer.public_url` ← `services.job_public_url`). سببُها أنّ الخادمَ الأمامي يخدم `frontend_v2/index.html` لكلّ ما ليس `/api/`، **وزاحفُ فيسبوك لا ينفّذ JavaScript** — فكان كلُّ إعلانٍ يُشارَك يظهر بعنوان المنصّة العامّ ووصفِها. تحمل `og:*` و`twitter:*` من حقول الإعلان و`JobPosting` JSON-LD لـ«وظائف جوجل». و**تُفهرَس عمداً** خلافاً لصفحة `docshare` (تلك مستنداتٌ خاصّةٌ تُوسَم `noindex`). مركَّبةٌ مرّتين كـ`docshare`: `/j/` القصيرُ يلزمه سطرٌ في الخادم الأمامي، و`/api/careers/j/` يعمل بلا لمسِه — والاختيارُ `PLATFORM_JOB_SHARE_PATH`. وزرُّ «قدّم» يقود إلى شاشة الـSPA (`services.job_apply_url` ← `PLATFORM_JOB_PUBLIC_PATH`). |
| GET | `/api/careers/invitations/{token}/` · POST `{token}/accept/` | `AllowAny` + `ClientIpScopedThrottle` — الحساب يُنشأ **عند قبول الدعوة لا قبلها**؛ ورمز مستهلك أو منتهٍ يرد 410 وغير موجود يرد 404. و(211-A) القبولُ **يردّ جلسةَ دخولٍ جاهزةً** (`token` + `user`) لا اسمَ المستخدم وحدَه. ومنذ #214-د يعرض `note` و`contact_phone` اللذين كتبهما المدير عند الإصدار — **ولا شيءَ من `JobApplicant.notes`**: تلك ملاحظاتُ الفرز الداخليّةُ عن الشخص نفسِه. |
| GET | `/api/platform/ops/work-orders/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` (تنقيب مفلتر بدون معاملات شركة) |
| POST | `/api/platform/ops/work-orders/create/` | `IsPlatformOperationsManager` — فتح أمر عمل يدوياً (210-C)؛ الشركة تُتحقق من أهليتها للخدمة |
| GET | `/api/platform/ops/work-orders/queue/` | موظف المنصة نفسه — طابوره الموحَّد عبر شركات ارتباطاته النشطة، مرتَّب بالأولوية ثم الأجل (210-C) |
| POST | `/api/platform/ops/work-orders/{id}/assign/` · `/{id}/change-priority/` | `IsPlatformOperationsManager` — إسناد مسؤول أو إعادة للطابور، وتعديل الأولوية (210-C)؛ موصولتان بضابطَي «الإسناد والأولوية» داخل `WorkOrdersPanel.tsx` (مدير العمليات فقط، `is_platform_admin`) منذ 210-E — كانتا بلا مستدعٍ رغم توثيقهما |
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
| GET | `/api/platform/ops/integration-keys/` | `IsPlatformOperationsManager` — موصولةٌ بـ`IntegrationKeysPanel.tsx` منذ 210-E (كانت بلا مستدعٍ) |
| POST | `/api/platform/ops/integration-keys/issue/` · `{id}/rotate/` · `{id}/revoke/` | `IsPlatformOperationsManager` — موصولةٌ منذ 210-E؛ السرُّ الخامّ يظهر مرّةً واحدةً في الردّ |
| GET | `/api/platform/ops/policy-profiles/` · `/{id}/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` — قراءة فقط؛ محرّر الأوزان يعمل على `PerformanceEvaluationPolicy` (محاور الـpilot الأربعة) منذ 210-D، و`PolicyProfile` بمحاوره الخمسة يبقى كما هو لمسار #207 بلا تعديل |
| GET | `/api/platform/ops/performance-snapshots/` | `IsPlatformOperationsManager` أو `IsPlatformOperationsStaff` (مفلتر للموظف على لقطاته) |
| POST | `/api/platform/ops/performance-snapshots/capture/` | `IsPlatformOperationsManager` |
| GET | `/api/platform/ops/employees/{id}/pilot-performance/` | `IsPlatformOperationsManager` أو الموظف نفسه — تفصيل محاور الـpilot الأربعة (`?year=`/`?month=`) (210-D) |
| GET | `/api/platform/ops/employees/{id}/wallet/` | `IsPlatformOperationsManager` أو الموظف نفسه — محفظته الشهرية بسطورها وأسباب تعليقها (`?year=`/`?month=`) (210-D) |
| GET | `/api/platform/ops/employees/{id}/pay-terms/` (#214-ج) | `IsPlatformOperationsManager` أو الموظف نفسه — **القاعدةُ** التي يُصرف بها راتبُه لا حصيلتُها، ومعها `pay_terms_note`: شرحٌ حرٌّ يكتبه المدير على **نسخة السياسة** (بلاغُ المالك الثاني: «الراتب لازم عليه شرح لأنّو ممكن الأساسي قليل يكون عمولات عالتسويق، مو رقم وخلص»). ومكانُه على النسخة لا على الموظّف لأنّ النسخة مؤرَّخةٌ ولا تُعدَّل بعد تفعيلها، فيُحفَظ الشرحُ مع الأرقام التي يشرحها ويتقاعد معها — ولو عُلِّق على الموظّف لبقي شرحٌ قديمٌ فوق أرقامٍ جديدة. و**غيرُ `activation_reason`**: ذاك للمدقّق ولا يُعرَض على أحد. تفصيلُ الشروط: الراتبُ الأساسيُّ وعمولةُ الاكتساب وأساسُ الدوام ويومُ الاستحقاق، مع `source` (`employee` سياسةٌ باسمه · `platform` سياسةُ المنصّة · `default` لا نسخةَ منشورةً بعد) و`policy_version`. كان الموظّف يرى محفظتَه ولا يرى ما تُحتسب به. المصدرُ `services.get_employee_pay_terms` فوق `get_active_employee_compensation_policy` — **نفسُها التي يحتسب بها محرّكُ الاستحقاق**، فلا تفترق أرقامُ العرض عن أرقام الصرف. والمبالغُ نصّاً لا `Decimal`. |
| GET | `/api/platform/ops/performance-evaluation-policies/` · `/{id}/` | `IsPlatformOperationsManager` — نسخ سياسة تقييم الـpilot (210-D) |
| POST | `/api/platform/ops/performance-evaluation-policies/draft/` · `/{id}/update-draft/` · `/{id}/clone/` · `/{id}/preview/` · `/{id}/activate/` | `IsPlatformOperationsManager` — نفس اصطلاح `subscription-policies` تماماً؛ الحفظ والتفعيل يرفضان مجموع أوزانٍ لا يساوي 100% بالضبط (210-D) |
| GET | `/api/platform/ops/compensation-policies/` · `/{id}/` | `IsPlatformOperationsManager` — نسخ سياسة تعويض الموظف (تصفية `?employee=`) (210-D) |
| POST | `/api/platform/ops/compensation-policies/draft/` · `/{id}/update-draft/` · `/{id}/clone/` · `/{id}/preview/` · `/{id}/activate/` | `IsPlatformOperationsManager` — نفس الاصطلاح (210-D) |
| GET | `/api/platform/ops/salary-lines/` · `/api/platform/ops/commission-lines/` | `IsPlatformOperationsManager` — قراءة سطور المحفظة (تصفية `?employee=`، والعمولة أيضاً `?company=`) (210-D) |
| POST | `/{salary-lines\|commission-lines}/{id}/transition/` · `/{id}/reverse/` · `/{id}/adjust/` | `IsPlatformOperationsManager` — نقل الحالة ضمن `PENDING → ELIGIBLE → APPROVED → PAYABLE → PAID`، عكسٌ بسبب (سطرٌ معكوسٌ لا حذف)، أو تسويةٌ بمبلغ وسبب (سطرٌ جديد ظاهر لا تعديل على الأصل) — بلا مسار حذف على أيٍّ منهما (210-D) |
| GET · POST | `/api/platform/ops/compensation/close/` | `IsPlatformOperationsManager` — `GET` معاينةٌ بلا كتابة (الحالة، التسليمات المعلَّقة المانعة، عدد الموظفين المؤهَّلين، مهلة المراجعة)، و`POST` إغلاقٌ idempotent (`period_year`/`period_month`) يرد 409 مع `blockers` عند وجود تسليماتٍ معلَّقة (210-D) |
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
| GET | `/api/platform/ops/meetings/` · `/{id}/` | `IsPlatformOperationsStaff` أو `IsPlatformOperationsManager` — المديرُ يرى الكلّ، والموظّفُ اجتماعاتِه المدعوَّ إليها وحدَها مشتقّةً من صفوف الحضور لا من معاملٍ في الطلب (211-F) |
| POST | `/api/platform/ops/meetings/create/` · `/{id}/update/` · `/{id}/cancel/` · `/{id}/invite/` | مدير العمليات وحدَه (`_require_manager`) — الإنشاءُ والتعديلُ والإلغاءُ وتحديدُ المدعوّين؛ الدعوةُ idempotent |
| GET | `/api/platform/ops/meetings/{id}/attendance/` | مدير العمليات وحدَه — دفترُ الحضور كاملاً («وكلّه محفوظ» في نصّ المالك) |
| POST | `/api/platform/ops/meetings/{id}/decide-excuse/` | مدير العمليات وحدَه — بتٌّ في عذرٍ **معلّق** بقبولٍ أو رفض؛ صفُّ الحضور يُتحقَّق من انتمائه لهذا الاجتماع لا لمعرّفٍ حرّ |
| POST | `/api/platform/ops/meetings/{id}/check-in/` | الموظّفُ المدعوُّ — «يحطّ دخول»: يسجّل حضورَه **ويستلم رابطَ الاجتماع في الردّ نفسِه**، فعلٌ واحدٌ لا فعلان |
| POST | `/api/platform/ops/meetings/{id}/excuse/` | الموظّفُ المدعوُّ — «يحطّ ملاحظة ليش ما بدّه يحضر»؛ السببُ إلزاميّ والحالةُ تصير **معلّقة** لا مقبولة |
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

## عدّادُ الحضور على المنصّة (#212 212-D)

`PlatformPresenceDay` (موظّف × يوم، `active_seconds`) هو دفترُ حضورِ **كترا
نفسِها**. و`hr.AttendanceDay` لا يصلح: يحمل `tenant` وهو دوامُ موظّفٍ في شركةِ
زبون، ومحورُ `attendance_regularity` القديمُ يقرؤه مُقيَّداً
بـ`tenant_id__in=engaged_tenant_ids` — فموظّفُ كترا لا صفوفَ له أبداً، فكان
المحورُ يُسقَط ويُعاد توزيعُ وزنه، أي أنّ «الحضور» لا يقيس شيئاً لفريق كترا.

**والأثرُ معامِلٌ على المركَّب لا محورٌ خامس.** نصُّ قرار المالك: «حدٌّ أدنى ٣
ساعات، وما زاد علاماتٌ أكثر، وما قلّ **خصم**» — والخصمُ تعديلٌ على الناتج. ومحاورُ
الـpilot أربعةٌ (40/30/20/10) يرفض `_validate_pilot_weights` مجموعاً غيرَ المئة،
فمحورٌ خامسٌ كان يستلزم إعادةَ كتابةِ أوزانٍ قرّرها المالكُ بنفسِه. ولا يُغذَّى
المحورُ القديم: حاسبتُه (`calculate_employee_performance`) **لا تُعرَض للموظّف**
— واجهتُه تعرض محاورَ الـpilot، فتغذيةُ محورٍ لا يراه أحدٌ أثرُها صفرٌ على
الشاشة.

| القاعدة | الموضع |
|---|---|
| درجةُ اليوم = `ساعات ÷ العتبة` مسقوفةً بسقف السياسة | `presence_discipline_factor` |
| المعامِلُ متوسّطُ **الأيّام التي فيها نبضة** — ويومٌ بلا نبضةٍ ليس صفراً | نفسها |
| العتبةُ والسقفُ حقلا سياسةٍ يُجمَّدان في `policy_snapshot` | `PerformanceEvaluationPolicy.presence_min_hours_per_day` · `presence_day_cap_percent` |
| عتبةُ صفرٍ = إطفاءٌ صريحٌ للأثر كلِّه | `presence_discipline_factor` |
| الدرجةُ **قبل وبعد** في الحمولة | `score_before_presence` و`presence.score_before/after` |
| نقطةُ السجلّ تقرأ **حاسبةَ التقييم نفسَها** لا `presence_discipline_factor` مباشرةً | `PlatformPresenceLogView` |
| رقاقةُ الطاولة تُلوَّن بعتبةِ **تخصّصِ الموظّف** النشطة | `presence_target_hours` في `get_platform_dashboard_summary` |
| سقفُ اليوم لا ينزل تحت ١٠٠٪ | `_validate_presence_policy` |

**والعتبةُ والسقفُ يُضبَطان من شاشةِ سياسةِ الأداء** (`PilotSettingsPanel`)، ويحملهما
الاستنساخُ (`clone_performance_evaluation_policy_to_draft` ينسخ الحقولَ يدويّاً،
فالمنسيُّ يرتدّ للافتراض بصمتٍ)، ويُسجَّلان في حدث السياسة. وحقلٌ لا تستطيع شاشةٌ
ضبطَه ليس سياسةً بل افتراضَ قاعدةِ بيانات.

**وموضعُ القاعدةِ واحد.** نقطةُ سجلِّ الحضور تنادي `calculate_employee_pilot_performance`
وتعرض `presence` منها: نداءُ `presence_discipline_factor` مباشرةً كان يعيد عتبةَ
الدالّةِ الافتراضيّةَ لا عتبةَ السياسةِ النشطة (شاشةٌ تقول «المطلوب ٣ ساعات» وقد
حُوسِب صاحبُها على ستّ)، وبلا `score_before/after` إطلاقاً — فسطرُ «قبل ← بعد»
فرعٌ ميّتٌ لا يُصيَّر. ورقاقةُ الطاولة كذلك: عتبتُها تأتي من الحمولة
(`presence_target_hours`، استعلامٌ لكلّ **تخصّصٍ** لا لكلّ بطاقة) لا رقماً في المكوّن.

**والجمعُ بالفجوات لا بالنبضات** (`record_presence_heartbeat`): تُجمَع الثواني
المنقضيةُ فعلاً بين نبضتين متقاربتين، مسقوفةً بـ`PRESENCE_HEARTBEAT_GRACE_SECONDS`.
ولو عُدَّت النبضاتُ (`+60` لكلّ نبضة) لصار عددُ الألسنة المفتوحة مضروبَ الوقت؛
ولو أُخِذ الفرقُ بين أوّل نبضةٍ وآخرِها لصار من نبض صباحاً وعاد عند المغيب حاضراً
يوماً كاملاً.

**والرقاقةُ مكوّنٌ واحدٌ لموضعَين** (212-N2، `PresenceClockChip`): بطاقةُ
الموظّف والمقعدُ على طاولة مساحة العمل. وكانت في البطاقة وحدَها بينما نصُّ طلب
المالك «يبين بالطاولة فوق صورتو» — والطاولةُ عنده حيث تجلس الوجوه. وقاعدتُها
دالّتان خالصتان في `frontend_v2/utils/presenceClock.ts` (`presenceClockLabel`
و`presenceToneOf`) يختبرهما `npm test`: غيابُ الحقل شُرطتان لا صفراً (صفرُ ثوانٍ
خبرٌ، والغيابُ حمولةٌ لا تحمل العدّاد)، والنبرةُ قياسُ اليوم على **عتبةِ تخصّصِ
صاحبه** من السياسة النشطة لا على رقمٍ مثبَّت. وخريطةُ الأصناف في ملفّ `.tsx`
داخل `components/platform/` عن قصد: حارسُ الجلد الداكن يمسح الـ`*.tsx` هناك،
فخريطةٌ في `.ts` تفلت من المسح وتظهر بيضاءَ وسطَ مركز قيادةٍ داكن.

**والنبضةُ تدقّ من حيث يعمل الموظّفُ فعلاً، لا من `/staff` وحدَها** (212-N1).
كانت الحلقةُ مكتوبةً داخل `StaffTopBar.tsx`، أي داخل قشرة المنصّة؛ وموظّفُ كترا
يقضي يومَه في نظام الشركة التي يخدمها — يفتح `/staff` دقيقةً ثمّ يعمل ساعاتٍ في
`/employee-ops` وسائرِ الشاشات — فكان عدّادُه يقرأ دقائقَ **ويُخصَم عليها في
التقييم**. فصارت الحلقةُ `hooks/usePlatformPresenceHeartbeat.ts` يركّبها الجانبان:
شريطُ `/staff` بلا شرط (القشرةُ لا تُصيَّر لغير أهلها)، و`AppLayout` بشرطِ
`presenceHeartbeatEnabled` — **موظّفُ منصّةٍ فقط وبعد حسمِ الجواب**، وإلّا نبض كلُّ
مستخدمٍ في كلّ شركةٍ كلَّ دقيقةٍ إلى الأبد بلا سطرٍ واحدٍ يُكتَب. والتركيبُ مرّتين
لا يضاعف شيئاً: الجمعُ بالفجوات هو نفسُه ما يجعل لسانين لا يضاعفان الوقت. والقاعدةُ
دالّةٌ خالصةٌ في `frontend_v2/utils/presenceHeartbeat.ts` يختبرها `npm test`.

## مهامُّ موظّفي كترا وملاحظاتُهم (#212 212-E)

خمسةُ نماذجَ في `platform_ops/models.py`: `PlatformTask` ·
`PlatformTaskAssignment` · `PlatformTaskSubmission` · `PlatformEmployeeNote` ·
`PlatformWorkspaceNote`. وكلُّها **بلا `tenant`** كنظيرتها `PlatformEmployee`.

**ولماذا لا `employee_ops.Task`:** ذاك جدولٌ كلُّ صفٍّ فيه يحمل `tenant` FK
و`hr.Employee` — مهامُّ موظّفي **شركةِ زبون**. وموظّفو كترا صفوفٌ في
`PlatformEmployee` بلا شركة، فإعادةُ استعمالِ ذاك الجدول كانت تستلزم `tenant`
مُلفَّقاً لكلّ مهمّةٍ داخليّة. والمفرداتُ متشابهةٌ بقصدٍ («بنفس الطريقة القديمة»
بنصّ المالك).

| القاعدة | الموضع |
|---|---|
| الجمهورُ أربعةٌ: فرديّ · محدَّدون · الجميع · **مجمَعٌ يُطالب به الموظّف** | `PlatformTask.AUDIENCE_*` |
| `ALL` تُسنِد للنشطين وحدهم، **والمجمَعُ لا يطالب به غيرُ نشط** | `create_platform_task` · `claim_platform_task` |
| حالةُ المهمّة **مشتقّةٌ من إسناداتها** لا حقلٌ يُكتَب | `_recompute_platform_task_status` |
| `completed_at` عند اكتمال **كلِّ** إسنادٍ لا أوّلِه | نفسها |
| القبولُ والتسليمُ من **صاحب الإسناد وحدَه** — في الخدمة وفي الـview | `_assert_assignment_belongs_to_actor` · `_require_owner` |
| «مقبول بس لسّا ما خلص» يعيد الإسنادَ `IN_PROGRESS` ولا يُقفله | `review_platform_task_submission` |
| **الرفضُ يعيدها مفتوحة** — لا حالةَ `REJECTED` نهائيّةً للمهمّة | نفسها |
| ملاحظاتُ المراجِع إلزاميّةٌ على الرفض والقبول الجزئيّ | نفسها |
| ملاحظةُ المديرِ افتراضُها **يراها الموظّف**، و`MANAGER_ONLY` استثناءٌ صريح | `PlatformEmployeeNote.visibility` |
| ملاحظةُ الموظّف على مهمّةٍ **مُسندةٍ له** أو عمومية (`task=null`) | `add_platform_workspace_note` |
| عددُ المطالبين بمهمّةِ المجمَع **من الحمولة** (`claimed_count`) لا من قائمة القارئ | `PlatformTaskViewSet.queryset` · `PlatformTaskSerializer` |

**والرفضُ لا يقفل شيئاً** — قرارُ المالك: «المرفوضةُ تعود مفتوحة». فإسنادُ
مهمّةٍ مُسندةٍ يعود `RETURNED` (يُسلّم صاحبُه ثانيةً)، وإسنادُ مهمّةِ مجمَعٍ
**يُحذَف** فترجع المهمّةُ إلى المجمَع يطالب بها غيرُه. ولذلك لا وجودَ لحالة
`REJECTED` في `PlatformTask.STATUS_CHOICES` أصلاً: حالةٌ كهذه كانت بابَ طريقٍ
مسدودٍ لعملٍ ما زال مطلوباً.

### ملفُّ المهمّة: مرفقاتٌ وخيطٌ ولوحٌ وإجباريّة (#213-ب)

نموذجٌ سادسٌ `PlatformTaskAttachment`، وحقلٌ واحدٌ `PlatformTask.is_mandatory`.

| القاعدة | الموضع |
|---|---|
| **المُسنَدةُ شخصيّاً لا تُرفَض** — الإسنادُ يولد `ACCEPTED` بتاريخه، فلا زرَّ قبولٍ أصلاً | `create_platform_task` · `PlatformTask.is_mandatory` |
| الفرديُّ إجباريٌّ **دائماً** والمجمَعُ اختياريٌّ **دائماً** — لا يُقبَل عكسُهما من الحمولة | `create_platform_task` |
| الجماعيّةُ (محدَّدون · الجميع) هي وحدَها التي يختار المديرُ إجباريّتَها، والموظّفُ يراها | نفسها · `PlatformTaskSerializer` |
| دورُ المرفق ثلاثةٌ — شرحُ المدير · عملُ الموظّف · ما رافق تسليماً — **ويُحرَس بقيد قاعدة** لا في بايثون وحدَها | `PlatformTaskAttachment.Kind` · `platform_ops_task_attachment_role_is_coherent` |
| الرفعُ **يُرفَض قبل البايتات لا بعدها** | `PlatformTaskViewSet.upload_attachment` ينادي `assert_platform_task_is_assigned_to` قبل `upload_media_file` |
| الموظّفُ يرفع **قبل القبول وقبل التسليم**: الشرطُ إسنادٌ قائمٌ لا إسنادٌ مقبول | `assert_platform_task_is_assigned_to` |
| التنزيلُ يمرّ بـ`core.media_views.stream_stored_asset` — لا رابطَ تخزينٍ عارٍ في الحمولة | `PlatformTaskViewSet.download_attachment` |
| الخيطُ **إسقاطُ قراءةٍ** يجمع المرفقاتِ وملاحظاتِ الطرفين والتسليماتِ والمراجعات مرتَّبةً بالوقت — لا جدولَ تعليقاتٍ ثالثاً | `platform_task_thread` |
| وكلُّ حدثٍ يُرشَّح **لقارئه**: `MANAGER_ONLY` لا تخرج، وعملُ زميلٍ لا يراه زميل | `_thread_event_is_visible_to` |
| نصُّ القرار العربيُّ يخرج مع رمزه (`decision_display`) — لا قاموسَ ترجمةٍ ثانٍ في الواجهة يتخلّف عن `choices` | `platform_task_thread` |
| «مين معو شو ومين استلم» **أربعةُ استعلاماتٍ ثابتةٍ** لا استعلامٌ لكلّ موظّف | `platform_task_board` |
| واللوحُ **لا يُرشَّح على «نشط»**: من خرج من الخدمة وبيده عملٌ يبقى فيه بشارة حالته — وإخفاؤه يُخفي عملَه معه | نفسها |
| و«مقبولة» تُقرأ بجانب **«منها إجبارية»**: الإجباريّةُ تولد `ACCEPTED` بلا فعلِ صاحبها، فجمعُهما يخلط «أخذ» بـ«أُلزم» | نفسها |

**ولماذا `kind` بقيدِ قاعدةٍ لا بمنطقٍ في الخدمة:** المرفقُ يُنشأ من بابين
(رفعُ المدير ورفعُ الموظّف) ويُنقَل من حالةٍ إلى حالةٍ عند التسليم. وصفٌّ
بـ`kind=BRIEF` يحمل `employee` أو `kind=DELIVERY` بلا `submission` يقلب كلَّ قراءةٍ
لاحقةٍ — والقيدُ في القاعدة يمنعه من أيّ مسار، بما فيه `shell` وهجرةٌ مستقبليّة.
(وMySQL **تفرض** `CheckConstraint` وإن تجاهلت `UniqueConstraint(condition=…)`.)

**ودَينٌ مفتوحٌ يُبلَّغ للمالك:** مرفقُ PDF يُرفَع ولا يُنزَّل — Cloudinary يمنع
تسليمَ PDF **على مستوى الحساب** (401)، وهو إعدادٌ خارجيٌّ لا عطبُ كود، ويصيب
مستنداتِ مكتب المحاسبة أيضاً.

### شبكةُ حضور المتقدّمين للاجتماعات (#213-ج)

بلا نموذجٍ جديد: قراءةٌ فوق `ApplicantMeeting` و`ApplicantMeetingAttendee`.

| القاعدة | الموضع |
|---|---|
| صفٌّ لكلّ **هويّة** (`identity_key`) لا لكلّ اسمٍ معروض — متقدّمان باسمٍ واحدٍ صفّان | `build_applicant_attendance_matrix` |
| خليّةٌ غائبةٌ تعني **«لم يُدعَ»** ولا تُقرأ غياباً — والغيابُ حالةٌ مكتوبةٌ في صفّها | نفسها |
| النافذةُ ٦٠ يوماً خلفاً و٣٠ أماماً افتراضاً، وسقفُها ٣٦٦ يوماً — شبكةٌ بلا حدٍّ تجرّ الجدولَ كلَّه | `ATTENDANCE_MATRIX_*` |
| والمدى يُرشَّح بـ`core.date_ranges.filter_local_date_range` — لا تطبيقَ ثانٍ للنافذة الزمنيّة | نفسها |
| تاريخٌ يطابق الشكلَ ويستحيل تقويمياً (`2026-13-40`) يردّ **٤٠٠ بنصٍّ عربيّ** — `parse_date` **ترفع** `ValueError` هنا ولا تعيد `None` | `ApplicantMeetingViewSet._attendance_window` |
| التصديرُ **فعلٌ مستقلٌّ** لا `?format=csv` — الأخيرُ يصطدم بـ`URL_FORMAT_OVERRIDE` في DRF | `export_attendance_matrix` |
| والبابُ لمسؤول التوظيف وحدَه كسائر `applicant-meetings/` | `IsPlatformRecruiter` |
| خليّةُ CSV التي تبدأ بـ`=` أو `+` أو `-` أو `@` **تُهرَّب بفاصلةٍ علويّة** — الاسمُ يكتبه المتقدّمُ نفسُه، وإكسل ينفّذ ما يبدأ بها | `views._csv_safe` |
| ورمزُ حالة المتقدّم يخرج ومعه نصُّه (`applicant_status_display`) | `build_applicant_attendance_matrix` |

**وفي الواجهة** (`ApplicantAttendanceMatrix.tsx` · `PlatformMeetingsTab.tsx` ·
`PlatformApplicantsTab.tsx`) خمسُ قواعدَ كلُّها مكتوبةٌ على عطبٍ وقع فعلاً:

| القاعدة | لماذا |
|---|---|
| أيقونةُ الحالة **خريطةٌ شاملةٌ على النوع**، وحقلا الحالة (`ApplicantAttendanceStatus` · `ApplicantMeetingStatus`) اتّحادان مُسمّيان لا `string` | مقارنةُ `"ATTENDED"` بـ`attended` كاذبةٌ دائماً ولا يبلّغ عنها `tsc` على `string`: كانت **كلُّ** خليّةٍ ترسم ساعةَ «مدعوّ» |
| يومُ العمود يمرّ بـ`new Date(start)` (`meetingDay`) | `formatDateValue` على نصٍّ تقتطع أوّلَ عشرة محارف — أي يومَ UTC، فيختلف عن قائمة الاجتماعات |
| فتحُ اجتماعٍ **يُخفي** جسمَ التبويب ولا يفكّكه، والعودةُ تزيد `refreshToken` | التفكيكُ يمحو المدى والعرضَ المختارين، والبقاءُ بلا إعادةِ جلبٍ يعرض خلايا قديمة بعد تسجيل الحضور |
| طلبُ فتح ملفٍّ من الشبكة يُفرَغ عند تنفيذه (`onFocusHandled`)، ولا يُبَتّ فيه قبل أن تصل القائمةُ **غيرُ المصفّاة** (`loadedFilters`) | لجامُ «آخر معرّفٍ نُفِّذ» كان يجعل الضغطةَ الثانية بلا أثر، والبتُّ المبكّر يبحث في نتيجةِ فلترٍ قديمٍ فيعلن الموجودَ مفقوداً |
| الصفُّ يعرض حالةَ المتقدّم، والعمودُ يعرض حالةَ الاجتماع غيرِ المجدول | حقولٌ يرسلها الخادمُ سلفاً، وبلا الحالةِ لا تكتمل «النظرةُ الواحدة» ويبدو الملغى اجتماعاً عاديّاً |

**وعددُ المطالبين لا يُحسَب في المتصفّح** (212-E2): قائمةُ `assignments/`
مقصورةٌ على الموظّف، وبطاقةُ المجمَع لا تُعرَض إلا لمن لا إسنادَ له فيها — فعدٌّ
منها **صفرٌ بحكم البناء** لا معلومةٌ ناقصة، وهو ما كانت الشاشةُ تعرضه «طالب بها ٠
من حدّ ٣». فصار `claimed_count` حقلاً في الحمولة يُحسب باستعلامٍ فرعيٍّ مستقلٍّ عن
مرشّح النطاق، ويُقفل الزرَّ عند بلوغ الحدّ بدل تركه يفشل عند الخادم.

**وفحصُ «رُوجع سلفاً» يسبق البحثَ عن الإسناد** في دالّة المراجعة: رفضُ تسليمِ
مجمَعٍ يحذف الإسناد، فمراجعةُ ذلك التسليمِ ثانيةً كانت ترفع `DoesNotExist` غيرَ
معالجةٍ — خطأَ خادمٍ مكان رسالةٍ مفهومة.

**والإسنادُ يبدأ من الشخص لا من نموذجٍ مركزيّ** (212-O1). كان المديرُ يكتب
المهمّةَ ثمّ يبحث عن اسم صاحبها في قائمةٍ منسدلة، وهو ينظر إلى وجهه أمامه على
الطاولة. فصار على بطاقة كلِّ شخصٍ بابٌ يفتح ملفَّه على تبويب **«المهامّ»**، وفيه
نموذجُ إسنادٍ بلا حقلِ موظّفٍ أصلاً: `audience=INDIVIDUAL` يلزمه واحدٌ بالضبط
وهو صاحبُ الدرج. ولا نقطةَ خادمٍ جديدة — `create_platform_task` هي هي.
و**النموذجُ مشروطٌ بـ`canManage`**: الدرجُ يُركَّب في قشرة الموظّف أيضاً، وزرٌّ
يراه من لا يملكه وعدٌ كاذبٌ ينتهي بـ403.

**ومهامُّ كلِّ شخصٍ على بطاقته** (212-O2): `open_platform_tasks_count` في حمولة
اللوحة — **تجميعةٌ واحدةٌ** لكلّ الموظّفين كنظيرتها `presence_seconds_today`، لا
استعلامٌ لكلّ بطاقة. و«مفتوحة» = كلُّ ما لم يكتمل: `RETURNED` عملٌ **عاد إلى
صاحبه** لا عملٌ انتهى، وعدُّها منتهيةً كان يُظهر طاولةً فارغةً وأصحابُها يعملون.
وهي **غيرُ** `active_work_orders_count`: ذاك `WorkOrder` وهذا
`PlatformTaskAssignment`، نظامان لا يلتقيان ورقمٌ واحدٌ عنهما يكذب. والدرجُ
يقرأ قائمةَ صاحبه بمرشِّح `?employee=` على `assignments/` — **يُطبَّق بعد تضييق
غير المدير** فلا يقرأ موظّفٌ إسناداتِ زميله بمعرّفٍ يكتبه في العنوان.

## بابُ CRM التسويق من مركز القيادة (#212-H)

تبويبُ «العملاء» هو الثاني بعد اللوحة في `PlatformOpsDashboard.tsx` ويُركّب
`CrmPanel` نفسها داخل قشرة `ops-shell`؛ لا رابطَ إلى `/staff` ولا نسخةَ ثانيةً
من الشاشة. الوصولُ إلى مركز القيادة محروسٌ خادميّاً بـ`IsPlatformAdmin`، لذلك
`isManager={true}` صحيحٌ في هذا الموضع وحده. و`myEmployeeId={null}` مقصود: السوبر
أدمن قد لا يملك صفَّ `PlatformEmployee`، فلا يجوز اختراع هويةٍ أو نسبةُ ملكيةِ
عميلٍ إليه. يبقى تركيبُ القشرة الموظف `StaffShell.tsx` كما هو، فهو باب المسوّق
الأول. والشريط السفلي الضيق يبقى أربعةَ تبويباتٍ تشغيلية؛ «العملاء» لا يزاحمها
خامساً حتى لا يضيق الشريط.

**والنطاقُ الابتدائيُّ للوحة مشتقٌّ من وجود دفترٍ شخصيّ لا ثابت.** `scope=mine`
يُرشَّح خادميّاً بـ`assigned_to=employee`، فبلا صفٍّ يعيد `none()`: فمن يدخل من
مركز القيادة كان يهبط على «عملائي» فيقرأ **صفراً بحكم البناء** والقاعدةُ مملوءة.
ولمن لا دفترَ له وهو مديرٌ يكون الهبوطُ على «الكل» — و«المخزنُ المتاح» ليس
بديلاً، فهو لا يحمل عميلاً مُسنَداً لزميل. وشريطُ «عدّاداتي» لا يُركَّب له:
`stats/me/` يرفع 403 بلا صفّ موظّف، واللوحةُ تعرض نصَّ الخطأ مكانَها بالتصميم.
يُقاس الطرفان: `crm/tests/test_manager_without_employee_row.py` للحقيقة
الخادميّة، و`CrmPanelLandsOnADeskThatHasRowsTest` لاختيار الشاشة.

## ملاحظاتُ الموظّف في ملفّه الشخصيّ (#212-J)

تبويبُ «الملاحظات» في `EmployeeProfileDrawer.tsx` هو مكانُ ما كُتب **على**
الموظّف: قائمةٌ ببشارةِ الرؤية والكاتبِ والتاريخ، ونموذجُ إضافةٍ لا يُعرَض إلا
لمن يملك `is_platform_admin` — الخادمُ يرفض غيرَه بـ403، ونموذجٌ معروضٌ لمن
يُرفَض فعلُه بابٌ مسدود. وكانت الملاحظاتُ تُكتَب وتُقرَأ في تبويب «مهامّ
الموظفين» وحدَه باختيارِ الموظّف من منسدلة، فمن فتح ملفَّ موظّفٍ لم يجد شيئاً.

`PlatformEmployeeNoteViewSet` يقبل `?employee=<id>` — **ترشيحٌ في الخادم**، لأنّ
القائمةَ بلا مرشّحٍ تعيد ملاحظاتِ كلِّ الموظّفين. ويُطبَّق **بعد** تضييق غير
المدير لا قبلَه: مُعامِلٌ يُقرأ قبل التضييق يصير بابَ تسريبٍ يكتب فيه موظّفٌ
معرّفَ زميله. وقيمةٌ غير رقميّة ⇒ `ValidationError` (٤٠٠) لا `ValueError` (٥٠٠).

ويرى الموظّفُ ما `visibility=EMPLOYEE` في `/staff/tasks` («ملاحظات المدير عليّ»)؛
و`MANAGER_ONLY` لا تخرج من الخادم إليه أصلاً.

**وللملاحظة `task` اختياريّةٌ منذ 212-M3**، فتصير ملاحظةً **على مهمّة** لا على
صاحبها عموماً، ويقبل الموجّهُ `?task=<id>` لخيط تلك المهمّة. وقبلَها لم يكن
للمدير مكانٌ يكتب فيه على مهمّة إطلاقاً: ملاحظتُه على الموظّف، و`reviewer_notes`
على **التسليم** أي لا وجودَ لها قبل أن يُسلّم — فمن لحظةِ الإسناد إلى لحظةِ
التسليم لا كلمةَ منه، بينما الموظّفُ يكتب على مهمّته منذ 212-E
(`PlatformWorkspaceNote.task`). والقيدُ نظيرُ قيدِ الموظّف حرفاً بحرف: **مهمّةٌ
ليست مُسندةً لهذا الموظّف مرفوضة** (`task_not_assigned_to_employee`) — وإلّا سكنت
الملاحظةُ خيطاً لا يفتحه أحد، أو أرت الموظّفَ مهمّةً ليست له. وتظهر له **عند
مهمّته** في بطاقة الإسناد لا في قائمةٍ بعيدة.

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
  و`PlatformRecruiter` و`ApplicantMeeting` و`ApplicantMeetingAttendee` و`ServiceSubscriptionPolicy` و`ServiceSubscriptionPolicyEvent` (افتراضيات
  منصة لا شركة)، و`SubscriptionBillingRecord` و`ServiceSubscriptionEvent` شركتهما مشتقة عبر
  `subscription.tenant` لا بحقل مباشر.
- فرادة الارتباط النشط لنفس (الموظف، الشركة) تُفرض تحت قفل `select_for_update` في الخدمة داخل `transaction.atomic` لأن MySQL تتجاهل القيود الشرطية.
- الإلغاء والتعليق يسحبان فقط العضوية التي أنشأها الارتباط (`created_membership=True`)، ولا يمسّان أي عضوية مسبقة للزبون.
- إيقاف أو تعليق اشتراك الخدمة يُعلّق الارتباطات النشطة ولا يحذفها.
- نقطة أوامر العمل مفلترة بخلاف أختيها: موظف المنصة يرى شركات ارتباطاته النشطة وحدها، والشركات تُشتق من `Engagement` لا من الطلب. ومدير المنصة وحده يرى كل الشركات — المؤهلة للخدمة منها فقط.
- كل تغيير حالة لأمر العمل يمر بـ`transition_work_order_status` وفق خريطة `WORK_ORDER_TRANSITIONS` وحدها — لا كتابة مباشرة على `status`.
- مغادرة موظف المنصة (`offboard_platform_employee`) عملية ذرية idempotent لا تفشل ولا تكرر الآثار عند تكرار الاستدعاء.
- قائمة الاستيراد البيضاء تتوسع فقط عند حاجة مرحلة موثقة، ولا تستورد الوحدة `employee_ops`؛ اتسعت في م٨ عمّا يسمّيه §١ من المواصفة بـ`sales.models` · `sales.serializers` · `sales.services` · `inventory.models`، لأن §٥ يفرض أن تمر فاتورة الخدمة بمسار المبيعات — قرار مسجّل.
- ترتيب الأقفال الصارم: `Tenant -> ServiceSubscriptionPolicy -> ServiceUnitCatalog -> PerformanceEvaluationPolicy -> EmployeeCompensationPolicy -> IntegrationKey -> ServiceSubscription -> CompanyHealthCheck -> CompanyHealthCheckItem -> CustomerAcquisition -> PlatformEmployee -> Engagement -> WorkOrder -> WorkOrderDeliverable -> WorkOrderDocumentLink -> ServiceUsageEvent -> MonthlyCompensationClose -> EmployeeSalaryLine -> AcquisitionCommissionLine -> PerformanceReviewRequest -> UserCompanyMembership -> DailyRating -> JobPosting -> JobApplicantInvitation -> JobApplicant` (محروسٌ ساكناً بـ`platform_ops/tests/test_engagement_lifecycle.py` (`LockOrderSourceGuardTest`) — `ServiceUnitCatalog` و`ServiceUsageEvent` أُضيفا في 210-C، والخمسة `PerformanceEvaluationPolicy`/`EmployeeCompensationPolicy`/`MonthlyCompensationClose`/`EmployeeSalaryLine`/`AcquisitionCommissionLine` في 210-D). **تركيب أقفالٍ عابرٌ لدالّتين لا يراه الحارس الساكن** (يفحص كل دالّة على حدة): `approve_work_order_deliverable_with_usage` تقفل `ServiceSubscription` صراحةً **قبل** استدعاء `review_work_order_deliverable` (تقفل `WorkOrderDeliverable`) — عكس الترتيب الظاهر في كل دالّة منفردة كان يُنتج تشابكاً حقيقياً على MySQL لولا هذا القفل المسبق المتعمَّد.
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
- **بابُ موظّف المنصّة: أربعُ عُقَدٍ لا واحدة** (211 م١). موظّفٌ تُقبَل دعوتُه لم يكن يصل إلى `PlatformEmployeeWorkspace` أبداً، والعُقَدُ مستقلّةٌ وكلٌّ منها تكفي وحدَها لقطع الطريق:
  - **(أ) القبولُ يُدخِل صاحبَه ولا يكتفي بإخباره**: `platform_ops/public_hiring/views.py` (`PublicInvitationAcceptView`) يستدعي `hr/auth_api.py` (`issue_login_session`) فيردّ `token` و`user`. الرمزُ المهشَّرُ أُثبت واستُهلك في السطر السابق، فطلبُ كلمةِ سرٍّ ثانيةً بعده **بلا فائدةٍ أمنيّةٍ وبابٌ مسدودٌ عمليّاً**. والدالّةُ **مستخرَجةٌ** من `login_view` لا منسوخةٌ عنه — نسخةٌ ثانيةٌ من إنشاء الجهاز والمرآة وسجلّ الجلسة كانت ستتباعد عن الأصل عند أوّل تعديل؛ ولذلك أُضيفت `hr.auth_api` إلى قائمة `test_isolation_guard.py` البيضاء صراحةً.
  - **(ب) حقلُ الدخول يقبل اسمَ المستخدم**: `hr/auth_api.py` (`login_view`) يبحث `Q(username__iexact=…) | Q(email__iexact=…)` **من الأصل**، بينما حقلُ `frontend_v2/components/LoginPage.tsx` كان `type="email" required` داخلَ `<form onSubmit>` — فالمتصفّحُ نفسُه يرفض إرسالَ اسم مستخدم قبل أن يبلغ الخادمَ، واسمُ المستخدم هو ما تُنشئه دعوةُ التوظيف. الحارسُ ساكنٌ بالضرورة (`npm test` يشغّل دوالَّ خالصةً ولا يُصيّر مكوّناً) ويفحص **عنصرَ** `value={email}` لا نصَّ الملفّ، وإلاّ اصطاد التعليقَ الذي يشرح القاعدة.
  - **(ج) `ApplicationBoundary` كان يبتلع من لا شركةَ له**: `accept_applicant_invitation` لا يُنشئ `UserCompanyMembership` — بخلاف نظيرتها في `employee_ops` — فمن عُيِّن ولم يُسنَد بعدُ يهبط على **«أنشئ شركتك الأولى»**. صار `frontend_v2/index.tsx` يستثني مساراتِ المنصّة (`platformTenantlessPath`) كما يستثني مساراتِ المحاسب وبالحجّة نفسِها: هذه الشاشاتُ لا تقرأ شركةَ جلسةٍ إطلاقاً.
  - **(د) الهبوطُ بعد الدخول**: `frontend_v2/App.tsx` (`roleDefault`) لا يعرف موظّفَ المنصّة فيرسله إلى شاشةِ مهامّ **شركةِ الزبون**. الحلُّ **بابٌ ثانٍ لا تعديلُ الأوّل**: مسارٌ خصوصيٌّ `/staff` (`frontend_v2/components/platform/StaffLoginPage.tsx`) **خارجَ شجرة المزوّدات** كصفحةِ قبول الدعوة، يُثبت الهويّة بـ`platform-staff/me/` ثمّ ينتقل انتقالاً كاملاً إلى `/staff/home` فلا يمرّ بـ`roleDefault` أصلاً. **ومن وصله وجلستُه قائمةٌ وهو موظّفُ منصّةٍ يُحوَّل إلى مساحته فوراً** (212-L1): `/staff` بلا شَرطةٍ هو العنوانُ الذي يحفظه الموظّفُ ويكتبه بيده، والقشرةُ على `/staff/*` — فكان نموذجَ دخولٍ لمن هو داخلٌ أصلاً، بلا رسالةٍ ولا رابطٍ إلى القشرة. والتحويلُ مشروطٌ بصفة المنصّة لا بمجرّد وجود جلسة: مستخدمُ شركةٍ يفتح البابَ ليدخل بحسابٍ آخر يجب أن يرى النموذج. **وليس بوّابةَ صلاحيّة**: الحراسةُ خادميّةٌ كما كانت، ومن يدخل منه وليس موظّفَ منصّةٍ يُرسَل إلى `/` بلا رسالة — قولُ «هذا الباب ليس لك» يُخبر الغريبَ أنّ هنا باباً. والمسارُ **غيرُ مذكورٍ** في صفحة الهبوط ولا في `PublicNavbar` بقرار المالك، ويحرس ذلك اختبارٌ صريح.
- **إبطال الدعوة عند مغادرة العرض:** `platform_ops/services.py` (`transition_applicant_status`) يبطل تحت القفل كل دعوة حية للمتقدم (`revoked_at`) عند مغادرة حالة `offered`؛ و`platform_ops/services.py` (`accept_applicant_invitation`) لا يقبل إلا متقدماً حالتُه `offered` تماماً وإلا 410 ولا ينشأ مستخدم، فلا يُوظَّف المرفوض برابط قديم. تمر كلمة المرور بـ`validate_password`، وسباق اسم المستخدم ⇒ 400 لا 500.
- **الدورة ذات الإجمالي الصفري:** `platform_ops/services.py` (`bill_subscription_for_period`) تنشئ `SubscriptionBillingRecord` بلا فاتورة، وتقدّم الدورة وتصفّر العداد في المعاملة نفسها؛ وإلا علق الاشتراك وتراكم العداد أشهراً.
- **بوابة الفوترة الواحدة:** `platform_ops/services.py` (`billing_preflight`) هي بوابة التشغيل والمعاينة؛ ومنها أن عميل الفوترة لا يكون من شركة الاشتراك نفسها (`billing_customer_same_tenant`) وإلا رُحّلت فاتورة الخدمة في دفاتر الزبون.
- **فتح وإغلاق الإعلان:** `platform_ops/serializers.py` (`JobPostingSerializer`) يجعل `is_open` للقراءة فقط؛ الإغلاق وإعادة الفتح بفعلَي `close`/`reopen` وحدهما.
- **لا إسناد تشغيلي بلا أساس معتمد (210-B):** `assign_platform_employee` يرفض `kind=standard` بلا `CompanyHealthCheck` تأسيسي `approved` (`baseline_required`)؛ الاستثناء الوحيد `kind=onboarding` الموسوم بتاريخ انتهاء `onboarding_expires_at` (حدّه `MAX_ONBOARDING_DAYS`). لا تُخلط قط مع درجتي «صحة الخدمة»/«تعاون الزبون» المشتقّتين حيّاً في `CompanyHealthView` — الأولى سجلٌّ يُعتمد ويبقى تاريخه، والثانيتان لقطة لحظية.
- **الطاقة قبل الإسناد أو النقل:** حِمل الموظف مجموع وحدات حِمل شركات ارتباطاته النشطة (`employee_capacity_snapshot`)، ووحدة حمل الشركة من تعقيد أحدث أساس معتمد لها (`low=1`/`medium=2`/`high=3`، أو `medium` افتراضاً بلا أساس بعد). تجاوز `capacity_target` يُرفض (`capacity_exceeded`، 409) إلا بـ`capacity_override_reason` صريح يُحفظ على الصفّ. و`capacity_target` صفراً تعني **«لم تُضبط بعد» لا «طاقة صفر»** فلا تُفعِّل الرفض (`_would_exceed_capacity`) — هو افتراض النموذج، وهو معنى الصفر نفسه في مقام «الإنتاجية المنجزة» وفي كشف الحمل الزائد؛ القراءة الحرفية كانت ترفض كل إسناد لكل موظف حقيقي. وكانت بلا واجهة كتابة إطلاقاً حتى 210-ز، فصارت تُضبط عبر `PATCH /employees/{id}/targets/` (`set_employee_targets`) لا من الـshell وحده.
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
- **سياسة تقييم الـpilot سياسةٌ ثانيةٌ مستقلّة لا تعديلٌ في مكان (210-D):** `PerformanceEvaluationPolicy` لا تمسّ `PolicyProfile` ولا `DEFAULT_AXIS_WEIGHTS` القديمين بأثرٍ رجعي — لقطات #207 القديمة (`policy_profile` مملوءة) تبقى كما هي، ولقطات الـpilot الجديدة (`evaluation_policy` مملوءة) تستعمل المحاور الأربعة (40/30/20/10). محور الحضور والانضباط يسقط من هذه السياسة فقط ولم يُحذف من الكود — يبقى قابلاً للاستعمال في #207 القديم.
- **استبعاد وقت الإجازة المعتمدة سؤالٌ مفتوحٌ غير منفَّذ (210-D، §٦ من التذكرة):** لا رابط بين `PlatformEmployee` (هويةٌ منصيةٌ لا تخص شركة) وموظف `hr` المرتبط بشركة وإجازاته؛ الاستبعادات الثلاثة الأخرى (onboarding، انتظار العميل، النقل قبل الاستحقاق) منفَّذة في `calculate_employee_pilot_performance`، وهذه وحدها TODO صريح في الكود لا حلٌّ مُختلَق.
- **مقامُ محور إنجاز العمل بالوحدات لا بعددِ الأوامر (210-D):** بسطُ المحور الأوّل مجموعُ `units` من دفتر الاستخدام، فوجب أن يكون مقامُه من الجنس نفسِه — مجموعَ `ServiceUnitCatalogEntry.units_for()` على روابط مستندات الأوامر المُسندة في الفترة، **بالصيغة عينِها** التي يحتسب بها الدفترُ البسط لا بصيغةٍ ثانيةٍ تُشتق. مقامٌ بعددِ الصفوف يقيس جنساً آخر: أمرٌ واحدٌ بعشرِ وحداتٍ يُنتج 1000% تُقصُّ بصمتٍ إلى 100، وموظّفٌ أنجز نصفَ ما أُسند إليه من عملٍ متعدّدِ الوحدات يظهر بدرجةٍ كاملة. ويصحّ هذا لأنّ الروابط تُنشأ «تمهيداً للتسليم» و`deliverable` فيها يُملأ لحظةَ التسليم — فهي نطاقُ العملِ المُسند لا أثرُ المُنجَز، فيبقى عملٌ أُسند ولم يُسلَّم حاضراً في المقام. ورابطٌ بنوعٍ لا بندَ له في الكتالوج السارِي **لا يُطرح صامتاً** (فيصغّر المقامَ ويرفع الدرجةَ بغير حقّ) بل يُعدُّ ويُعرض في `uncatalogued_document_links`. والفائضُ فوق المئة يُعرض في `raw_percent` والدرجةُ تبقى مقصوصةً عند 100 لأنّ المركَّبَ الموزون لا يقبل أكثر — فالفرقُ بين «أنجز المُسندَ إليه» و«أنجز ضعفَه» قرارُ إدارةٍ لا يُطوى في القصّ. و**البسطُ نفسُه مقصورٌ على شركات الإسناد المعياريّ** (`standard_tenant_ids`) كالمقام تماماً: وحداتُ التهيئة (`onboarding`) لا مقابلَ لها في المقام أصلاً، فعدُّها في البسط وحدَه يرفع النسبةَ فوق المئة بعملٍ لم يُسند في نطاق المحور.
- **المحفظة دفترٌ تشغيليٌّ لا payroll قانوني (210-D):** لا ضرائب ولا حوالة بنكية ولا قيد محاسبي — `platform_ops` لا تستورد `accounting` ولا تكتب قيداً مباشرة (يحرسه `test_isolation_guard.py`). السطر المالي **لا يُحذف أبداً**: لا `delete()` ولا مسار حذف في الـAPI؛ التصحيح بعد الإغلاق سطرُ تسويةٍ ظاهرٌ (`adjustment_of`) أو سطرٌ معكوس (`REVERSED`) لا كتابةً فوق الأصل.
- **الراتب والعمولة سطران منفصلان دوماً (210-D):** `EmployeeSalaryLine` و`AcquisitionCommissionLine` نموذجان لا نموذجٌ واحد بعمود مميِّز NULL، لأن قيد فرادةٍ مركّبٍ يضمّ NULL لا يمنع تكراراً بدلالة SQL القياسية.
- **عمولة الاكتساب مستقلّةٌ عن موظّف الخدمة الحالي (210-D):** تُنسب دوماً إلى `acquisition.acquired_by` الملتقط وقت إنشاء السطر لا موظّف الخدمة وقت الإغلاق؛ النقل لا يغيّر المستفيد ولا يُعيد عدّ الأشهر من الصفر. بعد `acquisition_commission_months` (افتراضياً 3) **لا يُنشأ سطرٌ جديد إطلاقاً** — لا حتى بمبلغ صفر.
- **السطرُ المعكوس لا يستهلك شهراً من أشهر العمولة (210-D):** عدُّ الأشهر المستهلكة يستثني `REVERSED` وحدَها، لأنّ العكسَ يعني أنّ العمولةَ لم تُستحق أصلاً (اشتراكٌ أُلغي، اكتسابٌ خاطئ) فعدُّه يحرم الموظّفَ شهراً استحقّه ولم يُقبض. و`PENDING` **يستهلك** سلفاً لأنّه استحقاقٌ قائمٌ ينتظر إثباتَ الدفع لا استحقاقاً مُلغى.
- **عكسُ سطرٍ ماليٍّ وتسويتُه يكتبان أثراً يسمّي فاعلَه (210-D):** `reverse_wallet_line` و`adjust_wallet_line` كلتاهما تكتبان `PlatformActivityLog` بـ`entity_type` من شكل `wallet_line:{kind}`؛ والسجلُّ يُعلَّق على موظّف السطر لأنّ الجدول بنيةٌ موظَّفيّةٌ بلا عمود فاعل، فيُثبَّت الفاعلُ في `details.actor_user_id` صراحةً. بغير ذلك يتغيّر مبلغٌ مستحقٌّ بلا سجلٍّ يُراجَع.
- **الأهلية الشهرية شرطٌ ثلاثيٌّ مشترك (210-D):** انقضاءُ تجربة العميل إن كانت له تجربةٌ أصلاً (عميلٌ فُعِّل مدفوعاً بلا تجربةٍ قَطّ — `trial_ends_at` فارغٌ لأنّ `activate_paid_subscription` لا تضبطه إطلاقاً — **مستحقٌّ لا محجوب**؛ فالحاجزُ تجربةٌ **ساريةٌ** تمتدّ بعد نهاية الفترة لا غيابُ تجربة)، **دفعٌ مسجَّلٌ فعلاً لا مجرّد فوترة** (`SubscriptionBillingRecord` مربوطٌ بفاتورةٍ `amount_paid >= grand_total`؛ وجود سجلّ الفوترة وحده ليس دليل دفع)، والخدمة نشطة حتى نهاية الفترة معاً — غياب أيٍّ منها يترك السطر `PENDING` بسببٍ صريح (مثل «الدفع غير مسجَّل») لا صفراً صامتاً ولا مبلغاً مؤكَّداً خاطئاً.
- **إغلاق الشهر idempotent ومؤرَّخ لا يُعاد فتحه (210-D):** `MonthlyCompensationClose` فرادةٌ غير مشروطة على `(period_year, period_month)`؛ تكرار الإغلاق (بما فيه تسابقٌ يُمسَك بـ`IntegrityError`) يعيد الصفّ القائم بلا إعادة تنفيذ الحلقة فلا يتكرّر أي سطر. تعديل سياسة التقييم أو التعويض لاحقاً **لا يعيد حساب شهرٍ مُغلَق** — اللقطة والسطور مجمَّدتان. تسليماتٌ بانتظار المراجعة مُقدَّمةٌ ضمن الشهر تمنع الإغلاق صراحةً (`MonthCloseBlockedError` مع `blockers`) بدل إغلاقٍ صامتٍ فوقها.
- **مهلة المراجعة إعدادٌ لا رقمٌ مطمور (210-D):** `review_grace_period_hours` على `PerformanceEvaluationPolicy` (افتراضياً 48) إعلاميةٌ في معاينة الإغلاق؛ التسليمات المعلَّقة تمنع الإغلاق دوماً بصرف النظر عن قيمتها.
- **حاجزُ الإغلاق عابرٌ للشركات والموظفين جميعاً (210-D):** `close_compensation_month` إغلاقٌ واحدٌ لكلّ المنصة (فرادة على السنة والشهر وحدهما)، وحاجزُه استعلامٌ **غيرُ مقيَّدٍ بموظفٍ ولا بشركة**: أيُّ `WorkOrderDeliverable` معلَّقٍ قُدِّم خلال الشهر — في أيّ شركةٍ ولأيّ موظف — يمنع إغلاق مستحقّات الشهر للجميع. هذا سلوكٌ مقصودٌ بمقتضى «لا يُغلق فوق تسليماتٍ معلَّقةٍ بصمت»، ولكنه يعني عمليّاً أنّ مراجعةً واحدةً متأخّرةً تُجمّد رواتبَ كلّ الموظفين: فمهلةُ المراجعة لا تُنفِذ شيئاً، والعلاجُ الوحيدُ اليوم إكمالُ المراجعات. **قرارٌ معلَّقٌ عند المالك** إن أُريد حصرُ الحاجز بالموظف أو بالشركة أو إعمالُ المهلة فعلاً.
- **سطرُ التسوية يُولد `PENDING` ولا يعتمد نفسَه (210-D):** `adjust_wallet_line` تُنشئ السطرَ بحالة `PENDING` بلا `approved_by`/`approved_at`؛ الاعتمادُ فعلٌ منفصلٌ عبر `transition_wallet_line` بفاعلٍ ووقتٍ مسجَّلَين — وإلا لمنح مالكُ صلاحيةِ التسوية نفسَه مبلغاً معتمَداً بقفزةٍ فوق سلسلة الاعتماد.
- **افتراضيّاتُ التعويض تُقرأ من تعريف الحقول (210-D):** `get_default_compensation_policy_dict` تقرأ `_meta.get_field(...).default` ولا تُعيد كتابة الأرقام — وإلا صار للراتب والعمولة مصدرا حقيقةٍ اثنان، وتعديلُ الحقل وحدَه يُبقي مسارَ «لا سياسة منشورة بعد» يدفع الرقمَ القديمَ بصمت.

- **العزلُ داخل المنصّة يُقاس ببابين لا بباب (211-D):** `IsPlatformOperationsStaff` تسمح للموظّف بعشر نقاطٍ **عمداً**، فالخطرُ ليس دخولَه بل أن يرى صفَّ زميله؛ والتضييقُ سطرٌ يدويٌّ داخلَ كلّ `get_queryset`، ونسيانُه **غيرُ مرئيّ**: المسارُ يظلّ يعمل ويبدأ بإرجاع صفوف الجميع. و`core/tests/test_platform_admin.py::PlatformRouteGuardTest` لا يسدّ هذا: يُصادق **عضوَ شركةٍ عاديّاً** مرفوضاً في كلّ مكان. **والبابُ الثاني أخفى**: `DailyRatingViewSet` لائحتُه `[IsAuthenticated]` وحدها ويعيش خارجَ `/api/platform/ops/` (تحت `/api/my-agent/`)، ومع ذلك يضيّق على هويّة الموظّف في `get_queryset` — فتعدادٌ يقرأ `permission_classes` وحدَها لا يبلغه أبداً، وسقوطُ ذلك السطر يكشف شهادةَ كلّ زبونٍ على كلّ موظّف. لذلك يعدّ `test_staff_scope_guard.py` **الاثنين**.

- **القشرةُ السماويّةُ لسطح المنصّة وحدَه، وبالغلاف لا بالمكوّنات (211-K):** بقرار المالك يغطّي السماويُّ **كامل** موديول المنصّة (لوحةُ السوبر أدمن · بابُ المتابعة · مساحةُ الموظّف · الاجتماعات · الغرفة) ولا يتجاوزه إلى شاشات الزبائن. وشاشاتُ المنصّة مكتوبةٌ بأدوات Tailwind الحرفيّة — **864 استعمالاً لـslate/blue مقابل 14 للرموز الدلاليّة** — وأكثرُها في ملفّاتٍ محجوزةٍ لمهمّةٍ أخرى، فإعادةُ تعريف `--color-primary` وحدَها كانت تصبغ أربعةَ عشرَ موضعاً لا غير. **والطريقُ الأنظفُ مسدودٌ بحكم الأداة**: الأداةُ تُترجَم إلى `var(--color-slate-50)` لكنّ Tailwind v4 **يحذف** أيّ `--color-*` يُعرَّف خارج `@theme` — جُرِّب فلم تصل الكتلةُ إلى الـCSS المخدوم (صفرُ مطابقة). فالتنفيذُ تجاوزاتٌ للأدوات مقصورةٌ بـ`.platform-surface` **خارجَ الطبقات عمداً** (غيرُ المُطبَّق يغلب `@layer utilities`)، والغلافُ على **جذر كلّ شاشةٍ** فترثه لوحاتُها. يحرسه `platform_ops/tests/test_platform_skin.py`: لا قاعدةَ سُلَّمٍ خارج الغلاف، و`--color-primary` في `@theme` يبقى أزرقَ الشركات. **وسقط شطرُ «كامل الموديول» في 212-G**: مركزُ القيادة خرج من السماويّ إلى الداكن بقرار المالك، وبقي السماويُّ لما دونَه من شاشات المنصّة.

- **بوّابةُ `/staff` تنتظر جوابَ صلاحيّاتِ *هذا* المستخدم، لا «انتهاءَ نداءٍ ما»
  (212-L0):** كانت `usePlatformStaffCapabilities` تضبط `loading = false` في فرعِ «لا
  مستخدمَ بعد»، فحين تنتهي المصادقةُ يقع **رسمٌ واحد** فيه `authLoading` و`fetching`
  كلاهما كاذبٌ والجوابُ ما زال `NONE` ولم يُسأل عن أحدٍ قطّ — فيقرأ شرطُ `StaffShell`
  «ممنوع» ويطلق `<Navigate to="/" />` **قبل انطلاق النداء**، ثمّ يهبط الموظّفُ على
  شاشةِ دوره. المقيسُ من المالك: «بوديني ثانيةً على `/staff/home` وبرجع على
  `/employee-ops`». والعلاجُ حقلُ `answeredFor` (معرّفُ صاحب الجواب) وقاعدةٌ خالصةٌ
  تفرّق «لم أسأل» عن «قيل لا»؛ وهما في هذه البوّابة نقيضان: الأوّلُ انتظارٌ والثاني
  طرد. **ولا يمسك هذا اختبارٌ يصيّر المكوّن**: `npm test` هنا `node --test` على
  `utils/*.test.ts`، فالقاعدةُ مُستخرَجةٌ ليختبرها، ووصلُها بالشاشة محروسٌ ساكناً في
  `platform_ops/tests/test_employee_door.py`.
- **لوحةُ الجلد كحليّةٌ مشبَعةٌ لا فحميّةٌ محايدة (212-T):** شكا المالكُ أنّ الجلد «راح داكن لدرجة السواد» وطلب أزرق. وقِيست صورتُه المرجعيّةُ ولقطةُ الشاشة بعدّ البكسلات، فالفارقُ **ليس الإضاءة** — لوحةُ المرجع كانت **أفتحَ** (33.4 مقابل 27.2) — بل **الزُرقة**: ‎+26.5 معروضاً مقابل ‎+43.5 مرجعاً. فالسُلَّمُ كان يرفع الإضاءةَ بين الدرجات بلا صبغة، وهو ما تحذّر منه Material 3 صراحةً للأسطح الداكنة (الارتفاعُ صبغةٌ من اللون الأساسيّ لا تدرّجٌ رماديّ). صارت الرموزُ `rail #00102b` · `bg #011632` · `panel #0a2543` (قيمةُ المرجع حرفيّاً) · `line #22476f`، وصبغةُ قواعد السُلَّم `oklch` رُفعت إلى ‎0.07–0.10 عند الزاوية ‎253. **والكتلةُ تبقى مشتركةً بين `.staff-shell` و`.ops-shell`**: شقُّها يصنع سوادين مختلفين جنبَ بعضهما، فالقشرتان تتغيّران معاً بقرارٍ مبلَّغ.
- **مركزُ القيادة داكنٌ بغلافٍ ثانٍ يقرأ جلدَ الموظّف نفسَه (212-G):** بقرار المالك «بدي كل مركز القياده» داكناً كقشرة `/staff`. والتنفيذُ **صنفُ غلافٍ واحدٌ** (`ops-shell`) على جذر `PlatformOpsDashboard.tsx` بجانب `platform-surface`، ومحدِّداتُ الجلد تحمل الغلافَين معاً (`.staff-shell, .ops-shell`) فلا نسخةَ ثانيةً من اللوحة. **وثلاثةُ أشياءَ هنا تنكسر صامتةً:**
  **(أ) الترتيبُ جزءٌ من الصحّة.** الجذرُ يلبس الغلافَين، وقواعدُ سُلَّم `.platform-surface` تساوي قواعدَ الجلد نوعيّةً `(0,2,0)` — فالمتأخّرُ في الملفّ هو الفائز، وكتلةٌ تُرفع فوق السُلَّم تُعيد الشاشةَ بيضاءَ بلا أن يسقط اختبارُ صنف. يُقاس **موضعُ القواعد** لا موضعُ تعليقٍ فوقها، و**أوّلُ** قاعدةِ جلدٍ بعد **آخرِ** قاعدةِ سُلَّم — مقارنةُ الآخرِ بالآخر تمرّ على رفعِ كتلةٍ واحدة.
  **(ب) محدِّدُ السليل لا يبلغ حاملَه.** الجذرُ يكتب `bg-slate-50 text-slate-800` على **العنصر نفسِه**، وكلُّ قواعد الجلد من شكل `.ops-shell .x` — فكانت صفحةً بيضاءَ تطفو عليها بطاقاتٌ داكنة. فالأرضيّةُ ولونُ النصّ يُكتبان على `.ops-shell` مباشرةً.
  **(ج) الصنفُ ليس المصدرَ الوحيدَ للفاتح.** أرضيّاتُ قاعة العمل (`pf-room` وأخواتُها) مكتوبةٌ في `index.css` بألوانٍ حرفيّةٍ لا بأدوات Tailwind، فلا يراها مسحُ الأصناف مهما وُسِّع تعبيرُه: شارةُ المقعد بقيت `rgba(255,255,255,.92)` ونصُّها `text-slate-900` صار فاتحاً — **اسمُ الموظّف بتباينِ 1.1:1**. ومثلُها الرموزُ التي تُقرأ بأصنافِ قيمةٍ اعتباطيّة (`text-[var(--color-text)]`) والأصنافُ ذاتُ بادئةِ variant (`group-hover:`) التي كان التعبيرُ يُسقِط بادئتَها فيُرضيه تجاوزُ الصنف العاري. ولكلٍّ من الثلاثة حارسُه.
  **وتعبيرُ المسح واحدٌ للقشرتين**: `LIGHT_PANEL_CLASS` يستورد `LIGHT_PLATFORM_CLASS` — القواعدُ صارت مشتركةً، فتعبيرٌ ضيّقٌ هنا وواسعٌ هناك يترك صنفاً تلبسه لوحةٌ مشتركةٌ محروساً في قشرةٍ ومُفلتاً من الأخرى. حدث فعلاً: `PlatformNotificationBell` مركَّبٌ في `StaffTopBar` ولم يكن في أيّ تعداد، فبنفسجيُّ قائمته المنسدلة لم يره مسحٌ قطّ.

- **حضورُ الاجتماع خمسُ حالاتٍ لا بوليان، والغيابُ افتراضٌ مبدئيٌّ لا حكم (211-E):** «حضر · غائب · عذرٌ معلَّق · عذرٌ مقبول · عذرٌ مرفوض». والتمييزُ **شرطُ عدالةٍ لا ترفٌ نمذجة**: المالكُ قرّر أنّ الحضور يرفع الدرجةَ ويُنزّلها، فلو كان العذرُ بولياناً واحداً لنزّل العذرُ **المعلَّقُ** درجةَ موظّفٍ لم يُبتَّ في عذره بعد — عقوبةٌ قبل الحكم. **وصفوفُ الحضور تُنشأ سلفاً لكلّ مدعوٍّ بحالة «غائب»** لا عند أوّل تفاعل: سؤالُ المالك هو «مين ما حضر»، فاجتماعٌ بخمسةٍ وعشرين مدعوّاً وثلاثةِ حاضرين يجب أن يُظهر ٢٢ صفَّ غيابٍ صريحاً لا فراغاً يُستنتَج بطرح عددين. **و«غائب» الافتراضيّةُ حكمٌ مبدئيٌّ**: لا تُقرأ للتقييم قبل انقضاء `meeting.end`، وإلاّ عوقب من لم يحِن دورُه. **والمتبقّي على طبقة الخدمة (211-F):** منعُ تسجيل حضورٍ على اجتماعٍ ملغى — النموذجُ لا يمنعه.

- **المحفظةُ ثلاثةُ أرقامٍ لا اثنان (§٧):** `get_employee_wallet_summary` تُرجع `confirmed` و`pending` و**`expected`** — والمتوقَّعُ مشتقٌّ لا مُخترَع: المؤكَّدُ زائدَ المعلَّق، أي حصيلةُ الشهر لو تحقّق كلُّ شرطٍ ناقص. و`REVERSED` خارجَ الثلاثة: سطرٌ عُكس ليس مبلغاً يُنتظَر، ويُرسَم بلونٍ مغايرٍ مشطوبٍ في بطاقة الموظف بدل أخضر المؤكَّد.
- **فشلُ نداء القدرات يُعلَن ولا يُترجَم إلى «لا» (§٢):** `usePlatformStaffCapabilitiesState` يُرجع `failed` و`reload` بجانب `capabilities` و`loading`؛ و`WorkOrdersPanel` يعرض سبباً وزرَّ إعادةِ محاولةٍ حين يفشل النداء بدل أن تختفي أزرارُ الإنشاء والإسناد بلا تفسير — إعادةُ `NONE` صامتةً كانت تجعل انقطاعةَ شبكةٍ عابرةً تُخرج المديرَ من أفعاله حتى تحديث الصفحة.

- **الوزنُ الأصليُّ والفعليُّ يُعرضان معاً (210-D §٥، وُصلا في 210-E):** يُرجع الخادمُ `weight_original_pct` بجانب `weight_pct`، و`raw_percent` (قبل القصّ عند ١٠٠) و`uncatalogued_document_links` لمحور إنجاز العمل — وثلاثتُها لم تكن معلنةً في `PilotAxisBreakdown` فلم تعرضها شاشةٌ قطّ. تعرضها الآن `EmployeeSelfWalletCard.tsx` و`EmployeeWalletPanel.tsx` معاً: الوزنُ بصيغة «الأصلي ← الفعلي» حين يختلفان، والفائضُ فوق الطاقة سطراً تحت الدرجة، وروابطُ المستندات غيرُ المُكتلَجة تحذيراً — لأنّ الوزنَ الفعليَّ وحدَه يُخفي أنّ محوراً غيرَ منطبقٍ أُسقط وأُعيد توزيعُ وزنه.

**قيودٌ معروفةٌ مقبولةٌ للإطلاق التجريبيّ (م٨)** — قرارٌ واعٍ لا سهو، يُعاد النظرُ فيه بعد الـpilot:

- **ربطُ عميل الفوترة محروسٌ من الشاشة:** تكتب شاشة السوبر أدمن `ServiceSubscription.billing_customer` عبر خدمة الإعدادات فقط، وتُرفض قيمة من شركة الاشتراك نفسها قبل الحفظ؛ وتبقى بوابة الفوترة `billing_preflight` الحارس النهائي قبل أي فاتورة.
- **العدّادُ بلا تاريخ:** `consumed_quota` يُحسب على الدورة الجارية لحظةَ القبول، فعمليّةٌ تُقبل بين `period_end` وتشغيل الأمر تُفوتَر على الدورة المنتهية.
  لذلك يُشغَّل `bill_service_subscriptions` صباحَ أوّل يومٍ من الشهر.
- **مسؤولُ التوظيف يرى رابطَ الدعوة الخامّ** لأنّه مَن يسلّمه للمرشّح؛ فيستطيع تقنيّاً قبولَها بنفسه. الحسابُ الناتج يظهر `PlatformEmployee`
  مرتبطاً بالمتقدّم (`hired_employee`) تحت أنظار السوبر أدمن، والدعوةُ تُبطل بالرفض أو بإصدار غيرها.
- **ثلاثُ نقاطٍ يتيمةٌ من #207 تسبق #210 ولم تُمَسّ (جردُ 210-F)**: `/employees/ranking/`،
  `/employees/{id}/performance/` (المقاييس الستّة القديمة، لا تخلط مع `/pilot-performance/` الجديدة)،
  و`/performance-snapshots/` بأفعالها الثلاثة — بلا مستدعٍ من `frontend_v2` إطلاقاً. اللوحةُ الحاليّة
  ترتّب الموظفين محلّياً (`sortEmployeesWorstFirst`) واللقطاتُ الشهريّة القديمة لا شاشةَ تلتقطها يدويّاً —
  خارجَ نطاق #210 فلم تُوصَل بشاشة.

- **الربحيّةُ مؤشّرٌ منفصلٌ عن الصحّة وعن التقييم** (§٩، `platform_ops/services.py` (`compute_customer_profitability`)): الإيرادُ رسمُ الاشتراك زائدَ وحداتِ التجاوز بسعرها من `ServiceSubscription` نفسِه، والتكلفةُ البشريّةُ **تقديريّةٌ مشتقّة**: راتبُ الموظّف من `EmployeeCompensationPolicy` السارية **بلحظةٍ داخل الشهر المحسوب** مقسوماً على كلّ وحداتِه المعتمدة ذلك الشهر، مضروباً في وحدات هذه الشركة منه. موظّفٌ بصفر وحداتٍ لا يُوزَّع راتبُه على أحد (لا قسمةَ على صفر ولا تكلفةٌ تُلصَق بشركةٍ لم تستهلك منه). و**النفقاتُ المخصَّصة مُدخَلٌ لا مُشتَقّ** — لا مصدرَ لها في المستودع فتُمرَّر صراحةً وتكون صفراً حين لا تُمرَّر. والتصنيفُ الرباعيُّ بـ**نسبةِ** الهامش لا بمبلغه (`classify_profitability`)، وإيرادٌ صفريٌّ بتكلفةٍ موجبةٍ خاسرٌ لا «مراقب».
- **وحداتُ العكس تُطرح لا تُجمع:** `ServiceUsageEvent` من نوع `REVERSAL` يخزّن وحداتِه **موجبةً** كالأصل تماماً (`platform_ops/services.py` (`reverse_usage_event`))، فكلُّ تجميعٍ للوحدات يقرأ `event_type` ويُشير — وإلاّ ظهرت شركةٌ عُكست وحداتُها وقد استهلكت ضِعفَها وشُحن عليها تجاوزٌ لم يقع.
- **الاقتراحُ يُعرَض ولا يُنفَّذ** (`platform_ops/services.py` (`build_plan_fit_suggestions`)): خمسُ قواعدَ deterministic بنصّ §٩، والترقيةُ تنفصل عن شراء الوحدات **بالتكرار لا بالمقدار** — تجاوزٌ في شهرٍ يُشترى، وتجاوزٌ في شهرين متتاليين يُرقّى. و`GET` وحدَها على `/profitability/`: «الاقتراح لا ينفذ نفسه ولا يغير سعراً أو اشتراكاً دون تأكيد السوبر أدمن».
- **الربحيّةُ لمدير العمليات وحدَه** (`platform_ops/views.py` (`CustomerProfitabilityView`)): صفُّها يحمل تكلفةً مشتقّةً من الرواتب، وهي بعينها ما تمنعه §١٠ عن لوحة الموظفين — فلا `IsPlatformOperationsStaff` عليها، بخلاف `ChampionsBoardView` التي جمهورُها موظّفو المنصّة المسجَّلون.
- **KTRA Champions إيجابيّةٌ فقط** (§١٠، `platform_ops/services.py` (`build_champions_board`)): ستُّ فئاتٍ شهريّة، لا رواتبَ ولا قيمَ عمولاتٍ (الاكتسابُ **عددُ عملاءَ** لا مبلغ) ولا أسماءَ عملاء، ولا ترتيبَ للأسوأ — القمّةُ وحدَها، ولا دخولَ لمن دون حدّ العينة.

- **مستهدفان لا مستهدَف: `capacity_target` و`monthly_units_target`** (210-ز، `platform_ops/models.py` (`PlatformEmployee`) · `platform_ops/services.py` (`set_employee_targets` · `suggest_monthly_units_targets`)): الرقمان يقيسان **جنسين مختلفين**. `capacity_target` يُقارَن بمجموع وحدات حِمل الشركات المرتبطة (١/٢/٣ للشركة، `employee_capacity_snapshot`) وبعدد أوامر العمل النشطة في شريط التدخّل — آحادُه عشرات. و`monthly_units_target` سقفُ مقامِ محور الإنجاز بوحدات الكتالوج شهرياً — آحادُه مئات. وكانا حقلاً واحداً حتى 210-ز، فقيمةٌ صالحةٌ لأحد السُلَّمين تُعطّل الآخرَ بصمت: قيمةُ إسنادٍ معقولةٌ (١٠) تقصّ المقامَ إلى عشرِ وحداتٍ فترفع الدرجةَ بلا عملٍ إضافيّ، وقيمةُ وحداتٍ معقولةٌ (٢٠٠) تُطفئ حارسَ الإسناد وكاشفَ الحمل الزائد إلى الأبد. وصفرُ كلٍّ منهما يبقى «لم يُضبط» لا «طاقة صفر».
- **المستهدَفُ سقفٌ على المقام، وعيّنتُه من جنس المقام** (`platform_ops/services.py` (`suggest_monthly_units_targets` · `assigned_eligible_units_by_employee`)): `min(monthly_units_target, assigned_eligible_units)` — فرقمٌ أصغرُ يعني مقاماً أصغرَ ودرجةً **أعلى** على العمل نفسِه، ورقمٌ يفوق المُسنَدَ ذلك الشهرَ لا أثرَ له. ولذلك تُقاس المقاديرُ الثلاثةُ بوحدات العمل **المُسنَد** (`received_at` على أوامر العمل، بالدالّة التي يستدعيها المحورُ نفسُه) لا بالوحدات المعتمَدة: المعتمَدُ بسطٌ يقع دائماً دون المقام، فاقتراحٌ مبنيٌّ عليه يَربِط عبر `min()` في كلّ شهرٍ ويرفع كلَّ درجةٍ بلا عملٍ إضافيٍّ واحد.
- **ومشتقّةٌ من إنتاجٍ وقع لا من ثوابتَ مخترَعة**: الأدنى أضعفُ أشهر الموظّف المكتملة والمتوسّطُ وسيطُها والأعلى أقواها (`basis="self"`)؛ وموظّفٌ بلا تاريخٍ يستعير توزيعَ زملائه للأشهر نفسِها (`basis="peers"`)؛ ومنصّةٌ بلا تاريخٍ تُعيد `targets=None` بـ`basis="no_history"` — **لا تُخترع أرقامٌ لمقامِ درجةٍ تقرّر راتباً**. والشهرُ الجاري ناقصٌ فلا يُقاس عليه. والضبطُ لمدير العمليات وحدَه (`manager_only`) لأنّ من يخفض مقامَه يرفع درجتَه؛ والقراءةُ لصاحبها عبر تضييق `get_queryset` **لكنّ المقاديرَ تصله `null`** لأنّ بديلَ الزملاء يشتقّها من إنتاج غيره (§١٠). وكلُّ تغييرٍ يُسجَّل بـ«قبلُ وبعدُ» داخلَ المعاملة في `PlatformActivityLog` (`entity_type="employee_targets"`).
- **والمستهدَفُ يُجمَّد مع اللقطة كما تُجمَّد الأوزان** (`capture_pilot_performance_snapshot`): يُكتب في `policy_snapshot["monthly_units_target"]` ويُقرأ منه عند إعادة الالتقاط، فلا يُعيد ضبطُ مستهدَفٍ اليومَ تسعيرَ شهرٍ أُغلق ودُفع — وهو «لا أثر رجعي» (210-د) الذي صار بلوغُه نقرةً منذ أن صارت إعادةُ الالتقاط زرّاً (210-و).

- **قبولُ الاعتراض خطوتان لا واحدة** (`platform_ops/services.py` (`resolve_performance_review` · `recapture_performance_after_accepted_review`)): الردُّ بالقبول **لا يمسّ الدرجةَ إطلاقاً** — وإلاّ صار الاعتراضُ باباً خلفيّاً يرفع به الموظّفُ درجتَه. فالتصحيحُ يقع عند المصدر (رابطٌ يُعاد تقييمُه، حدثُ استخدامٍ يُعكس، تصنيفُ رفضٍ يُصحَّح) ثمّ **تُعاد اللقطة** عبر `POST /performance-review-requests/{pk}/recapture/`. وهذه النقطةُ مقيَّدةٌ بالمبرِّر لا بالرتبة وحدَها: طلبٌ **مقبولٌ** على الشهر نفسِه شرطُ قبولها (`review_request_not_accepted` وإلاّ)، ولا تمسّ المحفظةَ — أسطرُ الشهر قد تكون `PAID` وبابُ تصحيحها الظاهرُ `adjust_wallet_line` بسطر تسويةٍ يُرى. وقبل 210-F لم يكن لـ«تُعاد اللقطة» مسارٌ واحدٌ في النظام: `force_refresh` لا يستدعيها إلا الإغلاق، والإغلاقُ idempotent فلا يُعيد الحساب — فكان القبولُ وعداً بلا أثرٍ إلى الأبد.

- **حضورُ الاجتماع يُشتقّ من الجلسة ويُقيَّد بنافذةٍ** (211-F، `platform_ops/services.py` (`check_in_to_meeting` · `submit_meeting_excuse`) · `platform_ops/views.py` (`PlatformMeetingViewSet`)): الموظّفُ يأتي من `request.user` لا من معاملٍ في الحمولة — فلا سبيلَ لتسجيل حضورٍ باسم زميل؛ والاجتماعُ يمرّ عبر `get_queryset` المضيَّقة فيردّ 404 على اجتماعٍ لم يُدعَ إليه **قبل** بلوغ الخدمة. والنافذةُ من `start − 15` دقيقةً حتى `end` (`MEETING_CHECK_IN_EARLY_WINDOW_MINUTES`) هي ما يمنح الدفترَ معناه: بدونها يسجّل الموظّفُ اليومَ حضورَ اجتماعِ الشهر القادم. والاعتذارُ يكتب `excused_pending` **دائماً** ولا يكتب `excused_accepted` من أيّ مسارٍ يملكه الموظّف — القبولُ فعلُ المدير وحدَه؛ واعتذارٌ جديدٌ يمحو بتّاً سابقاً فلا يرث قراراً على نصٍّ مختلف.
- **دعوةُ المدعوّين تتخطّى المصطدمَ وحدَه** (`platform_ops/services.py` (`invite_employees_to_meeting`)): `bulk_create(..., ignore_conflicts=True)` لا التقاطُ `IntegrityError` حول الدفعة — فالالتقاطُ يتراجع عن **العبارة بتمامها**، ومدعوٌّ واحدٌ مصطدمٌ من خمسةٍ يُضيع الأربعةَ الباقين بصمتٍ والطلبُ ناجح.
- **الإلغاءُ يُقيَّد على دفتر كلِّ مدعوٍّ** (`cancel_platform_meeting`): `PlatformActivityLog` يلزمه موظّفٌ والمديرُ الملغي قد لا يملك ملفَّ موظّفٍ، فالفاعلُ في `details.actor_user_id` كما في بتّ الأعذار؛ والمدعوُّ يرى أنّ اجتماعَه أُلغي بدل أن يجد اجتماعاً صامتاً يرفض دخولَه. والتكرارُ لا يكتب سجلّاً ثانياً.

- **الغرفةُ تعرض كلَّ الموظّفين لا المفلترين، والضوءُ لا يُخترَع** (211-I، `frontend_v2/components/platform/PlatformOpsDashboard.tsx` · `frontend_v2/utils/roomPresence.ts`): سكّانُ الغرفة من `data.employees` كاملةً لا من `filteredEmployees` — الغرفةُ لوحةُ حضورٍ لا نتيجةَ بحث، وإخفاءُ زميلٍ لأنّ كلمةَ بحثٍ لا تطابقه يجعل «من يعمل الآن» كذبة. و«في اجتماع» (211-H) من `is_in_meeting` الذي تحسبه `get_platform_dashboard_summary` خادميّاً من دفتر حضور الاجتماعات، **لا اشتقاقاً محلّيّاً من النشاط**: ضوءٌ أصفرُ مشتقٌّ من النشاط وحدَه كذبٌ على قارئ اللوحة. وكان يُمرَّر `null` صراحةً حتى 211-H لأنّ الحمولةَ لم تكن تحمل العَلَم.
- **هندسةُ الغرفة مقيسةٌ لا مُخمَّنة** (`platform_ops/tests/test_workspace_room.py`): `npm test` هنا لا يُصيّر مكوّناً و`tsc` لا يرى صنف CSS، فالتراكبُ الذي يُخفي اسمَ موظّفٍ لا تمسكه أيُّ بوّابةٍ إلاّ حارسٌ ساكنٌ يقرأ `WorkspaceRoom.tsx` و`index.css` معاً ويُعيد حسابَ الصناديق على ثلاثة عشر عرضاً. ونموذجُه (عرضُ البطاقة ومقدارُ ارتفاعها لكلّ وحدة عمق) مقيسٌ في متصفّحٍ حقيقيّ، **وثوابتُه مقابَلةٌ بالقواعد نفسِها** — وإلاّ بقيت صورةً لِما كان فبقي الحارسُ أخضرَ على تراكبٍ عاد.

- **«غاب» حالةٌ لا طرح، ونافذةُ الدخول تلميحٌ لا قفل** (211-G، `frontend_v2/utils/meetingAttendanceTally.ts` · `frontend_v2/components/platform/MyMeetingsPanel.tsx`): عدُّ الغياب `absent` وحدَها؛ و`total - attended` يلصق صفةَ الغياب بصاحب العذر **المقبول** وبمن لم يُبتَّ في عذره — وهو بعينه الخلطُ الذي فُصلت لأجله الحالاتُ الخمس في 211-E، ودرجةُ الحضور تدخل تسعيرَ راتب. وزرُّ تسجيل الدخول **لا يُعطَّل بحساب ساعة المتصفّح**: ساعةُ جهازٍ مغلوطةٌ بساعةٍ واحدةٍ تحبس الموظّفَ خارجَ اجتماعه بلا مخرج، والخادمُ — وساعتُه هي المرجع — يردّ `outside_check_in_window` برسالةٍ صريحة. أسوأُ ما يقع طلبٌ ضائع، وأسوأُ البديل حضورٌ ضائع.

- **المسمّى الوظيفيُّ ليس التخصّص** (211-Q، `platform_ops/models.py` — `PlatformEmployee`): `specialty` **مفتاحُ سياسة** يُطابَق بـ`PolicyProfile.specialty` في احتساب الأداء، فتغييرُه ليقرأ أجملَ على اللوحة **يبدّل سياسةَ تقييم الموظّف بصمت** ودرجتُه مالٌ في محفظته. `job_title` عرضٌ صِرفٌ بلا أثرٍ حسابيّ، وهو ما يُكتب على وجه الموظّف في الغرفة والبطاقة.
- **القيدُ المُعلَن في النموذج يُنفَّذ صراحةً في الخدمة** (211-Q، `platform_ops/services.py` — `set_employee_profile_card`): `save()` لا يستدعي المدقّقات، فيبقى `max_length` و`URLField` توثيقاً لا حارساً. وSQLite في الاختبارات يبتلع القيمةَ الطويلةَ صامتاً بينما MySQL يردّ 1406 في وجه المستخدم — فالبوّابةُ تمرّ خضراءَ هنا والعطبُ يقع هناك. تُشغَّل `field.clean(...)` فيُردّ 400 برسالةٍ عربيّة.
- **«في اجتماعٍ الآن» حضورٌ فعليٌّ داخلَ نافذة الاجتماع، لا دعوةٌ ولا نافذةُ دخول** (211-H، `platform_ops/services.py` — `get_platform_dashboard_summary`): `is_in_meeting` يعني صفَّ حضورٍ حالتُه `ATTENDED` على اجتماعٍ **غيرِ ملغىً** نافذتُه الحقيقيّةُ `start <= now <= end` تشمل اللحظة. وكلُّ قيدٍ من الثلاثة يُسقط اللوحةَ في كذبةٍ مختلفةٍ لو غاب: صفوفُ الحضور **تُنشأ سلفاً لكلّ مدعوٍّ بحالة «غائب»** (211-E) فالعدُّ بالدعوة يُشعل الأصفرَ في وجه من لم يحضر إطلاقاً؛ و`MEETING_CHECK_IN_EARLY_WINDOW_MINUTES` نافذةُ **السماح بالتسجيل** لا «هو في الاجتماع»، فمن سجّل قبل الموعد بعشر دقائق ليس مجتمعاً بعد؛ والملغى يُستثنى بالمطابقة نفسِها التي يستعملها `check_in_to_meeting`. **والحدّان شاملان** (`now == start` و`now == end` كلاهما داخلَ الاجتماع) مطابقةً لرفض `check_in_to_meeting` بـ`now > end`. ويُبنى العَلَمُ **باستعلامٍ واحدٍ قبل الحلقة** كما تُبنى `last_active_by_user` — لوحةٌ تُفتَح كلَّ دقيقةٍ على عشرات البطاقات، واستعلامٌ لكلّ صفٍّ هو بعينه العيبُ المتكرّر هنا.
- **الحقلُ الذي لا يصل حمولةَ اللوحة لا يُرى** (211-Q، `platform_ops/services.py` — `get_platform_dashboard_summary`): الغرفةُ وبطاقةُ الموظّف تُرسمان من حمولة اللوحة لا من نقطة الموظّف، فصورةٌ مرفوعةٌ وغائبةٌ عن تلك الحمولة تبقى وجهاً بأحرفٍ أولى على المقعد. و**الصورةُ تُوضَع داخلَ دائرة الوجه نفسِها** فلا يتغيّر صندوقُ البطاقة ولا تبطل هندسةُ الغرفة المقيسة.

- **لوحةُ عمليات كترا لا تعرض رقمَ مالٍ مخترَعاً** (211-S): نموذجُ المالك البصريُّ يعرض «مبيعات اليوم» لأنّه رسمُ شركةِ زبون، وحمولةُ `get_platform_dashboard_summary` لا تحمل مبيعاتٍ يوميّةً ولا إيراداً. رقمٌ يُخترَع هنا كذبةٌ على لوحةِ قرار، ويحرس ذلك `test_dashboard_shell_contract.py` بمنع ألفاظ المال في المكوّنات الثلاثة.
- **البطاقةُ لا تُرسَم قبل وصول حمولتها** (211-S، `PlatformOpsDashboard.tsx`): المجاميعُ تُحسب من `data.employees`، فحمولةٌ لم تصل — أو فشل تحميلُها — تعطي صفراً بخطٍّ عريضٍ يُقرأ «لا أمرَ عملٍ متأخّراً». والغيابُ أصدقُ من رقمٍ لم يُحسَب.

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
| `platform_ops/tests/test_job_share_page.py` (#214-أ) | صفحةُ الإعلان المُصيَّرةُ من الخادم — **كلُّ تأكيدٍ فيها يقيس نصَّ الردّ الخامّ لا حالةَ المتصفّح**: العنوانُ والوصفُ يخصّان الوظيفة لا المنصّة، الوصفُ سطرٌ واحدٌ مقطوعٌ عند حدٍّ معلوم، الصفحةُ تُقرأ بلا JavaScript وبلا دخول، الرابطُ المنسوخُ ليس مسارَ SPA، الـJSON-LD **يُحلَّل بـ`json.loads` فعلاً** (تهريبُ القالب التلقائيُّ كان يقلبه نصّاً يتجاهله جوجل بلا رسالة)، «عقد» تُسمّى `CONTRACTOR` لا `CONTRACT`، وصفٌ يحمل `</script>` لا يكسر الوسم، حقلٌ فارغٌ يُحذف من المخطَّط لا يُكتب فارغاً، ورابطٌ مغلقٌ يردّ 410 **بلا أيّ وسمِ معاينة** |
| `platform_ops/tests/test_pay_terms_note.py` (#214-ج، البلاغ الثاني) | شرحُ شروط الصرف: يصل صاحبَه بفقراته، وفارغٌ لا غائبٌ قبل أوّل نشر، **ويسافر مع النسخة** التي تحمل أرقامَه (خاصّةٌ تغلب عامّةً بشرحها معها)، وزميلٌ لا يقرأ شرحَ زميل، ومحوُه فعلٌ مقبولٌ كإثباته، والاستنساخُ يحمله، والطويلُ يُقَصّ، وتعديلُه يُسجَّل في دفتر التدقيق — **ولا يختلط بـ`activation_reason`**: ذاك للمدقّق وهذا للموظّف |
| `platform_ops/tests/test_pay_terms_and_invitation_note.py` (#214-ج · #214-د) | شروطُ الأجر: الافتراضاتُ قبل أوّل نشر، سياسةُ المنصّة، وسياسةٌ باسم الموظّف تغلبها، **ومساواةُ ما يُعرَض بما يحتسب به المحرّك** (مصدرٌ واحدٌ لا نسختان)، والمبالغُ نصوصٌ لا أرقامٌ مُعرَّبة، وزميلٌ لا يخرج له رقمٌ عن زميله. والدعوة: الشرحُ ورقمُ التواصل يظهران قبل الدخول، الفقراتُ تُحفَظ، دعوةٌ بلا شرحٍ تبقى صالحة، **وملاحظاتُ الفرز الداخليّةُ لا تتسرّب للمدعوّ**، وشرحٌ طويلٌ يُقَصّ ولا يُسقِط الدعوة |

| `platform_ops/tests/test_subscription_billing.py` | فوترة الاشتراكات الشهرية: الحساب وفصل السطور وترحيل الفواتير وعدم التكرار والذرية وعزل الشركات وسلامة الحقول، والدورة الصفرية بلا فاتورة، ورفض عميل من شركة الاشتراك، والمعاينة تساوي التشغيل و`CommandError` |
| `platform_ops/tests/test_subscription_management.py` | جدول انتقالات كامل (تجربة/تفعيل مدفوع/تعليق/استئناف/إلغاء مجدول أو فوري/سحب الجدولة)، تجربة واحدة مدى الحياة، انتهاء التجربة يُسقط الأهلية، رفض فوترة `trial`، تطبيق الإلغاء المجدول مرة واحدة idempotent، تعارض تفعيل متزامن 409، عزل عميل الفوترة وبحثه بشركة فوترة الاشتراك الملتقطة، عميل الفوترة إلزامي للتفعيل المدفوع، الإلغاء في شهر التفعيل قبل أول دورة، حدث واحد بمعرّف ارتباط لكل إجراء اشتراك وسياسة، قاعدة نسخة السياسة النشطة الواحدة ومعاينة الفروق بالمال نصاً، خروج التجربة المنتهية والملغى من أوامر العمل والصحة للدورين، صلاحيات 403 لغير السوبر أدمن (بمن فيهم موظف المنصة) على كل مسار، وعقد API الواجهة |
| `platform_ops/tests/test_daily_ratings_and_books.py` | العمل الفعلي شرطاً، انتهاء الرمز بـ410، التعديل الواحد، عدم حفظ الرمز الخام، القائمة البيضاء للرد العام، الخانق بـ429 مع ترويسة مزوَّرة، استبعاد العرض والدخول، عزل الشركة، اشتقاق الوكيل من `Engagement` حصراً، فصل الدرجتين، ومنع المُقيَّم من تعديل تقييمه أو حذفه |
| `platform_ops/tests/test_hiring_portal.py` | بوابة التوظيف والسطح الإداري (`PlatformHiringAdminSurfaceTests`): النماذج بلا `tenant`، فحص السيرة بالبايتات والبنية، التقديم العام، 410 للمغلق، تهشير رمز الدعوة، إنشاء الحساب عند القبول لا قبله، منع تحريك الحالة بكتابة مباشرة، رفض حذف إعلان له متقدمون، تمرير بايتات السيرة بلا تسليم رابط التخزين، عزل دور التوظيف عن كل مسارات المنصة، وجرد السطح العام بخانقه ومصادقته، ورفض المتقدم يبطل الدعوة، و`PATCH is_open` متجاهل، واسم السيرة العربي `filename*=`، وقوة كلمة المرور وسباق اسم المستخدم |
| `platform_ops/tests/test_applicant_meetings.py` | اجتماعاتُ المتقدّمين (212-S1): نافذةُ الاجتماع على القاعدة وفي الخدمة معاً، وهويّةُ الحاضر الواحدة (لا الاثنان ولا لا شيء)، ومنعُ تكراره، ومنعُ إضافة من وُظِّف **لحظةَ الإضافة وحدَها** (فالفحصُ الرجعيُّ يمحو تاريخاً)، واستقلالُ الملاحظة عن الحضور، و«مدعوّ» افتراضاً لا «غائب»، ومنعُ الكتابة على حاضرِ اجتماعٍ آخر بمعرّفٍ مخمَّن، وعدمُ تسريب `cv_url` من الباب الجديد. وحرّاسٌ ساكنةٌ على ما لا يقرؤه `tsc`: نافذةُ الاجتماع تُحوَّل قبل أن تُقارَن (طرفٌ نصٌّ من الشبكة وطرفٌ `datetime` من الصفّ ⇒ خمسمئة)، ومنتقي المتقدّمين يخفي **الحالةَ نفسَها** التي ترفضها `add_meeting_attendee` |
| `platform_ops/tests/test_hiring_frontend_contract.py` | حارس العقد بين واجهات التوظيف والفوترة بالـ frontend وحمولات الخادم الحقيقية للـ 15 واجهة، ومطابقة `APPLICANT_STATUS_OPTIONS`/`EMPLOYMENT_TYPE_OPTIONS` لـ`choices` الخادم |
| `platform_ops/tests/test_employee_space_surfaces.py` (210-E) | القصص ٣٩ و٤٠ و٤٤: المتبقّي لا يكون سالباً والتجاوزُ رقمٌ مستقلّ، وبنودُ الزميل وبنودُ المسودّة والبنودُ السليمة لا تُعرَض، ورفضُ معرّفِ شركةٍ من الطلب بـ400، والسببُ إلزاميّ، وطلبٌ مفتوحٌ واحدٌ لكلّ فترة، وطلبٌ جديدٌ مسموحٌ بعد الردّ، ولا ردَّ مرّتين، والموظّفُ لا يردّ على اعتراضِ نفسِه (403) |
| `platform_ops/tests/test_employee_space_frontend_contract.py` (210-E) | مطابقةُ `MyPlatformEmployeeProfile` لحقول `PlatformEmployeeSerializer`، وأنّ الصفَّ يُنتقى بمطابقة هويّة المستخدم لا بـ`rows[0]` — العزلُ الخادميُّ سليمٌ والهويّةُ هي ما كان يَضيع |
| `platform_ops/tests/test_wallet_expected_total.py` (210-E) | «متوقَّع» = المؤكَّد + المعلَّق، و`REVERSED` خارجَه؛ وأنّ واجهةَ `totals` تعلن `expected` |
| `platform_ops/tests/test_pilot_axes_frontend_contract.py` (210-E) | حارس العقد بين `PilotAxisBreakdown` وحمولة محاور الـpilot الحقيقية: **كلُّ** مفتاحٍ يُرجعه `calculate_employee_pilot_performance` لكلّ محورٍ معلَنٌ في الواجهة — أمسك أنّ `weight_original`/`weight_original_pct`/`raw_percent`/`uncatalogued_document_links` كانت تصل ولا تُقرأ |
| `platform_ops/tests/test_integration_keys_frontend_contract.py` (210-E) | حارس العقد بين `IntegrationKeyRow`/`IntegrationKeyIssuedRow` وحمولة `IntegrationKeySerializer` الحقيقية، وتغطية خيارات `Channel` كاملةً، وأنّ `raw_token` لا يظهر على واجهة الصفّ المخزَّن |
| `platform_ops/tests/test_pilot_performance_wallet.py` (210-D) | دورة حياة سياستَي التقييم والتعويض (مسودة/استنساخ/معاينة/تفعيل ورفض مجموع أوزانٍ لا يساوي 100%)، حساب المحاور الأربعة وتجميد لقطتها بعد تعديل السياسة، الإغلاق الشهري: العميل يستحق ثلاثة أسطر عمولة مؤهَّلة ثم صفراً في الرابع، `PENDING` بسببٍ صريح حين لا يُسجَّل الدفع، عدم تكرار أي سطر عند إغلاقٍ مكرَّر، منع الإغلاق بتسليماتٍ معلَّقة مُقدَّمة ضمن الشهر، وسطح الـAPI (403/201/200 وعزل الموظف عن محفظة غيره) |
| `platform_ops/tests/test_champions_board.py` (210-E) | لوحةُ Champions: الفئاتُ الستّ، الاكتسابُ عدداً لا مبلغاً، حدُّ العيّنة يمنع الدخول، لا رواتبَ ولا أسماءَ عملاءَ في الحمولة، والتحسُّنُ فرقٌ موثَّقٌ عن لقطة الشهر السابق |
| `platform_ops/tests/test_customer_profitability.py` (210-E) | الربحيّة: الإيرادُ رسمٌ + تجاوزٌ بسعر الاشتراك، الراتبُ يُقسَّم على **كلّ** إنتاج الشهر لا على إنتاج شركةٍ واحدة، موظّفٌ بلا وحداتٍ لا يكلّف أحداً، `REVERSAL` يطرح فلا يُشحن تجاوزٌ لم يقع، الشهرُ مدىً محلّيٌّ صريحٌ لا `__month`، التصنيفُ بالنسبة لا بالمبلغ، النفقاتُ المخصَّصةُ صفرٌ حتى تُمرَّر، والاقتراحُ لا يغيّر اشتراكاً و`POST` مرفوضةٌ بـ405 |
| `frontend_v2/e2e/platform-ops-full-journey.spec.ts` (210-F) | البوّابةُ التي لا يسمّيها `package.json`: الرحلةُ الأعلى بشبكةٍ مموَّهةٍ بالكامل — تفعيلُ الخدمة (تجربة) ← أمرُ عملٍ ← ربطُ مستندٍ ← تسليمٌ ← اعتمادٌ يولّد حدثَ استخدامٍ ← ظهورُه في دفتر الاستخدام ← محاورُ التقييم ومحفظةُ الموظّف بأرقامها الثلاثة ← Champions ← الربحيّة، ومساحةُ الموظّف: حالةُ تحميلٍ صريحةٌ ثم رفضٌ صريحٌ لغير المخوَّل (لا وميضَ «ممنوع» في أوّل رسم) |
| `platform_ops/tests/test_full_journey.py` (210-F) | الرحلةُ عبر الطبقات **الحقيقيّة** لا mock: اعتمادٌ يولّد وحدةً، والوحدةُ تدخل محورَ الإنجاز ببسطٍ هو وحداتُ الدفتر عينُها، والإغلاقُ يلتقط اللقطةَ ويولّد المحفظةَ وهو idempotent، وChampions والربحيّةُ يقرآن ما تولّد؛ والعكسُ يفكّ السلسلةَ نفسَها. ويحمل **حارسَ نصوص الـE2E**: كلُّ تسميةٍ في `platform-ops-full-journey.spec.ts` تُقابَل بثوابت الخادم — أمسك عند كتابته فئتين مُخترَعتين تماماً وتسميتين تخالفان الخادم، والاختبارُ المُموَّهُ أخضرُ عليها |
| `platform_ops/tests/test_review_recapture.py` (210-F) | إعادةُ اللقطة بعد قبول الاعتراض: لا تُعاد إلا بطلبٍ **مقبول** (مفتوحٌ أو مرفوضٌ ⇒ `review_request_not_accepted`)، وتُحدَّث اللقطةُ نفسُها لا تُنشأ ثانيةٌ تنافسها، وتقرأ التصحيحَ عند المصدر لا الرقمَ القديم، وتُسجَّل بـ«قبلُ وبعدُ» في `PlatformActivityLog`، **ولا تمسّ المحفظة**، والنقطةُ لمدير العمليات وحدَه |
| `platform_ops/tests/test_employee_door.py` (211 م١) | بابُ الموظّف من الدعوة إلى مساحته: الرمزُ العائدُ من القبول يفتح نقطةً مصادَقاً عليها فعلاً ويُسجَّل جهازاً باسم صاحبه، ورابطٌ مستهلَكٌ لا يُصدر جلسةً ثانية، والدخولُ يقبل اسمَ المستخدم كما يقبل البريد؛ وحرّاسٌ ساكنون على الواجهة: حقلُ الهويّة ليس `type="email"`، وشاشةُ الدعوة تحفظ الجلسةَ بمفتاحَي الدخول نفسِهما، ومسارُ `/staff` مسجَّلٌ **خارجَ شجرة المزوّدات** ويقصد مساحةَ الموظّف **وغيرُ معلَنٍ** في صفحة الهبوط ولا في الشريط العام |
| `platform_ops/tests/test_staff_scope_guard.py` (211-D) | عزلُ موظّف المنصّة عن زميله: **تعدادان لا واحد** — مساراتُ `/api/platform/ops/` التي تقبل `IsPlatformOperationsStaff` في لائحتها، و**الـviews التي تفرّق على هويّة الموظّف داخلَ جسمها** وإن كانت لائحتُها `[IsAuthenticated]`؛ ولكلّ مسارٍ في التعدادين مصيرٌ صريح (يُنفَّذ أو يُستثنى بسبب) فلا يمرّ مسارٌ جديدٌ بلا قرار |
| `platform_ops/tests/test_platform_skin.py` (211-K · 212-G) | قشرةُ المنصّة مقصورةٌ عليها: كلُّ شاشةٍ جذريّةٍ تحمل `platform-surface`، و**لا قاعدةَ سُلَّمِ لونٍ خارجَ الغلاف** — وتُقرأ **مقدِّمةُ كلّ كتلةٍ** لا الأسطرُ الحاملةُ للقوس، فمحدِّدٌ بلا غلافٍ في مجموعةٍ على سطرَين كان يمرّ صامتاً — و`--color-primary` في `@theme` يبقى أزرقَ الشركات، وأضواءُ الحالة الثلاثةُ معرَّفةٌ رمزاً واحداً. **و212-G يضيف جلدَ القيادة**: الجذرُ يصبغ أرضيّتَه بنفسه (محدِّدُ السليل لا يبلغ حاملَه)، وكلُّ صنفٍ فاتحٍ تلبسه الاثنان وأربعون ملفّاً له تجاوزٌ **ببادئة الـvariant كاملةً**، والرموزُ تُشتقّ من `--staff-*` لا تُعرَّف بأيّ قيمةٍ (`--ktra-field: white` كان يمرّ)، وأرضيّاتُ قاعة العمل المكتوبةُ بألوانٍ حرفيّةٍ لها نظائرُ داكنة، وأوّلُ قاعدةِ جلدٍ بعد آخرِ قاعدةِ سُلَّم. **و212-T يحرس اللونَ نفسَه**: كلُّ سطحٍ في لوحة الجلد زُرقتُه (`B − (R+G)/2`) ≥ ‎+30، والسُلَّمُ مرتَّبٌ وفروقُه ≥ ‎4 فلا تذوب البطاقةُ في أرضيّتها، ونصُّ المتن ‎7:1 على اللوحة والثانويُّ ‎4.5:1 — وهو ما لم يكن محروساً فانزلقت اللوحةُ إلى رماديٍّ محايدٍ والمجموعةُ خضراءُ بكاملها |
| `platform_ops/tests/test_meetings.py` (211-E) | فرادةُ (اجتماع، موظّف) بقيدٍ حقيقيٍّ لا بالعُرف (صفٌّ ثانٍ يضاعف وزنَ الموظّف في محورٍ يقرّر راتباً)، والحالاتُ الخمسُ تتمايز بمرشِّحٍ واحدٍ فلا يتسلّل المعلَّقُ إلى بُقعة المقبول، والملغى يُستعلَم عنه، وبدايةٌ بعد نهايةٍ تسقط بـ`CheckConstraint` لا بـ`clean()` (فـ`clean()` لا يحمي `bulk_create`) |
| `platform_ops/tests/test_meeting_flow.py` (211-F) | تدفّقُ الاجتماع فوق النموذجَين: الدخولُ يعيد الرابطَ ويقلب الصفَّ إلى «حاضر»، ولا دخولَ على ملغىً ولا قبل النافذة ولا بعد النهاية (والحدُّ المبكّرُ بالضبط يمرّ)، ولا دخولَ باسم زميلٍ بأيّ معامل، والاعتذارُ معلَّقٌ دوماً ولا يبلغ «مقبولاً» من أيّ مسارٍ يملكه الموظّف، والبتُّ لا يقع مرّتين ولا يقع من موظّف؛ و**دعوةٌ مختلطةٌ يصطدم أحدُها لا تُضيع الباقين** (سباقٌ محاكىً بإعماء القراءة المسبقة)، والإلغاءُ يكتب سجلّاً لكلّ مدعوٍّ بالفاعل ولا يكرّره |
| `platform_ops/tests/test_choices_fit_columns.py` (211-E) | **كلُّ قيمةِ `choices` تسع في عمودها** — الأطولُ يُقتطَع في MySQL بصمتٍ فيسقط القيدُ كلُّه، **و‏SQLite لا تعيد إنتاجَه** لأنّها لا تفرض `max_length`؛ فالمجموعةُ تمرّ خضراء على خللٍ لا يظهر إلاّ في الإنتاج. حارسٌ ساكنٌ على الوحدة كلِّها |
| `platform_ops/tests/test_meetings_frontend_contract.py` (211-G) | عقدُ شاشتَي الاجتماعات: مفاتيحُ المُسلسِلَين مطابقةٌ **تماماً** لواجهتَي TypeScript، وتسمياتُ الحالتين مطابقةٌ لخيارات النماذج، والنقاطُ العشرُ كلُّها مُعلَنة، وثابتُ نافذة الدخول مقروءٌ من `platform_ops/services.py`. وحارسان سلوكيّان: عدُّ الغياب يمرّ بالدالّة الخالصة (فحصُ **موضع النداء** لا الاستيراد — استيرادٌ باقٍ فوق حسابٍ يدويٍّ عاد يُرضي أيَّ فحصِ تضمينٍ ساذج) ولا أثرَ لطرح الحاضرين، ولا زرَّ في شاشة الموظّف مُعطَّلاً بتعبيرٍ يذكر نافذةَ الساعة |
| `platform_ops/tests/test_room_meeting_light.py` (211-H) | الضوءُ الأصفر: حاضرٌ في اجتماعٍ جارٍ ⇒ صحيح، و**مدعوٌّ لم يحضر** ⇒ خطأ (أهمُّها: بلا هذا التمييز يصير الأصفرُ «مدعوّاً» لا «حاضراً»)، والمنتهي والملغى وما لم يبدأ بعدُ وإن كان داخلَ نافذة الدخول المبكّرة ⇒ خطأ، والحدّان `now == start` و`now == end` ⇒ صحيح. وعدُّ استعلام العضويّة **مطلقٌ (١) بموظّفٍ واحدٍ وبخمسة** لا موازنةَ تشغيلٍ بتشغيل — تلك لا تستطيع السقوط |
| `platform_ops/tests/test_dashboard_shell_contract.py` (211-S) | شكلُ اللوحة: كلُّ رقمٍ في الشريط العلويّ مشتقٌّ من مفتاحٍ **موجودٍ فعلاً** في `get_platform_dashboard_summary` (يُقرأ مصدرُ الدالّة نفسِه)، ولا لفظَ مالٍ في المكوّنات الثلاثة، والدوناتُ محروسةٌ من مقامٍ صفريّ، و`capacity_target == 0` مُعامَلٌ «لم تُضبط»، والفائضُ فوق المئة يبقى في الرقم وإن قُصّ الشريط، والمكوّناتُ **مركَّبةٌ لا مستوردةً**، والشريطُ السفليُّ `md:hidden` وصفُّ التبويبات `hidden md:inline-flex` فلا يظهران معاً، والبطاقاتُ لا تُرسَم قبل وصول الحمولة |
| `platform_ops/tests/test_employee_profile_card.py` (211-Q) | بابا البطاقة: المديرُ يضبط الثلاثة، والموظّفُ صورتَه وهاتفَه، ومحاولتُه المسمّى تُرَدّ 403 **والقيمةُ في القاعدة لم تتغيّر** (لا الردُّ وحدَه)، وصفُّ زميلٍ 404 لا 403؛ والقيمُ المخالفةُ للقيد (هاتفٌ أطولُ من العمود، مسمّى أطول، رابطٌ ليس رابطاً) تُرَدّ 400 ولا تُخزَّن، والفراغُ يمسح الصورة؛ والرفعُ ينادي الخدمةَ المشتركةَ بـ`tenant=None` ويحفظ الرابط؛ و**حمولةُ اللوحة تحمل الصورةَ والمسمّى** وإلاّ لم يرَهما أحد |
| `platform_ops/tests/test_tasks_ui_contract.py` (212-E2) | عقدُ الواجهة ساكناً: مسارات 212-E **معدودةً من الـURLconf نفسِه** ← دالّةٌ في العميل ← **نداءٌ من مكوّن** · اللوحتان مركَّبتان فعلاً (نهايةُ قسم `tasks:` مشتقّةٌ من الشكل لا مثبَّتةٌ على اسم مفتاحٍ تالٍ) · حقلُ ملاحظات المراجعة إلزاميّ · الموظّفُ يرى القرارَ وملاحظتَه في سجلٍّ لا يزول بزوال الإسناد · `claimed_count` في المُسلسِل **وفي البطاقة** · لا حوارَ متصفّحٍ ولا نمطٍ سطريٍّ ولا `toLocale*` ولا سطحٍ فاتحٍ في القشرة الداكنة |
| `platform_ops/tests/test_platform_tasks.py` (212-E) | مهامُّ الفريق: `ALL` تستبعد غيرَ النشط · مجمَعٌ بحدِّ مطالبين · تسليمٌ ثانٍ قبل المراجعة مرفوض · «مقبول بس لسّا ما خلص» **لا يُقفل** بل يعيد العملَ `IN_PROGRESS` · والرفضُ **يعيدها مفتوحة** (إسنادٌ `RETURNED`، أو يُحذَف فترجع للمجمَع) · ورفضٌ بلا سببٍ مكتوبٍ مرفوض · و`completed_at` عند **آخر** إسنادٍ لا أوّله · والملكيّةُ محروسةٌ في الخدمة كما في الـview · وموظّفٌ موقوفٌ لا يطالب · ومراجعةُ تسليمٍ رُوجع سلفاً خطأُ مجالٍ لا 500 · والقوائمُ بلا استعلامٍ لكلّ صفّ |
| `platform_ops/tests/test_platform_presence.py` (212-D) | دفترُ الحضور: **الجمعُ بالفجوات لا بالنبضات** (لسانان ينبضان معاً لا يضاعفان الوقت، وفجوةُ ثماني ساعاتٍ ليست حضوراً)، ومعامِلُ الحضور عند العتبة/دونها/فوقها بسقفِ السياسة، ويومٌ بلا نبضةٍ ليس صفراً، وعتبةُ صفرٍ تُطفئ الأثر. والنقطتان: النبضةُ بلا معامِلِ موظّفٍ (لا انتحالَ حضور)، وسجلُّ زميلٍ 403 للموظّف و200 للمدير |
| `platform_ops/tests/test_dashboard_and_notifications.py::DashboardCardCarriesTodaysPresenceTest` (212-D) | الحمولةُ **ترسل** ثواني اليوم وعتبةَ التخصّص، واستعلامُ العتبةِ لا يكبر مع البطاقات — وحارسُ الواجهةِ النصّيُّ يثبت أنّ المكوّنَ يقرأ الحقلَ لا أنّ الخادمَ يرسله |
| `platform_ops/tests/test_pilot_performance_wallet.py::PresenceLogEndpointMirrorsTheEvaluationTest` (212-D) | سجلُّ الموظّفِ = أرقامُ التقييم: العتبةُ من السياسةِ النشطة، والدرجةُ قبل/بعد موجودتان فعلاً في الحمولة |
| `platform_ops/tests/test_presence_frontend_contract.py` (212-D) | حرّاسٌ ساكنة: المؤقّتُ كلَّ دقيقةٍ **ينادي النبضةَ فعلاً** (لا يدقّ بلا تسجيل)، والعدّادُ مرسومٌ **فوق الصورة** لا بعدها، ولوحةُ السجلّ مركَّبةٌ في تبويب الأداء، وعدّادُ الجلسة القديمُ لم يعد، ولسانٌ مخفيٌّ لا ينبض، وحمولةٌ بلا الحقل لا تُعرَض صفراً |
| `platform_ops/tests/test_crm_ui_contract.py` (212-C · 212-H) | عقدُ شاشات CRM: **تعدادُ استهلاكٍ يَعدُّ النداءَ في مكوّنٍ لا التصديرَ في عميل الـAPI** (الصيغةُ الأولى أبقت صندوقَ طلبات التحويل باباً مسدوداً وهي خضراء)، وتعدادٌ ثانٍ على كلِّ دالّةٍ مُصدَّرة لأنّ `patchCrmLead` تشارك `getCrmLead` مسارَها فلا يراها تعدادُ المسارات، ولكلِّ استثناءٍ سببٌ مكتوب. ومنعُ `window.prompt`/`confirm`/`alert`، وشارةُ واتساب مشروطةٌ بوجود رقمِ واتساب، وأفعالُ المدير خلف شرطِ صفةٍ صريح. و**لوحة CRM نفسها مركّبة في مركز القيادة وفي قشرة الموظف معاً**: الأول لا يفتح باب `/staff`، والثاني لا يفقد باب المسوّق. و**اللوحةُ لا تهبط على دفترٍ فارغٍ بحكم البناء**: النطاقُ الابتدائيُّ يقرأ `myEmployeeId`، وشريطُ «عدّاداتي» مشروطٌ به |
| `platform_ops/tests/test_employee_profile_frontend_contract.py` (211-Q · 211-J · 212-J) | عقدُ الدرج: مفاتيحُ المُسلسِل مطابقةٌ للواجهة، والتبويباتُ الأربعةُ مُعلَنةٌ **ومركَّبةٌ فعلاً**، والدرجُ مركَّبٌ في اللوحة، والنقرُ على الوجه وعلى المقعد يفتحانه. وحرّاسٌ على ما لا يمسكه `tsc`: المقعدُ والبطاقةُ يعرضان الصورةَ الحقيقيّةَ لا الأحرفَ الأولى وحدَها، واللوحةُ تمرّرها، وسطرُ الدور يفضّل المسمّى على مفتاح السياسة، وبطاقةُ الموظّف مركَّبةٌ في مساحته ولا ترسل `job_title`، ولونُ سطر المحفظة يفرّق الحالاتِ الستّ فلا يُطبع **المعكوسُ** بأخضر المصروف. و**مفاتيحُ التبويبات مشتقّةٌ من `TABS` في الـTSX لا مسرودةً** (تبويبٌ يُعلَن ولا يُركَّب يسقط)، ومعها حارسٌ على الحذف لأنّ الاشتقاقَ وحدَه لا يمسكه؛ وتبويبُ الملاحظات ينادي النقطةَ **بمعرّف هذا الموظّف** (بلا الوسيط يعرض ملفُّه ملاحظاتِ الفريق)، ونموذجُ الكتابة خلف `canManage` |
| `platform_ops/tests/test_workspace_room.py` (211-I) | حرّاسٌ ساكنون على الغرفة: كلُّ مقعدٍ يرسمه المكوّن له قاعدةُ موضعٍ ولا قاعدةَ يتيمة (رفعُ `SEAT_COUNT` بلا توليدٍ يكدّس الموظّفين في زاوية بلا خطأ)، وكلُّ صنف `pf-*` يستعمله المكوّن معرَّفٌ فعلاً **بحدّ كلمةٍ لا بالتضمين**، وثوابتُ النموذج الهندسيّ مقابَلةٌ بقواعد `index.css` نفسِها، ولا بطاقتان تتراكبان ولا بطاقةٌ تُقصّ عند أيّ عرضٍ من ثلاثة عشر (٣٢٠ ← ١٩٢٠)، والغرفةُ مركَّبةٌ خلفَ تبويبٍ يفتحها. وفيه اختبارُ إثباتِ سقوطٍ صريح: الغرفةُ القصيرةُ القديمة يجب أن تُرفَض هنا لا أن تمرّ. و**حارسُ 211-H**: اللوحةُ لا تمرّر `null` لعضويّة الاجتماع بل مجموعةً مبنيّةً من `is_in_meeting` — بقاءُ `null` بعد وصول الحقل يعني ضوءاً أصفرَ لا يظهر أبداً مهما صحّ الخادم، عطبٌ صامتٌ لا يكشفه خطأٌ ولا اختبارٌ خادميّ |
| `platform_ops/tests/test_employee_targets.py` (210-ز) | فصلُ السُلَّمين: طاقةُ الإسناد لا تقصّ مقامَ الوحدات و`monthly_units_target` وحدَه يقصّه، وضبطُ أحدهما لا يمسّ الآخر؛ ورفضُ السالب وغير الرقم والنداء الفارغ؛ والتسجيلُ بـ«قبلُ وبعدُ»؛ والمقاديرُ من أشهر الموظّف ثمّ من زملائه ثمّ لا شيء، والشهرُ الجاري لا يُقاس؛ والنقطةُ: الكتابةُ للمدير والقراءةُ لصاحبها و404 على مستهدَف غيره؛ وحارسُ تطابق واجهة TypeScript مع مفاتيح الحمولة |
| `tenants/tests/test_member_activity_log.py` | تسجيل إضافة عضو وتغيير دوره وحذفه في `ActivityLog` |
