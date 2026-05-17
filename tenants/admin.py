from django.contrib import admin
from .models import Currency, Tenant


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("CurrencyID", "Code", "Name", "Symbol", "IsBaseCurrency")
    search_fields = ("Code", "Name")
    list_filter = ("IsBaseCurrency",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('CompanyName', 'SubscriptionPlan', 'Status', 'CreatedAt')
    search_fields = ('CompanyName', 'DomainName')
