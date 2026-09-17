# حماية الصفحة العامّة: الرفع والإساءة — بحثُ حقائق (قضيّة #172 · خريطة #169)

**السؤال:** صفحةُ تقديمٍ على وظيفة يفتحها **مجهولٌ بلا حساب** ويرفع سيرةً ذاتيّة
ورقمَ تواصل. ما الذي تملكه المنصّة اليوم من آليّاتٍ قابلةٍ لإعادة الاستعمال،
وما الثغرات؟

**المنهج:** حقائقُ من كود المستودع نفسِه لا قرارات ولا تصميم. كل سطرٍ أدناه
مقروءٌ من ملفّه، ويُشار بالملفّ والرمز لا برقم السطر. استُثني `venv/` و
`node_modules/` و`.claude/worktrees/`. الفرع: `research/public-upload-safety`
من `newktra`؛ لا تعديلَ على أيّ كود إنتاج.

---

## ١ — حجّة عزل `AllowAny` والنمط المفروض

**`store/views.py`** (رأس الملفّ) يقول حرفيّاً:

> «**لماذا app مستقلة:** حجّتها أمنية لا تنظيمية. كل كود `AllowAny` يعيش في
> مجلد واحد يقرؤه مراجعُ الأمن كاملاً في جلسة، ويبقى `inventory/views.py` مئة
> بالمئة خلف المصادقة.»

**`docshare/views.py`** (رأس الملفّ) يقول:

> «**كل كود `AllowAny` في هذا الملف ملفٌّ واحد يُقرأ كاملاً في جلسة**، وهي نفس
> حجّة `store/views.py`. الفرق الوحيد أن هذا السطح يُصيَّر HTML لا JSON […]
> الصفحة تعمل **بلا JavaScript إطلاقاً**: القرار نموذج POST عادي.»

و**`docshare/models.py`** (رأس الملفّ) يعيد صياغة القاعدة نفسِها ويكمل الحجّة:

> «كل كود `AllowAny` في المنصة يعيش في مجلدين يقرؤهما مراجع الأمن كاملين في
> جلسة، ويبقى `sales/views.py` مئة بالمئة خلف المصادقة — بدل view عام مدسوس بين
> عشرين view محمي حيث يصير سطرٌ خاطئ في `get_queryset` تسريباً لا يلاحظه أحد.»

**النمط الذي تفرضه هذه الحجّة على أيّ app عامّة جديدة** — مقروءاً من الكود لا
مستنتَجاً:

1. **app مستقلّة**، وكلُّ `AllowAny` داخل ملفِّ views واحدٍ فيها.
2. **صنفُ أساسٍ عامٌّ واحد** يحمل الثلاثيّة: `store/views.py` (`StorePublicView`)
   و`docshare/views.py` (`DocSharePublicBase`) — كلاهما
   `authentication_classes = []` + `permission_classes = [AllowAny]` +
   `throttle_scope` خاصٌّ بالسطح. الأول موثَّقٌ بأنّ «توكنٌ يُرسَل إلى هذه النقطة
   لا يقدر أن يغيّر حرفاً في الرد — خاصية بنيوية لا وعدٌ في مراجعة».
3. **فصل مسار العامّ عن مسار الإدارة**: `docshare/urls_public.py` مقابل
   `docshare/urls.py` («فلا يختلط ما يحتاج توكن مستخدم بما لا يحتاجه»)، مع
   تسجيل السطح العامّ مرّتين (`/s/<token>` و`/api/share/<token>/`) في
   `core/urls.py`.
4. **الشركةُ من المسار لا من الترويسة**: `store/views.py` (`_tenant_or_404`)
   يحلّها من `store_slug`، و`docshare/services.py` (`resolve_share`) من التوكن.
5. **حمولةٌ صريحةٌ مبنيّةٌ بيد** لا سيريالايزر يعكس النموذج
   (`docshare/documents/_contract.py` · `PAYLOAD_FIELDS`)، **يحرسها اختبار
   تسريبٍ سالب**: `docshare/tests/test_public_leakage.py` و
   `store/tests/test_public_leakage.py` — `assert set(keys) == WHITELIST` لا
   غيابَ حقلٍ مُسمّى، «فبالبناء لا بالتعداد».
6. **ترويسات تقسية على السطح العامّ**: `docshare/views.py` (`_harden`) يضع
   `X-Robots-Tag: noindex, nofollow, noarchive` و`Cache-Control: no-store` —
   ومعلَّلٌ صراحةً بأنّ `NoStoreAPIMiddleware` يغطّي `/api/*` وحده و`/s/` خارجه.
