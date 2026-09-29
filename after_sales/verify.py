"""رمز التحقق الدائم للبطاقة وما يُعرض للزبون خلفه (#237).

هذه الوحدة **لا تستورد `models`**: `WarrantyCard.verify_token` يستدعي
`new_verify_token` عند الإدراج، فأي استيرادٍ هنا يُغلق حلقة. وما يحتاج النموذج
(`resolve_scan`) يستورده داخل الدالة.

الصفحة العامة مبنيةٌ على **قائمة بيضاء** في `public_view_model`: لا يخرج منها حقلٌ
لم يُكتب فيها بالاسم، فإضافةُ حقلٍ خاصٍّ للبطاقة لاحقاً لا تسرّبه بصمت.
"""
import io
import re
import secrets

import segno
from django.conf import settings
from django.utils import timezone

# 16 بايتاً عشوائية = 128 بت = 22 محرفاً base64url بلا حشو.
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{22}")
_SCANNED_URL = re.compile(r"/api/w/([A-Za-z0-9_-]{22})/?$")

QR_ERROR_LEVEL = "m"
QR_BORDER = 4

_MASK = "••••"

TEXT_NONE = "لا يوجد"
TEXT_EXPIRED = "منتهية"
TEXT_VOIDED = "ملغاة"
TEXT_NOT_STARTED = "لم تبدأ بعد"
TEXT_LAST_DAY = "سارية — آخر يوم"


def new_verify_token() -> str:
    return secrets.token_urlsafe(16)


def mask_serial(serial: str) -> str:
    """آخر 4 خانات، وآخر خانتين إن كان الرقم 5 خانات أو أقل — ولا يُكشف رقمٌ كاملاً."""
    serial = (serial or "").strip()
    if not serial:
        return ""
    keep = 2 if len(serial) <= 5 else 4
    if len(serial) <= keep:
        keep = 0
    return _MASK + (serial[-keep:] if keep else "")


def verify_base_url() -> str:
    base = (
        getattr(settings, "WARRANTY_VERIFY_BASE_URL", "")
        or getattr(settings, "DOCSHARE_PUBLIC_BASE_URL", "")
    )
    return str(base).rstrip("/")


def verify_url(card) -> str:
    return f"{verify_base_url()}/api/w/{card.verify_token}"


def make_qr(card):
    """`make_qr` لا `make`: الأخيرة قد تختار Micro QR، و`boost_error=False` يمنع رفع M تلقائياً."""
    return segno.make_qr(verify_url(card), error=QR_ERROR_LEVEL, boost_error=False)


def qr_svg(card, size_mm: float) -> str:
    qr = make_qr(card)
    modules = qr.symbol_size(border=QR_BORDER)[0]
    out = io.BytesIO()
    qr.save(
        out, kind="svg", border=QR_BORDER, scale=size_mm / modules, unit="mm",
        xmldecl=False, nl=False,
    )
    return out.getvalue().decode("utf-8")


def resolve_scan(tenant, scanned_text):
    """يحلّ نصّاً ممسوحاً (رابط `/api/w/<token>` أو الرمز وحده) إلى بطاقة **هذه الشركة وحدها**.

    رمزُ شركةٍ أخرى وما لا يطابق النمط يعودان `None` — الأخير بلا استعلام.
    """
    text = (scanned_text or "").strip()
    if not text:
        return None
    if TOKEN_PATTERN.fullmatch(text):
        token = text
    else:
        match = _SCANNED_URL.search(re.split(r"[?#]", text, maxsplit=1)[0].rstrip())
        if match is None:
            return None
        token = match.group(1)

    from .models import WarrantyCard

    return WarrantyCard.objects.filter(tenant=tenant, verify_token=token).first()


def _days_text(days: int) -> str:
    return TEXT_LAST_DAY if days == 0 else f"سارية — متبقٍّ {days} يوماً"


def _dealer_line(card, today) -> str:
    if card.duration_months == 0 and card.end_date <= card.start_date:
        return TEXT_NONE
    status = card.status_on(today)
    if status == card.STATUS_ENDED:
        return TEXT_EXPIRED
    if status == card.STATUS_VOIDED:
        return TEXT_VOIDED
    if status == card.STATUS_EXPIRED:
        return TEXT_EXPIRED
    if card.start_date > today:
        return TEXT_NOT_STARTED
    return _days_text(card.days_remaining(today))


def _manufacturer_line(card, today) -> str:
    status = card.manufacturer_status_on(today)
    if status is None or card.manufacturer_end_date is None:
        return TEXT_NONE
    if status in (card.STATUS_ENDED, card.STATUS_EXPIRED):
        return TEXT_EXPIRED
    if card.manufacturer_start_date and card.manufacturer_start_date > today:
        return TEXT_NOT_STARTED
    return _days_text(card.manufacturer_days_remaining(today))


def _company(tenant) -> tuple[str, str]:
    tenant_settings = getattr(tenant, "settings", None)
    name = (getattr(tenant_settings, "company_name_primary", None) or tenant.CompanyName or "")
    logo = getattr(tenant_settings, "logo_url", None) or ""
    return name, logo


def _device(card) -> str:
    if card.device_name:
        return card.device_name
    if card.product_id:
        from inventory.services import product_display_name

        return product_display_name(card.product)
    return ""


def public_view_model(card, today=None) -> dict:
    """كل ما تراه الصفحة العامة — القائمة البيضاء الوحيدة."""
    today = today or timezone.localdate()
    company_name, logo_url = _company(card.tenant)
    is_invoice_card = card.quantity > 0 and not card.serial
    warrantor = card.manufacturer_warrantor if card.manufacturer_warrantor_id else None
    # #244: كفالة الإصلاح تُسمّى باسمها لا «كفالة التاجر»، ومعها رقم الأمر ونطاقها — وحدهما.
    # لا سعر ولا ملاحظات ولا نصّ شروط: القائمة البيضاء تبقى بالاسم.
    is_repair = card.is_repair
    return {
        "is_repair": is_repair,
        "repair_order_number": (
            card.origin_service_order.order_number
            if is_repair and card.origin_service_order_id else ""
        ),
        "repair_scope": card.coverage_scope if is_repair else "",
        "company_name": company_name,
        "logo_url": logo_url,
        "device": _device(card),
        "serial_masked": "" if is_invoice_card else mask_serial(card.serial),
        "invoice_line": (
            f"كفالة على الفاتورة · الكمية {card.covered_quantity}" if is_invoice_card else ""
        ),
        "ended": card.ended_on is not None,
        "dealer_text": _dealer_line(card, today),
        "manufacturer_text": _manufacturer_line(card, today),
        "warrantor_name": warrantor.name if warrantor else "",
        "warrantor_phone": warrantor.phone if warrantor else "",
    }
