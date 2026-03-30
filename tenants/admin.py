from django.contrib import admin
from .models import Tenant

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('CompanyName', 'SubscriptionPlan', 'Status', 'CreatedAt')
    search_fields = ('CompanyName', 'DomainName')
