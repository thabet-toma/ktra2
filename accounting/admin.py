from django.contrib import admin
from .models import Account, JournalHeader, JournalLine, AccountingAuditLog, FiscalPeriod

class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 1

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'parent', 'is_active', 'tenant')
    list_filter = ('account_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')

@admin.register(JournalHeader)
class JournalHeaderAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction_date', 'reference_type', 'is_posted', 'tenant')
    list_filter = ('is_posted', 'transaction_date', 'tenant')
    inlines = [JournalLineInline]

@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display = ('id', 'journal', 'account', 'debit', 'credit', 'tenant')
    list_filter = ('tenant',)

@admin.register(AccountingAuditLog)
class AccountingAuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'object_id', 'user', 'timestamp', 'tenant')
    list_filter = ('action', 'model_name', 'timestamp', 'tenant')
    readonly_fields = ('tenant', 'user', 'action', 'model_name', 'object_id', 'change_details', 'timestamp')

@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'status', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('name',)