7. **404 لا 403** عند غياب المستند أو الوحدة (`docshare/views.py`
   (`DocumentShareViewSet.create`)): «403 يُثبت لمن يخمّن المعرّفات أن المستند
   موجود».

---

## ٢ — مسحُ كلّ `AllowAny` / `permission_classes = []` في المستودع

الحصرُ الكامل (خارج `venv/` و`node_modules/` و`.claude/worktrees/`):

| الملفّ (الرمز) | الحالة |
|---|---|
| `store/views.py` (`StorePublicView`) | داخل الحصن — سطح المتجر العامّ، `throttle_scope="store_public"` |
| `docshare/views.py` (`DocSharePublicBase`) | داخل الحصن — `throttle_scope="doc_share_public"`، و`DocShareQuoteView` يضيّقه إلى `doc_share_public_quote` |
| `accountant_portal/views.py` (`VerifyEmailView`) | **خارج الحصن** — `AllowAny` + `ScopedRateThrottle` بنطاق `accountant_verify` (10/hour) |
| `accountant_portal/views.py` (`ResendVerificationView`) | **خارج الحصن** — نفس النطاق والسقف |
| `accounting/views.py` (`CurrencyViewSet`) | **خارج الحصن** — `AllowAny` بلا `throttle_scope`؛ الدوكسترينغ: «قراءة فقط — قائمة العملات للقوائم المنسدلة؛ لا تحتوي على أسرار». و`tenants/models.py` (`Currency`) فعلاً **بلا `tenant` FK** — جدولٌ عامٌّ للمنصّة، فلا تسريبَ بين شركات، لكنّه سطحٌ عامٌّ يعيش وسط ملفٍّ محاسبيّ ضخم (وهو بالضبط ما تحذّر منه الحجّة أعلاه) |
| `core/tests/test_exception_handler.py` | اختبار — `permission_classes = []` على view وهميّ |

**الخلاصة: لا، ليس محصوراً في `store` و`docshare`.** ثلاث نقاطٍ إنتاجيّة تعيش
خارجهما (اثنتان في `accountant_portal`، وواحدة في `accounting`). الاثنتان في
`accountant_portal` تحملان خانقاً صريحاً؛ `CurrencyViewSet` لا تحمل شيئاً فوق
`anon` العامّ — و`core/tests/test_global_throttle.py` يستعملها **بوصفها النقطة
العامّة المرجعيّة** لقياس سلّة `anon`.

---

## ٣ — شكل الرابط/المفتاح في `docshare.DocumentShare`

مقروءاً من `docshare/models.py` (`DocumentShare`) و`docshare/services.py`:

- **التوليد:** `docshare/services.py` (`TOKEN_BYTES = 32`) ⇒
  `secrets.token_urlsafe(32)` — **٢٥٦ بت عشوائيّة** من مولّد التشفير، تُعطي **٤٣
  محرفاً**. العمود `token` بطول ٦٤ «ليتّسع لتغيير الطول لاحقاً»، `unique=True`
  و`db_index=True`.
- **التخزين خامٌّ لا مهشَّر** — وهو قرارٌ موثَّقٌ بحجّته في رأس `docshare/models.py`:
  الرابط يُفتح مراراً ويجب أن يُعاد نسخُه من نافذة المشاركة بعد أسبوع، وذلك
  مستحيلٌ مع تهشيرٍ أحاديّ (بخلاف `accountant_portal.models`
  (`AccountantEngagement.invitation_token_hash`) الذي يُستهلَك مرّةً فيُهشَّر).
  المقابل معلَنٌ: «تسريب نسخة القاعدة يسرّب الروابط الحيّة».
- **الصلاحية الزمنيّة إلزاميّة:** `expires_at` **بلا `null`** — «رابط بلا انتهاء
  حالةٌ لا نريد أن توجد أصلاً». المدد المسموحة `ALLOWED_EXPIRY_DAYS = (7, 30, 90)`
  والافتراضيّ `DEFAULT_EXPIRY_DAYS = 30` (`docshare/services.py`).
- **الإبطال فوريّ ولا يحذف:** `revoked_at` + `docshare/services.py`
  (`revoke_share`) — «الصفّ يبقى: من شارك ومتى سؤالٌ يُسأل لاحقاً»، ويكتب سطراً
  في سجلّ النشاط (`core.activity.log_activity`).
- **تعريفٌ واحدٌ لـ«حيّ»:** `DocumentShare.is_live` = `not is_revoked and not
  is_expired`، وهو ما تفحصه كلُّ نقطةٍ عامّة عبر `resolve_share`.
