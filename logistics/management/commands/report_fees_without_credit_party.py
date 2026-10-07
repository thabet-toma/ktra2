"""رسوم فواتير شراء غير مرحّلة بلا طرف دائن، ووصفها لا يشبه المورد — قراءة فقط.

قبل الطرف الدائن (`PurchaseInvoiceFee.credit_partner`/`credit_account`) كان كل رسمٍ يُدائَن
على مورد الفاتورة: «تكاليف كترا» على فاتورةٍ دولية كانت ستجعل المورد الصيني دائناً بها.
الأمر يعرضها ليختار المالك طرفها من شاشة الفاتورة — لا يكتب شيئاً.

    python manage.py report_fees_without_credit_party --tenant 1
"""
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand

from logistics.models import PurchaseInvoiceFee


def _looks_like_supplier(description, supplier_name) -> bool:
    """الوصف يذكر المورد (اسمه أو كلمةً منه من ثلاثة أحرف فأكثر)."""
    text = (description or '').strip().lower()
    name = (supplier_name or '').strip().lower()
    if not text or not name:
        return False
    return name in text or any(len(w) >= 3 and w in text for w in name.split())


class Command(BaseCommand):
    help = "رسوم فواتير غير مرحّلة بلا طرف دائن ووصفها لا يشبه المورد (قراءة فقط)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")

    def handle(self, *args, **options):
        fees = (
            PurchaseInvoiceFee.objects
            .filter(tenant_id=options["tenant"], invoice__is_posted=False,
                    credit_partner__isnull=True, credit_account__isnull=True)
            .select_related('invoice', 'invoice__partner', 'expense_account')
            .order_by('invoice_id', 'id')
        )
        w = self.stdout.write
        rows = [f for f in fees if not _looks_like_supplier(f.description, f.invoice.partner.name)]
        by_desc = defaultdict(lambda: [0, Decimal('0')])
        for f in rows:
            by_desc[f.description][0] += 1
            by_desc[f.description][1] += Decimal(str(f.amount or 0))
        w(self.style.MIGRATE_HEADING(
            f"رسوم بلا طرف دائن ووصفها لا يشبه المورد: {len(rows)} — "
            f"{sum((f.amount for f in rows), Decimal('0')):.2f} ₪"))
        for desc, (count, total) in sorted(by_desc.items(), key=lambda kv: -kv[1][1]):
            w(f"  «{desc}»: {count} رسم، {total:.2f} ₪")
        for f in rows:
            w(f"    #{f.pk} {f.invoice.invoice_number} (المورد: {f.invoice.partner.name}) "
              f"«{f.description}» {f.amount} ₪ — مدين {f.expense_account.code}"
              f"{' مرسمَل' if f.capitalize_to_inventory else ''}")
        taxable = fees.filter(is_taxable=True).count()
        w(f"رسوم «ضمن أساس الضريبة» على فواتير غير مرحّلة: {taxable}")
        if rows:
            w("الإجراء: افتح الفاتورة واختر «الطرف الدائن» لكل رسم (جهة أو حساب).")
