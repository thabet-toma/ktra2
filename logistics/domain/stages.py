"""The single, guarded deal stage machine (import redesign M0).

One canonical field — `LogisticsDeal.stage` — governs the pipeline position.
Every transition (manual UI click OR automated system advance from a signal)
goes through `advance_deal_stage`, which validates *and* writes. This kills the
RC-2/RC-7 defect where programmatic advances used bulk `.update()` to bypass the
FSM guard, so invalid states could arise and never be validated.

Legacy `shipping_workflow_status` still exists during the additive window; this
module maps between the two so nothing downstream breaks mid-migration.
"""
from __future__ import annotations

from typing import Optional

from django.core.exceptions import ValidationError

from logistics.models import LogisticsDeal as _Deal

# ── The canonical transition table ──────────────────────────────────────────
# Deal → Shipment → Clearance → [Transport] → Invoice → Closed, plus Cancel from
# any non-terminal. Backward edges exist where the UI genuinely allows undo
# (unlink from shipment, remove clearance) so the machine mirrors reality.
STAGE_TRANSITIONS = {
    None: [_Deal.STAGE_DRAFT, _Deal.STAGE_READY_TO_SHIP],
    _Deal.STAGE_DRAFT: [_Deal.STAGE_READY_TO_SHIP, _Deal.STAGE_CANCELLED],
    _Deal.STAGE_READY_TO_SHIP: [_Deal.STAGE_DRAFT, _Deal.STAGE_IN_SHIPMENT, _Deal.STAGE_CANCELLED],
    _Deal.STAGE_IN_SHIPMENT: [_Deal.STAGE_READY_TO_SHIP, _Deal.STAGE_AT_CLEARANCE, _Deal.STAGE_CANCELLED],
    _Deal.STAGE_AT_CLEARANCE: [_Deal.STAGE_IN_SHIPMENT, _Deal.STAGE_IN_TRANSPORT, _Deal.STAGE_INVOICED, _Deal.STAGE_CANCELLED],
    _Deal.STAGE_IN_TRANSPORT: [_Deal.STAGE_AT_CLEARANCE, _Deal.STAGE_INVOICED, _Deal.STAGE_CANCELLED],
    _Deal.STAGE_INVOICED: [_Deal.STAGE_CLOSED],
    _Deal.STAGE_CLOSED: [],
    _Deal.STAGE_CANCELLED: [],
}

# Deterministic backfill map: legacy shipping_workflow_status → canonical stage.
STAGE_FROM_WORKFLOW = {
    None: _Deal.STAGE_DRAFT,
    'sw_mfg_start': _Deal.STAGE_DRAFT,
    'sw_wait_agent_ship': _Deal.STAGE_DRAFT,
    'sw_wait_intl_ship': _Deal.STAGE_READY_TO_SHIP,
    'sw_wait_arrival': _Deal.STAGE_IN_SHIPMENT,
    'sw_wait_clearance': _Deal.STAGE_AT_CLEARANCE,
    'sw_released': _Deal.STAGE_INVOICED,
}

# Reverse map so the additive window keeps shipping_workflow_status in step when
# a new-model transition fires (dashboards/UI still read the legacy field).
WORKFLOW_FROM_STAGE = {
    _Deal.STAGE_DRAFT: 'sw_mfg_start',
    _Deal.STAGE_READY_TO_SHIP: 'sw_wait_intl_ship',
    _Deal.STAGE_IN_SHIPMENT: 'sw_wait_arrival',
    _Deal.STAGE_AT_CLEARANCE: 'sw_wait_clearance',
    _Deal.STAGE_IN_TRANSPORT: 'sw_wait_clearance',
    _Deal.STAGE_INVOICED: 'sw_released',
    _Deal.STAGE_CLOSED: 'sw_released',
    _Deal.STAGE_CANCELLED: None,
}


def derive_stage(deal) -> str:
    """Canonical stage for a deal, honoring an explicit Cancelled status."""
    if getattr(deal, 'status', None) == 'Cancelled':
        return _Deal.STAGE_CANCELLED
    if getattr(deal, 'stage', None):
        return deal.stage
    return STAGE_FROM_WORKFLOW.get(getattr(deal, 'shipping_workflow_status', None), _Deal.STAGE_DRAFT)


def can_transition(current: Optional[str], target: str) -> bool:
    return target in STAGE_TRANSITIONS.get(current, [])


def advance_deal_stage(deal, target: str, *, force: bool = False, save: bool = True) -> str:
    """Move `deal` to `target`, validating the edge unless force=True.

    Writes both the canonical `stage` and (during the additive window) the legacy
    `shipping_workflow_status`, so a single call keeps every consumer consistent.
    Idempotent: transitioning to the current stage is a no-op success.
    Returns the resulting stage.
    """
    current = derive_stage(deal)
    if current == target:
        return current
    if not force and not can_transition(current, target):
        allowed = STAGE_TRANSITIONS.get(current, [])
        raise ValidationError(
            f"انتقال مرحلة غير صالح: '{current}' → '{target}'. "
            f"المسموح: {allowed or 'لا انتقال (حالة نهائية)'}."
        )
    deal.stage = target
    legacy = WORKFLOW_FROM_STAGE.get(target, deal.shipping_workflow_status)
    if legacy is not None:
        deal.shipping_workflow_status = legacy
    if save:
        # Persist via bulk .update() to bypass the *legacy* shipping_workflow_status
        # guard (it forbids backward edges that the canonical machine allows, e.g.
        # unlink IN_SHIPMENT→READY_TO_SHIP). The canonical `stage` machine, validated
        # above, is now the authority. Same bypass pattern the old signals used —
        # but here it runs only after this module's own validation.
        _Deal.objects.filter(pk=deal.pk).update(
            stage=deal.stage, shipping_workflow_status=deal.shipping_workflow_status,
        )
        # Resync the denormalized cache columns (status/order_status/payment_status)
        # from the (now-updated) workflow + posted payments, reusing the single
        # existing helper so there is exactly one place that computes them.
        from logistics.signals import recalculate_deal_payment_status
        recalculate_deal_payment_status(deal.pk)
    return target
