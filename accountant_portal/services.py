import hashlib
import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accountant_portal.audit import write_financial_audit
from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    PortalSettings,
    ReviewQuery,
    TaxPeriodReview,
)
from accountant_portal.permissions import is_legal_accountant_forbidden
from core.access import permission_keys
from core.activity import log_activity
from core.modules import module_enabled
from tenants.models import MemberPermission, UserCompanyMembership


logger = logging.getLogger(__name__)


class EngagementConflict(Exception):
    def __init__(self, code, detail, status_code=409):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def get_portal_settings(tenant):
    """إعدادات البوابة لهذه الشركة — الصفّ كسول، وغيابه يعني الافتراضات كاملةً."""
    value, _ = PortalSettings.objects.get_or_create(tenant=tenant)
    return value


_settings = get_portal_settings


def require_reauth(*, request, tenant, user):
    """ق5/T17 — الفعل الحسّاس يلزمه إعادة إدخال كلمة المرور ضمن نافذة قصيرة."""
    config = get_portal_settings(tenant)
    if not config.require_reauth_for_sensitive:
        return
    cache_key = f"acct_portal_reauth:{tenant.pk}:{user.pk}"
    if cache.get(cache_key):
        return
    data = request.data if isinstance(request.data, dict) else {}
    password = data.get("reauth_password")
    if not isinstance(password, str) or not password or not user.check_password(password):
        # لا تسجّل كلمة المرور ولا طولها — الحدث وحده يكفي للتدقيق.
        logger.info(
            "accountant_portal reauth_required user=%s tenant=%s",
            user.pk,
            tenant.pk,
        )
        raise EngagementConflict(
            "reauth_required",
            "أعد إدخال كلمة المرور لتأكيد هذا الإجراء الحسّاس.",
            403,
        )
    cache.set(cache_key, True, timeout=max(1, config.reauth_window_minutes) * 60)


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _profile_for(user):
    try:
        return user.accountant_profile
    except AccountantProfile.DoesNotExist as exc:
        raise EngagementConflict("accountant_profile_required", "يلزم ملف محاسب مهني.", 403) from exc


def _require_verified_profile(user):
    """الملف المهني شرط دائم؛ تحقق البريد شرط **اختياري** خلف عَلَم المنصة."""
    from accountant_portal.identity import email_verification_required

    profile = _profile_for(user)
    if email_verification_required() and profile.email_verified_at is None:
        raise EngagementConflict("email_unverified", "يجب التحقق من البريد الإلكتروني أولاً.", 403)
    return profile


def _check_not_barred(user):
    profile = _profile_for(user)
    if profile.verification_status == "barred" or (
        profile.barred_until is not None and profile.barred_until >= timezone.localdate()
    ):
        raise EngagementConflict("accountant_barred", "ملف المحاسب ممنوع من الارتباط.", 422)


def internal_membership(accountant, tenant):
    """عضوية المحاسب الداخلية في هذه الشركة (مدير/موظف…) أو None.

    قرار المالك (2026-08-05): **العضوية الداخلية لا تمنع الارتباط** — لصاحب الشركة
    أن يفتح ملفها في مكتبه المحاسبي. الخطر الذي كان الرفضُ يحميه واحد: العضوية صفٌّ
    واحد لكل (مستخدم، شركة)، فتفعيل الارتباط كان يستبدل دور المدير بدور
    `legal_accountant` وإلغاؤه يحذف العضوية — أي أن الشركة تفقد مديرها. الحماية
    الآن في مكانها الصحيح: **الارتباط لا يمسّ العضوية الداخلية إطلاقاً** (لا دورها
    ولا تخصيصاتها ولا وجودها)، فالوصول يبقى من الدور الداخلي كما كان.
    """
    return (
        UserCompanyMembership.objects
        .filter(user=accountant, tenant=tenant)
        .exclude(role="legal_accountant")
        .first()
    )


def _drop_engagement_membership(engagement):
    """تعليق/إلغاء الارتباط يسحب عضوية المحاسب الخارجي — ولا يمسّ عضواً داخلياً.

    عضوية العضو الداخلي ليست من صنع الارتباط، فحذفها يطرده من شركته هو.
    """
    UserCompanyMembership.objects.filter(
        user=engagement.accountant,
        tenant=engagement.tenant,
        role="legal_accountant",
    ).delete()


def _check_active_limit(accountant, tenant):
    limit = _settings(tenant).max_active_engagements
    if limit and AccountantEngagement.objects.filter(accountant=accountant, status="active").count() >= limit:
        raise EngagementConflict(
            "max_engagements_reached",
            "بلغ المحاسب الحد الأقصى للارتباطات النشطة.",
            422,
        )


# حزم المنح (ق12) — ما يفعله المحاسب القانوني عادةً بلا مفاوضة على كل مفتاح.
# «review_only» ليست فراغاً: افتراضات الدور نفسها تعطيه قراءة الفواتير والقيود
# والتقارير، فيُخرج الميزانية وورقة الضريبة من أول يوم. الحزم تضيف فوقها فقط.
GRANT_PROFILE_EXTRAS = {
    "review_only": (),
    "review_and_prepare": (
        "sales.invoice.create",
        "sales.invoice.edit",
        "purchase.invoice.create",
        "purchase.invoice.edit",
        "accounting.journal.create",
    ),
    "full_accounting": (
        "sales.invoice.create",
        "sales.invoice.edit",
        "sales.invoice.post",
        "sales.invoice.unpost",
        "purchase.invoice.create",
        "purchase.invoice.edit",
        "purchase.invoice.post",
        "purchase.invoice.unpost",
        "accounting.journal.create",
        "accounting.journal.post",
        "accounting.journal.unpost",
        "tax.period.approve",
    ),
}


def default_engagement_scope(tenant, profile=None):
    """النطاق الافتراضي عند الموافقة: عمل المحاسب الدارج جاهزاً بلا تأشير يدوي."""
    from core.access import role_default_permissions

    profile = profile or get_portal_settings(tenant).default_grant_profile
    visible = permission_keys(tenant)
    keys = set(role_default_permissions("legal_accountant", tenant))
    keys.update(
        key for key in GRANT_PROFILE_EXTRAS.get(profile, ()) if key in visible
    )
    return sorted(key for key in keys if not is_legal_accountant_forbidden(key))


