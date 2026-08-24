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
from rest_framework.permissions import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access import require_perm
from core.api_defaults import ApiAuthAndUser
from core.mixins import TenantQuerySetMixin
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


def _page_context(request, share, document, payload):
    company = company_card(share.tenant)
    today = timezone.localdate()
    expired_offer = bool(payload["valid_until"] and payload["valid_until"] < today)
    return {
        "doc": payload,
        "company": company,
        "share": share,
        "public_url": services.public_url(share),
        "expired_offer": expired_offer,
        # القرار متاح متى كانت حالة العرض تسمح، **ولم** تنقضِ صلاحيته، **ولم**
        # يُقرَّر على هذا الرابط من قبل. الشروط الثلاثة مستقلة ولكلٍّ رسالته.
        "can_decide": payload["can_decide"] and not expired_offer and not share.decision,
        "decision_error": "",
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
        try:
            services.record_decision(token, decision, name, request)
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


class DocumentShareViewSet(TenantQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """سطح الإدارة المصادَق عليه — إنشاء الرابط وقراءته وإبطاله.

    `ReadOnlyModelViewSet` لا `ModelViewSet`: الرابط لا يُعدَّل بـPATCH ولا
    يُحذَف. يُنشأ بفعلٍ صريح ويُبطَل بفعلٍ صريح، وبينهما هو حقيقةٌ لا تُحرَّر.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = DocumentShareSerializer
    queryset = DocumentShare.objects.all().order_by("-created_at", "-id")

    def get_queryset(self):
        queryset = super().get_queryset()
        doc_type = self.request.query_params.get("doc_type")
        doc_id = self.request.query_params.get("doc_id")
        if doc_type:
            queryset = queryset.filter(doc_type=doc_type)
        if doc_id and str(doc_id).isdigit():
            queryset = queryset.filter(doc_id=int(doc_id))
        return queryset

    def list(self, request, *args, **kwargs):
        require_perm(request, "sales.document.share")
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        require_perm(request, "sales.document.share")
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        require_perm(request, "sales.document.share")
        tenant = get_tenant(request, raise_on_missing=True)
        doc_type = (request.data.get("doc_type") or "").strip()
        doc_id = request.data.get("doc_id")
        if doc_type not in DOC_TYPES or not str(doc_id).isdigit():
            return Response(
                {"detail": "نوع المستند أو معرّفه غير صالح."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
        require_perm(request, "sales.document.share")
        share = self.get_object()
        services.revoke_share(share, user=request.user, request=request)
        return Response(self.get_serializer(share).data)
