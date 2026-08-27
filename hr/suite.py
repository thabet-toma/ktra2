"""أساس وحدة الموارد البشرية الموسّعة (`hr_suite`) — بوابةٌ واحدة لكل ما هو جديد.

الوحدة **مرخَّصة لكل شركة**، وسطحها القديم ليس كذلك: نقاط الرواتب والموظفين
(`/api/hr/employees/`، `/api/hr/payslips/`…) تعمل لكل شركة كما كانت قبل الوحدة،
لأن حجبها خلف ترخيصٍ جديد كان سيُطفئ رواتب شركاتٍ تشتغل عليها اليوم.

فالنتيجة بابان في تطبيق واحد: القديم مفتوح، والجديد كلّه يرث
`HrSuiteViewSetBase` فيمرّ ببوابة الترخيص أولاً ثم الصلاحية. الترتيب مقصود
كما في `device_registry`: **404 لا 403** لشركةٍ غير مرخّصة — 403 يُثبت أن
الوحدة موجودة، و404 لا يُثبت شيئاً. واختبارُ البوابة يعدّد الـrouter كاملاً
إنفاذاً لهذه القاعدة، فلا يفلت ViewSet جديد من الوراثة سهواً.
"""
import logging

from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from accountant_portal.permissions import LegalAccountantRoutePermission
from core.access import require_perm
from core.mixins import BaseTenantViewSet
from core.modules import require_module

logger = logging.getLogger(__name__)

MODULE_KEY = "hr_suite"

PERM_ORG = "hr.org.manage"
PERM_SHIFTS = "hr.shifts.manage"
PERM_ATTENDANCE_VIEW = "hr.attendance.view"
PERM_ATTENDANCE_MANAGE = "hr.attendance.manage"
PERM_LEAVE = "hr.leave.manage"
PERM_REQUESTS_VIEW = "hr.requests.view"
PERM_REQUESTS_APPROVE = "hr.requests.approve"
PERM_CONTRACTS_VIEW = "hr.contracts.view"
PERM_CONTRACTS_MANAGE = "hr.contracts.manage"
PERM_SETTINGS = "admin.settings.manage"
PERM_ESS = "ess.self"

READ_METHODS = ("GET", "HEAD", "OPTIONS")


class HrSuiteViewSetBase(BaseTenantViewSet):
    """كل ViewSet في الوحدة يرث هذا — الترخيص ثم الصلاحية ثم عزل الشركة.

    الوارث يعلن `perm_read` و`perm_write` (أو `action_perms` لتفصيلٍ أدق)،
    ويجد الشركة جاهزةً في `self.tenant` بعد `initial`.
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, LegalAccountantRoutePermission]

    #: صلاحية القراءة (GET/HEAD/OPTIONS) — يعلنها الوارث.
    perm_read: str = PERM_ATTENDANCE_VIEW
    #: صلاحية الكتابة — يعلنها الوارث.
    perm_write: str = PERM_ORG
    #: تفصيل اختياري لكل action باسمه، يتقدّم على الثنائي أعلاه.
    action_perms: dict = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # الترخيص أولاً: شركة غير مرخّصة لا تصل إلى فحص الصلاحية أصلاً.
        self.tenant = require_module(request, MODULE_KEY)
        require_perm(request, self.required_perm(request), tenant=self.tenant)

    def required_perm(self, request) -> str:
        explicit = self.action_perms.get(getattr(self, "action", None))
        if explicit:
            return explicit
        return self.perm_read if request.method in READ_METHODS else self.perm_write

    def _tenant(self):
        """الشركة النشطة — محلولةٌ سلفاً في `initial` عبر بوابة الترخيص."""
        tenant = getattr(self, "tenant", None)
        if tenant is None:
            raise ValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        return tenant
