"""خدمات المشاركة — إنشاء الرابط وحلّه وإبطاله وتسجيل ما يجري عليه.

كل كتابة على `DocumentShare` تمرّ من هنا. الـviews لا تلمس النموذج مباشرةً،
كي تبقى قواعد «ما هو رابط حيّ؟» و«متى تُحتسب مشاهدة؟» و«من يملك أن يقرّر؟»
في موضع واحد يُقرأ ويُختبَر.
"""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.activity import log_activity
from core.modules import module_enabled
from docshare.documents import DOC_TYPES
from docshare.models import (
    DECISION_ACCEPTED,
    DECISION_REJECTED,
    DocumentShare,
)

logger = logging.getLogger(__name__)

#: مدد الصلاحية المعروضة في نافذة المشاركة. «بلا انتهاء» ليس خياراً عمداً:
#: رابط أبدي على واتساب يُعاد توجيهه بعد سنة إلى من لم يُقصد به.
ALLOWED_EXPIRY_DAYS = (7, 30, 90)
DEFAULT_EXPIRY_DAYS = 30

#: الطول بالبايت قبل ترميز base64 — 32 بايت = 43 محرفاً و256 بت عشوائية.
TOKEN_BYTES = 32

#: زواحف المعاينة. واتساب يجلب الرابط **أثناء الكتابة قبل الإرسال**، فاحتساب
#: جلبه مشاهدةً يجعل «شوهد» تكذب على المالك: يرى «شوهدت» قبل أن يضغط إرسال.
_CRAWLER_MARKERS = (
    "facebookexternalhit", "whatsapp", "twitterbot", "slackbot",
    "telegrambot", "linkedinbot", "discordbot", "skypeuripreview",
    "embedly", "bot", "crawler", "spider", "preview",
)


class ShareNotFound(Exception):
    """لا صفّ بهذا التوكن، أو المستند خلفه لم يعد موجوداً ⇒ 404."""


class ShareGone(Exception):
    """الرابط كان موجوداً وانتهى أو أُبطِل ⇒ 410."""


class DecisionRefused(Exception):
    """قرارٌ لا يجوز الآن — مع سبب عربي يُعرض للزائر كما هو."""


def _client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return (forwarded or request.META.get("REMOTE_ADDR") or "")[:64]


def is_crawler(request) -> bool:
    agent = (request.META.get("HTTP_USER_AGENT") or "").lower()
    return any(marker in agent for marker in _CRAWLER_MARKERS)


def public_url(share: DocumentShare) -> str:
    """الرابط المنسوخ — من إعدادٍ صريح لا من ترويسة الطلب الوارد.

    `request.build_absolute_uri` يبني من `Host`، وهي ترويسة يرسلها العميل.
    الرابط هنا يُلصق في واتساب ويعيش شهراً، فأساسه يُثبَّت في الإعدادات.

    والوجهة كذلك (`DOCSHARE_PUBLIC_PATH`): القصير `/s` يلزمه سطر في nginx،
    و`/api/share` يعمل بلا لمس الخادم — فالاختيار متغيّر بيئة لا نشرُ كود.
    """
    base = str(getattr(settings, "DOCSHARE_PUBLIC_BASE_URL", "")).rstrip("/")
    path = str(getattr(settings, "DOCSHARE_PUBLIC_PATH", "/s")).rstrip("/")
    return f"{base}{path}/{share.token}"


def active_share(tenant, doc_type: str, doc_id: int):
    """أحدث رابط حيّ لهذا المستند، أو `None`."""
    now = timezone.now()
    return (
        DocumentShare.objects
        .filter(
            tenant=tenant, doc_type=doc_type, doc_id=doc_id,
            revoked_at__isnull=True, expires_at__gt=now,
        )
        .order_by("-created_at", "-id")
        .first()
    )


