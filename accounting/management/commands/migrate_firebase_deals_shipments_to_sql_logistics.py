from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction

from bridge.models import FirestoreMirrorDoc
from partners.models import Partner
from tenants.models import Tenant, Currency
from accounting.models import Account
from logistics.models import (
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
)
from inventory.models import Product, ProductCategory, UnitOfMeasure


def _parse_date(v) -> datetime.date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # ISO with time (e.g. 2024-11-03T22:00:00.000Z)
        s = s.replace("Z", "+00:00")
        try:
            # handle yyyy-mm-dd or yyyy-mm-ddTHH:MM:SS+00:00
            return datetime.datetime.fromisoformat(s).date()
        except ValueError:
            pass
        try:
            return datetime.date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _to_decimal(v, default: Decimal = Decimal("0")) -> Decimal:
    if v is None or v == "":
        return default
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _truncate(v, max_len: int) -> str | None:
    if v is None:
        return None
    s = str(v)
    if not s:
        return None
    return s[:max_len]


def _pick(*values):
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _map_supplier_type_to_partner_type(supplier_type: str | None) -> str:
    # Keep consistent with partners/signals.py
    return {
        "shipping_agent": "FreightForwarder",
        "international_trader": "CustomsBroker",
        "factory": "Supplier",
        "local_company": "Supplier",
        "service_provider": "Supplier",
    }.get(supplier_type or "factory", "Supplier")


def _map_deal_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "Open"
    if "ship" in s:
        return "Shipped"
    if "clear" in s:
        return "Cleared"
    if "close" in s or "done" in s:
        return "Closed"
    if "cancel" in s:
        return "Cancelled"
    return "Open"


def _map_payment_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "Pending"
    if "paid" in s:
        return "Paid"
    if "confirm" in s:
        return "Confirmed"
    if "claim" in s:
        return "ClaimUploaded"
    return "Pending"


def _map_payment_status_from_payload(p: dict) -> str:
    """
    Legacy Firebase payments may not include `status`.
    Infer it from known timestamp fields.
    """
    confirmed_at = p.get("confirmedAt") or p.get("confirmed_at")
    confirmed_by = p.get("confirmedBy") or p.get("confirmed_by")
    claim_date = p.get("claimDate") or p.get("claim_date")
    payment_date = p.get("paymentDate") or p.get("payment_date")
    transfer_date = p.get("transferDate") or p.get("transfer_date")

    if confirmed_at or confirmed_by:
        return "Confirmed"
    if payment_date or transfer_date:
        return "Paid"
    if claim_date:
        return "ClaimUploaded"
    return _map_payment_status(p.get("status"))


def _map_shipment_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "Pending"
    if "draft" in s or "pending" in s:
        return "Pending"
    if "transit" in s:
        return "In-Transit"
    if "arriv" in s:
        return "Arrived"
    if "clear" in s or "customs" in s:
        return "Clearing"
    if "cleared" in s:
        return "Cleared"
    return "Pending"


