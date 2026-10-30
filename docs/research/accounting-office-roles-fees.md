# الأدوار والصلاحيات، والإسناد، والأتعاب والتحصيل — بحث مرجعي ثانٍ

موديول «مكتب محاسبة» على K.T.R.A. هذا الملف **يُكمل** بحثاً سابقاً ولا يعيده: `docs/research/accounting-office-practice-management.md` (في فرع `research/acct-practice-mgmt`) غطّى الكيانات والعمل المتكرر وطلب المستندات ولوحات الصباح. أمّا هنا فالأسئلة الثلاثة التي لم يُجب عنها هناك: **الأدوار والصلاحيات**، **تفصيل الإسناد ورؤية الضغط**، **آليات الأتعاب والتحصيل وأسعار الخدمات والدفع المحلي**.

كل ما هو **مقترح لنا** مسبوقٌ بعبارة «توصيتنا» أو يأتي في §6. وما عدا ذلك **قول مصدر** ومعه رابطه. والأرقام الافتراضية التي تُصدرها البرامج (مثل «كل 3 أيام، مرة واحدة») مذكورة بوصفها **افتراضيات المنتج** لا توصية.

---

## 1) منهج البحث وحدوده

اعتُمدت **توثيقات المنتِج الرسمية** فقط (help centre / knowledge base)، بالقراءة المباشرة لا عبر مراجعةٍ ثالثة. والنتيجة الأولى لهذا البحث **تصحيحُ حجبٍ في البحث السابق**:

| البرنامج | الحالة في هذه الجلسة |
|---|---|
| **TaxDome** | **مقروء بالكامل هذه المرة** — `help.taxdome.com` يخدم الآن نصّ المقال كاملاً بعد أن كان يردّ `HTTP 403` من Cloudflare. (مضيف `help-center.taxdome.com` المذكور في `sitemap` يعيد 404/406 فلا يُستخدم.) |
| **Canopy** · **Financial Cents** · **Jetpack Workflow** · **Ignition** | مقروءة (Intercom) |
| **Karbon** | **لا يزال غير مقروء نصّاً**: الصفحات تُبنى بالـJavaScript، واستدعاء `https://help.karbonhq.com/s/articles/2000285-overview-karbon-job-roles` أعاد `HTTP 200` بجسمٍ عنوانه «Karbon Help» وحده. المؤكَّد **عناوين المقالات** من الـ`sitemap` الرسمي فقط. |
| **Xero Practice Manager** | **لم يُقرأ**: `central.xero.com` أعاد `200` بلا أي نصّ (تطبيق client-side)، وصفحة `https://www.xero.com/us/practice-manager/` أعادت `404`. لا أدّعي عنه شيئاً. |
| **iCount (إسرائيل)** | الفهرس وقوائم الوحدات مقروءة بالعبرية؛ نصّ مقال «הוראות קבע» لم يُصيَّر كاملاً. |
| **مصادر الدفع المحلي** | **لم تُقرأ**: `pma.ps` (سلطة النقد) و`boi.org.il` و`payboxapp.com` ردّت `200` بلا نصّ (JS أو صفحة حماية)، ونطاق `help.greeninvoice.co.il` غير موجود (فشل DNS). فلا أدّعي شيئاً عن Bit أو PayBox. |

**تحفّظات:**
1. هذه البرامج **كلها تفترض بوابة زبون** بحساب أو بريد؛ نموذجنا (زبون بلا دخول) لا يقابله نموذج عند أحد — وهو ما يجعل بعض آلياتهم (توقُّف التذكير عند «إتمام الزبون») بلا مقابل عندنا.
2. **تكرارٌ مقصود مع البحث السابق في موضعين فقط** — (أ) Ignition §5.3 استُعيد رابطه لأن آلية الأنواع الخدمية هي أساس توصية الأتعاب؛ (ب) تصحيح: البحث السابق قال «لا توثيق يذكر عدداً افتراضياً للتذكير». **هذا لم يبق صحيحاً**: TaxDome ينصّ على افتراضيين صريحين (§5.4).
3. لم أُعِد التحقّق من ادّعاءات البحث السابق؛ ما لم يُذكر هنا فهو على حاله هناك.

---

## 2) الملخّص

