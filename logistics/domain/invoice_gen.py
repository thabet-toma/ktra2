"""Build/refresh the International (landed-cost) PurchaseInvoice from engine output.

M5 will consolidate the three legacy landed-cost code paths (import-time, live-on-
GET, explicit recompute) into this single module and add the backward-trace API.
For now it re-exports the existing landed_cost entry points so callers can migrate
imports to `logistics.domain.invoice_gen` incrementally without behaviour change.
"""
from __future__ import annotations

from logistics.landed_cost import (  # noqa: F401  (intentional re-export)
    import_invoices_from_clearance,
    preview_landed_import,
    recalculate_landed_for_shipment,
    compute_live_purchase_invoice_read_payload,
    build_import_trace,
)
