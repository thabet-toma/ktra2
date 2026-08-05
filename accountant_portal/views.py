import csv
import io
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, Exists, OuterRef, Q, When
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_202_ACCEPTED,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_501_NOT_IMPLEMENTED,
)
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accountant_portal.identity import (
    EmailTokenError,
    email_verification_required,
    read_email_verification_token,
    send_existing_account_email,
    send_invitation_email,
    send_verification_email,
)
from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    ReviewQuery,
    TaxPeriodReview,
)
from accountant_portal.services import (
    GRANT_PROFILE_EXTRAS,
    REVIEW_PACKAGE_COLUMNS,
    EngagementConflict,
    accept_company_invitation,
    answer_review_query,
    approve_accountant_request,
    approve_tax_period,
    build_review_package,
    client_expense_rows,
    client_financial_summary,
    client_invoice_rows,
    client_monthly_trend,
    client_statements,
    close_review_query,
    create_company_invitation,
    default_engagement_scope,
    create_review_query,
    decline_engagement,
    get_portal_settings,
    period_readiness,
    portal_settings_payload,
    practice_overview,
    prepare_tax_period,
    record_package_export,
    reopen_tax_period,
    request_company_engagement,
    require_reauth,
    resume_engagement,
    revoke_engagement,
    set_engagement_scope,
    submit_tax_period,
    suspend_engagement,
    update_portal_settings,
)
from core.access import permission_catalog, require_perm, user_has_perm, user_tenant_role
from core.modules import guard_module_surface, module_enabled, require_module
from core.models import ActivityLog, TenantModule
from core.tenant_utils import get_tenant
from tenants.models import Tenant


logger = logging.getLogger(__name__)
User = get_user_model()
PROFILE_EDITABLE_FIELDS = {
    "professional_type",
    "license_number",
    "license_authority",
    "tax_registration_number",
    "business_address",
    "phone",
}


