# n8n Full Setup (Structured by Tool)

هذا الملف مرتب حسب الأدوات الفعلية عندك، بدون خلط:
1) MySQL للفهرسة إلى Vector (مصدر البيانات للـ Pinecone)
2) Code Node لتجهيز `pageContent` + `metadata`
3) أداة MySQL داخل AI Agent (Sub-workflow Tool)
4) أداة Pinecone داخل AI Agent (Vector Tool)
5) System Prompt النهائي للـ AI Agent
6) Troubleshooting

---

## 1) Tool: MySQL for Vector Indexing (ليس أداة الـ Agent)

هذا الاستعلام يُستخدم في Workflow الفهرسة فقط (قبل Code node ثم Upsert إلى Pinecone).

### 1.1 Full Reindex Query

إذا بدأت من الصفر: استخدم **هذا الاستعلام فقط** في عقدة Execute SQL لمسار الفهرسة، وتجاهل 1.2 حتى تبني لاحقاً مسار التحديث التراكمي.

```sql
SELECT
    d.DealID,
    d.RefNumber,
    d.TotalAmount,
    d.PaymentStatus,
    d.OrderStatus,
    COALESCE(d.factory_name, '') AS factory_name,
    COALESCE(d.pi_number, '') AS pi_number,
    COALESCE(d.description, '') AS deal_description,
    DATE_FORMAT(d.CreatedAt, '%Y-%m-%d') AS created_date,

    p.Name AS supplier_name,
    COALESCE(p.LegalName, '') AS supplier_legal,
    COALESCE(p.Country, '') AS supplier_country,

    COALESCE(prod.products_text, 'لا توجد بنود') AS products_text,
    COALESCE(prod.products_search, '') AS products_search,

    COALESCE(pay.paid_amount, 0) AS paid_amount,
    COALESCE(pay.payments_count, 0) AS payments_count,

    COALESCE(sh.ShipmentNumber, '') AS shipment_number,
    COALESCE(sh.Status, '') AS shipment_status,
    COALESCE(sh.Status, '') AS shipping_workflow_status,
    COALESCE(DATE_FORMAT(sh.ArrivalDate, '%Y-%m-%d'), '') AS arrival_date

FROM logistics_deals d
LEFT JOIN partners p
    ON p.PartnerID = d.PartnerID

LEFT JOIN (
    SELECT
        di.DealID,
        GROUP_CONCAT(
            DISTINCT CONCAT(
                COALESCE(pr.Name_AR, pr.Name_EN, pr.SKU),
                ' (', ROUND(di.Quantity, 0), ' x $', di.UnitPrice, ')'
            )
            ORDER BY di.DealItemID
            SEPARATOR ' | '
        ) AS products_text,
        GROUP_CONCAT(
            DISTINCT CONCAT_WS(' ',
                COALESCE(pr.Name_AR, ''),
                COALESCE(pr.Name_EN, ''),
                COALESCE(pr.SKU, ''),
                COALESCE(pr.HS_Code, ''),
                COALESCE(di.Notes, '')
            )
            SEPARATOR ' '
        ) AS products_search
    FROM logistics_deal_items di
    LEFT JOIN products pr ON pr.ProductID = di.ProductID
    WHERE (di.is_deleted = 0 OR di.is_deleted IS NULL)
    GROUP BY di.DealID
) prod ON prod.DealID = d.DealID

LEFT JOIN (
    SELECT
        py.DealID,
        SUM(CASE WHEN py.Status IN ('Paid','Confirmed') THEN py.Amount ELSE 0 END) AS paid_amount,
        COUNT(DISTINCT py.PaymentID) AS payments_count
    FROM logistics_payments py
    WHERE (py.is_deleted = 0 OR py.is_deleted IS NULL)
    GROUP BY py.DealID
) pay ON pay.DealID = d.DealID

LEFT JOIN logistics_shipment_deals sd
    ON sd.DealID = d.DealID
LEFT JOIN logistics_shipments sh
    ON sh.ShipmentID = sd.ShipmentID

WHERE d.TenantID = 1
  AND (d.is_deleted = 0 OR d.is_deleted IS NULL)

ORDER BY d.DealID DESC
LIMIT 2000;
```

