"""اختبارات دفتر استخدام خدمة الإدخال وربط المستندات (التذكرة 210-C).

يغطي هذا الملف قصص المستخدم ١٦-١٩ و٣٤-٣٨ و٥٦-٥٨ من مواصفة #210:
1. صيغة الوحدات (أساس + وزن السطر × الكمية الموثقة).
2. لا وحدات قبل اعتماد السوبر أدمن.
3. كتالوجٌ غائب أو بندٌ غائب لنوع المستند يمنعان الاحتساب صراحةً.
4. idempotency: رابطُ مستندٍ واحد لا يُنتج أكثر من حدثٍ استخدامٍ واحد مهما تكرّرت
   المراجعة أو أعيد الاستدعاء (شبكةٌ منقطعة/إعادة طلب).
5. إعادة العمل بسبب خطأ الموظف لا تخصم العميل ثانيةً ولا تمنح الموظف إنجازاً ثانياً.
6. إعادة العمل بمعلومات جديدة من العميل تسمح باحتساب رابطٍ جديد.
7. مستندٌ وصل عبر قناة (customer-originated) لا يمنح الموظف إنجازاً إلا بمراجعةٍ مستقلة.
8. العكس (`reverse_usage_event`) يولّد حدثاً جديداً بلا حذف ولا أرقام سالبة مجهولة.
9. الاختبار العابر (seam) عبر الـAPI الحقيقي: فاتورة متعددة البنود → رد → اعتماد →
   وحدة عميل واحدة بلا credit مضاعف للموظف.
"""
import datetime
from decimal import ROUND_HALF_UP, Decimal


def _round_units(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency, Tenant

from platform_ops.models import (
    Engagement,
    LineCountSource,
    PlatformActivityLog,
    PlatformEmployee,
    ServiceDocumentType,
    ServiceSubscription,
    ServiceUnitCatalogEntry,
    ServiceUsageEvent,
    WorkOrder,
    WorkOrderDeliverable,
    WorkOrderDocumentLink,
)
from platform_ops.services import (
    SubscriptionManagementError,
    UsageLedgerError,
    WorkOrderDocumentLinkError,
    activate_paid_subscription,
    activate_service_unit_catalog,
    activate_subscription_policy,
    create_subscription_policy_draft,
    start_service_trial,
    approve_work_order_deliverable_with_usage,
    assign_work_order,
    change_work_order_priority,
    create_service_unit_catalog_draft,
    create_work_order,
    generate_usage_events_for_deliverable,
    link_work_order_document,
    review_work_order_deliverable,
    reverse_usage_event,
    submit_work_order_deliverable,
    transition_work_order_status,
    update_service_unit_catalog_entries,
)

User = get_user_model()


class UsageLedgerTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=3001, CompanyName="شركة اختبار الوحدات")
        self.sub = ServiceSubscription.objects.create(
            tenant=self.tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="standard",
            included_quota=100,
            consumed_quota=0,
            period_start=datetime.date(2026, 9, 1),
            period_end=datetime.date(2026, 9, 30),
        )
        self.admin = User.objects.create_superuser(username="usage_admin", email="ua@platform.local", password="x")
        self.staff_user = User.objects.create_user(username="usage_agent", email="uag@platform.local", password="x")
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        Engagement.objects.create(employee=self.employee, tenant=self.tenant, status=Engagement.Status.ACTIVE)

        self.currency, _ = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        self.customer = Partner.objects.create(tenant=self.tenant, name="عميل الاختبار", partner_type="Customer")
        self.product = Product.objects.create(tenant=self.tenant, sku="TEST-SVC-1", name_ar="خدمة اختبار", is_service=True)

        self._activate_catalog()

    def _activate_catalog(self, base_units=Decimal("1.00"), per_line_weight=Decimal("0.50")):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(
            catalog=draft,
            entries=[{
                "document_type": ServiceDocumentType.SALES_INVOICE,
                "base_units": base_units,
                "per_line_weight": per_line_weight,
            }],
            actor=self.admin,
        )
        self.catalog = activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="pilot v1")

    def _make_multiline_invoice(self, line_count=3):
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"INV-{line_count}L-{timezone.now().timestamp()}",
            customer=self.customer,
            invoice_date=datetime.date(2026, 9, 5),
            currency=self.currency,
        )
        for _ in range(line_count):
            SalesInvoiceLine.objects.create(
                tenant=self.tenant, invoice=invoice, product=self.product,
                quantity=Decimal("1.0000"), unit_price=Decimal("100.0000"),
            )
        return invoice

    def _work_order(self, **kwargs):
        defaults = dict(
            tenant=self.tenant, title="أمر عمل اختبار",
            kind=WorkOrder.Kind.DATA_ENTRY, source=WorkOrder.Source.STAFF,
        )
        defaults.update(kwargs)
        wo = create_work_order(**defaults)
        return assign_work_order(work_order=wo, assignee=self.employee)

    def _advance_to_review(self, wo):
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW)
        return wo