def validate_scope(tenant, scope):
    if not isinstance(scope, list):
        raise EngagementConflict("invalid_scope", "يجب أن يكون النطاق قائمة صلاحيات.", 422)
    normalized = list(dict.fromkeys(str(key) for key in scope))
    visible = permission_keys(tenant)
    for key in normalized:
        if is_legal_accountant_forbidden(key):
            raise EngagementConflict(
                "forbidden_permission_key",
                "لا يمكن منح هذه الصلاحية للمحاسب القانوني الخارجي.",
                422,
            )
        if key not in visible:
            raise EngagementConflict("unknown_permission_key", "مفتاح صلاحية غير معروف.", 422)
    if "inventory.cost.view" in normalized and not _settings(tenant).allow_grant_cost_view:
        # ق8 — الشركة أقفلت منح رؤية التكاليف وهوامش الربح للمحاسب الخارجي.
        raise EngagementConflict(
            "cost_view_not_allowed",
            "منعت الشركة منح صلاحية عرض التكاليف للمحاسب القانوني الخارجي.",
            422,
        )
    return normalized


def _replace_membership_scope(engagement, scope):
    # عضو داخلي في الشركة: وصوله من دوره الداخلي لا من الارتباط، فلا نلمس دوره ولا
    # نمسح تخصيصاته — الارتباط عنده **علاقة مكتبٍ بزبون** لا منحَ صلاحيات.
    internal = internal_membership(engagement.accountant, engagement.tenant)
    if internal is not None:
        return internal
    membership, _ = UserCompanyMembership.objects.update_or_create(
        user=engagement.accountant,
        tenant=engagement.tenant,
        defaults={"role": "legal_accountant", "is_example_access": False},
    )
    membership.permission_overrides.all().delete()
    selected = set(scope)
    MemberPermission.objects.bulk_create(
        [
            MemberPermission(
                membership=membership,
                permission_key=key,
                allowed=key in selected,
            )
            for key in permission_keys(engagement.tenant)
            if not is_legal_accountant_forbidden(key)
        ]
    )
    return membership


def sanitize_log_value(value, limit=200):
    """T13 — كل قيمة من المستخدم تدخل سطر سجل تُنقّى من CR/LF قبل الكتابة."""
    return str(value or "").replace("\r", " ").replace("\n", " ")[:limit]


def _write_engagement_audit(engagement, actor, action, details=None):
    write_financial_audit(
        tenant=engagement.tenant,
        user=actor,
        action=action,
        model_name="AccountantEngagement",
        object_id=engagement.pk,
        change_details=details or {},
    )


def _log_engagement(engagement, actor, action, description):
    log_activity(
        action=action,
        entity_type="accountant_engagement",
        entity_id=engagement.pk,
        entity_label=sanitize_log_value(
            engagement.accountant.get_full_name() or engagement.accountant.username
        ),
        description=sanitize_log_value(description),
        metadata={"module": "accountant_portal"},
        tenant=engagement.tenant,
        user=actor,
    )


@transaction.atomic
def request_company_engagement(*, accountant, tenant, note=""):
    _require_verified_profile(accountant)
    _check_active_limit(accountant, tenant)
    if AccountantEngagement.objects.filter(accountant=accountant, tenant=tenant).exists():
        raise EngagementConflict("engagement_exists", "يوجد ارتباط سابق مع هذه الشركة.")
    engagement = AccountantEngagement.objects.create(
        accountant=accountant,
        tenant=tenant,
        initiated_by="accountant",
        requested_by=accountant,
        engagement_note=str(note)[:2000],
    )
    _write_engagement_audit(engagement, accountant, "ENG_REQUESTED")
    _log_engagement(engagement, accountant, "create", "طلب ارتباط محاسبي")
    return engagement


@transaction.atomic
def create_company_invitation(*, tenant, manager, accountant, scope, note=""):
    _require_verified_profile(accountant)
    _check_active_limit(accountant, tenant)
    if AccountantEngagement.objects.filter(accountant=accountant, tenant=tenant).exists():
        raise EngagementConflict("engagement_exists", "يوجد ارتباط سابق مع هذا المحاسب.")
    normalized_scope = validate_scope(tenant, scope)
    token = secrets.token_urlsafe(32)
    engagement = AccountantEngagement.objects.create(
        accountant=accountant,
        tenant=tenant,
        initiated_by="company",
        requested_by=manager,
        invitation_token_hash=_token_hash(token),
        invitation_expires_at=timezone.now() + timedelta(days=_settings(tenant).invitation_expiry_days),
        approved_scope_snapshot=normalized_scope,
        engagement_note=str(note)[:2000],
    )
    _write_engagement_audit(engagement, manager, "ENG_REQUESTED")
    _log_engagement(engagement, manager, "create", "دعوة ارتباط محاسبي")
    return engagement, token


def _activate_locked(engagement, actor, scope):
    if not module_enabled(engagement.tenant, "accountant_portal"):
        # سُحب ترخيص الوحدة بعد إنشاء الدعوة — لا تفعيل، وبرسالة لا تكشف الشركة.
        raise EngagementConflict("company_not_found", "الشركة غير موجودة أو غير مرخصة.", 404)
    if engagement.status != "pending":
        raise EngagementConflict("not_pending", "الارتباط ليس قيد الانتظار.")
    if engagement.invitation_expires_at and engagement.invitation_expires_at <= timezone.now():
        engagement.status = "expired"
        engagement.save(update_fields=["status", "updated_at"])
        raise EngagementConflict("invitation_expired", "انتهت صلاحية الدعوة.", 410)
    _check_not_barred(engagement.accountant)
    _check_active_limit(engagement.accountant, engagement.tenant)
    normalized_scope = validate_scope(engagement.tenant, scope)
    engagement.status = "active"
    engagement.approved_by = actor
    engagement.approved_at = timezone.now()
    engagement.invitation_used_at = timezone.now() if engagement.invitation_token_hash else None
    engagement.approved_scope_snapshot = normalized_scope
    engagement.save(
        update_fields=[
            "status", "approved_by", "approved_at", "invitation_used_at",
            "approved_scope_snapshot", "updated_at",
        ]
    )
    _replace_membership_scope(engagement, normalized_scope)
    _write_engagement_audit(engagement, actor, "ENG_APPROVED", {"scope": normalized_scope})
    _log_engagement(engagement, actor, "update", "تفعيل الارتباط المحاسبي")
    return engagement