class PortalAPIView(APIView):
    """أساس كل مسارات الوحدة — الشركة غير المرخّصة لا ترى المسار أصلاً (404)."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        guard_module_surface(request, "accountant_portal")


class SuccessOnlyScopedThrottle(ScopedRateThrottle):
    """حصة تُحسب على العمليات **الناجحة** وحدها.

    الحدّ هنا يحمي الشركات من إغراقها بطلبات ارتباط. أما المحاولة المرفوضة (عضوية
    داخلية في الشركة نفسها، أو شركة غير مرخَّصة، أو طلب مكرر) فلا تُنشئ شيئاً —
    وعدّها كان يقفل المحاسب ساعةً كاملة بسبب رسالة رفضٍ صحيحة قرأها للتو.
    التسجيل مؤجَّل إلى `commit()` يناديها المسار بعد نجاح الإنشاء.
    """

    def throttle_success(self):
        return True

    def commit(self):
        if getattr(self, "history", None) is None:
            return  # لا نطاق لهذا المسار ⇒ لا حصة أصلاً
        super().throttle_success()


def _error(code, detail, status_code):
    return Response({"code": code, "detail": detail}, status=status_code)


def _conflict_response(exc):
    return _error(exc.code, exc.detail, exc.status_code)


def _profile_data(profile):
    return {
        "id": profile.pk,
        "user_id": profile.user_id,
        "full_name": profile.user.get_full_name(),
        "email": profile.user.email,
        "account_type": profile.account_type,
        "professional_type": profile.professional_type,
        "license_number": profile.license_number,
        "license_authority": profile.license_authority,
        "tax_registration_number": profile.tax_registration_number,
        "business_address": profile.business_address,
        "phone": profile.phone,
        "email_verified": profile.email_verified_at is not None,
        "verification_status": profile.verification_status,
        "rejection_reason": profile.rejection_reason,
        "barred_until": profile.barred_until,
    }


def _engagement_data(engagement):
    return {
        "id": engagement.pk,
        "accountant_id": engagement.accountant_id,
        "accountant_name": engagement.accountant.get_full_name() or engagement.accountant.username,
        "accountant_email": engagement.accountant.email,
        "tenant_id": engagement.tenant_id,
        "company_name": engagement.tenant.CompanyName,
        "status": engagement.status,
        "initiated_by": engagement.initiated_by,
        "scope": engagement.approved_scope_snapshot,
        "note": engagement.engagement_note,
        "invitation_expires_at": engagement.invitation_expires_at,
        "created_at": engagement.created_at,
        "updated_at": engagement.updated_at,
    }


class AccountantSignupView(PortalAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "accountant_signup"

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        full_name = str(data.get("fullName") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        password = data.get("password")
        professional_type = str(data.get("professional_type") or "").strip()
        tax_number = str(data.get("tax_registration_number") or "").strip()
        business_address = str(data.get("business_address") or "").strip()

        required = (
            (full_name, "missing_full_name", "الاسم الكامل مطلوب."),
            (email, "invalid_email", "البريد الإلكتروني مطلوب."),
            (professional_type, "missing_professional_type", "الصفة المهنية مطلوبة."),
            (tax_number, "missing_tax_registration", "رقم التسجيل الضريبي مطلوب."),
            (business_address, "missing_business_address", "عنوان العمل الدائم مطلوب."),
        )
        for value, code, detail in required:
            if not value:
                return _error(code, detail, HTTP_400_BAD_REQUEST)
        try:
            validate_email(email)
        except DjangoValidationError:
            return _error("invalid_email", "أدخل بريداً إلكترونياً صالحاً.", HTTP_400_BAD_REQUEST)
        if professional_type not in dict(AccountantProfile.PROFESSIONAL_TYPES):
            return _error("invalid_professional_type", "الصفة المهنية غير صالحة.", HTTP_400_BAD_REQUEST)
        if not isinstance(password, str) or len(password) < 10:
            return _error("weak_password", "يجب أن تتكون كلمة المرور من 10 محارف على الأقل.", HTTP_400_BAD_REQUEST)
        try:
            CommonPasswordValidator().validate(password)
        except DjangoValidationError:
            return _error("weak_password", "كلمة المرور شائعة جداً.", HTTP_400_BAD_REQUEST)

        requires_verification = email_verification_required()
        existing = User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).first()
        if existing is not None:
            send_existing_account_email(email)
            return Response(
                {"accepted": True, "email_verification_required": requires_verification},
                status=HTTP_201_CREATED,
            )

        parts = full_name.split(maxsplit=1)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=parts[0][:150],
                    last_name=(parts[1] if len(parts) > 1 else "")[:150],
                    is_active=True,
                )
                AccountantProfile.objects.create(
                    user=user,
                    professional_type=professional_type,
                    tax_registration_number=tax_number,
                    business_address=business_address,
                    license_number=str(data.get("license_number") or "").strip(),
                    license_authority=str(data.get("license_authority") or "").strip(),
                    phone=str(data.get("phone") or "").strip(),
                    email_verified_at=None if requires_verification else timezone.now(),
                )
        except IntegrityError:
            if User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).exists():
                send_existing_account_email(email)
                return Response(
                    {"accepted": True, "email_verification_required": requires_verification},
                    status=HTTP_201_CREATED,
                )
            return _error("duplicate_tax_registration", "رقم التسجيل الضريبي مستخدم.", HTTP_400_BAD_REQUEST)
        if requires_verification:
            send_verification_email(user)
        return Response(
            {"accepted": True, "email_verification_required": requires_verification},
            status=HTTP_201_CREATED,
        )


class VerifyEmailView(PortalAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "accountant_verify"

    def post(self, request):
        token = request.data.get("token") if isinstance(request.data, dict) else None
        if not token:
            return _error("token_invalid", "رمز التحقق غير صالح.", HTTP_400_BAD_REQUEST)
        try:
            user = read_email_verification_token(str(token))
        except EmailTokenError as exc:
            return _error(exc.code, "رمز التحقق غير صالح أو منتهي.", HTTP_400_BAD_REQUEST)
        profile = user.accountant_profile
        if profile.email_verified_at is not None:
            return _error("token_used", "استُعمل رمز التحقق سابقاً.", HTTP_400_BAD_REQUEST)
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["email_verified_at", "updated_at"])
        return Response({"verified": True}, status=HTTP_200_OK)


class ResendVerificationView(PortalAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "accountant_verify"

    def post(self, request):
        email = str(request.data.get("email") or "").strip().lower()
        profile = AccountantProfile.objects.select_related("user").filter(user__email__iexact=email).first()
        if profile is not None and profile.email_verified_at is None:
            send_verification_email(profile.user)
        return Response({"accepted": True}, status=HTTP_202_ACCEPTED)


class AccountantMeView(PortalAPIView):
    permission_classes = [IsAuthenticated]

    def _profile(self, request):
        try:
            profile = request.user.accountant_profile
        except AccountantProfile.DoesNotExist:
            return None, _error("accountant_profile_required", "لا يوجد ملف محاسب.", HTTP_404_NOT_FOUND)
        if email_verification_required() and profile.email_verified_at is None:
            return None, _error("email_unverified", "يجب التحقق من البريد الإلكتروني أولاً.", HTTP_403_FORBIDDEN)
        return profile, None

    def get(self, request):
        profile, error = self._profile(request)
        return error or Response({"profile": _profile_data(profile)})

    def patch(self, request):
        profile, error = self._profile(request)
        if error:
            return error
        for field in PROFILE_EDITABLE_FIELDS:
            if field in request.data:
                setattr(profile, field, str(request.data[field] or "").strip())
        try:
            profile.full_clean(exclude=["user"])
            profile.save()
        except DjangoValidationError as exc:
            return _error("invalid_profile", exc.message_dict, HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return _error("duplicate_tax_registration", "رقم التسجيل الضريبي مستخدم.", HTTP_400_BAD_REQUEST)
        return Response({"profile": _profile_data(profile)})


class SubmitProfileVerificationView(PortalAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            profile = request.user.accountant_profile
        except AccountantProfile.DoesNotExist:
            return _error("incomplete_profile", "الملف المهني غير مكتمل.", HTTP_400_BAD_REQUEST)
        if email_verification_required() and profile.email_verified_at is None:
            return _error("email_unverified", "يجب التحقق من البريد الإلكتروني أولاً.", HTTP_403_FORBIDDEN)
        if profile.verification_status == "pending_review":
            return _error("already_pending", "الملف بانتظار المراجعة بالفعل.", HTTP_409_CONFLICT)
        if not all((profile.professional_type, profile.tax_registration_number, profile.business_address)):
            return _error("incomplete_profile", "الملف المهني غير مكتمل.", HTTP_400_BAD_REQUEST)
        profile.verification_status = "pending_review"
        profile.rejection_reason = ""
        profile.save(update_fields=["verification_status", "rejection_reason", "updated_at"])
        return Response({"status": "pending_review"}, status=HTTP_202_ACCEPTED)


class PortalStatusView(PortalAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        require_module(request, "accountant_portal")
        return Response({"module": "accountant_portal", "enabled": True})


class AccountantEngagementListView(PortalAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = AccountantEngagement.objects.filter(accountant=request.user).select_related("tenant", "accountant")
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if search:
            queryset = queryset.filter(tenant__CompanyName__icontains=search)
        results = [_engagement_data(item) for item in queryset.order_by("-updated_at")]
        return Response({"results": results, "count": len(results)})


class WorkspaceCompaniesView(PortalAPIView):
    """لوحة شركات المحاسب — تجميع خادمي كامل بأربعة استعلامات مهما كثرت الشركات."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get("page") or 1))
            page_size = min(200, max(1, int(request.query_params.get("page_size") or 25)))
        except (TypeError, ValueError):
            return _error("invalid_pagination", "قيم الترقيم غير صالحة.", HTTP_400_BAD_REQUEST)

        queryset = (
            AccountantEngagement.objects.filter(accountant=request.user)
            .select_related("tenant")
            .annotate(
                licensed=Exists(
                    TenantModule.objects.filter(
                        tenant_id=OuterRef("tenant_id"),
                        module_key="accountant_portal",
                        enabled=True,
                    )
                )
            )
        )
        status_filter = request.query_params.get("status")
        search = request.query_params.get("search")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if search:
            queryset = queryset.filter(tenant__CompanyName__icontains=search)

        count = queryset.count()
        offset = (page - 1) * page_size
        engagements = list(queryset.order_by("tenant__CompanyName")[offset:offset + page_size])
        tenant_ids = [item.tenant_id for item in engagements]

        latest_period = {}
        for review in (
            TaxPeriodReview.objects.filter(tenant_id__in=tenant_ids)
            .order_by("tenant_id", "-period_to", "-id")
            .values("id", "tenant_id", "period_from", "period_to", "status")
        ):
            latest_period.setdefault(review["tenant_id"], review)

        query_stats = {
            row["tenant_id"]: row
            for row in ReviewQuery.objects.filter(
                tenant_id__in=tenant_ids,
                status__in=("open", "answered"),
            )
            .values("tenant_id")
            .annotate(
                open_count=Count("id"),
                blockers=Count(Case(When(severity="blocker", then=1))),
            )
        }

        results = []
        for item in engagements:
            stats = query_stats.get(item.tenant_id, {})
            period = latest_period.get(item.tenant_id)
            results.append({
                "engagement_id": item.pk,
                "tenant_id": item.tenant_id,
                "company_name": item.tenant.CompanyName,
                "status": item.status,
                "accessible": item.status == "active" and bool(item.licensed),
                "open_queries": stats.get("open_count", 0),
                "blockers": stats.get("blockers", 0),
                "last_period": {
                    "id": period["id"],
                    "period_from": period["period_from"],
                    "period_to": period["period_to"],
                    "status": period["status"],
                } if period else None,
            })
        return Response({
            "results": results,
            "count": count,
            "page": page,
            "page_size": page_size,
        })


