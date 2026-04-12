"""
Re-download HTTP(S) media URLs stored in SQL and upload them to Cloudinary,
then replace the stored URL with the new secure_url.

Use when old links (e.g. another Cloudinary account or expiring Firebase URLs)
may break. Put the **destination** Cloudinary credentials in the environment
(do not paste API secrets in chat):

  CLOUDINARY_REHOST_CLOUD_NAME
  CLOUDINARY_REHOST_API_KEY
  CLOUDINARY_REHOST_API_SECRET

If those are unset, falls back to CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET.

Dry-run (no DB writes, no uploads):
  python manage.py rehost_http_media_to_cloudinary --tenant 1

Execute:
  python manage.py rehost_http_media_to_cloudinary --tenant 1 --yes

Options:
  --limit N     Process at most N URLs (0 = all).
  --only-host x Only rows whose URL contains substring x (e.g. old cloud name).
"""

from __future__ import annotations

import hashlib
import io
import os
from typing import BinaryIO

import requests
from django.core.management.base import BaseCommand

from core.models import SystemAttachment
from logistics.models import LogisticsPayment
from partners.models import Partner
from tenants.models import Tenant


def _target_cloudinary_config():
    cloud = os.environ.get("CLOUDINARY_REHOST_CLOUD_NAME") or os.environ.get(
        "CLOUDINARY_CLOUD_NAME", ""
    )
    key = os.environ.get("CLOUDINARY_REHOST_API_KEY") or os.environ.get(
        "CLOUDINARY_API_KEY", ""
    )
    secret = os.environ.get("CLOUDINARY_REHOST_API_SECRET") or os.environ.get(
        "CLOUDINARY_API_SECRET", ""
    )
    return cloud.strip(), key.strip(), secret.strip()


def _is_http(u: str | None) -> bool:
    return isinstance(u, str) and u.startswith(("http://", "https://"))


def _public_id_for_url(url: str, prefix: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    safe_prefix = prefix.replace("/", "_")[:40]
    return f"rehost/{safe_prefix}/{h}"


def _guess_resource_type(url: str, content_type: str | None) -> str:
    ct = (content_type or "").lower()
    u = url.lower()
    if "pdf" in ct or u.endswith(".pdf"):
        return "raw"
    if ct.startswith("image/"):
        return "image"
    if any(u.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
        return "image"
    return "auto"


def _upload_to_cloudinary(
    cloud_name: str,
    api_key: str,
    api_secret: str,
    file_like: BinaryIO,
    resource_type: str,
    public_id: str,
) -> str | None:
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
    file_like.seek(0)
    result = cloudinary.uploader.upload(
        file_like,
        resource_type=resource_type,
        public_id=public_id,
        overwrite=True,
        invalidate=True,
    )
    return result.get("secure_url") or result.get("url")


def _fetch_url(url: str, timeout: int = 120) -> tuple[bytes, str | None]:
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; KTRA-rehost/1.0)",
            "Accept": "*/*",
        },
    )
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type")


