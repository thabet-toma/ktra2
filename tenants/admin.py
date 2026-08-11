from django.contrib import admin
from .models import Currency, Tenant, WhatsAppContact


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("CurrencyID", "Code", "Name", "Symbol", "IsBaseCurrency")
    search_fields = ("Code", "Name")
    list_filter = ("IsBaseCurrency",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('CompanyName', 'SubscriptionPlan', 'Status', 'CreatedAt')
    search_fields = ('CompanyName', 'DomainName')


@admin.register(WhatsAppContact)
class WhatsAppContactAdmin(admin.ModelAdmin):
    """إدارة الأرقام المصرَّح لها بمحادثة المساعد الذكي عبر واتساب.

    هذا هو المكان الوحيد لإضافة/تعطيل رقم — لا صلاحية بلا سطر هنا.
    """
    list_display = ('phone_number', 'tenant', 'label', 'is_active', 'created_at')
    list_filter = ('is_active', 'tenant')
    search_fields = ('phone_number', 'label', 'tenant__CompanyName')
    autocomplete_fields = ['tenant']
