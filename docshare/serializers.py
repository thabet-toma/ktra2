"""سيريالايزر سطح الإدارة — ما يراه **المالك** عن رابطه، لا ما يراه الزائر.

الزائر لا يمرّ من هنا إطلاقاً: صفحته HTML تُبنى في `docshare/documents.py`
بقائمة بيضاء مستقلة. الفصل مقصود — خلطهما يجعل حقلاً إدارياً (من أنشأ الرابط،
كم مرة شوهد) قابلاً للتسرّب إلى الصفحة العامة بسطرٍ واحد.
"""
from rest_framework import serializers

from docshare import services
from docshare.models import DocumentShare


class DocumentShareSerializer(serializers.ModelSerializer):
    public_url = serializers.SerializerMethodField()
    is_live = serializers.BooleanField(read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DocumentShare
        # الحقول مُعدَّدة صراحةً لا `__all__`: حقلٌ جديد على النموذج لا يصير
        # مقروءاً بمجرد إضافته.
        fields = (
            "id", "doc_type", "doc_id", "token", "public_url",
            "expires_at", "revoked_at", "is_live",
            "view_count", "first_viewed_at", "last_viewed_at",
            "decision", "decided_at", "decided_name",
            "created_at", "created_by_name",
        )
        read_only_fields = fields

    def get_public_url(self, obj) -> str:
        return services.public_url(obj)

    def get_created_by_name(self, obj) -> str:
        user = obj.created_by
        if user is None:
            return ""
        return (user.get_full_name() or user.get_username() or "").strip()
