"""الحسابُ الافتراضيّ للترحيل لا يجوز أن يكون حساباً **أباً**.

`resolve_default_account` (`sales/services/foundation.py`) كانت تطابق بادئةَ
الكود بـ`code__startswith` ثم تأخذ **الأوّل بالترتيب النصّي** — و`"41" < "4102"`
لأن الأقصر يسبق ما هو امتدادٌ له. فشركةٌ شجرتُها «مهنيّة» (فيها `41` بلا
`4101`، وتحته فروعٌ مثل `4102`) كانت تُرجِع `41` نفسَه: **حسابٌ أبٌ يُرحَّل
عليه إيرادُ كل بضاعةٍ تُباع**.

وأخطرُ من ذلك أنّ أمر الإصلاح `fix_product_revenue_account_default` كان
**يهزم نفسه** على هذه الشركات: يرى المثبَّت أباً فيصفّره، ثمّ ينادي
`resolve_product_revenue_account` فيعود بالأبِ ذاتِه ويثبّته — ويطبع أنّه
أصلحه. فتوثيقُه («بعد التشغيل يصير الحساب المثبَّت ورقةً بلا أبناء») كان
يكذب، والشركاتُ تبقى معطوبةً مهما أُعيد تشغيله.

والذمّةُ `1103` **استثناءٌ مقصود** لا سهو: هي «المدينون التجاريون»، أبُ حسابات
الزبائن، وعليها يقع ما كان «على الحساب» بلا زبونٍ بعينه. فاستبعادُ الآباء
هناك كان سيُرجع **حسابَ زبونٍ عشوائيّ** — أسوأ من الأب بكثير.
"""
import pytest

from accounting.models import Account
from sales.models import SalesSettings
from sales.services import resolve_product_revenue_account
from sales.services.foundation import (
    _fill_missing_default_accounts,
    get_or_create_sales_settings,
    resolve_default_account,
)
from tenants.models import Tenant


def _professional_revenue_tree(tenant):
    """شجرةٌ فيها `41` أبٌ بلا `4101` — الحالةُ التي كشفت العطب في الإنتاج."""
    root = Account.objects.create(
        tenant=tenant, code="4", name="الإيرادات",
        account_type="Revenue", is_active=True)
    parent = Account.objects.create(
        tenant=tenant, code="41", name="إيرادات النشاط",
        account_type="Revenue", is_active=True, parent=root)
    Account.objects.create(
        tenant=tenant, code="4102", name="إيرادات الخدمات",
        account_type="Revenue", is_active=True, parent=parent)
    return parent


@pytest.mark.django_db
def test_prefix_match_never_returns_an_account_that_has_children():
    tenant = Tenant.objects.create(CompanyName="شجرة مهنية")
    parent = _professional_revenue_tree(tenant)

    hit = resolve_default_account(
        tenant.TenantID, ["4101", "41"], "Revenue", "مبيعات",
        allow_any_of_type=False, allow_parent=False,
    )

    assert hit is None or hit.pk != parent.pk, (
        "أُعيد الحسابُ الأبُ نفسُه — ترحيلٌ صامتٌ على رأس الشجرة."
    )
    if hit is not None:
        assert not hit.children.filter(tenant_id=tenant.TenantID).exists()


@pytest.mark.django_db
def test_product_revenue_creates_a_leaf_instead_of_pinning_the_parent():
    """الحالةُ الحيّة: بلا `4101` يُنشأ تحت الأب الصحيح، ولا يُثبَّت الأبُ ولا
    يُخطَف حسابُ **الخدمات** `4102` (خطأٌ آخرُ بنفس الفداحة: إيرادُ البضاعة
    يقع في إيراد الخدمات)."""
    tenant = Tenant.objects.create(CompanyName="شجرة مهنية")
    parent = _professional_revenue_tree(tenant)

    account = resolve_product_revenue_account(tenant.TenantID)

    assert account.pk != parent.pk, "ثُبِّت الأبُ حسابَ إيرادِ المنتجات."
    assert account.code != "4102", "خُطف حسابُ الخدمات لإيراد البضاعة."
    assert not account.children.filter(tenant_id=tenant.TenantID).exists()
    assert account.account_type == "Revenue"


