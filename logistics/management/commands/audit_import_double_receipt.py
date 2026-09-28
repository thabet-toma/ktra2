"""تقرير فقط: أثر ISSUE #225 على البيانات — مسودات معرّضة لاستلامٍ ثانٍ، ومخزونٌ تضاعف.

كانت إعادة احتساب التكلفة الواصلة تحذف بنود الفاتورة الدولية وتعيد إنشاءها،
فتُصفَّر `received_quantity` بلا إعادة مزامنة: مسودّةٌ دخلت بضاعتها بحركات
`SHIPMENT` القديمة تصير «مستلمة» بكميات صفرية، فيُقبل عليها استلامٌ ثانٍ
ويتضاعف المخزون. الحفظ صار في مكانه؛ هذا الأمر يسرد ما انحرف قبل الإصلاح.

**لا يكتب شيئاً** — تشغيلٌ تجريبيّ دائماً. تصحيح مخزونٍ تضاعف قرارٌ بشريّ (أيّ
الحركتين تُعكس، وأثر ذلك على FIFO والتكلفة)، والأرقام التسلسلية التي ضاعت عن
المسودات لا تُستعاد من القاعدة.

    python manage.py audit_import_double_receipt --tenant 1
    python manage.py audit_import_double_receipt          # كل الشركات، شركةً شركة
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from inventory.models import StockMovement
from logistics.landed_cost import quantity_text
from logistics.models import PurchaseInvoice
from logistics.services import (
    import_receipt_quantities_from_shipment_stock,
    import_shipment_legacy_stock_by_product,
)
from tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "كشف الفواتير الدولية المعرّضة لاستلام ثانٍ والمخزون الذي تضاعف فعلاً "
        "(ISSUE #225) — تقرير فقط بلا أي كتابة."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="معرّف الشركة (افتراضياً كل الشركات).")

    def handle(self, *args, **options):
        tenants = Tenant.objects.all().order_by("TenantID")
        if options.get("tenant"):
            tenants = tenants.filter(TenantID=options["tenant"])

        at_risk_total = doubled_total = 0
        for tenant in tenants:
            invoices = list(
                PurchaseInvoice.objects.filter(
                    tenant=tenant,
                    invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
                    is_return=False,
                )
                .select_related("deal")
                .prefetch_related("items__product")
                .order_by("pk")
            )
            if not invoices:
                continue
            at_risk = [row for row in map(self._at_risk_row, invoices) if row]
            doubled = [row for inv in invoices for row in self._doubled_rows(inv)]
            if not at_risk and not doubled:
                continue

            at_risk_total += len(at_risk)
            doubled_total += len(doubled)
            self.stdout.write(f"\nشركة {tenant.TenantID} — {tenant.CompanyName}")
            self.stdout.write("  (أ) مسودات دولية معرّضة لاستلام ثانٍ:")
            for line in at_risk or ["    — لا شيء"]:
                self.stdout.write(line)
            self.stdout.write("  (ب) فواتير تضاعف مخزونها فعلاً:")
            for line in doubled or ["    — لا شيء"]:
                self.stdout.write(line)

        self.stdout.write(
            f"\nالمجموع: (أ) {at_risk_total} فاتورة · (ب) {doubled_total} سطر. "
            "تقرير فقط — لم يُكتب شيء. عالج (أ) بإعادة احتساب التكلفة الواصلة "
            "للشحنة (تعيد المزامنة)، و(ب) بقرارٍ يدويّ على أيّ الحركتين تُعكس."
        )

    # ── (أ) مسودة «مستلمة» بكميات أقلّ مما تقوله حركات شحنتها ──────────────
    def _at_risk_row(self, invoice):
        if invoice.is_posted or invoice.receipt_status == PurchaseInvoice.RECEIPT_NOT:
            return None
        planned = import_receipt_quantities_from_shipment_stock(invoice)
        if not planned:
            return None
        expected = sum(planned.values(), Decimal("0"))
        actual = sum(
            (Decimal(str(it.received_quantity or 0)) for it in invoice.items.all()),
            Decimal("0"),
        )
        if actual >= expected:
            return None
        deal_ref = invoice.deal.ref_number if invoice.deal_id else "—"
        return (
            f"    {invoice.invoice_number} (صفقة {deal_ref}) · مستلَم {quantity_text(actual)} "
            f"مقابل {quantity_text(expected)} من حركات الشحنة · الحالة {invoice.receipt_status}"
        )

    # ── (ب) حركات الشحنة القديمة + حركات الفاتورة تتجاوز كمية البند ────────
    def _doubled_rows(self, invoice):
        legacy = import_shipment_legacy_stock_by_product(invoice) or {}
        from_invoice: dict[int, Decimal] = {}
        for pid, qty in StockMovement.objects.filter(
            tenant_id=invoice.tenant_id, reference_type="PURCHASE_INVOICE",
            reference_id=invoice.pk, movement_type="IN",
        ).values_list("product_id", "quantity"):
            from_invoice[pid] = from_invoice.get(pid, Decimal("0")) + Decimal(str(qty or 0))

        ordered: dict[int, Decimal] = {}
        names: dict[int, str] = {}
        for it in invoice.items.all():
            if not it.product_id:
                continue
            ordered[it.product_id] = ordered.get(it.product_id, Decimal("0")) + Decimal(
                str(it.quantity or 0))
            names.setdefault(it.product_id, it.name)

        rows = []
        for pid, qty in ordered.items():
            entered = legacy.get(pid, Decimal("0")) + from_invoice.get(pid, Decimal("0"))
            if entered <= qty:
                continue
            rows.append(
                f"    {invoice.invoice_number} · «{names[pid]}» (#{pid}): "
                f"شحنة {quantity_text(legacy.get(pid, Decimal('0')))} + "
                f"فاتورة {quantity_text(from_invoice.get(pid, Decimal('0')))} = "
                f"{quantity_text(entered)} مقابل كمية البند {quantity_text(qty)}"
            )
        return rows