class CompanyLookupView(PortalAPIView):
    """بحث المحاسب عن شركة ليطلب الارتباط بها.

    **مطابقة تامة فقط** (الاسم كما هو مسجَّل أو معرّف الشركة) ولا تُعاد قائمة —
    فالبحث الجزئي يفتح باب تعداد شركات المنصة (T8). وغير الموجودة وغير المرخَّصة
    ترجعان الرسالة نفسها.
    """

    permission_classes = [IsAuthenticated]
    # حصة مستقلة عن حصة الطلب: البحث خطوةٌ سابقة للطلب، وجعلُهما حصةً واحدة كان
    # يستهلك رصيد الطلبات بالبحث وحده فيُقفل المسار قبل أن يصل المحاسب إليه.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "accountant_company_lookup"

    def get(self, request):
        query = str(request.query_params.get("q") or "").strip()
        if len(query) < 3:
            return _error("query_too_short", "اكتب اسم الشركة كما هو مسجَّل.", HTTP_400_BAD_REQUEST)
        try:
            request.user.accountant_profile
        except AccountantProfile.DoesNotExist:
            return _error("accountant_profile_required", "لا يوجد ملف محاسب.", HTTP_404_NOT_FOUND)

        # بالاسم التام وحده: البحث بالمعرّف يسمح بالمرور على 1..N فيكشف أسماء
        # شركات المنصة — وهو التعداد الذي يمنعه T8.
        tenant = Tenant.objects.filter(CompanyName__iexact=query).first()
        if tenant is None or not module_enabled(tenant, "accountant_portal"):
            return _error("company_not_found", "الشركة غير موجودة أو غير مرخصة للبوابة.", HTTP_404_NOT_FOUND)

        existing = AccountantEngagement.objects.filter(
            accountant=request.user, tenant=tenant,
        ).values_list("status", flat=True).first()
        return Response({
            "company": {
                "tenant_id": tenant.pk,
                "company_name": tenant.CompanyName,
                "engagement_status": existing or "",
            }
        })


