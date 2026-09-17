# بحث: الفلترةُ بعدّاداتٍ (faceted search) في المتاجر الاحترافية

القضية: [#157](https://github.com/thabet-toma/ktra2/issues/157) — جزءٌ من الخريطة #148.
التاريخ: 2026-09-07. الفرع: `research/store-facets`.

## النطاق — ما غُطّي وما لم يُغطَّ

غُطّي بمصادرَ أوليّةٍ (توثيقُ المنصّة نفسِها أو شيفرتُها المفتوحة):

1. **Algolia** — مرجعُ المصطلح ودلالتُه.
2. **Shopify Storefront API** — `filters` على `products` داخل المجموعة.
3. **WooCommerce Store API** — نقطةُ `/products/collection-data`.

**لم يُغطَّ في هذه الجولة** (بقرارِ نطاقٍ صريح، لا لغيابِ مصادر): **Salla** · **Zid** · **Meilisearch** · **BigCommerce**.
ولذلك فالسؤالُ الأوّلُ في التذكرة — «ماذا تفعل المنصّاتُ العربيةُ الثلاثُ تحديداً» — **بقي بلا جواب**، ويحتاج جولةً ثانية.

قاعدةُ الأدلّة المتّبعة: كلُّ ادّعاءٍ برابط. حيث لم أجد نصّاً صريحاً كتبتُ «لا يوثّقه المصدر» بدل التخمين. ولم أستعمل مدوّناتٍ ثانويةً أصلاً.

---

## 1) موضعُ العدّادات في الردّ: مع القائمة أم نقطةٌ منفصلة؟

**Algolia — في الردّ نفسِه.** استجابةُ البحث تحمل كائناً `facets` بالشكل
`{"facets": {"attributeName": {"facetValue": count}}}` إلى جانب `hits`، ومعه رايةُ اكتمالٍ
`exhaustiveFacetsCount` (وصيغةٌ متداخلة `exhaustive.facetsCount`).
المصدر: <https://www.algolia.com/doc/api-reference/api-parameters/facets/>

**Shopify — في الردّ نفسِه، حقلٌ شقيقٌ للقائمة.** الاستعلامُ الواحد يُعيد `products(first: 10) { filters { … } nodes { … } }`؛
أي حقلٌ منفصلٌ داخل الردّ ذاته لا نقطةٌ ثانية.
المصدر: <https://shopify.dev/docs/storefronts/headless/building-with-the-storefront-api/products-collections/filter-products>
وبنيةُ `Filter`: `id` · `label` · `type: FilterType!` · `presentation` · `values: [FilterValue!]!`
(<https://shopify.dev/docs/api/storefront/latest/objects/Filter>)، وبنيةُ `FilterValue`:
`count` = «The number of results that match this filter value» · `id` · `input` (JSON: «an input object that can be used to filter by this value on the parent field… you can combine their respective `input` values to use in a subsequent query») · `label` · `image` · `swatch`
(<https://shopify.dev/docs/api/storefront/latest/objects/FilterValue>).

**WooCommerce — نقطةٌ منفصلة.** `GET /wc/store/v1/products/collection-data` مستقلّةٌ عن `GET /products`،
وتُعيد `price_range` · `attribute_counts` · `rating_counts` · `taxonomy_counts` (وكذلك عدّاداتُ حالةِ المخزون).
المصدر: <https://github.com/woocommerce/woocommerce/blob/trunk/docs/apis/store-api/resources-endpoints/product-collection-data.md>
لكنّ النقطةَ المنفصلةَ **ليست عقداً منفصلاً**: `get_collection_params()` فيها تبدأ حرفيّاً بـ
`$params = ( new Products( $this->schema_controller, $this->schema ) )->get_collection_params();`
أي أنّها ترث كلَّ معاملاتِ فلترةِ `/products` ثمّ تضيف معاملاتِ `calculate_*`.
المصدر: <https://github.com/woocommerce/woocommerce/blob/trunk/plugins/woocommerce/src/StoreApi/Routes/V1/ProductCollectionData.php>

**لا إجماع.** اثنان من ثلاثةٍ يُدمجان، وWooCommerce يفصل — لكنّه يفصل مع **توحيدِ معاملاتِ الفلترة**.
والمشتركُ الحقيقيّ: مهما كان الموضعُ، **الفلاترُ المُطبَّقةُ واحدةٌ لكلا الجانبين**.

> **التوصية:** ردٌّ واحدٌ يحمل `results` و`facets` معاً (نمطُ Algolia/Shopify)، لأنّ مسارَنا عامٌّ ومخنوقٌ وكلُّ نقطةٍ إضافيةٍ تضاعف الطلبات وتعقّد بصمةَ الكاش. إن فُصلت لاحقاً لأسبابِ كاش، فيجب — على منوال Woo — أن تقبل **نفسَ** معاملاتِ الفلترة حرفيّاً.

---

## 2) العدّاداتُ سياقيّةٌ أم مطلقة؟ وهل يُستثنى محورُ الاختيارِ المتعدّد من فلترةِ نفسِه؟ (أدقُّ نقطة)

### الجواب المختصر
**سياقيّةٌ بالإجماع.** و**نعم**، محورُ الاختيارِ المتعدّد (OR) يُستثنى من فلترةِ نفسِه عند حساب عدّاداته —
وهذا هو «disjunctive faceting». وهو **ليس** سلوكاً تلقائيّاً في محرّك البحث، بل **مسؤوليةُ الطبقةِ التي تبني الردّ**.

### Algolia
العدّاداتُ سياقيّةٌ نصّاً: «Enabling faceting on attributes computes facet counts for each facet value,
and the engine updates and returns the list of values and counts **with each search result**».
وأهمُّ جملةٍ في البحث كلِّه:

> «When using these operators, the engine handles the facet counts differently to keep a consistent user experience.
> **This doesn't happen at the API level but in the InstantSearch libraries.**»

المصدر: <https://www.algolia.com/doc/guides/managing-results/refine-results/faceting/>

أي أنّ محرّكَ Algolia نفسَه **لا** يُنفّذ الفصلَ الانفصاليّ؛ المكتبةُ هي من تفعل. وآليّتُها موثّقةٌ في
`algoliasearch-helper`: عند وجود محورٍ انفصاليّ تُرسَل **طلبتان** — «the first request retrieves the results
and a second one will retrieve the values for the `category` attribute» — والمشكلةُ التي تحلّها موصوفةٌ بأنّه
«once you've selected a value the other[s] that could be chosen won't be returned».
المصدر: <https://instantsearchjs.netlify.app/algoliasearch-helper-js/concepts.html>
وتُدمَج الطلبتان في نداءٍ واحدٍ عبر `multipleQueries` منعاً لمضاعفة الطلبات.

**قيدٌ يجب معرفتُه:** لأنّ عدّاداتِ المحور الانفصاليّ تُحسب باستعلامٍ **مختلف**، فمجموعُها لا يساوي بالضرورة عددَ النتائج المعروضة. هذا سلوكٌ مقصودٌ لا خلل.

### WooCommerce — أوضحُ دليلٍ مكتوبٍ وجدتُه في المصادر الثلاثة
المعاملُ `calculate_attribute_counts` يأخذ مصفوفةَ كائناتٍ كلُّ واحدٍ منها `{taxonomy, query_type}`،
و`query_type` عدّادٌ محصورٌ صراحةً: `'enum' => [ 'and', 'or' ]` بوصفٍ نصّه
«Filter condition being performed **which may affect counts**».
وفي جسم النقطة:

> ```php
> // Or type queries need special handling because the attribute, if set,
> // needs removing from the query first otherwise counts would not be correct.
> ```
> ```php
> $filter_request    = clone $request;
> $filter_attributes = $filter_request->get_param( 'attributes' );
> if ( ! empty( $filter_attributes ) ) {
>     $filter_attributes = array_filter(
>         $filter_attributes,
>         function ( $query ) use ( $taxonomy ) {
>             return wc_sanitize_taxonomy_name( $query['attribute'] ) !== $taxonomy;
>         }
>     );
> }
> $filter_request->set_param( 'attributes', $filter_attributes );
> $counts = $filters->get_attribute_counts( $filter_request, [ $taxonomy ] );
> ```

وتعليقٌ آخرُ يحسم الفرقَ بين الوضعين:

> «the "or" branch **removes the active attribute filter before counting** while the "and" branch **keeps it**,
> so for the same taxonomy the two counts can legitimately differ.»

كما أنّ الافتراضَ عند غيابِ `query_type` هو **`or`**:
`if ( empty( $attributes_to_count['query_type'] ) || 'or' === $attributes_to_count['query_type'] )`.
المصدر: <https://github.com/woocommerce/woocommerce/blob/trunk/plugins/woocommerce/src/StoreApi/Routes/V1/ProductCollectionData.php>

وباقي المحاور (السعر، التقييم، حالةُ المخزون، التصنيفات) تُحسب من `$request` كما هو — أي **سياقيّةٌ تماماً بلا استثناء**؛
الاستثناءُ محصورٌ بمحاور السماتِ الانفصاليّة وحدَها.

### Shopify — **فجوةٌ موثّقة**
Shopify يُعرّف `FilterValue.count` بأنّه «The number of results that match this filter value»
(<https://shopify.dev/docs/api/storefront/latest/objects/FilterValue>)، وتوثيقُ Liquid يقول
«The number of results related to the filter value. Returns a value only for `boolean` and `list` type filters.
Returns `nil` for `price_range` type filters» (<https://shopify.dev/docs/api/liquid/objects/filter_value>).
**ولا يقول أيٌّ من صفحتَي التوثيق، ولا صفحةُ الفلترةِ في القوالب، ما إذا كانت العدّاداتُ تُحسب مع الفلاترِ النشطةِ الأخرى، ولا ما إذا كان المحورُ يُستثنى من فلترةِ نفسِه.** بحثتُ عن نصٍّ صريحٍ فلم أجده. هذه فجوةُ توثيقٍ عند Shopify لا خلاصةُ بحث.
(<https://shopify.dev/docs/storefronts/themes/navigation-search/filtering/storefront-filtering>)

> **التوصية:** نطبّق نمطَ WooCommerce لأنّه الوحيدُ **المكتوبُ** بين الثلاثة: العدّاداتُ سياقيّةٌ افتراضاً،
> ولكلِّ محورٍ **متعدّدِ الاختيار** يُحسب عدّادُه على استعلامٍ **مُزالٍ منه شرطُ ذلك المحور وحده** مع بقاء كلّ الشروط الأخرى.
> وللمحاور أحاديّةِ الاختيار يُحسب العدّادُ بالشروط كاملةً.
> ويجب أن يُصرَّح في عقدِ الواجهة أنّ **مجموعَ عدّاداتِ محورٍ انفصاليٍّ قد يتجاوز عددَ النتائج** — وإلّا حُسبت الظاهرةُ خللاً في أوّل مراجعة.

---

## 3) مدى السعر: منزلقٌ بحدّين خادميّين أم شرائحُ جاهزة؟

**إجماعٌ نادرٌ بين الثلاثة: حدّان مستمرّان (min/max) يُحسبان خادميّاً — لا شرائحُ (buckets) جاهزة.**

- **Algolia:** حدَّا المنزلق «automatically computed by Algolia from the data in the index» عند عدم تمريرهما،
  بشرط أن يكون الحقلُ ضمن `attributesForFaceting`.
  <https://www.algolia.com/doc/api-reference/widgets/range-slider/js/>
- **Shopify:** نوعٌ مستقلٌّ في العدّاد `FilterType`: `BOOLEAN` · `LIST` · `PRICE_RANGE`
  (<https://shopify.dev/docs/api/storefront/latest/enums/FilterType>).
  و`count` **`nil` لمرشّح `price_range`** — أي لا عدّاداتِ شرائحَ أصلاً
  (<https://shopify.dev/docs/api/liquid/objects/filter_value>).
  والحدودُ تأتي حقولاً على المرشّح: `min_value` و`max_value` («Returns a value only for `price_range` type filters»)
  و`range_max` = «The highest product price within the collection or search results»
  (<https://shopify.dev/docs/api/liquid/objects/filter>). والإدخالُ في Storefront API نطاقٌ: `price: PriceRangeFilter`
  «A range of prices to filter with-in» (<https://shopify.dev/docs/api/storefront/latest/input-objects/ProductFilter>).
- **WooCommerce:** `calculate_price_range` — «Returns the min and max price for the product collection.
  If false, only `null` will be returned» — والردُّ `price_range: { min_price, max_price, currency_code,
  currency_minor_unit, currency_symbol, … }`، والفلترةُ بـ`min_price`/`max_price`
  «provided using the smallest unit of the currency».
  <https://github.com/woocommerce/woocommerce/blob/trunk/docs/apis/store-api/resources-endpoints/product-collection-data.md>

> **التوصية:** نُعيد `price_range: {min, max}` محسوباً خادميّاً بالوحدة الصغرى للعملة (تجنّباً لعوائم الفاصلة)،
> وبمعلوماتِ العملة في الردّ كما تفعل Woo. لا شرائحَ جاهزةً ولا عدّاداتٍ للسعر.
> **نقطةٌ تحتاج قرارَ مالك:** هل تُعاد حدودُ السعر **مطلقةً** (كلّ منتجات المتجر/التصنيف) أم **سياقيّةً** (بعد بقيّة الفلاتر)؟
> Shopify يصف `range_max` بأنّه «within the collection or search results» — وهي عبارةٌ لا تحسم الأمر؛
> وWoo يحسبها من `$request` كاملاً أي سياقيّةً. عمليّاً: الحدودُ السياقيّةُ تجعل المنزلقَ يقفز تحت يد المستخدم كلّما غيّر فلتراً آخر.

---

## 4) دلالةُ الجمع: OR داخل المحور وAND بين المحاور

**إجماعٌ كامل، وهو المعياريّ فعلاً.**

- **Shopify** (نصّان مستقلّان):
  «Different filters get combined using the `AND` operator» و«Multiples of the same filter get combined using the `OR` operator»
  (<https://shopify.dev/docs/storefronts/headless/building-with-the-storefront-api/products-collections/filter-products>)؛
  و«Filters are applied with `AND` logic, and filter values with `OR`»
  (<https://shopify.dev/docs/storefronts/themes/navigation-search/filtering/storefront-filtering>).
  ويُقبل تعدُّدُ القيم بصيغتين: `filter.v.option.color=red,blue` أو `filter.v.option.color=red&filter.v.option.color=blue`.
- **Algolia** — `facetFilters`: المصفوفةُ المسطّحةُ AND، والمتداخلةُ OR:
  `[["category:Book", "category:Movie"], "author:John Doe"]` ⇐ `(Book OR Movie) AND John Doe`.
  وقيدٌ صريح: «You can't group `AND` conditions inside an `OR` group. `(A AND B) OR C` is invalid.»
  <https://www.algolia.com/doc/api-reference/api-parameters/facetFilters/>
- **WooCommerce** — المعاملُ `attributes` مصفوفةُ كائناتٍ فيها `attribute` و`term_id`/`slug` و`operator` اختياريّ
  بقيمٍ `in` · `not_in` · `and`؛ فـ`in` (الافتراضيّ) = OR داخل المحور، و`and` = AND داخله (تقاطعُ السمات).
  <https://github.com/woocommerce/woocommerce/blob/trunk/docs/apis/store-api/resources-endpoints/products.md>

> **التوصية:** OR داخل المحور، AND بين المحاور — بلا نقاش، فهذه دلالةٌ متّفقٌ عليها عند الثلاثة.
> وWoo وحدَه يسمح بقلبِ المحور إلى AND لكلّ سمةٍ على حدة، وهو ما يرتبط مباشرةً بالسؤال #2 (الوضعُ `and` **لا** يُستثنى من فلترة نفسه).
> لا نحتاجه في الإصدار الأوّل؛ نتركه امتداداً مستقبليّاً بنفس اسم المعامل `query_type`.

---

## 5) الأداء: هل يكفي تجميعُ SQL عاديٍّ في متجرٍ بمئاتِ المنتجات؟

**نعم، يكفي — وبأدلّةٍ لا بترجيح.**

**الدليلُ الحاسم:** WooCommerce — أقربُ نظيرٍ لحالتنا (تطبيقٌ خادميٌّ فوق MySQL، بلا محرّكِ بحث) — ينفّذ
كلَّ عدّاداته باستعلاماتِ تجميعٍ خامٍّ على MySQL، لا محرّكَ بحثٍ ولا فهرسَ مقلوباً. من `FilterData.php`:

- مدى السعر: `SELECT min( min_price ) as min_price, MAX( max_price ) as max_price …`
- حالةُ المخزون: `SELECT stock_status, COUNT( DISTINCT product_id ) as status_count … GROUP BY stock_status`
- التقييم: `SELECT COUNT( DISTINCT product_id ) …, ROUND( average_rating, 0 ) … GROUP BY rounded_average_rating`
- السمات: `SELECT COUNT( DISTINCT term_relationships.object_id ) …, terms.term_id … INNER JOIN … GROUP BY terms.term_id`
- وتحسينٌ لافت: تجميعُ عدّةِ محاورَ في استعلامٍ واحدٍ عبر
  `COUNT(DISTINCT CASE WHEN tt.term_id IN (…) THEN tr.object_id END) as count_{$term_id}`

المصدر: <https://github.com/woocommerce/woocommerce/blob/trunk/plugins/woocommerce/src/Internal/ProductFilters/FilterData.php>

**والدليلُ المقابل:** Algolia نفسُها تُقرّ بأنّ عدّاداتِها قد تصير تقريبيّةً وتُصدر رايةَ `exhaustiveFacetsCount`
لتمييز الدقيقِ من التقريبيّ (<https://www.algolia.com/doc/api-reference/api-parameters/facets/>).
أي أنّ ثمنَ المحرّكِ يُدفَع لمشكلةِ **الملايين**، وعَرَضُه الجانبيُّ (عدّاداتٌ غيرُ مضمونةِ الدقّة) عيبٌ لا نحتاج أن نشتريه بمئاتِ الصفوف.

**ترجمةٌ لحالتنا (Django 5.1 + MySQL، مسارٌ عامٌّ مخنوقٌ بكاشٍ ببصمةِ معاملات):**

- كلفةُ الطلبة = استعلامُ القائمة + استعلامُ تجميعٍ لكلّ محورٍ انفصاليٍّ (لأنّ كلّاً منها يسقط شرطَ نفسِه)
  + استعلامٌ واحدٌ يجمع كلَّ المحاور غيرِ الانفصاليّة + استعلامُ `MIN/MAX` للسعر.
  بخمسة محاورَ وبضع مئاتِ الصفوف هذا في نطاقِ الملّي ثانية، لا العشرات.
- **لا داعيَ لـCelery ولا لمحرّكِ بحث.** يتّسق هذا مع خلاصةِ اختبارِ الحمل السابقة في المشروع
  (`docs/` — «الإنتاجيةُ الثابتةُ اختناقُ سعةٍ لا كود»).
- ما يُلزَم فعلاً: فهارسُ على أعمدةِ الفلترة (`tenant`, السعر, حالةُ التوفّر, مفاتيحُ السمات)، وأن تدخل **كلُّ**
  معاملاتِ الفلترة في بصمةِ الكاش بترتيبٍ مُطبَّعٍ (قيمُ المحور المتعدّد مرتّبةً) وإلّا انفجرت البصمة أو — أسوأ — تصادمت.
- **حذرٌ خاصٌّ بـMySQL عندنا:** أيُّ محورٍ يقوم على تاريخ (مثل رايةِ «جديد» أدناه) لا يُبنى بـ`__date` على عمود
  `DateTimeField`؛ جداولُ المناطق الزمنية في نسخةِ الإنتاج فارغةٌ فيُعيد الشرطُ صفرَ صفوفٍ **بصمت**
  (فخٌّ مسجَّلٌ في ذاكرة المشروع؛ يُستعمل حسابُ المدى بحدّين بدلَه). SQLite في الاختبارات لا يكشف هذا.

> **التوصية:** تجميعُ SQL عاديٌّ عبر Django ORM (`values().annotate(Count(...))`) — بلا محرّكِ بحث.
> ويُعاد النظرُ فقط إن تجاوز مستأجرٌ واحدٌ عشراتِ الآلاف من الأصناف، أو إن دخل بحثٌ نصّيٌّ حرٌّ بترتيبِ ملاءمة.

---

## 6) الرايات «مخفَّض / جديد / متوفّر»: حقولٌ محسوبةٌ أم وسومٌ يدويّة؟

| الراية | Shopify | WooCommerce | Algolia |
|---|---|---|---|
| **متوفّر** | حقلٌ محسوب: `available` — «Filter on if the product is available for sale» ([ProductFilter](https://shopify.dev/docs/api/storefront/latest/input-objects/ProductFilter)) | محسوب: `stock_status` ∈ `instock`/`outofstock`/`onbackorder`، وله عدّادُه `calculate_stock_status_counts` ([products.md](https://github.com/woocommerce/woocommerce/blob/trunk/docs/apis/store-api/resources-endpoints/products.md)) | أيُّ حقلٍ مفهرس |
| **مخفَّض** | **لا مرشّحَ مدمجاً**؛ لا وجودَ لـ`onSale` في `ProductFilter` — تُنجَز بوسمٍ (`tag`) أو `productMetafield` | **محسوب ومدمج**: معاملُ `on_sale` منطقيٌّ في `/products` | أيُّ حقلٍ مفهرس |
| **جديد** | **لا شيء**: لا مرشّحَ ولا نافذةَ زمنيةً في أيّ من الصفحات المفحوصة | **لا شيء** في Store API | **لا شيء** |

**تفصيلُ مرشّحاتِ Shopify المدمجة** (وهي القائمةُ الكاملة في `ProductFilter`):
`available` · `category` · `price` · `productMetafield` · `productType` · `productVendor` · `tag` ·
`taxonomyMetafield` · `variantMetafield` · `variantOption`.
<https://shopify.dev/docs/api/storefront/latest/input-objects/ProductFilter>

> **التوصية:** «متوفّر» راية محسوبةٌ من المخزون — إجماعٌ صريح. «مخفَّض» محسوبةٌ من وجودِ سعرٍ مخفَّضٍ ساري المفعول
> (نمطُ Woo `on_sale`) لا وسمٌ يدويّ، لأنّ الوسمَ اليدويَّ يتعفّن.
> **«جديد» قرارُ مالكٍ لا بحث:** لم تُعرّفه أيٌّ من المنصّات الثلاث ولم تحدّد له نافذةً زمنية.
> يلزم حسمُ: (أ) النافذة بالأيام، (ب) مصدرُ التاريخ — `created_at` للصنف أم تاريخُ أوّلِ إدخالٍ للمخزون؟ —
> (ج) أهي إعدادٌ لكلّ مستأجرٍ أم ثابتٌ في النظام. ولا تُبنى بـ`__date` (انظر §5).

---

## خلاصةُ ما **لا** إجماعَ عليه — يحتاج قرارَ مالكٍ لا بحثاً

1. **موضعُ العدّادات**: ردٌّ واحدٌ (Algolia/Shopify) مقابل نقطةٍ منفصلةٍ ترث نفسَ المعاملات (Woo).
2. **حدودُ السعر: مطلقةٌ أم سياقيّة؟** لا نصَّ حاسماً عند أيٍّ منها؛ والاختيارُ يغيّر إحساسَ المنزلق تحت يدِ المستخدم.
3. **إظهارُ القيم بعدّادٍ صفر**: Shopify يوصي بتعطيلها لا إخفائها؛ Woo وAlgolia لا يفرضان شيئاً. قرارُ واجهة.
4. **راية «جديد»**: بلا تعريفٍ ولا نافذةٍ زمنيةٍ في أيّ منصّة. قرارُ مالكٍ صافٍ.
5. **راية «مخفَّض»**: مدمجةٌ ومحسوبةٌ عند Woo، وغائبةٌ تماماً عند Shopify. لا إجماع.
6. **قلبُ محورٍ إلى AND** (`query_type=and` عند Woo): موجودٌ عند Woo وحدَه. نؤجّله أم ندخله من البداية؟

## فجواتُ توثيقٍ صريحة (لا نتائجَ بحثٍ ناقصة)

- **Shopify لا يوثّق سياقيّةَ عدّاداتِه ولا الفصلَ الانفصاليّ** — لا في `FilterValue` ولا في `filter_value` (Liquid)
  ولا في صفحةِ الفلترة. أُثبت هنا كفجوةٍ لا كنفي.
- **Algolia** تُصرّح بأنّ الفصلَ الانفصاليّ **ليس** سلوكَ الـAPI بل سلوكَ مكتبةِ الواجهة — وهذا يعني أنّ أيّ تنفيذٍ
  يبني على الـAPI مباشرةً سيحصل على عدّاداتٍ «تختفي» ما لم يتولَّ الفصلَ بنفسه.
- **المنصّاتُ العربيةُ الثلاثُ (Salla · Zid) لم تُفحص أصلاً** في هذه الجولة.

## المصادر

- Algolia — Faceting: <https://www.algolia.com/doc/guides/managing-results/refine-results/faceting/>
- Algolia — `facets`: <https://www.algolia.com/doc/api-reference/api-parameters/facets/>
- Algolia — `facetFilters`: <https://www.algolia.com/doc/api-reference/api-parameters/facetFilters/>
- Algolia — Range slider widget: <https://www.algolia.com/doc/api-reference/widgets/range-slider/js/>
- algoliasearch-helper — Concepts (conjunctive/disjunctive): <https://instantsearchjs.netlify.app/algoliasearch-helper-js/concepts.html>
- Shopify — `Filter`: <https://shopify.dev/docs/api/storefront/latest/objects/Filter>
- Shopify — `FilterValue`: <https://shopify.dev/docs/api/storefront/latest/objects/FilterValue>
- Shopify — `FilterType`: <https://shopify.dev/docs/api/storefront/latest/enums/FilterType>
- Shopify — `ProductFilter`: <https://shopify.dev/docs/api/storefront/latest/input-objects/ProductFilter>
- Shopify — Filter products with the Storefront API: <https://shopify.dev/docs/storefronts/headless/building-with-the-storefront-api/products-collections/filter-products>
- Shopify — Storefront filtering (themes): <https://shopify.dev/docs/storefronts/themes/navigation-search/filtering/storefront-filtering>
- Shopify Liquid — `filter`: <https://shopify.dev/docs/api/liquid/objects/filter>
- Shopify Liquid — `filter_value`: <https://shopify.dev/docs/api/liquid/objects/filter_value>
- WooCommerce Store API — Product Collection Data: <https://github.com/woocommerce/woocommerce/blob/trunk/docs/apis/store-api/resources-endpoints/product-collection-data.md>
- WooCommerce Store API — Products: <https://github.com/woocommerce/woocommerce/blob/trunk/docs/apis/store-api/resources-endpoints/products.md>
- WooCommerce — `ProductCollectionData.php`: <https://github.com/woocommerce/woocommerce/blob/trunk/plugins/woocommerce/src/StoreApi/Routes/V1/ProductCollectionData.php>
- WooCommerce — `FilterData.php`: <https://github.com/woocommerce/woocommerce/blob/trunk/plugins/woocommerce/src/Internal/ProductFilters/FilterData.php>
