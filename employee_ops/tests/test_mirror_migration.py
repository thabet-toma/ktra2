# -*- coding: utf-8 -*-
"""اختبارات أمر هجرة بيانات متابعة الموظفين من مرآة bridge (المواصفة #186 — المرحلة ٧).

تُبنى وثائق مرآة حقيقية في قاعدة الاختبار، ثم يُشغّل الأمر وتُقرأ الجداول
(سلوك خارجي لا دوال داخلية، سابقة accountant_portal).

تغطي:
1. مهمة كاملة بمسندَين وتسليم ببندين -> Task + TaskAssignment*2 + TaskSubmission + TaskSubmissionItem*2.
2. الترجمات الثلاث: low->LOW · approved->approved_full · ACCEPTED كما هي.
3. النسب لكل شركة على حدة: وثيقتان لشركتين مختلفتين -> كل صف في شركته.
4. ما لا يُحسم يُترك: وثيقة بلا شركة وبمستخدم له عضويتان أو لا وجود له -> لا صف يُنشأ ويظهر السبب.
5. إعادة التشغيل: تشغيل مرتين -> الأعداد نفسها، ولا استثناء، وidempotent.
6. --dry-run: التقرير يُحسب والجداول فارغة تماماً.
7. نقاط يومية فيها فئتان غير صفرية وفئة صفرية -> قيدان لا ثلاثة، بالتاريخ الصحيح.
8. users/<id>.notes -> EmployeeNote بكاتب None والوثيقة في المرآة لم تتغير.
9. --tenant: قصر التشغيل على شركة محددة.
10. عدم وجود Employee -> تسجيل employee_not_found في التقرير.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from io import StringIO

from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command
from employee_ops.management.commands.migrate_employee_ops_mirror import (
    Command as MigrateCommand,
)
from django.test import TestCase

from core.access import FIELD_STAFF_ROLE
from employee_ops.models import (
    EmployeeNote,
    PointEntry,
    Task,
    TaskAssignment,
    TaskSubmission,
    TaskSubmissionItem,
)
from hr.models import Employee
from tenants.models import Currency, Tenant, UserCompanyMembership
from tenants.services import create_company

FirestoreMirrorDoc = apps.get_model("bridge", "FirestoreMirrorDoc")


def _run_command(*args, **kwargs) -> tuple[dict, str]:
    """يشغّل الأمرَ عبر طبقةِ الأوامر ويقرأ عدّاداتِه من المثيل.

    `call_command` يقبل **مثيلَ** أمرٍ لا اسمَه فقط، فلا حاجةَ لصنفٍ يرث `str`
    ويتظاهر بأنّه `dict` كي يمرّ من `BaseCommand.execute`.
    """
    out = StringIO()
    kwargs["stdout"] = out
    command = MigrateCommand()
    call_command(command, *args, **kwargs)
    return command.stats, out.getvalue()


class MigrateEmployeeOpsMirrorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True})

        # مستخدمو ومديرو الشركتين
        cls.manager_a = User.objects.create_user(username="mgr_mirror_a", password="x")
        cls.manager_b = User.objects.create_user(username="mgr_mirror_b", password="x")

        cls.tenant_a = create_company("شركة المرآة أ", cls.manager_a)
        cls.tenant_b = create_company("شركة المرآة ب", cls.manager_b)

        # موظفو الشركة أ
        cls.staff_a1 = User.objects.create_user(username="mirror_staff_a1", password="x")
        cls.staff_a2 = User.objects.create_user(username="mirror_staff_a2", password="x")
        UserCompanyMembership.objects.create(user=cls.staff_a1, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)
        UserCompanyMembership.objects.create(user=cls.staff_a2, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)

        cls.employee_a1 = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff_a1, name="موظف أ1", code="E101", is_active=True
        )
        cls.employee_a2 = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff_a2, name="موظف أ2", code="E102", is_active=True
        )

        # موظفو الشركة ب
        cls.staff_b1 = User.objects.create_user(username="mirror_staff_b1", password="x")
        UserCompanyMembership.objects.create(user=cls.staff_b1, tenant=cls.tenant_b, role=FIELD_STAFF_ROLE)
        cls.employee_b1 = Employee.objects.create(
            tenant=cls.tenant_b, user=cls.staff_b1, name="موظف ب1", code="EB101", is_active=True
        )

        # مستخدم متعدد العضويات (في الشركتين أ و ب)
        cls.user_multi = User.objects.create_user(username="mirror_staff_multi", password="x")
        UserCompanyMembership.objects.create(user=cls.user_multi, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)
        UserCompanyMembership.objects.create(user=cls.user_multi, tenant=cls.tenant_b, role=FIELD_STAFF_ROLE)

        # مستخدم له عضوية في أ ولكن ليس له سجل Employee
        cls.user_no_emp = User.objects.create_user(username="mirror_staff_no_emp", password="x")
        UserCompanyMembership.objects.create(user=cls.user_no_emp, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)

    def test_full_task_with_two_assignees_and_two_submission_items(self):
        """1. مهمّةٌ كاملةٌ بمُسنَدَين وتسليمٍ ببندين ← Task + TaskAssignment×٢ + TaskSubmission + TaskSubmissionItem×٢ بالقيم الصحيحة."""
        doc = FirestoreMirrorDoc.objects.create(
            path="tasks/task_full_1",
            tenant=self.tenant_a,
            data={
                "title": "مهمة شراء أجهزة",
                "description": "البحث عن أفضل عروض اللابتوبات",
                "priority": "low",
                "status": "ACCEPTED",
                "dueDate": "2026-09-20",
                "targetPrice": 1200.50,
                "allowedSites": ["https://amazon.com", "https://ebay.com"],
                "extraProp": "قيمة_إضافية_للمهمة",
                "assignedTo": [str(self.staff_a1.pk), str(self.staff_a2.pk)],
                "userStatuses": {
                    str(self.staff_a1.pk): {
                        "status": "in_progress",
                        "totalWorkTime": 3600,
                        "extraStatusProp": "بيان_إضافي",
                    },
                    str(self.staff_a2.pk): {
                        "status": "submitted",
                        "totalWorkTime": 1800,
                    },
                },
                "submissions": [
                    {
                        "id": "sub_full_1",
                        "userId": self.staff_a1.pk,
                        "status": "approved",
                        "reviewerNotes": "فحص ممتاز ومطابق",
                        "reviewedBy": self.manager_a.pk,
                        "reviewedAt": "2026-09-18T14:30:00Z",
                        "items": [
                            {
                                "id": "it_1",
                                "productLink": "https://amazon.com/item1",
                                "productPrice": 550.00,
                                "notes": "جهاز ديل",
                                "attachmentUrl": "https://img.example/1.jpg",
                                "extraItemProp": "إضافي_بند",
                            },
                            {
                                "id": "it_2",
                                "productLink": "https://ebay.com/item2",
                                "productPrice": 620.00,
                                "notes": "جهاز لينوفو",
                            },
                        ],
                    }
                ],
            },
        )

        stats, output = _run_command()

        # التحقق من Task
        self.assertEqual(Task.objects.filter(tenant=self.tenant_a).count(), 1)
        task = Task.objects.get(tenant=self.tenant_a, source_path="tasks/task_full_1")
        self.assertEqual(task.title, "مهمة شراء أجهزة")
        self.assertEqual(task.description, "البحث عن أفضل عروض اللابتوبات")
        self.assertEqual(task.due_date, datetime.date(2026, 9, 20))
        self.assertEqual(task.target_price, Decimal("1200.50"))
        self.assertEqual(task.allowed_sites, ["https://amazon.com", "https://ebay.com"])
        self.assertEqual(task.extra.get("extraProp"), "قيمة_إضافية_للمهمة")

        # التحقق من TaskAssignment x 2
        assignments = TaskAssignment.objects.filter(task=task).order_by("employee_id")
        self.assertEqual(assignments.count(), 2)

        a1 = assignments.get(employee=self.employee_a1)
        self.assertEqual(a1.status, TaskAssignment.STATUS_IN_PROGRESS)
        self.assertEqual(a1.total_work_seconds, 3600)
        self.assertEqual(a1.extra.get("extraStatusProp"), "بيان_إضافي")

        a2 = assignments.get(employee=self.employee_a2)
        self.assertEqual(a2.status, TaskAssignment.STATUS_SUBMITTED)
        self.assertEqual(a2.total_work_seconds, 1800)

        # التحقق من TaskSubmission
        submissions = TaskSubmission.objects.filter(task=task)
        self.assertEqual(submissions.count(), 1)
        sub = submissions.first()
        self.assertEqual(sub.employee, self.employee_a1)
        self.assertEqual(sub.decision, TaskSubmission.DECISION_APPROVED_FULL)
        self.assertEqual(sub.reviewer, self.manager_a)
        self.assertEqual(sub.reviewer_notes, "فحص ممتاز ومطابق")

        # التحقق من TaskSubmissionItem x 2
        items = TaskSubmissionItem.objects.filter(submission=sub).order_by("id")
        self.assertEqual(items.count(), 2)
        self.assertEqual(items[0].product_link, "https://amazon.com/item1")
        self.assertEqual(items[0].product_price, Decimal("550.00"))
        self.assertEqual(items[0].notes, "جهاز ديل")
        self.assertEqual(items[0].attachment_url, "https://img.example/1.jpg")
        self.assertEqual(items[0].extra.get("extraItemProp"), "إضافي_بند")

        self.assertEqual(items[1].product_link, "https://ebay.com/item2")
        self.assertEqual(items[1].product_price, Decimal("620.00"))
        self.assertEqual(items[1].notes, "جهاز لينوفو")

    def test_three_translations_low_priority_approved_submission_and_accepted_status(self):
        """2. الترجماتُ الثلاث: low->LOW · approved->approved_full · ACCEPTED كما هي."""
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_translations",
            tenant=self.tenant_a,
            data={
                "title": "مهمة اختبار الترجمات",
                "priority": "low",
                "status": "ACCEPTED",
                "assignedTo": [self.staff_a1.pk],
                "submissions": [
                    {
                        "id": "sub_trans_1",
                        "userId": self.staff_a1.pk,
                        "status": "approved",
                    }
                ],
            },
        )

        _run_command()

        task = Task.objects.get(tenant=self.tenant_a, source_path="tasks/task_translations")
        self.assertEqual(task.priority, Task.PRIORITY_LOW, "فشل ترجمة الأولوية: low يجب أن تصبح LOW")
        self.assertEqual(task.status, Task.STATUS_ACCEPTED, "فشل استيراد الحالة: ACCEPTED يجب أن تبقى كما هي")

        sub = TaskSubmission.objects.get(task=task)
        self.assertEqual(
            sub.decision,
            TaskSubmission.DECISION_APPROVED_FULL,
            "فشل ترجمة التسليم: approved يجب أن تصبح approved_full",
        )

    def test_attribution_per_company_fails_if_all_attributed_to_first(self):
        """3. النسب لكلّ شركةٍ على حدة: وثيقتان لشركتين مختلفتين ← كلُّ صفٍّ في شركته.

        يسقط الاختبار صراحة لو نُسب الكل للشركة الأولى.
        """
        # وثيقة للشركة أ عبر مسار المستخدم
        FirestoreMirrorDoc.objects.create(
            path=f"users/{self.staff_a1.pk}",
            tenant=None,  # يُحل عبر عضوية المستخدم الفردية
            data={"notes": "ملاحظة شركة أ"},
        )
        # وثيقة للشركة ب عبر مسار المستخدم
        FirestoreMirrorDoc.objects.create(
            path=f"users/{self.staff_b1.pk}",
            tenant=None,  # يُحل عبر عضوية المستخدم الفردية
            data={"notes": "ملاحظة شركة ب"},
        )

        _run_command()

        # تحقق أن كل صف استقر في شركته تماماً
        self.assertEqual(EmployeeNote.objects.filter(tenant=self.tenant_a).count(), 1)
        self.assertEqual(EmployeeNote.objects.filter(tenant=self.tenant_b).count(), 1)

        note_a = EmployeeNote.objects.get(tenant=self.tenant_a)
        note_b = EmployeeNote.objects.get(tenant=self.tenant_b)

        self.assertEqual(note_a.employee, self.employee_a1)
        self.assertEqual(note_b.employee, self.employee_b1)

        # تأكيد حاسم: يسقط لو نُسب كل شيء إلى الشركة الأولى
        self.assertNotEqual(
            note_b.tenant_id,
            self.tenant_a.pk,
            "فشل أمني (عزل الشركات): وثيقة تخص الشركة ب نُسبت إلى الشركة أ!",
        )

    def test_unresolved_docs_leave_no_rows_and_record_reasons(self):
        """4. ما لا يُحسم يُترك: وثيقة بلا tenant وبمستخدم له عضويتان (أو لا وجود له) ← لا صفّ يُنشأ، ويظهر في التقرير بسببه."""
        # حالة 1: مستخدم متعدد العضويات
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_ambiguous_user",
            tenant=None,
            data={
                "title": "مهمة مستخدم متعدد العضويات",
                "createdBy": self.user_multi.pk,
            },
        )
        # حالة 2: مستخدم غير موجود
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_missing_user",
            tenant=None,
            data={
                "title": "مهمة مستخدم غائب",
                "createdBy": 9999999,
            },
        )
        # حالة 3: وثيقة بلا شركة وبلا أي مستخدم
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_no_owner",
            tenant=None,
            data={
                "title": "مهمة يتيمة بالكامل",
            },
        )

        stats, output = _run_command()

        # لا صف يُنشأ في الجداول
        self.assertEqual(Task.objects.count(), 0)

        # التقرير يظهر الأسباب صراحة
        self.assertGreaterEqual(stats["unresolved"]["multiple_memberships"], 1)
        self.assertGreaterEqual(stats["unresolved"]["user_not_found"], 1)
        self.assertGreaterEqual(stats["unresolved"]["no_tenant_on_doc"], 1)

    def test_rerun_is_idempotent(self):
        """5. إعادةُ التشغيل: شغّل الأمرَ مرّتين ← الأعدادُ نفسُها، ولا استثناء."""
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_idempotent",
            tenant=self.tenant_a,
            data={
                "title": "مهمة التكرار",
                "assignedTo": [self.staff_a1.pk],
                "submissions": [{"id": "s_rep_1", "userId": self.staff_a1.pk, "status": "pending"}],
            },
        )
        FirestoreMirrorDoc.objects.create(
            path=f"pointsHistory/{self.staff_a1.pk}/days/2026-08-01",
            tenant=self.tenant_a,
            data={"userId": self.staff_a1.pk, "date": "2026-08-01", "taskPoints": 10},
        )
        FirestoreMirrorDoc.objects.create(
            path=f"users/{self.staff_a1.pk}",
            tenant=self.tenant_a,
            data={"notes": "ملاحظة التكرار"},
        )

        stats1, _ = _run_command()

        tasks_count1 = Task.objects.count()
        assign_count1 = TaskAssignment.objects.count()
        sub_count1 = TaskSubmission.objects.count()
        points_count1 = PointEntry.objects.count()
        notes_count1 = EmployeeNote.objects.count()

        self.assertEqual(stats1["tasks_migrated"], 1)
        self.assertEqual(stats1["points_migrated"], 1)
        self.assertEqual(stats1["notes_migrated"], 1)

        # التشغيل الثاني
        stats2, _ = _run_command()

        self.assertEqual(Task.objects.count(), tasks_count1)
        self.assertEqual(TaskAssignment.objects.count(), assign_count1)
        self.assertEqual(TaskSubmission.objects.count(), sub_count1)
        self.assertEqual(PointEntry.objects.count(), points_count1)
        self.assertEqual(EmployeeNote.objects.count(), notes_count1)

        # العدادات في التشغيل الثاني تثبت التخطي
        self.assertEqual(stats2["tasks_migrated"], 0)
        self.assertEqual(stats2["tasks_already_migrated"], 1)
        self.assertEqual(stats2["points_migrated"], 0)
        self.assertEqual(stats2["points_already_migrated"], 1)
        self.assertEqual(stats2["notes_migrated"], 0)
        self.assertEqual(stats2["notes_already_migrated"], 1)

    def test_dry_run_writes_nothing_to_database(self):
        """6. --dry-run: التقريرُ يُطبع والجداولُ فارغة."""
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_dry_1",
            tenant=self.tenant_a,
            data={"title": "مهمة تجريبية", "assignedTo": [self.staff_a1.pk]},
        )
        FirestoreMirrorDoc.objects.create(
            path=f"pointsHistory/{self.staff_a1.pk}/days/2026-08-05",
            tenant=self.tenant_a,
            data={"userId": self.staff_a1.pk, "date": "2026-08-05", "attendancePoints": 2},
        )
        FirestoreMirrorDoc.objects.create(
            path=f"users/{self.staff_a1.pk}",
            tenant=self.tenant_a,
            data={"notes": "ملاحظة تجريبية"},
        )

        stats, output = _run_command(dry_run=True)

        # الجداول فارغة تماماً
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(TaskAssignment.objects.count(), 0)
        self.assertEqual(TaskSubmission.objects.count(), 0)
        self.assertEqual(PointEntry.objects.count(), 0)
        self.assertEqual(EmployeeNote.objects.count(), 0)

        # التقرير يُطبع ويحسب الأعداد المتوقعة
        self.assertEqual(stats["tasks_migrated"], 1)
        self.assertEqual(stats["points_migrated"], 1)
        self.assertEqual(stats["notes_migrated"], 1)
        self.assertIn("--dry-run", output)

    def test_daily_points_with_two_nonzero_and_one_zero_creates_two_entries(self):
        """7. نقاطٌ يوميّةٌ فيها فئتان غيرُ صفريّةٍ وفئةٌ صفريّة ← قيدان لا ثلاثة، بالتاريخ الصحيح."""
        FirestoreMirrorDoc.objects.create(
            path=f"pointsHistory/{self.staff_a1.pk}/days/2026-05-10",
            tenant=self.tenant_a,
            data={
                "userId": self.staff_a1.pk,
                "date": "2026-05-10",
                "activityPoints": 15,
                "taskPoints": 40,
                "attendancePoints": 0,  # صفرية لا يجب أن تنشئ قيداً
            },
        )

        _run_command()

        # يجب إنشاء قيدين فقط
        entries = PointEntry.objects.filter(tenant=self.tenant_a).order_by("points")
        self.assertEqual(entries.count(), 2, "يجب أن ينشأ قيدان فقط لأن الفئة الثالثة صفرية")

        # التحقق من التاريخ
        expected_date = datetime.date(2026, 5, 10)
        self.assertEqual(entries[0].awarded_on, expected_date)
        self.assertEqual(entries[1].awarded_on, expected_date)

        # التحقق من مسار المصدر والنقاط
        entry_activity = PointEntry.objects.get(
            source_path=f"pointsHistory/{self.staff_a1.pk}/days/2026-05-10#activity"
        )
        self.assertEqual(entry_activity.points, 15)

        entry_task = PointEntry.objects.get(
            source_path=f"pointsHistory/{self.staff_a1.pk}/days/2026-05-10#task"
        )
        self.assertEqual(entry_task.points, 40)

        # التحقق من عدم وجود قيد حضور
        self.assertFalse(
            PointEntry.objects.filter(
                source_path=f"pointsHistory/{self.staff_a1.pk}/days/2026-05-10#attendance"
            ).exists()
        )

    def test_user_notes_migrates_to_single_employeenote_and_mirror_doc_untouched(self):
        """8. users/<id>.notes ← EmployeeNote واحدةٌ بكاتبٍ None، ووثيقةُ المرآة لم تتغيّر."""
        doc = FirestoreMirrorDoc.objects.create(
            path=f"users/{self.staff_a1.pk}",
            tenant=self.tenant_a,
            data={"notes": "ملاحظة أصلية أولى عن الموظف"},
        )

        _run_command()

        self.assertEqual(EmployeeNote.objects.count(), 1)
        note = EmployeeNote.objects.get()
        self.assertEqual(note.body, "ملاحظة أصلية أولى عن الموظف")
        self.assertIsNone(note.author, "كاتب الملاحظة المهاجرة يجب أن يكون None")
        self.assertEqual(note.employee, self.employee_a1)
        self.assertEqual(note.source_path, f"users/{self.staff_a1.pk}")

        # وثيقة المرآة لم تتغير ولم تُمس
        doc.refresh_from_db()
        self.assertEqual(doc.data.get("notes"), "ملاحظة أصلية أولى عن الموظف")

    def test_tenant_filter_limits_migration_to_specified_tenant(self):
        """9. خيار --tenant يقصر التشغيل على شركة محددة ويتجاهل الأخرى."""
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_comp_a_only",
            tenant=self.tenant_a,
            data={"title": "مهمة خاصة بالشركة أ"},
        )
        FirestoreMirrorDoc.objects.create(
            path="tasks/task_comp_b_only",
            tenant=self.tenant_b,
            data={"title": "مهمة خاصة بالشركة ب"},
        )

        _run_command(tenant=self.tenant_a.pk)

        self.assertEqual(Task.objects.filter(tenant=self.tenant_a).count(), 1)
        self.assertEqual(Task.objects.filter(tenant=self.tenant_b).count(), 0)

    def test_employee_not_found_leaves_record_unmigrated_and_reports_reason(self):
        """10. إذا لم يوجد سجل Employee للمستخدم المسند إليه تسجل employee_not_found."""
        FirestoreMirrorDoc.objects.create(
            path=f"users/{self.user_no_emp.pk}",
            tenant=self.tenant_a,
            data={"notes": "ملاحظة لمستخدم بلا سجل موظف"},
        )

        stats, _ = _run_command()

        self.assertEqual(EmployeeNote.objects.count(), 0)
        self.assertGreaterEqual(stats["unresolved"]["employee_not_found"], 1)


class MirrorMigrationHonestyTest(TestCase):
    """ما تصمت عنه الهجرةُ يصير كذبةً في الدفاتر بعد شهر.

    هذه الاختباراتُ تحرس **صدقَ التقرير** و**عدمَ ضياع الأصل** — لا عدَّ الصفوف:
    هجرةٌ تُعيد تفسيرَ قيمةٍ بصمتٍ تمرّ خضراءَ في كلّ اختبارِ عدّ.
    """

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager = User.objects.create_user(username="honest_mgr", password="x")
        cls.tenant = create_company("شركة الصدق", cls.manager)
        cls.staff = User.objects.create_user(username="honest_staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role=FIELD_STAFF_ROLE
        )
        cls.employee = Employee.objects.create(
            tenant=cls.tenant, user=cls.staff, name="موظف الصدق", code="H1"
        )

    def test_an_unreadable_date_is_reported_as_a_bad_date_not_a_missing_tenant(self):
        """سببٌ يُحشر في خانةِ سببٍ آخر يجعل رقمَ التقرير كذبةً مرتّبة.

        كان تاريخٌ لا يُقرأ يُعدّ `no_tenant_on_doc` — فيقرأ المالكُ «وثائقُ بلا
        شركة» ويبحث في العضويّات، والعطبُ في صيغة التاريخ.
        """
        FirestoreMirrorDoc.objects.create(
            path=f"pointsHistory/{self.staff.pk}/days/ليس-تاريخاً",
            tenant=self.tenant,
            data={"activityPoints": 3},
        )
        stats, _ = _run_command()

        self.assertEqual(stats["unresolved"]["bad_date"], 1)
        self.assertEqual(stats["unresolved"]["no_tenant_on_doc"], 0)
        self.assertEqual(PointEntry.objects.count(), 0)

    def test_a_status_we_do_not_understand_keeps_its_original_in_extra(self):
        """«لا يضيع شيء» تشمل ما أسأنا قراءته.

        الحالةُ حقلٌ **معروف**، فلا تدخل `extra` تلقائيّاً: بلا هذا الحفظِ
        الصريح تصير `ARCHIVED` حالةَ «جديدة» ولا أثرَ لما كانت.
        """
        FirestoreMirrorDoc.objects.create(
            path="tasks/weird_status",
            tenant=self.tenant,
            data={
                "title": "مهمة بحالة مجهولة",
                "status": "ARCHIVED_BY_OLD_APP",
                "priority": "blazing",
            },
        )
        stats, report = _run_command()

        task = Task.objects.get()
        self.assertEqual(task.status, Task.STATUS_NEW)
        self.assertEqual(task.extra["_source_status"], "ARCHIVED_BY_OLD_APP")
        self.assertEqual(task.extra["_source_priority"], "blazing")

        self.assertEqual(stats["coerced"]["task_status"], 1)
        self.assertEqual(stats["coerced"]["task_priority"], 1)
        self.assertIn("لم تُفهم", report)

    def test_a_status_we_do_understand_leaves_no_coercion_trace(self):
        """وإلا كان الاختبارُ أعلاه يمرّ لأنّ كلَّ حالةٍ تُعدّ «غيرَ مفهومة»."""
        FirestoreMirrorDoc.objects.create(
            path="tasks/known_status",
            tenant=self.tenant,
            data={"title": "مهمة", "status": "COMPLETED", "priority": "low"},
        )
        stats, _ = _run_command()

        task = Task.objects.get()
        self.assertEqual(task.status, Task.STATUS_COMPLETED)
        self.assertEqual(task.priority, "LOW")
        self.assertNotIn("_source_status", task.extra)
        self.assertEqual(stats["coerced"]["task_status"], 0)
        self.assertEqual(stats["coerced"]["task_priority"], 0)

    def test_an_assignee_is_never_taken_for_the_owner(self):
        """المُسنَدُ إليه ليس مالكَ الوثيقة.

        وثيقةٌ بلا شركةٍ وبلا `createdBy` تبقى بلا نسبٍ ولو كان لها مُسنَدٌ واحدٌ
        بعضويّةٍ واحدة: النسبُ بالمُسنَد تخمينٌ، وموظفٌ يعمل لشركتين يقلبه.
        """
        FirestoreMirrorDoc.objects.create(
            path="tasks/owner_unknown",
            tenant=None,
            data={"title": "مهمة يتيمة", "assignedTo": [self.staff.pk]},
        )
        stats, _ = _run_command()

        self.assertEqual(Task.objects.count(), 0, "لا تُنسب بالتخمين")
        self.assertEqual(stats["unresolved"]["no_tenant_on_doc"], 1)

    def test_submission_attachments_are_counted_in_the_report(self):
        """نوعٌ كاملٌ كان يُهاجَر ولا يظهر في التقرير الذي يقرّر عليه المالك."""
        FirestoreMirrorDoc.objects.create(
            path="tasks/with_attachment",
            tenant=self.tenant,
            data={
                "title": "مهمة بمرفق",
                "assignedTo": [self.staff.pk],
                "submissions": [
                    {
                        "id": "s1",
                        "userId": self.staff.pk,
                        "status": "pending",
                        "items": [],
                        "attachments": [
                            {"url": "https://example.com/a.pdf", "name": "a.pdf"},
                            {"url": "", "name": "بلا رابط"},
                        ],
                    }
                ],
            },
        )
        stats, report = _run_command()

        # المرفقُ بلا رابطٍ لا يُنشأ ولا يُعدّ.
        self.assertEqual(stats["submission_attachments_migrated"], 1)
        self.assertIn("مرفقات التسليم", report)

    def test_a_dry_run_reports_the_same_shape_and_writes_nothing(self):
        FirestoreMirrorDoc.objects.create(
            path="tasks/dry",
            tenant=self.tenant,
            data={"title": "مهمة", "assignedTo": [self.staff.pk]},
        )
        stats, report = _run_command("--dry-run")

        self.assertEqual(stats["tasks_migrated"], 1)
        self.assertIn("--dry-run", report)
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(TaskAssignment.objects.count(), 0)