class RequestEngagementView(PortalAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SuccessOnlyScopedThrottle]
    throttle_scope = "accountant_engagement_request"

    def get_throttles(self):
        # نمسك النسخ نفسها التي فحصت الحصة كي نُثبّتها بعد نجاح الإنشاء وحده.
        self.checked_throttles = super().get_throttles()
        return self.checked_throttles

    def post(self, request):
        tenant_id = request.data.get("tenant_id")
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None or not module_enabled(tenant, "accountant_portal"):
            return _error("company_not_found", "الشركة غير موجودة أو غير مرخصة.", HTTP_404_NOT_FOUND)
        try:
            engagement = request_company_engagement(
                accountant=request.user,
                tenant=tenant,
                note=request.data.get("note", ""),
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        for throttle in getattr(self, "checked_throttles", ()):
            commit = getattr(throttle, "commit", None)
            if commit is not None:
                commit()
        return Response({"engagement": _engagement_data(engagement)}, status=HTTP_201_CREATED)


class AcceptInvitationView(PortalAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            engagement = accept_company_invitation(
                accountant=request.user,
                token=request.data.get("token", ""),
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"engagement": _engagement_data(engagement)})


class AccountantEngagementActionView(PortalAPIView):
    permission_classes = [IsAuthenticated]
    action = None

    def post(self, request, engagement_id):
        engagement = AccountantEngagement.objects.filter(pk=engagement_id, accountant=request.user).first()
        if engagement is None:
            return _error("engagement_not_found", "الارتباط غير موجود.", HTTP_404_NOT_FOUND)
        try:
            if self.action == "withdraw" and engagement.status != "pending":
                raise EngagementConflict("not_pending", "الارتباط ليس قيد الانتظار.")
            if self.action == "resign" and engagement.status != "active":
                raise EngagementConflict("not_active", "الارتباط غير نشط.")
            result = revoke_engagement(
                engagement=engagement,
                actor=request.user,
                reason=request.data.get("reason", "انسحاب المحاسب"),
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"engagement": _engagement_data(result)})


class WithdrawEngagementView(AccountantEngagementActionView):
    action = "withdraw"


class ResignEngagementView(AccountantEngagementActionView):
    action = "resign"


class CompanyContextView(PortalAPIView):
    permission_classes = [IsAuthenticated]

    def company(self, request):
        tenant = get_tenant(request)
        require_module(request, "accountant_portal")
        require_perm(request, "admin.members.manage", tenant=tenant)
        return tenant

    def engagement(self, request, engagement_id):
        tenant = self.company(request)
        item = AccountantEngagement.objects.filter(pk=engagement_id, tenant=tenant).select_related("tenant", "accountant").first()
        if item is None:
            raise EngagementConflict("engagement_not_found", "الارتباط غير موجود.", 404)
        return item


class CompanyEngagementListView(CompanyContextView):
    def get(self, request):
        tenant = self.company(request)
        queryset = AccountantEngagement.objects.filter(tenant=tenant).select_related("tenant", "accountant")
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        results = [_engagement_data(item) for item in queryset.order_by("-updated_at")]
        return Response({"results": results, "count": len(results)})


