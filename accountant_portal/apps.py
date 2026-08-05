from django.apps import AppConfig


class AccountantPortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accountant_portal"
    verbose_name = "بوابة المحاسب القانوني الخارجي"

    def ready(self):
        """التحام L3 الوحيد: تسجيل حارس قفل الفترة — بلا إشارات ولا مهام دورية."""
        from accountant_portal.guards import register_guards

        register_guards()
