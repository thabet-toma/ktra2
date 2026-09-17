# سُلَّم التكلفة حين يرتفع السعر دائماً — بحثٌ خارج المستودع

> بحثُ قضية [#125](https://github.com/thabet-toma/ktra2/issues/125) ضمن خريطة [#123](https://github.com/thabet-toma/ktra2/issues/123).
> فرعٌ مؤقّت `research/cost-ladder` — لا كودَ إنتاجيّ، ولا يُدمج.
> كل مصطلحٍ أدناه **مقروءٌ من صفحة موثّقة** مذكورةٌ في §8؛ وما لم يُتحقَّق منه موسومٌ صراحةً «غير مُتحقَّق».

---

## 0. التوصية المسمّاة

**«كلفةٌ مرجعية بمستند إعادة تقييم، وورقةُ اقتراحٍ فوقها»**
`Reference Cost` + `Cost Revaluation` document + `Cost Suggestion Worksheet`
— على نمط **Business Central**: `Standard Cost Worksheet` (اقتراح) ← `Revaluation Journal` (تثبيت) ← `Last Direct Cost` (عرضٌ مستقلّ).

ثلاثةُ أجزاءٍ لا واحد:

1. **`last_direct_cost`** — حقلٌ مشتقّ آلياً من **آخر** فاتورة شراء مرحَّلة (نظير BC `Last Direct Cost`). لا يُختار ولا يُسنَد لأحد؛ حقيقةٌ خام تُعرض بجانب المرجع.
2. **`reference_cost`** — رقمٌ **مخزَّن** بعملة الأساس، هو ما تعرضه الشاشات وتبني عليه التسعير. لا يتغيّر إلا بمستند.
3. **`CostRevaluation`** — المستند الذي يغيّره، ويحمل: القيمة الجديدة · العملة والسعر الأصليان · تاريخ السريان · **مَن أثبتها** · السبب · ومرجع سطر الشراء المرحَّل الذي اشتُقّت منه.
   وفوقه **ورقةُ اقتراح** تعرض المرشّحين (أدنى مطلقاً · أدنى خلال ١٢ شهراً · آخر شراء · متوسط مرجّح ١٢ شهراً) — المستخدم يختار درجةً **مرّةً واحدة**، فيتولّد المستند.

**جوهر التوصية:** السُّلَّم **شاشةُ قرارٍ لا حالةٌ محفوظة**. الدرجة تُختار وتُثبَّت، لا تُحسب في كل عرض.
السبب مباشر: المالك طلب شيئين — رقماً أحدث، **ومَن أثبته**. والإسناد يستلزم حدثاً، والحدث يستلزم قيمةً مخزَّنة. سُلَّمٌ يُحسب لحظياً لا يمكن إسناده لأحد أبداً.

---

## 1. Cost tiering / cost layers — وهل يُختار «طبقة» كمرجع؟

الطبقات موجودةٌ في الأنظمة كلها، لكن **لغرض التقييم والاستهلاك، لا لغرض المرجعية**.

| النظام | آلية الطبقات (بمصطلحها) | هل يختار المستخدمُ طبقة؟ |
|---|---|---|
| **Business Central** | `Item Ledger Entry` + `Value Entry`؛ وطرقُ الكلفة الخمس `FIFO` · `LIFO` · `Specific` · `Average` · `Standard` | **نعم، لكن لغرضٍ آخر:** حقل `Applies-from Entry` في `Item Journal` — *"manually create a fixed application between an inbound transaction and the original outbound transaction"*. أي: يختار **أيّ طبقةٍ يستهلكها الصرف**، لا أيّ طبقةٍ تكون السعرَ المرجعي. |
| **NetSuite** | طرق الكلفة السبع: `Average` · `FIFO` · `LIFO` · `Specific` · `Lot Numbered` · `Group Average` · `Standard` | **نعم، بالكائن لا بالدرجة:** `Specific` — *"This method uses the exact cost of a serial number you enter."* اختيارُ رقمٍ تسلسلي هو ضمناً اختيارُ طبقة. لا شاشةَ «اختر درجة كلفة». |
| **SAP** | `Material Ledger` وطبقاتُ الفترة؛ `CKM3` — *Material Price Analysis* لعرض طبقات السعر والفروق | لا. التحليل عرضٌ للطبقات، والمرجعُ يُحسم بـ`price control` (S أو V). |
| **Odoo** | `stock.valuation.layer` (تقرير `Inventory Valuation`) | لا. لا اختيارَ طبقةٍ كمرجع. |
| **Zoho Inventory** | `FIFO` و`WAC` فقط | لا. لا طبقاتٍ مكشوفة، ولا كلفةً معيارية، ولا إعادة تقييم. |

### الحكم

> **لا نظامَ من الخمسة يعرض «سُلَّم كلف» ويطلب من المستخدم اختيار درجةٍ كسعرٍ مرجعي.**
> أقربُ ما وجدته إلى فكرة المالك هو نمطُ **«ورقةُ اقتراحٍ ثم تثبيت»** (BC `Standard Cost Worksheet` · NetSuite `Planned Standard Cost` + `Cost Version`)، لا **«مؤشّرٌ ينتقل بين طبقات»**.
> وهذا فرقٌ جوهريّ في التصميم، لا فرقٌ في التسمية.

---

## 2. Moving average vs standard cost with revaluation

### SAP

- `price control` في `Accounting View` من الـ Material Master: **`S` = Standard Price** · **`V` = Moving Average Price**. توصيةُ SAP المنشورة: `S` للمنتجات نصف المصنّعة والتامّة، و`V` تصلح للمواد الخام والمشتريات الخارجية.
- تغييرُ السعر يدوياً: **`MR21` — Change Material Prices**. من محتوى SAP Help Portal: *"With MR21, you can change prices, mark prices for change, and release prices for material valuation."*
- **الفخّ الرسميّ عند SAP:** إن كان `Material Ledger` نشطاً و`price determination 3`، فتغييرُ السعر **ممنوعٌ** إن كانت في الفترة حركاتُ بضاعةٍ ذاتُ صلةٍ بالتقييم أو فواتيرُ واردة. أي: SAP لا تسمح بتغيير المرجع في فترةٍ «حيّة».
- في `MR21` عمودان: `New price` و`New statistical price` — إن كان الصنف `S` فالمعياريُّ هو السعر والمتحرّكُ إحصائيّ، والعكس بالعكس. **أي أنّ SAP تحتفظ بالرقمين دائماً وتسمّي أحدهما مرجعاً والآخر إحصائياً.**
- المسارُ المُفضَّل عند SAP للمعياريّ ليس `MR21` بل **`Standard Cost Estimate`** بدورة `mark` ثم `release` (`CK11N` / `CK24` / `CK40N`).

### Dynamics 365 Business Central

- طرقُ الكلفة الخمس، و**`Standard Cost Worksheet`** بأربع مهامٍ مجمّعة: `Suggest Item Standard Cost` · `Suggest Capacity Standard Cost` · `Roll Up Standard Cost` · `Implement Standard Cost Changes`.
- للأصناف التي عليها مخزون: تحريرُ الحقل وحده **لا يُصلح التاريخ**؛ لا بدّ من `Revaluation Journal` أو من الورقة. والنصُّ الرسميّ: *"If you want to appreciate or depreciate an item or a specific item ledger entry, you must use the revaluation journal."*
- خطواتُ `Revaluation Journal` المُتحقَّق منها: إجراء **`Calculate Inventory Value`** ← ملءُ **`Unit Cost (Revalued)`** أو **`Inventory Value (Revalued)`** ← حقلُ **`Amount`** يُظهر الفرق عن `Inventory Value (Calculated)` ← **`Post`**.
- وقيدُ التصميم: *"The revaluable quantity can be calculated for any date, also back in time"* — أي إعادةُ التقييم قد **تُعيد كتابة COGS لأصنافٍ بيعت**، وتُنشئ `Value Entry` من نوع `Revaluation` (ومع المعياريّ نوعاً ثالثاً `Variance`).
- **الحقل الفاصل لمشكلتنا:** BC تحتفظ بحقلين منفصلين على بطاقة الصنف — **`Unit Cost`** (قيمةُ المخزون بحسب طريقة الكلفة) و**`Last Direct Cost`** (آخرُ كلفةِ شراءٍ/تصنيعٍ مباشرة)، والأخيرُ هو ما يُنسخ إلى `Direct Unit Cost` في سطر الشراء.

### NetSuite

- بتفعيل خاصّية **`Standard Costing`**: **`Cost Version`** — *"a label to identify a time period or other identifying characteristic"* — ثم **`Planned Standard Cost`** لكل صنفٍ داخل تلك النسخة، مع **`Cost Category`**، ثم **`Standard Cost Rollup`**.
- التثبيتُ بمستندٍ اسمه **`Inventory Cost Revaluation`** (المسار: *Transactions > Inventory > Revalue Inventory Cost*): يضبط قيمة المخزون بـ`standard cost × current quantity on hand`، و*"tells NetSuite which cost and cost category to use on transactions for the item as of the effective date"*.
- توجد صفحاتٌ رسمية لـ`Revalue Standard Cost Inventory and Backdate` — أي أنّ التأريخ للخلف مدعومٌ ومُوثَّق.

### Odoo

- **`Costing Method`** بثلاث قيم: **`Standard Price`** · **`First In First Out (FIFO)`** · **`Average Cost (AVCO)`**.
- `Standard Price` هي الافتراضية، ووصفُها الحرفيّ: *"The cost of the product is manually defined on the product form, and this cost is used to compute the valuation."* — **أي أنّ أشهرَ ERP مفتوحٍ يجعل الكلفةَ المُدخلة يدوياً هي الوضعَ الافتراضي.**
- والأثر: *"If the value in the Cost field on a product form is changed manually, Odoo generates a corresponding record in the Inventory Valuation report."*
- وللتعديل الجَماعي: نموذج **`Product Revaluation`** من لوحة `Inventory ‣ Reporting ‣ Valuation` مع `Group by ‣ Product` — *"the inventory valuation for a product can be recalculated, by increasing or decreasing the unit price of each product."*

### Zoho Inventory

- **`FIFO`** و**`WAC — Weighted Average Costing`** فقط، بنصّ قاعدة المعرفة. لا كلفةَ معيارية، ولا نموذجَ إعادة تقييم، ولا اختيارَ طبقة.
- **وهذه أهمّ مقارنةٍ من حيث الحجم:** Zoho هي أقربُ الخمسة إلى شريحة عملائنا، وهي **لا تقدّم شيئاً ممّا يطلبه المالك**. أي أنّ ما نبنيه يضعنا فوق شريحتنا لا تحتها.

---

## 3. Stale-cost detection — **لا يوجد نمطٌ صناعيّ مسمّى. هذه نتيجةٌ بحدّ ذاتها.**

بحثتُ عن مصطلحٍ معياريّ أو خاصّيةِ منتَجٍ تُسمّى «كشفُ الكلفة البائتة» أو ما يعادلها. **لم أجد.**
لا SAP ولا BC ولا NetSuite ولا Odoo ولا Zoho تُسمّي خاصّيةً تُنبّه أنّ الكلفة المرجعية «لم تعد قابلةً للتحقّق». وما وجدتُه بدلاً منها:

1. **`Purchase Price Variance` (PPV)** — وهو المصطلحُ الصناعيّ **الوحيد** الحقيقيّ هنا، ويعمل **بالاتجاه المعاكس**: يقيس فرقَ سعر الشراء الفعليّ عن المعياريّ ويُرحّله إلى حساب فروق. **تراكمُ PPV هو الإشارة** إلى أنّ المعياريّ بات قديماً — إشارةٌ في **الدفاتر** لا شارةٌ في الواجهة. (وثائق Oracle Cost Management و PeopleSoft تُعرّف PPV صراحةً.)
2. **إرشاداتُ ممارسين لا خصائصُ منتجات** — دوريّةُ المراجعة بحسب التقلّب (سنويّاً / نصف سنويّ / ربعيّ)، والتحديثُ الفوريّ عند تغيّر عقد المورد، واعتبارُ «فرقٍ بالإشارة نفسها ٣ أشهرٍ متتالية» أو «تحرّكِ سعرِ مادةٍ فوق ١٠٪» مؤشّرَ بياتٍ للمعياريّ. **هذه أعمدةُ رأيٍ استشاريّ ومدوّناتُ بائعين — ليست معياراً محاسبياً ولا خاصّيةً في أيٍّ من الأنظمة الخمسة.** أوردتُها موسومةً بمصدرها ولا أبني عليها ادّعاءَ «هكذا تفعل الصناعة».
3. **`Inventory Obsolescence`** مصطلحٌ مسمّى وموجود — لكنه عن **البضاعة** لا عن **رقم الكلفة**. **لا نستعير لفظه**؛ استعارتُه ستُربك المحاسب.

### الأثر على التصميم

إن بنينا شارةَ «هذه الكلفة بائتة»، فنحن **نخترعها**. لا بأس — لكن يجب أن نُسمّيها بما يربطها بشيءٍ حقيقيّ.
**التسميةُ المقترحة: «فجوةُ الشراء عن المرجع» (Purchase Gap vs Reference)** — مشتقّةٌ من منطق PPV نفسه: عددُ ومقدارُ المشتريات المرحَّلة **بعد تاريخ سريان المرجع** التي جاءت **أعلى** منه، بعد تطبيعها لعملة الأساس. لا اختراعَ في المفهوم، فقط في الشارة.

---

## 4. Attribution — «مَن أثبت هذه الكلفة ومتى»

| النظام | آليةُ الإسناد | حالةُ التحقّق |
|---|---|---|
| **NetSuite** | `System Notes`: *"the date when the change was made, who made the change, the role of the user … the type of change, and the old and new record values"*؛ و`Transaction Audit Trail` (Transactions > Management > View Audit Trail) | **مُتحقَّق** من وثائق Oracle |
| **SAP** | تغييرُ السعر بـ`MR21` **مستندٌ محاسبيّ** لا تحريرُ حقل: يُرحّل FI document ولا يُنشئ material document؛ والمستندُ يحمل مُدخِلَه وتاريخه بحكم كونه مستنداً | **مُتحقَّق جزئياً**: كونُه FI document وعدمُ إنشائه material document من محتوى دعم SAP ومن مدوّنات المجتمع. لم أستطع فتح صفحة app-help الرسمية لـ`MR21` (لم تُصيَّر). **نوعُ المستند `PR` تحديداً: غير مُتحقَّق.** |
| **Business Central** | إعادةُ التقييم **قيدٌ يُرحَّل** فيُنتج `Value Entry` من نوع `Revaluation` — فالحدثُ موجودٌ ومؤرَّخ | **مُتحقَّق** أنّ الحدث مستندٌ مرحَّل. **حقلُ «المستخدم» تحديداً: لم أقرأه في الصفحات التي فتحتُها** — لا أزعمه. |
| **Odoo** | تغييرُ `Cost` يدوياً *"generates a corresponding record in the Inventory Valuation report"* — فالحدثُ سجلٌّ لا تحريرٌ صامت | **مُتحقَّق** أنّ سجلاً يتولّد. أنّ السجلّ يحمل `create_uid` أو chatter: **استنتاجٌ من بنية Odoo، لا مقروءٌ من الصفحة.** |
| **Zoho Inventory** | لا مستندَ إعادة تقييم أصلاً ⇒ لا إسناد | **مُتحقَّق** أنّ الخاصّية غير موجودة |

### أقوى نتيجةٍ عابرةٍ للبائعين

> **تغييرُ الكلفة المرجعية عند كلّ من يدعمه = مستندٌ يُرحَّل، لا حقلٌ يُحرَّر.**
> هذا هو الجواب المعماريّ على شقّ «مَن أثبتها» في سؤال المالك، وهو مُتحقَّقٌ عند SAP وBC وNetSuite وOdoo أربعتِها.

---

## 5. ما **يناقض** طرحَ المالك (أهمّ ما في هذا البحث)

**(أ) «أقلّ سعر شراء» ليس كلفةً عند أحد.**
لا SAP ولا BC ولا NetSuite ولا Odoo ولا Zoho تعرف مفهوم «lowest purchase price» كأساسِ كلفة. المصطلح **غيرُ موجود** في أيٍّ من وثائقها. أقربُ حقلٍ حقيقيّ هو BC `Last Direct Cost` — و«آخر» **لا** «أقلّ». فمشكلةُ «القاع الميّت» ليست عيباً في السُّلَّم؛ هي عيبٌ في اختيار القاع أساساً.

**(ب) «الصعودُ درجة» يناقض «مَن أثبتها».**
الطلبان في القضية نفسها متعارضان بنيوياً. مؤشّرٌ ينتقل بين درجاتٍ محسوبةٍ لحظياً **لا يمكن إسناده لأحد**، لأنّ الرقم يتغيّر تحت المستخدم كلّما رُحِّلت فاتورةٌ جديدة دون أن يفعل أحدٌ شيئاً. الأنظمة تحلّها بجعل الاختيار **حدثاً مرّةً واحدة**: اقتراحٌ ← اختيارٌ ← ترحيلٌ ← ثباتٌ حتى إعادة تقييمٍ تالية. لا يمكن أن نمنحه السُّلَّمَ المتحرّك والإسنادَ معاً.

**(ج) المشكلة ليست بياتَ القاع، بل رقمٌ واحدٌ يخدم غرضين متعارضين.**
التقييمُ والربح يحتاجان رقماً **تاريخياً صادقاً**؛ والتسعيرُ والتفاوض يحتاجان رقماً **قابلاً للتحقّق اليوم**. الأنظمةُ الخمسُ كلّها تفصلهما صراحةً: BC بـ`Unit Cost` مقابل `Last Direct Cost`؛ وSAP بـ`New price` مقابل `New statistical price` في `MR21`. **الحلّ ليس ترقيةَ القاع — الحلّ الفصل.** وترقيةُ رقمٍ واحدٍ دون فصلٍ ستنقل العطب من التسعير إلى الربح.

**(د) أيّ سُلَّمٍ بأثرٍ رجعيّ يُعيد كتابة أرباحٍ محقّقة.**
BC توثّق صراحةً أنّ إعادة التقييم يمكن أن تُؤرَّخ للخلف لتصحيح COGS لأصنافٍ بيعت بالفعل، وNetSuite تنشر صفحاتٍ للـ backdating. هذا يمسّ `sales_cogs_map` عندنا مباشرةً — وهو سؤالٌ مفتوحٌ في الخريطة #123 ولم يُحسم. **القرارُ الآمن: الكلفةُ المرجعية للعرض والتسعير فقط، تسري من تاريخها فصاعداً، ولا تمسّ تقييمَ المخزون ولا الأرباح المحقّقة.** أيّ خيارٍ آخر يفتح ملفّ إعادة احتساب الربح كلَّه.

---

## 6. الخياراتُ وفخُّ كلٍّ منها

| # | الخيار | مصطلحُه الصناعيّ | الفخّ |
|---|---|---|---|
| ١ | إبقاءُ «أقلّ سعر» | لا يوجد نظير | القاعُ الميّت — وهو شكوى المالك نفسُها. لا يحلّ شيئاً. |
| ٢ | التحوّل إلى «آخر سعر شراء» | BC `Last Direct Cost` | صفقةٌ شاذّةٌ واحدة (كميّةٌ صغيرة، مورّدٌ طارئ) تصير المرجعَ فوراً. ولا يحلّ شقَّ الإسناد إطلاقاً. |
| ٣ | سُلَّمٌ محسوبٌ في كل عرض، والمستخدم يختار «الدرجة» كإعداد | لا نظير صناعيّ | **ثلاثةُ فخاخ:** (أ) لا إسنادَ ممكن — ليس حدثاً؛ (ب) الرقمُ يتحرّك تحت المستخدم بلا فعلٍ منه؛ (ج) **كلُّ درجةٍ مقارنةٌ إضافية بين وثائق ⇒ سطحُ عودةِ عطب #111 يتضاعف** (١٢ USD تبدو «أقلّ» من ٤٥ ILS). |
| ٤ | **مستندُ إعادة تقييم + ورقةُ اقتراح (التوصية)** | BC `Standard Cost Worksheet` + `Revaluation Journal` · NetSuite `Cost Version` + `Inventory Cost Revaluation` · Odoo `Product Revaluation` | فخُّه **انضباطيّ لا تقنيّ**: إن لم يراجع أحدٌ الورقة، بقيت الكلفةُ قديمةً إلى الأبد — وهو العطبُ نفسُه بثوبٍ جديد. **علاجُه:** شارةُ «فجوةُ الشراء عن المرجع» من §3، وهي شرطُ نجاحٍ لا زينة. |
| ٥ | كلفةٌ معيارية كاملة بنمط SAP/BC مع ترحيل الفروق | `Standard Costing` + `PPV` | يفرض حساباتِ فروقِ أسعارٍ وقيداً مع كلّ شراء، ويُدخل المحاسبَ في تسويةِ فروقٍ شهرية. ثقيلٌ جداً على شريحتنا — وZoho، أقربُ أقراننا، لا تقترب منه. |

---

## 7. قيودُ مستودعنا التي تُلزم أيّ تنفيذٍ لاحق

1. **المصدر** — فواتيرُ الشراء المرحَّلة **وحدها** (قرارُ خريطة #89). ورقةُ الاقتراح تقرأ من `PurchaseInvoiceItem` المرحَّلة، **لا** من عروض الموردين ولا من `supplier_prices`.
2. **العملة — الفخّ الأخطر** — عطبُ #111 كان مقارنةً رقمية عابرةً للعملات. اليوم `core/pricing.py` (`_lowest_purchase_item`) يُطبِّع كلَّ سعرٍ إلى عملة الأساس بسعر مستنده قبل المقارنة، عبر `_convert_currency`.
   **القاعدةُ المُلزمة:** كلُّ درجةٍ في السُّلَّم تُحسب وتُقارَن **بعملة الأساس حصراً**، و`reference_cost` **يُخزَّن بعملة الأساس** مع حفظ العملة والسعر الأصليَّين للعرض فقط. أيُّ درجةٍ جديدة = مقارنةٌ جديدة = موضعُ ارتدادٍ محتمل لـ#111، فتلزمها تغطيةٌ اختبارية بعملتين على الأقل.
3. **القيود** — إن قُرِّر لاحقاً أنّ إعادة التقييم تُنتج قيداً، فعبر `accounting.services.post_journal` حصراً. **وتوصيتُنا للمرحلة الأولى: بلا قيدٍ أصلاً** — الكلفةُ المرجعية للعرض والتسعير، لا تمسّ تقييمَ المخزون (§5-د).
4. **`avg_cost` يبقى** — هو المشتقُّ المحاسبيّ ولا يُمَسّ؛ `reference_cost` يجاوره ولا يحلّ محلّه.
5. **العرضُ الرقميّ** عبر `utils/formatNumber` كعادة المشروع.

---

## 8. المصادر — وما قُرِئ مقابل ما استُنتج

### مقروءٌ من صفحةٍ رسمية (مُتحقَّق)

- Business Central — *Design details: Revaluation*: https://learn.microsoft.com/en-us/dynamics365/business-central/design-details-revaluation
- Business Central — *Create new value entries for items in the inventory* (`Revaluation Journal`, `Calculate Inventory Value`, `Unit Cost (Revalued)`, `Inventory Value (Revalued)`): https://learn.microsoft.com/en-us/dynamics365/business-central/inventory-how-revalue-inventory
- Business Central — *Managing inventory costs* (`Applies-from Entry`, `Exact Cost Reversing Mandatory`, `Average Cost Period`): https://learn.microsoft.com/en-us/dynamics365/business-central/finance-manage-inventory-costs
- Business Central — *Update standard costs* (`Standard Cost Worksheet` وبطالاتُه الأربع): https://learn.microsoft.com/en-us/dynamics365/business-central/finance-how-to-update-standard-costs
- Business Central — *About unit cost calculation* (`Unit Cost` مقابل `Last Direct Cost`): https://learn.microsoft.com/en-us/dynamics365/business-central/finance-about-calculating-unit-cost
- NetSuite — *Costing Methods* (السبع، ونصُّ `Specific`): https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N2191818.html
- NetSuite — *Revalue Standard Cost Inventory*: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N2205401.html
- NetSuite — *Inventory Cost Revaluation*: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_23081803437.html
- NetSuite — *Defining Cost Versions* · *Entering Planned Standard Cost Records*: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N2202327.html · https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N2202799.html
- NetSuite — *System Notes and System Notes v2* · *Viewing System Notes*: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_160225379741.html · https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_0312034612.html
- Odoo 18 — *Inventory valuation configuration* (`Costing Method`، نصُّ `Standard Price`، أثرُ تعديل `Cost` يدوياً): https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/product_management/inventory_valuation/inventory_valuation_config.html
- Odoo 18 — *Using inventory valuation* (نموذج `Product Revaluation`): https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/product_management/inventory_valuation/using_inventory_valuation.html
- Zoho Inventory — *Inventory Valuation Method* (`FIFO` و`WAC` فقط): https://www.zoho.com/us/inventory/kb/items/item-inventory-evaluation.html
- Oracle Cost Management — *Inventory Standard Cost Variances* (تعريفُ PPV): https://docs.oracle.com/cd/A60725_05/html/comnls/us/cst/stdvari.htm
- PeopleSoft — *Calculating and Applying Purchase Price Variance*: https://docs.oracle.com/cd/F46511_01/fscm92pbr41/eng/fscm/scem/CalculatingandApplyingPurchasePriceVarianceandExchangeRateVariance-c9fc70.html

### مقروءٌ من مصدرٍ ثانويّ أو محتوى دعم (مُتحقَّقٌ جزئياً — موسوم)

- SAP — *MR21 Price changes and MR22 debiting / crediting materials*، SAP Help Portal (support content): https://help.sap.com/docs/SUPPORT_CONTENT/ficontrolling/3361879100.html
  الصفحةُ لم تُصيَّر عند الجلب المباشر؛ نصُّها وصلني عبر مقتطفات البحث. `mark` و`release`، وقيدُ `price determination 3`، وقيدُ حالة المادة — من هذا المصدر.
- SAP — `price control` S/V وتوصياتُ الاستعمال، و`CKM3 — Material Price Analysis`: من صفحات SAP Learning ومناقشات SAP Community. **لم أفتح صفحةَ app-help رسميةً لأيٍّ منها.**
- **`FI document type PR` لمستند تغيير السعر: غيرُ مُتحقَّق** — ورد في مدوّنات مجتمعٍ فقط. لا يُبنى عليه.
- دوريّاتُ مراجعة المعياريّ وعتباتُ الـ١٠٪ أو الـ٣ أشهر: **أعمدةُ رأيٍ استشاريّ ومدوّناتُ بائعين**، لا وثائقُ منتَجٍ ولا معيارٌ محاسبيّ. أُوردت في §3 موسومةً بذلك.

### استنتاجٌ لا قراءة

- أنّ سجلَّ إعادة التقييم في Odoo يحمل هويّةَ منشئه: **استنتاجٌ** من بنية Odoo العامّة، لا مقروءٌ من الصفحة.
- أنّ `Value Entry` في BC يحمل حقلَ مستخدم: **لم أقرأه**؛ المُتحقَّقُ فقط أنّ إعادة التقييم قيدٌ مرحَّلٌ مؤرَّخ.
- التوصيةُ في §0 وتسميةُ «فجوةُ الشراء عن المرجع» في §3: **تصميمُنا نحن** مبنيّاً على الأنماط أعلاه، لا خاصّيةٌ منقولة عن بائع.
