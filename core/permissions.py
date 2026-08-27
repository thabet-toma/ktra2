"""task11 R2-B — فرض أدوار العضوية على مستوى المنصة.

الأدوار (UserCompanyMembership.role) كانت موجودة منذ task10 لكنها لم تُفرض
في أي endpoint عمليات — «مستعرض» كان يستطيع ترحيل قيود وحذف مسودات وتعديل
إعدادات. هذه الطبقة تفرض الحد الأدنى الواضح:

    viewer  → قراءة فقط (GET/HEAD/OPTIONS)
    غيره    → حسب فحوصات كل endpoint (manager-only تبقى في مكانها)

تُطبَّق افتراضياً عبر ApiAuthAndUser وعبر DEFAULT_PERMISSION_CLASSES.
"""
import logging

from django.core.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.plans import subscription_expired

logger = logging.getLogger(__name__)


def is_read_only_post(request, view) -> bool:
    """POST قراءةٌ لا كتابة: نقطةٌ قرائية يسافر محدِّدها في **جسم** الطلب لأن سطر
    الطلب لا يسعه — الكرت المجمّع يمرّر معرّفات تصنيفٍ فيه ~1500 منتج (~7.5KB في
    سطر الطلب ⇒ nginx يردّ 414). الـview يعلنها في `read_only_post_actions`،
    فتُفحص هنا كأنها GET: يسقط شرط «ليس مستعرضاً» وحده، ويبقى كل ما عداه
    (المسارات المقيَّدة على المحاسب القانوني، والعضوية) كما هو.
    """
    return (
        request.method == "POST"
        and getattr(view, "action", None) in getattr(view, "read_only_post_actions", ())
    )


def subscription_block_reason(tenant, user) -> str | None:
    """T-TRIAL: سبب منع الكتابة إن انتهى اشتراك الشركة، وإلا `None`.

    القاعدة في دالّة واحدة لأن لها **مستدعيَين**: الحارس العام أدناه، وبوابة
    المحاسب التي تستبدل `permission_classes` بـ`[IsAuthenticated]` فلا يمرّ بها
    الحارس العام أصلاً. نسخةٌ ثانية من الشرط هناك كانت ستفترق عن هذه بيومٍ أو
    بشرطِ `>=` مقابل `>` عند أول تعديل.

    السوبر أدمن مستثنى: هو من يجدّد الاشتراك المنتهي.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return None
    if tenant is None or not subscription_expired(tenant):
        return None
    return (
        f"انتهى اشتراك الشركة بتاريخ {tenant.subscription_ends_at:%Y-%m-%d} — "
        "الحساب للقراءة والطباعة فقط. تواصل مع إدارة المنصة لتجديد الاشتراك."
    )


def require_active_subscription(request, tenant) -> None:
    """يمنع الكتابة على شركة انتهى اشتراكها — للمسارات خارج `TenantRolePermission`.

    القراءات تمرّ (`SAFE_METHODS`)، فيبقى للزبون أن يرى ويطبع ويصدّر.
    """
    if request is not None and request.method in SAFE_METHODS:
        return
    reason = subscription_block_reason(tenant, getattr(request, "user", None))
    if reason is None:
        return
    logger.info(
        "subscription_expired_write_blocked tenant=%s user=%s path=%s",
        getattr(tenant, "pk", None), getattr(request.user, "pk", None), request.path,
    )
    raise PermissionDenied(reason)


class TenantRolePermission(BasePermission):
    message = "صلاحيتك في هذه الشركة «مستعرض» — قراءة فقط."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            # المصادقة نفسها مسؤولية IsAuthenticated — لا نكررها هنا
            return True
        if user.is_superuser:
            return True

        from accountant_portal.permissions import is_restricted_accountant_route

        restricted_route = is_restricted_accountant_route(request.path)
        legal_office_bootstrap = (
            request.method == "POST"
            and request.path.rstrip("/") == "/api/tenants/companies"
        )
        is_read = request.method in SAFE_METHODS or is_read_only_post(request, view)
        if is_read and not restricted_route:
            return True

        from core.tenant_utils import get_tenant
        # get_tenant يرفع PermissionDenied لغير الأعضاء — يصل 403 من هناك
        tenant = get_tenant(request)
        from tenants.models import UserCompanyMembership

        if tenant is None:
            has_legal_membership = UserCompanyMembership.objects.filter(
                user=user,
                role="legal_accountant",
            ).exists()
            if has_legal_membership and (
                restricted_route
                or (
                    not is_read
                    and not request.path.startswith("/api/accountant/")
                    and not legal_office_bootstrap
                )
            ):
                self.message = "يلزم سياق شركة صالح للمحاسب القانوني الخارجي."
                return False
            return True  # بلا سياق شركة — فحوصات أخرى تتكفل

        # T-TRIAL: انتهى اشتراك الشركة ⇒ قراءة وطباعة وتصدير، بلا كتابة. يقع
        # الفحص هنا لا في `get_tenant`: الإيقاف الإداري يمنع الدخول كلّه، أما
        # انتهاء التجربة فيترك الزبون يرى بياناته ويصدّرها — منعُه منها يفقده
        # سبب الترقية أصلاً. القراءات خرجت أعلاه قبل هذا السطر، والسوبر أدمن
        # خرج قبلها، فما يصل هنا كتابةٌ من عضو في شركة انتهى وقتها.
        expiry_reason = subscription_block_reason(tenant, user)
        if expiry_reason is not None:
            logger.info(
                "subscription_expired_write_blocked tenant=%s user=%s path=%s ends_at=%s",
                tenant.pk, user.pk, request.path, tenant.subscription_ends_at,
            )
            self.message = expiry_reason
            return False

        cached_role = getattr(request, "_tenant_membership_role", None)
        if cached_role and cached_role[0] == tenant.pk:
            role = cached_role[1]
        else:
            membership = (
                UserCompanyMembership.objects
                .filter(user=user, tenant=tenant)
                .only("role")
                .first()
            )
            role = membership.role if membership is not None else None
        if role is None:
            return True  # superuser بلا عضوية أو سياق خاص — العضوية مفروضة في get_tenant
        if role == "legal_accountant" and restricted_route:
            self.message = "هذا المسار التشغيلي غير متاح للمحاسب القانوني الخارجي."
            return False
        if (
            role == "legal_accountant"
            and not is_read
            and not request.path.startswith("/api/accountant/")
            and not legal_office_bootstrap
        ):
            self.message = "الكتابة التشغيلية متاحة للمحاسب من بوابة المراجعة فقط."
            return False
        if is_read:
            return True
        return role != "viewer"
