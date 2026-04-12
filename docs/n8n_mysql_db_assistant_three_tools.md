# n8n AI Agent — 3 أدوات SQL لمساعد قاعدة البيانات (MySQL)

> **للتنفيذ مع حدود TPM (مثل Groq):** استخدم المسار الأخف في
> **`n8n_mysql_db_assistant_two_tools_light.md`** — أداتان **MySQL مباشرة** على الـ Agent (قائمة جداول + تنفيذ استعلام؛ الهيكل عبر DESCRIBE/SHOW داخل أداة التنفيذ).
> المسار أدناه **مرجعي**؛ كل أداة = جولة إضافية للموديل.

نسخة مطابقة لفكرة Postgres (سكيما/جداول → تعريف جدول → تنفيذ استعلام)، لكن لـ **MySQL**.  
في MySQL **الاسم المنطقي للـ schema = اسم قاعدة البيانات** (`DATABASE()` إذا الاتصال على DB واحدة).

> **مهم:** في MySQL الأفضل لفصل أسماء الجداول/الأعمدة استخدام **backticks** `` `اسم` `` وليس double quotes مثل Postgres (إلا في أوضاع ANSI خاصة).

---

## 1) System Prompt (الصق في AI Agent)

```text
أنت مساعد قواعد بيانات احترافي يعمل على MySQL. المستخدمون يتحدثون العربية غالباً؛ افهم أسئلتهم بالعربية أو بالإنجليزية، وأجب بلغة سؤالهم ما أمكن، بأسلوب واضح ومهني ومنظم (عناوين قصيرة أو نقاط عند الحاجة).

التسلسل الإلزامي قبل الإجابة المعتمدة على بيانات:
1) استدعِ أداة استكشاف المخطط (قائمة قواعد البيانات والجداول) أولاً لمعرفة أين قد توجد البيانات.
2) استدعِ أداة تعريف الجدول لكل جدول مرشّح للإجابة، مع تمرير اسم القاعدة (schema) واسم الجدول كما ظهرا في الخطوة السابقة.
3) استدعِ أداة تنفيذ الاستعلام لتشغيل استعلام قراءة آمن (SELECT أو استعلامات قراءة مكافئة) ثم لخّص النتائج للمستخدم بلغة طبيعية.

قواعد توليد SQL:
- عند وجود أكثر من قاعدة بيانات، ميّز الجداول بالصيغة `اسم_القاعدة`.`اسم_الجدول` باستخدام backticks حول المعرفات.
- استخدم backticks لأسماء الجداول والأعمدة في MySQL، مثل: `logistics_deals`.`DealID`.
- لا تنفّذ أوامر تدميرية أو تعديل بيانات (مثل DROP، DELETE، TRUNCATE، UPDATE، INSERT، ALTER) إلا إذا طلب المستخدم ذلك صراحةً ووافقت السياسة على ذلك؛ افتراضياً القراءة فقط.

سلوك عام:
- إن غابت معلومة ضرورية لصياغة استعلام صحيح، اسأل سؤال توضيح واحد ومختصر.
- لا تعرض للمستخدم نص SQL خام طويلاً إلا إذا طُلب؛ ركّز على النتيجة والتفسير.
- استخدم أسماء الأدوات الحرفية كما تظهر في قائمة الأدوات المتاحة لك فقط.

التاريخ المرجعي لليوم: {{ $now }}
```

(إذا صيغة `$now` عندك مختلفة في n8n، عدّل السطر الأخير حسب إعداد العقدة.)

---

## 2) Tool 1 — DB Schema (قائمة القواعد والجداول)

**الوصف المقترح للأداة (لصق في حقل Description):**

```text
تُرجع قائمة قواعد بيانات MySQL (المخططات) وجداول نوع BASE TABLE من information_schema، مع استثناء جداول النظام. استخدمها كخطوة أولى دائماً قبل بناء أي استعلام لمعرفة أين توجد الجداول ذات الصلة.
```

**Execute SQL — استعلام مقترح (كل الجداول ما عدا النظام):**

```sql
SELECT
    TABLE_SCHEMA AS table_schema,
    TABLE_NAME   AS table_name
FROM information_schema.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN (
        'mysql',
        'information_schema',
        'performance_schema',
        'sys'
      )
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

**بديل — إذا اتصال n8n مربوط بقاعدة واحدة وتريد فقط `DATABASE()`:**

```sql
SELECT
    TABLE_SCHEMA AS table_schema,
    TABLE_NAME   AS table_name
