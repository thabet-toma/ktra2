# RFC: Attachments Model

> **Status:** RFC · 2026-05-25 (task6 P-K-5)
> **Decision:** **deferred** — owner input required.
> **Reference:** task6.md category V («نمط Attachments السيِّئ»).

## The problem

File attachments are currently scattered across **6 URL fields on 3 models**:

| Model | Field | Stored as |
|-------|-------|-----------|
| `LogisticsDeal` | `alibaba_link` | `CharField(500)` URL |
| `LogisticsPayment` | `bank_swift_image` | `CharField(500)` URL |
| `LogisticsPayment` | `supplier_confirmation_image` | `CharField(500)` URL |
| `LogisticsPayment` | `invoice_doc` | `CharField(500)` URL |
| `LogisticsPayment` | `claim_doc` | `CharField(500)` URL |
| `LogisticsShipment` | `bill_of_lading_file` | `CharField(500)` URL |
| `LogisticsShipment` | `airway_bill_file` | `CharField(500)` URL |
| `LogisticsShipment` | `tracking_link` | `CharField(500)` URL |

(That's 8 actually, not 6 — the original spec under-counted.)

## What this costs us

1. **No metadata.** We store the URL but not `filename`, `mime_type`, `size_bytes`, `uploaded_by`, `uploaded_at`. Reconstructing «who uploaded what when» requires reading Cloudinary's own logs.
2. **Single-file ceiling.** Each field holds exactly one URL. You can't attach two photos of a bank-swift screenshot, or three PDFs of an invoice.
3. **No cascade on delete.** Delete a `LogisticsShipment` and the Cloudinary blobs it pointed to live on as orphans forever. Eventually we pay for terabytes of dead files.
4. **No schema for new attachments.** Adding «certificate of origin» means adding a 9th URL column. Adding «customs broker stamp» means a 10th. We've quietly created a wide-table anti-pattern.

## Proposed shape

```python
class Attachment(models.Model):
    """Polymorphic attachment — any model can have many files."""
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=CASCADE)

    # Polymorphic owner
    content_type = models.ForeignKey(ContentType, on_delete=CASCADE)
    object_id = models.PositiveIntegerField()
    owner = GenericForeignKey('content_type', 'object_id')

    # Where the bytes live
    url = models.URLField(max_length=500)
    storage_provider = models.CharField(max_length=32, default='cloudinary')

    # What it is
    kind = models.CharField(max_length=64)   # 'bank_swift', 'bill_of_lading', ...
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()

    # Provenance
    uploaded_by = models.ForeignKey(User, on_delete=SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['tenant', 'kind']),
        ]
```

## Migration plan

1. Add the `Attachment` table.
2. Data migration: for every existing `*_link` / `*_file` / `*_image` / `*_doc` URL on the 3 owner models, create an `Attachment` row with `kind = '<field name>'` and the URL, leaving owner FKs intact.
3. Stop writing the old URL columns on creation paths — write `Attachment` instead.
4. Add a `@property` on each owner model that returns the URL for backwards-compat reads (e.g. `LogisticsShipment.bill_of_lading_file` returns `self.attachments.filter(kind='bill_of_lading_file').first().url`).
5. Eventually drop the old URL columns (separate migration after a release with the proxies in place).

## What this RFC does not propose

- Replacing Cloudinary with self-hosted storage. That's a separate decision.
- Indexing file contents for search. Out of scope.
- Versioning attachments (storing edit history). Out of scope.

## Why this is deferred

This is a multi-day migration touching three models and many UI surfaces (the deal form, the shipment form, the local-shipping form, etc.). It shouldn't be bundled into task6 — task6 already touches all of those. Open a dedicated task7 ticket once the import-flow editor is settled in production.
