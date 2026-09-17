# عبريةٌ وعربية في ورقة واحدة: ما تحتمله أدواتنا فعلاً

بحثٌ يجيب القضية [#91](https://github.com/thabet-toma/ktra2/issues/91) (ضمن الخريطة [#89](https://github.com/thabet-toma/ktra2/issues/89)).
**قيد القضية: بحثٌ فقط — لم يُمسّ كودُ المنصّة.**

السؤال العملي: ورقةُ طلبيةٍ عناوينُ أعمدتها **عبرية**، وأسماءُ أصنافها **عربية/إنجليزية**،
وفيها **عمودُ سعرٍ فارغ** يملؤه المورّد بيده. ما الذي تحتمله أدواتنا؟

---

## 0. ما نستعمله فعلاً (لا تخمين)

| البند | القيمة |
|---|---|
| المكتبة | **ExcelJS** |
| النسخة المُعلَنة | `"exceljs": "^4.4.0"` — `frontend_v2/package.json` |
| النسخة المثبَّتة | **4.4.0** (`frontend_v2/node_modules/exceljs/package.json`) |
| نقطة الاستعمال | `frontend_v2/utils/reportXlsx.ts` (`reportToXlsxBuffer`) |
| الاختبارات | `frontend_v2/utils/reportXlsx.test.ts` |
| كيف تُحمَّل | استيرادٌ ديناميكي عند أول ضغطة تصدير: `(await import('exceljs')).default` |
| حزمة المتصفح | `dist/exceljs.min.js` — حقل `browser` في `package.json` |

وموضعُ الشاهد في كودنا اليوم — الورقة **مضبوطةٌ على اليمين أصلاً**:

```ts
// frontend_v2/utils/reportXlsx.ts
sheet.views = [{ state: 'frozen', rightToLeft: true, ySplit: headerRow.number }];
```

ويحرسه اختبارٌ قائم:

```ts
// frontend_v2/utils/reportXlsx.test.ts
assert.equal(view.rightToLeft, true, 'الورقة تبدأ من اليمين');
```

فالجواب المختصر عن كل ما يلي: **المكتبة التي عندنا تكفي، والاتجاه مضبوطٌ فيها منذ اليوم.**

---

## 1. اتجاه الورقة — `sheetView@rightToLeft`

### ما يقوله المعيار

الخاصية سِمةٌ على عنصر `sheetView` في `CT_SheetView` من ECMA‑376. توثيق مايكروسوفت
لواجهة OpenXML الرسمية يصفها حرفياً:

> "Right To Left Represents the following attribute in the schema: rightToLeft"
> — [SheetView.RightToLeft Property, Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.sheetview.righttoleft?view=openxml-3.0.1)

ونوعها `BooleanValue`، أي `rightToLeft="1"` في XML.

### هل تكشفها مكتبتنا؟ نعم — صراحةً وفي التوثيق والأنواع

توثيق ExcelJS الرسمي يعدّها ضمن خصائص `views` المشتركة:

> "Sets the worksheet view's orientation to right-to-left"
> — [ExcelJS README, worksheet views](https://github.com/exceljs/exceljs#worksheet-views)

```javascript
worksheet.views = [ {rightToLeft: true} ];
```

وملفُّ الأنواع المثبَّت عندنا يعلنها (`frontend_v2/node_modules/exceljs/index.d.ts:37`):

```ts
rightToLeft: boolean;
```

### تحقّقٌ عملي — قرأنا XML الناتج بأنفسنا

وُلّد ملفٌ بورقةٍ اسمها `הזמנה` بعناوين عبرية وأصنافٍ عربية/لاتينية، ثم فُكَّ الـzip
وقُرئ `xl/worksheets/sheet1.xml`. الناتج حرفياً:

```xml
<sheetViews><sheetView workbookViewId="0" rightToLeft="1">
  <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
</sheetView></sheetViews>
```

فالسمة تُكتب فعلاً، وتعود صحيحةً في القراءة العكسية (`view.rightToLeft === true`).

**النتيجة: لا بديل مطلوب. المكتبة تكشفها، ونحن نضبطها بالفعل.**

ملاحظةٌ نافعة: العبرية والعربية كلتاهما RTL، فورقةُ الطلبية بعناوين عبرية وأصنافٍ
عربية **لا تحتاج اتجاهين للورقة** — اتجاهٌ واحد يخدم الطرفين، والانحراف الوحيد هو
أسماءُ الأصناف اللاتينية داخل خلاياها، وهذا شأنُ البند التالي.

---

## 2. خلط اتجاهين في ورقة واحدة

### القاعدة التي يطبّقها Excel افتراضياً

اتجاه الورقة (`rightToLeft`) يحكم **ترتيبَ الأعمدة** (أين يقع العمود A)، لا اتجاهَ
النصّ داخل كل خلية. اتجاهُ الخلية سِمةٌ مستقلّة على المحاذاة:

> "Reading Order Represents the following attribute in the schema: readingOrder"
> — [Alignment.ReadingOrder Property, Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.alignment.readingorder?view=openxml-3.0.1)

قيمتها عددية: `0` = سياقي (Context)، `1` = يسار‑إلى‑يمين، `2` = يمين‑إلى‑يسار.
والافتراضُ هو السياقي، ومايكروسوفت تصف سلوكه:

> "If the first strong character is right-to-left, the reading order is also right-to-left"
> — [Using right-to-left languages in Office, Microsoft Support](https://support.microsoft.com/en-us/office/using-right-to-left-languages-in-office-17d8a34d-36d6-49ad-b765-257cb7cd22e2)

وهذا هو نفسُ منطق «أوّل محرفٍ قوي» في خوارزمية Unicode ثنائية الاتجاه (قاعدتا P2/P3).

### متى يكفي الاستنتاج ومتى يخذل

- **يكفي** حين يبدأ نصُّ الخلية بمحرفٍ قوي من اتجاهها الحقيقي:
  `إطار ميشلان 205/55 R16` يبدأ بعربيّ ⇒ RTL ومحاذاةٌ يمنى. صحيح.
  `Michelin Primacy 4 — 205/55R16` يبدأ بلاتينيّ ⇒ LTR ومحاذاةٌ يسرى. صحيح.
- **يخذل** حين لا يكون أوّلُ محرفٍ قويّ من اتجاه النصّ الغالب. الأرقامُ والرموز
  **ليست محارفَ قوية**، فاسمٌ كـ`205/55R16 إطار ميشلان` أوّلُ قويٍّ فيه لاتينيّ `R`،
  فيُقرأ كسطرٍ لاتيني ويقفز الذيلُ العربي إلى غير موضعه بصرياً. ونفسُ الشيء في
  عنوانٍ عبريٍّ يبدأ برمزٍ أو رقمٍ أو قوس.

### العلاجان — وأيّهما نختار

**(أ) محارف تحكّم في النصّ نفسه** (RLM `U+200F` / LRM `U+200E`، أو العوازل FSI/PDI).
Unicode توصي بالعوازل في المستندات الجديدة:

> "The use of the directional isolates instead of embeddings is encouraged in new documents"
> — [UAX #9: Unicode Bidirectional Algorithm](https://www.unicode.org/reports/tr9/)

وهي محارفُ صفريةُ العرض؛ توصيفُ Unicode للعلامتين:

> "they do not display or have any other semantic effect"
> — [UAX #9](https://www.unicode.org/reports/tr9/)

**لكنها لا تخلو من ثمنٍ عندنا**: المحرف يصير **جزءاً من قيمة الخلية**. فإن أعاد
المورّد الملف واستوردناه، لن يطابق `إطار ميشلان` سلسلةَ `‏إطار ميشلان`، ولا
تجده `VLOOKUP` ولا مقارنةُ نصٍّ صارمة. أي أننا نصلح المظهر بإفسادِ البيانات.

**(ب) محاذاةٌ صريحة لكل خلية** — `readingOrder` + `horizontal`، وهي **تنسيقٌ لا بيانات**،
فلا تلمس قيمةَ الخلية أصلاً. ومكتبتنا تكشفها (`index.d.ts:286`):

```ts
readingOrder: 'rtl' | 'ltr';
```

وقد جرّبناها فعلاً وقرأنا `xl/styles.xml` الناتج:

```xml
<xf ... applyAlignment="1"><alignment horizontal="right" readingOrder="2"/></xf>
```

أي أنّ `'rtl'` تُترجَم إلى `readingOrder="2"` تماماً كما يوجب المعيار.

**التوصية للبند 2:** اترك الاستنتاجَ السياقي هو الأصل (فهو يصيب في الغالبية الساحقة)،
وإن ظهرت أسماءُ أصنافٍ تبدأ برقمٍ أو رمز فاضبط `alignment` صراحةً على تلك الخلايا
بحسب لغة الاسم — **ولا تحقن محارفَ تحكّمٍ في القيمة**، لأن الورقة قد تعود إلينا للاستيراد.

---

## 3. الترميز والخطوط

### الترميز: لا شيء مطلوب

`xlsx` صيغةُ ZIP تحوي XML بترميز UTF‑8، والعبرية والعربية محارفُ Unicode عادية فيه.
قرأنا `xl/sharedStrings.xml` من الملف الذي ولّدناه:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst ...><si><t>פריט</t></si><si><t>מחיר ליחידה</t></si>
<si><t>إطار ميشلان 205/55 R16</t></si>
<si><t>Michelin Primacy 4 — 205/55R16</t></si></sst>
```

العبرية والعربية واللاتينية والشرطةُ الطويلة — كلُّها نصٌّ خام بلا هروبٍ ولا صفحةِ
ترميز. **فلا إعدادَ ترميزٍ خاصٌّ للعبرية أصلاً.**

### الخطوط: لا تسمِّ خطاً، ودع الاحتياط يعمل

مكتبتنا اليوم لا تفرض اسمَ خطٍّ في `reportXlsx.ts` (تضبط `bold` و`size` فقط)، فالورقة
ترث خطَّ القالب الافتراضي — ورأينا في `xl/styles.xml` أنه `Calibri`، وهو يغطّي
العبرية والعربية معاً. **وهذا هو التصرّف الصحيح**، وتوثيق مايكروسوفت للتوطين يحذّر
من عكسه:

> "Don't hardcode font face names."
> — [Customize font selection with font fallback and font linking, Microsoft Learn](https://learn.microsoft.com/en-us/globalization/fonts-layout/fonts)

### ماذا يحدث على جهازٍ بلا خطٍّ عبري؟

نظامُ العرض يبدّل الخطَّ تلقائياً لا يعرض فراغاً:

> "most rendering systems ... can automatically switch (fall back) to a predefined font"
> — [Microsoft Learn، الاحتياط الخطّي](https://learn.microsoft.com/en-us/globalization/fonts-layout/fonts)

> "Each application and each operating system can define its own fallback font"
> — [المصدر نفسه](https://learn.microsoft.com/en-us/globalization/fonts-layout/fonts)

عملياً:

| المنصّة | السلوك المتوقّع |
|---|---|
| Excel لوِندوز/ماك | الاحتياطُ الخطّي يعمل؛ العبرية تظهر ولو بخطٍّ غير المسمّى. Windows يشحن خطوطاً عبرية أصلاً. |
| Excel على الوِب / Google Sheets | العرضُ على خطوط الخادم/المتصفح — لا يعتمد على جهاز المستخدم إطلاقاً. |
| LibreOffice | يستبدل الخطَّ الناقص بأقرب متاح؛ ومعظم توزيعات لينكس تشحن خطوطاً عبرية. |
| جهازٌ عارٍ تماماً من أي خطٍّ عبري | مربّعاتٌ فارغة (*tofu*) — وهو **عطبُ نظامٍ لا عطبُ ملفّنا**، ولا يُصلَح من جانب الكاتب إلا بتضمين الخطّ، وExcel لا يضمّن الخطوط في `xlsx`. |

**النتيجة: لا إعدادَ خاصّاً مطلوباً. والأسلمُ ألّا نسمّي خطاً بتاتاً — وهو ما نفعله اليوم.**

---

## 4. عمودٌ فارغ مهيّأ للتعبئة

المطلوب ثلاثة: **عرضٌ كافٍ** + **تنسيقٌ رقمي/عملة** + **تحقّقُ إدخالٍ يمنع النصّ**.
والثلاثة متاحةٌ في ExcelJS 4.4.0، وجرّبناها جميعاً.

### الوصفة

```ts
const price = sheet.getColumn(3);
price.width  = 16;                        // عرضٌ كافٍ
price.numFmt = '#,##0.00 "₪"';            // تنسيق العملة

for (let r = firstDataRow; r <= lastDataRow; r++) {
  sheet.getCell(r, 3).dataValidation = {
    type: 'decimal',
    operator: 'greaterThanOrEqual',
    formulae: [0],
    allowBlank: true,                     // مهم: الفراغ مسموح، فالمورّد يملأ تدريجياً
    showErrorMessage: true,
    errorStyle: 'stop',
    errorTitle: 'מחיר',
    error: 'נא להזין מספר בלבד',
  };
}
```

توثيق ExcelJS يوثّق أنواعَ التحقّق: `list, whole, decimal, textLength, custom, date`
ومثالَه الحرفي:

```javascript
worksheet.getCell('A1').dataValidation = {
  type: 'decimal', operator: 'between', allowBlank: true, formulae: [1.5, 7]
};
```
— [ExcelJS README, Data Validations](https://github.com/exceljs/exceljs#data-validations)

### ما يخرج فعلاً (مقروءاً من الملف المولَّد)

```xml
<cols><col min="3" max="3" width="16" style="1" customWidth="1"/></cols>
...
<c r="C2" s="1"/>            <!-- خليةٌ فارغة تحمل التنسيق -->
...
<dataValidations count="1"><dataValidation type="decimal"
  operator="greaterThanOrEqual" allowBlank="1" showErrorMessage="1"
  errorStyle="stop" errorTitle="מחיר" error="נא להזין מספר בלבד" ...
```

ومع `numFmts`:

```xml
<numFmt numFmtId="164" formatCode="#,##0.00 &quot;₪&quot;"/>
```

والقراءةُ العكسية تعيد كلَّ شيء سليماً: `width=16`، `numFmt='#,##0.00 "₪"'`،
والقيمةُ `null` (خليةٌ فارغةٌ حقاً لا صفرٌ ولا شرطة)، وكائنُ `dataValidation` كاملاً
بعنوانِ خطئه العبري.

### ثلاثةُ مزالق تستحق التسجيل

1. **الخليةُ الفارغة يجب أن تبقى فارغة.** لا تكتب `0` ولا `'-'` في عمود السعر:
   الصفرُ سعرٌ كاذب، والشرطةُ نصٌّ يكسر `SUM`. وهذه القاعدةُ مطبَّقةٌ عندنا أصلاً في
   `xlsxCell` (`if (value === … || value === '') return { value: null }`).
2. **`numFmt` على العمود يطال خليةَ العنوان أيضاً.** في تجربتنا أخذت `C1` (العنوان
   العبري) نمطاً فيه `numFmtId="164"`. غيرُ ضارٍّ لأن العنوان نصّ، لكن إن أردت
   نظافةً تامّة فاضبط `numFmt` على خلايا البيانات لا على كائن العمود.
3. **`allowBlank: true` غيرُ اختياري هنا.** بدونه يشتكي Excel من كل خليةٍ لم تُملأ بعد،
   وهذا بالضبط عكسُ الغرض من ورقةٍ تُرسَل فارغةً لتُملأ.

**النتيجة: البند الرابع مغطّى بالكامل بمكتبتنا الحالية بلا أي إضافة.**

---

## 5. السقف والبدائل — وهل نبدّل؟

لا حاجة للتبديل، لكن نسجّل المقارنة لتكون القضيةُ مقفلةً بحجّة لا بانطباع.

### كلفةُ مكتبتنا اليوم

قياسٌ مباشرٌ على النسخة المثبَّتة (`node_modules/exceljs/dist/exceljs.min.js`):

| القياس | القيمة |
|---|---|
| الحزمة المصغّرة | **925 KB** |
| مضغوطةً بـgzip | **250 KB** |
| المجلد كاملاً على القرص | ~21 MB (تطويريّ فقط، لا يصل المتصفح) |

**والمهم**: هذه الـ250 KB **لا تدخل الحزمة الأولى إطلاقاً** — `reportXlsx.ts` يستوردها
ديناميكياً عند أول ضغطة تصدير، وهو قرارٌ موثَّقٌ في رأس الملف نفسه. فمن لا يصدّر
لا يدفع شيئاً.

### البدائل التي تبقى في المتصفح بلا خادم

| المكتبة | RTL للورقة | تنسيق/خطوط | تحقّق إدخال | الحجم | الحكم |
|---|---|---|---|---|---|
| **ExcelJS 4.4.0** (الحالية) | ✅ `rightToLeft` | ✅ كامل + `readingOrder` | ✅ مدمج | 250 KB gzip، مؤجَّل | **يفي بالخمسة كلّها** |
| **SheetJS CE** (`xlsx`) | ❌ | ❌ (تجاري) | ❌ | أصغر | **مستبعَد** |
| **write-excel-file 4.1.1** | ✅ | ✅ محدود | ⚠️ إضافةُ طرفٍ ثالث | ~1.7 MB مفكوكاً | بديلٌ نحيف لو احتجناه — ولا نحتاجه |

**لماذا يسقط SheetJS رغم صغره؟** لأن التنسيق نفسه ليس في النسخة المجانية:

> "SheetJS Pro offers solutions beyond data processing: ... let out your inner Picasso with styling"
> — [xlsx على npm، ملفّ التعريف الرسمي](https://www.npmjs.com/package/xlsx)

وبحثٌ في نصّ README الرسمي كاملاً (65 KB) لا يجد `rightToLeft` ولا `dataValidation`
ولا `numFmt` — يجد `!cols` لعرض الأعمدة فقط. وطلبا RTL في مستودعهم
([#322](https://github.com/SheetJS/sheetjs/issues/322)، [#927](https://github.com/SheetJS/sheetjs/issues/927))
أُغلقا دون أن يصلا النسخةَ المجتمعية. يضاف إلى ذلك أن آخر نسخةٍ لهم على npm هي
`0.18.5` (المشروع انتقل إلى توزيعٍ خاصّ به خارج npm) — وهذا وحده اعتبارُ إمدادٍ يكفي.

**و`write-excel-file`؟** يدعم الاتجاه صراحةً:

> "`rightToLeft: boolean` — Pass `true` to use right-to-left layout"
> — [write-excel-file على npm](https://www.npmjs.com/package/write-excel-file)

لكن تحقّقَ الإدخال عنده ليس في اللبّ، بل في حزمةِ طرفٍ ثالث
(`@onparallel/write-excel-file-data-validation`) — أي أننا نستبدل تبعيةً واحدةً
ناضجةً باثنتين إحداهما جانبية، مقابل توفيرٍ في حزمةٍ **مؤجَّلة التحميل أصلاً**.
صفقةٌ خاسرة.

---

## التوصية

> ## **نبقى على ExcelJS 4.4.0. لا نبدّل.**

الأسبابُ الخمسة بترتيب أسئلة القضية:

1. **الاتجاه** — `rightToLeft` مكشوفٌ في المكتبة، وموضوعٌ في كودنا اليوم
   (`reportXlsx.ts`)، ويحرسه اختبارٌ قائم. صفرُ عمل.
2. **خلط الاتجاهين** — استنتاجُ Excel السياقي يصيب في الغالبية؛ وحين يخذل فالعلاجُ
   `alignment.readingOrder` المكشوفةُ في المكتبة — **لا محارفَ تحكّمٍ في القيمة**،
   حفاظاً على استيرادٍ لاحقٍ يطابق النصوص.
3. **الترميز والخطوط** — UTF‑8 بلا إعداد، ولا نسمّي خطاً فيعمل احتياطُ النظام.
4. **العمود الفارغ** — `width` + `numFmt` + `dataValidation` الثلاثةُ مدمجة ومجرَّبة.
5. **السقف** — 250 KB مضغوطةً، **مؤجَّلةً** حتى أول تصدير؛ والبديلان إما ناقصان
   (SheetJS) أو يستبدلان تبعيةً بتبعيتين مقابل توفيرٍ لا يُدفَع أصلاً.

### ما يلزم عند بناء ورقة الطلبية فعلياً (لا يلزم تغييرَ مكتبة)

- ضبط `rightToLeft: true` (قائم).
- عمودُ السعر: `width` معقول + `numFmt` بعملة المورّد + `dataValidation` من نوع
  `decimal` مع **`allowBlank: true`**.
- إبقاءُ خلايا السعر **فارغةً حقاً** (`null`) — لا صفرَ ولا شرطة.
- عدمُ تسمية خطّ.
- عند اسمِ صنفٍ يبدأ برقمٍ أو رمز: `alignment: { readingOrder, horizontal }` على تلك
  الخلية وحدها.

---

## المصادر

- [SheetView.RightToLeft Property — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.sheetview.righttoleft?view=openxml-3.0.1)
- [Alignment.ReadingOrder Property — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.alignment.readingorder?view=openxml-3.0.1)
- [Using right-to-left languages in Office — Microsoft Support](https://support.microsoft.com/en-us/office/using-right-to-left-languages-in-office-17d8a34d-36d6-49ad-b765-257cb7cd22e2)
- [Customize font selection with font fallback and font linking — Microsoft Learn](https://learn.microsoft.com/en-us/globalization/fonts-layout/fonts)
- [UAX #9: Unicode Bidirectional Algorithm — Unicode Consortium](https://www.unicode.org/reports/tr9/)
- [ExcelJS — المستودع والتوثيق الرسمي](https://github.com/exceljs/exceljs)
- [ECMA-376 — Office Open XML File Formats](https://ecma-international.org/publications-and-standards/standards/ecma-376/)
- [xlsx (SheetJS Community Edition) — npm](https://www.npmjs.com/package/xlsx)
- [SheetJS issue #322 — writing sheet with direction RTL](https://github.com/SheetJS/sheetjs/issues/322) · [issue #927 — page layout: sheet right-to-left](https://github.com/SheetJS/sheetjs/issues/927)
- [write-excel-file — npm](https://www.npmjs.com/package/write-excel-file)