class CompanyInviteView(CompanyContextView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "accountant_invite"

    def post(self, request):
        tenant = self.company(request)
        profile = AccountantProfile.objects.select_related("user").filter(user__email__iexact=request.data.get("email", "")).first()
        if profile is None:
            return _error("accountant_not_found", "المحاسب غير موجود.", HTTP_404_NOT_FOUND)
        try:
            engagement, token = create_company_invitation(
                tenant=tenant,
                manager=request.user,
                accountant=profile.user,
                scope=request.data.get("scope", []),
                note=request.data.get("note", ""),
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        send_invitation_email(profile.user, token, tenant)
        return Response({"engagement": _engagement_data(engagement)}, status=HTTP_201_CREATED)


class CompanyEngagementActionView(CompanyContextView):
    action = None

    def post(self, request, engagement_id):
        try:
            engagement = self.engagement(request, engagement_id)
            if self.action == "approve":
                result = approve_accountant_request(
                    engagement=engagement,
                    manager=request.user,
                    # غياب المفتاح = «امنحه الافتراضي المهني»؛ القائمة الفارغة قرارٌ صريح.
                    scope=request.data.get("scope") if isinstance(request.data, dict) and "scope" in request.data else None,
                )
            elif self.action == "decline":
                result = decline_engagement(
                    engagement=engagement,
                    actor=request.user,
                    reason=request.data.get("reason", ""),
                )
            elif self.action == "suspend":
                result = suspend_engagement(
                    engagement=engagement,
                    actor=request.user,
                    reason=request.data.get("reason", ""),
                )
            elif self.action == "resume":
                result = resume_engagement(engagement=engagement, actor=request.user)
            else:
                result = revoke_engagement(
                    engagement=engagement,
                    actor=request.user,
                    reason=request.data.get("reason", ""),
                )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"engagement": _engagement_data(result)})


class CompanyApproveView(CompanyEngagementActionView):
    action = "approve"


class CompanyDeclineView(CompanyEngagementActionView):
    action = "decline"


class CompanySuspendView(CompanyEngagementActionView):
    action = "suspend"


class CompanyResumeView(CompanyEngagementActionView):
    action = "resume"


class CompanyRevokeView(CompanyEngagementActionView):
    action = "revoke"


class CompanyScopeView(CompanyContextView):
    def patch(self, request, engagement_id):
        try:
            engagement = self.engagement(request, engagement_id)
            require_reauth(request=request, tenant=engagement.tenant, user=request.user)
            result = set_engagement_scope(
                engagement=engagement,
                actor=request.user,
                scope=request.data.get("scope", []),
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"engagement": _engagement_data(result)})


class CompanyScopeCatalogView(CompanyContextView):
    def get(self, request):
        tenant = self.company(request)
        return Response({
            "permissions": list(permission_catalog(tenant)),
            # الشاشة تؤشّر الافتراضي مسبقاً، وتعرض الحزم الثلاث كأزرار جاهزة.
            "defaults": default_engagement_scope(tenant),
            "profiles": {
                profile: default_engagement_scope(tenant, profile)
                for profile in GRANT_PROFILE_EXTRAS
            },
            "active_profile": get_portal_settings(tenant).default_grant_profile,
        })


class TenantScopedView(PortalAPIView):
    """مسار داخل شركة: الوحدة مرخّصة + العضوية سارية (الارتباط النشط يُفحص في L2)."""

    permission_classes = [IsAuthenticated]

    def tenant_for(self, request, permission=None):
        tenant = get_tenant(request)
        require_module(request, "accountant_portal")
        if permission:
            require_perm(request, permission, tenant=tenant)
        return tenant


def _query_data(query):
    return {
        "id": query.pk,
        "tenant_id": query.tenant_id,
        "entity_type": query.entity_type,
        "entity_id": query.entity_id,
        "entity_label": query.entity_label,
        "title": query.title,
        "body": query.body,
        "severity": query.severity,
        "status": query.status,
        "raised_by": query.raised_by_id,
        "raised_by_name": query.raised_by.get_full_name() or query.raised_by.username if query.raised_by else "",
        "raised_at": query.raised_at,
        "answered_at": query.answered_at,
        "answer_body": query.answer_body,
        "attachment_url": query.attachment_url,
        "period_review_id": query.period_review_id,
    }


