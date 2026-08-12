"""THA-45 M1 — سلوك وحدة الأجهزة الحساسة: البوابة، العزل، التحقق، الحذف الناعم، التدقيق."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import ActivityLog, TenantModule
from device_registry.models import DeviceAuditLog, SensitiveDevice
from tenants.models import Tenant, UserCompanyMembership


BASE = "/api/devices/records/"

# IMEI صحيحان يجتازان Luhn على الخانات الـ15 كاملة.
IMEI_A = "490154203237518"
IMEI_B = "356938035643809"
# خانة أخيرة مبدّلة ⇒ يسقط في Luhn وهو 15 رقماً.
IMEI_LUHN_FAIL = "490154203237519"


def enable_module(tenant):
    return TenantModule.objects.create(
        tenant=tenant, module_key="sensitive_devices", enabled=True,
    )


class DeviceRegistryTestBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الأجهزة")
        self.manager = User.objects.create_user("devices-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager",
        )
        self.license = enable_module(self.tenant)
        self.client.force_authenticate(self.manager)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def payload(self, **overrides):
        data = {
            "customer_name": "أحمد خالد",
            "customer_phone": "0599-123 456",
            "model_name": "iPhone 15",
            "serial_number": "SN-0001",
            "imei": IMEI_A,
            "technical_notes": "شاشة مكسورة",
        }
        data.update(overrides)
        return data

    def create_device(self, **overrides):
        response = self.client.post(
            BASE, self.payload(**overrides), format="json", **self.headers(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response


class ModuleGateTest(DeviceRegistryTestBase):
    def test_every_endpoint_is_404_without_a_module_license(self):
        device = self.create_device().data
        self.license.delete()

        calls = [
            ("get", BASE, None),
            ("post", BASE, self.payload(imei=IMEI_B)),
            ("get", f"{BASE}{device['id']}/", None),
            ("patch", f"{BASE}{device['id']}/", {"status": "in_check"}),
            ("delete", f"{BASE}{device['id']}/", None),
            ("post", f"{BASE}{device['id']}/restore/", {}),
            ("get", f"{BASE}check_imei/?imei={IMEI_A}", None),
            ("get", f"{BASE}model_names/", None),
            ("get", f"{BASE}{device['id']}/audit/", None),
        ]
        for method, url, body in calls:
            with self.subTest(method=method, url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 404, f"{method} {url} → {response.status_code}")

    def test_licensed_company_reaches_the_list(self):
        response = self.client.get(BASE, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)


class ImeiValidationTest(DeviceRegistryTestBase):
    def test_valid_luhn_imei_is_accepted(self):
        response = self.create_device()

        self.assertEqual(response.data["imei"], IMEI_A)

    def test_short_letters_and_luhn_failure_are_field_errors(self):
        for bad in ("49015420323751", "49015420323751A", IMEI_LUHN_FAIL):
            with self.subTest(imei=bad):
                response = self.client.post(
                    BASE, self.payload(imei=bad), format="json", **self.headers(),
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("imei", response.data)

    def test_empty_imei_is_accepted_without_duplicate_noise(self):
        """IMEI اختياري: أجهزة بلا شريحة (لابتوب/ساعة) تُسجَّل بالسيريال وحده،
        وفراغان لا يُعدّان تكراراً لبعضهما."""
        first = self.client.post(
            BASE, self.payload(imei=""), format="json", **self.headers(),
        )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.data["imei"], "")

        second = self.client.post(
            BASE, self.payload(imei="", serial_number="SN-EMPTY-2"),
            format="json", **self.headers(),
        )
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(second.data["duplicate_of"], [])

    def test_phone_is_normalized_and_a_bad_phone_is_rejected(self):
        response = self.create_device()
        self.assertEqual(response.data["customer_phone"], "0599123456")

        bad = self.client.post(
            BASE, self.payload(imei=IMEI_B, customer_phone="12"), format="json", **self.headers(),
        )
        self.assertEqual(bad.status_code, 400, bad.content)
        self.assertIn("customer_phone", bad.data)


class DuplicateAlertTest(DeviceRegistryTestBase):
    def test_same_tenant_duplicate_is_flagged_but_never_blocked(self):
        first = self.create_device().data
        second = self.create_device(serial_number="SN-0002")

        self.assertEqual(second.status_code, 201)
        self.assertEqual([row["id"] for row in second.data["duplicate_of"]], [first["id"]])

        check = self.client.get(f"{BASE}check_imei/?imei={IMEI_A}", **self.headers())
        self.assertTrue(check.data["valid"])
        self.assertTrue(check.data["is_duplicate"])
        self.assertEqual(len(check.data["matches"]), 2)

    def test_soft_deleted_record_stops_being_a_duplicate(self):
        first = self.create_device().data
        self.client.delete(f"{BASE}{first['id']}/", **self.headers())

        check = self.client.get(f"{BASE}check_imei/?imei={IMEI_A}", **self.headers())

        self.assertFalse(check.data["is_duplicate"])
        self.assertEqual(check.data["matches"], [])

    def test_invalid_imei_is_never_reported_as_duplicate(self):
        check = self.client.get(f"{BASE}check_imei/?imei={IMEI_LUHN_FAIL}", **self.headers())

        self.assertFalse(check.data["valid"])
        self.assertFalse(check.data["is_duplicate"])


class TenantIsolationTest(DeviceRegistryTestBase):
    def setUp(self):
        super().setUp()
        self.other_tenant = Tenant.objects.create(CompanyName="شركة أخرى")
        self.other_user = User.objects.create_user("devices-other", password="x")
        UserCompanyMembership.objects.create(
            user=self.other_user, tenant=self.other_tenant, role="manager",
        )
        enable_module(self.other_tenant)

    def test_another_company_cannot_open_or_list_our_record(self):
        device = self.create_device().data
        self.client.force_authenticate(self.other_user)

        detail = self.client.get(f"{BASE}{device['id']}/", **self.headers(self.other_tenant))
        listing = self.client.get(BASE, **self.headers(self.other_tenant))

        self.assertEqual(detail.status_code, 404, detail.content)
        self.assertEqual(listing.data, [])

    def test_check_imei_never_sees_another_companys_rows(self):
        self.create_device()
        self.client.force_authenticate(self.other_user)

        check = self.client.get(
            f"{BASE}check_imei/?imei={IMEI_A}", **self.headers(self.other_tenant),
        )

        self.assertTrue(check.data["valid"])
        self.assertFalse(check.data["is_duplicate"])
        self.assertEqual(check.data["matches"], [])

    def test_model_names_are_scoped_to_the_active_company(self):
        self.create_device()
        self.client.force_authenticate(self.other_user)

        names = self.client.get(f"{BASE}model_names/", **self.headers(self.other_tenant))

        self.assertEqual(names.data, [])


class SoftDeleteTest(DeviceRegistryTestBase):
    def test_delete_keeps_the_row_hides_it_and_restore_brings_it_back(self):
        device = self.create_device().data

        deleted = self.client.delete(f"{BASE}{device['id']}/", **self.headers())
        self.assertEqual(deleted.status_code, 204, deleted.content)

        row = SensitiveDevice.all_objects.get(pk=device["id"])
        self.assertIsNotNone(row.deleted_at)
        self.assertEqual(row.deleted_by, self.manager)
        self.assertFalse(SensitiveDevice.objects.filter(pk=device["id"]).exists())

        self.assertEqual(self.client.get(BASE, **self.headers()).data, [])
        self.assertEqual(
            self.client.get(f"{BASE}{device['id']}/", **self.headers()).status_code, 404,
        )

        with_deleted = self.client.get(f"{BASE}?include_deleted=1", **self.headers())
        self.assertEqual([r["id"] for r in with_deleted.data], [device["id"]])
        self.assertTrue(with_deleted.data[0]["is_deleted"])

        restored = self.client.post(f"{BASE}{device['id']}/restore/", {}, format="json", **self.headers())
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertIsNone(SensitiveDevice.all_objects.get(pk=device["id"]).deleted_at)
        self.assertEqual([r["id"] for r in self.client.get(BASE, **self.headers()).data], [device["id"]])

    def test_restoring_a_live_record_is_a_400_not_a_silent_success(self):
        device = self.create_device().data

        response = self.client.post(
            f"{BASE}{device['id']}/restore/", {}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)


class SearchAndFilterTest(DeviceRegistryTestBase):
    def test_search_matches_imei_serial_customer_and_phone(self):
        self.create_device()
        self.create_device(
            imei=IMEI_B, serial_number="SN-0002", customer_name="سارة", customer_phone="0567891234",
        )

        for term, expected in (("4901542", 1), ("SN-0002", 1), ("سارة", 1), ("0599", 1), ("SN-", 2)):
            with self.subTest(term=term):
                response = self.client.get(f"{BASE}?q={term}", **self.headers())
                self.assertEqual(len(response.data), expected, response.data)

    def test_status_and_date_filters_narrow_the_list(self):
        first = self.create_device().data
        self.create_device(imei=IMEI_B, serial_number="SN-0002")
        self.client.patch(f"{BASE}{first['id']}/", {"status": "delivered"}, format="json", **self.headers())

        by_status = self.client.get(f"{BASE}?status=delivered", **self.headers())
        self.assertEqual([r["id"] for r in by_status.data], [first["id"]])

        future = self.client.get(f"{BASE}?date_from=2099-01-01", **self.headers())
        self.assertEqual(future.data, [])


class AuditTrailTest(DeviceRegistryTestBase):
    def _actions(self, device_id=None):
        rows = DeviceAuditLog.objects.filter(tenant=self.tenant)
        if device_id:
            rows = rows.filter(device_id=device_id)
        return list(rows.order_by("id").values_list("action", flat=True))

    def test_every_lifecycle_event_writes_its_own_audit_row(self):
        device = self.create_device().data
        device_id = device["id"]

        self.client.get(f"{BASE}{device_id}/", **self.headers())
        self.client.patch(
            f"{BASE}{device_id}/", {"customer_name": "أحمد خالد الشريف"},
            format="json", **self.headers(),
        )
        self.client.patch(
            f"{BASE}{device_id}/", {"status": "in_check"}, format="json", **self.headers(),
        )
        self.client.delete(f"{BASE}{device_id}/", **self.headers())
        self.client.post(f"{BASE}{device_id}/restore/", {}, format="json", **self.headers())
        self.client.get(f"{BASE}?q={IMEI_A}", **self.headers())

        self.assertEqual(
            self._actions(device_id),
            ["register", "view", "update", "update", "status", "delete", "restore"],
        )
        search_rows = DeviceAuditLog.objects.filter(tenant=self.tenant, action="search")
        self.assertEqual(search_rows.count(), 1)
        self.assertEqual(search_rows.first().details["term"], IMEI_A)
        self.assertEqual(search_rows.first().details["results"], 1)
        self.assertIsNone(search_rows.first().device_id)

    def test_update_audit_carries_the_old_to_new_field_diff(self):
        device = self.create_device().data

        self.client.patch(
            f"{BASE}{device['id']}/", {"model_name": "iPhone 16"},
            format="json", **self.headers(),
        )

        row = DeviceAuditLog.objects.get(tenant=self.tenant, action="update")
        change = row.details["changes"][0]
        self.assertEqual(change["field"], "model_name")
        self.assertEqual(change["old"], "iPhone 15")
        self.assertEqual(change["new"], "iPhone 16")

    def test_status_audit_records_from_and_to(self):
        device = self.create_device().data

        self.client.patch(
            f"{BASE}{device['id']}/", {"status": "delivered"}, format="json", **self.headers(),
        )

        row = DeviceAuditLog.objects.get(tenant=self.tenant, action="status")
        self.assertEqual(row.details, {"from": "registered", "to": "delivered"})

    def test_an_empty_search_writes_nothing(self):
        self.create_device()

        self.client.get(f"{BASE}?q=  ", **self.headers())

        self.assertEqual(DeviceAuditLog.objects.filter(action="search").count(), 0)

    def test_edit_events_mirror_to_shared_activity_but_views_and_searches_do_not(self):
        device = self.create_device().data
        self.client.get(f"{BASE}{device['id']}/", **self.headers())
        self.client.get(f"{BASE}?q={IMEI_A}", **self.headers())

        mirrored = ActivityLog.objects.filter(entity_type="sensitive_device")

        self.assertEqual(list(mirrored.values_list("action", flat=True)), ["create"])
        self.assertEqual(mirrored.first().entity_label, IMEI_A)

    def test_audit_endpoint_returns_the_devices_trail_including_after_deletion(self):
        device = self.create_device().data
        self.client.delete(f"{BASE}{device['id']}/", **self.headers())

        response = self.client.get(f"{BASE}{device['id']}/audit/", **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            sorted(row["action"] for row in response.data), ["delete", "register"],
        )


class PermissionTest(DeviceRegistryTestBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user("devices-staff", password="x")
        UserCompanyMembership.objects.create(
            user=self.staff, tenant=self.tenant, role="staff",
        )

    def test_staff_registers_and_reads_but_cannot_edit_delete_or_read_the_audit(self):
        device = self.create_device().data
        self.client.force_authenticate(self.staff)

        self.assertEqual(self.client.get(BASE, **self.headers()).status_code, 200)
        created = self.client.post(
            BASE, self.payload(imei=IMEI_B, serial_number="SN-0002"),
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)

        for method, url, body in (
            ("patch", f"{BASE}{device['id']}/", {"status": "in_check"}),
            ("delete", f"{BASE}{device['id']}/", None),
            ("post", f"{BASE}{device['id']}/restore/", {}),
            ("get", f"{BASE}{device['id']}/audit/", None),
            ("get", f"{BASE}?include_deleted=1", None),
        ):
            with self.subTest(url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 403, f"{method} {url} → {response.status_code}")

    def test_device_permission_keys_vanish_for_an_unlicensed_company(self):
        from core.access import permission_keys

        self.assertIn("devices.registry.view", permission_keys(self.tenant))

        self.license.delete()
        self.assertNotIn("devices.registry.view", permission_keys(self.tenant))
