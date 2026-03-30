from django.urls import re_path

from .views import MapperView

urlpatterns = [
    re_path(r'^(?P<subpath>.+)/?$', MapperView.as_view()),
]
