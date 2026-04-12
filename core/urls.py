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

from core import assistant_views, agent_db_view, dashboard_api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/mapper/', include('bridge.urls')),
    path('api/assistant/chat/', assistant_views.assistant_chat),
    path('api/agent/query/', agent_db_view.agent_query),
    path('api/dashboard/', dashboard_api.trade_dashboard),
    path('api/', include('partners.urls')),
    path('api/accounting/', include('accounting.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/logistics/', include('logistics.urls')),
    path('api/hr/', include('hr.urls')),
]
