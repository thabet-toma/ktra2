"""سيريالايزرات المتجر العام — قائمة بيضاء صريحة، لا `ModelSerializer`.

**لماذا `Serializer` صِرف:** `ModelSerializer` يشتقّ حقوله من النموذج، فحقلٌ
جديد على `Product` (تكلفة، هامش، رصيد فرع) قد يصير عاماً بمجرد إضافته إن سها
أحدٌ عن قائمة `fields`. هنا لا يملك السيريالايزر حقلاً لم يُصرَّح به سطراً
سطراً، فالنشر قرارٌ واعٍ دائماً — والحارس الآلي عليه
`store/tests/test_public_leakage.py` بمساواة مجموعة المفاتيح.

الطبقة الثانية في `store/views.py` (`published_products`): الرصيد الخام
والتكلفة لا يُحمَّلان من القاعدة أصلاً، فلا شيء لِيُسرَّب حتى لو أُضيف حقل.
"""
from rest_framework import serializers


class StoreProfileSerializer(serializers.Serializer):
    """بطاقة الشركة كما يراها زائر: مَن هي، وكيف يتواصل معها. لا أكثر."""

    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    logo_url = serializers.CharField(read_only=True, allow_null=True)
    phone = serializers.CharField(read_only=True, allow_null=True)
    address = serializers.CharField(read_only=True, allow_null=True)
    #: رمز العملة (أو رمزها الدولي) التي تُقرأ بها كل الأسعار في هذا المتجر.
    #: المنصة متعدّدة العملات والزائر خارج أي جلسة، فرقمٌ بلا عملة مُلتبِس.
    currency = serializers.CharField(read_only=True, allow_null=True)


class StoreProductSerializer(serializers.Serializer):
    """المنتج كما يُنشر للعالم — عشرة حقول، كلٌّ منها قرار.

    `price` و`availability` تأتيان annotations من الاستعلام لا من صفوف النموذج:
    السعر يُحسب بقاعدة واحدة (سعر المتجر إن وُجد، وإلا سعر البيع) والتوفّر حالةٌ
    نصّية. الرقم الخام للرصيد لا يُحمَّل ولا يُشتقّ منه شيء في بايثون.
    """

    id = serializers.IntegerField(read_only=True)
    name_ar = serializers.CharField(read_only=True, allow_null=True)
    name_en = serializers.CharField(read_only=True, allow_null=True)
    brand = serializers.CharField(read_only=True, allow_null=True)
    category_name = serializers.CharField(
        source="category.name", read_only=True, allow_null=True)
    uom_name = serializers.CharField(
        source="uom.name_ar", read_only=True, allow_null=True)
    price = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True, allow_null=True)
    availability = serializers.CharField(read_only=True)
    description = serializers.CharField(
        source="online_description", read_only=True, allow_null=True)
    images = serializers.SerializerMethodField()

    def get_images(self, obj):
        """روابط صور المنتج — من خريطة مجهّزة باستعلام واحد للصفحة كلها.

        غياب الخريطة يعني «لا صور» لا استعلاماً إضافياً: N+1 على أوسع سطح عام
        هو بالضبط ما يُسقط الـworkers الثلاثة (درس P0-8).
        """
        return self.context.get("images", {}).get(obj.id, [])
