# store — المتجر العام للمنتجات (سطح بلا مصادقة فوق كتالوج المنتجات)

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-13 (ST-1)، ومُحدَّث 2026-08-19 (ST-5: المظهر والحملات والسلة ولوحة إدارة المتجر)، 2026-09-07 (THA-166 م٢: القراءةُ العامة تحوّلت إلى `StoreProduct`، وظهر الخصم)، 2026-09-07 (THA-166 م٣: شاشاتُ إدارة المتجر على العقد الجديد + استيراد من الأصناف — الفجوة أُغلقت)، و2026-09-07 (THA-166 م٤: الفلترةُ بعدّاداتٍ سياقية). عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
app تخدم سطحين لا سطحاً واحداً: **زائراً مجهولاً** بخمس نقاط قراءة تحت `/api/store/<slug>/` (بطاقة الشركة ومظهرها · شبكة المنتجات المنشورة · صفحة المنتج · قائمة الحملات · صفحة هبوط الحملة)، و**مديراً مصادَقاً عليه** بنقاط `/api/store/admin/…` يضبط منها المظهر والصور والحملات ومنتجات المتجر.
السطح العام هو الواجهة التي يُشارَك رابطها على واتساب ويلتقطها محرك البحث، ولا يكتب في أي جدول من جداول الـERP سوى عدّاد المشاهدات.

**لماذا app مستقلة ولم تُضَف إلى `inventory`:** الحجة أمنية لا تنظيمية. كل كود `AllowAny` الجديد يعيش في مجلد واحد يقرؤه مراجع الأمن كاملاً في جلسة،
ويبقى `inventory/views.py` مئة بالمئة خلف المصادقة — بدل view عام مدسوس بين عشرين view محمي حيث يصير سطرٌ خاطئ في `get_queryset` تسريباً لا يلاحظه أحد.
السابقة الداخلية `accountant_portal` (سطح منفصل بطبقة وصول مختلفة)، والخارجية فصل Odoo لـ`website_sale` عن `stock`.

## مفتاح التشغيل: `Tenant.store_slug`
`tenants/models.py` (`validate_store_slug`) — حقل `store_slug` على `Tenant`: فريد، ونمطه `^[a-z0-9-]{3,40}$`، وكلماتٌ محجوزة مرفوضة (`RESERVED_STORE_SLUGS`).

**القيمة نفسها هي مفتاح التفعيل: NULL = المتجر مقفل.** فلا حقل `store_enabled` ثانٍ يمكن أن يتناقض معه، ولا حالة «متجر مفعّل بلا رابط».
ولا backfill للشركات القائمة: المتجر opt-in، والمدير يختار المعرّف عند أول فتح لشاشة «متجري».
(ملاحظة MySQL: قيد `unique` لا يمنع تكرار NULL — نفس ما وُثِّق في `TenantBook` — وهو المطلوب هنا بالضبط: كل الشركات مقفلة المتجر تتعايش.)

المعرّف **مقروء لا مبهم** لأن الرابط يُرسَل على واتساب ويظهر في نتائج البحث، و**قابل للتغيير** من المدير — وتغييره يكسر الروابط القديمة بلا redirect في هذه النسخة.

الكتابة من `tenants/views.py` (`set_store_slug`) وحدها — `POST /api/tenants/companies/<id>/set-store-slug/`، بصلاحية **`store.manage`**.
قيمة فارغة تُقفل المتجر. و`store_slug` **للقراءة فقط** في `tenants/serializers.py` (`TenantSerializer`) عمداً: لو كان قابلاً للكتابة لصار PATCH عادي على الشركة باباً خلفياً يتجاوز التحقّق.

## النقاط
| الطريقة | المسار | ماذا تُرجع |
|---|---|---|
| GET | `store/<slug>/` | بطاقة الشركة من `TenantSettings`: الاسم، الشعار، الهاتف، العنوان، **رمز العملة** |
| GET | `store/<slug>/products/` | المنتجات المنشورة — بحث `q`، تصفية `brand`/`category` (معرّفاتٌ متعدّدة بفواصل **أو اسمٌ مفرد**)، رايات `on_sale`/`is_new`/`in_stock`، مدى `min_price`/`max_price`، فرز `sort=price_asc\|price_desc`، **ترقيم إلزامي**، وعدّادات `facets`/`price_range` (انظر «الفلترةُ بعدّادات» أدناه) |
| GET | `store/<slug>/products/<id>/` | منتج واحد + كتابة عدّاد المشاهدة |
| GET | `store/<slug>/collections/` | الحملات النشطة (`StoreCollection`) مع عدد منتجاتها |
| GET | `store/<slug>/collections/<collection_slug>/` | صفحة هبوط الحملة: بياناتها + منتجها المميّز + منتجاتها مُرقَّمة |

كلها بلا مصادقة إطلاقاً (`authentication_classes = []`): توكن يُرسَل إلى نقطة متجر لا يقدر أن يغيّر حرفاً في الرد — خاصية بنيوية لا وعدٌ في مراجعة.
والشركة تأتي من الـslug في المسار وحده، لا من ترويسة `X-Tenant-Id`.
كل حالات «غير موجود» تردّ **404 لا 403**: 403 يُثبت لمن يخمّن المعرّفات أن الشركة أو المنتج موجود.

## القائمة البيضاء — ثلاث طبقات لمنع التسريب
الحمولة العامة **سبعةَ عشر** حقلاً حصراً منذ THA-166 م٢ (كانت أحد عشر): الأصلُ بقي حرفياً — `id, name_ar, name_en, brand, category_name, uom_name, price, availability, description, images, cover_overlay` — وستٌّ إضافيةٌ محضة: `slug, original_price, discount_percent, categories, stock_state, brand_id`.
وبطاقة الشركة لها قائمتها البيضاء المستقلة (`PROFILE_WHITELIST` في اختبار التسريب) بعد أن حملت إعدادات المظهر والهوية.

1. **الاستعلام** — `store/views.py` (`published_products`): مصدره منذ م٢ `StoreProduct.objects.filter(tenant=…, is_active=True)` لا `inventory.Product`. لا حاجة لـ`.only()` تحرس الرصيد والتكلفة كما في العصر السابق — **هذا الكتالوج لا يحمل هذه الأعمدة أصلاً بالتصميم** (لا مخزون ولا محاسبة أبداً، THA-166 م١). حين تكون الأسعار محجوبة (`show_prices=false`) يُستعمَل `.defer("price", "sale_price")` فلا يُقرآن من القاعدة حتى.
2. **السيريالايزر** — `store/serializers.py` (`StoreProductSerializer`): `serializers.Serializer` صِرف بحقول مصرَّحة واحداً واحداً، لا `ModelSerializer`.
   حقلٌ جديد على `StoreProduct` لا يصير عاماً بمجرد إضافته.
3. **الاختبار** — `store/tests/test_public_leakage.py`: يقارن **مجموعة** المفاتيح بالقائمة البيضاء (لا غياباً فردياً)، ثم يمسح شجرة JSON تكرارياً بحثاً عن الرصيد والتكلفة.

## التوفّر حالة لا رقم
**منذ THA-166 م٢**، التوفّر مصدره `StoreProduct.stock_state` — إعلانٌ من التاجر لا رقمٌ مشتقّ من رصيد: `store/serializers.py` (`StoreProductSerializer.get_availability`) يُطابق `in_stock ⇐ available` · `out_of_stock ⇐ out` · `preorder ⇐ preorder`. **`limited` سقطت ولا بديل لها**: كانت تُحسَب من `quantity_on_hand`/`min_stock_level`، وهذان حقلا مخزونٍ لا وجود لهما على `StoreProduct` بقرار مالكٍ صريح (لا مخزون ولا محاسبة أبداً، THA-166 م١).

