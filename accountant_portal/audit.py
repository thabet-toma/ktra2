AUDIT_ACTION_CODES = frozenset(
    {
        "ENG_REQUESTED",
        "ENG_APPROVED",
        "ENG_DECLINED",
        "ENG_SUSPENDED",
        "ENG_RESUMED",
        "ENG_REVOKED",
        "ENG_SCOPE_SET",
        "TAX_PREPARED",
        "TAX_APPROVED",
        "TAX_SUBMITTED",
        "TAX_REOPENED",
        "TAX_LOCKED",
        "PKG_EXPORTED",
        "MODULE_TOGGLED",
        "PORTAL_CFG_SET",
        "OFFICE_MIGRATED",
    }
)


def write_financial_audit(*, tenant, user, action, model_name, object_id, change_details):
    """Write a mandatory audit row; callers keep this inside their business transaction."""
    if action not in AUDIT_ACTION_CODES:
        raise ValueError(f"Unknown accountant portal audit action: {action}")

    from accounting.models import AccountingAuditLog

    return AccountingAuditLog.objects.create(
        tenant=tenant,
        user=user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        change_details=change_details,
    )