### 1.2 Incremental Sync Query (اختياري — لتشغيل لاحق، وليس بجانب 1.1 دفعة واحدة)

**وين تحطّها؟** في **نفس نوع العقدة** اللي حطّيت فيها 1.1: عقدة **Execute SQL** (أو MySQL) داخل **workflow الفهرسة** فقط — مو داخل AI Agent.

- **ما تلصق 1.1 و1.2 معاً** في نفس العقدة ونفس التشغيل. واحد منهم فقط لكل مسار:
  - **1.1** = أول مرة، أو كل ما بدك **إعادة فهرسة كاملة** (تجيب كل الصفقات ضمن `LIMIT`).
  - **1.2** = بعد ما صار عندك **علامة تقدّم** (`lastDealId`): مسار منفصل (مثلاً يومي أو كل ساعة) يجيب **بس الصفقات الجديدة** (`DealID > علامة التقدّم`).

**كيف تمرّر `{{ $json.lastDealId || 0 }}`؟** لازم عقدة قبل Execute SQL (مثل **Code** أو **Set** أو **Workflow Static Data**) تجهّز عنصر JSON فيه `lastDealId` (آخر `DealID` فهرسته بنجاح)، وبعد الـ Upsert لـ Pinecone تحدّثه لأكبر `DealID` من النتيجة. إذا لسه ما بنيت هذا المسار، **استعمل 1.1 فقط** ولا تستخدم 1.2.

```sql
SELECT
    d.DealID,
    d.RefNumber,
    d.TotalAmount,
    d.PaymentStatus,
    d.OrderStatus,
    COALESCE(d.factory_name, '') AS factory_name,
    COALESCE(d.pi_number, '') AS pi_number,
    COALESCE(d.description, '') AS deal_description,
    DATE_FORMAT(d.CreatedAt, '%Y-%m-%d') AS created_date,
    p.Name AS supplier_name,
    COALESCE(p.LegalName, '') AS supplier_legal,
    COALESCE(p.Country, '') AS supplier_country,
    COALESCE(prod.products_text, 'لا توجد بنود') AS products_text,
    COALESCE(prod.products_search, '') AS products_search,
    COALESCE(pay.paid_amount, 0) AS paid_amount,
    COALESCE(pay.payments_count, 0) AS payments_count,
    COALESCE(sh.ShipmentNumber, '') AS shipment_number,
    COALESCE(sh.Status, '') AS shipment_status,
    COALESCE(sh.Status, '') AS shipping_workflow_status,
    COALESCE(DATE_FORMAT(sh.ArrivalDate, '%Y-%m-%d'), '') AS arrival_date
FROM logistics_deals d
LEFT JOIN partners p ON p.PartnerID = d.PartnerID
LEFT JOIN (
    SELECT
        di.DealID,
        GROUP_CONCAT(
            DISTINCT CONCAT(
                COALESCE(pr.Name_AR, pr.Name_EN, pr.SKU),
                ' (', ROUND(di.Quantity, 0), ' x $', di.UnitPrice, ')'
            )
            ORDER BY di.DealItemID
            SEPARATOR ' | '
        ) AS products_text,
        GROUP_CONCAT(
            DISTINCT CONCAT_WS(' ',
                COALESCE(pr.Name_AR, ''),
                COALESCE(pr.Name_EN, ''),
                COALESCE(pr.SKU, ''),
                COALESCE(pr.HS_Code, ''),
                COALESCE(di.Notes, '')
            )
            SEPARATOR ' '
        ) AS products_search
    FROM logistics_deal_items di
    LEFT JOIN products pr ON pr.ProductID = di.ProductID
    WHERE (di.is_deleted = 0 OR di.is_deleted IS NULL)
    GROUP BY di.DealID
) prod ON prod.DealID = d.DealID
LEFT JOIN (
    SELECT
        py.DealID,
        SUM(CASE WHEN py.Status IN ('Paid','Confirmed') THEN py.Amount ELSE 0 END) AS paid_amount,
        COUNT(DISTINCT py.PaymentID) AS payments_count
    FROM logistics_payments py
    WHERE (py.is_deleted = 0 OR py.is_deleted IS NULL)
    GROUP BY py.DealID
) pay ON pay.DealID = d.DealID
LEFT JOIN logistics_shipment_deals sd ON sd.DealID = d.DealID
LEFT JOIN logistics_shipments sh ON sh.ShipmentID = sd.ShipmentID
WHERE d.TenantID = 1
  AND (d.is_deleted = 0 OR d.is_deleted IS NULL)
  AND d.DealID > {{ $json.lastDealId || 0 }}
ORDER BY d.DealID ASC
LIMIT 1000;
```