@pytest.mark.django_db
def test_running_the_fix_twice_actually_moves_off_the_parent():
    """حارسُ العطب الثاني: الأمرُ كان يصفّر ثم يعيد الحلّ فيعود بالأبِ ذاته."""
    tenant = Tenant.objects.create(CompanyName="شجرة مهنية")
    parent = _professional_revenue_tree(tenant)
    settings_obj = get_or_create_sales_settings(tenant.TenantID)
    settings_obj.default_revenue_account_product = parent
    settings_obj.save(update_fields=["default_revenue_account_product"])

    # ما يفعله الأمر بالضبط: تصفيرٌ ثم إعادةُ حلّ.
    settings_obj.default_revenue_account_product = None
    settings_obj.save(update_fields=["default_revenue_account_product"])
    resolved = resolve_product_revenue_account(tenant.TenantID)

    assert resolved.pk != parent.pk, (
        "الأمرُ يعود بالأبِ ذاته — يطبع «أُصلح» ولا يُصلح شيئاً."
    )
    settings_obj.refresh_from_db()
    assert settings_obj.default_revenue_account_product_id == resolved.pk


@pytest.mark.django_db
def test_receivable_default_stays_the_parent_of_the_customer_accounts():
    """`1103` أبٌ **عمداً** — استبعادُه يُرجع حسابَ زبونٍ بعينه لكلّ ما هو
    «على الحساب»، وهو عطبٌ أفدح من الذي نُصلحه."""
    tenant = Tenant.objects.create(CompanyName="ذمم")
    assets = Account.objects.create(
        tenant=tenant, code="11", name="الأصول المتداولة",
        account_type="Asset", is_active=True)
    ar_parent = Account.objects.create(
        tenant=tenant, code="1103", name="المدينون التجاريون",
        account_type="Asset", is_active=True, parent=assets)
    Account.objects.create(
        tenant=tenant, code="1103001", name="زبون تجريبي",
        account_type="Asset", is_active=True, parent=ar_parent)

    settings_obj = get_or_create_sales_settings(tenant.TenantID)
    settings_obj.default_ar_account = None
    settings_obj.save(update_fields=["default_ar_account"])
    _fill_missing_default_accounts(settings_obj, tenant.TenantID)

    assert settings_obj.default_ar_account_id == ar_parent.pk, (
        "ذمّةُ العملاء العامّة انزاحت إلى حساب زبونٍ بعينه."
    )


@pytest.mark.django_db
def test_a_leaf_without_the_keyword_in_its_name_is_still_resolved():
    """حارسُ ارتداد: الشجرةُ المعياريّة تسمّي `1101` **«النقدية»** لا «صندوق»،
    فاشتراطُ تطابق الاسم كان سيُفرغ حسابَ الصندوق الافتراضيّ في كلّ شركة."""
    tenant = Tenant.objects.create(CompanyName="نقدية")
    assets = Account.objects.create(
        tenant=tenant, code="11", name="الأصول المتداولة",
        account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1101", name="النقدية (Cash)",
        account_type="Asset", is_active=True, parent=assets)

    hit = resolve_default_account(
        tenant.TenantID, ["1101", "1102", "1110"], "Asset", "صندوق",
        allow_any_of_type=False, allow_parent=False,
    )

    assert hit is not None and hit.pk == cash.pk


@pytest.mark.django_db
def test_default_behaviour_is_unchanged_for_callers_that_did_not_opt_in():
    """`allow_parent` افتراضُه `True` — لا مستدعيَ قائمٌ يتغيّر سلوكُه صامتاً."""
    tenant = Tenant.objects.create(CompanyName="شجرة مهنية")
    parent = _professional_revenue_tree(tenant)

    hit = resolve_default_account(tenant.TenantID, ["41"], allow_any_of_type=False)

    assert hit is not None and hit.pk == parent.pk


@pytest.mark.django_db
def test_the_pinned_account_is_a_leaf_so_the_repair_command_is_idempotent():
    """بعد الإصلاح لا يُعاد ترشيحُ الصفّ — وهو ما كان توثيقُ الأمر يزعمه."""
    tenant = Tenant.objects.create(CompanyName="شجرة مهنية")
    _professional_revenue_tree(tenant)
    first = resolve_product_revenue_account(tenant.TenantID)

    settings_obj = SalesSettings.objects.get(tenant_id=tenant.TenantID)
    is_parent = settings_obj.default_revenue_account_product.children.filter(
        tenant_id=tenant.TenantID).exists()

    assert not is_parent
    assert resolve_product_revenue_account(tenant.TenantID).pk == first.pk
