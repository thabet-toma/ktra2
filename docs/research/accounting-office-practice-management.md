# كيف تنظّم برامج إدارة مكاتب المحاسبة شغل المكتب؟ — بحث مرجعي

للتذكرة [#251](https://github.com/thabet-toma/ktra2/issues/251): تصميم موديول «مكتب محاسبة» من الصفر على K.T.R.A.
السؤال: ما النمط الذي رسخته برامج **practice management** في تنظيم شغل المكتب — الكيانات، والعمل المتكرر، وطلب المستندات والتذكير، والأتعاب، والإسناد، ولوحات الصباح — وما الذي يكفيه مكتب صغير في فلسطين/إسرائيل منه وما الذي يزيد عن حاجته.

الغرض مفاهيميّ لا واجهيّ: لا نُقلَّد شاشةً ولا تسميةً، بل نلتقط **السلوك** الذي يتكرّر عند من يوثّق عمله رسمياً.

---

## منهج البحث وحدوده — يُقرأ أولاً

اعتُمدت **توثيقات المنتِج الرسمية** حصراً (help center / knowledge base)، لا مقالة تسويقية ولا مراجعة طرف ثالث. فُتحت وصُنِّفت كالتالي:

| البرنامج | التوثيق | الحالة |
|---|---|---|
| Financial Cents | `help.financial-cents.com` | مقروء بالكامل (Intercom) |
| Jetpack Workflow | `support.jetpackworkflow.com` | مقروء بالكامل (Intercom) |
| Canopy | `support.getcanopy.com` | مقروء بالكامل (Intercom) |
| Ignition | `support.ignitionapp.com` | مقروء بالكامل (Intercom) |
| Karbon | `help.karbonhq.com` | **عناوين المقالات فقط** — الصفحات تُبنى بالـJavaScript فلا نصّ في الـHTML |
| TaxDome | `help.taxdome.com` | **محجوب**: كل محاولة ردّت `HTTP 403` من Cloudflare («Just a moment…») |
| iCount (إسرائيل) | `help.icount.co.il` | مقروء لكن **ليس practice management** — تفصيله في §5 |

**تحفّظان يجب أن يُقالا صراحةً:**

1. **Karbon**: قرأتُ فهرس مقالاته (`sitemap`) وعناوينها الحرفية، وهي دليلٌ على **أسماء الكيانات عنده**، لكن **لا سلوك** — أيّ ادّعاء عن كيف يعمل عنده مُعلَّم «غير مؤكَّد».
2. **TaxDome**: لم أقرأ منه حرفاً. غيابه يُضعف المقارنة لأنه من أقرب البرامج لموضوعنا، ولذلك **لا أستنتج عنه شيئاً** ولا أُدرجه في الجدول كعمود مبنيّ على قراءة.

**وحدّ ثالث يخصّ سؤالنا نحن:** البرامج الخمسة كلها مبنية على أن **للزبون حسابٌ في البوابة** (Financial Cents يخفّفه بـ«magic link» بلا كلمة مرور، لكنه يبقى بوابة). نموذجنا المحسوم — زبائن المكتب **خارج المنصة** بلا تسجيل دخول — لا يقابله نموذجٌ في أيٍّ منها. هذا فرقٌ جوهري لا تفصيل، وأثره مبثوث في §3.3 و§4.

---

## 1) الملخّص — ما يتكرّر بين البرامج (المعيار الفعلي للمهنة)

1. **الوحدة الذرّية للعمل ليست المهمة بل «نسخة عملٍ لزبون في فترة»**: مشروع/مهمة متكررة/سلسلة (Financial Cents: *Project*، Jetpack: *Project* من *Series*، Canopy: *Recurring Task*). المهمة (task) خطوةٌ داخلها، والزمن هو زمن **الفترة** لا زمن المشروع ككل.
2. **قالب + تكرار يولّد الشغل، لا قائمةٌ يحرّرها المحاسب كل شهر**: «Templates → Clients → Projects → Tasks» هو النموذج الذهني الذي تعلنه Jetpack صراحةً، وهو نفسه عند Canopy وFinancial Cents.
3. **الفترة كيانٌ صريح**: Financial Cents يعطي المشروع حقل *Accounting Period* يتقدّم تلقائياً مع التكرار (Jan '22 ← Feb '22). هذه أهمّ فكرة في البحث كلّه بالنسبة لنا.
4. **التكرار يُولَّد بالحدث لا بالتقويم وحده**: Financial Cents يُنشئ النسخة التالية عند **إغلاق** الحالية **أو تجاوزها تاريخ الاستحقاق** (وظيفةٌ تعمل كل ساعة). Canopy يسمح بـ«upon completion of prior instance» بديلاً عن يومٍ ثابت. Jetpack يُبقي التوليد تقويمياً لكنه يحمي النسخ الجارية من تعديلات السلسلة.
5. **الاستحقاق مشتقّ لا مُدخل**: في Financial Cents تُعرَّف قاعدةٌ في القالب (قبل استحقاق المشروع بـN يوماً / بعد بدايته بـN) وتُحسب كل مواعيد المهام في تمريرة واحدة. Canopy أوسع: استحقاق «نسبةً إلى تغيّر حالة» لا إلى تاريخ.
6. **طلب المستندات سجلٌّ بحالات، لا رسالة**: Canopy يسمّي حالاته حرفياً: `Draft → With client → Needs review → Completed / Canceled`. التذكير ينتظر حالةً، ويتوقف حين تصل إلى `Completed`.
7. **الأتعاب مشتقّة من الخدمة لا من ساعات العمل**: Ignition يربط الاشتراك بـ*Service Type* (تكرار + تاريخ بدء + نهاية)، والفاتورة تسقط من الاتفاق لا تُكتب يدوياً؛ والتذكير بالدفع يتبع الفاتورة ويقف تلقائياً عند السداد.
8. **لوحة الصباح هي «قائمة العمل المفلترة»**: Financial Cents يُسمّيها *Workflow Dashboard* وهي أول ما يظهر عند الدخول؛ Canopy *Tasks List* + *Queued Work*؛ Jetpack *My Work*؛ Karbon *My Week*. الفلاتر المحفوظة (saved views) هي الميزة الحقيقية فيها، لا الرسوم.

---

## 2) جدول المقارنة

> العمود الأخير محدودٌ بشكلٍ معلن: **Karbon** من عناوين مقالاته فقط. و**TaxDome** لم يُقرأ (محجوب) فلا عمود له.

| المحور | Financial Cents | Jetpack Workflow | Canopy | Ignition | Karbon (أسماء فقط) |
|---|---|---|---|---|---|
| **1. الكيانات الأساسية** | Client · Client Group · Project (work) · Section · Team Task · **Client Task** · Template · **Accounting Period** · Tag · Portal · Invoice | **Template · Client (+Contact) · Project · Series · Individual Project · Task** | Client · Contact · Client Group · **Task / Subtask** · **Client Request** · Task Template · Task Workspace · Custom Status/Date | Client · Client Group · **Proposal** · **Service** · **Service Type (billing rule)** · Terms · Invoice · Payment | Contact/Organization · Client Group · **Work Item** · Work Template · **Engagement** · Client Request · Service Library |
| **2. العمل المتكرر** | مشروع يتكرر يومي/أسبوعي/شهري/ربعي/سنوي، أو Custom (نصف شهري، آخر يوم، أول جمعة…)؛ يُنشأ حتى **370 يوماً** مقدماً؛ قسمٌ يمكن استثناؤه من التكرار | سلسلة (Series) بجدول مخصّص: كل N يوم/أسبوع/شهر/سنة، تعدّد أيام الأسبوع، «ثاني اثنين»، «آخر يوم»، استثناء نهاية الأسبوع، تاريخ انتهاء | مهمة متكررة: **Repeats** + **Create** (يوم الشهر/نمط أسبوعي/عند إتمام السابقة) + **Due** + **Repeats until** (مدة/عدد/للأبد) | لا يولّد شغلاً؛ يولّد **فوترة**: Service Type بتردد (أيام/أسابيع/أشهر) وبداية (عند القبول/تاريخ البدء/تاريخ محدّد) ونهاية (بلا نهاية/بعد N مرة) | «Setup repeating work on a schedule» · «Work templates» |
| **3. طلب المستندات والتذكير** | Client Task داخل المشروع (مستند/توقيع/إرسال/سؤال)؛ إرسال فوري أو مجدول أو **معلَّق على إنجاز قسم**؛ **Auto-reminders** تكرّر بريداً وSMS **حتى إتمام الطلب**؛ تُجدول مرة فتتكرر مع المشروع | لا يظهر في فهرس توثيقه قسمٌ لطلبات المستندات | **Client Request** بحالات؛ أتمتة: «قبل الاستحقاق بـN يوم → أرسل بريداً»، «عند بلوغ الاستحقاق»، «عند تغيّر الحالة»، مع قوالب بريد | لا يطلب مستندات؛ يذكّر **بالدفع**: تذكيرات فاتورة على مستوى الحساب أو لكل فاتورة (متى وكم عدداً)، **تتوقف تلقائياً عند السداد** | «Overview of client requests» · «Send client requests» |
| **4. الأتعاب** | Billing (Beta) + تتبّع وقت + فوترة عبر QuickBooks؛ «Project Based Billing» | لا يوجد قسم فوترة في فهرسه (Time log في الخطط المدفوعة) | Time & Billing (67 مقالاً): وقتٌ قابل للفوترة، فواتير، مدفوعات، **Group Billing** لمجموعة زبائن | القلب: الاتفاق ← خدمة ← نوع خدمة ← فاتورة تلقائية؛ Deposits، Milestone، Catch-up periods، زيادة سنوية، Change orders | «Recurring billing» · «Billing runs» · «Fee types per service» |
| **5. الإسناد وضغط الشغل** | Assignee لكل عمل ومهمة؛ فلتر **Show Current Assignee**؛ أدوار نائبة في القوالب تُسند تلقائياً؛ تعديل جماعي للمسؤولين | Assignee + Project members لكل مشروع ومهمة؛ **Budgeted Time**؛ **Capacity Management** (أسبوعي/سنوي) | Roles & Assignees؛ **Capacity Planning Board (Beta)**؛ **Queued Work** (سحب عمل من طابور) | لا إسناد عمل ولا سعة — أدوات تقارير فقط | «My Week» · «Time budgets» · «Assign/reassign task» |
| **6. لوحات الصباح** | **Workflow Dashboard** أول شاشة بعد الدخول: الحالة، الزبون، البداية، الاستحقاق، المسؤول + فلاتر محفوظة + عمود Client Tasks بعدّاد `N/M` | **My Work** (ما عليّ، مرتّباً بالمستحق والمحجوب) + Projects + Capacity | **Tasks List** (فلاتر/عروض محفوظة/تثبيت/إجراءات جماعية) + Queued Work + Capacity Board | Dashboard + Collections + Payouts + Receivables | «My Week» · «View work and manage work views» |

---

## 3) المحاور الستة — النمط، والفروق، وما يصلح لنا

### 3.1 الكيانات الأساسية وأسماؤها

**النمط الغالب.** ثلاث طبقات تتكرر عند من يوثّق عمله رسمياً، بدرجاتٍ متفاوتة من التصريح:
**قالبٌ** (وصفة العمل، لا يخصّ زبوناً) ← **التزامٌ تجاه زبون** (اتفاق/باقة/سلسلة) ← **نسخة عملٍ لفترة** (Project/Recurring Task). والزبون نفسه سجلٌّ مستقل عن «جهة الاتصال»: Jetpack ينصّ: «One client can have multiple contacts, and one contact can be linked to multiple clients» ([How Jetpack Workflow Works](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works)). وCanopy يسمّي الطبقة العليا **Client & Contact Structure** ويضمّ تحتها Client Groups وEngagements وClient Portals ([فهرس Canopy](https://support.getcanopy.com/en/collections/9680294-client-contact-structure)).

**الفروق المهمة.**
- **الالتزام (engagement/agreement) ليس كياناً في الكل.** في توثيق Financial Cents وJetpack الذي قرأته **لا يظهر كيانُ اتفاق**: العلاقة بين الزبون والقالب/السلسلة مباشرة. Ignition يملكها صريحةً (*Proposal*) وهي مركز منتجه. Karbon يسمّيها *Engagement* ولديه **Service Library** ومكتبة قوالب التزام ([عناوين Karbon](https://help.karbonhq.com/s/articles/11707750-overview-of-engagements)).
- **«الفترة» كيانٌ صريح عند واحد فقط**: Financial Cents (*Accounting Period*: شهري/ربعي/سنوي، ويتقدّم تلقائياً مع التكرار) ([Accounting Periods](https://help.financial-cents.com/en/articles/5947205-accounting-periods-for-projects)). البقية يستنتجونها من تاريخ الاستحقاق.
- **طلب المستندات كيانٌ مستقل** عند Canopy (*Client Request* بحالات) وعند Karbon (*Client Requests*)، بينما هو عند Financial Cents **قسمٌ داخل المشروع** ([Client Tasks & Requests](https://help.financial-cents.com/en/articles/4213219-client-tasks-requests)) — فرقٌ في النمذجة لا في الوظيفة.

**ما يناسب مكتباً صغيراً في فلسطين/إسرائيل.** الطبقات الثلاث كلها، لكن **بالترتيب الذي قرّره المالك**: الباقة هي الالتزام، والقالب يبقى داخلياً (وصفة الخدمة) لا يظهر للمحاسب كخطوة إعداد. والفترة يجب أن تكون كياناً صريحاً لأن سؤال المكتب اليومي هو: «مستندات أيّ شهرٍ ينقصني من أيّ زبون؟».

**الزائد عن الحاجة.** `Client Group` ككيان (شركات متعددة المالك نفسه) و`Client Portal` و`Engagement letter` بالتوقيع الإلكتروني. مكتبٌ بأربعين زبوناً محلاً لا يحتاج طبقة تجميع؛ ويحتاج فقط «زبون ← فروع/أسماء تجارية» كحقل.

### 3.2 العمل المتكرر — كيف يتولّد شغل كل فترة

**النمط الغالب: التوليد، لا العرض.** في البرامج الثلاثة التي قرأت سلوكها (Financial Cents · Jetpack · Canopy) الشغل **سجلٌّ مادي يُنشأ** لكل فترة، لا نتيجةُ استعلامٍ على موعد — لأن السجل هو ما يُسند ويُعلَّم ويُفوتر ويُعاد فتحه بعد سنة.

الآلية كما وثّقها Financial Cents حرفياً: المشروع المتكرر يتكرر عند **إغلاقه** أو **تجاوزه تاريخ الاستحقاق**، والنسخة الجديدة تُنشأ **خلال ساعة** (وظيفة كل ساعة)، وتأخذ تعديلات النسخة السابقة معها ([Recurring Projects](https://help.financial-cents.com/en/articles/5043865-recurring-projects-how-they-work)). ويستثني أقساماً كاملة من التكرار («Do not recur all tasks») لخطوات التهيئة التي تحدث مرة واحدة.

**الاستحقاق مشتقّ.** في Financial Cents تُخزَّن **قاعدة** في القالب لا تاريخ: «قبل استحقاق المشروع بـN يوماً» أو «بعد تاريخ بدء المشروع بـN»، وتُحلّ كلها في تمريرة واحدة عند الإنشاء؛ وتعيين تاريخٍ يدوي لمهمة **يمحو** قاعدتها ([Due Date Constraints](https://help.financial-cents.com/en/articles/6779501-due-date-constraints-on-templates)). Canopy يذهب أبعد: الاستحقاق يمكن أن يكون «نسبةً إلى تغيّر حالة» بـN يوم/أسبوع/شهر ([Recurring Task — New Scheduler](https://support.getcanopy.com/en/articles/12524993-how-do-i-create-a-recurring-task-new-scheduler-beta)).

**حماية النسخ الجارية قاعدةٌ عند الاثنين.** Jetpack: تعديل القالب يسري على المشاريع **التي لم تبدأ**، وتعديل السلسلة على **النسخ التي لم تبدأ**، و«Entries already in progress or completed are never overwritten by upstream changes» ([How Jetpack Workflow Works](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works)). Canopy: تعديل تاريخ نسخةٍ واحدة لا يمسّ القالب، وتعديل القالب يسري على التوليدات **المستقبلية** فقط ([المصدر نفسه أعلاه](https://support.getcanopy.com/en/articles/12524993-how-do-i-create-a-recurring-task-new-scheduler-beta)).

**تفاصيل تقويمية يجهلها من يصمّم على عجل** (Jetpack، [Custom Repeat Schedules](https://support.jetpackworkflow.com/en/articles/17341565-custom-repeat-schedules)): من يختار «31» لا يحصل على شغل في فبراير/أبريل/يونيو/سبتمبر/نوفمبر — لذا «آخر يوم» خيارٌ منفصل؛ و«Exclude weekends» في الجدول الشهري **يقدّم** الموعد إلى الجمعة السابقة، وفي اليومي **يحذف** اليوم.

**الفروق المهمة.** Ignition لا يشارك في هذا المحور إطلاقاً: لا يولّد شغلاً، بل فوترة (وهذا اختيار منتجٍ لا نقص). وKarbon — بحسب عناوينه — يجمع الاثنين: «Setup repeating work on a schedule» + «Configure billing frequency and fee types for services».

**ما يناسب مكتباً صغيراً.** نموذج Financial Cents هو الأقرب لحاجتنا: **الباقة تولّد نسخة عملٍ لكل فترة، والاستحقاق قاعدةٌ مشتقة من الفترة** («الإقرار الضريبي مستحقٌ في اليوم 15 من الشهر التالي للفترة»)، والتوليد يحدث بمجرد إغلاق السابقة أو تجاوزها — فلا ينتظر المكتب أن يفتح أحدهم الشاشة. ويُضاف خيار «آخر يوم» و«تقديم نهاية الأسبوع» من Jetpack لأن الأعياد والعطل في فلسطين/إسرائيل تجعل هذا ضرورةً لا رفاهية.

**الزائد.** `Custom recurrence` بكل تعقيده (نصف شهري بنمط أسبوعي، إنشاء حتى 370 يوماً مقدماً، استحقاقٌ نسبةً إلى تغيّر حالة) — مكتب صغير يحتاج شهري/ربعي/سنوي + «آخر يوم» + تقديم العطلة. والتوليد المسبق قبل سنةٍ كاملة يشوّش أكثر مما ينفع.

### 3.3 طلب المستندات والتذكير الآلي

**النمط الغالب: الطلب سجلٌّ بحالات، والتذكير ينتظر الحالة.**

- **Canopy** يوثّق الحالات حرفياً: `Draft · With client · Needs review · Completed · Canceled` ([Client Request automations](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests))، والتذكير يُبنى كأتمتةٍ شرطية: «عندما يقترب الطلب من الاستحقاق بـ**N يوماً** → أرسل بريداً بقالب كذا»، أو «عندما يبلغ الاستحقاق»، أو «عندما تتغيّر حالته إلى Needs review → أرسل». أي أنّ **الجدول عدديّ يضبطه المكتب**، والتوقف مشروطٌ بالحالة لا بعددٍ ثابت من الرسائل.
- **Financial Cents**: الطلب يُرسل فوراً أو **مجدولاً بتاريخ** أو **معلَّقاً على إنجاز قسمٍ في المشروع** (dependency). و**Auto-reminders** «تتابع الزبون تلقائياً **حتى يُتمّ** قائمة الطلبات»، ويرسل بريداً **وSMS**، ويُختار الإيقاع — والتوثيق لا يذكر أرقاماً محددة للإيقاع الافتراضي ([Client Tasks & Requests](https://help.financial-cents.com/en/articles/4213219-client-tasks-requests) · [Automated Client Reminders](https://help.financial-cents.com/en/articles/8781064-automated-client-reminders)). ونصيحة التوثيق: جدولة الطلب بتاريخ تجعله **يتكرر تلقائياً مع المشروع**، فلا يُعاد تفعيله كل شهر.
- **كيف يُعلَّم «وصل»**: عند Canopy بتغيّر حالة الطلب إلى `Completed`/`Needs review`؛ وعند Financial Cents بإتمام المهمة من الزبون في البوابة. **في الحالتين الفاعل هو الزبون**، ولوحة المكتب تعرض العدّاد: عمود *Client Tasks* في Financial Cents يُظهر `1/4` أي مهمةٌ واحدة ناقصة من أربع، مع تفصيلها عند التحويم ([Workflow Dashboard](https://help.financial-cents.com/en/articles/5390143-tracking-work-deadlines-in-your-workflow-dashboard)).
- **Jetpack** لا يظهر في فهرس توثيقه قسمٌ لطلبات المستندات أو بوابة زبون — وغياب القسم من الفهرس **لا يثبت الغياب** (قد يكون ضمن «Advanced Features» المدفوعة) فأتركه «غير مؤكَّد».

**الفروق المهمة.** الفرق الحقيقي بين الثلاثة هو **من يملك الحالة**: عند الجميع الزبون (عبر البوابة). ولا واحدٌ منها مصمَّم لـ«الزبون لا يسجّل دخولاً، والموظف يعرف شفهياً أنّ الورقة وصلت ثم يعلّمها بنفسه». وهذا بالضبط نموذجنا.

**ما يناسب مكتباً صغيراً.** سجلّ طلبٍ لكل فترة ولكل زبون، بحالاتٍ مختصرة (مطلوب · مُرسَل للزبون · وصل جزئياً · وصل · لا ينطبق)، وقائمة مستنداتٍ **قالبية** تأتي من الباقة (كشف بنك، فواتير مشتريات، كشف رواتب…) تُنسخ لكل فترة. والتذكير **بكبسة موظف** كما قرّر المالك — أي أن التذكير فعلٌ يدويّ مسجَّل لا أتمتة صامتة — مع **عدّاد تذكيرات** لكل طلب وسقف (مثلاً ثلاثة) وبصمة «آخر تذكير قبل N يوم» تمنع الإلحاح.

**الزائد.** بوابة الزبون، وSMS، والتوقيع الإلكتروني، والأتمتة الشرطية المتشعّبة (N يوماً قبل الاستحقاق → قالب بريد → إسناد مالك جديد). وكلها تفترض حساب زبونٍ لا نملكه.

### 3.4 الأتعاب

**النمط الغالب: الفاتورة تسقط من الالتزام، لا تُكتب.**

Ignition هو المرجع الأنضج: الاتفاق (*Proposal*) يحمل خدمات، والخدمات تُجمَّع في **Service Type** يحدّد **متى** تُفوتر المجموعة: التردد (متكرر: كل N يوم/أسبوع/شهر — أو لمرة واحدة)، وبداية الفوترة (عند القبول / تاريخ بدء الاتفاق / تاريخ محدّد، مع إمكان تأجيل)، ونهايتها (بلا نهاية / بعد N مرة) ([Service Types & Billing Rules](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules)). ويجوز أن يحمل الاتفاق **عدة أنواع خدمة معاً** (شهري + ربعي + سنوي) — وهو بالضبط شكل «اشتراك شهري + خدمات إضافية».

**التذكير بالدفع محورٌ منفصل ومقصود.** Ignition يفصل بين **تذكيرٍ قبل السحب التلقائي** ([Upcoming payment reminders](https://support.ignitionapp.com/en/articles/16146103-upcoming-payment-reminders)) و**تذكيرٍ بعد إصدار فاتورةٍ لم تُدفع** ([Invoice reminders](https://support.ignitionapp.com/en/articles/12151860-invoice-reminders)): «اختر متى تُرسل وكم عدداً» على مستوى الحساب، مع تجاوزٍ لكل فاتورة، و**إيقافٍ تلقائي عند السداد**، وسجلٍّ في تاريخ الفاتورة. ويلاحظ التوثيق أنّ التذكيرات **لا تُرسل** لفواتير مجدولة السحب أصلاً.

**الفروق المهمة.** Financial Cents يفوتر عبر QuickBooks (نموذج «لا تعِد بناء المحاسبة») ولديه «Project Based Billing»؛ Canopy يملك Time & Billing و**Group Billing** لمجموعة زبائن؛ Jetpack لا قسم فوترة في فهرس توثيقه (أداة سير عمل، والوقت فيها ميزةٌ مدفوعة). وأيّ البرامج لا يربط **موعد الاستحقاق بالفاتورة** إلا Ignition.

**ما يناسب مكتباً صغيراً.** نموذج Ignition مصغّراً: باقة ← بنود متكرّرة (اشتراك شهري) + بنود لمرة واحدة (خدمات إضافية: تصديق، تدقيق، استشارة) ← **جدول أتعاب** لكل زبون بتاريخ استحقاق، وعليه تنبيهٌ في لوحة الصباح لا سحبٌ آلي. والتحصيل عندنا نقدي/تحويل/شيك، لا بطاقة — فلا حاجة لبوابة دفع.

**الزائد.** Deposits، Milestone billing، Catch-up periods، الزيادة السنوية التلقائية، Change orders، Stripe/Payouts، وتجاوزات التذكير لكل فاتورة. مكتب صغير يحتاج «كم على هذا الزبون، ومن متى، وهل ذكّرناه».

### 3.5 الإسناد وضغط الشغل

**النمط الغالب: مسؤولٌ واحد لكل عمل، وقائمةُ «ما عليّ» تُشتقّ من ذلك.**

- Financial Cents: مسؤول (assignee) لكل مشروع ومهمة، وفلتر **Show Current Assignee** «يتيح للمدير أن يرى في أيّ طابورٍ يقف كل مشروع» ([Workflow Dashboard](https://help.financial-cents.com/en/articles/5390143-tracking-work-deadlines-in-your-workflow-dashboard))، وأدوارٌ نائبة في القوالب تُسند تلقائياً عند إنشاء العمل ([Placeholder roles](https://help.financial-cents.com/en/articles/7017275-placeholders-roles-for-templates)).
- Jetpack: مسؤول + أعضاء مشروع، و**Budgeted Time** لكل مهمة/مشروع، وشاشتا **Capacity Management** أسبوعية وسنوية ([Budgeted Time](https://support.jetpackworkflow.com/en/articles/9773463-budgeted-time) · [Capacity — Weekly](https://support.jetpackworkflow.com/en/articles/15935731-capacity-management-weekly-view)).
- Canopy: Roles & Assignees + **Capacity Planning Board (Beta)** + **Queued Work** (طابور يُسحب منه العمل بلا إسنادٍ مسبق) ([Queued Work](https://support.getcanopy.com/en/articles/16075779-how-do-i-pick-up-tasks-from-the-queued-work-tab)).
- Karbon: *My Week* و*Time budgets* (عناوين).

**الفروق المهمة.** الإسناد **على الزبون** مقابل الإسناد **على العمل**: البرامج كلها تُسند العمل (المشروع/المهمة) وليس الزبون. وإضافةُ السعة (capacity) ميزةٌ في الطبقة المدفوعة عند Jetpack وCanopy، وليست أصلاً عند Ignition.

**ما يناسب مكتباً صغيراً.** «كل زبون مُسنَد لموظف» كما قرّر المالك، ويُورَّث منه مسؤول كل نسخة عمل — هذا أوفر من إسنادٍ لكل مهمة، ومقروءٌ للمدير في جدولٍ واحد: صفوفٌ = موظفون، أعمدةٌ = عدد الزبائن، والشغل المتأخر، والتذكيرات المعلّقة. ورؤية المدير تكفيها **عدّادات** (لكل موظف: كم زبوناً، كم مستنداً ناقصاً، كم متأخراً) لا لوحة سعةٍ بصرية.

**الزائد.** Capacity Planning Board، وتقدير الساعات (budgeted hours)، و«سحب من طابور»، ونسب الاستغلال. مكتبٌ بثلاثة موظفين يعرف ضغطه بالنظر؛ والأسوأ أن تقدير الساعات يفرض على المكتب سلوكَ تسجيل وقتٍ لا يفعله.

### 3.6 لوحات العرض الرئيسية (ما يفتحه المكتب صباحاً)

**النمط الغالب.** شاشةٌ واحدة، جدولية، تُفلتر ولا تُرسَم: الحالة، الزبون، البداية، الاستحقاق، المسؤول، ثم **فلاتر محفوظة** بأسماءٍ خاصة بالمكتب («شغل هذا الأسبوع»، «بانتظار مستندات الزبون»). Financial Cents يعلن أنّ لوحته «أول ما تراه عند الدخول»، وأن الفلاتر تشمل النوع والوسوم والمسؤول والزبون والاستحقاق ومجموعة الزبائن، وأن العرض الافتراضي يمكن تثبيته ([Workflow Dashboard](https://help.financial-cents.com/en/articles/5390143-tracking-work-deadlines-in-your-workflow-dashboard) · [Saved filtered views](https://help.financial-cents.com/en/articles/5087436-create-saved-filtered-workflow-views)). Canopy يضيف تثبيت مهمةٍ في أعلى القائمة (pin) وعروضاً محفوظة قابلة للمشاركة ([Tasks List](https://support.getcanopy.com/en/collections/9480154-task-list)). Jetpack يجعل لوحة الموظف **My Work** مرتّبة بـ«المستحق والمحجوب».

**الفروق المهمة.** العمود الذي يخصّنا فعلاً هو **حالة طلب المستندات** بجانب كل عمل — وهو ما يفعله Financial Cents وحده بعمود `N/M` مع تفصيلٍ عند التحويم. ولا واحدٌ من البرامج يفتح صباحاً على «المتأخرات» وحدها؛ كلها تفتح على «كل شغلي» ثم تُفلتر.

**ما يناسب مكتباً صغيراً.** لوحتان لا أكثر: **«اليوم»** (ما استحقّ أو تأخّر، ومن المسؤول، وهل المستندات وصلت) و**«الزبائن»** (كل زبون: باقته، موظفه، ما ينقصه، أتعابه المتأخرة). وعدّاداتٌ أعلى الشاشة بدل الرسوم البيانية.

**الزائد.** التقارير المتشعّبة (Canopy يوثّق 185 مقالاً في فئة التقارير وحدها!) ومقاييس الربحية والاستغلال. مكتبٌ صغير يحتاج رقماً واحداً: «كم على الناس من فلوس، وكم متأخراً علينا من شغل».

---

## 4) معجم الكيانات المقترح (مفاهيم، لا كود) ومصدر كل مفهوم

العمود الأخير يبيّن **من أين جاء المفهوم**؛ وما ليس له مصدرٌ رسمي فهو **قرار تصميمٍ لنا** لا نقل.

| # | الكيان المقترح | ما يقابله عند الآخرين | المصدر |
|---|---|---|---|
| 1 | **مكتب المحاسبة** (Office) — شركةٌ على المنصة | Firm / Practice | لا كيانَ مقابل في أيٍّ منها (كلها للشركة الواحدة) — **قرارٌ لنا** |
| 2 | **الزبون** (Client) — سجلٌّ يملكه المكتب، بلا دخول | Client | [Jetpack](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works) · [Financial Cents](https://help.financial-cents.com/en/collections/3129390-client-database) |
| 3 | **جهة الاتصال** (Contact) — شخصٌ تابع للزبون | Contact | [Jetpack](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works) · [Canopy](https://support.getcanopy.com/en/collections/9680294-client-contact-structure) |
| 4 | **الخدمة** (Service) — ما يستطيع المكتب تقديمه (مسك دفاتر، إقرار، رواتب، تدقيق، استشارة) | Service / Service Library | [Ignition](https://support.ignitionapp.com/en/collections/2376663-library-of-services-terms-emails) · [Karbon](https://help.karbonhq.com/s/articles/11708950-building-your-first-service-in-the-service-library) |
| 5 | **الباقة** (Package) — الخدمات المشتراة لزبونٍ معيّن + دوريّتها | Service Type / Engagement / Series | [Ignition: Service Type](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules) · [Jetpack: Series](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works) |
| 6 | **الفترة** (Period) — الشهر/الربع/السنة التي يخدمها العمل | **Accounting Period** | [Financial Cents](https://help.financial-cents.com/en/articles/5947205-accounting-periods-for-projects) — أنضج تصريحٍ بهذا المفهوم |
| 7 | **نسخة العمل** (Work Item) — شغلٌ لزبون في فترة، يتولّد من الباقة | Project / Recurring Task instance | [Jetpack: Project/Series](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works) · [Financial Cents: Recurring Projects](https://help.financial-cents.com/en/articles/5043865-recurring-projects-how-they-work) |
| 8 | **الخطوة** (Task) — ما يفعله الموظف داخل نسخة العمل | Task / Subtask | [Canopy](https://support.getcanopy.com/en/collections/9480152-workflow-automation) · [Jetpack](https://support.jetpackworkflow.com/en/articles/9014850-overview-of-an-individual-project-profile) |
| 9 | **قائمة المستندات المطلوبة** (Document Request List) — لكل زبون لكل فترة | Client Request / Client Task | [Canopy: Client Request](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests) · [Financial Cents: Client Tasks](https://help.financial-cents.com/en/articles/4213219-client-tasks-requests) |
| 10 | **بند المستند** (Document Item) بحالة: مطلوب · مُرسَل · وصل جزئياً · وصل · لا ينطبق | Client Request statuses | [Canopy](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests) — الحالات حرفياً |
| 11 | **التذكير** (Reminder) — فعلٌ يسجّله الموظف بكبسة، مع عدّادٍ وسقف | Auto-reminder / reminder timing | [Financial Cents](https://help.financial-cents.com/en/articles/8781064-automated-client-reminders) · [Ignition](https://support.ignitionapp.com/en/articles/12151860-invoice-reminders) |
| 12 | **الاستحقاق** (Due Date) — مشتقٌّ من الفترة بقاعدة، لا مُدخلٌ يدوي | Due date constraint | [Financial Cents](https://help.financial-cents.com/en/articles/6779501-due-date-constraints-on-templates) — أدقّ توثيقٍ للفكرة |
| 13 | **الإسناد** (Assignment) — زبونٌ ← موظف، يورَّث لكل نسخة عمل | Assignee / Owner | [Financial Cents](https://help.financial-cents.com/en/articles/5390143-tracking-work-deadlines-in-your-workflow-dashboard) · [Canopy](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests) |
| 14 | **جدول الأتعاب** (Fee Schedule) — اشتراكٌ شهري + بنودٌ لمرة واحدة، مربوطٌ بالخدمة | Service Type / recurring billing | [Ignition](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules) · [Karbon](https://help.karbonhq.com/s/articles/8753810-use-recurring-billing) |
| 15 | **فاتورة/مستحق** (Charge) + تذكير دفع | Invoice + invoice reminders | [Ignition](https://support.ignitionapp.com/en/articles/12151860-invoice-reminders) |
| 16 | **لوحة اليوم** (Today Board) | Workflow Dashboard / My Work | [Financial Cents](https://help.financial-cents.com/en/articles/5390143-tracking-work-deadlines-in-your-workflow-dashboard) · [Jetpack](https://support.jetpackworkflow.com/en/collections/8575608-my-work) |
| 17 | **قالب الخدمة** (Service Template) — وصفةٌ داخلية: خطواتٌ وقائمة مستنداتٍ وقاعدة استحقاق | Work Template / Task Template | [Jetpack](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works) · [Canopy](https://support.getcanopy.com/en/collections/9480155-task-templates) |
| 18 | **قالب دورة العمل** (Cycle Template) — يُنتج التكرار: يوم الاستحقاق، آخر يوم، تقديم نهاية الأسبوع | Custom recurrence | [Jetpack](https://support.jetpackworkflow.com/en/articles/17341565-custom-repeat-schedules) |

**ملاحظتان على المعجم.** الأولى: **17 و18 منفصلان قصداً** — البرامج تخلط «وصفة العمل» و«متى يتكرر» في كائنٍ واحد، وخلطهما هو ما يجعل تعديل الخطوات يُعيد كتابة تاريخ التكرار بالخطأ. الثانية: **الكيان 2 بلا 3 يكفي** لمكتبٍ محلّي، و«جهة الاتصال» تُبقى لأن الزبون شركةٌ وله أكثر من مخاطَب (صاحب المحل، المحاسب الداخلي).

---

## 5) ما بقي غير مؤكَّد

1. **TaxDome — لم يُقرأ شيء.** كل مسارات `help.taxdome.com` ردّت `403` (Cloudflare). ومع أنه من أقرب البرامج لنا (Jobs/Accounts/Documents/Proposals)، **لم أُدرج له عموداً ولا ادّعاءً**. يلزم مصدرٌ آخر للتحقق منه.
2. **Karbon — أسماءٌ بلا سلوك.** التوثيق يُبنى بالـJavaScript فلم يصل نصّ. المؤكَّد فقط **عناوين المقالات** (وهي دليلٌ على التسمية): `Overview of work` · `Setup repeating work on a schedule` · `Overview of engagements` · `Overview of client requests` · `Use recurring billing` · `Create a billing run` · `Overview of My Week` · `Overview of time budgets` ([Sitemap الرسمي](https://help.karbonhq.com/s/sitemap-topicarticle-1.xml)). **غير مؤكَّد**: كيف يولّد تكراره، وهل طلباته بحالات، وهل أتعابه مشتقّة من الـEngagement.
3. **إيقاع التذكير بالأرقام.** لا توثيقٌ من الأربعة يذكر عدّاً افتراضياً (كل كم يوم؟ كم مرة قبل التوقف؟). المؤكَّد أنّ الإيقاع **قابل للضبط** وأن التوقف **مشروطٌ بالإتمام** ([Financial Cents](https://help.financial-cents.com/en/articles/8781064-automated-client-reminders) · [Ignition](https://support.ignitionapp.com/en/articles/12151860-invoice-reminders)) — أمّا «كل 3 أيام، ثلاث مرات» فهي **عادة سوقٍ لا نصّ**.
4. **Jetpack وطلبات المستندات.** لا قسم لها في فهرس توثيقه؛ وقد تكون ضمن «Advanced Features» المدفوعة ([الفهرس](https://support.jetpackworkflow.com/en/)). غياب القسم **لا يثبت الغياب**.
5. **Canopy «Engagements».** مذكورةٌ في فهرس Client & Contact Structure وClient Engagement، ولم أقرأ نصّها؛ فلا أزعم أنها اتفاقٌ بأتعاب كاتفاق Ignition.
6. **فوترة Financial Cents.** فئة «Billing (Beta)» موجودة (24 مقالاً) لكنني لم أقرأ تفاصيلها؛ المؤكَّد أنّ الفوترة تمرّ عبر QuickBooks وأن هناك «Project Based Billing» بعنوانه فقط.
7. **إسرائيل والعالم العربي — لم أجد برنامج practice management بتوثيقٍ رسمي.** جرّبتُ `help.qoyod.com` (Qoyod، السعودية) → النطاق غير موجود؛ و`help.brightmanager.co.uk` → فشل DNS؛ و`help.clienthub.app` → صفحةٌ بلا محتوى. أما **iCount** الإسرائيلي فتوثيقه مفتوح (بالعبرية) لكن فهرسه يصف **منصة محاسبة وفوترة للمنشآت الصغيرة** لا إدارة مكتب: الوحدات هي: מסמכים (مستندات)، CRM «ניהול לקוחות, עובדים ומטלות» (زبائن وموظفون ومهام)، הוראות קבע (أوامر دفع متكررة)، הוצאות، מלאי، סליקה، דוחות ([فهرس iCount](https://help.icount.co.il/crm/)). لا وحدةَ «باقة زبون تولّد شغلاً لفترة» ولا «طلبات مستندات لكل فترة» — أي أنّ **الفراغ الذي نصمّمه فراغٌ حقيقي في السوق المحلي**، وهذا استنتاجٌ من فهرسٍ لا حكمٌ نهائي.
8. **حدّ منهجي عام:** هذه البرامج كلها **أمريكية/أسترالية**، وقواعدها الضريبية (1040، sales tax، VAT) تغيّر شكل الاستحقاق. عندنا الاستحقاق يتبع **شهرية/ثنائية الشهر لضريبة القيمة المضافة** وتقارير سنوية — وهذا يُبسّط التكرار لا يُعقّده.

---

## 6) المصادر

**Financial Cents — `help.financial-cents.com`**
- [Workflow & Automation (فهرس المحور)](https://help.financial-cents.com/en/collections/2776456-workflow-automation)
- [Recurring Projects: How They Work](https://help.financial-cents.com/en/articles/5043865-recurring-projects-how-they-work)
- [Due Date Constraints on Templates](https://help.financial-cents.com/en/articles/6779501-due-date-constraints-on-templates)
- [Accounting Periods for Projects](https://help.financial-cents.com/en/articles/5947205-accounting-periods-for-projects)
- [Client Tasks & Requests](https://help.financial-cents.com/en/articles/4213219-client-tasks-requests)
- [Automated Client Reminders](https://help.financial-cents.com/en/articles/8781064-automated-client-reminders)
- [Tracking Work & Deadlines in Your Workflow Dashboard](https://help.financial-cents.com/en/articles/5390143-tracking-work-deadlines-in-your-workflow-dashboard)
- [Client Portal, requests & documents (فهرس)](https://help.financial-cents.com/en/collections/2776461-client-portal-requests-documents)
- [Client Database (فهرس)](https://help.financial-cents.com/en/collections/3129390-client-database)
- [Billing (فهرس، Beta)](https://help.financial-cents.com/en/collections/10663376-billing)
- [Placeholders roles for templates](https://help.financial-cents.com/en/articles/7017275-placeholders-roles-for-templates)
- [Create Saved Filtered Workflow Views](https://help.financial-cents.com/en/articles/5087436-create-saved-filtered-workflow-views)

**Jetpack Workflow — `support.jetpackworkflow.com`**
- [How Jetpack Workflow Works](https://support.jetpackworkflow.com/en/articles/15648484-how-jetpack-workflow-works)
- [Custom Repeat Schedules](https://support.jetpackworkflow.com/en/articles/17341565-custom-repeat-schedules)
- [Overview of an Individual Project Profile](https://support.jetpackworkflow.com/en/articles/9014850-overview-of-an-individual-project-profile)
- [Impact of Edits to Templates, Series, and Individual Entries](https://support.jetpackworkflow.com/en/articles/10270050-impact-of-edits-to-templates-series-and-individual-entries)
- [Budgeted Time](https://support.jetpackworkflow.com/en/articles/9773463-budgeted-time)
- [Capacity Management — Weekly View](https://support.jetpackworkflow.com/en/articles/15935731-capacity-management-weekly-view)
- [Projects (فهرس)](https://support.jetpackworkflow.com/en/collections/13879231-projects) · [My Work (فهرس)](https://support.jetpackworkflow.com/en/collections/8575608-my-work) · [Clients & Contacts (فهرس)](https://support.jetpackworkflow.com/en/collections/8575617-clients-contacts)

**Canopy — `support.getcanopy.com`**
- [Workflow & Automation (فهرس المحور)](https://support.getcanopy.com/en/collections/9480152-workflow-automation)
- [How do I create a Recurring Task? (New Scheduler)](https://support.getcanopy.com/en/articles/12524993-how-do-i-create-a-recurring-task-new-scheduler-beta)
- [What automations are available on Client Requests?](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests)
- [Client & Contact Structure (فهرس)](https://support.getcanopy.com/en/collections/9680294-client-contact-structure)
- [Time & Billing (فهرس)](https://support.getcanopy.com/en/collections/9480167-time-billing)
- [Capacity Planning Board View (Beta)](https://support.getcanopy.com/en/articles/12812362-how-do-i-use-the-capacity-planning-board-view-beta)
- [Pick Up Tasks From the Queued Work Tab](https://support.getcanopy.com/en/articles/16075779-how-do-i-pick-up-tasks-from-the-queued-work-tab)
- [Manage Task Statuses](https://support.getcanopy.com/en/articles/13000023-how-do-i-manage-task-statuses)

**Ignition — `support.ignitionapp.com`**
- [Service Types & Billing Rules](https://support.ignitionapp.com/en/articles/4163232-service-types-billing-rules)
- [Invoice reminders](https://support.ignitionapp.com/en/articles/12151860-invoice-reminders)
- [Upcoming payment reminders](https://support.ignitionapp.com/en/articles/16146103-upcoming-payment-reminders)
- [Proposals (فهرس)](https://support.ignitionapp.com/en/collections/2435078-proposals) · [Payments & Billing (فهرس)](https://support.ignitionapp.com/en/collections/2372968-payments-billing)
- [Library of Services, Terms & Emails (فهرس)](https://support.ignitionapp.com/en/collections/2376663-library-of-services-terms-emails)
- [Defining the proposal term: start date & minimum contract length](https://support.ignitionapp.com/en/articles/4163212-defining-the-proposal-term-proposal-start-date-minimum-contract-length)
- [Reporting Tools and The Dashboard (فهرس)](https://support.ignitionapp.com/en/collections/21678-reporting-tools-and-the-dashboard)

**Karbon — `help.karbonhq.com` (عناوين فقط)**
- [Sitemap الرسمي للمقالات](https://help.karbonhq.com/s/sitemap-topicarticle-1.xml)
- [Overview of work](https://help.karbonhq.com/s/articles/5834177-overview-of-work) · [Setup repeating work on a schedule](https://help.karbonhq.com/s/articles/6096234-setup-repeating-work-on-a-schedule) · [Overview of engagements](https://help.karbonhq.com/s/articles/11707750-overview-of-engagements) · [Overview of client requests](https://help.karbonhq.com/s/articles/1524439-overview-of-client-requests) · [Use recurring billing](https://help.karbonhq.com/s/articles/8753810-use-recurring-billing) · [Overview of My Week](https://help.karbonhq.com/s/articles/11012926-overview-of-my-week) · [Overview of time budgets](https://help.karbonhq.com/s/articles/4439115-overview-of-time-budgets)

**محجوب أو غير موجود**
- TaxDome: [help.taxdome.com](https://help.taxdome.com/en/) — `HTTP 403` من Cloudflare في كل محاولة.
- iCount (إسرائيل): [فهرس قاعدة المعرفة](https://help.icount.co.il/crm/) — مفتوح، لكنه منصة محاسبة للمنشآت لا إدارة مكتب محاسبة.