class ReviewQueryListCreateView(TenantScopedView):
    def get(self, request):
        tenant = self.tenant_for(request)
        if not (
            user_has_perm(request.user, tenant, "review.query.create")
            or user_has_perm(request.user, tenant, "review.query.respond")
        ):
            return _error("forbidden", "لا تملك صلاحية طلبات التوضيح.", HTTP_403_FORBIDDEN)
        queryset = ReviewQuery.objects.filter(tenant=tenant).select_related("raised_by")
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("severity"):
            queryset = queryset.filter(severity=request.query_params["severity"])
        if request.query_params.get("period_review_id"):
            queryset = queryset.filter(period_review_id=request.query_params["period_review_id"])
        results = [_query_data(item) for item in queryset.order_by("-raised_at")[:500]]
        return Response({"results": results, "count": len(results)})

    def post(self, request):
        tenant = self.tenant_for(request, "review.query.create")
        try:
            query = create_review_query(
                tenant=tenant,
                user=request.user,
                data=request.data if isinstance(request.data, dict) else {},
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"query": _query_data(query)}, status=HTTP_201_CREATED)


class ReviewQueryActionView(TenantScopedView):
    action = None

    def post(self, request, query_id):
        permission = "review.query.respond" if self.action == "answer" else "review.query.create"
        tenant = self.tenant_for(request, permission)
        query = ReviewQuery.objects.filter(pk=query_id, tenant=tenant).select_related("raised_by", "period_review").first()
        if query is None:
            return _error("query_not_found", "طلب التوضيح غير موجود.", HTTP_404_NOT_FOUND)
        try:
            if self.action == "answer":
                result = answer_review_query(
                    query=query,
                    user=request.user,
                    body=request.data.get("answer_body"),
                )
            else:
                result = close_review_query(query=query, user=request.user, outcome=self.action)
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"query": _query_data(result)})


class ReviewQueryAnswerView(ReviewQueryActionView):
    action = "answer"


class ReviewQueryResolveView(ReviewQueryActionView):
    action = "resolved"


class ReviewQueryWithdrawView(ReviewQueryActionView):
    action = "withdrawn"


class ClientDocumentsView(TenantScopedView):
    """سحب مستندات الزبون — بيع/شراء/مصاريف. قراءة محضة بلا أي مسار كتابة."""

    PERMISSION_BY_KIND = {
        "sales": "sales.invoice.view",
        "purchases": "purchase.invoice.view",
        "expenses": "accounting.journal.view",
    }

    def get(self, request):
        kind = str(request.query_params.get("kind") or "sales").lower()
        permission = self.PERMISSION_BY_KIND.get(kind)
        if permission is None:
            return _error("invalid_kind", "نوع المستندات غير مدعوم.", HTTP_400_BAD_REQUEST)
        tenant = self.tenant_for(request, permission)
        date_from = parse_date(str(request.query_params.get("from") or ""))
        date_to = parse_date(str(request.query_params.get("to") or ""))
        if date_from is None or date_to is None or date_from > date_to:
            return _error("invalid_period", "حدود الفترة غير صالحة.", HTTP_400_BAD_REQUEST)

        if kind == "expenses":
            rows, totals = client_expense_rows(
                tenant=tenant, date_from=date_from, date_to=date_to,
            )
        else:
            rows, totals = client_invoice_rows(
                tenant=tenant, kind=kind, date_from=date_from, date_to=date_to,
            )
        logger.info(
            "accountant_office documents user=%s tenant=%s kind=%s rows=%s",
            request.user.pk, tenant.pk, kind, len(rows),
        )
        return Response({
            "kind": kind,
            "results": rows,
            "totals": totals,
            "count": len(rows),
        })


class ClientStatementsView(TenantScopedView):
    """قائمة الدخل والميزانية العمومية بالحسابات — البيانان اللذان يطلبهما كل مكتب."""

    def get(self, request):
        tenant = self.tenant_for(request, "accounting.report.view")
        date_from = parse_date(str(request.query_params.get("from") or ""))
        date_to = parse_date(str(request.query_params.get("to") or ""))
        if date_from is None or date_to is None or date_from > date_to:
            return _error("invalid_period", "حدود الفترة غير صالحة.", HTTP_400_BAD_REQUEST)
        return Response({
            "company_name": tenant.CompanyName,
            "period_from": date_from,
            "period_to": date_to,
            **client_statements(tenant=tenant, date_from=date_from, date_to=date_to),
        })


class ClientTrendView(TenantScopedView):
    """منحنى الأشهر الأخيرة — يعطي المحاسب اتجاه الزبون بنظرة واحدة."""

    def get(self, request):
        tenant = self.tenant_for(request, "accounting.report.view")
        try:
            months = min(24, max(3, int(request.query_params.get("months") or 6)))
        except (TypeError, ValueError):
            months = 6
        return Response({"months": months, "series": client_monthly_trend(tenant=tenant, months=months)})