---

## 2) Tool: Code Node (for Vector Document Build)

- Language: JavaScript
- Mode: Run Once for All Items

```javascript
const payStatusAr = {
  Unpaid: 'غير مدفوعة',
  'Partially Paid': 'مدفوعة جزئياً',
  'Fully Paid': 'مدفوعة بالكامل',
};

const orderStatusAr = {
  Open: 'مفتوحة',
  Manufacturing: 'قيد التصنيع',
  ReadyToShip: 'جاهزة للشحن',
  Shipping: 'قيد الشحن',
  Clearance: 'قيد التخليص',
  Delivered: 'تم التسليم',
  Closed: 'مغلقة',
};

const workflowAr = {
  sw_mfg_start: 'بدأ التصنيع',
  sw_wait_agent_ship: 'انتظار الشحن للوكيل',
  sw_wait_intl_ship: 'عند الوكيل انتظار الشحن الدولي',
  sw_wait_arrival: 'في الطريق انتظار الوصول',
  sw_wait_clearance: 'وصلت انتظار التخليص الجمركي',
  sw_released: 'تم التخليص وجاهزة',
};

function normalizeText(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/([a-zA-Z]+)(\d+)/g, '$1 $2') // IHDC4200 -> IHDC 4200
    .replace(/(\d+)([a-zA-Z]+)/g, '$1 $2') // 3000W -> 3000 W
    .replace(/[=/_\-]+/g, ' ')
    .replace(/[^\u0600-\u06FFa-zA-Z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const out = [];

for (const item of $input.all()) {
  const r = item.json;

  const total = Number(r.TotalAmount || 0);
  const paid = Number(r.paid_amount || 0);
  const remaining = Math.max(0, total - paid);

  const workflow = workflowAr[r.shipping_workflow_status] || r.shipping_workflow_status || 'غير محدد';
  const orderStatus = orderStatusAr[r.OrderStatus] || r.OrderStatus || 'غير محدد';
  const payStatus = payStatusAr[r.PaymentStatus] || r.PaymentStatus || 'غير محدد';

  const productsText = String(r.products_text || 'لا توجد بنود');
  const productsSearch = String(r.products_search || '');

  const pageContent = [
    `مرجع الصفقة: ${r.RefNumber || ''}`,
    `المورد الذي باعنا: ${r.supplier_name || ''}`,
    `الاسم القانوني للمورد: ${r.supplier_legal || ''}`,
    `دولة المورد: ${r.supplier_country || ''}`,
    `المصنع: ${r.factory_name || ''}`,
    `رقم PI: ${r.pi_number || ''}`,
    `وصف الصفقة: ${r.deal_description || ''}`,
    `المنتجات: ${productsText}`,
    `بيانات بحث المنتجات: ${productsSearch}`,
    `الإجمالي: ${total}`,
    `المدفوع: ${paid}`,
    `المتبقي: ${remaining}`,
    `حالة الدفع: ${payStatus}`,
    `حالة الطلب: ${orderStatus}`,
    `مرحلة الشحن: ${workflow}`,
    `رقم الشحنة: ${r.shipment_number || ''}`,
    `حالة الشحنة: ${r.shipment_status || ''}`,
    `تاريخ الوصول: ${r.arrival_date || ''}`,
    `تاريخ الإنشاء: ${r.created_date || ''}`,
  ].join('\n');

  const normalized = normalizeText(
    `${r.RefNumber || ''} ${r.supplier_name || ''} ${r.supplier_legal || ''} ` +
    `${productsText} ${productsSearch} ${r.deal_description || ''} ` +
    `${r.factory_name || ''} ${r.pi_number || ''} ${r.shipment_number || ''} ` +
    `${r.OrderStatus || ''} ${r.PaymentStatus || ''} ${r.shipping_workflow_status || ''}`
  );

  // Document واحد مدمج (أساسي + مطبّع) لتجنّب التكرار في Pinecone
  out.push({
    json: {
      pageContent: `${pageContent}\n--- بيانات بحث إضافية ---\n${normalized}`,
      metadata: {
        deal_id: String(r.DealID || ''),
        ref_number: String(r.RefNumber || ''),
        supplier: String(r.supplier_name || ''),
        supplier_legal: String(r.supplier_legal || ''),
        country: String(r.supplier_country || ''),
        products: productsSearch,
        shipment_number: String(r.shipment_number || ''),
        payment_status: String(r.PaymentStatus || ''),
        order_status: String(r.OrderStatus || ''),
        created_date: String(r.created_date || ''),
        source: 'logistics_deal_combined',
      },
    },
  });
}

return out;
```