**السعر الفعليّ خصمٌ محسوبٌ في SQL** — `store/views.py` (`published_products`):
مصدران يتنافسان والأكبر خصماً يفوز (الأفضل للزبون؛ لافتةٌ «خصم ٣٠٪ على الكل» فوق منتجٍ خصمُه المفرد ١٠٪ لا يجوز أن تُظهر ١٠٪):
- **المنتج المفرد** — `StoreProduct.sale_price`: **مبلغٌ مطلق**، هو السعر بعد الخصم نفسه.
- **الحملة** — `StoreCollection.discount_percent`: **نسبة** تسري على كل أعضائها، بشرط أن تكون **سارية الآن** (`_active_campaign_discount_percent`): `is_active=True` و`starts_at`/`ends_at` يحصرانها زمنياً — **بلا `__date` إطلاقاً** (جداول المناطق الزمنية الفارغة في MySQL تُعيده صفر صفوفٍ بلا خطأ، `core/date_ranges.py`؛ المقارنة على `datetime` مباشرة). لا مهمّة تُطفئ `discount_percent` عند الانقضاء — الحملة تسكت وحدها بشرط التاريخ، وإعادةُ تشغيلها تعديلُ تاريخٍ لا إعادةَ إدخال.

أعلى نسبة خصمٍ ساريةٍ تُحسَب بـ`Max("collection_items__collection__discount_percent", filter=Q(...))` — ضمٌّ واحد لا استعلامٌ لكل صف — ثم `Least(Coalesce(sale_price, price), Coalesce(campaign_price, price))` يختار الأصغر (تعويض الغائب بالسعر الأساس عبر `Coalesce` كي لا يُبطل `LEAST` الناتج كلّه بـ`NULL` حين يغيب أحد الطرفين؛ هذا التعويض نفسه هو ما يضمن ألّا يتجاوز الناتج السعر الأساس أبداً — **الحارس الأوّل**: لا يُعرَض خصمٌ إلا إذا كان أصغر من `price` فعلاً). عند تساوي المصدرين تفوز الحملة منطقياً — بلا أثرٍ ملحوظ في الناتج لأن القيمتين متساويتان أصلاً. حملةٌ ضدّ حملة: النسبة الأكبر تحسم وحدها، والأولوية والتاريخ الأحدث لا يدخلان الحساب إلا عند تساوي النسب (والسعر الناتج متطابقٌ حينها بالضرورة).

`store/serializers.py` (`StoreProductSerializer`) يشتقّ `original_price`/`discount_percent` من `obj.price` (الأساس) و`obj.effective_price` (الفعليّ المحسوب في SQL، على الكائن نفسه بلا استعلامٍ إضافي): كلاهما `null` صراحةً إلا حين يكون الفعليّ أصغر من الأساس فعلاً — نفس الحارس الأوّل، فيحمي حتى من بياناتٍ قديمة (`sale_price` أعلى من `price`). `discount_percent` صحيحٌ مقرَّبٌ **للشارة فقط**؛ `price` المُعاد لا يُقرَّب في الخادم.

**حرّاسُ الحفظ** (نمط `StoreCategory._reject_third_level`: دالّةٌ واحدةٌ من `clean()` و`save()` معاً، لأن جانغو لا ينادي `clean()` من `save()` تلقائياً): `StoreProduct._reject_non_positive_sale_price` يرفض `sale_price ≤ 0`، و`StoreCollection._reject_price_killing_discount` يرفض `discount_percent ≥ 100` — كلاهما «خصمٌ يُنزل السعر إلى صفرٍ أو دونه» فيرمي `ValidationError` صريحاً بدل قصّه صامتاً إلى صفر.

**العتبة القديمة (`min_stock_level`) وحقلا السعر القديمان (`online_price`/`sale_price` على `inventory.Product`) بقيا كما هما** للاستهلاك الداخلي (الفوترة، شاشات المخزون) — لم يعودا مصدر الحمولة العامة منذ م٢.

**العملة على بطاقة الشركة لا على المنتج** (`StoreProfileSerializer.currency`): كل أسعار المتجر بعملة الشركة الواحدة (`TenantSettings.currency`)، والقيمة رمزُها («₪») وإلا رمزها الدولي («JOD»)، و`null` حين لا عملة مضبوطة — لا نخترع افتراضاً، والواجهة تعرض الرقم عارياً حينها.
المنصة متعدّدة العملات والزائر خارج أي جلسة، فرقمٌ بلا عملة على صفحة عامة يُقرأ شيكلاً أو دولاراً حسب مَن يقرأ.

**التصفية بالتصنيف تقبل الاسم كما تقبل المعرّف** (`StoreProductListView._filtered`، عبر M2M `categories`، مع `distinct()` كي لا يتكرّر صفّ منتجٍ في أكثر من فئة): تاريخياً الحمولة العامة نشرت `category_name` وحده، والاسم بقي مقبولاً للتوافق؛ ومنذ م٢ `categories[].id` منشورٌ أيضاً فالمعرّف صار خياراً كاملاً بدوره.
الاسم لا يفتح باباً: الاستعلام مفلتر بالشركة قبل هذا الشرط، فاسم تصنيف شركة أخرى يعطي فراغاً لا تسريباً (`test_a_category_name_from_another_tenant_returns_nothing`).

## الفلترةُ بعدّادات (THA-166 م٤)

**ردٌّ واحدٌ لا نقطةٌ ثانية**: `GET /api/store/<slug>/products/` يردّ
`{count, next, previous, results, facets, price_range}` — `facets` و
`price_range` إضافتان على عقد الترقيم القائم لا نقطة `/facets/` منفصلة (بحث
#157: الفصلُ يُضاعف الرحلات وينتج أعداداً لا تطابق المعروض؛ نقطة WooCommerce
المنفصلة نتاجُ معماريّة ووردبريس لا اختيارِ تصميم).

**العدّاداتُ سياقيّةٌ بالاستثناء الانفصاليّ** (`store/views.py`،
`StoreProductListView._filtered(exclude_axis=…)`): كلُّ محورٍ يُعدُّ بعد
إسقاط فلترِ *نفسِه* وحدَه، مع إبقاء بقيّة المحاور. مثال: زبونٌ اختار الماركة
«سامسونج» والفئة «هواتف» — عدّاداتُ **الفئات** تُحسَب داخل «سامسونج» (فلترُ
الماركة يبقى، وفلترُ الفئة يسقط)، وعدّاداتُ **الماركات** تُحسَب داخل «هواتف»
(والعكس) — فتبقى بقيّةُ الماركات ظاهرةً بأعدادها ويستطيع الزبون إضافةَ
ماركةٍ ثانية. حُسبت لو بعد تطبيق فلتر الماركة لظهرت «سامسونج» وحدها بعددٍ
يساوي النتائج، ولانغلق المحورُ على نفسه — وهذا بالضبط ما تثبته
`store/tests/test_store_facets.py::DisjunctiveExceptionTest` في الاتجاهين.