FROM information_schema.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

---

## 3) Tool 2 — Get table definition (أعمدة + مفاتيح + علاقات تقريبية)

**الوصف المقترح للأداة (لصق في حقل Description):**

```text
تُرجع هيكل جدول واحد في MySQL: أسماء الأعمدة، أنواع البيانات، إمكانية القيم الفارغة، القيم الافتراضية، مؤشرات المفاتيح، وأي ارتباطات مفاتيح أجنبية معروفة. المدخلات: table_schema (اسم قاعدة البيانات) و table_name (اسم الجدول) كما ظهرا في أداة المخطط. استخدمها قبل كتابة SELECT نهائي لضمان صحة أسماء الأعمدة والعلاقات.
```

**Execute SQL:**

```sql
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    c.COLUMN_KEY,
    c.EXTRA,
    tc.CONSTRAINT_TYPE,
    kcu.REFERENCED_TABLE_SCHEMA AS referenced_schema,
    kcu.REFERENCED_TABLE_NAME   AS referenced_table,
    kcu.REFERENCED_COLUMN_NAME  AS referenced_column
FROM information_schema.COLUMNS c
LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu
    ON c.TABLE_SCHEMA = kcu.TABLE_SCHEMA
   AND c.TABLE_NAME   = kcu.TABLE_NAME
   AND c.COLUMN_NAME  = kcu.COLUMN_NAME
LEFT JOIN information_schema.TABLE_CONSTRAINTS tc
    ON kcu.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
   AND kcu.CONSTRAINT_NAME   = tc.CONSTRAINT_NAME
   AND tc.TABLE_SCHEMA       = c.TABLE_SCHEMA
   AND tc.TABLE_NAME         = c.TABLE_NAME
WHERE c.TABLE_SCHEMA = '{{ $fromAI("table_schema") }}'
  AND c.TABLE_NAME   = '{{ $fromAI("table_name") }}'
ORDER BY c.ORDINAL_POSITION;
```

> إذا أنت متأكد أن كل شيء داخل `DATABASE()` وحدة، يمكنك تثبيت السكيما في العقدة بدل `table_schema` من الـ AI، مثلاً استبدل السطرين في `WHERE` بـ:  
> `c.TABLE_SCHEMA = DATABASE()` و `c.TABLE_NAME = '{{ $fromAI("table_name") }}'`.

---

## 4) Tool 3 — Run SQL query (تنفيذ الاستعلام)

**الوصف المقترح للأداة (لصق في حقل Description):**

```text
تنفّذ استعلام MySQL كاملاً يوفّره النموذج. الاستخدام المعتمد: استعلامات قراءة (SELECT وما يشابهها) فقط ما لم تنصّ سياسة التشغيل عندكم على خلاف ذلك. يجب أن يكون SQL صحيحاً لـ MySQL مع backticks للمعرفات عند الحاجة. لا تُستخدم لحذف أو تعديل بيانات دون تفويض صريح.
```

**Execute SQL:**

```sql
{{ $fromAI('query') }}
```

> في n8n قد تحتاج وضع العقدة على **تنفيذ استعلام خام** أو عقدة MySQL التي تقبل query كاملة من تعبير — حسب نوع العقدة عندك. إذا العقدة لا تقبل إلا جسم الاستعلام داخل حقل واحد، الصق نفس التعبير `{{ $fromAI('query') }}` هناك.

---

## 5) ملاحظات أمان وتشغيل

1. **صلاحيات المستخدم MySQL:** أنشئ مستخدماً بصلاحيات `SELECT` فقط على الجداول المطلوبة إن أمكن.
2. **الـ Agent قد يولّد DELETE/UPDATE:** عزّز البرومبت بـ «SELECT only» واستخدم مستخدم read-only.
3. **`pgml` في Postgres** = مخطط إضافة PostgresML؛ **في MySQL لا يوجد pgml** — استخدم أسماء قواعدك الحقيقية (`TABLE_SCHEMA`) كما يرجعها Tool 1.
4. ربط الأدوات الثلاث في **AI Agent → Tools**. البرومبت أعلاه لا يسمّي أدواتاً بعناوين إنجليزية ثابتة؛ يعتمد على «الأدوات المتاحة في القائمة» — إن احتجت صيغة أدق، اذكر في السطر الأول أسماء الأدوات كما تظهر في n8n حرفياً.
