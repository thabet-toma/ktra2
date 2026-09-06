"""السطح العام للمستند المُشارَك — وسطح إدارته المصادَق عليه.

**كل كود `AllowAny` في هذا الملف ملفٌّ واحد يُقرأ كاملاً في جلسة**، وهي نفس
حجّة `store/views.py`. الفرق الوحيد أن هذا السطح يُصيَّر HTML لا JSON: زاحف
واتساب وفيسبوك **لا ينفّذ JavaScript**، فصفحة SPA تُعطيه عنواناً فارغاً بلا
معاينة. الصفحة الخادمية هي الطريق الوحيد إلى معاينةٍ تحمل اسم الشركة وشعارها.

الصفحة تعمل **بلا JavaScript إطلاقاً**: القرار نموذج POST عادي، والطباعة
`window.print()` في زر واحد لا يعتمد عليه شيء آخر.
"""
import logging

from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access import require_perm, user_has_perm
from core.api_defaults import ApiAuthAndUser
from core.mixins import TenantQuerySetMixin
from core.modules import module_enabled, require_module
from core.tenant_utils import get_tenant
from docshare import services
from docshare.documents import DOC_TYPES, company_card
from docshare.models import DECISION_ACCEPTED, DECISION_REJECTED, DocumentShare
from docshare.serializers import DocumentShareSerializer

logger = logging.getLogger(__name__)

SHARE_TEMPLATE = "docshare/share.html"
NOTICE_TEMPLATE = "docshare/notice.html"


def _harden(response, *, status_code=200):
    """ترويسات هذا السطح: لا فهرسة، ولا تخزين، مهما كان المسار.

    `NoStoreAPIMiddleware` يغطّي `/api/*` وحده، ومسار `/s/` خارجه — فالضبط هنا
    لا هناك، كي لا يعتمد أمان الصفحة على أي المسارين فُتح.
    """
    response.status_code = status_code
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    return response


def _notice(request, title, message, status_code):
    return _harden(
        Response(
            {"notice_title": title, "notice_message": message},
            template_name=NOTICE_TEMPLATE,
        ),
        status_code=status_code,
    )


