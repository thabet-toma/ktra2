# خطة: الجرد الحديث + رابط موظف المستودع + شجرة التصنيفات + كرت المنتج + تقرير المبيعات حسب المنتج

> MODE A — PLAN · 2026-10-21 · الحالة: **بانتظار موافقة المالك** (لا تنفيذ قبلها) · أسئلة §4 محسومة
> التحقيق: أربع جلسات قراءة فقط عبر `opencode-go/deepseek-v4.1-flash`، ثم تحقّقٌ يدوي من كل
> ادّعاء حاسم في الكود (الأسطر المذكورة أدناه بالرمز لا بالرقم).

---

## 0. ما طلبه المالك (النطاق المجمَّد)

| # | الطلب | النوع |
|---|---|---|
| 1 | جرد جديد: شجرة تصنيفات كاملة بكل مستوياتها، بصناديق اختيار، أختار أي مستوى وأكثر من تصنيف، ويظهر في الجرد **فقط** ما اخترته | ميزة |
| 2 | بعد فتح الجرد: زر «تصدير رابط» لموظف المستودع (توكن، بلا تسجيل دخول، يرى صفحة الجرد فقط)، يسأل عن اسم الموظف عند التصدير، يعبّئ المعدود فيرجع للمنصة **غير مرحَّل** مع ملاحظة مَن عبّأ | ميزة |
| 3 | اختيار التصنيف داخل إنشاء/تعديل المنتج غير واضح — طريقة احترافية | UX |
| 4 | من الشجرة: كبسة يمين → تغيير تصنيف المنتج تحت أي مستوى، وتغيير التصنيفات نفسها (نقلها) | ميزة |
| 5 | فتح «المنتجات» يفتح الشجرة افتراضياً لا الجدول | تغيير افتراضي |
| 6 | تقرير المبيعات حسب المنتج: لا يميّز المنتج من البراند، والفلتر قائمة منسدلة ضخمة بلا بحث | UX/خلل |
| 7 | كبسة يمين على **منتج** في الشجرة تتصرّف كأنها على الفراغ وتعرض «إضافة منتج هنا» | **خلل** |
| 8 | الواجهة لا تسمح بتعديل البراند | **خلل** |

خارج النطاق صراحةً: مسح الباركود بالكاميرا في صفحة الموظف، السحب والإفلات في الشجرة، فلتر
التصنيف في التقارير — مقترحات في §9، لا تُبنى بلا «نعم».

---

## 1. التشخيص — ما وجدناه فعلاً (مُتحقَّق)

### 1.1 الجرد (`inventory`)
- `Stocktake` = تاريخ، مستودع، ملاحظات، `is_posted`، قيد. `StocktakeLine.counted_quantity` **غير قابل
  لـnull**. لا `created_by` ولا اسم عادّ ولا حالة غير `is_posted`.
- **البنود يرسلها العميل 100%** والخادم لا يولّد بنداً من تصنيف إطلاقاً. `StocktakeSerializer.update`
  **يحذف كل البنود ويعيد إنشاءها** (استبدال كامل).
- الواجهة (`StocktakePage.tsx`) تنزّل **الكتالوج كاملاً** (`getAllProducts`، حلقة 200/طلب) وخياراها:
  إكمال تلقائي لكل سطر، أو «إدراج كل المنتجات». التصنيفات للعرض فقط بعد وجود البنود — لا اختيار.
- خدمات الأحفاد (`category_descendant_ids` / `category_descendant_product_ids`) تقبل **تصنيفاً واحداً**.
- لا مكوّن شجرة بصناديق اختيار ثلاثية الحالة في المشروع كله (`indeterminate` = 0 نتيجة).
  الأساس الصحيح موجود: `utils/categoryTree.ts` (`buildCategoryIndex`، `descendantIds`، حارس الحلقات).

### 1.2 الروابط العامة — سابقة جاهزة، لا نخترع
- `docshare` (`DocumentShare`): توكن `token_urlsafe(32)` خام (قابل لإعادة النسخ)، `expires_at` إلزامي،
  `revoked_at`، المستأجر يُشتقّ من صفّ التوكن (بلا تسجيل دخول)، throttle، `ActivityLog` بـ`user=None`.
- **`submit_quote` هو نفس شكل طلبنا تقريباً**: طرفٌ خارجي يكتب قيماً على بنود مستند، الاسم إلزامي،
  كتابات متكرّرة مسموحة ما دام المستند مفتوحاً، عبر عقد `DOC_TYPES[…]["quote"]`. والرابط الخاص
  بمستقبِلٍ مسمّى سابقته `PurchaseRFQRecipient.share → DocumentShare`.
- **ثابت معماري**: كل كود `AllowAny` يعيش في `docshare` و`store` فقط — فالواجهة العامة للجرد تُبنى
  **داخل `docshare`** لا في `inventory/views.py`.
- صفحات React العامة بلا قشرة التطبيق: `frontend_v2/index.tsx` (`/jobs/:token`، `/rate/:token`…) قبل
  `AuthProvider`. والـthrottle الصحيح للكتابة العامة: `employee_ops` (`ClientIpScopedThrottle`) لأن
  `NUM_PROXIES=None` يجعل `ScopedRateThrottle` قابلاً للتجاوز بـ`X-Forwarded-For`.

### 1.3 الشجرة وقائمة الكبسة اليمين (`InvoiceCategoryTree.tsx`)
- **سبب الخلل #7 (مُتحقَّق):** ورقة المنتج (`leafButton`) عليها `onClick` فقط. الكبسة اليمين تفقّع إلى
  `.ktra-tree-body` الذي يستدعي `openMenu(e, null)` = «فراغ» ⇒ «إضافة تصنيف رئيسي» + «إضافة منتج هنا».
  **وأثره ليس شكلياً:** اختيار «إضافة منتج هنا» من صفّ منتج يُنشئ منتجاً **بلا تصنيف**.
- المكوّن **مشترك** مع شاشات الفواتير ⇒ أي فعل كتابة جديد يجب أن يُفعَّل بخاصية صريحة من شاشة
  المنتجات فقط، وبصلاحية.
- لا نقل منتج من الشجرة، ولا إعادة تعيين أب التصنيف منها (موجودة فقط في تبويب «التصنيفات» بـ`<select>`).
- الخادم جاهز: `CategorySerializer._validate_parent` يمنع الحلقة والشركة الأخرى؛
  `PATCH products/{id}/ {category}` يمرّ بـ`_validate_category_tenant` ثم `sync_family_from_product`.