@transaction.atomic
def accept_company_invitation(*, accountant, token):
    digest = _token_hash(str(token))
    try:
        engagement = AccountantEngagement.objects.select_for_update().select_related("tenant", "accountant").get(
            invitation_token_hash=digest,
        )
    except AccountantEngagement.DoesNotExist as exc:
        raise EngagementConflict("token_invalid", "رمز الدعوة غير صالح.", 400) from exc
    if engagement.accountant_id != accountant.pk:
        raise EngagementConflict("token_invalid", "رمز الدعوة غير صالح.", 400)
    if engagement.invitation_used_at is not None or engagement.status != "pending":
        raise EngagementConflict("invitation_used", "استُعملت الدعوة أو أُلغيت سابقاً.")
    return _activate_locked(engagement, engagement.requested_by, engagement.approved_scope_snapshot)


@transaction.atomic
def approve_accountant_request(*, engagement, manager, scope=None):
    """الموافقة بلا نطاق صريح تمنح الافتراضي المهني — لا فراغاً يشلّ المحاسب."""
    locked = AccountantEngagement.objects.select_for_update().select_related("tenant", "accountant").get(pk=engagement.pk)
    if scope is None:
        scope = default_engagement_scope(locked.tenant)
    return _activate_locked(locked, manager, scope)


@transaction.atomic
def suspend_engagement(*, engagement, actor, reason=""):
    locked = AccountantEngagement.objects.select_for_update().get(pk=engagement.pk)
    if locked.status != "active":
        raise EngagementConflict("not_active", "الارتباط غير نشط.")
    locked.status = "suspended"
    locked.suspended_at = timezone.now()
    locked.revocation_reason = str(reason)[:2000]
    locked.save(update_fields=["status", "suspended_at", "revocation_reason", "updated_at"])
    _drop_engagement_membership(locked)
    _write_engagement_audit(locked, actor, "ENG_SUSPENDED", {"reason": locked.revocation_reason})
    _log_engagement(locked, actor, "update", "تعليق الارتباط المحاسبي")
    return locked


@transaction.atomic
def resume_engagement(*, engagement, actor):
    locked = AccountantEngagement.objects.select_for_update().select_related("tenant", "accountant").get(pk=engagement.pk)
    if locked.status == "revoked":
        raise EngagementConflict("already_revoked", "الارتباط الملغى نهائي ولا يمكن استئنافه.")
    if locked.status != "suspended":
        raise EngagementConflict("not_suspended", "الارتباط غير معلّق.")
    _check_not_barred(locked.accountant)
    _check_active_limit(locked.accountant, locked.tenant)
    # هذه قراءة انتقال lifecycle لإعادة الحالة السابقة، وليست مصدراً لفحص أي طلب.
    _replace_membership_scope(locked, locked.approved_scope_snapshot)
    locked.status = "active"
    locked.suspended_at = None
    locked.save(update_fields=["status", "suspended_at", "updated_at"])
    _write_engagement_audit(locked, actor, "ENG_RESUMED")
    _log_engagement(locked, actor, "update", "استئناف الارتباط المحاسبي")
    return locked


@transaction.atomic
def revoke_engagement(*, engagement, actor, reason=""):
    locked = AccountantEngagement.objects.select_for_update().get(pk=engagement.pk)
    if locked.status == "revoked":
        raise EngagementConflict("already_revoked", "الارتباط ملغى سابقاً.")
    if locked.status not in {"pending", "active", "suspended"}:
        raise EngagementConflict("invalid_status", "لا يمكن إلغاء الارتباط في حالته الحالية.")
    locked.status = "revoked"
    locked.revoked_at = timezone.now()
    locked.revoked_by = actor
    locked.revocation_reason = str(reason)[:2000]
    locked.save(
        update_fields=["status", "revoked_at", "revoked_by", "revocation_reason", "updated_at"]
    )
    _drop_engagement_membership(locked)
    _write_engagement_audit(locked, actor, "ENG_REVOKED", {"reason": locked.revocation_reason})
    _log_engagement(locked, actor, "update", "إلغاء الارتباط المحاسبي")
    return locked


@transaction.atomic
def decline_engagement(*, engagement, actor, reason=""):
    locked = AccountantEngagement.objects.select_for_update().get(pk=engagement.pk)
    if locked.status != "pending":
        raise EngagementConflict("not_pending", "الارتباط ليس قيد الانتظار.")
    locked.status = "declined"
    locked.revocation_reason = str(reason)[:2000]
    locked.save(update_fields=["status", "revocation_reason", "updated_at"])
    _write_engagement_audit(locked, actor, "ENG_DECLINED", {"reason": locked.revocation_reason})
    _log_engagement(locked, actor, "update", "رفض الارتباط المحاسبي")
    return locked


# ── M4: مراجعة مالية — طلبات التوضيح وحزمة التصدير ───────────────────────────

# كل نوع كيان مسموح ونموذجه، كي يُتحقق من ملكية الشركة قبل الربط (T2 — IDOR).
REVIEW_ENTITY_MODELS = {
    "sales_invoice": ("sales", "SalesInvoice"),
    "purchase_invoice": ("sales", "SalesInvoice"),
    "journal": ("accounting", "JournalHeader"),
    "customer_payment": ("sales", "CustomerPayment"),
    "supplier_payment": ("sales", "SupplierPayment"),
    "partner": ("partners", "Partner"),
    "period": ("accountant_portal", "TaxPeriodReview"),
    "other": None,
}


def active_engagement(*, user, tenant):
    """ارتباط المحاسب النشط مع هذه الشركة، أو None لغير المحاسبين (مدير الشركة)."""
    return (
        AccountantEngagement.objects.filter(accountant=user, tenant=tenant, status="active")
        .select_related("tenant")
        .first()
    )


def _resolve_entity(tenant, entity_type, entity_id):
    if entity_type not in REVIEW_ENTITY_MODELS:
        raise EngagementConflict("invalid_entity_type", "نوع الكيان غير مدعوم.", 422)
    target = REVIEW_ENTITY_MODELS[entity_type]
    if target is None or entity_id in (None, ""):
        return None
    from django.apps import apps

    model = apps.get_model(*target)
    instance = model.objects.filter(pk=entity_id, tenant=tenant).first()
    if instance is None:
        # مستند شركة أخرى أو غير موجود ⇒ نفس الرسالة (منع التعداد).
        raise EngagementConflict("entity_not_found", "المستند غير موجود في هذه الشركة.", 404)
    return instance