- **تمييزُ ٤٠٤ عن ٤١٠:** `ShareNotFound` مقابل `ShareGone` — «انتهى» رسالةٌ
  للزبون، و«غير موجود» صمتٌ أمام من يخمّن.
- **الجمهوران: نعم، حقيقةٌ مخزَّنة لا استنتاج.** الحقل `is_public` (هجرة
  `docshare/migrations/0004_share_public_audience.py`): `False` = رابطٌ خاصٌّ
  بمستقبِلٍ مسمّى، `True` = رابطٌ لأيّ مجهولٍ يحمله. والدوكسترينغ يشرح لماذا هي
  رايةٌ صريحة: أيُّ عطبٍ يحذف صفّ المستقبِل كان سيحوّل رابطاً خاصّاً إلى عامٍّ
  بصمت. والجمهور **جزءٌ من الاستعلام** في `docshare/services.py` (`active_share`)
  لا فلترةٌ لاحقة — وهو إصلاحُ تسريبٍ حيٍّ موثَّق: بدونه كان الرابط العامّ يُعيد
  رابط المورّد الخاصّ فتظهر أسعارُه لكلّ من يفتحه.
- **ومفتاحا الصلاحية:** لكلّ نوعِ مستندٍ مفتاحُ صلاحيّةٍ خاصٌّ به في
  `docshare/documents/` (`DOC_TYPES[…]["permission"]`) — مبيعاتٌ
  (`sales.document.share`) وشراءٌ (`purchase.document.share`) — يفرضه
  `docshare/views.py` (`DocumentShareViewSet.create/retrieve/revoke`) عبر
  `core.access.require_perm`، **بعد** `core.modules.require_module` (الترخيص قبل
  الصلاحية، والوحدة غير المرخّصة تختفي بـ٤٠٤ لا ٤٠٣). أمّا الرابطُ العامّ
  للطلبيّة فيُنشأ من مسارٍ آخر (`logistics/views/procurement.py`
  (`PurchaseRFQViewSet.public_link`)) وليس له مفتاحٌ ثالثٌ مستقلّ — لا
  `permission` ثانياً يفصل «شارك مع مورّدٍ مسمّى» عن «افتح للعموم».

---

## ٤ — التقييد المعدّل (throttling)

**موجودٌ ومركَّبٌ عالميّاً** — `core/settings.py` (`REST_FRAMEWORK`):

```
DEFAULT_THROTTLE_CLASSES = [ScopedRateThrottle, UserRateThrottle, AnonRateThrottle]
```

و`DEFAULT_THROTTLE_RATES` (كلُّها قابلةٌ للضبط من البيئة حيث ذُكر `os.environ`):

| النطاق | السقف |
|---|---|
| `user` | `300/min` (`THROTTLE_RATE_USER`) |
| `anon` | `60/min` (`THROTTLE_RATE_ANON`) |
| `accountant_verify` | `10/hour` |
| `accountant_invite` | `20/hour` |
| `accountant_engagement_request` | `10/hour` |
| `accountant_company_lookup` | `60/hour` |
| `agent_query` | `120/hour` |
| `media_upload` | `120/hour` |
| `store_public` | `120/min` (`THROTTLE_RATE_STORE`) |
| `doc_share_public` | `60/min` (`THROTTLE_RATE_DOC_SHARE`) |
| `doc_share_public_quote` | `20/min` (`THROTTLE_RATE_DOC_SHARE_QUOTE`) |
| `ess` / `ess_punch` | `120/min` / `10/min` |

**والتطبيق الصريح على النقاط العامّة موجود:** `store/views.py`
(`StorePublicView.throttle_scope`)، `docshare/views.py`
(`DocSharePublicBase.throttle_scope`) و(`DocShareQuoteView.throttle_scope`)،
`accountant_portal/views.py` (`VerifyEmailView`/`ResendVerificationView`
بـ`throttle_classes = [ScopedRateThrottle]`)، `core/media_views.py`
(`MediaUploadThrottle` — `UserRateThrottle` بنطاق `media_upload`)، ونفسُها
مُعادةُ الاستعمال في `accountant_portal/practice_views.py`
(`PracticeDocumentUploadView.throttle_classes`).

**قيودٌ موثَّقةٌ في المستودع نفسِه يجب معرفتها:**

- `core/tests/test_global_throttle.py`
  (`test_anonymous_hit_on_protected_endpoint_is_rejected_before_throttling`):
  DRF ينفّذ `check_permissions` **قبل** `check_throttles`، فالمجهول على نقطةٍ
  محميّة يُردّ ٤٠١ ولا يُحتسَب. أي: `anon` يحمي **النقاط العامّة وحدها**.
