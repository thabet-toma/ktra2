"""
حذف نهائي لصفقات محددة (مرجع مثل D-0110) مع:
  - حذف قيود اليومية المرتبطة (حذف السطر والرأس من journal_lines / journal_headers) وليس عكس قيد
  - حذف دفعات الصفقة، بنود الصفقة، فواتير الشراء SQL لهذه الصفقة
  - إزالة ربط الصفقة بالشحنة (logistics_shipment_deals)

اختياري: --delete-empty-shipments
  إذا لم يبقَ على الشحنة أي صفقة بعد الحذف، حذف الشحنة + التخليص + دفعات التخليص/الوكيل وجميع قيودها.

الاستخدام (معاينة افتراضية — لا يكتب إلا مع --apply):
  python manage.py purge_deals --tenant-id 1 --refs D-0110,D-0106,D-0105,D-0109,D-0104,D-0108,D-0107
  python manage.py purge_deals --tenant-id 1 --refs D-0110 --delete-empty-shipments --apply
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.api import purge_journals
from accounting.models import JournalHeader


def _split_refs(raw: str) -> list[str]:
    parts = []
    for chunk in (raw or "").replace("،", ",").split(","):
        s = chunk.strip().upper()
        if s:
            parts.append(s)
    return parts


def _collect_journal_ids_for_payment_ids(payment_ids: list[int]) -> set[int]:
    if not payment_ids:
        return set()
    qs = JournalHeader.objects.filter(
        reference_type__in=("LOGISTICS_PAYMENT", "LOGISTICS_PAYMENT_UNPOST"),
        reference_id__in=payment_ids,
    )
    return set(qs.values_list("pk", flat=True))


def _collect_journal_ids_for_invoice_ids(invoice_ids: list[int]) -> set[int]:
    if not invoice_ids:
        return set()
    qs = JournalHeader.objects.filter(
        reference_type__in=("PURCHASE_INVOICE", "PURCHASE_RECEIPT"),
        reference_id__in=invoice_ids,
    )
    return set(qs.values_list("pk", flat=True))


def _collect_journal_ids_for_shipment(shipment_id: int) -> set[int]:
    jids = set(
        JournalHeader.objects.filter(
            reference_type="LOGISTICS_SHIPMENT",
            reference_id=shipment_id,
        ).values_list("pk", flat=True)
    )
    return jids


def _null_all_journal_fks(journal_ids: set[int]) -> None:
    if not journal_ids:
        return
    from logistics.models import (
        LogisticsDeal,
        LogisticsPayment,
        LogisticsClearancePayment,
        PurchaseInvoice,
    )

    LogisticsPayment.all_objects.filter(journal_id__in=journal_ids).update(
        journal_id=None, bank_account_id=None
    )
    LogisticsDeal.all_objects.filter(journal_id__in=journal_ids).update(journal_id=None)
    PurchaseInvoice.objects.filter(journal_id__in=journal_ids).update(journal_id=None)
    LogisticsClearancePayment.objects.filter(journal_id__in=journal_ids).update(journal_id=None)


def _delete_journal_headers(journal_ids: set[int]) -> int:
    # المرحلة 2: الحذف الجماعي للقيود عبر واجهة accounting.api —
    # جمع المعرّفات (قراءة) يبقى هنا، والكتابة الوحيدة تمرّ من الواجهة.
    return purge_journals(journal_ids)


class Command(BaseCommand):
    help = "Hard-delete deals by ref_number and remove linked journals (no reversal entries)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=1)
        parser.add_argument(
            "--refs",
            type=str,
            required=True,
            help="Comma-separated deal ref_numbers e.g. D-0110,D-0106",
        )
        parser.add_argument(
            "--delete-empty-shipments",
            action="store_true",
            help="After unlinking deals, delete shipments that have zero deals left (full cascade cleanup).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete. Without this flag, only a dry-run summary is printed.",
        )

    def handle(self, *args, **opts):
        from logistics.models import (
            LogisticsDeal,
            LogisticsDealItem,
            LogisticsPayment,
            LogisticsShipmentDeal,
            LogisticsShipment,
            LogisticsClearance,
            LogisticsClearancePayment,
            PurchaseInvoice,
            PurchaseInvoiceItem,
        )

        tenant_id = opts["tenant_id"]
        refs = _split_refs(opts["refs"])
        if not refs:
            self.stderr.write(self.style.ERROR("No refs in --refs"))
            return

        deals = list(
            LogisticsDeal.all_objects.filter(tenant_id=tenant_id, ref_number__in=refs).order_by("id")
        )
        found = {d.ref_number.upper() for d in deals}
        missing = [r for r in refs if r not in found]
        if missing:
            self.stdout.write(self.style.WARNING(f"Refs not found (tenant={tenant_id}): {missing}"))
        if not deals:
            self.stderr.write(self.style.ERROR("No matching deals to purge."))
            return

        apply = bool(opts["apply"])
        del_empty = bool(opts["delete_empty_shipments"])

        self.stdout.write(
            f"Deals to purge ({len(deals)}): " + ", ".join(d.ref_number for d in deals)
        )
        self.stdout.write(f"delete_empty_shipments={del_empty}  apply={apply}")

        if not apply:
            self.stdout.write(self.style.NOTICE("Dry run — add --apply to execute."))
            return

        shipment_ids_touched: set[int] = set()

        with transaction.atomic():
            for deal in deals:
                shipment_ids_touched.update(
                    LogisticsShipmentDeal.objects.filter(deal_id=deal.id).values_list(
                        "shipment_id", flat=True
                    )
                )
                self._purge_one_deal(deal)
                self.stdout.write(self.style.SUCCESS(f"Purged deal {deal.ref_number} (id={deal.id})"))

            if del_empty and shipment_ids_touched:
                for sid in sorted(shipment_ids_touched):
                    remaining = LogisticsShipmentDeal.objects.filter(shipment_id=sid).count()
                    if remaining == 0:
                        self._purge_orphan_shipment(sid)
                        self.stdout.write(
                            self.style.SUCCESS(f"Deleted orphan shipment id={sid}")
                        )

    def _purge_one_deal(self, deal):
        from logistics.models import (
            LogisticsDealItem,
            LogisticsPayment,
            LogisticsShipmentDeal,
            PurchaseInvoice,
            PurchaseInvoiceItem,
        )

        jids: set[int] = set()
        if deal.journal_id:
            jids.add(deal.journal_id)

        pay_q = LogisticsPayment.all_objects.filter(deal_id=deal.id)
        payment_ids = list(pay_q.values_list("id", flat=True))
        for jid in pay_q.exclude(journal_id__isnull=True).values_list("journal_id", flat=True):
            if jid:
                jids.add(jid)
        jids |= _collect_journal_ids_for_payment_ids(payment_ids)

        inv_q = PurchaseInvoice.objects.filter(deal_id=deal.id)
        invoice_ids = list(inv_q.values_list("id", flat=True))
        for jid in inv_q.exclude(journal_id__isnull=True).values_list("journal_id", flat=True):
            if jid:
                jids.add(jid)
        jids |= _collect_journal_ids_for_invoice_ids(invoice_ids)

        _null_all_journal_fks(jids)
        n = _delete_journal_headers(jids)
        if n:
            self.stdout.write(f"  Deleted {n} journal header(s), lines removed.")

        PurchaseInvoiceItem.objects.filter(invoice_id__in=invoice_ids).delete()
        inv_q.delete()

        for p in pay_q:
            p.hard_delete()

        for it in LogisticsDealItem.all_objects.filter(deal_id=deal.id):
            it.hard_delete()

        LogisticsShipmentDeal.objects.filter(deal_id=deal.id).delete()
        deal.hard_delete()

    def _purge_orphan_shipment(self, shipment_id: int):
        from logistics.models import (
            LogisticsShipment,
            LogisticsPayment,
            LogisticsClearance,
            LogisticsClearancePayment,
            PurchaseInvoice,
            PurchaseInvoiceItem,
        )

        ship = LogisticsShipment.all_objects.filter(pk=shipment_id).first()
        if not ship:
            return

        jids: set[int] = set()
        jids |= _collect_journal_ids_for_shipment(shipment_id)

        cpay = LogisticsClearancePayment.objects.filter(clearance__shipment_id=shipment_id)
        for jid in cpay.exclude(journal_id__isnull=True).values_list("journal_id", flat=True):
            if jid:
                jids.add(jid)

        apay = LogisticsPayment.all_objects.filter(shipment_id=shipment_id, deal_id__isnull=True)
        for jid in apay.exclude(journal_id__isnull=True).values_list("journal_id", flat=True):
            if jid:
                jids.add(jid)

        inv_ship = PurchaseInvoice.objects.filter(shipment_id=shipment_id)
        inv_ids = list(inv_ship.values_list("id", flat=True))
        for jid in inv_ship.exclude(journal_id__isnull=True).values_list("journal_id", flat=True):
            if jid:
                jids.add(jid)
        jids |= _collect_journal_ids_for_invoice_ids(inv_ids)

        clr = LogisticsClearance.objects.filter(shipment_id=shipment_id).first()
        if clr:
            jids |= set(
                JournalHeader.objects.filter(
                    reference_type="LOGISTICS_CLEARANCE_PAYMENT",
                    reference_id=clr.id,
                ).values_list("pk", flat=True)
            )

        _null_all_journal_fks(jids)
        _delete_journal_headers(jids)

        PurchaseInvoiceItem.objects.filter(invoice_id__in=inv_ids).delete()
        inv_ship.delete()

        for p in apay:
            p.hard_delete()

        LogisticsClearance.objects.filter(shipment_id=shipment_id).delete()
        ship.hard_delete()