def refresh_period_status(period):
    """§7.2 — الحالة تُشتق من الموانع القائمة؛ المعتمدة وما بعدها لا تتحرك تلقائياً."""
    if period is None or period.status not in {"in_review", "needs_company_action", "ready"}:
        return period
    has_blockers = ReviewQuery.objects.filter(
        period_review=period,
        severity="blocker",
        status__in=("open", "answered"),
    ).exists()
    target = "needs_company_action" if has_blockers else "ready"
    if period.status != target:
        period.status = target
        period.save(update_fields=["status", "updated_at"])
    return period


def _query_audit_label(query):
    return sanitize_log_value(query.title)


@transaction.atomic
def create_review_query(*, tenant, user, data):
    engagement = active_engagement(user=user, tenant=tenant)
    if engagement is None:
        raise EngagementConflict("engagement_required", "يلزم ارتباط محاسبي نشط.", 403)
    title = sanitize_log_value(data.get("title"), 200)
    body = str(data.get("body") or "").strip()
    if not title or not body:
        raise EngagementConflict("invalid_query", "العنوان والنص مطلوبان.", 400)
    severity = str(data.get("severity") or "warning")
    if severity not in dict(ReviewQuery.SEVERITIES):
        raise EngagementConflict("invalid_severity", "درجة الأهمية غير صالحة.", 422)
    entity_type = str(data.get("entity_type") or "other")
    entity = _resolve_entity(tenant, entity_type, data.get("entity_id"))
    period = None
    if data.get("period_review_id"):
        period = TaxPeriodReview.objects.filter(
            pk=data["period_review_id"], tenant=tenant,
        ).first()
        if period is None:
            raise EngagementConflict("period_not_found", "الفترة غير موجودة.", 404)

    query = ReviewQuery.objects.create(
        tenant=tenant,
        engagement=engagement,
        period_review=period,
        entity_type=entity_type,
        entity_id=getattr(entity, "pk", None),
        entity_label=sanitize_log_value(data.get("entity_label"), 200),
        title=title,
        body=body,
        severity=severity,
        raised_by=user,
        attachment_url=sanitize_log_value(data.get("attachment_url"), 500),
    )
    refresh_period_status(period)
    log_activity(
        action="create",
        entity_type="accountant_review_query",
        entity_id=query.pk,
        entity_label=_query_audit_label(query),
        description=f"طلب توضيح ({query.severity}): {_query_audit_label(query)}",
        metadata={"module": "accountant_portal", "severity": query.severity},
        tenant=tenant,
        user=user,
    )
    return query


@transaction.atomic
def answer_review_query(*, query, user, body):
    if query.status in ("resolved", "withdrawn"):
        raise EngagementConflict("query_closed", "طلب التوضيح مغلق.")
    answer = str(body or "").strip()
    if not answer:
        raise EngagementConflict("invalid_answer", "نص الرد مطلوب.", 400)
    query.answer_body = answer
    query.answered_by = user
    query.answered_at = timezone.now()
    query.status = "answered"
    query.save(update_fields=["answer_body", "answered_by", "answered_at", "status", "updated_at"])
    refresh_period_status(query.period_review)
    log_activity(
        action="update",
        entity_type="accountant_review_query",
        entity_id=query.pk,
        entity_label=_query_audit_label(query),
        description=f"رد الشركة على طلب توضيح: {_query_audit_label(query)}",
        metadata={"module": "accountant_portal"},
        tenant=query.tenant,
        user=user,
    )
    return query


@transaction.atomic
def close_review_query(*, query, user, outcome):
    if outcome not in ("resolved", "withdrawn"):
        raise EngagementConflict("invalid_outcome", "إجراء غير معروف.", 422)
    if query.status in ("resolved", "withdrawn"):
        raise EngagementConflict("query_closed", "طلب التوضيح مغلق سابقاً.")
    query.status = outcome
    query.save(update_fields=["status", "updated_at"])
    refresh_period_status(query.period_review)
    log_activity(
        action="update",
        entity_type="accountant_review_query",
        entity_id=query.pk,
        entity_label=_query_audit_label(query),
        description=f"إغلاق طلب توضيح ({outcome}): {_query_audit_label(query)}",
        metadata={"module": "accountant_portal"},
        tenant=query.tenant,
        user=user,
    )
    return query


REVIEW_PACKAGE_COLUMNS = (
    ("kind", "النوع"),
    ("invoice_number", "رقم المستند"),
    ("invoice_date", "التاريخ"),
    ("partner_name", "الطرف"),
    ("partner_tax_number", "الرقم الضريبي"),
    ("currency", "العملة"),
    ("exchange_rate", "سعر الصرف"),
    ("subtotal", "الصافي قبل الضريبة"),
    ("tax_amount", "الضريبة"),
    ("grand_total", "الإجمالي"),
    ("status", "الحالة"),
)


def build_review_package(*, tenant, period_from, period_to):
    """صفوف حزمة المراجعة — استعلام واحد بلا حلقة على قاعدة البيانات."""
    from sales.models import SalesInvoice

    rows = []
    invoices = (
        SalesInvoice.objects.filter(
            tenant=tenant,
            invoice_date__gte=period_from,
            invoice_date__lte=period_to,
        )
        .select_related("customer", "currency")
        .order_by("invoice_date", "id")
    )
    for invoice in invoices:
        rows.append({
            "kind": invoice.get_invoice_kind_display(),
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat(),
            "partner_name": getattr(invoice.customer, "name", ""),
            "partner_tax_number": getattr(invoice.customer, "tax_number", "") or "",
            "currency": getattr(invoice.currency, "Code", ""),
            "exchange_rate": str(invoice.exchange_rate),
            "subtotal": str(invoice.subtotal_excl_tax),
            "tax_amount": str(invoice.tax_amount),
            "grand_total": str(invoice.grand_total),
            "status": invoice.get_status_display(),
        })
    return rows


