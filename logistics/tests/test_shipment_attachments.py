"""مرفقات الشحنة الاختيارية: مطالبة المخلّص (التخليص) · الشحن الدولي (الشحنة) · الناقل (الإرسالية).

صورة أو PDF لكلٍّ منها في `SystemAttachment` عبر `core.mixins.DocumentAttachmentsMixin`.
تُرفق ولو كان المستند مرحّلاً (المطالبة تصل بعد الإفراج)، ولا تُقرأ ولا تُحذف عبر الشركات
ولا من مستندٍ آخر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import SystemAttachment
from logistics.models import LocalShipment, LogisticsClearance, LogisticsShipment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

PDF = "https://res.cloudinary.com/demo/raw/upload/v1/claims/broker-claim-17.pdf"
IMG = "https://res.cloudinary.com/demo/image/upload/v1/claims/freight.jpg"


class ShipmentAttachmentsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="shipatt", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة المرفقات", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-ATT", chargeable_unit="cbm")
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, currency=cls.ils)
        carrier = Partner.objects.create(tenant=cls.tenant, name="ناقل", partner_type="LocalTransporter")
        cls.local = LocalShipment.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, clearance=cls.clearance, carrier=carrier,
            amount=Decimal("100"), currency=cls.ils, exchange_rate=Decimal("1"))

        cls.other_user = User.objects.create_user(username="shipatt2", password="x")
        cls.other = create_company("شركة أخرى", cls.other_user)
        cls.other.import_enabled = True
        cls.other.save(update_fields=["import_enabled"])

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _base(self, doc):
        return {
            "clearance": f"/api/logistics/clearances/{self.clearance.pk}/attachments/",
            "shipment": f"/api/logistics/shipments/{self.shipment.pk}/attachments/",
            "local": f"/api/logistics/local-shipments/{self.local.pk}/attachments/",
        }[doc]

    def test_each_document_takes_an_image_or_pdf_and_lists_only_its_own(self):
        for doc, table in (("clearance", "logistics_clearance"),
                           ("shipment", "logistics_shipments"),
                           ("local", "logistics_local_shipments")):
            with self.subTest(doc=doc):
                res = self.client.post(self._base(doc), {"url": PDF}, format="json", **self.h)
                self.assertEqual(res.status_code, 201, res.content)
                self.assertEqual(res.data["file_type"], "PDF")
                self.assertEqual(res.data["filename"], "broker-claim-17.pdf")
                res = self.client.post(self._base(doc), {"url": IMG}, format="json", **self.h)
                self.assertEqual(res.data["file_type"], "Image")
                self.assertTrue(SystemAttachment.objects.filter(
                    tenant=self.tenant, related_table=table, file_path=IMG).exists())
                listed = self.client.get(self._base(doc), **self.h)
                self.assertEqual([r["url"] for r in listed.data], [PDF, IMG])

    def test_same_link_twice_is_one_attachment(self):
        self.client.post(self._base("clearance"), {"url": PDF}, format="json", **self.h)
        self.client.post(self._base("clearance"), {"url": PDF}, format="json", **self.h)
        self.assertEqual(len(self.client.get(self._base("clearance"), **self.h).data), 1)

    def test_posted_document_still_accepts_attachments(self):
        # الشحنة والتخليص المرحّلان لا يُعدَّلان، والمطالبة تصل بعد الإفراج.
        LogisticsShipment.objects.filter(pk=self.shipment.pk).update(freight_is_posted=True)
        LocalShipment.objects.filter(pk=self.local.pk).update(is_posted=True)
        for doc in ("shipment", "local"):
            res = self.client.post(self._base(doc), {"url": PDF}, format="json", **self.h)
            self.assertEqual(res.status_code, 201, res.content)

    def test_bad_link_is_refused(self):
        res = self.client.post(self._base("shipment"), {"url": "javascript:alert(1)"},
                               format="json", **self.h)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(SystemAttachment.objects.filter(related_table="logistics_shipments").exists())

    def test_delete_is_scoped_to_the_document(self):
        clearance_att = self.client.post(
            self._base("clearance"), {"url": PDF}, format="json", **self.h).data["id"]
        # معرّف مرفق التخليص عبر مسار الإرسالية: غير موجود، ويبقى.
        res = self.client.delete(f"{self._base('local')}{clearance_att}/", **self.h)
        self.assertEqual(res.status_code, 404)
        self.assertTrue(SystemAttachment.objects.filter(pk=clearance_att).exists())
        res = self.client.delete(f"{self._base('clearance')}{clearance_att}/", **self.h)
        self.assertEqual(res.status_code, 204)
        self.assertFalse(SystemAttachment.objects.filter(pk=clearance_att).exists())

    def test_other_company_cannot_read_add_or_delete(self):
        att = self.client.post(self._base("shipment"), {"url": PDF}, format="json", **self.h).data["id"]
        self.client.force_authenticate(user=self.other_user)
        other = {"HTTP_X_TENANT_ID": str(self.other.TenantID)}
        self.assertEqual(self.client.get(self._base("shipment"), **other).status_code, 404)
        self.assertEqual(
            self.client.post(self._base("shipment"), {"url": IMG}, format="json", **other).status_code, 404)
        self.assertEqual(self.client.delete(f"{self._base('shipment')}{att}/", **other).status_code, 404)
        self.assertEqual(SystemAttachment.objects.filter(related_table="logistics_shipments").count(), 1)
