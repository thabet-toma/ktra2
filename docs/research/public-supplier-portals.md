# ردُّ مورّدٍ غير مسجَّل — كيف تعالجه بوابات المورّدين الناضجة؟

بحثُ القضية **#139** (ضمن الخريطة **#138**). المصادر أوّليّةٌ حصراً: توثيقُ المنتَج
الرسميّ، وأدلّةُ الإدارة الرسميّة (PDF)، ومراجعُ الـAPI الرسميّة، وشيفرةُ المصدر
الرسميّة، والنصوصُ التشريعيّة. **لا مدوّناتٍ ولا صفحاتِ تسويق.**

---

## ٠) الخلاصةُ في ثلاثة أسطر

1. **لا نظامَ من الستّة يقبل سعراً من مجهولٍ مجهولِ الهويّة.** البابُ الذي يقبل مجهولاً
   حقّاً (SAP Ariba) يقبل **تعريفاً بالنفس** لا سعراً. والبابُ الذي يقبل **سعراً** بلا
   حساب (Coupa) يربطه دائماً بـ**بريدٍ معروفٍ سلفاً** ورابطٍ فرديّ.
2. **حيثما وُجد بابٌ عامّ، نزل الردُّ في كيانٍ وسيطٍ مستقلٍّ عن سجلّ المورّد** — ويُخلَق
   المورّدُ (أو يُربَط) **بفعلٍ بشريٍّ لاحق**. هذا **قرارُ المالك ٤** حرفيّاً، ويسنده
   الآن مصدران أوّليّان مستقلّان (Ariba وCoupa).
3. **أقربُ نموذجٍ بياناتٍ لنا هو Coupa `QuoteSupplier`**: صفٌّ على *حدث التسعير نفسه*
   يحمل اسماً وبريداً وجهةَ اتّصال، وعليه يُعلَّق العرض — ومؤشّرُ المورّد الحقيقيّ
   **حقلٌ للقراءة فقط** يملؤه النظام.

---

## منهجيّة — ما تحقّقتُ منه بنفسي وما فوّضته

| المصدر | الحالة |
|---|---|
| SAP Ariba — دليل `SlpSetup.pdf` 2608 (٨٦٤ صفحة) | نُزِّل واستُخرج نصُّه وقُرِئت صفحاتُه المعنيّة **مباشرةً**؛ **ووسّعه وكيلٌ فرعيّ** ببلوغ صفحات البوّابة عبر خدمة المحتوى نفسها (`/http.svc/pagecontent`) — الأقسامُ المفوَّضةُ مُعلَّمة |
| Coupa — `compass.coupa.com` (توثيق المورّدين + مرجع Core API) | قُرِئ مباشرةً، **وتوسّعَ فيه وكيلٌ فرعيّ** بلغ ملفّات DITA الخام |
| Zoho Procurement / Spend | قُرِئ مباشرةً + توسيعٌ مفوَّض |
| Odoo (توثيق 18.0/19.0 + مصدر `odoo/odoo`) | قُرِئ مباشرةً + **قراءةٌ مفوَّضةٌ عميقةٌ للمصدر** |
| ERPNext/Frappe (مصدر رسميّ) | قُرِئ مباشرةً + قراءةٌ مفوَّضةٌ صحّحت قراءتي الأولى |
| Dynamics 365 · WTO GPA · EU ESPD · US FAR/SAM | **قراءةٌ مفوَّضةٌ لوكلاء فرعيّين**، بروابطَ رسميّةٍ مُثبَتة، **لم أُعِد التحقّق منها بنفسي** |

> **ملاحظةٌ تقنيّة:** صفحاتُ `help.sap.com` و`docs.coupa.com` وبعضُ صفحات EUR-Lex
> تُبنى بجافاسكربت فتعود فارغةً للجالب الآليّ. اعتُمِدت **ملفّاتُ PDF الرسميّة**
> و**نُسَخُ DITA الخام** و**المرايا اللغويّة** بدلاً منها — وكلُّها مصادرُ رسميّةٌ لا
> بدائلُ ثانوية. وحيث تعذّر ذلك، **دُوِّن التعذّرُ صراحةً**.

---

## ١) SAP Ariba — «External Supplier Request»: البابُ المجهولُ الوحيد

**المصدر:** _Supplier Management Setup and Administration Guide_ 2608 (2026‑08)، PDF رسميّ
<https://help.sap.com/doc/3d4a256ce5774f729b3c240187c0624a/2608/en-US/SlpSetup.pdf>
· الصفحةُ المقابلة على البوّابة
<https://help.sap.com/docs/strategic-sourcing/managing-suppliers-and-supplier-lifecycles/external-supplier-requests>

### أين ينزل الردّ؟ — **مشروعُ طلبٍ منفصل، والمورّدُ يُخلَق عند الاعتماد وحده**

> "External supplier request projects allow suppliers who want to do business with your
> organization to introduce themselves. **When an external request is approved, the
> supplier is created in your site.**" — ص ١٦

> "External supplier requests are sometimes called self-registration, but **the form
> submitted is a request, the first step** in working with a supplier. Supplier
> registration, the next step, is a **separate type of project**." — ص ١٦

> "The system user **`aribasystem`** is the explicit owner of external supplier request
> projects as well as the requester. **If the request is approved, the supplier is
> created in the database.**" — ص ٢٣٢

**والغريبُ يدخل بصفة «ضيف» لا مستخدم:**

> "The external supplier request URL allows suppliers to access the external supplier
> request form in your site **as guest users for this strictly limited purpose**." — ص ٢٣٤

### منعُ العبث — **reCAPTCHA منصوصةً بالحرف**

> "**SM-2861 — External supplier request (supplier self-registration).** … **Suppliers
> accessing this custom URL must complete a ReCAPTCHA verification before the external
> supplier request opens to prevent malicious automated attempts to repeatedly access
> the external supplier request ("bot spamming")**." — ص ٦٢٦

والميزةُ **معطَّلةٌ افتراضاً** (تُفعَّل بطلبٍ من دعم SAP) — البابُ العامّ عندهم قرارٌ
لا افتراض.

### مطابقةُ الاسم الحرّ — **يحلّونها لحظةَ الاعتماد، اقتراحاً لا حسماً**

> "**Approvers see a list of existing suppliers in the database that match information in
> the external request** so that they can deny duplicate requests and approve only
> requests for genuinely new suppliers." — ص ١٦

هذا جوابٌ مباشرٌ لسؤالٍ تركته الخريطة **#138** مفتوحاً تحت «Not yet specified».

### تفاصيلُ أخرى موثَّقة

- **رابطٌ واحدٌ للموقع كلّه لا رابطٌ لكل مستجيب:** «an external supplier request URL
  **that's specific to your site** … by publishing it on a corporate website» (ص ١٦).
  فتعدُّدُ الردود على الرابط الواحد **هو التصميم**، والتمييزُ يقع على محتوى الاستمارة
  وعلى المعتمِد.
- **عمليّةٌ لمرّةٍ واحدة:** "The external supplier request process is a **one-time
  process**. Approvers can edit submitted external requests while approval is still in
  progress." (ص ٢٣٢) — لا تعديلَ من المرسِل بعد الإرسال.
- **ما يُطلَب أساسيٌّ عمداً:** «the supplier's name and address, the name of a contact»
  (ص ٢٣٢)، و**أسئلةُ الحساب البنكيّ والضريبة ممنوعةٌ صراحةً**: "Questions of answer type
  **Bank Account and Tax aren't supported** in the external supplier request" (ص ٢٣٤).
- **البابُ لا يقبل سعراً.** لم أجد في الدليل أيَّ مسارٍ يسمح لغيرِ المسجَّل بتقديم سعر.

### ⭐ والحقلُ الإلزاميّ على الاستمارة المجهولة: **بريدُ جهةِ الاتّصال**

