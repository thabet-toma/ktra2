"""إشارات النظام المشتركة (Shared System Signals)."""
import django.dispatch

# تُطلق عند إضافة عضو لشركة أو تغيير دوره
# المعاملات: actor, membership, role_before, role_after, tenant, request
company_member_changed = django.dispatch.Signal()