class UnitsFormulaTest(UsageLedgerTestBase):
    def test_units_equal_base_plus_line_weight_times_documented_quantity(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=3)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=invoice.lines.count(), linked_by=self.staff_user,
        )
        deliverable = submit_work_order_deliverable(
            work_order=wo, kind=WorkOrderDeliverable.Kind.STRUCTURED_REPORT,
            submitted_by=self.staff_user, document_link_ids=[link.pk],
        )
        updated, events = approve_work_order_deliverable_with_usage(
            deliverable=deliverable, reviewed_by=self.admin,
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.units, Decimal("2.50"))  # 1.00 + 0.50*3
        self.assertTrue(event.chargeable_to_customer)
        self.assertTrue(event.creditable_to_employee)
        self.assertEqual(event.employee_id, self.employee.pk)
        self.assertEqual(event.catalog_version, self.catalog.version)
        self.assertEqual(event.line_count_snapshot, 3)

        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 3)  # int(2.50) مقرَّبةً لأقرب صحيح (ROUND_HALF_UP)

    def test_no_units_before_deliverable_is_approved(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=2)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2,
        )
        submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk], submitted_by=self.staff_user)
        self.assertEqual(ServiceUsageEvent.objects.count(), 0)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 0)


class CatalogGuardTest(TestCase):
    """لا كتالوج نشط = لا احتساب — بلا الاعتماد المسبق للكتالوج في `setUp`."""

    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=3002, CompanyName="شركة بلا كتالوج")
        self.sub = ServiceSubscription.objects.create(tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE)
        self.admin = User.objects.create_superuser(username="no_catalog_admin", email="nca@platform.local", password="x")

    def test_missing_active_catalog_blocks_unit_generation(self):
        wo = create_work_order(tenant=self.tenant, title="أمر بلا كتالوج")
        # مستندٌ حقيقيٌّ لا معرِّفٌ مُلفَّق: الربط يرصد عدد البنود من الفاتورة نفسها
        # ويرفض معرِّفاً لا وجود له (`document_not_found`) — فالحارس المُختبَر هنا
        # هو غيابُ الكتالوج لا غيابُ المستند.
        currency, _ = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        customer = Partner.objects.create(tenant=self.tenant, name="عميل بلا كتالوج", partner_type="Customer")
        product = Product.objects.create(
            tenant=self.tenant, sku="NOCAT-SVC-1", name_ar="خدمة بلا كتالوج", is_service=True,
        )
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-NOCAT-1", customer=customer,
            invoice_date=datetime.date(2026, 9, 5), currency=currency,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=product,
            quantity=Decimal("1.0000"), unit_price=Decimal("100.0000"),
        )
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=invoice.lines.count(),
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        with self.assertRaises(UsageLedgerError) as ctx:
            generate_usage_events_for_deliverable(deliverable=deliverable, reviewed_by=self.admin)
        self.assertEqual(ctx.exception.code, "service_unit_catalog_required")


class MissingCatalogEntryTest(UsageLedgerTestBase):
    def test_document_type_missing_from_active_catalog_raises_explicit_error(self):
        wo = self._work_order()
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.PURCHASE_INVOICE, document_id=99, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        with self.assertRaises(UsageLedgerError) as ctx:
            generate_usage_events_for_deliverable(deliverable=deliverable, reviewed_by=self.admin)
        self.assertEqual(ctx.exception.code, "catalog_entry_missing_for_document_type")


class LinkValidationTest(UsageLedgerTestBase):
    def test_invalid_document_type_rejected(self):
        wo = self._work_order()
        with self.assertRaises(WorkOrderDocumentLinkError) as ctx:
            link_work_order_document(work_order=wo, document_type="not_real", document_id=1)
        self.assertEqual(ctx.exception.code, "invalid_document_type")

    def test_invalid_line_count_rejected(self):
        wo = self._work_order()
        with self.assertRaises(WorkOrderDocumentLinkError) as ctx:
            link_work_order_document(
                work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=1, line_count=0,
            )
        self.assertEqual(ctx.exception.code, "invalid_line_count")

    def test_invalid_complexity_rejected(self):
        wo = self._work_order()
        with self.assertRaises(WorkOrderDocumentLinkError) as ctx:
            link_work_order_document(
                work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=1,
                complexity="extreme",
            )
        self.assertEqual(ctx.exception.code, "invalid_complexity")


class IdempotencyTest(UsageLedgerTestBase):
    def test_generating_twice_for_same_link_does_not_duplicate(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=2)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        deliverable = review_work_order_deliverable(
            deliverable=deliverable, review_status=WorkOrderDeliverable.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )
        first = generate_usage_events_for_deliverable(deliverable=deliverable, reviewed_by=self.admin)
        second = generate_usage_events_for_deliverable(deliverable=deliverable, reviewed_by=self.admin)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0].pk, second[0].pk)
        self.assertEqual(ServiceUsageEvent.objects.filter(document_link=link).count(), 1)

        self.sub.refresh_from_db()
        expected_units = int(Decimal("1.00") + Decimal("0.50") * 2)
        self.assertEqual(self.sub.consumed_quota, expected_units)

    def test_review_endpoint_second_call_is_conflict_not_double_charge(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])

        url = f"/api/platform/ops/work-orders/{wo.pk}/deliverables/{deliverable.pk}/review/"
        first = client.post(url, {"review_status": "approved"}, format="json")
        self.assertEqual(first.status_code, 200, first.content)
        second = client.post(url, {"review_status": "approved"}, format="json")
        self.assertEqual(second.status_code, 409, second.content)
        self.assertEqual(second.data["code"], "already_reviewed")

        self.assertEqual(ServiceUsageEvent.objects.filter(document_link=link).count(), 1)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 2)  # 1.00 + 0.50*1 = 1.50 -> ROUND_HALF_UP = 2