@transaction.atomic
def create_share(tenant, doc_type: str, doc_id: int, *, days: int = DEFAULT_EXPIRY_DAYS,
                 user=None, request=None) -> DocumentShare:
    """ينشئ رابطاً جديداً — أو يعيد الحيّ القائم بدل إغراق المستند بروابط.

    ولعرض سعر ما زال **مسودة**: يَنقله إلى «أُرسل». بدون ذلك يضغط الزبون
    «موافق» فيسقط على آلة حالات `SalesQuotation`، لأن القبول لا يجوز إلا من
    «أُرسل». وهذا هو معنى الإرسال نفسه في Odoo وZoho: مشاركةُ العرض هي إرساله.
    """
    if doc_type not in DOC_TYPES:
        raise ShareNotFound(doc_type)
    if days not in ALLOWED_EXPIRY_DAYS:
        days = DEFAULT_EXPIRY_DAYS

    document = DOC_TYPES[doc_type]["loader"](tenant.pk, doc_id)
    if document is None:
        raise ShareNotFound(f"{doc_type}#{doc_id}")

    existing = active_share(tenant, doc_type, doc_id)
    if existing is not None:
        return existing

    share = DocumentShare.objects.create(
        tenant=tenant,
        doc_type=doc_type,
        doc_id=doc_id,
        token=secrets.token_urlsafe(TOKEN_BYTES),
        expires_at=timezone.now() + timedelta(days=days),
        created_by=user if (user and user.is_authenticated) else None,
    )

    # خطافُ «ما معنى أن يُشارَك هذا النوع؟» — يعرفه النوع لا هذه الدالّة.
    # كان اسمُ عرض السعر مثبَّتاً هنا حرفياً، فكان كلُّ نوعٍ جديد يقبل قراراً
    # سيضيف فرعاً ثانياً في خدمةٍ لا شأن لها بآلات حالات المبيعات.
    on_share = DOC_TYPES[doc_type].get("on_share")
    if on_share is not None:
        on_share(document)

    log_activity(
        action="create",
        entity_type="document_share",
        entity_id=share.pk,
        entity_label=f"{DOC_TYPES[doc_type]['label']} #{doc_id}",
        description="أُنشئ رابط مشاركة عام للمستند",
        metadata={"doc_type": doc_type, "doc_id": doc_id, "expiry_days": days},
        request=request,
        tenant=tenant,
        user=user,
    )
    return share


@transaction.atomic
def revoke_share(share: DocumentShare, *, user=None, request=None) -> DocumentShare:
    """يُبطل الرابط فوراً. الصفّ يبقى — من شارك ومتى سؤالٌ يُسأل لاحقاً."""
    if share.revoked_at is None:
        share.revoked_at = timezone.now()
        share.save(update_fields=["revoked_at"])
        log_activity(
            action="update",
            entity_type="document_share",
            entity_id=share.pk,
            entity_label=f"{DOC_TYPES[share.doc_type]['label']} #{share.doc_id}",
            description="أُبطل رابط المشاركة العام",
            metadata={"doc_type": share.doc_type, "doc_id": share.doc_id,
                      "event": "revoked"},
            request=request,
            tenant=share.tenant,
            user=user,
        )
    return share


def resolve_share(token: str) -> tuple[DocumentShare, object, dict]:
    """يحلّ التوكن إلى (الصفّ، المستند، الحمولة العامة).

    يرفع `ShareNotFound` (‏404) أو `ShareGone` (‏410). التمييز بينهما مقصود:
    «انتهى» رسالةٌ يفهمها الزبون ويطلب بها رابطاً جديداً، و«غير موجود» صمتٌ
    أمام من يخمّن. وهو تمييزٌ لا يكشف أكثر من أن توكناً كان موجوداً يوماً.
    """
    share = DocumentShare.objects.select_related("tenant").filter(token=token).first()
    if share is None:
        raise ShareNotFound(token)
    if not share.is_live:
        raise ShareGone(token)

    spec = DOC_TYPES.get(share.doc_type)
    if spec is None:
        raise ShareNotFound(share.doc_type)

    # وحدةٌ مرخّصة أُطفئت بعد إنشاء الرابط ⇒ **410 لا 404**: الرابط كان حيّاً
    # يوماً، والصفحة تقول للزائر أن يطلب بديلاً بدل أن تصمت. وإبقاؤه عاملاً
    # كان يعني أن وحدةً غير مشترَك بها تخدم صفحاتٍ للعالم.
    if spec.get("module") and not module_enabled(share.tenant, spec["module"]):
        raise ShareGone(f"{share.doc_type}: module off")

    document = spec["loader"](share.tenant_id, share.doc_id)
    if document is None:
        # المستند حُذف بعد المشاركة، أو تغيّر نوعه إلى ما لا يُشارَك.
        raise ShareNotFound(f"{share.doc_type}#{share.doc_id}")

    return share, document, spec["builder"](document)


