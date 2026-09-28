"""#222 §٧ — إصلاح بيانات: بطاقات كفالة خاطئة نجت من قبل هذا الإصلاح.

الأعطال الأربعة (المرجع لا يُنهي البطاقة، والمشتري الثاني لا يأخذها، وحذفُ
البطاقة عند إلغاء الترحيل) تركت في الإنتاج بطاقاتٍ حيّةً كاذبة. هذه تذكرة
إصلاحٍ مستقلة — لا تُبنى فوق منطق الكفالة الجديدة بل تُصحِّح ما خلَّفه القديم
مرّةً واحدة.

**تشغيلٌ تجريبيٌّ افتراضياً**، ومتكرّرٌ بلا أثر إضافي (كل حالةٍ تُصلَح تخرج من
معايير الاختيار في المرّة القادمة). وللشركات المرخّصة فقط — إصلاحُ بياناتٍ في
جدولٍ لا تراه الشركة أصلاً عبثٌ لا إصلاح.

الحالات الثلاث (§7):
  (أ) بطاقة حيّة، ووحدتها `in_stock` ومعها `return_line`، ورابط بيعها = بند
      البطاقة ← تُنهى `returned` بتاريخ المرجع.
  (ب) بطاقة حيّة، ووحدتها مُباعة على بند آخر ← تُنهى `superseded`. ثم تُنشأ
      بطاقة المشتري الحالي إن كانت على منتجه مدة، بتاريخ فاتورته، مع ملاحظة
      «أُنشئت بأثر رجعي».
  (ج) أوامر صيانة `warranty_card` فيها فارغ، ولها رقم تطابقه بطاقة واحدة ←
      **تقرير فقط، بلا ربط آلي** — القرار للموظف الذي يعرف الملف.

الرموز المطبوعة: لا شيء يُصلَح فيها، لأنه لا رمز QR صدر بعد (#217 لاحقة).

    python manage.py repair_warranty_lifecycle --tenant <id>            # عرض فقط
    python manage.py repair_warranty_lifecycle --tenant <id> --apply    # تطبيق
"""
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from after_sales.models import ServiceOrder, WarrantyCard, WarrantyPolicy, add_months
from after_sales.services import MODULE_KEY, get_or_create_after_sales_settings
from core.modules import module_enabled
from inventory.models import ProductSerial
from tenants.models import Tenant

logger = logging.getLogger(__name__)


def _card_invoice_id(card):
    """فاتورة البطاقة — بالمرساتين معاً، لأن الأقدم قد تحمل البند وحده.

    القياس هنا **بالفاتورة لا بالبند**: تعديل مسودّة حذف بنداً وأعاد آخر
    (#222 §هـ) ينقطع به رقم البند فقط، فتبقى الفاتورة نفسها ولا يصحّ أن
    يبدو الأمر «بيعاً ثانياً» أو «إرجاعاً لا يخصّه» لمجرّد اختلاف رقم البند.
    """
    if card.sales_invoice_id:
        return card.sales_invoice_id
    if card.sales_invoice_line_id:
        return card.sales_invoice_line.invoice_id
    return None