class Command(BaseCommand):
    help = "Re-upload HTTP(S) URLs from SQL attachments/payments/partners to Cloudinary."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=1, help="TenantID")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Perform uploads and update SQL (default: dry-run).",
        )
        parser.add_argument("--limit", type=int, default=0, help="Max URLs to process (0=all).")
        parser.add_argument(
            "--only-host",
            type=str,
            default="",
            help="Only URLs containing this substring (e.g. res.cloudinary.com).",
        )

    def handle(self, *args, **options):
        tenant_id = int(options["tenant"])
        write = bool(options["yes"])
        limit = int(options["limit"] or 0)
        only_host = (options["only_host"] or "").strip().lower()

        cloud_name, api_key, api_secret = _target_cloudinary_config()
        if not all([cloud_name, api_key, api_secret]):
            self.stdout.write(
                self.style.ERROR(
                    "Missing Cloudinary target config. Set CLOUDINARY_REHOST_* "
                    "or CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET in .env."
                )
            )
            return

        tenant = Tenant.objects.filter(TenantID=tenant_id).first() or Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant."))
            return

        stats = {
            "processed": 0,
            "skipped_already_target": 0,
            "skipped_filter": 0,
            "failed": 0,
            "uploaded": 0,
        }

        def want_url(url: str) -> bool:
            if not _is_http(url):
                return False
            if only_host and only_host not in url.lower():
                stats["skipped_filter"] += 1
                return False
            if cloud_name and cloud_name in url:
                stats["skipped_already_target"] += 1
                return False
            return True

        def process_one(url: str, public_prefix: str, update_fn) -> None:
            if limit and stats["processed"] >= limit:
                return
            if not want_url(url):
                return
            stats["processed"] += 1
            if not write:
                self.stdout.write(f"[Dry-run] would rehost: {url[:80]}...")
                return
            try:
                content, ctype = _fetch_url(url)
                bio = io.BytesIO(content)
                rtype = _guess_resource_type(url, ctype)
                pid = _public_id_for_url(url, public_prefix)
                new_url = _upload_to_cloudinary(
                    cloud_name, api_key, api_secret, bio, rtype, pid
                )
                if not new_url:
                    stats["failed"] += 1
                    self.stdout.write(self.style.WARNING(f"No URL returned for {url[:60]}..."))
                    return
                update_fn(new_url)
                stats["uploaded"] += 1
                self.stdout.write(self.style.SUCCESS(f"OK {url[:50]}... -> {new_url[:60]}..."))
            except Exception as e:
                stats["failed"] += 1
                self.stdout.write(self.style.ERROR(f"FAIL {url[:70]}... | {e}"))

        # --- SystemAttachment ---
        atts = SystemAttachment.objects.filter(tenant=tenant).exclude(file_path="")
        for row in atts.iterator():
            if limit and stats["processed"] >= limit:
                break
            prefix = f"{row.related_table}_{row.related_id}_{row.id}"
            row_id = row.id

            def make_updater(pk=row_id):
                def _u(new_url: str):
                    SystemAttachment.objects.filter(pk=pk).update(
                        file_path=new_url[:500]
                    )

                return _u

            process_one(row.file_path or "", prefix, make_updater())

        # --- Partner.image_path ---
        for p in Partner.objects.filter(tenant=tenant).exclude(image_path="").iterator():
            if limit and stats["processed"] >= limit:
                break
            pid = p.id

            def make_partner_updater(partner_id=pid):
                def _u(new_url: str):
                    Partner.objects.filter(pk=partner_id).update(image_path=new_url[:512])

                return _u

            process_one(p.image_path or "", f"partner_{p.id}", make_partner_updater())

        # --- LogisticsPayment URL fields ---
        pay_qs = LogisticsPayment.objects.filter(deal__tenant=tenant)
        for pay in pay_qs.iterator():
            if limit and stats["processed"] >= limit:
                break
            pay_id = pay.id
            for field, maxlen in (
                ("bank_swift_image", 500),
                ("supplier_confirmation_image", 500),
                ("claim_doc", 255),
            ):
                val = getattr(pay, field, None)
                if not _is_http(val):
                    continue

                def make_pay_updater(pk=pay_id, fname=field, ml=maxlen):
                    def _u(new_url: str):
                        LogisticsPayment.objects.filter(pk=pk).update(
                            **{fname: new_url[:ml]}
                        )

                    return _u

                process_one(
                    val,
                    f"payment_{pay_id}_{field}",
                    make_pay_updater(),
                )

        action = "Finished" if write else "[Dry-run]"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: processed={stats['processed']}, uploaded={stats['uploaded']}, "
                f"failed={stats['failed']}, skipped_target_cloud={stats['skipped_already_target']}, "
                f"skipped_host_filter={stats['skipped_filter']}"
            )
        )
        if not write:
            self.stdout.write(self.style.WARNING("Re-run with --yes to upload and update SQL."))
