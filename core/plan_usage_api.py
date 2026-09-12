"""نقطة «خطّتي»: حدودُ شركةِ الطالب واستهلاكُها — لعضوٍ فيها، لا للمنصّة.

**لماذا ملفٌّ مستقلّ:** لأنّ المقابلَ له مستقلٌّ لسببٍ أمنيّ. حدودُ الخطط
واستهلاكُها موجودةٌ اليوم في مكانين: `core/public_pricing.py` **بلا مصادقةٍ
إطلاقاً** (أرقامُ الخطط لا أرقامُ شركة)، و`core/platform_admin_api.py` خلفَ
`IsPlatformAdmin` (كلُّ شركةٍ على المنصّة). وهذه ثالثةٌ بينهما تماماً: أرقامُ
**شركةٍ واحدةٍ لعضوٍ فيها**. دسُّها في أيٍّ من الملفّين يجعل حدَّ الصلاحيّة في
ذلك الملفّ غيرَ صحيحٍ في سطرٍ واحدٍ منه — وهذا بالضبط شكلُ الثغرة التي تمرّ في
المراجعة.

ولا كتابةَ هنا: رفعُ حدٍّ يبقى في لوحة المنصّة حيث هو.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.plans import PLAN_LABELS, _plan_of, tenant_usage_rows
from core.tenant_utils import get_tenant


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_plan_usage(request):
    """حدودُ الشركة الحاليّة واستهلاكُها، لأيّ عضوٍ فيها.

    **الشركةُ من `get_tenant(request)` حصراً** — لا من معاملٍ في العنوان ولا من
    جسم الطلب. والدالّةُ تتحقّق من عضويّة المستخدم في الشركة التي تطلبها ترويسةُ
    `X-Tenant-Id`، فترويسةٌ مزوّرةٌ لشركةٍ أخرى تُرَدّ لا تُخدَم. هذه هي قاعدةُ
    العزل نفسُها التي تسري على كلّ ViewSet في المستودع، مكتوبةً هنا صراحةً لأنّ
    هذه دالّةٌ لا ViewSet فلا `get_queryset` تحرسها.

    **ولأيّ عضوٍ لا للمدير وحدَه**: الرقمُ المعروض هو «كم بقي من حصّتك»، وحارسُ
    `enforce_limits` يرفع رسالتَه في وجه **أيّ** مستخدمٍ يبلغ الحدّ — فمن يُمنَع
    من الإنشاء يحقّ له أن يرى لماذا قبل أن يُمنَع، لا بعدها فقط.
    """
    tenant = get_tenant(request)
    if tenant is None:
        # لا شركةَ محلولة: ردٌّ صريحٌ لا قائمةٌ فارغةٌ تُقرأ «استهلاكُك صفر».
        return Response({"detail": "لم تُحدَّد الشركة في الطلب."}, status=400)

    # `_plan_of` خاصّةٌ بالاسم لا بالعقد: هي قارئةُ الخطّة الوحيدة في
    # `core/plans.py` ويستعملها `limit_value` و`limit_exceeded_message`
    # نفسُهما. نسخةٌ ثانيةٌ هنا تعني خطّةً معروضةً تخالف الخطّةَ المفروضة.
    plan = _plan_of(tenant)
    return Response({
        "plan": plan,
        "plan_label": PLAN_LABELS.get(plan, plan),
        "limits": tenant_usage_rows(tenant),
    })