- **عدّادات الـthrottle تعيش في الكاش الافتراضيّ** (`core/settings.py`
  (`CACHES`)): Redis إن ضُبط `REDIS_URL`، وإلّا
  `core.cache_backends.ResilientFileBasedCache` على القرص —
  و`SCALABILITY_AUDIT §1.1` مقتبسٌ في الإعدادات نفسِها بأنّها
  «read-modify-write بلا قفل بين العمليات». أي أنّ دقّة السقف بلا Redis ليست
  مضمونة.
- **`NUM_PROXIES` غير مضبوط افتراضيّاً** (`core/settings.py` — `None` ما لم
  يُمرَّر `DRF_NUM_PROXIES`). في هذه الحالة `rest_framework.throttling`
  (`BaseThrottle.get_ident`) يستعمل **كامل ترويسة `X-Forwarded-For` كهويّة** حين
  توجد؛ وهي ترويسةٌ يرسلها العميل. فالسطحُ خلف nginx، وترويسةٌ ملفّقةٌ مختلفةٌ في
  كلّ طلب = سلّةُ خنقٍ جديدة في كلّ مرّة. (التحقّق تمّ من مصدر DRF المثبَّت.)

---

## ٥ — تخزين الملفات وتقديمها

- **مكانُ الكتابة: Cloudinary، لا قرص الخادم.** `core/media_views.py`
  (`upload_media_file`) هي «نقطة الاختناق الوحيدة لكل رفوعات المنصة»: ترفع إلى
  Cloudinary في مجلّد `{folder}/t{tenant_id}` وتعيد `secure_url`. السرّ يبقى
  خادميّاً.
- **`MEDIA_ROOT`/`MEDIA_URL` معرَّفان وغيرُ مستعمَلَين:** `core/settings.py`
  يضع `MEDIA_URL='/media/'` و`MEDIA_ROOT=BASE_DIR/'media'`، لكن **لا `FileField`
  ولا `ImageField` في أيّ نموذج** في المستودع، ولا `static()`/`django.views.static.serve`
  في `core/urls.py`. أي: لا ملفَّ يُكتب على القرص ولا يُقدَّم منه.
- **`core.SystemAttachment` سجلٌّ لا مخزن:** `core/models.py`
  (`SystemAttachment`) = `tenant` + `related_table` + `related_id` +
  `file_type` + **`file_path` نصٌّ (رابط Cloudinary)** + `uploaded_at`. لا بايتات
  فيه. يكتبه `inventory/views.py` (`_handle_attachments`)، `partners/views.py`،
  `logistics/views/invoices.py`؛ ويقرؤه سيريالايزراتُ تلك الـapps
  **مفلتَراً بالشركة** (`tenant=…`) — باستثناء `partners/serializers.py` الذي
  يفلتر بـ`related_table`/`related_id` وحدهما (الطرفُ نفسُه مفلتَرٌ بالشركة قبله،
  فالنطاق يبقى سليماً بالنتيجة لا بالتصريح).
- **لكنّ قراءة الملفّ نفسِه ليست محروسةً بشيء:** ما يُقدَّم للمتصفّح هو
  **رابط Cloudinary العامّ** (`res.cloudinary.com/...`). لا وسيطَ ولا رابطٌ
  موقَّتٌ موقَّع؛ من يملك الرابط يفتح الملفّ بلا مصادقةٍ ولا انتماءٍ لشركة، وإلى
  الأبد. وهذا مستعمَلٌ عمداً على السطح العامّ: `store/views.py`
  (`PRODUCT_IMAGE_TYPES`) يسقط إلى صور `SystemAttachment` ويُخرج
  `file_path` للزوّار المجهولين. والحذف من Cloudinary «أفضل-جهد» لا مضمون
  (`core/media_views.py` (`destroy_cloudinary_asset`)).

---

## ٦ — حدود الحجم والأنواع المطبَّقة اليوم

القيم الفعليّة، حصراً:

| المسار (الرمز) | حدّ الحجم | حدّ النوع |
|---|---|---|
| `core/media_views.py` (`MAX_UPLOAD_BYTES`) — كلُّ رفعٍ يمرّ من `upload_media_file` | **25 MB** | **لا شيء.** `_resource_type` **تصنيفٌ لا حصر**: صورة/`raw`/`auto`. لا قائمةَ امتدادات مسموحة ولا فحصَ توقيعٍ للبايتات. (`_IMAGE_EXTS` تشمل `.svg`) |
| `core/media_views.py` (`media_upload`) — `POST /api/media/upload/` | نفسه | نفسه؛ + `IsAuthenticated` + `MediaUploadThrottle` (120/hour) |
| `accountant_portal/practice_views.py` (`PracticeDocumentUploadView`) | نفسه (نفس الدالّة) | نفسه |
| `hr/attendance_api.py` (`MAX_IMPORT_BYTES`) — استيراد الحضور | **2 MB** | نصٌّ فقط بالفعل: يُفكّ ترميزُه `utf-8-sig`/`utf-8`/`cp1256` أو يُرفض |
| `store/views.py` (`StoreOrderIntentView.MAX_ITEMS` / `MAX_QUANTITY_PER_ITEM`) | ٥٠ بنداً / ١٠٠٬٠٠٠ للكميّة | حدودُ حمولةٍ لا ملفّات |
| `store/views.py` (`StoreProductListView.MAX_IDS`) | ٦٠ معرّفاً | — |