class Command(BaseCommand):
    help = (
        "Migrate legacy Firebase deals + shipments + referenced items into SQL logistics tables.\n"
        "This also triggers accounting signals immediately (as per your choice) by keeping is_posted=False."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--credentials",
            type=str,
            default="serviceAccountKey.json",
            help="Firebase service account JSON path.",
        )
        parser.add_argument(
            "--tenant",
            type=int,
            default=1,
            help="TenantID (single-tenant mode).",
        )
        parser.add_argument(
            "--deals-limit",
            type=int,
            default=0,
            help="0 = all deals. Otherwise cap number of deals.",
        )
        parser.add_argument(
            "--shipments-limit",
            type=int,
            default=0,
            help="0 = all shipments. Otherwise cap number of shipments.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="When set, actually write to SQL. Without it, runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"firebase-admin init failed: {e}"))
            return

        cred_path: str = options["credentials"]
        tenant_id: int = int(options["tenant"])
        deals_limit: int = int(options["deals_limit"])
        shipments_limit: int = int(options["shipments_limit"])
        write: bool = bool(options["yes"])

        tenant = Tenant.objects.filter(TenantID=tenant_id).first() or Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant found."))
            return

        currency_ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.first()

        cred = credentials.Certificate(cred_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()

        partner_cache: dict[str, Partner] = {}
        product_cache: dict[str, Product] = {}
        category_cache: dict[tuple[int, str], ProductCategory] = {}
        deal_map: dict[str, LogisticsDeal] = {}

        created_deals = 0
        created_shipments = 0

        # --- helpers for creation/upsert ---
        def get_or_create_product(item_id: str, item_data: dict) -> Product:
            if item_id in product_cache:
                return product_cache[item_id]

            sku = f"FB-{item_id}"[:50]
            name_ar = item_data.get("name") or ""
            category_name = item_data.get("categoryName") or ""
            hs_code = item_data.get("hsCodePrimary") or item_data.get("hsCodeAlternative") or None

            if category_name:
                cat_key = (tenant_id, category_name)
                if cat_key in category_cache:
                    category = category_cache[cat_key]
                else:
                    category, _ = ProductCategory.objects.get_or_create(
                        tenant=tenant,
                        name=category_name,
                        defaults={},
                    )
                    category_cache[cat_key] = category
            else:
                category = None

            uom = None
            # UOM not available in legacy item doc reliably; keep nullable.

            product, _ = Product.objects.get_or_create(
                tenant=tenant,
                sku=sku,
                defaults={
                    "name_ar": name_ar,
                    "hs_code": hs_code,
                    "category": category,
                    "uom": uom,
                },
            )

            # Update some fields if exists.
            if write:
                changed = False
                if name_ar and product.name_ar != name_ar:
                    product.name_ar = name_ar
                    changed = True
                if hs_code and product.hs_code != hs_code:
                    product.hs_code = hs_code
                    changed = True
                if category and product.category_id != category.id:
                    product.category = category
                    changed = True
                if changed:
                    product.save()

            product_cache[item_id] = product
            return product

        def get_or_create_partner_from_supplier_doc(supplier_doc_id: str) -> Partner | None:
            if supplier_doc_id in partner_cache:
                return partner_cache[supplier_doc_id]

            supplier_doc = db.collection("suppliers").document(supplier_doc_id).get()
            if not supplier_doc.exists:
                return None
            data = supplier_doc.to_dict() or {}

            supplier_type = data.get("type")
            partner_type = _map_supplier_type_to_partner_type(supplier_type)
            name = (data.get("tradeName") or "").strip() or (data.get("supplierId") or "").strip() or supplier_doc_id

            # best-effort: match by name; if not found create
            partner = (
                Partner.objects.filter(tenant=tenant, partner_type=partner_type, name__iexact=name).first()
            )
            if not partner and write:
                partner = Partner.objects.create(
                    tenant=tenant,
                    name=name,
                    legal_name=(data.get("alias") or "").strip() or None,
                    partner_type=partner_type,
                    phone=data.get("phone") or None,
                    email=data.get("email") or None,
                    opening_balance=data.get("openingBalance") or 0,
                    opening_balance_date=_parse_date(data.get("balanceDate")),
                    currency=currency_ils,
                )

            if partner:
                partner_cache[supplier_doc_id] = partner
            return partner

        def get_currency_from_deal_or_default(d: dict):
            code = d.get("currency") or d.get("Currency") or None
            if code:
                cur = Currency.objects.filter(Code=str(code)).first()
                if cur:
                    return cur
            return currency_ils

        # --- migrate deals ---
        deal_q = db.collection("deals")
        if deals_limit and deals_limit > 0:
            # Firestore doesn't support limit() with stream easily in firebase-admin; we can just stream all
            pass

        deals_iter = deal_q.stream()
        for i, deal_doc in enumerate(deals_iter, start=1):
            if deals_limit and deals_limit > 0 and i > deals_limit:
                break

            d = deal_doc.to_dict() or {}
            supplier_doc_id = d.get("supplierId")
            if not supplier_doc_id:
                continue

            partner = get_or_create_partner_from_supplier_doc(str(supplier_doc_id))
            if not partner:
                continue

            ref_number = d.get("dealNumber") or deal_doc.id
            order_date = _parse_date(d.get("dealDate")) or datetime.date.today()
            total_amount = _to_decimal(d.get("totalAmount", 0))
            deal_status = _map_deal_status(d.get("status"))
            currency = get_currency_from_deal_or_default(d)
            original_offer_number = _truncate(
                _pick(
                    d.get("originalOfferNumber"),
                    d.get("offerNumber"),
                    d.get("dealTitle"),
                    d.get("title"),
                ),
                50,
            )
            supplier_invoice_number = _truncate(
                _pick(
                    d.get("supplierInvoiceNumber"),
                    d.get("piNumber"),
                    d.get("pi_number"),
                ),
                100,
            )
            factory_name = _truncate(
                _pick(
                    d.get("factoryName"),
                    d.get("supplierName"),
                    d.get("supplierTradeName"),
                ),
                255,
            )
            alibaba_link = _truncate(
                _pick(
                    d.get("alibabaOrderLink"),
                    d.get("alibabaLink"),
                    d.get("alibaba_link"),
                ),
                500,
            )
            description_val = _truncate(
                _pick(
                    d.get("description"),
                    d.get("internalNotes"),
                    d.get("shipmentNotes"),
                    ref_number,
                ),
                255,
            )
            notes_val = _pick(d.get("internalNotes"), d.get("notes"), d.get("description"))
            shipment_notes_val = d.get("shipmentNotes") or d.get("shippingNotes") or ""

            # Upsert by ref_number+partner
            existing = (
                LogisticsDeal.objects.filter(
                    tenant=tenant,
                    ref_number=ref_number,
                    partner=partner,
                    order_date=order_date,
                ).first()
            )

            if existing:
                deal_obj = existing
            else:
                if not write:
                    created_deals += 1
                    continue
                deal_obj = LogisticsDeal.objects.create(
                    tenant=tenant,
                    ref_number=ref_number,
                    partner=partner,
                    order_date=order_date,
                    total_amount=total_amount,
                    currency=currency,
                    status=deal_status,
                    description=description_val,
                    payment_method=_truncate(d.get("paymentMethod") or "T/T", 50) or "T/T",
                    incoterms=_truncate(d.get("incoterms") or "FOB", 10) or "FOB",
                    shipping_method=_truncate(d.get("shippingMethod") or "Sea", 50) or "Sea",
                    installment_plan_enabled=bool(d.get("installmentPlanEnabled") or False),
                    original_offer_number=original_offer_number,
                    supplier_invoice_number=supplier_invoice_number,
                    factory_name=factory_name,
                    alibaba_link=alibaba_link,
                    notes=notes_val,
                    shipment_notes=shipment_notes_val or None,
                    subtotal=_to_decimal(d.get("subtotal") or 0),
                    tax_rate=_to_decimal(d.get("taxRate") or 0),
                    tax_amount=_to_decimal(d.get("taxAmount") or 0),
                    tax_type="amount" if str(d.get("taxType") or "").strip().lower() == "amount" else "percentage",
                    shipping_cost_estimate=_to_decimal(d.get("shippingCost") or 0),
                    discount_amount=_to_decimal(d.get("discountAmount") or 0),
                    remaining_amount=_to_decimal(d.get("remainingAmount") or 0),
                    is_posted=False,
                )
                created_deals += 1

            if write:
                # Always backfill/refresh key columns for already-existing SQL deals.
                deal_obj.partner = partner
                deal_obj.order_date = order_date
                deal_obj.currency = currency
                deal_obj.status = deal_status
                deal_obj.payment_method = _truncate(d.get("paymentMethod") or deal_obj.payment_method or "T/T", 50) or "T/T"
                deal_obj.incoterms = _truncate(d.get("incoterms") or deal_obj.incoterms or "FOB", 10) or "FOB"
                deal_obj.shipping_method = _truncate(d.get("shippingMethod") or deal_obj.shipping_method or "Sea", 50) or "Sea"
                deal_obj.installment_plan_enabled = bool(d.get("installmentPlanEnabled") or False)

                if original_offer_number:
                    deal_obj.original_offer_number = original_offer_number
                if supplier_invoice_number:
                    deal_obj.supplier_invoice_number = supplier_invoice_number
                if factory_name:
                    deal_obj.factory_name = factory_name
                if alibaba_link:
                    deal_obj.alibaba_link = alibaba_link
                if description_val:
                    deal_obj.description = description_val
                if notes_val:
                    deal_obj.notes = notes_val
                if shipment_notes_val:
                    deal_obj.shipment_notes = shipment_notes_val

                deal_obj.subtotal = _to_decimal(d.get("subtotal") or deal_obj.subtotal or 0)
                deal_obj.tax_rate = _to_decimal(d.get("taxRate") or deal_obj.tax_rate or 0)
                deal_obj.tax_amount = _to_decimal(d.get("taxAmount") or deal_obj.tax_amount or 0)
                deal_obj.tax_type = "amount" if str(d.get("taxType") or deal_obj.tax_type or "").strip().lower() == "amount" else "percentage"
                deal_obj.shipping_cost_estimate = _to_decimal(d.get("shippingCost") or deal_obj.shipping_cost_estimate or 0)
                deal_obj.discount_amount = _to_decimal(d.get("discountAmount") or deal_obj.discount_amount or 0)
                deal_obj.remaining_amount = _to_decimal(d.get("remainingAmount") or deal_obj.remaining_amount or 0)
                deal_obj.save()

            # items
            items = d.get("items") or []
            total_calc = Decimal("0")
            for item in items:
                item_id = item.get("itemId") or item.get("id")
                if not item_id:
                    continue
                item_id = str(item_id)
                # Embedded deal-item already contains the fields we need (name/category/hs code).
                product = get_or_create_product(item_id, item)

                qty = _to_decimal(item.get("quantity") or 0)
                unit_price = _to_decimal(item.get("unitPrice") or item.get("unit_price") or 0)
                notes = item.get("specifications") or item.get("notes") or ""
                notes = _truncate(notes, 255)
                total_calc += qty * unit_price

                if write:
                    LogisticsDealItem.objects.update_or_create(
                        deal=deal_obj,
                        product=product,
                        defaults={
                            "quantity": qty,
                            "unit_price": unit_price,
                            "notes": notes if notes else None,
                        },
                    )

            if write:
                deal_obj.total_amount = total_calc if total_calc > 0 else deal_obj.total_amount
                deal_obj.save(update_fields=["total_amount"])

            # payments
            payments = d.get("payments") or []
            if payments and write:
                for p in payments:
                    amount = _to_decimal(p.get("amount") or 0)
                    transfer_date = _parse_date(p.get("transferDate") or p.get("transfer_date"))
                    conf_date = _parse_date(p.get("confirmationDate") or p.get("confirmation_date"))
                    due_date = _parse_date(p.get("dueDate") or p.get("due_date"))
                    status = _map_payment_status_from_payload(p)
                    payment_number = int(p.get("installmentNumber") or p.get("paymentNumber") or 1)

                    posted_payment = (
                        LogisticsPayment.objects.filter(
                            deal=deal_obj,
                            payment_number=payment_number,
                            is_posted=True,
                        )
                        .order_by("id")
                        .first()
                    )
                    existing_payment = (
                        LogisticsPayment.objects.filter(
                            deal=deal_obj, payment_number=payment_number
                        )
                        .order_by("id")
                        .first()
                    )

                    defaults = {
                        "title": _truncate(p.get("title") or f"Payment {deal_obj.ref_number}", 100)
                        or f"Payment {deal_obj.ref_number}"[:100],
                        "due_date": due_date,
                        "percentage": _to_decimal(p.get("percentage") or 0),
                        "amount": amount,
                        "amount_local": _to_decimal(p.get("amount_local") or p.get("amountLocal") or 0),
                        "status": status,
                        "transfer_date": transfer_date,
                        "confirmation_date": conf_date,
                        "notes": p.get("notes") or "",
                        "usd_to_ils": _to_decimal(p.get("usdToIls") or p.get("usd_to_ils") or 3.5),
                        "transfer_cost": _to_decimal(p.get("transferCost") or 0),
                        "bank_swift_image": p.get("bankSwiftImage") or None,
                        "supplier_confirmation_image": p.get("supplierConfirmationImage") or None,
                        "supplier_notes": p.get("supplierNotes") or None,
                        "confirmed_by_supplier": bool(p.get("confirmedBySupplier") or False),
                    }

                    target = posted_payment or existing_payment
                    if target:
                        # If already posted, keep its accounting references to avoid double-posting.
                        target.is_posted = bool(posted_payment is not None)
                        if posted_payment:
                            target.journal = posted_payment.journal
                            target.bank_account = posted_payment.bank_account

                        for k, v in defaults.items():
                            setattr(target, k, v)
                        target.save()
                    else:
                        LogisticsPayment.objects.create(
                            deal=deal_obj,
                            payment_number=payment_number,
                            is_posted=False,
                            journal=None,
                            bank_account=None,
                            **defaults,
                        )
                    # payment accounting signal will run only on create (when is_posted=False).

            # keep mapping
            if write:
                deal_map[deal_doc.id] = deal_obj

        if not write:
            self.stdout.write(self.style.WARNING(f"[Dry-run] Deals would be created/updated."))
            self.stdout.write(self.style.WARNING("Dry-run stops before writing shipments to keep mapping valid."))
            return

        # --- migrate shipments (requires deal_map) ---
        shipments_q = db.collection("shipments")
        shipments_iter = shipments_q.stream()
        for j, ship_doc in enumerate(shipments_iter, start=1):
            if shipments_limit and shipments_limit > 0 and j > shipments_limit:
                break

            sd = ship_doc.to_dict() or {}

            agent_id = sd.get("shippingAgentId")
            shipping_partner = None
            if agent_id:
                shipping_partner = get_or_create_partner_from_supplier_doc(str(agent_id))

            shipment_number = sd.get("shipmentNumber") or sd.get("agentShipmentNumber") or ship_doc.id
            shipment_number_clean = str(shipment_number)[:50]
            status = _map_shipment_status(sd.get("status") or (sd.get("shippingInfo") or {}).get("shipmentStatus", {}).get("status"))

            departure_date = _parse_date(sd.get("departureDate"))
            arrival_date = _parse_date(sd.get("arrivalDate"))
            ship_notes = sd.get("notes") or sd.get("shipmentNotes") or ""

            shipment_obj, created = LogisticsShipment.objects.get_or_create(
                tenant=tenant,
                shipment_number=shipment_number_clean,
                defaults={
                    "shipping_agent": shipping_partner,
                    "bill_of_lading": _truncate(
                        sd.get("billOfLadingNumber") or sd.get("bill_of_lading") or None, 100
                    ),
                    "container_number": _truncate(
                        sd.get("containerNumber") or sd.get("container_number") or None, 100
                    ),
                    "departure_date": departure_date,
                    "arrival_date": arrival_date,
                    "status": status,
                    "notes": ship_notes if ship_notes else None,
                    "remaining_amount": _to_decimal(sd.get("remainingAmount") or 0),
                    "total_shipping_cost_usd": _to_decimal(sd.get("totalShippingCostUsd") or 0),
                    "total_volume": _to_decimal(sd.get("totalVolume") or 0),
                    "total_weight_kg": _to_decimal(sd.get("totalWeightKg") or 0),
                    "shipping_type": _truncate(sd.get("shippingType") or sd.get("shipping_type") or "sea", 20)
                    or "sea",
                    "unit_type": sd.get("unitType") or sd.get("unit_type") or None,
                },
            )

            if write and not created:
                shipment_obj.shipping_agent = shipping_partner
                shipment_obj.status = status
                shipment_obj.departure_date = departure_date
                shipment_obj.arrival_date = arrival_date
                shipment_obj.notes = ship_notes if ship_notes else None
                shipment_obj.remaining_amount = _to_decimal(sd.get("remainingAmount") or 0)
                shipment_obj.total_shipping_cost_usd = _to_decimal(sd.get("totalShippingCostUsd") or 0)
                shipment_obj.total_volume = _to_decimal(sd.get("totalVolume") or 0)
                shipment_obj.total_weight_kg = _to_decimal(sd.get("totalWeightKg") or 0)
                shipment_obj.shipping_type = _truncate(
                    sd.get("shippingType") or sd.get("shipping_type") or "sea", 20
                ) or "sea"
                shipment_obj.unit_type = sd.get("unitType") or sd.get("unit_type") or None
                shipment_obj.save()

            deals = sd.get("deals") or []
            for rel in deals:
                deal_id = rel.get("dealId") or rel.get("id") or None
                if not deal_id:
                    continue
                deal_id = str(deal_id)
                deal_obj = deal_map.get(deal_id)
                if not deal_obj:
                    continue
                LogisticsShipmentDeal.objects.get_or_create(
                    shipment=shipment_obj,
                    deal=deal_obj,
                )

            if created:
                created_shipments += 1

        self.stdout.write(self.style.SUCCESS(f"Migration done. Deals created={created_deals}, Shipments created={created_shipments}"))

