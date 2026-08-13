"""عدّاد مشاهدات المتجر — الجدول الوحيد الذي يكتبه مسارٌ مجهول في المنصة.

**لماذا جدول تجميع يومي لا عمود على `Product`:** صفّ المنتج يعيش في قلب الـERP
(المخزون والتسعير والفوترة تقرؤه وتقفله). كتابةُ زائرٍ مجهول عليه تعني قفل صفٍّ
ساخن مع كل فتحة صفحة، وتُدخِل مسارَ كتابة غيرَ مصادَقٍ عليه إلى جدولٍ تحرسه
قواعد المخزون. الفصل يجعل أسوأ حالةٍ للإساءة `UPDATE` واحداً على جدولٍ جانبي
لا يقرؤه أي مسار مالي.

**ولماذا يومي لا صفٌّ لكل مشاهدة:** الصفّ لكل مشاهدة ينمو بلا حدّ على أوسع
سطحٍ عام لدينا. التجميع اليومي هو الحبيبة التي يحتاجها فعلاً تقريرُ «الأكثر
مشاهدة» ومقارنةُ الأسعار لاحقاً (#60).
"""
from django.db import models

from inventory.models import Product
from tenants.models import Tenant


class StoreProductView(models.Model):
    """عدّاد مشاهدات صفحة منتج واحد في يوم واحد.

    يُكتب من `store/views.py` (`StoreProductDetailView`) وحده، بـ`F('count') + 1`
    ذرّي — لا قراءة ثم كتابة، فمشاهدتان متزامنتان لا تبتلع إحداهما الأخرى.
    وصفحة القائمة **لا** تكتب شيئاً: مشاهدة المنتج فتحُ صفحته لا مرورُه في شبكة.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="store_product_views",
        db_column="TenantID")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="store_views",
        db_column="ProductID")
    view_date = models.DateField(db_column="ViewDate")
    count = models.PositiveIntegerField(default=0, db_column="Count")

    class Meta:
        db_table = "store_product_views"
        managed = True
        # القيد هو ما يجعل الـupsert ذرّياً: سباقُ إنشاءٍ متزامن يُخفق بـIntegrity
        # فيسقط إلى `UPDATE … F('count') + 1` بدل أن يخلق صفّاً ثانياً لليوم نفسه.
        unique_together = [["tenant", "product", "view_date"]]

    def __str__(self):
        return f"{self.product_id} — {self.view_date}: {self.count}"