def record_view(share: DocumentShare, request) -> None:
    """يُحصي مشاهدةً بشرية واحدة. لا يرمي أبداً — العرض أهمّ من العدّاد."""
    if is_crawler(request):
        return
    now = timezone.now()
    try:
        DocumentShare.objects.filter(pk=share.pk).update(
            view_count=F("view_count") + 1,
            last_viewed_at=now,
            first_viewed_at=share.first_viewed_at or now,
        )
    except Exception:
        logger.warning("[docshare] تعذّر تسجيل مشاهدة للرابط %s", share.pk, exc_info=True)


@transaction.atomic
def record_decision(token: str, decision: str, name: str, request,
                    note: str = "") -> DocumentShare:
    """يسجّل قبول المستلم أو رفضه، ويحرّك حالة المستند معه.

    القفل على صفّ المشاركة داخل معاملة: ضغطتان متتاليتان على «موافق» من
    جوالٍ بطيء طلبان متزامنان، والثاني يجب أن يرتدّ لا أن يُعيد الكتابة.

    **وأيُّ نوعٍ يقبل قراراً سؤالٌ يجيب عنه `DOC_TYPES` لا هذه الدالّة.** كان
    اسم عرض السعر مثبَّتاً هنا حرفياً وفي القالب معاً — موضعان متباعدان لحقيقةٍ
    واحدة، وأولُ نوعٍ ثانٍ يقبل قراراً كان سينسى أحدَهما.
    """
    if decision not in (DECISION_ACCEPTED, DECISION_REJECTED):
        raise DecisionRefused("قرار غير معروف.")
    name = (name or "").strip()[:120]
    if not name:
        raise DecisionRefused("الاسم مطلوب لتسجيل القرار.")
    note = (note or "").strip()[:500]

    share = (
        DocumentShare.objects
        .select_for_update()
        .select_related("tenant")
        .filter(token=token)
        .first()
    )
    if share is None:
        raise ShareNotFound(token)
    if not share.is_live:
        raise ShareGone(token)
    spec = DOC_TYPES.get(share.doc_type)
    if spec is None:
        raise ShareNotFound(share.doc_type)
    decision_spec = spec.get("decision")
    if decision_spec is None:
        raise DecisionRefused("هذا المستند لا يقبل قراراً.")
    if share.decision:
        raise DecisionRefused("تم تسجيل قرارك على هذا المستند مسبقاً.")

    document = spec["loader"](share.tenant_id, share.doc_id)
    if document is None:
        raise ShareNotFound(f"{share.doc_type}#{share.doc_id}")
    if not decision_spec["is_open"](document):
        raise DecisionRefused(decision_spec["closed_reason"](document))

    # **قواعدُ العمل ترفض أحياناً، والزائر يجب أن يقرأ لماذا.** تأكيدُ طلبيةٍ
    # بكميةٍ لا تكفي يرمي `ValidationError` من `confirm_sales_order` — بلا هذا
    # اللفّ يصعد الاستثناء إلى 500 بصفحةٍ بيضاء، فيضغط الزبون ثانيةً وثالثة ولا
    # يعرف أن السبب نفادُ المخزون. الرسالة عربيةٌ أصلاً في الخدمة، فتُمرَّر كما هي.
    try:
        decision_spec["apply"](document, decision == DECISION_ACCEPTED)
    except ValidationError as exc:
        raise DecisionRefused(" ".join(exc.messages) or "تعذّر تنفيذ القرار.") from exc

    share.decision = decision
    share.decided_at = timezone.now()
    share.decided_ip = _client_ip(request)
    share.decided_name = name
    share.decided_note = note
    share.save(update_fields=[
        "decision", "decided_at", "decided_ip", "decided_name", "decided_note",
    ])

    # `action` محصور بـ`choices` النموذج وطوله ≤20 — التفصيل يسكن في `metadata`،
    # ووضعه في `action` يُسقط القيد بصمت على MySQL بينما SQLite لا يكشفه.
    log_activity(
        action="update",
        entity_type=decision_spec["entity_type"],
        entity_id=document.pk,
        entity_label=decision_spec["entity_label"](document),
        description=(
            f"قرار المستلم من الرابط العام: "
            f"{'موافقة' if decision == DECISION_ACCEPTED else 'رفض'} — بتوقيع {name}"
            + (f" — السبب: {note}" if note else "")
        ),
        metadata={
            "source": "public_share",
            "doc_type": share.doc_type,
            "decision": decision,
            "decided_by_name": name,
            "note": note,
            "ip": share.decided_ip,
            "share_id": share.pk,
        },
        request=request,
        tenant=share.tenant,
        user=None,
    )
    return share