1. **الأدوار تُشحن ثلاثةً إلى أربعة، والفارق الحقيقي ليس في أسمائها بل في سؤالين:** هل يرى الموظف زبائن غيره؟ وهل يرى المبالغ؟ — وكلانا يُجاب عنه بـ**إعدادٍ منفصل** لا بعضوية الدور.
2. **النمط الغالب: «مُسنَد إليّ فقط» هو الافتراضي للموظف.** TaxDome يقيّد `employee` بحسابات الزبائن المُسنَدة إليه ما لم تُمنح له `View all accounts` ([System roles](https://help.taxdome.com/article/601-team-basic-owner-admin-employee-roles))، وCanopy يُسمّي مجموعةً جاهزة `Staff (Assigned Clients, No Billing)` ([Permission sets](https://support.getcanopy.com/en/articles/13371632-how-permission-sets-work)).
3. **المبالغ تُحجب عن الموظف افتراضياً عند اثنين نصّاً:** Financial Cents: «افتراضياً **المالك وحده** يرى معلومات الفوترة… بما فيها معدلات الساعات وإجمالي فواتير الزبون وتقرير المعدل الفعلي» ([المصدر](https://help.financial-cents.com/en/articles/7208803-can-my-team-see-client-billing-information))؛ وCanopy يشحن مجموعات `No Billing` صراحةً. أمّا TaxDome فلا يملك «قراءة الفواتير» بل `Manage invoices` فقط، و«هذه الصلاحية تمنح الوصول إلى **كل بيانات الفاتورة، بما فيها المبالغ**» ([Access rights](https://help.taxdome.com/article/193-team-member-access-rights)) — أي إمّا مبالغ كاملة أو لا شيء.
4. **الإسناد عند TaxDome أربعة أنواع** — محادثة/عمل (job)/مهمة/فاتورة — و**الإسناد منفصل عن وصول الحساب**: «إعطاء أحدهم وصولاً للحساب لا يُسنِده تلقائياً إلى أي عمل… وبالعكس، إسناده إلى مهمة أو عمل لا يمنحه وصولاً إلى حساب الزبون» ([Assignment explained](https://help.taxdome.com/article/380-assignees-and-account-access-how-everything-works-together)).
5. **الضغط يُعرض بالساعات لا بالأعداد، ويشترط سلوك تسجيل وقت.** Financial Cents: تقرير السعة لا يُظهر المشروع بلا ميزانية ساعات ولا بلا تاريخ استحقاق ولا بلا مُسنَد ([Capacity](https://help.financial-cents.com/en/articles/4464492-capacity-management))؛ Jetpack: `Actual` مقابل `Scheduled/Capacity` وشعارٌ أحمر عند تجاوز السعة بأربع ساعات وأكثر ([Weekly view](https://support.jetpackworkflow.com/en/articles/15935731-capacity-management-weekly-view))؛ TaxDome: يضع السعة أسبوعياً ويحلّلها عبر التقارير ([Weekly capacity](https://help.taxdome.com/article/1745-weekly-capacity)).
6. **اشتراك شهري = «سلسلة فواتير لمرة واحدة تُصدر آلياً على جدول»** — بهذه العبارة يعرّف TaxDome الفاتورة المتكررة، ويُسمّي مثالها «خدمات اشتراكية مثل مسك الدفاتر الشهري» ([Invoicing explained](https://help.taxdome.com/article/1843-invoicing-overview)).
7. **الحالة المسوَّدة قائمة فعلاً في منتجٍ مهني:** TaxDome يعطي زرّ **Save as draft** فتذهب الفاتورة إلى تبويب `Inactive` بحالة **Draft**، «ويمكنك مراجعتها وتعديلها لكنها لا تكون مرئية للزبون حتى تضغط Create» ([Recurring invoices](https://help.taxdome.com/article/995-recurring-invoices-recurring-invoices-basic-create-schedule-save-as-draft)).
8. **حجب المخرجات حتى الدفع نمطٌ في منتجين لا واحد:** TaxDome `Lock docs to invoices` — الزبون يرى المستند ولا يفتحه حتى السداد، و«الدفع الجزئي غير ممكن» ([المصدر](https://help.taxdome.com/article/141-locking-a-document-to-a-bill))؛ وFinancial Cents `Lock Client Files Behind an Invoice` بالمنطق نفسه والشرط نفسه ([المصدر](https://help.financial-cents.com/en/articles/14630941-lock-client-files-behind-an-invoice)).
9. **الدفع النقدي/الشيك/التحويل يُسجَّل يدوياً في المنتجين المهنيين** (TaxDome: «سجّل دفعة تمّت نقداً أو بشيك أو بتحويل بنكي»، وبلا دفع جزئي) ([Offline payments](https://help.taxdome.com/article/offline-payments)) — وهذا بالضبط ما يحتاجه سوقنا حيث لا بوابة دفع.
10. **افتراضيات جاهزة للتذكير موجودة:** حقلا التذكير في TaxDome: **«الأيام حتى التذكير التالي: 3»** و**«عدد التذكيرات: 1»** ([Reminders reference](https://help.taxdome.com/article/reminders-reference)).

---

## 3) الأدوار والصلاحيات

### 3.1 ما تشحنه المنتجات افتراضياً

| البرنامج | المجموعة الافتراضية | المصدر |
|---|---|---|
| **TaxDome** | ثلاثة أدوار نظام: **owner · admin · employee**. مالكٌ واحد فقط لا تُسحب صلاحياته. | [System roles](https://help.taxdome.com/article/601-team-basic-owner-admin-employee-roles) |
| **Financial Cents** | أربعة: **Owner · Admin · Member · Contractor**، وكل دور قابل للتخصيص صلاحيةً صلاحية. | [Customize user permissions](https://help.financial-cents.com/en/articles/4914265-customize-user-permissions) |
| **Canopy** | **مجموعات صلاحيات** جاهزة غير قابلة للتعديل (تُنسَخ لتُخصَّص)، ومنها `Admin`، و`Admin (No Billing)`، و`Staff (Assigned Clients, No Billing)`، و`Staff – All Clients, No Billing`. | [Assign permission sets](https://support.getcanopy.com/en/articles/9375878-how-do-i-assign-access-permission-sets) · [How permission sets work](https://support.getcanopy.com/en/articles/13371632-how-permission-sets-work) |
| **Jetpack Workflow** | لا أدوار مسمّاة بل **صلاحيات حبيبية لكل مستخدم** + دور `Account Admin` وحده يديرها. | [Permissions overview](https://support.jetpackworkflow.com/en/articles/9425583-permissions-overview) |
| **Karbon** | **أسماء فقط** (من الـsitemap): `Overview of Karbon job roles` · `Analytics access permissions` · `Giving access without edit rights in Karbon` · `What permissions are needed to edit templates in Karbon`. | [sitemap](https://help.karbonhq.com/s/sitemap-topicarticle-1.xml) |

**قراءةٌ لهذه الأسماء (توصيتنا في التفسير لا في الواقعة):** ثلاث درجات تتكرر — **مالك** لا يُقيَّد، **مدير** يُدير الناس والزبائن لكن لا يملك الاشتراك، **موظف** مقيَّد. وثلاثتها تعرف **«قارئاً» أو حجباً مسمّى**: Karbon يعنون `without edit rights`، وCanopy يشحن `No Billing`، وTaxDome يعطي `read-only view` لمنظور الزبون لا للموظف.

### 3.2 الفروق النصّية في الأدوار العليا

TaxDome يحدّد **الاستثناءات** بدقة، وهي ما يهمّ في تصميم دور «مدير»:

- **admin** «له وصول فوري إلى كل ميزات TaxDome وكل الحسابات» ويستطيع إضافة موظفين واختيار حقوقهم، **لكنه لا يستطيع**: تعيين الأدوار أو تغييرها، ولا إضافة/حذف/تعطيل مدراء، ولا إدارة الاشتراك أو وسائل دفع الاشتراك، ولا ربط TaxDome بـQuickBooks Online، ولا إدارة **السعة الأسبوعية للمالك** ([المصدر](https://help.taxdome.com/article/601-team-basic-owner-admin-employee-roles)).
- **employee** لا يستطيع: تغيير حقوقه أو حقوق غيره، ولا منح الآخرين وصولاً للحسابات **إلا** بحقّ `Assign teammates`، ولا رؤية **Team summary** في صفحة Insights، ولا حذف تعليقات غيره على الأعمال، ولا حذف رسائل المحادثة ([المصدر نفسه](https://help.taxdome.com/article/601-team-basic-owner-admin-employee-roles)).

Jetpack يقارب الأمر بعرضٍ مختلف: كل تصنيف صلاحية (مشاريع، زبائن، مهام، ميزانيات، سلاسل، جهات اتصال، أوقات) له مفتاح «يقترح إمّا **عملاً مُسنَداً إليه وحده** أو كل العمل في التصنيف»؛ و«من له `view only assigned` على الزبائن لا يرى زبوناً إلا إذا اختير `client assignee` في ملفه» ([المصدر](https://support.jetpackworkflow.com/en/articles/9425583-permissions-overview)).

Canopy يربط الصلاحية بـ**الترخيص** لا بالدور فقط: «من لا يملك ترخيص `Time & Billing` لا يرى تبويب Time ولو مُنح الصلاحية»، وإطفاء صلاحيةٍ قد يُطفئ صلاحياتٍ تابعة لها تلقائياً ([المصدر](https://support.getcanopy.com/en/articles/13371632-how-permission-sets-work)).

### 3.3 الأسئلة الثلاثة صريحةً

**(أ) هل يرى الموظف زبائن مُسنَدين لغيره؟**

| البرنامج | الجواب الموثَّق |
|---|---|
| TaxDome | **لا افتراضياً** — استخدام الموظف «يبقى محدوداً حتى يُمنح وصولاً لحسابات زبائن»، إمّا مجموعةً مختارة أو `View All Accounts` ([System roles](https://help.taxdome.com/article/601-team-basic-owner-admin-employee-roles)). |
| Canopy | **لا** في المجموعة الجاهزة المسمّاة `Staff (Assigned Clients, No Billing)`؛ و**نعم** في `Staff – All Clients…` ([Permission sets](https://support.getcanopy.com/en/articles/13371632-how-permission-sets-work)). |
| Jetpack | يعتمد على المفتاح؛ والقيد الفعلي يقع عند **الزبون** لا العمل: `view only assigned` يتطلّب اختيار الموظف `client assignee` ([Permissions](https://support.jetpackworkflow.com/en/articles/9425583-permissions-overview)). |
| Financial Cents | **غير مؤكَّد** — لم أقرأ توثيقاً يحدّد نطاق رؤية الزبائن لدور `Member`. |

**(ب) هل يرى الموظف الأتعاب والفواتير والمبالغ المستحقّة؟**

- **Financial Cents**: «لا، **افتراضياً المالك وحده** يرى معلومات الفوترة» — وتشمل معدلات الفوترة للساعة وإجمالي فواتير الزبون وتقرير المعدل الفعلي، ويمكن السماح بها عبر تخصيص الصلاحيات ([المصدر](https://help.financial-cents.com/en/articles/7208803-can-my-team-see-client-billing-information)).
- **Canopy**: يشحن مجموعتَي `Admin (No Billing)` و`Staff (…, No Billing)` — أي أن **حجب الفوترة خيارٌ مسمّى ومقصود** ([المصدر](https://support.canopy.com/en/articles/9375878-how-do-i-assign-access-permission-sets)).
- **TaxDome**: لا صلاحية «عرض» للفواتير؛ `Manage invoices` «تمنح الوصول إلى كل بيانات الفاتورة، **بما فيها المبالغ**»، و`Manage proposals` تسمح برؤية الفواتير **داخل العروض** فقط ([Access rights](https://help.taxdome.com/article/193-team-member-access-rights)).
- **Jetpack**: لا وحدة فوترة في فهرس توثيقه ([sitemap](https://support.jetpackworkflow.com/en/sitemap.xml)) — وغياب القسم لا يثبت الغياب.

**(ج) هل يستطيع الموظف مراسلة الزبون؟**

- **TaxDome**: الإرسال مربوطٌ **بوصول الحساب**: `View all accounts` «تتيح أيضاً عرض وإرسال الرسائل الآمنة والبريد وكتابة الملاحظات لكل الحسابات»؛ ومن ليس له وصول الحساب لا يراسله ([Access rights](https://help.taxdome.com/article/193-team-member-access-rights)). وإسناد **المحادثة** (thread) منفصل عن الإرسال: «إسناد المحادثة مستقلٌ عن مَن أرسل الرسالة» ([Assignment explained](https://help.taxdome.com/article/380-assignees-and-account-access-how-everything-works-together)).
- **البقية**: لم أقرأ نصّاً يحسمها (Canopy: غير مؤكَّد؛ Jetpack: لا قسم في فهرسه؛ Financial Cents: لم أقرأ نصّاً فيه).

### 3.4 توصيتنا لدورٍ افتراضي (لا نقل)

**مبدأ:** الدور **ثلاثة** لا أكثر، والصلاحيات المتنازَع عليها **مفاتيح منفصلة** لا أدوار إضافية. أمّا «مكتبٌ من شخصٍ واحد» فلا يعرض أدواراً إطلاقاً.

| الدور | يرى الزبائن | يرى المبالغ | يراسل الزبون | يُسند ويعدّل | يعتمد الفاتورة الشهرية | إعدادات المكتب والاشتراك |
|---|---|---|---|---|---|---|
| **المالك** | الكل | نعم | نعم | نعم | نعم | نعم |
| **مدير المكتب** | الكل | نعم (افتراضياً) | نعم | نعم | نعم | لا (لا اشتراك ولا مالكين) |
| **محاسب** | **المُسنَد إليه فقط** (قابل للفتح) | **لا** افتراضياً (مفتاح «يستطيع رؤية المبالغ») | نعم — لزبائنه وحدهم | لا يُسند لغيره | لا | لا |
| **قارئ/مراجع** | حسب إسناده | لا | لا | لا | لا | لا |

**كيف تتصرّف مع حجم المكتب (الافتراض في الإعداد):**
- **شخص واحد (solo):** لا شاشة أدوار، ولا كلمة «موظف»؛ المستخدم هو المالك، وكل المفاتيح مفتوحة، وتُخفى الأعمدة الفارغة (المسؤول دائماً هو هو).
- **صغير (2–5):** الأدوار الثلاثة الأولى فقط (مالك/مدير/محاسب)، والمفاتيح المتنازَع عليها **مرئية** في شاشة الموظف: «يرى زبائن الآخرين»، «يرى المبالغ»، «يراسل الزبائن».
- **كبير (6+):** تُضاف صلاحيات حبيبية على نمط Jetpack (تصنيف × مُسنَد/الكل) ودور القارئ، **دون** كسر الافتراض أن المُسنَد فقط.

**السبب في حجب المبالغ عن المحاسب افتراضياً:** أقوى دليلين نصّيان (Financial Cents والمالك وحده؛ Canopy ومجموعات `No Billing`) يقصدان حماية بيانات الأتعاب، ومكتبٌ عائلي/صغير في السوق المحلي يفشي أتعابه بالخطأ إن كانت مكشوفة؛ وفتحُها يبقى متاحاً بمفتاحٍ واحد لأن كثيراً من المكاتب تريدها لموظفٍ كبير. وهذا **قرارٌ لنا** مبنيٌّ على قراءة المصدرين لا نصٌّ منهما.

**أمّا «يرى زبائن غيره» فافتراضُنا «لا»** لسببٍ عمليّ: عندنا **لا بوابة زبون**، فالميزة الوحيدة من رؤية عمل غيره هي تغطية غياب — وهي تُحلّ بـ«مشاركة زبونٍ مع موظفٍ ثانٍ» (توكيل مؤقت) لا بفتح كل شيء.

---

## 4) الإسناد وضغط الشغل

### 4.1 على أي مستوى يُسنَد؟

| البرنامج | مستوى الإسناد |
|---|---|
| **TaxDome** | **أربعة مستويات**: thread (محادثة/بريد/SMS) · job (عمل في مسار) · task (مهمة) · invoice (فاتورة — تُنسب أداءً، والمنشئ يُسنَد افتراضياً). والوصول للحساب منفصلٌ تماماً عن الإسناد. ([Assignment explained](https://help.taxdome.com/article/380-assignees-and-account-access-how-everything-works-together)) |
| **Canopy** | إسناد **فرق** وزبائن (`Assign team members and teams to a client`) + إسناد في المهام؛ ودور `Account role` (محضّر ضرائب، مسك دفاتر) يُوزَّع عند الإنشاء لا على شخص. (عناوين/صفحات: [Assign teammates and teams](https://support.getcanopy.com/en/articles/9375888-assign-team-members-and-teams-to-a-client)) |
| **Jetpack** | إسناد على **الزبون** (client assignee) وعلى **المشروع/المهمة** معاً؛ والقيد الفعلي يجري عند الزبون ([Permissions](https://support.jetpackworkflow.com/en/articles/9425583-permissions-overview)). |
| **Financial Cents** | مسؤول على **المشروع** والمهمة، وفلتر `Show Current Assignee` يرتّب العمل «على طابور مَن يقف» ([Capacity](https://help.financial-cents.com/en/articles/4464492-capacity-management) · [الفلتر](https://help.financial-cents.com/en/articles/4486865-how-does-the-show-current-assignee-filter-work)). |
| **Karbon** | عناوين: `Assign/reassign and unassign a task` · `Create a client team` — بلا سلوك مؤكَّد. |

**نمطٌ يستحقّ التنبيه:** TaxDome note الصريح: «الإسناد **لا يمنح** وصولاً، والوصول **لا يُسنِد**» — فصلٌ بين «مَن يرى» و«مَن مسؤول». وإن أخذناه حرفياً مع نموذج «الزبون مُسنَد لموظف» يصير كل عملٍ له مسؤولٌ بالوراثة.

### 4.2 كيف يرى المالك الضغط؟

- **Financial Cents** — تقرير سعة **بالساعات**: لكل عضو ساعات العمل المقدّرة ونسبة مئوية من سعته الأسبوعية، وتُحمرّ الساعات عند التجاوز، و`Set Capacity` لكل عضو (40 لبدوام كامل، 20 لجزئي). **وشرطه الثقيل:** يحتاج ميزانية ساعات للمشروع + تاريخ استحقاق + مُسنَداً + مهمة واحدة على الأقل، وإلا «المشروع لا يظهر في التقرير» ([Capacity](https://help.financial-cents.com/en/articles/4464492-capacity-management)).
- **Jetpack** — لوحة أسبوعية لكل عضو: `Actual` (ساعات مسجّلة) و`Scheduled/Capacity` («12/32hrs»)، «وشعار السعة يُحمرّ عند تجاوز السعة بأربع ساعات أو أكثر»، وزرّ `Display Overdue Work`، و`Export to CSV`، وهي **لمديري الحساب على خطة Premium فقط** ([Weekly view](https://support.jetpackworkflow.com/en/articles/15935731-capacity-management-weekly-view)).
- **TaxDome** — المالك/المدير يضبط ساعات كل عضو (ساعات لكل يوم، أو دفعةً واحدة)، والتحليل في لوحة `Team capacity`، و**لا معنى لها بلا تسجيل وقت**: «إن لم يسجّل الموظفون وقتهم فلا يمكن تحليل الوقت» ([Weekly capacity](https://help.taxdome.com/article/1745-weekly-capacity)). وموظف `employee` **لا يرى** Team summary في Insights ([System roles](https://help.taxdome.com/article/601-team-basic-owner-admin-employee-roles)).
- **عدّ المتأخرات لكل موظف:** المؤكَّد أنه **فلتر/عرض** لا عمودُ عدّ: `Display Overdue Work` (Jetpack) و`Overdue` في فلاتر الفواتير (TaxDome: الفواتير المتأخرة تُظلَّل وتُفلتر) ([Manage overdue](https://help.taxdome.com/article/429-how-to-manage-overdue-invoices)). لم أجد توثيقاً لعمود «عدد المتأخرات لكل موظف» في أيٍّ منها.

### 4.3 توصيتنا

1. **المستوى الافتراضي: الزبون** (مسؤول واحد)، ويورَّث منه كل نسخة عمل وكل فاتورة شهرية — هذا ما قرّره المالك أصلاً، وهو أوفر من إسنادٍ على كل مهمة، ويقع بين نمط Jetpack (إسناد زبون + عمل) ونمط TaxDome (أربعة مستويات نرفضها في v1).
2. **تجاوزٌ اختياري على نسخة العمل** (مسؤول مختلف لهذا الشهر)، لا على المهمة. أمّا **المحادثة** فتُترك بلا إسناد على مستوى الرسالة: الموظف يرسل، ويُسجَّل «مَن أرسل» تلقائياً.
3. **لوحة الضغط أعدادٌ لا ساعات.** سببٌ مستخرج من المصادر نفسها: عرض الساعات يستلزم ميزانية ساعات وتسجيل وقت (FC وJetpack وTaxDome كلهم يصرّحون بذلك)، ومكتبٌ محلّي لا يسجّل وقته؛ فالتوصية: صفٌّ لكل موظف و**أربعة أعمدة** — عدد الزبائن · نسخ العمل المتأخرة · المستندات الناقصة · مبالغ متأخرة على زبائنه. والتعريفات من السياق: «متأخر» = تجاوز الاستحقاق المشتقّ من الفترة (البحث السابق §3.2)، لا حقلٌ يدوي.
4. **إشارة الاحمرار:** نأخذ فكرة «الشعار الأحمر عند تجاوز حدّ» ونستبدل الساعات بعددٍ: يَحمرّ صفّ الموظف إذا كان متأخراته > 20% من نسخ عمله أو إذا كان عدد زبائنه > 1.5× متوسط المكتب. **هذا اختيارنا وحدوده اعتباطية** — تُترك في إعدادات المكتب لا في الكود.
5. **زرّ «إعادة توزيع»** لا «سحب من طابور»: نقل مجموعة زبائن من موظفٍ إلى آخر بضغطة، مع أثرٍ مسجَّل (على نمط `Reassign` عند FC).

---

## 5) الأتعاب والتحصيل

### 5.1 نماذج التسعير — وما تشحنه المنتجات

| النموذج | دعمٌ موثَّق | ملاحظة |
|---|---|---|
| **اشتراك ثابت متكرر** (retainer شهري) | Ignition: نوع خدمة `Recurring` بمدّة كل N يوم/أسبوع/شهر، وبداية (عند القبول / تاريخ بدء / تاريخ محدَّد) ونهاية (بلا نهاية / بعد N مرة) ([Service Types](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules)) · TaxDome: فاتورة متكررة «سلسلة فواتير لمرة واحدة… لخدمات اشتراكية مثل مسك الدفاتر الشهري» ([Invoicing](https://help.taxdome.com/article/1843-invoicing-overview)) | الأشيع مفهومياً في المنتجات التي قرأتها |
| **خدمة/بند بسعر** (per service، لمرة واحدة) | Ignition: نوع `One time` يُفوتر عند القبول/البداية/النهاية/تاريخ محدَّد ([Service Types](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules)) · TaxDome: `Services` تُستخدم قوالبَ للفوترة وتُضاف للفاتورة ([Invoicing](https://help.taxdome.com/article/1843-invoicing-overview)) | هو آلية «الخدمات الإضافية» عندنا |
| **بالساعة** | TaxDome: تسجيل وقت ← فاتورة من قيود الوقت، ومعدلات فوترة (`Manage billing rates`) ([Access rights](https://help.taxdome.com/article/193-team-member-access-rights)) · Financial Cents: معدلات بالساعة وتقرير المعدل الفعلي ([billing info](https://help.financial-cents.com/en/articles/7208803-can-my-team-see-client-billing-information)) | يشترط سلوك تسجيل وقت |
| **سعري Packages/Bundles** | TaxDome: عرضٌ بقائمة سعرية ثابتة أو **حتى 3 حزم** يقارنها الزبون، ووديعة، وتشغيل خدمة اشتراكية ([Invoicing](https://help.taxdome.com/article/1843-invoicing-overview)) · Ignition: عدة أنواع خدمة في عرضٍ واحد (شهري + ربعي + سنوي) ([Service Types](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules)) | الأساس المفهومي لـ«باقة + إضافات» |
| **تسعير بالقيمة** | **لم أجد توثيقاً** لأي منتجٍ يسمّيه نمطاً أولياً؛ المنتجات تسعّر بالمبلغ الثابت أو الساعة | لا أدّعي انتشاره |

**تحفّظ صريح:** **لا مصدر عندي يقيس شيوع كل نموذج** (نِسَبٌ أو مسح مهني). فما أعلاه «ماذا تدعم الأدوات» لا «كم يستعمله المكتب». أي ترتيب شيوعٍ في §6 هو **توصيتنا وتقديرنا** لا نتيجة بحث.

### 5.2 آليات الفوترة المتكررة: مسودة، إرسال، تناسب، إضافات

- **مسودة vs إرسال آلي.** TaxDome: الافتراضي في الإنشاء هو **الإرسال** (`Create`)، وخيار `Save as draft` يوضع في تبويب `Inactive` بحالة `Draft`، «غير مرئية للزبون حتى تضغط Create»، و`Balance` يظهر `$0.00` حتى الإنشاء ([Recurring invoices](https://help.taxdome.com/article/995-recurring-invoices-recurring-invoices-basic-create-schedule-save-as-draft)). أي أن المنتج يملك **الحالة** لا الافتراض: الافتراض عندهم إرسال، والمسودة خيار. ونحن نعكس الافتراض (مسودة ثم اعتماد) **لأنه قرار المالك المحسوم في التكليف**، لا لأن مصدراً يفضّله.
- **ماذا يحدث عند تأخّر التوقيع/الموافقة.** TaxDome ينصّ: «إن وقّع الزبون بعد تاريخ الفاتورة الأولى تُولَّد وتُحصَّل كل الفواتير الفائتة تلقائياً» — أي لا تناسُب ولا إسقاط، بل **تجميع الفائت** ([المصدر نفسه](https://help.taxdome.com/article/995-recurring-invoices-recurring-invoices-basic-create-schedule-save-as-draft)). هذا سلوك منتجٍ ببطاقة، ولا ننقله حرفياً.
- **التناسب (proration).** **لم أجد في أيٍّ من الصفحات التي قرأتها** ذِكراً للتناسب عند الانضمام وسط الشهر. فالتوصية فيه **لنا** (§6)، وموسومة كذلك.
- **الإضافات على الفاتورة الشهرية.** في المنتجات: `Services` تُضاف للفاتورة ([TaxDome](https://help.taxdome.com/article/1843-invoicing-overview))، والوديعة نوع خدمة منفصل ([Ignition](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules)). أمّا «إضافة خدمة إلى المسودة الشهرية الجارية» فآليةُ تنفيذ لا يوثّقها أحدٌ صراحةً؛ TaxDome يقرّبها بفكرة أن **إعدادات التذكير/الفوترة تُورَّث من القالب** لكل ما يُنشأ منه ([Reminders reference](https://help.taxdome.com/article/reminders-reference)) — أي أن القالب هو مصدر السلوك.
- **إعادة المحاولة عند فشل السحب.** TaxDome: محاولة واحدة بعد **4 ساعات**، ثم يحتاج الزبون تحديث وسيلته ([المصدر](https://help.taxdome.com/article/995-recurring-invoices-recurring-invoices-basic-create-schedule-save-as-draft)). لا أثر له عندنا (لا سحب آلي) لكنه يبيّن أن الفشل يُدار كسجلّ لا كخطأ.

### 5.3 الملاحقة والتحصيل

**(أ) متى تصير الفاتورة متأخرة؟** TaxDome: إعداد `Days before marked overdue` في `Settings > Billing > General`، والفواتير المتأخرة تُظلَّل وتُفلتر بحالات `Unpaid/Partially paid/Overdue` ([Manage overdue](https://help.taxdome.com/article/429-how-to-manage-overdue-invoices)).

**(ب) التذكيرات: جدولٌ يضبطه المكتب لا عددٌ ثابت.** الحقول المنصوصة:
- **`Days until next reminder` — الافتراضي 3.**
- **`Number of reminders` — الافتراضي 1.**
([Reminders reference](https://help.taxdome.com/article/reminders-reference))

**(ج) شرط التوقف شرطُ حالة، ودقيق.** الجدول الرسمي: تذكيرات **الفاتورة** تتوقف عند «سداد الفاتورة **كاملاً** — الدفع الجزئي **لا** يوقف التذكير»، أو نفاد العدد، أو أرشفة العمل المرتبط؛ وتذكيرات **طلب المستند** تتوقف عند إرسال الزبون أو تغيير المكتب حالته إلى `Completed`؛ و**المحادثة** عند إتمام مهام الزبون فيها أو أرشفتها ([المصدر نفسه](https://help.taxdome.com/article/reminders-reference)). ولا حقّ وصولٍ منفصلٌ للتذكير: «مَن يستطيع إرسال الكائن يستطيع ضبط تذكيره» ([Reminders explained](https://help.taxdome.com/article/119-automatic-reminders)).

**(د) التذكير اليدوي والجماعي.** زرّ `Resend` لكل فاتورة، و`Select all items` لإعادة الإرسال لكل ما يطابق الفلتر، مع استثناء تلقائي للمسدّد والمسوَّد والمجدول ([Manage overdue](https://help.taxdome.com/article/429-how-to-manage-overdue-invoices) · [Reminders reference](https://help.taxdome.com/article/reminders-reference)).

**(هـ) كشف الحساب وغرامات التأخير.** Canopy يملك **غرامة تأخير آلية متكرّرة** تُطبَّق على الفواتير العادية والمتكررة، وتُعاد على الجدول المضبوط ما دامت غير مدفوعة ([FAQ Billing](https://support.getcanopy.com/en/articles/9375786-faq-billing-invoicing)). وتقارير الأعمار موجودة عناوينَ في فهرسَي Financial Cents (`Accounts Receivable Aging Report`) وCanopy (`insights-aged-receivables-summary`) — لم أقرأ نصّها.

**(و) «أوقف العمل حتى يدفع».** آليتان موثّقتان تتقاربان:
- **TaxDome — `Lock docs to invoices`:** يربط المستند بفاتورة فيراه الزبون **`Pending payment`** ولا يفتحه/ينزّله حتى السداد، و«السداد الجزئي غير ممكن»، ويلزم لتفعيله: إعداد المدفوعات + أن يكون المستند في **مجلد يراه الزبون**، ويُفتح يدوياً عند الحاجة، ويمكن وصله بمسار عمل فيتقدّم العمل تلقائياً عند الفتح ([المصدر](https://help.taxdome.com/article/141-locking-a-document-to-a-bill)).
- **Financial Cents — `Lock Client Files Behind an Invoice`:** الملفات تُقفل فوراً، والزبون يرى الاسم ولا يفتح، و«الدفع الجزئي لا يفتح»، ويُفتح آلياً عند السداد الكامل، مع أيقونة قفلٍ مغلق/مفتوح وسجلّ «أي فاتورة تقفل أي ملف» ([المصدر](https://help.financial-cents.com/en/articles/14630941-lock-client-files-behind-an-invoice)).

### 5.4 وسائل الدفع المحلية — ما أمكن إثباته وما لم يمكن

**المؤكَّد من المصادر:**

- المنتجان المهنيان يتعاملان مع **النقد والشيك والتحويل البنكي** كوسائل تُسجَّل يدوياً: TaxDome: «سجّل دفعة نقداً أو بشيك أو بتحويل بنكي»، ولا دفع جزئي، وإن لم تُسدَّد الفاتورة كاملةً تُضاف كرصيد دائن ([Offline payments](https://help.taxdome.com/article/offline-payments)).
- **إسرائيل:** فهرس قاعدة معرفة **iCount** يبيّن أن الآلية المتكررة المحلية هي **הוראות קבע** (أوامر دفع ثابتة) «بالائتمان **أو** الحساب البنكي»، وفيها وحدة **סליקת אשראי** (مقاصة بطاقات) عبر مزوّدي إسراكارد/ויזה כאל/מקס، ووحدة **נודניק** أي «تذكيرات دفع للزبائن» ([فهرس iCount](https://help.icount.co.il/) · [הוראות קבע](https://help.icount.co.il/standing-orders/)). أي أن السوق الإسرائيلي يعرف الاشتراك الشهري **كهيئة دفع بنكية/بطاقية ثابتة** لا كفاتورة بريدٍ فقط.
- **فلسطين:** **لم أقرأ مصدراً محلياً** — `pma.ps` (سلطة النقد) ردّ بلا نصّ. فلا أدّعي شيئاً عن شيوع الشيك أو غلبة النقد أو Bit/PayBox في المكاتب.

**توصيتنا (موسومة):** وسائل الدفع عندنا **سجلّ يدوي بالدرجة الأولى**: نقد · شيك (بتواريخه وحالاته) · تحويل بنكي · وبطاقة/Bit/PayBox كـ«وسيلة مسجَّلة» بلا ربط مقاصة في v1. لا نموذج بوابة دفع ولا سحب آلي، لأن **الزبون لا يسجّل دخولاً** أصلاً — وهو ما يجعل `offline payments` في TaxDome أقرب آليةٍ إلى حالتنا.

### 5.5 توصيتنا في الأتعاب

1. **افتراضي العميل: اشتراك شهري ثابت + بنود إضافية بسعرٍ خاص.** الاشتراك يُنشئ **مسودة** كل شهر؛ والاعتماد فعلٌ بشري. والبنود الإضافية (تصديق، تدقيق، استشارة، إقرار سنوي) تُضاف إلى **المسودة نفسها** لا كفاتورة ثانية — هذا يطابق قرار المالك ويبسّط على الزبون.
2. **الساعة متاحة ومطفأة.** لا تُفتح إلا لمكتبٍ يقرّر تسجيل وقته؛ وعندها فقط يُعرض عمود استهلاك الساعات. سبب الإطفاء: كل أدوات «السعة/الساعات» تفترض تسجيل وقتٍ صريحاً (§4.2).
3. **التناسب (proration): مفتاحٌ باسمه، افتراضه مفعّل للشهر الأول فقط** — يُحسب بعدد الأيام من تاريخ بدء الخدمة. **دليلٌ صفري**: لا مصدر يوثّق التناسب، فهو قرار لنا؛ وقرارنا أن يبقى بسيطاً وقابلاً للإطفاء.
4. **التحصيل الافتراضي:** استحقاق بعد **7 أيام** من إصدار المسودة المعتمدة (مهلة تسمح بالتحصيل النقدي). تذكير أول بعد **3 أيام** من الاستحقاق (مطابقٌ لافتراضي TaxDome)، وتذكير ثانٍ بعد **7 أيام** منه (نرفع العدد من 1 إلى 2 لأن وسائلنا بلا سحبٍ آلي)، وسقف **2** ثم تصعيدٌ يدوي إلى المالك.
5. **كشف حساب شهري لكل زبون** يُطبع/يُرسل بضغطة — ليس عند أيٍّ من البرامج التي قرأتها ككائن «كشف» مستقل (تقرير أعمارٍ فقط)، ولنا أن نجعلَه أرخص لأن الزبون لا يدخل.
6. **حجب المخرجات: مطفأ افتراضياً، ومفتاحٌ للعميل.** عند التشغيل: لا تُسلَّم «المخرَج النهائي» (إقرار، قوائم مالية) حتى سداد الفاتورة، ويُسجَّل التسليم بالتاريخ. هذا نظير TaxDome/FC في عالمٍ بلا بوابة: «مقفلٌ حتى الدفع» يُترجم إلى **«لم يُسلَّم بعد»** في سجلّنا لا إلى قفل ملفٍ رقمي.
7. **لا غرامات تأخير آلية افتراضياً** (Canopy يشحنها) لأن السوق المحلي يجرّبها اجتماعياً بشكل مختلف؛ تُترك خياراً.
8. **ربطٌ لا تكرار:** الشيكات القابلة للتحصيل وحالاتها موجودة أصلاً في موديول `accounting` في المشروع؛ فموديول المكتب يُسجّل **طريقة الدفع ونوعها** ويُحيل الشيك إلى كيان الشيك القائم بدل ابتلاع نظامٍ ثانٍ.

---

## 6) الافتراضيات المقترحة لنا

ملخّصٌ قابل للتنفيذ كمواصفة، لا «أفضل الممارسات» عند غيرنا:

**الإعداد `office_size`** (`solo` / `small` / `large`) — هو مفتاح الظهور الوحيد:
- `solo`: تُخفى الأدوار والإسناد وشاشة الإسناد بالكامل.
- `small`: ثلاثة أدوار + مفاتيح المبالغ والرؤية.
- `large`: أربعة أدوار + صلاحيات حبيبية اختيارية.

**الأدوار:** `owner` · `manager` · `staff` · `viewer`، حيث `manager` لا يملك: تغيير الأدوار، ولا إدارة المالكين، ولا الاشتراك/وسائل دفع الاشتراك (اقتباسٌ محدَّد من استثناءات TaxDome).

**المفاتيح (لكل دور، لا داخل الكود):** `sees_all_clients` (staff: false) · `sees_amounts` (staff: false) · `can_message_clients` (staff: true, مقيَّد بزبائنه) · `can_approve_monthly_invoice` (owner, manager) · `can_lock_deliverables` (owner, manager) · `can_export`.

**الأتعاب:** `billing_model = retainer+extras` افتراضياً · `generate_draft_on_day` (يوم الشهر) · `prorate_first_month = on` · `due_days_after_issue = 7` · `reminders = [3, 7]` مع سقف 2 وتوقفٍ عند السداد الكامل · `statement_monthly = on` · `lock_deliverables = off` · `late_fee = off`.

**الضغط:** عدّادات لكل موظف: `clients_count`, `overdue_items`, `missing_docs`, `overdue_amount_clients`؛ عتبة احمرارٍ إعدادية (20% متأخرات أو 1.5× المتوسط) بدل ساعات.

**الإسناد:** `client.owner_staff_id` إلزامي؛ `work_item.assignee` يرِث ويُتجاوز؛ `invoice.assignee` يرِث من الزبون؛ `message.sent_by` يُسجَّل ولا يُسنَد.

---

## 7) ما بقي غير مؤكَّد

1. **Karbon — أسماءٌ بلا سلوك** (كما في البحث السابق): الـJS يمنع النصّ. من العناوين: أدوار عمل (`job roles`) و`Analytics access permissions` و`without edit rights` و`Can anyone send and export invoices` — أي أن **الفوترة صلاحيةُ وصولٍ منفصلة** عندهم، وهذا استنتاجٌ من عنوانٍ لا نصّ.
2. **Xero Practice Manager — صفر.** لا نصّ من `central.xero.com` ولا صفحة منتج عامة (404). فلا أعرف أدواره الافتراضية ولا آلياته، وهو ثغرةٌ في الجدول لأن سؤاله كان صريحاً في التكليف.
3. **Financial Cents — نطاق رؤية الزبائن لدور `Member` غير مؤكَّد.** المؤكَّد أن **المبالغ للمالك وحده** افتراضياً.
4. **Canopy — رسائل الزبون ومراسلة الموظف** لم أقرأ لها نصّاً، وقائمة مجموعات الصلاحيات الجاهزة **لم أقرأها كاملةً**؛ المؤكَّد أربعة أسماء فقط.
5. **Jetpack — هل يملك فوترة؟** لا قسم فوترة في فهرسه؛ وغياب القسم لا يثبت الغياب.
6. **Bit وPayBox — لم أُثبت شيئاً.** كل الصفحات الرسمية التي جرّبتها (`payboxapp.com`) بلا نصّ، ونطاق مساعدة `greeninvoice` غير موجود. فلا أزعم أنهما شائعان أو غير شائعين؛ التوصية بجعلهما «وسيلة مسجَّلة» **قرارُ تصميمٍ** لا نتيجة بحث.
7. **فلسطين — لا مصدر محلي مقروء.** لم أتحقّق من إلزام الفاتورة الإلكترونية ولا من شيوع الشيك ولا من دور سلطة النقد. يلزم مصدرٌ عربي محلي (وزارة المالية/سلطة النقد/غرفة التجارة) أو مقابلات ميدانية قبل تثبيت افتراضات التحصيل.
8. **التناسب (proration) و«كشف الحساب»** لا توثيق لأيٍّ منهما في المنتجات التي قرأتها؛ ما ورد في §5.5 قرارُنا.
9. **لا قياس لشيوع نماذج التسعير.** لم أجد مسحاً مهنياً (AICPA/ICAEW/غيره) في هذه الجلسة، فترتيب النماذج تقديرٌ لا نتيجة.
10. **حدّ منهجي عام:** هذه الأدوات مبنية على بوابة زبون ومدفوعات بطاقة؛ وكل ما نقلته عن «توقف التذكير عند إتمام الزبون» لا مقابلَ له عندنا (الموظف هو من يعلّم «وصل»). فالنقل هنا **تشبيهُ آلية** لا نقلُ اعتماد.

---

## 8) المصادر

**TaxDome — `help.taxdome.com` (مقروء بالكامل هذه الجلسة؛ كان محجوباً سابقاً)**
- [System roles explained](https://help.taxdome.com/article/601-team-basic-owner-admin-employee-roles)
- [Employee access rights](https://help.taxdome.com/article/193-team-member-access-rights)
- [Assignment explained](https://help.taxdome.com/article/380-assignees-and-account-access-how-everything-works-together)
- [Weekly capacity](https://help.taxdome.com/article/1745-weekly-capacity)
- [Invoicing explained](https://help.taxdome.com/article/1843-invoicing-overview)
- [Send recurring invoices](https://help.taxdome.com/article/995-recurring-invoices-recurring-invoices-basic-create-schedule-save-as-draft)
- [Manage overdue invoices](https://help.taxdome.com/article/429-how-to-manage-overdue-invoices)
- [Reminders explained](https://help.taxdome.com/article/119-automatic-reminders) · [Reminders reference](https://help.taxdome.com/article/reminders-reference)
- [Lock docs to invoices](https://help.taxdome.com/article/141-locking-a-document-to-a-bill)
- [Accept cash payments and transfers via offline payments](https://help.taxdome.com/article/offline-payments)
- [Hide invoices from clients](https://help.taxdome.com/article/183-hiding-billings) (قرئ للسياق: لا علاقة له برؤية الموظف)

**Financial Cents — `help.financial-cents.com`**
- [Customize User Permissions](https://help.financial-cents.com/en/articles/4914265-customize-user-permissions)
- [Can my team see client billing information?](https://help.financial-cents.com/en/articles/7208803-can-my-team-see-client-billing-information)
- [Capacity Management](https://help.financial-cents.com/en/articles/4464492-capacity-management)
- [Show Current Assignee filter](https://help.financial-cents.com/en/articles/4486865-how-does-the-show-current-assignee-filter-work)
- [Lock Client Files Behind an Invoice](https://help.financial-cents.com/en/articles/14630941-lock-client-files-behind-an-invoice)
- [sitemap](https://help.financial-cents.com/sitemap.xml) (لعناوين تقارير الأعمار)

**Canopy — `support.getcanopy.com`**
- [How do I Assign Access & Permission Sets?](https://support.getcanopy.com/en/articles/9375878-how-do-i-assign-access-permission-sets)
- [How Permission Sets Work](https://support.getcanopy.com/en/articles/13371632-how-permission-sets-work)
- [Assign team members and teams to a client](https://support.getcanopy.com/en/articles/9375888-assign-team-members-and-teams-to-a-client)
- [FAQ | Billing & Invoicing](https://support.getcanopy.com/en/articles/9375786-faq-billing-invoicing)

**Jetpack Workflow — `support.jetpackworkflow.com`**
- [Permissions Overview](https://support.jetpackworkflow.com/en/articles/9425583-permissions-overview)
- [Capacity Management — Weekly View](https://support.jetpackworkflow.com/en/articles/15935731-capacity-management-weekly-view)
- [sitemap](https://support.jetpackworkflow.com/sitemap.xml)

**Ignition — `support.ignitionapp.com`**
- [Service Types & Billing Rules](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules)

**Karbon — `help.karbonhq.com` (عناوين فقط)**
- [sitemap المقالات](https://help.karbonhq.com/s/sitemap-topicarticle-1.xml)
- عناوين مستعملة: [Overview of Karbon job roles](https://help.karbonhq.com/s/articles/2000285-overview-karbon-job-roles) · [Analytics access permissions](https://help.karbonhq.com/s/articles/9092220-analytics-access-permissions) · [Giving access without edit rights](https://help.karbonhq.com/s/articles/11146170-giving-access-without-edit-rights-in-karbon) · [Can anyone send and export invoices](https://help.karbonhq.com/s/articles/7240253-can-anyone-send-and-export-invoices)

**iCount (إسرائيل) — `help.icount.co.il`**
- [فهرس قاعدة المعرفة](https://help.icount.co.il/) (وصف الوحدات: הוראות קבע · סליקת אשראי · נודניק · CRM)
- [הוראות קבע](https://help.icount.co.il/standing-orders/) · [סליקת אשראי](https://help.icount.co.il/credit-card-processing/)

**لم يُقرأ / محجوب / غير موجود**
- **Xero Practice Manager**: `https://central.xero.com/s/article/...` → `HTTP 200` بلا نصّ (client-side)؛ `https://www.xero.com/us/practice-manager/` → `404`.
- **Karbon**: صفحات المقالات → جسمٌ عنوانه «Karbon Help» فقط.
- **سلطة النقد الفلسطينية**: `https://www.pma.ps/en/` → `HTTP 200` بعنوان الصفحة فقط.
- **بنك إسرائيل**: `https://www.boi.org.il/en/` → صفحة حماية «Radware Page».
- **PayBox**: `https://www.payboxapp.com` → `HTTP 200` بلا نصّ.
- **Green Invoice**: `https://help.greeninvoice.co.il/` → فشل DNS (`ENOTFOUND`).
- **Bit**: لم أجد صفحةً رسمية قابلة للقراءة في هذه الجلسة، فلا أزعم شيئاً عنه.