@transaction.atomic
def record_package_export(*, tenant, user, period_from, period_to, export_format, row_count):
    write_financial_audit(
        tenant=tenant,
        user=user,
        action="PKG_EXPORTED",
        model_name="ReviewPackage",
        object_id=0,
        change_details={
            "from": str(period_from),
            "to": str(period_to),
            "format": export_format,
            "rows": row_count,
        },
    )
    log_activity(
        action="export",
        entity_type="accountant_review_package",
        entity_id=0,
        entity_label=f"{period_from} → {period_to}",
        description=f"تصدير حزمة المراجعة ({export_format})",
        metadata={"module": "accountant_portal", "rows": row_count},
        tenant=tenant,
        user=user,
    )


# ── M5: الفترة الضريبية — التجهيز والجاهزية والاعتماد والقفل ─────────────────


def _write_period_audit(period, actor, action, details=None):
    write_financial_audit(
        tenant=period.tenant,
        user=actor,
        action=action,
        model_name="TaxPeriodReview",
        object_id=period.pk,
        change_details=details or {},
    )


def _log_period(period, actor, action, description):
    log_activity(
        action=action,
        entity_type="accountant_tax_period",
        entity_id=period.pk,
        entity_label=f"{period.period_from} → {period.period_to}",
        description=sanitize_log_value(description),
        metadata={"module": "accountant_portal", "status": period.status},
        tenant=period.tenant,
        user=actor,
    )


@transaction.atomic
def prepare_tax_period(*, tenant, user, period_from, period_to):
    """يفتح مراجعة فترة ويولّد كشف ض.ق.م لها. التكرار ⇒ 409 لا صفّاً ثانياً."""
    if period_from is None or period_to is None or period_from > period_to:
        raise EngagementConflict("invalid_period", "حدود الفترة غير صالحة.", 400)
    overlap = (
        TaxPeriodReview.objects.select_for_update()
        .filter(tenant=tenant, period_from__lte=period_to, period_to__gte=period_from)
        .first()
    )
    if overlap is not None:
        raise EngagementConflict("period_overlap", "توجد مراجعة تغطي هذه الفترة.")

    period = TaxPeriodReview.objects.create(
        tenant=tenant,
        period_from=period_from,
        period_to=period_to,
        status="in_review",
        prepared_by=user,
        prepared_at=timezone.now(),
    )
    from django.core.exceptions import ValidationError as DjangoValidationError
    from sales.services import build_vat_statement

    try:
        statement = build_vat_statement(tenant.pk, period_from, period_to, user=user)
    except DjangoValidationError as exc:
        raise EngagementConflict("period_overlap", "يوجد كشف ضريبة يغطي هذه الفترة.") from exc
    period.vat_statement = statement
    period.save(update_fields=["vat_statement", "updated_at"])

    _write_period_audit(period, user, "TAX_PREPARED", {
        "from": str(period_from), "to": str(period_to), "statement": statement.statement_number,
    })
    _log_period(period, user, "create", "تجهيز فترة ضريبية للمراجعة")
    refresh_period_status(period)
    return period


def period_readiness(period):
    from accountant_portal.readiness import run_readiness_checks

    return run_readiness_checks(
        tenant=period.tenant,
        period_from=period.period_from,
        period_to=period.period_to,
        settings=get_portal_settings(period.tenant),
        period=period,
    )


@transaction.atomic
def approve_tax_period(*, period, user, request):
    from accountant_portal.readiness import has_blockers

    locked = TaxPeriodReview.objects.select_for_update().select_related("tenant").get(pk=period.pk)
    if locked.status in ("approved", "submitted", "locked"):
        raise EngagementConflict("not_open", "الفترة معتمدة أو مقدَّمة سابقاً.")
    require_reauth(request=request, tenant=locked.tenant, user=user)
    findings = period_readiness(locked)
    if has_blockers(findings):
        raise EngagementConflict("has_blockers", "لا يمكن الاعتماد مع وجود موانع مفتوحة.")
    locked.status = "approved"
    locked.approved_by = user
    locked.approved_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _write_period_audit(locked, user, "TAX_APPROVED")
    _log_period(locked, user, "update", "اعتماد الفترة الضريبية")
    return locked


@transaction.atomic
def reopen_tax_period(*, period, user, reason):
    """ق16 — إعادة الفتح لمدير الشركة بسبب إلزامي، والمقفلة لا رجعة فيها."""
    locked = TaxPeriodReview.objects.select_for_update().select_related("tenant").get(pk=period.pk)
    if locked.status in ("submitted", "locked"):
        raise EngagementConflict("period_locked", "الفترة المقدَّمة مقفلة نهائياً.")
    if locked.status != "approved":
        raise EngagementConflict("not_approved", "الفترة ليست معتمدة.")
    cleaned = sanitize_log_value(reason, 2000)
    if not cleaned:
        raise EngagementConflict("reason_required", "سبب إعادة الفتح إلزامي.", 400)
    locked.status = "in_review"
    locked.approved_by = None
    locked.approved_at = None
    locked.reopen_count = (locked.reopen_count or 0) + 1
    locked.last_reopen_reason = cleaned
    locked.save(update_fields=[
        "status", "approved_by", "approved_at", "reopen_count", "last_reopen_reason", "updated_at",
    ])
    _write_period_audit(locked, user, "TAX_REOPENED", {"reason": cleaned, "count": locked.reopen_count})
    _log_period(locked, user, "update", "إعادة فتح فترة معتمدة")
    refresh_period_status(locked)
    return locked


@transaction.atomic
def submit_tax_period(*, period, user, request, reference, submitted_on=None):
    """تسجيل التقديم يدوياً ثم القفل فوراً — لا إرسال آلي (§17)."""
    locked = TaxPeriodReview.objects.select_for_update().select_related("tenant").get(pk=period.pk)
    if locked.status in ("submitted", "locked"):
        raise EngagementConflict("already_submitted", "سُجِّل تقديم هذه الفترة سابقاً.")
    if locked.status != "approved":
        raise EngagementConflict("not_approved", "لا تقديم قبل الاعتماد.")
    require_reauth(request=request, tenant=locked.tenant, user=user)
    cleaned = sanitize_log_value(reference, 120)
    if not cleaned:
        raise EngagementConflict("reference_required", "مرجع التقديم إلزامي.", 400)
    now = timezone.now()
    locked.status = "locked"
    locked.submitted_by = user
    locked.submitted_at = submitted_on or now
    locked.submission_reference = cleaned
    locked.locked_at = now
    locked.save(update_fields=[
        "status", "submitted_by", "submitted_at", "submission_reference", "locked_at", "updated_at",
    ])
    _write_period_audit(locked, user, "TAX_SUBMITTED", {"reference": cleaned})
    _write_period_audit(locked, user, "TAX_LOCKED")
    _log_period(locked, user, "update", "تسجيل تقديم الإقرار وقفل الفترة")
    return locked


