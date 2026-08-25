# hr — الموظفون والرواتب والمهام والحضور، ودفتر المصاريف الشخصي لكل مستخدم

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض

يجمع الـapp ثلاث مسؤوليات منفصلة تحت مجلد واحد: (1) **الرواتب** — موظفون بنوعين (دائم بأجر
شهري، جزئي بأجر ساعة)، ساعات عمل، غيابات وتأخيرات، كشوف رواتب وسندات صرف، وكلها تولّد قيوداً
في شجرة الحسابات عبر `accounting`. (2) **المهام والحضور والنقاط** (`Task`، `AttendanceRecord`،
`PointsHistory`) وهي نماذج قديمة بلا منطق خدمات. (3) **المصاريف الشخصية** — دفتر جيب لكل
مستخدم، معزول بالمستخدم لا بالشركة، وبلا أي أثر محاسبي (`hr/models.py:81-92`).
كما يستضيف الـapp مسارات المصادقة العامة (`hr/auth_api.py`) وقائمة المستخدمين.

## أهم الملفات

| الملف | الغرض | أسطر |
|---|---|---|
| `hr/models.py` | كل النماذج: الرواتب، المهام، الحضور، المصاريف الشخصية | 478 |
| `hr/payroll.py` | محرّك الرواتب: ربط الشجرة، الاحتساب، الترحيل وإلغاؤه | 385 |
| `hr/serializers.py` | مُسلسِلات + تحققات (أجر لكل نوع، منع موظف شركة أخرى) | 315 |
| `hr/auth_api.py` | تسجيل الدخول/الخروج/الاشتراك/تغيير كلمة المرور | 316 |
| `hr/payroll_api.py` | ViewSets الرواتب + حراسة `hr.payroll.*` | 297 |
| `hr/views.py` | ViewSets المهام/الحضور/النقاط/المصاريف الشخصية | 240 |
| `hr/urls.py` | تسجيل الراوتر ومسارات المصادقة | 43 |

## الـModels

| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Employee` | `pay_type` (monthly/hourly)، `monthly_salary`، `hourly_rate`، `standard_hours_per_day`، `working_days_per_month`، `code`، `is_active` | `tenant`، `account` → `accounting.Account` (PROTECT)، `user` (اختياري، SET_NULL)؛ `unique_together = [['tenant','code']]` |
| `WorkLog` | `date`، `hours` | `employee` (CASCADE)؛ `unique_together = [['employee','date']]` |
| `AttendanceAdjustment` | `kind` (absence/late)، `days`، `minutes`، `is_deductible` | `tenant`، `employee` |
| `Payslip` | لقطات: `rate`، `worked_hours`، `absence_days`، `late_minutes`، `gross`، `allowances`، `absence_deduction`، `late_deduction`، `other_deductions`، `net`، `status` (draft/posted) | `employee` (PROTECT)؛ `unique_together = [['employee','period_start','period_end']]` |
| `PayrollPayment` | `date`، `amount` | `employee` (PROTECT)، `payslip` (SET_NULL)، `cash_account` → `accounting.Account` |
| `PersonalExpense` | `date`، `title`، `category` (مفتاح نصّي)، `amount`، `is_paid` | `user` فقط — **بلا tenant وبلا أي FK محاسبي** (`hr/models.py:81-92`)، `sheet` |
| `PersonalExpenseSheet` | `name`، `position` | `user`؛ `unique_together = [['user','name']]` |
| `PersonalExpenseCategory` | `key`، `label`، `position` | `user`؛ `unique_together = [['user','key']]` |
| `Task` / `TaskSubmission` | `status`، `priority`، `total_work_time` | `assigned_to`/`created_by` → User، `tenant` |
| `AttendanceRecord` | `date`، `punch_in_time`، `punch_out_time`، `status` | `user`؛ `unique_together = [['user','date']]` |
| `PointsHistory` | `task_points`، `attendance_points`، `total_points` | `user`؛ `unique_together = [['user','date']]` |

## دوال الـservices العامة

المنطق في `hr/payroll.py` (لا يوجد `hr/services.py`):

```python
def money(value) -> Decimal:  # تقريب كل مبلغ لقرشين قبل التخزين أو الترحيل
def get_payroll_parent_account(tenant):  # بند «2112 رواتب مستحقة للموظفين»، يُنشأ إن غاب
def get_payroll_expense_account(tenant):  # حساب المصروف 5201 عبر tenants.services.ensure_operational_account
def next_employee_code(tenant) -> str:  # رقم الموظف التالي لكل شركة
def ensure_employee_account(employee: Employee):  # حساب الموظف الابن، ويتبع اسمه عند التغيير
def employee_balances(tenant_id: int, employees) -> dict:  # أرصدة صفحة كاملة باستعلام تجميعي واحد
def employee_balance(employee: Employee) -> Decimal:  # غلاف رقيق حول employee_balances
def compute_payslip(employee: Employee, period_start, period_end, *,
                    allowances=0, other_deductions=0) -> dict:  # أرقام الكشف بلا حفظ
