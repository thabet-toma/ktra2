"""سجل الأجهزة الحساسة (THA-45) — وحدة مرخّصة محايدة مالياً بالكامل.

لا حقل ولا علاقة هنا تشير إلى accounting / sales / inventory / logistics، ولا
تُنشئ الوحدة قيداً ولا حساباً ولا فاتورة. أجهزة هذه الوحدة **ملك الزبون** تدخل
للتوثيق والفحص والتسليم، فلم يُعَد استعمال `inventory.ProductSerial`: ذاك سجل
بضاعةٍ مملوكة يُنشأ من ترحيل الشراء ويُستهلك بترحيل البيع، مقيّدٌ بالتكلفة
والمخزون بحكم بنائه. ورود الـIMEI نفسه في الجدولين حالة مشروعة (بِعنا الهاتف ثم
استُقبل للتوثيق) — لا قيد بينهما، وتنبيه التكرار يقرأ هذا الجدول وحده.

الحذف ناعم دائماً (`deleted_at` + `deleted_by`) بلا أي مسار حذف نهائي — السجل
دليلٌ أمني. `objects` تُخفي المحذوف و`all_objects` تراه، و`base_manager_name`
يبقى `all_objects` كي لا يختفي الجهاز من سطر التدقيق المرتبط به بعد حذفه.
"""
import re

from django.core.exceptions import ValidationError
from django.db import models

from tenants.models import Tenant


_PHONE_RE = re.compile(r"^\+?\d{7,15}$")
_IMEI_RE = re.compile(r"^\d{15}$")


def normalize_phone(value: str) -> str:
    """يُسقط الفراغات والشرطات — النسخ من جهات الاتصال يأتي بها دائماً."""
    return re.sub(r"[\s\-]", "", (value or "").strip())


def validate_phone(value) -> None:
    """يتحقق بعد التطبيع، كي لا يُرفض «059-123 4567» وهو رقم صحيح."""
    if not _PHONE_RE.match(normalize_phone(value)):
        raise ValidationError(
            "رقم هاتف غير صالح — من 7 إلى 15 رقماً، مع مقدمة دولية اختيارية (+)."
        )


def imei_is_valid(imei: str) -> bool:
    """15 خانة رقمية تجتاز Luhn على الخانات كاملةً (mod 10 = 0)."""
    imei = (imei or "").strip()
    if not _IMEI_RE.match(imei):
        return False
    total = 0
    for index, char in enumerate(reversed(imei)):
        digit = int(char)
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def validate_imei(value) -> None:
    if not imei_is_valid(value):
        raise ValidationError(
            "رقم IMEI غير صالح — يجب أن يكون 15 خانة رقمية تجتاز خوارزمية Luhn."
        )


class SensitiveDeviceManager(models.Manager):
    """المدير الافتراضي يُخفي المحذوف ناعماً — لئلا يتسرّب سجلٌ محذوف إلى قائمة."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SensitiveDevice(models.Model):
    """جهاز زبون مسجَّل للتوثيق والتتبع الأمني — بلا أي أثر محاسبي."""

    STATUSES = [
        ("registered", "مسجَّل"),
        ("in_check", "في الفحص"),
        ("delivered", "تم التسليم"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="sensitive_devices",
    )
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=32, validators=[validate_phone])
    model_name = models.CharField(max_length=120)
    serial_number = models.CharField(max_length=100)
    imei = models.CharField(max_length=15, validators=[validate_imei])
    technical_notes = models.TextField(blank=True, default="")
    photo_url = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUSES, default="registered")
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="registered_sensitive_devices",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deleted_sensitive_devices",
    )

    objects = SensitiveDeviceManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "sensitive_devices"
        # المدير الأساسي غير مفلتر: علاقة سطر التدقيق بجهازٍ محذوف يجب أن تُحَل.
        base_manager_name = "all_objects"
        # لا قيد فرادة على IMEI: التكرار **تنبيه لا منع** (الجهاز نفسه قد يعود)،
        # وMySQL لا تدعم فرادةً شرطيةً تستثني المحذوف ناعماً — قيدٌ يكذب عليه
        # اختبار SQLite أسوأ من غيابه.
        indexes = [
            models.Index(fields=["tenant", "imei"], name="sens_dev_tenant_imei_idx"),
            models.Index(fields=["tenant", "serial_number"], name="sens_dev_tenant_sn_idx"),
            models.Index(fields=["tenant", "-created_at"], name="sens_dev_tenant_new_idx"),
        ]

    def __str__(self):
        return f"{self.model_name} — {self.imei}"


class DeviceAuditLog(models.Model):
    """تدقيق إلحاقي خاص بالوحدة: يشمل العرض والبحث، ولا يُعدَّل ولا يُحذف من أي طبقة.

    قيم `action` كلها ≤ 20 حرفاً بحكم التصميم — تجاوز طول العمود على MySQL يُسقِط
    المعاملة صامتاً واختبار SQLite لا يراه.
    """

    ACTIONS = [
        ("register", "تسجيل"),
        ("update", "تعديل"),
        ("status", "تغيير الحالة"),
        ("delete", "حذف"),
        ("restore", "استرجاع"),
        ("view", "عرض"),
        ("search", "بحث"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="device_audit_logs",
    )
    # فارغ لأحداث البحث — البحث حدثٌ على القائمة لا على جهاز بعينه.
    device = models.ForeignKey(
        SensitiveDevice, on_delete=models.CASCADE, null=True, blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTIONS)
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="device_audit_events",
    )
    details = models.JSONField(default=dict, blank=True)
    ip = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "device_audit_logs"
        indexes = [
            models.Index(fields=["tenant", "-created_at"], name="dev_audit_tenant_new_idx"),
        ]

    def __str__(self):
        return f"{self.action}#{self.device_id or '-'}"
