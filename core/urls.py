"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from core import (
    assistant_views, agent_db_view, dashboard_api, health, media_views,
    permissions_api, platform_admin_api, reports_api, scan, whatsapp_views,
)
from core.activity_views import ActivityLogViewSet
from core.platform_admin_api import DevelopmentNoteViewSet, PlatformRouter
from inventory import agent_api as inventory_agent_api
from partners import agent_api as partners_agent_api
from sales import agent_api as sales_agent_api

_activity_router = DefaultRouter()
_activity_router.register(r'', ActivityLogViewSet, basename='activity')
# راوتر المنصة بجذرٍ محروس — لا نقطة تحت `/api/platform/` تُقرأ بغير سوبر أدمن.
_platform_router = PlatformRouter()
_platform_router.register(
    r'development-notes', DevelopmentNoteViewSet, basename='platform-development-notes',
)

urlpatterns = [
    path('api/health/', health.health_check),
    path('api/activity/', include(_activity_router.urls)),
    path('api/client-logs/', health.client_logs),
    path('admin/', admin.site.urls),
    path('api/mapper/', include('bridge.urls')),
    path('api/media/upload/', media_views.media_upload),
    path('api/assistant/chat/', assistant_views.assistant_chat),
    path('api/assistant/files/', assistant_views.assistant_upload),
    path('api/assistant/openclaw-status/', assistant_views.assistant_openclaw_status),
    path('api/assistant/openclaw-ws-probe/', assistant_views.assistant_openclaw_ws_probe),
    path('api/assistant/whatsapp/webhook/<str:secret>/', whatsapp_views.whatsapp_webhook),
    # Evolution API يضيف اسم الحدث لآخر الرابط تلقائياً عند webhookByEvents=true
    # (إعداد عام بسيرفر Evolution، غير قابل للتحكم لكل instance) — **بلا شرطة مائلة
    # بالآخر** (تأكَّدنا من سجلات الإنتاج). لا نعتمد على تحويل APPEND_SLASH لأنه
    # يحوّل POST إلى GET ويُفقِد جسم الطلب — نطابق الشكل الحقيقي مباشرة، ونقبل
    # النسخة بشرطة مائلة أيضاً احتياطاً.
    path('api/assistant/whatsapp/webhook/<str:secret>/<str:event_suffix>', whatsapp_views.whatsapp_webhook),
    path('api/assistant/whatsapp/webhook/<str:secret>/<str:event_suffix>/', whatsapp_views.whatsapp_webhook),
    # واجهة الوكيل — المسارات ثابتة بحرفها (بوت خارجي يناديها)، لكن كل نقطة
    # تسكن في الـapp المالكة لبياناتها: `core` ممنوع من استيراد سيريالايزر app
    # آخر (`.importlinter`). وحدها `agent_query` تبقى في `core` — لا سيريالايزر
    # لها أصلاً، وحراستها superuser لا مفتاح (P0-2).
    path('api/agent/query/', agent_db_view.agent_query),
    path('api/agent/invoices/draft/', sales_agent_api.agent_create_draft_invoice),
    path('api/agent/invoices/draft/<int:pk>/', sales_agent_api.agent_draft_invoice_detail),
    path('api/agent/invoices/', sales_agent_api.agent_list_invoices),
    path('api/agent/last-price/', sales_agent_api.agent_last_price),
    path('api/agent/suppliers/', partners_agent_api.agent_suppliers),
    path('api/agent/customers/', partners_agent_api.agent_customers),
    path('api/agent/products/', inventory_agent_api.agent_products),
    # T-SCAN: «ما الذي في يدي؟» — نقطة واحدة تحلّ الباركود والسيريال والـIMEI
    # ورمز الصنف وجزء الاسم، بلا أن يختار المستخدم النوع.
    path('api/scan/', scan.scan_lookup),
    path('api/dashboard/', dashboard_api.trade_dashboard),
    # T-REPORTS: قسم التقارير — فهرس واحد ومشغّل واحد لكل تقارير المنصة.
    path('api/reports/', reports_api.reports_catalog),
    # التنقيب قبل التشغيل: `<str:key>` يبتلع «drill» لو جاء بعده،
    # فيُطلب تقريرٌ اسمه drill بدل فتح تفصيل السطر.
    path('api/reports/<str:key>/drill/', reports_api.report_drill),
    path('api/reports/<str:key>/', reports_api.report_run),
    path('api/platform/dashboard/', platform_admin_api.platform_dashboard),
    path('api/platform/super-admins/', platform_admin_api.platform_super_admins),
    path('api/platform/super-admins/<int:pk>/', platform_admin_api.platform_super_admin_detail),
    path('api/platform/companies/<int:pk>/', platform_admin_api.platform_company_detail),
    path('api/platform/companies/<int:pk>/modules/', platform_admin_api.platform_company_modules),
    path('api/platform/companies/<int:pk>/limits/', platform_admin_api.platform_company_limits),
    path('api/platform/companies/<int:pk>/activity/', platform_admin_api.platform_company_activity),
    path('api/platform/accountant-workspace/', platform_admin_api.platform_accountant_workspace),
    path('api/platform/accountants/pending/', platform_admin_api.platform_accountants_pending),
    path('api/platform/accountants/<int:profile_id>/verify/', platform_admin_api.platform_accountant_verify),
    path('api/platform/companies/<int:pk>/members/', platform_admin_api.platform_company_members),
    path('api/platform/companies/<int:pk>/members/<int:membership_id>/',
         platform_admin_api.platform_company_member_detail),
    path('api/platform/users/<int:pk>/set-active/', platform_admin_api.platform_user_set_active),
    path('api/platform/', include(_platform_router.urls)),
    # T-PERM: محرّك الصلاحيات (صلاحياتي + مصفوفة الأدوار لكل شركة)
    path('api/permissions/me/', permissions_api.my_permissions),
    path('api/permissions/roles/', permissions_api.permission_roles),
    path('api/permissions/matrix/', permissions_api.permissions_matrix),
    path('api/permissions/matrix/reset/', permissions_api.reset_permissions_matrix),
    path('api/permissions/members/', permissions_api.permission_members),
    path('api/permissions/member/', permissions_api.member_permissions),
    path('api/', include('partners.urls')),
    path('api/accounting/', include('accounting.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/logistics/', include('logistics.urls')),
    path('api/hr/', include('hr.urls')),
    path('api/realestate/', include('realestate.urls')),
    path('api/sales/', include('sales.urls')),
    path('api/accountant/', include('accountant_portal.urls')),
    # THA-45: وحدة الأجهزة الحساسة — كل نقطة خلفها ترد 404 لشركة غير مرخّصة.
    path('api/devices/', include('device_registry.urls')),
    # THA-24: خدمة ما بعد البيع — كل نقطة خلفها ترد 404 لشركة غير مرخّصة.
    path('api/after-sales/', include('after_sales.urls')),
    # THA-114: ملف الاستيراد — كل نقطة خلفها ترد 404 لشركة غير مرخّصة.
    path('api/import-file/', include('import_file.urls')),
    # N0-T4: Group Constants (F11) — tenant-level settings + books + currencies
    path('api/tenants/', include('tenants.urls')),
    # ST-1: المتجر العام — **كل** نقطة خلفه بلا مصادقة (`AllowAny`)، والشركة
    # تأتي من الـslug في المسار لا من ترويسة. مجموعة في app واحدة عمداً كي
    # يُقرأ سطحُ المنصة العام كاملاً في ملف واحد: `store/views.py`.
    path('api/store/', include('store.urls')),
]