خارج ذلك: `DATA_UPLOAD_MAX_MEMORY_SIZE`/`FILE_UPLOAD_MAX_MEMORY_SIZE` **غير
مضبوطَين** في `core/settings.py` (تبقى افتراضيّات جانغو). **ولا CAPTCHA ولا
فحصَ فيروسات ولا فحصَ توقيعٍ سحريّ (magic bytes) في المستودع كلّه** — البحث عن
`captcha`/`clamav`/`virus`/`python-magic` لا يُرجع إلّا تعليقَين يقرّان بغياب
CAPTCHA عمداً (`core/settings.py` عند `doc_share_public_quote`، و
`docshare/views.py` (`DocShareQuoteView`): «مخالفةٌ واعية موثَّقة لا سهواً»).

---

## ٧ — السابقة الأهمّ: نقطةٌ عامّة **تستقبل** من مجهول

**نعم، سابقتان — وأقربُهما إلى الحالة المطلوبة هي الـRFQ العامّ (مواصفة #147).**

### أ) الرابط العامّ للطلبيّة (`purchase_rfq`) — القالب الكامل

**دورةُ حياة الرابط:** `logistics/views/procurement.py`
(`PurchaseRFQViewSet.public_link`) ينشئ `DocumentShare` بـ`is_public=True`
و`dedupe=True` ضمن جمهوره، ومدّتُه من `logistics/services.py`
(`public_rfq_share_expiry_days`) لا الشهرِ الافتراضيّ. وإيقافُه فعلٌ صريح
(`stop_public_link` ← `logistics/services.py` (`revoke_live_public_rfq_share`))،
**ويُبطَل تلقائيّاً عند الترسية أو الإلغاء** من داخل `award()`/`cancel()`.

**التحقّق من الرابط:** `docshare/services.py` (`resolve_share`) — التوكن ⇒ الصفّ
⇒ `is_live` (لا مُبطَل ولا منتهٍ) ⇒ النوع في `DOC_TYPES` ⇒ الوحدة ما تزال
مرخّصة (وإلّا **٤١٠** لا ٤٠٤: «الرابط كان حيّاً يوماً») ⇒ `loader` يجلب المستند
أو ٤٠٤.

**الاستقبال:** `docshare/views.py` (`DocShareQuoteView.post`) — سطحٌ عامٌّ
(`authentication_classes = []`)، **بخانقٍ مستقلٍّ أضيق** (`doc_share_public_quote`
= 20/min) معلَّلٍ بأنّ خانق القراءة «مضبوطٌ على رابطٍ يُفتح مرّةً أو مرّتين».
يجمع الحقول `price_<line_id>` في `{line_id: raw_price}` **بلا أيّ معرفةٍ ببنية
المستند**، ويسلّمها إلى `docshare/services.py` (`submit_quote`) الذي يقفل الصفّ
(`select_for_update`) ويفوّض التطبيق إلى `DOC_TYPES[…]["quote"]`
(`docshare/documents/purchase_docs.py`). CSRF غير مفروضٍ هنا — موثَّقاً: DRF لا
يفرضه إلّا داخل `SessionAuthentication`.

**التفريعُ بالجمهور:** `docshare/documents/purchase_docs.py`
(`_rfq_public_share`) — رابطٌ خاصٌّ ⇒ `logistics/services.py`
(`submit_rfq_supplier_quote`) يكتب في الدفاتر؛ رابطٌ عامٌّ ⇒
`logistics/services.py` (`record_public_quote_request`).

**وهنا القاعدةُ الجوهريّة — الحجرُ الصحّيّ:** المُدخَل من المجهول **لا يُكتب في
الدفاتر أبداً**. يذهب إلى جدولَي انتظارٍ مستقلَّين: `logistics/models.py`
(`PublicSupplierQuoteRequest`) و(`PublicSupplierQuoteRequestLine`) — «مساحةُ
انتظار لا كتابٌ للدفاتر». والصفّ يحمل: `tenant`، `rfq`، `share`
(`SET_NULL` كي لا يمحو إبطالُ الرابط ردّاً وصل فعلاً)، `supplier_name`،
`supplier_email`، `supplier_phone`، `submitted_ip`، `submitted_at`، و`status`
(`pending`/`approved`/`rejected`)، و`email_verified_at` **مُعدٌّ سلفاً ولا
يُكتَب في هذه المرحلة** كي لا تحتاج ميزةُ تحقّق البريد لاحقاً هجرةً ثانية. ولا
يُنشَأ `Partner` ولا `SupplierQuotation` إلّا بموافقةٍ بشريّةٍ صريحة
(`approve_public_quote_request`)، والتكرار **يُقترَح لا يُدمَج**
(`partners.suggest_partner_matches`).

**والتحقّقاتُ على المُدخَل** (`record_public_quote_request`): الاسم والبريد
إلزاميّان؛ حالةُ الطلبيّة يجب أن تكون `SENT` (وإلّا «لم تعد الطلبية تقبل
الأسعار»)؛ كلُّ سعرٍ يُفسَّر `Decimal` ويُرفض السالبُ وغيرُ الصالح، ويُشترط سعرٌ
لبندٍ واحدٍ على الأقلّ؛ **وصفٌّ جديدٌ لكلّ إرسال، أبداً تحديثٌ لسابق** — «لا حساب
يربط الغريب الثاني بالأوّل، والدهسُ يعني أنّ غريباً يمحو سعر غريبٍ آخر بصمت»؛
ولقطاتٌ إلزاميّة (`name_snapshot`/`seq_snapshot`) كي لا يضيع سعرٌ كتبه إنسانٌ لو
حُذف بندُ الطلبيّة؛ وقيدُ قاعدةٍ `pub_qr_line_price_gte_zero`؛ وسطرُ سجلٍّ
(`logger.info` مع `rfq`/`request`/`ip`).

**ما لا تملكه هذه السابقة:** لا تستقبل **ملفّاً** إطلاقاً — أرقامٌ ونصوصٌ فقط.
ولا سقفَ على عدد الردود، ولا إغلاقَ تلقائيّاً بالحجم، ولا CAPTCHA، ولا تحقّقَ
من البريد — كلُّها مخالفاتٌ واعيةٌ موثَّقةٌ في `docshare/views.py`
(`DocShareQuoteView`) و`core/settings.py`.

### ب) نيّةُ الطلب في المتجر (`store`)

`store/views.py` (`StoreOrderIntentView.post`) — «نقطةُ كتابةٍ عامّة بلا
مصادقة»: سقفٌ على عدد البنود (`MAX_ITEMS=50`) وعلى الكميّة
(`MAX_QUANTITY_PER_ITEM=100_000`)، **والمجموع يُحسَب على الخادم دائماً — ما
أرسله العميل من أسعارٍ لا يُقرأ إطلاقاً**، ومعرّفاتُ منتجاتٍ لا تخصّ هذه الشركة
أو غيرُ منشورةٍ تُسقَط **بصمت** («معرّفٌ أجنبي يُعطي فراغاً لا تسريباً»). لا
ملفّات فيها كذلك.

---

## آليّاتٌ جاهزة لإعادة الاستعمال

1. **صنفُ أساسٍ عامٍّ جاهزٌ للنسخ** — `docshare/views.py` (`DocSharePublicBase`)
   و`store/views.py` (`StorePublicView`): `authentication_classes = []` +
   `AllowAny` + `throttle_scope` خاصّ.
2. **مفتاحٌ عامٌّ ناضج** — `docshare/models.py` (`DocumentShare`) +
   `docshare/services.py` (`TOKEN_BYTES`, `create_share`): ٢٥٦ بت، انتهاءٌ
   إلزاميّ (7/30/90)، إبطالٌ فوريّ بلا حذف، عدّادُ مشاهدات.
3. **حلُّ الرابط بقواعدَ واحدة** — `docshare/services.py` (`resolve_share`,
   `DocumentShare.is_live`) مع تمييز ٤٠٤/٤١٠ وفحص ترخيص الوحدة.
4. **جمهوران مخزَّنان لا مستنتَجان** — `DocumentShare.is_public` +
   `docshare/services.py` (`active_share`) الذي يجعل الجمهور جزءاً من الاستعلام.
5. **حجرٌ صحّيٌّ لمُدخَل المجهول** — `logistics/models.py`
   (`PublicSupplierQuoteRequest`) + `logistics/services.py`
   (`record_public_quote_request`) + `approve_public_quote_request`: جدولُ
   انتظارٍ بحالة `pending`، لا كتابةَ في الدفاتر إلّا بموافقةٍ بشريّة، وصفٌّ
   جديدٌ لكلّ إرسال، ولقطاتٌ تحفظ المُدخَل من حذفٍ لاحق.
6. **خانقٌ لكلّ نطاقٍ عامٍّ على حدة** — `core/settings.py`
   (`DEFAULT_THROTTLE_RATES`)؛ إضافةُ نطاقٍ جديد سطرٌ واحد، وسابقةُ «الكتابة
   أضيقُ من القراءة» مثبتةٌ في `doc_share_public_quote` (20/min مقابل 60/min).
7. **قلبُ رفعٍ واحدٌ بحدٍّ وحصّة** — `core/media_views.py` (`upload_media_file`,
   `MAX_UPLOAD_BYTES`, `MediaUploadThrottle`) + سجلُّ استهلاكٍ
   (`core.TenantAsset` عبر `_record_asset`) + حذفٌ أفضل-جهد
   (`destroy_cloudinary_asset`).
8. **تقسيةُ الترويسات للسطح العامّ** — `docshare/views.py` (`_harden`):
   `noindex` + `no-store` مستقلّاً عن `NoStoreAPIMiddleware`.
9. **اختبارُ تسريبٍ سالبٌ بمساواة المجموعات** —
   `docshare/tests/test_public_leakage.py` و`store/tests/test_public_leakage.py`:
   `set(keys) == WHITELIST`، فأيّ حقلٍ يُضاف مستقبلاً يُسقط المجموعة.
10. **حارسُ الخنق العامّ** — `core/tests/test_global_throttle.py` (يوثّق أيضاً
    أنّ الصلاحية تسبق الخنق في DRF).
11. **رابطٌ يُبنى من إعدادٍ لا من ترويسة `Host`** — `docshare/services.py`
    (`public_url`) عبر `DOCSHARE_PUBLIC_BASE_URL`/`DOCSHARE_PUBLIC_PATH`.
12. **حياد المحرِّك عن نوع المستند** — `docshare/documents/` (`DOC_TYPES`) مع
    `loader`/`builder`/`decision`/`quote`: نوعٌ جديد = إدخالٌ في السجلّ + سطرٌ في
    `DOC_TYPE_CHOICES`، بلا لمسِ الـviews.
13. **سجلُّ نشاطٍ موحّد** — `core.activity.log_activity` (يُستعمل عند الإنشاء
    والإبطال في `docshare/services.py`).

---

## ثغراتٌ يجب سدّها قبل فتح نقطةٍ عامّةٍ تقبل ملفاً

1. **لا سابقةَ لاستقبال ملفٍّ من مجهول إطلاقاً.** كلُّ رفعٍ في المنصّة يمرّ من
   `core/media_views.py` (`media_upload`) وهي `IsAuthenticated` — ودوكسترينغُها
   يوثّق أنّ الرفع المجهول **أُزيل عمداً** (P0-8): «كانت النقطة `AllowAny` بلا
   مصادقة ولا throttle ⇒ أي زائر يقدر يشغّل رفع Cloudinary متزامناً حتى 25MB
   فيقفل worker (وسقف الـworkers = 3)». أيُّ صفحةٍ عامّةٍ تقبل ملفاً تُعيد فتح
   هذه الثغرة بعينها ما لم تُعالَج بحصّةٍ ومتطلَّبٍ آخر.
2. **لا حصرَ لأنواع الملفات ولا فحصَ لمحتواها.** `core/media_views.py`
   (`_resource_type`) يصنّف ولا يمنع؛ لا قائمةَ امتداداتٍ بيضاء، ولا فحصَ
   `magic bytes`، ولا مضادَّ فيروسات في المستودع. و`.svg` مصنَّفٌ صورةً.
3. **٢٥ ميغابايت سقفٌ واحدٌ لكلّ شيء.** `MAX_UPLOAD_BYTES` لا يميّز مجهولاً عن
   مستخدم؛ والسابقةُ الوحيدة لسقفٍ أضيق هي `hr/attendance_api.py`
   (`MAX_IMPORT_BYTES` = 2 MB).
4. **الملفّ المرفوع عامٌّ إلى الأبد بمجرّد وجود رابطه.** لا رابطَ موقَّعٌ موقَّت
   ولا وسيطُ تقديمٍ يفحص الشركة؛ `core.SystemAttachment.file_path` رابط
   Cloudinary مكشوف — والقراءة **غيرُ محروسةٍ بالشركة** بأيّ حال. سيرةٌ ذاتيّة
   تحمل اسماً وهاتفاً ليست صورة منتج.
5. **`AllowAny` تسرّب خارج `store`/`docshare`** — `accountant_portal/views.py`
   (`VerifyEmailView`, `ResendVerificationView`) و`accounting/views.py`
   (`CurrencyViewSet`). القاعدة المكتوبة في رؤوس الملفّات لم تعد صادقةً حرفيّاً،
   ولا حارسَ آليّاً يمنع التسرّب الرابع.
6. **`CurrencyViewSet` نقطةٌ عامّةٌ بلا `throttle_scope`** — تعتمد على `anon`
   العامّ وحده، وتعيش داخل `accounting/views.py` لا في app عامّة.
7. **هويّةُ الخنق للمجهول قابلةٌ للتلفيق.** `NUM_PROXIES` غير مضبوط
   (`core/settings.py`)، فـ`BaseThrottle.get_ident` يتّخذ كامل `X-Forwarded-For`
   هويّةً — ترويسةٌ يرسلها العميل. الخنقُ بالـIP على سطحٍ عامٍّ ليس حاجزاً موثوقاً
   قبل ضبط `DRF_NUM_PROXIES`.
8. **عدّادات الخنق بلا قفلٍ بين العمليات إن غاب Redis** — `core/settings.py`
   (`CACHES` ← `ResilientFileBasedCache`)، وهو مذكورٌ في الإعدادات نفسِها.
9. **لا CAPTCHA ولا تحقّقَ من هويّة المُرسِل** في أيّ سطحٍ عامّ — مخالفةٌ واعيةٌ
   موثَّقة، لكنّها تبقى مفتوحةً هنا. و`PublicSupplierQuoteRequest.email_verified_at`
   حقلٌ **موجودٌ ولا يُكتب**.
10. **لا سقفَ على عدد الإرسالات لكلّ رابطٍ عامّ ولا إغلاقَ تلقائيّ بالحجم** —
    `docshare/views.py` (`DocShareQuoteView`) يصرّح بذلك. مع ملفّاتٍ يصير هذا
    امتلاءَ تخزينٍ لا مجرّد صفوفٍ مكرّرة.
11. **لا حصّةَ تخزينٍ نافذة.** `core.TenantAsset` **يقيس** ولا يمنع
    (`core/media_views.py` (`_record_asset`) «أفضل-جهد لا يُسقط رفعاً ناجحاً»)،
    ولا يُنسَب رفعُ المجهول إلى أحدٍ أصلاً.
12. **لا مسارَ حذفٍ مضمون.** `destroy_cloudinary_asset` أفضل-جهد؛ ولا سياسةَ
    احتفاظٍ (retention) لأيّ مرفقٍ في المستودع — وسيرةٌ ذاتيّة بيانٌ شخصيّ له
    عمرٌ مفترَض.
13. **لا مفتاحَ صلاحيّةٍ يفصل «رابطٌ خاصّ» عن «رابطٌ للعموم»** — كلاهما تحت
    `purchase.document.share` (`docshare/documents/purchase_docs.py`)، و
    `logistics/views/procurement.py` (`public_link`) لا يفرض مفتاحاً ثالثاً.
14. **الصفّ العامّ لا يحمل بريداً/هاتفاً مُتحقَّقاً** — `submitted_ip` وحده
    (وهو مأخوذٌ من `docshare/services.py` (`_client_ip`) ⇒ أوّلُ مدخلٍ في
    `X-Forwarded-For`، أي قابلٌ للتلفيق كذلك؛ قيمتُه توثيقيّةٌ لا أمنيّة).

---

## ما لم يُتحقَّق منه في هذه الجلسة

- **إعدادات nginx/الاستضافة الفعليّة** (`client_max_body_size`، وهل تُمرَّر
  `X-Forwarded-For` مُعادَ كتابتها) — خارج المستودع، ولا ملفَّ nginx فيه.
- **إعدادات Cloudinary من جهة الحساب** (هل التسليم موقَّعٌ أو مقيَّد، وحدودُ
  الخطّة) — خارج الكود؛ الكودُ يستعمل `secure_url` غير الموقَّع فحسب.
- **قيم متغيّرات البيئة على الإنتاج** (`REDIS_URL`، `DRF_NUM_PROXIES`،
  `THROTTLE_RATE_*`، `DOCSHARE_PUBLIC_*`) — القيمُ أعلاه هي الافتراضيّات
  المكتوبة في `core/settings.py`.
- **`codebase-memory-mcp` لم يكن متاحاً** في هذه الجلسة (فشل الاتصال)، فكلُّ ما
  سبق من قراءةٍ مباشرةٍ للملفّات و`grep` لا من الرسم المعرفيّ.
