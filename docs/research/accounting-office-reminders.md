# المواعيد والتذكير والرسائل الافتراضية — موديول «مكتب محاسبة»

بحثٌ تكميليّ يبني على أربعة أبحاثٍ سابقة ولا يعيدها (انظر §7-هـ). تاريخ الجمع: **2026-10-30**.
السؤال: ماذا تعني «المواعيد» في برامج إدارة مكاتب المحاسبة، وما **القيم الافتراضية** التي تُشحن بها
برامج المهنة للتذكير ورسائل الزبائن؟ ثم: ما الافتراضيّ الذي نطرحه نحن.

**اصطلاح الإسناد:** كل ما لم يُنسب إلى مصدرٍ صريح فهو **توصيةٌ لنا** لا نقل. وكل ما لم أقرأه
بنفسي مُعلَّم «لم يُقرأ» في §6 ولا يُبنى عليه حكم.

---

## 1) منهج البحث وحدوده

**دُفعت العقبةُ التي أوقفت البحث السابق.** تقرير practice management السابق سجّل أنّ
`help.taxdome.com` يردّ `403` من Cloudflare وأنّ Karbon يُبنى بالـJavaScript فلا نصّ — ومن ثمّ
**لم يُقرأ TaxDome إطلاقاً**، وهو أقربُ برنامجٍ لموضوعنا. في هذه الجلسة تبيّن:

- **TaxDome: صار مقروءاً.** مركزُ المساعدة يعمل على المسار `/article/<رقم>-<اسم>` (فالمسار
  `/en/` يردّ صفحةَ «Page not found»)، ويُقرأ نصُّه عبر وسيطٍ نصّيّ
  (`r.jina.ai`) يعيد محتوى الصفحة نفسها. فكلُّ ما في §3-أ و§4 أدناه من TaxDome **مقروءٌ من
  صفحته الرسمية**، خلافاً للبحث السابق.
- **Karbon: ما زال محجوباً** — يردّ قشرةَ تطبيقٍ + تحقّق CAPTCHA
  («This page maybe requiring CAPTCHA»)، فالمتاحُ عناوينُ المقالات من `sitemap` وحدها.
- **Xero Central: محجوبٌ بتحقّق CAPTCHA** — الصفحة تُبنى ثم تعود «Article Detail» فارغة؛ ولم أقرأ
  حرفاً من صفحات `central.xero.com`.
- **Canopy وIgnition وJetpack وQuickBooks: مفتوحة** وتُقرأ مباشرةً.

**ما قُرئ بنصّه (16 صفحة):** 7 صفحات TaxDome · 5 Canopy · 1 Ignition · 1 Jetpack · 2 QuickBooks.
والباقي (Karbon · Xero · فهرس Financial Cents الذي أعاد واجهةً فقط) عناوينُ أو محجوب.

**الحدّ الثالث، وهو الأهمّ لسؤالنا:** البرامج التي قرأتها كلها تفترض **بوابةَ زبون** أو بريداً
يستطيع الزبون أن يتصرّف عبره. نموذجنا المحسوم — زبون **بلا حسابٍ وبلا بريدٍ بالضرورة**، ورسالةٌ
يضغطها موظّف بعد مراجعتها — لا يقابله نموذجٌ في أيٍّ منها، وهذا يقلب معنى «التذكير» من أتمتةٍ
إلى **فعلٍ بشريّ مسجَّل**، ويجعل أرقام §4 أدناه مرجعاً للإيقاع لا للآلية.

---

## 2) الملخّص

1. **«المواعيد» عند المهنة مفهومان منفصلان لا يُدمجان:** (أ) **موعد الالتزام/العمل** — تاريخُ
   استحقاقٍ لمهمةٍ أو نسخةِ عمل، يُعرَض في تقويمٍ شبكيّ؛ (ب) **الموعد مع الزبون** — اجتماعٌ أو
   زيارةُ مكتب، ونمذجته عندهم **ليست كياناً** بل إحالةٌ إلى مُجدوِلٍ خارجيّ أو وحدةُ مواعيد منفصلة
   (§3). ولا برنامجَ واحداً من عائلة practice management يربط «الزيارة» بالدورة الضريبية.