class Command(BaseCommand):
    help = "يصلح بطاقات الكفالة الخاطئة من قبل #222 — تشغيلٌ تجريبيٌّ افتراضياً."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", type=int, required=True, help="TenantID — شركة واحدة لكل تشغيلة.",
        )
        parser.add_argument(
            "--apply", action="store_true", help="اكتب الإصلاح فعلياً بدل عرضه فقط.",
        )

    def handle(self, *args, **opts):
        tenant_id = opts["tenant"]
        apply_changes = opts["apply"]

        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            raise CommandError(f"لا شركة بالمعرّف {tenant_id}.")
        if not module_enabled(tenant_id, MODULE_KEY):
            raise CommandError(
                f"الشركة «{tenant.CompanyName}» (#{tenant_id}) غير مرخّصة لوحدة "
                "«خدمة ما بعد البيع» — لا إصلاح لبياناتٍ لا تراها الشركة أصلاً."
            )

        self.stdout.write(
            f"— {'تطبيق' if apply_changes else 'عرض فقط (dry-run)'} — "
            f"الشركة «{tenant.CompanyName}» (#{tenant_id})"
        )

        self._unanchored_pks = set()
        fixed_returned = self._fix_returned_units(tenant_id, apply=apply_changes)
        fixed_resold = self._fix_resold_units(tenant_id, apply=apply_changes)
        self._report_unanchored_cards(tenant_id)
        self._report_unlinked_service_orders(tenant_id)

        if not (fixed_returned or fixed_resold):
            self.stdout.write(self.style.SUCCESS("لا شيء يحتاج إصلاحاً."))
        elif not apply_changes:
            self.stdout.write(self.style.WARNING("أعد التشغيل بـ --apply للتطبيق."))

    # ── (أ) وحدةٌ أُرجعت والبطاقة بقيت حيّة ─────────────────────────────
    def _fix_returned_units(self, tenant_id: int, *, apply: bool) -> bool:
        candidates = (
            WarrantyCard.objects
            .filter(
                tenant_id=tenant_id, source=WarrantyCard.SOURCE_AUTO_SALE,
                ended_on__isnull=True, product_serial__isnull=False,
            )
            .select_related(
                "product_serial", "product_serial__return_line__invoice",
                "product_serial__sales_line__invoice",
                "sales_invoice", "sales_invoice_line__invoice",
            )
        )
        rows = []
        for card in candidates:
            unit = card.product_serial
            if unit.status != ProductSerial.STATUS_IN_STOCK:
                continue
            if not unit.return_line_id:
                continue
            card_invoice_id = _card_invoice_id(card)
            if card_invoice_id is None:
                self._unanchored_pks.add(card.pk)
                continue
            unit_invoice_id = unit.sales_line.invoice_id if unit.sales_line_id else None
            if unit_invoice_id != card_invoice_id:
                continue
            rows.append((card, unit.return_line))

        for card, return_line in rows:
            self.stdout.write(
                f"(أ) returned — بطاقة #{card.pk} (serial={card.serial}) ← "
                f"مرجع «{return_line.invoice.invoice_number}» "
                f"بتاريخ {return_line.invoice.invoice_date}"
            )

        if apply and rows:
            with transaction.atomic():
                for card, return_line in rows:
                    card.ended_on = return_line.invoice.invoice_date
                    card.end_reason = WarrantyCard.END_RETURNED
                    card.end_return_line = return_line
                    card.save(update_fields=[
                        "ended_on", "end_reason", "end_return_line", "updated_at",
                    ])
            logger.info(
                "repair_warranty_lifecycle: tenant=%s returned=%d applied",
                tenant_id, len(rows),
            )
        return bool(rows)

    # ── (ب) وحدةٌ بِيعت لمشترٍ آخر والبطاقة القديمة بقيت حيّة ────────────
    def _fix_resold_units(self, tenant_id: int, *, apply: bool) -> bool:
        candidates = (
            WarrantyCard.objects
            .filter(
                tenant_id=tenant_id, source=WarrantyCard.SOURCE_AUTO_SALE,
                ended_on__isnull=True, product_serial__isnull=False,
            )
            .select_related(
                "product_serial", "product_serial__sales_line__invoice",
                "product_serial__product",
                "sales_invoice", "sales_invoice_line__invoice",
            )
        )
        rows = []
        for card in candidates:
            unit = card.product_serial
            if unit.status != ProductSerial.STATUS_SOLD:
                continue
            if not unit.sales_line_id:
                continue
            card_invoice_id = _card_invoice_id(card)
            if card_invoice_id is None:
                self._unanchored_pks.add(card.pk)
                continue
            new_invoice = unit.sales_line.invoice
            if new_invoice.pk == card_invoice_id:
                continue
            already_carded = (
                WarrantyCard.objects
                .filter(
                    tenant_id=tenant_id, product_serial_id=unit.pk, ended_on__isnull=True,
                )
                .exclude(pk=card.pk)
                .filter(
                    Q(sales_invoice_id=new_invoice.pk)
                    | Q(sales_invoice_line__invoice_id=new_invoice.pk)
                )
                .exists()
            )
            rows.append((card, unit, new_invoice, already_carded))

        for card, unit, new_invoice, already_carded in rows:
            extra = "" if already_carded else " + بطاقة جديدة للمشتري الحالي بأثر رجعي"
            self.stdout.write(
                f"(ب) superseded — بطاقة #{card.pk} (serial={card.serial}) ← "
                f"بِيعت على فاتورة «{new_invoice.invoice_number}»{extra}"
            )

        if apply and rows:
            from inventory.services import product_display_name

            # #231: المدة من سياسة البراند لا من عمودٍ على المنتج — استعلامٌ
            # واحد لكل منتجات هذه الدفعة، لا واحدٌ لكل صفّ.
            policies = {
                policy.product_id: policy
                for policy in WarrantyPolicy.objects.filter(
                    tenant_id=tenant_id,
                    product_id__in={unit.product_id for _, unit, _, _ in rows},
                )
            }
            settings_row = (
                get_or_create_after_sales_settings(tenant_id) if policies else None
            )

            with transaction.atomic():
                for card, unit, new_invoice, already_carded in rows:
                    card.ended_on = new_invoice.invoice_date
                    card.end_reason = WarrantyCard.END_SUPERSEDED
                    card.save(update_fields=["ended_on", "end_reason", "updated_at"])
                    if already_carded:
                        continue
                    policy = policies.get(unit.product_id)
                    if policy is None:
                        continue
                    customer = new_invoice.customer if new_invoice.customer_id else None
                    WarrantyCard.objects.create(
                        tenant_id=tenant_id,
                        product=unit.product,
                        device_name=product_display_name(unit.product)[
                            :WarrantyCard._meta.get_field("device_name").max_length
                        ],
                        serial=unit.serial,
                        product_serial=unit,
                        sales_invoice=new_invoice,
                        sales_invoice_line_id=unit.sales_line_id,
                        partner_id=new_invoice.customer_id,
                        customer_name=(customer.name if customer else "")[:150],
                        customer_phone=(
                            (getattr(customer, "phone", "") or "")[:32] if customer else ""
                        ),
                        start_date=new_invoice.invoice_date,
                        duration_months=policy.dealer_months,
                        end_date=add_months(new_invoice.invoice_date, policy.dealer_months),
                        source=WarrantyCard.SOURCE_AUTO_SALE,
                        terms_text=policy.terms_override or settings_row.default_terms,
                        notes="أُنشئت بأثر رجعي — أداة إصلاح البيانات (#222).",
                    )
            logger.info(
                "repair_warranty_lifecycle: tenant=%s superseded=%d applied",
                tenant_id, len(rows),
            )
        return bool(rows)

    # ── بطاقةٌ بلا مرساة على الإطلاق — تقرير فقط، لا تخمين ────────────────
    def _report_unanchored_cards(self, tenant_id: int) -> None:
        if not self._unanchored_pks:
            return
        cards = WarrantyCard.objects.filter(pk__in=self._unanchored_pks).order_by("pk")
        for card in cards:
            self.stdout.write(
                f"— بلا مرساة — بطاقة #{card.pk} (serial={card.serial}) لا تحمل "
                "فاتورة بيعٍ ولا بندها — راجعها يدوياً، بلا إصلاحٍ آلي."
            )

    # ── (ج) أوامر صيانة بلا بطاقة — تقرير فقط ────────────────────────────
    def _report_unlinked_service_orders(self, tenant_id: int) -> None:
        orders = list(
            ServiceOrder.objects
            .filter(tenant_id=tenant_id, warranty_card__isnull=True)
            .exclude(serial="")
        )
        if not orders:
            return
        serials = {o.serial for o in orders}
        cards_by_serial = {}
        for serial in serials:
            matches = list(WarrantyCard.objects.filter(tenant_id=tenant_id, serial=serial))
            if len(matches) == 1:
                cards_by_serial[serial] = matches[0]

        for order in orders:
            card = cards_by_serial.get(order.serial)
            if card is None:
                continue
            self.stdout.write(
                f"(ج) تقرير فقط — أمر الصيانة «{order.order_number or order.pk}» "
                f"(serial={order.serial}) يطابقه بطاقة واحدة #{card.pk} — "
                "راجعها يدوياً، بلا ربط آلي."
            )
