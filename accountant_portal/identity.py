from django.conf import settings
from django.core.mail import send_mail
from django.core.signing import SignatureExpired, TimestampSigner


EMAIL_TOKEN_SALT = "accountant-portal-email-verification"


class EmailTokenError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def email_verification_required() -> bool:
    """هل يُشترط تحقق البريد قبل استعمال البوابة؟ الافتراض: لا (بلا SMTP)."""
    return bool(getattr(settings, "ACCOUNTANT_REQUIRE_EMAIL_VERIFICATION", False))


def make_email_verification_token(user):
    return TimestampSigner(salt=EMAIL_TOKEN_SALT).sign(str(user.pk))


def read_email_verification_token(token):
    from django.contrib.auth import get_user_model

    try:
        user_id = TimestampSigner(salt=EMAIL_TOKEN_SALT).unsign(
            token,
            max_age=getattr(settings, "ACCOUNTANT_EMAIL_TOKEN_MAX_AGE", 60 * 60 * 24),
        )
    except SignatureExpired as exc:
        raise EmailTokenError("token_expired") from exc
    except Exception as exc:
        raise EmailTokenError("token_invalid") from exc
    try:
        return get_user_model().objects.select_related("accountant_profile").get(pk=user_id)
    except (get_user_model().DoesNotExist, ValueError) as exc:
        raise EmailTokenError("token_invalid") from exc


def _frontend_url(path):
    base = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    return f"{base}{path}" if base else path


def send_verification_email(user):
    token = make_email_verification_token(user)
    link = _frontend_url(f"/accountant/verify-email?token={token}")
    send_mail(
        "تحقق من بريدك — بوابة المحاسب",
        f"أكمل التحقق من بريدك عبر الرابط التالي:\n{link}",
        getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost"),
        [user.email],
        fail_silently=True,
    )


def send_invitation_email(user, token, tenant):
    link = _frontend_url(f"/accountant/engagements?invite={token}")
    send_mail(
        "دعوة ارتباط محاسبي",
        f"دعتك {tenant.CompanyName} للارتباط كمحاسب قانوني خارجي:\n{link}",
        getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost"),
        [user.email],
        fail_silently=True,
    )

