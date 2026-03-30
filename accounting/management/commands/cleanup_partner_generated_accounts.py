from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from accounting.models import Account, JournalLine
from partners.models import Partner


class Command(BaseCommand):
    help = (
        "Delete old partner-generated chart accounts (child accounts under AR/AP parents) "
        "and re-sync current partners via signals."
    )

    # Parent accounts where partner child accounts are expected to live.
    PARTNER_PARENT_CODES = ["1103", "2101", "2102", "2103", "2104"]

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=int,
            default=1,
            help="TenantID to operate on (single-tenant mode in project).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Actually delete accounts. Without this flag it runs in dry-run mode.",
        )
        parser.add_argument(
            "--include-with-journals",
            action="store_true",
            help=(
                "If set, delete accounts even if they are referenced by JournalLine. "
                "Default is safer: only delete accounts with no journal lines."
            ),
        )
        parser.add_argument(
            "--resync-partners",
            action="store_true",
            default=False,
            help="After deletion, re-save partners with linked_account=NULL to trigger signal re-creation.",
        )

    def handle(self, *args, **options):
        tenant_id: int = options["tenant"]
        dry_run: bool = not options["yes"]
        include_with_journals: bool = options["include_with_journals"]
        resync_partners: bool = options["resync_partners"]

        # Candidate rule:
        # - code starts with one of parent codes
        # - code length should be 8: parent_code(4) + partner-id padded(4)
        # - and must be numeric after the parent code (best-effort using regex via DB)
        # Note: This is best-effort; we keep it narrow by also requiring no journal lines by default.
        q_parent_prefix = Q()
        for c in self.PARTNER_PARENT_CODES:
            q_parent_prefix |= Q(code__startswith=c)

        candidates_qs = (
            Account.objects.filter(tenant_id=tenant_id)
            .exclude(code__isnull=True)
            .exclude(code__exact="")
            .filter(q_parent_prefix)
        )

        # Narrow further: keep only 8-char codes
        # (Django's Length() not imported; we use a simple filter by code length via slicing not supported in ORM.)
        # We'll do filtering in Python after pulling minimal fields.
        candidates = list(candidates_qs.only("id", "code"))
        candidates = [a for a in candidates if a.code and len(a.code) == 8]

        if not candidates:
            self.stdout.write(self.style.WARNING("No candidate partner-generated accounts found."))
            return

        candidate_ids = [a.id for a in candidates]

        if not include_with_journals:
            used_by_journals = set(
                JournalLine.objects.filter(
                    tenant_id=tenant_id, account_id__in=candidate_ids
                ).values_list("account_id", flat=True)
            )
            candidates_to_delete = [a for a in candidates if a.id not in used_by_journals]
        else:
            candidates_to_delete = candidates

        delete_ids = [a.id for a in candidates_to_delete]

        self.stdout.write(
            f"Tenant={tenant_id} | Candidates={len(candidates)} | "
            f"ToDelete={len(delete_ids)} | include_with_journals={include_with_journals} | dry_run={dry_run}"
        )
        if delete_ids:
            sample = candidates_to_delete[:10]
            self.stdout.write("Sample codes to delete (up to 10): " + ", ".join([a.code for a in sample if a.code]))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run only. Re-run with --yes to delete."))
            return

        with transaction.atomic():
            if delete_ids:
                Account.objects.filter(id__in=delete_ids).delete()

            if resync_partners:
                # Trigger signal-driven re-creation for partners that lost their linked account.
                # (After Account deletion with FK on_delete=SET_NULL, linked_account becomes NULL.)
                partners = Partner.objects.filter(tenant_id=tenant_id, linked_account__isnull=True)
                total = partners.count()
                self.stdout.write(f"Resync partners with linked_account=NULL: {total}")
                # Saving each partner triggers post_save signal.
                for i, p in enumerate(partners.iterator(), start=1):
                    # Save without changing fields; still triggers post_save.
                    p.save()
                    if i % 50 == 0:
                        self.stdout.write(f"... resync progress: {i}/{total}")

        self.stdout.write(self.style.SUCCESS("Cleanup complete. Refresh the COA page to see the updated tree."))

