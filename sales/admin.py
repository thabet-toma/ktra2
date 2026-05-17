from django.contrib import admin

from .models import CustomerPayment, DeliveryOrder, PaymentAllocation, SalesInvoice, SalesInvoiceLine


class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 0


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "invoice_date", "status", "grand_total")
    list_filter = ("status", "invoice_type")
    inlines = [SalesInvoiceLineInline]


@admin.register(DeliveryOrder)
class DeliveryOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "invoice", "status", "delivered_at")


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "partner", "payment_date", "amount", "is_posted")


admin.site.register(PaymentAllocation)
