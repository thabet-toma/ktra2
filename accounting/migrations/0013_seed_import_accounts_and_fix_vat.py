"""
هجرة بيانات حرجة — إصلاح شجرة الحسابات وتصحيح ربط ضريبة القيمة المضافة:

المشكلة قبل الإصلاح:
- لا يوجد حسابات مخصّصة لـ VAT Input / VAT Output / رسوم الاستيراد.
- الهجرة 0011 كانت تربط `VAT16` بأول حساب Liability (غالباً 2101 الدائنون التجاريون!)
  نتيجة: ضريبة المدخلات كانت تُقيَّد دائنة في حساب الموردين → خلل كارثي.

هذه الهجرة:
1) تُنشئ/تحدّث الحسابات التالية لكل Tenant إن لم تكن موجودة:
     1105  ضريبة القيمة المضافة - مدخلات (Asset)
     1106  دفعات مقدمة للموردين (Asset)
     2104  ضريبة القيمة المضافة - مخرجات (Liability)
     2105  رسوم جمركية مستحقة (Liability)
     53    مصاريف الاستيراد المباشرة (Expense parent)
     5301–5307  شحن دولي/تخليص/رسوم جمركية/تأمين/شحن محلي/موانئ/متنوعة (Expense)
   مع ضمان Parent صحيح.
2) تُعيد توجيه `VAT16` الحالي إلى 2104 (مخرجات) مع direction='sales'.
3) تُنشئ سجلّ جديد `VAT16_IN` يشير إلى 1105 (مدخلات) مع direction='purchase'.

هذه الهجرة idempotent — يمكن تشغيلها عدة مرات بأمان.
"""
from decimal import Decimal

from django.db import migrations


NEW_ACCOUNTS = [
    # (code, name, type, parent_code)
    ("1105", "ضريبة القيمة المضافة - مدخلات (VAT Input)", "Asset", "11"),
    ("1106", "دفعات مقدمة للموردين (Supplier Advances)", "Asset", "11"),
    ("2104", "ضريبة القيمة المضافة - مخرجات (VAT Output)", "Liability", "21"),
    ("2105", "رسوم جمركية مستحقة (Customs Duties Payable)", "Liability", "21"),
    ("53", "مصاريف الاستيراد المباشرة (Direct Import Expenses)", "Expense", "5"),
    ("5301", "مصاريف الشحن الدولي (International Shipping)", "Expense", "53"),
    ("5302", "مصاريف التخليص الجمركي (Customs Clearance Fees)", "Expense", "53"),
    ("5303", "الرسوم الجمركية (Customs Duties)", "Expense", "53"),
    ("5304", "مصاريف التأمين على الشحنات (Shipment Insurance)", "Expense", "53"),
    ("5305", "مصاريف الشحن المحلي (Local Shipping & Delivery)", "Expense", "53"),
    ("5306", "رسوم موانئ / تخزين (Port & Storage Fees)", "Expense", "53"),
    ("5307", "رسوم استيراد متنوعة (Misc. Import Fees)", "Expense", "53"),
]


def _ensure_parent_roots(Account, tenant_id):
    """يتأكد أن الحسابات الأب 11 و21 و5 موجودة (ينشئها إن لم تكن)."""
    roots = [
        ("1", "الأصول (Assets)", "Asset", None),
        ("2", "الخصوم (Liabilities)", "Liability", None),
        ("5", "المصروفات (Expenses)", "Expense", None),
        ("11", "الأصول المتداولة (Current Assets)", "Asset", "1"),
        ("21", "الالتزامات المتداولة (Current Liabilities)", "Liability", "2"),
    ]
    for code, name, a_type, parent_code in roots:
        parent = None
        if parent_code:
            parent = Account.objects.filter(tenant_id=tenant_id, code=parent_code).first()
        Account.objects.get_or_create(
            tenant_id=tenant_id,
            code=code,
            defaults={
                "name": name,
                "account_type": a_type,
                "parent": parent,
                "is_active": True,
            },
        )


def forwards(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    TaxRate = apps.get_model("accounting", "TaxRate")
    Tenant = apps.get_model("tenants", "Tenant")

    for tenant in Tenant.objects.all():
        tid = tenant.TenantID

        _ensure_parent_roots(Account, tid)

        # إنشاء الحسابات المفقودة
        for code, name, a_type, parent_code in NEW_ACCOUNTS:
            parent = Account.objects.filter(tenant_id=tid, code=parent_code).first()
            Account.objects.get_or_create(
                tenant_id=tid,
                code=code,
                defaults={
                    "name": name,
                    "account_type": a_type,
                    "parent": parent,
                    "is_active": True,
                },
            )

        # المراجع المحاسبية الحاسمة
        vat_input_acc = Account.objects.filter(tenant_id=tid, code="1105").first()
        vat_output_acc = Account.objects.filter(tenant_id=tid, code="2104").first()
        if not (vat_input_acc and vat_output_acc):
            continue  # شيء غريب — نتجاوز

        # إصلاح VAT16 الحالي → مخرجات (sales) مربوطاً بـ 2104
        existing_vat = TaxRate.objects.filter(tenant_id=tid, code="VAT16").first()
        if existing_vat:
            changed = False
            if existing_vat.tax_account_id != vat_output_acc.id:
                existing_vat.tax_account_id = vat_output_acc.id
                changed = True
            if getattr(existing_vat, "direction", "both") != "sales":
                existing_vat.direction = "sales"
                changed = True
            if not existing_vat.is_active:
                existing_vat.is_active = True
                changed = True
            if changed:
                existing_vat.save()
        else:
            TaxRate.objects.create(
                tenant_id=tid,
                name="ضريبة القيمة المضافة 16% - مخرجات",
                code="VAT16",
                rate=Decimal("16.00"),
                tax_account_id=vat_output_acc.id,
                direction="sales",
                is_active=True,
            )

        # إنشاء VAT16_IN لضريبة المدخلات
        if not TaxRate.objects.filter(tenant_id=tid, code="VAT16_IN").exists():
            TaxRate.objects.create(
                tenant_id=tid,
                name="ضريبة القيمة المضافة 16% - مدخلات",
                code="VAT16_IN",
                rate=Decimal("16.00"),
                tax_account_id=vat_input_acc.id,
                direction="purchase",
                is_active=True,
            )


def reverse_noop(apps, schema_editor):
    # لا نحذف البيانات المُنشأة عند التراجع (سلامة المحاسبة).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0012_taxrate_direction"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_noop),
    ]
