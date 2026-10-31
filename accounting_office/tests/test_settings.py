"""سجلّ الإعدادات والمحلّل الواحد — قلب #271.

**القاعدة:** المحلّل وحده يقرأ الإعدادات. لكل إعداد مستوياتٌ مسموحة وقيمةٌ
افتراضية (أو «لا افتراضي — يُختار»)، والقراءة بالترتيب:
**تخصيص الشغلة ← تخصيص الزبون ← قيمة المكتب ← الافتراضي**.

أولُ الإعدادات أربعة لا غير: `tax_system` · `office_size` · `rest_days` ·
`filing_method`.
"""
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting_office import settings_registry
from accounting_office.models import (
    ClientSettingOverride,
    OfficeClient,
    OfficeSettingValue,
    TaxCard,
)
from accounting_office.services import (
    clients_customized_for,
    first_run_status,
    office_setting_row,
    reset_client_setting,
    reset_office_setting,
    resolve_setting,
    resolve_setting_for_clients,
    resolve_setting_with_source,
    set_client_setting,
    set_office_setting,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency
from tenants.services import create_company

BASE = "/api/accounting-office/"
CLIENTS = f"{BASE}clients/"
SETTINGS = f"{BASE}settings/"


class SettingTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager = User.objects.create_user(username="settings_mgr", password="x")
        cls.tenant = create_company("مكتب الإعدادات", cls.manager, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def ensure_ready(self):
        """اختيارا أول تشغيل — الإنشاء مرفوضٌ قبلهما، فكل اختبارٍ ينشئ زبوناً يُكملهما."""
        for key, value in (("tax_system", "PS"), ("office_size", "solo")):
            if resolve_setting(self.tenant, key) is None:
                set_office_setting(self.tenant, key, value)

    def make_client(self, name="زبون"):
        self.ensure_ready()
        res = self.client.post(CLIENTS, {"name": name}, format="json", **self.headers())
        self.assertEqual(res.status_code, 201, res.content)
        return OfficeClient.objects.get(pk=res.data["id"])


class RegistryShapeTest(SettingTestCase):
    def test_exactly_the_four_agreed_settings_exist(self):
        self.assertEqual(
            set(settings_registry.SETTINGS_REGISTRY),
            {"tax_system", "office_size", "rest_days", "filing_method"},
        )

    def test_each_setting_declares_its_levels_and_its_default(self):
        registry = settings_registry.SETTINGS_REGISTRY

        self.assertEqual(registry["tax_system"].levels, ("office", "client"))
        self.assertTrue(registry["tax_system"].has_no_default)
        self.assertEqual(registry["tax_system"].choices, ("PS", "IL"))
        self.assertEqual(registry["tax_system"].labels, {"PS": "فلسطيني", "IL": "إسرائيلي"})

        self.assertEqual(registry["office_size"].levels, ("office",))
        self.assertTrue(registry["office_size"].has_no_default)
        self.assertEqual(registry["office_size"].choices, ("solo", "small", "large"))

        self.assertEqual(registry["rest_days"].levels, ("office", "client"))
        self.assertEqual(registry["rest_days"].kind, settings_registry.KIND_WEEKDAYS)
        self.assertEqual(registry["rest_days"].default, ["fri"])
        self.assertEqual(registry["rest_days"].label, "أيام عطلة المكتب")
        self.assertEqual(registry["rest_days"].client_label, "يوم راحة الزبون")

        self.assertEqual(registry["filing_method"].levels, ("office", "client"))
        self.assertEqual(registry["filing_method"].default, "electronic")

    def test_the_group_has_its_own_constant_not_the_level(self):
        self.assertEqual(settings_registry.GROUP_OFFICE, "office")
        self.assertIn(
            (settings_registry.GROUP_OFFICE, "المكتب"), settings_registry.SETTING_GROUPS,
        )
        self.assertEqual(
            settings_registry.SETTINGS_REGISTRY["rest_days"].group,
            settings_registry.GROUP_OFFICE,
        )

    def test_no_setting_allows_an_item_level_yet(self):
        """مستوى الشغلة مدعومٌ في المحرّك، ولا إعدادٌ يشحنه اليوم."""
        for definition in settings_registry.SETTINGS_REGISTRY.values():
            self.assertNotIn("item", definition.levels, definition.key)


class ValidatorTest(SettingTestCase):
    """الأنواع الأربعة التي يقول السجلّ إنه يدعمها — كلٌّ بمُتحقِّقه."""

    def test_choice_requires_one_of_the_declared_values(self):
        definition = settings_registry.SETTINGS_REGISTRY["tax_system"]
        self.assertEqual(settings_registry.validate_value(definition, "PS"), "PS")
        with self.assertRaises(DjangoValidationError):
            settings_registry.validate_value(definition, "JO")

    def test_boolean_is_required_for_a_boolean_setting(self):
        definition = settings_registry.SettingDefinition(
            key="probe_bool", label="مفتاح", kind=settings_registry.KIND_BOOL,
            levels=("office",), default=False,
        )
        self.assertIs(settings_registry.validate_value(definition, True), True)
        with self.assertRaises(DjangoValidationError):
            settings_registry.validate_value(definition, "true")

    def test_integer_setting_rejects_text_and_floats(self):
        definition = settings_registry.SettingDefinition(
            key="probe_int", label="مفتاح", kind=settings_registry.KIND_INTEGER,
            levels=("office",), default=0,
        )
        self.assertEqual(settings_registry.validate_value(definition, 12), 12)
        for bad in ("12", 1.5, True):
            with self.assertRaises(DjangoValidationError):
                settings_registry.validate_value(definition, bad)

    def test_weekdays_are_canonicalised_and_deduplicated_away(self):
        definition = settings_registry.SETTINGS_REGISTRY["rest_days"]
        self.assertEqual(
            settings_registry.validate_value(definition, ["sat", "fri"]),
            ["fri", "sat"],
        )
        self.assertEqual(settings_registry.validate_value(definition, []), [])
        for bad in (["funday"], "fri", ["fri", "fri"]):
            with self.assertRaises(DjangoValidationError):
                settings_registry.validate_value(definition, bad)


class DefaultChainTest(SettingTestCase):
    """الافتراضي ← قيمة المكتب ← تخصيص الزبون، لكل إعداد على مستوياته."""

    def test_rest_days_starts_at_friday_and_climbs_the_chain(self):
        self.assertEqual(resolve_setting(self.tenant, "rest_days"), ["fri"])
        self.assertEqual(
            resolve_setting_with_source(self.tenant, "rest_days"), (["fri"], "default"),
        )

        set_office_setting(self.tenant, "rest_days", ["fri", "sat"])
        self.assertEqual(resolve_setting(self.tenant, "rest_days"), ["fri", "sat"])

        client = self.make_client("زبون يعمل بالأحد")
        self.assertEqual(resolve_setting(self.tenant, "rest_days", client=client), ["fri", "sat"])

        set_client_setting(client, "rest_days", ["sun"])
        self.assertEqual(resolve_setting(self.tenant, "rest_days", client=client), ["sun"])
        self.assertEqual(
            resolve_setting_with_source(self.tenant, "rest_days", client=client),
            (["sun"], "client"),
        )
        self.assertEqual(resolve_setting(self.tenant, "rest_days"), ["fri", "sat"])

    def test_the_client_tax_system_follows_the_office_until_overridden(self):
        self.assertIsNone(resolve_setting(self.tenant, "tax_system"))
        self.assertEqual(
            resolve_setting_with_source(self.tenant, "tax_system"), (None, None),
        )

        set_office_setting(self.tenant, "tax_system", "IL")
        client = self.make_client("زبون إسرائيلي افتراضاً")
        self.assertEqual(resolve_setting(self.tenant, "tax_system", client=client), "IL")

        set_client_setting(client, "tax_system", "PS")
        self.assertEqual(resolve_setting(self.tenant, "tax_system", client=client), "PS")
        self.assertEqual(resolve_setting(self.tenant, "tax_system"), "IL")

    def test_filing_method_defaults_to_electronic(self):
        self.assertEqual(resolve_setting(self.tenant, "filing_method"), "electronic")
        set_office_setting(self.tenant, "filing_method", "manual")
        self.assertEqual(resolve_setting(self.tenant, "filing_method"), "manual")

    def test_office_size_has_no_default_and_is_chosen(self):
        self.assertIsNone(resolve_setting(self.tenant, "office_size"))
        set_office_setting(self.tenant, "office_size", "small")
        self.assertEqual(resolve_setting(self.tenant, "office_size"), "small")

    def test_resetting_the_office_value_falls_back_to_the_default(self):
        set_office_setting(self.tenant, "filing_method", "manual")
        reset_office_setting(self.tenant, "filing_method")
        self.assertEqual(resolve_setting(self.tenant, "filing_method"), "electronic")
        self.assertFalse(OfficeSettingValue.objects.filter(tenant=self.tenant).exists())

    def test_resetting_a_client_override_falls_back_to_the_office_value(self):
        client = self.make_client("زبون")
        set_office_setting(self.tenant, "filing_method", "manual")
        set_client_setting(client, "filing_method", "electronic")
        self.assertEqual(resolve_setting(self.tenant, "filing_method", client=client), "electronic")

        reset_client_setting(client, "filing_method")
        self.assertEqual(resolve_setting(self.tenant, "filing_method", client=client), "manual")
        self.assertFalse(ClientSettingOverride.objects.filter(client=client).exists())


class ResetWithoutDefaultTest(SettingTestCase):
    """«ارجع للافتراضي» لإعدادٍ بلا افتراضي يُعيد المكتب إلى أول تشغيل — فيُرفض."""

    def test_the_service_refuses_to_reset_a_setting_without_a_default(self):
        set_office_setting(self.tenant, "tax_system", "PS")
        with self.assertRaises(DjangoValidationError) as caught:
            reset_office_setting(self.tenant, "tax_system")
        self.assertIn("بلا افتراضي", str(caught.exception))
        self.assertEqual(resolve_setting(self.tenant, "tax_system"), "PS")

    def test_the_api_answers_400(self):
        set_office_setting(self.tenant, "office_size", "large")
        res = self.client.delete(f"{SETTINGS}office_size/", **self.headers())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(resolve_setting(self.tenant, "office_size"), "large")

    def test_the_row_flags_whether_a_reset_is_possible(self):
        set_office_setting(self.tenant, "tax_system", "PS")
        set_office_setting(self.tenant, "filing_method", "manual")

        self.assertFalse(office_setting_row(self.tenant, "tax_system", user=None)["can_reset"])
        self.assertTrue(office_setting_row(self.tenant, "filing_method", user=None)["can_reset"])
        self.assertFalse(office_setting_row(self.tenant, "rest_days", user=None)["can_reset"])


class LevelPermissionTest(SettingTestCase):
    def test_a_level_the_setting_does_not_allow_is_refused(self):
        client = self.make_client("زبون")
        with self.assertRaises(DjangoValidationError):
            set_client_setting(client, "office_size", "small")
        with self.assertRaises(DjangoValidationError):
            resolve_setting(self.tenant, "office_size", client=client)

    def test_a_client_override_must_belong_to_the_same_office(self):
        other_manager = User.objects.create_user(username="settings_other", password="x")
        other_tenant = create_company("مكتب آخر", other_manager, template="accounting_office")
        foreign = OfficeClient.objects.create(tenant=other_tenant, name="زبون مكتب آخر")

        with self.assertRaises(DjangoValidationError):
            set_client_setting(foreign, "tax_system", "PS", tenant=self.tenant)

    def test_an_unknown_key_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            resolve_setting(self.tenant, "nope")


class ItemLevelTest(SettingTestCase):
    """مستوى الشغلة: حقل `setting_overrides` على أيّ كائنٍ يُمرَّر.

    لا إعدادٌ يشحن هذا المستوى في #271 — فالسجلّ يُوسَّع مؤقّتاً هنا لأن
    المفحوص **المحرّك** لا الإعداد.
    """

    def setUp(self):
        super().setUp()
        self.probe = settings_registry.SettingDefinition(
            key="probe_item", label="مسبار", kind=settings_registry.KIND_CHOICE,
            choices=("a", "b"), levels=("office", "client", "item"), default="a",
        )
        settings_registry.SETTINGS_REGISTRY["probe_item"] = self.probe
        self.addCleanup(settings_registry.SETTINGS_REGISTRY.pop, "probe_item", None)

    def _item(self, overrides):
        class _Item:
            setting_overrides = overrides

        return _Item()

    def test_the_item_override_beats_the_client_and_the_office(self):
        client = self.make_client("زبون")
        set_office_setting(self.tenant, "probe_item", "b")
        set_client_setting(client, "probe_item", "a")

        self.assertEqual(resolve_setting(self.tenant, "probe_item", client=client), "a")
        self.assertEqual(
            resolve_setting(
                self.tenant, "probe_item", client=client,
                item=self._item({"probe_item": "b"}),
            ),
            "b",
        )
        self.assertEqual(
            resolve_setting_with_source(
                self.tenant, "probe_item", client=client,
                item=self._item({"probe_item": "b"}),
            ),
            ("b", "item"),
        )

    def test_an_item_without_the_key_falls_through_to_the_client(self):
        client = self.make_client("زبون")
        set_office_setting(self.tenant, "probe_item", "b")
        self.assertEqual(
            resolve_setting(self.tenant, "probe_item", client=client, item=self._item({})),
            "b",
        )

    def test_an_invalid_item_value_is_refused_too(self):
        client = self.make_client("زبون")
        with self.assertRaises(DjangoValidationError):
            resolve_setting(
                self.tenant, "probe_item", client=client,
                item=self._item({"probe_item": "z"}),
            )

    def test_a_shipped_setting_refuses_an_item_argument(self):
        with self.assertRaises(DjangoValidationError):
            resolve_setting(self.tenant, "filing_method", item=self._item({}))


class CustomizationCountTest(SettingTestCase):
    def test_the_count_and_the_list_name_only_this_office_customisers(self):
        one = self.make_client("الأول")
        two = self.make_client("الثاني")
        self.make_client("لم يخصّص")
        set_client_setting(one, "tax_system", "IL")
        set_client_setting(two, "tax_system", "PS")

        other_manager = User.objects.create_user(username="count_other", password="x")
        other_tenant = create_company("مكتب مجاور", other_manager, template="accounting_office")
        elsewhere = OfficeClient.objects.create(tenant=other_tenant, name="زبون المكتب المجاور")
        set_client_setting(elsewhere, "tax_system", "IL")

        self.assertEqual(clients_customized_for(self.tenant, "tax_system", user=None).count(), 2)
        self.assertEqual(
            sorted(client.name for client in clients_customized_for(self.tenant, "tax_system", user=None)),
            ["الأول", "الثاني"],
        )
        self.assertEqual(
            office_setting_row(self.tenant, "tax_system", user=None)["client_customization_count"], 2,
        )
        set_client_setting(one, "filing_method", "manual")
        self.assertEqual(clients_customized_for(self.tenant, "tax_system", user=None).count(), 2)
        self.assertEqual(clients_customized_for(self.tenant, "filing_method", user=None).count(), 1)


class FirstRunTest(SettingTestCase):
    def test_the_first_run_lasts_until_the_tax_system_and_the_office_size_are_chosen(self):
        status = first_run_status(self.tenant)
        self.assertTrue(status["first_run_required"])
        self.assertEqual(status["missing_settings"], ["tax_system", "office_size"])
        self.assertNotIn("groups", status)

        set_office_setting(self.tenant, "tax_system", "PS")
        self.assertEqual(first_run_status(self.tenant)["missing_settings"], ["office_size"])

        set_office_setting(self.tenant, "office_size", "solo")
        status = first_run_status(self.tenant)
        self.assertFalse(status["first_run_required"])
        self.assertEqual(status["missing_settings"], [])


class SettingsApiTest(SettingTestCase):
    def test_the_office_registry_is_served_with_its_values_and_defaults(self):
        set_office_setting(self.tenant, "tax_system", "PS")
        # صفٌّ مباشر لا عبر الـAPI: `create_office_client` يشترط اكتمال أول تشغيل،
        # وهذا الاختبار يريد `office_size` غير مختارٍ ليرى كيف يُعرض.
        client = OfficeClient.objects.create(tenant=self.tenant, name="زبون له تخصيص")
        TaxCard.objects.create(client=client)
        set_client_setting(client, "filing_method", "manual")

        res = self.client.get(SETTINGS, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        rows = {row["key"]: row for row in res.data["settings"]}
        self.assertEqual(set(rows), {"tax_system", "office_size", "rest_days", "filing_method"})

        self.assertEqual(res.data["groups"], [{"id": "office", "label": "المكتب"}])
        self.assertEqual(rows["tax_system"]["value"], "PS")
        self.assertTrue(rows["tax_system"]["differs_from_default"])
        self.assertFalse(rows["tax_system"]["can_reset"])
        self.assertEqual(rows["office_size"]["value"], None)
        self.assertFalse(rows["office_size"]["has_default"])
        self.assertEqual(rows["rest_days"]["value"], ["fri"])
        self.assertFalse(rows["rest_days"]["differs_from_default"])
        self.assertEqual(rows["rest_days"]["label"], "أيام عطلة المكتب")
        self.assertEqual(rows["rest_days"]["client_label"], "يوم راحة الزبون")
        # النصّ المعروض يأتي من الخادم — الواجهة لا تبني تسميةً بنفسها.
        self.assertEqual(rows["rest_days"]["value_label"], "الجمعة")
        self.assertEqual(rows["tax_system"]["value_label"], "فلسطيني")
        self.assertEqual(rows["office_size"]["value_label"], "غير مختار")
        self.assertEqual(rows["filing_method"]["client_customization_count"], 1)
        self.assertTrue(res.data["first_run_required"])

    def test_the_office_value_is_set_and_reset_through_the_api(self):
        put = self.client.put(
            f"{SETTINGS}filing_method/", {"value": "manual"}, format="json", **self.headers(),
        )
        self.assertEqual(put.status_code, 200, put.content)
        self.assertEqual(put.data["value"], "manual")
        self.assertTrue(put.data["can_reset"])

        reset = self.client.delete(f"{SETTINGS}filing_method/", **self.headers())
        self.assertEqual(reset.status_code, 200, reset.content)
        self.assertEqual(reset.data["value"], "electronic")

    def test_an_invalid_value_is_a_400(self):
        res = self.client.put(
            f"{SETTINGS}tax_system/", {"value": "JO"}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400)

    def test_a_level_the_key_forbids_is_a_400_on_its_own_endpoint(self):
        res = self.client.put(
            f"{SETTINGS}office_size/", {"value": "large"}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200)
        client = self.make_client("زبون")
        bad = self.client.put(
            f"{CLIENTS}{client.pk}/settings/office_size/",
            {"value": "small"}, format="json", **self.headers(),
        )
        self.assertEqual(bad.status_code, 400)

    def test_the_customising_clients_are_listed_per_key(self):
        client = self.make_client("زبون مخصَّص")
        set_client_setting(client, "tax_system", "IL")

        res = self.client.get(f"{SETTINGS}tax_system/clients/", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual([row["name"] for row in res.data], ["زبون مخصَّص"])
        self.assertEqual(res.data[0]["status_label"], "نشط")

        empty = self.client.get(f"{SETTINGS}office_size/clients/", **self.headers())
        self.assertEqual(empty.data, [])

    def test_the_client_settings_carry_the_customised_flag_and_its_source(self):
        set_office_setting(self.tenant, "tax_system", "PS")
        set_office_setting(self.tenant, "filing_method", "manual")
        client = self.make_client("زبون")
        set_client_setting(client, "tax_system", "IL")

        res = self.client.get(f"{CLIENTS}{client.pk}/settings/", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        rows = {row["key"]: row for row in res.data["settings"]}

        self.assertEqual(rows["tax_system"]["value"], "IL")
        self.assertTrue(rows["tax_system"]["is_customized"])
        self.assertEqual(rows["tax_system"]["source"], "client")

        self.assertEqual(rows["filing_method"]["value"], "manual")
        self.assertFalse(rows["filing_method"]["is_customized"])
        self.assertEqual(rows["filing_method"]["source"], "office")

        self.assertEqual(rows["rest_days"]["value"], ["fri"])
        self.assertEqual(rows["rest_days"]["source"], "default")
        # التسمية من منظور الزبون — لا تسمية المكتب.
        self.assertEqual(rows["rest_days"]["label"], "يوم راحة الزبون")
        self.assertEqual(rows["rest_days"]["value_label"], "الجمعة")
        self.assertEqual(rows["filing_method"]["label"], "طريقة التقديم")

    def test_a_client_override_is_set_and_reset_through_the_api(self):
        client = self.make_client("زبون")
        put = self.client.put(
            f"{CLIENTS}{client.pk}/settings/rest_days/",
            {"value": ["sun"]}, format="json", **self.headers(),
        )
        self.assertEqual(put.status_code, 200, put.content)
        self.assertEqual(put.data["value"], ["sun"])
        self.assertTrue(put.data["is_customized"])

        reset = self.client.delete(
            f"{CLIENTS}{client.pk}/settings/rest_days/", **self.headers(),
        )
        self.assertEqual(reset.status_code, 200, reset.content)
        self.assertEqual(reset.data["value"], ["fri"])
        self.assertFalse(reset.data["is_customized"])

    def test_the_settings_surface_is_closed_to_an_unlicensed_office(self):
        from core.models import TenantModule

        TenantModule.objects.filter(
            tenant=self.tenant, module_key="accounting_office",
        ).delete()
        invalidate_module_cache(self.tenant.pk)

        for path in (SETTINGS, f"{SETTINGS}tax_system/", f"{SETTINGS}tax_system/clients/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, **self.headers()).status_code, 404)


class TaxSystemSwitchTest(SettingTestCase):
    """تبديلُ النظام يُفرّغ ما لا معنى له في النظام الجديد — ويُبقي المشترك."""

    def _card_with(self, client, entity_type, vat):
        card = TaxCard.objects.get(client=client)
        card.entity_type = entity_type
        card.vat_classification = vat
        card.save(update_fields=["entity_type", "vat_classification", "updated_at"])
        return card

    def test_a_client_switch_clears_only_the_disjoint_choices(self):
        client = self.make_client("زبون")
        self._card_with(client, "individual", "licensed")

        set_client_setting(client, "tax_system", "IL")

        card = TaxCard.objects.get(client=client)
        self.assertEqual(card.entity_type, "individual")  # مفتاحٌ مشترك — يبقى
        self.assertEqual(card.vat_classification, "")  # «مشتغل مرخّص» ليس إسرائيلياً

    def test_the_office_switch_hits_the_inheriting_clients_only(self):
        inheriting = self.make_client("يرث نظام المكتب")
        overriding = self.make_client("له نظامه")
        set_client_setting(overriding, "tax_system", "PS")
        self._card_with(inheriting, "nonprofit", "licensed")
        self._card_with(overriding, "nonprofit", "licensed")

        set_office_setting(self.tenant, "tax_system", "IL")

        inheriting_card = TaxCard.objects.get(client=inheriting)
        overriding_card = TaxCard.objects.get(client=overriding)
        self.assertEqual(inheriting_card.vat_classification, "")
        self.assertEqual(inheriting_card.entity_type, "nonprofit")
        self.assertEqual(
            overriding_card.vat_classification, "licensed",
            "زبونٌ بنظامه الخاص لم يتغيّر نظامه فلا تُمسّ بطاقته",
        )

    def test_clearing_a_client_override_returns_it_to_the_office_system_too(self):
        set_office_setting(self.tenant, "tax_system", "IL")
        client = self.make_client("زبون")
        set_client_setting(client, "tax_system", "PS")
        self._card_with(client, "company", "licensed")

        reset_client_setting(client, "tax_system")

        card = TaxCard.objects.get(client=client)
        self.assertEqual(card.vat_classification, "")
        self.assertEqual(card.entity_type, "company")  # شركة مساهمة في النظامين

class TaxSystemPropagationQueryTest(SettingTestCase):
    """تبديلُ نظام المكتب لا يكلّف استعلاماً لكل زبون — مكتبٌ بخمس مئة زبون معاملةٌ ثقيلة."""

    def _switch_with_stale_cards(self):
        """من PS إلى IL وكلُّ بطاقةٍ «مشتغل مرخّص» — فتُفرَّغ كلُّها وتمرّ بالحفظ."""
        set_office_setting(self.tenant, "tax_system", "PS")
        TaxCard.objects.filter(tenant=self.tenant).update(vat_classification="licensed")
        with CaptureQueriesContext(connection) as captured:
            set_office_setting(self.tenant, "tax_system", "IL")
        self.assertFalse(
            TaxCard.objects.filter(tenant=self.tenant).exclude(vat_classification="").exists(),
            "البطاقات لم تُفرَّغ — الاختبار لم يمرّ بمسار الحفظ",
        )
        return [query["sql"] for query in captured.captured_queries]

    def test_the_office_switch_costs_one_update_per_cleared_card_and_nothing_more(self):
        self.ensure_ready()
        for index in range(2):
            self.make_client(f"زبون {index}")
        small = self._switch_with_stale_cards()

        for index in range(8):
            self.make_client(f"زبون إضافي {index}")
        big = self._switch_with_stale_cards()

        def updates(queries):
            return [sql for sql in queries if sql.lstrip().upper().startswith("UPDATE")]

        self.assertEqual(
            len(big) - len(small), 8,
            "ثمانُ بطاقاتٍ إضافية = ثمانية UPDATE لا أكثر (لا SELECT لكل بطاقة): "
            f"{len(small)} ⇒ {len(big)}",
        )
        self.assertEqual(len(updates(big)) - len(updates(small)), 8)
        self.assertLessEqual(
            len(small) - len(updates(small)), 12,
            "سقفٌ مطلقٌ لما عدا الـUPDATE: قراءةٌ ثابتة لا تكبر بالزبائن — "
            f"{len(small)} استعلاماً لزبونين.",
        )


class BulkResolverGuardTest(SettingTestCase):
    def test_a_client_from_another_office_is_refused(self):
        other_manager = User.objects.create_user(username="bulk_other", password="x")
        other_tenant = create_company("مكتب مجاور ٢", other_manager, template="accounting_office")
        mine = OfficeClient.objects.create(tenant=self.tenant, name="زبوني")
        foreign = OfficeClient.objects.create(tenant=other_tenant, name="زبون غيري")

        with self.assertRaises(DjangoValidationError):
            resolve_setting_for_clients(
                self.tenant, "tax_system", [mine, foreign],
            )

    def test_the_valid_bulk_call_still_answers(self):
        first = OfficeClient.objects.create(tenant=self.tenant, name="أ")
        second = OfficeClient.objects.create(tenant=self.tenant, name="ب")
        set_office_setting(self.tenant, "tax_system", "PS")

        self.assertEqual(
            resolve_setting_for_clients(self.tenant, "tax_system", [first, second]),
            {first.pk: "PS", second.pk: "PS"},
        )


class ResetClientLevelTest(SettingTestCase):
    def test_resetting_a_client_value_at_a_forbidden_level_is_refused(self):
        client = self.make_client("زبون")
        with self.assertRaises(DjangoValidationError):
            reset_client_setting(client, "office_size")

    def test_the_api_answers_400_too(self):
        client = self.make_client("زبون")
        res = self.client.delete(
            f"{CLIENTS}{client.pk}/settings/office_size/", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)


class ResetOfficeLevelTest(SettingTestCase):
    """«ارجع للافتراضي» يفحص المستوى كما يفحصه `set_office_setting`.

    لا إعدادٌ مشحونٌ بلا مستوى مكتب، فالمسبارُ مفتاحٌ مؤقّت **له افتراضيّ** — كي
    لا يُرفض لغياب الافتراضيِّ بدل المستوى.
    """

    def test_resetting_an_office_value_at_a_forbidden_level_is_refused(self):
        probe = settings_registry.SettingDefinition(
            key="probe_client_only", label="مسبار", kind=settings_registry.KIND_CHOICE,
            choices=("a", "b"), levels=("client",), default="a",
        )
        with mock.patch.dict(settings_registry.SETTINGS_REGISTRY, {probe.key: probe}):
            with self.assertRaises(DjangoValidationError) as caught:
                reset_office_setting(self.tenant, probe.key)
        self.assertIn("level", caught.exception.message_dict)