# طلبيةٌ بلا سعر وعروضٌ تُقارَن — كيف تنمذجها الأنظمة المهنية

بحثٌ مرجعيّ للقضية [#90](https://github.com/thabet-toma/ktra2/issues/90) ضمن خريطة [#89](https://github.com/thabet-toma/ktra2/issues/89).
السؤال: كيف تُنمذَج دورة «طلبٌ بكميات ← عروضُ موردين ← مقارنة ← التزام»، وأيّ الخيارين نختار لأنفسنا.

---

## منهج البحث ومستوى الثقة

اعتُمدت **مصادر أولية من المنتِج نفسه** حصراً: توثيق Odoo الرسمي و**شفرته المصدرية** على مستودعه، وMicrosoft Learn، وOracle NetSuite Help Center، وتوثيق Zoho الرسمي. لم يُستشهَد بأي مدوّنة أو صفحة استشارية.

**تحفّظ يجب أن يُقال:** بوابة `help.sap.com` تطبيقُ صفحةٍ واحدة يُبنى محتواه بالـJavaScript، فلم يتمكّن العميل من قراءة نصّ أيٍّ من صفحاتها (جُرِّبت صفحات S/4HANA وAriba وSAP Sourcing وملفّ PDF رسمي — كلّها أعادت العنوان بلا جسد). لذلك **قسم SAP أدناه محدود ومعلَّم صراحةً**، ولا يُبنى عليه قرار. الأنظمة الأربعة الأخرى موثَّقة بنصٍّ حرفيّ.

---

## 1) التسميات وحدودها: هل الـRFQ سجلٌّ مستقل أم حالةٌ مبكّرة من الـPO؟

الجواب **منقسم انقساماً حاداً**، وهذا أهمّ ما في البحث كلّه:

### Odoo — نفس السجلّ، حالةٌ مبكّرة (وله ثمن)

توثيق Odoo يقول عن الـRFQ إنها «RFQs are documents companies send to vendors requesting product pricing» ([Odoo 18 — Requests for quotation](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/rfq.html))، وأنّ «Once an RFQ is confirmed, it creates a PO» (المصدر نفسه).

لكن الشفرة تحسم أنّه **ليس** إنشاءَ سجلٍّ جديد بل انتقالَ حالة. في `addons/purchase/models/purchase_order.py` فرعِ 18.0:

```python
_name = "purchase.order"
_description = "Purchase Order"

state = fields.Selection([
    ('draft', 'RFQ'),
    ('sent', 'RFQ Sent'),
    ('to approve', 'To Approve'),
    ('purchase', 'Purchase Order'),
    ('done', 'Locked'),
    ('cancel', 'Cancelled')
], string='Status', ...)
```
([odoo/odoo @ 18.0 — purchase_order.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase/models/purchase_order.py))

فـ«RFQ» عند Odoo ليست كياناً، بل **تسمية عرضٍ لقيمة `draft`** في جدول أوامر الشراء نفسه. لا جدول، لا نموذج، لا ترقيم مستقلّ.

**وما ثمن ذلك؟** ثلاثة أثمان ظاهرة في توثيق Odoo وشفرته:

1. **كلّ استعلامٍ يجب أن يُصفّي بالحالة، وإلا خلط الطلبَ بالالتزام.** تقرير Purchase Analysis يعرض افتراضياً أوامرَ الشراء **والـRFQ معاً**، ويلزمه مُرشِّح صريح للفصل بينهما ([Odoo 18 — Purchase Analysis report](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/advanced/analyze.html)). أي أن عبء التمييز انتقل من قاعدة البيانات إلى كل مستهلِك للبيانات — وهذا ديْنٌ يُدفَع في كل تقرير جديد إلى الأبد.
2. **السعر إلزاميّ حتى في مرحلة السؤال.** انظر القسم 3.
3. **احتاجت Odoo إلى اختراع نموذجٍ تقنيّ إضافيّ لأنّ الأب الطبيعي غير موجود.** انظر القسم 2 — وهو أبلغ دليل على أنّ إعادة الاستعمال لم تكن مجّانية.

### Dynamics 365 — سجلّ مستقلّ تماماً، بل **سجلّان**

«The RFQ case is the base document that you use to issue an RFQ» ([Microsoft Learn — Requests for quotation (RFQs) overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/request-quotations)). و«An RFQ journal is generated for each vendor» (المصدر نفسه).

فالبنية عند مايكروسوفت ثلاثيةٌ صريحة: **قضية طلب (RFQ case)** ← **ردّ لكلّ مورد (RFQ reply / journal)** ← **مستند التزام**. والالتزام ليس نوعاً واحداً: «Transfer bids that you accept to a purchase order, purchase agreement, or purchase requisition» (المصدر نفسه).

### NetSuite — سجلّ مستقلّ، والالتزام عقدُ شراء

«a request you send to one or more vendors» ([NetSuite — Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_4189559896.html)). والـRFQ نوع سجلٍّ قائم بذاته، تلزمه ميزتان مُفعَّلتان (Purchase Contracts + Request for Quotes)، وله فترة مناقصة بتاريخَي فتحٍ وإغلاق.

### Zoho — الـRFQ خارج المنتج المحاسبي أصلاً

هذه ملاحظة عملية تخصّنا: **لا يوجد RFQ في Zoho Books ولا Zoho Inventory.** «Quotes» في Zoho Books عرضُ سعرٍ للزبون لا للمورد. الـRFQ موجودة في منتجٍ منفصل هو **Zoho Procurement**: «Request for Quotes are documents organizations send to vendors detailing the required items» ([Zoho Procurement — Request for Quotes Overview](https://www.zoho.com/us/procurement/help/request-for-quotes/overview/))، وله دورةُ حياةٍ خاصّة به: `Draft, Awaiting Approval, Recalled, Approved, Rejected, Published, Awarded, Canceled, Closed` (المصدر نفسه).

**الدلالة:** حتى Zoho — وهي الأقرب إلينا حجماً وفلسفةً — لم تُقحِم المناقصة في دفتر الفواتير، بل جعلتها وحدةً مستقلّة. مَن أدخلها في نفس سجلّ الـPO هو Odoo وحدها.

---

## 2) تعدّد الموردين: ما الكيان الذي يجمع العروض؟

### Odoo: نموذجٌ تقنيّ اضطراريّ اسمه `purchase.order.group`

هنا الاكتشاف الحاسم. حين أرادت Odoo دعم «Alternative RFQs» لم تجد في نموذجها أباً يجمع العروض — لأنّ الـRFQ ليست إلا صفَّ PO — فاضطرّت إلى إنشاء نموذجٍ فارغ وظيفته الوحيدة الجمع. في `addons/purchase_requisition/models/purchase.py`:

```python
class PurchaseOrderGroup(models.Model):
    _name = 'purchase.order.group'
    _description = "Technical model to group PO for call to tenders"
```

وربطه بأمر الشراء:

```python
purchase_group_id = fields.Many2one('purchase.order.group')

alternative_po_ids = fields.One2many(
    'purchase.order', related='purchase_group_id.order_ids', readonly=False,
    domain="[('id', '!=', id), ('state', 'in', ['draft', 'sent', 'to approve'])]",
    string="Alternative POs", check_company=True,
    help="Other potential purchase orders for purchasing products")
```
([odoo/odoo @ 18.0 — purchase_requisition/models/purchase.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase_requisition/models/purchase.py))

انتبه إلى وصف النموذج بلسان Odoo نفسها: «Technical model to group PO for call to tenders». كلمة **technical** اعترافٌ صريح بأنّ هذا ليس كياناً من الدومين، بل رقعةٌ لسدّ فجوةٍ خلقها قرارُ إعادة الاستعمال. ولاحظ أنّ حقل البدائل يحمل شرطاً على الحالة `state in ['draft','sent','to approve']` — أي أنّ حتى تعريف «مَن هو بديل» صار يتطلّب تصفيةً بالحالة، لأنّ الجدول يخلط المرحلتين.

ولاحظ كذلك أنّ **Purchase Agreement ليست هي الجامع.** في Odoo 18 صار نوع الاتفاقية محصوراً في:

```python
requisition_type = [('blanket_order', 'Blanket Order'), ('purchase_template', 'Purchase Template')]
```
([odoo/odoo @ 18.0 — purchase_requisition.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase_requisition/models/purchase_requisition.py))

فلا وجود لنوع «call for tender» بين أنواع الاتفاقيات؛ انتقلت المناقصة كلياً إلى آلية البدائل. أمّا الاتفاقية (Blanket Order) فغرضها مختلف تماماً: «long-term purchase agreements ... to deliver products on a recurring basis with predetermined pricing» ([Odoo 18 — Blanket orders](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/blanket_orders.html)) — أي سعرٌ **مُتّفَقٌ عليه سلفاً**، وهو نقيض حالتنا لا حلٌّ لها.

**شاشة المقارنة عند Odoo:** بعد ورود الردود «the product lines from each RfQ can be compared» ([Odoo 18 — Call for tenders](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/calls_for_tenders.html)). الشاشة اسمها *Compare Order Lines*، تُجمِّع افتراضياً حسب المنتج، فتظهر تحت كلّ صنفٍ عروضُ الموردين المختلفة صفوفاً متجاورة مع أرقام مستنداتها، ولكلّ صفٍّ زرُّ اختيار. وعند تأكيد أحد العروض يسأل النظام إن كان يريد إلغاء البدائل أم إبقاءها.

### Dynamics 365: الجامع هو «القضية»، والمقارنة صفحةٌ قائمة بذاتها

القضية (RFQ case) هي الأب، ويتولّد عن إرسالها ردٌّ لكلّ مورد. والمقارنة صفحة رسمية اسمها **Compare replies**، وعليها — إن عُرِّفت معايير تقييم — لوحةُ تنقيط: تظهر الدرجات الكلّية «when you compare the replies on the Compare replies page» ([Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/request-quotations))، ويُقارَن معها «the line price, receipt date, and total price» (المصدر نفسه).

ولمايكروسوفت تفصيلٌ نموذجيّ لطيف يستحقّ الالتفات: للقضية **حالتان لا واحدة** — دنيا وعليا — «The lowest status is the least advanced stage of any line» و«the highest status is the most advanced stage of any line» (المصدر نفسه). لأنّ الأب يجمع أبناءً متفاوتي التقدّم، فحالةٌ واحدة تكذب عليه.

### NetSuite: المقارنة نافذةٌ لكلّ بند

«Click the Compare icon to view a comparison of response details from all vendors» ([NetSuite — Analyzing and Awarding a Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4213373490.html)). والنافذة تعرض لكلّ مورد: متوسّط السعر، وسعر كلّ شريحة، والحدّ الأدنى للشراء، وخصم الإجمالي، وشرط التسليم (Incoterm)، وشروط الدفع.

### Zoho: النشر ثم المزايدة

«you need to publish them» لتمكين الموردين من المشاركة ([Zoho Procurement](https://www.zoho.com/us/procurement/help/request-for-quotes/overview/))، ثم يقدّم كلُّ مورد عرضاً (bid) يُدخِل فيه الكميّة والسعر ورسوم الشحن وتاريخ التسليم.

---

## 3) السعر الفارغ: هل يقبل النموذج سطراً بلا سعر؟

هذا هو الفارق الأوضح بين مَن جعل الـRFQ كياناً ومَن جعلها حالة.

### NetSuite — **نعم، طلبٌ بكميات بلا سعر إطلاقاً**

هذا هو التجسيد الأنقى لِما نريده. المشتري يُدخِل الأصناف و**بنية شرائح الكمية فقط**: «Enter the Number of Pricing Tiers you require for this RFQ»، و«The first tier always starts at zero»، و«Enter the lowest quantity required to be ordered to receive the price on this tier» ([NetSuite — Entering a Request For Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4212822856.html)). **المشتري لا يُدخِل سعراً البتّة**؛ الأسعار حقولٌ يملؤها المورد لاحقاً: «The vendors can access the RFQ to define and submit their pricing» ([NetSuite — Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_4189559896.html)).

### Dynamics 365 — نعم، والسعر مِلكُ الردّ لا مِلكُ الطلب

«you ask vendors to provide the prices and delivery times for the item quantities that you specify» ([Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/request-quotations)). الجملة نفسها تقسم الملكية: **الكميات من عندك، الأسعار من عندهم**. وللمشتري أن يُدخِل قيمةً تقديرية لأغراضه الداخلية ثم **يخفيها عن المورد**، إذ تتيح مايكروسوفت إعداد الحقول الظاهرة في نموذج الردّ لِـ«prevent vendors from seeing data when reviewing bids» (المصدر نفسه).

### Odoo — **لا. السعر إلزاميّ ولا يمكن تركه فارغاً**

```python
price_unit = fields.Float(
    string='Unit Price', required=True, min_display_digits='Product Price', aggregator='avg',
    compute="_compute_price_unit_and_date_planned_and_name", readonly=False, store=True)
```
([odoo/odoo @ 18.0 — purchase_order_line.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase/models/purchase_order_line.py))

`required=True` وعلى نوع `Float` — و`Float` في Odoo لا يقبل NULL ويبدأ بـ`0.0`. أي أن سطر الـRFQ عند Odoo **يحمل صفراً أو سعراً محسوباً** (من قائمة أسعار المورد أو آخر شراء)، ولا يحمل «لا أعرف» أبداً. هذا ثمنٌ مباشر لكون السطر هو نفسه سطرَ أمر الشراء: القيد الذي يحمي الالتزام يُفرَض على مرحلة السؤال.

**والأثر المحاسبي:** لا شيء عند أحد منهم. لا يُنتج الـRFQ قيداً في أيٍّ من هذه الأنظمة — هو مستندٌ تجاريّ لا ماليّ. الأثر الوحيد المذكور أثرٌ **تخطيطيّ لا محاسبيّ**: في Dynamics، حين تكون القضية من نوع أمر شراء تتولّد حركة مخزون بحالة استلامٍ اسمها *Quotation receipt*، و«Only RFQ case lines that have this status are considered when you use a master plan» (المصدر نفسه) — أي أنها تُرى في تخطيط الاحتياج فقط إن أُعِدّ لذلك.

---

## 4) الترسية المجزّأة: صنفٌ لمورد وآخرُ لغيره؟

**الجواب نعم عند الجميع، وهي ميزةٌ صريحة موثَّقة لا حيلةٌ جانبية.**

- **Dynamics 365:** «You can accept some lines in a bid and reject others» و«You can also accept lines from different vendors» ([Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/request-quotations)). ولها تفصيلٌ عمليّ: إن قبلتَ بعض السطور طُلِب منك رفضُ الباقي، فتضغط إلغاءً إن كنتَ تنوي قبول سطورٍ أخرى من مورد آخر.
- **NetSuite:** «your buyer can mark which items are to be purchased from which vendors» ([NetSuite — Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_4189559896.html))، والاختيار يتمّ بنداً بنداً: «click the check mark icon on the line by the vendor» ([NetSuite — Analyzing and Awarding](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4213373490.html)).
- **Odoo:** شاشة *Compare Order Lines* تسمح باختيار كلّ سطرٍ من عرضٍ مختلف؛ فتُنقَل السطور المختارة وتُلغى البدائل.

**وهنا الملاحظة البنيوية الأهمّ لقرارنا:** لأنّ الترسية مجزّأة، فإنّ العلاقة بين مستند الطلب ومستند الالتزام هي **واحد-إلى-متعدّد بالضرورة**. NetSuite تصرّح بذلك بلا لبس: «a purchase contract is created for all line items, one contract per vendor» ([NetSuite — Analyzing and Awarding](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4213373490.html))، و«A buyer can creates one or multiple purchase contracts from a single RFQ» ([NetSuite — Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_4189559896.html)).

طلبٌ واحد ← عدّة التزامات. أيّ نموذجٍ يربط الطلب بالالتزام برابطةِ **واحد-إلى-واحد** يكون قد أغلق باب الترسية المجزّأة قبل أن يُفتَح.

---

## 5) ردّ المورد بنفسه: بوابةٌ يملأ فيها سعره؟

### Dynamics 365 — نعم، وحدةٌ كاملة اسمها Vendor collaboration

«It lets vendors work with purchase orders (POs), invoices, consignment inventory information, and requests for quotation (RFQs)» ([Microsoft Learn — Vendor collaboration with external vendors](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/vendor-collaboration-work-external-vendors)).

**وكيف تُؤمَّن؟** بأربع طبقات موثَّقة:
1. **تفعيلٌ لكلّ مورد على حِدة** — «Before user accounts can be created for an external vendor, you must configure the vendor account» (المصدر نفسه)، عبر حقل `Collaboration activation`.
2. **حسابات مستخدمين مُزوَّدة** لا وصولٌ مجهول، بأدوارٍ أمنية يضبطها المسؤول.
3. **تحكّمٌ صريح برؤية السعر** — «Specify whether the vendor should see price information» (المصدر نفسه)، وهو خيارٌ منفصل لكلّ حساب مورد.
4. **حدودٌ على ما يستطيع المورد تغييره** في مستند الالتزام: «The vendor can't change price information and charges» (المصدر نفسه) — للمورد أن يقترح بملاحظة، لا أن يكتب.

ويُضاف إليها انضباطُ الإصدارات: إن عُدِّلت القضية بعد الإرسال «the existing bid replies are removed so that they can be replaced by updated values» (المصدر نفسه) — أي لا يُقبَل عرضٌ بُني على نسخةٍ قديمة من الطلب.

### NetSuite — نعم، عبر Vendor Center

«A vendor logs in to the Vendor Center» ([NetSuite — Vendor Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4213374003.html)) ليملأ الأسعار والشروط، ثم «The vendor clicks Save to send quote back to buyer» (المصدر نفسه). والضوابط:
- الدعوة بالبريد فقط لموردٍ له جهةُ اتصال صالحة — «only if they have a contact with a valid email address» ([NetSuite — Entering a RFQ](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4212822856.html)).
- التعديل مسموح **حتى تاريخ الإغلاق فقط**: «After the Bid Close Date, the vendor can no longer edit their response» ([NetSuite — Vendor RFQ](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4213374003.html)).
- الأدوار مقلوبة عمداً: «Generally, buyers can only view the form» (المصدر نفسه) — نموذجُ الردّ مِلكُ المورد، والمشتري قارئ.

### Zoho Procurement — نعم، بوابةُ موردٍ ونشرٌ صريح

للموردين بوابةٌ يُقِرّون فيها بالدعوة ثم يقدّمون عروضهم بالكميّة والسعر والرسوم وتاريخ التسليم؛ ولا يصل إليها المورد إلا بعد نشر الطلب.

### Odoo — **لا، ليس في المنتج القياسي**

لا يوجد في توثيق Odoo الرسمي بوّابةُ موردٍ يكتب فيها المورد سعره. بوابة Odoo مبنيّةٌ لطرف الزبون (عروض البيع والفواتير). والدليل العمليّ على الفجوة: متجرُ تطبيقات Odoo نفسه يعجّ بوحداتٍ خارجية غرضها الوحيد سدّ هذا النقص («Portal Purchase RFQ Edit»، «Vendor Portal Management»، «Purchase Order Tender Portal» وغيرها). ما يُباع كإضافةٍ لا يكون موجوداً في الأصل.

---

## جدول الخلاصة

| | Odoo | Dynamics 365 | NetSuite | Zoho Procurement |
|---|---|---|---|---|
| الـRFQ سجلٌّ مستقل؟ | **لا** — حالة `draft` في `purchase.order` | نعم (RFQ case) | نعم (نوع سجلّ خاص) | نعم (منتج منفصل كلياً) |
| جامعُ العروض | `purchase.order.group` — «نموذج تقنيّ» اضطراريّ | القضية نفسها (أبٌ طبيعي) | الـRFQ نفسها | الـRFQ نفسها |
| ردُّ كلّ مورد كيانٌ مستقل؟ | لا — نسخةُ PO كاملة لكلّ مورد | **نعم** (RFQ reply/journal) | **نعم** (Vendor RFQ) | **نعم** (Bid) |
| سطرٌ بلا سعر | **ممنوع** (`required=True`) | مسموح | مسموح (المشتري لا يُدخِل سعراً أصلاً) | مسموح |
| ترسية مجزّأة | نعم | نعم (صراحةً) | نعم (صراحةً) | نعم |
| بوابة مورد قياسية | **لا** | نعم (Vendor collaboration) | نعم (Vendor Center) | نعم |
| علاقة الطلب بالالتزام | 1→كثير (عبر البدائل) | 1→كثير | **1→كثير صراحةً** (عقد لكلّ مورد) | 1→كثير |

**النمط المشترك بين الثلاثة التي جعلتها كياناً** (مايكروسوفت، أوراكل، زوهو) واحدٌ لا يتغيّر:

> **طلبٌ واحد (كميات) ← ردٌّ مستقلّ لكلّ مورد (أسعار) ← مقارنة على مستوى البند ← عدّة مستندات التزام.**

وOdoo وحدها شذّت عن هذا النمط، ودفعت ثمنه: نموذجاً تقنيّاً زائداً، وسعراً إلزاميّاً في مرحلة السؤال، وتصفيةً بالحالة في كلّ تقرير، وغيابَ بوابةِ المورد.

---

## ما يصلح لنا وما لا يصلح

### حالتنا الراهنة (محقَّقة من الشفرة لا من الذاكرة)

- `logistics/models.py` (`SupplierQuotationLine`): `unit_price` غير قابلٍ للفراغ، وعليه قيدٌ `supplier_quote_line_price_gte_zero`. فسطرٌ بلا سعر **مستحيلٌ اليوم** — أقصى ما يمكن كتابته صفرٌ يكذب.
- `logistics/models.py` (`SupplierQuotation`): مورد اختياري بفضل `supplier_draft_name`، وحالاتٌ ثريّة أصلاً (`pending_info`, `under_discussion`, `accepted`, `rejected`, `converted`) — **بنيةٌ ناضجة نصفَ الطريق**.
- `logistics/models.py` (`PurchaseOrder`): `supplier` **إلزاميّ**، و`quotation` علاقةُ **`OneToOneField`**، و`PurchaseOrderLine.product` إلزاميّ.
- الواجهة: `frontend_v2/types/offer.ts` (`offerType`) و`PriceOfferForm.tsx` — النوع يُختار في الشاشة و**لا يُحفَظ في الخادم إطلاقاً**؛ لا وجود لـ`offer_type` على النموذج (ما في `logistics/migrations/0060_migrate_legacy_procurement_documents.py` قراءةٌ لحمولة Firestore قديمة لا حقلٌ حيّ).

**فجوتان صارختان أمام النمط المهنيّ:**
1. `OneToOneField` بين العرض وأمر الشراء **يمنع الترسية المجزّأة بنيوياً**. كلُّ نظامٍ فحصناه يجعلها 1→كثير، وNetSuite تصرّح بعقدٍ لكلّ مورد.
2. لا كيان يجمع عروضاً متعدّدة لطلبٍ واحد — وهو بالضبط ما اضطرّت Odoo لاختراعه بعد فوات الأوان.

### الخيار (أ): سجلّ `PurchaseRFQ` جديد + سطوره

**له:** يحاكي ما استقرّت عليه ثلاثة أنظمة من أربعة. سطرٌ بكميّةٍ بلا سعر يصير طبيعياً لا استثناءً — `unit_price` ببساطة **غير موجود** في `PurchaseRFQLine`، فلا حاجة إلى تخفيف قيدٍ ولا إلى صفرٍ يكذب. الترقيم مستقل، والتقارير لا تحتاج تصفيةً بالحالة أبداً لأنّ الجدولين منفصلان.

**عليه:** جدولان جديدان وهجرة وطبقةُ خدمات وشاشة، ثمّ **ازدواجٌ حقيقيّ** — سيكون لدينا مستندان متشابهان جداً (`PurchaseRFQ` و`SupplierQuotation`) والفرقُ بينهما سطرُ سعرٍ واحد. وهذا ازدواجٌ مكلف في مشروعٍ فيه `logistics` مستوردة من ثماني apps.

**والأخطر:** الخيار (أ) وحده **لا يحلّ المشكلة**. لأنّ الطلب طرفٌ واحد؛ يبقى السؤال: أين تُخزَّن ردودُ الموردين الثلاثة؟ إمّا `SupplierQuotation` يشير إلى `PurchaseRFQ` (وعندها احتجنا الكيانين معاً على أي حال)، أو نصنع `PurchaseRFQResponse` ثالثاً فنكون قد بنينا برجاً من ثلاثة جداول لدورةٍ واحدة.

### الخيار (ب): `SupplierQuotation` بحقل نوعٍ محفوظ + أبٌ يجمع العروض

**له:** يطابق النمط المهنيّ في المكان الذي يهمّ فعلاً. لأنّ التقسيم الذي أجمعت عليه الأنظمة ليس «RFQ مقابل Quotation» بل **«الأب الجامع مقابل ردّ كلّ مورد»** — والردّ عندنا موجودٌ وناضج: `SupplierQuotation` هو تماماً ما تسمّيه مايكروسوفت *RFQ reply* وأوراكل *Vendor Request for Quote*. فما ينقصنا هو **الأب فقط**، لا الابن.

وهو يتجنّب الخطأ الذي وقعت فيه Odoo من الجهة المعاكسة: Odoo أعادت استعمالَ **مستند الالتزام** (`purchase.order`) لتمثيل السؤال — فورثت قيودَ الالتزام (السعر الإلزامي، المورد الإلزامي، خلطُ التقارير). أمّا نحن فسنُعيد استعمال **مستند العرض** (`SupplierQuotation`) الذي هو أصلاً مستندُ استكشاف: مورده اختياريّ، ومنتجه اختياريّ، وحالاته حالاتُ تفاوض. الفرق جوهريّ ومعاكسٌ في الاتجاه.

**عليه (ثمنٌ يجب أن يُدفَع صراحةً):**
- `unit_price` لا بدّ أن يصير `null=True`، ويُستبدل القيد `>= 0` بقيدٍ يقبل NULL. هذا هو **الالتزام الوحيد الحقيقي** في هذا الخيار، وهو تمكينٌ لا تخفيف: NULL تعني «لم يُسأل بعد»، والصفرُ يعني «مجّاناً» — والخلطُ بينهما هو بالضبط ما تدفعه Odoo اليوم.
- يجب أن يُفرَض السعرُ **عند التحويل** لا عند الحفظ: بوابةُ التحويل إلى `PurchaseOrder` ترفض أيّ سطرٍ بسعرٍ فارغ. هذا هو الدرس المستفاد من `task76-serial-guards-m4`: الإلزام مكانه بوابة الترحيل لا مكان الكتابة.
- حقل النوع **يجب أن يُحفَظ** — الوضع الحالي (`offerType` في الواجهة وحدها) هو أسوأ الاحتمالات: تمييزٌ يراه المستخدم ولا تعرفه قاعدة البيانات.

**وهناك تعديلٌ إلزاميّ ثالث لا يخصّ أيّ خيار بعينه:** كسرُ `OneToOneField` بين `PurchaseOrder` و`SupplierQuotation` وجعلها `ForeignKey`. بدونه لا ترسية مجزّأة مهما فعلنا بباقي النموذج.

### التوصية

**الخيار (ب)، بشرط أن يكون الأب كياناً حقيقياً من الدومين لا حقلَ تجميعٍ عابراً.**

أي: طلبُ عروضٍ (`PurchaseRFQ` أو ما نسمّيه) يحمل **الكميات والمواصفات وتاريخ الإغلاق ولا يحمل أسعاراً**، وتحته `SupplierQuotation` واحدٌ لكلّ مورد بحقل نوعٍ محفوظ ورابطٍ إلى الأب. هذا ليس رفضاً للخيار (أ) بقدر ما هو تصحيحٌ لصياغته: الأنظمة المهنية **لم تختر بين الطلب والعرض، بل بَنَت الاثنين** — لكنّها لم تُكرِّر مستند العرض، وهو الاقتصاد الذي يمنحنا إياه الخيار (ب).

الفرق العمليّ بين ما نوصي به وبين الخيار (أ) الكامل: **جدولٌ واحد جديد لا ثلاثة**، ولا ازدواج بين مستندَي عرضٍ متشابهين، وتحتفظ حالاتُ التفاوض الناضجة في `SupplierQuotation` بمكانها.

**وما لا يصلح لنا صراحةً:**
- **نمط Odoo** — إعادة استعمال مستند الالتزام لتمثيل السؤال. ثمنُه موثَّقٌ أعلاه بلسان Odoo نفسها (نموذجٌ «تقنيّ» اضطراريّ، وسعرٌ إلزاميّ، وتصفيةٌ بالحالة في كل تقرير). ولا سبب لنا لنكرّر خطأً مشخَّصاً.
- **Blanket Order / اتفاقية الإطار** — حلٌّ لمشكلةٍ أخرى تماماً (سعرٌ متّفَقٌ عليه سلفاً لتوريدٍ متكرّر)، لا لمشكلة السعر المجهول.
- **بوابةُ موردٍ خارجية في هذه المرحلة** — الأنظمة الثلاثة التي تملكها تدفع ثمناً أمنياً كبيراً (تزويدُ حسابات، أدوار، تحكّمٌ بكلّ حقلٍ مرئيّ، إبطالُ العروض عند تعديل الطلب). البوابة تُبنى **بعد** أن يستقرّ النموذج لا معه؛ والنموذج الموصى به لا يمنعها لاحقاً لأنّ ردّ كلّ مورد كيانٌ مستقلّ أصلاً.

---

## SAP — قسمٌ ناقص بإقرار

لم أستطع قراءة نصّ أيّ صفحةٍ من `help.sap.com` (تطبيقُ صفحةٍ واحدة يُبنى بالـJavaScript؛ جُرِّبت صفحات S/4HANA وAriba وSAP Sourcing وBusiness Network وملفٌّ PDF رسميّ). **فلا أنقل عن SAP اقتباساً حرفياً ولا أبني على شيءٍ منها.**

ما أستطيع قوله بأمان هو أنّ SAP تملك المفاهيم المقابلة، وهذه عناوين صفحاتها الرسمية لمن يتابع البحث بمتصفّح:
- [SAP S/4HANA — Request for Quotation](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/91af7f8d3acd47da90d33aaacfcd0d59/3f674082aecc45709f0f87594a60926d.html)
- [SAP Sourcing & CLM — RFx](https://help.sap.com/docs/SAP_SOURCING_AND_SAP_CONTRACT_LIFECYCLE_MANAGEMENT/93d751e10a9042bebb776fc42aba0ea1/4a00320adc5f42f3a2ed96407a1e5d15.html)
- [SAP — RFQ and Award Integration with SAP Ariba Sourcing](https://help.sap.com/docs/strategic-sourcing/rfq-and-award-integration-with-sap-ariba-sourcing/about-sap-erp-rfq-process)
- [SAP Business Network — Contents of RFQ Event and Supplier's Quote](https://help.sap.com/docs/business-network-for-procurement/quote-automation-configuration-and-integration/contents-of-rfq-event-and-supplier-s-quote)

**ولا يُغيّر هذا النقصُ التوصية**: الأنظمة الأربعة المقروءة أصلاً منقسمةٌ ثلاثةً إلى واحد لصالح فصل الطلب عن العرض، والدليل الأقوى على ثمن نمط Odoo مأخوذٌ من شفرة Odoo نفسها لا من مقارنةٍ بغيرها.

---

## المصادر

**Odoo** — [Requests for quotation](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/rfq.html) · [Call for tenders](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/calls_for_tenders.html) · [Blanket orders](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/blanket_orders.html) · [Purchase Analysis report](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/advanced/analyze.html) · شفرة 18.0: [purchase_order.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase/models/purchase_order.py) · [purchase_order_line.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase/models/purchase_order_line.py) · [purchase_requisition/models/purchase.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase_requisition/models/purchase.py) · [purchase_requisition.py](https://github.com/odoo/odoo/blob/18.0/addons/purchase_requisition/models/purchase_requisition.py)

**Microsoft Dynamics 365** — [Requests for quotation (RFQs) overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/request-quotations) · [Vendor collaboration with external vendors](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/vendor-collaboration-work-external-vendors)

**Oracle NetSuite** — [Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_4189559896.html) · [Entering a Request For Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4212822856.html) · [Analyzing and Awarding a Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4213373490.html) · [Vendor Request for Quote](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4213374003.html)

**Zoho** — [Zoho Procurement — Request for Quotes Overview](https://www.zoho.com/us/procurement/help/request-for-quotes/overview/) · [Zoho Books — Quotes](https://www.zoho.com/us/books/help/quote/)