⚠️ **لازمةٌ حتميّة: مجموعُ عدّاداتِ محورٍ انفصاليٍّ قد يتجاوز `count`.**
`categories` علاقةُ M2M — منتجٌ في فئتين يُحسَب في عدّاد كلٍّ منهما، فمجموعُ
عدّادات الفئات قد يفوق عدد النتائج الفعليّ. **هذا ليس عطباً** — هو نفسُ نمط
WooCommerce وAlgolia الموثَّق في بحث #157، ومُثبَتٌ اختباراً
(`FacetSumExceedsCountTest`) لا مُصحَّحاً.

**المحاور الأربعة:**
- **الفئات** — شجريّةٌ بمستويين، **والعدُّ شاملٌ للأبناء**: أبٌ بلا منتجٍ
  مباشرٍ وتحته ابنٌ بعشرة ⇒ الأبُ يُظهر عشرة لا صفراً (`_category_facet`).
  **العدُّ عددُ منتجاتٍ متمايزة لا مجموع عدّادين** — منتجٌ موسومٌ بالأب
  وابنه معاً (`M2M`، استعمالٌ طبيعيٌّ لا شاذّ) كان يُحسَب مرّتين فيَعِد الأبُ
  بعددٍ أكبر من منتجاته الفعليّة قبل تصحيحٍ بعد المراجعة (سطرٌ منفصلٌ عن
  لازمة تجاوز المجموع أدناه: تلك عن محاورَ *مختلفة*، وهذه عن قيمةٍ واحدةٍ
  تكذب على نفسها). التنفيذ: استعلامٌ واحد يقرأ أزواج (منتج، فئة) خاماً، ثم
  اتحادُ مجموعتَي معرّفات المنتجات (الأب + كل ابن) في بايثون — لا `SUM` على
  عدّين مستقلّين. استعلامان ثابتان بصرف النظر عن عدد الفئات أو المنتجات
  (الأزواج + قراءةُ شجرة الفئات كاملةً)، ومُثبَتٌ اختباراً
  (`TreeCategoryCountTest.test_product_tagged_with_both_parent_and_child_is_not_double_counted`).
