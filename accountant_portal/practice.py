"""مكتب المحاسبة — خدمات سجلّ الممارسة (زبائن، برامج، مواعيد، مستندات).

ISSUE #86: زبون المكتب صار `partners.Partner` داخل شركة مكتب المحاسب — لا سجلّ
منفصل، وفاتورة الأتعاب فاتورة بيع عادية على نفس الطرف. `PracticeClient` مجمَّدٌ
(انظر `models.py` وقرار `docs/decisions/practice_client_retirement.md`)؛
البرامج والمواعيد والمستندات تبقى نماذجها كما هي، مفتاحها الحيّ `partner`.

**الجدار** (§الوحدة): البرامج والمواعيد والمستندات مملوكة للمحاسب لا لشركة، فلا
`tenant` عليها، ولا يصل من هذه الوحدة طريق إلى `post_journal` ولا إلى
`record_stock_movement`. زبون المكتب وحده استثناءٌ الآن — طرفٌ حقيقي داخل شركة
المكتب (`office_tenant_id`)، وأتعابه تُفوتَر بفاتورة بيع عادية بمحاسبتها الكاملة.

**العزل**: البرامج/المواعيد/المستندات كما في `services.py` — `accountant=`،
وصفّ محاسبٍ آخر «غير موجود» (404) لا «ممنوع» (403). الزبون عبر
`tenant=office_tenant_id(accountant)` بنفس فلسفة «غير موجود» لا «ممنوع».
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    PracticeClient,
    PracticeDocument,
    PracticeProgram,
    PracticeSettings,
    PracticeTask,
)
from accountant_portal.services import (
    EngagementConflict,
    practice_overview,
    sanitize_log_value,
)


logger = logging.getLogger(__name__)

# «قريب» في لوحة المواعيد — أسبوع، وهو أفق المتابعة الذي يعمل به المكتب.
DUE_SOON_DAYS = 7

# ISSUE #86: زبون المكتب صار `partners.Partner` — هذه الحقول تُحرَّر عبر
# `/api/accountant/practice/clients/*` (كما `/api/partners/` العام) بلا حاجة
# لاستيراد `partners.serializers` (داخلياتٌ محرَّمة على apps أخرى؛ الموديل
# وحده واجهة عامة مؤقتة — `.importlinter`).
PARTNER_TEXT_FIELDS = ("phone", "mobile", "sector", "tax_number")


def _profile(accountant):
    try:
        return accountant.accountant_profile
    except AccountantProfile.DoesNotExist as exc:
        raise EngagementConflict("accountant_profile_required", "يلزم ملف محاسب مهني.", 403) from exc


def _log(action, accountant, **details):
    """أثر تشغيلي فقط: لا `tenant` هنا ⇒ لا `ActivityLog` ولا تدقيق مالي."""
    logger.info(
        "accountant_practice %s user=%s %s",
        action,
        accountant.pk,
        " ".join(f"{key}={sanitize_log_value(value, 120)}" for key, value in details.items()),
    )


def _text(data, key, limit):
    return str(data.get(key) or "").strip()[:limit]


# ── إعدادات المكتب ───────────────────────────────────────────────────────────


def get_practice_settings(accountant):
    """إعدادات المكتب — تتجسّد عند أول قراءة، وغيابها لا يكسر شيئاً."""
    config, _ = PracticeSettings.objects.get_or_create(profile=_profile(accountant))
    return config


def practice_settings_payload(config):
    return {
        "default_program_due_days": config.default_program_due_days,
        "service_types": list(config.service_types or []),
    }


@transaction.atomic
def update_practice_settings(*, accountant, data):
    config = get_practice_settings(accountant)
    if "default_program_due_days" in data:
        try:
            days = int(data["default_program_due_days"])
        except (TypeError, ValueError) as exc:
            raise EngagementConflict("invalid_settings", "مهلة الاستحقاق يجب أن تكون رقماً.", 400) from exc
        if not 1 <= days <= 365:
            raise EngagementConflict("invalid_settings", "مهلة الاستحقاق بين يوم و365 يوماً.", 422)
        config.default_program_due_days = days
    if "service_types" in data:
        value = data["service_types"]
        if not isinstance(value, list):
            raise EngagementConflict("invalid_settings", "أنواع الخدمات يجب أن تكون قائمة.", 400)
        cleaned = [str(item).strip()[:120] for item in value]
        cleaned = list(dict.fromkeys(item for item in cleaned if item))
        if not cleaned:
            raise EngagementConflict("invalid_settings", "أبقِ نوع خدمة واحداً على الأقل.", 422)
        config.service_types = cleaned
    config.save()
    _log("settings_updated", accountant)
    return config


# ── الزبائن (ISSUE #86 — الطرف نفسه) ─────────────────────────────────────────
#
# زبون المكتب صار `partners.Partner` داخل شركة مكتب المحاسب: لا سجلّ منفصل،
# وفاتورة الأتعاب فاتورة بيع عادية على نفس الطرف (#46/#11). العزل يبقى بنفس
# فلسفة الوحدة — صفّ مكتبٍ آخر (أو طرفٌ خارج شركة المكتب) «غير موجود» لا
# «ممنوع» — لكنه الآن عبر `tenant=office_tenant_id` بدل `accountant=`.


def office_tenant_id(accountant):
    """شركة مكتب هذا المحاسب — أول عضوية Manager على شركة ليست دفتراً مُداراً.

    نفس شرط `_office_tenant_ids` تحت: محاسبٌ لم يُرحَّل بعد (ISSUE #55) لا مكتب
    له بعد، فتُعيد None — ولا يُنشئ استدعاءٌ قارئٌ شركةً ضمنياً.
    """
    tenant_ids = _office_tenant_ids(accountant)
    return tenant_ids[0] if tenant_ids else None


def _require_office_tenant(accountant):
    tenant_id = office_tenant_id(accountant)
    if tenant_id is None:
        raise EngagementConflict(
            "office_required", "أنشئ شركة مكتب محاسبة أولاً قبل إضافة زبائن.", 409,
        )
    return tenant_id


#: علامة CustomerNote التي يكتبها `migrate_practice_clients_to_partners` —
#: مصدر الحقيقة الوحيد لـ«هل نُقل هذا الزبون؟». يستوردها الأمر من هنا فلا يتكرّر
#: الحرفي في مكانين قد ينحرفان.
MIGRATION_MARKER_TARGET_TYPE = "practice_client_migration"

#: سِجلٌّ واحد لكل طرف يحمل ما لا حقل بنيويّاً له على `Partner` — جهة الاتصال
#: والملاحظات الحرّة (مراجعة 2 من ISSUE #86: أُعيدت بعد أن حذفتها المراجعة
#: الأولى بلا إذن). يُحدَّث في مكانه لا يُراكَم صفاً بعد صفّ.
PROFILE_NOTE_TARGET_TYPE = "practice_client_profile"


def _migrated_practice_client_ids(client_ids):
    """أيّ `PracticeClient.pk` من هذه المجموعة عليه علامة نقلٍ ناجحة — استعلامٌ
    واحدٌ لا واحد لكل صفّ."""
    from partners.models import CustomerNote

    if not client_ids:
        return set()
    return set(
        CustomerNote.objects.filter(
            target_type=MIGRATION_MARKER_TARGET_TYPE,
            target_id__in=[str(pk) for pk in client_ids],
        ).values_list("target_id", flat=True)
    )


def _unmigrated_practice_clients(accountant, search=None):
    """PracticeClient تابعةٌ لهذا المحاسب ولم تُنقل بعد — **سقوط قراءةٍ وحده**
    (مراجعة 2 من ISSUE #86): محاسبٌ لم يُشغَّل له أمر الترحيل بعد، أو تعثّر، أو
    أضاف له `migrate_accountant_offices` (#55) زبوناً جديداً بعد ترحيله، يبقى
    يرى هذه الصفوف هنا حتى تُنقل فعلاً. **لا كتابة على `PracticeClient` من هذه
    الدالة ولا من أي دالة تستدعيها** — القراءة فقط تسقط، لا الكتابة.
    """
    queryset = PracticeClient.objects.filter(accountant=accountant)
    if search:
        queryset = queryset.filter(trade_name__icontains=str(search)[:200])
    clients = list(queryset)
    if not clients:
        return []
    migrated = _migrated_practice_client_ids([client.pk for client in clients])
    return [client for client in clients if str(client.pk) not in migrated]


def _legacy_client_payload(client):
    """معرّفٌ **سالبٌ** عمداً: لا يتقاطع أبداً مع معرّف `Partner` (موجبٌ دوماً)،
    فكتابةٌ عليه (`get_office_partner` الصارمة) تُخفق بأمان بدل أن تصيب صفّاً
    خطأً. القراءة وحدها تفهمه (`get_office_client_view` تحت)."""
    return {
        "id": -client.pk,
        "trade_name": client.trade_name,
        "contact_first": client.contact_first,
        "contact_last": client.contact_last,
        "phone": client.phone or "",
        "mobile": client.mobile or "",
        "email": client.email or "",
        "address": client.address or "",
        "sector": client.sector or "",
        "tax_number": client.tax_number or "",
        "notes": client.notes,
        "status": client.status,
        "engagement_id": client.engagement_id,
        "managed_tenant_id": client.managed_tenant_id,
        "client_type": client.client_type,
        "tenant_id": client.engagement.tenant_id if client.engagement_id else None,
        "created_at": client.created_at,
        "legacy": True,
    }


def _load_profile_notes(partner_ids):
    """جهة الاتصال والملاحظات — استعلامٌ واحدٌ مجمَّعٌ لكل الأطراف المطلوبة."""
    import json

    from partners.models import CustomerNote

    if not partner_ids:
        return {}
    notes = CustomerNote.objects.filter(
        target_type=PROFILE_NOTE_TARGET_TYPE, target_id__in=[str(pk) for pk in partner_ids],
    )
    result = {}
    for note in notes:
        try:
            result[int(note.target_id)] = json.loads(note.body or "{}")
        except (TypeError, ValueError):
            result[int(note.target_id)] = {}
    return result


def _save_profile_note(partner, data):
    """يكتب جهة الاتصال/الملاحظات في سِجلٍّ واحدٍ محدَّثٍ في مكانه — لا حقل
    بنيويّ جديد على `Partner` (مُجازٌ له `sector`/`mobile` وحدهما)."""
    import json

    from partners.models import CustomerNote

    if not any(key in data for key in ("contact_first", "contact_last", "notes")):
        return
    note, _ = CustomerNote.objects.get_or_create(
        tenant_id=partner.tenant_id, partner=partner,
        target_type=PROFILE_NOTE_TARGET_TYPE, target_id=str(partner.pk),
        defaults={"title": "ملف تعريف زبون المكتب"},
    )
    try:
        current = json.loads(note.body or "{}")
    except (TypeError, ValueError):
        current = {}
    if "contact_first" in data:
        current["contact_first"] = _text(data, "contact_first", 100)
    if "contact_last" in data:
        current["contact_last"] = _text(data, "contact_last", 100)
    if "notes" in data:
        current["notes"] = _text(data, "notes", 2000)
    note.body = json.dumps(current, ensure_ascii=False)
    note.save(update_fields=["body", "updated_at"])


def _archived_partner_ids(accountant, partner_ids):
    from accountant_portal.models import PracticeClientArchive

    if not partner_ids:
        return set()
    return set(
        PracticeClientArchive.objects.filter(
            accountant=accountant, partner_id__in=partner_ids,
        ).values_list("partner_id", flat=True)
    )


def partner_client_payload(partner, *, profile=None, archived=False):
    profile = profile or {}
    return {
        "id": partner.pk,
        "trade_name": partner.name,
        "contact_first": profile.get("contact_first", ""),
        "contact_last": profile.get("contact_last", ""),
        "phone": partner.phone or "",
        "mobile": partner.mobile or "",
        "email": partner.email or "",
        "address": partner.street_address or "",
        "sector": partner.sector or "",
        "tax_number": partner.tax_number or "",
        "notes": profile.get("notes", ""),
        "status": "archived" if archived else "active",
        "engagement_id": partner.engagement_id,
        # ISSUE #52 (قرار 9 في #46): النوع مشتقّ لا مخزَّن — `Partner.client_type`.
        "managed_tenant_id": partner.managed_tenant_id,
        "client_type": partner.client_type,
        "tenant_id": partner.engagement.tenant_id if partner.engagement_id else None,
        "created_at": partner.created_at,
        "legacy": False,
    }


def get_office_partner(*, accountant, partner_id):
    """زبونٌ (طرف) داخل شركة مكتب هذا المحاسب أو «غير موجود».

    **صارمةٌ عمداً**: `Partner` وحده، معرّفٌ موجبٌ وحده — كل كتابة (إنشاء برنامج/
    موعد/مستند، تعديل، ربط) تمرّ من هنا فتُخفق بأمان على زبونٍ لم يُرحَّل بعد
    (معرّفه سالبٌ من `_legacy_client_payload`) بدل أن تكتب على `PracticeClient`.
    """
    from partners.models import Partner

    tenant_id = _require_office_tenant(accountant)
    partner = (
        Partner.objects.filter(tenant_id=tenant_id, pk=partner_id, partner_type="Customer")
        .select_related("engagement", "managed_tenant")
        .first()
    )
    if partner is None:
        raise EngagementConflict("client_not_found", "الزبون غير موجود.", 404)
    return partner


def get_office_client_view(*, accountant, client_id):
    """عرض القراءة لبطاقة الزبون — يفهم المعرّف السالب (زبونٌ قديمٌ لم يُرحَّل
    بعد) فلا يختفي ملفّه من الشاشة وقت الانتقال. الكتابة تبقى حصراً على
    `get_office_partner`/`update_office_partner` (موجبتَي المعرّف فقط)."""
    try:
        numeric_id = int(client_id)
    except (TypeError, ValueError) as exc:
        raise EngagementConflict("client_not_found", "الزبون غير موجود.", 404) from exc
    if numeric_id < 0:
        client = PracticeClient.objects.filter(accountant=accountant, pk=-numeric_id).first()
        if client is None:
            raise EngagementConflict("client_not_found", "الزبون غير موجود.", 404)
        return _legacy_client_payload(client)
    partner = get_office_partner(accountant=accountant, partner_id=numeric_id)
    profile = _load_profile_notes([partner.pk]).get(partner.pk, {})
    archived = partner.pk in _archived_partner_ids(accountant, [partner.pk])
    return partner_client_payload(partner, profile=profile, archived=archived)


def list_office_partners(*, accountant, search=None, status=None):
    """زبائن هذا المكتب: أطراف شركة المكتب المُرحَّلة **مدموجةً** بمن لم يُرحَّل
    بعد من `PracticeClient` (سقوط قراءةٍ وحده — انظر `_unmigrated_practice_clients`).

    عدد الاستعلامات ثابتٌ بصرف النظر عن عدد الزبائن: استعلامٌ للأطراف، وآخران
    مجمَّعان لملفّاتها وأرشفتها، وثالثٌ ورابعٌ للزبائن القدامى وعلامة نقلهم.
    """
    from partners.models import Partner

    rows = []
    tenant_id = office_tenant_id(accountant)
    if tenant_id is not None:
        queryset = Partner.objects.filter(
            tenant_id=tenant_id, partner_type="Customer",
        ).select_related("engagement", "managed_tenant")
        if search:
            queryset = queryset.filter(name__icontains=str(search)[:200])
        partners = list(queryset.order_by("name", "id"))
        profiles = _load_profile_notes([partner.pk for partner in partners])
        archived_ids = _archived_partner_ids(accountant, [partner.pk for partner in partners])
        rows = [
            partner_client_payload(
                partner, profile=profiles.get(partner.pk, {}), archived=partner.pk in archived_ids,
            )
            for partner in partners
        ]

    legacy_rows = [
        _legacy_client_payload(client)
        for client in sorted(_unmigrated_practice_clients(accountant, search=search), key=lambda c: c.trade_name)
    ]
    rows.extend(legacy_rows)

    if status:
        rows = [row for row in rows if row["status"] == status]
    return rows


def _resolve_engagement_for_partner(*, accountant, tenant_id, engagement_id, exclude_partner=None):
    """ربط زبون المكتب بشركة على المنصة — وارتباط مكتبٍ آخر «غير موجود» (T2)."""
    from partners.models import Partner

    if engagement_id in (None, ""):
        return None
    engagement = AccountantEngagement.objects.filter(
        pk=engagement_id, accountant=accountant,
    ).first()
    if engagement is None:
        raise EngagementConflict("engagement_not_found", "الارتباط غير موجود.", 404)
    duplicate = Partner.objects.filter(tenant_id=tenant_id, engagement=engagement)
    if exclude_partner is not None:
        duplicate = duplicate.exclude(pk=exclude_partner.pk)
    if duplicate.exists():
        raise EngagementConflict("engagement_linked", "هذه الشركة مرتبطة بزبون آخر في مكتبك.")
    return engagement


def _resolve_managed_tenant_for_partner(*, accountant, tenant_id, managed_tenant_id, exclude_partner=None):
    """ربط زبون المكتب بدفتر مُدار يملكه مكتب هذا المحاسب — دفتر مكتبٍ آخر «غير موجود».

    نفس حَكَم `TenantViewSet.get_queryset`: مديرٌ للمكتب المالك وحده يربط.
    """
    from partners.models import Partner
    from tenants.models import Tenant, UserCompanyMembership

    if managed_tenant_id in (None, ""):
        return None
    tenant = Tenant.objects.filter(pk=managed_tenant_id, managed_by__isnull=False).first()
    if tenant is None:
        raise EngagementConflict("managed_tenant_not_found", "الدفتر المُدار غير موجود.", 404)
    is_office_manager = UserCompanyMembership.objects.filter(
        user=accountant, tenant_id=tenant.managed_by_id, role="manager",
    ).exists()
    if not is_office_manager:
        raise EngagementConflict("managed_tenant_not_found", "الدفتر المُدار غير موجود.", 404)
    duplicate = Partner.objects.filter(tenant_id=tenant_id, managed_tenant=tenant)
    if exclude_partner is not None:
        duplicate = duplicate.exclude(pk=exclude_partner.pk)
    if duplicate.exists():
        raise EngagementConflict("managed_tenant_linked", "هذا الدفتر مرتبط بزبون آخر في مكتبك.")
    return tenant


def _apply_partner_fields(partner, data):
    if "trade_name" in data:
        trade_name = _text(data, "trade_name", 150)
        if not trade_name:
            raise EngagementConflict("invalid_client", "الاسم التجاري مطلوب.", 400)
        partner.name = trade_name
    for field in PARTNER_TEXT_FIELDS:
        if field in data:
            limit = partner._meta.get_field(field).max_length or 200
            setattr(partner, field, _text(data, field, limit))
    if "address" in data:
        partner.street_address = _text(data, "address", 255)
    if "email" in data:
        email = _text(data, "email", 100)
        if email:
            try:
                validate_email(email)
            except DjangoValidationError as exc:
                raise EngagementConflict("invalid_email", "أدخل بريداً إلكترونياً صالحاً.", 400) from exc
        partner.email = email


@transaction.atomic
def create_office_partner(*, accountant, data):
    """يعيد حمولة العرض جاهزةً (لا صنف `Partner` خاماً) — الحقول التي لا مكان
    بنيويّ لها (`contact_first`/`contact_last`/`notes`) كُتبت في ملفّها الجانبي
    قبل أن تُقرأ منه فوراً، فلا يرى المستدعي فرقاً بين الحفظ والقراءة."""
    from partners.models import Partner

    tenant_id = _require_office_tenant(accountant)
    if not _text(data, "trade_name", 150):
        raise EngagementConflict("invalid_client", "الاسم التجاري مطلوب.", 400)
    partner = Partner(tenant_id=tenant_id, partner_type="Customer")
    _apply_partner_fields(partner, data)
    partner.engagement = _resolve_engagement_for_partner(
        accountant=accountant, tenant_id=tenant_id, engagement_id=data.get("engagement_id"),
    )
    partner.managed_tenant = _resolve_managed_tenant_for_partner(
        accountant=accountant, tenant_id=tenant_id, managed_tenant_id=data.get("managed_tenant_id"),
    )
    try:
        partner.save()
    except IntegrityError as exc:
        raise EngagementConflict("duplicate_client", "يوجد زبون بهذا الاسم التجاري في مكتبك.") from exc
    _save_profile_note(partner, data)
    _log("client_created", accountant, client=partner.pk, name=partner.name)
    profile = _load_profile_notes([partner.pk]).get(partner.pk, {})
    return partner_client_payload(partner, profile=profile, archived=False)


@transaction.atomic
def update_office_partner(*, accountant, partner_id, data):
    partner = get_office_partner(accountant=accountant, partner_id=partner_id)
    _apply_partner_fields(partner, data)
    if "engagement_id" in data:
        partner.engagement = _resolve_engagement_for_partner(
            accountant=accountant, tenant_id=partner.tenant_id,
            engagement_id=data.get("engagement_id"), exclude_partner=partner,
        )
    if "managed_tenant_id" in data:
        partner.managed_tenant = _resolve_managed_tenant_for_partner(
            accountant=accountant, tenant_id=partner.tenant_id,
            managed_tenant_id=data.get("managed_tenant_id"), exclude_partner=partner,
        )
    try:
        partner.save()
    except IntegrityError as exc:
        raise EngagementConflict("duplicate_client", "يوجد زبون بهذا الاسم التجاري في مكتبك.") from exc
    _save_profile_note(partner, data)
    _log("client_updated", accountant, client=partner.pk)
    profile = _load_profile_notes([partner.pk]).get(partner.pk, {})
    archived = partner.pk in _archived_partner_ids(accountant, [partner.pk])
    return partner_client_payload(partner, profile=profile, archived=archived)


def link_office_partner(*, accountant, partner_id, data):
    """تعديل الربط وحده (`engagement_id`/`managed_tenant_id`) — فعلٌ حسّاس مستقلّ
    عن تعديل بيانات الاتصال العادية، لسهولة تدقيقه ولإبقاء `OfficeClientLinkForm`
    نداءً واحداً واضح النية."""
    return update_office_partner(
        accountant=accountant,
        partner_id=partner_id,
        data={key: data[key] for key in ("engagement_id", "managed_tenant_id") if key in data},
    )


@transaction.atomic
def archive_office_partner(*, accountant, partner_id):
    """أرشفة زبون مكتب — حالة طبقة المكتب لا الطرف (`PracticeClientArchive`،
    مراجعة 2 من ISSUE #86). الطرف نفسه لا يُمسّ: يبقى فاعلاً في كل مكانٍ آخر
    يستعمله (فواتير الأتعاب، شجرة الحسابات)، والأرشفة تخصّ سجلّ المكتب وحده."""
    from accountant_portal.models import PracticeClientArchive

    partner = get_office_partner(accountant=accountant, partner_id=partner_id)
    PracticeClientArchive.objects.get_or_create(accountant=accountant, partner=partner)
    _log("client_archived", accountant, client=partner.pk)
    profile = _load_profile_notes([partner.pk]).get(partner.pk, {})
    return partner_client_payload(partner, profile=profile, archived=True)


@transaction.atomic
def restore_office_partner(*, accountant, partner_id):
    from accountant_portal.models import PracticeClientArchive

    partner = get_office_partner(accountant=accountant, partner_id=partner_id)
    PracticeClientArchive.objects.filter(accountant=accountant, partner=partner).delete()
    _log("client_restored", accountant, client=partner.pk)
    profile = _load_profile_notes([partner.pk]).get(partner.pk, {})
    return partner_client_payload(partner, profile=profile, archived=False)


# ── البرامج ──────────────────────────────────────────────────────────────────


def _is_overdue(due_date, status, today):
    return bool(due_date) and status != "done" and due_date < today


def _client_ref(entity):
    """(معرّف العرض، الاسم) لبند يحمل `partner`/`client` معاً — `Partner` إن
    وُجد، وإلا زبونٌ قديمٌ لم يُرحَّل بعد (معرّفٌ سالبٌ، يطابق `_legacy_client_payload`).
    """
    if entity.partner_id:
        return entity.partner_id, entity.partner.name
    if entity.client_id:
        return -entity.client_id, entity.client.trade_name
    return None, ""


def _filter_by_client_ref(queryset, client_ref_id):
    """يقبل معرّفاً موجباً (`partner_id`) أو سالباً (`client_id` القديم)."""
    client_ref_id = int(client_ref_id)
    if client_ref_id < 0:
        return queryset.filter(client_id=-client_ref_id)
    return queryset.filter(partner_id=client_ref_id)


def program_payload(program, today=None):
    today = today or timezone.localdate()
    partner_id, partner_name = _client_ref(program)
    return {
        "id": program.pk,
        "partner_id": partner_id,
        "partner_name": partner_name,
        "service_type": program.service_type,
        "frequency": program.frequency,
        "team_note": program.team_note,
        "due_date": program.due_date,
        "status": program.status,
        "notes": program.notes,
        # التأخر مشتقّ لا مخزَّن — حالة اليوم لا حالة آخر حفظ.
        "is_overdue": _is_overdue(program.due_date, program.status, today),
    }


def get_practice_program(*, accountant, program_id):
    program = (
        PracticeProgram.objects.filter(accountant=accountant, pk=program_id)
        .select_related("partner", "client")
        .first()
    )
    if program is None:
        raise EngagementConflict("program_not_found", "البرنامج غير موجود.", 404)
    return program


def list_practice_programs(*, accountant, partner_id=None, status=None):
    queryset = PracticeProgram.objects.filter(accountant=accountant).select_related("partner", "client")
    if partner_id:
        queryset = _filter_by_client_ref(queryset, partner_id)
    if status:
        queryset = queryset.filter(status=status)
    return list(queryset.order_by("due_date", "id"))


def _validate_choice(value, choices, code, detail):
    if value not in dict(choices):
        raise EngagementConflict(code, detail, 422)
    return value


def _service_type(accountant, value):
    """نوع الخدمة من قائمة الإعدادات — كي لا يتشظّى النوع نفسه بأربع كتابات."""
    service_type = str(value or "").strip()[:120]
    if not service_type:
        raise EngagementConflict("invalid_program", "نوع الخدمة مطلوب.", 400)
    allowed = get_practice_settings(accountant).service_types or []
    if service_type not in allowed:
        raise EngagementConflict(
            "unknown_service_type",
            "نوع الخدمة غير معرَّف في إعدادات المكتب.",
            422,
        )
    return service_type


def _parse_due_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    due_date = parse_date(str(value))
    if due_date is None:
        raise EngagementConflict("invalid_due_date", "تاريخ الاستحقاق غير صالح.", 400)
    return due_date


@transaction.atomic
def create_practice_program(*, accountant, data, today=None):
    partner = get_office_partner(accountant=accountant, partner_id=data.get("partner_id"))
    today = today or timezone.localdate()
    due_date = _parse_due_date(data.get("due_date"))
    if due_date is None:
        # غياب التاريخ ليس فراغاً: مهلة المكتب الافتراضية تملؤه فوراً.
        due_date = today + timedelta(days=get_practice_settings(accountant).default_program_due_days)
    program = PracticeProgram.objects.create(
        accountant=accountant,
        partner=partner,
        service_type=_service_type(accountant, data.get("service_type")),
        frequency=_validate_choice(
            str(data.get("frequency") or "monthly"),
            PracticeProgram.FREQUENCIES,
            "invalid_frequency",
            "دورية البرنامج غير صالحة.",
        ),
        team_note=_text(data, "team_note", 2000),
        due_date=due_date,
        status=_validate_choice(
            str(data.get("status") or "planned"),
            PracticeProgram.STATUSES,
            "invalid_status",
            "حالة البرنامج غير صالحة.",
        ),
        notes=_text(data, "notes", 2000),
    )
    _log("program_created", accountant, program=program.pk, client=partner.pk)
    return program


@transaction.atomic
def update_practice_program(*, accountant, program_id, data):
    program = get_practice_program(accountant=accountant, program_id=program_id)
    if "partner_id" in data:
        program.partner = get_office_partner(accountant=accountant, partner_id=data.get("partner_id"))
    if "service_type" in data:
        program.service_type = _service_type(accountant, data.get("service_type"))
    if "frequency" in data:
        program.frequency = _validate_choice(
            str(data.get("frequency") or ""),
            PracticeProgram.FREQUENCIES,
            "invalid_frequency",
            "دورية البرنامج غير صالحة.",
        )
    if "status" in data:
        program.status = _validate_choice(
            str(data.get("status") or ""),
            PracticeProgram.STATUSES,
            "invalid_status",
            "حالة البرنامج غير صالحة.",
        )
    if "due_date" in data:
        program.due_date = _parse_due_date(data.get("due_date"))
    for field in ("team_note", "notes"):
        if field in data:
            setattr(program, field, _text(data, field, 2000))
    program.save()
    _log("program_updated", accountant, program=program.pk)
    return program


@transaction.atomic
def delete_practice_program(*, accountant, program_id):
    program = get_practice_program(accountant=accountant, program_id=program_id)
    program.delete()
    _log("program_deleted", accountant, program=program_id)


# ── المواعيد والاستحقاقات ────────────────────────────────────────────────────


def task_payload(task, today=None):
    today = today or timezone.localdate()
    due_date = timezone.localtime(task.due_at).date() if timezone.is_aware(task.due_at) else task.due_at.date()
    partner_id, partner_name = _client_ref(task)
    return {
        "id": task.pk,
        "partner_id": partner_id,
        "partner_name": partner_name,
        "title": task.title,
        "due_at": task.due_at,
        "status": task.status,
        "kind": task.kind,
        "is_overdue": _is_overdue(due_date, task.status, today),
    }


def get_practice_task(*, accountant, task_id):
    task = (
        PracticeTask.objects.filter(accountant=accountant, pk=task_id)
        .select_related("partner", "client")
        .first()
    )
    if task is None:
        raise EngagementConflict("task_not_found", "الموعد غير موجود.", 404)
    return task


def list_practice_tasks(*, accountant, partner_id=None, status=None):
    queryset = PracticeTask.objects.filter(accountant=accountant).select_related("partner", "client")
    if partner_id:
        queryset = _filter_by_client_ref(queryset, partner_id)
    if status:
        queryset = queryset.filter(status=status)
    return list(queryset.order_by("due_at", "id"))


def _parse_due_at(value):
    if value in (None, ""):
        raise EngagementConflict("invalid_due_at", "موعد التنفيذ مطلوب.", 400)
    if isinstance(value, datetime):
        due_at = value
    else:
        due_at = parse_datetime(str(value))
        if due_at is None:
            # تاريخ بلا ساعة موعدٌ صالح — أول اليوم.
            day = value if isinstance(value, date) else parse_date(str(value))
            if day is None:
                raise EngagementConflict("invalid_due_at", "موعد التنفيذ غير صالح.", 400)
            due_at = datetime(day.year, day.month, day.day)
    if timezone.is_naive(due_at):
        due_at = timezone.make_aware(due_at)
    return due_at


@transaction.atomic
def create_practice_task(*, accountant, data):
    _profile(accountant)
    partner = None
    if data.get("partner_id") not in (None, ""):
        partner = get_office_partner(accountant=accountant, partner_id=data.get("partner_id"))
    title = _text(data, "title", 200)
    if not title:
        raise EngagementConflict("invalid_task", "عنوان الموعد مطلوب.", 400)
    task = PracticeTask.objects.create(
        accountant=accountant,
        partner=partner,
        title=title,
        due_at=_parse_due_at(data.get("due_at")),
        status=_validate_choice(
            str(data.get("status") or "open"),
            PracticeTask.STATUSES,
            "invalid_status",
            "حالة الموعد غير صالحة.",
        ),
        kind=_validate_choice(
            str(data.get("kind") or "appointment"),
            PracticeTask.KINDS,
            "invalid_kind",
            "نوع الموعد غير صالح.",
        ),
    )
    _log("task_created", accountant, task=task.pk)
    return task


@transaction.atomic
def update_practice_task(*, accountant, task_id, data):
    task = get_practice_task(accountant=accountant, task_id=task_id)
    if "partner_id" in data:
        task.partner = (
            get_office_partner(accountant=accountant, partner_id=data["partner_id"])
            if data["partner_id"] not in (None, "")
            else None
        )
    if "title" in data:
        title = _text(data, "title", 200)
        if not title:
            raise EngagementConflict("invalid_task", "عنوان الموعد مطلوب.", 400)
        task.title = title
    if "due_at" in data:
        task.due_at = _parse_due_at(data.get("due_at"))
    if "status" in data:
        task.status = _validate_choice(
            str(data.get("status") or ""),
            PracticeTask.STATUSES,
            "invalid_status",
            "حالة الموعد غير صالحة.",
        )
    if "kind" in data:
        task.kind = _validate_choice(
            str(data.get("kind") or ""),
            PracticeTask.KINDS,
            "invalid_kind",
            "نوع الموعد غير صالح.",
        )
    task.save()
    _log("task_updated", accountant, task=task.pk)
    return task


@transaction.atomic
def delete_practice_task(*, accountant, task_id):
    task = get_practice_task(accountant=accountant, task_id=task_id)
    task.delete()
    _log("task_deleted", accountant, task=task_id)


# ── المستندات ────────────────────────────────────────────────────────────────


def document_payload(document):
    partner_id, _partner_name = _client_ref(document)
    return {
        "id": document.pk,
        "partner_id": partner_id,
        "program_id": document.program_id,
        "name": document.name,
        "url": document.url,
        "uploaded_at": document.uploaded_at,
    }


def list_practice_documents(*, accountant, partner_id=None, program_id=None):
    queryset = PracticeDocument.objects.filter(accountant=accountant).select_related("partner", "client")
    if partner_id:
        queryset = _filter_by_client_ref(queryset, partner_id)
    if program_id:
        queryset = queryset.filter(program_id=program_id)
    return list(queryset.order_by("-uploaded_at", "-id"))


@transaction.atomic
def create_practice_document(*, accountant, data):
    partner = get_office_partner(accountant=accountant, partner_id=data.get("partner_id"))
    program = None
    if data.get("program_id") not in (None, ""):
        program = get_practice_program(accountant=accountant, program_id=data.get("program_id"))
        if program.partner_id != partner.pk:
            raise EngagementConflict("program_not_found", "البرنامج غير موجود.", 404)
    name = _text(data, "name", 200)
    url = _text(data, "url", 500)
    if not name or not url:
        raise EngagementConflict("invalid_document", "اسم المستند ورابطه مطلوبان.", 400)
    document = PracticeDocument.objects.create(
        accountant=accountant,
        partner=partner,
        program=program,
        name=name,
        url=url,
    )
    _log("document_added", accountant, document=document.pk, client=partner.pk)
    return document


@transaction.atomic
def delete_practice_document(*, accountant, document_id):
    document = PracticeDocument.objects.filter(accountant=accountant, pk=document_id).first()
    if document is None:
        raise EngagementConflict("document_not_found", "المستند غير موجود.", 404)
    document.delete()
    _log("document_deleted", accountant, document=document_id)


# ── أجندة المكتب ─────────────────────────────────────────────────────────────


def practice_deadlines(*, accountant, today=None):
    """كل ما يستحق على المكتب في قائمة واحدة: برامج، مواعيد، ومواعيد تقديم.

    مواعيد التقديم مشتقّة من الشركات المرتبطة (`practice_overview`) لا مخزَّنة،
    فلا صفَّ يتقادم حين يعدّل الزبون إعداد مهلة التقديم عنده.
    """
    _profile(accountant)
    today = today or timezone.localdate()
    items = []

    for program in (
        PracticeProgram.objects.filter(accountant=accountant)
        .exclude(status="done")
        .select_related("partner", "client")
        .order_by("due_date", "id")
    ):
        if program.due_date is None:
            continue
        partner_id, partner_name = _client_ref(program)
        items.append({
            "kind": "program",
            "id": program.pk,
            "title": program.service_type,
            "partner_id": partner_id,
            "partner_name": partner_name,
            "tenant_id": None,
            "due_date": program.due_date,
            "status": program.status,
        })

    for task in (
        PracticeTask.objects.filter(accountant=accountant, status="open")
        .select_related("partner", "client")
        .order_by("due_at", "id")
    ):
        due_at = timezone.localtime(task.due_at) if timezone.is_aware(task.due_at) else task.due_at
        partner_id, partner_name = _client_ref(task)
        items.append({
            "kind": task.kind,
            "id": task.pk,
            "title": task.title,
            "partner_id": partner_id,
            "partner_name": partner_name,
            "tenant_id": None,
            "due_date": due_at.date(),
            "status": task.status,
        })

    for row in practice_overview(accountant=accountant, today=today)["clients"]:
        items.append({
            "kind": "filing",
            "id": None,
            "title": "تقديم إقرار ض.ق.م",
            "partner_id": None,
            "partner_name": row["company_name"],
            "tenant_id": row["tenant_id"],
            "due_date": parse_date(row["filing_due_date"]),
            "status": "planned",
        })

    for item in items:
        days_left = (item["due_date"] - today).days
        item["days_left"] = days_left
        item["is_overdue"] = days_left < 0
    items.sort(key=lambda item: (item["due_date"], item["kind"], item["id"] or 0))

    return {
        "today": today,
        "items": items,
        "totals": {
            "count": len(items),
            "overdue": sum(1 for item in items if item["is_overdue"]),
            "due_soon": sum(1 for item in items if 0 <= item["days_left"] <= DUE_SOON_DAYS),
        },
    }


# ── لوحة المكتب (ISSUE #58) ──────────────────────────────────────────────────
#
# ثلاثة عناصر لا رابع: قائمة العملاء وحالة كل دفتر، الاستحقاقات القريبة
# (`practice_deadlines`)، والأتعاب غير المحصّلة. أرصدة الصفحة كلّها بعدد
# استعلامات ثابتٍ مهما كثر العملاء — لا استعلام لكل صفّ (§الأداء).


def _dashboard_client_row(payload):
    return {
        "id": payload["id"],
        "trade_name": payload["trade_name"],
        "status": payload["status"],
        "client_type": payload["client_type"],
        "last_activity": payload["created_at"],
    }


def _office_tenant_ids(accountant):
    """الشركات التي يديرها هذا المحاسب بصفته مالك مكتبٍ لا زبوناً مُدارَ دفتره.

    `tenant__managed_by__isnull=True` يستثني دفاتر الزبائن المُدارة (ISSUE #52):
    المحاسب عضوٌ `manager` فيها أيضاً لأنه من يشغّلها، فبلا هذا الشرط تختلط
    مبيعات دفتر الزبون بأتعاب مكتبه نفسه.
    """
    from tenants.models import UserCompanyMembership

    return list(
        UserCompanyMembership.objects.filter(
            user=accountant, role="manager", tenant__managed_by__isnull=True,
        ).values_list("tenant_id", flat=True)
    )


def _unpaid_fee_invoices(accountant):
    """فواتير الأتعاب غير المحصّلة — من دفتر مكتب المحاسب نفسه، لا من دفاتر عملائه.

    استعلامان ثابتان مهما كثرت الفواتير: عضويات الإدارة، ثم فواتير البيع الآجلة
    المرحّلة بمتبقٍّ أكبر من صفر (نفس صيغة `SalesReportViewSet.aging`).
    """
    from sales.models import SalesInvoice

    tenant_ids = _office_tenant_ids(accountant)
    if not tenant_ids:
        return {"invoices": [], "total": str(Decimal("0.00"))}

    rows = (
        SalesInvoice.objects.filter(
            tenant_id__in=tenant_ids,
            status=SalesInvoice.STATUS_POSTED,
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        )
        .annotate(remaining=F("grand_total") - F("amount_paid"))
        .filter(remaining__gt=0)
        .select_related("customer")
        .order_by("invoice_date", "id")
    )
    invoices = []
    total = Decimal("0.00")
    for invoice in rows:
        total += invoice.remaining
        invoices.append({
            "invoice_id": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "tenant_id": invoice.tenant_id,
            "customer_id": invoice.customer_id,
            "customer_name": invoice.customer.name if invoice.customer_id else "",
            "invoice_date": invoice.invoice_date,
            "remaining": str(invoice.remaining),
        })
    return {"invoices": invoices, "total": str(total)}


def practice_dashboard(*, accountant, today=None):
    """لوحة المكتب: العناصر الثلاثة معاً بعدد استعلامات ثابت مهما كثر العملاء."""
    today = today or timezone.localdate()
    clients = [_dashboard_client_row(row) for row in list_office_partners(accountant=accountant)]
    return {
        "clients": clients,
        "deadlines": practice_deadlines(accountant=accountant, today=today),
        "unpaid_fees": _unpaid_fee_invoices(accountant),
    }


# ── لوحة المكتب لموظّف بلا ملف محاسب (القرار 7) ──────────────────────────────
#
# القيد الوحيد المتاح اليوم لإسناد زبونٍ لموظف هو نفسه الذي أسّسه ISSUE #52:
# عضوية `UserCompanyMembership` على **دفتر العميل المُدار نفسه** — لا حقل
# تعيين ثالث، ولا جدول إسنادٍ جديد. زبونٌ بلا دفتر مُدار (اسمٌ مجرّد، أو
# مربوطٌ بإذن `engagement` لا تشغيل) لا يملك دفتراً تُمنح عليه عضوية أصلاً،
# فيبقى مرئياً لصاحب المكتب (`accountant=`) وحده — لا سبيل لإسناده هكذا.


def _staff_assigned_client_rows(staff):
    """عملاء الدفاتر المُدارة التي هذا الموظف عضوٌ فيها — أربعة استعلامات ثابتة
    بصرف النظر عن عدد العملاء: أطرافٌ مُرحَّلة + زبائن قدامى لم يُرحَّلوا بعد
    (سقوط قراءةٍ — نفس فلسفة `list_office_partners`)."""
    from partners.models import Partner
    from tenants.models import UserCompanyMembership

    book_ids = list(
        UserCompanyMembership.objects.filter(
            user=staff, tenant__managed_by__isnull=False,
        ).values_list("tenant_id", flat=True)
    )
    if not book_ids:
        return []
    partners = list(
        Partner.objects.filter(managed_tenant_id__in=book_ids, partner_type="Customer")
        .select_related("engagement", "managed_tenant")
        .order_by("name", "id")
    )
    rows = [_dashboard_client_row(partner_client_payload(partner)) for partner in partners]

    # زبونٌ قديمٌ مُداراً دفترُه ولم يُنقل بعد — لا سبيل لمعرفة صاحب مكتبه من
    # هنا (لا `accountant=` في هذه الدالة)، فيُطابَق بدفتره المُدار مباشرةً؛
    # علامة النقل تمنع ازدواج الصفّ بعد أن يُرحَّل.
    migrated_books = {partner.managed_tenant_id for partner in partners}
    remaining_books = [book_id for book_id in book_ids if book_id not in migrated_books]
    if remaining_books:
        legacy = list(PracticeClient.objects.filter(managed_tenant_id__in=remaining_books))
        migrated_ids = _migrated_practice_client_ids([client.pk for client in legacy])
        legacy = [client for client in legacy if str(client.pk) not in migrated_ids]
        rows += [
            _dashboard_client_row(_legacy_client_payload(client))
            for client in sorted(legacy, key=lambda c: c.trade_name)
        ]
    return rows


def staff_practice_dashboard(*, staff, today=None):
    """لوحة المكتب لموظفٍ لا ملف محاسبٍ له — عملاؤه المُسنَدون فقط.

    لا استحقاقات مكتبٍ ولا أتعاباً هنا: كلاهما مملوكٌ لصاحب المكتب (`accountant=`
    على `PracticeProgram`/`PracticeTask`، أو عضوية `manager` على دفتر المكتب
    نفسه للأتعاب) لا للموظف — فتعودان فارغتين بنفس شكل استجابة صاحب المكتب كي
    لا تتفرّع الواجهة بحسب من يفتحها.
    """
    today = today or timezone.localdate()
    return {
        "clients": _staff_assigned_client_rows(staff),
        "deadlines": {
            "today": today,
            "items": [],
            "totals": {"count": 0, "overdue": 0, "due_soon": 0},
        },
        "unpaid_fees": {"invoices": [], "total": str(Decimal("0.00"))},
    }
