from django.contrib import admin

from .models import AssistantLesson


@admin.register(AssistantLesson)
class AssistantLessonAdmin(admin.ModelAdmin):
    """مراجعة وتفعيل دروس المساعد — الدرس لا يؤثر على الردود إلا بعد تفعيله هنا."""

    list_display = ('text', 'is_active', 'source', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('text', 'source')
    list_editable = ('is_active',)