الحقولُ المُلزَمة لأنّها ضروريّةٌ لخلق المورّد عند الاعتماد هي: **اسمُ المورّد**،
و**اسمُ جهةِ الاتّصال الأوّلُ والأخير**، و**عنوانُ بريدِ جهةِ الاتّصال** (ص ٢٣٤ وما
بعدها). أي أنّ **البابَ المجهولَ الوحيدَ في الصناعة لا يقبل اسماً حرّاً بلا بريد.**
هذا سندٌ مباشرٌ للتوصية (ب) في §١١.

### كشفُ التكرار عندهم **خوارزميّةٌ مسجَّلةٌ بعتبةٍ رقميّة**

كلُّ طلبِ مورّدٍ مُرسَل يمرّ بفحصِ تكرارٍ على **D-U-N-S**، و**الرقم الضريبيّ**
(للطلبات الداخليّة)، و**تطابقِ الاسم الصارم** (مع بترِ لواحق الشركات)، و**تطابقِ
الاسم الجزئيّ مع العنوان**، وأسئلةٍ مخصَّصةٍ اختياريّة — بدرجةٍ من **٠ إلى ١٠٠**،
و«**70% and above considered strong matches**».
— <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/3eaa1681e3a14fdc8df0da334c7da43c.html>
_(قراءةٌ مفوَّضة عبر خدمة محتوى البوّابة نفسها)_

**والهويّةُ تُسوَّى لحظةَ الاعتماد لا لحظةَ الإرسال** — وهذا هو الضابطُ الحامل، لا
الـCAPTCHA.

### الطلبُ المرفوض **لا يظهر في بحث المورّدين أصلاً**

يُعثَر عليه ببحثِ مشاريعَ على نوع المحتوى `Supplier Request Project` مرشَّحاً بحقل
**`Is Self Registration`** — أي أنّ منطقةَ الانتظار **معزولةٌ فعلاً** عن فضاء المورّدين.
— <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/5ace53634d904b748acc052132c33adf.html>

### مساراتُ الحالات — مفرداتٌ جاهزةٌ للاقتباس

- **حالةُ الطلب:** `Not Started → Initiated → Draft → Submitted → In Approval →
  Approved | Rejected | Pending Resubmission | Canceled`
  — <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/bda1cc090df14b56aac5921353ad7c19.html>
- **حالةُ التسجيل (مسارٌ ثانٍ منفصل):** `Not Invited → Invite in Progress → Invited →
  In Registration → Pending Approval → Registered | Registration Denied`
  — <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/94b7e2ca1a224520a77198cf273824e5.html>

**⚠️ نتيجةٌ سلبيّةٌ مهمّة:** «**prospective supplier**» و«**potential supplier**»
**ليستا حالتين في دورة حياة SLP إطلاقاً**. الاستعمالُ الموثَّق الوحيد لـ«prospective
supplier» هو **ميزةُ تعليمٍ في واجهة Discovery** لا حالةَ نموذجِ بيانات. فسؤالُ
التذكرة عن هذا المصطلح **مبنيٌّ على فرضٍ خاطئ** — المصطلحُ من عالم Dynamics لا Ariba.
_(قراءةٌ مفوَّضة)_

### البابان الآخران عند Ariba (وكلاهما **يشترط حساباً**)

- **Ariba Discovery:** «postings **enable suppliers who are not part of the buyer's
  supplier network** to express their interest». لكنّ الردَّ يعيش **في منتَجٍ منفصل**،
  والمشتري يسحبه صراحةً بـ**Import to Sourcing** مختاراً «Import as an **approved**
  seller» أو «as an **unapproved** seller» — و«**Unapproved suppliers cannot be invited
  to events until they are approved**». والحسابُ شرطٌ: Discovery جزءٌ من بوّابة
  الشركاء («walk up registrations»).
- **صفحةُ الوصول العامّ (القطاع العامّ):** «can be accessed by **all suppliers,
  including those who are not the customers of SAP Ariba**» — لكنّ زرَّ **Participate**
  يعيدك إلى Discovery: «**Register yourself to participate in the event**… After
  registering… you are **eligible to start bidding**».
_(قراءةٌ مفوَّضة؛ الروابطُ في الملحق)_

### ماذا يرى المشاركُ في حدثِ Ariba — **محسومٌ الآن**

قواعدُ **Event Market Feedback Rules**:
— <https://help.sap.com/docs/ARIBA_SOURCING/14957b649fe54ff6bf721c7e579d098d/7c733fd271ea1014b82f8f7dfa652ef6.html>

- **`Can participants see ranks?`** بأربع قيم: `No` / `Their own rank when leading` /
  `Their own rank` / `All participants' ranks`.
- **وقاعدةٌ قاطعة:** «**RFI and RFP participants are NEVER shown information about
  responses from other participants, including ranks, regardless of the value for this
  rule**». أي أنّ التغذيةَ التنافسيّة **مقصورةٌ على المزادات** — وطلبُ عروض الأسعار
  عندنا نظيرُ RFQ/RFI، **فلا ترتيبَ ولا مقارنةَ للمستجيب.**
- `Show lead bid to all participants` · `Show bid graph` · `Show ceiling/reserve price`
  · `Hide countdown clock` · **ومزلاجُ إخفاء العدد**: `Hide the number of bidders by
  using the same participant alias` — والتحذيرُ الصريح أنّ الأسماءَ المرقَّمة
  («Company 9») **تُسرِّب عددَ المشاركين**.
- **هويّةُ المشتري:** تُخفى **في Discovery فقط** («hide your company name» → company
  alias). أمّا **داخل حدث Sourcing نفسه فإخفاءُ المشتري غيرُ موثَّقٍ إطلاقاً** — لا
  يُفترَض. وصفحةُ القطاع العامّ **تُظهِر الجهةَ المتعاقدة عمداً**.

### وبوّاباتُ الوصول قبل التسعير

`Application.SM.MinimumRegistrationStatusForEventAccess` (0 Not Invited … 3 Registered):
«Suppliers who are below the minimum status **can be invited to events, but can't access
them**». وفوقها **Access Gate** (يمنع **الرؤية**) و**Participation Gate** (يمنع
**الإرسال**)، و`HideContentUntilAgreementAccepted` الذي يحجب محتوى الحدث كلَّه حتى
قبولِ اتّفاقيّة المزايدة. _(قراءةٌ مفوَّضة)_

### ⚠️ **انتهاءُ صلاحيّة رابطِ الطلب العامّ غيرُ موثَّقٍ عند Ariba**

لا نصَّ على انتهاءٍ ولا على استعمالٍ لمرّةٍ واحدة — والرابطُ **مصمَّمٌ للنشر الدائم**
على موقع الشركة. الانتهاءُ الوحيدُ الموثَّقُ في هذا الجوار هو **OTP تسجيلِ شبكة SAP:
صالحٌ ٣٠ دقيقة**، مع انتظارِ ٣٠ دقيقةً قبل طلبِ رمزٍ جديد، **وفحصِ حساباتٍ مكرّرة**،
**ونطاقاتِ بريدٍ قابلةٍ للحظر**. _(قراءةٌ مفوَّضة)_

---

## ٢) Coupa — أقربُ نموذجِ بياناتٍ إلينا

**المصدر:** توثيقُ Coupa الرسميّ + **مرجعُ Core API** وملفّاتُ DITA الخام.

### النموذج — **`QuoteSupplier` صفٌّ على الحدث، لا سجلُّ مورّد**

> "For the Coupa back end, a sourcing event is known as a **quote request**."
> — <https://compass.coupa.com/en-us/products/product-documentation/integration-technical-documentation/the-coupa-core-api/resources/transactional-resources/sourcing-api-(quote_requests)>

ثلاثةُ موارد عليا: `/api/quote_requests` (الأحداث) · `/api/quote_responses` (الردود) ·
`/api/quote_suppliers` (المستجيبون).

