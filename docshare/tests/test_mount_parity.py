"""تكافؤ التركيبين: `/s/` و`/api/share/` — كلاهما سطحٌ كامل لا نصف سطح.

**لماذا هذا الملف موجود:** كل اختبارات هذه الوحدة كانت تفتح `/s/` وحده، فمرّت
خضراء بينما نموذج القرار في القالب والتحويلُ بعده مثبَّتان على `/s/` حرفياً.
النتيجة على خادمٍ لم يُضَف إليه سطر `location /s/` في nginx: الصفحة تُعرض من
`/api/share/…` سليمةً، فيضغط الزبون «موافق» فيذهب الطلب إلى `/s/…/decision/`
الذي يسقط في `location /` فيردّ nginx **صفحة الـSPA بحالة 200** — لا خطأ ولا
تسجيل ولا أثر. عطلٌ صامت لا يكشفه لا اختبارٌ أخضر ولا فحصٌ بصري للصفحة.

القاعدة التي تحرسها هذه الاختبارات: **لا مسار مثبَّت في الصفحة**؛ كل عنوان
تولّده الصفحة يُشتقّ من التركيب الذي خُدمت منه (`docshare/views.py`
(`_mount_urls`)).
"""
import pytest
from django.test import override_settings

from docshare import services
from docshare.models import DOC_SALES_INVOICE, DOC_SALES_QUOTATION
from sales.models import SalesQuotation

pytestmark = pytest.mark.django_db

MOUNTS = ("/s", "/api/share")


@pytest.mark.parametrize("mount", MOUNTS)
def test_page_renders_on_both_mounts(client, env, invoice, mount):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    response = client.get(f"{mount}/{share.token}/")
    assert response.status_code == 200
    assert invoice.invoice_number.encode() in response.content


@pytest.mark.parametrize("mount", MOUNTS)
def test_decision_form_points_at_the_mount_that_served_it(client, env, quotation, mount):
    """النموذج يجب أن يعود إلى حيث جاء — لا إلى `/s/` دائماً."""
    share = services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)
    html = client.get(f"{mount}/{share.token}/").content.decode("utf-8")
    assert f'action="{mount}/{share.token}/decision/"' in html


@pytest.mark.parametrize("mount", MOUNTS)
def test_decision_works_and_redirects_within_the_same_mount(client, env, quotation, mount):
    share = services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)
    response = client.post(
        f"{mount}/{share.token}/decision/", {"decision": "accepted", "name": "زبون"},
    )
    assert response.status_code == 302
    assert response["Location"] == f"{mount}/{share.token}/"

    quotation.refresh_from_db()
    assert quotation.status == SalesQuotation.STATUS_ACCEPTED


@override_settings(
    DOCSHARE_PUBLIC_BASE_URL="https://ktra-pro.tech",
    DOCSHARE_PUBLIC_PATH="/api/share",
)
def test_copied_link_follows_the_configured_path(env, invoice):
    """إن رُفض سطر nginx، متغيّرُ بيئة واحد يحوّل الرابط المنسوخ — بلا نشر كود."""
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    assert services.public_url(share) == f"https://ktra-pro.tech/api/share/{share.token}"


@override_settings(
    DOCSHARE_PUBLIC_BASE_URL="https://ktra-pro.tech", DOCSHARE_PUBLIC_PATH="/s",
)
def test_default_copied_link_is_the_short_one(env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    assert services.public_url(share) == f"https://ktra-pro.tech/s/{share.token}"


def test_no_hardcoded_mount_path_in_the_template():
    """حارسٌ نصّي: عودة `/s/` إلى القالب تُعيد العطل الصامت نفسه."""
    from pathlib import Path

    template = Path("docshare/templates/docshare/share.html").read_text(encoding="utf-8")
    assert "/s/{{" not in template
    assert 'action="{{ decision_url }}"' in template