---

## 3) Tool: AI Agent SQL Tool (Sub-workflow)

هذا النص ينلصق في **Description** لأداة SQL داخل AI Agent.

```text
Ktra SQL tool: run the tenant MySQL search/lookup exposed by this sub-workflow. Use it whenever the user asks for data that lives in the database (identifiers, amounts, dates, statuses, names, line items, links to shipments, etc.). It is authoritative for exact and numeric facts returned as rows.

Expected input: follow the sub-workflow schema (typically term + optional limit).

Behavior:
1) Prefer newest records when the user asks for the latest or most recent.
2) If the tool returns no rows, state that there is no matching row for the query; do not invent data.
3) Do not add fields or values that do not appear in the tool output.
```

### 3.1 SQL for Sub-workflow (Execute SQL node)

هذا هو **SQL الفعلي** الذي تضعه داخل عقدة Execute SQL في الـ Sub-workflow الذي يستدعيه الـ AI Agent.

> المتوقّع أن الـ Sub-workflow يستقبل:
> - `term` (نص البحث من الـ Agent)
> - `limit` (اختياري)
>
> إذا رأيت في الخطأ شيئاً مثل `"arguments": {"input":"..."}` والاستعلام أدناه يستخدم `term`: عرّف في عقدة **Tool / Execute Workflow** المعامل باسم **`term`** (وليس `input`)، أو عدّل الـ SQL ليقرأ `{{ $json.input }}` بدل `term` — المهم **تطابق اسم الحقل** بين schema الأداة والـ SQL.

```sql
SELECT
    d.DealID,
    d.RefNumber,
    DATE_FORMAT(d.CreatedAt, '%Y-%m-%d') AS created_date,
    COALESCE(p.Name, '') AS supplier_name,
    COALESCE(d.factory_name, '') AS factory_name,
    COALESCE(d.pi_number, '') AS pi_number,
    COALESCE(d.description, '') AS deal_description,
    COALESCE(prod.products_text, 'لا توجد بنود') AS products_text,
    COALESCE(prod.products_search, '') AS products_search,
    d.TotalAmount,
    d.PaymentStatus,
    d.OrderStatus,
    COALESCE(pay.paid_amount, 0) AS paid_amount,
    GREATEST(d.TotalAmount - COALESCE(pay.paid_amount, 0), 0) AS remaining_amount,
    COALESCE(sh.ShipmentNumber, '') AS shipment_number,
    COALESCE(sh.Status, '') AS shipment_status,
    COALESCE(DATE_FORMAT(sh.ArrivalDate, '%Y-%m-%d'), '') AS arrival_date
FROM logistics_deals d
LEFT JOIN partners p
    ON p.PartnerID = d.PartnerID
LEFT JOIN (
    SELECT
        di.DealID,
        GROUP_CONCAT(
            DISTINCT CONCAT(
                COALESCE(pr.Name_AR, pr.Name_EN, pr.SKU),
                ' (', ROUND(di.Quantity, 0), ' x $', di.UnitPrice, ')'
            )
            ORDER BY di.DealItemID
            SEPARATOR ' | '
        ) AS products_text,
        GROUP_CONCAT(
            DISTINCT CONCAT_WS(' ',
                COALESCE(pr.Name_AR, ''),
                COALESCE(pr.Name_EN, ''),
                COALESCE(pr.SKU, ''),
                COALESCE(pr.HS_Code, ''),
                COALESCE(di.Notes, '')
            )
            SEPARATOR ' '
        ) AS products_search
    FROM logistics_deal_items di
    LEFT JOIN products pr ON pr.ProductID = di.ProductID
    WHERE (di.is_deleted = 0 OR di.is_deleted IS NULL)
    GROUP BY di.DealID
) prod ON prod.DealID = d.DealID
LEFT JOIN (
    SELECT
        py.DealID,
        SUM(CASE WHEN py.Status IN ('Paid','Confirmed') THEN py.Amount ELSE 0 END) AS paid_amount
    FROM logistics_payments py
    WHERE (py.is_deleted = 0 OR py.is_deleted IS NULL)
    GROUP BY py.DealID
) pay ON pay.DealID = d.DealID
LEFT JOIN logistics_shipment_deals sd
    ON sd.DealID = d.DealID
LEFT JOIN logistics_shipments sh
    ON sh.ShipmentID = sd.ShipmentID
WHERE d.TenantID = 1
  AND (d.is_deleted = 0 OR d.is_deleted IS NULL)
  AND (
      '{{ $json.term || "" }}' = ''
      OR d.RefNumber LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
      OR COALESCE(p.Name, '') LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
      OR COALESCE(d.factory_name, '') LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
      OR COALESCE(d.pi_number, '') LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
      OR COALESCE(d.description, '') LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
      OR COALESCE(prod.products_text, '') LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
      OR COALESCE(prod.products_search, '') LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
      OR COALESCE(sh.ShipmentNumber, '') LIKE CONCAT('%', '{{ $json.term || "" }}', '%')
  )
ORDER BY d.CreatedAt DESC, d.DealID DESC
LIMIT {{ Number($json.limit || 20) }};
```