# ── مكتب المحاسبة: ملف الزبون (قراءة فقط) ────────────────────────────────────
#
# الحساب هنا **بسيط عمداً** كما طلب المالك: إيرادات − مصروفات = الربح،
# وضريبة المخرجات − ضريبة المدخلات = المستحق للضريبة. لا اشتقاقات إضافية.

_ZERO = Decimal("0.00")

CLIENT_DOCUMENT_KINDS = {
    "sales": ("sale", "sale_return"),
    "purchases": ("purchase", "purchase_return"),
}


def _money(value):
    return (Decimal(value or 0)).quantize(Decimal("0.01"))


def client_invoice_rows(*, tenant, kind, date_from, date_to):
    """فواتير الزبون في النافذة — استعلام واحد، وقراءة محضة."""
    from sales.models import SalesInvoice

    kinds = CLIENT_DOCUMENT_KINDS[kind]
    invoices = (
        SalesInvoice.objects.filter(
            tenant=tenant,
            invoice_kind__in=kinds,
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
        )
        .select_related("customer", "currency")
        .order_by("-invoice_date", "-id")
    )
    rows = []
    totals = {"subtotal": _ZERO, "tax_amount": _ZERO, "grand_total": _ZERO}
    for invoice in invoices:
        sign = Decimal("-1") if invoice.invoice_kind.endswith("_return") else Decimal("1")
        rows.append({
            "id": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "kind": invoice.invoice_kind,
            "kind_label": invoice.get_invoice_kind_display(),
            "partner_name": getattr(invoice.customer, "name", ""),
            "partner_tax_number": getattr(invoice.customer, "tax_number", "") or "",
            "status": invoice.status,
            "status_label": invoice.get_status_display(),
            "subtotal": str(_money(invoice.subtotal_excl_tax)),
            "tax_amount": str(_money(invoice.tax_amount)),
            "grand_total": str(_money(invoice.grand_total)),
        })
        totals["subtotal"] += sign * _money(invoice.subtotal_excl_tax)
        totals["tax_amount"] += sign * _money(invoice.tax_amount)
        totals["grand_total"] += sign * _money(invoice.grand_total)
    return rows, {key: str(_money(value)) for key, value in totals.items()}


def client_expense_rows(*, tenant, date_from, date_to):
    """مصاريف الزبون من الأستاذ مجمّعةً بالحساب — لا تفوتها مصاريف بلا فاتورة."""
    from django.db.models import Count, F, Sum
    from accounting.models import JournalLine

    rows = (
        JournalLine.objects.filter(
            tenant=tenant,
            journal__is_posted=True,
            journal__transaction_date__gte=date_from,
            journal__transaction_date__lte=date_to,
            account__account_type="Expense",
        )
        .values("account_id", "account__code", "account__name")
        .annotate(
            debit=Sum("debit"),
            credit=Sum("credit"),
            entries=Count("id"),
        )
        .order_by("account__code")
    )
    results = []
    total = _ZERO
    for row in rows:
        amount = _money(row["debit"] or 0) - _money(row["credit"] or 0)
        if amount == _ZERO:
            continue
        total += amount
        results.append({
            "account_id": row["account_id"],
            "code": row["account__code"] or "",
            "name": row["account__name"] or "",
            "entries": row["entries"],
            "amount": str(amount),
        })
    return results, {"amount": str(_money(total))}


def client_financial_summary(*, tenant, date_from, date_to):
    """ملخص الزبون: الربح والضريبة بحسبة مباشرة يفهمها صاحب المكتب فوراً."""
    from django.db.models import Case, DecimalField, Sum, When
    from accounting.models import JournalLine
    from sales.models import SalesInvoice

    decimal_field = DecimalField(max_digits=18, decimal_places=2)
    ledger = JournalLine.objects.filter(
        tenant=tenant,
        journal__is_posted=True,
        journal__transaction_date__gte=date_from,
        journal__transaction_date__lte=date_to,
        account__account_type__in=("Revenue", "Expense"),
    ).aggregate(
        revenue=Sum(
            Case(
                When(account__account_type="Revenue", then=F("credit") - F("debit")),
                default=Decimal("0"),
                output_field=decimal_field,
            )
        ),
        expenses=Sum(
            Case(
                When(account__account_type="Expense", then=F("debit") - F("credit")),
                default=Decimal("0"),
                output_field=decimal_field,
            )
        ),
    )
    vat = SalesInvoice.objects.filter(
        tenant=tenant,
        status="posted",
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
    ).aggregate(
        output_vat=Sum(
            Case(
                When(invoice_kind="sale", then=F("tax_amount")),
                When(invoice_kind="sale_return", then=-F("tax_amount")),
                default=Decimal("0"),
                output_field=decimal_field,
            )
        ),
        input_vat=Sum(
            Case(
                When(invoice_kind="purchase", then=F("tax_amount")),
                When(invoice_kind="purchase_return", then=-F("tax_amount")),
                default=Decimal("0"),
                output_field=decimal_field,
            )
        ),
    )

    # الميزانية تراكمية حتى نهاية الفترة لا داخلها — أصول وخصوم وحقوق ملكية.
    balances = JournalLine.objects.filter(
        tenant=tenant,
        journal__is_posted=True,
        journal__transaction_date__lte=date_to,
        account__account_type__in=("Asset", "Liability", "Equity"),
    ).aggregate(
        assets=Sum(
            Case(
                When(account__account_type="Asset", then=F("debit") - F("credit")),
                default=Decimal("0"),
                output_field=decimal_field,
            )
        ),
        liabilities=Sum(
            Case(
                When(account__account_type="Liability", then=F("credit") - F("debit")),
                default=Decimal("0"),
                output_field=decimal_field,
            )
        ),
        equity=Sum(
            Case(
                When(account__account_type="Equity", then=F("credit") - F("debit")),
                default=Decimal("0"),
                output_field=decimal_field,
            )
        ),
    )

    revenue = _money(ledger["revenue"])
    expenses = _money(ledger["expenses"])
    output_vat = _money(vat["output_vat"])
    input_vat = _money(vat["input_vat"])
    assets = _money(balances["assets"])
    liabilities = _money(balances["liabilities"])
    equity = _money(balances["equity"])
    return {
        "assets": str(assets),
        "liabilities": str(liabilities),
        "equity": str(equity),
        # الفرق يكشف اختلال الميزانية فوراً بدل تركه للمحاسب يبحث عنه.
        "balance_gap": str(assets - liabilities - equity),
        "period_from": str(date_from),
        "period_to": str(date_to),
        "revenue": str(revenue),
        "expenses": str(expenses),
        "profit": str(revenue - expenses),
        "output_vat": str(output_vat),
        "input_vat": str(input_vat),
        "vat_due": str(output_vat - input_vat),
    }


