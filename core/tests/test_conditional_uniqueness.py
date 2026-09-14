"""‏**فرادةٌ مشروطةٌ لا تفرضها MySQL — والاختبارُ على SQLite لا يراها.**

الإنتاج على MySQL، وMySQL **لا تدعم الفهارس الجزئية**: كلُّ
`UniqueConstraint(..., condition=...)` **يُتجاهَل بصمت** — الهجرةُ تنجح، وجانغو
يطلق `models.W036` تحذيراً لا خطأً، ولا يُنشأ فهرسٌ البتّة. والاختباراتُ هنا على
SQLite و**هي تدعم الفهارس الجزئية**، فالقيدُ حقيقيٌّ حيث لا يهمّ ووهميٌّ حيث
يهمّ: بوّابةٌ خضراءُ تحرس ما لا وجودَ له.

وكان في المستودع ثلاثةُ نماذجَ كذلك (أربعةُ قيود): حاضرُ اجتماع المتقدّمين
(في `platform_ops/tests/test_applicant_meetings.py` — حارسُ العزل يمنع استيرادَ
تلك الوحدة من هنا)، وجهازُ الدخول الأساسيّ، ورمزُ المستودع. صارت كلُّها قيوداً **غيرَ مشروطة** على
عمودٍ مُولَّدٍ يترجم الشرطَ إلى `NULL` — وMySQL تسمح بتكرار `NULL` في الفهرس
الفريد، فالصفوفُ الخارجةُ عن الشرط لا تتزاحم والداخلةُ فيه تُحرَس فعلاً.

**ولذلك اختباراتُ هذا الملفّ صادقةٌ على المحرّكين معاً** — بخلاف ما سبقها.
"""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from hr.models import UserDevice
from inventory.models import Warehouse
from tenants.models import Tenant


class NoModelRelaysOnAConditionMySqlIgnoresTest(TestCase):
    """‏**الحارسُ الذي يمنع عودةَ الصنف كلِّه.**

    إصلاحُ ثلاثةِ نماذجَ لا يمنع رابعاً: `UniqueConstraint(condition=…)` تبدو
    سليمةً في المراجعة، وتمرّ الهجرةُ، وتخضرّ المجموعةُ على SQLite — ولا شيء
    يقول إنّها لم تُنشأ على الإنتاج إلّا تحذيرٌ يمرّ في مخرجات أمرٍ لا يقرؤه أحد.

    ‏`CheckConstraint(condition=…)` **غيرُ معنيّةٍ بهذا**: تُنشئها MySQL وتفرضها
    فعلاً، والحارسُ يفحص الفرادةَ وحدَها.
    """

    def test_no_unique_constraint_in_the_repository_carries_a_condition(self):
        from django.apps import apps
        from django.db.models import UniqueConstraint

        violations = []
        for model in apps.get_models():
            for constraint in model._meta.constraints:
                if not isinstance(constraint, UniqueConstraint):
                    continue
                if getattr(constraint, "condition", None) is not None:
                    violations.append(
                        f"{model._meta.label}.{constraint.name}"
                    )
        self.assertEqual(
            violations,
            [],
            "فرادةٌ مشروطةٌ تتجاهلها MySQL بصمت (استعمل عموداً مُولَّداً ثمّ "
            f"فرادةً غيرَ مشروطة): {violations}",
        )


class ThePrimaryDeviceConstraintIsRealOnBothEnginesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dev_owner", password="x")
        cls.other = User.objects.create_user(username="dev_owner_b", password="x")

    def test_one_user_cannot_hold_two_primary_devices(self):
        UserDevice.objects.create(user=self.user, is_primary=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # ‏`objects.create` يمرّ بـ`save` الذي ينزّل الباقين، فالكتابةُ
                # المباشرةُ هي ما يختبر الجدولَ نفسَه.
                UserDevice.objects.bulk_create(
                    [UserDevice(user=self.user, is_primary=True, key="k-dup-1")]
                )

    def test_many_secondary_devices_for_one_user_stay_allowed(self):
        """الحالةُ المشروعة: مستخدمٌ بأجهزةٍ كثيرةٍ غيرِ أساسيّة.

        فرادةٌ غيرُ مشروطةٍ على `user` وحدَه كانت ستكسر هذا.
        """
        for _ in range(3):
            UserDevice.objects.create(user=self.user, is_primary=False)
        self.assertEqual(UserDevice.objects.filter(user=self.user).count(), 3)

    def test_two_users_each_keep_their_own_primary(self):
        UserDevice.objects.create(user=self.user, is_primary=True)
        UserDevice.objects.create(user=self.other, is_primary=True)
        self.assertEqual(UserDevice.objects.filter(is_primary=True).count(), 2)

    def test_promoting_a_device_demotes_the_previous_one(self):
        """الحراسةُ البايثونيّةُ باقيةٌ — والقيدُ ضمانٌ لا بديل.

        لولا التنزيلُ داخل `save` لصار القيدُ يرفض ترقيةً مشروعةً بدل أن يحرس.
        """
        first = UserDevice.objects.create(user=self.user, is_primary=True)
        second = UserDevice.objects.create(user=self.user)
        second.is_primary = True
        second.save(update_fields=["is_primary"])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)


class TheWarehouseCodeConstraintIsRealOnBothEnginesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(CompanyName="شركة المستودعات")
        cls.other_tenant = Tenant.objects.create(CompanyName="شركة أخرى")

    def test_one_company_cannot_hold_two_warehouses_with_the_same_code(self):
        Warehouse.objects.create(tenant=self.tenant, name="أ", code="WH1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Warehouse.objects.create(tenant=self.tenant, name="ب", code="WH1")

    def test_many_warehouses_without_a_code_stay_allowed(self):
        """الحالةُ المشروعة — والسببُ الذي وُضع الشرطُ لأجله أصلاً.

        فرادةٌ غيرُ مشروطةٍ على `code` نفسِه كانت ستمنع المستودعَ الثاني بلا رمز.
        """
        for name in ("أ", "ب", "ج"):
            Warehouse.objects.create(tenant=self.tenant, name=name, code="")
        self.assertEqual(Warehouse.objects.filter(tenant=self.tenant).count(), 3)

    def test_the_same_code_in_two_companies_stays_allowed(self):
        Warehouse.objects.create(tenant=self.tenant, name="أ", code="WH1")
        Warehouse.objects.create(tenant=self.other_tenant, name="أ", code="WH1")
        self.assertEqual(Warehouse.objects.filter(code="WH1").count(), 2)