class DocSharePublicBase(APIView):
    """الأساس العام: بلا مصادقة إطلاقاً، وبسقف معدّل خاص به.

    `authentication_classes = []` ليست زينة: توكنٌ يُرسَل إلى هذه النقطة لا
    يقدر أن يغيّر حرفاً في الرد — خاصية بنيوية لا وعدٌ في مراجعة.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "doc_share_public"
    renderer_classes = [TemplateHTMLRenderer]


def _attach_quote_prefill(share, document, payload):
    """يُلحق بكل بندٍ سعرَ **صاحب هذا الرابط** إن كان قد أرسله من قبل، ومعه
    عملتُه (ISSUE #133 غ٢) وملاحظاته (غ٣) — `prefill_fn` يعيد `{"prices":
    {...}, "notes": {...}, "currency_id": ..., "general_note": ...}` منذ
    هذه التذكرة.

    في طبقة العرض لا في الباني: `build_*` لا يعرف بالرابط ولا يجوز أن يعرف —
    حمولتُه مدقَّقةٌ بالقائمة البيضاء في `test_public_leakage.py` وتبقى كما هي.
    والقيمةُ هنا سعرُ المورّد نفسِه وملاحظتُه هو لا رقمٌ أو نصٌّ من دفترنا،
    فلا تسريب.
    """
    quote_spec = (DOC_TYPES.get(share.doc_type) or {}).get("quote") or {}
    prefill_fn = quote_spec.get("prefill")
    if not prefill_fn:
        return
    prefill = prefill_fn(document, share) or {}
    if not prefill:
        return
    prices = prefill.get("prices") or {}
    notes = prefill.get("notes") or {}
    for line in payload.get("lines") or []:
        line_id = line.get("id")
        value = prices.get(line_id)
        if value is not None:
            # **نصّاً لا `Decimal`**: تعريبُ جانغو يقلب النقطة العشرية فاصلةً
            # («11,5000»)، و`<input type="number">` يرفض تلك القيمة صامتاً —
            # فتُعرَض الخانةُ فارغةً وكأن شيئاً لم يُرسَل.
            line["price"] = format(value, "f")
        note_value = notes.get(line_id)
        if note_value:
            line["note"] = note_value
    if payload.get("quote") is not None:
        currency_id = prefill.get("currency_id")
        if currency_id is not None:
            payload["quote"]["selected_currency_id"] = currency_id
        general_note = prefill.get("general_note")
        if general_note:
            payload["quote"]["general_note_value"] = general_note


def _attach_quote_currency_options(share, document, payload):
    """يُلحق قائمة العملات المتاحة للتسعير — ISSUE #133 غ٢.

    مفتاحٌ اختياريّ مثل `prefill` تماماً: نوعٌ لا يُعرّفه لا يكسب قائمة عملات
    ولا يُخفق شيء. الحمولة المبنيّة نفسها لا تعرف بهذا — القائمة البيضاء في
    `test_public_leakage.py` تُقاس على مخرَج الباني مباشرةً، وهذه الدالّة
    تعمل بعده في طبقة العرض.
    """
    quote_spec = (DOC_TYPES.get(share.doc_type) or {}).get("quote") or {}
    options_fn = quote_spec.get("currency_options")
    if not options_fn or payload.get("quote") is None:
        return
    payload["quote"]["currency_options"] = options_fn(document)


def _page_context(request, share, document, payload):
    _attach_quote_prefill(share, document, payload)
    _attach_quote_currency_options(share, document, payload)
    company = company_card(share.tenant)
    today = timezone.localdate()
    expired_offer = bool(payload["valid_until"] and payload["valid_until"] < today)
    decision = payload["decision"]
    return {
        "doc": payload,
        "company": company,
        "share": share,
        "public_url": services.public_url(share),
        "expired_offer": expired_offer,
        # القرار متاح متى كان النوع يقبله، **وكانت** حالة المستند تسمح، **ولم**
        # تنقضِ صلاحيته، **ولم** يُقرَّر على هذا الرابط من قبل. الشروط الأربعة
        # مستقلة ولكلٍّ رسالته.
        "can_decide": bool(
            decision and decision["open"] and not expired_offer and not share.decision
        ),
        "decision_error": "",
        "quote_error": "",
        "quote_error_en": "",
        # ISSUE #115: العَلَم يصل عبر `?submitted=1` بعد إعادة توجيه ناجحة
        # (Post/Redirect/Get) — التسعير يُقبل مراراً فلا معنى لقفل الصفحة على
        # «تمّ» دائم كما يفعل `share.decision` مع القرار.
        "quote_submitted": request.GET.get("submitted") == "1",
        **_mount_urls(request, share.token),
    }


def _mount_urls(request, token):
    """عناوين هذه الصفحة **من نطاق المسار الذي خُدمت منه**، لا من ثابت `/s/`.

    السطح مركَّب مرتين (`/s/` و`/api/share/`) لأن `/s/` يلزمه سطر `location`
    في nginx بينما `/api/` ممرَّر أصلاً. لو ثبَّتنا `/s/` في نموذج القرار
    وفي التحويل بعده، لانكسر القبول والرفض **بصمت** على التركيب الاحتياطي:
    الطلب يسقط في `location /` فيردّ nginx صفحة الـSPA بحالة 200 — فيضغط
    الزبون «موافق» ويرى واجهة التطبيق، ولا يُسجَّل شيء ولا يظهر خطأ.
    `resolver_match.namespace` يقول أيّ تركيب استُعمل، فيُبنى الباقي عليه.
    """
    namespace = getattr(request.resolver_match, "namespace", "") or "docshare-s"
    return {
        "page_url": reverse(f"{namespace}:docshare-public", args=[token]),
        "decision_url": reverse(f"{namespace}:docshare-decision", args=[token]),
        "quote_url": reverse(f"{namespace}:docshare-quote", args=[token]),
    }

class DocSharePublicView(DocSharePublicBase):
    """`GET /s/<token>` و`GET /api/share/<token>/` — صفحة المستند."""

    def get(self, request, token):
        try:
            share, document, payload = services.resolve_share(token)
        except services.ShareGone:
            return _notice(
                request,
                "انتهت صلاحية هذا الرابط",
                "لم يعد هذا الرابط صالحاً للعرض. اطلب من مُرسِله رابطاً جديداً.",
                status.HTTP_410_GONE,
            )
        except services.ShareNotFound:
            return _notice(
                request,
                "الرابط غير صالح",
                "لا يوجد مستند خلف هذا الرابط. تأكّد من نسخه كاملاً.",
                status.HTTP_404_NOT_FOUND,
            )

        services.record_view(share, request)
        return _harden(
            Response(_page_context(request, share, document, payload),
                     template_name=SHARE_TEMPLATE)
        )


class DocShareDecisionView(DocSharePublicBase):
    """`POST …/decision/` — قبول الزبون أو رفضه لعرض السعر.

    الردّ **تحويلٌ** إلى صفحة العرض (Post/Redirect/Get): تحديثُ الصفحة بعد
    القبول لا يجوز أن يعيد إرسال القرار، والصفحة بلا JavaScript يمنعه.
    CSRF غير مفروض هنا لأن `authentication_classes = []` — DRF لا يفرضه إلا
    داخل `SessionAuthentication`، وهو نفس ما يجري على نقاط `store`.
    """

    def post(self, request, token):
        decision = (request.data.get("decision") or "").strip()
        name = (request.data.get("name") or "").strip()
        note = (request.data.get("note") or "").strip()
        try:
            services.record_decision(token, decision, name, request, note=note)
        except services.ShareGone:
            return _notice(
                request,
                "انتهت صلاحية هذا الرابط",
                "لم يعد هذا الرابط صالحاً. اطلب من مُرسِله رابطاً جديداً.",
                status.HTTP_410_GONE,
            )
        except services.ShareNotFound:
            return _notice(
                request,
                "الرابط غير صالح",
                "لا يوجد مستند خلف هذا الرابط.",
                status.HTTP_404_NOT_FOUND,
            )
        except services.DecisionRefused as exc:
            # الصفحة تُعاد كاملةً بالسبب في مكانه — لا شاشة خطأ عارية يخرج
            # منها الزائر بلا طريق رجوع.
            try:
                share, document, payload = services.resolve_share(token)
            except (services.ShareGone, services.ShareNotFound):
                return _notice(
                    request, "الرابط غير صالح", "لا يوجد مستند خلف هذا الرابط.",
                    status.HTTP_404_NOT_FOUND,
                )
            context = _page_context(request, share, document, payload)
            context["decision_error"] = str(exc)
            return _harden(
                Response(context, template_name=SHARE_TEMPLATE),
                status_code=status.HTTP_409_CONFLICT,
            )

        return _harden(
            HttpResponseRedirect(_mount_urls(request, token)["page_url"]),
            status_code=302,
        )


class DocShareQuoteView(DocSharePublicBase):
    """`POST …/quote/` — تسعير المورّد على طلبٍ (ISSUE #115).

    مسارٌ **مستقلّ تماماً** عن `DocShareDecisionView`: الكتابة أسعارُ بنودٍ لا
    قرارُ قبول/رفض، وتُقبل مراراً ما دام النوع يقول إن الباب مفتوح — لا مرّةً
    واحدة كالقرار. الحقول `price_<line_id>` تصل من صناديق السعر في الجدول
    (مربوطة بالنموذج عبر `form="…"` لا بتداخل HTML، فالجدول يبقى خارج
    `<form>`)، ويجمعها هذا الـview في قاموسٍ `{line_id: raw_price}` يفسّره
    النوع نفسه — لا معرفة هنا بشكل بنود أيّ مستند.

    **مواصفة #147 (المرحلة 3ب): خانقٌ أضيق مستقلّ** — `doc_share_public`
    مضبوطٌ على **قراءة** رابطٍ يُفتح مرّةً أو مرّتين، وإعادة استعماله هنا كانت
    تعني عشرات الإرسالات في الدقيقة من عنوانٍ واحد على رابطٍ عامّ يملؤه غرباء.
    لا سقفَ على عدد الردود ولا إغلاقاً تلقائياً بالحجم (بحثٌ عبر ستة أنظمة
    مشابهة لم يجد سقفاً كهذا في أيٍّ منها)، ولا CAPTCHA في هذا الإصدار —
    مخالفةٌ واعية موثَّقة لا سهواً.
    """

    throttle_scope = "doc_share_public_quote"

    def post(self, request, token):
        name = (request.data.get("name") or "").strip()
        prices = {}
        for key, value in request.data.items():
            if not key.startswith("price_"):
                continue
            line_id = key[len("price_"):]
            if line_id.isdigit():
                prices[int(line_id)] = value

        try:
            services.submit_quote(token, name, prices, request)
        except services.ShareGone:
            return _notice(
                request,
                "انتهت صلاحية هذا الرابط",
                "لم يعد هذا الرابط صالحاً. اطلب من مُرسِله رابطاً جديداً.",
                status.HTTP_410_GONE,
            )
        except services.ShareNotFound:
            return _notice(
                request,
                "الرابط غير صالح",
                "لا يوجد مستند خلف هذا الرابط.",
                status.HTTP_404_NOT_FOUND,
            )
        except services.DecisionRefused as exc:
            try:
                share, document, payload = services.resolve_share(token)
            except (services.ShareGone, services.ShareNotFound):
                return _notice(
                    request, "الرابط غير صالح", "لا يوجد مستند خلف هذا الرابط.",
                    status.HTTP_404_NOT_FOUND,
                )
            context = _page_context(request, share, document, payload)
            error_message = str(exc)
            context["quote_error"] = error_message
            # ISSUE #133 غ٤ (مراجعة الجولة الثانية): «رسائلُ التحقّق» بندٌ
            # صريح في المواصفة — مورّدٌ يُخطئ يستحقّ أن يقرأ لماذا بلغته. مفتاح
            # اختياريّ على مواصفة النوع (`error_translations`)؛ نوعٌ لا
            # يعرّفه (أو رسالةٌ غير مُترجَمة فيه) يترك السطر الإنجليزيّ فارغاً
            # فيختفي — لا يظهر نصٌّ عربيٌّ مكرَّرٌ يتظاهر بأنه إنجليزيّ.
            quote_spec = (DOC_TYPES.get(share.doc_type) or {}).get("quote") or {}
            translations = quote_spec.get("error_translations") or {}
            context["quote_error_en"] = translations.get(error_message, "")
            return _harden(
                Response(context, template_name=SHARE_TEMPLATE),
                status_code=status.HTTP_409_CONFLICT,
            )

        url = _mount_urls(request, token)["page_url"]
        return _harden(HttpResponseRedirect(f"{url}?submitted=1"), status_code=302)


class DocumentShareViewSet(TenantQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """سطح الإدارة المصادَق عليه — إنشاء الرابط وقراءته وإبطاله.

    `ReadOnlyModelViewSet` لا `ModelViewSet`: الرابط لا يُعدَّل بـPATCH ولا
    يُحذَف. يُنشأ بفعلٍ صريح ويُبطَل بفعلٍ صريح، وبينهما هو حقيقةٌ لا تُحرَّر.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = DocumentShareSerializer
    queryset = DocumentShare.objects.all().order_by("-created_at", "-id")

    def _allowed_doc_types(self, request) -> set:
        """الأنواع التي يملك هذا المستخدم مشاركتها — من `DOC_TYPES` لا من ثابت.

        الصلاحية كانت `sales.document.share` **مثبَّتةً حرفياً** في كل طريقة
        هنا، بينما `DOC_TYPES[…]["permission"]` معلَنةٌ ومهملة. مع أول نوع شراء
        كان ذلك يعني: موظف المبيعات يشارك فواتير المورّدين، وموظف المشتريات
        لا يقدر أن يشارك مستنده هو.
        """
        tenant = get_tenant(request, raise_on_missing=False)
        if tenant is None:
            return set()
        return {
            doc_type for doc_type, spec in DOC_TYPES.items()
            if user_has_perm(request.user, tenant, spec["permission"])
            and (not spec.get("module") or module_enabled(tenant, spec["module"]))
        }

    def get_queryset(self):
        queryset = super().get_queryset()
        doc_type = self.request.query_params.get("doc_type")
        doc_id = self.request.query_params.get("doc_id")
        if doc_type:
            queryset = queryset.filter(doc_type=doc_type)
        if doc_id and str(doc_id).isdigit():
            queryset = queryset.filter(doc_id=int(doc_id))
        if self.action == "list":
            # يرى روابط ما يملك مشاركته وحده — لا كلَّ روابط الشركة. القائمةُ
            # مفلترةٌ لا محجوبة: من يملك المبيعات وحدها يرى روابط المبيعات.
            queryset = queryset.filter(
                doc_type__in=self._allowed_doc_types(self.request)
            )
        return queryset

    def list(self, request, *args, **kwargs):
        allowed = self._allowed_doc_types(request)
        if not allowed:
            raise PermissionDenied("لا تملك صلاحية مشاركة المستندات.")
        doc_type = request.query_params.get("doc_type")
        if doc_type and doc_type not in allowed:
            raise PermissionDenied("لا تملك صلاحية مشاركة هذا النوع من المستندات.")
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        share = self.get_object()
        spec = DOC_TYPES.get(share.doc_type)
        require_perm(request, spec["permission"] if spec else "sales.document.share")
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        tenant = get_tenant(request, raise_on_missing=True)
        doc_type = (request.data.get("doc_type") or "").strip()
        doc_id = request.data.get("doc_id")
        if doc_type not in DOC_TYPES or not str(doc_id).isdigit():
            return Response(
                {"detail": "نوع المستند أو معرّفه غير صالح."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        spec = DOC_TYPES[doc_type]
        # الترخيص **قبل** الصلاحية، و`require_module` يردّ **404 لا 403**
        # (`core/modules.py`) — قرارٌ قائم في المستودع: الوحدة غير المرخّصة
        # تختفي كمسارٍ غير موجود بدل أن تُعلن عن نفسها بـ«ممنوع». وترتيبُهما
        # هو ما يجعل ذلك صادقاً: لو سبقت الصلاحيةُ الترخيصَ لردّ السطح 403
        # على شركةٍ لا تملك الوحدة أصلاً — وهو إقرارٌ بوجودها.
        if spec.get("module"):
            require_module(request, spec["module"])
        # والصلاحية **بعد** التحقّق من صحّة النوع: نوعٌ مجهول خطأُ طلبٍ (400)
        # لا حرمانُ صلاحية، وقلبُ الترتيب يجعل الخطأ المطبعي يبدو منعاً.
        require_perm(request, spec["permission"])
        try:
            days = int(request.data.get("days") or services.DEFAULT_EXPIRY_DAYS)
        except (TypeError, ValueError):
            days = services.DEFAULT_EXPIRY_DAYS

        try:
            share = services.create_share(
                tenant, doc_type, int(doc_id),
                days=days, user=request.user, request=request,
            )
        except services.ShareNotFound:
            # 404 لا 403: 403 يُثبت لمن يخمّن المعرّفات أن المستند موجود.
            return Response(
                {"detail": "المستند غير موجود."}, status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(share)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        share = self.get_object()
        spec = DOC_TYPES.get(share.doc_type)
        require_perm(request, spec["permission"] if spec else "sales.document.share")
        services.revoke_share(share, user=request.user, request=request)
        return Response(self.get_serializer(share).data)