class PracticeOverviewView(PortalAPIView):
    """لوحة المكتب: كل الزبائن وأرقام الشهر ومواعيد التقديم في نداء واحد."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            request.user.accountant_profile
        except AccountantProfile.DoesNotExist:
            return _error("accountant_profile_required", "لا يوجد ملف محاسب.", HTTP_404_NOT_FOUND)
        return Response(practice_overview(accountant=request.user))


class ClientSummaryView(TenantScopedView):
    """ملخص الزبون: إيرادات − مصروفات = الربح، ومخرجات − مدخلات = ضريبة مستحقة."""

    def get(self, request):
        tenant = self.tenant_for(request, "accounting.report.view")
        date_from = parse_date(str(request.query_params.get("from") or ""))
        date_to = parse_date(str(request.query_params.get("to") or ""))
        if date_from is None or date_to is None or date_from > date_to:
            return _error("invalid_period", "حدود الفترة غير صالحة.", HTTP_400_BAD_REQUEST)
        summary = client_financial_summary(
            tenant=tenant, date_from=date_from, date_to=date_to,
        )
        logger.info(
            "accountant_office summary user=%s tenant=%s window=%s..%s",
            request.user.pk, tenant.pk, date_from, date_to,
        )
        return Response({"company_name": tenant.CompanyName, "summary": summary})


def _period_data(period):
    statement = period.vat_statement
    return {
        "id": period.pk,
        "tenant_id": period.tenant_id,
        "period_from": period.period_from,
        "period_to": period.period_to,
        "status": period.status,
        "prepared_at": period.prepared_at,
        "approved_at": period.approved_at,
        "submitted_at": period.submitted_at,
        "submission_reference": period.submission_reference,
        "locked_at": period.locked_at,
        "reopen_count": period.reopen_count,
        "last_reopen_reason": period.last_reopen_reason,
        "vat": {
            "statement_number": statement.statement_number,
            "total_sales_vat": str(statement.total_sales_vat),
            "total_purchase_vat": str(statement.total_purchase_vat),
            "net_vat": str(statement.net_vat),
        } if statement else None,
    }


class TaxPeriodListView(TenantScopedView):
    def get(self, request):
        tenant = self.tenant_for(request, "tax.period.view")
        queryset = TaxPeriodReview.objects.filter(tenant=tenant).select_related("vat_statement")
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("from"):
            queryset = queryset.filter(period_to__gte=request.query_params["from"])
        if request.query_params.get("to"):
            queryset = queryset.filter(period_from__lte=request.query_params["to"])
        results = [_period_data(item) for item in queryset.order_by("-period_to")[:200]]
        return Response({"results": results, "count": len(results)})


class TaxPeriodDetailView(TenantScopedView):
    def get(self, request, period_id):
        tenant = self.tenant_for(request, "tax.period.view")
        period = TaxPeriodReview.objects.filter(pk=period_id, tenant=tenant).select_related("vat_statement").first()
        if period is None:
            return _error("period_not_found", "الفترة غير موجودة.", HTTP_404_NOT_FOUND)
        return Response({"period": _period_data(period)})


class TaxPeriodPrepareView(TenantScopedView):
    def post(self, request):
        tenant = self.tenant_for(request, "tax.period.prepare")
        data = request.data if isinstance(request.data, dict) else {}
        try:
            period = prepare_tax_period(
                tenant=tenant,
                user=request.user,
                period_from=parse_date(str(data.get("period_from") or "")),
                period_to=parse_date(str(data.get("period_to") or "")),
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"period": _period_data(period)}, status=HTTP_201_CREATED)


class TaxPeriodReadinessView(TenantScopedView):
    def get(self, request, period_id):
        tenant = self.tenant_for(request, "tax.period.view")
        period = TaxPeriodReview.objects.filter(pk=period_id, tenant=tenant).select_related("tenant").first()
        if period is None:
            return _error("period_not_found", "الفترة غير موجودة.", HTTP_404_NOT_FOUND)
        findings = period_readiness(period)
        return Response({
            "findings": [item.as_dict() for item in findings],
            "blockers": sum(1 for item in findings if item.severity == "blocker"),
            "warnings": sum(1 for item in findings if item.severity == "warning"),
        })


class TaxPeriodActionView(TenantScopedView):
    action = None
    permission_key = None

    def post(self, request, period_id):
        tenant = self.tenant_for(request, self.permission_key)
        period = TaxPeriodReview.objects.filter(pk=period_id, tenant=tenant).select_related("tenant").first()
        if period is None:
            return _error("period_not_found", "الفترة غير موجودة.", HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}
        try:
            if self.action == "approve":
                result = approve_tax_period(period=period, user=request.user, request=request)
            elif self.action == "reopen":
                if not get_portal_settings(tenant).allow_accountant_reopen:
                    require_perm(request, "admin.members.manage", tenant=tenant)
                result = reopen_tax_period(period=period, user=request.user, reason=data.get("reason"))
            else:
                result = submit_tax_period(
                    period=period,
                    user=request.user,
                    request=request,
                    reference=data.get("submission_reference"),
                    submitted_on=parse_date(str(data.get("submitted_on") or "")) or None,
                )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"period": _period_data(result)})


class TaxPeriodApproveView(TaxPeriodActionView):
    action = "approve"
    permission_key = "tax.period.approve"


class TaxPeriodReopenView(TaxPeriodActionView):
    action = "reopen"
    permission_key = "tax.period.reopen"


class TaxPeriodSubmitView(TaxPeriodActionView):
    action = "submit"
    permission_key = "tax.filing.submit"


class TaxClearanceView(TenantScopedView):
    """ق3 — المقاصة يدوية بالكامل؛ المسار محجوز ويعيد 501 دائماً."""

    def post(self, request):
        self.tenant_for(request, "tax.clearance.issue")
        return _error(
            "not_implemented",
            "إصدار فاتورة المقاصة يدوي في هذا الإصدار — لا ربط حكومي.",
            HTTP_501_NOT_IMPLEMENTED,
        )


class ReviewPackageExportView(TenantScopedView):
    """حزمة المراجعة: CSV ملفّاً، وpdf صفوفاً تطبعها الواجهة بنمط المستودع القائم."""

    def post(self, request):
        tenant = self.tenant_for(request, "finance.export.package")
        data = request.data if isinstance(request.data, dict) else {}
        period_from = parse_date(str(data.get("period_from") or ""))
        period_to = parse_date(str(data.get("period_to") or ""))
        if period_from is None or period_to is None or period_from > period_to:
            return _error("invalid_period", "حدود الفترة غير صالحة.", HTTP_400_BAD_REQUEST)
        export_format = str(data.get("format") or "csv").lower()
        allowed = get_portal_settings(tenant).export_formats or ["csv"]
        if export_format not in allowed:
            return _error("format_not_allowed", "صيغة التصدير غير مسموحة لهذه الشركة.", HTTP_400_BAD_REQUEST)

        rows = build_review_package(tenant=tenant, period_from=period_from, period_to=period_to)
        record_package_export(
            tenant=tenant,
            user=request.user,
            period_from=period_from,
            period_to=period_to,
            export_format=export_format,
            row_count=len(rows),
        )
        if export_format != "csv":
            return Response({
                "columns": [{"key": key, "header": header} for key, header in REVIEW_PACKAGE_COLUMNS],
                "rows": rows,
                "period_from": period_from,
                "period_to": period_to,
            })

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([header for _, header in REVIEW_PACKAGE_COLUMNS])
        for row in rows:
            writer.writerow([row[key] for key, _ in REVIEW_PACKAGE_COLUMNS])
        response = HttpResponse(
            buffer.getvalue().encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="review-package-{period_from}-{period_to}.csv"'
        )
        return response


class AccountantActivityView(TenantScopedView):
    """سجل عمليات المحاسب داخل الشركة — المحاسب يرى عملياته، والمدير يرى الجميع."""

    def get(self, request):
        tenant = self.tenant_for(request)
        role = user_tenant_role(request.user, tenant)
        queryset = ActivityLog.objects.filter(tenant=tenant)
        if role == "legal_accountant":
            queryset = queryset.filter(user=request.user)
        else:
            require_perm(request, "admin.activity.view", tenant=tenant)
            accountant_ids = AccountantEngagement.objects.filter(tenant=tenant).values_list(
                "accountant_id", flat=True,
            )
            queryset = queryset.filter(user_id__in=list(accountant_ids))
        try:
            limit = min(200, max(1, int(request.query_params.get("page_size") or 50)))
        except (TypeError, ValueError):
            limit = 50
        results = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "entity_label": row.entity_label,
                "description": row.description,
                "timestamp": row.timestamp,
            }
            for row in queryset.order_by("-timestamp", "-id")[:limit]
        ]
        return Response({"results": results, "count": len(results)})


class CompanyPortalSettingsView(PortalAPIView):
    """إعدادات البوابة — مدير الشركة وحده؛ المحاسب لا يملك `admin.settings.manage` أبداً."""

    permission_classes = [IsAuthenticated]

    def _tenant(self, request):
        tenant = get_tenant(request)
        require_module(request, "accountant_portal")
        require_perm(request, "admin.settings.manage", tenant=tenant)
        return tenant

    def get(self, request):
        tenant = self._tenant(request)
        return Response({"settings": portal_settings_payload(get_portal_settings(tenant))})

    def patch(self, request):
        tenant = self._tenant(request)
        try:
            config = update_portal_settings(
                tenant=tenant,
                actor=request.user,
                data=request.data if isinstance(request.data, dict) else {},
            )
        except EngagementConflict as exc:
            return _conflict_response(exc)
        return Response({"settings": portal_settings_payload(config)})


# Compatibility for the M1 route test and external imports.
portal_status = PortalStatusView.as_view()