def apply_computation(payslip: Payslip) -> Payslip:  # إعادة احتساب مسودّة عند كل حفظ
def post_payslip(payslip: Payslip, *, user=None) -> Payslip:  # مصروف مدين / ذمّة الموظف دائنة
def unpost_payslip(payslip: Payslip, *, user=None) -> dict:  # إلغاء الترحيل وإعادة الكشف مسودّة
def resolve_payment_source(tenant, account_id=None):  # الحساب المختار أو الصندوق الافتراضي
def post_payroll_payment(payment: PayrollPayment, *, user=None) -> PayrollPayment:  # ذمّة مدينة / صندوق دائن
def unpost_payroll_payment(payment: PayrollPayment, *, user=None) -> dict:  # يحذف قيد الصرف
```

## أهم الـAPI endpoints

مركّبة تحت `api/hr/` (`core/urls.py`).

| Method | المسار | الـview |
|---|---|---|
| POST | `/api/hr/auth/login/` · `logout/` · `signup/` · `change-password/` | `auth_api.login_view` … |
| GET/POST | `/api/hr/employees/` | `payroll_api.EmployeeViewSet` |
| GET | `/api/hr/employees/{id}/statement/` | `EmployeeViewSet.statement` |
| GET/POST | `/api/hr/work-logs/` | `payroll_api.WorkLogViewSet` |
| GET/POST | `/api/hr/attendance-adjustments/` | `payroll_api.AttendanceAdjustmentViewSet` |
| GET/POST | `/api/hr/payslips/` | `payroll_api.PayslipViewSet` |
| GET | `/api/hr/payslips/preview/` | `PayslipViewSet.preview` |
| POST | `/api/hr/payslips/{id}/post_slip/` · `/unpost/` | `PayslipViewSet.post_slip` · `unpost` |
| GET/POST/DELETE | `/api/hr/payroll-payments/` | `payroll_api.PayrollPaymentViewSet` |
| GET/POST | `/api/hr/personal-expenses/` + `/summary/` | `views.PersonalExpenseViewSet` |
| GET/POST | `/api/hr/personal-expense-sheets/` · `-categories/` | `views.PersonalExpenseSheetViewSet` · `…CategoryViewSet` |
| GET/POST | `/api/hr/tasks/` · `/attendance/` · `/points/` | `views.TaskViewSet` · `AttendanceRecordViewSet` · `PointsHistoryViewSet` |

## الاعتماديات

**يعتمد على:**
- `accounting` — **عبر services لا كتابة مباشرة للقيود**: `hr/payroll.py` يستورد
  `post_journal`، `resolve_default_cash_account`، `unpost_document`؛ ويستورد نماذج `Account`
  و`JournalLine` للقراءة وبناء الحسابات (`hr/payroll.py`)، و`allocate_child_account_code`
  من `accounting.cashbox` (`hr/payroll.py`).
- `tenants` — `ensure_operational_account` لضمان حساب المصروف 5201 (`hr/payroll.py`)،
  ونموذج `Tenant` (`hr/models.py`).
- `core` — `BaseTenantViewSet`، `get_tenant`، `require_perm` (`hr/payroll_api.py:21-23`).
- `accountant_portal` — `LegalAccountantRoutePermission` لحجب المحاسب الخارجي
  (`hr/views.py`، `hr/payroll_api.py`).
- `bridge` — `FirestoreMirrorDoc` في `hr/auth_api.py`.

**يعتمد عليه:** `core/reports/hr.py` يستورد `hr.models.Payslip` و`hr.models.PayrollPayment`
و`hr.models.Employee` و`hr.models.WorkLog` و`hr.models.AttendanceAdjustment` لتقارير
الرواتب الثلاثة (انظر «الكشفان» أدناه). الواجهة `frontend_v2` تستهلك مسارات `/api/hr/`
(مثال: `frontend_v2/services/personalExpensesApi.ts`).

## قواعد لا يجوز كسرها

- **لا مسار محاسبي موازٍ**: كل قيد رواتب يمرّ بـ`post_journal` وكل تراجع بـ`unpost_document`
  (`hr/payroll.py:1-21`، `hr/payroll.py`، `hr/payroll.py`) — لا تكتب `JournalLine` مباشرةً.
- **قيد اعتماد الكشف سطران فقط**: مدين 5201 (المصروف) ودائن حساب الموظف 2112x بقيمة `net`
  (`hr/payroll.py:283-288`). وقيد الصرف: مدين حساب الموظف ودائن الصندوق/البنك (`hr/payroll.py:361-366`).
- **الاحتساب خادمي دائماً**: `perform_create`/`perform_update` تستدعيان `apply_computation`
  (`hr/payroll_api.py`, `210`)، والمعاينة تستدعي `compute_payslip` نفسها (`hr/payroll_api.py`)
  — مصدر أرقام واحد لا اثنان (اختبار `test_preview_matches_the_saved_slip`).
- **الكشف المرحّل مجمَّد**: لا تعديل (`hr/payroll_api.py`)، لا حذف (`hr/payroll_api.py`)،
  ولا إعادة احتساب (`hr/payroll.py`)؛ ولا يُرحَّل كشف صافيه ≤ 0 (`hr/payroll.py`).
- **لا إلغاء ترحيل كشف صُرفت منه دفعات** (`hr/payroll.py:307-310`).
- **موظف دخل الدفاتر يُعطَّل ولا يُحذف** (`hr/payroll_api.py:123-126`).
- **سند الصرف يُرحَّل مع الحفظ في صفقة واحدة** ولا يُعدَّل — يُحذف ويُنشأ غيره
  (`hr/payroll_api.py:276-281`، `hr/payroll_api.py:290-294`).
- **صلاحيات ثلاث**: `hr.payroll.view` للقراءة، `hr.payroll.manage` للكتابة (`hr/payroll_api.py`)،
  و`hr.payroll.post` للترحيل وكل كتابة على سندات الصرف (`hr/payroll_api.py`, `251`, `268`).
- **الكتابة لا تقبل موظف شركة أخرى** حتى لو مرّ المعرّف في الجسم (`hr/serializers.py:214-228`).
- **المصاريف الشخصية معزولة بالمستخدم لا بالشركة**، ولا تُنتج قيداً، ومدير الشركة ليس استثناءً
  (`hr/views.py:160-168`، `hr/models.py:81-92`).
- **شاشتها تسكن «حسابي» لا قوائم الشركة** (`frontend_v2/components/personal/MyAccountPage.tsx`،
  مسار `/my-account`، مدخلها بطاقة المستخدم أسفل الشريط الجانبي). إعادة بندها إلى قائمة
  الشركة تُوهم أنها مصروف شركة — وهي ليست كذلك لا بياناً ولا محاسبةً.
- **`PersonalExpenseCategory.key` خادمي** — يُولَّد بـ`next_key` ولا يُعدَّل من العميل
  (`hr/views.py`، اختبار `test_key_is_server_owned_and_cannot_be_rewritten`).
- **المحاسب القانوني الخارجي محجوب عن `/api/hr/`** عدا `/api/hr/auth/`
  (`accountant_portal/permissions.py:47-57`).

## الكشفان — مسير الرواتب وكشف الساعات

تقريران في محرّك `core/reports` (لا شاشة خاصة ولا نقطة API ثانية)، كلاهما خلف
`hr.payroll.view` ويُصدَّران Excel وCSV ويُطبعان من الشاشة العامة:

| المفتاح | ماذا يقول | مصدره |
|---|---|---|
| `payslips` «كشوف الرواتب» | صفٌّ لكل كشف: الساعات وأيام الغياب والأساسي والبدلات و**الخصم مفكَّكاً** (غياب · تأخير · أخرى) والصافي | لقطات `Payslip` المحفوظة — لا احتساب جديد |
| `timesheet-daily` «كشف الساعات اليومي» | صفٌّ لكل موظف وعمودٌ لكل يوم: ساعاته أو «غ»/«ت» — ومجاميع الساعات وفوق الدوام والغياب والتأخير | `WorkLog` و`AttendanceAdjustment` مباشرةً |

**الكشفان يتطابقان على المقياس الذي يُحاسَب به كل نوع، لا على «الساعات» مطلقاً.**
`compute_payslip` لا يشتقّ ساعات إلا للموظف الجزئي؛ والدائم `worked_hours` عنده
صفرٌ دائماً ويُحاسَب على غيابه وتأخيره. فالحارس في
`hr/tests/test_payroll_reports.py`: مجموع ساعات الجزئي == `worked_hours`، وأيام
غياب الدائم ودقائق تأخيره == `absence_days` و`late_minutes`. مطالبةُ كشف الساعات
بمطابقة ساعات الدائم تعني تغيير احتساب المال — وهو ما لا يفعله تقرير.

**فوق الدوام استدلالٌ للعِلم لا للتسعير**: ما تجاوز `standard_hours_per_day` في
اليوم. لا مفهوم «أجر إضافي» في محرّك الرواتب أصلاً، فالعمود يُقرأ ولا يُحتسب.

**سقف الفترة 31 يوماً** (`TIMESHEET_MAX_DAYS`) — الكشف عمودٌ لكل يوم، وما فوق
الشهر جدولٌ لا يُقرأ ولا يُطبع؛ وتجاوزه يعود 400 برسالته. والتقرير يُعلن «هذا
الشهر» نطاقاً افتراضياً (`ReportFilter.default`) فلا يُفتح على رسالة خطأ.

## الورقتان اللتان تُسلَّمان بيد الموظف

الكشفان أعلاه **لكل الموظفين** — يُراجَعان قبل الاعتماد ولا يُسلَّمان لأحد. وما
يُعطى للموظف ورقتان تُطبعان من شاشة الرواتب نفسها
(`frontend_v2/components/hr/PayrollPage.tsx`) عبر القالب المشترك
`frontend_v2/utils/printReport.ts` — **بلا نقطة API جديدة**: كل رقم فيهما محمَّل
في الشاشة أصلاً، وبناء المحتوى في `frontend_v2/utils/payroll.ts`
(`buildPayslipPrint`، `buildDailySheet`) كي يُختبر بلا متصفّح.

| الورقة | زرّها | ماذا تحمل |
|---|---|---|
| **قسيمة الراتب** | «طباعة القسيمة» على سطر الكشف في تبويب «كشوف الرواتب» | هويّة الموظف والفترة والأجر المحتسب، وخمسة سطور ثابتة (الأساسي · البدلات · خصم الغياب · خصم التأخير · خصومات أخرى) وصافيها، وسطرا توقيع |
| **كشف الدوام** | «طباعة كشف الساعات» في تبويب «السجل اليومي» | صفٌّ لكل يوم من الشهر المعروض: ساعاته (للجزئي) أو غيابه وتأخيره (للدائم)، ومجاميعها، وسطرا توقيع |

**ثلاث قواعد لا تُكسَر في الورقتين:**

- **لا مبلغ يُشتقّ في الواجهة.** «المتبقّي» تحديداً لا يُطبع: دفعةٌ غير مربوطة
  بالكشف (`payslip=null`) تجعل `الصافي − المصروف` كذباً على ورقةٍ موقّعة. المطبوع
  «المصروف من هذا الكشف» (`paid_total`) و«رصيده في الدفاتر» (`balance`) — كلاهما
  رقمٌ خادمي يُنقل كما هو.
- **الصفر يُطبع ولا يُحذف** — «خصم غياب 0» على ورقةٍ يوقّعها الموظف إقرارٌ بأن
  شيئاً لم يُخصم، وحذفُ السطر يترك السؤال مفتوحاً.
- **صفٌّ لكل يوم لا لكل سجلّ** في كشف الدوام: اليوم بلا تسجيل يبقى فراغاً ظاهراً
  فتُرى الثغرة. وعمود الساعات للجزئي وحده — الدائم لا ساعات يومية له في النموذج
  (`WorkLog` لا يُسجَّل إلا للجزئي)، فلا تُخترع له.

## الاختبارات المهمة

| الملف | ما يغطيه |
|---|---|
| `hr/tests/test_payroll.py` (393) | بناء الشجرة وحسابات الموظفين، احتساب الجزئي من الساعات والدائم بالخصومات، قيد الاعتماد والصرف، تجميد الكشف المرحّل، منع حذف موظف بسجلّ، العزل والصلاحيات، تطابق المعاينة مع الحفظ |
| `hr/tests/test_payroll_reports.py` | تطابق الكشفين لكل نوع، الشبكة اليومية وعلاماتها، فوق الدوام، حارس الـ31 يوماً، العزل والصلاحية، وثبات عدّ الاستعلامات مع عدد الموظفين |
| `frontend_v2/utils/payroll.test.ts` | بناء القسيمة وكشف الدوام: الأسطر الخمسة، انعدام «المتبقّي» المشتقّ، صفٌّ لكل يوم، طول الشهر، وتجميع سجلّات اليوم الواحد |
| `frontend_v2/e2e/payroll-print.spec.ts` | الزرّان مركَّبان فعلاً والنافذة تُفتح بمحتواها — `tsc` لا يفحص خصائص JSX هنا فلا يمسك زرّاً غير موصول |
| `hr/tests/test_personal_expenses.py` (350) | ملكية المصروف من الطلب لا من الجسم، العزل بين المستخدمين، انعدام القيد المحاسبي، الفلاتر والملخص، أوراق المصاريف (بذر الورقة الأولى، منع حذف الأخيرة)، كتالوج الفئات لكل مستخدم |