class ReworkClassificationTest(UsageLedgerTestBase):
    def test_employee_error_rework_reuses_link_no_double_charge_or_credit(self):
        wo = self._work_order(source=WorkOrder.Source.STAFF)
        invoice = self._make_multiline_invoice(line_count=3)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=3,
        )
        first_deliverable = submit_work_order_deliverable(
            work_order=wo, document_link_ids=[link.pk], submitted_by=self.staff_user,
        )
        rejected = review_work_order_deliverable(
            deliverable=first_deliverable,
            review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
            reviewed_by=self.admin,
            rejection_reason="خطأ في إدخال أسعار البنود.",
            rejection_category=WorkOrderDeliverable.RejectionCategory.EMPLOYEE_ERROR,
        )
        self.assertEqual(rejected.rejection_category, WorkOrderDeliverable.RejectionCategory.EMPLOYEE_ERROR)
        self.assertEqual(ServiceUsageEvent.objects.count(), 0)

        # إعادة التسليم بنفس رابط المستند لا رابطٍ جديد
        second_deliverable = submit_work_order_deliverable(
            work_order=wo, document_link_ids=[link.pk], submitted_by=self.staff_user,
        )
        link.refresh_from_db()
        self.assertEqual(link.deliverable_id, second_deliverable.pk)

        updated, events = approve_work_order_deliverable_with_usage(
            deliverable=second_deliverable, reviewed_by=self.admin,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(ServiceUsageEvent.objects.filter(document_link=link).count(), 1)
        self.assertTrue(events[0].chargeable_to_customer)
        self.assertTrue(events[0].creditable_to_employee)

        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, _round_units(Decimal("1.00") + Decimal("0.50") * 3))

    def test_customer_new_info_rework_allows_a_new_billable_link(self):
        wo = self._work_order(source=WorkOrder.Source.STAFF)
        invoice = self._make_multiline_invoice(line_count=2)
        first_link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2,
        )
        first_deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[first_link.pk])
        review_work_order_deliverable(
            deliverable=first_deliverable,
            review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
            reviewed_by=self.admin,
            rejection_reason="العميل زوّدنا ببيانات إضافية غيّرت الفاتورة.",
            rejection_category=WorkOrderDeliverable.RejectionCategory.CUSTOMER_NEW_INFO,
        )

        # طلبٌ جديدٌ صريح: رابطٌ جديد على نفس المستند المصحَّح (تعديلٌ جوهري باعتماد السوبر أدمن)
        second_link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2,
        )
        second_deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[second_link.pk])
        updated, events = approve_work_order_deliverable_with_usage(
            deliverable=second_deliverable, reviewed_by=self.admin,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(ServiceUsageEvent.objects.count(), 1)
        self.assertNotEqual(events[0].document_link_id, first_link.pk)
        self.assertEqual(events[0].document_link_id, second_link.pk)


class CustomerOriginatedCreditTest(UsageLedgerTestBase):
    def test_channel_sourced_data_entry_charges_customer_but_no_employee_credit(self):
        wo = self._work_order(source=WorkOrder.Source.CHANNEL, kind=WorkOrder.Kind.DATA_ENTRY)
        invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        self.assertTrue(events[0].chargeable_to_customer)
        self.assertFalse(events[0].creditable_to_employee)

    def test_channel_sourced_review_kind_credits_the_employee(self):
        wo = self._work_order(source=WorkOrder.Source.CHANNEL, kind=WorkOrder.Kind.REVIEW)
        invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        self.assertTrue(events[0].chargeable_to_customer)
        self.assertTrue(events[0].creditable_to_employee)


class ReversalTest(UsageLedgerTestBase):
    def test_reversal_creates_new_event_and_restores_quota_without_deleting_original(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=2)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice.pk, line_count=2,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        original = events[0]
        self.sub.refresh_from_db()
        after_charge = self.sub.consumed_quota
        self.assertGreater(after_charge, 0)

        reversal = reverse_usage_event(usage_event=original, reason="فاتورة أُلغيت لدى العميل.", actor=self.admin)
        self.assertEqual(reversal.event_type, ServiceUsageEvent.EventType.REVERSAL)
        self.assertEqual(reversal.reversed_event_id, original.pk)
        self.assertTrue(ServiceUsageEvent.objects.filter(pk=original.pk).exists())  # لا حذف للأصل

        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 0)

    def test_reversal_requires_reason(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        with self.assertRaises(UsageLedgerError) as ctx:
            reverse_usage_event(usage_event=events[0], reason="", actor=self.admin)
        self.assertEqual(ctx.exception.code, "reversal_reason_required")

    def test_reversal_cannot_be_applied_twice(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        reverse_usage_event(usage_event=events[0], reason="سبب أول", actor=self.admin)
        with self.assertRaises(UsageLedgerError) as ctx:
            reverse_usage_event(usage_event=events[0], reason="سبب ثانٍ", actor=self.admin)
        self.assertEqual(ctx.exception.code, "already_reversed")


class WorkOrderQueueAndTransitionApiTest(UsageLedgerTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_employee_queue_orders_by_priority_then_deadline(self):
        """الأولويةُ أوّلاً ثمّ الأجل — وكلا الشقّين قابلٌ للسقوط.

        آجالٌ متساويةٌ و`assertIn` تجعل شقَّ «ثمّ الأجل» تأكيداً لا يستطيع السقوط:
        فآجالُ الثلاثة مختلفةٌ عمداً، والترتيبُ يُؤكَّد **تسلسلاً كاملاً** بحيث
        يسقط الاختبارُ لو رُتِّب بالأولوية وحدَها أو بالأجل وحدَه.
        """
        # `deadline_at` **مشتقٌّ** من `received_at` زائدَ ساعات السياسة — لا يُمرَّر،
        # فاختلافُ الآجال يُصنع باختلاف وقت الاستلام.
        now = timezone.now()
        # عاجلٌ استُلم أوّلاً فأجلُه الأبعد: لو رُتِّب بالأجل وحدَه لجاء أخيراً لا أوّلاً.
        wo_urgent = self._work_order(
            title="عاجل", priority=WorkOrder.Priority.URGENT, received_at=now + datetime.timedelta(days=9),
        )
        # عاديّان يفترقان بالأجل وحدَه: لو رُتِّب بالأولوية وحدَها لتبادلا الموضع.
        wo_normal_late = self._work_order(
            title="عادي متأخّر", priority=WorkOrder.Priority.NORMAL, received_at=now + datetime.timedelta(days=7),
        )
        wo_normal_soon = self._work_order(
            title="عادي قريب", priority=WorkOrder.Priority.NORMAL, received_at=now + datetime.timedelta(days=2),
        )
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/platform/ops/work-orders/queue/")
        self.assertEqual(response.status_code, 200, response.content)
        ids = [row["id"] for row in response.data]
        self.assertEqual(ids, [wo_urgent.pk, wo_normal_soon.pk, wo_normal_late.pk])

    def test_transition_endpoint_optimistic_conflict_returns_current_version(self):
        wo = self._work_order()
        self.client.force_authenticate(user=self.staff_user)
        stale = wo.updated_at.isoformat()
        wo2 = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        response = self.client.post(
            f"/api/platform/ops/work-orders/{wo.pk}/transition/",
            {"target_status": "data_entry", "expected_updated_at": stale},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data["code"], "conflict_stale_version")

    def test_transition_forbidden_for_colleague_who_is_not_the_assignee(self):
        """زميلٌ مرتبطٌ بالشركة نفسها فيرى الأمر، لكنّه ليس مسؤولَه فيُرفض بـ403 — لا 404 مُبهماً."""
        wo = self._work_order()
        other_user = User.objects.create_user(username="other_agent", email="other@platform.local", password="x")
        other_employee = PlatformEmployee.objects.create(
            user=other_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        Engagement.objects.create(employee=other_employee, tenant=self.tenant, status=Engagement.Status.ACTIVE)
        self.client.force_authenticate(user=other_user)
        response = self.client.post(
            f"/api/platform/ops/work-orders/{wo.pk}/transition/", {"target_status": "screening"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_review_deliverable_forbidden_for_staff(self):
        wo = self._work_order()
        deliverable = submit_work_order_deliverable(work_order=wo, submitted_by=self.staff_user)
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            f"/api/platform/ops/work-orders/{wo.pk}/deliverables/{deliverable.pk}/review/",
            {"review_status": "approved"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_reject_without_category_is_rejected_by_api_contract(self):
        """طبقة الخدمة تسمح بترك التصنيف فارغاً توافقاً مع اختبارات #207 القديمة،
        لكنّ نقطة الكتابة الجديدة تفرضه إلزامياً — الحارسان مختلفان عمداً."""
        wo = self._work_order()
        deliverable = submit_work_order_deliverable(work_order=wo, submitted_by=self.staff_user)
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            f"/api/platform/ops/work-orders/{wo.pk}/deliverables/{deliverable.pk}/review/",
            {"review_status": "rejected", "rejection_reason": "بيانات ناقصة."},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)


class FullAcceptanceSeamApiTest(UsageLedgerTestBase):
    """السدّ (seam) الأعلى المعتمد في مواصفة #210، مبنيّاً على الـAPI الحقيقي:

    شركةٌ مؤهَّلة → موظفٌ مُسنَد → أمر عمل بفاتورة متعددة البنود → إدخال وربط →
    ردٌّ بسبب خطأ الموظف → إعادة تسليم → اعتماد → وحدة عميل واحدة بلا credit مضاعف.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_multiline_invoice_reject_then_approve_yields_one_customer_unit_no_double_employee_credit(self):
        self.client.force_authenticate(user=self.admin)

        create_resp = self.client.post(
            "/api/platform/ops/work-orders/create/",
            {
                "tenant": self.tenant.pk,
                "title": "إدخال فاتورة بيع بعدة بنود",
                "kind": "data_entry",
                "priority": "high",
                "assignee": self.employee.pk,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.content)
        wo_id = create_resp.data["id"]

        for target in ("screening", "data_entry", "review"):
            resp = self.client.post(
                f"/api/platform/ops/work-orders/{wo_id}/transition/", {"target_status": target}, format="json",
            )
            self.assertEqual(resp.status_code, 200, resp.content)

        invoice = self._make_multiline_invoice(line_count=4)

        self.client.force_authenticate(user=self.staff_user)
        link_resp = self.client.post(
            f"/api/platform/ops/work-orders/{wo_id}/link-document/",
            {
                "document_type": "sales_invoice",
                "document_id": invoice.pk,
                "line_count": invoice.lines.count(),
            },
            format="json",
        )
        self.assertEqual(link_resp.status_code, 201, link_resp.content)
        link_id = link_resp.data["id"]

        submit_resp = self.client.post(
            f"/api/platform/ops/work-orders/{wo_id}/deliverables/",
            {"kind": "structured_report", "content": "إدخال فاتورة البيع", "document_link_ids": [link_id]},
            format="json",
        )
        self.assertEqual(submit_resp.status_code, 201, submit_resp.content)
        deliverable_id = submit_resp.data["id"]

        # السوبر أدمن يردّ مرّةً بسبب خطأ الموظف
        self.client.force_authenticate(user=self.admin)
        reject_resp = self.client.post(
            f"/api/platform/ops/work-orders/{wo_id}/deliverables/{deliverable_id}/review/",
            {
                "review_status": "rejected",
                "rejection_reason": "نسي الموظف بنداً من الفاتورة.",
                "rejection_category": "employee_error",
            },
            format="json",
        )
        self.assertEqual(reject_resp.status_code, 200, reject_resp.content)
        self.assertEqual(ServiceUsageEvent.objects.count(), 0)

        # الموظف يعيد التسليم بنفس رابط المستند
        self.client.force_authenticate(user=self.staff_user)
        resubmit_resp = self.client.post(
            f"/api/platform/ops/work-orders/{wo_id}/deliverables/",
            {"kind": "structured_report", "content": "تصحيح الإدخال", "document_link_ids": [link_id]},
            format="json",
        )
        self.assertEqual(resubmit_resp.status_code, 201, resubmit_resp.content)
        second_deliverable_id = resubmit_resp.data["id"]

        # السوبر أدمن يعتمد
        self.client.force_authenticate(user=self.admin)
        approve_resp = self.client.post(
            f"/api/platform/ops/work-orders/{wo_id}/deliverables/{second_deliverable_id}/review/",
            {"review_status": "approved"},
            format="json",
        )
        self.assertEqual(approve_resp.status_code, 200, approve_resp.content)
        usage_events = approve_resp.data["usage_events"]
        self.assertEqual(len(usage_events), 1)
        self.assertTrue(usage_events[0]["chargeable_to_customer"])
        self.assertTrue(usage_events[0]["creditable_to_employee"])

        # وحدةٌ واحدةٌ فقط في كامل الدفتر لهذا الرابط رغم الرفض وإعادة التسليم
        self.assertEqual(ServiceUsageEvent.objects.filter(document_link_id=link_id).count(), 1)

        self.sub.refresh_from_db()
        expected_units = int(Decimal("1.00") + Decimal("0.50") * 4)  # 3
        self.assertEqual(self.sub.consumed_quota, expected_units)

        # إعادة نداء الاعتماد (محاكاة انقطاع شبكة) لا تُضاعف شيئاً
        retry_resp = self.client.post(
            f"/api/platform/ops/work-orders/{wo_id}/deliverables/{second_deliverable_id}/review/",
            {"review_status": "approved"},
            format="json",
        )
        self.assertEqual(retry_resp.status_code, 409)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, expected_units)


class NewWriteActionsActivityLogTest(UsageLedgerTestBase):
    """كلُّ فعلٍ كتابيٍّ جديدٍ في 210-C يترك أثراً في PlatformActivityLog بفاعلٍ محدَّد."""

    def test_link_work_order_document_logs_activity_for_linker(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=2)
        before = PlatformActivityLog.objects.filter(action=PlatformActivityLog.Action.DOCUMENT_LINKED).count()
        link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2, linked_by=self.staff_user,
        )
        after = PlatformActivityLog.objects.filter(action=PlatformActivityLog.Action.DOCUMENT_LINKED)
        self.assertEqual(after.count(), before + 1)
        self.assertEqual(after.last().employee_id, self.employee.pk)

    def test_change_work_order_priority_logs_activity_for_changer(self):
        wo = self._work_order()
        before = PlatformActivityLog.objects.filter(
            action=PlatformActivityLog.Action.WORK_ORDER_PRIORITY_CHANGED,
        ).count()
        change_work_order_priority(work_order=wo, priority=WorkOrder.Priority.URGENT, changed_by=self.staff_user)
        after = PlatformActivityLog.objects.filter(action=PlatformActivityLog.Action.WORK_ORDER_PRIORITY_CHANGED)
        self.assertEqual(after.count(), before + 1)
        self.assertEqual(after.last().details, {"from_priority": WorkOrder.Priority.NORMAL, "to_priority": "urgent"})

    def test_change_work_order_priority_without_actor_does_not_log(self):
        wo = self._work_order()
        before = PlatformActivityLog.objects.count()
        change_work_order_priority(work_order=wo, priority=WorkOrder.Priority.HIGH)
        self.assertEqual(PlatformActivityLog.objects.count(), before)


class NewChoiceColumnWidthTest(SimpleTestCase):
    """طولُ العمود مقابل أطولِ مفتاحِ رمز لكلّ حقل choices جديد في 210-C."""

    def test_every_new_choices_column_fits_its_longest_key(self):
        fields = [
            (WorkOrder, "priority"),
            (WorkOrderDeliverable, "rejection_category"),
            (WorkOrderDocumentLink, "document_type"),
            (WorkOrderDocumentLink, "complexity"),
            (WorkOrderDocumentLink, "line_count_source"),
            (ServiceUsageEvent, "event_type"),
            (ServiceUsageEvent, "source_type"),
            (ServiceUsageEvent, "line_count_source"),
            (ServiceUnitCatalogEntry, "document_type"),
        ]
        for model, name in fields:
            with self.subTest(model=model.__name__, field=name):
                field = model._meta.get_field(name)
                keys = [key for key, _ in (field.choices or [])]
                self.assertTrue(keys)
                longest = max(keys, key=len)
                self.assertGreaterEqual(field.max_length, len(longest))


class ObservedLineCountTest(UsageLedgerTestBase):
    """**اللقطةُ تُرصد لا تُصدَّق**: عددُ البنود يحدّد فاتورةَ العميل وإنجازَ الموظّف معاً."""

    def test_observed_count_overrides_a_wrong_declared_count_and_is_marked_observed(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=3)
        # الموظّف يصرّح بتسعة بنودٍ على فاتورةِ ثلاثة — الرصدُ يغلب التصريح.
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=9,
        )
        self.assertEqual(link.line_count, 3)
        self.assertEqual(link.line_count_source, LineCountSource.OBSERVED)

    def test_unobservable_document_type_stays_declared(self):
        """نوعٌ مالكُه خارج القائمة البيضاء لحارس العزل يبقى تصريحاً موسوماً."""
        wo = self._work_order()
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.PURCHASE_INVOICE,
            document_id=4242, line_count=7,
        )
        self.assertEqual(link.line_count, 7)
        self.assertEqual(link.line_count_source, LineCountSource.DECLARED)

    def test_missing_document_is_refused(self):
        wo = self._work_order()
        with self.assertRaises(WorkOrderDocumentLinkError) as ctx:
            link_work_order_document(
                work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
                document_id=987654, line_count=1,
            )
        self.assertEqual(ctx.exception.code, "document_not_found")

    def test_document_of_another_company_is_refused(self):
        """عزلُ الشركات على مرجع الاحتساب: فاتورةُ شركةٍ أخرى لا تُربط ولا تُفوتَر هنا."""
        other_tenant = Tenant.objects.create(TenantID=3099, CompanyName="شركة أخرى")
        other_customer = Partner.objects.create(
            tenant=other_tenant, name="عميل الشركة الأخرى", partner_type="Customer",
        )
        other_product = Product.objects.create(
            tenant=other_tenant, sku="OTHER-SVC-1", name_ar="خدمة أخرى", is_service=True,
        )
        foreign_invoice = SalesInvoice.objects.create(
            tenant=other_tenant, invoice_number="INV-OTHER-1", customer=other_customer,
            invoice_date=datetime.date(2026, 9, 5), currency=self.currency,
        )
        SalesInvoiceLine.objects.create(
            tenant=other_tenant, invoice=foreign_invoice, product=other_product,
            quantity=Decimal("1.0000"), unit_price=Decimal("100.0000"),
        )
        wo = self._work_order()
        with self.assertRaises(WorkOrderDocumentLinkError) as ctx:
            link_work_order_document(
                work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
                document_id=foreign_invoice.pk, line_count=1,
            )
        self.assertEqual(ctx.exception.code, "document_tenant_mismatch")

    def test_line_count_source_is_carried_onto_the_usage_event_and_its_reversal(self):
        """مصدرُ العدد يُثبَّت على الحدث كما يُثبَّت العددُ، ويُنقل مع العكس.

        بدونه يقرأ من يراجع اعتراضاً على الوحدات «مُصرَّح به» عن عددٍ رصدَه النظامُ
        بنفسه — ودفترٌ لا يُصدَّق في هذا لا يُصدَّق في غيره.
        """
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=2)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        self.assertEqual(events[0].line_count_source, LineCountSource.OBSERVED)

        reversal = reverse_usage_event(usage_event=events[0], reason="فاتورة أُلغيت.", actor=self.admin)
        self.assertEqual(reversal.line_count_source, LineCountSource.OBSERVED)


class ActivationRequiresUnitCatalogTest(TestCase):
    """**لا تُفعَّل خدمةٌ بلا كتالوج وحداتٍ سارٍ** (القصة ١٨ من #210).

    الاحتسابُ بلا صيغةٍ منشورةٍ سلفاً احتسابٌ غيرُ محدَّد: تبدأ الخدمة، وتُعتمد
    المستندات، ثمّ يُنشر كتالوجٌ لاحقاً فتُحتسب الوحداتُ بصيغةٍ لم تكن قائمةً وقت
    العمل. الحارسُ على بوّابتَي البدء كلتيهما لا على إحداهما.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=3103, CompanyName="شركة بلا كتالوج وحدات")
        self.admin = User.objects.create_superuser(
            username="gate_admin", email="gate@platform.local", password="x",
        )
        self.platform_tenant = Tenant.objects.create(TenantID=3104, CompanyName="كترا")
        self.customer = Partner.objects.create(
            tenant=self.platform_tenant, name="عميل الفوترة", partner_type="Customer",
        )
        self.fee_product = Product.objects.create(
            tenant=self.platform_tenant, sku="GATE-SVC-1", name_ar="اشتراك خدمة", is_service=True,
        )
        policy = create_subscription_policy_draft(
            billing_tenant=self.platform_tenant, fixed_fee_product=self.fee_product,
        )
        activate_subscription_policy(policy=policy, actor=self.admin, change_reason="سياسةٌ للاختبار")

    def test_trial_refuses_to_start_without_an_active_unit_catalog(self):
        with self.assertRaises(SubscriptionManagementError) as ctx:
            start_service_trial(tenant=self.tenant, actor=self.admin)
        self.assertEqual(ctx.exception.code, "service_unit_catalog_required")

    def test_paid_activation_refuses_without_an_active_unit_catalog(self):
        with self.assertRaises(SubscriptionManagementError) as ctx:
            activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer)
        self.assertEqual(ctx.exception.code, "service_unit_catalog_required")

    def test_activation_succeeds_once_a_catalog_is_published(self):
        """الحارسُ يمنع البدءَ بلا كتالوج لا أن يمنع البدءَ مطلقاً."""
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(
            catalog=draft,
            entries=[{
                "document_type": ServiceDocumentType.SALES_INVOICE,
                "base_units": Decimal("1.00"),
                "per_line_weight": Decimal("0.50"),
            }],
            actor=self.admin,
        )
        activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="كتالوجٌ أوّل")
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer)
        self.assertEqual(subscription.status, ServiceSubscription.Status.ACTIVE)


class FractionalUnitsAccumulateTest(UsageLedgerTestBase):
    """الكسورُ لا تضيع: العدّادُ يتحرّك بفرق مجموعَي الدفتر لا بتقريب كلّ حدثٍ وحدَه."""

    def setUp(self):
        super().setUp()
        # كتالوجٌ يُنتج نصفَ وحدةٍ لفاتورةِ سطرٍ واحد: أساسٌ صفر ووزنُ سطرٍ 0.50.
        self._activate_catalog(base_units=Decimal("0.00"), per_line_weight=Decimal("0.50"))

    def _charge_one_line_invoice(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        return events[0]

    def test_two_half_unit_events_consume_one_whole_unit(self):
        first = self._charge_one_line_invoice()
        self.assertEqual(first.units, Decimal("0.50"))

        self._charge_one_line_invoice()
        self.sub.refresh_from_db()
        # تقريبُ كلّ حدثٍ وحدَه كان يبتلع النصفين معاً فيبقى العدّادُ صفراً أبداً.
        self.assertEqual(self.sub.consumed_quota, 1)

    def test_reversing_everything_returns_the_counter_to_zero(self):
        """العكسُ الكامل يُرجع العدّادَ إلى الصفر تماماً — لا بقايا ولا رقمٌ عالق.

        أمّا عكسٌ **جزئيّ** فيترك العدّادَ على تقريب ما تبقّى نصفاً لأعلى: نصفُ وحدةٍ
        باقيةٌ في الدفتر تُقرَأ وحدةً كاملة (`ROUND_HALF_UP` هو اصطلاح الوحدات
        المعتمَد في 210-C، ويُفوتَر عليه مباشرةً في `_calculate_subscription_charge`).
        فالتماثلُ مضمونٌ عند تصفير الدفتر لا عند كلّ خطوةٍ منه — وهذا أثرُ اصطلاح
        التقريب نفسِه لا خللٌ في العكس.
        """
        first = self._charge_one_line_invoice()
        second = self._charge_one_line_invoice()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 1)

        # عكسُ أحدِهما يُبقي 0.50 في الدفتر ⇒ تُقرَّب نصفاً لأعلى فتبقى وحدةً واحدة.
        reverse_usage_event(usage_event=second, reason="عكسُ الثاني.", actor=self.admin)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 1)

        reverse_usage_event(usage_event=first, reason="عكسُ الأول.", actor=self.admin)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 0)


class ChargedSourceIsNotCountedTwiceAcrossWorkOrdersTest(UsageLedgerTestBase):
    """§١٦٧: «المصدر الواحد لا يُحتسب مرتين حتى مع إعادة الطلب» — **لا بحصر أمر العمل**.

    منعُ التكرار كان مقصوراً على أمر العمل نفسِه، فنفسُ الفاتورة تُربط بأمر عملٍ
    ثانٍ فتُفوتَر مرّتين ويُمنح الموظّفُ إنجازين بلا سببٍ ولا اعتمادِ مدير.
    """

    def _charge(self, invoice, work_order=None):
        wo = work_order or self._work_order()
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=invoice.lines.count(),
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        return events[0]

    def test_same_invoice_under_a_second_work_order_is_refused(self):
        invoice = self._make_multiline_invoice(line_count=2)
        self._charge(invoice)
        second_wo = self._work_order(title="أمرٌ ثانٍ على نفس الفاتورة")
        with self.assertRaises(WorkOrderDocumentLinkError) as ctx:
            link_work_order_document(
                work_order=second_wo, document_type=ServiceDocumentType.SALES_INVOICE,
                document_id=invoice.pk, line_count=2,
            )
        self.assertEqual(ctx.exception.code, "document_already_charged")

    def test_another_companys_identical_document_id_is_unaffected(self):
        """الحصرُ بالشركة لا بالمنصّة: رقمُ مستندِ شركةٍ لا يقيس شركةً أخرى."""
        invoice = self._make_multiline_invoice(line_count=2)
        self._charge(invoice)
        # فاتورةٌ أخرى لنفس الشركة برقمٍ مختلف تُربط بلا عائق — الحارسُ على المصدر لا على النوع.
        other_invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=self._work_order(title="أمرٌ لفاتورةٍ أخرى"),
            document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=other_invoice.pk, line_count=1,
        )
        self.assertEqual(link.document_id, other_invoice.pk)

    def test_a_reversed_charge_frees_the_document_again(self):
        """حدثٌ عُكس لم يبقَ محتسَباً — فالمستندُ يُربط من جديدٍ بلا سببٍ مكتوب."""
        invoice = self._make_multiline_invoice(line_count=2)
        event = self._charge(invoice)
        reverse_usage_event(usage_event=event, reason="أُلغيت الفاتورة لدى العميل.", actor=self.admin)
        link = link_work_order_document(
            work_order=self._work_order(title="إعادةُ إدخالٍ بعد العكس"),
            document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2,
        )
        self.assertEqual(link.recount_reason, "")