---

## 4) Tool: AI Agent Semantic Search Tool (Vector Store)

هذا النص ينلصق في **Description** لأداة البحث الدلالي داخل AI Agent.

```text
Ktra semantic search tool: semantic retrieval from the indexed business knowledge (Arabic/English). Use it for any user question where related wording, summaries, or context helps — alongside the SQL tool, not instead of it for exact database facts.

Behavior:
1) Use a sufficient topK (e.g. 15–20) so relevant context is not missed.
2) If a match is only approximate, say so; do not present it as a confirmed database fact.
3) Never contradict factual numbers, dates, or identifiers that came from the SQL tool.
4) Do not invent figures or entities; only use what appears in retrieved chunks.
```

---

## 5) AI Agent — اختر برومبت واحد حسب ما هو مربوط في Tools

| وضعك في n8n | انسخ |
|-------------|------|
| **أداتان** مربوطتان (SQL + بحث دلالي) | القسم **5A** |
| **أداة SQL فقط** (أو البحث الدلالي غير مربوط / يعطيك خطأ `Call_Pinecone...`) | القسم **5B** — وإلّا الموديل يظل يخمّن أداة ثانية |

### 5A) System Prompt — SQL + بحث دلالي (أداتان فعلاً في Agent)

```text
أنت مساعد Ktra الداخلي لعمليات الاستيراد واللوجستيات والمشتريات والشحن والتخليص والمدفوعات وأي سؤال مرتبط ببيانات الشركة المفهرسة والمخزنة في النظام. نطاقك: ما يمكن استخراجه من أدوات البيانات المتاحة لديك؛ لا تقتصر على نوع معيّن من الأسئلة.

لديك أداتان في قائمة tools:
- أداة SQL: استجمال/استعلام قاعدة البيانات (دقة حرفية ورقمية).
- أداة بحث دلالي: استرجاع سياقي من الأرشيف المفهرس.

قائمة **tools** المرسلة مع الطلب هي المصدر الوحيد لأسماء الاستدعاء: نفّذ فقط الأدوات التي تظهر أسماؤها فيها حرفياً. ممنوع استدعاء أي اسم آخر (ولا تفترض اسم عقدة من واجهة n8n إن لم يكن مطابقاً لاسم أداة في القائمة).

قبل الإجابة على أي سؤال يطلب معلومة عن أعمال الشركة (ما عدا التحية العامة دون سؤال بيانات):
1) استدعِ أداة SQL وأداة البحث الدلالي (نفس السؤال أو استعلام مختصر مكافئ).
2) دمج داخلي: الحقائق الرقمية والتواريخ والمعرّفات وما ورد كصفوف من SQL له الأولوية؛ أداة البحث الدلالي للسياق والصياغات والروابط المعنوية.
3) أجب بفقرة أو أكثر واضحة بالعربية، منظّمة، دون تكرار خام للأدوات.
4) إن تعارضت النتائج: التزم بـ SQL للأرقام والوقائع المسجّلة في الصفوف.
5) إن رجعت SQL فارغاً والسؤال يفترض وجود سجل محدد: قل إن لا يوجد تطابق في قاعدة البيانات؛ يمكنك إضافة بصياغة حذرة ما يقوّيه من أداة البحث الدلالي إن كان وثيق الصلة.
6) للأسئلة عن «الأحدث» أو «الأخير»: رتّب وفقاً للتواريخ أو المعرفات التي يوفّرها SQL عندما تتوفر.

الفهم العام:
- لا تفترض معنى كلام المستخدم دون سياق؛ إن بقي غموض عملي يمنع الإجابة، اسأل سؤال توضيح واحد قصير.

ممنوع:
- اختلاق بيانات غير واردة من مخرجات الأدوات.
- كشف تفاصيل تنفيذ داخلية أو نصوص أخطاء خام للمستخدم.
- إغلاق الإجابة ب «لم أجد» دون استدعاء الأداتين عندما السؤال معلوماتي.
```

