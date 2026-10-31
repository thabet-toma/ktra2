from django.apps import AppConfig


class AccountingOfficeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounting_office"
    verbose_name = "مكتب المحاسبة"

    def ready(self):
        # سجلُّ «زبون المكتب» في `core` متاحٌ لكل عضو (نمط سجلّ المستند)، وبوّابته
        # هنا: مَن لا يرى الزبون لا يقرأ تاريخه. الطريقةُ الوحيدة المتاحة بلا أن
        # يستورد `core` هذا الموديول (عقود `.importlinter` تمنع الاتجاه المعاكس).
        from core.activity import register_document_history_guard

        register_document_history_guard("office_client", _client_history_visible)


def _client_history_visible(request, tenant, entity_id) -> bool:
    """هل يرى صاحبُ الطلب هذا الزبون؟ — `visible_clients` وحدها تقول."""
    from accounting_office import services

    try:
        entity_id = int(entity_id)
    except (TypeError, ValueError):
        # معرّفٌ غير رقميّ ليس زبوناً — يُحجب 404 بدل `ValueError` من الاستعلام.
        return False
    if tenant is None:
        return False
    return (
        services.visible_clients(tenant, getattr(request, "user", None))
        .filter(pk=entity_id)
        .exists()
    )