class QuotaCountsPerBillingCycleTest(UsageLedgerTestBase):
    """العدّادُ يُصفَّر كلَّ دورة، فمجموعُ الدفتر يُحصر بالدورة الجارية.

    مجموعٌ لكلّ الزمن يجعل الكسورَ تتراكم عبر الدورات فتُبتلع أحداثٌ جديدة:
    تاريخيٌّ 10.50 + نصفُ وحدة ⇒ `تقريب(11.00) − تقريب(10.50) = 0` فلا يُستهلك شيء.
    """

    def setUp(self):
        super().setUp()
        self._activate_catalog(base_units=Decimal("0.00"), per_line_weight=Decimal("0.50"))

    def _charge_half_unit(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=1)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        _, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        return events[0]

    def test_a_new_cycle_starts_counting_from_zero_not_from_history(self):
        # دورةٌ أولى: ثلاثةُ أنصافٍ ⇒ 1.50 ⇒ العدّاد 2 (نصفٌ لأعلى).
        for _ in range(3):
            self._charge_half_unit()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 2)

        # تدويرُ الدورة كما يفعل التدوير الحقيقي: تصفيرُ العدّاد وتقديمُ النافذة.
        self.sub.consumed_quota = 0
        self.sub.period_start = datetime.date(2026, 10, 1)
        self.sub.period_end = datetime.date(2026, 10, 31)
        self.sub.save(update_fields=["consumed_quota", "period_start", "period_end"])

        # نصفُ وحدةٍ في الدورة الجديدة: مجموعٌ تاريخيٌّ (1.50) كان سيبتلعها.
        self._charge_half_unit()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, 1)

    def test_reversing_a_previous_cycles_event_does_not_touch_the_current_counter(self):
        """§٢٧٠: لا إعادةَ حسابٍ رجعيّة على دورةٍ فُوترت سلفاً."""
        old_event = self._charge_half_unit()
        self.sub.consumed_quota = 0
        self.sub.period_start = datetime.date(2026, 10, 1)
        self.sub.period_end = datetime.date(2026, 10, 31)
        self.sub.save(update_fields=["consumed_quota", "period_start", "period_end"])
        self._charge_half_unit()
        self.sub.refresh_from_db()
        before = self.sub.consumed_quota

        reverse_usage_event(usage_event=old_event, reason="عكسُ حدثٍ من دورةٍ سابقة.", actor=self.admin)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.consumed_quota, before)