- **حقيقة نطاقية يجب أن تُقال للمستخدم:** `category` حقلٌ على مستوى «المنتج الأب» (`FAMILY_FIELD_NAMES`) —
  نقلُ براندٍ واحد **ينقل كل براندات المنتج نفسه**. هذا تصميم مقصود (#20)، والواجهة اليوم لا تقوله.
- الوضع الافتراضي «جدول» مكتوب في الكود بتعليق «بطلب المالك» — المالك يطلب الآن العكس. الشجرة
  تنزّل الكتالوج كاملاً بثمانية طلبات **متتالية**؛ لا حفظ لآخر وضع.

### 1.4 كرت المنتج والبراند
- **سبب الخلل #8 (مُتحقَّق، ثلاثة عيوب واجهة — لا قاعدة خادم):**
  1. حقل البراند في وضع التعديل موجود **فقط في الشريط العلوي** (`currentId != null && fld("البراند"`)،
     وتبويب «بيانات عامة» حيث يعمل المستخدم لا يحويه.
  2. `ItemQuickEditModal` (قلم التعديل من كل مستند ومن كرت المنتج والأرصدة) **بلا حقل براند**،
     وتعليق `utils/itemSimpleFields.ts` يدّعي أنه «خلف متقدّم» ولا قسم متقدّم هناك.
  3. **فقدان بيانات:** `ValuePicker` يستدعي `onChange("")` عند «+» وعند «إلغاء» ⇒ يمسح البراند
     الحالي فوراً ويُحفظ فارغاً إن ضغط حفظ. نفس العيب على حقل «الصنف/المجموعة».
- الخادم سليم: `brand` قابل للكتابة، ليس حقل عائلة (يخصّ الصفّ وحده).
- اختيار التصنيف: `CategoryPicker` = `<select>` مسطّح بإزاحة، بلا بحث، الخيار يحمل الاسم الأخير فقط
  (تصنيفان باسم «جوالات» لا يتميّزان)، «+» يُنشئ **ابناً للمحدَّد** ويستبدل الاختيار، والحقل **مكرّر
  مرتين** في نفس الكرت (الشريط + التبويب) بجلبين منفصلين. `ItemQuickCreateModal` من الفواتير بلا
  تصنيف ⇒ منتجات الفواتير تصل `category = null`. ونسخة ثانية من مسار الشجرة في `ItemForm` تخالف
  قاعدة «خوارزمية واحدة».

### 1.5 تقرير المبيعات حسب المنتج (`core/reports/sales.py`)
- الصفوف مجمّعة على **`ProductFamily`** (`_bucket_of`، `family:N`) بعمود رمز فارغ، والفلتر الوحيد
  «المنتج» يمرّر **`Product` (براند)** ⇒ نفس الكلمة لجدولين، واختيار الفلتر يغيّر حبيبة التقرير بصمت.
- لا عمود براند ولا مؤشّر مستوى، حتى في التفصيل المعنون «برندات هذا المنتج». التفصيل لا يُكتشف إلا
  بالنقر على الصف.
- الفلتر `<select>` أصلي بكل الكتالوج (~1490 خياراً، ~1.1MB لكل فتح للتقرير) بلا بحث، والخيار
  `SKU — الاسم` بلا براند. الطباعة تحذف الرمز والبراند من سطر الفلتر.
- المكوّن البديل موجود: `KitAutocomplete`، والتقرير يقبل أصلاً نوع فلتر غير `<select>` (`account`).

---

## 2. ⚠️ خطر وُجد أثناء التحقيق (يُبلَّغ في نفس اللحظة)

| # | الخطر | الموضع | الحكم |
|---|---|---|---|
| D1 | **ترحيل الجرد بلا قفل صفّ**: `post_stocktake` يفحص `is_posted` على نسخة قديمة بلا `select_for_update`. ترحيلان متزامنان ⇒ `record_stock_movement` يطبّق الفرق **مرتين** بينما `post_journal` متساوي الأثر فيعيد القيد نفسه ⇒ **المخزون والدفاتر يفترقان** | `inventory/services.py` (`post_stocktake`) | تذكرة S1، أولى المراحل |
| D2 | **ثغرة صلاحيات**: `CategoryViewSet` وكتابات `ProductViewSet` (تعديل/حذف) لا تشترط `inventory.item.manage` — أي دور غير «مشاهد» ينشئ/يحذف/ينقل تصنيفات. و`add-brand` بلا حارس رغم أن التوثيق يوحي بالعكس | `inventory/views.py` (`CategoryViewSet`، `ProductViewSet.update/destroy`، `add_brand`) | تذكرة S2 (قاعدة المالك: ثغرات الأمن تُصلح كتذكرة بلا سؤال) |
| D3 | ترقيم الجرد `MAX+1` بلا قيد فرادة، خارج `TenantBook` المطلوب في `ARCHITECTURE.md` §5 | `inventory/services.py` (`_next_doc_number`) | ضمن S1 (الترقيم فقط؛ قيد الفرادة يحتاج فحص تكرارات الإنتاج أولاً) |
| D4 | تعديل المدير لمسودّة الجرد يحذف كل البنود ويعيد إنشاءها ⇒ سيمحو ما عبّأه موظف الرابط بصمت | `StocktakeSerializer.update` | ضمن K1 (شرطٌ لازم للميزة) |
| D5 | `ValuePicker` يمسح البراند الحالي بـ«+»/«إلغاء» | `components/inventory/ValuePicker.tsx` | ضمن B2 |
| D6 | «إضافة منتج هنا» من صفّ منتج يُنشئ منتجاً بلا تصنيف | `InvoiceCategoryTree.tsx` | ضمن B1 |

لا شيء «ينزف» في الإنتاج الآن بشكلٍ مؤكّد (D1 يحتاج نقرتين متزامنتين)، فلا احتواء طارئ — تذاكر مستقلّة.

---

## 3. المراجع المهنية (§1.5)

- **Odoo** (وحدات الجرد): جلسات عدّ تُبنى من مستودع/تصنيفات/منتجات وتُسند لمستخدم مسؤول، بحالات
  «بانتظار/معدود/مطبَّق»، ومراجعة المدير قبل التطبيق. **Zoho Inventory**: جرد يُسند لمستخدم، والعدّ من
  تطبيق الجوال فقط ويتطلّب حساباً. **Eren Stocktake (Shopify)**: اختيار النطاق بالمجموعة/النوع/الوسم،
  والموظف يدخل **برابط أو QR بلا حساب**، و**عدّ أعمى** يخفي الكمية المتوقّعة.
- **ما أخذناه:** النطاق بالتصنيفات، إسناد كل رابط لاسم عادّ، عدّة روابط لجرد واحد (تقسيم الأقسام بين
  موظفين كجلسات Odoo — اختيارياً)، مراجعة المدير ثم الترحيل.
  **ما رفضناه:** حساب إلزامي للعادّ (Zoho) — موظف المستودع لا يملك حساباً، وهذا أصل الطلب. والعدّ الأعمى
  (Eren) أوصينا به ورفضه المالك: الموظف يرى كمية النظام (قرار ق1).
  **أين نتجاوزهم:** شجرة بكل المستويات بحالة ثلاثية بدل وسمٍ مسطّح؛ حفظٌ تلقائي لكل سطر يصمد أمام انقطاع
  الشبكة؛ لوحة تقدّم حيّة للمدير (مَن عدّ ماذا ومتى)؛ إبطال تلقائي للروابط عند الترحيل.

---

## 4. القرارات التصميمية

1. **«التصنيف» = عقدة الشجرة · «المنتج» = الأب (`ProductFamily`) · «البراند» = الصفّ القابل للبيع
   (`Product`).** تُطبَّق هذه التسمية في كل نصّ واجهة نلمسه (التقرير، الشجرة، الكرت). لا إعادة تسمية
   لأعمدة أو APIs.
2. **مكوّن واحد للشجرة القابلة للاختيار:** `CategoryTreeSelect` بوضعين `single` / `multi`، فوق
   `utils/categoryTree.ts`. يخدم: كرت المنتج، نافذة النقل، أب التصنيف، الجرد الجديد، رابط الجرد الجزئي.
   منطق الحالة الثلاثية دوالّ خالصة في `utils/categoryTree.ts` تُختبر بـ`node --test`.
3. **دلالة اختيار الشجرة في الجرد (صريحة لا ضمنية):** كل عقدة مؤشَّرة = منتجاتها **المباشرة**. تأشير أب
   يؤشّر كل أحفاده بصرياً؛ إلغاء ابن يجعل الأب «جزئياً» وتبقى منتجات الأب المباشرة مشمولة. يُرسَل للخادم
   قائمة المعرّفات المؤشَّرة كما هي + علم «بدون تصنيف». الخادم يطابق `category_id__in` بعد تحقّق المستأجر.
   سبب الرفض للبديل («الأب يعني كل أحفاده»): يجعل «جزئي» غير قابل للتعبير.
4. **البنود تولَّد في الخادم** من النطاق (`counted_quantity = null` = لم يُعَدّ) — نهاية تنزيل الكتالوج كاملاً.
5. **رابط الموظف = `DocumentShare` بنوع مستند جديد `stocktake_count`** + صفّ `StocktakeCountLink`
   (اسم العادّ، نطاق تصنيفات اختياري ضمن نطاق الجرد) على نمط `PurchaseRFQRecipient`. الواجهة العامة
   JSON داخل `docshare`، والصفحة React على `/count/:token` (لا تحتاج سطر nginx: `/api/` يمرّ أصلاً).
6. **الكتابة العامة على مستوى السطر لا استبدال المستند:** الموظف يرسل `[{line_id, counted_quantity}]`،
   تُقبل فقط بنود ضمن نطاق رابطه، تحت `select_for_update` للجرد، وتُرفض إن رُحِّل. تكتب
   `counted_by_name` و`counted_at` على السطر.
7. **لا يُرحِّل الرابط شيئاً أبداً** — الترحيل للمدير فقط (`inventory.doc.post`)، والترحيل يُبطل كل روابط الجرد.
8. نقل المنتج من الشجرة يكتب صفّ البراند عبر المسار القائم (`sync_family_from_product`) ويعرض تحذيراً
   صريحاً «سينتقل معه N براند» عند `family_brand_count > 1`.

### قرارات المالك (2026-10-21)
| سؤال | القرار |
|---|---|
| ق1: هل يرى موظف الرابط كمية النظام؟ | **نعم — يراها** (خلافاً لتوصيتنا بالعدّ الأعمى). التكلفة والأسعار تبقى محجوبة |
| ق2: البنود غير المعدودة عند الترحيل؟ | **تُستثنى** مع نافذة تأكيد تذكر عددها، وخيار صريح «اعتبرها صفراً» |
| ق3: مدّة صلاحية الرابط؟ | خيارات 1 / 3 / 7 أيام، الافتراضي **3** (+ إبطال يدوي فوري + تلقائي عند الترحيل) |
| ق4: أكثر من رابط لجرد واحد؟ | **ممكن لا إلزامي**: الافتراضي رابط واحد للجرد كله باسم موظف واحد؛ «رابط إضافي» بنطاق تصنيفات جزئي متاح لمن يريد التقسيم ولا يُفرض |

---

## 5. تدفّق المستخدم (SYSTEM_FLOW) — الحالة الابتدائية ← الفعل ← النتيجة ← الخطأ

### 5.1 جرد جديد (المدير)
1. «جرد جديد» ← نافذة خطوتين. **خطوة 1:** التاريخ، المستودع، ملاحظات. **خطوة 2 «ماذا سنجرد؟»:**
   `كل المنتجات` | `تصنيفات محدّدة` (افتراضي) | `يدوي (فارغ)`. في «تصنيفات محدّدة»: الشجرة كاملة مفتوحة
   على المستوى الأول، بحث يفتح الفروع المطابقة، عدّاد منتجات بجانب كل عقدة، «تحديد الكل/إلغاء»، وملخّص
   حيّ «سيُجرد 143 منتجاً في 6 تصنيفات». خيار «شمل المنتجات غير الفعّالة» (افتراضي: لا)، «شمل الخدمات»
   (دائماً لا).
2. «إنشاء» ← `POST stocktakes/` بالنطاق ← الخادم يولّد البنود ← تفتح ورقة الجرد بالبنود مجمّعة على
   الشجرة، شريط تقدّم «معدود 0 / 143».
3. **أخطاء:** نطاق فارغ (0 منتجات) ← زر الإنشاء معطّل + رسالة «لا منتجات في هذا الاختيار». فشل شبكة ←
   النافذة تبقى بحالتها. تصنيف حُذف أثناء الاختيار ← 400 بأسماء المرفوض، النافذة تبقى.

### 5.2 تصدير رابط للموظف
1. في جرد مسودّة: «تصدير رابط للموظف» ← نافذة: **اسم الموظف (إلزامي)**، الصلاحية (1/3/7، افتراضي 3).
   النطاق `كل الجرد` افتراضياً، وخيار مطويّ «تقسيم على أكثر من موظف؟» لمن يريد رابطاً إضافياً بتصنيفات
   جزئية (شجرة مقصورة على تصنيفات هذا الجرد) — متاح لا مفروض (ق4).
2. «إنشاء الرابط» ← رابط + نسخ + مشاركة واتساب + QR. يظهر في قائمة «روابط هذا الجرد»: الاسم، الحالة
   (لم يُفتح / فُتح / يعدّ / أنهى)، المعدود X/Y، آخر إرسال، زر إبطال، زر نسخ مجدّداً.
3. **أخطاء:** جرد مرحَّل ← الزر مخفي، والخادم يرفض 400. اسم فارغ ← الزر معطّل. نطاق رابط خارج نطاق
   الجرد ← 400.

### 5.3 صفحة الموظف `/count/:token` (جوال أولاً، بلا تسجيل)
1. فتح ← رأس: اسم الشركة، رقم/تاريخ الجرد، المستودع، «العادّ: أحمد». قائمة البنود مجمّعة بالتصنيف،
   بحث (اسم/رمز/باركود نصّي)، فلتر «غير المعدود فقط»، شريط تقدّم. بجانب كل صنف **كمية النظام** (ق1)
   وخانة المعدود، والفرق يتلوّن عند الإدخال.
2. إدخال كمية ← حفظ تلقائي مؤجَّل (~1.5 ث) لدفعة الأسطر المتغيّرة ← علامة ✓ للسطر. نسخة محلية في
   `localStorage` تصمد أمام انقطاع الشبكة وإغلاق الصفحة وتُعاد إرسالها.
3. «انتهيت» ← تأكيد يذكر غير المعدود ← حالة «أنهى» على الرابط. يبقى التعديل ممكناً حتى يرحّل المدير.
4. **أخطاء:** توكن مجهول ← صفحة 404 «الرابط غير صحيح». منتهٍ/مبطَل/الجرد رُحِّل ← 410 «انتهى هذا
   الرابط — راجع المسؤول». قيمة سالبة/غير رقمية ← رفض على السطر بلا ضياع الباقي. throttle ← رسالة
   «حاول بعد قليل» والنسخة المحلية محفوظة.
5. **لا يظهر أبداً:** التكلفة، القيم المالية، الأسعار، أي رابط للتطبيق.

### 5.4 مراجعة وترحيل (المدير)
ورقة الجرد تعرض لكل سطر «عدّه: أحمد · 10:42» وتتحدّث بزر «تحديث» (وتلقائياً كل 30 ث أثناء وجود رابط
حيّ). التعديل اليدوي بـ`If-Match` ⇒ 412 «تغيّر الجرد — حدّث» بدل محو عمل الموظف. «ترحيل» ← تأكيد ق2 ←
`post/` ← الروابط تُبطل.

### 5.5 المنتجات والشجرة
- فتح «المنتجات» ← **الشجرة** افتراضياً، وآخر وضع يختاره المستخدم يُحفظ له.
- كبسة يمين على **منتج**: فتح الكرت · تعديل سريع · **نقل إلى تصنيف…** · إضافة منتج في نفس التصنيف ·
  نسخ الرمز. على **تصنيف**: إضافة تصنيف فرعي · إضافة منتج هنا · إعادة تسمية · **نقل تحت…** · حذف. على
  **الفراغ**: إضافة تصنيف رئيسي · إضافة منتج بلا تصنيف.
- «نقل إلى تصنيف…» ← نافذة `CategoryTreeSelect` (single) + تحذير البراندات ← حفظ ← الشجرة تتحدّث
  والمنتج ظاهر تحت مكانه الجديد. **خطأ:** 403 لمن لا يملك `inventory.item.manage` (والأفعال مخفية له
  أصلاً)؛ «نقل تحت…» يستبعد العقدة وأحفادها من الخيارات، والخادم يرفض الحلقة.

### 5.6 كرت المنتج
حقل تصنيف **واحد** (تبويب «بيانات عامة»؛ الشريط العلوي يعرض المسار كشارة تقفز إليه). منتقي منسدل:
بحث يعرض **المسار كاملاً** لكل نتيجة، تصفّح بالشجرة، «إنشاء تصنيف» بخيار صريح للموضع (تحت المحدَّد /
بجانبه / رئيسي). تحت الحقل: المسار + «يحدّد حسابات الإيراد والتكلفة والمخزون» + تحذير البراندات عند التغيير.
البراند: حقل واحد في «بيانات عامة» في الإنشاء والتعديل، ولا يُمسح بـ«+» أو «إلغاء».

### 5.7 تقرير المبيعات حسب المنتج
عنوان «المبيعات حسب المنتج» مع سطر توضيح «كل صف = منتج بكل براندياته — افتح الصف لترى البراندات».
أعمدة: المنتج · عدد البراندات · الكمية · … ؛ زرّ توسيع ظاهر على كل صف. التفصيل: البراند · الرمز · … .
فلتران بحثيّان: **المنتج** (أب) و**البراند** — كلاهما `KitAutocomplete` بنصّ «الاسم (البراند)» وسطر فرعي
«الرمز · المنتج». زر مسح يعيد «الكل». الطباعة تكتب الاسم + الرمز + البراند.

---

## 6. التذاكر

> لكل منفّذ: **ابدأ بـ`/engineering-protocol`**. البوّابة قبل التسليم: `python -m pytest <app>/tests -q` أثناء
> العمل، ثم `python -m pytest -q -n auto` كاملة، و`npm test` في `frontend_v2` عند لمس `utils/*.ts`،
> و`npx tsc --noEmit` للواجهة. المنفّذ **لا يعمل commit**. تحديث `docs/modules/<app>.md` +
> `ARCHITECTURE.md` (إن تغيّر وصف) + سطر `docs/CHANGELOG.md` + `python manage.py sync_docs`.

### المرحلة M0 — السلامة (قبل أي ميزة)

```
TASK-ID: S1
TIER: T3 deep
EXECUTOR: sonnet-implementer (Sonnet 5.5) — مسار مخزون+قيود
CONTEXT: inventory/services.py (post_stocktake, _next_doc_number) · accounting/services.py (next_document_number) ·
  tenants/models.py (TenantBook.get_next_number) · inventory/views.py (StocktakeViewSet.post_doc) ·
  inventory/tests/test_inventory_documents.py · ARCHITECTURE.md §5 · docs/modules/inventory.md (الجرد)
GOAL: ترحيل الجرد آمنٌ تحت التزامن ويُرقَّم من TenantBook.
SUCCESS CRITERIA:
  - post_stocktake يقفل صفّ Stocktake (select_for_update) ويعيد فحص is_posted بعد القفل، ويقرأ
    system_quantity تحت قفل المنتج داخل المعاملة.
  - اختبار يحاكي ترحيلاً ثانياً لنفس الجرد بعد الأول بنسخةٍ قديمة من الكائن ⇒ ValidationError، وحركة
    مخزون واحدة لكل منتج، وقيد واحد. يسقط قبل الإصلاح (يُثبَت بتشغيله على الكود القديم).
  - stocktake_number من next_document_number/TenantBook بنفس البادئة JRD (اختبار تسلسل).
  - pytest -q -n auto أخضر.
CONSTRAINTS: كل حركة عبر record_stock_movement وكل قيد عبر post_journal. لا قيد فرادة على الرقم
  (يحتاج فحص تكرارات الإنتاج — يُسجَّل في [ORPHANS & PENDING]).
OUT OF SCOPE: أي تغيير في نموذج الجرد أو واجهته.
DELIVERABLE: services.py + اختبارات + docs/modules/inventory.md + CHANGELOG.
ROUTING REASON: مال ومخزون — لا يُعطى لمنفّذ ميكانيكي.
```

```
TASK-ID: S2
TIER: T3 deep
EXECUTOR: sonnet-implementer (Sonnet 5.5)
CONTEXT: inventory/views.py (CategoryViewSet, ProductViewSet.update/partial_update/destroy, add_brand,
  bulk_set_group كنموذج requires_perm) · core/access.py (inventory.item.manage ومصفوفة الأدوار) ·
  core/permissions.py (requires_perm, TenantRolePermission) · inventory/tests/test_category_api.py
GOAL: كتابات التصنيفات وتعديل/حذف المنتج وadd-brand تشترط inventory.item.manage.
SUCCESS CRITERIA:
  - قبل البدء: جدول في التقرير «دور × هل يملك inventory.item.manage» من core/access.py، ومَن سيخسر
    صلاحية فعلية.
  - create/update/partial_update/destroy على categories/ ⇒ 403 لدور بلا المفتاح، 2xx لمن يملكه (اختبارات).
  - PATCH/DELETE products/{id}/ و products/add-brand/ ⇒ نفس الشيء.
  - **إنشاء** منتج (POST products/) يبقى على القاعدة الحالية: الإنشاء السريع من الفواتير يستعمله دور
    المبيعات — اختبار يثبت أن دور sales ما زال ينشئ.
  - pytest -q -n auto أخضر، وe2e items-* تمنح المفتاحين أصلاً (تحقّق قراءةً).
CONSTRAINTS: لا تغيير في مصفوفة الأدوار نفسها. الواجهة: أخفِ أفعال الكتابة في الشجرة/التصنيفات عمّن لا
  يملك المفتاح (usePermissions().can).
OUT OF SCOPE: صلاحيات أي app أخرى.
DELIVERABLE: views.py + اختبارات + تصحيح سطر add-brand في docs/modules/inventory.md + CHANGELOG.
ROUTING REASON: ثغرة صلاحيات — تغيّر سلوك أدوار قائمة.
```

### المرحلة M1 — الأخطاء والتغييرات السريعة

```
TASK-ID: B1
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: frontend_v2/components/procurement/invoices/InvoiceCategoryTree.tsx (menu, openMenu, leafButton,
  ktra-tree-body, صفّ «بدون تصنيف») · components/items/ItemsManagement.tsx (استدعاء الشجرة)
GOAL: كبسة يمين على منتج تفتح قائمة المنتج لا قائمة الفراغ.
SUCCESS CRITERIA:
  - menu يحمل الهدف {kind: 'empty'|'category'|'item', id}. leafButton عليه onContextMenu يوقف الانتشار.
  - قائمة المنتج (قراءة فقط في هذه التذكرة): فتح الكرت · إضافة منتج في نفس التصنيف (يمرّر تصنيف المنتج
    لا null) · نسخ الرمز. «إضافة منتج هنا» لا تظهر على منتج أبداً.
  - صفّ «بدون تصنيف» يعلن openMenu(e, null) صراحةً.
  - اختبار Playwright جديد في e2e/: كبسة يمين على منتج ⇒ «فتح الكرت» ظاهر و«إضافة تصنيف رئيسي» غائب.
    يُشغَّل يدوياً ويُلصق مخرجه.
  - npx tsc --noEmit نظيف.
CONSTRAINTS: لا أفعال كتابة جديدة هنا. المكوّن مشترك مع الفواتير — سلوكها لا يتغيّر إلا بإصلاح الخلل.
OUT OF SCOPE: النقل (C3)، استبدال القائمة بمكوّن عام.
DELIVERABLE: الملف + e2e spec + CHANGELOG.
ROUTING REASON: خلل واجهة محصور بملف واحد.
```

```
TASK-ID: B2
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: frontend_v2/components/inventory/ValuePicker.tsx · components/items/ItemForm.tsx (حقل البراند في
  الشريط وفي «بيانات عامة»، handleSave) · components/items/ItemQuickEditModal.tsx ·
  utils/itemSimpleFields.ts (+ اختبارها) · components/items/ItemsManagement.tsx (commitNameEdit)
GOAL: البراند قابل للتعديل من كل سطح تعديل، ولا يُمسح بالخطأ.
SUCCESS CRITERIA:
  - ValuePicker: «+» و«إلغاء» لا يستدعيان onChange — القيمة القديمة تبقى حتى تأكيد جديدة (اختبار وحدة
    إن أمكن عبر دالّة خالصة، وإلا e2e).
  - ItemForm: حقل براند واحد في «بيانات عامة» في الإنشاء والتعديل؛ يُزال من الشريط العلوي.
  - itemSimpleFields يضمّ brand؛ ItemQuickEditModal يعرضه بـValuePicker(getBrands)؛ dirtySimplePayload لا
    يُصدر brand في تعديل الاسم فقط (اختبار node --test).
  - تصحيح تعليق itemSimpleFields الكاذب.
  - npm test وtsc نظيفان؛ e2e items-inline-name-edit ما زال يمرّ.
CONSTRAINTS: لا تغيير في الخادم. نصّ الحقل «البراند».
OUT OF SCOPE: إعادة تصميم إنشاء البراندات المتعدّدة.
DELIVERABLE: الملفات + اختبارات + CHANGELOG.
ROUTING REASON: ثلاثة عيوب واجهة مثبتة الأسباب.
```

```
TASK-ID: B3
TIER: T1 mechanical
EXECUTOR: opencode (deepseek-v4.1-flash)
CONTEXT: frontend_v2/components/items/ItemsManagement.tsx (displayMode) · services/inventoryApi.ts
  (getAllProducts) · e2e/items-tree-card-pane.spec.ts · e2e/items-inline-name-edit.spec.ts
GOAL: المنتجات تفتح على الشجرة، ويُحفظ آخر وضع للمستخدم.
SUCCESS CRITERIA:
  - useState يقرأ localStorage['ktra.items.displayMode'] (try/catch) والافتراضي "tree"؛ التبديل يكتبه.
  - تعليق «بطلب المالك» يُحدَّث للطلب الجديد بتاريخه.
  - getAllProducts: الصفحة الأولى ثم الباقي بالتوازي بعد معرفة count (لا حلقة متتالية) — نفس النتيجة.
  - e2e المذكوران محدَّثان (لا يفترضان الجدول افتراضياً).
  - tsc نظيف.
CONSTRAINTS: لا تغيير في سلوك الجدول.
OUT OF SCOPE: التحميل الكسول للشجرة (§9).
DELIVERABLE: الملفات + CHANGELOG.
ROUTING REASON: تغيير قيمة افتراضية + حلقة جلب.
```

### المرحلة M2 — المكوّن المشترك

```
TASK-ID: C1
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: frontend_v2/utils/categoryTree.ts (+ categoryTree.test.ts) · components/inventory/CategoryPicker.tsx ·
  components/kit/KitAutocomplete.tsx (للنمط) · docs/modules/frontend.md · قواعد Tailwind فقط
GOAL: CategoryTreeSelect واحد (single/multi) قابل للبحث بمسارات كاملة وحالة ثلاثية.
SUCCESS CRITERIA:
  - دوالّ خالصة في utils/categoryTree.ts: toggleSubtree(checked, id) · checkState(id) → 'on'|'off'|'partial' ·
    searchCategories(q) → [{id, pathLabel}] · مع اختبارات node --test تغطّي: تأشير أب يؤشّر الأحفاد،
    إلغاء ابن يجعل الأب partial ويُبقي الأب نفسه مؤشَّراً، تصنيف يتيم، حلقة بيانات لا تعلّق.
  - المكوّن: وضع single (منسدل بحث + تصفّح + إنشاء بموضع صريح) ووضع multi (شجرة صناديق، عدّاد منتجات
    اختياري، تحديد/إلغاء الكل، ملخّص). indeterminate عبر ref. لوحة مفاتيح: أسهم/Enter/Space/Esc.
  - لا inline styles (Tailwind)، RTL، يعمل في الوضع الداكن.
  - npm test وtsc نظيفان.
CONSTRAINTS: الخوارزمية في categoryTree.ts وحدها — لا نسخة ثانية. لا مكتبة جديدة.
OUT OF SCOPE: استبدال الاستخدامات (C2/C3/K2).
DELIVERABLE: المكوّن + الدوالّ + الاختبارات + docs/modules/frontend.md.
ROUTING REASON: مكوّن أساس تبني عليه أربع تذاكر.
```

### المرحلة M3 — التصنيفات في المنتج والشجرة (تعتمد C1، S2)

```
TASK-ID: C2
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: components/items/ItemForm.tsx (حقلا التصنيف، مسار «سيُحفظ تحت»، handleSave) ·
  components/items/ItemQuickCreateModal.tsx · components/items/ItemQuickEditModal.tsx ·
  components/inventory/CategoryPicker.tsx · inventory/serializers.py (family_brand_count إن وُجد في الردّ)
GOAL: اختيار تصنيف المنتج واضح ومهني في كل أسطح الإنشاء/التعديل.
SUCCESS CRITERIA:
  - حقل تصنيف واحد في ItemForm (التبويب)، والشريط يعرض شارة المسار. لا نسخة ثانية لمسار الشجرة في
    ItemForm (تُستعمل categoryPathLabel).
  - CategoryPicker يصبح غلافاً لـCategoryTreeSelect(single) فيستفيد كل مستدعيه.
  - ItemQuickCreateModal فيه المنتقي (مملوء مسبقاً من الخاصية).
  - تحذير «سينتقل معه N براند» عند تغيير تصنيف منتج له أكثر من براند، وسطر «يحدّد حسابات…».
  - e2e: إنشاء منتج تحت تصنيف عميق بالبحث بالمسار ⇒ يظهر في الشجرة تحته. tsc نظيف.
CONSTRAINTS: الحفظ عبر PATCH products/{id}/ القائم.
OUT OF SCOPE: الشجرة والنقل (C3).
DELIVERABLE: الملفات + e2e + CHANGELOG + docs/modules/inventory.md (سطر الواجهة).
ROUTING REASON: UX متعدّد الملفات على مكوّن جاهز.
```

```
TASK-ID: C3
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: InvoiceCategoryTree.tsx (بعد B1) · ItemsManagement.tsx · GroupedItemsTable.tsx (التحديد الجماعي) ·
  inventory/views.py (ProductViewSet، bulk_set_group كنموذج، _validate_category_tenant) ·
  inventory/services.py (sync_family_from_product) · core/permissions.py (read_only_post_actions)
GOAL: نقل المنتج (فرداً وجماعةً) وإعادة تعيين أب التصنيف من الشجرة بكبسة يمين.
SUCCESS CRITERIA:
  - خادم: POST products/bulk-set-category/ {ids:[...], category: id|null} — requires_perm
    inventory.item.manage، معرّفات في الجسم، تحقّق مستأجر التصنيف، كل منتج يمرّ بـsync_family_from_product
    داخل معاملة، ردّ {moved, skipped}. ليس في read_only_post_actions. اختبارات: نقل، تصنيف شركة أخرى ⇒
    400، معرّف منتج شركة أخرى ⇒ يُتجاهَل ولا يُكتب، بلا صلاحية ⇒ 403، الإخوة ينتقلون.
  - واجهة: خاصية allowCatalogEdit على InvoiceCategoryTree (true في ItemsManagement فقط) تُظهر «نقل إلى
    تصنيف…» على المنتج و«نقل تحت…» على التصنيف (PATCH categories/{id}/ {parent}) بنافذة
    CategoryTreeSelect تستبعد العقدة وأحفادها (eligibleParents). الجدول: «نقل المحدَّد إلى تصنيف…».
  - شاشات الفواتير لا ترى أفعال الكتابة (e2e أو قراءة مستدعيها).
  - pytest inventory/tests أخضر ثم الكامل؛ tsc نظيف؛ e2e نقل منتج يُشغَّل يدوياً.
CONSTRAINTS: لا كتابة على ProductFamily مباشرة. لا سحب وإفلات.
OUT OF SCOPE: السحب والإفلات (§9).
DELIVERABLE: views.py + inventoryApi.ts + الواجهة + اختبارات + docs/modules/inventory.md (نقطة جديدة) +
  docs/API_INDEX.md عبر sync_docs + CHANGELOG.
ROUTING REASON: كتابة جماعية بصلاحية ومستأجر.
```

### المرحلة M4 — الجرد (تعتمد S1، C1)

```
TASK-ID: K1
TIER: T3 deep
EXECUTOR: sonnet-implementer
CONTEXT: inventory/models.py (Stocktake, StocktakeLine) · inventory/serializers.py (StocktakeSerializer,
  StocktakeLineSerializer) · inventory/views.py (StocktakeViewSet) · inventory/services.py (post_stocktake،
  category_descendant_ids) · core/concurrency.py (OptimisticConcurrencyMixin) · sales/views.py
  (DeliveryOrderViewSet كمثال للمزيج) · inventory/tests/test_inventory_documents.py
GOAL: جرد يُبنى من نطاق تصنيفات في الخادم، بأسطر تُحدَّث لا تُستبدل، وتزامن متفائل.
SUCCESS CRITERIA:
  - هجرة: StocktakeLine.counted_quantity nullable · StocktakeLine.counted_by_name (120) · counted_at ·
    Stocktake.created_by (FK user, SET_NULL) · Stocktake.scope (JSON: {categories:[...], uncategorized:bool,
    include_inactive:bool}). الهجرة ذهاباً وإياباً على SQLite.
  - خدمة create_stocktake_from_scope(tenant, user, date, warehouse, notes, scope) في services.py: تتحقّق أن
    كل تصنيف للمستأجر، تولّد سطراً لكل منتج غير خدمي مطابق (category_id__in بالضبط + بدون تصنيف إن طُلب)،
    counted_quantity=null. الـserializer يقبل إمّا scope أو lines (يدوي — السلوك الحالي محفوظ).
  - update يحدّث الأسطر بالـproduct (upsert) ولا يحذف أسطراً لم تُرسَل إلا بعلم صريح replace_lines=true؛
    لا يمسح counted_by_name لسطرٍ لم تتغيّر كميته.
  - StocktakeViewSet يستعمل OptimisticConcurrencyMixin (ETag/If-Match ⇒ 412).
  - post_stocktake: الأسطر بـnull تُستثنى، أو تُعتبر صفراً عند post({uncounted_as_zero:true}) (ق2)؛ رفض
    إن كانت كل الأسطر null.
  - list endpoint يعيد ملخّصاً بلا lines (serializer مختصر) + counted_count/line_count.
  - اختبارات لكل ما سبق + تسرّب المستأجر (تصنيف شركة أخرى في scope ⇒ 400). pytest -q -n auto أخضر.
CONSTRAINTS: كل حركة عبر record_stock_movement وكل قيد عبر post_journal. لا كسر لأي مستدعٍ حالي.
OUT OF SCOPE: الرابط العام (K3)، الواجهة (K2).
DELIVERABLE: models + migration + serializers + views + services + tests + docs/modules/inventory.md + CHANGELOG.
ROUTING REASON: هجرة + ترحيل مخزون.
```

```
TASK-ID: K2
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: frontend_v2/components/inventory/StocktakePage.tsx · services/inventoryApi.ts ·
  types/inventory.ts · CategoryTreeSelect (C1) · hooks/useDocumentDraft (المستعمل في الصفحة)
GOAL: «جرد جديد» بنافذة خطوتين وشجرة اختيار، وورقة جرد بلا تنزيل الكتالوج.
SUCCESS CRITERIA:
  - التدفّق §5.1 كما هو: كل/تصنيفات/يدوي، ملخّص حيّ (عدّاد من الخادم أو من categories بعدّادات)، منع
    النطاق الفارغ.
  - الصفحة لم تعد تستدعي getAllProducts عند الفتح؛ البنود تأتي من الجرد. الإكمال التلقائي للإضافة اليدوية
    يبحث في الخادم.
  - شريط تقدّم، فلتر غير المعدود، عمود «عدّه» (counted_by_name + الوقت)، If-Match عند الحفظ ومعالجة 412
    بنافذة «حدّث» دون فقدان المسودّة المحلية.
  - نافذة الترحيل تعرض عدد غير المعدود وخيار «اعتبرها صفراً».
  - أنواع Stocktake تنتقل إلى types/inventory.ts. tsc نظيف؛ e2e: جرد من تصنيفين ⇒ عدد البنود صحيح.
CONSTRAINTS: formatNumber/formatDate لكل رقم/تاريخ. Tailwind فقط.
OUT OF SCOPE: زر الرابط (K4).
DELIVERABLE: الملفات + e2e + CHANGELOG.
ROUTING REASON: إعادة بناء شاشة على عقد خادم جديد.
```

```
TASK-ID: K3
TIER: T3 deep
EXECUTOR: sonnet-implementer
CONTEXT: docshare/models.py (DocumentShare, DOC_TYPE_CHOICES) · docshare/documents/__init__.py +
  purchase_docs.py (QUOTE_PURCHASE_RFQ نموذجاً) + _contract.py · docshare/services.py (create_share,
  resolve_share, submit_quote, revoke_share) · docshare/views.py (DocSharePublicBase، DocumentShareViewSet) ·
  docshare/urls_public.py · logistics PurchaseRFQRecipient (نمط المستقبِل) · employee_ops/throttles.py
  (ClientIpScopedThrottle) · core/settings.py (معدّلات throttle) · docshare/tests (test_public_leakage إن وُجد)
GOAL: رابط عدّ عام لموظف مسمّى، يقرأ أسطر نطاقه ويكتب الكميات على مسودّة الجرد فقط.
SUCCESS CRITERIA:
  - نوع مستند stocktake_count في القائمتين (اختبار test_choices_match_registry يبقى أخضر).
  - نموذج StocktakeCountLink (في inventory: tenant, stocktake FK, share OneToOne→DocumentShare,
    counter_name, categories JSON|null, finished_at, created_by) + هجرة.
  - إداري (مصادَق): POST stocktakes/{id}/count-links/ {counter_name, days∈(1,3,7), categories?} ⇒ رابط؛
    GET قائمة الروابط بالحالة والتقدّم؛ POST …/{link}/revoke/. يشترط إمكانية تعديل الجرد؛ جرد مرحَّل ⇒ 400؛
    تصنيفات خارج نطاق الجرد ⇒ 400.
  - عام (داخل docshare، authentication_classes=[]، AllowAny، ClientIpScopedThrottle):
    GET /api/share/<token>/count/ ⇒ JSON {company_name, stocktake_number, date, warehouse, counter_name,
    lines:[{line_id, sku, name, brand, category_path, uom, system_quantity, counted_quantity}]} —
    system_quantity = الرصيد الحالي وقت القراءة (ق1)؛ **بلا تكلفة ولا قيم مالية ولا أسعار** (اختبار قائمة
    سماح للمفاتيح).
    POST /api/share/<token>/count/ {entries:[{line_id, counted_quantity}], finished?:bool} ⇒ تحت
    select_for_update للجرد: يرفض مرحَّلاً (410)، يقبل أسطر نطاق الرابط فقط (غيرها ⇒ يُتجاهَل ويُعدّ)،
    كمية ≥0 عشرية، يكتب counted_by_name=counter_name وcounted_at، يحدّث decided_at، ActivityLog
    user=None. حدّ حجم الجسم وعدد الأسطر.
  - 404 لتوكن مجهول، 410 لمنتهٍ/مبطَل/جرد مرحَّل، والوحدة المعطَّلة ⇒ 410.
  - post_stocktake (أو خدمة الترحيل) تُبطل كل روابط الجرد.
  - اختبارات: عزل المستأجر (توكن شركة أ لا يكتب سطر شركة ب)، نطاق جزئي، مرحَّل، منتهٍ، throttle، تسرّب
    مفاتيح. pytest -q -n auto أخضر.
CONSTRAINTS: لا AllowAny خارج docshare. لا ترحيل من المسار العام أبداً. التوكن بنمط create_share القائم.
OUT OF SCOPE: الصفحة العامة والنافذة (K4).
DELIVERABLE: models + migrations + services + views + urls + settings + tests + docs/modules/inventory.md +
  docs/modules (docshare إن وُجد) + ARCHITECTURE.md (سطح AllowAny جديد) + CHANGELOG.
ROUTING REASON: سطح عام بلا مصادقة يكتب بيانات — أعلى حساسية أمنية.
```

```
TASK-ID: K4
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: frontend_v2/index.tsx (المسارات العامة) · components/employee-ops/PublicJoinPage.tsx (نمط صفحة عامة +
  API_BASE) · constants/publicPages.ts · StocktakePage.tsx (بعد K2) · utils/formatNumber
GOAL: نافذة تصدير الرابط للمدير وصفحة عدّ جوالية للموظف.
SUCCESS CRITERIA:
  - نافذة التصدير §5.2: اسم إلزامي، صلاحية، نطاق (CategoryTreeSelect multi مقصور على نطاق الجرد)، نسخ،
    واتساب، QR (بلا مكتبة جديدة إن وُجد مولّد QR في المشروع، وإلا يُطلب إذن)، قائمة الروابط بالحالة
    والتقدّم وإبطال.
  - مسار /count/:token خارج AuthProvider؛ الصفحة §5.3: تجميع بالتصنيف، بحث، غير المعدود، حفظ تلقائي
    مؤجَّل بدفعات، نسخة localStorage تُعاد إرسالها، «انتهيت»، رسائل 404/410/429 بالعربية.
  - ورقة المدير تتحدّث كل 30 ث ما دام رابط حيّ.
  - e2e: إنشاء رابط ⇒ فتحه في سياق بلا جلسة ⇒ إدخال كميتين ⇒ ظهورهما عند المدير باسم العادّ. tsc نظيف.
CONSTRAINTS: الصفحة العامة لا تستورد restApi المصادَق ولا قشرة التطبيق. Tailwind فقط. عرض 360px بلا تمرير أفقي.
OUT OF SCOPE: مسح الكاميرا.
DELIVERABLE: الملفات + e2e + CHANGELOG + docs/modules/frontend.md.
ROUTING REASON: واجهتان على عقد K3.
```

### المرحلة M5 — التقرير (مستقلّة؛ تُوازى مع M3/M4)

```
TASK-ID: R1
TIER: T2 standard
EXECUTOR: sonnet-implementer
CONTEXT: core/reports/sales.py (_bucket_of, _sales_line_aggregate, _PRODUCT_SALES_COLUMNS، مواصفتا
  sales-by-product وsales-by-brand) · core/reports (ReportFilter، أنواع الفلاتر) ·
  core/tests/test_reports_family_rollup.py · frontend_v2/components/reports/ReportRunnerPage.tsx
  (renderFilter، ProductRow، طباعة الفلتر، lookupsNeeded) · components/kit/KitAutocomplete.tsx ·
  services/inventoryApi.ts (listPickerProducts، product-families)
GOAL: التقرير يقول بوضوح «منتج» مقابل «براند»، وفلاتره قابلة للبحث.
SUCCESS CRITERIA:
  - خادم: صفّ رئيسي يحمل brand_count؛ التفصيل يحمل brand وsku؛ عمود «عدد البراندات» في الرئيسي و«البراند»
    في التفصيل؛ فلتر family_id معلَن بنوع "family" بتسمية «المنتج»، والفلتر الحالي product يُعاد تسميته
    «البراند». كل حلّ لمعرّف مقيّد بـtenant_id. اختبارات family_rollup القائمة خضراء + اختبار للأعمدة الجديدة.
  - واجهة: فلترا product/family بـKitAutocomplete (نصّ display_name، فرعي «الرمز · المنتج»، كلمات بحث
    sku+name+brand) مع زر مسح يعيد «الكل»؛ سطر توضيح تحت العنوان؛ مؤشّر توسيع ظاهر على الصف؛ الطباعة
    تكتب الاسم + الرمز + البراند؛ ProductRow يضمّ brand/family_*/display_name.
  - إن كان lookup/products يدعم ?search= فالمنتقي يبحث في الخادم (لا تنزيل 1.1MB) — المنفّذ يتحقّق ويذكر.
  - pytest core/tests أخضر ثم الكامل؛ tsc نظيف.
CONSTRAINTS: لا تغيير في أرقام التقرير (الحبيبة نفسها). مفاتيح الفلاتر الجديدة في initialFilterValues.
OUT OF SCOPE: فلتر تصنيف (§9)، إعادة تصميم sales-by-brand.
DELIVERABLE: الملفات + اختبارات + CHANGELOG.
ROUTING REASON: تقرير قراءة فقط عبر الطبقتين.
```

---

## 7. جدول المراحل

| مرحلة | تذاكر | الهدف القابل للتحقّق | يعتمد على | يمكن توازيه مع |
|---|---|---|---|---|
| M0 | S1 · S2 | ترحيل الجرد آمن تحت التزامن؛ 403 على الكتابات بلا صلاحية | — | M1, M5 |
| M1 | B1 · B2 · B3 | الكبسة اليمين صحيحة؛ البراند قابل للتعديل؛ الشجرة افتراضية | — | M0, M5 |
| M2 | C1 | CategoryTreeSelect مختبَر | — | M0, M1, M5 |
| M3 | C2 · C3 | تصنيف المنتج واضح؛ نقل من الشجرة | C1, S2, B1 | M4 (ملفات مختلفة) |
| M4 | K1 → K2 · K3 → K4 | جرد بالتصنيفات + رابط الموظف من الطرف إلى الطرف | S1, C1 | M3 |
| M5 | R1 | تقرير واضح بفلاتر بحثية | — | الكل |

ترتيب التنفيذ المقترح: S1 ‖ B1 ‖ B2 ‖ R1 ← S2 ‖ B3 ‖ C1 ← C2 ‖ K1 ← C3 ‖ K2 ‖ K3 ← K4.
(ممنوع: كاتبان على نفس الملفات في وقت واحد — B1 وC3 يلمسان InvoiceCategoryTree فهما متتاليان.)

## 8. [ORPHANS & PENDING]
- قيد فرادة `(tenant, stocktake_number)` — بعد فحص تكرارات قاعدة الإنتاج.

## 9. أفكار أفضل مطروحة — لا تُبنى بلا «نعم»
1. **مسح الباركود بكاميرا الجوال** في صفحة الموظف (يقفز للسطر ويزيد 1) — أسرع عدّ ميدانياً.
2. **السحب والإفلات** في الشجرة لنقل المنتجات والتصنيفات (فوق قائمة الكبسة اليمين لا بديلاً عنها).
3. **تحميل كسول للشجرة** (منتجات العقدة عند فتحها + عدّادات من الخادم) — ضروري حين يتجاوز الكتالوج بضعة آلاف.
4. **فلتر تصنيف (CategoryTreeSelect)** في تقارير المبيعات والمخزون — المكوّن سيكون جاهزاً.
5. **جرد دوري ABC**: اقتراح تلقائي لتصنيفات الجرد التالية حسب القيمة/الحركة.