- **الماركات** — من `StoreBrand`، تجميعٌ واحد.
- **الرايات** (`flags{on_sale, is_new, in_stock}`):
  - `on_sale` — خصمٌ سارٍ فعلاً: `effective_price < price` (منتجٍ مفردٍ أو حملة، نفس منطق `published_products`).
  - `in_stock` — **`stock_state == 'in_stock'` وحدَها دون `preorder`**: من يفلتر بالتوفّر يقصد «أقدر آخذه هلّق»، ومن أراد الطلب المسبق يجده بلا هذا الفلتر.
  - `is_new` — `created_at >= now() - new_product_days` أيام. **بلا `__date` إطلاقاً** (`core/date_ranges.py`: جداول المناطق الزمنية الفارغة في MySQL تُعيده صفر صفوفٍ بلا خطأ) — المقارنة على `datetime` مباشرة. `StoreSettings.new_product_days` (هجرة `0010`، افتراضه **٣٠**) قرارٌ لكل شركة — لا تعريف قياسيّ لهذه الراية عند أيّ منصّة (بحث #157).
- **مدى السعر** (`price_range: {min, max}`) — حدّان مستمرّان `min_price`/`max_price`، **لا شرائحُ جاهزة** (إجماعٌ ثلاثيٌّ في #157)، على `effective_price` (بعد الخصم) لا `price` الخام. **سياقيٌّ باستثناء فلتر السعر نفسِه** — قرارُ استعمالٍ لا سابقة (`_price_range_facet`): لو حُسب شاملاً لاختيار الزبون لانطبق المنزلقُ على قبضته ولما استطاع توسيعَه ثانيةً. **يغيب من الحمولة كلّياً** حين `show_prices=false` (ومعاملا السعر يُهمَلان تماماً حينها، `_apply_price_range`).

**تعدّدُ الاختيار** — `brand=1,5` و`category=3,9` بفواصل: **OR داخل المحور، AND
بين المحاور** (إجماعٌ ثلاثيٌّ في #157). **المعرّفاتُ لا الأسماء** طريق
التعدّد؛ الاسمُ المفرد (`brand=سامسونج`) يبقى مقبولاً للتوافق الخلفيّ
(الواجهة الحاليّة تستعمله ولن تُعاد كتابتها إلا في المرحلة الأخيرة).
`_apply_category` تستعمل `Q(categories__id__in=…)`، والقائمةُ النهائية تُغلَق
بـ`.distinct()` (M2M يكرّر الصفّ)، بينما العدّاداتُ تستعمل
`Count('id', distinct=True)` بدل `.distinct()` على الاستعلام — نفس نمط
WooCommerce المُسنَد في #157.

**العدّاداتُ تعود عند `page == 1` فقط** (أو بلا `page=` أصلاً) **وتُحذَف من
الصفحات التالية** — التصفّحُ لا يغيّرها، وحسابُها في كلّ صفحةٍ إهدارُ تجميعٍ
محضٌ على مسارٍ عامٍّ مخنوق (`store_public`). `include_facets=1` يفتحها
صراحةً لمن وصل مباشرةً إلى صفحةٍ تالية.

**الكاش** — `StoreProductListView.CACHE_PARAMS` كسبت ستّة معاملات:
`min_price`, `max_price`, `on_sale`, `is_new`, `in_stock`, `include_facets`.
**كل معاملٍ يقرؤه `_filtered` يجب أن يدخل هذه القائمة** وإلا خُدِم قديماً
بصمتٍ من الكاش — حارسٌ آليٌّ في `test_store_facets.py::CacheFingerprintGuardTest`
(`test_every_filtered_read_param_is_covered_by_cache_params`) يقارن مجموعة
المعاملات المقروءة فعلياً بـ`CACHE_PARAMS` بدل تعداد الحالات يدوياً، على غرار
قائمة `test_public_leakage.py` البيضاء.

**الأداء** — SQL يكفي بمقاس هذا المتجر: لا محرّك بحثٍ ولا Celery (#157).
عددُ استعلامات بناء العدّادات **ثابتٌ** بصرف النظر عن عدد المنتجات أو
الفئات أو الماركات (`FacetQueryBudgetTest`) — لا استعلامَ لكل فئةٍ ولا لكل
صفّ (درسا ٣٥٠١ استعلام و١٧ ثانية موثَّقان في المستودع). الأساس ارتفع من ٦
إلى ١٣ استعلاماً على الصفحة الأولى (`test_store_catalog_public.py::QueryBudgetTest`)
— سبعةٌ إضافيةٌ لبناء `facets`/`price_range`.

## الصور
روابط Cloudinary عامة أصلاً لمن يملك الرابط. `core/media_views.py` (`media_upload`) يخدم **الرفع** لا التسليم، فلا توكن هنا ولا حاجة إليه.
المصدر صفوف `SystemAttachment(related_table='products')`، والحصر **إيجابي** بـ`PRODUCT_IMAGE_TYPES`: «كل ما ليس داتا شيت» كان سينشر أي مرفق يُضاف مستقبلاً على الملأ.

## الخنق وعدّاد المشاهدات
`throttle_scope = "store_public"` على النقاط الثلاث، بمعدل من البيئة `THROTTLE_RATE_STORE` افتراضه `120/min`، **فوق** `AnonRateThrottle` العام.
الحدّان يعملان معاً و**الأضيق هو النافذ** — أي `anon` (60/دقيقة) اليوم؛ فالمقبض الجديد يضيّق على المتجر وحده بلا لمس بقية المنصة، ويصير هو النافذ إن وُسِّع `anon`.
درس P0-8: نقطة عامة بلا سقف مخصّص تُشبع الـworkers الثلاثة.

**الترقيم إلزامي** على القائمة (`EnforcedPageNumberPagination`) خلافاً لافتراضي المشروع الاختياري، فالرد **دائماً** `{count, next, previous, results}` — هذا هو العقد الذي يستهلكه ST-2.
السبب: كتالوج المنتجات جدولٌ ينمو بلا حدّ (حالة «الفئة أ» في `core/pagination.py`) والطلب هنا **مجهول**؛ بلا إلزام يصير طلبٌ واحد بـ120 بايت رداً بعدّة ميغابايت مضروباً في سقف الخنق — مُضخِّم إساءة من نفس عائلة درس P0-8. و`page_size` مسقوف بـ`max_page_size`.

قائمة المنتجات تُكاش 60 ثانية بمفتاح يحمل الـslug (`store:<slug>:products:<بصمة المعاملات>`) — عزل الشركة قانون المشروع ويسري على الكاش كما يسري على الاستعلام.
صفحة المنتج **لا** تُكاش: هي التي تكتب العدّاد.

`store/models.py` (`StoreProductView`) — تجميع يومي `(tenant, product, view_date, count)` يكتبه `store/views.py` (`_record_view`) بـ`F('count') + 1` ذرّي، **عند فتح صفحة منتج فقط** لا مع كل طلب قائمة.
لماذا جدول جانبي لا عمود على `Product`: صفّ المنتج يعيش في قلب الـERP، وكتابةُ زائرٍ مجهول عليه تقفل صفّاً ساخناً وتُدخِل مسار كتابة غير مصادَق عليه إلى جدول تحرسه قواعد المخزون.

## الواجهة العامة (ST-2)
شاشات المتجر تعيش في `frontend_v2/components/store/` وتُوجَّه من `frontend_v2/index.tsx` **خارج `AuthProvider`/`CompanyProvider`**: زائرٌ بلا جلسة لا ينتظر إقلاع مساحة عمل لا تخصّه.
ثلاثة مسارات: `/store` (صفحة تعريف، أو تحويل إلى `VITE_DEFAULT_STORE_SLUG` إن ضُبط) · `/store/<slug>` (الشبكة) · `/store/<slug>/p/<id>` (المنتج).
الشاشات نفسها لا تعرف المسارات ولا تستورد موجِّه المسارات — محوِّلات المسار في `index.tsx` تمرّر الـslug والمعرّف كـprops.
العميل `frontend_v2/services/storeApi.ts` فوق `restApi.ts` (طلبات GET عامة)، وروابط واتساب والنسخ في `frontend_v2/utils/storeLinks.ts` (رقم غير دولي ⇒ لا رابط `wa.me` بل زر اتصال، فلا يُخمَّن مفتاح دولة).

## شاشة «متجري» ومفتاح `store.manage` (ST-3)
`frontend_v2/components/settings/StoreSettingsPage.tsx` — الشاشة المصادَق عليها التي يفتح منها المدير متجره ويقرّر ما يُعرض فيه، على المسار `/store-settings` داخل التطبيق (لا تحت `/store` العام).
تعيش في `components/settings/` لا في `components/store/`: ذاك المجلد خاصيّتُه أن **كل ما فيه عام**، وشاشةٌ مصادَق عليها بينه تُفقده تلك الخاصية على أول قارئ.

**المفتاح `store.manage`** في كتالوج `core/access.py` ضمن مجموعة «الإدارة والإعدادات». المدير يملكه ضمناً (`"*"`) ويمنحه لغيره من شاشة الصلاحيات القائمة، ولا يملكه أي دور آخر افتراضياً.
**مستقل عن `admin.settings.manage` عمداً**: مَن يضبط عنوان الشركة وشعارها لا يفتح بذلك واجهةً تعرض أسعار الشركة لكل زائر — قراران تجاريان مختلفان. الحارس مُثبَت في `store/tests/test_store_slug.py` من الطرفين: مَن يملك إعدادات الشركة وحدها يُردّ 403، ومَن يُمنح `store.manage` بتجاوزٍ في شركته يُقبَل 200 (وهذا ما يثبت أن المفتاح في الكتالوج فعلاً، إذ `core/access.py` (`_apply`) يتجاهل أي مفتاح خارجه).

**النشر بلا نقطة خادمية جديدة**: `is_for_sale_online` و`online_price` و`online_description` حقولٌ قائمة على `Product` تقبلها `inventory/views.py` (`ProductViewSet`) بـPATCH منذ ما قبل المتجر — الشاشة واجهةٌ فوقها، بلا سيريالايزر ثانٍ للنشر.
أُضيف فلتر `?is_for_sale_online=true|false` على قائمة المنتجات (`ProductViewSet.get_queryset`) وحده: بدونه كانت الشاشة تُحمّل الكتالوج كاملاً وتصفّيه في المتصفح لتعرض المنشور أو تعدّه. قيمةٌ غير مفهومة لا تُصفّي بصمت.

**مراجعة أول تفعيل** — أهم سطر في الشاشة: `is_for_sale_online` **ليس علماً جديداً**؛ هو في المخطط منذ ما قبل المتجر، ورفيقه `online_price` تقرؤه الفوترة (`SalesInvoiceEditor.tsx`) سعراً افتراضياً حين يخلو كرت المنتج من سعر بيع. فقد تكون الشركة علّمت العلم على منتجات لسببٍ قديم بلا أي نيّة نشر، وتلك المنتجات تصير علنيةً **لحظةَ** اختيار المعرّف — يتغيّر معنى العلم تحتها بصمت.
لذلك أول فتحٍ للمتجر يعرض عدد تلك المنتجات وأسماءها ويستأذن (`useConfirm`)، و«راجع القائمة أولاً» يُبقي المتجر مقفلاً ويفتح الجدول على المعروضة كي تُلغى قبل الفتح. تغيير معرّفٍ قائم يحذّر أن الروابط القديمة تنكسر، والإقفال يحذّر أن الصفحة تصير «غير موجودة» — ولا واحدة منها افتراضٌ صامت.

✅ **الفجوةُ أُغلقت (THA-166 م٣)**: `StoreSettingsPage.tsx` وعقدُ `storeAdminApi.ts` أُعيد بناؤهما بالكامل ليكتبا على `StoreProduct` مباشرة (لا `inventory.Product.is_for_sale_online` بعد اليوم) — فمنتجٌ يُنشأ أو يُنشَر من قسم «المنتجات» في هذه الشاشة يظهر فعلاً في المتجر العام فور الحفظ، لأن الشاشة والسطح العام يقرآن ويكتبان الجدول نفسه. القسمُ الآن يعرض حقول `StoreProduct` كما هي: الاسمان، الماركة (قائمةٌ منسدلةٌ من `StoreBrand`)، الفئات (اختيارٌ متعدّد M2M)، الوحدة، السعر، سعر التخفيض (مبلغٌ مطلق موصوفٌ صراحةً في الواجهة)، حالةُ التوفّر الثلاثية (`in_stock`/`out_of_stock`/`preorder` — مُسمّاةٌ «متوفر»/«نفد»/«بالطلب»، ولا تُسمّى «الرصيد» أبداً)، الوصف، النشر (`is_active`)، والترتيب. إنشاءُ ماركةٍ أو فئةٍ جديدةٍ من داخل نموذج المنتج (نمط `quick-create-returns-id-to-caller`) يعيد المعرّف فيُختار تلقائياً بلا فقدان ما كُتب في نموذج المنتج الأمّ.

**«استيراد من الأصناف» — الجسر الوحيد المسموح بين المخزون والمتجر**: `POST /api/store/admin/products/import-from-inventory/` (إجراءٌ على `StoreProductAdminViewSet`) ينسخ صنفاً مخزنياً إلى `StoreProduct` **مرّةً واحدةً بلا علاقةٍ ولا مزامنة لاحقة** — الاسم والماركة (توحيدٌ غير حسّاس لحالة الأحرف، نفس منطق هجرة `0006`) والوحدة والوصف، والسعر بقاعدة هجرة `0006` حرفياً (`online_price` الموجب يغلب، وإلا `sale_price`). يملأ `imported_from_product_id`، يتخطّى ما استُورد من قبل ويُبلّغ عن العدد في كلٍّ (`{"imported_count", "skipped_count", "message"}`)، مفلترٌ بالشركة، محروسٌ بـ`store.manage` (نفس حراسة الـViewSet)، ولا يكتب حرفاً في `inventory.Product`. الواجهة: `StoreImportFromInventoryModal.tsx` — منتقي أصنافٍ متعدّد الاختيار عبر `listPickerProducts`، ونتيجة الاستيراد نصٌّ عبر `useToast` (لا `alert`/`confirm` المتصفّح).

**لا نسخَ للفئات عند الاستيراد — قرارٌ مقصود** (خلافاً لهجرة `0006` التي سطّحت فئات المخزون **مرّةً واحدة** عند الانفصال): شجرةُ فئات المتجر صارت ملكَ التاجر بعد م٢، وإعادةُ اشتقاق فئاتٍ تسويقيةٍ من فئاتٍ محاسبيةٍ عند **كل** استيرادٍ تُعيد ربط الشجرتين وتُولّد فئاتٍ لم يطلبها أحد. المستورَد يصل بلا فئة، والتاجر يصنّفه بنفسه من شجرة `/store-categories` — ونصٌّ صريحٌ بهذا في نافذة الاستيراد كي لا يُقرأ سلوكٌ مقصودٌ عطباً. **سقفٌ صريح** على حجم دفعة الاستيراد (`StoreProductAdminViewSet.IMPORT_MAX_IDS = 500`، 400 برسالةٍ تذكر الحدّ والعدد المُرسَل) والحلقةُ داخل `transaction.atomic()` (الوحدةُ الطلبُ كلُّه — فشلٌ في المنتصف لا يترك دفعةً جزئية، والنقطة قابلةٌ لإعادة التشغيل أصلاً فتخطّي المستورد سلفاً يلتقط الباقي). `stock_state` يُشتقّ بنفس منطق الهجرة حرفياً (`preorder` إن كان `allow_preorder` وإلا `in_stock`) — وإلا هبط المنتج نفسُه بحالتين مختلفتين حسب طريق وصوله.

**شجرة فئات المتجر شاشةٌ مستقلّة** — `StoreCategoriesPage.tsx` على مسار `/store-categories` (مفتاح `store.manage` نفسه)، لا قسمٌ داخل `StoreSettingsPage.tsx`: قرارُ مواصفة #166 الصريح أن محرِّر شجرةٍ داخل ملفٍّ ضخمٍ أصلاً يجعله غير قابلٍ للصيانة. عرضُ الشجرة بمستويين، إنشاءٌ وتعديلٌ وحذف، `sort_order`/`is_active`/`image_url`. المنعُ الواجهيّ للمستوى الثالث (منتقي الأب لا يعرض إلا فئاتٍ بلا أبٍ) مكمَّلٌ بعرض خطأ الخادم الصريح عند وقوعه (`StoreCategory._reject_third_level` يعود 400). **تعطيلُ الفئة يُخفيها من تصفّح المتجر ولا يُخفي منتجاتِها** — نصٌّ صريحٌ في الشاشة كي لا يظنّ التاجر أنه أخفى بضاعةً وهي معروضة.

| الملف | الغرض |
|---|---|
| `frontend_v2/components/settings/StoreSettingsPage.tsx` | الشاشة: الحالة والرابط ونسخُه + جدول المنتجات على عقد `StoreProduct` |
| `frontend_v2/components/settings/StoreCategoriesPage.tsx` | شجرة فئات المتجر — شاشةٌ مستقلّة (م٣) |
| `frontend_v2/components/settings/StoreImportFromInventoryModal.tsx` | منتقي «استيراد من الأصناف» متعدّد الاختيار (م٣) |
| `frontend_v2/services/storeAdminApi.ts` | نداءاتها المصادَق عليها على عقد `StoreProduct`/`StoreBrand`/`StoreCategory` — منفصلة عن `storeApi.ts` العام |
| `frontend_v2/utils/storeLinks.ts` (`storeHomeUrl`) | بناء الرابط المنسوخ — نفس باني مسارات المتجر العام |
| `store/tests/test_store_import_from_inventory.py` | نقطة الاستيراد: نسخٌ صحيح، تخطّي المستورد سلفاً، عزل الشركة، صفر صفٍّ متغيّر في `inventory.Product` (م٣) |
| `frontend_v2/e2e/store-catalog-publish-journey.spec.ts` | الرحلة الحقيقية: إنشاءٌ من اللوحة ← ظهورٌ في المتجر العام (م٣) |

## المظهر والحملات والسلة ولوحة الإدارة (ST-5)

**المظهر والهوية** — `store/models.py` (`StoreSettings`): صفٌّ واحد لكل شركة (`OneToOne`) يحمل الترويسة والشريط الإعلاني والألوان والخلفية وروابط التواصل ومفتاح السلة.
يُقرأ في السطح العام ضمن بطاقة الشركة (`StoreProfileView`)، ويُكتب من `StoreSettingsAdminView` بصلاحية `store.manage`.
غيابه ليس خطأً: كل قراءة تسقط إلى قيمة افتراضية معلَنة، فمتجرٌ لم يُضبط مظهره يعمل بمظهر المنصة.

⚠️ **الموصول فعلاً من هذه الحقول أقلّ ممّا يوحي به النموذج** (مُتحقَّق منه في 2026-08-19):
| الحقل | متحكّم في «متجري» | تقرؤه شاشات المتجر |
|---|---|---|
| `background_image_url` · `background_style` | ✅ | ✅ `StorefrontPage` · `StoreProductPage` |
| `catalog_mode_default` | ❌ | ✅ `StorefrontPage` |
| `show_prices` | ❌ (يُضاف في EXEC-5) | ✅ الخادم يحجب السعر من الحمولة |
| `primary_color` · `accent_color` · `background_color` · `theme_preset` · `allow_cart` | ❌ | ❌ |
| `new_product_days` (م٤) | ❌ (لا واجهةَ ضبطٍ بعد) | لا تقرؤه الواجهة مباشرةً — يقود فلتر `is_new` **خادميّاً** في `StoreProductListView` |
الخمسة الأخيرة (السطر قبل الأخير) **حقول محجوزة بلا أثر**: تُحفظ وتُقرأ عبر الـAPI ولا تغيّر بكسلاً واحداً. `allow_cart=false` **لا يُخفي السلة**. تُوصَل في THA-424.

**صور المتجر** — `store/models.py` (`StoreProductImage`): صور تسويقية مستقلة عن مرفقات المنتج، مرتَّبة، بغلافٍ واحد، وبنصٍّ إعلاني فوق الغلاف (`cover_overlay`).
الأولوية لها؛ ومَن لا يملك صورة متجر يسقط إلى `SystemAttachment` كما قبل — `store/views.py` (`_store_media_context`) يجمع الاثنتين لصفحة كاملة باستعلامين لا باستعلام لكل منتج.

**الحملات** — `StoreCollection` + `StoreCollectionItem`: مجموعة منتجات بمعرّف نصّي فريد داخل الشركة، لها صفحة هبوط عامة ومنتج مميّز.
**المنتج المميّز يمرّ من `published_products` لا من الـFK مباشرةً** (`StoreCollectionDetailView`): قراءته من `collection.featured_product` تنشر منتجاً غير منشور أو منتج شركة أخرى، وتُسقط `price` و`availability` لأن حقلَيهما محسوبان في الاستعلام لا على النموذج. مُثبَت في `store/tests/test_store_admin_scoping.py`.

**السلة** — في المتصفح وحده: `frontend_v2/contexts/StoreCartContext.tsx` يحفظ المنتجات في `localStorage` بمفتاح يحمل الـslug، ويبني منها رسالة واتساب.
**لا طلب ولا فاتورة ولا حركة مخزون**: المتجر ما زال قراءةً فقط على الخادم، والسلة تنتهي عند رسالةٍ يرسلها الزبون بنفسه.

**منتجاتٌ خاصة بالمتجر (إرثٌ سابقٌ على THA-166)** — `Product.is_store_only` (هجرة `inventory/0019`) و`Product.allow_preorder` (هجرة `inventory/0018`) حقلان على `inventory.Product` نفسه، **لم تعد لوحة إدارة المتجر تكتبهما منذ م٢** (كانت تفعل قبل التصحيح).
`inventory/views.py` (`ProductViewSet.get_queryset`) لا يزال يستبعد `is_store_only` افتراضياً من الكتالوج المخزني ومحدّدات الفواتير — آليةٌ مستقلّةٌ بقيت كما هي، بلا صلةٍ بكتالوج المتجر المستقلّ.

**عزل الشركات في نقاط الإدارة** — `store/serializers.py` (`TenantScopedPrimaryKeyRelatedField`): كل مرجع كتابةٍ في نقاط `/api/store/admin/` يُقيَّد بشركة الطلب — `store_product` و`collection` و`featured_product` و`featured_store_product` و`brand` و`categories` و`parent` (فئة).
تقييد `get_queryset` وحده يحجب سجلّ الغير عن القائمة ولا يمنع ربطه بمعرّفه في جسم الطلب — وهو ما كان يسرّب اسم منتج شركةٍ أخرى وسعره عبر عنصر حملة.

**لا حصر حقولٍ على `StoreProductAdminSerializer`** (THA-166 م٢، يُلغي `STORE_EDITABLE_ON_INVENTORY` القديم): كل حقول `StoreProduct` قابلةٌ للتعديل من اللوحة — لا تمييز «مخزني/متجر خالص» بعد اليوم لأن كل صفٍّ في هذا الجدول **ملكُ اللوحة كاملاً بالتعريف** (يُنسَخ مرّةً من `inventory.Product` إن وُجد ثم يتباعدان، `imported_from_product_id` رقمٌ مجرَّدٌ لا يعيد فتح تلك الصلة). حرّاسا الحفظ (سعرٌ يُنزل السعر إلى صفرٍ أو دونه) هما القيد الوحيد المتبقّي، ويعودان **400** عبر `_ConvertsModelValidationErrors` لا 500.

**الطلب المسبق قرارُ صاحب المتجر** — `stock_state` يبدأ `in_stock` افتراضياً (`StoreProduct.STOCK_IN_STOCK`) ولا يُفرض `preorder` على أي منتجٍ جديد؛ التاجر يختاره صراحةً عند الإنشاء أو التعديل.

**لا رمز منتج (`sku`) على `StoreProduct`** — الحقل غير موجودٍ على هذا النموذج أصلاً (كان تسلسلياً `ST-{n:06d}` على `inventory.Product` في المسار القديم، عبر `TenantBook.get_next_number`؛ ذاك المسار لم يعد مستعمَلاً من لوحة المتجر). `slug` هو المعرّف النصّي الوحيد، ويُولَّد تلقائياً (`store/slugs.py`) ولا يُكتب من الـAPI (`read_only`).

**حذف منتج المتجر** — `StoreProductAdminViewSet` بلا `perform_destroy` مخصّص: حذفٌ مباشر (`204`) دائماً. **لا `ProtectedError` ممكنة على `StoreProduct`**: كل توابعه (`StoreProductImage`، `StoreProductView`، `StoreCollectionItem`) `CASCADE`، ولا صلة له بحركةٍ مخزنية أو فاتورة — حارسُ الـ409/403 القديم (`ProductHasHistoryError`، تمييز `is_store_only`) كان خاصّاً بمسار `inventory.Product` ولا معنى له هنا.

## إظهار/إخفاء الأسعار — `StoreSettings.show_prices`

مفتاحٌ واحد على مستوى المتجر (هجرة `store/0004`، افتراضيه `True` فلا يفقد متجرٌ
قائم أسعاره بالترقية). سببه أن `sale_price` حقلٌ **تشغيلي** تقرؤه الفوترة، ووجودُه
على كرت المنتج ليس إذناً بإعلانه للعموم — متاجر الجملة تعرض الكتالوج وتترك السعر
لمحادثة.

**الحجب في `published_products` وحدها** (`store/views.py`): حين يكون المفتاح
مطفأً يُستبدل حساب الخصم كلّه بـ`.annotate(effective_price=_hidden_price_expression())`
(`Value(None)`) مع `.defer("price", "sale_price")` — فعمودا السعر **لا يُقرآن من
القاعدة أصلاً**، ولا يُبنى ضمّ الحملات (`_active_campaign_discount_percent`) عبثاً.
وبما أن المسارات الثلاثة (القائمة · صفحة المنتج · صفحة الحملة) كلها تمرّ من هذه
الدالة، يغطّيها الحجب بالبناء لا بثلاثة شروط تُنسى إحداها.

**المفاتيح `price`/`original_price`/`discount_percent` تبقى في العقد وقيمتها
`null` معاً** (THA-166 م٢ — كانت `price` وحدها قبل الخصم) — لا تغيير في
`PUBLIC_WHITELIST`، و`StorePrice` في الواجهة تعرض «السعر عند الطلب» تلقائياً
عند `null` (مكوّنٌ قائم، لم يُخترع ثانٍ).

**البروفايل العام يُعلن الحالة** (`show_prices` في `PROFILE_WHITELIST`) كي تُخفي
الواجهة الفرز بالسعر ومبالغ السلة.

**الحارس:** `store/tests/test_price_visibility.py` — سعرٌ مزروع (`StoreProduct.price=99`)
ومسحٌ تكراري لكل حمولة عامة بحثاً عن تمثيلاته. إخفاء السعر **لا يُخفي المنتجات**:
الكتالوج يبقى كاملاً بحالة توفّره.

## كتالوجُ المتجر المستقلّ (THA-166) — م١ نماذجٌ وهجرة، م٢ القراءةُ العامة والخصم

**قرار مالكٍ حاكم: كتالوجُ المتجر مستقلٌّ تماماً عن `inventory.Product` — لا مخزونَ ولا محاسبةَ أبداً.**
المرحلةُ الأولى من مواصفة #166 كانت مضيفةً محضة: نماذجُ جديدة وهجرةُ نسخٍ بلا قارئ. **المرحلة الثانية (م٢) حوّلت `published_products` والكتابةَ الإداريةَ معاً** — القراءةُ العامة والكتابةُ الإدارية تنتقلان دائماً معاً، لا مساراً يقرأ من جدولٍ ويكتب في آخر (تصحيحٌ لتقسيمٍ أوّليٍّ فصل بينهما سهواً). السطحُ العامّ بمساراته الثلاثة (القائمة، المنتج، صفحة الحملة) يقرأ الكتالوج المستقلّ، والخصمُ (منتجٍ مفردٍ أو حملة) ظاهرٌ فيه (انظر «التوفّر حالة لا رقم، والسعر خصمٌ محسوبٌ في SQL» أعلاه)، ولوحة الإدارة (`/api/store/admin/products|brands|categories/`) تكتب على `StoreProduct`/`StoreBrand`/`StoreCategory` حصراً — لا صلة لها بـ`inventory.Product` بعد اليوم.

**حاجزٌ أُزيل قبل القراءة**: `StoreProductImage.product`/`StoreProductView.product`/`StoreCollectionItem.product` كانت `ForeignKey` **بلا `null=True`** — فمنتجُ متجرٍ من الصفر (بلا صنفٍ مخزونٍ خلفه) لم يكن يقبل صورةً ولا مشاهدةً ولا عضويّة حملة. هجرة `store/migrations/0007_m2_product_fk_nullable.py` تُسقط قيد `NOT NULL` وحده — **بلا حذفٍ ولا مسٍّ لبيانات الصفوف القائمة**.

**`StoreCollection.featured_store_product`** — FK جديدٌ إلى `StoreProduct` (`null=True`, `SET_NULL`، هجرة `0008`) هو المرساةُ الحيّة التي يقرؤها العرض العام (`StoreCollectionDetailView`) الآن بمطابقة `pk` مباشرة. **`featured_product` القديم (FK إلى `inventory.Product`) بقي بلا حذفٍ ولا كتابةٍ فعلية جديدة إليه** — فضاء معرّفاته منفصلٌ تماماً عن `StoreProduct.id`، ومطابقتُه مباشرةً كانت لتصادف صنفاً آخر أو لا شيء. هجرةُ بياناتٍ (`0009_populate_featured_store_product.py`) ملأت الحقل الجديد للحملات القائمة عبر `imported_from_product_id` — **مُضيفةٌ محضة** ولا تمسّ `featured_product`.

`store/models.py`:
- **`StoreProduct`** — الصفّ المستقلّ: `name_ar`/`name_en`/`slug` (فريدٌ لكل شركة، يُولَّد من `store/slugs.py` (`build_unique_slug`) عند الحفظ إن تُرك فارغاً)، `brand`→`StoreBrand`، `categories` M2M→`StoreCategory`، `unit` **نصٌّ حرّ** (لا FK إلى `inventory.UnitOfMeasure`)، `price`/`sale_price` قابلان للفراغ، `stock_state` (`in_stock`/`out_of_stock`/`preorder`) **إعلانٌ من التاجر لا رقمٌ محسوب**، و`imported_from_product_id` — **رقمٌ مجرَّدٌ عمداً لا `ForeignKey`**: مفتاحٌ أجنبيٌّ هنا يعيد بناء الاقتران الذي قطعه قرارُ المالك.
- **`StoreBrand(tenant, name, sort_order, is_active)`** — ماركةٌ جدولٌ لا نصٌّ حرّ، فرادة `(tenant, name)`.
- **`StoreCategory(tenant, name, parent→self, slug, sort_order, is_active, image_url)`** — شجرةٌ **مستقلّةٌ تماماً** عن `inventory.ProductCategory` المحاسبية، فرادة `(tenant, slug)`. **العمقُ محدودٌ بمستويين بالتحقّق لا بالبنية** (لا حفيد، ولا فئة أباً لنفسها، **ولا إسنادُ أبٍ لفئةٍ لها أبناء** — الحالة الثالثة تنتج نفس انتهاك العمق من الجهة المعاكسة) — رفعُ السقف لاحقاً تغييرُ سطرِ تحقّقٍ لا هجرةَ بنية. الحارسُ (`_reject_third_level`) موصولٌ بـ`clean()` **و`save()` معاً** عمداً: جانغو لا ينادي `clean()` من `save()` تلقائياً، فـ`objects.create()` كان سيتجاوزه بصمت لولا هذا الربط الصريح. `bulk_create` يبقى خارج المسار عمداً (تعتمد عليه الهجرة).
- **`StorePriceHistory(tenant, store_product, price, changed_at)`** — يُكتَب من `StoreProduct.save()` مباشرةً (لا إشارة) عند كل تغيير سعرٍ فعليّ، **ولا يظهر في أيّ عقدٍ عامّ ولا إداريّ بعد** — تلبيةً للمادة 6a الأوروبية (أدنى سعرٍ خلال ٣٠ يوماً)؛ التاريخ لا يُسترجَع بأثرٍ رجعيّ فالتسجيلُ يبدأ من أوّل يوم.
- **`StoreCollection`** كسبت `starts_at`/`ends_at` (كلاهما `null` — بلا بدايةٍ/نهايةٍ) و`discount_percent` و`priority`. **لا `StoreCampaign` منفصل**: مجموعةٌ ذاتُ تواريخَ وخصمٍ تُسمّى «حملة» في الواجهة، الفرقُ حالةٌ لا نوع.
- **`StoreProductImage`/`StoreProductView`/`StoreCollectionItem`** كسبت حقلاً `store_product` FK→`StoreProduct` (`null=True`, `CASCADE`) **بجانب** `product` القائم — لا حذف ولا تغيير عليه. فرادة `StoreProductView` و`StoreCollectionItem` اكتسبت نظيرةً موازيةً بالحقل الجديد بلا كسر القديمة.

**هجرةُ البيانات** `store/migrations/0006_migrate_catalog_to_store_product.py` — `RunPython` بدالّة تراجعٍ صريحة، **مُضيفةٌ محضة** (لا تحذف/تعدّل صفّاً في `inventory.Product`)، **قابلةٌ لإعادة التشغيل** يحرسها `imported_from_product_id`.
معيارُ الاستحقاق **أوسعُ من راية `is_for_sale_online`** عمداً: يُنسَخ كلُّ منتجٍ له **أيضاً** صفٌّ في `StoreProductImage` أو عضويّةٌ في `StoreCollectionItem` — الصورةُ والعضويّةُ إعلانا نيّةٍ لا يقلّان صراحةً عن الراية. السعرُ المنسوخ حرفياً منطقُ دالّة `_price_expression` التي كانت تحكم القراءة العامة قبل م٢ (`online_price` الموجب وإلّا `sale_price`؛ الدالّةُ نفسها أُسقطت من `store/views.py` بعد أن حلّ محلَّها `published_products` الجديد، وهذا وصفٌ للسلوك المجمَّد في الهجرة لا إشارةٌ لكودٍ حيّ). الماركاتُ تُوحَّد لكلّ شركةٍ بغير حساسيةٍ لحالة الأحرف، والفئاتُ تُسطَّح بمستوىً واحد من فئات `inventory.ProductCategory` المُستعمَلة فعلاً — **بلا رابطٍ دائم** بها. `StoreProductImage`/`StoreCollectionItem` **لا يتيمَ ممكنٌ فيهما** (الهجرة تتوقّف بخطأٍ صريح إن وجدت واحداً)؛ `StoreProductView` يتيمُه مُتوقَّعٌ (منتجٌ شوهد ثم لم يُستحقّ) **ويُحذَف**.

**قيدٌ معماريٌّ لا يُنقَض**: لا استيراد من `inventory` إلى `store/models.py` ولا العكس — `imported_from_product_id` رقمٌ مجرَّدٌ للسبب نفسه.

## ما لا تفعله هذه الـapp
لا تكتب قيداً ولا حركة مخزون — `StoreProduct` لا صلة له بـ`quantity_on_hand`/`StockMovement` أصلاً (قرار مالكٍ حاكم منذ م١).
لا طلب شراء ولا دفع ولا تحصيل: السلة تنتهي عند رسالة واتساب يرسلها الزبون، ولا شيء منها يصل الخادم.
لوحة الإدارة تكتب على `StoreProduct`/`StoreBrand`/`StoreCategory`/`StoreCollection` حصراً بصلاحية `store.manage` منذ م٢ — لا على `inventory.Product` — والسطح العام يبقى قراءةً فقط عدا عدّاد المشاهدات.

## أهم الملفات
| الملف | الغرض |
|---|---|
| `store/views.py` | النقاط العامة + نقاط الإدارة + `published_products` (الاستعلام المقيَّد + الخصم بـSQL) + الكاش + العدّاد + `StoreProductAdminViewSet.import_from_inventory` (م٣) + عدّاداتُ `StoreProductListView` السياقية (`_filtered(exclude_axis=…)`, `_category_facet`, `_brand_facet`, `_flags_facet`, `_price_range_facet`) (م٤) |
| `store/serializers.py` | القائمة البيضاء المصرَّحة حقلاً حقلاً (سبعةَ عشر منذ م٢) + `TenantScopedPrimaryKeyRelatedField` |
| `store/models.py` | `StoreProductView` · `StoreSettings` (كسبت `new_product_days` م٤) · `StoreProductImage` · `StoreCollection(Item)` · `StoreProduct` · `StoreBrand` · `StoreCategory` · `StorePriceHistory` — وحرّاسا الحفظ `StoreProduct._reject_non_positive_sale_price` و`StoreCollection._reject_price_killing_discount` (م٢) |
| `store/slugs.py` | `build_unique_slug` — النسخةُ **الحيّة** لتوليد slug عربيٍّ فريد، يستعملها `StoreProduct.save()` وحده |
| `store/migrations/0006_migrate_catalog_to_store_product.py` | نسخُ الأصناف المستحقّة إلى `StoreProduct` — مُضيفةٌ محضة وقابلةٌ لإعادة التشغيل. تحمل نسخةً **مجمَّدةً** مستقلّةً من منطق الـslug (`_build_unique_slug_frozen`) ولا تستورد من `store/slugs.py` عمداً — هجرةٌ يجب أن تُنتج نفسَ النتيجة بعد سنوات بلا تأثّرٍ بتطوّر الكود الحيّ |
| `store/migrations/0007_m2_product_fk_nullable.py` | إسقاطُ قيد `NOT NULL` عن `product` في الجداول الثلاثة — بلا حذفٍ ولا مسٍّ للبيانات (م٢) |
| `store/migrations/0008_m2_featured_store_product.py` | إضافةُ `StoreCollection.featured_store_product` (م٢) |
| `store/migrations/0009_populate_featured_store_product.py` | مِلءُ الحقل الجديد من `featured_product` القديم عبر `imported_from_product_id` — مُضيفةٌ محضة (م٢) |
| `store/migrations/0010_storesettings_new_product_days.py` | إضافةُ `StoreSettings.new_product_days` (افتراضه ٣٠) لفلتر `is_new` (م٤) |
| `store/urls.py` | المسارات تحت `/api/store/` — بما فيها `admin/brands` و`admin/categories` (م٢) |
| `store/tests/test_public_leakage.py` | معيار النجاح السالب: إثبات غياب التسريب + القائمة البيضاء الموسَّعة (م٢) |
| `store/tests/test_store_catalog_public.py` | **م٢**: الخصمُ (الأكبر يفوز، منتجٌ ضدّ حملة، حملةٌ ضدّ حملة)، سريانُ الحملة بالتاريخ، الحرّاسان، حجبُ الأسعار، وحدُّ الاستعلامات |
| `store/tests/test_store_catalog_models.py` | نماذج الكتالوج المستقلّ: عمق الفئات، فرادة الـslug، سجلّ الأسعار |
| `store/tests/test_store_api.py` | التوفّر والسعر والبحث والفرز والصور والكاش — على `StoreProduct` منذ م٢ |
| `store/tests/test_store_slug.py` | حارس كتابة المعرّف والتحقّق منه، والرحلة الكاملة عبر `/api/store/admin/products/` |
| `store/tests/test_view_counter.py` | حدود العدّاد: أين يُكتب وأين لا يُكتب |
| `store/tests/test_store_advanced.py` | الطلب المسبق والصور المخصصة والمظهر والحملات |
| `store/tests/test_store_admin_scoping.py` | المنتج المميّز (`featured_store_product`)، وعزل الشركات في نقاط الإدارة، وحذف منتجٍ بلا توابع |
| `store/tests/test_store_admin_fields.py` | **م٢**: CRUD كامل على `StoreProduct`/`StoreBrand`/`StoreCategory`، وحرّاسا الحفظ يعودان 400 عبر الـAPI |
| `store/tests/test_publish_flow.py` | مراجعةُ أول تفعيل، وفوريّةُ الظهور والاختفاء — عبر `/api/store/admin/products/` منذ م٢ |
| `store/tests/test_store_surface.py` | إبطال الكاش عند النشر/السحب، وترقيم الحملات، وانتقاء المنتجات بـ`ids` |
| `store/tests/test_store_import_from_inventory.py` | **م٣**: استيراد من الأصناف — نسخٌ صحيح، تخطّي المستورد سلفاً، عزل الشركة، صفر صفٍّ متغيّر في `inventory.Product` |
| `store/tests/test_store_facets.py` | **م٤**: الاستثناءُ الانفصاليّ في الاتجاهين، تجاوزُ مجموع محورٍ لـ`count`، العدُّ الشجريّ الشامل، تعدّدُ الاختيار (OR/AND)، ظهور/غياب العدّادات بالصفحة، مدى السعر السياقيّ وغيابه عند حجب الأسعار، `in_stock` دون `preorder`، حدُّ `is_new`، حارسا بصمة الكاش والأداء |
| `frontend_v2/contexts/StoreCartContext.tsx` | سلة المتصفح ورسالة الواتساب |
| `frontend_v2/components/settings/StoreCategoriesPage.tsx` | شجرة فئات المتجر — شاشةٌ مستقلّة على `/store-categories` (م٣) |
| `frontend_v2/components/settings/StoreImportFromInventoryModal.tsx` | منتقي «استيراد من الأصناف» متعدّد الاختيار (م٣) |
| `frontend_v2/e2e/store-catalog-publish-journey.spec.ts` | إثبات الرحلة: إنشاءٌ من اللوحة ← ظهورٌ في المتجر العام (م٣) |