def _statement_rows(queryset, *, credit_positive):
    """صفوف بيان مالي مجمَّعة بالحساب — الاتجاه يحدد إشارة الرصيد."""
    rows = []
    total = _ZERO
    for row in queryset:
        debit = _money(row["debit"] or 0)
        credit = _money(row["credit"] or 0)
        amount = (credit - debit) if credit_positive else (debit - credit)
        if amount == _ZERO:
            continue
        total += amount
        rows.append({
            "account_id": row["account_id"],
            "code": row["account__code"] or "",
            "name": row["account__name"] or "",
            "amount": str(amount),
        })
    return rows, total


def client_statements(*, tenant, date_from, date_to):
    """قائمة الدخل والميزانية العمومية بالحسابات — بيانان يعرفهما كل محاسب.

    قائمة الدخل عن **الفترة**، والميزانية **تراكمية حتى تاريخ نهايتها** — وهو الفرق
    الذي يخطئ فيه كل تقرير مرتجل.
    """
    from django.db.models import Sum
    from accounting.models import JournalLine

    posted = {"tenant": tenant, "journal__is_posted": True}
    income = (
        JournalLine.objects.filter(
            **posted,
            journal__transaction_date__gte=date_from,
            journal__transaction_date__lte=date_to,
            account__account_type__in=("Revenue", "Expense"),
        )
        .values("account_id", "account__code", "account__name", "account__account_type")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code")
    )
    balance = (
        JournalLine.objects.filter(
            **posted,
            journal__transaction_date__lte=date_to,
            account__account_type__in=("Asset", "Liability", "Equity"),
        )
        .values("account_id", "account__code", "account__name", "account__account_type")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code")
    )

    income_rows = list(income)
    balance_rows = list(balance)
    revenue_rows, revenue_total = _statement_rows(
        [row for row in income_rows if row["account__account_type"] == "Revenue"],
        credit_positive=True,
    )
    expense_rows, expense_total = _statement_rows(
        [row for row in income_rows if row["account__account_type"] == "Expense"],
        credit_positive=False,
    )
    asset_rows, asset_total = _statement_rows(
        [row for row in balance_rows if row["account__account_type"] == "Asset"],
        credit_positive=False,
    )
    liability_rows, liability_total = _statement_rows(
        [row for row in balance_rows if row["account__account_type"] == "Liability"],
        credit_positive=True,
    )
    equity_rows, equity_total = _statement_rows(
        [row for row in balance_rows if row["account__account_type"] == "Equity"],
        credit_positive=True,
    )
    return {
        "income": {
            "revenue": revenue_rows,
            "expenses": expense_rows,
            "revenue_total": str(revenue_total),
            "expense_total": str(expense_total),
            "profit": str(revenue_total - expense_total),
        },
        "balance": {
            "assets": asset_rows,
            "liabilities": liability_rows,
            "equity": equity_rows,
            "asset_total": str(asset_total),
            "liability_total": str(liability_total),
            "equity_total": str(equity_total),
            "gap": str(asset_total - liability_total - equity_total),
        },
    }


def client_monthly_trend(*, tenant, months=6, today=None):
    """منحنى آخر أشهر: إيراد/مصروف/ربح لكل شهر — استعلامان مهما طال المدى."""
    from django.db.models import Case, DecimalField, Sum, When
    from django.db.models.functions import TruncMonth
    from accounting.models import JournalLine

    today = today or timezone.localdate()
    first_of_month = today.replace(day=1)
    start = first_of_month
    for _ in range(max(1, int(months)) - 1):
        start = (start - timedelta(days=1)).replace(day=1)

    decimal_field = DecimalField(max_digits=18, decimal_places=2)
    rows = (
        JournalLine.objects.filter(
            tenant=tenant,
            journal__is_posted=True,
            journal__transaction_date__gte=start,
            account__account_type__in=("Revenue", "Expense"),
        )
        .annotate(month=TruncMonth("journal__transaction_date"))
        .values("month")
        .annotate(
            revenue=Sum(
                Case(
                    When(account__account_type="Revenue", then=F("credit") - F("debit")),
                    default=Decimal("0"),
                    output_field=decimal_field,
                )
            ),
            expenses=Sum(
                Case(
                    When(account__account_type="Expense", then=F("debit") - F("credit")),
                    default=Decimal("0"),
                    output_field=decimal_field,
                )
            ),
        )
        .order_by("month")
    )
    by_month = {
        (row["month"].strftime("%Y-%m") if hasattr(row["month"], "strftime") else str(row["month"])[:7]): row
        for row in rows
    }

    series = []
    cursor = start
    while cursor <= first_of_month:
        key = cursor.strftime("%Y-%m")
        row = by_month.get(key)
        revenue = _money(row["revenue"]) if row else _ZERO
        expenses = _money(row["expenses"]) if row else _ZERO
        series.append({
            "month": key,
            "revenue": str(revenue),
            "expenses": str(expenses),
            "profit": str(revenue - expenses),
        })
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return series


