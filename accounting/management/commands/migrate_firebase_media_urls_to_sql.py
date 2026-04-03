"""
Pull image/document URLs from legacy Firebase (items, deals, suppliers)
into SQL: SystemAttachment + Partner.image_path.

Run after main SQL migration so Product/Partner/LogisticsDeal rows exist.

Usage:
  python manage.py migrate_firebase_media_urls_to_sql --credentials serviceAccountKey.json --tenant 1 --yes
  python manage.py migrate_firebase_media_urls_to_sql --tenant 1   # dry-run counts only
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from bridge.models import FirestoreMirrorDoc
from core.models import SystemAttachment
from inventory.models import Product
from logistics.models import LogisticsDeal
from partners.models import Partner
from tenants.models import Tenant


def _truncate(s: str, max_len: int) -> str:
    if not s:
        return ""
    s = str(s).strip()
    return s[:max_len] if len(s) > max_len else s


def _is_http_url(v) -> bool:
    return isinstance(v, str) and v.startswith(("http://", "https://"))


def _attach_product_url(tenant, product_id: int, url: str, file_type: str, stats: dict, write: bool) -> None:
    url = _truncate(url, 500)
    if not url:
        return
    if SystemAttachment.objects.filter(
        tenant=tenant,
        related_table="products",
        related_id=product_id,
        file_path=url,
    ).exists():
        return
    if write:
        SystemAttachment.objects.create(
            tenant=tenant,
            related_table="products",
            related_id=product_id,
            file_path=url,
            file_type=_truncate(file_type, 50) or "Image",
        )
    stats["product_attachments"] += 1


def _attach_deal_url(tenant, deal_id: int, url: str, file_type: str, stats: dict, write: bool) -> None:
    url = _truncate(url, 500)
    if not url:
        return
    if SystemAttachment.objects.filter(
        tenant=tenant,
        related_table="logistics_deals",
        related_id=deal_id,
        file_path=url,
    ).exists():
        return
    if write:
        SystemAttachment.objects.create(
            tenant=tenant,
            related_table="logistics_deals",
            related_id=deal_id,
            file_path=url,
            file_type=_truncate(file_type, 50) or "Attachment",
        )
    stats["deal_attachments"] += 1


def _attach_partner_url(tenant, partner_id: int, url: str, file_type: str, stats: dict, write: bool) -> None:
    url = _truncate(url, 500)
    if not url:
        return
    if SystemAttachment.objects.filter(
        tenant=tenant,
        related_table="partners",
        related_id=partner_id,
        file_path=url,
    ).exists():
        return
    if write:
        SystemAttachment.objects.create(
            tenant=tenant,
            related_table="partners",
            related_id=partner_id,
            file_path=url,
            file_type=_truncate(file_type, 50) or "Logo",
        )
    stats["partner_attachments"] += 1


class Command(BaseCommand):
    help = "Copy Firebase media URLs into SQL attachments (products, deals, partners)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--credentials",
            type=str,
            default="serviceAccountKey.json",
            help="Firebase service account JSON path.",
        )
        parser.add_argument("--tenant", type=int, default=1, help="TenantID")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Actually write to SQL (default: dry-run).",
        )

    def handle(self, *args, **options):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"firebase-admin: {e}"))
            return

        cred_path = options["credentials"]
        tenant_id = int(options["tenant"])
        write = bool(options["yes"])

        tenant = Tenant.objects.filter(TenantID=tenant_id).first() or Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant."))
            return

        stats = {
            "product_attachments": 0,
            "deal_attachments": 0,
            "partner_logos": 0,
            "partner_attachments": 0,
            "products_missing": 0,
            "deals_missing": 0,
            "partners_missing": 0,
        }

        cred = credentials.Certificate(cred_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()

        def process_item_payload(item_id: str, data: dict):
            if not item_id:
                return
            sku = f"FB-{item_id}"[:50]
            product = Product.objects.filter(tenant=tenant, sku=sku).first()
            if not product:
                stats["products_missing"] += 1
                return
            urls = []
            for u in data.get("imageUrls") or data.get("image_urls") or []:
                if _is_http_url(u):
                    urls.append(u)
            fi = data.get("factoryImageUrl") or data.get("factory_image_url")
            if _is_http_url(fi):
                urls.append(fi)
            for i, u in enumerate(urls):
                _attach_product_url(tenant, product.id, u, f"Product Image {i + 1}", stats, write)

        # --- items collection ---
        for doc in db.collection("items").stream():
            process_item_payload(doc.id, doc.to_dict() or {})

        # --- embedded deal line items (covers items only referenced inside deals) ---
        for deal_doc in db.collection("deals").stream():
            d = deal_doc.to_dict() or {}
            for item in d.get("items") or []:
                item_id = str(item.get("itemId") or item.get("id") or "")
                if item_id:
                    process_item_payload(item_id, item)

            ref_number = d.get("dealNumber") or deal_doc.id
            sql_deal = LogisticsDeal.objects.filter(tenant=tenant, ref_number=ref_number).first()
            if not sql_deal:
                stats["deals_missing"] += 1
                continue

            for i, u in enumerate(d.get("quoteImages") or d.get("quote_images") or []):
                if _is_http_url(u):
                    _attach_deal_url(tenant, sql_deal.id, u, f"Quote Image {i + 1}", stats, write)
            for j, pdf in enumerate(d.get("quotePdfs") or d.get("quote_pdfs") or []):
                if isinstance(pdf, dict):
                    u = pdf.get("url") or pdf.get("URL")
                    name = pdf.get("name") or pdf.get("fileName") or f"quote-{j + 1}.pdf"
                else:
                    u, name = pdf, f"quote-{j + 1}.pdf"
                if _is_http_url(u):
                    _attach_deal_url(tenant, sql_deal.id, u, _truncate(f"Quote PDF: {name}", 50), stats, write)

            # Payment proof images on SQL payments (match by deal + order)
            payments_fb = d.get("payments") or []
            if write and payments_fb:
                sql_pays = list(sql_deal.payments.all().order_by("id"))
                for idx, p in enumerate(payments_fb):
                    if idx >= len(sql_pays):
                        break
                    sp = sql_pays[idx]
                    changed = False
                    swift = p.get("bankSwiftImage") or p.get("bank_swift_image")
                    conf = p.get("supplierConfirmationImage") or p.get("supplier_confirmation_image")
                    claim = p.get("alibabaClaimImage") or p.get("alibaba_claim_image")
                    if _is_http_url(swift) and not (sp.bank_swift_image or "").strip():
                        sp.bank_swift_image = _truncate(swift, 500)
                        changed = True
                    if _is_http_url(conf) and not (sp.supplier_confirmation_image or "").strip():
                        sp.supplier_confirmation_image = _truncate(conf, 500)
                        changed = True
                    if changed:
                        sp.save()
                        stats.setdefault("payment_images", 0)
                        stats["payment_images"] += 1

        # --- suppliers logos ---
        for sdoc in db.collection("suppliers").stream():
            data = sdoc.to_dict() or {}
            logo = data.get("logoUrl") or data.get("logo_url")
            if not _is_http_url(logo):
                continue
            name = (data.get("tradeName") or "").strip()
            if not name:
                continue
            partner = (
                Partner.objects.filter(tenant=tenant, partner_type="Supplier", name__iexact=name)
                .order_by("id")
                .first()
            )
            if not partner:
                stats["partners_missing"] += 1
                continue
            if write:
                path = _truncate(logo, 512)
                if partner.image_path != path:
                    partner.image_path = path
                    partner.save(update_fields=["image_path"])
                    stats["partner_logos"] += 1
                _attach_partner_url(tenant, partner.id, logo, "Logo", stats, write)

        # Mirror docs users/* — optional: skip (no product images there)

        action = "Wrote" if write else "[Dry-run] would process"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: product_attachments={stats['product_attachments']}, "
                f"deal_attachments={stats['deal_attachments']}, "
                f"partner_logos={stats['partner_logos']}, "
                f"partner_attach_attach={stats['partner_attachments']}, "
                f"missing_product={stats['products_missing']}, "
                f"missing_deal={stats['deals_missing']}, "
                f"missing_partner={stats['partners_missing']}"
                + (f", payment_image_updates={stats.get('payment_images', 0)}" if stats.get("payment_images") else "")
            )
        )
        if not write:
            self.stdout.write(self.style.WARNING("Re-run with --yes to write to SQL."))