2. **TaxDome — أرقامٌ افتراضية صريحة، وهي الوحيدة المنشورة التي بلغتُها:** «الأيام حتى التذكير
   التالي» = **3**، و«عدد التذكيرات» = **1**، لكل بندٍ ينتظر إجراءً من الزبون
   ([reference](https://help.taxdome.com/article/reminders-reference)).
3. **التذكير عندهم مشروطٌ بالإتمام لا بالتاريخ:** البند يظلّ يُذكَّر حتى يُنجَز (سداد، توقيع،
   إرسال، موافقة) أو تُنفَد العدّة أو يُؤرشَف العمل المرتبط — وتفاصيل التوقّف **تختلف باختلاف
   نوع البند** (السداد الجزئيّ لا يوقف تذكير الفاتورة) ([المصدر نفسه](https://help.taxdome.com/article/reminders-reference)).
4. **التذكير بالتاريخ موجودٌ لكنه ليس الافتراض:** Canopy يسمح بشرطٍ «عندما يقترب الطلب من
   الاستحقاق بـN يوماً» يُدخِله المكتب — **بلا قيمةٍ افتراضية منشورة**
   ([automations](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests)).
5. **الافتراضيّ يُوضع مرّةً في الأعلى ثم يُورَّث:** TaxDome على القالب ثم الأتمتة، وIgnition على
   مستوى الحساب (افتراضٌ لكل الفواتير) مع استثناءٍ لكل فاتورة
   ([Ignition](https://support.ignitionapp.com/en/articles/12151860-invoice-reminders)).
6. **التصعيدُ إلى الموظّف/المالك ليس سلوكاً افتراضياً في أيٍّ منها:** إشعاراتُ الفريق موجودة
   كـ«إجراء» يُوصَل يدوياً (Canopy) أو كتفضيلاتِ إشعارٍ شخصية (TaxDome، Jetpack) — لا سلّمَ
   تصعيدٍ جاهز. **سلّم التصعيد في §4-ج اقتراحُنا.**
7. **Jetpack بلا قناةٍ للزبون:** إشعاراته «تُبقي **أنت وفريقك** على علم» — أنواعها Overdue وProject
   وTask وMention، وكلُّ عضوٍ يضبط تفضيلاته
   ([notifications](https://support.jetpackworkflow.com/en/articles/9014992-notifications-overview)).
8. **والأهمّ عملياً:** أعلى فائدتين مستوحيتان من TaxDome وسهلتان عندنا — حقل **«تاريخ
   الاستلام»** وحقل **«الاستحقاق الداخليّ»** منفصلان عن تاريخ البدء والاستحقاق
   ([intake](https://help.taxdome.com/article/track-intake-and-internal-deadlines))، و**قالبُ
   الرسالة** الذي تُحرّره كلُّ مكتبٍ مرّةً (وهذا هو قرار المالك أصلاً).

---

## 3) المواعيد

### 3-أ. النموذج الأول: موعدُ العمل (استحقاقٌ لا لقاء)

هذا هو معنى «المواعيد» الغالب في البرامج: **تواريخُ المهام ونسخ العمل**، لا لقاءات.

- **TaxDome** يسمّي الشاشة **Calendar**، ويفتحها من `Workflow > Calendar`، وتعرض **المهام ونسخ
  العمل بحسب تاريخ البدء وتاريخ الاستحقاق**. العرضُ يوم/أسبوع/شهر، وتحويلُ «تاريخ الاستحقاق فقط»
  يُظهر الحدث في يومه بلا مدى، وبطاقاتٌ ملوّنة للتمييز السريع، وفلترٌ افتراضيّ باسم كلّ موظّف. ويمكن سحبُ الحدث لتغيير تاريخه، والفلاتر
  (المسؤول، الحساب، المسار والمرحلة، الحالة، الأولوية، الوسم) قابلةٌ للحفظ كقوالب
  ([Calendar view](https://help.taxdome.com/article/785-workflow-basic-calendar-view)).
  ولاحظ الفرق الذي ينصّ عليه التوثيق: **تاريخ البدء ليس تاريخ الإنشاء** — «هو التاريخ الذي يجب أن
  يبدأ فيه الموظّف المُسنَد العمل»، وقد يُنشأ العمل تلقائياً وتاريخُ بدئه لاحقاً (المصدر نفسه).
- **TaxDome** أضاف حقلين يفصلان «متى وصلت الورق» عن «متى يجب أن أسلّم»: **Intake date** (تاريخ
  الاستلام الفعليّ) و**Internal deadline date** (هامشٌ داخليّ قبل الاستحقاق الرسميّ)، وهما
  مستقلّان عن Start/Due، ويُغذّيان مؤشّر **On Track / At Risk**، ويُستعملان لترتيب العمل FIFO
  ([Track intake and internal deadlines](https://help.taxdome.com/article/track-intake-and-internal-deadlines)).
  وهذا بالضبط السؤال اليوميّ للمكتب: «المستندات وصلت ولا لأ؟».
- **Canopy**: التقويم عنده **مرآةٌ** لتقويم Google أو Microsoft، لا كيانٌ داخليّ — «لا يمكنك إنشاء
  حدثٍ في Canopy إن لم يكن لديك تقويم Google أو Microsoft موصول»، والتقويم يُنسَخ 100%، **وتذكيرات
  التقويم تظلّ في التقويم الأصليّ ولا تظهر في Canopy**
  ([FAQ: Calendar](https://support.getcanopy.com/en/articles/9375785-faq-calendar)). فما يُعرَض
  للموظّف هو يومه، لا مواعيد المكتب.
- **Karbon** (عناوين فقط): `Overview of My Week` و`Use deadline dates in work` و`Filling deadlines
  overview` — أي أنّ اللقاء اليوميّ مع الاستحقاقات يمرّ بـ«أسبوعي» لا بتقويم مواعيد
  ([sitemap](https://help.karbonhq.com/s/sitemap-topicarticle-1.xml)).
- **Jetpack**: لا تقويم في فهرس توثيقه؛ العرضُ قائمةُ «ما عليّ» مرتّبةً بالمستحقّ، وإشعاراتٌ داخلية
  ([notifications](https://support.jetpackworkflow.com/en/articles/9014992-notifications-overview)).

**خلاصة النموذج:** الشكلُ الغالب للعرض **جدول/تقويم شبكيّ على مستوى المكتب + فلترة بالموظّف**،
ومعه **تبويبٌ في ملفّ الزبون**، ولوحةُ الصباح هي القائمة المفلترة. ولا شيء منه لقاءٌ بين إنسانين.

### 3-ب. النموذج الثاني: الموعدُ مع الزبون — إحالةٌ إلى مُجدوِلٍ خارجيّ

هذا هو الجواب الصريح على «كيف يعملون الحجز»: **لا يبنونه**.

- **TaxDome**: تبويب **Scheduler** في `Settings > Integrations` يربط **Calendly أو Acuity أو
  YouCanBookMe أو Schedulista**، فيظهر في صفحة البوابة الرئيسية زرُّ **Book appointment**، ويُفتح
  للزبون جدولُ المُجدوِل نفسه. ولا يحتاج المكتب إلا لصق الرابط؛ والتوثيق يقترح أتمتةً ترسل رابط
  الحجز عبر المحادثة أو البريد. وليس في فهرس مركز المساعدة أيُّ مقالٍ يبدأ بـ«appointment»: أقربُ
  ما فيه إلى المواعيد هو `embed-scheduler` (هذا المقال) و`kiosk` — وهذا **غيابٌ في الفهرس** لا
  إثباتُ غيابِ ميزة
  ([Connect a scheduler](https://help.taxdome.com/article/532-embed-scheduler)).
- **Canopy**: «Custom Links» في العلامة التجارية تتيح ثلاثة روابط جاهزة، أحدها **Appointment
  Scheduler**، تُعرَض في بوابة الزبون
  ([Third-party links & schedulers](https://support.getcanopy.com/en/articles/9375900-add-third-party-links-schedulers-to-the-client-portal)).
- **Karbon**: مقالُ تكاملٍ باسم `Calendly` في فهرسه — أي النمط نفسه (العنوان فقط؛ لم يُقرأ نصّه)
  ([sitemap](https://help.karbonhq.com/s/sitemap-topicarticle-1.xml)).

### 3-ج. النموذج الثالث: المواعيد وحدةً أصلية (خارج عائلة إدارة المكاتب)

الوحيدُ الذي قرأت فيه وحدةَ مواعيدٍ حقيقية هو **QuickBooks Online** (محاسبةُ منشأة، لا إدارةُ مكتب):
«Appointments» في `Customer Hub`، تُضبط فيه **أوقات التوفّر** الأسبوعية والاستثنائية، ثم يُرسَل
**دعوةُ حجزٍ بالبريد** إلى زبونٍ أو عميلٍ محتمل، فيحجز بنفسه من الرابط؛ **الحجز متاحٌ حتى 30 يوماً
مقدماً**؛ ويحصل الطرفان على تأكيد، مع إعادة جدولةٍ وإلغاء، ومواعيدَ قادمة في القائمة، ومكالمةٍ
مرئية 30 دقيقة (بيتا)، وربطِ تقويمات. والوحدة متاحة في خطة Essentials فأعلى
([Schedule appointments](https://quickbooks.intuit.com/learn-support/en-us/help-article/manage-appointments/schedule-appointments-quickbooks-online/L7pZhPDEP_US_en_US)).

**لماذا يهمّنا هذا؟** لأنه يبيّن أنّ «الموعد» **يُبنى** فقط حين يوجد للزبون **هويةٌ يتصرّف بها**
(حسابُ بوابة أو رابطُ بريدٍ شخصيّ). البرامجُ التي تعرف أنّ الزبون قد لا يدخل شيئاً (TaxDome ·
Canopy · Karbon) أحالت الحجز إلى مُجدوِلٍ خارجيّ ولم تُنفق عليه. وهذا **تأييدٌ خارجيّ** لقرارنا
المحسوم: الزبون لا يسجّل دخولاً.

### 3-د. كيف تُعرَض الثلاثة معاً

| ما يُعرَض | عند من | الشكل |
|---|---|---|
| استحقاقاتُ العمل لكل موظّف | TaxDome · Karbon · Jetpack · Canopy (مهام) | تقويم يوم/أسبوع/شهر بفلاتر محفوظة، أو قائمة «ما عليّ» |
| مواعيدُ اللقاء مع الزبائن | QuickBooks (أصليّ) · TaxDome/Canopy/Karbon (رابط خارجيّ) | صفحةُ حجزٍ للزبون + قائمةُ «المواعيد القادمة» للمكتب |
| حالةُ المستندات والاستلام | TaxDome (حقل **Intake date**) · Financial Cents (عمودُ عدّاد `N/M`) | حقلٌ في بطاقة العمل + عمودٌ في الجدول |

### 3-هـ. توصيتنا للنسخة الأولى

**نعم، المواعيد عندنا تشمل الاثنين، لكن بكيانٍ واحدٍ صغير لا أكثر.**
(هذا القسم توصيةٌ لنا، مبنية على ما سبق لا منقولةً عنه.)

1. **موعدُ العمل يبقى كما حُسم في البحث السابق**: الاستحقاق مشتقٌّ من الفترة بقاعدة، ويظهر في
   «لوحة اليوم» وفي تقويمٍ شهريّ/أسبوعيّ. ولا نضيف شيئاً هنا.
2. **نضيف كيان «موعد» (لقاء/زيارة) داخليّاً فقط**، يُنشئه الموظّف ولا يراه الزبون ولا يحجز منه:
   الزبون · الموظّف المسؤول · التاريخ والوقت · المدة · النوع (زيارةُ مكتب · مكالمة · توقيع ·
   استلامُ مستندات · جلسةُ إعداد) · الحالة (مجدول · حضر · لم يحضر · أُلغي) · ملاحظات · ربطٌ اختياريّ
   بنسخة عملٍ أو بطلب مستندات.
3. **بلا حجزٍ ذاتيّ وبلا تقويمٍ عامّ في v1.** السببُ من §3-ب و§3-ج: الحجز الذاتيّ يحتاج للزبون
   هويةً (بوابة أو بريد)؛ ومكاتبُنا ترتّب الزيارة في واتساب أصلاً. أمّا «رابطُ موعدٍ يُرسَل بالواتساب»
   (نمط QuickBooks) فمؤجَّلٌ صراحةً لمرحلةٍ تالية لأنه يفتح بابَ نسخٍ من المنصة إلينا.
4. **العرضُ ثلاثة مواضع لا خمسة:** شبكةُ تقويمٍ شهرية للمكتب (مع فلتر الموظّف) · «اليوم» في لوحة
   الصباح (مواعيدُ اليوم + استحقاقاتُ اليوم في قائمةٍ واحدة مرتّبة بالوقت) · تبويبُ «المواعيد» في
   ملفّ الزبون. هذا مطابقٌ لنمط §3-د ومقتصرٌ على ما يحتاجه مكتبُ ثلاثة موظّفين.
5. **حقلان مستعاران من TaxDome يستحقّان الدخول** لأنّهما يفسّران الشكوى اليومية: **تاريخ الاستلام**
   و**الاستحقاق الداخليّ** — ويُستعمل الثاني في حساب «متى ننبّه الموظّف» لا الزبون (§4-ج).
6. **لا تذكيرَ آليّ للمواعيد في v1.** لا برنامجَ قرأته يوثّق سلسلةَ تذكيرٍ للمواعيد بقيمٍ افتراضية؛
   وإضافةُ نوع رابعٍ من الرسائل يضاعف ما يُحرّره المكتب بلا دليلِ طلب. وإذا احتاج المكتب تذكيراً
   فيكتبه بكبسةٍ من نموذج (ب) بعد تعديله.

---

## 4) إيقاع التذكير

### 4-أ. ما ينشره المنتجون فعلاً (جدول الأرقام)

| البرنامج | ما يُذكَّر به | التذكير الأول | التكرار | العدّة/السقف | ما يوقفه | المصدر |
|---|---|---|---|---|---|---|
| **TaxDome** | أيّ بندٍ ينتظر إجراءً: منظّم، طلب مستندات، عرض، فاتورة، توقيع، موافقة، محادثة | **3 أيام** بعد الإرسال (افتراضيّ) | كل **3 أيام** (افتراضيّ) | **1** افتراضياً، ويُرفَع بلا حدٍّ منشور | إنجازُ الإجراء · نفادُ العدّة · أرشفةُ العمل المرتبط · إقفالُ المنظّم · انتهاءُ العرض · إعادةُ تفعيل الدردشة · إطفاءُ المفتاح | [reference](https://help.taxdome.com/article/reminders-reference) |
| **Canopy** | طلبُ مستنداتٍ من الزبون | ليس افتراضاً بل شرطاً: «عندما يقترب من الاستحقاق بـ**N يوماً**» يُدخِله المكتب | تكراراتٌ متعدّدة بقوالب بريدٍ مختلفة | غير منشور | تغيّرُ حالة الطلب | [automations](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests) |
| **Ignition** | فاتورةٌ لم تُدفع | افتراضٌ على **مستوى الحساب** لكل الفواتير | إعداداتٌ مستقلّة لكل فاتورة تتجاوز الافتراض | غير منشور («اختر متى وكم») | السداد · وهو **نظامٌ منفصل** عن «تذكير الدفع القادم» | [invoice reminders](https://support.ignitionapp.com/en/articles/12151860-invoice-reminders) |
| **QuickBooks Online** | فاتورة | **N يوماً قبل** الاستحقاق أو بعده (يختاره المكتب) | حتى **3 تذكيرات** في السلسلة | **3**، والنافذة كلها ±**90 يوماً** من الاستحقاق | السداد · إطفاءُ المفتاح · انتهاءُ السلسلة | [invoice reminders](https://quickbooks.intuit.com/learn-support/en-us/help-article/invoicing/send-invoice-reminders-automatically-manually/L84cQjpxo_US_en_US) |
| **Financial Cents** | طلبٌ داخل المشروع | غير منشور في التوثيق | «تتابع الزبون **حتى يُتمّ** قائمة الطلبات» | غير منشور | الإتمام | `…\acct-practice-mgmt\docs\research\accounting-office-practice-management.md` §3.3 (البحث السابق؛ لم أُعد قراءته) |
| **Jetpack Workflow** | **لا شيء للزبون** | — | — | — | إشعاراته داخليةٌ للفريق وحدها (Overdue · Project · Task · Mention) وتفضيلاتُها شخصية | [notifications](https://support.jetpackworkflow.com/en/articles/9014992-notifications-overview) |
| **Karbon · Xero** | — | — | — | — | **لم يُقرأ** (§6) | — |

**أربع قراءاتٍ لهذا الجدول:**

1. **الرقمُ المنشور الوحيد للفاصل الزمنيّ الافتراضيّ هو 3 أيام، وللعدّة الافتراضية 1** — وكلاهما
   عند TaxDome. والباقي يُوثّق **أنّ الإيقاع قابلٌ للضبط** ولا ينشر افتراضيّه: QuickBooks ينشر
   **سقفاً** (3 رسائل) و**نافذةً** (±90 يوماً) لا قيمةً افتراضية، وCanopy وIgnition لا ينشران
   رقماً أصلاً.
2. **محورُ التذكير عند المهنة هو «إجراءٌ لم يُنجَز»، لا «تاريخٌ يقترب».** TaxDome يصف التذكيرات
   حرفياً بأنها «رسائلُ متابعةٍ لزبائن **لم يُكملوا** إجراءً على بندٍ معلّق»
   ([Reminders explained](https://help.taxdome.com/article/119-automatic-reminders)). والاستثناءُ
   الوحيد الذي قرأته هو شرطُ Canopy القائم على التاريخ — **وهو خيارٌ لا افتراض**.
3. **الافتراضُ يُوضع في القالب/الحساب ثم يُورَّث، لا يُعاد إدخاله لكل بند.** TaxDome يضع المفتاح
   في القوالب (chat/invoice/proposal) وفي أتمتات المسار، **وتغييرُ الأتمتة لا يمسّ ما أُطلِق
   سابقاً** ([reference](https://help.taxdome.com/article/reminders-reference))؛ وIgnition يضع
   الافتراض على الحساب ويُجيز استثناءً لكل فاتورة.
4. **التوقّفُ ليس حدثاً واحداً بل جدولاً بحسب النوع.** عند TaxDome: السداد الكامل يوقف تذكير
   الفاتورة و**السداد الجزئيّ لا يوقفه**؛ وإقفالُ المنظّم يوقف؛ وأرشفةُ العمل توقف كلَّ الأنواع
   ([reference](https://help.taxdome.com/article/reminders-reference)).

### 4-ب. التصعيد

- **إلى الزبون فقط افتراضياً.** نصُّ TaxDome: «التذكيرات تذهب **إلى الزبائن وحدهم**»؛ وليس لكل
  كائنٍ مفتاحُ تصعيدٍ إلى موظّف
  ([Reminders explained](https://help.taxdome.com/article/119-automatic-reminders)).
- **إلى الفريق كإجراءٍ يُضاف:** Canopy يجعل «إرسال إشعارٍ لعضو فريق» **إجراءً** في الأتمتة يمكن
  ربطُه بشرطٍ (حالةٌ، أو تغيّرُ حالةِ مهمةٍ سابقة) — أي تصعيدٌ ممكنٌ لكنه **يُبنى** لا يُشحَن
  ([automations](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests)).
- **إلى المكتب كتفضيلِ إشعار:** TaxDome يُنادي بتشغيل تفضيل إشعار **Invoices** ليصل بريدٌ وإشعارٌ
  في `Inbox+` حين تصير الفاتورة متأخّرة
  ([Manage overdue invoices](https://help.taxdome.com/article/429-how-to-manage-overdue-invoices))؛
  وJetpack يترك لكل عضوٍ ضبطَ تفضيلاته، ومنها تبويب **Overdue**
  ([notifications](https://support.jetpackworkflow.com/en/articles/9014992-notifications-overview)).

**الحكم:** لا سلّمَ تصعيدٍ افتراضيّ جاهز في أيِّ برنامجٍ قرأته؛ المُشحَنُ هو الإشعار، والمبنيُّ
يدوياً هو التصعيد.

### 4-ج. الإيقاعُ الافتراضيّ الذي نقترحه (توصيةٌ لنا)

الأساس: نبدأ من **3 أيام** كفاصل، لأنها القيمةُ الافتراضية الموثَّقة الوحيدة في المهنة
([TaxDome](https://help.taxdome.com/article/reminders-reference))، ونرفع **العدّة من 1 إلى 3**
لأنّ زبون TaxDome يستطيع أن يُنجز بنفسه في البوابة بمجرّد وصول الرسالة، أمّا زبوننا فلا قناةَ له
غير الموظّف؛ فيُعطى ثلاث محاولاتٍ قبل أن يتحوّل الأمر إلى عملٍ داخليّ.

| الحالة | أول رسالة | الرسائل التالية | السقف | التصعيد الداخليّ | ما يوقفها |
|---|---|---|---|---|---|
| **(أ) مستندات ناقصة لفترة** | يوم **1** من الشهر التالي لنهاية الفترة | يوم **4** ثم **7** ثم **10** | **3** رسائل | يوم **11**: إشعارُ الموظّف المسؤول · يوم **13**: إشعارُ مالك المكتب إن لم يصل شيء والاستحقاق يوم 15 | وصولُ كل المستندات · إغلاقُ الفترة · إيقافٌ يدويّ |
| **(ب) استحقاقٌ قريب** | **T-7** | **T-2** | **2** | **T-2** مع الرسالة: إشعارُ الموظّف المسؤول | التقديمُ الفعليّ · إقرارُ المكتب بأنه لا ينطبق · إيقافٌ يدويّ |
| **(ج) المستحقّ (أتعاب + ضريبة)** | **T-3** من استحقاق الأتعاب | **+3** ثم **+7** | **3** | بعد **14** يوماً من التأخير: إشعارُ المالك | السدادُ الكامل · السدادُ الجزئيّ يُبقيها (على قاعدة TaxDome) · إيقافٌ يدويّ |

**ضوابط تُشحَن مع الإيقاع (كلها توصية):** لا رسالةَ يوم الجمعة أو السبت (عطلةُ السوقين)، ولا في
عيدٍ رسميّ، والنافذةُ الافتراضية **الأحد–الخميس 9:00–19:00**؛ ولا تُحتسب الرسالةُ في العدّة إن
أرسلها الموظّف يدوياً خارج الجدول؛ وتأجيلٌ بكبسة واحدة إن قال الزبون «ببعتلك بكرة» — يُؤجَّل
3 أيام بلا استهلاك عدّة. وموعدُ (ب) يُحسب من **آخر موعدٍ صالح** لا من التاريخ القانونيّ: في إسرائيل
يمنح التقديمُ الإلكترونيّ حتى **19** لتقرير מע"מ و**23** للتقرير المفصّل
(`…\acct-tax-il\docs\research\accounting-office-tax-il.md` §3.3)، وفي فلسطين **لا نصَّ يُمدّد** موعدَ
يوم 15 (`…\acct-tax-ps\docs\research\accounting-office-tax-ps.md` §3)؛ فالقاعدة تعمل هناك ولا تعمل
هنا، وفي الحالتين التذكير بتاريخ 15 يحرق هامشاً ممنوحاً.

> **تنبيه على (ب) و(ج):** لم أجد في منتجٍ قرأته **تذكيراً افتراضياً قائماً على اقتراب التاريخ**، ولا
> **تذكيراً يجمع الأتعاب والضريبة**. فالأرقامُ أعلاه تصميمٌ لنا، مستندٌ إلى الفواصل الموثَّقة
> وإلى مواعيد النظامين في بحثَي الضرائب، لا إلى نصٍّ من منتج.

---

## 5) الرسائل الافتراضية

**قبل النصوص — القواعد التي تُقيّد الصياغة** (منقولٌ من بحث الواتساب السابق، وهو قرأ صفحات Meta):

- في v1 (`wa.me`) **لا قوالبَ ولا تصنيف**؛ النصُّ حرّ. لكن يجب أن يكون النصُّ **صالحاً لأن يصير
  قالباً `utility`** حين ننتقل إلى Cloud API، فتُكتب الصياغة منذ اليوم على هذا الأساس.
- `utility` يشترط أمرين معاً: **غير ترويجيّ**، و**خاصٌّ بالمستخدم أو بطلبه** أو جوهريٌّ له؛ وأمثلتُه
  الموثَّقة تشمل تذكيرَ دفعةٍ بمبلغٍ وتاريخ، وتحديثاتِ الحساب، و«لتُكمل إعداد X تحتاج رفع Y»
  ([template categorization](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization)).
- `marketing` يشمل **المحتوى المختلط** (تحديثُ طلبٍ مع عرض)؛ فالفرقُ في السعر بينهما في سوقنا
  **نحو ثمانية أضعاف** (0.0077$ مقابل 0.0604$ إلى فلسطين) — أي أنّ سطرَ خصمٍ أو تقسيطٍ في رسالة
  أتعاب يقلب تصنيفها وكلفتها ([pricing](https://developers.facebook.com/docs/whatsapp/pricing)،
  `…\acct-whatsapp\docs\research\accounting-office-whatsapp.md` §٢-٠).
- **قواعد المراجعة التي تمسّ الشكل:** لا يبدأ النصُّ بمعاملٍ ولا ينتهي به، أقواسٌ متوازنة، معاملاتٌ
  متسلسلة، ولا رموز خاصة (`#` `$` `%`) داخل المعامل، وإرفاقُ قيمةٍ نموذجية لكل معامل
  ([template review](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review)،
  [templates overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview)).
  ولذلك كلُّ نصٍّ أدناه يبدأ باسم الزبون وينتهي باسم المكتب.
- **لغةٌ لكل قالب:** العربية `ar` والعبرية `he` قالبان منفصلان لا واحد
  ([supported languages](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/supported-languages)).
- `wa.me` لا ينشر سقفاً لطول `?text=` (سقفُ 140 حرفاً يخصّ روابط QR/القصيرة)
  ([QR & short links](https://developers.facebook.com/documentation/business-messaging/whatsapp/qr-codes)) —
  ومع ذلك نُبقي النصَّ قصيراً: أربعة أسطر كحدٍّ أقصى.
- **إيموجي واحد كحدّ أقصى**، ويُفضَّل صفراً في (ب) و(ج): لا يضيف شيئاً ويصعّب المراجعة.
- المعاملاتُ المطلوبة: `{client_name}` · `{period}` · `{due_date}` · `{amount}` · `{office_name}` ·
  `{missing_list}`، ويُضاف إليها في (ج) `{amount_fees}` و`{amount_tax}` و`{amount_total}` لمن يريد
  التفصيل، وفي (ب) `{deadline_name}` (اسمُ الالتزام: تقرير قيمة مضافة، اقتطاع رواتب…).

### (أ) مستنداتٌ ناقصة لفترة

**عربي**
```
أهلاً {client_name}،
لما نجهّز {period} ناقصنا منك: {missing_list}.
لو بتقدر تبعتلنا إياهم قبل {due_date} بنكون خلّصنا بأسرع وقت،
وإذا في شي مش واضح خبرنا.
شكراً — {office_name}
```

**עברית**
```
שלום {client_name},
כדי שנוכל להכין את {period} חסרים לנו: {missing_list}.
נשמח לקבל אותם עד {due_date},
ואם משהו לא ברור — דברו איתנו.
תודה, {office_name}
```

### (ب) استحقاقٌ قريب

**عربي**
```
أهلاً {client_name}،
بذكّرك إنّ موعد {deadline_name} عن {period} هو {due_date}،
ولسا بدنا نستلم منك {missing_list} قبل ما نقدّم.
إذا في عائق خبرنا من اليوم لنلحق.
{office_name}
```

**עברית**
```
שלום {client_name},
תזכורת: המועד ל{deadline_name} של {period} הוא {due_date},
ועדיין חסרים לנו {missing_list} לפני ההגשה.
אם יש משהו תקוע — דברו איתנו היום כדי שנספיק.
{office_name}
```

### (ج) ما عليهم: أتعاب المكتب + الضريبة

**عربي — النسخة القصيرة (المشحونة افتراضياً)**
```
أهلاً {client_name}،
على حساب {period} عندك {amount} مستحقة،
آخر موعد للسداد {due_date}.
بنستلم كاش أو تحويل أو شيك، وإذا في استفسار خبرنا.
شكراً — {office_name}
```

**עברית — النسخة القصيرة**
```
שלום {client_name},
יתרת החובה שלך עבור {period} היא {amount},
המועד האחרון לתשלום: {due_date}.
אפשר לשלם במזומן, בהעברה או בצ'ק. לכל שאלה — אנחנו כאן.
תודה, {office_name}
```

**عربي — نسخةٌ مفصّلة (اختيارية، تُستعمل حين تُحصَّل الضريبة عبر المكتب)**
```
أهلاً {client_name}،
حساب {period} عندك:
أتعاب المكتب {amount_fees}
الضريبة المستحقة {amount_tax}
المجموع {amount_total}
الاستحقاق {due_date}. شكراً — {office_name}
```

**עברית — نسخةٌ مفصّلة**
```
שלום {client_name},
סיכום {period}:
שכר טרחה {amount_fees}
מס לתשלום {amount_tax}
סה"כ {amount_total}
מועד תשלום: {due_date}. תודה, {office_name}
```

**ثلاثُ ملاحظاتٍ على (ج) تخصّ التصنيف والوضوح:**

1. **لا خصمَ ولا تقسيطَ في النصّ.** جملةُ «خصم 5% إن سدّدت هذا الشهر» تُخرج الرسالة من `utility`
   إلى `marketing` فتصير كلفتها 8 أضعاف، وهذا استنتاجٌ من دليل التصنيف لا نصُّ Meta
   ([template categorization](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization)).
2. **الضريبة والأتعاب في رسالةٍ واحدة جائزتان، لكن الأنظف فصلهما** حين يدفع الزبون ضريبته لدائرة
   الضرائب مباشرةً: تبقى رسالةُ الأتعاب معاملةً واحدةً صافية، ورسالةُ الضريبة تنبيهَ موعد. والحسمُ
   النهائيّ للمكتب لا لنا — لذلك تبقى النسختان القصيرة والمفصّلة مشحونتَين.
3. **لا روابط**، فالمطلوب في v1 ألا يعتمد النصُّ على رابط (سقفُ الروابط القصيرة 140 حرفاً وتوثيقُ
   Meta لا ينشر سقفاً لـ`?text=`) — والرسالةُ تفهم بلا رابط
   ([QR & short links](https://developers.facebook.com/documentation/business-messaging/whatsapp/qr-codes)).

**عن النبرة (توصية):** عربيةٌ شاميّةٌ بسيطة كما في المسوّدات أعلاه — «أهلاً» لا «تحيّاتنا الطيّبة»،
و«ناقصنا منك» و«بنكون خلّصنا» بصيغة المكتب لا الفصحى، وسطرُ ختامٍ ثابت باسم المكتب. والعبريةُ
بالنبرة نفسها في القِصَر («נשמח», «דברו איתנו») بلا صيغٍ رسمية ثقيلة. ولا مصدرَ مهنيّ يضبط النبرة
في السوقين — فهي **اختيارٌ تحريريّ لنا** يُعرض على المالك مع أول مكتبٍ تجريبيّ، ويُحرَّر داخل
المنصة (قرار المالك: النظام يشحن نصاً والمكتب يعدّله). وكلُّ نصٍّ منها يمرّ **بشاشة مراجعة الموظّف
قبل الإرسال** كما حُسم في بحث الواتساب — فلا يُرسَل شيءٌ من المنصة بلا عينٍ بشرية في v1.

---

## 6) ما بقي غير مؤكَّد

1. **Karbon — لم يُقرأ نصّه.** الصفحات تردّ قشرةَ تطبيقٍ + CAPTCHA. المؤكَّدُ عناوينُ مقالاته فقط،
   ومنها ما يهمّنا هنا: `Overview of My Week` · `Use deadline dates in work` · `Filling deadlines
   overview` · `Overview of client requests` · `Calendly` (تكامل) — أي أنّ Karbon **على الأرجح**
   لا يملك مواعيد أصلية بل تكاملَ Calendly، وهذا **استدلالٌ من اسم المقال لا قراءة**. ولا نعرف
   هل لتذكيره افتراضٌ عدديّ.
2. **Xero Practice Manager — لم يُقرأ منه حرف.** `central.xero.com` يردّ CAPTCHA. رأيتُ في نتائج
   البحث **عناوينَ** مقالاتٍ فقط: `Set up and add invoice reminders` · `How invoice reminders
   work` · `Set up payment follow-ups`
   ([How invoice reminders work](https://central.xero.com/0/article/How-invoice-reminders-work) —
   محجوب). فلا نعرف أرقامه، **ولا أُثبت ولا أنفي** وجودَ مواعيد/حجزٍ أصليٍّ في XPM؛ لم أجد صفحةً
   رسمية تذكره، وغيابُ ما لم أقرأه ليس نفياً.
3. **Canopy: لا قيمة افتراضية منشورة** لـ«N يوماً قبل الاستحقاق»، ولا للعدّة. المؤكَّد أنّ الحقل
   يُدخِله المكتب ([automations](https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests)).
4. **Ignition: لا عدّةً ولا مواعيد منشورة.** صفحته تصف **مكان** الافتراض (الحساب) والاستثناء (لكل
   فاتورة) لا قيمته.
5. **TaxDome: لم يُقرأ مقدارُ حقل «Days before marked overdue»** الافتراضي — التوثيق يذكر الحقل
   وموضعه فقط ([overdue invoices](https://help.taxdome.com/article/429-how-to-manage-overdue-invoices)).
   ولم أتحقّق هل قيمةُ 3/1 تختلف بالخطة أو بالسوق.
6. **تذكيرٌ بالتاريخ: لا سابقةَ افتراضية.** لم أقرأ منتجاً يُشحن «تذكيراً N أيام قبل الاستحقاق»
   قيمةً افتراضية؛ Canopy يجعله شرطاً اختيارياً. فسلسلةُ (ب) و(ج) في §4-ج تصميمٌ لنا.
7. **Financial Cents:** فهرس مقال التذكيرات أعاد واجهةً لا نصّاً في هذه الجلسة؛ استندتُ فيه إلى
   البحث السابق (قرأه كاملاً) لا إلى قراءتي.
8. **النافذة الإلكترونية تختلف بين النظامين:** الإسرائيلي يمنح حتى 19 لتقرير المع"מ و23 للتقرير
   المفصّل، والفلسطيني لا نصَّ يُمدّد موعدَه — فقاعدةُ «التذكير من آخر موعدٍ صالح» تعمل في إسرائيل
   ولا تعمل في فلسطين. تفاصيلُ ذلك في بحثَي الضرائب لا هنا.
9. **صياغة الرسائل:** لا مصدرَ مهنيّ يضبط نبرة العربية الشامية أو العبرية في مراسلة المكاتب؛
   النصوصُ أعلاه مسوّداتٌ لنا تحتاج مراجعةَ مكتبٍ حقيقيٍّ واحدٍ من كل سوق قبل الشحن.
10. **الحدّ المنهجيّ العامّ:** عامّةُ هذه البرامج أمريكية/أسترالية، وقيمُها الافتراضية محسوبةٌ على
    زبونٍ له بوابةٌ وبريد. أرقامُها صحيحةٌ كمرجع لكنها ليست وصفة؛ والفارقُ المقصود في §4-ج مذكورٌ
    صراحةً في مكانه.

---

## 7) المصادر

**أ) TaxDome — `help.taxdome.com` (مقروءةٌ هذه الجلسة، على خلاف البحث السابق)**
- <https://help.taxdome.com/article/119-automatic-reminders> — Reminders explained (نُشِر 2026-10-21)
- <https://help.taxdome.com/article/reminders-reference> — Reminders reference (**الافتراضيان 3 و1**، جدولُ شروط التوقّف لكل كائن)
- <https://help.taxdome.com/article/785-workflow-basic-calendar-view> — Calendar view for tasks and jobs
- <https://help.taxdome.com/article/532-embed-scheduler> — Connect a scheduler to your portal (Calendly · Acuity · YouCanBookMe · Schedulista)
- <https://help.taxdome.com/article/174-creating-emailing-and-setting-reminders-for-invoices> — Send one-time invoices (+ تفاصيل تذكير الفاتورة)
- <https://help.taxdome.com/article/429-how-to-manage-overdue-invoices> — Manage overdue invoices
- <https://help.taxdome.com/article/track-intake-and-internal-deadlines> — Track document intake and internal deadlines
- <https://help.taxdome.com/sitemap.xml> — الفهرس (لا مقالَ باسم appointment فيه)

**ب) Canopy — `support.getcanopy.com`**
- <https://support.getcanopy.com/en/articles/11796290-what-automations-are-available-on-client-requests> — Client Request automations (تحديث 2026-01-16)
- <https://support.getcanopy.com/en/articles/9376016-add-a-reminder-to-tasks-subtasks> — Add a Reminder to Tasks/Subtasks (تذكيرٌ داخليّ بالبريد)
- <https://support.getcanopy.com/en/articles/9375785-faq-calendar> — FAQ: Calendar (التقويم مرآةٌ لتقويم Google/Microsoft)
- <https://support.getcanopy.com/en/articles/9375762-sync-a-calendar> — Sync a Calendar
- <https://support.getcanopy.com/en/articles/9375900-add-third-party-links-schedulers-to-the-client-portal> — Third-party links & schedulers in the client portal

**ج) منتجاتٌ أخرى**
- Ignition — <https://support.ignitionapp.com/en/articles/12151860-invoice-reminders> (افتراضٌ على مستوى الحساب + استثناءٌ لكل فاتورة؛ نظامان منفصلان للتذكير)
- Jetpack Workflow — <https://support.jetpackworkflow.com/en/articles/9014992-notifications-overview> (إشعاراتٌ داخلية للفريق وحدها)
- QuickBooks Online — <https://quickbooks.intuit.com/learn-support/en-us/help-article/manage-appointments/schedule-appointments-quickbooks-online/L7pZhPDEP_US_en_US> (مواعيدُ أصلية: توفّر، دعوةُ حجزٍ بالبريد، حتى 30 يوماً مقدماً)
- QuickBooks Online — <https://quickbooks.intuit.com/learn-support/en-us/help-article/invoicing/send-invoice-reminders-automatically-manually/L84cQjpxo_US_en_US> (حتى 3 تذكيرات، ±90 يوماً)
- Financial Cents — <https://help.financial-cents.com/en/articles/8781064-automated-client-reminders> (لم يُقرأ نصُّه هذه الجلسة؛ يُنسب إلى البحث السابق)
- Karbon — <https://help.karbonhq.com/s/sitemap-topicarticle-1.xml> (**الفهرس وحده**؛ النصوص محجوبة)

**د) Meta / WhatsApp — قواعد القوالب (منقولةٌ عن بحث الواتساب الذي قرأها)**
- <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization>
- <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review>
- <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview>
- <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/supported-languages>
- <https://developers.facebook.com/documentation/business-messaging/whatsapp/qr-codes>
- <https://developers.facebook.com/docs/whatsapp/pricing>

**هـ) الأبحاث السابقة التي يبني عليها هذا الملف (لا يعيدها)**
- `D:\Users\asus\Desktop\ktra\.agents\worktrees\research\acct-practice-mgmt\docs\research\accounting-office-practice-management.md` — الكيانات والفترة وطلب المستندات ولوحات الصباح.
- `D:\Users\asus\Desktop\ktra\.agents\worktrees\research\acct-whatsapp\docs\research\accounting-office-whatsapp.md` — قرار `wa.me` + سجلّ الإرسال، وقواعد تصنيف القوالب والتسعير.
- `D:\Users\asus\Desktop\ktra\.agents\worktrees\research\acct-tax-ps\docs\research\accounting-office-tax-ps.md` — المواعيد الفلسطينية (يوم 15، 30 يوماً، الشهر الرابع) ولا قاعدةَ عطلة.
- `D:\Users\asus\Desktop\ktra\.agents\worktrees\research\acct-tax-il\docs\research\accounting-office-tax-il.md` — المواعيد الإسرائيلية (15/16/19/23، التمديدات، يوم الراحة بحسب دين المكلَّف).

**و) محجوبٌ أو غير مقروء**
- `central.xero.com` — كلُّ الصفحات ردّت CAPTCHA؛ لم يُقرأ حرف. (عنوانٌ فقط:
  <https://central.xero.com/0/article/How-invoice-reminders-work>)
- `help.karbonhq.com` — JavaScript + CAPTCHA؛ العناوين فقط.
- `help.taxdome.com/en/` — صفحةُ «Page not found» (المسار الصحيح `/article/<id>-<slug>`).
