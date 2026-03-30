from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Inspect legacy Firebase (Firestore) top-level collections and show sample schemas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--credentials",
            type=str,
            default="serviceAccountKey.json",
            help="Path to Firebase service account JSON.",
        )
        parser.add_argument(
            "--max-docs-per-collection",
            type=int,
            default=20,
            help="Maximum number of docs to scan per collection for quick sampling.",
        )
        parser.add_argument(
            "--limit-collections",
            type=int,
            default=200,
            help="Maximum number of collections to iterate (safety guard).",
        )

    def handle(self, *args, **options):
        credentials_path = options["credentials"]
        max_docs = int(options["max_docs_per_collection"])
        limit_collections = int(options["limit_collections"])

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"firebase-admin not available: {e}"))
            return

        try:
            cred = credentials.Certificate(credentials_path)
            # Initialize once per process.
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to init Firebase admin SDK: {e}"))
            return

        collections = list(db.collections())[:limit_collections]
        if not collections:
            self.stdout.write(self.style.WARNING("No collections found (or insufficient permissions)."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(collections)} top-level collections (limited)."))

        for col in collections:
            col_id = getattr(col, "id", None) or str(col)
            docs = col.limit(max_docs).stream()
            docs_list = []
            keys_union = set()

            for doc in docs:
                try:
                    data = doc.to_dict() or {}
                    keys_union.update(data.keys())
                    docs_list.append((doc.id, data.keys()))
                except Exception:
                    continue

            sample_keys = sorted(list(keys_union))
            sample_count = len(docs_list)
            self.stdout.write(f"\n- {col_id}: sampled_docs={sample_count} keys={sample_keys[:30]}")

