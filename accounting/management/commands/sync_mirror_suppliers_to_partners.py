from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from bridge.models import FirestoreMirrorDoc
from partners.models import Partner
from tenants.models import Tenant, Currency
from accounting.models import Account


def _map_supplier_type_to_partner_type(supplier_type: str | None) -> str:
    """
    Map frontend v2 supplier.type to SQL partner_type.
    """
    return {
        "shipping_agent": "FreightForwarder",
        # Best-effort guess: international trader tends to act as broker
        "international_trader": "CustomsBroker",
        "factory": "Supplier",
        "local_company": "Supplier",
        "service_provider": "Supplier",
    }.get(supplier_type or "factory", "Supplier")


class Command(BaseCommand):
    help = "Sync FirestoreMirrorDoc suppliers/* to SQL partners and trigger accounting auto-generation via signals."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=int,
            default=1,
            help="TenantID (single-tenant mode in this project).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="When set, actually create/update partners. Without it, runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        tenant_id: int = options["tenant"]
        dry_run: bool = not options["yes"]

        # In this project, Tenant primary key field name is TenantID.
        tenant = Tenant.objects.filter(TenantID=tenant_id).first() or Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant found."))
            return

        mirror_qs = FirestoreMirrorDoc.objects.filter(path__startswith="suppliers/")
        mirror_suppliers = list(mirror_qs)

        self.stdout.write(
            f"Found mirror suppliers: {len(mirror_suppliers)} (tenant={tenant.TenantID}). "
            f"Dry-run={dry_run}"
        )
        if not mirror_suppliers:
            return

        # used to show the intended placement
        # (signals enforce canonical mapping; we just display for clarity)
        expected_parent = {
            "Supplier": "2101",
            "Customer": "1103",
            "FreightForwarder": "2102",
            "CustomsBroker": "2103",
            "LocalTransporter": "2104",
        }

        created = 0
        updated = 0

        with transaction.atomic():
            for doc in mirror_suppliers:
                data = doc.data or {}

                supplier_type = data.get("type")
                partner_type = _map_supplier_type_to_partner_type(supplier_type)

                name = (data.get("tradeName") or "").strip() or (data.get("supplierId") or "").strip() or "New Partner"
                legal_name = (data.get("alias") or "").strip() or None

                phone = data.get("phone") or None
                email = data.get("email") or None

                opening_balance = data.get("openingBalance") or 0
                opening_balance_date = data.get("balanceDate") or None

                currency_code = data.get("currency") or None
                currency = None
                if currency_code:
                    currency = Currency.objects.filter(Code=currency_code).first()

                # De-dup rule (best-effort): name + partner_type + tenant
                existing = (
                    Partner.objects.filter(tenant=tenant, partner_type=partner_type, name__iexact=name)
                    .order_by("id")
                    .first()
                )

                payload = {
                    "name": name,
                    "legal_name": legal_name,
                    "partner_type": partner_type,
                    "phone": phone,
                    "email": email,
                    "opening_balance": opening_balance,
                    "opening_balance_date": opening_balance_date,
                    "currency": currency,
                }

                if existing:
                    if dry_run:
                        updated += 1
                        continue
                    for k, v in payload.items():
                        setattr(existing, k, v)
                    existing.save()
                    updated += 1
                else:
                    if dry_run:
                        created += 1
                        continue
                    Partner.objects.create(**payload, tenant=tenant)
                    created += 1

        # After creation/update, signals will generate linked accounts automatically.
        parent_code = expected_parent.get("Supplier", "2101")
        coa_parent = Account.objects.filter(tenant=tenant, code=parent_code).first()
        children_count = (
            Account.objects.filter(tenant=tenant, parent=coa_parent).count() if coa_parent else 0
        )

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[Dry-run] would create={created}, update={updated}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Created={created}, updated={updated}."))
            self.stdout.write(f"COA parent '{parent_code}' children now: {children_count} (for Supplier mapping)")

        self.stdout.write("Refresh the 'شجرة الحسابات' page to see the new accounts.")

