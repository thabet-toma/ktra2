"""
Backfill stock from existing cleared shipments.

Usage:
    python manage.py backfill_stock          # dry-run
    python manage.py backfill_stock --apply  # actually write
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import Product, StockMovement
from logistics.models import LogisticsShipment, LogisticsShipmentDeal
from django.utils import timezone


class Command(BaseCommand):
    help = "Backfill stock movements from cleared shipments"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually apply changes (default is dry-run)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"\n=== backfill_stock ({mode}) ===\n")

        cleared = LogisticsShipment.objects.filter(status="Cleared")
        self.stdout.write(f"Found {cleared.count()} cleared shipments\n")

        total_created = 0
        total_skipped = 0

        for shipment in cleared:
            links = LogisticsShipmentDeal.objects.filter(
                shipment=shipment,
            ).select_related("deal", "deal__partner")

            for link in links:
                deal = link.deal
                items = deal.items.select_related("product").filter(is_deleted=False)

                for item in items:
                    existing = StockMovement.objects.filter(
                        reference_type="SHIPMENT",
                        reference_id=shipment.pk,
                        product=item.product,
                    ).exists()

                    if existing:
                        total_skipped += 1
                        continue

                    self.stdout.write(
                        f"  → {item.product.sku}: qty={item.quantity} "
                        f"cost={item.unit_price} "
                        f"(shipment #{shipment.shipment_number}, deal {deal.ref_number})"
                    )

                    if apply:
                        movement_date = (
                            shipment.arrival_date
                            or deal.order_date
                            or timezone.localdate()
                        )

                        with transaction.atomic():
                            prod = Product.objects.select_for_update().get(
                                pk=item.product.pk
                            )
                            qty = Decimal(str(item.quantity))
                            cost = Decimal(str(item.unit_price))
                            old_qty = Decimal(str(prod.quantity_on_hand))
                            old_avg = Decimal(str(prod.avg_cost))

                            new_qty = old_qty + qty
                            if new_qty > 0:
                                new_avg = (
                                    (old_qty * old_avg) + (qty * cost)
                                ) / new_qty
                            else:
                                new_avg = cost

                            new_qty = new_qty.quantize(Decimal("0.0001"))
                            new_avg = new_avg.quantize(Decimal("0.0001"))

                            StockMovement.objects.create(
                                tenant=deal.tenant,
                                product=prod,
                                movement_type="IN",
                                quantity=qty,
                                unit_cost=cost,
                                total_cost=(qty * cost).quantize(Decimal("0.01")),
                                reference_type="SHIPMENT",
                                reference_id=shipment.pk,
                                partner=deal.partner,
                                movement_date=movement_date,
                                notes=f"[backfill] شحنة {shipment.shipment_number} | صفقة {deal.ref_number}",
                                quantity_before=old_qty,
                                quantity_after=new_qty,
                                avg_cost_before=old_avg,
                                avg_cost_after=new_avg,
                            )

                            prod.quantity_on_hand = new_qty
                            prod.avg_cost = new_avg
                            prod.save(update_fields=["quantity_on_hand", "avg_cost"])

                    total_created += 1

        self.stdout.write(
            f"\n{'Created' if apply else 'Would create'}: {total_created} movements"
        )
        self.stdout.write(f"Skipped (already exist): {total_skipped}")
        self.stdout.write(self.style.SUCCESS("\nDone.\n"))