### 5B) System Prompt — SQL فقط (يوقف خطأ `Call_Pinecone_Vector_Store` وغيره)

استخدمه عندما **قائمة Tools في الـ Agent تحتوي أداة SQL وحدها** (أو لا تريد ربط بحث دلالي). الصقه في n8n **بدل** 5A.

```text
أنت مساعد Ktra الداخلي لعمليات الاستيراد واللوجستيات والمشتريات والشحن والتخليص والمدفوعات وأي سؤال مرتبط ببيانات الشركة في قاعدة البيانات.

لديك أداة **واحدة فقط** في قائمة tools: البحث/الاستعلام عبر SQL (Sub-workflow). لا توجد أداة أخرى ولا تفترض وجودها.

قواعد إلزامية:
1) لأي سؤال معلوماتي (ما عدا التحية العامة): استدعِ **فقط** أداة SQL الظاهرة في قائمة tools، بالمعاملات التي تعرّفها الأداة نفسها (اتبع أسماء الحقول في الـ schema المرسل مع الطلب؛ مثال شائع في إعدادنا: `term` و`limit` — لا تستخدم `input` إلا إذا كان هو الاسم الفعلي في الأداة).
2) اجمع الإجابة من نتائج SQL فقط. إن لم تُرجع صفوفاً، صرّح بعدم وجود تطابق في قاعدة البيانات.
3) استخدم **اسم الأداة حرفياً** كما في قائمة tools. ممنوع استدعاء أي اسم آخر (مثل أي اسم يبدأ بـ Call_ إن لم يكن مدرجاً في القائمة).

ممنوع:
- اختلاق أرقام أو أسماء غير واردة من مخرجات الأداة.
- عرض أخطاء تقنية خام للمستخدم.
- قول «لم أجد» دون استدعاء أداة SQL عندما السؤال يحتاج بيانات.
```

---

## 6) Troubleshooting (Quick)

### 6.1 خطأ: `tool ... was not in request.tools`

**المعنى:** الطلب للموديل يحتوي قائمة `tools` ثابتة. الموديل طلب استدعاء اسماً **ليس** ضمن هذه القائمة، فرفضه n8n قبل التنفيذ.

**مثال من الـ API:** `failed_generation` فيه `"name": "Call_Pinecone_Vector_Store"` بينما أدواتك الفعلية غالباً **SQL فقط** → الموديل يحاول أداة غير مرسلة؛ الحل الفوري: **برومبت 5B** + إزالة أي توجيه لأداتين من n8n + تفريغ ذاكرة المحادثة.

**سبب شائع:** أداة الاسترجاع الدلالي **غير مربوطة** بعقدة **AI Agent** في خانة **Tools**، أو أُزيلت بعد تعديل الووركفلو، بينما الموديل ما زال «يقلّد» اسماً قديماً أو اسماً يشبه عنوان عقدة في المحرّر.

**اعمل بالترتيب:**