حقولُ `QuoteSupplier`: `name` · `email` · `contact-name` · `display-name` ("Name that we
display to buyer") · `public-profile-link` · **`supplier` ("Supplier which is linked to
quote supplier")**.
— <https://compass.coupa.com/en-us/products/product-documentation/integration-technical-documentation/the-coupa-core-api/resources/transactional-resources/sourcing-api-(quote_requests)/quote-suppliers-api>
· المصدرُ الخام بجدول In/Out:
<https://compass.coupa.com/_dita_/en-us/documentation/plat/integ/coupa_core_api/topics/quote_suppliers_api.dita>

**وهنا بيتُ القصيد:** في جدول DITA، الحقولُ `name` و`email` و`contact-name` **In = Yes**
(تُكتَب من الخارج)، بينما `supplier` **In = No, Out = Yes** — **للقراءة فقط، يملؤه
النظام**. أي أنّ المستجيبَ كيانٌ قائمٌ بذاته يحمل هويّةً مُدَّعاة، ورابطُه بالمورّد
الحقيقيّ **مشتقٌّ لا مُدخَل**.

**والعرضُ يُعلَّق على هذا الصفّ لا على المورّد:** `QuoteResponse` يحمل `quote-supplier`
و`state` و`submitted-at` و`awarded` و`lines`؛ و`GET /api/quote_requests/:id/quote_responses`
= "Get the **latest submitted response per supplier**".
— <https://compass.coupa.com/en-us/products/product-documentation/integration-technical-documentation/the-coupa-core-api/resources/transactional-resources/sourcing-api-(quote_requests)/quote-responses-api>

**ولا مسارَ ترقيةٍ آليٍّ موثَّقاً** من `QuoteSupplier` إلى `Supplier`. صيرورةُ المستجيب
مورّداً فعلاً فعلٌ **لاحقٌ يبدؤه المشتري**: `/api/supplier_invites` — و**يشترط أن يكون
سجلُّ المورّد موجوداً أصلاً** — فتنتقل حالةُ CSP من **Invited** إلى **Linked**.
— <https://compass.coupa.com/en-us/products/product-documentation/suppliers/supplier-integration-resources/api-endpoint-for-supplier-csp-invites>

### الحسابُ ليس شرطاً، لكنّ الهويّةَ شرط

> "**As a supplier you do not need to have a Coupa account or access to the CSP to take
> part in sourcing events.** When the event is launched, an invitation mail is
> automatically sent to the participants. The email contains **a unique link to the
> event**."
> — <https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/view-sourcing-events>

**ثلاثةُ أوضاعٍ يختار بينها المشتري** (المرآةُ الألمانيّة للصفحة تحتفظ بالنصّ الذي
حُذف من الإنجليزيّة):

1. الرابطُ يدخلك الحدثَ مباشرةً — بلا حساب.
2. الرابطُ يطلب **OTP** — بلا حساب. «Das OTP verfällt nach **15 Minuten** oder **sobald
   Sie es verwenden**» (**ينتهي بعد ١٥ دقيقة أو فورَ استعماله**).
3. **حسابٌ مطلوب** — أوّلُ دعوةٍ تحمل اسمَ مستخدمٍ ورابطَ تعيينِ كلمةِ مرور.
   — <https://compass.coupa.com/de-de/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/access-a-sourcing-event>

الاختيارُ من إعداد **«Sourcing OTP Settings»** عند المشتري (شاشتُه خلف جدار SSO —
**غيرُ قابلةٍ للتحقّق**). وفي منتَج **CSO** المنفصل، الـOTP **صالحٌ سبعةَ أيّام** ويُفرَض
عند أوّل دخولٍ تغييرُ كلمة المرور وقبولُ سياسة الخصوصيّة.
— <https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/core-supplier-onboarding/coupa-sourcing-optimization-for-suppliers>

### الأحداثُ العامّة — عموميّةٌ في الاكتشاف لا في الإرسال

أنواعُ الرؤية: **Public** («open for all suppliers») · **Private** · **Hidden**.
— <https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/sourcing-events-types-for-suppliers>

لكنّ الحدثَ العامّ يُتصفَّح **من داخل CSP بعد تسجيل الدخول**، والمشاركةُ تمرّ ببوّابة
موافقة: **Request Participation → Request Sent → Request Approved**.
(نفس صفحة View Sourcing Events)

### عدّةُ ردود — **علَمٌ صريحٌ على الحدث**

`allow-multiple-response` — **"Allow multiple responses from one supplier"** على
`/api/quote_requests`.
— <https://compass.coupa.com/_dita_/en-us/documentation/plat/integ/coupa_core_api/topics/quote_requests_api.dita>

**وكيف يميّزون شخصين على رابطٍ واحدٍ بلا حساب؟ لا يفعلون** — مرساةُ الهويّة هي صفُّ
`QuoteSupplier` (بريد + جهةُ اتّصال)، فيلتقي الإرسالان في سجلّ المستجيب نفسه.
(**استنتاجٌ من دلالة الحقول**، لا نصَّ صريحاً عند Coupa.)

آليّةُ التصحيح موثَّقة: «Ask the buyer to **disqualify** your incorrect bid… The buyer can
disqualify **only your most recent bid**»، مع تحذيرٍ إذا كان العرضُ الجديد أفضلَ بـ٥٠٪.
— <https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/sourcing-faq>

### ماذا يرى المستجيب؟

> "Each event will display information about **the buyer company**, commodity, start and
> end dates, and type of event."
> — <https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/participate-in-a-sourcing-event>

ويرى: الجدولَ الزمنيّ · «Event Information & Bidding Rules» يقبلها **قبولاً لا رجعةَ
فيه** · استبياناتٍ · «Items and Lots» حيث يسعّر · مرفقاتٍ (يتحكّم بها المشتري عبر
`allow_supplier_to_send_attachments`) · مركزَ رسائل · ثمّ **Submit Response to Buyer**.

**وعن رؤية المنافسين — الجوابُ دقيقٌ ومهمّ:**

> "You will see feedback on your pricing expressed as **a rank or as a difference to best
> bid, depending on the buyer's choice**." (في المزادات الإنجليزيّة)

أي **إشارةٌ تنافسيّةٌ بلا هويّة**. والإخفاءُ الكاملُ إعدادٌ على الحدث:
`sealed-bids` · `automatic-bid-unsealing` · `sealing-type` · `sealing-stage`.
(ملفّ DITA أعلاه). **هل تُكشَف أسماءُ المشاركين الآخرين؟ لا نصَّ يثبته ولا ينفيه —
غيرُ محسوم.**

**فجواتٌ صريحةٌ عند Coupa:** لا سقفَ ردودٍ رقميّاً موثَّقاً · لا CAPTCHA على صفحة
التسعير نفسها (الموثَّقةُ الوحيدةُ في نافذة MFA بالبريد البديل) · انتهاءُ صلاحيّة رابطِ
**الحدث** (تمييزاً عن رابط تسجيل CSP الذي **ينتهي بعد ٣٠ يوماً**) غيرُ موثَّق.

---

## ٣) Zoho — لا بابَ عامّاً إطلاقاً

**RFQ غيرُ موجودةٍ أصلاً في Zoho Books ولا Zoho Inventory** — هي في منتَجٍ منفصل
(Zoho Procurement / Spend / ERP، بمحتوى مساعدةٍ واحد).

- **الترشيحُ للـRFQ من قائمة مورّديك فقط:** صفحةُ النشر توثّق `+ Add Vendor` (اختيارٌ
  **من المورّدين القائمين**) ثمّ `Invite vendors automatically upon publishing` أو
  `Invite Vendors` يدويّاً. **لا خانةَ بريدٍ حرّة ولا رابطَ عامّ.**
  — <https://www.zoho.com/us/procurement/help/request-for-quotes/publish-request-for-quotes/>
- **التعريفُ بمورّدٍ جديدٍ دعوةٌ من الإدارة لا تسجيلٌ ذاتيّ:** «You only need to invite
  them using their email address. The vendor can fill in their details by signing up to
  the vendor portal»، والحالات: **Invited → Pending Review → Approval Pending → Active**.
  — <https://www.zoho.com/us/procurement/help/vendors/vendor-onboarding/>
- **المورّدُ يردّ بعد تسجيل الدخول:** «Log in to your portal».
  — <https://www.zoho.com/us/procurement/help/vendor-portal/request-for-quotes/>
- **بوّابةُ Books/Inventory دعوةٌ على سجلٍّ قائم:** «select the vendor for whom you want
  to enable the portal».
  — <https://www.zoho.com/us/inventory/help/vendor-portal/> · <https://www.zoho.com/us/books/help/vendor-portal/>
  _(قراءةٌ مفوَّضة)_ والـAPI يؤكّده: صلاحيّةُ البوّابة **فرعٌ من جهةِ اتّصال** —
  `POST /contacts/{contact_id}/portal/enable` — **ولا نقطةَ نهايةٍ تُنشئ مستخدمَ بوّابةٍ
  بلا جهةِ اتّصال**. — <https://www.zoho.com/books/api/v3/contacts/>
- **عدّةُ عروضٍ بإعدادٍ من المشتري:** «send multiple bids until the bidding period ends…
  **your latest bid will be considered as the final bid**».
  — <https://www.zoho.com/us/spend/help/admin/vendor-portal/request-for-quotes/>
- **ما يراه:** البنودُ المطلوبة، شروطٌ يقبلها، واستمارةٌ فيها `Bid Quantity, Item Price
  per Quantity, Shipping Charges, Additional Charges, Delivery Date, Notes` مع رفعِ
  مستندات. **رؤيةُ عروضِ الآخرين غيرُ موثَّقةٍ نفياً ولا إثباتاً.**

**ولم أجد في Zoho أيَّ توثيقٍ لانتهاءِ صلاحيّة رابطِ الدعوة ولا CAPTCHA ولا سقفِ ردود.**
لا يُفترَض وجودُها.

---

## ٤) Odoo — الفجوةُ الأوضح، وأخطرُ درسٍ في الهويّة

- **لا مسارَ كتابةِ سعرٍ عامّاً إطلاقاً.** مسارات بوّابة الشراء في 18.0 خمسةٌ فقط،
  و**مسارُ الكتابة العامّ الوحيد** `‎/my/purchase/<id>/update` **يكتب `date_planned`
  وحده** — لا سعرَ ولا كمّيّةَ ولا مرفق.
  — <https://github.com/odoo/odoo/blob/18.0/addons/purchase/controllers/portal.py>
  والوثيقةُ الرسميّة تؤكّده: الآليّةُ **بريدٌ** («Send by Email… Purchase: Request for
  Quotation template») والسعرُ يُدخِله **المشتري**.
  — <https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/rfq.html>
  وحدةُ `purchase_requisition` (اتّفاقيّاتُ الشراء) **بلا مجلّد `controllers` أصلاً** —
  صفرُ انكشافٍ على البوّابة.
- **المورّدُ إلزاميٌّ على مستوى ORM:** `partner_id = fields.Many2one('res.partner',
  string='Vendor', **required=True**, …)`.
  — <https://github.com/odoo/odoo/blob/18.0/addons/purchase/models/purchase_order.py>
- **ومعالجُ المشاركة لا يشارك مجهولاً:** `partner_ids = fields.Many2many('res.partner',
  string="Recipients", **required=True**)`.
  — <https://github.com/odoo/odoo/blob/18.0/addons/portal/wizard/portal_share.py>
- **التوكن:** `access_token = fields.Char('Security Token', copy=False)` على **السجلّ**،
  يُولَّد `str(uuid.uuid4())`، ويُقارَن بـ`consteq`. **ولا انتهاءَ صلاحيّةٍ ولا إبطالَ ولا
  تدوير** — إطلاقاً.
  — <https://github.com/odoo/odoo/blob/18.0/addons/portal/models/portal_mixin.py>
  · <https://github.com/odoo/odoo/blob/18.0/addons/portal/controllers/portal.py>
- **⚠️ الدرسُ الأهمّ — Odoo لا يقدر أن يميّز الغرباءَ على رابطٍ واحد:**

  ```python
  def get_portal_partner(thread, _hash, pid, token):
      if validate_thread_with_hash_pid(thread, _hash, pid):
          return thread.env["res.partner"].sudo().browse(int(pid))
      if validate_thread_with_token(thread, token):
          if partner := thread._mail_get_partners()[thread.id][:1]:
              return partner
      return thread.env["res.partner"]
  ```
  — <https://github.com/odoo/odoo/blob/18.0/addons/portal/utils.py>

  **بالتوكن وحده، كلُّ غريبٍ يُنسَب إلى شريك السجلّ نفسِه** (أي مورّد أمر الشراء). ثلاثةُ
  أشخاصٍ على رابطٍ واحدٍ = ثلاثُ رسائلَ موقّعةٌ باسمٍ واحد. والأسوأ أنّ
  `purchase.order._notify_get_recipients_groups` **يستبدل** رابطَ الهويّة الموقّع
  (`pid`+`hash`) برابطِ التوكن المجرَّد — فرسالةُ الـRFQ **لا تحمل هويّةً موقّعةً أصلاً**.
- **جوابُ Odoo لِـ«غريبٌ يُرسِل بيانات» في مكانٍ آخر:** استماراتُ الموقع العامّة، تنزل
  **`crm.lead`** (كيانُ انتظارٍ مستقلّ)، ومحميّةٌ بـ**Turnstile أو reCAPTCHA v3** —
  و**البوّابةُ ليست منها**: «All pages using the **Form**, Newsletter Block, or Newsletter
  Popup snippets are protected».
  — <https://www.odoo.com/documentation/18.0/applications/websites/website/configuration/spam_protection.html>
- **ماذا يرى الغريب؟** عنوانَ الشركة المشترية، ورقمَ المستند وتاريخه، والإجماليّ،
  وجدولَ البنود (والأسعارُ **محجوبةٌ في حالة `sent`** في 19.0)، **ومسؤولَ الشراء واسمَه
  وهاتفه**، وسجلَّ المراسلات. **ولا يرى بدائلَ ولا موردين آخرين** — قالبُ البوّابة لا
  يذكر `alternative_po_ids` ولا `requisition_id` إطلاقاً.
  — <https://github.com/odoo/odoo/blob/18.0/addons/purchase/views/portal_templates.xml>
  · <https://github.com/odoo/odoo/blob/19.0/addons/purchase/views/portal_templates.xml>

---

## ٥) ERPNext — أقربُ معماريّةً إلينا، وأشدُّ إغلاقاً

**تصحيحٌ لقراءةٍ أولى:** ERPNext **لا يستعمل توكنَ مستندٍ حاملاً** إطلاقاً. المسارُ:
`Supplier` قائمٌ سلفاً → `Contact` → **`User` من نوع `Website User`** → **مفتاحُ تعيين
كلمة مرور** → جلسةٌ مصادَقة → فحصُ `Portal User`.

- المورّدُ إلزاميّ: `validate_party_frozen_disabled(self.company, "Supplier", d.supplier)`،
  والبريدُ إلزاميّ: «Row {0}: For Supplier {1}, **Email Address is Required** to send an
  email».
  — <https://github.com/frappe/erpnext/blob/develop/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py>
- **المفتاحُ مهشَّرٌ ومنتهي الصلاحيّة ومحدودُ المعدّل** (خلافاً لتوكن Odoo الخام الأبديّ):
  `hashed_key = sha256_hash(key)` · `reset_password_link_expiry_duration` ·
  `@rate_limit(limit=get_password_reset_limit, seconds=60*60)`.
  — <https://github.com/frappe/frappe/blob/develop/frappe/core/doctype/user/user.py>
- **الإرسالُ محميٌّ بعضويّةٍ لا بتوكن:**
  `if frappe.session.user not in frappe.get_all("Portal User", {"parent": supplier}, pluck="user"): frappe.throw(_("Not Permitted"), frappe.PermissionError)`.
  — <https://github.com/frappe/erpnext/blob/develop/erpnext/buying/doctype/request_for_quotation/mapper.py>
- **رؤيةُ المنافسين ممنوعةٌ على مستوى الاستعلام:** `.where(… & (sq.supplier == supplier))`،
  وقائمةُ المدعوّين `doc.suppliers` **لا تُعرَض على البوّابة**.
  — <https://github.com/frappe/erpnext/blob/develop/erpnext/templates/pages/rfq.html>
- **تكرارُ الإرسال غيرُ ممنوعٍ في الخادم** — الواجهةُ تُخفي الزرَّ فقط.
- **مفاتيحُ Frappe العامّة للاستمارات** جديرةٌ بالنظر كقائمةِ ضوابط: `login_required` ·
  `allow_multiple` ("Allow multiple responses") · `allow_edit` · `anonymous` ·
  `max_attachment_size`. **ولا حقلَ CAPTCHA في النواة إطلاقاً.**
  — <https://github.com/frappe/frappe/blob/develop/frappe/website/doctype/web_form/web_form.json>

---

## ٦) Dynamics 365 _(قراءةٌ مفوَّضة — لم أُعِد التحقّق)_

يؤكّد نمطَ جدولِ الانتظار من مصدرٍ خامس:

- **SCM:** غيرُ المسجَّل **يُسجِّل ولا يُسعِّر**. استمارةُ التسجيل المجهولة **صفحةٌ
  يستضيفها العميلُ بنفسه** («a customer-hosted website that allows anonymous access»)،
  تُستورَد إلى **`Prospective vendor registration requests`** بحالات `New, User
  requested, User invited, Registration in progress, Vendor request created, Approved,
  Rejected`. — <https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/vendor-onboarding>
  والردُّ على RFQ يلزمه حسابُ Entra B2B مربوطٌ بمورّد — **ومع منعٍ صريحٍ لبُرُدِ
  المستهلكين** (`@gmail.com` وأخواتها).
  — <https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/vendor-collaboration-work-external-vendors>
- **Supplier Engagement (معاينة):** «anonymous registration page» ينزل
  **`Registration requests`** (`New / In review / Approved / Rejected`)، و**عند الاعتماد
  يُشغَّل كشفُ التكرار** بالاسم والموقع والبريد **ويمنعُ الاعتماد** عند التطابق.
  — <https://learn.microsoft.com/en-us/dynamics365/supply-chain/supplier-engagement/supplier-engagement-review-registrations>
- **حجبُ الحقول عن المورّد إعدادٌ صريح:** «RFQ fields included in vendor RFQ reply
  forms… Set the slider to *No* for each field where you want to prevent vendors from
  seeing data» — ومرفقاتٌ **داخليّةٌ مقابل خارجيّة**.
  — <https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/request-quotations>
- **Business Central:** لا سطحَ خارجيّ إطلاقاً، لكنّه يحلّ «المورّدُ غيرُ موجودٍ بعد»
  **داخليّاً**: عرضُ شراءٍ على `Contact` غيرِ مربوطةٍ بمورّد، **والمورّدُ يُخلَق آليّاً عند
  التحويل** عبر `vendor template` — نفسُ نمطِ «المورّد المبدئيّ يتجسّد عند التحويل»
  الموجود عندنا أصلاً (القضية #68).
  — <https://learn.microsoft.com/en-us/dynamics365/business-central/purchasing-how-request-quotes>

---

## ٧) المناقصاتُ الحكوميّة — النمطُ الأصليّ لـ«غريبٌ يقدّم عرضاً» _(قراءةٌ مفوَّضة)_

هنا **يجب** أن يقدر المجهولُ على العرض، فكيف حُلَّت الهويّة؟ **بطبقتين.**

- **WTO GPA:** `"open tendering"` = «a procurement method whereby **all interested
  suppliers may submit a tender**»، و«supplier» = «a person or group of persons that
  **provides or could provide** goods or services». والمادّة XV: «shall receive, open and
  treat all tenders under procedures that guarantee… **the confidentiality of tenders**».
  — <https://www.wto.org/english/docs_e/legal_e/rev-gpr-94_01_e.htm>
- **الاتّحاد الأوروبيّ — إقرارٌ ذاتيٌّ للجميع، وإثباتٌ من الفائز وحده:**
  > «The **European single procurement document (ESPD)** is a **self-declaration** form…
  > **Only the winner of the tender then needs to provide the actual documents.**»
  — <https://single-market-economy.ec.europa.eu/single-market/public-procurement/digital-procurement/european-single-procurement-document-and-ecertis_en>
  · الأداةُ التشريعيّة: لائحةُ التنفيذ (EU) 2016/7
  <https://eur-lex.europa.eu/eli/reg_impl/2016/7/oj/eng>
  · التوجيه 2014/24/EU (تعريفُ `economic operator` في م.٢(١)(١٠)، وسرّيّةُ العروض في م.٢١(١))
  <https://eur-lex.europa.eu/eli/dir/2014/24/2024-01-01/eng>
  ⚠️ **تعذّر** استخراجُ نصّ م.٥٩(٤)(٥) حرفيّاً (EUR-Lex يعيد قشرةَ جافاسكربت) — قاعدةُ
  «إثباتُ الفائز وحده» مقتبسةٌ من صفحة المفوّضيّة واللائحة 2016/7 **لا** من نصّ المادّة.
  · ومع ذلك، نظامُ التقديم الأوروبيّ نفسُه **يطلب هويّةً خفيفةً مسبقاً**: «Get an **EU
  Login** account» و«Get a **PIC** number»، و«The proposals will remain **sealed and
  closed** until after the call deadline».
  — <https://webgate.ec.europa.eu/funding-tenders-opportunities/spaces/OM/pages/1867927/Submit+a+proposal+%E2%80%94+Electronic+Submission+System>
- **الولايات المتّحدة — العكسُ تماماً:** التسجيلُ **شرطٌ سابقٌ للعرض نفسه**:
  «An Offeror is **required to be registered in SAM when submitting an offer or
  quotation** and at time of award» — <https://www.acquisition.gov/far/52.204-7>
  · <https://www.acquisition.gov/far/4.1102> · و«Registration can take **up to 10
  business days** to become active» — <https://sam.gov/content/entity-registration>

**الدرس:** النظامُ الوحيدُ في الدنيا الذي **يجب** أن يقبل الغريب، يقبله بـ**إقرارٍ
ذاتيٍّ صريحٍ يُعاقَب على كذبه**، ويؤجّل التحقّق إلى **لحظة الترسية**. وهذا بالضبط ما
تفعله بنيةُ «جدولِ انتظارٍ + اعتماد».

---

## ٨) المصطلحاتُ الرسميّة — لتسمية الشاشة العربيّة

| المصطلح | المنتَج/المصدر | ماذا يعني بالضبط |
|---|---|---|
| **External Supplier Request** | SAP Ariba | استمارةُ الغريب — **«طلب»** لا «تسجيل» |
| **Supplier Self-Registration** | SAP Ariba | الاسمُ الدارج؛ والدليلُ يصحّحه: «the form submitted is a **request**» |
| **Guest user** | SAP Ariba | صفةُ الغريب لحظةَ التعبئة |
| **Private / Public supplier** | SAP Ariba | «خاصّ» = موجودٌ عندك **بلا حسابِ شبكة**؛ «عامّ» = مربوطٌ بحسابٍ وANID |
| **Approved / Unapproved seller** | SAP Ariba Discovery | حالتا الاستيراد؛ و«غيرُ المعتمَد **لا يُدعى إلى حدث**» |
| **Access Gate / Participation Gate** | SAP Ariba | بوّابةُ **الرؤية** مقابل بوّابةِ **الإرسال** |
| ~~Prospective supplier~~ | SAP Ariba | **ليست حالةً في دورة حياة SLP** — نتيجةٌ سلبيّةٌ موثَّقة |
| **Quote Supplier** | Coupa (API) | **صفُّ المستجيب على الحدث** — اسمٌ وبريدٌ وجهةُ اتّصال، ومؤشّرُ المورّد **للقراءة فقط** |
| **Quote Request / Quote Response** | Coupa (API) | الحدثُ / الردّ |
| **Public · Private · Hidden event** | Coupa | مستوياتُ رؤية الحدث |
| **Prospective vendor** · **Registration request** | Dynamics | المرشَّح · صفُّ جدول الانتظار |
| **Invited Vendor** | Zoho | مورّدٌ دُعِيَ ولم يكمل |
| **Public user** (`base.public_user`) | Odoo | كلمةُ Odoo للغريب — مقابل `portal user` |
| **Economic operator** | توجيه EU 2014/24 م.٢(١)(١٠) | المصطلحُ القانونيّ للمتقدّم أيّاً كان |
| **Offeror / quoter** | US FAR | مقدّمُ العرض |
| **Self-declaration / preliminary evidence** | EU ESPD | إقرارٌ ذاتيٌّ يقوم مقام الإثبات مؤقّتاً |
| **OTP identity authentication** | Coupa | توكيدُ الهويّة ببريدٍ بلا حساب |

**التوصيةُ اللفظيّة:** كلمةُ **«طلب» (request)** مقصودةٌ في كل توثيقٍ رسميّ لتقول:
**هذا ادّعاءٌ ينتظر بتّاً، لا سجلّ.** فاسمُ القسم في الخريطة #138 («عروض عامة») سليمٌ
للمستخدم، لكنّ **حالةَ النموذج** ينبغي أن تحمل معنى `request / pending review` لا
`quotation`. والتسميةُ الأدقُّ للصفّ نفسه: **«عرضٌ من مورّدٍ غيرِ مسجَّل»** أو
**«طلبُ تعريفٍ بمورّد»**.

---

## ٩) أجوبةُ الأسئلة الخمسة، مختصرةً

| # | السؤال | الجواب الموثَّق |
|---|---|---|
| ١ | **أين ينزل الردّ؟** | **كيانٌ وسيطٌ مستقلٌّ عن سجلّ المورّد، في كل نظامٍ فيه بابٌ غيرُ مسجَّل.** Coupa: **`QuoteSupplier`** صفٌّ على الحدث ومؤشّرُ المورّد فيه **للقراءة فقط** · Ariba: **مشروعُ طلبٍ** مملوكٌ لمستخدمِ نظام، والمورّدُ يُخلَق **عند الاعتماد** · Dynamics: **`Prospective vendor registration request`** · Odoo (للاستمارات العامّة): `crm.lead`. أمّا Zoho وOdoo (شراء) وERPNext فلا بابَ لهم أصلاً: **المورّدُ يجب أن يسبق**. **ولا نظامَ واحدٌ يسمح للغريب بأن يكتب نفسَه في جدول المورّدين** — والاستثناءُ الوحيد (`unapproved seller` عند Ariba Discovery) **فعلٌ يبدؤه المشتري** باستيرادٍ صريح، لا فعلُ الغريب. |
| ٢ | **المصطلح؟** | `external supplier request` · `supplier self-registration` · `quote supplier` · `prospective vendor` · `registration request` · `economic operator` (قانونيّاً) · وللتسعير `sourcing event` / `bid` / `quote response`. |
| ٣ | **منعُ العبث؟** | **reCAPTCHA** منصوصةً عند Ariba (و«bot spamming» بالحرف)، وTurnstile/reCAPTCHA v3 عند Odoo للاستمارات العامّة (والتوكنُ عند Google **ينتهي بعد دقيقتين**، بعتبةٍ موصىً بها ٠٫٥ — <https://developers.google.com/recaptcha/docs/v3>) · **OTP بالبريد ينتهي بـ١٥ دقيقة أو بالاستعمال** عند Coupa · **مفتاحٌ مهشَّرٌ منتهي الصلاحيّة محدودُ المعدّل** عند Frappe · **الاعتمادُ البشريُّ الإلزاميّ** في الكلّ · **والميزةُ معطَّلةٌ افتراضاً** عند Ariba. **ولم أجد سقفَ ردودٍ رقميّاً موثَّقاً في أيٍّ منها.** |
| ٤ | **عدّةُ ردود؟** | **رابطُ Ariba العامّ واحدٌ للموقع كلّه** ويستقبل بلا حدّ، والتمييزُ يقع على المعتمِد الذي **يُعرَض عليه مرشَّحو التكرار**. Coupa: **رابطٌ فرديٌّ لكل مدعوّ** + علَمُ `allow-multiple-response`، **ولا يميّز شخصين على رابطٍ واحد** (المرساةُ صفُّ `QuoteSupplier`). Zoho: يسمح بإعداد («الأخيرُ هو النهائيّ»). Ariba **يمنع** التكرار (`one-time process`). ERPNext: **غيرُ ممنوعٍ في الخادم** (إخفاءُ زرٍّ فقط). |
| ٥ | **ماذا يرى الغريب؟** | **اسمُ الشركة الطالبة ظاهرٌ دائماً** (Coupa ينصّ: «information about **the buyer company**»؛ Odoo يعرض عنوانها **ومسؤولَ الشراء وهاتفه**؛ وإخفاءُ المشتري موثَّقٌ **في Ariba Discovery وحده** لا داخل حدثِ التسعير). **البنودُ والكمّيّاتُ نعم**، وما زاد **محجوبٌ بإعداد** (Dynamics: مزلاجٌ لكل حقل؛ Coupa: `sealed-bids`؛ Ariba: مصفوفةُ `Response Required` × `Visible to Participants`). **وعروضُ الآخرين لا تُرى**؛ وأقصى ما يُعطى إشارةٌ تنافسيّةٌ **بلا هويّة** («rank» أو «difference to best bid») — **وهي مقصورةٌ على المزادات**: Ariba ينصّ أنّ «**RFI and RFP participants are NEVER shown information about responses from other participants, including ranks**». وعند Ariba **البابُ المجهولُ لا يعرض مستنداً أصلاً** — استمارةُ تعريفٍ فقط، **وأسئلةُ البنك والضريبة ممنوعةٌ فيها**. |

---

## ١٠) ما لم أستطع حسمه (فجواتٌ صريحة)

1. **هل تُكشَف أسماءُ المشاركين الآخرين في حدثٍ عامّ عند Coupa؟** إعداداتُ الرؤية عند
   المشتري خلف جدار Okta. **غيرُ محسوم.**
2. **سقفُ ردودٍ رقميٌّ أو تحديدُ معدّلٍ لكل IP على صفحة التسعير** — **لم أجده موثَّقاً في
   أيٍّ من الستّة**، ولا حتى عند Ariba فوق الـCAPTCHA. الضوابطُ الموثَّقة كلُّها
   CAPTCHA أو OTP أو كشفُ تكرارٍ أو اعتمادٌ بشريّ.
3. **انتهاءُ صلاحيّة الروابط العامّة** — **غيرُ موثَّقٍ عند Ariba** (رابطُ الطلب العامّ
   مصمَّمٌ للنشر الدائم)، **ولا عند Zoho** (رابطُ الدعوة)، **ولا لرابطِ حدثِ Coupa**
   (بخلاف رابط تسجيل CSP الذي ينتهي بـ٣٠ يوماً). **لا تُفترَض.**
4. **مسارُ ترقيةِ `QuoteSupplier` إلى `Supplier` عند الترسية في Coupa** — غيرُ موثَّق
   إطلاقاً؛ الموثَّقُ فقط أنّ `/api/supplier_invites` **يشترط سجلَّ مورّدٍ قائماً**.
5. **رؤيةُ مورّدِ Zoho لعروض غيره** — غيرُ موثَّقةٍ نفياً ولا إثباتاً.
6. **نصُّ م.٥٩(٤)(٥) من التوجيه الأوروبيّ حرفيّاً** — تعذّر استخراجُه من EUR-Lex.

---

## ١١) التوصيةُ لـ K.T.R.A

### أ) قرارُ المالك ٤ صحيح — وله الآن سندان أوّليّان مستقلّان

«ردُّ المجهول ينزل جدولَ انتظارٍ منفصلاً — لا يلمس `Partner` ولا `SupplierQuotation`»:

- **Ariba:** «the form submitted is a **request**… **when an external request is
  approved, the supplier is created in your site**».
- **Coupa:** العرضُ يُعلَّق على **`QuoteSupplier`** لا على `Supplier`، ومؤشّرُ المورّد
  **`In = No`** — أي **مشتقٌّ لا مُدخَل**.

**ولا نظامَ واحدٌ من الستّة** يسمح للغريب بأن يكتب نفسَه في جدول المورّدين ولو بحالة
«غير معتمَد». بل يذهب Ariba أبعد: **الطلبُ المرفوض لا يظهر في بحث المورّدين إطلاقاً**،
ويُعثَر عليه ببحثِ مشاريعَ مرشَّحاً بحقل `Is Self Registration`. والاستثناءُ الوحيد
(`unapproved seller`) **فعلُ استيرادٍ يبدؤه المشتري**، لا فعلُ الغريب.

**فلا تُعِد فتحَ القرار ٤، ولا تُغرِ نفسك بحقل `status` على `Partner`** — لأنّ كلَّ
استعلامٍ في المنصّة يفلتر على `Partner` سيضطرّ عندئذٍ أن يتذكّر استثناءَ «غير المعتمَد»،
وأوّلُ استعلامٍ ينساه يصير تسريباً أو رقماً كاذباً في تقرير.

### ب) التوصيةُ الأقوى — **البريدُ إلزاميٌّ بجانب الاسم الحرّ**

> **اجعل البريدَ حقلاً إلزاميّاً على صفحة الرابط العامّ، واجعل صفَّ جدول الانتظار يحمل
> «بريداً مُدَّعى» اليوم و«بريداً مُثبَتاً» غداً (`email_verified_at` فارغٌ الآن).**

الحجّةُ من المصادر، لا من الذوق:

1. **كلُّ نظامٍ يقبل ردّاً من غيرِ صاحبِ حسابٍ يرسو على بريد.** مرساةُ Coupa هي
   `QuoteSupplier.email` وفوقها OTP اختياريّ. **وحتى البابُ المجهولُ عند Ariba —
   الذي لا يقبل سعراً أصلاً — يفرض «contact email address» حقلاً إلزاميّاً** لأنّه
   ضروريٌّ لخلق المورّد عند الاعتماد. **لا سابقةَ واحدةً لاسمٍ حرٍّ بلا بريد.**
2. **Odoo يُرينا الثمنَ حين يسقط البريد:** بالتوكن وحده، **كلُّ غريبٍ يُنسَب إلى شريكٍ
   واحد**. اسمٌ حرٌّ بلا بريدٍ يجعل كلَّ صفٍّ **مجهولَ المصدر نهائيّاً**: لا مطابقةَ
   تكرارٍ ممكنة، ولا طريقَ للسؤال، ولا معنى لِـ«اعتماد».
3. **والترقيةُ لاحقاً بلا هجرةٍ ثانية:** إن احتجنا تشديداً، أضفنا **OTP على نمط Coupa
   (١٥ دقيقة أو الاستعمال)** فوق نفس العمود.

### ج) ما نملكه أصلاً — وما ينقص

| الضابط | حالتُنا |
|---|---|
| انتهاءُ صلاحيّةٍ إلزاميّ | **موجود** — `DocumentShare.expires_at` بلا قيمةٍ فارغة. **أقوى من Odoo** (لا انتهاءَ فيه إطلاقاً) و**من Zoho** (غيرُ موثَّق). |
| إبطالٌ فوريّ | **موجود** — `revoked_at` + `revoke` (`docshare/views.py`) |
| تحديدُ معدّل | **موجود** — `throttle_scope = "doc_share_public"` بمعدّل `60/min` (`core/settings.py`) |
| توقيعُ IP | **موجود** — `decided_ip` يُكتب في كل إرسال |
| حجبُ ما لا يخصّ المورّد | **موجود وقويّ** — قائمةُ سماحٍ لبنود `purchase_rfq` بلا `unit_price`، و`estimated_price` **لا يُحمَّل من القاعدة أصلاً**؛ ومصفوفةُ المقارنة **بلا `doc_type`** بقرارٍ محروسٍ باختبار. **هذا يطابق أفضلَ ما رأيت** (Dynamics «internal vs external attachments»، ERPNext الذي يفلتر في SQL). |
| **CAPTCHA** | **ناقص** — الضابطُ الوحيدُ الذي تنصّ عليه Ariba **بالحرف** لبابٍ عامّ. التحديدُ بالمعدّل يحمي **الخادم** من الطوفان، **ولا يحمي جدولَ الانتظار** من عشرين صفّاً كاذباً بخطّ يد. |
| **بريدٌ على الصفّ** | **ناقص** — انظر (ب) |

### د) مطابقةُ الاسم الحرّ — النمطُ محسومٌ الآن: **اقتراحٌ لا حسم**

سؤالُ الخريطة المفتوح («أحمد للتجارة» مقابل «احمد للتجاره») له جوابان متعارضان من
مصدرين أوّليّين:

- **Ariba:** درجةُ تطابقٍ **من ٠ إلى ١٠٠** على تطابقِ الاسم الصارم (**مع بترِ لواحق
  الشركات**) وتطابقِ الاسم الجزئيّ **مع العنوان** والرقمِ الضريبيّ وD-U-N-S، وعتبةُ
  «**٧٠٪ فما فوق تطابقٌ قويّ**» — **تُعرَض على المعتمِد ليرفض المكرّر**. أي **اقتراحٌ
  مُرتَّبٌ بدرجة، لا حسم**.
- **Dynamics Supplier Engagement:** كشفُ تكرارٍ بالاسم/الموقع/البريد **يمنعُ الاعتماد**
  — **حسمٌ صارم**.

**اختر نمطَ Ariba.** النمطُ الصارم يعطّل حالةً مشروعةً — فرعان لنفس المالك باسمين
متقاربين — ويكلّف مالكَ النظام مكالمةً ليفهم لماذا رُفض الاعتماد. اعرض مرشّحين مرتَّبين
بدرجةٍ لحظةَ الاعتماد، مع خيارين: «اربط بمورّدٍ قائم» أو «أنشئ جديداً».

**وثلاثةُ إشاراتِ مطابقةٍ جاهزةٍ عندنا بلا عملٍ إضافيّ:** الاسمُ المطبَّع (بعد بترِ
«شركة/مؤسّسة/للتجارة» ونظائرها، وتوحيدِ الهمزة والتاء المربوطة — وهو جوهرُ حالة
«أحمد للتجارة / احمد للتجاره»)، و**البريدُ** (إن أُخِذ بالتوصية (ب))، و**الرقمُ
الضريبيّ** إن كُتِب. أمّا D-U-N-S فلا محلَّ له هنا.

### هـ) ملاحظةٌ بنيويّةٌ على `PurchaseRFQRecipient`

الخريطةُ #138 تسجّل أنّ `PurchaseRFQRecipient.supplier` **إلزاميٌّ (`PROTECT`)** وعليه
فرادة `(rfq, supplier)` — «فالرابط المجهول يصطدم بالبنية اليوم». **نموذجُ Coupa يقول
إنّ هذا القيدَ نفسَه هو موضعُ الخطأ**: عندهم المستجيبُ صفٌّ قائمٌ بذاته على الحدث،
ومؤشّرُ المورّد **مشتقٌّ اختياريّ**. فسواءٌ أُنشئ جدولٌ ثالثٌ منفصل (نمطُ Ariba) أم
أُرخِيَ `supplier` على صفٍّ نظير (نمطُ Coupa)، **المبدأُ واحد: الصفُّ يسبق المورّد، لا
العكس.** وقرارُ المالك ٤ (جدولٌ منفصل) هو الخيارُ الأقلُّ خطراً عندنا لأنّه **لا يمسّ
هجرةَ جدولٍ مستعمَلٍ في الإنتاج**.

---

## ملحق: كلُّ الروابط

**SAP Ariba** — <https://help.sap.com/doc/3d4a256ce5774f729b3c240187c0624a/2608/en-US/SlpSetup.pdf> (ص ١٦ · ٢٣٢ · ٢٣٣ · ٢٣٤ · ٦٢٦) ·
<https://help.sap.com/docs/strategic-sourcing/managing-suppliers-and-supplier-lifecycles/external-supplier-requests>
· _(قراءةٌ مفوَّضة عبر خدمة محتوى بوّابة SAP)_
كشفُ التكرار <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/3eaa1681e3a14fdc8df0da334c7da43c.html> ·
حالاتُ الطلب <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/bda1cc090df14b56aac5921353ad7c19.html> ·
حالاتُ التسجيل <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/94b7e2ca1a224520a77198cf273824e5.html> ·
البحثُ عن الطلبات <https://help.sap.com/docs/ARIBA_SOURCING/f081c6c38fb7466a84d746a7998bfe0e/5ace53634d904b748acc052132c33adf.html> ·
معرّفاتُ المورّد (private/public) <https://help.sap.com/docs/ARIBA_SOURCING/c6163e943b0d48e0885ac73047145cbf/eeecd03038c44a109a853471211528fc.html> ·
قواعدُ التغذية التنافسيّة <https://help.sap.com/docs/ARIBA_SOURCING/14957b649fe54ff6bf721c7e579d098d/7c733fd271ea1014b82f8f7dfa652ef6.html> ·
استيرادُ Discovery <https://help.sap.com/docs/ARIBA_SOURCING/36a99e6ce8954882ba1cbe6d42056c3e/7c23261271ea1014a6c1d0bc299ddd8b.html> ·
صفحةُ الوصول العامّ <https://help.sap.com/docs/ARIBA_SOURCING/9f02c6c905a34e45ba16b5f03d9ec261/e4d314e3dfd14288adf6bf4e900dbdaa.html> ·
المشاركةُ من الصفحة العامّة <https://help.sap.com/docs/ARIBA_SOURCING/7237950fdb6e46988f14803fee4367d6/9f4f45131bc24bc7bd0e01f0342d49fe.html> ·
حدُّ حالة التسجيل للوصول <https://help.sap.com/docs/ARIBA_SOURCING/c6163e943b0d48e0885ac73047145cbf/daa9bc7aac2c43d0aa3d4fddef480dc7.html> ·
بوّابتا الوصول والمشاركة <https://help.sap.com/docs/ARIBA_SOURCING/7237950fdb6e46988f14803fee4367d6/aa59c1d5d5af1014a85097dc030ea51f.html> ·
إخفاءُ اسم المشتري في Discovery <https://help.sap.com/docs/ARIBA_SOURCING/36a99e6ce8954882ba1cbe6d42056c3e/7c33dd7571ea1014ae6ad66811823624.html> ·
توكيدُ البريد وOTP على شبكة SAP <https://help.sap.com/docs/ARIBA_NETWORK/207b8f3d3d054df1a3c1333dcfdd2550/970ef2845a8b433cb353d0309364f80c.html>

**Coupa** —
<https://compass.coupa.com/en-us/products/product-documentation/integration-technical-documentation/the-coupa-core-api/resources/transactional-resources/sourcing-api-(quote_requests)> ·
<https://compass.coupa.com/en-us/products/product-documentation/integration-technical-documentation/the-coupa-core-api/resources/transactional-resources/sourcing-api-(quote_requests)/quote-suppliers-api> ·
<https://compass.coupa.com/_dita_/en-us/documentation/plat/integ/coupa_core_api/topics/quote_suppliers_api.dita> ·
<https://compass.coupa.com/_dita_/en-us/documentation/plat/integ/coupa_core_api/topics/quote_requests_api.dita> ·
<https://compass.coupa.com/en-us/products/product-documentation/integration-technical-documentation/the-coupa-core-api/resources/transactional-resources/sourcing-api-(quote_requests)/quote-responses-api> ·
<https://compass.coupa.com/en-us/products/product-documentation/suppliers/supplier-integration-resources/api-endpoint-for-supplier-csp-invites> ·
<https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/view-sourcing-events> ·
<https://compass.coupa.com/de-de/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/access-a-sourcing-event> ·
<https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/participate-in-a-sourcing-event> ·
<https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/sourcing-events-types-for-suppliers> ·
<https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/set-up-the-csp/sourcing/sourcing-faq> ·
<https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/core-supplier-onboarding/coupa-sourcing-optimization-for-suppliers> ·
<https://compass.coupa.com/en-us/products/product-documentation/supplier-resources/for-suppliers/coupa-supplier-portal/get-started-with-the-csp/registration-and-login/register-for-the-csp>

**Zoho** —
<https://www.zoho.com/us/procurement/help/request-for-quotes/overview/> ·
<https://www.zoho.com/us/procurement/help/request-for-quotes/publish-request-for-quotes/> ·
<https://www.zoho.com/us/procurement/help/vendor-portal/request-for-quotes/> ·
<https://www.zoho.com/us/spend/help/admin/vendor-portal/request-for-quotes/> ·
<https://www.zoho.com/us/procurement/help/vendors/vendor-onboarding/> ·
<https://www.zoho.com/us/inventory/help/vendor-portal/> · <https://www.zoho.com/us/books/help/vendor-portal/> ·
<https://www.zoho.com/books/api/v3/contacts/>

**Odoo** —
<https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/rfq.html> ·
<https://www.odoo.com/documentation/18.0/applications/general/users/portal.html> ·
<https://www.odoo.com/documentation/18.0/applications/websites/website/configuration/spam_protection.html> ·
<https://github.com/odoo/odoo/blob/18.0/addons/portal/models/portal_mixin.py> ·
<https://github.com/odoo/odoo/blob/18.0/addons/portal/controllers/portal.py> ·
<https://github.com/odoo/odoo/blob/18.0/addons/portal/utils.py> ·
<https://github.com/odoo/odoo/blob/18.0/addons/portal/wizard/portal_share.py> ·
<https://github.com/odoo/odoo/blob/18.0/addons/purchase/controllers/portal.py> ·
<https://github.com/odoo/odoo/blob/18.0/addons/purchase/models/purchase_order.py> ·
<https://github.com/odoo/odoo/blob/18.0/addons/purchase/views/portal_templates.xml> ·
<https://github.com/odoo/odoo/blob/19.0/addons/purchase/views/portal_templates.xml>

**ERPNext / Frappe** —
<https://github.com/frappe/erpnext/blob/develop/erpnext/buying/doctype/request_for_quotation/request_for_quotation.py> ·
<https://github.com/frappe/erpnext/blob/develop/erpnext/buying/doctype/request_for_quotation/mapper.py> ·
<https://github.com/frappe/erpnext/blob/develop/erpnext/templates/pages/rfq.html> ·
<https://github.com/frappe/frappe/blob/develop/frappe/core/doctype/user/user.py> ·
<https://github.com/frappe/frappe/blob/develop/frappe/rate_limiter.py> ·
<https://github.com/frappe/frappe/blob/develop/frappe/website/doctype/web_form/web_form.json> ·
<https://docs.frappe.io/erpnext/user/manual/en/request-for-quotation>

**Dynamics 365** _(قراءةٌ مفوَّضة)_ —
<https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/vendor-onboarding> ·
<https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/vendor-collaboration-work-external-vendors> ·
<https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/request-quotations> ·
<https://learn.microsoft.com/en-us/dynamics365/supply-chain/supplier-engagement/supplier-engagement-review-registrations> ·
<https://learn.microsoft.com/en-us/dynamics365/business-central/purchasing-how-request-quotes>

**مناقصاتٌ ومعايير** _(قراءةٌ مفوَّضة)_ —
<https://www.wto.org/english/docs_e/legal_e/rev-gpr-94_01_e.htm> ·
<https://single-market-economy.ec.europa.eu/single-market/public-procurement/digital-procurement/european-single-procurement-document-and-ecertis_en> ·
<https://eur-lex.europa.eu/eli/reg_impl/2016/7/oj/eng> ·
<https://eur-lex.europa.eu/eli/dir/2014/24/2024-01-01/eng> ·
<https://docs.ted.europa.eu/ESPD-EDM/3.1.0/home.html> ·
<https://www.acquisition.gov/far/52.204-7> · <https://www.acquisition.gov/far/4.1102> ·
<https://sam.gov/content/entity-registration> ·
<https://developers.google.com/recaptcha/docs/v3> ·
<https://wiki.dolibarr.org/index.php?title=Module_Ticket>