class RecountRequiresManagerApprovalTest(UsageLedgerTestBase):
    """مستندٌ احتُسب سلفاً لا يُعاد احتسابه بنقرةٍ عابرة (المواصفة §٤)."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _charged_work_order(self):
        wo = self._work_order()
        invoice = self._make_multiline_invoice(line_count=2)
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk])
        approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        return wo, invoice

    def test_relinking_an_already_charged_document_is_refused(self):
        wo, invoice = self._charged_work_order()
        with self.assertRaises(WorkOrderDocumentLinkError) as ctx:
            link_work_order_document(
                work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
                document_id=invoice.pk, line_count=2,
            )
        self.assertEqual(ctx.exception.code, "document_already_charged")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_written_reason_allows_the_recount_and_is_kept_on_the_row(self):
        wo, invoice = self._charged_work_order()
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE,
            document_id=invoice.pk, line_count=2, recount_reason="العميل عدّل الفاتورة بعد الاعتماد.",
        )
        self.assertEqual(link.recount_reason, "العميل عدّل الفاتورة بعد الاعتماد.")

    def test_executing_employee_cannot_grant_himself_a_recount(self):
        wo, invoice = self._charged_work_order()
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            f"/api/platform/ops/work-orders/{wo.pk}/link-document/",
            {
                "document_type": "sales_invoice",
                "document_id": invoice.pk,
                "line_count": 2,
                "recount_reason": "أعيد الاحتساب.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.data["code"], "manager_only")

    def test_operations_manager_may_grant_the_recount_through_the_api(self):
        wo, invoice = self._charged_work_order()
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            f"/api/platform/ops/work-orders/{wo.pk}/link-document/",
            {
                "document_type": "sales_invoice",
                "document_id": invoice.pk,
                "line_count": 2,
                "recount_reason": "العميل عدّل الفاتورة بعد الاعتماد.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["line_count_source"], LineCountSource.OBSERVED)
        self.assertEqual(response.data["recount_reason"], "العميل عدّل الفاتورة بعد الاعتماد.")
