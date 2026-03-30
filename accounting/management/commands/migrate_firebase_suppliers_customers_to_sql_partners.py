from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


def _map_supplier_type_to_partner_type(supplier_type: str | None) -> str:
    """
    Map legacy frontend v2 supplier.type to SQL partner_type.
    """
    return {
        "shipping_agent": "FreightForwarder",
        "international_trader": "CustomsBroker",
        "factory": "Supplier",
        "local_company": "Supplier",
        "service_provider": "Supplier",
    }.get(supplier_type or "factory", "Supplier")


class Command(BaseCommand):
    help = (
        "Migrate legacy Firebase Firestore suppliers/customers into SQL Partner records.\n"
        "Partner post_save signals will auto-generate linked accounting accounts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--credentials",
            type=str,
            default="serviceAccountKey.json",
            help="Path to Firebase service account JSON.",
        )
        parser.add_argument(
            "--tenant",
            type=int,
            default=1,
            help="TenantID (single-tenant mode).",
        )
        parser.add_argument(
            "--suppliers-limit",
            type=int,
            default=0,
            help="0 = migrate all. Otherwise cap number of supplier docs.",
        )
        parser.add_argument(
            "--customers-limit",
            type=int,
            default=0,
            help="0 = migrate all. Otherwise cap number of customer docs.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Actually write to SQL. Without --yes, runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"firebase-admin not available: {e}"))
            return

        credentials_path = options["credentials"]
        tenant_id = int(options["tenant"])
        suppliers_limit = int(options["suppliers_limit"])
        customers_limit = int(options["customers_limit"])
        write = bool(options["yes"])

        try:
            from tenants.models import Tenant, Currency
            from partners.models import Partner
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Import models failed: {e}"))
            return

        tenant = Tenant.objects.filter(TenantID=tenant_id).first() or Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant found. Create tenant first."))
            return

        cred = credentials.Certificate(credentials_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()

        def _currency(code: str | None):
            if not code:
                return None
            return Currency.objects.filter(Code=code).first()

        def _migrate_supplier_doc(sdoc_id: str, data: dict) -> tuple[bool, str]:
            supplier_type = data.get("type")
            partner_type = _map_supplier_type_to_partner_type(supplier_type)

            name = (data.get("tradeName") or "").strip() or (data.get("supplierId") or "").strip() or "New Partner"
            legal_name = (data.get("alias") or "").strip() or None
            phone = data.get("phone") or None
            email = data.get("email") or None

            opening_balance = data.get("openingBalance") or 0
            opening_balance_date = data.get("balanceDate") or None
            currency_code = data.get("currency") or None

            currency = _currency(currency_code)

            existing = (
                Partner.objects.filter(
                    tenant=tenant,
                    partner_type=partner_type,
                    name__iexact=name,
                )
                .order_by("id")
                .first()
            )

            payload = dict(
                name=name,
                legal_name=legal_name,
                partner_type=partner_type,
                phone=phone,
                email=email,
                opening_balance=opening_balance,
                opening_balance_date=opening_balance_date,
                currency=currency,
            )

            if existing:
                if not write:
                    return True, "would_update"
                for k, v in payload.items():
                    setattr(existing, k, v)
                existing.save()
                return True, "updated"

            if not write:
                return True, "would_create"
            Partner.objects.create(tenant=tenant, **payload)
            return True, "created"

        def _migrate_customer_doc(cdoc_id: str, data: dict) -> tuple[bool, str]:
            # Legacy customers collection represents SQL partner_type="Customer"
            partner_type = "Customer"

            name = (data.get("name") or "").strip() or cdoc_id
            legal_name = (data.get("notes") or "").strip() or None
            phone = data.get("phone") or None
            email = data.get("email") or None

            opening_balance = data.get("openingBalance") or 0
            opening_balance_date = data.get("openingBalanceDate") or data.get("balanceDate") or None
            currency_code = data.get("currency") or None

            currency = _currency(currency_code)

            existing = (
                Partner.objects.filter(
                    tenant=tenant,
                    partner_type=partner_type,
                    name__iexact=name,
                )
                .order_by("id")
                .first()
            )

            payload = dict(
                name=name,
                legal_name=legal_name,
                partner_type=partner_type,
                phone=phone,
                email=email,
                opening_balance=opening_balance,
                opening_balance_date=opening_balance_date,
                currency=currency,
            )

            if existing:
                if not write:
                    return True, "would_update"
                for k, v in payload.items():
                    setattr(existing, k, v)
                existing.save()
                return True, "updated"

            if not write:
                return True, "would_create"
            Partner.objects.create(tenant=tenant, **payload)
            return True, "created"

        # --- migrate suppliers ---
        supplier_col = db.collection("suppliers")
        supplier_q = supplier_col
        if suppliers_limit > 0:
            supplier_q = supplier_col.limit(suppliers_limit)

        suppliers_created = 0
        suppliers_updated = 0
        suppliers_would_create = 0
        suppliers_would_update = 0

        for doc in supplier_q.stream():
            data = doc.to_dict() or {}
            _, status = _migrate_supplier_doc(doc.id, data)
            if status == "created":
                suppliers_created += 1
            elif status == "updated":
                suppliers_updated += 1
            elif status == "would_create":
                suppliers_would_create += 1
            elif status == "would_update":
                suppliers_would_update += 1

        # --- migrate customers ---
        customer_col = db.collection("customers")
        customer_q = customer_col
        if customers_limit > 0:
            customer_q = customer_col.limit(customers_limit)

        customers_created = 0
        customers_updated = 0
        customers_would_create = 0
        customers_would_update = 0

        for doc in customer_q.stream():
            data = doc.to_dict() or {}
            _, status = _migrate_customer_doc(doc.id, data)
            if status == "created":
                customers_created += 1
            elif status == "updated":
                customers_updated += 1
            elif status == "would_create":
                customers_would_create += 1
            elif status == "would_update":
                customers_would_update += 1

        if write:
            self.stdout.write(self.style.SUCCESS("Migration completed."))
        else:
            self.stdout.write(self.style.WARNING("Dry-run completed (no DB writes)."))

        self.stdout.write(
            f"Suppliers: created={suppliers_created} updated={suppliers_updated} | "
            f"would_create={suppliers_would_create} would_update={suppliers_would_update} | "
            f"Customers: created={customers_created} updated={customers_updated} | "
            f"would_create={customers_would_create} would_update={customers_would_update}"
        )