def practice_overview(*, accountant, today=None):
    """لوحة المكتب: كل زبائن المحاسب في مكان واحد بأربعة استعلامات مهما كثروا."""
    from django.db.models import Case, Count, DecimalField, Sum, When
    from accounting.models import JournalLine
    from sales.models import SalesInvoice

    today = today or timezone.localdate()
    period_from = today.replace(day=1)
    period_to = (period_from + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    decimal_field = DecimalField(max_digits=18, decimal_places=2)

    engagements = list(
        AccountantEngagement.objects
        .filter(accountant=accountant, status="active")
        .select_related("tenant")
        .order_by("tenant__CompanyName")
    )
    tenant_ids = [item.tenant_id for item in engagements]

    ledger = {
        row["tenant"]: row
        for row in JournalLine.objects.filter(
            tenant_id__in=tenant_ids,
            journal__is_posted=True,
            journal__transaction_date__gte=period_from,
            journal__transaction_date__lte=period_to,
            account__account_type__in=("Revenue", "Expense"),
        )
        .values("tenant")
        .annotate(
            revenue=Sum(
                Case(
                    When(account__account_type="Revenue", then=F("credit") - F("debit")),
                    default=Decimal("0"),
                    output_field=decimal_field,
                )
            ),
            expenses=Sum(
                Case(
                    When(account__account_type="Expense", then=F("debit") - F("credit")),
                    default=Decimal("0"),
                    output_field=decimal_field,
                )
            ),
        )
    }
    invoices = {
        row["tenant"]: row
        for row in SalesInvoice.objects.filter(
            tenant_id__in=tenant_ids,
            invoice_date__gte=period_from,
            invoice_date__lte=period_to,
        )
        .values("tenant")
        .annotate(
            output_vat=Sum(
                Case(
                    When(invoice_kind="sale", status="posted", then=F("tax_amount")),
                    When(invoice_kind="sale_return", status="posted", then=-F("tax_amount")),
                    default=Decimal("0"),
                    output_field=decimal_field,
                )
            ),
            input_vat=Sum(
                Case(
                    When(invoice_kind="purchase", status="posted", then=F("tax_amount")),
                    When(invoice_kind="purchase_return", status="posted", then=-F("tax_amount")),
                    default=Decimal("0"),
                    output_field=decimal_field,
                )
            ),
            drafts=Count(Case(When(status="draft", then=1))),
        )
    }
    due_days = dict(
        PortalSettings.objects.filter(tenant_id__in=tenant_ids)
        .values_list("tenant_id", "filing_due_days")
    )

    clients = []
    totals = {"vat_due": _ZERO, "profit": _ZERO, "drafts": 0, "attention": 0}
    for engagement in engagements:
        stats = ledger.get(engagement.tenant_id, {})
        vat = invoices.get(engagement.tenant_id, {})
        revenue = _money(stats.get("revenue"))
        expenses = _money(stats.get("expenses"))
        output_vat = _money(vat.get("output_vat"))
        input_vat = _money(vat.get("input_vat"))
        vat_due = output_vat - input_vat
        drafts = int(vat.get("drafts") or 0)
        filing_due = period_to + timedelta(days=int(due_days.get(engagement.tenant_id, 15)))
        needs_attention = drafts > 0
        totals["vat_due"] += vat_due
        totals["profit"] += revenue - expenses
        totals["drafts"] += drafts
        totals["attention"] += 1 if needs_attention else 0
        clients.append({
            "tenant_id": engagement.tenant_id,
            "company_name": engagement.tenant.CompanyName,
            "revenue": str(revenue),
            "expenses": str(expenses),
            "profit": str(revenue - expenses),
            "vat_due": str(vat_due),
            "draft_documents": drafts,
            "filing_due_date": str(filing_due),
            "days_to_filing": (filing_due - today).days,
            "needs_attention": needs_attention,
        })

    return {
        "period_from": str(period_from),
        "period_to": str(period_to),
        "clients": clients,
        "totals": {
            "clients": len(clients),
            "vat_due": str(totals["vat_due"]),
            "profit": str(totals["profit"]),
            "draft_documents": totals["drafts"],
            "needs_attention": totals["attention"],
        },
    }


PORTAL_SETTING_FIELDS = (
    "tax_jurisdiction",
    "strict_invoice_field_validation",
    "clearance_mode",
    "is_israeli_registered_dealer",
    "require_reauth_for_sensitive",
    "reauth_window_minutes",
    "engagement_retention_years",
    "allow_grant_cost_view",
    "invitation_expiry_days",
    "max_active_engagements",
    "lock_blocks_posting",
    "default_grant_profile",
    "tax_period_type",
    "filing_due_days",
    "input_vat_window_months",
    "allow_accountant_reopen",
    "export_formats",
    "notify_company_on_accountant_action",
)


def portal_settings_payload(config):
    return {field: getattr(config, field) for field in PORTAL_SETTING_FIELDS}


@transaction.atomic
def update_portal_settings(*, tenant, actor, data):
    """تعديل إعدادات البوابة — لمدير الشركة وحده، وكل تعديل مدقَّق."""
    config = get_portal_settings(tenant)
    changed = {}
    for field in PORTAL_SETTING_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field == "export_formats" and not isinstance(value, list):
            raise EngagementConflict("invalid_settings", "صيغ التصدير يجب أن تكون قائمة.", 400)
        if getattr(config, field) != value:
            changed[field] = value
        setattr(config, field, value)
    if not changed:
        return config
    try:
        config.full_clean(exclude=["tenant"])
    except Exception as exc:  # ValidationError من full_clean
        raise EngagementConflict("invalid_settings", "قيمة إعداد غير صالحة.", 400) from exc
    config.save()
    write_financial_audit(
        tenant=tenant,
        user=actor,
        action="PORTAL_CFG_SET",
        model_name="PortalSettings",
        object_id=config.pk,
        change_details={"fields": sorted(changed)},
    )
    log_activity(
        action="update",
        entity_type="accountant_portal_settings",
        entity_id=config.pk,
        entity_label="إعدادات بوابة المحاسب",
        description="تعديل إعدادات بوابة المحاسب",
        metadata={"module": "accountant_portal", "fields": sorted(changed)},
        tenant=tenant,
        user=actor,
    )
    return config


@transaction.atomic
def set_engagement_scope(*, engagement, actor, scope):
    locked = AccountantEngagement.objects.select_for_update().select_related("tenant").get(pk=engagement.pk)
    if locked.status != "active":
        raise EngagementConflict("not_active", "الارتباط غير نشط.")
    normalized_scope = validate_scope(locked.tenant, scope)
    _replace_membership_scope(locked, normalized_scope)
    locked.approved_scope_snapshot = normalized_scope
    locked.save(update_fields=["approved_scope_snapshot", "updated_at"])
    _write_engagement_audit(locked, actor, "ENG_SCOPE_SET", {"scope": normalized_scope})
    _log_engagement(locked, actor, "update", "تعديل نطاق الارتباط المحاسبي")
    return locked

