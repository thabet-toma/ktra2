"""صفحة التحقق العامة للكفالة — `GET/HEAD /api/w/<token>` (#237).

**كل كود `AllowAny` في `after_sales` ملفٌّ واحد هو هذا الملف**، على نمط
`docshare/views.py` و`store/views.py`: يقرؤه مراجع الأمن كاملاً في جلسة.

HTML خادمي بلا JavaScript، ولا مصادقة، ولا كتابة، ولا عدّاد مشاهدات، ولا بحث
بالرقم التسلسلي. والرمز غير المطابق للنمط يُردّ قبل أي استعلام. الشركة هنا تأتي
من البطاقة نفسها لا من ترويسة الطلب، والوحدة المطفأة عندها تردّ 404 **بلا اسم الشركة**.
"""
import logging

from rest_framework.permissions import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules import module_enabled

from .models import WarrantyCard
from .services import MODULE_KEY
from .verify import TOKEN_PATTERN, public_view_model

logger = logging.getLogger(__name__)

PAGE_TEMPLATE = "after_sales/verify.html"
NOTICE_TEMPLATE = "after_sales/verify_notice.html"

NOT_FOUND_TEXT = "لا توجد كفالة مسجّلة خلف هذا الرمز — تحقّق من البائع"
UNAVAILABLE_TEXT = "التحقق الإلكتروني غير متاح حالياً؛ الشهادة الورقية تبقى المرجع — راجع البائع"


def _notice(message: str) -> Response:
    return Response({"notice_message": message}, template_name=NOTICE_TEMPLATE, status=404)


class WarrantyVerifyPublicView(APIView):
    """`authentication_classes = []` بنيوية لا زينة: رمزٌ يُرسَل هنا لا يغيّر حرفاً في الرد."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "warranty_verify_public"
    renderer_classes = [TemplateHTMLRenderer]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["X-Robots-Tag"] = "noindex"
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def get(self, request, token):
        if not TOKEN_PATTERN.fullmatch(token):
            return _notice(NOT_FOUND_TEXT)

        card = (
            WarrantyCard.objects
            .select_related("tenant", "tenant__settings", "product", "manufacturer_warrantor")
            .filter(verify_token=token)
            .first()
        )
        if card is None:
            return _notice(NOT_FOUND_TEXT)
        if not module_enabled(card.tenant, MODULE_KEY):
            return _notice(UNAVAILABLE_TEXT)

        logger.info("warranty verify page opened card=%s", card.pk)
        return Response({"page": public_view_model(card)}, template_name=PAGE_TEMPLATE)