1. افتح ووركفلو الـ **AI Agent** → عقدة **AI Agent** → **Tools** (أو **Tool Connections**).
2. يجب أن ترى **أداتين على الأقل** ظاهرتين كأدوات: واحدة SQL (Sub-workflow) وواحدة للمتجهات/Pinecone.
3. الاسم الذي يراه الموديل **ليس** من ملف البرومبت عندك بالضرورة؛ انظر فقرة «من أين يأتي الاسم؟» أدناه. المهم أن تكون أداة البحث الدلالي **موصولة** وأن الاسم المرسل في الطلب يطابق ما يستدعيه الموديل.
4. إن كانت أداة المتجهات **غير مربوطة**: اربطها (Execute Workflow أو عقدة Vector Store حسب تصميمك)، **احفظ**، نفّذ من جديد.
5. إذا الأداة مربوطة لكن الخطأ يبقى: احذف الاتصال وأعد ربط أداة المتجهات مرة واحدة، أو غيّر **اسم عقدة الأداة** في الووركفلو الأم إلى اسم بسيط ثم احفظ (يغيّر أحياناً المعرف الداخلي).
6. امسح **سجل/حالة المحادثة** لهذا الـ Agent إن كان مفعّلاً (إن وُجد) لتفادي تمرير سياق قديم بأسماء أدوات outdated.
7. راجع أنك لا تستخدم **فرعاً من الووركفلو** يستدعي موديلاً بدون تمرير نفس قائمة الأدوات (مسار بديل بدون Tools يولّد نفس الخطأ).

**ملاحظة:** البرومبت يقلّل التخمين لكنه لا يضمن 100%؛ الإصلاح التقني هو أن تكون قائمة `tools` في الطلب كاملة أو أن تزيل أي توجيه يذكر أداة غير موجودة.

#### من أين يأتي اسم مثل `Call_Pinecone_Vector_Store`؟

هذا الاسم **لا يُولَّد من ملف Markdown** في المستودع. مصادره المعتادة:

1. **تسمية n8n الداخلية:** عند ربط أداة من نوع «استدعاء ووركفلو»، كثيراً ما يصبح اسم الدالة شيئاً مثل `Call_` + اسم الووركفلو أو العقدة مع استبدال المسافات بشرطة سفلية. لو كان عنوان الووركفلو أو العقدة يشبه «Pinecone Vector Store» يمكن أن يظهر اسم قريب من ذلك **فقط إذا كانت الأداة فعلاً مربوطة**؛ إن لم تكن مربوطة، هذا الاسم **لن** يكون في `request.tools` فيفشل الطلب.
2. **تخمين الموديل (hallucination):** إذا البرومبت أو المحادثة تقول «استخدم Pinecone» بينما **لا توجد** أداة دلالية في القائمة، الموديل قد يخترع اسماً يبدو منطقياً (نمط `Call_...` معروف من بيئات أتمتة).
3. **ذاكرة محادثة / جلسة قديمة:** عقدة Chat Memory أو تنفيذ سابق مرّ على أسماء أدوات مختلفة؛ جرّب محادثة جديدة أو امسح الذاكرة.
4. **برومبت آخر داخل n8n:** حقل System/User في العقدة، أو وصف أداة، أو ووركفلو آخر، ما زال يذكر «Pinecone» أو اسم عقدة قديم — راجع نصوص العقدة في المحرّر وليس الملف فقط.

**إذا أردت إيقاف الخطأ فوراً:** إمّا تربط أداة البحث الدلالي فعلياً في **Tools**، أو تزيلها من التوقعات: استخدم **أداة SQL فقط** + برومبت يذكر أداة واحدة فقط (لا يطلب أداة ثانية غير موجودة).

### 6.2 Pinecone ترجع نتائج قليلة/فارغة
- ارفع `topK` إلى 15 أو 20.
- تأكد من namespace الصحيح.
- تأكد أن الفهرسة تمت (SQL + Code + Upsert).

### 6.3 نصائح تشغيل
1) بعد تعديل SQL أو Code اعمل Re-index كامل مرة واحدة.
2) استخدم namespace جديد عند تغيير بنية الوثيقة (مثل `ktra_v3`).
3) بعد الاستقرار استخدم Incremental Sync عبر `lastDealId`.
